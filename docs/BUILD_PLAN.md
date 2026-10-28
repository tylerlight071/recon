# Recon — Build Plan

How Recon gets built, in order. Behaviour is defined in `docs/SPEC.md`; engineering rules are in `CLAUDE.md`. This plan says **what to build when**, and **how we know each phase is done**.

## How to use this plan

- Work through phases in order. Within a phase, tasks are in a sensible order but can be reordered if a dependency demands it.
- Create one GitHub issue per task (`task` template, labels, the phase's milestone) before the previous phase's gate handover, so they can be reviewed at the gate. Phase 0's are created in task 0.1. Each task is done on its own branch and pull request, as set out in CLAUDE.md (Git and GitHub). Tick the task here (`- [x]`) in that same pull request.
- Each phase ends at a **gate**. Before handing over: run the independent audit described in CLAUDE.md (Audits), fix every Critical, High and Medium finding, and confirm CI is green. Then stop, summarise what was built with the audit result, coverage, mutation score and dependency audit, run the phase's manual test script, fix what it finds (each as an issue and PR), and sign the gate off. Once it's signed off, tag `v0.<phase>.0` on `main` and publish the GitHub Release from `CHANGELOG.md`, then close the milestone.
- Every task's tests are written alongside the code, in the same pull request. A task isn't ticked until its tests pass and coverage gates hold.
- Every phase leaves Recon in a usable state. Never leave the app unlaunchable at a gate.
- If a task turns out bigger than it looks, split it here before starting it.

## Phase overview

| Phase | Goal | After the gate, you can… |
| --- | --- | --- |
| 0 | Repo, environment checks, risky dependencies proven | Nothing new yet; the stack is proven on the target machine |
| 1 | Shell and capture | Take notes for a real room in the side panel; export them as Markdown |
| 2 | Processing and review | Finish a room and get real Obsidian notes after reviewing them |
| 3 | Linking and fact-checking | See rooms link to shared concepts, with mistakes flagged |
| 4 | Cards and revision | Keep flashcards, revise daily, take the end-of-room quiz, back-fill old rooms |
| 5 | Voice, screenshots and extras | Talk notes, paste screenshots, ask questions of the vault, see a weekly recap, reopen rooms |

---

## Phase 0 — Foundations

**Goal:** a clean repo and proof that every risky piece of the stack runs on the target machine before any UI work.

### Tasks

- [x] **0.1 Repo and GitHub setup.** Phase 0's setup tasks (0.1–0.3) are the only ones committed before the PR workflow exists; everything after goes through issues and PRs.
    - Run `gh auth login` if `gh` isn't authenticated. Create the private repo `recon`; first commit is `CLAUDE.md`, `docs/SPEC.md`, `docs/BUILD_PLAN.md`.
    - Repo settings per CLAUDE.md: squash merge only, auto-delete branches, Dependabot alerts and security updates, dependency graph, wiki and projects off, read-only default Actions token.
    - Labels, and milestones `Phase 0` to `Phase 5` plus `Release v1`.
    - Check the account's plan (`gh api user --jq .plan.name`). Pro or above: create the `main` ruleset. Free: install the local `pre-push` hook that refuses pushes to `main`. Do this at the end of 0.3, once the direct setup commits are in. Tell the user which applies at Gate 0.
    - Decide once whether to use SSH commit signing; set it up only if wanted.
    - Create issues for the remaining Phase 0 tasks.
- [x] **0.2 Project scaffold.** `uv init`, pin Python 3.13 (`.python-version`), `pyproject.toml` with ruff, mypy and pytest config, the folder layout from CLAUDE.md with empty packages, `.gitignore` (venv, caches, `tests/screenshots/`, any `*.db`). Agree the app ID with the user (reverse-DNS, e.g. `io.github.<github-user>.Recon`) and record it in `recon/config.py`; every later task uses that constant.
- [x] **0.3 Quality tooling and docs.** Everything in CLAUDE.md's Engineering standards, Security and privacy, and Testing sections is wired up before any feature code:
    - `ruff` (full rule set), `mypy --strict`, `pytest` with `pytest-cov` (branch coverage gates), `hypothesis`, `mutmut` 3.x config for the safety-critical modules.
    - GitHub files: `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/` (`task.yml`, `bug.yml`, `audit-finding.yml`), `.github/dependabot.yml`, `.github/workflows/release.yml`, `SECURITY.md`, `.editorconfig`, `.gitattributes`.
    - `.pre-commit-config.yaml`: ruff, ruff format, mypy, fast tests, gitleaks, plus the `commit-msg` Conventional Commits check. The gitleaks hook needs either the Go toolchain or the system `gitleaks` package; decide which before installing anything.
    - `.github/workflows/ci.yml`: the same plus `uv lock --check`, coverage gates, dependency audit and offscreen Qt tests (`QT_QPA_PLATFORM=offscreen`). Pin action versions by commit SHA.
    - `recon/errors.py` (`ReconError` hierarchy), logging setup with rotation and a test proving note content never reaches `app.log`.
    - The network test: fails if any module other than `services/ollama.py` imports networking libraries.
    - Docs: `README.md` skeleton, `docs/ARCHITECTURE.md`, `docs/THREAT_MODEL.md` (assets, entry points, threats and mitigations, matching CLAUDE.md), `docs/AUDIT_CHECKLIST.md`, `docs/adr/0001-stack.md`, `CHANGELOG.md` (Keep a Changelog format).
    - *Done when:* a deliberately bad commit (type error, failing test, fake secret, non-conventional message) is blocked by the hooks; CI is green on the empty skeleton; and a test pull request goes from issue to branch to green CI to squash merge, proving the workflow end to end.
- [x] **0.4 Environment check script** (`scripts/check_env.py`, run with `uv run`). Reports, in plain English, each with OK / needs attention:
    - Ollama: binary location, how it was installed (`pacman -Qo` on the binary; `ollama` vs `ollama-cuda` package, or the official script), version, whether the service is running, whether it uses the GPU.
    - NVIDIA driver version and CUDA version from `nvidia-smi`; confirm compute capability 12.0.
    - Session type (`XDG_SESSION_TYPE` = wayland), Plasma version, `xdg-desktop-portal` version (≥ 1.20 needed for the host app Registry) and whether the GlobalShortcuts portal is available.
    - Default audio input device, and whether the system `portaudio` library is installed (`sounddevice` needs it on Linux).
    - Obsidian: installed or not, how (pacman, Flatpak or AppImage), and whether the `obsidian://` link handler is registered.
    - Free disk space in home (models + vault).
- [x] **0.5 Report and agree fixes.** Review the check output. Propose fixes for anything flagged (e.g. Ollama too old for the Qwen 3.5 family, CPU-only Ollama) and **ask before running anything with `sudo`**.
- [x] **0.6 Pull models** (ask first; several GB): `qwen3.5:9b`, `gemma4:12b`, `qwen3-embedding:0.6b`. If a tag doesn't exist or needs a newer Ollama, say so and propose the nearest alternative.
- **0.7 Smoke tests** (`scripts/smoke/`), each a tiny script that passes or fails clearly. Split into three tasks because each needs different dependencies and hardware:
- [x] **0.7a Model smoke tests** (Ollama, no new system packages):
    - Structured output: one call with a pydantic schema; response validates.
    - Embeddings: two related and one unrelated sentence; related pair scores higher.
    - Vision: a generated test PNG containing a small table; the model returns the table's text.
- [x] **0.7b Whisper on Blackwell** and `packaging/recon-launch` (passed on float16; cuDNN turned out unnecessary; see ADR 0002):
    - **Whisper on Blackwell:** `faster-whisper` `large-v3-turbo` on CUDA (`float16`) transcribes a 5-second test clip. This is the riskiest dependency: needs CTranslate2 ≥ 4.5 built for CUDA 12.8+, plus cuBLAS (CUDA 12) and cuDNN 9 from `nvidia-cublas-cu12` and `nvidia-cudnn-cu12==9.*`, with their folders on `LD_LIBRARY_PATH` before Python starts. Write `packaging/recon-launch` here and run the smoke test through it. If it fails, try `int8_float16`, then document the fallback options (whisper.cpp with CUDA, or openai-whisper on PyTorch cu128) and decide which to take. Don't block Phases 1–4 on this.
- [x] **0.7c Qt and desktop smoke tests** (PySide6 6.11, portal, KWin; needs someone at the keyboard):
    - QML window: a PySide6 6.11 Qt Quick window opens on Wayland with Inter rendering and a 200 ms animation.
    - Global shortcut: call the host `Registry.Register` with the app ID as the first portal call, register F9, and print press and release events. Run it once from a terminal and once from a test `.desktop` entry. Confirm KDE's permission dialog appears.
    - KWin rule: open two test windows with the same app ID and different titles ("Recon Panel test", "Recon test"); write a rule to `kwinrulesrc` matching the app ID **and** the panel title; reload KWin; confirm only the panel pins to the right edge and the other window moves and resizes freely. **Ask before writing to the user's KDE config.** Remove the test rule afterwards.
- [x] **0.8 Fixture rooms.** Write three original sample rooms in `tests/fixtures/rooms/` as JSON (the same shape the app will store): *Number Systems* (binary, hex, conversions, with two deliberate conversion mistakes), *Intro to Networking* (ports, TCP/UDP, OSI, with one wrong port), *Linux Basics* (commands with `#` descriptions, one wrong flag). Include a fake flag (`THM{this_is_a_test}`) in one to test stripping. **No TryHackMe text.**

### Gate 0 — manual test for the user

1. Read the environment report; confirm anything odd.
2. Press and release F9 when asked; confirm the terminal shows both events.
3. Watch the test window snap to the right edge.
4. Look over the repo on GitHub: README, labels, milestones, the Phase 1 issues, and the merged test pull request. Confirm how `main` is protected (ruleset or local hook).

---

## Phase 1 — Shell and capture

**Goal:** the user can take notes for a real room in a polished side panel, never lose anything, and export them.

### Data model (app.db)

Create through migrations in `recon/db/migrations/`:

| Table | Key columns |
| --- | --- |
| `rooms` | id, platform, path, module, name, task_count, mode (`new` / `from_memory`), status (`capturing` / `queued` / `processing` / `in_review` / `done`), created_at, updated_at, time_spent_s, last_task_index |
| `tasks` | id, room_id, task_index (`index` is an SQL keyword), title, status (`open` / `done` / `skipped`) |
| `blocks` | id, task_id, type (`key_idea` / `command` / `table` / `screenshot` / `question` / `confused` / `room_question` / `voice`), position, content (JSON: text, plus per-type fields, e.g. answer, image path), pass (`recall` / `fill`), created_at, updated_at |
| `sessions` | id, room_id, started_at, ended_at, focus_minutes |
| `settings_kv` | key, value |
| `undo_log` | id, entity, entity_id, before (JSON), created_at |

Later phases add: `runs`, `flags`, `cards`, `reviews`, `quiz_items`, `recaps`.

### Tasks

- [x] **1.1 Theme and fonts.** `Theme.qml` singleton with all tokens from CLAUDE.md; bundle Inter and JetBrains Mono; `reduceMotion` switch.
- [x] **1.2 Component set** (each with a gallery entry in a dev-only `Gallery.qml` screen, launched with `--gallery`): Button (primary / secondary / quiet), IconButton, Card, TextArea with hint placeholder, Block (coloured edge, type label, drag handle), ProgressRing (animated), Toast (with Undo), Dialog, Sidebar item, Timer chip, Tooltip with shortcut.
- [x] **1.3 Two windows.** `PanelWindow` (title "Recon Panel", default 420 px wide, user-resizable 360–520, width remembered) and `MainWindow` (normal window with sidebar, size and position left to KWin). One engine, shared bridge objects. Opening a full-view screen from the panel raises the main window with a quick fade; closing the main window never closes the panel.
- [x] **1.4 KWin rule (opt-in).** First-run step asks "Pin the Recon panel to the right edge of your screen while you work?" On yes, write a rule matching the app ID and the title "Recon Panel" (right edge, full height, panel width), reload KWin; on failure fall back to a bundled KWin script. Settings has an on/off switch that removes it cleanly.
- [x] **1.5 Database layer.** SQLite in WAL mode, migrations, repositories for rooms, tasks and blocks; an autosave queue (debounced 500 ms, flushed on window close and every task switch); a daily local snapshot of `app.db` into `backups/db/` using SQLite's online backup API, last 14 kept, so the spec's "backed up automatically each day" holds even before an off-machine backup folder is set.
- [x] **1.6 Flag filter.** `engine/flags_filter.py` plus tests; applied on every block save; "Flag skipped" toast with "Not a flag, keep it".
- [x] **1.7 Home screen.** One primary button ("Start a room" or "Carry on with <room>"); "Where was I?" card (room, "Task 4 of 7", how long ago, last line written); recent rooms list.
- [x] **1.8 Start a room.** Two fields: room name and number of tasks; path and module prefilled from the last room and editable behind "More". Mode choice: New room (default) or From memory (built in Phase 4; show it disabled with "Coming soon" until then).
- [x] **1.9 Room session (panel).** Header (room, "Task n of N", ring, timer chip); task title (optional, defaults to "Task n"); block list with one Key idea block pre-placed and focused; add bar with the eight block types (Voice and Screenshot disabled until Phase 5, labelled "Coming soon"); footer with one primary button ("Next task", becoming "Finish room" on the last task); "Skip this task" link; tick animation on Next.
- [x] **1.9b Previous task** (added during Phase 1). "Previous task" button (Alt+Left) in the panel footer, left of "Skip this task", disabled on task 1. Saves everything first, leaves task statuses alone, and moves "Where was I?" with it.
- [x] **1.10 Block editors.** Key idea, Command (mono, `#` comment shown dimmer), Table (paste-friendly; parse tab, comma or pipe separated into a grid preview), Question, Confused by, Room question (question + answer fields; answer hidden behind a "Show" toggle). Hints as in SPEC.md's block table; hints fade on typing and return when empty. Drag to reorder. Keyboard shortcuts Ctrl+1 to Ctrl+7.
- [x] **1.11 Undo.** Ctrl+Z / Ctrl+Shift+Z across the session, backed by `undo_log`; delete shows a 10 s Undo toast.
- [x] **1.12 Focus timer.** Chip in the header: 15 / 25 / 45 minute presets; soft chime (off by default; toggle in Settings); after 90 minutes of continuous work, one gentle "Time for a short break?" toast. Time spent per task and room recorded.
- [x] **1.13 Finish (temporary).** In this phase, "Finish room" marks the room done and offers "Export as Markdown" (one `.md` per room to a folder the user chooses). Replaced by the real pipeline in Phase 2.
- [x] **1.14 Settings (first pass).** Vault path, accent colour (violet / cyan / green), reduce motion, panel width, chime on/off, KWin pinning on/off.
- [x] **1.15 Desktop entry.** `packaging/<app-id>.desktop` and icon installed to `~/.local/share/applications/` and `~/.local/share/icons/` by `scripts/install_desktop.py`, so Recon launches from the app menu. It runs `packaging/recon-launch`; no terminal window. The file name matches the app ID exactly, or the shortcuts portal and KWin rule won't recognise the app.

### Acceptance

- App launches from the KDE menu in under 2 seconds to Home.
- Killing the process mid-typing (`kill -9`) loses no more than the last second of text.
- Every screen has exactly one accent button. No literal colours or sizes in QML outside `ui/theme/` (checked by a test that greps `ui/` excluding `ui/theme/`).
- Every text token meets 4.5:1 against every surface token (checked by a test that reads `Theme.qml`).
- A fixture flag typed into a block never reaches `app.db`.
- Data and config folders are `0700` and their files `0600`; a test checks this on a fresh profile.
- Every control is usable by keyboard alone with a visible focus ring; every interactive item has an accessible name.
- Migration tests pass; property tests cover the flag filter and table parser.

### Gate 1 — manual test for the user

1. Launch Recon from the app menu. Start a real room you've done before.
2. Write notes for at least three tasks using four different block types.
3. Close Recon mid-sentence. Reopen it: check the "Where was I?" card, carry on.
4. Paste `THM{test}` into a block: check it's skipped with a notice.
5. Finish the room and export the Markdown. Is anything missing?
6. Tell me anything that felt fiddly, slow, cluttered or unclear.

---

## Phase 2 — Processing and review

**Goal:** finishing a room produces real Obsidian notes, reviewed and applied by the user.

### Schemas (engine/schemas.py)

`RoomExtraction` (one model call per room):

- `summary`: 3–5 sentences.
- `tasks[]`: `index`, `points[]` (the user's points tidied; each with the `block_id`s it came from).
- `concepts[]`: `name`, `one_line_definition`, `source_block_ids[]`, `tyler_definition_present` (bool).
- `tools[]`: `name`, `purpose`, `commands[]` (`command`, `description`, `source_block_id`).
- `claims[]`: factual statements to check: `text`, `source_block_id`.
- `question_answers[]`: for Question blocks: `block_id`, `suggested_answer`.
- `confusions[]`: for Confused by blocks: `block_id`, `explanation`.
- `diagrams[]`: optional Mermaid source where a process was described, with `source_block_ids[]`.
- `card_suggestions[]`: `front`, `back`, `kind` (`basic` / `cloze`), `concept`.

Rendering uses only these fields plus the user's original blocks.

### Tasks

- [x] **2.1 Vault bootstrap.** On first run (or when the configured vault is missing), create `~/Cyber Vault/` with the folder structure, `Home.md`, `.base` files, and `.obsidian/app.json` with wikilinks on, "Automatically update internal links" on and attachments set to `Attachments/`. Never overwrite an existing `.obsidian/` folder; merge only missing keys. Then show a one-time step: "Open this folder in Obsidian once (Open folder as vault)", with a Copy path button and an "I've done that" button. Obsidian refuses `obsidian://` links to vaults it hasn't opened, so "Open in Obsidian" buttons stay hidden until the user confirms; if a link still fails, show the same step again rather than an error.
- [x] **2.2 Ollama service wrapper.** Health check, model presence check, structured call helper (schema in `format`, temperature 0, one retry with the validation error), timeouts, raw-response logging to `runs/<run_id>/`. Friendly error states for "Ollama not running" and "model missing".
- [x] **2.3 Pipeline steps 1, 3, 6 (parse, extract, render)** for text blocks. Jinja2 templates for room notes, raw notes, concept notes and tool notes, using `%% recon:start <section> %%` markers. Properties as in SPEC.md.
- [x] **2.4 Staging, apply, discard, backups.** Stage into `runs/<run_id>/staged/`; Apply re-hashes every target, aborts on conflict, backs up overwritten files, writes atomically (temp file, `fsync`, `os.replace`), writes raw notes, records the run. Discard deletes the staging folder and returns the room to `capturing`.
- [x] **2.5 Background processing.** Finish queues the room; a worker runs the pipeline; the panel shows plain-English progress; a desktop notification ("DNS in Detail is ready to review") with an action that opens the review screen. The user can keep using the app meanwhile.
- [ ] **2.6 Review screen.** Full window, sections with counts (Room note rendered as Markdown, New notes, Additions, Links, Flags), collapsible; sticky footer with Apply (primary) and Discard; Discard asks once.
- [ ] **2.7 Finish flow.** Replace the Phase 1 temporary Finish with: Finish → (quiz placeholder) → queued → review → Apply → done screen with "Open in Obsidian" (via `obsidian://open?vault=…&file=…`).
- [ ] **2.8 Library (first pass).** Rooms list with path and date; open a room's note in Obsidian; History of runs with one-click restore from backup.
- [ ] **2.9 Model bake-off.** Run the three fixture rooms plus three real rooms through `qwen3.5:9b` and `gemma4:12b`. Score: schema failures, concepts missed (against a hand list), invented content, time taken. Write results to `docs/bakeoff.md`; recommend one; the user picks.

### Acceptance

- All fixture rooms process end to end with zero schema failures after retry.
- Tests prove: nothing touches the vault before Apply; a conflict aborts Apply; backups exist for every overwritten file; raw notes are written once and never changed; flags never appear in the vault.
- Rendered notes open cleanly in Obsidian (properties panel parses, callouts and Mermaid render).
- The whole pipeline is tested without a GPU using recorded responses; golden-file tests cover every note type.
- Hostile-input tests pass: model output containing `![[…]]`, raw HTML, `%%` markers, frontmatter fences or `javascript:` links is neutralised; room names like `../../etc` or containing control characters produce safe file names inside the vault.
- Mutation testing on `stage`, sanitising and `flags_filter` kills at least 85% of mutants.
- Killing the process mid-Apply leaves the vault either fully before or fully after the change.

### Gate 2 — manual test for the user

1. Finish the room you captured in Gate 1 (or a new one). Close the panel while it processes; wait for the notification.
2. Read the review screen top to bottom. Is anything confusing or too long?
3. Apply. Open the room in Obsidian from the done screen. Is it the note you'd want?
4. Edit a concept note in Obsidian, then process another room that would touch it. Check Recon stops and asks rather than overwriting.
5. Read `docs/bakeoff.md` and pick the model.

---

## Phase 3 — Linking and fact-checking

**Goal:** concepts are shared across rooms without duplicates, and mistakes are flagged kindly.

### Tasks

- [ ] **3.1 Index (index.db).** Embeddings for every concept and tool note (title + aliases + definition), section hashes, aliases. Refresh on launch and before each run for any vault file whose mtime/hash changed. "Rebuild index" button in Settings.
- [ ] **3.2 Matching.** Exact name/alias match → link. Otherwise top 5 by cosine similarity; above the high threshold → link; below the low threshold → new; between → model decides `same | related | new` with a structured call. Thresholds in settings, tuned on fixtures.
- [ ] **3.3 Appending.** Additions to existing concept and tool notes go inside their markers as a dated "From <room>" sub-section; `seen_in` and aliases updated. Hand-edited sections (hash differs from last Apply) are never rewritten; new material shows as "Suggested additions" on the review screen.
- [ ] **3.4 Links section on review.** Each merge listed with Undo (Undo turns it into a new note in the staged output).
- [ ] **3.5 Deterministic checks.** `factcheck/conversions.py` (bases, two's complement, CIDR sizes), `factcheck/ports.py` against `data/ports.csv` (well-known ports and protocols, written by hand with sources in the file header), `factcheck/commands.py` (flags for common tools in `data/commands.yaml`, starting with nmap, ls, grep, find, chmod, curl; unknown commands are never flagged).
- [ ] **3.6 Model review pass.** One structured call over `claims[]` not already settled by code: `looks_right | likely_wrong | unsure`, with correction and one-line reason. Only `likely_wrong` becomes a flag.
- [ ] **3.7 Flag cards.** On the review screen: "Fix my note" (jumps to the block in the panel), "I was right" (dismiss, logged), "Later" (writes the warning callout into the vault and lists it under Library → Open flags). A fixed or dismissed flag never returns for the same sentence (hash of block text).
- [ ] **3.8 Generated definitions.** When `tyler_definition_present` is false, add a one-or-two-line definition in a `> [!info] Generated definition` callout, run through the same fact-check.
- [ ] **3.9 Open flags in Library and Bases.** `open_flags` property kept accurate; Library filter; the Bases view in the vault shows the same.

### Acceptance

- Processing the three fixture rooms in any order produces no duplicate concept notes (e.g. "TCP handshake" and "three-way handshake" land on one note).
- Every deliberate mistake in the fixtures is flagged; correct statements produce at most one false flag per room.
- Hand-edited sections survive re-processing byte for byte.
- Property tests cover number conversions and CIDR maths; mutation testing on `factcheck` kills at least 85% of mutants.
- Model-suggested merges and definitions pass through the same sanitising as every other model output (tested).

### Gate 3 — manual test for the user

1. Process two real rooms that share ideas. Check the Links section, then the graph view in Obsidian.
2. Put one deliberate mistake in a note (e.g. a wrong port). Check it's flagged, kindly, with a reason.
3. Try all three flag buttons.
4. Say whether the flags felt helpful or naggy.

---

## Phase 4 — Cards and revision

**Goal:** a daily revision habit in short, calm sessions, plus the quiz and From memory mode.

### Tasks

- [ ] **4.1 Card store.** `cards` (id, concept note path, front, back, kind, hidden id written into the note as `<!-- recon:card:<id> -->`), `reviews` (card id, rating, reviewed_at, FSRS state). Cards written into concept notes in Spaced Repetition plugin format (`Question::Answer`, multi-line with `?`, `==cloze==`).
- [ ] **4.2 Keep or skip.** After Apply: suggested cards one at a time, large and centred; Keep (Enter), Edit (E), Skip (S); counter; done when the pile is empty. Kept cards are written to their concept notes in a second small apply (same staging and backup rules).
- [ ] **4.3 Revise screen.** FSRS via `fsrs`; Space flips; ratings shown as Forgot / Got it / Easy (keys 1 / 2 / 3, mapped to Again / Good / Easy); progress bar of cards left; session cap of 10 minutes or 20 cards (both configurable); "Stop here" always visible; filter by topic or path.
- [ ] **4.4 Daily nudge.** `recon --nudge` checks due cards and, if any, sends one notification ("12 cards ready, about 5 minutes") with an action that opens Revise. The nudge process must stay alive listening for `ActionInvoked` (until the notification closes, or 30 minutes at most), otherwise clicking it does nothing; on click it launches Recon straight to Revise (`recon-launch --screen revise`). Installed as a systemd **user** timer at the time chosen in Settings (default 19:00), only if the user turns it on. No repeat nudges.
- [ ] **4.5 End-of-room quiz.** On Finish: 3–5 questions generated from the room's blocks (short answer or multiple choice); generous model marking with the right answer always shown; "Skip quiz" link; wrong answers become priority card suggestions. Processing starts after the quiz (or skip).
- [ ] **4.6 From memory mode.** Recall pass: one blank Key idea block per task, hint "Write what you remember. Don't look yet."; then "Now open the room" switches to the normal flow; blocks added in the fill pass get `pass = fill`. Room note marks fill-pass points with a subtle "(filled in)" tag; their card suggestions are prioritised.
- [ ] **4.7 Progress and completion.** Per-path progress on Home (rooms done, shown as a calm bar, no percentages of failure); completion moment after Apply (one short animation, room name, time spent, concepts added); gentle streak shown as "Studied 4 days this week" (never "streak broken").

### Acceptance

- FSRS scheduling matches `fsrs` library expectations in tests (due dates for a scripted rating sequence).
- The nudge fires once at the set time when cards are due, and never when none are.
- Quiz never blocks finishing.

### Gate 4 — manual test for the user

1. Keep or skip the cards from a processed room.
2. Use Revise every day for a week (turn the nudge on). Note how long sessions feel.
3. Back-fill one earlier room with From memory mode.
4. Take the quiz on a new room; try skipping it on another.

---

## Phase 5 — Voice, screenshots and extras

**Goal:** the remaining capture types and the extras.

### Tasks

- [ ] **5.1 Voice block.** Hold F9 (global, via the portal; works while the browser is focused) or the panel's mic button. Recording indicator in the panel; on release, transcribe with Whisper (lazy-loaded, unloaded after 60 s idle) and insert an editable Key idea block marked with a small mic icon. Custom vocabulary (`initial_prompt`) seeded with common tool names (nmap, Gobuster, Burp Suite, Wireshark, SSH, DNS, TCP, UDP). Audio deleted after transcription unless "Keep recordings" is on. Fallback per the Phase 0 smoke-test outcome.
- [ ] **5.2 Screenshot block.** Paste from clipboard (Spectacle copies to clipboard) or drop a file; cleaned (see CLAUDE.md, Images) and held in Recon's `media/` folder while the room is in progress, then copied to `Attachments/<room>-<task>-<n>.png` at Apply. Optional "why it matters" line.
- [ ] **5.3 Vision pass (pipeline step 2).** Text and tables read from each screenshot into structured data; shown in a collapsed callout under the image; never merged into the user's tables without review. Fallback model setting (`qwen3-vl:8b`).
- [ ] **5.4 Ask my notes.** Search box on its own screen: embeddings retrieval over room, concept and tool notes (chunked by section), top results shown as cards with "Open in Obsidian"; a question gets a short answer grounded only in retrieved chunks, with links; says "Your notes don't cover this yet" when retrieval is weak.
- [ ] **5.5 Weekly recap.** On the day the user picks, a recap card on Home: rooms finished, time spent, new concepts, hardest cards, open flags; plain and encouraging; no comparison to past weeks unless toggled on; "Save to vault" writes `Recaps/<week>.md` through the normal staging and apply.
- [ ] **5.6 Re-runs.** Library → room → "Add more notes" reopens the room in the panel with its blocks; finishing again merges per SPEC.md (unchanged sections rebuilt, hand-edited sections get suggestions only, resolved flags stay resolved).
- [ ] **5.7 Off-machine backup.** Settings field for a backup folder; daily copy of the vault and `app.db` (SQLite online backup API, not a file copy) keeping 14; quiet note on Home if the folder is missing.
- [ ] **5.8 Polish pass.** Empty states for every screen, keyboard shortcuts overlay (`?`), reduce-motion audit, contrast audit, copy review against the tone rules.

### Acceptance

- F9 hold-to-talk works with the browser focused; release-to-text under 3 seconds for a 15-second clip on the GPU.
- Ask my notes answers only from the vault and links every note it used.
- A re-run on a room with hand edits in Obsidian loses nothing.
- Pasted images are re-encoded with all metadata stripped (tested with an image carrying EXIF and GPS data); oversized images are refused kindly.
- Recordings are deleted after transcription unless "Keep recordings" is on (tested).
- The flag filter runs on voice transcripts and screenshot text too (tested).

### Gate 5 — manual test for the user

1. Do a full new room using voice and screenshots, start to finish.
2. Ask your notes three questions, one of which they shouldn't be able to answer.
3. Reopen a finished room, add notes, finish again; check your Obsidian edits survived.
4. Check the weekly recap and the backup folder.

---

## Release audit (v1)

Before v1 is called done:

- [ ] Full independent audit of the whole codebase against `docs/AUDIT_CHECKLIST.md`, plus a review of `docs/THREAT_MODEL.md` against what was actually built.
- [ ] Dependency and licence audit clean; no known-vulnerable package.
- [ ] Fresh clone install on a clean user account, following only the README.
- [ ] Every gate's manual test re-run.
- [ ] Performance budgets measured and recorded in `docs/audits/release.md`.
- [ ] One week of daily real use with no Critical or High issues open.
- [ ] Tag `v1.0.0`, publish the GitHub Release, close the `Release v1` milestone.

---

## Parked (not in v1)

- HackTheBox rooms and modules (the vault already allows `01 Rooms/HackTheBox/`).
- Terminal command logging from a Kali box.
- Syncing the vault to other devices.
- A packaged release (PKGBUILD or AppImage) beyond the local desktop entry.
