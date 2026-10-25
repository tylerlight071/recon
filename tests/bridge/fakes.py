"""Small fakes shared by bridge and window tests."""

from recon.db.models import BlockContent
from recon.db.repositories import BlockRepository


class FakeAutosave:
    """Holds edits like AutosaveQueue; `flush()` writes them through the repository."""

    def __init__(self, blocks: BlockRepository) -> None:
        self.blocks = blocks
        self.pending: dict[int, BlockContent] = {}
        self.flushes = 0

    def put(self, block_id: int, content: BlockContent) -> None:
        self.pending[block_id] = content

    def flush(self, timeout_s: float = 5.0) -> bool:  # noqa: ARG002 - same signature as the queue
        self.flushes += 1
        for block_id, content in self.pending.items():
            self.blocks.update_content(block_id, content)
        self.pending.clear()
        return True
