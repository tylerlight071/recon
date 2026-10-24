# ADR 0001: Application stack

- **Status:** Accepted; partly superseded by [ADR 0003](0003-desktop-integration.md) (the shortcut portal uses jeepney, not QtDBus)
- **Date:** 2026-10-23

## Context

Recon is a single-user desktop app on CachyOS (KDE Plasma 6, Wayland) with an RTX 5070 Ti (Blackwell, sm_120). It needs a polished, animated UI; local LLM calls through Ollama; local speech-to-text; embeddings; spaced repetition; and Markdown output for Obsidian. Everything must run locally. The spec (Look and feel; Models and hardware) already settled the main choices; this ADR records them and the reasons, so later changes start from here.

## Decision

| Concern | Choice |
| --- | --- |
| Language and tooling | Python 3.13, managed by uv (`pyproject.toml`, `uv.lock`) |
| UI | PySide6 6.11 with Qt Quick / QML; own components on `QtQuick.Templates`; no Qt Widgets |
| LLM | `ollama` client with structured outputs; pydantic v2 validation |
| Rendering | jinja2 templates; the model never writes Markdown |
| Embeddings | Ollama `qwen3-embedding:0.6b`, numpy cosine similarity, vectors in SQLite |
| Speech | faster-whisper `large-v3-turbo` on CUDA, started via `packaging/recon-launch` |
| Storage | stdlib `sqlite3`, WAL mode, numbered migrations |
| Desktop integration | XDG GlobalShortcuts portal (jeepney since ADR 0003) and freedesktop Notifications over QtDBus |
| Revision | `fsrs` (py-fsrs) |
| Quality | ruff, mypy strict, pytest, pytest-cov, hypothesis, mutmut 3.x, pre-commit, gitleaks |

## Reasons

- **One language.** The engine, Ollama, Whisper and the UI all live in Python. Tauri with a web front end looks as good but needs a second language and an IPC bridge.
- **QML over Widgets.** QML is GPU-accelerated and built around animation and tokens, which suits the Linear/Raycast-style design; Widgets need heavy styling to look current.
- **QtDBus over helper packages** for the portal and notifications: no extra dependency, and no asyncio loop fighting Qt's event loop.
- **Structured outputs plus templates** make every note's format identical and stop a bad model response from breaking a note.
- **uv** gives a lock file, a managed Python and fast installs; `UV_MALWARE_CHECK` adds a supply-chain check on sync.

## Consequences

- PySide6 is pinned to 6.11.x. 6.12 is out (October 2026) but untested here; moving to it is a separate decision after the Phase 0 QML smoke test.
- CUDA libraries for faster-whisper must be on `LD_LIBRARY_PATH` before Python starts, so the app always launches through `packaging/recon-launch`. Whisper on sm_120 is the riskiest dependency and is smoke-tested in Phase 0 (task 0.7), with whisper.cpp or openai-whisper on PyTorch cu128 as fallbacks.
- `engine/` must never import Qt, so the pipeline is testable headless; `bridge/` stays thin.
