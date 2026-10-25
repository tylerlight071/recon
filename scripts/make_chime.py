"""Write Recon's focus chime (`recon/ui/sounds/chime.wav`): two soft, fading notes.

Generated rather than downloaded, so there's no licence or download source to
track. Run once; the WAV is committed. Deterministic: same bytes every time.
"""

import math
import struct
import sys
import wave
from pathlib import Path

RATE = 22050
NOTES = ((659.25, 0.0), (880.0, 0.18))  # E5 then A5, the second a beat later
LENGTH_S = 1.4
PEAK = 0.22
"""Quiet on purpose: a nudge, not an alarm."""


def sample(t: float) -> float:
    """The chime's level at `t` seconds: soft sines with a gentle attack and long fade."""
    value = 0.0
    for frequency, start in NOTES:
        if t < start:
            continue
        local = t - start
        attack = min(1.0, local / 0.01)
        value += attack * math.exp(-3.2 * local) * math.sin(2 * math.pi * frequency * local)
    return PEAK * value / len(NOTES)


def main(out: Path) -> None:
    """Write the WAV to `out`."""
    frames = b"".join(
        struct.pack("<h", round(32767 * sample(i / RATE))) for i in range(int(LENGTH_S * RATE))
    )
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(frames)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("recon/ui/sounds/chime.wav"))
