# ADR 0012: Restoring from History

- **Status:** Accepted
- **Date:** 2026-10-28
- **Context task:** 2.8 (issue #126)

## Context

SPEC.md: "before Apply overwrites any file, the previous version is copied to the app's backup folder; the last 20 runs are kept, and Library > History can restore any of them with one click." Restoring overwrites vault files too, and some of those may have been edited by the user since.

## Decision

1. **Restore puts back what a run replaced, nothing more.** It copies `backups/<run>/` over the vault.
   - Notes the run created aren't deleted: removing files is the user's call, and the Library says so.
   - Raw notes are never touched (hard rule 4), and symlinks in a backup are ignored.
2. **One click, because it can be undone.** Before replacing each file, restore copies the current version to `backups/<new run>/` (hard rule 6). The restore is recorded as an applied run of its own, with `restored_from` set (migration 0005), so:
   - History lists it as "Restored N notes";
   - restoring it puts back exactly what the restore replaced;
   - the toast's Undo does that.

   A confirmation step would add friction without adding safety.
3. **No conflict check.** Apply stops if a note changed since staging, because it would otherwise overwrite unseen edits. A restore is a deliberate request to go back, and every replaced version is kept, so edits made since are always recoverable.
4. **Only runs whose backup is still kept can be restored** (the newest 20). The button shows only for runs that replaced something. An expired backup gives a plain message, and nothing changes.
5. **The Library's first pass:**
   - rooms in the vault, newest first, with path, module and date, and "Open in Obsidian" (once Obsidian knows the vault; until then, a line says how);
   - History, collapsed by default, because it's rarely needed (ADHD rule 2).

   The Library has no accent button, because nothing in it is the next step. Concepts, tools and open flags join it in Phase 3.

## Consequences

- `engine/stage.restore` is mutation-tested along with the rest of `stage.py`: every mutant is killed.
- A restore uses one of the 20 backup slots, so restoring repeatedly can push the oldest backups out sooner.
