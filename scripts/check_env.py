"""Check that this machine has what Recon needs, and say so in plain English.

Run with:
    uv run python scripts/check_env.py

Each check prints OK or "Needs attention" with a one-line fix. Nothing is
changed on the machine: the script only reads files and runs read-only
commands from a fixed allowlist, resolved by full path. It makes no network
calls of its own.

Exit code: 0 when everything is OK, 1 when anything needs attention.
"""

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

MIN_OLLAMA = (0, 20, 0)
"""Gemma 4 support arrived in Ollama v0.20.0; Qwen 3.5 support is older."""
MIN_PORTAL = (1, 20, 0)
"""xdg-desktop-portal 1.20 added the host Registry that unsandboxed apps need."""
MIN_CUDA = (12, 8)
"""Blackwell (sm_120) needs CUDA 12.8 or newer."""
BLACKWELL_COMPUTE = "12.0"
MIN_PLASMA_MAJOR = 6
MIN_MODELS_FREE_GB = 25
"""qwen3.5:9b + gemma4:12b + qwen3-embedding:0.6b are about 17 GB, plus headroom."""
MIN_HOME_FREE_GB = 10
"""Whisper large-v3-turbo (about 1.6 GB), the vault, backups and the venv."""

ALLOWED_COMMANDS = frozenset(
    {
        "busctl",
        "flatpak",
        "gdbus",
        "journalctl",
        "ldconfig",
        "nvidia-smi",
        "ollama",
        "pacman",
        "pactl",
        "plasmashell",
        "systemctl",
        "xdg-mime",
    }
)
_SEARCH_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
_TIMEOUT_S = 15
_GB = 1024**3


class Status(StrEnum):
    """Outcome of one check."""

    OK = "OK"
    ATTENTION = "Needs attention"


@dataclass(frozen=True, slots=True)
class Check:
    """One line of the report, with optional detail lines and a suggested fix."""

    name: str
    status: Status
    summary: str
    details: tuple[str, ...] = ()
    fix: str = ""


@dataclass(frozen=True, slots=True)
class Output:
    """Result of a command: exit code and combined text."""

    code: int
    stdout: str
    stderr: str = ""

    @property
    def text(self) -> str:
        """Stdout and stderr together, for tools that print to either."""
        return f"{self.stdout}\n{self.stderr}".strip()


type Runner = Callable[[Sequence[str]], Output | None]
"""Runs an allowlisted command; returns None when the program isn't installed."""


def run_command(args: Sequence[str]) -> Output | None:
    """Run an allowlisted, read-only command by full path with a timeout.

    Args:
        args: Program name followed by its arguments.

    Returns:
        The command's output, or None when the program isn't installed.

    Raises:
        ValueError: The program isn't on the allowlist.
    """
    name, *rest = args
    if name not in ALLOWED_COMMANDS:
        msg = f"{name} is not an allowlisted command"
        raise ValueError(msg)
    program = shutil.which(name, path=_SEARCH_PATH)
    if program is None:
        return None
    env = {"LC_ALL": "C", "PATH": _SEARCH_PATH, **_session_env()}
    try:
        done = subprocess.run(  # noqa: S603 - allowlisted program by full path, no shell
            [program, *rest],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Output(code=124, stdout="", stderr=f"{name} timed out")
    return Output(code=done.returncode, stdout=done.stdout, stderr=done.stderr)


def _session_env() -> dict[str, str]:
    # D-Bus and PipeWire clients need these to reach the user's session.
    keys = ("HOME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY")
    return {key: os.environ[key] for key in keys if key in os.environ}


def glob_files(folder: Path, pattern: str) -> list[Path]:
    """Files in `folder` matching `pattern`; empty when the folder doesn't exist."""
    return sorted(folder.glob(pattern)) if folder.is_dir() else []


def find_program(name: str) -> str | None:
    """Full path of `name` on the fixed search path, or None."""
    return shutil.which(name, path=_SEARCH_PATH)


@dataclass(frozen=True, slots=True)
class Probe:
    """Everything the checks read from the machine, injectable for tests."""

    run: Runner
    env: Mapping[str, str]
    home: Path
    free_bytes: Callable[[Path], int]
    which: Callable[[str], str | None] = field(default=find_program)
    find_files: Callable[[Path, str], list[Path]] = field(default=glob_files)


def parse_version(text: str) -> tuple[int, ...] | None:
    """Pull the first dotted version out of text, ignoring a pacman epoch.

    Args:
        text: Text such as "ollama version is 0.40.8" or "1:19.7.0-4.1".

    Returns:
        The version as a tuple of ints, or None when there isn't one.
    """
    match = re.search(r"(?:\d+:)?(\d+(?:\.\d+)+)", text)
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def _fmt(version: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in version)


def _sentence(parts: Sequence[str]) -> str:
    text = "; ".join(parts)
    return f"{text[:1].upper()}{text[1:]}."


def _ok(output: Output | None) -> Output | None:
    return output if output is not None and output.code == 0 else None


# --------------------------------------------------------------------------
# Ollama
# --------------------------------------------------------------------------


def check_ollama_install(probe: Probe) -> Check:
    """Where Ollama is installed, how, and whether the CUDA build is present."""
    name = "Ollama install"
    found = probe.which("ollama")
    if found is None:
        return Check(
            name, Status.ATTENTION, "Ollama isn't installed.", fix="sudo pacman -S ollama-cuda"
        )
    owner = _ok(probe.run(["pacman", "-Qo", found]))
    if owner is None:
        method = "official install script" if found.startswith("/usr/local/") else "unknown"
        return Check(name, Status.OK, f"{found}, installed by {method} (not a pacman package).")
    package = owner.stdout.split(" is owned by ")[-1].strip()
    cuda = _ok(probe.run(["pacman", "-Q", "ollama-cuda"]))
    details = (f"Binary: {found}", f"Package: {package}")
    if cuda is None:
        return Check(
            name,
            Status.ATTENTION,
            "Installed from pacman without the CUDA build, so models would run on the CPU.",
            details,
            fix="sudo pacman -S ollama-cuda",
        )
    return Check(name, Status.OK, f"pacman packages ollama and {cuda.stdout.strip()}.", details)


def check_ollama_version(probe: Probe) -> Check:
    """Ollama is new enough for the Qwen 3.5 and Gemma 4 families."""
    name = "Ollama version"
    output = probe.run(["ollama", "--version"])
    version = parse_version(output.text) if output else None
    if version is None:
        return Check(name, Status.ATTENTION, "Couldn't read Ollama's version.")
    if version < MIN_OLLAMA:
        return Check(
            name,
            Status.ATTENTION,
            f"{_fmt(version)} is older than {_fmt(MIN_OLLAMA)}, which Gemma 4 needs.",
            fix="Update Ollama (sudo pacman -Syu).",
        )
    return Check(name, Status.OK, f"{_fmt(version)} (needs {_fmt(MIN_OLLAMA)} or newer).")


def _service_error(probe: Probe) -> str:
    logs = _ok(
        probe.run(["journalctl", "-u", "ollama", "-b", "-n", "30", "--no-pager", "-o", "cat"])
    )
    errors = [line for line in (logs.stdout if logs else "").splitlines() if "Error" in line]
    return errors[-1].strip() if errors else ""


def check_ollama_service(probe: Probe) -> Check:
    """The Ollama server is running, and if not, the last error it logged."""
    name = "Ollama service"
    state_out = probe.run(["systemctl", "is-active", "ollama"])
    state = state_out.stdout.strip() if state_out else "unknown"
    if state == "active":
        return Check(name, Status.OK, "Running (systemd service ollama).")
    version = probe.run(["ollama", "--version"])
    if version is not None and "could not connect" not in version.text:
        return Check(name, Status.OK, "A server is answering, though not via the systemd service.")
    error = _service_error(probe)
    return Check(
        name,
        Status.ATTENTION,
        f"Not running (systemd says: {state}).",
        (f"Last error: {error}",) if error else (),
        fix="See the last error, fix its cause, then: sudo systemctl restart ollama",
    )


def check_ollama_gpu(probe: Probe) -> Check:
    """The running server found the GPU (from its start-up log)."""
    name = "Ollama on the GPU"
    logs = _ok(probe.run(["journalctl", "-u", "ollama", "-b", "--no-pager", "-o", "cat"]))
    lines = [
        line for line in (logs.stdout if logs else "").splitlines() if "inference compute" in line
    ]
    if not lines:
        return Check(
            name,
            Status.ATTENTION,
            "Can't tell yet: Ollama hasn't started successfully since boot.",
            fix="Re-run this check once the Ollama service is running.",
        )
    last = lines[-1]
    library = re.search(r"library=(\S+)", last)
    gpu = re.search(r'description="([^"]+)"', last)
    found = library.group(1) if library else "unknown"
    if found.lower() == "cuda":
        return Check(name, Status.OK, f"Using CUDA on {gpu.group(1) if gpu else 'the GPU'}.")
    return Check(
        name,
        Status.ATTENTION,
        f"Ollama is using {found}, not CUDA.",
        (last.strip(),),
        fix="Install ollama-cuda and restart the service.",
    )


# --------------------------------------------------------------------------
# GPU
# --------------------------------------------------------------------------


def check_nvidia(probe: Probe) -> Check:
    """Driver, CUDA version and compute capability 12.0 (Blackwell)."""
    name = "NVIDIA driver and CUDA"
    query = _ok(
        probe.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,compute_cap,memory.total",
                "--format=csv,noheader",
            ]
        )
    )
    if query is None:
        return Check(name, Status.ATTENTION, "nvidia-smi isn't available or found no GPU.")
    gpu, driver, compute, memory = (
        part.strip() for part in query.stdout.splitlines()[0].split(",")
    )
    banner = probe.run(["nvidia-smi"])
    cuda_match = re.search(r"CUDA (?:UMD )?Version:\s*([\d.]+)", banner.stdout if banner else "")
    cuda = parse_version(cuda_match.group(1)) if cuda_match else None
    cuda_shown = _fmt(cuda) if cuda else "unknown"
    details = (f"{gpu}, {memory}", f"Driver {driver}, compute capability {compute}")
    problems = []
    if compute != BLACKWELL_COMPUTE:
        problems.append(f"compute capability is {compute}, expected {BLACKWELL_COMPUTE}")
    if cuda is None or cuda < MIN_CUDA:
        problems.append(f"driver CUDA version {cuda_shown} is below {_fmt(MIN_CUDA)}")
    if problems:
        return Check(name, Status.ATTENTION, _sentence(problems), details)
    return Check(name, Status.OK, f"Driver {driver}, CUDA {cuda_shown}, Blackwell (12.0).", details)


# --------------------------------------------------------------------------
# Desktop
# --------------------------------------------------------------------------


def check_session(probe: Probe) -> Check:
    """Wayland session on KDE Plasma 6."""
    name = "Desktop session"
    session = probe.env.get("XDG_SESSION_TYPE", "")
    desktop = probe.env.get("XDG_CURRENT_DESKTOP", "")
    plasma_out = probe.run(["plasmashell", "--version"])
    plasma = parse_version(plasma_out.text) if plasma_out else None
    summary = f"{session or 'unknown'} session, {desktop or 'unknown desktop'}, Plasma "
    summary += _fmt(plasma) if plasma else "not found"
    if (
        session != "wayland"
        or "KDE" not in desktop
        or plasma is None
        or plasma[0] < MIN_PLASMA_MAJOR
    ):
        return Check(name, Status.ATTENTION, summary + ". Recon expects Plasma 6 on Wayland.")
    return Check(name, Status.OK, summary + ".")


def check_portal(probe: Probe) -> Check:
    """xdg-desktop-portal is 1.20+, with the host Registry and GlobalShortcuts."""
    name = "Desktop portal"
    package = _ok(probe.run(["pacman", "-Q", "xdg-desktop-portal"]))
    version = parse_version(package.stdout.split()[-1]) if package else None
    introspect = probe.run(
        [
            "gdbus",
            "introspect",
            "--session",
            "-d",
            "org.freedesktop.portal.Desktop",
            "-o",
            "/org/freedesktop/portal/desktop",
        ]
    )
    interfaces = introspect.stdout if introspect else ""
    registry = "org.freedesktop.host.portal.Registry" in interfaces
    shortcuts = "org.freedesktop.portal.GlobalShortcuts" in interfaces
    details = (
        f"xdg-desktop-portal {_fmt(version) if version else 'version unknown'}",
        f"Host app Registry: {'available' if registry else 'missing'}",
        f"GlobalShortcuts portal: {'available' if shortcuts else 'missing'}",
    )
    if version is None or version < MIN_PORTAL or not registry or not shortcuts:
        return Check(
            name,
            Status.ATTENTION,
            f"Hold-to-talk needs xdg-desktop-portal {_fmt(MIN_PORTAL)}+ with both interfaces.",
            details,
            fix="sudo pacman -Syu xdg-desktop-portal xdg-desktop-portal-kde",
        )
    return Check(name, Status.OK, f"{_fmt(version)}, with Registry and GlobalShortcuts.", details)


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------


def check_audio(probe: Probe) -> Check:
    """A sensible default microphone, and the PortAudio library sounddevice needs."""
    name = "Audio input"
    default = probe.run(["pactl", "get-default-source"])
    source = default.stdout.strip() if default and default.code == 0 else ""
    sources = probe.run(["pactl", "list", "sources", "short"])
    inputs = [
        line.split("\t")[1]
        for line in (sources.stdout if sources else "").splitlines()
        if "\t" in line and not line.split("\t")[1].endswith(".monitor")
    ]
    libraries = probe.run(["ldconfig", "-p"])
    portaudio = "libportaudio.so.2" in (libraries.stdout if libraries else "")
    details = (
        f"Inputs: {', '.join(inputs) or 'none'}",
        f"PortAudio: {'found' if portaudio else 'missing'}",
    )
    problems: list[str] = []
    fixes: list[str] = []
    if not source or source.endswith(".monitor"):
        problems.append("there's no default microphone")
        fixes.append("Pick your microphone in System Settings > Sound.")
    elif "line" in source.lower():
        problems.append(f"the default input is a line-in ({source}), not a mic")
        fixes.append("If that isn't your microphone, pick the mic in System Settings > Sound.")
    if not portaudio:
        problems.append("the PortAudio library is missing")
        fixes.append("sudo pacman -S portaudio")
    if problems:
        summary = _sentence(problems)
        return Check(name, Status.ATTENTION, summary, details, fix=" ".join(fixes))
    return Check(name, Status.OK, f"Default input {source}; PortAudio found.", details)


# --------------------------------------------------------------------------
# Obsidian
# --------------------------------------------------------------------------


def _obsidian_install(probe: Probe) -> str:
    if _ok(probe.run(["pacman", "-Q", "obsidian"])):
        return "pacman package"
    flatpaks = _ok(probe.run(["flatpak", "list", "--app", "--columns=application"]))
    if flatpaks and "md.obsidian.Obsidian" in flatpaks.stdout:
        return "Flatpak (md.obsidian.Obsidian)"
    for folder in ("Applications", ".local/bin", "Downloads"):
        images = probe.find_files(probe.home / folder, "*[Oo]bsidian*.AppImage")
        if images:
            return f"AppImage ({images[0]})"
    return ""


def check_obsidian(probe: Probe) -> Check:
    """Obsidian is installed, and obsidian:// links open it."""
    name = "Obsidian"
    method = _obsidian_install(probe)
    handler_out = probe.run(["xdg-mime", "query", "default", "x-scheme-handler/obsidian"])
    handler = handler_out.stdout.strip() if handler_out and handler_out.code == 0 else ""
    details = (f"obsidian:// handler: {handler or 'not registered'}",)
    if not method:
        return Check(
            name,
            Status.ATTENTION,
            "Not installed. Recon needs it from Phase 2, to read the vault.",
            details,
            fix="sudo pacman -S obsidian (or the Flatpak md.obsidian.Obsidian)",
        )
    if not handler:
        return Check(
            name,
            Status.ATTENTION,
            f"Installed ({method}), but obsidian:// links aren't registered.",
            details,
            fix="Open Obsidian once; it registers the link handler on first launch.",
        )
    return Check(name, Status.OK, f"Installed ({method}); obsidian:// links work.", details)


# --------------------------------------------------------------------------
# Disk
# --------------------------------------------------------------------------


def _models_folder(probe: Probe) -> Path:
    shown = _ok(probe.run(["systemctl", "show", "ollama", "-p", "Environment", "--value"]))
    matches = re.findall(r"OLLAMA_MODELS=(\S+)", shown.stdout if shown else "")
    # systemd applies Environment= lines in order, so the last one wins.
    return Path(matches[-1]) if matches else probe.home / ".ollama/models"


def _existing(path: Path) -> Path:
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def check_disk(probe: Probe) -> Check:
    """Free space in home (Whisper, vault, data) and where Ollama keeps models."""
    name = "Free disk space"
    models = _models_folder(probe)
    home_gb = probe.free_bytes(probe.home) / _GB
    models_gb = probe.free_bytes(_existing(models)) / _GB
    details = (f"Home: {home_gb:.0f} GB free", f"Ollama models ({models}): {models_gb:.0f} GB free")
    problems = []
    if home_gb < MIN_HOME_FREE_GB:
        problems.append(f"home has under {MIN_HOME_FREE_GB} GB free")
    if models_gb < MIN_MODELS_FREE_GB:
        problems.append(f"the models folder has under {MIN_MODELS_FREE_GB} GB free")
    if problems:
        return Check(name, Status.ATTENTION, _sentence(problems), details)
    return Check(
        name, Status.OK, f"{home_gb:.0f} GB in home, {models_gb:.0f} GB for models.", details
    )


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

SECTIONS: tuple[tuple[str, tuple[Callable[[Probe], Check], ...]], ...] = (
    (
        "Ollama",
        (check_ollama_install, check_ollama_version, check_ollama_service, check_ollama_gpu),
    ),
    ("GPU", (check_nvidia,)),
    ("Desktop", (check_session, check_portal)),
    ("Audio", (check_audio,)),
    ("Obsidian", (check_obsidian,)),
    ("Disk", (check_disk,)),
)


def run_checks(probe: Probe) -> list[tuple[str, Check]]:
    """Run every check in report order.

    Args:
        probe: How to read the machine.

    Returns:
        (section, check) pairs.
    """
    return [(section, check(probe)) for section, checks in SECTIONS for check in checks]


def render(results: Sequence[tuple[str, Check]]) -> str:
    """Format results as a plain-English report.

    Args:
        results: Output of `run_checks`.

    Returns:
        The report text.
    """
    lines = ["Recon environment check", ""]
    current = ""
    for section, check in results:
        if section != current:
            lines.extend(["", section] if current else [section])
            current = section
        lines.append(f"  [{check.status}] {check.name}: {check.summary}")
        lines.extend(f"      {detail}" for detail in check.details)
        if check.fix and check.status is Status.ATTENTION:
            lines.append(f"      Fix: {check.fix}")
    attention = sum(check.status is Status.ATTENTION for _, check in results)
    lines.append("")
    lines.append(
        "Everything looks ready."
        if attention == 0
        else f"{attention} of {len(results)} checks need attention. Nothing has been changed."
    )
    return "\n".join(lines)


def main() -> int:
    """Run the checks against this machine and print the report.

    Returns:
        0 when everything is OK, 1 when anything needs attention.
    """
    probe = Probe(
        run=run_command,
        env=dict(os.environ),
        home=Path.home(),
        free_bytes=lambda path: shutil.disk_usage(path).free,
    )
    results = run_checks(probe)
    print(render(results))  # noqa: T201 - command-line output
    return int(any(check.status is Status.ATTENTION for _, check in results))


if __name__ == "__main__":
    sys.exit(main())
