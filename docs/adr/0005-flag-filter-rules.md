# ADR 0005: Flag filter rules

- **Status:** Accepted
- **Date:** 2026-10-25
- **Context task:** 1.6 (issue #42)

## Context

Hard rule 2 says anything matching a flag pattern (`THM{…}`, `flag{…}`, `HTB{…}`, or a lone hex string of 32 or more characters) is stripped before it reaches storage, and that a "Not a flag, keep it" button restores "that one string" for hashing rooms. Building it raised three questions the spec doesn't settle.

## Decisions

1. **Only hex lookalikes can be kept.** The button appears only when the single thing skipped is a lone hex string, such as an example MD5. Braced flags are never keepable; `keep_lookalike` refuses them at the repository too. A braced flag is an answer, never study material, so a keep option there would just be a way round the rule.
2. **Unfinished flags are stripped when saving.** Typed one key at a time, `THM{this_is_a_te` isn't yet flag-shaped, so autosave would store almost the whole answer before the `}` arrived. The database layer therefore also removes a braced prefix with no closing brace before the end of its line. Editors don't, so Tyler sees what he types until the flag is complete; then the whole flag disappears with the notice. *Amended after the Phase 1 audit (F-03):* the first version removed everything from an unclosed brace to the end of the line. In CTF notes that isn't rare: `grep -ri "flag{" /home` was stored as `grep -ri "`, and prose about flag formats could vanish entirely, silently. Now only something that looks like a flag mid-typing counts: the prefix, then no whitespace, quotes or pipes, up to the end of the line. Commands and prose that mention a prefix keep every word. A flag body with a space in it is no longer held back while typing; real TryHackMe flags don't contain spaces, and the complete flag is still stripped with the notice once its `}` arrives.
3. **A hash typed key by key is held back while typing** (added after the audit, F-07). Each timed autosave used to store the hash so far, 31 of its 32 characters, before the last key stripped it. Timed autosaves and undo snapshots now also hold back a 20–31 character hex run that ends a line. Final saves (task switch, quit, close) store the text as it is, so a real ID that ends a line (a 24-character object ID, say) isn't lost once Tyler moves on.
4. **Filtering is enforced in the repository.** Every text field (block text, answers, task titles, room name, path and module) is cleaned in `recon/db/repositories.py`, the last stop before SQLite. No caller can store a flag by forgetting to filter. `FlagGuard` cleans editor text too, but only so the flag disappears from the screen and the notice can appear. Since the audit (F-14), task titles and Start's fields go through `FlagGuard.cleanField` as they're typed, so a flag disappears there with the notice too; these are names, so nothing in them can be kept.

## Details

- **Matching:** braced flags match in any letter case, with 1 to 200 characters inside on one line. Lone hex means no letter or digit touching either end (`0x…` is a number, not a lone hex string).
- **Repeat pass:** removing a match can join the neighbouring text into a new match, so stripping repeats until stable.
- **No overlaps:** braced flags are blanked out (same length) before searching for the rest, so findings never overlap.
- **Kept strings:** kept hex strings live in the block's own content (`kept`), so later saves of that block leave them alone.

## Known limits (left open, audit F-15)

These survive the filter: a brace inside the body (`THM{a{b}c}`), a body over 200 characters, zero-width or full-width lookalikes (`TH\u200bM{…}`, `THM｛…｝`), a space before the brace (`THM {…}`), and a flag split across lines. None is likely in real TryHackMe flags. Covering them needs NFKC-normalised detection with positions mapped back, so it waits until one turns up (issue #95).

## Verification

- **Acceptance:** the fixture flag typed into a block, key by key, through autosave never appears in the raw bytes of `app.db` or its WAL; not even its first three characters are ever stored.
- **Properties:** the output never contains a flag; stripping twice changes nothing; only characters are removed; kept hex survives.
- **Mutation testing:** 111 of 111 mutants killed at first; after the audit changes, 136 of 136 caught. The first run found real gaps (multi-finding cuts and positions after a mid-text flag), and they were fixed.
- **After the audit:** the three F-03 examples are regression tests that must keep every word, and a hash typed key by key through the real autosave queue never reaches the raw bytes of `app.db` or its WAL (F-07).
