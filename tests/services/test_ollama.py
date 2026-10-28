"""services.ollama: loopback only, health checks, and validated structured calls (task 2.2)."""

import json
import logging
import stat
from pathlib import Path

import httpx
import ollama
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, Field

from recon.errors import (
    ModelCallFailedError,
    ModelMissing,
    ModelResponseInvalidError,
    OllamaTimeoutError,
    OllamaUnavailable,
    UnsafeHostError,
)
from recon.services.ollama import (
    DEFAULT_HOST,
    OllamaService,
    Status,
    loopback,
    make_client,
    same_model,
)
from recon.services.runs import RunLog
from tests.services.fakes import FakeClient

SECRET = "my private note about THM"  # noqa: S105 - note text, not a password


class Summary(BaseModel):
    """A tiny schema for the tests."""

    summary: str = Field(min_length=1)
    points: list[str]


GOOD = json.dumps({"summary": "DNS maps names to addresses.", "points": ["A records"]})


def _call(client: FakeClient, run: RunLog | None = None) -> Summary:
    return OllamaService(client).structured(
        model="qwen3.5:9b",
        schema=Summary,
        system="Summarise the notes.",
        prompt=f"<notes>{SECRET}</notes>",
        run=run,
        step="extract",
    )


# ---- Loopback only (hard rule 1) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "used"),
    [
        (DEFAULT_HOST, DEFAULT_HOST),
        ("http://localhost:11434", "http://localhost:11434"),
        ("http://LOCALHOST:11434/", "http://localhost:11434"),
        ("http://[::1]:11434", "http://[::1]:11434"),
        ("http://127.0.0.2:11434", "http://127.0.0.2:11434"),
        ("https://127.0.0.1", "https://127.0.0.1:443"),
        ("http://127.0.0.1", "http://127.0.0.1:80"),
        ("127.0.0.1:11434", "http://127.0.0.1:11434"),
        ("127.0.0.1", "http://127.0.0.1:11434"),
        ("localhost", "http://localhost:11434"),
        ("http://127.0.0.1:11434/some/path?x=1#y", "http://127.0.0.1:11434"),
    ],
)
def test_this_computer_is_allowed(host: str, used: str) -> None:
    assert loopback(host) == used


@pytest.mark.parametrize(
    "host",
    [
        "http://10.0.0.5:11434",
        "http://192.168.1.20:11434",
        "http://0.0.0.0:11434",
        "http://ollama.example.com",
        "http://tryhackme.com",
        "http://127.0.0.1.nip.io:11434",
        "http://localhost.evil.com",
        "http://127.0.0.1@evil.com",
        "http://127.0.0.1\\@evil.com",
        "http://user:pass@127.0.0.1:11434",
        "http://127.0.0.1:99999",
        "http://127.0.0.1:port",
        "ftp://127.0.0.1",
        "file:///etc/passwd",
        "",
        "http://",
    ],
)
def test_any_other_machine_is_refused(host: str) -> None:
    with pytest.raises(UnsafeHostError):
        loopback(host)
    with pytest.raises(UnsafeHostError):
        make_client(host)


@given(st.ip_addresses())
def test_only_loopback_addresses_pass(address: object) -> None:
    import ipaddress  # noqa: PLC0415 - only this property test needs it

    ip = ipaddress.ip_address(str(address))
    host = f"http://[{ip}]:1" if ip.version == 6 else f"http://{ip}:1"
    if ip.is_loopback:
        assert loopback(host) == host
    else:
        with pytest.raises(UnsafeHostError):
            loopback(host)


def test_make_client_points_at_this_computer() -> None:
    client = make_client(DEFAULT_HOST, timeout=5)

    assert isinstance(client, ollama.Client)
    assert str(client._client.base_url).startswith("http://127.0.0.1:11434")
    assert client._client.timeout.read == 5


# ---- Health and models -------------------------------------------------------------------


def test_model_names_match_with_or_without_latest() -> None:
    assert same_model("nomic-embed-text", "nomic-embed-text:latest")
    assert same_model("qwen3.5:9b", "qwen3.5:9b")
    assert not same_model("qwen3.5:9b", "qwen3.5:4b")


def test_status_ready_when_every_model_is_installed() -> None:
    status = OllamaService(FakeClient()).status(["qwen3.5:9b", "qwen3-embedding:0.6b"])

    assert status == Status(running=True)
    assert status.ok


def test_status_names_what_is_missing() -> None:
    client = FakeClient(models=["qwen3.5:9b", "llama3:latest"])

    status = OllamaService(client).status(["qwen3.5:9b", "qwen3-embedding:0.6b", "llama3"])

    assert status == Status(running=True, missing=("qwen3-embedding:0.6b",))
    assert not status.ok


@pytest.mark.parametrize(
    "error",
    [
        ConnectionError("Failed to connect"),
        httpx.ConnectTimeout("slow"),
        httpx.RemoteProtocolError("bad"),
        ollama.ResponseError("internal", 500),
    ],
)
def test_status_says_not_running_and_never_raises(error: BaseException) -> None:
    status = OllamaService(FakeClient(list_error=error)).status(["qwen3.5:9b"])

    assert status == Status(running=False)
    assert not status.ok


def test_installed_raises_unavailable() -> None:
    with pytest.raises(OllamaUnavailable):
        OllamaService(FakeClient(list_error=ConnectionError())).installed()


# ---- Structured calls ----------------------------------------------------------------------


def test_a_good_reply_is_validated_and_returned() -> None:
    client = FakeClient(replies=[GOOD])

    result = _call(client)

    assert result == Summary(summary="DNS maps names to addresses.", points=["A records"])
    (call,) = client.calls
    assert call["format"] == Summary.model_json_schema()
    assert call["options"] == {"temperature": 0, "num_ctx": 16_384}
    assert call["stream"] is False
    assert call["think"] is False
    assert call["model"] == "qwen3.5:9b"


def test_the_schema_is_described_in_the_prompt_too() -> None:
    client = FakeClient(replies=[GOOD])

    _call(client)

    system, user = client.calls[0]["messages"]  # type: ignore[misc]  # a list of two dicts
    assert system["role"] == "system"
    assert system["content"].startswith("Summarise the notes.")
    assert json.dumps(Summary.model_json_schema()) in system["content"]
    assert user == {"role": "user", "content": f"<notes>{SECRET}</notes>"}


def test_one_retry_with_the_validation_error_then_success() -> None:
    client = FakeClient(replies=['{"summary": "", "points": "nope"}', GOOD])

    result = _call(client)

    assert result.summary == "DNS maps names to addresses."
    retry = client.calls[1]["messages"]
    assert isinstance(retry, list)
    assert retry[2] == {"role": "assistant", "content": '{"summary": "", "points": "nope"}'}
    note = retry[3]["content"]
    assert retry[3]["role"] == "user"
    assert "summary" in note
    assert "points" in note
    assert "match the schema" in note
    assert "nope" not in note  # where and what, never the input itself


def test_invalid_twice_fails_the_step_cleanly() -> None:
    client = FakeClient(replies=["not json", "still not json", GOOD])

    with pytest.raises(ModelResponseInvalidError):
        _call(client)
    assert len(client.calls) == 2  # exactly one retry


@pytest.mark.parametrize(
    ("error", "raised"),
    [
        (ConnectionError("Failed to connect to Ollama"), OllamaUnavailable),
        (httpx.ReadTimeout("slow"), OllamaTimeoutError),
        (httpx.ConnectTimeout("slow"), OllamaTimeoutError),
        (httpx.RemoteProtocolError("dropped"), OllamaUnavailable),
        (ollama.ResponseError("model 'qwen3.5:9b' not found", 404), ModelMissing),
        (ollama.ResponseError("out of memory", 500), ModelCallFailedError),
    ],
)
def test_errors_become_plain_ones(error: BaseException, raised: type[Exception]) -> None:
    with pytest.raises(raised) as caught:
        _call(FakeClient(replies=[error]))
    assert caught.value.__cause__ is error


def test_a_timeout_is_still_ollama_being_unavailable() -> None:
    assert issubclass(OllamaTimeoutError, OllamaUnavailable)


def test_an_empty_reply_counts_as_invalid() -> None:
    with pytest.raises(ModelResponseInvalidError):
        _call(FakeClient(replies=["", ""]))


# ---- Raw replies go to the run, never to app.log -------------------------------------------


def test_every_raw_reply_is_kept_privately_in_the_run(tmp_path: Path) -> None:
    run = RunLog(tmp_path / "runs" / "20261028T120000-abcd")
    client = FakeClient(replies=["not json", GOOD])

    _call(client, run)

    first = json.loads((run.folder / "extract-1.json").read_text())
    second = json.loads((run.folder / "extract-2.json").read_text())
    assert first["reply"] == "not json"
    assert second["reply"] == GOOD
    assert first["model"] == "qwen3.5:9b"
    assert SECRET in first["messages"][1]["content"]
    assert len(second["messages"]) == 4
    assert stat.S_IMODE(run.folder.stat().st_mode) == 0o700
    assert stat.S_IMODE((run.folder / "extract-1.json").stat().st_mode) == 0o600


def test_app_log_gets_ids_counts_and_timings_only(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ModelResponseInvalidError):
        _call(FakeClient(replies=['{"summary": "' + SECRET + '"}', "x" + SECRET]))
    _call(FakeClient(replies=[GOOD]))

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "extract" in logged
    assert "qwen3.5:9b" in logged
    assert SECRET not in logged
    assert "DNS maps" not in logged
    assert "Summarise" not in logged
