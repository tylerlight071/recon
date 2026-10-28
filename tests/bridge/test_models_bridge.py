"""ModelsBridge: Ollama's status for Settings, checked off the UI thread (task 2.2)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QObject

from recon.bridge.models import ModelsBridge
from recon.bridge.settings import SettingsBridge
from recon.config import Settings
from recon.errors import UnsafeHostError
from recon.services.ollama import OllamaService, loopback
from tests.services.fakes import FakeClient
from tests.ui.qml_harness import SignalCounter, app


class Held:
    """A submit that holds jobs until the test runs them (like a slow worker)."""

    def __init__(self) -> None:
        self.jobs: list[Callable[[], None]] = []

    def __call__(self, job: Callable[[], None]) -> None:
        self.jobs.append(job)

    def run(self) -> None:
        while self.jobs:
            self.jobs.pop(0)()


def _bridge(
    tmp_path: Path,
    client: FakeClient,
    settings: Settings | None = None,
    submit: Callable[[Callable[[], None]], None] = lambda job: job(),
) -> tuple[ModelsBridge, list[str], list[str]]:
    app()
    owner = QObject()
    bridge_settings = SettingsBridge(
        settings or Settings(),
        lambda _s: None,
        parent=owner,
        home=tmp_path,
        submit=lambda job: job(),
    )
    hosts: list[str] = []
    copied: list[str] = []

    def service_for(host: str) -> OllamaService:
        hosts.append(loopback(host))
        return OllamaService(client)

    models = ModelsBridge(bridge_settings, service_for, copied.append, submit=submit, parent=owner)
    models._owner = owner  # type: ignore[attr-defined]  # keep the Qt parent alive for the test
    return models, hosts, copied


def test_starts_out_checking(tmp_path: Path) -> None:
    models, _hosts, _copied = _bridge(tmp_path, FakeClient())

    assert models.property("state") == "checking"
    assert models.property("message") == "Checking Ollama…"
    assert models.property("commands") == ""


def test_ready_when_everything_is_installed(tmp_path: Path) -> None:
    models, hosts, _copied = _bridge(tmp_path, FakeClient())
    changed = SignalCounter(models, "changed()")

    models.check()

    assert models.property("state") == "ready"
    assert models.property("message") == "Ollama is running and has every model Recon uses."
    assert models.property("checking") is False
    assert models.property("commands") == ""
    assert hosts == ["http://127.0.0.1:11434"]
    assert changed.count >= 1


def test_offline_says_what_to_do(tmp_path: Path) -> None:
    models, _hosts, _copied = _bridge(tmp_path, FakeClient(list_error=ConnectionError()))

    models.check()

    assert models.property("state") == "offline"
    assert models.property("message") == (
        "Couldn't reach Ollama. Is it running? Start it, then press Check again."
    )


def test_one_missing_model_gets_its_pull_command(tmp_path: Path) -> None:
    models, _hosts, copied = _bridge(tmp_path, FakeClient(models=["qwen3.5:9b"]))

    models.check()

    assert models.property("state") == "missing"
    assert models.property("message") == (
        "Ollama is running, but qwen3-embedding:0.6b isn't installed yet. "
        "Run this in a terminal, then press Check again:"
    )
    assert models.property("commands") == "ollama pull qwen3-embedding:0.6b"
    models.copyCommands()
    assert copied == ["ollama pull qwen3-embedding:0.6b"]


def test_several_missing_models_get_a_line_each(tmp_path: Path) -> None:
    models, _hosts, _copied = _bridge(
        tmp_path, FakeClient(models=[]), Settings(vision_model="qwen3-vl:8b")
    )

    models.check()

    assert models.property("message").startswith("Ollama is running, but 3 models aren't")
    assert models.property("commands") == (
        "ollama pull qwen3.5:9b\nollama pull qwen3-vl:8b\nollama pull qwen3-embedding:0.6b"
    )


def test_nothing_to_copy_when_nothing_is_missing(tmp_path: Path) -> None:
    models, _hosts, copied = _bridge(tmp_path, FakeClient())
    models.check()

    models.copyCommands()

    assert copied == []


def test_another_machine_is_refused_with_plain_copy(tmp_path: Path) -> None:
    models, hosts, _copied = _bridge(
        tmp_path, FakeClient(), Settings(ollama_host="http://192.168.1.20:11434")
    )

    models.check()

    assert hosts == []
    assert models.property("state") == "problem"
    assert models.property("message") == UnsafeHostError.user_message


def test_an_unexpected_error_is_logged_not_shown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    models, _hosts, _copied = _bridge(tmp_path, FakeClient(list_error=RuntimeError("boom")))

    models.check()

    assert models.property("state") == "problem"
    assert "boom" not in models.property("message")
    assert "RuntimeError" in caplog.text


def test_a_second_press_while_checking_is_ignored(tmp_path: Path) -> None:
    held = Held()
    models, hosts, _copied = _bridge(tmp_path, FakeClient(), submit=held)

    models.check()
    models.check()

    assert models.property("checking") is True
    assert len(held.jobs) == 1
    held.run()
    assert hosts == ["http://127.0.0.1:11434"]
    assert models.property("checking") is False


def test_checking_again_keeps_ready_on_screen(tmp_path: Path) -> None:
    held = Held()
    models, _hosts, _copied = _bridge(tmp_path, FakeClient(), submit=held)
    models.check()
    held.run()

    models.check()

    # No flicker back to "Checking…" while a ready Ollama is re-checked.
    assert models.property("state") == "ready"
    assert models.property("checking") is True
    held.run()


def test_roles_list_each_model(tmp_path: Path) -> None:
    models, _hosts, _copied = _bridge(tmp_path, FakeClient())

    assert models.property("roles") == [
        {"role": "Notes and questions", "name": "qwen3.5:9b"},
        {"role": "Screenshots", "name": "qwen3.5:9b"},
        {"role": "Matching notes", "name": "qwen3-embedding:0.6b"},
    ]
