"""The current task's blocks as a Qt list model, plus the block-type catalogue.

The catalogue is SPEC.md's block table: label, shortcut and the hint shown in
an empty block. Voice and Screenshot arrive in Phase 5, so they're listed but
not yet available ("Coming soon"), and stay in the same place in the add bar.
"""

from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from recon.db.models import Block, BlockContent, BlockType

type Index = QModelIndex | QPersistentModelIndex


@dataclass(frozen=True, slots=True)
class BlockKind:
    """One block type as the add bar and the block show it."""

    type: BlockType
    label: str
    shortcut: str
    hint: str
    icon: str
    available: bool = True


BLOCK_KINDS: Final = (
    BlockKind(
        "key_idea",
        "Key idea",
        "Ctrl+1",
        "What's the one thing this task is teaching? Your words, one line is fine.",
        "bulb",
    ),
    BlockKind(
        "command",
        "Command",
        "Ctrl+2",
        "Paste or type the command. Add what it does after a #.",
        "terminal",
    ),
    BlockKind(
        "table", "Table", "Ctrl+3", "Paste a table, or type rows like: 80, HTTP, web", "table"
    ),
    BlockKind(
        "screenshot",
        "Screenshot",
        "Ctrl+4",
        "Paste an image. Add a line on why it matters.",
        "image",
        available=False,
    ),
    BlockKind("question", "Question", "Ctrl+5", "Something you want answered later.", "question"),
    BlockKind(
        "confused",
        "Confused by",
        "Ctrl+6",
        "What didn't click? Even 'no idea what X is'.",
        "squiggle",
    ),
    BlockKind(
        "room_question",
        "Room question",
        "Ctrl+7",
        "Copy a room question worth remembering, then your answer. Skip flags.",
        "bubble",
    ),
    BlockKind(
        "voice",
        "Voice",
        "Hold F9",
        "Talk it through: what was this task about?",
        "mic",
        available=False,
    ),
)
KINDS: Final = {kind.type: kind for kind in BLOCK_KINDS}


def kind_named(name: str) -> BlockKind | None:
    """The block kind called `name` (as QML passes it), or None."""
    return next((kind for kind in BLOCK_KINDS if kind.type == name), None)


def add_bar_entries() -> list[dict[str, object]]:
    """The add bar's buttons, in their fixed order, for QML."""
    return [
        {
            "type": kind.type,
            "label": kind.label,
            "shortcut": kind.shortcut,
            "icon": kind.icon,
            "available": kind.available,
        }
        for kind in BLOCK_KINDS
    ]


class BlockListModel(QAbstractListModel):
    """The blocks of the task on screen, in order."""

    IdRole: Final = Qt.ItemDataRole.UserRole + 1
    TypeRole: Final = Qt.ItemDataRole.UserRole + 2
    TextRole: Final = Qt.ItemDataRole.UserRole + 3
    LabelRole: Final = Qt.ItemDataRole.UserRole + 4
    HintRole: Final = Qt.ItemDataRole.UserRole + 5

    def __init__(self, parent: QObject | None = None) -> None:
        """Start empty."""
        super().__init__(parent)
        self._blocks: list[Block] = []

    def rowCount(self, parent: Index = QModelIndex()) -> int:  # noqa: B008, N802 - Qt API
        """Number of blocks (a flat list: no children)."""
        return 0 if parent.isValid() else len(self._blocks)

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802 - Qt API
        """Role names as QML sees them."""
        return {
            self.IdRole: QByteArray(b"blockId"),
            self.TypeRole: QByteArray(b"blockType"),
            self.TextRole: QByteArray(b"text"),
            self.LabelRole: QByteArray(b"typeLabel"),
            self.HintRole: QByteArray(b"hint"),
        }

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        """One value of one block, or None."""
        if not index.isValid() or not 0 <= index.row() < len(self._blocks):
            return None
        block = self._blocks[index.row()]
        kind = KINDS[block.type]
        values: dict[int, object] = {
            self.IdRole: block.id,
            self.TypeRole: block.type,
            self.TextRole: block.content.text,
            self.LabelRole: kind.label,
            self.HintRole: kind.hint,
        }
        return values.get(role)

    def reset(self, blocks: list[Block]) -> None:
        """Show another task's blocks."""
        self.beginResetModel()
        self._blocks = list(blocks)
        self.endResetModel()

    def append(self, block: Block) -> None:
        """Add a block at the end."""
        row = len(self._blocks)
        self.beginInsertRows(QModelIndex(), row, row)
        self._blocks.append(block)
        self.endInsertRows()

    def content(self, block_id: int) -> BlockContent | None:
        """A block's current content (what's on screen), or None if it isn't in this task."""
        row = self._row(block_id)
        return None if row is None else self._blocks[row].content

    def set_content(self, block_id: int, content: BlockContent, *, notify: bool) -> bool:
        """Replace a block's content.

        Args:
            block_id: The block.
            content: Its new content.
            notify: Tell QML (False while Tyler types, so his cursor stays put).

        Returns:
            Whether the block is in this task.
        """
        row = self._row(block_id)
        if row is None:
            return False
        self._blocks[row] = self._blocks[row].model_copy(update={"content": content})
        if notify:
            index = self.index(row)
            self.dataChanged.emit(index, index, [self.TextRole])
        return True

    def first_id(self) -> int | None:
        """The first block's ID (the one to focus), or None."""
        return self._blocks[0].id if self._blocks else None

    def _row(self, block_id: int) -> int | None:
        return next((i for i, b in enumerate(self._blocks) if b.id == block_id), None)
