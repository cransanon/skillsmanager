"""Write the transcript out as Markdown (and JSON if asked)."""

import json
import os

from . import events as E
from .notation import page


def ts(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m):02d}:{s:04.1f}"


def heard(s) -> str:
    if not s.label:
        return ""
    return f"{s.label} {s.label_p:.2f}"


def markdown(path, dur, model, page_items, sounds, voices, room, unspelled, args) -> str:
    name = os.path.basename(path)
    out = [f"# {name}", ""]
    meta = [ts(dur)]
    if args.start is not None or args.end is not None:
        meta.append(f"from {ts(args.start or 0)} to {ts(args.end or dur)}")
    meta.append(f"words: whisper {model}" if model else "words: off")
    out += [" · ".join(meta), ""]
    if voices:
        out.append("Voices: " + " · ".join(f"**{n}** around {int(hz)} Hz" for n, hz in voices))
        out.append("")
    if room:
        out.append(f"Under everything: {room}")
        out.append("")

    out += ["## On the page", ""]
    for it in page_items:
        at = f"`{ts(it['start'])}`"
        if it["type"] == "line":
            out.append(f"{at} **{it['who']}** — \"{it['text']}\"")
        elif it["type"] == "run":
            out.append(f"{at} **{it['who']}** — {it['spelled']} · {it['note']}, to {ts(it['end'])}")
        elif it["type"] == "sound":
            extra = f" · {it['kind']}"
            if it["notes"]:
                extra += ", " + ", ".join(it["notes"])
            out.append(f"{at} **{it['who']}** — {it['spelled']}{extra}")
        else:
            out.append(f"{at} **{it['who']}** — {it['kind']} (no spelling in the pool)")
        out.append("")

    out += ["## Every sound, measured", ""]
    out.append("| at | long | made by | what | heard as | phonemes | spelled | loud | pitch | notes |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for s in sounds:
        m = s.m
        pitch = f"{int(m.f0)} Hz" + (f", {m.f0_slope:+.0f} st" if abs(m.f0_slope) >= 1 else "") if m and m.f0 else ""
        loud = f"{s.tier}, {m.peak_db:.0f} dB" if m else s.tier
        spelled = page(s.spelled) if s.spelled else "—"
        notes = ", ".join(s.notes)
        out.append(
            f"| {ts(s.start)} | {s.dur:.2f} s | {s.source} | {s.kind} | {heard(s)} | {s.ipa} | {spelled} | {loud} | {pitch} | {notes} |"
        )
    out.append("")
    if unspelled:
        out += ["## Heard, not spelled", ""]
        out.append("The pool has no spelling for these. They stay unspelled until the style guide gives them one.")
        out.append("")
        for kind, n in sorted(unspelled.items()):
            out.append(f"- {kind}: {n}")
        out.append("")
    return "\n".join(out)


def to_json(sounds, page_items, words) -> str:
    rows = []
    for s in sounds:
        m = s.m
        rows.append({
            "start": round(s.start, 3), "end": round(s.end, 3), "track": s.track, "source": s.source,
            "kind": s.kind, "spelled": s.spelled, "tier": s.tier, "label": s.label,
            "label_p": round(s.label_p, 3), "phonemes": s.ipa, "notes": s.notes,
            "peak_db": round(m.peak_db, 1) if m else None, "f0": round(m.f0, 1) if m else None,
            "f0_slope": round(m.f0_slope, 1) if m else None,
            "f1": round(m.f1) if m else None, "f2": round(m.f2) if m else None,
            "onset_ms": round(m.onset_ms, 1) if m else None, "decay_ms": round(m.decay_ms, 1) if m else None,
        })
    ws = [{"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3), "prob": round(w.prob, 2),
           "peak_db": round(w.peak_db, 1), "f0": round(w.f0, 1)} for w in words]
    return json.dumps({"page": page_items, "words": ws, "sounds": rows}, ensure_ascii=False, indent=1)


def page_items(lines, rest):
    """Everything on one timeline: lines, runs, single sounds."""
    items = []
    for ln, text in lines:
        items.append({"type": "line", "start": ln.start, "end": ln.end, "who": ln.voice or "voice", "text": text})
    for r in rest:
        if isinstance(r, E.Run):
            items.append({"type": "run", "start": r.start, "end": r.end, "who": r.source, "spelled": r.spelled,
                          "note": r.note})
        elif r.spelled:
            items.append({"type": "sound", "start": r.start, "end": r.end, "who": r.source,
                          "spelled": page(r.spelled), "kind": r.kind, "notes": r.notes})
        else:
            items.append({"type": "unspelled", "start": r.start, "end": r.end, "who": r.source, "kind": r.kind})
    items.sort(key=lambda x: x["start"])
    return items
