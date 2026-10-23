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
uv sync
uv run pre-commit install
```

`pre-commit install` sets up three hooks: checks on commit, a Conventional Commits check on the message, and a pre-push hook that refuses pushes to `main`.

## Run

Not yet. From Phase 1, `./packaging/recon-launch` starts the app, and an app-menu entry is installed by `scripts/install_desktop.py`.

## Check your machine

```fish
uv run python scripts/check_env.py
```

Reports, in plain English, whether Ollama (install, version, service, GPU), the NVIDIA driver and CUDA, the Plasma Wayland session and desktop portal, the default microphone and PortAudio, Obsidian, and free disk space are ready for Recon. It only reads; it changes nothing and makes no network calls. Exit code 1 means something needs attention. The latest results for the development machine are in [`docs/environment.md`](docs/environment.md).

## Develop

```fish
uv run pytest -m "not ollama"            # fast tests
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
| CachyOS/Arch repos | `gitleaks` | once, by hand |

More sources (Ollama models, fonts, the Whisper model from Hugging Face) are added here before their first download.

## Troubleshooting

- **A commit is refused:** read the hook output. Fix the issue and commit again; never use `--no-verify`.
- **`gitleaks: command not found` on commit:** install it with `sudo pacman -S gitleaks`.
- **`uv lock --check` fails:** run `uv lock` and commit `uv.lock` with your change.
