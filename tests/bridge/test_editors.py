"""EditorsBridge: the table preview and dimmed command comments."""

import gc

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor, QTextDocument

from recon.bridge.editors import PREVIEW_COLUMNS, PREVIEW_ROWS, CommentDimmer, EditorsBridge
from tests.ui.qml_harness import app, wait


def test_table_preview_of_a_small_table() -> None:
    app()

    preview = EditorsBridge().tablePreview("80, HTTP\n443, HTTPS")

    assert preview == {
        "grid": True,
        "rows": [["80", "HTTP"], ["443", "HTTPS"]],
        "columns": 2,
        "hiddenRows": 0,
        "hiddenColumns": 0,
    }


def test_table_preview_is_capped() -> None:
    app()
    width = PREVIEW_COLUMNS + 2
    text = "\n".join(",".join(f"r{r}c{c}" for c in range(width)) for r in range(PREVIEW_ROWS + 3))

    preview = EditorsBridge().tablePreview(text)

    assert len(preview["rows"]) == PREVIEW_ROWS
    assert preview["columns"] == PREVIEW_COLUMNS
    assert (preview["hiddenRows"], preview["hiddenColumns"]) == (3, 2)


def test_plain_text_is_no_grid() -> None:
    app()

    assert EditorsBridge().tablePreview("just words")["grid"] is False


def _formats(document: QTextDocument, line: int) -> list[tuple[int, int, str]]:
    block = document.findBlockByNumber(line)
    return [
        (f.start, f.length, f.format.foreground().color().name()) for f in block.layout().formats()
    ]


def test_comments_are_dimmed_and_the_rest_left_alone() -> None:
    app()
    document = QTextDocument()
    document.setPlainText("dig example.com MX  # who handles mail\ncurl http://x/#top")

    CommentDimmer(document, QColor("#84868f"))
    gc.collect()  # the document owns the highlighter
    wait(20)  # Qt highlights on the next turn of the event loop

    assert _formats(document, 0) == [(20, 18, "#84868f")]
    assert _formats(document, 1) == []


def test_dim_comments_ignores_anything_but_a_text_document() -> None:
    app()

    EditorsBridge().dimComments(QObject(), QColor("#84868f"))
