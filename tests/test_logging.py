"""Hard rule: note content, prompts, transcripts and model output never reach app.log."""

import ast
import io
import logging
import logging.handlers
import stat
import uuid
from collections.abc import Callable, Iterator
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


_NOT_LOGGERS = {"np", "numpy", "math", "cmath"}
"""Receivers whose `.log` is maths, not logging."""


def _receiver_name(func: ast.Attribute) -> str:
    return func.value.id if isinstance(func.value, ast.Name) else ""


def message_offenders(source: str) -> list[int]:
    """Lines of logging-method calls whose message isn't a string literal.

    Any `<anything>.<debug|info|warning|...>(...)` call counts, whatever the
    receiver (`log`, `self._log`, `LOGGER`, `logging.getLogger(x)`), so the
    rule can't be dodged by naming the logger differently.
    """
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LOG_METHODS
            and _receiver_name(node.func) not in _NOT_LOGGERS
        ):
            continue
        # logger.log(level, msg, ...) takes the message second.
        index = 1 if node.func.attr == "log" else 0
        keyword = next((kw.value for kw in node.keywords if kw.arg == "msg"), None)
        message = node.args[index] if len(node.args) > index else keyword
        if not (isinstance(message, ast.Constant) and isinstance(message.value, str)):
            lines.append(node.lineno)
    return lines


def logger_name_offenders(source: str) -> list[int]:
    """Lines where getLogger gets something other than `__name__` or a literal."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "getLogger" or not node.args:
            continue
        arg = node.args[0]
        literal = isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        dunder = isinstance(arg, ast.Name) and arg.id == "__name__"
        if not (literal or dunder):
            lines.append(node.lineno)
    return lines


def adapter_offenders(source: str) -> list[int]:
    """Lines that use LoggerAdapter, whose process() could put content in msg."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if (isinstance(node, ast.Name) and node.id == "LoggerAdapter")
        or (isinstance(node, ast.Attribute) and node.attr == "LoggerAdapter")
    ]


@pytest.mark.parametrize(
    "source",
    [
        "log.info(text)",
        "self.log.info(text)",
        "self._logger.warning(text)",
        "LOGGER.error(text)",
        "logging.getLogger(__name__).warning(text)",
        "log.log(10, text)",
        "log.info(msg=text)",
        'log.info(f"{text}")',
        "log.exception(error)",
        "log.info()",
    ],
)
def test_detector_catches_non_literal_messages(source: str) -> None:
    assert message_offenders(source) == [1]


@pytest.mark.parametrize(
    "source",
    [
        'log.info("saved %s", text)',
        'self._log.log(20, "saved %s", text)',
        'log.info(msg="saved")',
        "np.log(values)",
        "parser.add_argument('x')",
    ],
)
def test_detector_allows_literal_messages(source: str) -> None:
    assert message_offenders(source) == []


@pytest.mark.parametrize(
    ("source", "bad"),
    [
        ("logging.getLogger(__name__)", False),
        ('logging.getLogger("recon.engine")', False),
        ("logging.getLogger()", False),
        ('logging.getLogger(f"recon.room.{name}")', True),
        ("getLogger(room_name)", True),
    ],
)
def test_detector_checks_logger_names(source: str, *, bad: bool) -> None:
    assert bool(logger_name_offenders(source)) is bad


def test_detector_finds_logger_adapters() -> None:
    assert adapter_offenders("class A(logging.LoggerAdapter): pass") == [1]
    assert adapter_offenders("from logging import LoggerAdapter") == []  # import alone is inert
    assert adapter_offenders("from logging import LoggerAdapter\nx = LoggerAdapter(l, {})") == [2]


@pytest.mark.parametrize(
    "check", [message_offenders, logger_name_offenders, adapter_offenders], ids=lambda f: f.__name__
)
def test_recon_source_obeys_the_logging_rules(check: Callable[[str], list[int]]) -> None:
    offenders = [
        f"{path.relative_to(RECON_SRC)}:{line}"
        for path in RECON_SRC.rglob("*.py")
        for line in check(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_exception_text_cached_by_another_handler_is_not_reused(log_file: Path) -> None:
    # A plain handler on a child logger formats first and caches record.exc_text.
    child = logging.getLogger("recon.engine.cache_probe")
    sink = logging.StreamHandler(io.StringIO())
    sink.setFormatter(logging.Formatter("%(message)s"))
    child.addHandler(sink)

    def fail() -> None:
        raise ValueError(NOTE)

    try:
        try:
            fail()
        except ValueError:
            child.exception("step failed")
    finally:
        child.removeHandler(sink)

    stream = sink.stream
    assert isinstance(stream, io.StringIO)
    assert NOTE in stream.getvalue()  # the other handler did cache the full text
    assert NOTE not in _read(log_file)
    assert "builtins.ValueError: <redacted>" in _read(log_file)


def test_existing_open_log_is_locked_down(tmp_path: Path) -> None:
    path = tmp_path / "app.log"
    path.write_text("old\n")
    path.chmod(0o644)

    handler = configure_logging(path)
    logging.getLogger("recon").removeHandler(handler)
    handler.close()

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
