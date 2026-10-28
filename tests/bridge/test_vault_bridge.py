"""VaultBridge: sets the vault up, and the one-time "open it in Obsidian" step."""

from pathlib import Path

from PySide6.QtCore import QObject, QUrl

from recon.bridge.settings import SettingsBridge
from recon.bridge.vault import VaultBridge
from recon.config import Settings
from recon.errors import VaultSetupError
from tests.ui.qml_harness import SignalCounter, app


def _bridge(tmp_path: Path) -> tuple[VaultBridge, SettingsBridge, list[str]]:
    app()
    owner = QObject()
    settings = SettingsBridge(
        Settings(), lambda _s: None, parent=owner, home=tmp_path, submit=lambda job: job()
    )
    copied: list[str] = []
    vault = VaultBridge(settings, copied.append, submit=lambda job: job(), parent=owner)
    vault._owner = owner  # type: ignore[attr-defined]  # keep the Qt parent alive for the test
    return vault, settings, copied


def test_set_up_creates_the_vault_and_asks_for_obsidian_once(tmp_path: Path) -> None:
    vault, _settings, copied = _bridge(tmp_path)
    assert vault.property("ready") is False

    vault.setUp()

    assert (tmp_path / "Cyber Vault" / "Home.md").exists()
    assert vault.property("ready") is True
    assert vault.property("shown") == "~/Cyber Vault"
    assert vault.property("needsObsidian") is True
    assert vault.property("canOpenInObsidian") is False
    vault.copyPath()
    assert copied == [str(tmp_path / "Cyber Vault")]


def test_confirming_hides_the_step_and_allows_obsidian_links(tmp_path: Path) -> None:
    vault, settings, _copied = _bridge(tmp_path)
    vault.setUp()
    changed = SignalCounter(vault, "changed()")

    vault.confirmOpened()

    assert settings.property("obsidianVault") == str(tmp_path / "Cyber Vault")
    assert vault.property("needsObsidian") is False
    assert vault.property("canOpenInObsidian") is True
    assert changed.count >= 1

    vault.forgetOpened()  # a link failed: show the step again
    assert vault.property("needsObsidian") is True


def test_a_new_vault_folder_is_set_up_and_needs_obsidian_again(tmp_path: Path) -> None:
    vault, settings, _copied = _bridge(tmp_path)
    vault.setUp()
    vault.confirmOpened()

    settings.chooseVault(QUrl.fromLocalFile(str(tmp_path / "Other Vault")).toString())

    assert (tmp_path / "Other Vault" / "Home.md").exists()
    assert vault.property("needsObsidian") is True


def test_a_vault_that_cant_be_set_up_says_so(tmp_path: Path) -> None:
    (tmp_path / "Cyber Vault").write_text("a file, not a folder")
    vault, _settings, _copied = _bridge(tmp_path)

    vault.setUp()

    assert vault.property("ready") is False
    assert vault.property("problem") == VaultSetupError.user_message
    assert vault.property("needsObsidian") is False
