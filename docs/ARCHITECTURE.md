# Architecture

How Recon is put together. Behaviour is defined in [`SPEC.md`](SPEC.md); conventions in [`../CLAUDE.md`](../CLAUDE.md). This file is kept current in the same pull request as any change it describes.

**Built so far:** Phase 0 foundations and Phase 1 (shell and capture): the theme and components, both windows, the database layer, the flag filter, Home, Start, the room session panel and its block editors, Undo, the focus timer, Finish with Markdown export, Settings and the app-menu entry. Phase 2 so far: the vault bootstrap, the Ollama service, pipeline steps 1, 3 and 6 (parse, extract and render), and staging, Apply, Discard and backups. `revision/` and the processing pipeline are still empty.

## Layers

```text
            QML (ui/)                     PanelWindow.qml · MainWindow.qml
               │  property bindings, slot calls (no I/O in QML)
            bridge/                       QObject controllers, list models; thin
               │  QThreadPool workers, progress signals
   ┌───────────┼───────────────┬────────────────┐
 engine/     revision/       db/            services/
 pure Python FSRS, cards     SQLite,        Ollama (only network user),
 no Qt       sessions        migrations,    Whisper, audio, portal,
                             repositories   notifications, KWin rule
```

Rules that the structure enforces:

- `engine/` never imports Qt. It takes pydantic models in and returns pydantic models out.
- `bridge/` holds no business logic; QML never does I/O.
- The UI thread never blocks: model calls, Whisper, embeddings and file writes run on worker threads and report plain-English progress. Writes go to serial workers (`workers.SerialWorker`): one for the room (session, focus timer, Finish, "Not a flag, keep it"), one for settings and one for KDE pinning. Reads use a separate read-only connection that never waits for a write. The only writes on the UI thread are the final saves at quit, after every worker has drained.
- Only `services/ollama.py` may import networking modules, and it refuses non-loopback hosts. Hugging Face libraries are allowed only in `services/whisper.py`, `subprocess` only in `services/kwin.py`, and `QDesktopServices` only in `services/open_url.py`. Dynamic imports are banned, and QML may not reference remote URLs or network APIs. `tests/test_network_imports.py` checks all of this, with self-tests for each bypass form.
- Dependencies (Ollama client, Whisper, clock, filesystem roots, ID generation) are passed in, so tests can fake them.

## Flag filter (hard rule 2)

`recon/engine/flags_filter.py` (pure Python) finds and strips `THM{…}`, `flag{…}` and `HTB{…}` flags and lone hex strings of 32 or more characters, repeating until the text is stable. The database layer always strips a braced flag still being typed: the prefix, then no whitespace, quotes or pipes, up to the end of the line. That's narrow on purpose, so `grep -ri "flag{"` keeps every word. Timed autosaves (`final=False`) and undo snapshots also hold back a 20–31 character hex run ending a line, a hash still being typed; final saves store it. Every repository write passes through it, so nothing flag-shaped can reach `app.db`, its snapshots, or anything built from it later. `bridge/flags.py` (`FlagGuard`) cleans editor text and signals the panel's "Flag skipped" toast. The toast offers "Not a flag, keep it" only for a single lone hex string, which is then recorded in the block's `kept` list. Task titles and Start's fields go through `FlagGuard.cleanField`, with the notice in their own window. Rules and reasons: [ADR 0005](adr/0005-flag-filter-rules.md).

## Design tokens

`recon/ui/theme/Theme.qml` is a QML singleton (`qmldir`; screens import it with `import "../theme"`). It holds every colour, type size and weight, spacing step, radius, panel width and duration from CLAUDE.md's design system. It also loads the bundled Inter (400/500/600) and JetBrains Mono fonts. `accentName` ("violet", "cyan" or "green") and `reduceMotion` are the two settable properties; Settings binds them in task 1.14. Tests check the tokens against CLAUDE.md, 4.5:1 contrast for every text token on every surface and on every accent fill, and that no QML outside `ui/theme/` uses literal colours or sizes.

## Components

`recon/ui/components/` holds Recon's own controls, built on `QtQuick.Templates` so they follow the design system rather than the system theme:

- **Controls:** `Button` (primary, secondary and quiet), `IconButton`, `TextArea` (the hint fades while typing), `TextField` (single line, same hint; Return accepts), `Choice` (a radio option with a detail line), `SidebarItem`, `TimerChip`.
- **Surfaces:** `Card`, `ListRow` (title, detail and a trailing note; clickable only when it leads somewhere), and `Block` (a coloured edge per type, a type label, a drag handle).
- **Feedback:** `ProgressRing`, `Toast` (an optional Undo; 10 s by default), `Dialog`, `Tooltip` (with a shortcut).
- **Helpers:** `Icon` (Recon's own line icons drawn with QtQuick.Shapes, no icon font) and `FocusRing`.

Every interactive component sets `Accessible.role` and `Accessible.name`, works from the keyboard (Space, Return and Enter), and shows a focus ring only for keyboard focus. `screens/Gallery.qml` shows them all (`python -m recon --gallery`, developer only).

## Entry point

`recon/__main__.py` sets up the private data folders and logging, then `recon/app.py` creates the `QGuiApplication` with the app ID (set before the app object, as the portal and KWin rule need) and loads QML into a `QQmlApplicationEngine`. QML warnings are logged as a count and line number only, since their text can quote bound values. `root_window()` casts PySide's plain `QWindow` root back to `QQuickWindow`.

Start-up problems are never silent (audit F-12). If the folders can't be set up, the database can't be opened, or a newer Recon wrote it, `show_startup_problem` prints the error's plain copy and shows it in a small window (`ui/StartupProblem.qml`, one "Close" button). Each cause has its own error and copy: `DataFolderUnusableError`, `InsecurePermissionsError`, `DatabaseUnreadableError` and `DatabaseTooNewError`.

One copy runs at a time (audit F-10). `main` takes a `QLockFile` (`recon.lock` in the data folder) before opening the database. A second launch finds it held, says "Recon is already open. Look for its window in the taskbar." and exits, never touching the database. Qt notices a stale lock left by a crash (its process is gone) and takes it over.

## Two windows

One `QQmlApplicationEngine` (`app.create_engine`) loads `MainWindow.qml` and `PanelWindow.qml`, and both bind to the same bridge objects, which are attached as context properties per engine so tests stay independent. Wayland windows can't position themselves, and a pinned window can't resize freely, hence two windows.

- **Main window** (title "Recon"; Home, Review, Cards, Revise, Ask, Library, Settings): shown at start at 960×640, which fits the 1280×720 logical desktop. Its position is left to KWin. A sidebar switches screens through `Navigation`.
- **Panel** (title "Recon Panel", which the KWin rule matches; room session and Finish): hidden until a room opens (`Navigation.showPanel()`). Its width comes from `AppSettings.panelWidth`, limited to 360–520. Resizing it updates the setting, which `SettingsBridge` saves 500 ms after the last change and again at quit.
- **Opening a full-view screen from the panel** (`Navigation.open(screen)`) shows or raises the main window, with a quick fade of its content (Wayland ignores window opacity). Closing the main window hides it and never closes the panel.
- **Network:** the engine's network access manager (`services/qml_network.py`) refuses every URL scheme except `file:`, `qrc:` and `data:`.
- **Pinning** (opt-in, [ADR 0004](adr/0004-panel-pinning.md)): asked once at first launch. `services/kwin.py` writes Recon's KWin rule (exact app ID and title, position forced, width forced, height from vertical maximise), with a session KWin script as the fallback. `bridge/pinning.py` runs it on Qt's thread pool and re-pins when the width setting changes. While pinned, the width comes from Settings only.

## Home

`bridge/home.py` (`HomeModel`) reads rooms each time Home is shown. The one accent button reads "Start a room", or "Carry on with <room>" when a room is still being captured (`RoomRepository.current()`: the most recently updated room in `capturing`). The "Where was I?" card shows the room, "Task 4 of 7", how long ago in calm words (`ago()`: "2 days ago", never an overdue count) and the last line written (`BlockRepository.latest_written()`). Recent rooms list up to five others; only rooms still being captured can be resumed from the list. "Carry on" emits `resumeRequested`; "Start a room" emits `startRequested`.

## Start a room

`screens/Start.qml` sits under Home (no sidebar entry; Home stays lit) and asks for two things: the room name and the number of tasks. Path and module are prefilled from the last room and sit behind "More". The mode choice shows New room, with From memory disabled as "Coming soon" until Phase 4, so the choice never moves. Return in any field starts; Escape goes back.

`bridge/start.py` (`StartRoom`) checks the fields (a name, and a whole number of tasks from 1 to 50) and says what to fix in one plain sentence, moving focus to that field. Lengths are capped (name 120, path and module 80), and the repository strips flags as usual. The room is created on Qt's thread pool (`bridge/workers.py`); a storage failure comes back as the error's calm message.

`bridge/flow.py` wires the hand-overs once, for the app and its tests: Home's "Start a room" opens Start; a new room switches the main window back to Home without raising it and shows the panel; "Carry on" shows the panel. Home refreshes whenever the session changes, so "Where was I?" stays current.

## Room session (panel)

`screens/Session.qml` fills the panel while a room is open; with none open, the panel says so and offers Home. Top to bottom:

- **Header:** room name, "Task 3 of 7", the progress ring (tasks done or skipped), time since the room was opened, and a Home button.
- **Task title:** optional; its hint is "Task 3".
- **Reminder:** a quiet one-line note about writing in your own words.
- **Blocks:** the task's blocks, with a Key idea block always present.
- **Add bar:** one button per block type, in a fixed order, with Ctrl+1 to Ctrl+7. Screenshot and Voice show "Coming soon" until Phase 5.
- **Footer:** "Previous task" (Alt+Left; disabled on task 1), "Skip this task", and the one accent button, "Next task" ("Finish room" on the last task, Ctrl+Return).

`bridge/session.py` (`RoomSession`) holds the open room, its tasks and a `BlockListModel` (`bridge/blocks_model.py`, which also holds SPEC.md's block table: labels, hints, shortcuts, icons).

- **Keystrokes:** each one goes through `edit()`, which strips flags via `FlagGuard`, queues the content in the autosave queue and returns the text to show. The model is updated without notifying QML, so the cursor stays put.
- **"Not a flag, keep it":** restores the string where it was, or at the end if Tyler has typed since.
- **Task title:** saves within half a second of the first unsaved keystroke, even while Tyler keeps typing (max-latency, like block autosave), and immediately on Next, on switching rooms and at quit.
- **Other writes:** opening a room, adding a block, saving the title, Next and Skip run in order on one private worker thread (`workers.serial_submit`); results come back as signals.
- **Next, Skip and Previous:** flush the autosave queue, mark the task done or skipped (Previous marks nothing), record the position, and open the target task with its starter block. Next plays a tick in the ring.
- **Last task:** finishing it emits `finishRequested` for task 1.13.
- **Failures:** a calm toast, never a stuck panel.

## Block editors

`ui/editors/BlockEditor.qml` gives each block the editor its type needs:

- **Key idea, Question, Confused by:** plain text with SPEC.md's hint, which fades on typing and returns when the block is cleared.
- **Command:** monospace. `Editors.dimComments` attaches a `QSyntaxHighlighter` (owned by the editor's document) that colours shell-style `# comments` with `engine/parse.comment_start`, ignoring `#` inside quotes or words.
- **Table:** free text, plus a grid preview (`TablePreview.qml`) from `Editors.tablePreview`, built on `engine/parse.parse_table`. That reads tab, pipe (Markdown included) or comma rows (CSV quoting), whichever appears on the most lines. The preview shows up to 12 rows and 6 columns and says how many more are in the note. Phase 2's templates use the same parser.
- **Room question:** the question, then the answer (`RoomSession.editAnswer`, flag-filtered like everything else). The answer shows while empty and is hidden behind "Show answer" when the task is opened again.

**Reordering:** drag a block's grip (an accent line shows where it will land), or press Alt+Up / Alt+Down in a block. `RoomSession.moveBlock` moves the model row at once and saves the new order on the worker thread.

## Focus timer

`bridge/focus.py` (`Focus`) drives the header's chip.

- **Time on task:**
  - It counts while Tyler is working. Every edit in the session (`RoomSession.activity`) keeps it going, and it carries on for up to 15 minutes without one (reading the room in the browser). After that he's away and it stops.
  - A suspend counts as at most 2 s.
  - Time is written per task (`tasks.time_spent_s`, migration 0002) and to the room every 30 s, on every task switch, and at quit. It doesn't touch the room's `updated_at`, so "Where was I?" still means the last note.
- **Focus blocks:** 15, 25 or 45 minutes from the chip's menu (`PopupMenu`). The chip shows a thin accent line filling up, never a countdown. At the end the panel says "That's 25 minutes of focus. Keep going, or take a short break.", and plays the soft chime if Settings has it on (`chime`, off by default).
  - The chime (`ui/sounds/chime.wav`) is generated by `scripts/make_chime.py`, so there's no download or licence to track. `services/chime.py` imports QtMultimedia and loads the sound on first play only, so Recon starts (silently) even without the system's audio library, libpulse.
- **Break nudge:** after 90 minutes of continuous work, one toast: "You've been at this for an hour and a half. Time for a short break?" Being away for 15 minutes counts as the break.

## Finish (temporary, task 1.13)

"Finish room" on the last task (or skipping it) hands over to `bridge/finish.py` (`Finish`), wired in `flow.connect_finish`:

- **Handing over:** the timer saves its last seconds, the session puts the room away (`closeRoom`, flushing autosave on the room's serial worker), and Finish marks the room `done` and shows `screens/Finished.qml` in the panel.
- **The screen:** a small tick settling in, "DNS in Detail is finished.", what was written ("3 tasks: 2 written up, 1 skipped.") and the time spent.
- **Export as Markdown:** opens the system folder picker (`FolderDialog`; on KDE, the portal's own dialog). The folder is remembered (`export_folder` in settings).
  - `engine/export.export_room` renders the room with `engine/render.render_export` (a Jinja2 template, `templates/export.md.j2`).
  - Your text is escaped where it would become structure, commands are fenced, and tables become Markdown tables. Flags are stripped again on the way out.
  - The file name comes from `engine/names.file_name`, the path is checked to stay in the folder, and the file is created with a hard link, so it never overwrites: a clash becomes "DNS in Detail (2).md".
- **Open folder:** goes through `services/open_url.py`, the only module allowed `QDesktopServices`, and only for local folders.
- **Back to the room:** sets the room back to `capturing` and reopens it at the last task. **Done** returns to Home.

The room, its tasks' time and the export all go through one serial worker (`room_worker`, a `workers.SerialWorker`), so a save always lands before the next read. At quit, `__main__` drains it, and Qt's global pool, before the last title, time and keystrokes are saved and before the database closes.

## Settings (first pass, task 1.14)

`screens/Settings.qml` in the main window. Every change saves on its own (`SettingsBridge` saves 500 ms after the last change), and "Done" (the screen's one accent button) goes back to Home.

- **Vault folder:** `vault_path`, where "" means `~/Cyber Vault` (`config.vault_folder`). It's shown with `~`, and changed with the system folder picker. Nothing is created yet; Phase 2 sets the vault up.
- **Accent colour:** violet, cyan or green (`accent`). `MainWindow` binds `Theme.accentName` and `Theme.reduceMotion` to `AppSettings` once; the engine is shared, so both windows follow live.
- **Reduce motion:** `reduce_motion` makes every theme duration 0.
- **Pin the panel:** a toggle calling `Pinning.pin()` / `unpin()` (ADR 0004). A failed unpin gets a calm toast.
- **Panel width:** a slider from 360 to 520 px in 4 px steps. While pinned, the rule is rewritten once the width settles.
- **Chime:** a toggle, with "Play" (`Focus.previewChime`) to hear it first.
- **Models** (task 2.2): what each model is for and whether Ollama has it; see Ollama service.

New components: `Toggle` (a switch with its label) and `Slider`. `Choice` gains an optional colour swatch.

## Vault (task 2.1)

`engine/vault.bootstrap` creates or completes the vault Recon owns (`~/Cyber Vault` unless Settings says otherwise):
- the folders from SPEC.md;
- `Home.md`, a Bases dashboard, from `templates/vault/home.md.j2`;
- three `.base` files in `Bases/`;
- Obsidian's `.obsidian/app.json` (wikilinks, automatically update links, attachments in `Attachments/`).

It never replaces a file, and `app.json` only gains missing keys. `bridge/vault.py` (`Vault`) runs it on the room worker at launch and whenever the vault setting changes. Until Tyler confirms he's opened the folder in Obsidian once (stored as `obsidian_vault`), Home shows a one-time card with Copy path and "I've done that", and `canOpenInObsidian` stays false. This is scaffolding, not room output, so hard rule 3 still holds: [ADR 0006](adr/0006-vault-bootstrap.md).

## Ollama service (task 2.2)

`services/ollama.py` is the only module that touches the network.

- **This computer only.** `loopback()` accepts http(s) addresses for `localhost`, `127.0.0.0/8` or `::1` and raises `UnsafeHostError` for anything else, before a client exists. `make_client()` builds every `ollama.Client` through it. The address is `ollama_host` in settings (default `http://127.0.0.1:11434`).
- **Health.** `OllamaService.status(models)` lists installed models and returns whether Ollama answered and which models are missing (`qwen3` matches `qwen3:latest`). It never raises.
- **Structured calls.** `structured(model=, schema=, system=, prompt=, run=, step=)` sends the pydantic schema as `format`, also appends it to the system prompt, uses temperature 0 and doesn't stream. The reply is validated with `model_validate_json`. On failure it retries once, adding the reply and a note with each error's location and message (never the input). A second failure raises `ModelResponseInvalidError`.
- **Errors.** A refused connection or HTTP failure becomes `OllamaUnavailable`; a timeout becomes `OllamaTimeoutError` (300 s for calls, 5 s for health checks). A 404 becomes `ModelMissing`, and any other Ollama error `ModelCallFailedError`. Each has plain copy.
- **Run logs.** `services/runs.py`: `RunStore.start()` makes a `RunLog` for `runs/<UTC time>-<id>/`, and every attempt's messages and raw reply are written there as `<step>-<attempt>.json` (folder 0700, file 0600, atomic). `app.log` gets only the model, step, attempt, duration and error counts. Start-up deletes runs older than 30 days on the global pool, and never follows a symlink.

Model names are settings (`text_model`, `vision_model`, `embedding_model`; defaults `qwen3.5:9b`, `qwen3.5:9b`, `qwen3-embedding:0.6b`), restricted to Ollama's name characters. `bridge/models.py` (`Models`) checks Ollama at launch, when Settings opens, and on "Check again", on the global pool. Settings shows what each model is for, a green or amber dot (never red), one plain line, and for missing models the exact `ollama pull` commands with Copy. Recon never pulls a model itself.

## Pipeline: parse, extract, render (task 2.3)

Pure Python in `engine/`. The bridge will run it on a worker in task 2.5. [ADR 0007](adr/0007-note-rendering.md) records why it works this way.

1. **Parse** (`engine/capture.py`): `capture_room(room, tasks, finished_on)` builds a `Capture` from the database rows. Each block keeps its type, empty blocks are left out, screenshots wait for Phase 5, and flags are stripped again, keeping only "Not a flag, keep it" hashes.
2. **Extract** (`engine/extract.py`, prompt `engine/prompts/extract.RoomExtract.md`, schema `engine/schemas.RoomExtract`): the room goes to the text model as numbered, typed blocks between `<room>` delimiters, described as data. `check` then applies every rule code can check: points cite their own block, concepts and tools must appear in his notes, `own_words` must be his, flags come from his commands, and tool names stay with tool notes.
3. **Render** (`engine/notes.py`, templates in `engine/templates/notes/`): `render_room` returns a `Rendered` set of notes, each with a path relative to the vault, a kind (room, raw, concept or tool) and its text. Model text goes through `engine/sanitise.inline` and gets its links from the engine. Tyler's own text is escaped only where it could break structure. Generated parts are labelled, and generated sections sit between markers. Nothing is written yet: staging is task 2.4.

`engine/commands.py` reads Command blocks in code: each command and its `# comment`, and the programs and flags it runs (`sudo -u root nmap -sV` runs `nmap` with `-sV`).

## Staging, Apply and Discard (task 2.4)

`engine/stage.py` is the only code that writes room output into the vault. [ADR 0008](adr/0008-staging-and-apply.md) records why it works this way.

- **Stage:** `stage(rendered, vault, run_folder, room_id=…)` writes each note to `runs/<run id>/staged/<vault path>`. It also writes `manifest.json`, which lists each file with its action (`create`, `update`, `same` or `skip`), the target's SHA-256 when staged, and the staged content's SHA-256.
  - An existing note is merged with `merge`: only the inside of matching `%% recon:start` sections changes, and new sections go at the end under their heading.
  - A note whose markers are damaged, or that isn't valid UTF-8, is skipped and listed.
  - Raw notes are never updated. A re-run's raw notes become `… (raw notes 2).md`, and the room note's link follows.
- **Apply:** `apply(run_folder, vault, backups)` runs in this order:
  1. It checks the staged files against the manifest.
  2. It re-hashes every target. Any change raises `ApplyConflict` before anything is written.
  3. It copies each file it will overwrite to `backups/<run id>/`.
  4. It writes `apply.json` (state "applying").
  5. It writes each note atomically: new notes are created without ever overwriting, and changed notes are replaced.
  6. It marks the journal "applied".
- **Recover:** `recover` finishes an Apply a crash interrupted. It writes only files still as staged and leaves hand-edited ones alone.
- **Discard and pruning:** `discard` removes the `staged/` folder. `prune_backups` keeps the newest 20 runs' backups.
- **Every path** goes through `inside()`, which resolves symlinks and refuses anything that lands outside its folder.

`recon/processing.py` (`Processing`) ties this to `app.db`:
- `stage_room` records the run (table `runs`, migration 0004, `db/runs.py`) and puts the room in review;
- `apply_run` records it as applied and marks the room done;
- `discard_run` records it as discarded and sends the room back to capturing;
- `recover_runs` finishes interrupted Applies.

At launch, `__main__.tidy_runs` runs `recover_runs` and then deletes runs over 30 days old, on the global pool. Runs still waiting for Apply or Discard are kept.

## Undo

Ctrl+Z / Ctrl+Shift+Z undo and redo within the task on screen.

- **What's undoable:** typing, adds, deletes, moves and "Not a flag, keep it". Typing is grouped by `bridge/undo.py` (`UndoHistory`), so one step is about a word: a new step starts on another block or field, after a one-second pause, or once a word ends.
- **How a step is stored:** each step is the action that goes back (`SetContent`, `RemoveBlock`, `InsertBlock`, `MoveBlock` in `db/models.py`). Applying one returns its opposite, which goes on the other stack.
- **Persistence:**
  - Undo steps are written to `undo_log` (`UndoRepository`, flag-filtered like every other store), so a deleted block can come back after a restart. A room keeps its newest 300 steps, steps older than 30 days go, and finishing a room clears its steps (and the old text they hold). Redo lives in memory.
  - Block IDs are never reused (`AUTOINCREMENT`, migration 0003), so a step about a block always means that block. `BlockRepository.restore` brings a deleted block back at its old place with its own ID.
  - A step leaves `undo_log` only after its change is saved. Bringing a block back and forgetting its step happen in one worker job, so a failed restore keeps the step. The delete toast's Undo works even after "Finish room".
- **Deleting:** a block's × (Ctrl+Shift+Backspace) deletes it, never the last one. The panel shows "Block deleted." with Undo for 10 s, and that Undo brings back that block even if other things happened since.
- **Tab:** Tab and Shift+Tab move between controls; in a Table block Tab types a tab and Ctrl+Tab leaves (audit F-13).
- **Keys:** the block editors catch Ctrl+Z themselves, so it undoes across the task rather than inside one editor. The task title field keeps its own text undo.

Settings live in `settings.toml` (`recon/config.py`: a pydantic model, read with `tomllib`, written with `tomli-w`). An unreadable file falls back to the defaults rather than stopping start-up. Every write goes through `recon/fs.py` (temp file, fsync, replace, fsync the folder).

## Data flow for a room

1. **Capture.** Blocks are written to `app.db` through a debounced autosave queue (≤ 1 s). The flag filter runs on every save.
2. **Finish.** The room is queued; one room processes at a time.
3. **Pipeline** (`engine/`, worker thread): parse → read screenshots → extract → link → fact-check → render into `runs/<run_id>/staged/`.
4. **Review.** The main window shows staged output, links and flags.
5. **Apply** (`engine/stage.py`): re-hash targets, abort on conflict, back up overwritten files to `backups/<run_id>/`, write atomically, write raw notes once, record the run. **Discard** deletes the staging folder.

## Storage

`recon/db/` (task 1.5):
- **`connection.py`:** `Database` holds one writer connection to `app.db`, guarded by a lock so there's only ever one writer, and a second connection for reads (`query_only`, its own lock). In WAL mode a read sees the last commit without waiting for a write in progress. Migrations and checkpoints use `writer()`. Pragmas: WAL, `synchronous=FULL`, `foreign_keys=ON`, `secure_delete=ON`. The file is created 0600, and SQLite gives the `-wal` and `-shm` files the same mode.
- **`migrate.py`:** applies `migrations/NNNN_name.sql` in order, tracked in `PRAGMA user_version`. Each migration runs in one transaction with its version bump. A database from a newer Recon is refused.
- **`0001_initial.sql`:** the Phase 1 tables as STRICT tables, with CHECK constraints on every enum, JSON-validated `content`, cascading deletes, and one task per index per room.
- **`models.py` and `repositories.py`:** rooms, tasks and blocks go in and out as pydantic models through literal, parameterised SQL. Every change bumps the room's `updated_at`; block positions stay 0..n-1; `ensure_starter_block` places the empty Key idea block.
- **`autosave.py`:** a writer thread. Edits coalesce per block, and each is written at most 0.5 s after its *first* unsaved change, so continuous typing can't postpone saving. `flush()` runs on task switch and window close, and failed writes are retried. The `kill -9` crash test loses 0.5 s, within the 1 s budget.
- **`backup.py`:** a daily snapshot through SQLite's online backup API into `backups/db/app-YYYY-MM-DD.db`. It's written to a temp file, fsynced and renamed, and the newest 14 are kept. It's taken at launch; a failed snapshot is logged and start-up continues.

| Store | Location | Notes |
| --- | --- | --- |
| `app.db` | `$XDG_DATA_HOME/recon/` | Rooms, tasks, blocks, sessions, cards, reviews, settings; WAL; one writer |
| `index.db` | same | Embeddings, aliases, section hashes; rebuildable from the vault |
| `runs/`, `backups/`, `media/`, `audio/` | same | Private permissions; runs expire after 30 days |
| `settings.toml` | `$XDG_CONFIG_HOME/recon/` | Validated with pydantic |
| `app.log` | `$XDG_DATA_HOME/recon/` | Rotated 5 MB × 5; content redacted (see below) |
| Vault | `~/Cyber Vault/` | Written only by Apply |

Folders are created `0700` and files `0600` (`recon/paths.py`).

## Logging

`recon/logging_setup.py` installs a rotating handler on the `recon` logger with two guards: a filter that redacts every string argument unless it's wrapped in `Safe`, and a formatter that drops exception messages but keeps types and frames, and always rebuilds that text rather than reusing a copy another handler cached. Ruff's `G` rules stop f-strings in log calls. Static tests (each with a self-test of the detector) check that every logging-method call in `recon/`, whatever its receiver, has a literal message; that logger names are `__name__` or literals; and that `LoggerAdapter` isn't used. Existing log files are locked to 0600 at start-up. Debug content (prompts, responses) goes only to `runs/<run_id>/`.

## Errors

All deliberate errors derive from `ReconError` (`recon/errors.py`), each with a `user_message` in plain, kind copy. `except Exception` appears only at thread and process boundaries, where the error is logged (type only) and turned into that message.

## Launching

`packaging/recon-launch` is the only supported way to start the app. The app-menu entry calls it: `scripts/install_desktop.py` fills `packaging/io.github.tylerlight071.Recon.desktop`'s `Exec` with this checkout's launcher, quoted per the Desktop Entry Specification. It installs that entry and `packaging/icons/io.github.tylerlight071.Recon.svg` under `$XDG_DATA_HOME`, both named by the app ID, then refreshes KDE's menu. `--uninstall` removes only files carrying its own `X-Recon-Installed-By` marker.

The launcher syncs the `voice` extra (a quick no-op when up to date), then puts the venv's `nvidia/*/lib` folders on `LD_LIBRARY_PATH` before Python starts, raises the CUDA JIT cache cap, and runs `uv run --frozen --extra voice --no-sync python -m recon`. See [ADR 0002](adr/0002-voice-runtime.md).

## Tooling and CI

- Pre-commit: ruff, ruff format, mypy, fast tests, gitleaks, Conventional Commits, and a git pre-push hook (`scripts/hooks/pre-push`, installed by `scripts/install-hooks`) that reads every ref being pushed and refuses any update or deletion of `main` (GitHub Free has no rulesets for private repos).
- CI (`.github/workflows/ci.yml`): `uv lock --check`, ruff, mypy, tests with branch coverage, per-package gates (`scripts/coverage_gates.py`), `uv audit`, gitleaks over full history, PR title check.
- Releases (`release.yml`): a `v*.*.*` tag publishes a GitHub Release from that version's `CHANGELOG.md` section.
- Screenshots for gates: `uv run python -m scripts.screenshots tests/screenshots` builds the app with the real wiring (`create_bridges`) against a throwaway, seeded data folder and saves every screen. `tests/test_screenshots_script.py` keeps it working.
