"""Phase 1 acceptance (hard rule 2): a fixture flag typed into a block never reaches app.db.

Checked on the raw bytes of the database and its WAL, not just through the
repositories, so a stray copy anywhere in the file would fail the test.
"""

import time
from pathlib import Path

import pytest

from recon.db.autosave import AutosaveQueue
from recon.db.connection import Database
from recon.db.models import BlockContent, NewRoom
from recon.db.repositories import BlockRepository, RoomRepository, TaskRepository
from tests.fixture_rooms import all_rooms

FLAG = all_rooms()["linux_basics"].fixture.flags[0]  # THM{this_is_a_test}
LOOKALIKE = all_rooms()["linux_basics"].fixture.flag_lookalikes[0]


def _raw_bytes(data_dir: Path) -> bytes:
    return b"".join(p.read_bytes() for p in data_dir.glob("app.db*"))


@pytest.fixture
def repos(db: Database) -> tuple[RoomRepository, TaskRepository, BlockRepository]:
    return RoomRepository(db), TaskRepository(db), BlockRepository(db)


def test_flag_typed_into_a_block_never_reaches_the_file(
    db: Database, data_dir: Path, repos: tuple[RoomRepository, TaskRepository, BlockRepository]
) -> None:
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="Linux Basics", task_count=4)).id)[0]
    block = blocks.ensure_starter_block(task.id)
    queue = AutosaveQueue(blocks.update_content, delay_s=0.01)

    typed = ""
    for ch in f"Got the answer for this task: {FLAG}":
        typed += ch
        queue.put(block.id, BlockContent(text=typed))
    queue.close()

    stored = blocks.get(block.id)
    assert stored is not None
    assert stored.content.text == "Got the answer for this task: "
    assert FLAG.encode() not in _raw_bytes(data_dir)
    with db.read() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert FLAG.encode() not in _raw_bytes(data_dir)


@pytest.mark.parametrize("field", ["name", "path", "module"])
def test_flags_in_room_details_are_stripped(
    data_dir: Path, repos: tuple[RoomRepository, TaskRepository, BlockRepository], field: str
) -> None:
    rooms, _tasks, _blocks = repos
    details = {"name": "Linux Basics", "path": "Pre Security", "module": "Linux"}
    details[field] = f"{details[field]} {FLAG}"

    room = rooms.create(NewRoom(task_count=1, **details))

    assert FLAG not in room.model_dump_json()
    assert FLAG.encode() not in _raw_bytes(data_dir)


def test_room_name_that_is_only_a_flag_gets_a_placeholder(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    rooms, _tasks, _blocks = repos

    assert rooms.create(NewRoom(name=FLAG, task_count=1)).name == "Untitled room"


def test_flags_in_task_titles_and_answers_are_stripped(
    data_dir: Path, repos: tuple[RoomRepository, TaskRepository, BlockRepository]
) -> None:
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=1)).id)[0]

    tasks.set_title(task.id, f"Find {FLAG}")
    blocks.add(task.id, "room_question", BlockContent(text="What is the flag?", answer=FLAG))

    assert tasks.for_room(task.room_id)[0].title == "Find "
    assert blocks.for_task(task.id)[0].content.answer == ""
    assert FLAG.encode() not in _raw_bytes(data_dir)


def test_an_example_hash_is_kept_only_when_tyler_says_so(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=1)).id)[0]
    block = blocks.add(task.id, "key_idea", BlockContent(text=f"md5 of hello is {LOOKALIKE}"))
    assert LOOKALIKE not in (blocks.get(block.id) or block).content.text

    assert blocks.keep_lookalike(block.id, LOOKALIKE)
    kept = blocks.get(block.id)
    assert kept is not None
    blocks.update_content(
        block.id, kept.content.model_copy(update={"text": f"md5 of hello is {LOOKALIKE}"})
    )

    stored = blocks.get(block.id)
    assert stored is not None
    assert stored.content.text == f"md5 of hello is {LOOKALIKE}"
    assert stored.content.kept == (LOOKALIKE,)


@pytest.mark.parametrize("not_keepable", [FLAG, "flag{x}", "a" * 31, "short", ""])
def test_only_hex_lookalikes_can_be_kept(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository], not_keepable: str
) -> None:
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=1)).id)[0]
    block = blocks.add(task.id, "key_idea")

    assert blocks.keep_lookalike(block.id, not_keepable) is False
    assert blocks.keep_lookalike(9999, LOOKALIKE) is False


def test_keeping_twice_records_once(
    repos: tuple[RoomRepository, TaskRepository, BlockRepository],
) -> None:
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=1)).id)[0]
    block = blocks.add(task.id, "key_idea")

    assert blocks.keep_lookalike(block.id, LOOKALIKE)
    assert blocks.keep_lookalike(block.id, LOOKALIKE)

    stored = blocks.get(block.id)
    assert stored is not None
    assert stored.content.kept == (LOOKALIKE,)


def test_a_flag_typed_key_by_key_never_reaches_the_database_even_half_typed(
    db: Database, data_dir: Path, repos: tuple[RoomRepository, TaskRepository, BlockRepository]
) -> None:
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="R", task_count=1)).id)[0]
    block = blocks.ensure_starter_block(task.id)
    answer = FLAG[len("THM{") : -1]  # this_is_a_test

    typed = "Answer: "
    for ch in FLAG + " noted":
        typed += ch
        blocks.update_content(block.id, BlockContent(text=typed))
        stored = blocks.get(block.id)
        assert stored is not None
        # Not even the first characters of the answer are ever stored.
        assert answer[:3] not in stored.content.text, typed

    assert stored.content.text == "Answer:  noted"
    with db.read() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert answer.encode() not in _raw_bytes(data_dir)


def test_a_hash_typed_key_by_key_never_reaches_the_file(
    db: Database, data_dir: Path, repos: tuple[RoomRepository, TaskRepository, BlockRepository]
) -> None:
    # Audit F-07: each timed save used to store the hash typed so far (31 of 32 characters).
    rooms, tasks, blocks = repos
    task = tasks.for_room(rooms.create(NewRoom(name="Hashing", task_count=1)).id)[0]
    block = blocks.ensure_starter_block(task.id)
    queue = AutosaveQueue(blocks.update_content, delay_s=0.005)
    hash_flag = "9e107d9d372bb6826bd81d3542a419d6"

    typed = ""
    for ch in f"The answer was {hash_flag}":
        typed += ch
        queue.put(block.id, BlockContent(answer=typed))
        time.sleep(0.01)  # slow enough for a timed save between keys
    queue.close()

    stored = blocks.get(block.id)
    assert stored is not None
    assert stored.content.answer == "The answer was "
    assert hash_flag[:20].encode() not in _raw_bytes(data_dir)  # app.db and its WAL
    with db.read() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert hash_flag[:20].encode() not in _raw_bytes(data_dir)
