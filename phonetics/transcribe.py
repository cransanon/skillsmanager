#!/usr/bin/env python3
"""Transcribe the words and spell the sounds in a .mov or .mp4.

    python transcribe.py clip.mov
    python transcribe.py clip.mp4 --high Megan --low Ed -o clip.md

Writes <clip>.sounds.md next to the video unless -o says otherwise.
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scribe import audio, events, render, speech  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Words and sounds from a video, spelled the style guide's way.")
    ap.add_argument("video", help=".mov, .mp4, or anything ffmpeg reads")
    ap.add_argument("-o", "--out", help="output .md (default: <video>.sounds.md)")
    ap.add_argument("--json", action="store_true", help="also write <out>.json with every measurement")
    ap.add_argument("--high", default="high voice", help="name for the higher voice")
    ap.add_argument("--low", default="low voice", help="name for the lower voice")
    ap.add_argument("--split-hz", type=float, default=165.0,
                    help="pitch that splits the two voices (default 165 Hz)")
    ap.add_argument("--model", default="small",
                    help="whisper model: tiny, base, small, medium, large-v3 (default small)")
    ap.add_argument("--language", default="en", help="spoken language, or 'auto' (default en)")
    ap.add_argument("--no-words", action="store_true", help="skip the words, spell sounds only")
    ap.add_argument("--min-word-prob", type=float, default=0.45,
                    help="words whisper is less sure of than this are treated as sound (default 0.45)")
    ap.add_argument("--start", type=float, help="start at this many seconds")
    ap.add_argument("--end", type=float, help="stop at this many seconds")
    args = ap.parse_args(argv)

    t0 = time.time()
    log = lambda s: print(s, file=sys.stderr, flush=True)  # noqa: E731

    log(f"reading {args.video}")
    y = audio.extract(args.video, args.start, args.end)
    dur = y.size / audio.SR
    offset = args.start or 0.0
    names = (args.high, args.low)

    db = audio.rms_db(y)
    floor_db, ref_db, thresh = events.levels(db)

    words = []
    model = None
    if not args.no_words:
        log(f"listening for words (whisper {args.model})")
        lang = None if args.language == "auto" else args.language
        words = speech.transcribe(y, args.model, lang, args.min_word_prob)
        speech.tighten(words, db, thresh)
        model = args.model
        log(f"  {len(words)} words")

    log("listening for everything else")
    sounds, ref_db, floor_db = events.find(y, words, args.split_hz, names, log)
    log(f"  {len(sounds)} sounds")

    lines = speech.lines(words)
    if words:
        speech.measure_words(y, db, words)
        for ln in lines:
            f0s = [w.f0 for w in ln.words if w.f0 > 0]
            ln.f0 = float(np.median(f0s)) if f0s else 0.0
            ln.voice = names[0] if ln.f0 >= args.split_hz else names[1] if ln.f0 > 0 else "voice"

    # Sounds inside a spoken line break the line where they land.
    used = set()
    for ln in lines:
        for i, s in enumerate(sounds):
            if s.track not in ("voice", "breath") or not s.spelled:
                continue
            if ln.start - 0.05 <= s.start <= ln.end + 0.3 and s.source in (ln.voice, "breath", "voice"):
                ln.inserts.append((s.start, render.page(s.spelled)))
                used.add(i)
    rest = [s for i, s in enumerate(sounds) if i not in used]
    grouped = events.runs([s for s in rest if s.spelled])
    grouped += [s for s in rest if not s.spelled]

    char_s = 0.07
    if words:
        per = [(w.end - w.start) / max(1, len(speech.bare(w.text))) for w in words]
        char_s = float(np.median(per))
    spoken = [(ln, speech.deliver(ln, ref_db, char_s)) for ln in lines]

    # Who's who, by pitch.
    voices = []
    for n in names:
        f0s = [s.m.f0 for s in sounds if s.source == n and s.m and s.m.f0 > 0]
        f0s += [ln.f0 for ln in lines if ln.voice == n and ln.f0 > 0]
        if f0s:
            voices.append((n, float(np.median(f0s))))

    room = room_under(y, db, floor_db)

    unspelled = {}
    for s in sounds:
        if not s.spelled:
            unspelled[s.kind] = unspelled.get(s.kind, 0) + 1

    items = render.page_items(spoken, grouped)
    if offset:
        for it in items:
            it["start"] += offset
            it["end"] += offset
        for s in sounds:
            s.start += offset
            s.end += offset

    md = render.markdown(args.video, dur, model, items, sounds, voices, room, unspelled, args)
    out = args.out or os.path.splitext(args.video)[0] + ".sounds.md"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(md)
    if args.json:
        with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as fh:
            fh.write(render.to_json(sounds, items, words))
    log(f"wrote {out} in {time.time() - t0:.0f} s")
    return 0


def room_under(y, db, floor_db):
    """What the room sounds like when nobody's making a sound."""
    quiet = np.nonzero(db <= floor_db + 3)[0]
    if quiet.size < 100:
        return ""
    idx = np.concatenate([np.arange(f * audio.HOP, (f + 1) * audio.HOP) for f in quiet[:500]])
    clip = y[idx[idx < y.size]]
    if np.sqrt(np.mean(clip ** 2)) < 1e-4:
        return ""
    sc = audio.classify([clip])[0]
    p, kind, label = events.best(sc, events.ROOM_LABELS)
    if p < 0.2 or not label:
        return ""
    s = events.spell_room(kind, None, "quiet") if kind == "hum" else None
    return f"{label.lower()} {render.page(s)}" if s else label.lower()


if __name__ == "__main__":
    sys.exit(main())
