"""Hard rule: note content, prompts, transcripts and model output never reach app.log."""

import ast
import logging
import logging.handlers
import stat
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recon.logging_setup import (
    LOG_BACKUPS,
    MAX_LOG_BYTES,
    RedactingFilter,
    RedactingFormatter,
    Safe,
    configure_logging,
)

RECON_SRC = Path(__file__).resolve().parents[1] / "recon"
NOTE = "TXT records hold text and my secret note about DNS"
_LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


@pytest.fixture
def log_file(tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "app.log"
    handler = configure_logging(path)
    yield path
    logging.getLogger("recon").removeHandler(handler)
    handler.close()


def _read(path: Path) -> str:
    for handler in logging.getLogger("recon").handlers:
        handler.flush()
    return path.read_text(encoding="utf-8")


def test_string_args_are_redacted(log_file: Path) -> None:
    logging.getLogger("recon.test").info("saved block %s with text %s", 12, NOTE)

    text = _read(log_file)
    assert NOTE not in text
    assert "saved block 12 with text <redacted str len=" in text


def test_mapping_args_are_redacted(log_file: Path) -> None:
    logging.getLogger("recon.test").info("block %(text)s", {"text": NOTE})

    assert NOTE not in _read(log_file)


def test_non_string_message_is_redacted(log_file: Path) -> None:
    logging.getLogger("recon.test").info(["list", NOTE])

    assert NOTE not in _read(log_file)


def test_safe_ids_and_numbers_pass_through(log_file: Path) -> None:
    run_id = uuid.UUID(int=7)
    logging.getLogger("recon.test").info(
        "run %s step %s took %s s ok=%s err=%s", run_id, 3, 1.5, True, Safe("ApplyConflict")
    )

    assert f"run {run_id} step 3 took 1.5 s ok=True err=ApplyConflict" in _read(log_file)


def test_exception_messages_are_redacted_but_types_kept(log_file: Path) -> None:
    def lookup() -> None:
        raise KeyError(NOTE)

    def fail() -> None:
        try:
            lookup()
        except KeyError as inner:
            raise ValueError(NOTE) from inner

    try:
        fail()
    except ValueError:
        logging.getLogger("recon.test").exception("step failed")

    text = _read(log_file)
    assert NOTE not in text
    assert "builtins.ValueError: <redacted>" in text
    assert "builtins.KeyError: <redacted>" in text
    assert "in fail" in text


def test_formatter_handles_missing_and_cyclic_exceptions() -> None:
    formatter = RedactingFormatter()
    first, second = ValueError(NOTE), KeyError(NOTE)
    first.__context__, second.__context__ = second, first

    assert formatter.formatException((None, None, None)) == ""
    text = formatter.formatException((ValueError, first, None))
    assert NOTE not in text
    assert text.count("<redacted>") == 2


def test_log_file_is_private_and_rotates(log_file: Path) -> None:
    handler = logging.getLogger("recon").handlers[-1]
    assert isinstance(handler, logging.handlers.RotatingFileHandler)
    assert handler.maxBytes == MAX_LOG_BYTES
    assert handler.backupCount == LOG_BACKUPS

    logging.getLogger("recon.test").info("first")
    handler.doRollover()
    logging.getLogger("recon.test").info("second")
    _read(log_file)

    for path in (log_file, log_file.with_name("app.log.1")):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@given(st.text(min_size=1))
def test_any_text_arg_never_appears_verbatim(text: str) -> None:
    record = logging.LogRecord("recon.t", logging.INFO, __file__, 1, "x %s", (text,), None)
    RedactingFilter().filter(record)

    assert record.args == (f"<redacted str len={len(text)}>",)


def _logging_calls(tree: ast.AST) -> Iterator[ast.Call]:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LOG_METHODS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"log", "logger", "logging", "_log", "_logger"}
        ):
            yield node


def test_every_log_message_in_recon_is_a_string_literal() -> None:
    offenders: list[str] = []
    for path in RECON_SRC.rglob("*.py"):
        for call in _logging_calls(ast.parse(path.read_text(encoding="utf-8"))):
            # logger.log(level, msg, ...) takes the message second.
            assert isinstance(call.func, ast.Attribute)
            index = 1 if call.func.attr == "log" else 0
            message = call.args[index] if len(call.args) > index else None
            if not (isinstance(message, ast.Constant) and isinstance(message.value, str)):
                offenders.append(f"{path.relative_to(RECON_SRC)}:{call.lineno}")

    assert offenders == []
