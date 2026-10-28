"""Step 1 (parse): the capture is the room as written, flags removed, empties left out."""

from datetime import UTC, date, datetime

from recon.db.models import Block, BlockContent, Room, Task
from recon.engine.capture import capture_room
from tests.engine.pipeline import capture_of

NOW = datetime(2026, 10, 28, tzinfo=UTC)


def _block(block_id: int, kind: str, text: str, **content: object) -> Block:
    return Block.model_validate(
        {
            "id": block_id,
            "task_id": 1,
            "type": kind,
            "position": block_id,
            "content": BlockContent.model_validate({"text": text, **content}),
            "pass": "fill",
            "created_at": NOW,
            "updated_at": NOW,
        }
    )


def _room(name: str = "Hashing Basics") -> Room:
    return Room(
        id=7,
        platform="TryHackMe",
        path="Cyber Security 101",
        module="Cryptography",
        name=name,
        task_count=1,
        mode="new",
        status="done",
        created_at=NOW,
        updated_at=NOW,
        time_spent_s=600,
        last_task_index=1,
    )


def test_a_fixture_room_keeps_every_written_block_in_order() -> None:
    capture = capture_of("number_systems")

    assert capture.name == "Number Systems"
    assert [t.index for t in capture.tasks] == [1, 2, 3, 4, 5]
    assert capture.tasks[4].status == "skipped"
    assert capture.tasks[4].blocks == ()
    assert [b.id for b in capture.tasks[1].blocks] == [1003, 1004, 1005]
    assert capture.block(1004) is not None
    assert capture.block(1004).text == "1101 in binary is 11 in decimal."  # type: ignore[union-attr]  # just asserted
    assert capture.block(99) is None


def test_flags_are_gone_and_kept_hashes_stay() -> None:
    md5 = "5d41402abc4b2a76b9719d911017c592"
    task = Task(id=1, room_id=7, task_index=1, title="Got THM{abc}", status="done")
    blocks = [
        _block(1, "key_idea", "Answer: THM{secret_flag}"),
        _block(2, "key_idea", f"hello hashes to {md5}", kept=(md5,)),
        _block(3, "key_idea", f"another {md5[::-1]}"),
        _block(4, "room_question", "What is the flag?", answer="flag{nope}"),
    ]

    capture = capture_room(_room("Room THM{x}"), [(task, blocks)], date(2026, 10, 28))

    texts = [b.text for b in capture.blocks()]
    assert texts == ["Answer: ", f"hello hashes to {md5}", "another ", "What is the flag?"]
    assert capture.blocks()[3].answer == ""
    assert capture.tasks[0].title == "Got "
    assert capture.name == "Room "
    assert "THM{" not in capture.model_dump_json()


def test_empty_blocks_and_screenshots_are_left_out() -> None:
    task = Task(id=1, room_id=7, task_index=1, title="", status="done")
    blocks = [
        _block(1, "key_idea", "  \n"),
        _block(2, "screenshot", "why it matters"),
        _block(3, "room_question", "", answer="only an answer"),
        _block(4, "command", "ls -la"),
        _block(5, "key_idea", "THM{only_a_flag}"),
    ]

    capture = capture_room(_room(), [(task, blocks)], date(2026, 10, 28))

    assert [(b.id, b.type) for b in capture.blocks()] == [(3, "room_question"), (4, "command")]
    assert capture.blocks()[0].answer == "only an answer"


def test_answers_belong_to_room_questions_only() -> None:
    task = Task(id=1, room_id=7, task_index=1, title="", status="done")

    capture = capture_room(
        _room(), [(task, [_block(1, "question", "Why?", answer="stray")])], date(2026, 10, 28)
    )

    assert capture.blocks()[0].answer == ""
