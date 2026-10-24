# CLAUDE.md — Recon

Recon is a desktop study companion for TryHackMe. It sits as a slim panel beside the browser, guides Tyler through writing notes one task at a time, then turns those notes into a linked Obsidian vault and short flashcard sessions. Everything runs locally. It is built for an ADHD brain: low friction, nothing to remember, nothing lost.

- **What to build:** `docs/SPEC.md` (the design spec — the source of truth for behaviour).
- **In what order:** `docs/BUILD_PLAN.md` (phases, tasks, acceptance checks).
- **This file:** how to build it — rules, stack, structure, conventions.

If this file, the build plan and the spec disagree, the spec wins on behaviour, this file wins on engineering conventions, and you ask Tyler before resolving anything that changes what he sees.

---

## Working with Tyler

- Tyler is the only user and the product owner. He prefers direct, technically precise answers and will push back on errors.
- **Research, don't guess.** Check library docs, versions and APIs before relying on them. Say when something is unverified.
- **Show whole files, not snippets,** whenever you show him code to read or paste.
- His shell is **Fish**. Any command you give him to run must be Fish-compatible (no `export VAR=…`, no `$(…)` — use `set -x VAR …` and `(…)`).
- **Stop at every phase gate** in the build plan: summarise what was built, give him the manual test script for that phase, and wait for his go-ahead.
- **Ask before:** installing system packages (`pacman`, `paru`, anything with `sudo`), changing KDE or system config, touching anything outside the repo, the vault and Recon's data folder, or deleting files.
- Work through GitHub exactly as described in **Git and GitHub** below: one issue, branch and pull request per task; nothing goes straight onto `main`.

## Environment

| Item | Value |
| --- | --- |
| OS | CachyOS (Arch-based), KDE Plasma 6, **Wayland** |
| Screen | One monitor, 2560×1440 |
| GPU | NVIDIA RTX 5070 Ti, 16 GB VRAM (**Blackwell, sm_120**) |
| CPU | Ryzen 7 9800X3D |
| Shell | Fish |
| LLM server | Ollama on `http://127.0.0.1:11434` (install method unknown — Phase 0 checks) |
| Rooms | Done on CachyOS in the browser, using TryHackMe's in-browser AttackBox |

**Blackwell gotchas:** anything CUDA must be built for CUDA ≥ 12.8. PyTorch needs `--index-url https://download.pytorch.org/whl/cu128`. CTranslate2 (faster-whisper) needs 4.5 or newer. Never assume a GPU library works on sm_120 — smoke-test it.

**Other platform gotchas (checked against upstream docs where they exist; each has a Phase 0 check that proves it on Tyler's machine):**

- **faster-whisper on GPU** needs cuBLAS for CUDA 12 (`nvidia-cublas-cu12`, in the `voice` extra) visible through `LD_LIBRARY_PATH` **before Python starts**. cuDNN isn't needed with CTranslate2 ≥ 4.6.3; verified in Phase 0 (`docs/adr/0002-voice-runtime.md`). So the app is launched through `packaging/recon-launch` (a small shell script that sets it, then runs `uv run python -m recon`), and the desktop entry calls that script.
- **sounddevice** doesn't bundle PortAudio on Linux; it needs the system `portaudio` package. Ask Tyler before installing it.
- **Global shortcuts portal** identifies unsandboxed apps by app ID. Recon uses one reverse-DNS app ID everywhere (decided in Phase 0, e.g. `io.github.<github-user>.Recon`): the `.desktop` file name, `QGuiApplication.setDesktopFileName`, and a host `Registry.Register` call made as the **first** portal call at start-up (needed when launched from a terminal).
- **Obsidian only opens vaults it already knows.** `obsidian://open` fails with "Vault not found" for a folder that hasn't been opened as a vault. After creating the vault, Recon asks Tyler to open it once in Obsidian ("Open folder as vault") and only shows "Open in Obsidian" buttons after he confirms.
- **Wayland windows can't position themselves**, and a KWin rule that pins a window also stops it resizing freely. So the panel and the full view are **two windows**: the panel (pinned by the KWin rule) and the main window (a normal window). See Architecture rules.

## Stack

| Concern | Choice | Notes |
| --- | --- | --- |
| Language | Python 3.13 | Managed by `uv` (`.python-version`). Don't use the system Python. PySide6 6.11 supports ≤ 3.14. |
| Packaging/deps | `uv` + `pyproject.toml` + `uv.lock` | `uv add`, `uv run`, `uv sync` |
| UI | PySide6 6.11.x, **Qt Quick / QML** | Custom components built on `QtQuick.Templates`. No Qt Widgets in the UI. |
| LLM | `ollama` Python client | Structured outputs only (see Model rules) |
| Validation | `pydantic` v2 | Every model response and every config file |
| Templates | `jinja2` | Renders every Markdown file written to the vault |
| Embeddings | Ollama `qwen3-embedding:0.6b` + `numpy` cosine similarity | Vectors stored in SQLite as blobs |
| Speech | `faster-whisper`, model `large-v3-turbo` | Lazy-loaded; unloaded after 60 s idle |
| Audio capture | `sounddevice` | 16 kHz mono |
| Spaced repetition | `fsrs` (py-fsrs) | |
| Global hotkey | XDG GlobalShortcuts portal via **jeepney** (blocking, on a worker thread) | Hold-to-talk via the `Activated`/`Deactivated` signals. QtDBus can't marshal `BindShortcuts`' `a(sa{sv})` from Python (ADR 0003). Call the portal directly rather than adding `global-shortcut-portal` (asyncio, which fights Qt's event loop) |
| Notifications | freedesktop Notifications via **QtDBus** | Actions open the right screen; no extra dependency |
| Storage | SQLite (stdlib `sqlite3`), WAL mode | Migrations in `recon/db/migrations/` |
| Images | `Pillow` | |
| Tests | `pytest`, `pytest-qt`, `pytest-cov`, `hypothesis`, `mutmut` (3.x) | See Testing |
| Lint/format/types | `ruff` (lint + format), `mypy --strict` on all of `recon/` | See Engineering standards |
| Supply chain | `uv audit` (preview) or `pip-audit` on an exported lock; `UV_MALWARE_CHECK=1` on sync; `gitleaks` | See Security and privacy |
| Hooks/CI | `pre-commit`; GitHub Actions | CI runs everything except GPU and Ollama tests |

Add a dependency only when a task needs it, and say why in the pull request description.

## Repository layout

```text
recon/
├── CLAUDE.md
├── README.md
├── CHANGELOG.md
├── SECURITY.md
├── .editorconfig
├── .gitattributes
├── .pre-commit-config.yaml
├── .github/
│   ├── workflows/ci.yml     # lint, types, tests, coverage, audits on every PR and push
│   ├── workflows/release.yml # GitHub Release from CHANGELOG on a version tag
│   ├── dependabot.yml
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/      # task.yml, bug.yml, audit-finding.yml
├── docs/
│   ├── SPEC.md
│   ├── BUILD_PLAN.md
│   ├── ARCHITECTURE.md
│   ├── THREAT_MODEL.md
│   ├── AUDIT_CHECKLIST.md
│   ├── adr/                 # one file per significant decision
│   └── audits/              # phase-N.md audit reports
├── pyproject.toml
├── recon/
│   ├── __main__.py          # `uv run python -m recon` launches the app; `--nudge` runs the nudge check
│   ├── app.py               # QGuiApplication + QQmlApplicationEngine setup
│   ├── config.py            # Settings model (pydantic), paths, defaults
│   ├── errors.py            # ReconError hierarchy
│   ├── paths.py             # XDG paths: data, config, cache; vault path
│   ├── db/                  # SQLite access, migrations, repositories
│   ├── engine/              # PURE PYTHON. No Qt imports. Fully testable headless.
│   │   ├── parse.py
│   │   ├── vision.py
│   │   ├── extract.py
│   │   ├── link.py
│   │   ├── factcheck/       # deterministic checks + model review
│   │   ├── render.py
│   │   ├── stage.py         # staging, apply, discard, backups
│   │   ├── flags_filter.py  # flag detection and removal
│   │   ├── schemas.py       # pydantic models for every model call
│   │   ├── prompts/         # one .md prompt file per model call
│   │   └── templates/       # jinja2 templates for vault notes
│   ├── services/            # Ollama client wrapper, Whisper, audio, portal, notifications, KWin rule
│   ├── revision/            # FSRS scheduling, card store, sessions
│   ├── bridge/              # QObject controllers + models exposed to QML (thin; call engine/services)
│   └── ui/
│       ├── PanelWindow.qml
│       ├── MainWindow.qml
│       ├── theme/           # Theme.qml singleton: tokens below
│       ├── components/      # Button, Card, Block, ProgressRing, Toast, Hint, …
│       └── screens/         # Home, RoomSession, Finish, Review, Cards, Revise, Ask, Library, Settings
├── tests/
│   ├── fixtures/rooms/      # ORIGINAL sample rooms written for testing — never TryHackMe text
│   ├── fixtures/responses/  # recorded Ollama responses for GPU-free pipeline tests
│   ├── golden/              # expected rendered notes
│   ├── engine/
│   └── bridge/
└── packaging/
    ├── recon-launch         # sets LD_LIBRARY_PATH for CUDA libs, then starts the app
    ├── <app-id>.desktop
    ├── icons/
    └── systemd/             # recon-nudge.service + recon-nudge.timer (user units)
```

### Architecture rules

- **`engine/` never imports Qt.** It takes data in, returns data out, and is driven by tests. The bridge calls it on a worker thread (`QThreadPool`) and reports progress through signals.
- **`bridge/` is thin.** No business logic in controllers or QML.
- **QML never does I/O.** It binds to properties and calls slots.
- **The UI thread never blocks.** Model calls, Whisper, embedding and file writes all run off the UI thread.
- **Long jobs report progress** as plain-English steps ("Linking 6 concepts to your notes"), never a bare spinner.
- **Two windows, one app.** `PanelWindow.qml` (room session and Finish; window title "Recon Panel", which the KWin rule matches together with the app ID) and `MainWindow.qml` (Home, Review, Cards, Revise, Ask, Library, Settings). Both share one `QQmlApplicationEngine` and the same bridge objects, so state is always in sync. Opening a full-view screen from the panel shows or raises the main window; the panel stays where it is.

## Hard rules (never break these)

1. **Never contact tryhackme.com.** No scraping, fetching, browser automation or API calls to it, ever; TryHackMe's terms prohibit automated extraction. At runtime the app's only network target is local Ollama on 127.0.0.1. One-off downloads during setup (Python packages, fonts, `ollama pull`, the Whisper model from Hugging Face) are fine, but each new download source is listed in the README and Tyler is told before the first download.
2. **Flags are never stored.** Anything typed, pasted, transcribed or read from a screenshot that matches a flag pattern (`THM{…}`, `flag{…}`, `HTB{…}`, or a lone 32+ character hex string) is stripped before data reaches the database, the vault, cards or backups, and the UI shows a small "Flag skipped" notice. Because rooms on hashing legitimately show example hashes, the notice has a "Not a flag, keep it" button that restores that one string. `engine/flags_filter.py` owns this; it has its own tests.
3. **Nothing reaches the vault without Apply.** All output is rendered to a staging folder first. Only `stage.apply()` writes into the vault.
4. **Never change `00 Raw notes/` after writing.** Never change Tyler's own text: fact-check results are flags beside his text, never edits.
5. **Generated content is always labelled.** Generated definitions go in a `> [!info] Generated definition` callout; suggested answers are marked generated. The model never pads a note with content Tyler didn't write.
6. **Back up before overwriting.** Apply copies every file it will overwrite to `backups/<run_id>/` first. Keep the last 20 runs.
7. **Autosave every keystroke** in a room session (debounced ≤ 1 s). A crash may lose at most one second.
8. **Generated vault sections live between markers** `%% recon:start <section> %%` and `%% recon:end %%`. Only edit inside markers; never touch anything outside them.
9. **Stop on conflict.** If a vault file changed between staging and Apply (hash mismatch), abort the apply and offer to re-run. Never overwrite.
10. **One room processes at a time.** Further finishes queue.

## Model rules

- Every call uses Ollama **structured outputs**: a pydantic schema passed as `format=Model.model_json_schema()`, with the schema also described in the prompt, and `temperature=0`.
- Validate every response with pydantic. On failure, retry once with the validation error appended; then fail the step cleanly and show it on the review screen.
- **The model never writes Markdown for the vault.** It returns data; `jinja2` templates render it.
- **Anything checkable in code is checked in code:** number base conversions, CIDR maths, port/protocol facts (from `engine/factcheck/data/ports.csv`), and known command flags. Code results override the model.
- Fact-check: the model returns `looks_right | likely_wrong | unsure` per claim. Only `likely_wrong` becomes a flag; drop `unsure`.
- Prompts live in `engine/prompts/*.md`, one file per call, with the schema name in the filename.
- Model names come from settings, never hardcoded. Defaults: `qwen3.5:9b` (text and vision), `qwen3-embedding:0.6b`, Whisper `large-v3-turbo`. Phase 2 runs a bake-off against `gemma4:12b`.
- Log the raw response of every call to `runs/<run_id>/` for debugging.

## Paths

| What | Where |
| --- | --- |
| Vault (owned by Recon) | `~/Cyber Vault/` (configurable) |
| App data | `$XDG_DATA_HOME/recon/` (→ `~/.local/share/recon/`): `app.db`, `index.db`, `audio/`, `media/` (cleaned screenshots for rooms in progress), `runs/`, `backups/` |
| Config | `$XDG_CONFIG_HOME/recon/settings.toml` |
| Logs | `~/.local/share/recon/app.log` |

Vault layout: `Home.md`, `00 Raw notes/`, `01 Rooms/<Platform>/<Path>/`, `02 Concepts/`, `03 Tools/`, `Attachments/`, `Recaps/`, `Bases/`. See SPEC.md for note types and properties.

## Design system

Restrained dark UI in the style of Linear and Raycast: near-black canvas, surfaces separated by small lightness steps and hairline borders, greyscale plus one accent, crisp type, quick quiet motion. **No gimmicks, no gradients-as-decoration, no emoji in UI.**

Define these in `ui/theme/Theme.qml` as a singleton. Components read tokens only — no literal colours or sizes in screens.

| Token | Value |
| --- | --- |
| `bg` | `#0b0c0e` |
| `surface` | `#111215` |
| `raised` | `#16181c` |
| `overlay` | `#1c1e23` |
| `border` | `#23252a` (1 px hairline) |
| `textPrimary` | `#ececef` |
| `textSecondary` | `#9a9ba3` |
| `textTertiary` | `#84868f` (hints and quiet labels; ≥ 4.6:1 on every surface — don't go darker) |
| `accent` (default: muted violet) | `#7c74d9`; hover `#8d86e3`; alternatives in Settings: cyan `#4fb3c9` (hover `#66bdd0`), green `#5fb47a` (hover `#74be8b`); the cyan and green hovers are a 13% white mix, like violet's |
| `onAccent` (QML: `textOnAccent`, since QML reads `on…` names as signal handlers) | `#0b0c0e` — text on accent-filled buttons. White on these accents fails contrast (3.9:1 on violet, 2.4:1 on cyan); near-black passes on all three (≥ 5:1) |
| `success` | `#5fb47a` |
| `warning` (flags) | `#d9a441` |
| Block edges | Key idea = accent, Command = `#4fb3c9`, Table = `#8a8fa3`, Screenshot = `#b37fd1`, Question = `#d9a441`, Confused by = `#d98a5f`, Room question = `#5fb47a`, Voice = `#7c9fd9` (all at 70% opacity, `blockEdgeOpacity`) |
| Font UI | Inter, 13 / 14 / 15 px, weights 400 / 500 / 600 |
| Font mono | JetBrains Mono 13 px (commands, code) |
| Spacing | 4 px grid: 4, 8, 12, 16, 20, 24, 32, 48 |
| Radius | 6 small, 8 cards, 12 dialogs |
| Motion | 150 ms (fast), 200 ms (base), ease-out; `Theme.reduceMotion` makes all durations 0 |

Bundle Inter and JetBrains Mono (both OFL) in `ui/theme/fonts/`. **Never use red for anything Tyler did.** All text, hints included, has contrast ≥ 4.5:1 against the surface it sits on; a test computes this from `Theme.qml`.

## ADHD design rules (apply to every screen)

1. Exactly one primary (accent) button per screen; everything else is quieter.
2. Show only what's needed now: one task at a time; stats and settings tucked away.
3. Never a blank page: every task opens with a Key idea block already present, hint showing.
4. Nothing can be lost: autosave; Undo everywhere; deletions get a 10 s Undo toast.
5. Same thing, same place: buttons and shortcuts never move between screens or rooms.
6. Remember for him: "Where was I?" card on launch with the room, task and last line.
7. Small wins: tick per task, progress ring, a calm completion moment per room.
8. No shame: no overdue counts, no broken-streak messages, nothing red.
9. Short sessions: revision capped at 10 minutes or 20 cards by default; "Stop here" always visible.
10. Time made visible, never as a threat: timer and time-on-task shown quietly; no countdown pressure.
11. Calm by default: no sounds or pop-ups unless enabled.

**UI copy:** British English, plain words, short sentences, kind and specific. Say what happened and what to do next. Never blame ("You forgot…"). Example: "Couldn't reach Ollama. Is it running? Recon will try again when you press Retry."

## Engineering standards

Write it as a careful senior engineer would for software other people depend on. These are gates, not aspirations: work that doesn't meet them isn't done.

**Code**

- `mypy --strict` passes on all of `recon/`, including `bridge/`. No `Any`, `cast` or `# type: ignore` without a one-line comment saying why.
- `ruff` with a broad rule set: at least `E, F, W, I, N, UP, B, S, A, C4, SIM, PL, PT, RET, ARG, PTH, TRY, RUF, ANN, D` (Google-style docstrings on every public module, class and function). Per-file ignores only for tests, each with a reason.
- Small, single-purpose functions; no function over ~50 lines or 3 levels of nesting without a reason in a comment.
- Dependencies injected, not imported globally: the Ollama client, Whisper, clock, filesystem roots and random IDs are passed in, so every one can be faked in tests.
- Pydantic models at every boundary: settings, database rows to engine, engine to bridge, model calls.
- No dead code, no commented-out code, no `TODO` without a GitHub issue number next to it (`# TODO(#42): …`).

**Errors**

- One exception hierarchy rooted at `ReconError` in `recon/errors.py`, with subclasses per area (`OllamaUnavailable`, `ApplyConflict`, `VaultMissing`, …).
- No bare `except`, no `except Exception` except at thread and process boundaries, where the error is logged and turned into a user-facing message.
- Every error the user can see maps to plain copy (see UI copy) and a next step. Never show a stack trace in the UI.

**Data safety**

- Every file write is atomic: write to a temp file in the same folder, `fsync`, then `os.replace`.
- SQLite: one writer connection, WAL mode, `foreign_keys=ON`, parameterised queries only. Every schema change is a numbered migration with a test that runs it on a copy of the previous schema with data in it.
- Background jobs can be cancelled, and cancelling leaves nothing half-written.

**Logging**

- stdlib `logging`, one line per event, rotated at 5 MB with 5 files kept.
- **Never log note content, prompts, transcripts or model responses** to `app.log`. Log IDs, counts, durations and error types only. Content for debugging goes only to `runs/<run_id>/` (private permissions, deleted after 30 days).

**Performance budgets** (measured in tests or at gates)

- Launch to Home: under 2 s. Keystroke to saved: under 1 s. Switching tasks: under 100 ms. Panel animations hold 60 fps on Tyler's machine. Idle memory under 300 MB with no models loaded.

**Accessibility**

- Every control reachable and usable by keyboard, with a visible focus ring. Every interactive QML item sets `Accessible.name` and `Accessible.role`. Contrast and reduce-motion rules as in the design system.

**Documentation** (kept current in the same pull request as the change)

- `README.md` (what it is, install, run, troubleshoot), `docs/ARCHITECTURE.md` (modules and data flow), `docs/THREAT_MODEL.md`, `docs/adr/NNNN-title.md` for every significant decision, `CHANGELOG.md`.

## Security and privacy

Tyler's notes are private. Treat everything as if a stranger will audit it.

- **Local only.** No telemetry, analytics, crash reporting or update checks. All network access goes through `services/ollama.py`, which refuses any host that isn't loopback. A test fails if any other module imports `socket`, `http`, `urllib`, `requests` or `httpx`.
- **Untrusted input** is: anything Tyler pastes (it may contain text from anywhere), screenshots, and **every model response**. A model's output is data to validate, never trusted text.
- **Prompt injection.** Pasted content goes into prompts between clear delimiters and is described to the model as data, not instructions. That's not relied on: the real defence is the schema, length limits, sanitising and the review screen.
- **Sanitise before rendering** anything model-derived into Markdown: neutralise `![[` and `[[` (only the engine creates links, from the index), raw HTML tags, `%%` marker sequences, frontmatter fences, and any URL that isn't `http(s)`. Tyler's own text is escaped where needed so it can't break the note's structure. Golden-file and property tests cover this.
- **Path safety.** Note and attachment file names built from room or concept names are sanitised (no path separators, `..`, control characters or reserved names; length-limited), and every resolved write path is checked to be inside the vault or data folder. Tested with hostile names.
- **Permissions.** Data and config folders `0700`, files `0600`, set on creation and checked at launch. The vault is created `0700`.
- **Images.** Pasted images are decoded with Pillow's decompression-bomb limit, re-encoded to PNG and stripped of metadata (EXIF, GPS) before being stored.
- **Subprocesses.** Only where unavoidable (e.g. reloading KWin), always with an argument list, never `shell=True`, from an allowlist of binaries resolved by full path.
- **Deletion.** SQLite `secure_delete=ON`. Deleted audio, staging folders and expired runs are removed promptly.
- **Supply chain.** All dependencies pinned in `uv.lock`; `UV_MALWARE_CHECK=1` on every sync; dependency audit (`uv audit`, or `pip-audit` against `uv export` if that's still in preview) at every gate with no known-vulnerable package shipped; licences checked as compatible.
- **Secrets and personal data in git.** `gitleaks` in pre-commit and CI. Never commit Tyler's real notes, vault, database or recordings; only invented fixtures.

## Testing

- **Coverage (branch):** at least 90% for `engine/`, `db/`, `revision/` and `services/`; at least 80% overall including `bridge/`. Enforced in CI; coverage never goes down without a written reason.
- **Unit tests** for every module, with the Ollama client, Whisper, clock and filesystem faked.
- **Recorded model responses.** Pipeline tests run against recorded Ollama responses (fixtures captured from real runs), so the whole pipeline is tested without a GPU. Separate `@pytest.mark.ollama` tests run against the real models locally.
- **Property tests (`hypothesis`)** for the flag filter, marker handling, sanitising, file-name building, table parsing, number conversions and CIDR maths.
- **Mutation testing (`mutmut` 3.x)** on the safety-critical modules — `flags_filter`, `stage`, sanitising and `factcheck` — with at least 85% of mutants killed. Surviving mutants are either killed with a new test or explained in the audit.
- **Golden-file tests** for every rendered note type.
- **Hard-rule tests:** every hard rule has at least one test that fails if the rule is broken.
- **Crash tests:** kill the process mid-save and mid-Apply; nothing is corrupted and at most one second of typing is lost.
- **Migration tests** for every schema version.
- **UI:** `pytest-qt` for bridge controllers (CI runs Qt with `QT_QPA_PLATFORM=offscreen`); screenshots of each screen via `QQuickWindow.grabWindow()` into `tests/screenshots/` at gates.
- **Fixture rooms** in `tests/fixtures/rooms/` are written from scratch. Never copy TryHackMe content into the repo.

**Before every commit** (enforced by `pre-commit`): ruff check, ruff format check, mypy strict, fast tests, gitleaks; the `commit-msg` hook checks Conventional Commits. **CI on every PR and push:** all of that plus `uv lock --check`, coverage gates, dependency audit and the offscreen UI tests (see Git and GitHub).

## Git and GitHub

Private repo `recon` on Tyler's GitHub account, run the way a well-kept professional repository is run.

**Workflow (GitHub Flow)**

- `main` is always green and runnable. Nothing is committed to it directly, and it is never force-pushed or rewritten.
- **One task = one issue = one branch = one pull request.** Issues are created from BUILD_PLAN.md at the start of each phase; each phase is a **milestone**.
- Branch names: `<type>/<task-id>-<short-slug>`, e.g. `feat/1.9-room-session`, `fix/2.4-apply-conflict`.
- PR title in Conventional Commits form (it becomes the squash commit): `feat(capture): room session panel (#12)`. The body follows the PR template: what and why, linked issue (`Closes #12`), how it was tested, screenshots for UI changes, checklist (tests added, coverage held, docs and CHANGELOG updated, no new dependency without a reason).
- Before opening a PR, self-review the full diff (`gh pr diff`) as if reviewing someone else's work.
- Merge only when CI is green, by **squash merge**; the branch is deleted after merging. Claude Code may merge task PRs itself once CI passes; anything that changes what Tyler sees beyond the task, and every gate, waits for him.

**Commits**

- Conventional Commits on every commit (`feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`, `build`, `perf`), with a scope where it helps. Enforced by a `commit-msg` hook (`conventional-pre-commit`).
- Small, focused commits that each pass the pre-commit hook. Never `--no-verify`.
- Commits are signed with Tyler's SSH key if he sets up commit signing (ask once in Phase 0; don't change his git config without asking).

**Versioning and releases**

- Semantic Versioning. Each phase gate that Tyler approves is tagged `v0.<phase>.0` (e.g. `v0.1.0` after Gate 1) with a GitHub Release whose notes come from `CHANGELOG.md`. Fixes between gates are `v0.<phase>.<patch>`. `v1.0.0` follows the release audit.
- `CHANGELOG.md` follows Keep a Changelog: an `Unreleased` section updated in every PR, moved under the version heading at release.

**Labels**

- Type: `type:feature`, `type:bug`, `type:refactor`, `type:docs`, `type:test`, `type:chore`. Area: `area:capture`, `area:engine`, `area:vault`, `area:revision`, `area:ui`, `area:security`, `area:infra`. Severity (audit findings and bugs): `sev:critical`, `sev:high`, `sev:medium`, `sev:low`.

**Repository files and settings**

- `README.md` (with CI badge), `CHANGELOG.md`, `SECURITY.md` (supported versions, how security issues are handled, link to `docs/THREAT_MODEL.md`), `.editorconfig`, `.gitattributes` (`* text=auto eol=lf`, binaries marked), `.github/` templates as in the layout. No `LICENSE` file; the repo is private.
- `dependabot.yml`: `uv` and `github-actions` ecosystems, weekly, grouped minor and patch updates, with a `cooldown`. Dependabot's uv support always raises lower bounds in `pyproject.toml` ([pitfall](https://dev.classmethod.jp/articles/dependabot-uv-versioning-pitfall/)), so CI runs `uv lock --check` and Dependabot PRs are reviewed, never auto-merged.
- Settings: squash merge only, auto-delete head branches, Dependabot alerts and security updates on, dependency graph on, wiki and projects off, Actions default token read-only.
- **Branch protection:** GitHub only offers rulesets on private repos with GitHub Pro or above ([docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)). Phase 0 checks Tyler's plan (`gh api user --jq .plan.name`). With Pro: a ruleset on `main` requiring a PR, passing CI, linear history and blocking force-pushes and deletion. Without Pro: the same rules enforced locally by a `pre-push` hook that refuses pushes to `main`, plus the workflow above. Say which applies at Gate 0.
- **Secret scanning:** GitHub's push protection isn't available on free private repos, so `gitleaks` runs in the pre-commit hook and in CI on every push.

**CI hygiene**

- Workflows declare least-privilege `permissions` (`contents: read` unless more is needed), pin every action by full commit SHA with the version in a comment, set `timeout-minutes`, use `concurrency` to cancel superseded runs, and cache uv.
- CI must pass on every PR: `uv lock --check`, ruff, ruff format check, mypy strict, tests with coverage gates, offscreen UI tests, dependency audit, gitleaks.

## Audits

- **At every phase gate**, before handing over to Tyler, run an independent audit using a fresh subagent that didn't write the code. It reviews the phase's changes against `docs/AUDIT_CHECKLIST.md` (correctness, hard rules, security and privacy, error handling, tests and coverage, performance budgets, accessibility, ADHD rules, copy, docs) and writes findings to `docs/audits/phase-N.md`, each with severity (Critical / High / Medium / Low), location and fix.
- **Critical, High and Medium findings are fixed before the gate.** Every finding becomes a GitHub issue (`audit-finding` template, severity label, milestone); Low findings are fixed or left open with a reason in the issue.
- The gate summary to Tyler includes the audit result, coverage and mutation scores, and the dependency audit result.
- **Release audit** before calling v1 done: full threat-model review, a fresh clone install on a clean user account, every gate's manual tests re-run, and a week of daily use with no Critical or High issues open.

## Commands

```fish
set -x UV_MALWARE_CHECK 1                # once per shell, or add to Fish config with Tyler's OK
uv sync                                  # install deps
./packaging/recon-launch                 # run the app as Tyler will (sets CUDA library paths)
uv run python -m recon                   # quick dev run (voice won't use the GPU without the launcher)
uv run python -m recon --nudge           # run the daily nudge check once
uv run pytest -m "not ollama and not gpu" # fast tests (CI and pre-commit run these)
uv run pytest                            # all tests (needs Ollama for -m ollama)
uv run pytest --cov --cov-branch         # with coverage
uv run mutmut run                        # mutation tests on safety-critical modules
uv run ruff check . ; uv run ruff format . ; uv run mypy --strict recon
uv run pre-commit run --all-files        # everything the commit hook runs
```

## When unsure

Check SPEC.md first. If it doesn't cover the case, pick the option that keeps Tyler's data safest and his screen calmest, record the decision in the pull request (and an ADR if it's significant), and mention it at the next phase gate.
