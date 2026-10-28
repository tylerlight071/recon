"""Talking to the local Ollama server: the only module allowed the network (task 2.2).

- **Loopback only.** The address must be this computer (127.0.0.1, ::1 or
  localhost); anything else is refused before a client exists (hard rule 1).
- **Health and models.** `status()` says whether Ollama answers and which of
  Recon's models are missing, without raising, for the Settings screen.
- **Structured calls.** `structured()` passes the pydantic schema as `format`,
  describes it in the prompt too, uses temperature 0, validates the reply,
  and retries once with the validation errors before failing cleanly
  (CLAUDE.md, Model rules). Every raw reply goes to the run's folder, never
  to `app.log`.
"""

import ipaddress
import json
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol
from urllib.parse import urlsplit

import httpx
import ollama
from pydantic import BaseModel, ValidationError

from recon.errors import (
    ModelCallFailedError,
    ModelMissing,
    ModelResponseInvalidError,
    OllamaTimeoutError,
    OllamaUnavailable,
    UnsafeHostError,
)
from recon.logging_setup import Safe
from recon.services.runs import RunLog

DEFAULT_PORT: Final = 11434
DEFAULT_HOST: Final = f"http://127.0.0.1:{DEFAULT_PORT}"
TIMEOUT_S: Final = 300.0
"""Generous: the first call after a while loads the model into VRAM."""
CONTEXT_TOKENS: Final = 16_384
"""Context per call. Ollama's default is 4k on cards under 24 GB, too small for a
whole room plus its schema, and it truncates silently, so every call sets it."""
CHECK_TIMEOUT_S: Final = 5.0
"""Health checks only list models, so a slow answer means something's wrong."""
_LOOPBACK_NAMES: Final = frozenset({"localhost"})

_log = logging.getLogger(__name__)


class Client(Protocol):
    """The parts of `ollama.Client` Recon uses (tests pass a fake)."""

    def list(self) -> ollama.ListResponse:
        """Installed models."""

    def chat(  # noqa: PLR0913 - mirrors ollama.Client.chat
        self,
        model: str = "",
        messages: Sequence[Mapping[str, str]] | None = None,
        *,
        stream: bool = False,
        think: bool | None = None,
        format: dict[str, object] | None = None,  # noqa: A002 - Ollama's own keyword
        options: Mapping[str, float] | None = None,
    ) -> object:
        """One chat completion (Recon never streams)."""


@dataclass(frozen=True, slots=True)
class _Call:
    """One structured call: what each attempt shares."""

    model: str
    step: str
    shape: dict[str, object]
    run: RunLog | None
    think: bool
    context: int


@dataclass(frozen=True, slots=True)
class Status:
    """What Settings shows about Ollama."""

    running: bool
    missing: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Running, with every model Recon needs installed."""
        return self.running and not self.missing


def loopback(host: str) -> str:
    """`host` rebuilt as scheme://address:port, if it's this computer.

    The client is given this rebuilt address, never `host` itself, so no
    difference between this parser and Ollama's can point it elsewhere.

    Raises:
        UnsafeHostError: It names any other machine, has a user name or
            password in it, or isn't an http(s) address.
    """
    has_scheme = "://" in host
    parts = urlsplit(host if has_scheme else f"http://{host}")
    try:
        port = parts.port
    except ValueError as exc:  # out of range or not a number
        raise UnsafeHostError from exc
    name = parts.hostname or ""
    if (
        parts.scheme not in {"http", "https"}
        or parts.username is not None
        or not _is_loopback(name)
    ):
        raise UnsafeHostError
    if port is None:
        # As Ollama reads it: a bare address means its own port.
        port = (443 if parts.scheme == "https" else 80) if has_scheme else DEFAULT_PORT
    address = f"[{name}]" if ":" in name else name
    return f"{parts.scheme}://{address}:{port}"


def _is_loopback(name: str) -> bool:
    if name.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def make_client(host: str = DEFAULT_HOST, timeout: float = TIMEOUT_S) -> ollama.Client:
    """An Ollama client for this computer only (refuses any other host)."""
    return ollama.Client(host=loopback(host), timeout=timeout)


def same_model(a: str, b: str) -> bool:
    """Whether two model names mean the same model ("qwen3" is "qwen3:latest")."""

    def full(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    return full(a) == full(b)


class OllamaService:
    """Health checks and validated, structured model calls."""

    def __init__(self, client: Client) -> None:
        """Use `client` (from `make_client`, or a fake in tests)."""
        self._client = client

    def installed(self) -> list[str]:
        """Names of the models Ollama has.

        Raises:
            OllamaUnavailable: Ollama isn't answering.
        """
        try:
            listed = self._client.list()
        except (ConnectionError, httpx.HTTPError, ollama.ResponseError) as exc:
            raise OllamaUnavailable from exc
        return [m.model for m in listed.models if m.model]

    def status(self, models: Sequence[str]) -> Status:
        """Whether Ollama answers and which of `models` are missing. Never raises."""
        try:
            installed = self.installed()
        except OllamaUnavailable:
            return Status(running=False)
        missing = tuple(m for m in models if not any(same_model(m, i) for i in installed))
        return Status(running=True, missing=missing)

    def structured[T: BaseModel](  # noqa: PLR0913 - keyword-only; each is one part of the call
        self,
        *,
        model: str,
        schema: type[T],
        system: str,
        prompt: str,
        run: RunLog | None = None,
        step: str = "call",
        think: bool = False,
        context: int = CONTEXT_TOKENS,
    ) -> T:
        """Ask `model` for JSON matching `schema`, validated, with one retry.

        Args:
            model: The Ollama model (from Settings).
            schema: What the reply must be; sent as `format` and described in the prompt.
            system: The step's instructions (from `engine/prompts/`).
            prompt: The step's input; untrusted text belongs between delimiters.
            run: Where raw replies are kept (none in health checks).
            step: The step's name, for the run's file names.
            think: Let a thinking model reason first (slower; the bake-off decides).
            context: Tokens of context for the call (`num_ctx`).

        Returns:
            The validated reply.

        Raises:
            OllamaUnavailable: Ollama isn't answering.
            OllamaTimeoutError: It didn't answer in time.
            ModelMissing: `model` isn't installed.
            ModelCallFailedError: Ollama answered with another error.
            ModelResponseInvalidError: Both replies failed validation.
        """
        call = _Call(
            model=model,
            step=step,
            shape=schema.model_json_schema(),
            run=run,
            think=think,
            context=context,
        )
        messages = [
            {"role": "system", "content": f"{system}\n\n{_describe(call.shape)}"},
            {"role": "user", "content": prompt},
        ]
        for attempt in (1, 2):
            raw = self._chat(call, messages, attempt)
            try:
                return schema.model_validate_json(raw)
            except ValidationError as exc:
                _log.warning(
                    "model reply for %s failed validation (attempt %s, %s errors)",
                    Safe(step),
                    attempt,
                    exc.error_count(),
                )
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": _retry_note(exc)},
                ]
        raise ModelResponseInvalidError

    def _chat(self, call: _Call, messages: list[dict[str, str]], attempt: int) -> str:
        started = time.monotonic()
        try:
            response = self._client.chat(
                model=call.model,
                messages=messages,
                format=call.shape,
                options={"temperature": 0, "num_ctx": call.context},
                think=call.think,
                stream=False,
            )
        except ConnectionError as exc:
            raise OllamaUnavailable from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError from exc
        except httpx.HTTPError as exc:
            raise OllamaUnavailable from exc
        except ollama.ResponseError as exc:
            if exc.status_code == 404:  # noqa: PLR2004 - HTTP "not found": the model isn't there
                raise ModelMissing from exc
            raise ModelCallFailedError from exc
        seconds = round(time.monotonic() - started, 2)
        raw = _content(response)
        _log.info(
            "model %s answered %s (attempt %s) in %s s",
            Safe(call.model),
            Safe(call.step),
            attempt,
            seconds,
        )
        if call.run is not None:
            call.run.record(
                call.step,
                attempt,
                {"model": call.model, "seconds": seconds, "messages": messages, "reply": raw},
            )
        return raw


def _content(response: object) -> str:
    message = getattr(response, "message", None)
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else ""


def _describe(shape: dict[str, object]) -> str:
    return "Reply with JSON only, matching this JSON Schema exactly:\n" + json.dumps(
        shape, ensure_ascii=False
    )


def _retry_note(exc: ValidationError) -> str:
    # Where and what, never the offending input: it may echo the notes back.
    problems = "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'reply'}: {error['msg']}"
        for error in exc.errors(include_input=False, include_url=False)
    )
    return (
        "That reply didn't match the schema: "
        f"{problems}. Reply again with JSON that matches the schema exactly."
    )
