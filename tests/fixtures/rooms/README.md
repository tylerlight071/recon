# Fixture rooms

Three sample rooms written from scratch for testing. **No TryHackMe text**: the notes are invented in a rough note-taking style. Never add real notes or copied room content here.

Each file mirrors the Phase 1 `app.db` tables (`rooms` → `tasks` → `blocks`); `tests/fixture_rooms.py` loads and validates them. IDs are unique across all three files, so they can share one database. `_fixture` is test-only metadata that the app never reads.

| Room | Tasks | Deliberate traps | Should be caught by |
| --- | --- | --- | --- |
| `number_systems.json` | 5 (one skipped, empty) | `1101` binary written as 11 (it's 13); `0x2F` written as 46 (it's 47) | `factcheck/conversions.py` |
| `intro_to_networking.json` | 4 | "SSH runs on port 23" (it's 22; 23 is Telnet) | `factcheck/ports.py` |
| `linux_basics.json` | 4 | `cat -l` for line numbers (no such flag; it's `-n`); fake flag `THM{this_is_a_test}`; a real MD5 example hash that looks like a flag | `factcheck/commands.py`; `flags_filter.py` (strip the flag; the hash is stripped too but restorable with "Not a flag, keep it") |

Everything else is meant to be correct, so it also measures false flags (Phase 3 allows at most one per room). Block types cover Key idea, Command, Table (pipe-, comma- and tab-separated), Question, Confused by and Room question. Screenshot and Voice blocks arrive with Phase 5.

`_fixture.concepts` and `_fixture.tools` are hand lists for the Phase 2 bake-off's "concepts missed" score. `tests/test_fixture_rooms.py` checks that every trap is really wrong, computing each conversion and running `cat -l` rather than trusting this file.
