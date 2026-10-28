"""scripts/record_responses.py writes each fixture room's reply (faked here; no Ollama)."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from scripts import record_responses
from tests.engine.pipeline import recorded


class _Service:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def structured[T: BaseModel](
        self, *, schema: type[T], model: str, think: bool, **_: object
    ) -> T:
        self.calls.append((model, think))
        return schema.model_validate(recorded("number_systems").model_dump())


def test_records_the_named_rooms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    service = _Service()
    monkeypatch.setattr(record_responses, "RESPONSES", tmp_path)
    monkeypatch.setattr(record_responses, "make_client", lambda _host: None)
    monkeypatch.setattr(record_responses, "OllamaService", lambda _client: service)

    assert record_responses.main(["--model", "gemma4:12b", "--think", "number_systems"]) == 0

    written = json.loads((tmp_path / "number_systems.extract.json").read_text())
    assert written == recorded("number_systems").model_dump()
    assert service.calls == [("gemma4:12b", True)]
    assert "number_systems:" in capsys.readouterr().out
