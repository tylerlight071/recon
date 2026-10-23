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
| Obsidian | 1.14.4 from pacman (Arch `extra`); `obsidian://` handler registered |
| Disk | About 1 TB free in home |

## Fixes made in task 0.5

| Problem | Cause | Fix (run by Tyler) |
| --- | --- | --- |
| Ollama service failed at boot | The override points `OLLAMA_MODELS` at `/data/models/ollama`, which didn't exist; `/data/models` is owned by `tyler` (755), so the `ollama` user couldn't create it | `sudo install -d -o ollama -g ollama -m 755 /data/models/ollama`, then `sudo systemctl restart ollama`. No models existed before, so nothing needed moving |
| Obsidian missing | Not installed | `sudo pacman -S obsidian`, then opened once to register `obsidian://` |

## Deferred

- **Default microphone** ([#10](https://github.com/tylerlight071/recon/issues/10)): the default input is the USB interface's Line input. The mic wasn't connected on 2026-10-23, so choosing the right input waits until before task 5.1 (Voice block). Nothing in Phases 1–4 needs it.
