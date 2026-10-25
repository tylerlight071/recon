# ADR 0005: Flag filter rules

- **Status:** Accepted
- **Date:** 2026-10-25
- **Context task:** 1.6 (issue #42)

## Context

Hard rule 2 says anything matching a flag pattern (`THM{…}`, `flag{…}`, `HTB{…}`, or a lone hex string of 32 or more characters) is stripped before it reaches storage, and that a "Not a flag, keep it" button restores "that one string" for hashing rooms. Building it raised three questions the spec doesn't settle.

## Decisions

1. **Only hex lookalikes can be kept.** The button appears only when the single thing skipped is a lone hex string, such as an example MD5. Braced flags are never keepable; `keep_lookalike` refuses them at the repository too. A braced flag is an answer, never study material, so a keep option there would just be a way round the rule.
2. **Unfinished flags are stripped when saving.** Typed one key at a time, `THM{this_is_a_te` isn't yet flag-shaped, so autosave would store almost the whole answer before the `}` arrived. The database layer therefore also removes a braced prefix with no closing brace before the end of its line. Editors don't, so Tyler sees what he types until the flag is complete; then the whole flag disappears with the notice. The cost: an unclosed brace mid-sentence ("use THM{ then the answer") loses the rest of that line from storage. It's rare, and the safe side to err on.
3. **Filtering is enforced in the repository.** Every text field (block text, answers, task titles, room name, path and module) is cleaned in `recon/db/repositories.py`, the last stop before SQLite. No caller can store a flag by forgetting to filter. `FlagGuard` cleans editor text too, but only so the flag disappears from the screen and the notice can appear.

## Details

- **Matching:** braced flags match in any letter case, with 1 to 200 characters inside on one line. Lone hex means no letter or digit touching either end (`0x…` is a number, not a lone hex string).
- **Repeat pass:** removing a match can join the neighbouring text into a new match, so stripping repeats until stable.
- **No overlaps:** braced flags are blanked out (same length) before searching for the rest, so findings never overlap.
- **Kept strings:** kept hex strings live in the block's own content (`kept`), so later saves of that block leave them alone.

## Verification

- **Acceptance:** the fixture flag typed into a block, key by key, through autosave never appears in the raw bytes of `app.db` or its WAL; not even its first three characters are ever stored.
- **Properties:** the output never contains a flag; stripping twice changes nothing; only characters are removed; kept hex survives.
- **Mutation testing:** 111 of 111 mutants killed. The first run found real gaps (multi-finding cuts and positions after a mid-text flag), and they were fixed.
