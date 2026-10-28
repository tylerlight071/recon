# ADR 0011: The finish flow and the done screen

- **Status:** Accepted
- **Date:** 2026-10-28
- **Context task:** 2.7 (issue #125)

## Context

Task 2.7 replaces Phase 1's temporary Finish with the spec's flow: Finish, the quiz, processing, review, Apply, flashcards, then a done screen with "Open in Obsidian". The quiz (task 4.5) and flashcards (Phase 4) don't exist yet. The build plan's sketch of the link used `obsidian://open?vault=…&file=…`.

## Decision

1. **The flow:**
   - Finish queues the room. Processing runs in the background.
   - The panel's one accent button is "Done" until the room is ready, then "Review notes". A hint says the panel can be closed, because a notification follows.
   - The review leads to Apply, which leads to the done screen in the main window.
2. **Placeholders with no UI.** The quiz will come in `FinishBridge.open`, before the room is queued, and flashcards will come between Apply and the done screen. Both are marked in the code. An empty "coming soon" step would only add a click (ADHD rule 2).
3. **The done screen:**
   - a completion tick;
   - "<room> is in your vault." and how many notes were written;
   - the room's place in its path ("3 rooms done in Pre Security."), counting only what's done, never against a target;
   - "Open in Obsidian" as the one accent button.

   A room already in the vault opens the same screen from Home, without the count.
4. **`obsidian://open?path=<absolute path>`, not `vault=…&file=…`.** Obsidian finds the vault containing the path, so Recon never has to guess the vault's name, which could collide with another vault's. Every reserved character is percent-encoded, slashes included, as Obsidian's documentation requires. `services/open_url.open_in_obsidian` opens only existing `.md` files.
5. **When Obsidian doesn't know the vault.** Until the user confirms opening the vault once, the done screen shows that one-time step (Copy path, "I've done that") instead of a link that would fail. After pressing "Open in Obsidian", a quiet "Didn't open?" brings the step back (task 2.1's rule: show the step again, not an error). If the desktop can't hand the link to Obsidian at all, the screen says so calmly and notes that the note is in the vault either way.
6. **"Export as Markdown" stays,** as a quiet button on the Finish screen. It's still useful for a copy outside the vault, but it's no longer the point of finishing.

## Consequences

- ADR 0010's interim "Apply returns to Home with a toast" is replaced by the done screen.
- Library (task 2.8) adds "Open in Obsidian" for every room, concept and tool, through the same function.
