"""Start-up: the entry point, the app identity and QML loading."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

import recon.__main__ as entry
from recon import app as recon_app
from recon.config import APP_ID
from tests.ui.qml_harness import app as qt_app
from tests.ui.qml_harness import wait


@pytest.fixture
def private_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    yield tmp_path
    for handler in list(logging.getLogger("recon").handlers):
        logging.getLogger("recon").removeHandler(handler)
        handler.close()


class _FakeApp:
    def __init__(self) -> None:
        self.ran = False

    def exec(self) -> int:
        self.ran = True
        return 0


def test_without_gallery_explains_and_exits(
    private_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert entry.main([]) == 2
    assert "--gallery" in capsys.readouterr().err
    assert (private_home / "xdg_data_home/recon/app.log").exists()


@pytest.mark.usefixtures("private_home")
def test_gallery_loads_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    qt_app()
    fake = _FakeApp()
    monkeypatch.setattr(entry, "create_application", lambda _argv: fake)

    assert entry.main(["--gallery"]) == 0
    assert fake.ran


@pytest.mark.usefixtures("private_home")
def test_gallery_that_fails_to_load_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    qt_app()
    monkeypatch.setattr(entry, "create_application", lambda _argv: _FakeApp())
    broken = tmp_path / "Broken.qml"
    broken.write_text("this is not QML")
    monkeypatch.setattr(entry, "GALLERY_QML", broken)

    assert entry.main(["--gallery"]) == 1


def test_application_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[list[str]] = []
    monkeypatch.setattr(recon_app, "QGuiApplication", _RecordingApp(made))

    recon_app.create_application(["recon"])

    assert made == [["recon"]]
    assert _RecordingApp.desktop_file == APP_ID


class _RecordingApp:
    desktop_file = ""

    def __init__(self, made: list[list[str]]) -> None:
        self.made = made

    def __call__(self, argv: list[str]) -> object:
        self.made.append(argv)
        return object()

    @classmethod
    def setDesktopFileName(cls, name: str) -> None:  # noqa: N802 - mirrors Qt's API
        cls.desktop_file = name

    @staticmethod
    def setApplicationName(_name: str) -> None:  # noqa: N802 - mirrors Qt's API
        return None


def test_gallery_qml_loads_without_warnings() -> None:
    qt_app()
    engine = QQmlApplicationEngine()
    warnings: list[str] = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))

    assert recon_app.load_qml(engine, recon_app.GALLERY_QML)
    window = recon_app.root_window(engine)
    assert isinstance(window, QQuickWindow)
    wait(100)
    assert warnings == []
    assert window.findChild(object, "galleryPrimary") is not None
    window.close()


def test_root_window_handles_missing_and_non_window_roots(tmp_path: Path) -> None:
    qt_app()
    engine = QQmlApplicationEngine()
    assert recon_app.root_window(engine) is None

    item = tmp_path / "Item.qml"
    item.write_text("import QtQuick\nItem {}\n")
    recon_app.load_qml(engine, item)
    assert recon_app.root_window(engine) is None


def test_qml_warnings_are_logged_without_their_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    qt_app()
    engine = QQmlApplicationEngine()
    note = "TXT records hold text and my private note"
    source = tmp_path / "Warns.qml"
    source.write_text(
        f'import QtQuick\nItem {{ property string note: "{note}"; width: undefinedThing + note }}\n'
    )

    with caplog.at_level(logging.WARNING, logger="recon"):
        recon_app.load_qml(engine, source)
        wait(50)

    messages = [record.getMessage() for record in caplog.records]
    assert any("qml warning at line" in message for message in messages)
    assert all(note not in message for message in messages)


def test_qguiapplication_is_the_type_we_create() -> None:
    assert isinstance(qt_app(), QGuiApplication)
