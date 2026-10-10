"""Words: what was said, when, and how it came out."""

import re
from dataclasses import dataclass, field

import numpy as np

from . import audio
from .notation import stretch_word

# Whisper writes moans and hums down as words. Those are sounds, not words:
# they go to the sound track and get spelled from the pool.
INTERJECTIONS = {
    "ah", "ahh", "ahhh", "aah", "oh", "ohh", "ooh", "oooh", "mm", "mmm", "mmmm", "hmm", "hm",
    "mhm", "uh", "uhh", "um", "umm", "ugh", "huh", "ha", "hah", "haha", "ow", "oww", "eh", "ehh",
    "nn", "nnn", "ngh", "unh", "oo", "aw", "aww", "awh", "whoa", "woah", "uhm", "mmh", "hmmm",
}


@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float
    peak_db: float = -120.0
    f0: float = 0.0


@dataclass
class Line:
    words: list
    voice: str = ""
    f0: float = 0.0
    inserts: list = field(default_factory=list)  # (time, spelled) sounds inside the line

    @property
    def start(self):
        return self.words[0].start

    @property
    def end(self):
        return self.words[-1].end


def bare(t: str) -> str:
    return re.sub(r"[^a-z]", "", t.lower())


def transcribe(y: np.ndarray, model_size: str, language: str | None, min_prob: float):
    """Words with timestamps. Low-confidence words and interjections are dropped
    here so the sound pass hears those stretches instead.

    Returns (words, doubts). A stretch whisper loops on (the same words over
    and over: compression ratio past 2.4, whisper's own line) isn't words; it
    goes to the sound pass, and what whisper thought it heard goes in doubts."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    # The samples go in directly (16 kHz mono), so whisper never opens the video itself.
    segs, _info = model.transcribe(
        y,
        language=language,
        word_timestamps=True,
        vad_filter=False,
        condition_on_previous_text=False,
        beam_size=5,
        temperature=0.0,  # no sampling: the same clip gives the same words every run
        hallucination_silence_threshold=1.0,  # skip silence whisper starts looping on
    )
    words, doubts = [], []
    for s in segs:
        if s.no_speech_prob > 0.6 and s.avg_logprob < -1.0:
            continue
        if s.compression_ratio > 2.4:
            doubts.append((float(s.start), float(s.end), s.text.strip()))
            continue
        ws = list(s.words or [])
        for i, w in enumerate(ws):
            text = w.word.strip()
            if not text or bare(text) in INTERJECTIONS or not bare(text):
                continue
            if w.probability < min_prob:
                # A shaky word next to a sure one, in a line whisper is sure
                # of overall, is still a word ("Come" in "Come here").
                near = [ws[j].probability for j in (i - 1, i + 1) if 0 <= j < len(ws)]
                if not (w.probability >= 0.1 and s.avg_logprob >= -0.7 and near and max(near) >= 0.8):
                    continue
            if (w.end - w.start) > 2.5:
                continue
            words.append(Word(text, float(w.start), float(w.end), float(w.probability)))
    return words, doubts


def lines(words: list, gap: float = 0.8) -> list:
    out = []
    for w in words:
        if out and w.start - out[-1].end <= gap:
            out[-1].words.append(w)
        else:
            out.append(Line([w]))
    return out


def tighten(words, db, thresh_db, gap=0.2):
    """Whisper's word edges run wide and can swallow a sound made just before
    the word. A word holds no silence longer than `gap`: it starts after the
    last one, at its first loud frame, and ends at its last loud frame.

    Whisper also loops: the same words written over and over, stacked on one
    timestamp or on silence. A word with no sound under it, a word shorter
    than anyone can say one, or a word sitting on top of the last one is
    dropped. Returns the words kept."""
    kept = []
    for w in words:
        if w.end - w.start < 0.06:
            continue
        a, b = audio.t2f(w.start), max(audio.t2f(w.end), audio.t2f(w.start) + 1)
        on = db[a:b] > thresh_db
        if not on.any():
            continue
        idx = np.nonzero(on)[0]
        start = int(idx[0])
        quiet = 0
        for i in range(start, on.size):
            if on[i]:
                if quiet * audio.HOP / audio.SR >= gap:
                    start = i
                quiet = 0
            else:
                quiet += 1
        w.start = audio.f2t(a + start)
        w.end = audio.f2t(a + int(idx[-1]) + 1)
        if kept and w.start < kept[-1].end - 0.02:
            continue
        kept.append(w)
    return kept


def measure_words(y, db, words):
    import librosa

    for w in words:
        a, b = audio.t2f(w.start), max(audio.t2f(w.end), audio.t2f(w.start) + 1)
        d = db[a:b]
        w.peak_db = float(d.max()) if d.size else -120.0
        seg = y[int(w.start * audio.SR) : int(w.end * audio.SR)]
        if seg.size >= 1024:
            f0, v, _ = librosa.pyin(seg, fmin=60, fmax=600, sr=audio.SR, frame_length=1024, hop_length=audio.HOP)
            f0 = f0[v]
            w.f0 = float(np.median(f0)) if f0.size else 0.0


def deliver(line: Line, ref_db: float, char_s: float) -> str:
    """The line spelled the way it came out (style guide, How the line sounds).

    Loud: caps. Quiet: lowercase. Held: stretched letters. One word leaned on:
    italics. A pause inside the line: ellipsis. A sound inside the line breaks
    it where it landed.
    """
    ws = line.words
    peaks = np.array([w.peak_db for w in ws])
    med = float(np.median(peaks))
    quiet_line = peaks.max() < ref_db - 18
    loud_cut = ref_db - 4
    # One leaned-on word: clearly louder or higher than the rest of the line.
    lean = -1
    if len(ws) >= 3:
        f0s = np.array([w.f0 for w in ws])
        f0m = np.median(f0s[f0s > 0]) if (f0s > 0).any() else 0
        score = (peaks - med) + np.where((f0s > 0) & (f0m > 0), 12 * np.log2(np.maximum(f0s, 1) / max(f0m, 1)), 0)
        j = int(score.argmax())
        if score[j] >= 5 and ws[j].peak_db < loud_cut:
            lean = j
    inserts = sorted(line.inserts)
    parts = []
    for i, w in enumerate(ws):
        t = w.text
        held = (w.end - w.start) / max(1, len(bare(t))) / max(char_s, 1e-3)
        level = 0 if held < 2.5 else 1 if held < 3.2 else 2 if held < 4.0 else 3
        t = stretch_word(t, level)
        if quiet_line:
            t = t.lower().replace("!", "")
        elif w.peak_db >= loud_cut:
            t = t.upper()
        elif i == lean:
            core = re.sub(r"[^\w']+$", "", t)
            t = f"*{core}*" + t[len(core):]
        if i > 0:
            prev = ws[i - 1]
            here = [s for (at, s) in inserts if prev.end - 0.05 <= at < w.start + 0.05]
            if here:
                parts.append("— " + " ".join(here))
            elif w.start - prev.end >= 0.5:
                parts[-1] = parts[-1].rstrip(",.") + "…"
        parts.append(t)
    text = " ".join(parts)
    tail = [s for (at, s) in inserts if at >= ws[-1].end - 0.05]
    if tail:
        text = text.rstrip(".") + " — " + " ".join(tail)
    head = [s for (at, s) in inserts if at < ws[0].start - 0.05]
    if head:
        text = " ".join(head) + " " + text
    return text
