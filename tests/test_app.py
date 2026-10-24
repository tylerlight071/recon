"""Start-up: the entry point, the app identity and QML loading."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal
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
    for window in QGuiApplication.topLevelWindows():
        window.close()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class _FakeApp(QObject):
    """Stands in for QGuiApplication so main() can run without a second app object."""

    aboutToQuit = Signal()  # noqa: N815 - mirrors Qt's signal name

    def __init__(self) -> None:
        super().__init__()
        self.ran = False
        self.open_windows: set[str] = set()

    def exec(self) -> int:
        # The engine only lives while main() runs, so look at the windows now.
        self.ran = True
        self.open_windows = {w.title() for w in QGuiApplication.topLevelWindows()}
        return 0


@pytest.fixture
def fake_app(monkeypatch: pytest.MonkeyPatch) -> _FakeApp:
    qt_app()
    fake = _FakeApp()
    monkeypatch.setattr(entry, "create_application", lambda _argv: fake)
    return fake


@pytest.mark.usefixtures("private_home")
def test_main_opens_the_two_windows(fake_app: _FakeApp) -> None:
    assert entry.main([]) == 0
    assert fake_app.ran
    assert {"Recon", "Recon Panel"} <= fake_app.open_windows


def test_main_sets_up_private_folders_and_the_log(private_home: Path, fake_app: _FakeApp) -> None:
    entry.main([])

    assert (private_home / "xdg_data_home/recon/app.log").exists()
    assert (private_home / "xdg_config_home/recon").is_dir()
    assert fake_app.ran


def test_unreadable_settings_still_start_with_defaults(
    private_home: Path, fake_app: _FakeApp, caplog: pytest.LogCaptureFixture
) -> None:
    settings = private_home / "xdg_config_home/recon/settings.toml"
    settings.parent.mkdir(parents=True)
    settings.write_text("panel_width = 'very wide'\n")

    with caplog.at_level(logging.WARNING, logger="recon"):
        assert entry.main([]) == 0

    assert fake_app.ran
    assert any("default settings" in record.getMessage() for record in caplog.records)


@pytest.mark.usefixtures("private_home")
def test_gallery_loads_and_runs(fake_app: _FakeApp) -> None:
    assert entry.main(["--gallery"]) == 0
    assert fake_app.ran
    assert "Recon component gallery" in fake_app.open_windows


@pytest.mark.usefixtures("private_home", "fake_app")
def test_qml_that_fails_to_load_exits_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    qml = recon_app.create_engine()
    note = "TXT records hold text and my private note"
    source = tmp_path / "Warns.qml"
    source.write_text(
        f'import QtQuick\nItem {{ property string note: "{note}"; width: undefinedThing + note }}\n'
    )

    with caplog.at_level(logging.WARNING, logger="recon"):
        recon_app.load_qml(qml.engine, source)
        wait(50)

    messages = [record.getMessage() for record in caplog.records]
    assert any("qml warning at line" in message for message in messages)
    assert all(note not in message for message in messages)


def test_qguiapplication_is_the_type_we_create() -> None:
    assert isinstance(qt_app(), QGuiApplication)
