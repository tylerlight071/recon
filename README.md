# Recon

[![CI](https://github.com/tylerlight071/recon/actions/workflows/ci.yml/badge.svg)](https://github.com/tylerlight071/recon/actions/workflows/ci.yml)

Recon is a desktop study companion for TryHackMe. It sits as a slim panel beside the browser, guides you through writing notes one task at a time, then turns those notes into a linked Obsidian vault and short flashcard sessions. Everything runs locally: the only network service it talks to at runtime is Ollama on `127.0.0.1`.

- What it does: [`docs/SPEC.md`](docs/SPEC.md)
- Build order and progress: [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md)
- How it's built: [`CLAUDE.md`](CLAUDE.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Security: [`SECURITY.md`](SECURITY.md), [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)

**Status:** Phase 0 (foundations). There's no app to run yet.

## Requirements

- CachyOS or another Arch-based distro, KDE Plasma 6 on Wayland
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.13 for you)
- [Ollama](https://ollama.com/) with the models in `docs/SPEC.md` (from Phase 2)
- An NVIDIA GPU with a CUDA 12.8+ driver for voice (from Phase 5)
- `gitleaks` for the commit hook: `sudo pacman -S gitleaks`

## Install for development

```fish
git clone https://github.com/tylerlight071/recon.git
cd recon
set -x UV_MALWARE_CHECK 1
uv sync --extra voice        # or plain `uv sync` to skip the ~1.5 GB of CUDA wheels for voice
scripts/install-hooks
```

`scripts/install-hooks` sets up three hooks: pre-commit checks on commit, a Conventional Commits check on the message, and a git pre-push hook that refuses any push that would update or delete `main` (including multi-ref pushes, `--all` and deletions).

## Run

Not yet. From Phase 1, `./packaging/recon-launch` starts the app, and an app-menu entry is installed by `scripts/install_desktop.py`.

## Check your machine

```fish
uv run python scripts/check_env.py
```

Reports, in plain English, whether Ollama (install, version, service, GPU), the NVIDIA driver and CUDA, the Plasma Wayland session and desktop portal, the default microphone and PortAudio, Obsidian, and free disk space are ready for Recon. It only reads and changes nothing; its only network contact is asking the local Ollama for its version. Exit code 1 means something needs attention. The latest results for the development machine are in [`docs/environment.md`](docs/environment.md).

## Smoke tests

Phase 0 scripts that prove each risky dependency works on this machine. Each prints PASS or FAIL with a reason.

```fish
uv run python -m scripts.smoke.structured --model qwen3.5:9b   # add --think to test thinking mode
uv run python -m scripts.smoke.embeddings
uv run python -m scripts.smoke.vision --model qwen3.5:9b
uv run pytest -m ollama                                        # all of them, against the real models
RECON_MODULE=scripts.smoke.whisper packaging/recon-launch      # Whisper on the GPU (add --compute-type int8_float16)
uv run python -m scripts.smoke.qml_window --screenshot tests/screenshots/smoke-qml.png
RECON_MODULE=scripts.smoke.shortcut packaging/recon-launch     # F9 via the portal; needs the app's .desktop file installed
uv run python -m scripts.smoke.kwin_rule apply                 # then: windows, geometry, remove (writes ~/.config/kwinrulesrc)
```

## Develop

```fish
uv run pytest -m "not ollama and not gpu"   # fast tests (what CI and the commit hook run)
uv run pytest --cov --cov-branch         # with coverage
uv run ruff check . ; uv run ruff format . ; uv run mypy
uv run pre-commit run --all-files        # everything the commit hook runs
uv run mutmut run                        # mutation tests on safety-critical modules
```

Work goes through one issue, one branch and one pull request per task. See CLAUDE.md, Git and GitHub.

## Download sources

Recon never contacts tryhackme.com. These are the only places anything is downloaded from, all during setup:

| Source | What | When |
| --- | --- | --- |
| PyPI (`pypi.org`, `files.pythonhosted.org`) | Python packages in `uv.lock` | `uv sync` |
| Astral python-build-standalone (`github.com/astral-sh`) | CPython 3.13 | first `uv sync` |
| GitHub: `pre-commit/pre-commit-hooks`, `compilerla/conventional-pre-commit` | Commit hook code, pinned by commit | `pre-commit install` |
| CachyOS/Arch repos | `gitleaks`, `obsidian` | once, by hand |
| PyPI: `nvidia-cublas-cu12` and other `voice` extra wheels | CUDA libraries for Whisper (~1.5 GB) | `uv sync --extra voice` |
| Hugging Face (`mobiuslabsgmbh/faster-whisper-large-v3-turbo`) | Whisper model (~1.6 GB) into `~/.cache/huggingface` | the Whisper smoke test today; a pinned setup step in Phase 5 (#30) |
| GitHub: `SYSTRAN/faster-whisper` test data, pinned commit, SHA-256 checked | Public-domain 11 s speech clip for the Whisper smoke test, cached in `~/.cache/recon/smoke` | Whisper smoke test |
| GitHub: `rsms/inter` release v4.1 | Inter font (OFL), bundled in `recon/ui/theme/fonts/` | once, committed |
| Ollama registry (`registry.ollama.ai`) | `qwen3.5:9b`, `gemma4:12b`, `qwen3-embedding:0.6b` | `ollama pull`, once (task 0.6) |

More sources (JetBrains Mono) are added here before their first download.

## Troubleshooting

- **A commit is refused:** read the hook output. Fix the issue and commit again; never use `--no-verify`.
- **`gitleaks: command not found` on commit:** install it with `sudo pacman -S gitleaks`.
- **Whisper says `libcublas.so.12 is not found`:** start it through `packaging/recon-launch`, which puts the CUDA libraries on the loader path.
- **The first voice clip after a driver update is slow (~13 s):** the driver is recompiling GPU kernels; later clips are fast.
- **`uv lock --check` fails:** run `uv lock` and commit `uv.lock` with your change.
