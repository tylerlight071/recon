"""A fake Ollama client: scripted replies and errors, every call recorded."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import ollama


@dataclass
class FakeClient:
    """Stands in for `ollama.Client` (the `services.ollama.Client` protocol)."""

    models: list[str] = field(default_factory=lambda: ["qwen3.5:9b", "qwen3-embedding:0.6b"])
    replies: list[str | BaseException] = field(default_factory=list)
    list_error: BaseException | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    def list(self) -> ollama.ListResponse:
        if self.list_error is not None:
            raise self.list_error
        return ollama.ListResponse(models=[ollama.ListResponse.Model(model=m) for m in self.models])

    def chat(
        self,
        model: str = "",
        messages: Sequence[Mapping[str, str]] | None = None,
        *,
        stream: bool = False,
        format: dict[str, object] | None = None,  # noqa: A002 - Ollama's own keyword
        options: Mapping[str, float] | None = None,
    ) -> object:
        self.calls.append(
            {
                "model": model,
                "messages": [dict(m) for m in messages or ()],
                "stream": stream,
                "format": format,
                "options": dict(options or {}),
            }
        )
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return ollama.ChatResponse(message=ollama.Message(role="assistant", content=reply))
