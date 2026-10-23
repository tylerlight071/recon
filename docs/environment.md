# Tyler's environment

The machine Recon is built and tested on, as reported by `scripts/check_env.py`, with the fixes agreed in task 0.5. Re-run the script after any system change and update this file when the results change.

**Last checked:** 2026-10-23 · 9 of 10 checks OK

| Area | State |
| --- | --- |
| Ollama | 0.40.8 from pacman (`ollama` + `ollama-cuda`); systemd service `ollama`, running; uses CUDA on the RTX 5070 Ti |
| Ollama models | `/data/models/ollama` (set by `/etc/systemd/system/ollama.service.d/override.conf`), owned by `ollama:ollama`, 655 GB free |
| GPU | NVIDIA RTX 5070 Ti, 16 GB; driver 615.78.08; CUDA 13.4 driver API; compute capability 12.0 (Blackwell) |
| Desktop | KDE Plasma 6.8.1 on Wayland; xdg-desktop-portal 1.22.1 with the host Registry and GlobalShortcuts portals |
| Audio | PortAudio installed. **Default input not set yet** (see below) |
| Models pulled | See below (15 GB in `/data/models/ollama`) |
| Obsidian | 1.14.4 from pacman (Arch `extra`); `obsidian://` handler registered |
| Disk | About 1 TB free in home |

## Models (task 0.6, pulled 2026-10-24)

| Model | Role | Ollama ID | Size | Details from `ollama show` |
| --- | --- | --- | --- | --- |
| `qwen3.5:9b` | Default text and vision | `56671c2ab938` | 6.6 GB | 9.0B, Q4_K_M, 262K context; completion, vision, tools, thinking |
| `gemma4:12b` | Bake-off candidate (Phase 2) | `6114515d63c1` | 8.0 GB | 11.9B, Q4_K_M, 262K context; completion, vision, audio, tools, thinking |
| `qwen3-embedding:0.6b` | Embeddings | `ac6da0dfba84` | 639 MB | 596M, Q8_0, 32K context, 1024-dimension vectors |

Both text models support thinking. The 0.7 smoke test checks how that interacts with structured output.

## Fixes made in task 0.5

| Problem | Cause | Fix (run by Tyler) |
| --- | --- | --- |
| Ollama service failed at boot | The override points `OLLAMA_MODELS` at `/data/models/ollama`, which didn't exist; `/data/models` is owned by `tyler` (755), so the `ollama` user couldn't create it | `sudo install -d -o ollama -g ollama -m 755 /data/models/ollama`, then `sudo systemctl restart ollama`. No models existed before, so nothing needed moving |
| Obsidian missing | Not installed | `sudo pacman -S obsidian`, then opened once to register `obsidian://` |

## Deferred

- **Default microphone** ([#10](https://github.com/tylerlight071/recon/issues/10)): the default input is the USB interface's Line input. The mic wasn't connected on 2026-10-23, so choosing the right input waits until before task 5.1 (Voice block). Nothing in Phases 1–4 needs it.
