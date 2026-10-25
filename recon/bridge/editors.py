"""Help for block editors, exposed to QML as `Editors` (task 1.10).

- `tablePreview(text)`: the Table block's grid preview, from the same parser
  the vault templates will use.
- `dimComments(document, colour)`: shows the `# what it does` part of each
  Command line in a quieter colour, without changing the text.

Pure presentation: nothing here reads or writes files.
"""

from typing import Final

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextDocument
from PySide6.QtQuick import QQuickTextDocument

from recon.engine.parse import comment_start, parse_table

PREVIEW_ROWS: Final = 12
PREVIEW_COLUMNS: Final = 6
"""The preview shows this much; the note keeps everything."""


class CommentDimmer(QSyntaxHighlighter):
    """Colours shell-style `#` comments in a Command block."""

    def __init__(self, document: QTextDocument, colour: QColor) -> None:
        """Attach to `document` (which owns this highlighter from now on)."""
        super().__init__(document)
        self._format = QTextCharFormat()
        self._format.setForeground(colour)

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        """Dim the comment on one line, if it has one."""
        start = comment_start(text)
        if start is not None:
            self.setFormat(start, len(text) - start, self._format)


class EditorsBridge(QObject):
    """Table previews and comment dimming for the block editors."""

    @Slot(str, result="QVariantMap")
    def tablePreview(self, text: str) -> dict[str, object]:  # noqa: N802 - Qt naming, used from QML
        """The grid to show under a Table block.

        Args:
            text: The block's text.

        Returns:
            grid (bool: worth showing), rows (cells, cut to the preview size),
            columns, and hidden (rows and columns not shown, for "and 3 more").
        """
        table = parse_table(text)
        columns = min(table.columns, PREVIEW_COLUMNS)
        rows = [list(row[:columns]) for row in table.rows[:PREVIEW_ROWS]]
        return {
            "grid": table.is_grid,
            "rows": rows,
            "columns": columns,
            "hiddenRows": max(0, len(table.rows) - PREVIEW_ROWS),
            "hiddenColumns": max(0, table.columns - PREVIEW_COLUMNS),
        }

    @Slot(QObject, QColor)
    def dimComments(self, document: QObject, colour: QColor) -> None:  # noqa: N802 - Qt naming, used from QML
        """Dim `#` comments in a Command editor (pass the TextArea's `textDocument`)."""
        if isinstance(document, QQuickTextDocument):
            CommentDimmer(document.textDocument(), colour)
