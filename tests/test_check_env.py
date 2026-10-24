"""The environment check script, driven by a fake command runner."""

import stat
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import check_env
from scripts.check_env import Output, Probe, Status

GB = 1024**3
JOURNAL_OK = (
    'level=INFO source=types.go:42 msg="inference compute" id=GPU-1 library=CUDA '
    'compute=12.0 name=CUDA0 description="NVIDIA GeForce RTX 5070 Ti" total="15.9 GiB"'
)
JOURNAL_FAILED = (
    'msg="server config" env="map[]"\n'
    "Error: mkdir /data/models/ollama: permission denied: ensure path elements are traversable"
)
GDBUS = """
  interface org.freedesktop.host.portal.Registry {
  interface org.freedesktop.portal.GlobalShortcuts {
"""
SOURCES = (
    "64\talsa_output.hdmi.monitor\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED\n"
    "69\talsa_input.usb-Generic_USB_Audio-00.HiFi__Mic__source\tPipeWire\ts24le\tSUSPENDED\n"
)

HEALTHY: dict[tuple[str, ...], Output] = {
    ("pacman", "-Qo", "/usr/bin/ollama"): Output(
        0, "/usr/bin/ollama is owned by ollama 0.40.8-1.1\n"
    ),
    ("pacman", "-Q", "ollama-cuda"): Output(0, "ollama-cuda 0.40.8-1.1\n"),
    ("ollama", "--version"): Output(0, "ollama version is 0.40.8\n"),
    ("systemctl", "is-active", "ollama"): Output(0, "active\n"),
    ("systemctl", "show", "ollama", "-p", "InvocationID", "--value"): Output(0, "abc123\n"),
    ("journalctl", "_SYSTEMD_INVOCATION_ID=abc123", "--no-pager", "-o", "cat"): Output(
        0, JOURNAL_OK
    ),
    (
        "nvidia-smi",
        "--query-gpu=name,driver_version,compute_cap,memory.total",
        "--format=csv,noheader",
    ): Output(0, "NVIDIA GeForce RTX 5070 Ti, 615.78.08, 12.0, 16303 MiB\n"),
    ("nvidia-smi",): Output(
        0, "| NVIDIA-SMI 615.78.08   KMD Version: 615.78.08   CUDA UMD Version: 13.4 |"
    ),
    ("plasmashell", "--version"): Output(0, "plasmashell 6.8.1\n"),
    ("pacman", "-Q", "xdg-desktop-portal"): Output(0, "xdg-desktop-portal 1.22.1-2.1\n"),
    (
        "gdbus",
        "introspect",
        "--session",
        "-d",
        "org.freedesktop.portal.Desktop",
        "-o",
        "/org/freedesktop/portal/desktop",
    ): Output(0, GDBUS),
    ("pactl", "get-default-source"): Output(
        0, "alsa_input.usb-Generic_USB_Audio-00.HiFi__Mic__source\n"
    ),
    ("pactl", "list", "sources", "short"): Output(0, SOURCES),
    ("ldconfig", "-p"): Output(
        0, "\tlibportaudio.so.2 (libc6,x86-64) => /usr/lib/libportaudio.so.2\n"
    ),
    ("pacman", "-Q", "obsidian"): Output(0, "obsidian 1.10.0-1\n"),
    ("xdg-mime", "query", "default", "x-scheme-handler/obsidian"): Output(0, "obsidian.desktop\n"),
    ("systemctl", "show", "ollama", "-p", "Environment", "--value"): Output(
        0, "HOME=/var/lib/ollama OLLAMA_MODELS=/var/lib/ollama OLLAMA_MODELS=/data/models/ollama\n"
    ),
}
ENV = {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE"}


class FakeRunner:
    """Answers commands from a table; missing entries behave as 'not installed'."""

    def __init__(self, table: dict[tuple[str, ...], Output]) -> None:
        self.table = table
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: Sequence[str]) -> Output | None:
        self.calls.append(tuple(args))
        return self.table.get(tuple(args))


def make_probe(
    overrides: dict[tuple[str, ...], Output | None] | None = None,
    *,
    env: dict[str, str] | None = None,
    free_gb: float = 500,
    which: str | None = "/usr/bin/ollama",
    files: list[Path] | None = None,
) -> Probe:
    table = dict(HEALTHY)
    for key, value in (overrides or {}).items():
        if value is None:
            table.pop(key, None)
        else:
            table[key] = value
    return Probe(
        run=FakeRunner(table),
        env=ENV if env is None else env,
        home=Path("/home/t"),
        free_bytes=lambda _path: int(free_gb * GB),
        find_files=lambda _folder, _pattern: files or [],
        which=lambda _name: which,
    )


def test_healthy_machine_is_all_ok() -> None:
    results = check_env.run_checks(make_probe())

    assert [check.name for _, check in results if check.status is Status.ATTENTION] == []
    assert check_env.render(results).endswith("Everything looks ready.")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ollama version is 0.40.8", (0, 40, 8)),
        ("Warning: client version is 0.20.0", (0, 20, 0)),
        ("1:19.7.0-4.1", (19, 7, 0)),
        ("plasmashell 6.8.1", (6, 8, 1)),
        ("no version here", None),
    ],
)
def test_parse_version(text: str, expected: tuple[int, ...] | None) -> None:
    assert check_env.parse_version(text) == expected


# Ollama --------------------------------------------------------------------


def test_ollama_missing() -> None:
    check = check_env.check_ollama_install(make_probe(which=None))

    assert check.status is Status.ATTENTION
    assert "isn't installed" in check.summary


def test_ollama_without_cuda_package() -> None:
    check = check_env.check_ollama_install(
        make_probe({("pacman", "-Q", "ollama-cuda"): Output(1, "")})
    )

    assert check.status is Status.ATTENTION
    assert check.fix == "sudo pacman -S ollama-cuda"


@pytest.mark.parametrize(
    ("path", "method"),
    [("/usr/local/bin/ollama", "official install script"), ("/opt/x/ollama", "unknown")],
)
def test_ollama_not_from_pacman(path: str, method: str) -> None:
    probe = make_probe({("pacman", "-Qo", path): Output(1, "")}, which=path)

    check = check_env.check_ollama_install(probe)

    assert check.status is Status.OK
    assert method in check.summary


def test_ollama_too_old() -> None:
    check = check_env.check_ollama_version(
        make_probe({("ollama", "--version"): Output(0, "ollama version is 0.19.9")})
    )

    assert check.status is Status.ATTENTION
    assert "0.19.9 is older than 0.20.0" in check.summary


def test_ollama_version_unreadable() -> None:
    check = check_env.check_ollama_version(make_probe({("ollama", "--version"): None}))

    assert check.status is Status.ATTENTION


def test_failed_service_shows_last_error() -> None:
    probe = make_probe(
        {
            ("systemctl", "is-active", "ollama"): Output(3, "failed\n"),
            ("ollama", "--version"): Output(
                0,
                "Warning: could not connect to a running Ollama instance\n"
                "Warning: client version is 0.40.8",
            ),
            ("journalctl", "-u", "ollama", "-b", "-n", "30", "--no-pager", "-o", "cat"): Output(
                0, JOURNAL_FAILED
            ),
        }
    )

    check = check_env.check_ollama_service(probe)

    assert check.status is Status.ATTENTION
    assert "failed" in check.summary
    assert check.details == (
        "Last error: Error: mkdir /data/models/ollama: permission denied: "
        "ensure path elements are traversable",
    )


def test_service_inactive_but_server_answering() -> None:
    probe = make_probe({("systemctl", "is-active", "ollama"): Output(3, "inactive\n")})

    assert check_env.check_ollama_service(probe).status is Status.OK


def test_service_down_without_logs() -> None:
    probe = make_probe(
        {
            ("systemctl", "is-active", "ollama"): None,
            ("ollama", "--version"): None,
        }
    )

    check = check_env.check_ollama_service(probe)

    assert check.status is Status.ATTENTION
    assert "unknown" in check.summary
    assert check.details == ()


def test_gpu_unknown_when_never_started() -> None:
    probe = make_probe(
        {
            ("journalctl", "_SYSTEMD_INVOCATION_ID=abc123", "--no-pager", "-o", "cat"): Output(
                0, JOURNAL_FAILED
            )
        }
    )

    check = check_env.check_ollama_gpu(probe)

    assert check.status is Status.ATTENTION
    assert "Can't tell yet" in check.summary


def test_gpu_detected_as_cuda() -> None:
    check = check_env.check_ollama_gpu(make_probe())

    assert check.status is Status.OK
    assert "RTX 5070 Ti" in check.summary


def test_gpu_on_cpu_library() -> None:
    line = 'msg="inference compute" id=cpu library=cpu'
    probe = make_probe(
        {
            ("journalctl", "_SYSTEMD_INVOCATION_ID=abc123", "--no-pager", "-o", "cat"): Output(
                0, line
            )
        }
    )

    check = check_env.check_ollama_gpu(probe)

    assert check.status is Status.ATTENTION
    assert "using cpu" in check.summary


# GPU -------------------------------------------------------------------------

NVIDIA_QUERY = (
    "nvidia-smi",
    "--query-gpu=name,driver_version,compute_cap,memory.total",
    "--format=csv,noheader",
)


def test_nvidia_old_banner_format_is_parsed() -> None:
    probe = make_probe(
        {("nvidia-smi",): Output(0, "| Driver Version: 570.1   CUDA Version: 12.8 |")}
    )

    assert check_env.check_nvidia(probe).status is Status.OK


def test_nvidia_missing() -> None:
    assert check_env.check_nvidia(make_probe({NVIDIA_QUERY: None})).status is Status.ATTENTION


def test_nvidia_wrong_arch_and_old_cuda() -> None:
    probe = make_probe(
        {
            NVIDIA_QUERY: Output(0, "NVIDIA GeForce RTX 3080, 535.1, 8.6, 10240 MiB\n"),
            ("nvidia-smi",): Output(0, "| CUDA Version: 12.2 |"),
        }
    )

    check = check_env.check_nvidia(probe)

    assert check.status is Status.ATTENTION
    assert check.summary == (
        "Compute capability is 8.6, expected 12.0; driver CUDA version 12.2 is below 12.8."
    )


def test_nvidia_cuda_version_unreadable() -> None:
    check = check_env.check_nvidia(make_probe({("nvidia-smi",): None}))

    assert check.status is Status.ATTENTION
    assert "unknown" in check.summary


# Desktop --------------------------------------------------------------------


@pytest.mark.parametrize(
    "env",
    [
        {"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "KDE"},
        {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"},
        {},
    ],
)
def test_session_not_plasma_wayland(env: dict[str, str]) -> None:
    assert check_env.check_session(make_probe(env=env)).status is Status.ATTENTION


def test_session_plasma_5_or_missing() -> None:
    old = make_probe({("plasmashell", "--version"): Output(0, "plasmashell 5.27.11")})
    missing = make_probe({("plasmashell", "--version"): None})

    assert check_env.check_session(old).status is Status.ATTENTION
    assert "not found" in check_env.check_session(missing).summary


def test_portal_too_old() -> None:
    probe = make_probe(
        {("pacman", "-Q", "xdg-desktop-portal"): Output(0, "xdg-desktop-portal 1.18.4-1")}
    )

    assert check_env.check_portal(probe).status is Status.ATTENTION


def test_portal_missing_interfaces() -> None:
    key = next(k for k in HEALTHY if k[0] == "gdbus")
    check = check_env.check_portal(make_probe({key: Output(0, "")}))

    assert check.status is Status.ATTENTION
    assert "Host app Registry: missing" in check.details
    assert "GlobalShortcuts portal: missing" in check.details


def test_portal_version_unknown() -> None:
    check = check_env.check_portal(make_probe({("pacman", "-Q", "xdg-desktop-portal"): None}))

    assert check.status is Status.ATTENTION
    assert "xdg-desktop-portal version unknown" in check.details


# Audio ----------------------------------------------------------------------


def test_line_in_default_is_flagged_with_case_kept() -> None:
    source = "alsa_input.usb-Generic_USB_Audio-00.HiFi__Line__source"
    check = check_env.check_audio(make_probe({("pactl", "get-default-source"): Output(0, source)}))

    assert check.status is Status.ATTENTION
    assert source in check.summary
    assert check.summary.startswith("The default input is a line-in")


def test_monitor_default_and_no_portaudio() -> None:
    probe = make_probe(
        {
            ("pactl", "get-default-source"): Output(0, "alsa_output.hdmi.monitor"),
            ("ldconfig", "-p"): Output(0, ""),
        }
    )

    check = check_env.check_audio(probe)

    assert check.status is Status.ATTENTION
    assert check.summary == "There's no default microphone; the PortAudio library is missing."
    assert "sudo pacman -S portaudio" in check.fix
    assert "Inputs: alsa_input.usb-Generic_USB_Audio-00.HiFi__Mic__source" in check.details


def test_audio_without_pulse_tools() -> None:
    probe = make_probe(
        {("pactl", "get-default-source"): None, ("pactl", "list", "sources", "short"): None}
    )

    check = check_env.check_audio(probe)

    assert check.status is Status.ATTENTION
    assert "Inputs: none" in check.details


# Obsidian -------------------------------------------------------------------

NO_PACMAN_OBSIDIAN: dict[tuple[str, ...], Output | None] = {
    ("pacman", "-Q", "obsidian"): Output(1, "")
}


def test_obsidian_flatpak() -> None:
    probe = make_probe(
        {
            **NO_PACMAN_OBSIDIAN,
            ("flatpak", "list", "--app", "--columns=application"): Output(
                0, "md.obsidian.Obsidian\n"
            ),
        }
    )

    check = check_env.check_obsidian(probe)

    assert check.status is Status.OK
    assert "Flatpak" in check.summary


def test_obsidian_appimage() -> None:
    image = Path("/home/t/Applications/Obsidian-1.10.0.AppImage")
    check = check_env.check_obsidian(make_probe(NO_PACMAN_OBSIDIAN, files=[image]))

    assert check.status is Status.OK
    assert str(image) in check.summary


def test_obsidian_missing() -> None:
    probe = make_probe(
        {
            **NO_PACMAN_OBSIDIAN,
            ("xdg-mime", "query", "default", "x-scheme-handler/obsidian"): Output(0, ""),
        }
    )

    check = check_env.check_obsidian(probe)

    assert check.status is Status.ATTENTION
    assert "Not installed" in check.summary
    assert "obsidian:// handler: not registered" in check.details


def test_obsidian_without_link_handler() -> None:
    probe = make_probe(
        {("xdg-mime", "query", "default", "x-scheme-handler/obsidian"): Output(0, "\n")}
    )

    check = check_env.check_obsidian(probe)

    assert check.status is Status.ATTENTION
    assert "aren't registered" in check.summary


# Disk -----------------------------------------------------------------------


def test_disk_low_space() -> None:
    check = check_env.check_disk(make_probe(free_gb=5))

    assert check.status is Status.ATTENTION
    assert check.summary == "Home has under 10 GB free; the models folder has under 25 GB free."


def test_models_folder_last_environment_line_wins_and_default() -> None:
    assert check_env._models_folder(make_probe()) == Path("/data/models/ollama")
    default = make_probe({("systemctl", "show", "ollama", "-p", "Environment", "--value"): None})
    assert check_env._models_folder(default) == Path("/home/t/.ollama/models")


def test_existing_walks_up_to_a_real_folder(tmp_path: Path) -> None:
    assert check_env._existing(tmp_path / "a" / "b") == tmp_path


# Report and runner -----------------------------------------------------------


def test_render_groups_sections_and_shows_fixes() -> None:
    results = check_env.run_checks(make_probe(free_gb=1))
    text = check_env.render(results)

    assert text.count("\nDisk\n") == 1
    assert "[Needs attention] Free disk space" in text
    assert text.endswith("1 of 10 checks need attention. Nothing has been changed.")


def test_runner_refuses_commands_off_the_allowlist() -> None:
    with pytest.raises(ValueError, match="not an allowlisted command"):
        check_env.run_command(["rm", "-rf", "/"])


def test_runner_reports_missing_program(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_env.shutil, "which", lambda *_a, **_k: None)

    assert check_env.run_command(["ollama", "--version"]) is None


def test_runner_runs_by_full_path_without_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "ollama"
    fake.write_text('#!/bin/sh\necho "args:$*"\nexit 3\n')
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(check_env.shutil, "which", lambda *_a, **_k: str(fake))

    output = check_env.run_command(["ollama", "--version; echo injected"])

    assert output == Output(3, "args:--version; echo injected\n", "")


def test_runner_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "ollama"
    fake.write_text("#!/bin/sh\nsleep 5\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(check_env.shutil, "which", lambda *_a, **_k: str(fake))
    monkeypatch.setattr(check_env, "_TIMEOUT_S", 0.1)

    output = check_env.run_command(["ollama"])

    assert output is not None
    assert output.code == 124


def test_main_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    healthy = check_env.run_checks(make_probe())
    unhealthy = check_env.run_checks(make_probe(free_gb=1))

    monkeypatch.setattr(check_env, "run_checks", lambda _probe: healthy)
    assert check_env.main() == 0
    monkeypatch.setattr(check_env, "run_checks", lambda _probe: unhealthy)
    assert check_env.main() == 1
    assert "Recon environment check" in capsys.readouterr().out


def test_default_file_and_program_lookups(tmp_path: Path) -> None:
    (tmp_path / "Obsidian-1.AppImage").touch()

    assert check_env.glob_files(tmp_path / "missing", "*") == []
    assert check_env.glob_files(tmp_path, "*AppImage") == [tmp_path / "Obsidian-1.AppImage"]
    assert check_env.find_program("definitely-not-a-program-xyz") is None


# Audit F-07 and F-16 -------------------------------------------------------------

_INACTIVE: dict[tuple[str, ...], Output | None] = {
    ("systemctl", "is-active", "ollama"): Output(3, "failed\n")
}


@pytest.mark.parametrize(
    ("version", "summary"),
    [
        (Output(124, "", "ollama timed out"), "didn't answer within 15 s"),
        (Output(1, "", "Error: something broke"), "Not running"),
        (Output(0, "Warning: client version is 0.40.8"), "Not running"),
        (Output(126, "", "ollama couldn't be run: Permission denied"), "Not running"),
    ],
)
def test_service_is_not_ok_unless_a_server_really_answers(version: Output, summary: str) -> None:
    check = check_env.check_ollama_service(
        make_probe({**_INACTIVE, ("ollama", "--version"): version})
    )

    assert check.status is Status.ATTENTION
    assert summary in check.summary


def test_server_answered_needs_a_clean_server_version() -> None:
    assert check_env.server_answered(Output(0, "ollama version is 0.40.8\n"))
    assert not check_env.server_answered(Output(1, "ollama version is 0.40.8\n"))
    assert not check_env.server_answered(
        Output(
            0,
            "Warning: could not connect to a running Ollama instance\n"
            "Warning: client version is 0.40.8",
        )
    )


def test_gpu_check_ignores_earlier_runs_without_an_invocation() -> None:
    probe = make_probe(
        {("systemctl", "show", "ollama", "-p", "InvocationID", "--value"): Output(0, "\n")}
    )

    check = check_env.check_ollama_gpu(probe)

    assert check.status is Status.ATTENTION
    assert "current run" in check.summary


@pytest.mark.parametrize("stdout", ["", "\n", "NVIDIA GeForce RTX 5070 Ti, 615.78.08\n"])
def test_nvidia_unreadable_output_is_reported_not_raised(stdout: str) -> None:
    check = check_env.check_nvidia(make_probe({NVIDIA_QUERY: Output(0, stdout)}))

    assert check.status is Status.ATTENTION
    assert check.summary == "Couldn't read nvidia-smi's output."


def test_runner_reports_a_program_it_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "ollama"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o644)  # found but not executable
    monkeypatch.setattr(check_env.shutil, "which", lambda *_a, **_k: str(fake))

    output = check_env.run_command(["ollama", "--version"])

    assert output is not None
    assert output.code == 126
    assert "couldn't be run" in output.stderr


def test_runner_replaces_undecodable_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "ollama"
    fake.write_bytes(b"#!/bin/sh\nprintf 'caf\\377'\n")
    fake.chmod(0o755)
    monkeypatch.setattr(check_env.shutil, "which", lambda *_a, **_k: str(fake))

    output = check_env.run_command(["ollama"])

    assert output is not None
    assert output.stdout == "caf\ufffd"


def test_busctl_is_no_longer_allowlisted() -> None:
    assert "busctl" not in check_env.ALLOWED_COMMANDS


_NO_MODELS_ENV: dict[tuple[str, ...], Output | None] = {
    ("systemctl", "show", "ollama", "-p", "Environment", "--value"): Output(
        0, "HOME=/var/lib/ollama\n"
    ),
}


def test_models_folder_defaults_to_the_service_users_home() -> None:
    probe = make_probe(
        {
            **_NO_MODELS_ENV,
            ("systemctl", "show", "ollama", "-p", "User", "--value"): Output(0, "ollama\n"),
        }
    )
    probe = replace(probe, home_of=lambda user: Path(f"/var/lib/{user}"))

    assert check_env._models_folder(probe) == Path("/var/lib/ollama/.ollama/models")


def test_unknown_service_user_makes_the_models_folder_unknown() -> None:
    probe = make_probe(
        {
            **_NO_MODELS_ENV,
            ("systemctl", "show", "ollama", "-p", "User", "--value"): Output(0, "ghost\n"),
        }
    )
    probe = replace(probe, home_of=lambda _user: None)

    check = check_env.check_disk(probe)

    assert check.status is Status.ATTENTION
    assert "Ollama models: folder unknown" in check.details


def test_user_home_lookup() -> None:
    assert check_env.user_home("root") == Path("/root")
    assert check_env.user_home("no-such-user-recon-test") is None
