"""Shared helpers for the Ollama smoke tests."""

import argparse
import time
from collections.abc import Callable
from dataclasses import dataclass

import ollama

OLLAMA_HOST = "http://127.0.0.1:11434"
"""Loopback only, as in the app (CLAUDE.md, Security and privacy)."""
TIMEOUT_S = 300.0
"""Generous: the first call loads the model into VRAM."""


@dataclass(frozen=True, slots=True)
class Outcome:
    """Result of one smoke test."""

    passed: bool
    detail: str


def make_client() -> ollama.Client:
    """Ollama client pinned to the loopback server."""
    return ollama.Client(host=OLLAMA_HOST, timeout=TIMEOUT_S)


def model_arg(description: str, default: str) -> argparse.ArgumentParser:
    """Argument parser with a `--model` option.

    Args:
        description: Shown by `--help`.
        default: Model tag used when `--model` isn't given.

    Returns:
        The parser, for scripts to add their own options.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--model", default=default, help=f"Ollama model tag (default {default})")
    return parser


def run(name: str, test: Callable[[], Outcome]) -> int:
    """Run `test`, print PASS or FAIL with timing, and return an exit code.

    Args:
        name: What is being tested, e.g. "Structured output (qwen3.5:9b)".
        test: The test body.

    Returns:
        0 on pass, 1 on fail.
    """
    start = time.monotonic()
    try:
        outcome = test()
    except ConnectionError:
        outcome = Outcome(False, f"Couldn't reach Ollama at {OLLAMA_HOST}. Is the service running?")
    except ollama.ResponseError as exc:
        outcome = Outcome(False, f"Ollama returned an error: {exc.error}")
    elapsed = time.monotonic() - start
    verdict = "PASS" if outcome.passed else "FAIL"
    print(f"{verdict}  {name}  ({elapsed:.1f} s)\n      {outcome.detail}")  # noqa: T201 - CLI output
    return 0 if outcome.passed else 1
