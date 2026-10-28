# ADR 0010: The review screen

- **Status:** Accepted (point 5's interim Apply toast replaced by the done screen, ADR 0011)
- **Date:** 2026-10-28
- **Context task:** 2.6 (issue #124)

## Context

SPEC.md's review screen opens full-window. It lists the room note "rendered as Obsidian will show it", new notes, additions (only the added parts), links and flags, each collapsible with a count. It has a sticky footer with Apply and Discard, and Discard asks once. Recon renders with Qt Quick, not Obsidian. Linking and fact-checking (and so links and flags) arrive in Phase 3.

## Decision

1. **Preview with Qt's own Markdown renderer.** `Text` with `textFormat: Text.MarkdownText` renders CommonMark with GitHub tables. `engine/review.for_display` first turns Obsidian's own syntax into what Qt understands:
   - frontmatter and `%%` markers are dropped;
   - wikilinks show their text;
   - callouts become quotes with a bold title;
   - Mermaid shows as its source;
   - headings shift two levels smaller, because Qt's are large.

   No web view or extra dependency is needed.
2. **The preview can't load or run anything.** Outside code, `![` and `<` are escaped, so a note can't pull in an image or interpret HTML. QML's network access manager refuses non-local URLs anyway (`services/qml_network.py`). Links aren't connected to anything. Code spans and fenced blocks show exactly as written.
3. **Additions show only what changes:** each Recon section that's new or different, under its heading (`added_parts`). Notes left alone because their markers are damaged get a "Left alone" section, so nothing is skipped silently. Raw notes aren't listed, because they're the user's words as typed.
4. **Empty sections are hidden** (ADHD rule 2). Until Phase 3, that means Links and Flags never show.
5. **Apply, Discard and Re-check.**
   - **Apply** runs on the room worker, after every pending save. If any note changed since the review was prepared, nothing is written, Apply is disabled, and the screen offers Re-check.
   - **Re-check** discards the run and processes the room again against the vault as it is now. Its progress shows in the panel.
   - **Discard** asks once, then reopens the room in the panel exactly as it was.
   - Until task 2.7's done screen, Apply returns to Home with a toast: "Applied: N notes written to your vault."
6. **Ways in:** a Home row that's ready to review, the panel's "Review notes" button, or the notification. A notification about a problem opens the room's Finish screen instead, because there's nothing to review.
7. **The bridge is `ReviewModel` in QML.** Inside `Review.qml`, the name `Review` means the screen itself; Home's bridge is `HomeModel` for the same reason.

## Consequences

- What the user sees in the review is close to Obsidian, but not identical: callouts don't fold, and diagrams show as source. The done screen's "Open in Obsidian" (task 2.7) shows the real thing.
- `for_display` has property tests: outside code, no `<` or `![` survives. Hostile-input tests cover images, HTML and comments.
