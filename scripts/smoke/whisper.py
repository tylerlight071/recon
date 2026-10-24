"""Smoke test: faster-whisper large-v3-turbo transcribes a 5-second clip on the GPU.

    RECON_MODULE=scripts.smoke.whisper packaging/recon-launch [--compute-type float16]

Run it through `packaging/recon-launch`, which puts the cuBLAS wheel's folder on
LD_LIBRARY_PATH before Python starts; that's the riskiest part on Blackwell
(sm_120). The first run downloads the model from Hugging Face (about 1.6 GB)
and a public-domain test clip from faster-whisper's own test data, pinned to a
commit and checked by SHA-256.
"""

import argparse
import hashlib
import os
import re
import sys
import time
import urllib.request
from collections.abc import Mapping
from pathlib import Path

from scripts.smoke._common import Outcome, run

CLIP_URL = (
    "https://raw.githubusercontent.com/SYSTRAN/faster-whisper/"
    "9e472ae9de8bb374552f531f752654554b76b2d6/tests/data/jfk.flac"
)
CLIP_SHA256 = "63a4b1e4c1dc655ac70961ffbf518acd249df237e5a0152faae9a4a836949715"
CLIP_SECONDS = 5
SAMPLE_RATE = 16_000
EXPECTED_WORDS = "my fellow americans"
"""The first five seconds of the clip are "And so, my fellow Americans..."."""
MODEL = "large-v3-turbo"


def cache_dir(env: Mapping[str, str], home: Path) -> Path:
    """Where the downloaded clip is kept: `$XDG_CACHE_HOME/recon/smoke`.

    Args:
        env: Environment mapping.
        home: The user's home folder.

    Returns:
        The folder path (not created).
    """
    base = env.get("XDG_CACHE_HOME", "")
    root = Path(base) if base and Path(base).is_absolute() else home / ".cache"
    return root / "recon" / "smoke"


def sha256_of(path: Path) -> str:
    """Hex SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_clip(folder: Path) -> Path:
    """Download the test clip once, verifying its checksum.

    Args:
        folder: Cache folder; created 0700 if missing.

    Returns:
        Path of the verified clip.

    Raises:
        ValueError: The download didn't match the pinned checksum.
    """
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    clip = folder / "jfk.flac"
    if clip.exists() and sha256_of(clip) == CLIP_SHA256:
        return clip
    partial = clip.with_suffix(".part")
    # Fixed https URL pinned to a commit; not user input.
    with urllib.request.urlopen(CLIP_URL, timeout=60) as response:
        partial.write_bytes(response.read())
    if sha256_of(partial) != CLIP_SHA256:
        partial.unlink()
        msg = "test clip checksum mismatch"
        raise ValueError(msg)
    partial.replace(clip)
    return clip


def cublas_on_path(env: Mapping[str, str]) -> bool:
    """Whether LD_LIBRARY_PATH includes the nvidia-cublas-cu12 wheel's folder."""
    return any(
        part.endswith("nvidia/cublas/lib") for part in env.get("LD_LIBRARY_PATH", "").split(":")
    )


def check_transcript(text: str) -> Outcome:
    """Pass when the transcript contains the clip's opening words.

    Args:
        text: Joined segment texts.

    Returns:
        The outcome, quoting what was heard.
    """
    heard = re.sub(r"[^a-z ]", "", text.casefold())
    heard = re.sub(r"\s+", " ", heard).strip()
    return Outcome(EXPECTED_WORDS in heard, f'Heard: "{text.strip()}"')


def transcribe(compute_type: str, env: Mapping[str, str]) -> Outcome:
    """Load the model on CUDA and transcribe the first five seconds.

    Args:
        compute_type: CTranslate2 compute type, e.g. "float16".
        env: Environment, checked for the cuBLAS path.

    Returns:
        The outcome with load and transcription times.
    """
    from faster_whisper import WhisperModel, decode_audio  # noqa: PLC0415 - heavy; only when run

    clip = fetch_clip(cache_dir(env, Path.home()))
    audio = decode_audio(str(clip), sampling_rate=SAMPLE_RATE)[: CLIP_SECONDS * SAMPLE_RATE]
    start = time.monotonic()
    try:
        model = WhisperModel(MODEL, device="cuda", compute_type=compute_type)
        loaded = time.monotonic()
        segments, _info = model.transcribe(audio, language="en", beam_size=5)
        text = " ".join(segment.text for segment in segments)
    except RuntimeError as exc:
        hint = "" if cublas_on_path(env) else " (cuBLAS isn't on LD_LIBRARY_PATH: use recon-launch)"
        return Outcome(False, f"CUDA error: {exc}{hint}")
    done = time.monotonic()
    outcome = check_transcript(text)
    timing = f"; model load {loaded - start:.1f} s, transcription {done - loaded:.2f} s"
    return Outcome(outcome.passed, outcome.detail + timing)


def main(argv: list[str]) -> int:
    """Parse arguments and run the smoke test.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        0 on pass, 1 on fail.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compute-type", default="float16", help="CTranslate2 compute type")
    args = parser.parse_args(argv)
    env = dict(os.environ)
    return run(
        f"Whisper {MODEL} on CUDA ({args.compute_type})",
        lambda: transcribe(args.compute_type, env),
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
