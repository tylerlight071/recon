"""BlockListModel and the block-type catalogue."""

from datetime import UTC, datetime

import pytest
from PySide6.QtCore import QModelIndex, Qt

from recon.bridge.blocks_model import BLOCK_KINDS, BlockListModel, kind_named
from recon.db.models import Block, BlockContent, BlockType
from tests.ui.qml_harness import SignalCounter, app

WHEN = datetime(2026, 10, 25, tzinfo=UTC)


def _block(block_id: int, block_type: BlockType = "key_idea", text: str = "") -> Block:
    return Block(
        id=block_id,
        task_id=1,
        type=block_type,
        position=block_id,
        content=BlockContent(text=text),
        phase="fill",
        created_at=WHEN,
        updated_at=WHEN,
    )


@pytest.fixture
def model() -> BlockListModel:
    app()
    model = BlockListModel()
    model.reset([_block(1, text="A records"), _block(2, "command", "dig")])
    return model


def test_roles_as_qml_sees_them(model: BlockListModel) -> None:
    names = {bytes(name.data()).decode() for name in model.roleNames().values()}

    assert names == {"blockId", "blockType", "text", "typeLabel", "hint"}


def test_data_for_each_role(model: BlockListModel) -> None:
    index = model.index(1)

    assert model.data(index, BlockListModel.IdRole) == 2
    assert model.data(index, BlockListModel.TypeRole) == "command"
    assert model.data(index, BlockListModel.TextRole) == "dig"
    assert model.data(index, BlockListModel.LabelRole) == "Command"
    assert model.data(index, BlockListModel.HintRole).startswith("Paste or type the command")
    assert model.data(index, Qt.ItemDataRole.DisplayRole) is None


def test_invalid_indexes_and_children(model: BlockListModel) -> None:
    assert model.data(QModelIndex(), BlockListModel.IdRole) is None
    assert model.data(model.index(5), BlockListModel.IdRole) is None
    assert model.rowCount() == 2
    assert model.rowCount(model.index(0)) == 0


def test_set_content_quietly_or_with_notice(model: BlockListModel) -> None:
    changed = SignalCounter(model, "dataChanged(QModelIndex,QModelIndex,QList<int>)")

    assert model.set_content(1, BlockContent(text="typing"), notify=False)
    assert changed.count == 0
    assert model.set_content(1, BlockContent(text="restored"), notify=True)
    assert changed.count == 1
    assert model.content(1) == BlockContent(text="restored")
    assert model.content(99) is None


def test_append_and_first_id(model: BlockListModel) -> None:
    model.append(_block(3, "question"))

    assert model.rowCount() == 3
    assert model.first_id() == 1
    model.reset([])
    assert model.first_id() is None


def test_catalogue_matches_the_spec() -> None:
    assert len(BLOCK_KINDS) == 8
    assert kind_named("key_idea") is BLOCK_KINDS[0]
    assert kind_named("Key idea") is None
    assert BLOCK_KINDS[0].hint == (
        "What's the one thing this task is teaching? Your words, one line is fine."
    )
