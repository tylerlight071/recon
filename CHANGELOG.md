# Changelog

All notable changes to Recon are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Recon uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Each approved phase gate is released as `v0.<phase>.0`.

## [Unreleased]

### Added

- Vault bootstrap: Recon creates `~/Cyber Vault` (or the folder in Settings) with SPEC.md's folders, a Bases `Home.md` with three dashboards, and Obsidian's settings (wikilinks, links kept up to date when notes are renamed, attachments in `Attachments/`). It never replaces a file you've changed. Home shows a one-time "Open your vault in Obsidian, once" card with Copy path and "I've done that". ADR 0006.
- Ollama service (`services/ollama.py`): talks only to Ollama on this computer, checks it's running and has Recon's models, and makes structured calls (schema in `format` and in the prompt, temperature 0, one retry with the validation errors) with plain errors for "not running", "too slow", "model missing" and "didn't make sense twice". Raw replies go only to `runs/<run_id>/` (private, deleted after 30 days at start-up). Model names and the Ollama address are settings. Settings has a Models section with Ollama's status, "Check again", and the `ollama pull` command for anything missing.
- Pipeline steps 1, 3 and 6 (parse, extract and render) for text blocks. The room goes to the text model, and code checks the reply. Recon then renders a room note, the user's raw notes (as typed), and a note per concept and tool. Properties follow SPEC.md, generated sections sit between `%% recon:start … %%` markers, and generated content is labelled. Model text is sanitised, so it can't add links, embeds, HTML, markers or structure. Every model call now sets a 16k context, and `model_thinking` (off) is a setting. Nothing is written to the vault yet. ADR 0007.
- Finish flow and done screen.
  - **Finish:** pressing Finish room starts processing; the panel's main button is "Done" until the notes are ready, then "Review notes". Export is a quiet extra.
  - **After Apply:** a done screen with a completion tick, how many notes were written, the room's place in its path, and "Open in Obsidian" (an `obsidian://open?path=…` link).
  - **Vault not yet opened in Obsidian:** the one-time "open your vault" step shows instead, and "Didn't open?" brings it back.
  - **From Home:** rooms already in the vault open this screen.
  - ADR 0011.
- Review screen: everything processing prepared, before anything reaches the vault.
  - **Sections:** the room note shown as it will read, new notes, additions to existing notes (only the parts that change), and notes left alone. Each section is collapsible with a count.
  - **Footer:** Discard and Apply stay in reach however far the page scrolls. Discard asks once, then reopens the room in the panel as it was.
  - **Conflicts:** if a note changed in Obsidian meanwhile, Apply writes nothing and offers Re-check.
  - **Ways in:** Home, the panel's "Review notes" button, or the notification.
  - New `Disclosure` component. ADR 0010.
- Background processing:
  - **Finish queues the room.** It's processed in the background, one room at a time, while the app stays usable.
  - **The panel shows each step in plain words**, with a thin progress line; a problem shows its reason and a Retry button.
  - **A desktop notification** says when a room is ready to review, or if it couldn't be processed; clicking it opens the room.
  - **Quitting mid-run is safe**: the room processes again at the next launch.
  - **"Back to the room"** discards anything already prepared.
  - ADR 0009; notifications use jeepney.
- Staging, Apply, Discard and backups (`engine/stage.py`, `recon/processing.py`):
  - **Staging:** a room's notes are staged under `runs/<run id>/staged/` with a manifest of hashes, and the vault isn't touched.
  - **Apply:** it re-checks every note and stops, writing nothing, if any changed in Obsidian meanwhile. Otherwise it backs up each file it will overwrite (keeping the newest 20 runs) and writes atomically. Existing notes change only inside Recon's markers.
  - **Raw notes** are never changed: a re-run gets "(raw notes 2)".
  - **Crashes:** an Apply interrupted by a crash is finished at the next launch.
  - **Discard** throws the staged notes away and sends the room back to capturing.
  - **Run records:** runs are recorded in `app.db` (migration 0004), for History later. ADR 0008.

## [0.1.0] - 2026-10-28

Phase 1, shell and capture: Home, Start a room, the room session panel with block editors, Undo, the focus timer, a temporary Finish with Markdown export, Settings and an app-menu entry. Notes autosave within half a second, and flags never reach storage. Includes every fix from the independent Phase 1 audit (`docs/audits/phase-1.md`).

### Added

- App menu entry: `scripts/install_desktop.py` installs `io.github.tylerlight071.Recon.desktop` (runs `packaging/recon-launch`, no terminal) and Recon's icon under `~/.local/share`, then refreshes KDE's menu; `--uninstall` removes only what it installed. The entry passes `desktop-file-validate`.
- Settings (first pass): vault folder (default `~/Cyber Vault`), accent colour (violet, cyan, green) applied live in both windows, Reduce motion, pin the panel on or off, panel width slider, and the focus chime with a "Play" preview. Changes save as you make them; "Done" returns to Home. New `Toggle` and `Slider` components. `scripts/screenshots.py` renders every screen for gates.
- Finish (temporary until Phase 2): "Finish room" marks the room done and shows a calm completion screen with what was written and the time spent, "Export as Markdown" (one `.md` per room into a folder you pick, remembered, never overwriting), "Open folder", "Back to the room" and "Done". Adds `jinja2` for rendering, safe file names (`engine/names.py`) and `services/open_url.py`.
- Focus timer: the header chip shows time on the task (it pauses after 15 minutes away), recorded per task and room (migration 0002). The chip's menu starts a 15, 25 or 45 minute focus block, shown as a thin line filling up, never a countdown, with a gentle notice at the end and an optional soft chime (off by default; `chime` in settings). One break nudge after 90 minutes of continuous work. New `PopupMenu` component.
- Undo: Ctrl+Z / Ctrl+Shift+Z across the task (typing about a word at a time, adds, deletes, moves), kept in `undo_log` so a deleted block can come back after a restart. Each block has a quiet × (Ctrl+Shift+Backspace) to delete it, with a 10 s "Block deleted." Undo toast; the last block can't be deleted.
- Block editors: Command is monospace with `# comments` shown dimmer; Table shows a grid preview of tab, pipe or comma rows; Room question has an answer field hidden behind "Show answer" when you come back. Drag a block's grip, or press Alt+Up / Alt+Down, to reorder. Table parsing and comment detection live in `engine/parse.py` with property tests.
- "Previous task" in the panel footer (Alt+Left) to go back and add or fix something. It saves first, never changes a task's status, and is greyed out on task 1.
- Room session in the panel: room name, "Task n of N", progress ring and time in the header; an optional task title; the task's blocks with a Key idea block always ready and focused; an add bar with all eight block types in a fixed order (Ctrl+1 to Ctrl+7; Screenshot and Voice "Coming soon"); "Skip this task"; and one primary button, "Next task" or "Finish room" (Ctrl+Return), with a small tick. Every keystroke is flag-filtered and autosaved; other writes run in order off the UI thread. Starting a room or "Carry on" opens it here.
- Start a room: the room name and number of tasks, with path and module remembered from the last room behind "More", and From memory shown as "Coming soon". Missing or unusable fields get one plain sentence and the cursor goes to the field. The room is saved off the UI thread, then the panel opens. New `TextField` and `Choice` components.
- Home screen: one accent button ("Start a room" or "Carry on with <room>"), a "Where was I?" card with the room, "Task 4 of 7", how long ago and the last line written, and up to five recent rooms. Times read calmly ("2 days ago"); nothing counts as overdue. A test checks that no main-window screen shows more than one accent button.
- Flag filter (hard rule 2): `THM{…}`, `flag{…}`, `HTB{…}` and lone 32+ character hex strings are stripped from every text field before it reaches the database, including flags still being typed. The panel shows "Flag skipped", and "Not a flag, keep it" is offered for example hashes only. Mutation testing kills 111 of 111 mutants. ADR 0005.
- Database layer: `app.db` in WAL mode, private, with numbered migrations (the Phase 1 tables as STRICT tables with constraints); repositories for rooms, tasks and blocks; an autosave queue that writes every edit within half a second, even during continuous typing; and a daily snapshot through SQLite's online backup API, keeping 14. A `kill -9` test confirms at most half a second of typing is lost.
- Opt-in panel pinning: a one-time question at first launch, then a KWin rule that keeps the panel at the right edge, full height (respecting a visible taskbar) and the width from Settings. A KWin script is the fallback if the rule can't be written, and a calm toast appears if neither works. Unpinning leaves `kwinrulesrc` exactly as it was. ADR 0004.
- The two windows on one shared QML engine: the main window (sidebar with Home and Settings for now) and the side panel ("Recon Panel"), whose width (360–520 px) is remembered in `settings.toml`. Opening a main-window screen from the panel raises the main window with a quick fade; closing the main window leaves the panel open. QML can only load local resources. Adds `tomli-w` to write settings, and crash-safe atomic file writes.
- Component set on QtQuick.Templates: Button (primary, secondary, quiet), IconButton, Card, TextArea with a fading hint, Block, ProgressRing, Toast with Undo, Dialog, SidebarItem, TimerChip, Tooltip with shortcut, plus Recon's own line icons and keyboard focus rings. Every interactive component has an accessible role and name. `python -m recon --gallery` shows them all.
- `Theme.qml` singleton with every design token (colours, accent choice, block edges, type, spacing, radii, panel widths, motion with Reduce motion) and the bundled Inter and JetBrains Mono fonts (OFL). Tests check the tokens against CLAUDE.md, text contrast of at least 4.5:1, and that QML outside the theme uses no literal colours or sizes.

### Fixed

- A finished room's row on Home opens its Finish screen again, so it can still be exported or reopened after "Done", a quit or a crash (audit F-11).
- Tab moves between blocks and controls instead of typing a tab; Table blocks keep their tabs, and Ctrl+Tab leaves them (audit F-13).
- When saving fails, one calm notice says Recon keeps trying (not a new one every second), and "Saved again." appears when it works (audit F-17).
- A vault path typed into `settings.toml` as `~/…` is expanded, and a relative path, or one inside Recon's checkout or data folder, falls back to `~/Cyber Vault` (audit F-20).
- A notice that arrives while the delete toast shows its Undo waits its turn instead of taking the Undo away (audit F-21).
- The app-menu installer escapes `%` in paths and won't replace a desktop entry it didn't write without `--force` (audit F-23).
- README, ARCHITECTURE and the threat model match the code again (audit F-24).
- Opening Recon while it's already open no longer starts a second copy that could overwrite your edits: it says "Recon is already open" and stops (audit F-10).
- If Recon can't start (a database from a newer Recon, a database it can't open, folders it can't set up), it says why in a small window, not only in a terminal you can't see from the app menu, and the copy names the real cause (audit F-12).
- In the Markdown export, a line of your notes starting with `<script`, `<style` or `<!--` no longer hides the rest of the note: a leading `<` is escaped, and so is any `<` in a table cell (audit F-08).
- Every folder Recon creates is private (0700), not just the last one: `backups/` was 0755. Files and folders already there are locked down to 0600/0700 at launch, and Qt's compiled-QML cache now lives in Recon's private cache folder (audit F-09, F-22).
- The UI thread no longer waits on storage. Reads use their own read-only connection that never waits for a write; "Not a flag, keep it" and settings saves run on workers (audit F-05).
- Turning panel pinning on and quickly off (or the reverse) can no longer leave the wrong state in KDE: pin and unpin run in order and check the setting when they run (audit F-16).
- Commands and notes that mention `flag{`, `THM{` or `HTB{` are no longer cut off at that word when saved. Only something that looks like a flag mid-typing is held back (audit F-03, ADR 0005 amended).
- A hash typed key by key no longer reaches the database before its last character: timed saves hold back a 20–31 character hex run ending a line (audit F-07).
- A flag typed into a task title, room name, path or module now disappears as you type, with the "Flag skipped" notice (audit F-14).
- The delete toast's Undo, pressed after "Finish room", no longer loses the block: it comes back into its task, and its undo step is forgotten only once it's saved (audit F-01).
- Undo can no longer land on the wrong block. Block IDs are never reused (migration 0003), so a restored block always gets its own ID back (audit F-04).
- A task title typed without pausing is saved within half a second; before, the save waited for a pause and could be lost in a crash (audit F-02).
- Quitting straight after "Next task", a delete or an undo no longer drops it: queued saves finish before the database closes (audit F-06).
- A finished room's undo history, which holds old and deleted text, is cleared, and steps older than 30 days are dropped (audit F-19).

## [0.0.0] - 2026-10-24

Phase 0, foundations: repository, tooling, environment checks and smoke tests proving the stack runs on the development machine. No app to run yet.

### Added

- Repository, labels, milestones and Phase 0 issues.
- uv project pinned to Python 3.13 with the package layout from CLAUDE.md, and the app ID `io.github.tylerlight071.Recon`.
- Quality tooling: ruff (broad rule set), mypy strict, pytest with branch coverage and per-package gates, hypothesis, mutmut config for the safety-critical modules.
- pre-commit hooks (ruff, mypy, fast tests, gitleaks, Conventional Commits, no pushes to `main`), CI and release workflows, Dependabot.
- `ReconError` hierarchy with plain user-facing messages; XDG paths with private permissions; rotating logging that redacts note content.
- Tests for the network-import rule and for keeping content out of `app.log`.
- README, SECURITY, architecture, threat model, audit checklist and the stack ADR.
- `docs/environment.md`: the development machine's state and the fixes agreed in task 0.5.
- Pulled the default models (`qwen3.5:9b`, `gemma4:12b`, `qwen3-embedding:0.6b`), recorded in `docs/environment.md`; the Ollama registry is listed as a download source.
- Model smoke tests (`scripts/smoke/`): structured output, embeddings and vision against local Ollama, with unit tests and `-m ollama` tests. Runtime dependencies `ollama`, `pydantic`, `numpy` and `pillow` added.
- `packaging/recon-launch`, which starts Recon with the CUDA libraries on the loader path, and the Whisper smoke test (`large-v3-turbo` on CUDA, float16 and int8_float16). Voice dependencies sit in a `voice` extra; ADR 0002 records why cuDNN isn't needed and why PyAV is capped below 19.
- Qt and desktop smoke tests: a QML window with the bundled Inter (400/500/600, OFL) and a 200 ms animation (also headless in CI); F9 through the GlobalShortcuts portal via jeepney; a KWin rule pinning only the panel. Dependencies `pyside6` 6.11.x and `jeepney` added, plus `pytest-qt` for development. ADR 0003 records the findings.
- Three original fixture rooms (`tests/fixtures/rooms/`) in the Phase 1 table shape, with deliberate conversion, port and command-flag mistakes, a fake flag and a flag-shaped example hash; a validating loader and tests proving each trap is really wrong.
- Phase 0 independent audit (`docs/audits/phase-0.md`): 18 findings, each tracked as an issue. Phase 1 task issues created.
- `scripts/check_env.py`: read-only environment check for Ollama, GPU, desktop portal, audio, Obsidian and disk space.

### Fixed

- The release workflow's main-and-CI guard no longer tries an unauthenticated `git fetch` (it already has `origin/main` from the full checkout), which stopped the first v0.0.0 release run.
- CI never cancels runs on `main`, and releases need a tag on `main` whose CI passed; the CHANGELOG section is matched literally (audit F-15). The headless QML test no longer depends on wall-clock timing (F-18). Reasons added to the remaining `Any` and ignore comments (F-13).
- `check_env` no longer reports Ollama as running when `ollama --version` times out or fails, and the GPU check reads only the service's current run (audit F-07). It also reports unreadable `nvidia-smi` output, unrunnable programs and an unknown models folder instead of crashing or guessing (F-16).
- `recon-launch` installs the voice extra before building the CUDA library path, so the first launch after a plain `uv sync` or a fresh clone finds cuBLAS (audit F-06).
- The per-package coverage gate prints what it checked, normalises absolute and `./` report paths, and fails on code the report never measured (audit F-05). `scripts/check_env.py` and `scripts/coverage_gates.py` are now measured too (F-08).
- The network guard for hard rule 1 now also catches stdlib network clients, `asyncio`, `webbrowser`, Qt web modules, Hugging Face downloads, `subprocess` and `QDesktopServices` outside named modules, dynamic imports, and remote URLs or network APIs in QML (audit F-04).
- Log redaction holes from the Phase 0 audit (F-03): content as the message under any logger name, exception text cached by another handler, and logger names. Permissions are re-checked after chmod, and an existing too-open `app.log` is locked to 0600 (F-14).
- `main` can no longer be changed by a multi-ref push, `--all` or a delete: the pre-push guard is now a git hook that reads every ref (audit F-02). Install with `scripts/install-hooks`. The fast-test commit hook now runs on every commit (F-17).
- Docs from the Phase 0 audit: when task issues are created, the fast-test command, the audit template's areas, ADR 0001's portal note, and README's network wording.

[Unreleased]: https://github.com/tylerlight071/recon/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tylerlight071/recon/compare/v0.0.0...v0.1.0
[0.0.0]: https://github.com/tylerlight071/recon/releases/tag/v0.0.0
