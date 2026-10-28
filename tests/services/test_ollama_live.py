"""services.ollama against the real local Ollama (`-m ollama`; not run in CI).

Proves the wrapper works with the real server and the default models: the
health check sees them, and a structured call comes back valid.
"""

from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from recon.config import Settings
from recon.errors import ModelMissing
from recon.services.ollama import OllamaService, make_client
from recon.services.runs import RunLog

pytestmark = pytest.mark.ollama


class Ports(BaseModel):
    """What a tiny invented note says about ports."""

    summary: str = Field(min_length=1)
    ports: list[int]


def _service() -> OllamaService:
    return OllamaService(make_client(Settings().ollama_host))


def test_the_default_models_are_installed() -> None:
    status = _service().status(Settings().models)

    assert status.running
    assert status.missing == ()


def test_a_structured_call_returns_valid_data(tmp_path: Path) -> None:
    run = RunLog(tmp_path / "run")

    result = _service().structured(
        model=Settings().text_model,
        schema=Ports,
        system="Read the notes and list every port number they mention.",
        prompt="<notes>SSH listens on 22 and HTTPS on 443.</notes>",
        run=run,
        step="ports",
    )

    assert sorted(result.ports) == [22, 443]
    assert (run.folder / "ports-1.json").exists()


def test_a_missing_model_is_reported_plainly() -> None:
    with pytest.raises(ModelMissing):
        _service().structured(
            model="recon-test-no-such-model:1b",
            schema=Ports,
            system="x",
            prompt="x",
        )
