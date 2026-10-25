"""A fresh, migrated database per test, with a controllable clock."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from recon.db.connection import Database
from recon.db.migrate import migrate


class FakeClock:
    """UTC time that only moves when told to."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "recon"
    folder.mkdir(mode=0o700)
    return folder


@pytest.fixture
def db(data_dir: Path) -> Iterator[Database]:
    database = Database.open(data_dir / "app.db")
    migrate(database)
    yield database
    database.close()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
