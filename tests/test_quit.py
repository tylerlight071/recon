"""Audit F-06: at quit, queued room jobs finish before the database closes."""

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal

from recon.__main__ import create_bridges
from recon.bridge.session import RoomSessionBridge
from recon.config import Settings
from recon.db.connection import Database
from recon.db.migrate import migrate
from recon.db.models import NewRoom
from recon.db.repositories import RoomRepository, TaskRepository
from recon.paths import AppPaths
from tests.ui.qml_harness import app, wait_until


class FakeApp(QObject):
    """Just the part of QGuiApplication that create_bridges wires to."""

    aboutToQuit = Signal()  # noqa: N815 - Qt's name


class SlowRooms(RoomRepository):
    """Moving on takes a while, so the job is still queued when quit starts."""

    def update_progress(self, *args: object, **kwargs: object) -> bool:
        import time  # noqa: PLC0415 - only this fake sleeps

        time.sleep(0.3)
        return super().update_progress(*args, **kwargs)  # type: ignore[arg-type]


def test_title_then_next_then_quit_keeps_the_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app()
    paths = AppPaths(data=tmp_path / "data", config=tmp_path / "config", cache=tmp_path / "cache")
    paths.ensure()
    db = Database.open(paths.data / "app.db")
    migrate(db)
    room = RoomRepository(db).create(NewRoom(name="DNS in Detail", task_count=3))
    fake = FakeApp()
    monkeypatch.setattr("recon.__main__.RoomRepository", SlowRooms)
    bridges, _pinning = create_bridges(fake, paths, Settings(kwin_pinning="off"), db)  # type: ignore[arg-type]
    session = bridges["RoomSession"]
    assert isinstance(session, RoomSessionBridge)
    session.open(room.id)
    assert wait_until(lambda: session.property("hasRoom") is True)

    session.setTitle("Record types")
    session.next()  # Ctrl+Return: queued behind the slow update
    fake.aboutToQuit.emit()  # quit straight away
    # main() then leaves the event loop for good: results still queued for the UI
    # thread are never delivered. Delete the bridges so they aren't here either.
    for bridge in bridges.values():
        bridge.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    db.close()

    reopened = Database.open(paths.data / "app.db")
    first = TaskRepository(reopened).for_room(room.id)[0]
    reopened.close()
    assert (first.title, first.status) == ("Record types", "done")
