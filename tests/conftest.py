"""Shared test setup."""

import os

# Qt tests run headless everywhere (CI sets the same), so they never open
# windows on the desktop. Set before any QGuiApplication exists.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from collections.abc import Iterator
from pathlib import Path

import pytest

REAL_VAULT = Path.home() / "Cyber Vault"


@pytest.fixture(autouse=True, scope="session")
def _never_touch_the_real_vault() -> Iterator[None]:
    # Recon creates ~/Cyber Vault at start-up (task 2.1). Tests must use a throwaway
    # one: fail the session if a real one appears that wasn't there before.
    existed = REAL_VAULT.exists()
    yield
    assert existed or not REAL_VAULT.exists(), "a test created the real ~/Cyber Vault"
