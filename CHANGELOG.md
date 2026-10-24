# Changelog

All notable changes to Recon are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Recon uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Each approved phase gate is released as `v0.<phase>.0`.

## [Unreleased]

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
- `scripts/check_env.py`: read-only environment check for Ollama, GPU, desktop portal, audio, Obsidian and disk space.
