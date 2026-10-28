# ADR 0008: Staging and Apply, and how a crash mid-Apply is handled

- **Status:** Accepted
- **Date:** 2026-10-28
- **Context task:** 2.4 (issue #122)

## Context

Hard rules 3, 4, 6, 8 and 9 meet in one place: getting a room's notes into the vault. The build plan's acceptance check asks that killing the process mid-Apply leave the vault "either fully before or fully after the change". A filesystem can replace one file atomically, but not several together.

## Decision

1. **Stage first, with hashes.**
   - Notes are written under `runs/<run id>/staged/`, mirroring the vault's paths.
   - `manifest.json` records, for every note, its action and the target's SHA-256 at staging (or that the target didn't exist). It also records the staged content's SHA-256.
   - Notes that would be unchanged are marked `same` and never written.
2. **Apply checks everything before writing anything.**
   - It verifies the staged files against the manifest (`StagingDamagedError`), then re-hashes every target.
   - A target that was edited, created or deleted since staging raises `ApplyConflict`, with nothing written, no backup taken and no journal started.
3. **Back up, then journal, then write.**
   - Every file Apply will overwrite is copied to `backups/<run id>/` first.
   - Then `apply.json` records "applying", each note is written atomically, and the journal is marked "applied".
   - New notes are created with a hard link, which fails rather than overwrite a file that appeared in the meantime.
4. **A crash mid-Apply is finished, not undone.**
   - At launch, `recover` completes any run whose journal says "applying". The user pressed Apply, so completing it is what was asked for.
   - It writes only files whose content still matches the hash recorded at staging. Files already written are left as they are, and a file changed by hand since is left alone.
   - The vault therefore ends fully after the change. A crash before the journal exists leaves it fully before.
   - The alternative, rolling back from backups, would also overwrite any edit made after the crash, and would undo work the user confirmed.
5. **Updating an existing note only touches marker insides.**
   - `merge` replaces the inside of each `%% recon:start <name> %%` section present in both versions, and adds new sections at the end under their heading.
   - Frontmatter and everything outside the markers stay byte for byte. Phase 3 will update properties such as `seen_in` within this rule.
   - A note with damaged markers (unclosed, nested or repeated), or one that isn't valid UTF-8, is skipped and listed for the review screen rather than guessed at.
6. **Raw notes are never updated.**
   - Identical raw notes are left as they are.
   - Otherwise a re-run writes `… (raw notes 2).md` (up to 99), and the room note's links point to it.
7. **Runs waiting for review are kept** past the 30-day run expiry, so a review can still be applied. Backups keep the newest 20 runs, and database snapshots in `backups/db/` are never touched by that pruning.

## Consequences

- `engine/stage.py` is mutation-tested, and all 448 of its mutants are killed. Two simplifications came out of that work:
  - `inside()` relies on resolving the path, which catches absolute paths, `..` and symlinks in one check.
  - Notes that aren't UTF-8 are now skipped. Decoding them with replacement characters would have changed the user's text on write.
- `tests/engine/test_stage_crash.py` kills a child process with SIGKILL after its first, second or third vault write, then runs recovery. Every note matches its staged hash. Killed before the first write, the vault is unchanged.
- Re-runs don't yet keep sections the user edited inside the markers. SPEC.md's "Suggested additions" behaviour needs the section hashes that Phase 3's index stores. Until then, the backup holds the user's version.
