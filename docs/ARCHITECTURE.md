# Architecture

How Recon is put together. Behaviour is defined in [`SPEC.md`](SPEC.md); conventions in [`../CLAUDE.md`](../CLAUDE.md). This file is kept current in the same pull request as any change it describes.

**Built so far:** Phase 0 foundations: `config`, `errors`, `paths`, `logging_setup`, and empty packages for everything else.

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
- The UI thread never blocks: model calls, Whisper, embeddings and file writes run on worker threads and report plain-English progress.
- Only `services/ollama.py` may import networking modules, and it refuses non-loopback hosts. Hugging Face libraries are allowed only in `services/whisper.py`, `subprocess` only in `services/kwin.py`, and `QDesktopServices` only in `services/open_url.py`. Dynamic imports are banned, and QML may not reference remote URLs or network APIs. `tests/test_network_imports.py` checks all of this, with self-tests for each bypass form.
- Dependencies (Ollama client, Whisper, clock, filesystem roots, ID generation) are passed in, so tests can fake them.

## Two windows

One `QQmlApplicationEngine` loads `PanelWindow.qml` (title "Recon Panel": room session and Finish, pinned to the right edge by an opt-in KWin rule) and `MainWindow.qml` (Home, Review, Cards, Revise, Ask, Library, Settings). Both bind to the same bridge objects. Wayland windows can't position themselves, and a pinned window can't resize freely, hence two windows.

## Data flow for a room

1. **Capture.** Blocks are written to `app.db` through a debounced autosave queue (≤ 1 s). The flag filter runs on every save.
2. **Finish.** The room is queued; one room processes at a time.
3. **Pipeline** (`engine/`, worker thread): parse → read screenshots → extract → link → fact-check → render into `runs/<run_id>/staged/`.
4. **Review.** The main window shows staged output, links and flags.
5. **Apply** (`engine/stage.py`): re-hash targets, abort on conflict, back up overwritten files to `backups/<run_id>/`, write atomically, write raw notes once, record the run. **Discard** deletes the staging folder.

## Storage

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

`packaging/recon-launch` is the only supported way to start the app (the desktop entry calls it). It syncs the `voice` extra (a quick no-op when up to date), then puts the venv's `nvidia/*/lib` folders on `LD_LIBRARY_PATH` before Python starts, raises the CUDA JIT cache cap, and runs `uv run --frozen --extra voice --no-sync python -m recon`. See [ADR 0002](adr/0002-voice-runtime.md).

## Tooling and CI

- Pre-commit: ruff, ruff format, mypy, fast tests, gitleaks, Conventional Commits, and a git pre-push hook (`scripts/hooks/pre-push`, installed by `scripts/install-hooks`) that reads every ref being pushed and refuses any update or deletion of `main` (GitHub Free has no rulesets for private repos).
- CI (`.github/workflows/ci.yml`): `uv lock --check`, ruff, mypy, tests with branch coverage, per-package gates (`scripts/coverage_gates.py`), `uv audit`, gitleaks over full history, PR title check.
- Releases (`release.yml`): a `v*.*.*` tag publishes a GitHub Release from that version's `CHANGELOG.md` section.
