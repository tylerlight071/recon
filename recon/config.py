"""Application-wide constants and, from Phase 1, the settings model."""

from typing import Final

APP_ID: Final = "io.github.tylerlight071.Recon"
"""Reverse-DNS app ID used everywhere the desktop identifies Recon.

It must match the `.desktop` file name, `QGuiApplication.setDesktopFileName`,
the GlobalShortcuts portal `Registry.Register` call and the KWin window rule.
Changing it breaks all four, so treat it as permanent.
"""

APP_NAME: Final = "Recon"
"""Name shown to Tyler in window titles and notifications."""
