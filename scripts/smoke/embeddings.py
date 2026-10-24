"""Smoke test: embeddings rank a related sentence above an unrelated one.

    uv run python -m scripts.smoke.embeddings [--model qwen3-embedding:0.6b]

Recon links concepts by cosine similarity of Ollama embeddings (SPEC.md,
Linking). This proves the embedding model loads and gives sensible scores.
"""

import sys
from collections.abc import Sequence

import numpy as np

from scripts.smoke._common import Outcome, make_client, model_arg, run

ANCHOR = "The TCP three-way handshake is SYN, then SYN-ACK, then ACK."
RELATED = "A TCP connection opens with a SYN packet, a SYN/ACK reply and a final ACK."
UNRELATED = "Hexadecimal uses sixteen digits, 0 to 9 and A to F."
EXPECTED_DIMENSIONS = 1024


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two vectors.

    Args:
        a: First vector.
        b: Second vector, the same length as `a`.

    Returns:
        A value in [-1, 1]; 0.0 when either vector is all zeros.
    """
    va, vb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return 0.0 if norm == 0 else float(va @ vb) / norm


def check_vectors(vectors: Sequence[Sequence[float]]) -> Outcome:
    """Check the three vectors' size and that the related pair scores higher.

    Args:
        vectors: Embeddings of ANCHOR, RELATED and UNRELATED, in that order.

    Returns:
        Pass when all are the expected size and related > unrelated.
    """
    anchor, related, unrelated = vectors
    sizes = {len(vector) for vector in vectors}
    if sizes != {EXPECTED_DIMENSIONS}:
        return Outcome(False, f"Vector sizes were {sorted(sizes)}; expected {EXPECTED_DIMENSIONS}")
    near, far = cosine(anchor, related), cosine(anchor, unrelated)
    detail = f"related {near:.3f}, unrelated {far:.3f}, {EXPECTED_DIMENSIONS} dimensions"
    return Outcome(near > far, detail)


def embed_and_check(model: str) -> Outcome:
    """Embed the three sentences in one call and check them.

    Args:
        model: Ollama embedding model tag.

    Returns:
        The outcome.
    """
    response = make_client().embed(model=model, input=[ANCHOR, RELATED, UNRELATED])
    return check_vectors(response.embeddings)


def main(argv: list[str]) -> int:
    """Parse arguments and run the smoke test.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        0 on pass, 1 on fail.
    """
    args = model_arg(__doc__ or "", "qwen3-embedding:0.6b").parse_args(argv)
    return run(f"Embeddings ({args.model})", lambda: embed_and_check(args.model))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
