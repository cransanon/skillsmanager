"""Pull the audio out of the video and measure it."""

import json
import os
import subprocess
from dataclasses import dataclass, field

import numpy as np

SR = 16000
HOP = 160  # 10 ms
WIN = 400  # 25 ms


def extract(path: str, start: float | None = None, end: float | None = None) -> np.ndarray:
    """Mono 16 kHz float32 from any file ffmpeg reads (.mov, .mp4, ...)."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    cmd = ["ffmpeg", "-nostdin", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if end is not None:
        dur = end - (start or 0.0)
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    out = subprocess.run(cmd, capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read {path}: {out.stderr.decode(errors='replace').strip()}")
    y = np.frombuffer(out.stdout, dtype=np.float32).copy()
    if y.size == 0:
        raise RuntimeError(f"{path} has no audio track")
    return y


def duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True,
    )
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def rms_db(y: np.ndarray) -> np.ndarray:
    """Frame loudness in dBFS, one value per 10 ms."""
    import librosa

    r = librosa.feature.rms(y=y, frame_length=WIN, hop_length=HOP, center=True)[0]
    return 20 * np.log10(np.maximum(r, 1e-6))


def t2f(t: float) -> int:
    return int(round(t * SR / HOP))


def f2t(f: int) -> float:
    return f * HOP / SR


@dataclass
class Measure:
    start: float
    end: float
    peak_db: float = -120.0
    mean_db: float = -120.0
    attack_ms: float = 0.0  # to within 6 dB of the peak, 10 ms frames
    onset_ms: float = 999.0  # sample-level rise, 10% to 90% of the peak
    decay_ms: float = 999.0  # sample-level fall, peak to 10%
    fall_ms: float = 999.0  # from the last near-peak frame to the end: short = cut off
    f1: float = 0.0  # formants, for the mouth shape when the phonemes are silent
    f2: float = 0.0
    rise_db: float = 0.0  # second half minus first half
    voiced: float = 0.0  # share of frames with a pitch
    f0: float = 0.0  # median Hz
    f0_slope: float = 0.0  # semitones, end third minus start third
    f0_tail: float = 0.0  # semitones, last fifth minus the middle
    flatness: float = 0.0
    centroid: float = 0.0
    low_share: float = 0.0  # energy under 1 kHz
    lead_breath: float = 0.0  # seconds of unvoiced sound before the voice
    tail_breath: float = 0.0  # seconds of unvoiced sound after the voice
    dips: int = 0  # loudness dips inside the sound
    extra: dict = field(default_factory=dict)

    @property
    def dur(self) -> float:
        return self.end - self.start


def measure(y: np.ndarray, db: np.ndarray, start: float, end: float, pitch: bool = True) -> Measure:
    import librosa

    m = Measure(start, end)
    a, b = int(start * SR), int(end * SR)
    seg = y[a:b]
    fa, fb = t2f(start), max(t2f(end), t2f(start) + 1)
    d = db[fa:fb]
    if seg.size < WIN or d.size == 0:
        return m
    m.peak_db = float(d.max())
    env = np.abs(seg)
    k = max(1, SR // 2000)  # half-ms smoothing
    env = np.convolve(env, np.ones(k) / k, mode="same")
    top = float(env.max())
    if top > 0:
        p = int(env.argmax())
        lo = np.nonzero(env[: p + 1] >= 0.1 * top)[0]
        hi = np.nonzero(env[: p + 1] >= 0.9 * top)[0]
        if lo.size and hi.size:
            m.onset_ms = float((hi[0] - lo[0]) * 1000 / SR)
        below = np.nonzero(env[p:] < 0.1 * top)[0]
        m.decay_ms = float(below[0] * 1000 / SR) if below.size else float((env.size - p) * 1000 / SR)
    m.mean_db = float(d.mean())
    above = np.nonzero(d >= m.peak_db - 6)[0]
    m.attack_ms = float(f2t(int(above[0])) * 1000) if above.size else 0.0
    near = np.nonzero(d >= m.peak_db - 6)[0]
    m.fall_ms = float((d.size - 1 - near[-1]) * HOP / SR * 1000) if near.size else 999.0
    half = d.size // 2
    if half >= 2:
        m.rise_db = float(d[half:].mean() - d[:half].mean())
    # Dips: places the loudness falls 6 dB under both sides and comes back.
    if d.size >= 9:
        sm = np.convolve(d, np.ones(3) / 3, mode="same")
        n = 0
        for i in range(3, sm.size - 3):
            if sm[i] == sm[i - 3 : i + 4].min() and min(sm[:i].max(), sm[i + 1 :].max()) - sm[i] >= 6:
                n += 1
        m.dips = n
    S = np.abs(librosa.stft(seg, n_fft=512, hop_length=HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=SR, n_fft=512)
    tot = S.sum() + 1e-12
    m.low_share = float(S[freqs < 1000].sum() / tot)
    m.flatness = float(librosa.feature.spectral_flatness(S=np.sqrt(S)).mean())
    m.centroid = float(librosa.feature.spectral_centroid(S=np.sqrt(S), sr=SR).mean())
    if pitch:
        pad = max(0, 2048 - seg.size)
        f0, vflag, _ = librosa.pyin(
            np.pad(seg, (0, pad)), fmin=60, fmax=1100, sr=SR, frame_length=1024, hop_length=HOP
        )
        # pyin centres its frames: one per hop, padding frames dropped.
        n = seg.size // HOP + 1
        f0, vflag = f0[:n], vflag[:n]
        m.voiced = float(vflag.mean()) if vflag.size else 0.0
        v = f0[vflag]
        if v.size >= 3:
            m.f0 = float(np.median(v))
            st = 12 * np.log2(v / m.f0)
            k = max(1, v.size // 3)
            m.f0_slope = float(st[-k:].mean() - st[:k].mean())
            k5 = max(1, v.size // 5)
            m.f0_tail = float(st[-k5:].mean() - st[v.size // 3 : 2 * v.size // 3].mean()) if v.size >= 6 else 0.0
            idx = np.nonzero(vflag)[0]
            m.lead_breath = float(idx[0] * HOP / SR)
            m.tail_breath = float(max(0.0, m.dur - (idx[-1] + 1) * HOP / SR))
            m.f1, m.f2 = formants(seg, idx)
    return m


def formants(seg, voiced_frames):
    """F1 and F2 by LPC over the voiced frames (median across frames)."""
    import librosa

    x = np.append(seg[0], seg[1:] - 0.97 * seg[:-1])
    f1s, f2s = [], []
    n = 480  # 30 ms
    for f in voiced_frames[:: max(1, len(voiced_frames) // 20)]:
        a = f * HOP
        fr = x[a : a + n]
        if fr.size < n or not np.any(fr):
            continue
        try:
            coef = librosa.lpc(fr * np.hamming(n), order=18)
        except Exception:
            continue
        roots = [r for r in np.roots(coef) if np.imag(r) > 0]
        cand = []
        for r in roots:
            fq = np.angle(r) * SR / (2 * np.pi)
            bw = -SR / np.pi * np.log(np.abs(r) + 1e-12)
            if 90 < fq < 4000 and bw < 400:
                cand.append(fq)
        cand.sort()
        if len(cand) >= 2:
            f1s.append(cand[0])
            f2s.append(cand[1])
    if len(f1s) < 2:
        return 0.0, 0.0
    return float(np.median(f1s)), float(np.median(f2s))


# --- Models ---------------------------------------------------------------

_ast = None
_phone = None


def ast_model():
    """AudioSet classifier: what kind of sound it is (moan, gasp, slap...)."""
    global _ast
    if _ast is None:
        import torch
        from transformers import ASTFeatureExtractor, ASTForAudioClassification

        name = "MIT/ast-finetuned-audioset-10-10-0.4593"
        fe = ASTFeatureExtractor.from_pretrained(name)
        model = ASTForAudioClassification.from_pretrained(name).eval()
        torch.set_grad_enabled(False)
        _ast = (fe, model)
    return _ast


def classify(clips: list, batch: int = 8) -> list:
    """AudioSet scores for each clip, as {label: probability}."""
    import torch

    fe, model = ast_model()
    labels = model.config.id2label
    out = []
    for i in range(0, len(clips), batch):
        part = [c if c.size >= SR // 4 else np.pad(c, (0, SR // 4 - c.size)) for c in clips[i : i + batch]]
        x = fe(part, sampling_rate=SR, return_tensors="pt")
        with torch.no_grad():
            p = torch.sigmoid(model(**x).logits).numpy()
        for row in p:
            top = np.argsort(row)[::-1][:12]
            out.append({labels[int(j)]: float(row[j]) for j in top})
    return out


def phone_model():
    """Phoneme recogniser: which vowel or hum a sound is made of."""
    global _phone
    if _phone is None:
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

        name = "facebook/wav2vec2-lv-60-espeak-cv-ft"
        fe = Wav2Vec2FeatureExtractor.from_pretrained(name)
        model = Wav2Vec2ForCTC.from_pretrained(name).eval()
        with open(hf_hub_download(name, "vocab.json"), encoding="utf-8") as fh:
            vocab = json.load(fh)
        inv = {v: k for k, v in vocab.items()}
        torch.set_grad_enabled(False)
        _phone = (fe, model, inv)
    return _phone


def phones(clip: np.ndarray) -> list:
    """Frame-level phonemes (20 ms each), blanks dropped, as [(ipa, frames)]."""
    import torch

    fe, model, inv = phone_model()
    if clip.size < SR // 10:
        clip = np.pad(clip, (0, SR // 10 - clip.size))
    x = fe(clip, sampling_rate=SR, return_tensors="pt")
    with torch.no_grad():
        ids = model(x.input_values).logits[0].argmax(-1).tolist()
    runs = []
    for i in ids:
        tok = inv.get(i, "")
        if tok in ("<pad>", "<s>", "</s>", "<unk>", "|", ""):
            if runs and runs[-1][0] is not None:
                runs.append((None, 0))
            continue
        if runs and runs[-1][0] == tok:
            runs[-1] = (tok, runs[-1][1] + 1)
        else:
            runs.append((tok, 1))
    return [r for r in runs if r[0] is not None]
