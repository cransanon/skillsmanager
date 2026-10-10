#!/usr/bin/env python3
"""Build a test clip (.mp4 and .mov) with known sounds in it.

Speech from espeak-ng, vowels from a pulse train through formant filters,
breath from shaped noise, hits from short decaying bursts.

    python tests/make_clip.py OUT_DIR
"""

import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter

SR = 16000
rng = np.random.default_rng(7)


def silence(s):
    return 0.002 * rng.standard_normal(int(s * SR))


def envelope(n, attack=0.03, release=0.08):
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    e[:a] = np.linspace(0, 1, a)
    e[-r:] = np.linspace(1, 0, r)
    return e


def formant(x, f, bw=120):
    lo, hi = max(50, f - bw), min(SR / 2 - 100, f + bw)
    b, a = butter(2, [lo / (SR / 2), hi / (SR / 2)], btype="band")
    return lfilter(b, a, x)


def vowel(f0, formants, dur, amp, glide=0.0):
    """A voiced vowel: pulse train at f0 (gliding by `glide` semitones)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * 2 ** ((glide * t / dur) / 12) * (1 + 0.01 * np.sin(2 * np.pi * 5 * t))
    phase = np.cumsum(f) / SR
    src = (np.diff(np.floor(phase), prepend=0) > 0).astype(float)
    src = lfilter([1], [1, -0.97], src)
    out = sum(formant(src, F) * g for F, g in formants)
    out /= np.abs(out).max() + 1e-9
    return amp * out * envelope(n)


def breath(dur, amp):
    n = int(dur * SR)
    x = formant(rng.standard_normal(n), 1800, 1200)
    x /= np.abs(x).max()
    return amp * x * envelope(n, 0.02, 0.06)


def hit(amp):
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n) * np.exp(-t / 0.008)
    x = formant(x, 1400, 1100)
    return amp * x / np.abs(x).max()


def speak(text, pitch, voice="en-us"):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.wav")
        subprocess.run(["espeak-ng", "-v", voice, "-p", str(pitch), "-s", "150", "-w", p, text], check=True)
        x, sr = sf.read(p)
        if sr != SR:
            idx = np.arange(0, len(x), sr / SR)
            x = np.interp(idx, np.arange(len(x)), x)
    return 0.5 * x / np.abs(x).max()


A = [(800, 1.0), (1200, 0.6), (2600, 0.2)]
O = [(500, 1.0), (850, 0.6), (2500, 0.15)]
UH = [(620, 1.0), (1200, 0.5), (2550, 0.15)]
M = [(250, 1.0), (1000, 0.05)]


def build():
    parts = [
        silence(0.6),
        speak("Don't stop. Right there.", 75, "en-us+f3"),
        silence(0.5),
        vowel(230, A, 0.9, 0.8, glide=-2),  # a long open moan
        silence(0.4),
        vowel(110, UH, 0.18, 0.6), silence(0.22),  # three low grunts
        vowel(112, UH, 0.18, 0.65), silence(0.22),
        vowel(108, UH, 0.18, 0.7),
        silence(0.5),
        breath(0.14, 0.25), silence(0.12), breath(0.14, 0.25), silence(0.12),
        breath(0.14, 0.25), silence(0.12), breath(0.14, 0.25),
        silence(0.5),
    ]
    for _ in range(8):  # rhythmic hits
        parts += [hit(0.7), silence(0.39)]
    parts += [
        silence(0.3),
        vowel(210, M, 0.7, 0.25),  # a closed-lip hum
        silence(0.5),
        speak("Come here.", 20, "en-us"),
        silence(0.5),
        vowel(260, O, 0.5, 0.9, glide=4),  # a rising oh
        silence(0.8),
    ]
    return np.concatenate(parts).astype(np.float32)


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    y = build()
    wav = os.path.join(out_dir, "fixture.wav")
    sf.write(wav, y, SR)
    dur = len(y) / SR
    for ext, codec in ((".mp4", "aac"), (".mov", "pcm_s16le")):
        out = os.path.join(out_dir, "fixture" + ext)
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={dur:.2f}",
             "-i", wav, "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", codec, out],
            check=True,
        )
        print(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "fixtures")
