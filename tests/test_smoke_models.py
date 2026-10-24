"""Ollama smoke tests: pure checks run everywhere; real-model runs need `-m ollama`."""

import io
import json

import pytest
from PIL import Image

from scripts.smoke import _common, embeddings, structured, vision
from scripts.smoke._common import Outcome

# Structured output -----------------------------------------------------------


def test_extraction_accepts_expected_ports() -> None:
    raw = json.dumps(
        {
            "summary": "Ports.",
            "ports": [{"port": 22, "protocol": "ssh"}, {"port": 443, "protocol": "HTTPS"}],
        }
    )

    assert structured.check_extraction(raw).passed


def test_extraction_rejects_wrong_ports() -> None:
    raw = json.dumps({"summary": "Ports.", "ports": [{"port": 80, "protocol": "HTTPS"}]})

    outcome = structured.check_extraction(raw)

    assert not outcome.passed
    assert "expected" in outcome.detail


@pytest.mark.parametrize(
    "raw", ["not json", '{"summary": "", "ports": []}', '{"ports": [{"port": 99999}]}']
)
def test_extraction_rejects_invalid_replies(raw: str) -> None:
    outcome = structured.check_extraction(raw)

    assert not outcome.passed
    assert "didn't validate" in outcome.detail


def test_prompt_delimits_notes_as_data() -> None:
    text = structured.prompt()

    assert f"<notes>\n{structured.NOTES}</notes>" in text
    assert "not instructions" in text


# Embeddings -----------------------------------------------------------------


def test_cosine() -> None:
    assert embeddings.cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert embeddings.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert embeddings.cosine([1, 0], [-1, 0]) == pytest.approx(-1.0)
    assert embeddings.cosine([0, 0], [1, 0]) == 0.0


def _vector(first: float, second: float) -> list[float]:
    return [first, second] + [0.0] * (embeddings.EXPECTED_DIMENSIONS - 2)


def test_vectors_pass_when_related_is_closer() -> None:
    outcome = embeddings.check_vectors([_vector(1, 0), _vector(0.9, 0.1), _vector(0, 1)])

    assert outcome.passed


def test_vectors_fail_when_unrelated_is_closer() -> None:
    assert not embeddings.check_vectors([_vector(1, 0), _vector(0, 1), _vector(0.9, 0.1)]).passed


def test_vectors_fail_on_wrong_size() -> None:
    outcome = embeddings.check_vectors([[1.0], [1.0], [1.0]])

    assert not outcome.passed
    assert "sizes" in outcome.detail


# Vision ---------------------------------------------------------------------


def test_rendered_table_is_a_png_of_the_right_size() -> None:
    image = Image.open(io.BytesIO(vision.render_table_png()))

    assert image.format == "PNG"
    assert image.size == (3 * 260 + 40, 3 * 64 + 40)


def test_table_check_ignores_case_and_spacing() -> None:
    rows = [
        ["port", "PROTOCOL", "Use"],
        ["22", "SSH", "Remote  shell"],
        ["443", "HTTPS", "secure web "],
    ]

    assert vision.check_table(json.dumps({"rows": rows})).passed


def test_table_check_rejects_a_misread_cell() -> None:
    rows = [
        ["Port", "Protocol", "Use"],
        ["22", "SSH", "Remote shell"],
        ["433", "HTTPS", "Secure web"],
    ]

    assert not vision.check_table(json.dumps({"rows": rows})).passed


def test_table_check_rejects_invalid_json() -> None:
    assert not vision.check_table('{"rows": "nope"}').passed


# Runner ---------------------------------------------------------------------


def test_run_reports_pass_and_fail(capsys: pytest.CaptureFixture[str]) -> None:
    assert _common.run("ok", lambda: Outcome(True, "fine")) == 0
    assert _common.run("bad", lambda: Outcome(False, "broken")) == 1

    out = capsys.readouterr().out
    assert "PASS  ok" in out
    assert "FAIL  bad" in out


def test_run_turns_connection_errors_into_a_plain_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def refuse() -> Outcome:
        raise ConnectionError

    assert _common.run("x", refuse) == 1
    assert "Couldn't reach Ollama at http://127.0.0.1:11434" in capsys.readouterr().out


def test_run_reports_ollama_errors(capsys: pytest.CaptureFixture[str]) -> None:
    def missing() -> Outcome:
        message = "model 'x' not found"
        raise _common.ollama.ResponseError(message, 404)

    assert _common.run("x", missing) == 1
    assert "model 'x' not found" in capsys.readouterr().out


def test_client_is_pinned_to_loopback() -> None:
    assert _common.OLLAMA_HOST.startswith("http://127.0.0.1:")
    assert str(_common.make_client()._client.base_url).startswith("http://127.0.0.1:11434")


# Real models (local only) ---------------------------------------------------


@pytest.mark.ollama
def test_real_embeddings() -> None:
    assert embeddings.main([]) == 0


@pytest.mark.ollama
@pytest.mark.parametrize("model", ["qwen3.5:9b", "gemma4:12b"])
@pytest.mark.parametrize("think", [False, True])
def test_real_structured_output(model: str, *, think: bool) -> None:
    assert structured.main(["--model", model, *(["--think"] if think else [])]) == 0


@pytest.mark.ollama
@pytest.mark.parametrize("model", ["qwen3.5:9b", "gemma4:12b"])
def test_real_vision(model: str) -> None:
    assert vision.main(["--model", model]) == 0
