"""Local, procedural soundtrack sketcher. Run from the workspace root."""
from __future__ import annotations

from array import array
import math
from pathlib import Path
import random
import struct
import wave

SR = 22050
TABLE_SIZE = 4096
SINE = [math.sin(2 * math.pi * i / TABLE_SIZE) for i in range(TABLE_SIZE)]

SPECS = {
    "zhongqiu": {"seconds": 92, "bpm": 74, "key": 57, "meter": 4,
                 "pulse": "wood", "mode": "warm",
                 "progress": [(57, 60, 64, 69), (53, 57, 60, 64), (60, 64, 67, 71), (55, 59, 62, 67)],
                 "sections": [0, 10, 27, 51, 69, 82, 92]},
    "guoqing": {"seconds": 90, "bpm": 78, "key": 48, "meter": 4,
                "pulse": "brush", "mode": "restrained",
                "progress": [(48, 55, 60, 62), (53, 57, 60, 64), (46, 53, 58, 60), (43, 50, 55, 59)],
                "sections": [0, 13, 31, 52, 70, 84, 90]},
    "gpt_music_film": {"seconds": 105, "bpm": 96, "key": 60, "meter": 4,
                       "pulse": "key", "mode": "layered",
                       "progress": [(60, 64, 67, 74), (57, 60, 64, 69), (62, 65, 69, 72), (55, 59, 62, 67)],
                       "sections": [0, 14, 28, 42, 57, 70, 83, 105]},
}


def compose(name: str, output: str | Path, duration: float | None = None) -> Path:
    cfg = SPECS[name]
    duration = float(duration or cfg["seconds"])
    n = int(SR * duration)
    left = array("f", [0.0]) * n
    right = array("f", [0.0]) * n
    beat = 60.0 / cfg["bpm"]
    progress = cfg["progress"]
    sections = cfg["sections"]
    kind = cfg["pulse"]

    def add_note(start: float, midi: int, length: float, gain: float,
                 timbre: str = "pluck", pan: float = 0.0) -> None:
        first = max(0, int(start * SR))
        count = min(n - first, int(length * SR))
        if count <= 0:
            return
        hz = 440.0 * (2.0 ** ((midi - 69) / 12.0))
        if timbre == "pad":
            harmonics, attack, fall, sustain, decay = (1.0, 0.24, 0.09, 0.035), 0.18, 0.42, 0.60, 0.32
        elif timbre == "wood":
            harmonics, attack, fall, sustain, decay = (1.0, 0.46, 0.22, 0.10), 0.002, 0.11, 0.16, 7.0
        elif timbre == "metal":
            harmonics, attack, fall, sustain, decay = (1.0, 0.31, 0.21, 0.12), 0.003, 0.24, 0.20, 3.5
        else:
            harmonics, attack, fall, sustain, decay = (1.0, 0.36, 0.19, 0.075), 0.006, 0.10, 0.10, 3.2
        lpan = math.sqrt((1.0 - pan) * 0.5)
        rpan = math.sqrt((1.0 + pan) * 0.5)
        phase = hz * TABLE_SIZE / SR
        for j in range(count):
            t = j / SR
            if t < attack:
                env = max(0.01, t / max(attack, 0.001))
            elif t < fall:
                env = sustain + (1.0 - sustain) * math.exp(-(t - attack) * 8.5)
            else:
                env = sustain * math.exp(-(t - fall) * decay)
            p = j * phase
            v = 0.0
            for h, weight in enumerate(harmonics, 1):
                v += weight * SINE[int(p * h) & (TABLE_SIZE - 1)]
            value = v * env * gain
            idx = first + j
            left[idx] += value * lpan
            right[idx] += value * rpan

    chord_index = 0
    bar_seconds = beat * cfg["meter"]
    bars = int(math.ceil(duration / bar_seconds))
    for bar in range(bars):
        bstart = bar * bar_seconds
        chord = progress[chord_index % len(progress)]
        chord_index += 1
        for step in range(cfg["meter"]):
            t = bstart + step * beat
            if t >= duration:
                continue
            chapter = sum(t >= point for point in sections) - 1
            # A steady acoustic object becomes a pulse only after the room is established.
            if name == "zhongqiu":
                add_note(t, cfg["key"] + (0 if step in (0, 2) else 7), 0.32, 0.105 if chapter < 2 else 0.13, "wood", -0.20 if step % 2 else 0.12)
                if chapter >= 1 and step in (0, 2):
                    add_note(t + 0.015, chord[0] - 12, 0.78, 0.12, "pad", -0.1)
                if chapter >= 2 and step in (1, 3):
                    add_note(t, chord[(step + bar) % len(chord)], 0.48, 0.095, "pluck", 0.35 if bar % 2 else -0.30)
                if chapter == 3 and step == 0:
                    for ix, m in enumerate(chord[1:]):
                        add_note(t + 0.04 * ix, m, 1.35, 0.052, "pad", (ix - 1) * 0.28)
                if chapter >= 5 and step == 0:
                    add_note(t, chord[0] + 12, 0.36, 0.075, "pluck", 0.0)
                if 69 <= t < 82 and step != 0:
                    continue
            elif name == "guoqing":
                if step in ((0, 3) if chapter < 2 else (0, 2)):
                    add_note(t, cfg["key"] + (0 if step == 0 else 5), 0.37, 0.11 if chapter < 4 else 0.055, "metal" if step == 0 else "wood", 0.18 if step == 0 else -0.18)
                if chapter >= 1 and step == 0:
                    add_note(t, chord[0] - 12, 1.05, 0.15, "pad", -0.2)
                if chapter >= 2 and step == 2:
                    add_note(t, chord[2], 0.72, 0.075, "pad", 0.32)
                if chapter == 3 and step in (0, 2):
                    add_note(t, chord[(step + bar) % len(chord)], 0.43, 0.07, "pluck", -0.25 + step * 0.25)
                if chapter >= 4 and step != 0:
                    continue
            else:
                # Each later stage adds an answer, a counter-rhythm, then a fuller chord.
                if 70 <= t < 83:
                    continue
                pulse_gain = 0.10 if chapter < 2 else 0.13
                add_note(t, cfg["key"] + (0 if step == 0 else 7), 0.26, pulse_gain, "wood", -0.22 if step % 2 else 0.18)
                if chapter >= 1 and step in (0, 2):
                    add_note(t + 0.025, chord[0] - 12, 0.56, 0.10, "pad", -0.12)
                if chapter >= 2 and step in (1, 3):
                    add_note(t, chord[(step + bar) % 4], 0.36, 0.08, "pluck", 0.38 if step == 1 else -0.35)
                if chapter >= 3 and step == 2:
                    add_note(t + 0.05, chord[3] + 12, 0.48, 0.07, "metal", 0.35)
                if chapter >= 4 and step == 3 and bar % 2 == 0:
                    add_note(t + 0.02, chord[2] + 7, 0.28, 0.065, "pluck", -0.4)
                if chapter >= 6 and step == 0:
                    for ix, m in enumerate(chord[1:]):
                        add_note(t + 0.035 * ix, m, 1.08, 0.058, "pad", (ix - 1) * 0.30)

    # Gentle echo makes the synthetic stems occupy a room rather than sound like test tones.
    for delay_s, amount in ((0.19, 0.13), (0.37, 0.06)):
        delay = int(delay_s * SR)
        for i in range(delay, n):
            left[i] += right[i - delay] * amount
            right[i] += left[i - delay] * amount

    peak = max(max(left), max(right), abs(min(left)), abs(min(right)), 1e-6)
    scale = min(0.72 / peak, 2.2)
    out = array("h")
    for i in range(n):
        fade = min(1.0, i / (SR * 0.6), (n - i) / (SR * 1.4))
        out.append(int(max(-32767, min(32767, left[i] * scale * fade * 32767))))
        out.append(int(max(-32767, min(32767, right[i] * scale * fade * 32767))))
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes(out.tobytes())
    return path


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    compose(root.name, root / "assets" / "music.wav")
