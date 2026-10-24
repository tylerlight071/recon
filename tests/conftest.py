"""Shared test setup."""

import os

# Qt tests run headless everywhere (CI sets the same), so they never open
# windows on the desktop. Set before any QGuiApplication exists.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
