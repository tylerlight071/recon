"""Record the real model's extract replies for the fixture rooms (tests run on these).

Pipeline tests replay these replies, so the whole pipeline is tested without a
GPU (CLAUDE.md, Testing). Re-record when the prompt or schema changes:

    uv run python -m scripts.record_responses [--model qwen3.5:9b]

Needs the local Ollama. Writes `tests/fixtures/responses/<room>.extract.json`
(the reply as validated, before the checks in code) and prints the time each took.
"""

import argparse
import json
import sys
import time

from recon.config import Settings
from recon.engine.extract import ask
from recon.services.ollama import OllamaService, make_client
from tests.engine.pipeline import RESPONSES, capture_of
from tests.fixture_rooms import all_rooms


def main(argv: list[str]) -> int:
    """Record every fixture room (or the ones named)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=Settings().text_model)
    parser.add_argument("--think", action="store_true", help="let the model reason first")
    parser.add_argument("rooms", nargs="*", help="fixture names (default: all)")
    args = parser.parse_args(argv)
    service = OllamaService(make_client(Settings().ollama_host))
    RESPONSES.mkdir(parents=True, exist_ok=True)
    for name in args.rooms or sorted(all_rooms()):
        started = time.monotonic()
        reply = ask(capture_of(name), service, args.model, None, think=args.think)
        path = RESPONSES / f"{name}.extract.json"
        path.write_text(json.dumps(reply.model_dump(), indent=2, ensure_ascii=False) + "\n")
        print(f"{name}: {time.monotonic() - started:.1f} s -> {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
