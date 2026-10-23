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
- `scripts/check_env.py`: read-only environment check for Ollama, GPU, desktop portal, audio, Obsidian and disk space.
