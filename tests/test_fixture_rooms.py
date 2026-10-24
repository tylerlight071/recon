"""The fixture rooms are valid, original, and contain exactly the traps they claim."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.fixture_rooms import ROOMS_DIR, Room, all_rooms, load_room

ROOMS = all_rooms()
FLAG_PATTERN = re.compile(r"(THM|flag|HTB)\{[^}]*\}|\b[0-9a-fA-F]{32,}\b")
"""Hard rule 2's flag shapes, as CLAUDE.md lists them (the real filter is task 1.6)."""


def _texts(room: Room) -> list[str]:
    return [
        part
        for task in room.tasks
        for block in task.blocks
        for part in (block.content.text, block.content.answer or "")
        if part
    ]


def test_three_rooms_load() -> None:
    assert set(ROOMS) == {"number_systems", "intro_to_networking", "linux_basics"}
    assert {room.name for room in ROOMS.values()} == {
        "Number Systems",
        "Intro to Networking",
        "Linux Basics",
    }


@pytest.mark.parametrize("stem", sorted(ROOMS))
def test_room_is_internally_consistent(stem: str) -> None:
    room = ROOMS[stem]

    assert room.task_count == len(room.tasks)
    assert [task.task_index for task in room.tasks] == list(range(1, room.task_count + 1))
    for task in room.tasks:
        assert [block.position for block in task.blocks] == list(range(len(task.blocks)))
        assert task.blocks or task.status == "skipped"
        for block in task.blocks:
            assert (block.content.answer is not None) == (block.type == "room_question")


def test_ids_are_unique_across_all_rooms() -> None:
    rooms = list(ROOMS.values())
    task_ids = [task.id for room in rooms for task in room.tasks]
    block_ids = [block.id for room in rooms for task in room.tasks for block in task.blocks]

    assert len({room.id for room in rooms}) == len(rooms)
    assert len(set(task_ids)) == len(task_ids)
    assert len(set(block_ids)) == len(block_ids)


@pytest.mark.parametrize("stem", sorted(ROOMS))
def test_every_mistake_points_at_its_block(stem: str) -> None:
    room = ROOMS[stem]

    for mistake in room.fixture.mistakes:
        assert room.block(mistake.block_id).content.text == mistake.claim


def test_unknown_block_id_raises() -> None:
    with pytest.raises(KeyError):
        ROOMS["number_systems"].block(999_999)


def test_number_systems_has_two_wrong_conversions() -> None:
    room = ROOMS["number_systems"]
    claims = {m.claim: m for m in room.fixture.mistakes}

    true_binary, true_hex = int("1101", 2), int("2F", 16)
    assert (true_binary, true_hex) == (13, 47)
    assert true_binary != 11
    assert true_hex != 46
    assert set(claims) == {"1101 in binary is 11 in decimal.", "0x2F is 46 in decimal."}
    assert all(m.check == "conversions" for m in claims.values())


def test_number_systems_correct_statements_really_are_correct() -> None:
    texts = _texts(ROOMS["number_systems"])

    assert "0xFF is 255, the biggest number one byte can hold." in texts
    assert int("FF", 16) == 255
    assert int("1010", 2) == 10
    assert "10" in texts


def test_number_systems_tables_are_right() -> None:
    texts = _texts(ROOMS["number_systems"])
    binary = next(t for t in texts if t.startswith("Binary | Decimal"))
    hex_table = next(t for t in texts if t.startswith("Hex,Decimal,Binary"))

    for line in binary.splitlines()[1:]:
        bits, decimal = (cell.strip() for cell in line.split("|"))
        assert int(bits, 2) == int(decimal)
    for line in hex_table.splitlines()[1:]:
        hex_digits, decimal, bits = line.split(",")
        assert int(hex_digits, 16) == int(decimal) == int(bits, 2)


def test_networking_has_exactly_one_wrong_port() -> None:
    room = ROOMS["intro_to_networking"]
    [mistake] = room.fixture.mistakes

    assert mistake.claim == "SSH runs on port 23."
    assert mistake.check == "ports"
    ports_table = next(t for t in _texts(room) if t.startswith("Port\t"))
    assert ports_table.splitlines()[1:] == ["80\tHTTP", "443\tHTTPS", "53\tDNS"]


def test_linux_has_one_nonexistent_flag() -> None:
    room = ROOMS["linux_basics"]
    [mistake] = room.fixture.mistakes

    assert mistake.claim.startswith("cat -l ")
    assert mistake.check == "commands"


def test_cat_really_has_no_l_flag() -> None:
    done = subprocess.run(
        ["/usr/bin/cat", "-l", "/dev/null"], capture_output=True, text=True, check=False
    )

    assert done.returncode != 0
    assert "invalid option" in done.stderr


def test_commands_carry_a_hash_description() -> None:
    commands = [
        block.content.text
        for task in ROOMS["linux_basics"].tasks
        for block in task.blocks
        if block.type == "command"
    ]

    assert commands
    assert all(re.search(r"\s#\s\S", text) for text in commands)


def test_fake_flag_is_in_exactly_one_room() -> None:
    holders = [stem for stem, room in ROOMS.items() if any("THM{" in text for text in _texts(room))]

    assert holders == ["linux_basics"]
    assert ROOMS["linux_basics"].fixture.flags == ["THM{this_is_a_test}"]


@pytest.mark.parametrize("stem", sorted(ROOMS))
def test_flag_shaped_strings_are_all_declared(stem: str) -> None:
    room = ROOMS[stem]
    found = {match.group(0) for text in _texts(room) for match in FLAG_PATTERN.finditer(text)}

    assert found == set(room.fixture.flags) | set(room.fixture.flag_lookalikes)


def test_hash_lookalike_is_a_real_md5() -> None:
    assert ROOMS["linux_basics"].fixture.flag_lookalikes == [
        hashlib.md5(b"hello", usedforsecurity=False).hexdigest()
    ]


@pytest.mark.parametrize("stem", sorted(ROOMS))
def test_fixtures_contain_no_tryhackme_text_markers(stem: str) -> None:
    raw = (ROOMS_DIR / f"{stem}.json").read_text(encoding="utf-8").casefold()

    assert "tryhackme.com" not in raw
    assert "http://" not in raw
    assert "https://" not in raw


def test_load_rejects_unknown_fields(tmp_path: Path) -> None:
    data = json.loads((ROOMS_DIR / "linux_basics.json").read_text(encoding="utf-8"))
    data["surprise"] = True
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="surprise"):
        load_room(bad)
