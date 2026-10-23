"""Logging for Recon: one line per event, rotated, and never containing note content.

Content safety is enforced, not left to discipline:

- Ruff's `G` rules forbid f-strings and `%`/`.format` in log calls, so every
  message is a literal format string and variable parts arrive as `args`.
- A test checks that the first argument of every logging call in `recon/` is
  a string literal, so content can't be passed as the message itself.
- `RedactingFilter` replaces every `str` (and any other non-allowlisted type)
  in `args` with a placeholder giving only its length. IDs and counts pass
  through when they are ints, floats, bools, UUIDs or enums. A string that is
  known to be safe (an error type name, a run ID) must be wrapped in `Safe`.
- `RedactingFormatter` drops exception messages and keeps only the exception
  types and the stack frames, because messages (pydantic errors in particular)
  can quote the input that failed.
"""

import enum
import io
import logging
import traceback
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import override

from recon.paths import private_opener

MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 5
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

type _ExcInfo = tuple[type[BaseException], BaseException, TracebackType | None]


class Safe(str):
    """A string vetted as free of note content, such as an ID or an error type name."""

    __slots__ = ()


_ALLOWED_ARG_TYPES: tuple[type, ...] = (Safe, int, float, bool, uuid.UUID, enum.Enum, type(None))


def _redact(value: object) -> object:
    if isinstance(value, _ALLOWED_ARG_TYPES):
        return value
    if isinstance(value, str | bytes):
        return f"<redacted {type(value).__name__} len={len(value)}>"
    return f"<redacted {type(value).__name__}>"


class RedactingFilter(logging.Filter):
    """Replace any log argument that might carry note content with a placeholder."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        # Messages must be literal strings (checked by tests/test_logging.py);
        # anything else is treated as content.
        if not isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: _redact(value) for key, value in record.args.items()}
        elif record.args:
            record.args = tuple(_redact(value) for value in record.args)
        return True


class RedactingFormatter(logging.Formatter):
    """Format exceptions as types and frames only, never their messages."""

    @override
    def formatException(self, ei: _ExcInfo | tuple[None, None, None]) -> str:
        _, exc, _ = ei
        if exc is None:
            return ""
        lines: list[str] = []
        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            lines.append("Traceback (most recent call last):")
            lines.extend(line.rstrip("\n") for line in traceback.format_tb(current.__traceback__))
            lines.append(f"{type(current).__module__}.{type(current).__qualname__}: <redacted>")
            current = current.__cause__ or current.__context__
        return "\n".join(lines)


class _PrivateRotatingFileHandler(RotatingFileHandler):
    """Rotating handler whose files are created as 0600."""

    @override
    def _open(self) -> io.TextIOWrapper:
        # RotatingFileHandler re-opens through this hook after every rollover, so
        # overriding it is the only way to set the mode on rotated files too.
        # Builtin open() because Path.open() has no `opener` parameter.
        return open(
            self.baseFilename,
            "a",  # configure_logging always appends; a literal keeps the return type exact
            encoding=self.encoding,
            errors=self.errors,
            opener=private_opener,
        )


def configure_logging(log_file: Path, level: int = logging.INFO) -> logging.Handler:
    """Send Recon's logs to `log_file`, rotated at 5 MB with five old files kept.

    The log's folder must already exist with private permissions
    (see `recon.paths.AppPaths.ensure`).

    Args:
        log_file: Path of `app.log`.
        level: Minimum level written.

    Returns:
        The installed handler, so callers (and tests) can remove it.
    """
    handler = _PrivateRotatingFileHandler(
        log_file, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    handler.setFormatter(RedactingFormatter(_FORMAT))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger("recon")
    root.setLevel(level)
    root.addHandler(handler)
    return handler
