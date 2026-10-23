"""Recon's exception hierarchy.

Every error Recon raises on purpose derives from `ReconError`. Each subclass
carries `user_message`: plain, kind British English that says what happened
and what to do next. The UI shows only that text, never a stack trace.
"""

from typing import ClassVar


class ReconError(Exception):
    """Base class for every error Recon raises deliberately."""

    user_message: ClassVar[str] = "Something went wrong. Your notes are safe. Try that again."


class ConfigError(ReconError):
    """Settings or another config file could not be read or failed validation."""

    user_message = "Couldn't read Recon's settings. The defaults are in use until they're fixed."


class StorageError(ReconError):
    """The app database or data folder could not be read or written."""

    user_message = (
        "Couldn't save to Recon's data folder. Check there's free disk space, then retry."
    )


class UnsafePathError(ReconError):
    """A write path resolved outside the folder it was meant to stay in."""

    user_message = (
        "Recon stopped a file write that would have left its own folders. Nothing changed."
    )


class InsecurePermissionsError(ReconError):
    """A data or config folder is readable by other users and couldn't be fixed."""

    user_message = (
        "Recon's data folder can be read by other users and couldn't be locked down. "
        "Check who owns it."
    )


class OllamaUnavailable(ReconError):  # noqa: N818 - name fixed by CLAUDE.md
    """The local Ollama server could not be reached."""

    user_message = (
        "Couldn't reach Ollama. Is it running? Recon will try again when you press Retry."
    )


class ModelMissing(ReconError):  # noqa: N818 - name fixed by CLAUDE.md
    """A configured model isn't pulled in Ollama."""

    user_message = "A model Recon needs isn't installed in Ollama yet. Settings shows which one."


class ModelResponseInvalidError(ReconError):
    """A model response failed schema validation, including after the retry."""

    user_message = (
        "The model's answer didn't make sense twice in a row. You can run this step again."
    )


class VaultMissing(ReconError):  # noqa: N818 - name fixed by CLAUDE.md
    """The configured vault folder doesn't exist."""

    user_message = "Couldn't find your vault folder. Pick it again in Settings."


class ApplyConflict(ReconError):  # noqa: N818 - name fixed by CLAUDE.md
    """A vault file changed between staging and Apply."""

    user_message = (
        "A note changed in Obsidian since this review was prepared, so nothing was written. "
        "Re-check to see the latest version."
    )
