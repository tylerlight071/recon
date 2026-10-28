# ADR 0009: Background processing and desktop notifications

- **Status:** Accepted
- **Date:** 2026-10-28
- **Context task:** 2.5 (issue #123)

## Context

Finishing a room starts processing that can take minutes: one model call is about 20–30 s on `qwen3.5:9b` with thinking off, and longer with it on. The app has to stay usable meanwhile. Only one room may process at a time (hard rule 10). When a room is ready, a desktop notification says so, and clicking it opens that room. ADR 0003 left notifications on QtDBus, "task 2.5 confirms".

## Decision

1. **A daemon worker, not the Qt thread pool.**
   - Processing runs on `workers.DaemonWorker`: one Python daemon thread with a queue.
   - A model call can't be interrupted, and `QThreadPool` waits for its threads when the app quits, so a busy run would hold quitting up for minutes.
   - The pipeline checks a cancel flag between steps instead. At quit it stops at the next check, and the daemon thread never delays exit.
   - Cutting a run off anywhere is safe:
     - the room stays `processing` and is queued again at the next launch;
     - a half-staged run has no database record and expires with old runs;
     - nothing reaches the vault before Apply.
2. **One queue, one room at a time.** `ProcessingBridge` keeps the order, and the single worker thread enforces hard rule 10.
   - At launch, every room left `queued` or `processing` is queued again, oldest first.
   - A step that fails sets the room back to `queued` and shows the problem with Retry. The next launch tries it again too.
   - "Back to the room" discards anything staged and withdraws the room. If the model call is already running, the pipeline sees the room is no longer `processing` and doesn't stage anything.
3. **Three plain steps** (`recon/pipeline.py`):
   - "Reading your notes";
   - "Structuring 4 tasks with qwen3.5:9b";
   - "Preparing 12 notes for review".

   The panel's Finish screen shows them as a line of text and a thin bar filling step by step, never a spinner. Screenshots, linking and fact-checking add steps in later phases.
4. **Notifications use jeepney, not QtDBus.**
   - `Notify` takes an unsigned `replaces_id`. From Python, QtDBus sends an int as a signed `i`, and there's no way to ask it for `u`.
   - jeepney writes the signature explicitly (`susssasa{sv}i`), and it's already the D-Bus library for the shortcut portal (ADR 0003).
   - One private thread owns one session-bus connection, used both to send `Notify` and to listen for `ActionInvoked`, because some servers only send the click back to the connection that created the notification.
   - Notifications are silent (`suppress-sound`) and use the server's usual timeout. With no session bus (CI, a TTY) they're skipped.
5. **Two notifications only:** "<room> is ready to review", and "<room> couldn't be processed" with the plain reason. Without the second, a failure after the panel was closed would go unnoticed. Clicking either opens that room's Finish screen. The review screen (tasks 2.6–2.7) takes over that click.

## Consequences

- CLAUDE.md's stack row for notifications now names jeepney. The network-import test confines jeepney to `services/notifications.py` and `services/portal.py`.
- On the development desktop, Plasma accepted a real `Notify` call and returned an ID. Whether the click reaches Recon needs someone at the screen, so it's in `docs/MANUAL_TESTS.md`.
- Quitting mid-run abandons the model call. The room processes again from the start at the next launch, so the work done before quitting is lost, but no data is.
