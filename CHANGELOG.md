# Changelog

All notable changes to Recon are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Recon uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Each approved phase gate is released as `v0.<phase>.0`.

## [Unreleased]

### Added

- Room session in the panel: room name, "Task n of N", progress ring and time in the header; an optional task title; the task's blocks with a Key idea block always ready and focused; an add bar with all eight block types in a fixed order (Ctrl+1 to Ctrl+7; Screenshot and Voice "Coming soon"); "Skip this task"; and one primary button, "Next task" or "Finish room" (Ctrl+Return), with a small tick. Every keystroke is flag-filtered and autosaved; other writes run in order off the UI thread. Starting a room or "Carry on" opens it here.
- Start a room: the room name and number of tasks, with path and module remembered from the last room behind "More", and From memory shown as "Coming soon". Missing or unusable fields get one plain sentence and the cursor goes to the field. The room is saved off the UI thread, then the panel opens. New `TextField` and `Choice` components.
- Home screen: one accent button ("Start a room" or "Carry on with <room>"), a "Where was I?" card with the room, "Task 4 of 7", how long ago and the last line written, and up to five recent rooms. Times read calmly ("2 days ago"); nothing counts as overdue. A test checks that no main-window screen shows more than one accent button.
- Flag filter (hard rule 2): `THM{…}`, `flag{…}`, `HTB{…}` and lone 32+ character hex strings are stripped from every text field before it reaches the database, including flags still being typed. The panel shows "Flag skipped", and "Not a flag, keep it" is offered for example hashes only. Mutation testing kills 111 of 111 mutants. ADR 0005.
- Database layer: `app.db` in WAL mode, private, with numbered migrations (the Phase 1 tables as STRICT tables with constraints); repositories for rooms, tasks and blocks; an autosave queue that writes every edit within half a second, even during continuous typing; and a daily snapshot through SQLite's online backup API, keeping 14. A `kill -9` test confirms at most half a second of typing is lost.
- Opt-in panel pinning: a one-time question at first launch, then a KWin rule that keeps the panel at the right edge, full height (respecting a visible taskbar) and the width from Settings. A KWin script is the fallback if the rule can't be written, and a calm toast appears if neither works. Unpinning leaves `kwinrulesrc` exactly as it was. ADR 0004.
- The two windows on one shared QML engine: the main window (sidebar with Home and Settings for now) and the side panel ("Recon Panel"), whose width (360–520 px) is remembered in `settings.toml`. Opening a main-window screen from the panel raises the main window with a quick fade; closing the main window leaves the panel open. QML can only load local resources. Adds `tomli-w` to write settings, and crash-safe atomic file writes.
- Component set on QtQuick.Templates: Button (primary, secondary, quiet), IconButton, Card, TextArea with a fading hint, Block, ProgressRing, Toast with Undo, Dialog, SidebarItem, TimerChip, Tooltip with shortcut, plus Recon's own line icons and keyboard focus rings. Every interactive component has an accessible role and name. `python -m recon --gallery` shows them all.
- `Theme.qml` singleton with every design token (colours, accent choice, block edges, type, spacing, radii, panel widths, motion with Reduce motion) and the bundled Inter and JetBrains Mono fonts (OFL). Tests check the tokens against CLAUDE.md, text contrast of at least 4.5:1, and that QML outside the theme uses no literal colours or sizes.

## [0.0.0] - 2026-10-24

Phase 0, foundations: repository, tooling, environment checks and smoke tests proving the stack runs on Tyler's machine. No app to run yet.

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

[Unreleased]: https://github.com/tylerlight071/recon/compare/v0.0.0...HEAD
[0.0.0]: https://github.com/tylerlight071/recon/releases/tag/v0.0.0
