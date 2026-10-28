"""Vault bootstrap: folders, Home, dashboards and Obsidian settings, never replacing anything."""

import json
import stat
from pathlib import Path

import pytest

from recon.engine.vault import FOLDERS, OBSIDIAN_SETTINGS, bootstrap
from recon.errors import VaultSetupError


def test_a_new_vault_gets_its_whole_structure(tmp_path: Path) -> None:
    vault = tmp_path / "Cyber Vault"

    result = bootstrap(vault)

    assert result.created is True
    assert stat.S_IMODE(vault.stat().st_mode) == 0o700
    assert all((vault / folder).is_dir() for folder in FOLDERS)
    assert sorted(result.written) == [
        ".obsidian/app.json",
        "Bases/Concepts.base",
        "Bases/Open flags.base",
        "Bases/Rooms.base",
        "Home.md",
    ]
    home = (vault / "Home.md").read_text(encoding="utf-8")
    assert home.startswith("---\ntype: home\n---\n# Cyber Vault\n")
    for base in ("Rooms", "Open flags", "Concepts"):
        assert f"![[Bases/{base}.base]]" in home
    assert json.loads((vault / ".obsidian" / "app.json").read_text()) == OBSIDIAN_SETTINGS


def test_the_dashboards_query_recons_properties(tmp_path: Path) -> None:
    bootstrap(tmp_path / "v")
    bases = tmp_path / "v" / "Bases"

    assert "'type == \"room\"'" in (bases / "Rooms.base").read_text()
    assert "property: note.path" in (bases / "Rooms.base").read_text()
    assert "'open_flags > 0'" in (bases / "Open flags.base").read_text()
    assert "'type == \"concept\"'" in (bases / "Concepts.base").read_text()
    for base in bases.glob("*.base"):
        text = base.read_text()
        assert text.startswith("filters:\n")
        assert "\nviews:\n  - type: table\n" in text


def test_running_again_changes_nothing(tmp_path: Path) -> None:
    vault = tmp_path / "Cyber Vault"
    bootstrap(vault)
    before = {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()}

    again = bootstrap(vault)

    assert (again.created, again.written) == (False, ())
    assert {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()} == before


def test_tylers_own_files_are_never_replaced(tmp_path: Path) -> None:
    vault = tmp_path / "Cyber Vault"
    (vault / "Bases").mkdir(parents=True)
    (vault / "Home.md").write_text("my own home\n")
    (vault / "Bases" / "Rooms.base").write_text("my own rooms view\n")

    result = bootstrap(vault)

    assert result.created is False
    assert (vault / "Home.md").read_text() == "my own home\n"
    assert (vault / "Bases" / "Rooms.base").read_text() == "my own rooms view\n"
    assert "Home.md" not in result.written
    assert "Bases/Concepts.base" in result.written


def test_obsidian_settings_only_gain_missing_keys(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".obsidian" / "app.json").write_text(
        json.dumps({"useMarkdownLinks": True, "vimMode": True})
    )

    result = bootstrap(vault)

    settings = json.loads((vault / ".obsidian" / "app.json").read_text())
    assert settings == {
        "useMarkdownLinks": True,  # Tyler's choice wins
        "vimMode": True,
        "alwaysUpdateLinks": True,
        "attachmentFolderPath": "Attachments",
    }
    assert ".obsidian/app.json" in result.written


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", "\xff\xfe"])
def test_unreadable_obsidian_settings_are_left_alone(tmp_path: Path, content: str) -> None:
    vault = tmp_path / "v"
    (vault / ".obsidian").mkdir(parents=True)
    app = vault / ".obsidian" / "app.json"
    app.write_bytes(content.encode("latin-1"))

    result = bootstrap(vault)

    assert app.read_bytes() == content.encode("latin-1")
    assert ".obsidian/app.json" not in result.written


def test_a_file_where_the_vault_should_be(tmp_path: Path) -> None:
    (tmp_path / "Cyber Vault").write_text("not a folder")

    with pytest.raises(VaultSetupError):
        bootstrap(tmp_path / "Cyber Vault")


def test_a_hostile_vault_name_makes_a_plain_title(tmp_path: Path) -> None:
    vault = tmp_path / "My %% hidden\\nvault"

    bootstrap(vault)

    first_heading = next(
        line for line in (vault / "Home.md").read_text().splitlines() if line.startswith("# ")
    )
    assert "%%" not in first_heading
