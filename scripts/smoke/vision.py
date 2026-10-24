"""Smoke test: the vision model reads a small table back from a generated PNG.

    uv run python -m scripts.smoke.vision [--model qwen3.5:9b]

Recon reads text and tables from screenshots (SPEC.md, pipeline step 2). This
draws a table with Pillow, sends it with a JSON schema, and checks every cell
comes back.
"""

import io
import re
import sys

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, ValidationError

from scripts.smoke._common import Outcome, make_client, model_arg, run

TABLE = (("Port", "Protocol", "Use"), ("22", "SSH", "Remote shell"), ("443", "HTTPS", "Secure web"))
_CELL_W, _CELL_H, _PAD, _FONT_PX = 260, 64, 20, 30


class ReadTable(BaseModel):
    """A table read from an image, row by row, including the header row."""

    rows: list[list[str]] = Field(max_length=20)


def render_table_png(table: tuple[tuple[str, ...], ...] = TABLE) -> bytes:
    """Draw `table` as black text on white with grid lines.

    Args:
        table: Rows of cell text; the first row is the header.

    Returns:
        PNG bytes.
    """
    columns = len(table[0])
    image = Image.new(
        "RGB", (columns * _CELL_W + 2 * _PAD, len(table) * _CELL_H + 2 * _PAD), "white"
    )
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=_FONT_PX)
    for row_index, row in enumerate(table):
        for col_index, cell in enumerate(row):
            left = _PAD + col_index * _CELL_W
            top = _PAD + row_index * _CELL_H
            draw.rectangle((left, top, left + _CELL_W, top + _CELL_H), outline="black", width=2)
            draw.text((left + 14, top + 16), cell, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def check_table(raw: str, expected: tuple[tuple[str, ...], ...] = TABLE) -> Outcome:
    """Validate the reply and check every expected cell appears in order.

    Args:
        raw: The model's message content.
        expected: The table that was drawn.

    Returns:
        Pass when the rows match the drawn table, ignoring case and spacing.
    """
    try:
        rows = ReadTable.model_validate_json(raw).rows
    except ValidationError as exc:
        return Outcome(False, f"Reply didn't validate: {exc.error_count()} error(s)")
    got = [[_norm(cell) for cell in row] for row in rows]
    want = [[_norm(cell) for cell in row] for row in expected]
    if got != want:
        return Outcome(False, f"Read {rows!r}; expected {[list(r) for r in expected]!r}")
    return Outcome(True, f"Read all {sum(map(len, expected))} cells correctly")


def read_table(model: str) -> Outcome:
    """Send the generated image and check the table that comes back.

    Args:
        model: Ollama vision model tag.

    Returns:
        The outcome.
    """
    response = make_client().chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": (
                    "Read the table in this image. Return JSON with `rows`: a list of rows, "
                    "each a list of the cell texts exactly as shown, header row first."
                ),
                "images": [render_table_png()],
            }
        ],
        format=ReadTable.model_json_schema(),
        options={"temperature": 0},
        think=False,
    )
    return check_table(response.message.content or "")


def main(argv: list[str]) -> int:
    """Parse arguments and run the smoke test.

    Args:
        argv: Command-line arguments without the program name.

    Returns:
        0 on pass, 1 on fail.
    """
    args = model_arg(__doc__ or "", "qwen3.5:9b").parse_args(argv)
    return run(f"Vision table ({args.model})", lambda: read_table(args.model))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
