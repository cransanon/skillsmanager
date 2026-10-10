"""Find every sound that isn't a word, say what made it, and spell it."""

from dataclasses import dataclass, field

import numpy as np

from . import audio, notation as nt, pool as P

# AudioSet labels, grouped by what made the sound.
VOICE_LABELS = {
    "Wail, moan": "moan", "Groan": "groan", "Grunt": "grunt", "Whimper": "whimper",
    "Crying, sobbing": "whimper", "Screaming": "scream", "Humming": "hum", "Singing": "hum",
    "Female singing": "hum", "Male singing": "hum", "Shout": "cry", "Yell": "cry", "Bellow": "cry",
    "Whoop": "cry", "Speech": "voice", "Female speech, woman speaking": "voice",
    "Male speech, man speaking": "voice", "Conversation": "voice", "Babbling": "voice",
    "Narration, monologue": "voice", "Whispering": "voice",
    "Laughter": "laugh", "Belly laugh": "laugh", "Chuckle, chortle": "laugh",
    "Giggle": "giggle", "Snicker": "giggle",
}
BREATH_LABELS = {
    "Breathing": "breath", "Gasp": "gasp", "Pant": "pant", "Sigh": "sigh", "Wheeze": "ragged",
    "Snort": "huff", "Cough": "cough", "Throat clearing": "clear", "Gargling": "gag",
    "Sniff": None, "Sneeze": None, "Snoring": None, "Hiccup": None, "Burping, eructation": None,
}
BODY_LABELS = {
    "Slap, smack": "slap", "Clapping": "clap", "Hands": "soft", "Whack, thwack": "thwack",
    "Thump, thud": "thud", "Squish": "wet", "Liquid": "wet", "Slosh": "wet", "Splash, splatter": "wet",
    "Drip": "drip", "Chewing, mastication": "mouth", "Biting": "bite",
}
ROOM_LABELS = {
    "Creak": "creak", "Squeak": "springs", "Zipper (clothing)": "zipper", "Rustle": "sheets",
    "Water tap, faucet": None, "Shower": "water", "Bathtub (filling or washing)": "water",
    "Door": None, "Knock": "headboard", "Tick": None, "Tick-tock": None, "Mechanical fan": "hum",
    "Air conditioning": "hum", "Mains hum": "hum", "Television": None, "Music": None,
    "Walk, footsteps": None, "Shuffle": None, "Dishes, pots, and pans": None, "Cutlery, silverware": None,
}

# IPA from the phoneme model, by mouth shape.
VOWEL_CLASS = {}
for ch in "aɑæɐä":
    VOWEL_CLASS[ch] = "a"
for ch in "oɔɒ":
    VOWEL_CLASS[ch] = "o"
for ch in "uʊɯ":
    VOWEL_CLASS[ch] = "u"
for ch in "ʌəɜɚɝ":
    VOWEL_CLASS[ch] = "uh"
for ch in "eɛ":
    VOWEL_CLASS[ch] = "e"
for ch in "iɪy":
    VOWEL_CLASS[ch] = "i"
for ch in "m":
    VOWEL_CLASS[ch] = "m"
for ch in "nŋɲ":
    VOWEL_CLASS[ch] = "n"
for ch in "hɦx":
    VOWEL_CLASS[ch] = "h"
for ch in "kgq":
    VOWEL_CLASS[ch] = "k"


@dataclass
class Sound:
    start: float
    end: float
    track: str  # "voice", "breath", "body", "room"
    kind: str  # what it is: moan, grunt, gasp, slap, creak...
    source: str  # what made it: high voice, low voice, breath, skin, wet, bed...
    spelled: str | None  # the pool form with notation, None = no pool spelling
    tier: str = nt.MID
    m: audio.Measure | None = None
    label: str = ""
    label_p: float = 0.0
    ipa: str = ""
    shape: str = ""  # mouth shape the spelling came from
    notes: list = field(default_factory=list)
    wet: bool = False  # a hit the classifier also hears as wet

    @property
    def dur(self):
        return self.end - self.start


# --- Finding the sounds ----------------------------------------------------


def regions(db: np.ndarray, floor: float, min_len: float = 0.05, bridge: float = 0.06):
    """Stretches louder than the room, as (start, end) seconds."""
    on = db > floor
    out = []
    i, n = 0, on.size
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            out.append([audio.f2t(i), audio.f2t(j)])
            i = j
        else:
            i += 1
    merged = []
    for a, b in out:
        if merged and a - merged[-1][1] <= bridge:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged if b - a >= min_len]


def split_on_dips(db, a, b, depth=6.0, min_len=0.08):
    """One region holding several sounds (UNH—UNH—UNH) cut where it dips."""
    fa, fb = audio.t2f(a), audio.t2f(b)
    d = db[fa:fb]
    if d.size < 12:
        return [(a, b)]
    sm = np.convolve(d, np.ones(5) / 5, mode="same")
    cuts = []
    last = 0
    i = 4
    while i < sm.size - 4:
        w = sm[max(0, i - 8) : i + 9]
        if sm[i] == w.min():
            left, right = sm[last:i].max() if i > last else sm[i], sm[i + 1 :].max()
            if min(left, right) - sm[i] >= depth and audio.f2t(i - last) >= min_len:
                cuts.append(i)
                last = i
                i += 4
        i += 1
    edges = [0] + cuts + [d.size]
    parts = [(a + audio.f2t(edges[k]), a + audio.f2t(edges[k + 1])) for k in range(len(edges) - 1)]
    return [p for p in parts if p[1] - p[0] >= 0.04]


def minus(spans, cover, before=0.06, after=0.12):
    """spans with the covered stretches (words) cut out. Whisper's word edges
    run early, so the tail of a word gets more room than its head."""
    out = []
    for a, b in spans:
        pieces = [(a, b)]
        for c, d in cover:
            nxt = []
            for x, y in pieces:
                c2, d2 = c - before, d + after
                if d2 <= x or c2 >= y:
                    nxt.append((x, y))
                    continue
                if c2 > x:
                    nxt.append((x, c2))
                if d2 < y:
                    nxt.append((d2, y))
            pieces = nxt
        out.extend(p for p in pieces if p[1] - p[0] >= 0.05)
    return out


def hits(y, sr, words):
    """Sharp hits (skin, wall, headboard) from the percussive part of the sound."""
    import librosa

    harm, perc = librosa.effects.hpss(y, margin=3.0)
    env = librosa.onset.onset_strength(y=perc, sr=sr, hop_length=audio.HOP)
    on = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=audio.HOP, backtrack=False, units="frames")
    if env.size == 0 or on.size == 0:
        return perc, []
    med = np.median(env)
    mad = np.median(np.abs(env - med)) + 1e-6
    strong = [int(f) for f in on if env[f] > med + 6 * mad]
    return perc, [audio.f2t(f) for f in strong]


# --- Shapes ----------------------------------------------------------------


def shape_of(ph):
    """Which mouth shape dominates: a, o, u, uh, e, i, m, n. Also whether it
    opens on breath (h) and closes on a stop (k)."""
    weight = {}
    for tok, n in ph:
        c = VOWEL_CLASS.get(tok[:1])
        if c:
            weight[c] = weight.get(c, 0) + n
    first = VOWEL_CLASS.get(ph[0][0][:1]) if ph else None
    last = VOWEL_CLASS.get(ph[-1][0][:1]) if ph else None
    vow = {k: v for k, v in weight.items() if k in ("a", "o", "u", "uh", "e", "i")}
    nas = {k: v for k, v in weight.items() if k in ("m", "n")}
    if vow and (not nas or max(vow.values()) >= max(nas.values())):
        core = max(vow, key=vow.get)
    elif nas:
        core = max(nas, key=nas.get)
    else:
        core = None
    return core, first == "h", last == "k", (last in ("n", "m") and core not in ("m", "n"))


# Rough F1/F2 for each mouth shape (adult average), for when the phoneme
# model hears nothing it knows.
FORMANT_SHAPES = {"a": (800, 1250), "o": (520, 880), "u": (330, 820), "uh": (640, 1200),
                  "e": (480, 1950), "i": (310, 2300)}


def shape_from_formants(m):
    if m.low_share >= 0.97 and (m.f1 == 0 or m.f1 < 380):
        return "m"
    if not m.f1 or not m.f2:
        return None
    lf1, lf2 = np.log(m.f1), np.log(m.f2)
    return min(FORMANT_SHAPES, key=lambda k: (np.log(FORMANT_SHAPES[k][0]) - lf1) ** 2
               + 0.5 * (np.log(FORMANT_SHAPES[k][1]) - lf2) ** 2)


def impact_like(m):
    """A hit: very short, instant attack, no pitch."""
    return m.dur <= 0.2 and m.onset_ms <= 8 and m.decay_ms <= 80 and m.voiced < 0.2


def length_level(dur, steps=(0.3, 0.6, 1.0)):
    return sum(dur >= s for s in steps)


# --- Spelling ---------------------------------------------------------------


def spell_voice(kind, m, core, h_lead, k_end, nasal_end, tier, voice_hi):
    """Pick the pool form for a voiced sound, then the notation."""
    lvl = length_level(m.dur)
    sharp = m.attack_ms <= 40
    notes = []
    core = core or ("m" if m.low_share > 0.9 else "a")
    swallowed = False
    shift = False

    if kind == "scream" or (tier == nt.LOUD and m.dur >= 0.7 and m.f0 >= 380):
        kind, s = "scream", nt.pick(P.SCREAM, length_level(m.dur, (0.9, 1.4)))
    elif kind == "grunt" or (kind == "moan" and m.dur < 0.35 and not voice_hi and core in ("uh", "a", "o") and m.fall_ms <= 60):
        kind = "grunt"
        if core == "n":
            s = nt.pick(P.GRUNT["n"], min(lvl, 1))
        elif core == "m":
            s = nt.pick(P.GRUNT["teeth"], 0)
        elif k_end or m.fall_ms <= 20:
            s = nt.pick(P.GRUNT["cut"], 0)
        elif core in ("o", "u"):
            s = nt.pick(P.GRUNT["o"], min(lvl, 1))
        elif nasal_end and m.dur >= 0.3:
            s = nt.pick(P.GRUNT["gut"], min(lvl, 1))
        else:
            s = nt.pick(P.GRUNT["uh"], 0)
    elif kind == "groan" and core not in ("m", "n"):
        kind = "groan"
        if nasal_end:
            s = nt.pick(P.GROAN["n"], 0)
        elif core == "o":
            s = nt.pick(P.GROAN["o"], lvl)
        else:
            s = nt.pick(P.GROAN["uh"], 1 if lvl >= 2 else 0)
        if tier == nt.LOUD and sharp and m.dur < 0.4:
            kind, s = "strain", nt.pick(P.STRAIN, 0)
    elif kind == "hum" or core == "m":
        if tier == nt.LOUD:
            kind = "muffled"
            s = nt.pick(P.LIMIT if (m.tail_breath >= 0.08 and m.fall_ms <= 40) else P.MUFFLED, min(lvl, 1))
        else:
            kind = "hum"
            s = nt.pick(P.HUM, lvl if lvl < 3 else 2)
            swallowed = tier == nt.QUIET
    elif kind == "whimper" or core == "n":
        if m.f0_slope >= 3 and m.dur >= 0.5 and m.f0 >= 300:
            kind, s = "keen", nt.pick(P.KEEN["n"], 0)
        elif m.dur < 0.2 and sharp and m.f0 >= 300:
            kind, s = "squeal", nt.pick(P.SQUEAL["n"], 0)
        elif core == "n" and k_end:
            kind, s = "swallowed moan", nt.pick(P.SWALLOWED, min(lvl, 1))
        else:
            kind = "whimper"
            s = nt.pick(P.WHIMPER["n" if core != "m" else "m"], min(lvl, 1))
            swallowed = tier == nt.QUIET and core == "m"
    elif core == "uh":
        kind = "groan"
        s = nt.pick(P.GROAN["n"], 0) if nasal_end else nt.pick(P.GROAN["uh"], 1 if lvl >= 2 else 0)
        if tier == nt.LOUD and sharp and m.dur < 0.4:
            kind, s = "strain", nt.pick(P.STRAIN, 0)
    elif core == "e":
        kind, s = "whine", nt.pick(P.WHINE, 1 if lvl >= 2 else 0)
    elif core == "i":
        if m.dur < 0.25:
            kind, s = "squeal", nt.pick(P.SQUEAL["i"], 0)
        else:
            kind, s = "keen", nt.pick(P.KEEN["i"], 0)
    else:
        vow = "o" if core == "o" else "u" if core == "u" else "a"
        if m.dur < 0.15 and sharp and tier != nt.QUIET:
            kind = "yelp"
            s = nt.pick(P.YELP["cut" if k_end else ("o" if vow == "o" else "a")], 0)
        elif m.dur < 0.35 and sharp and tier != nt.QUIET:
            kind = "cry out"
            s = nt.pick(P.CRY["o" if vow == "o" else "a"], 1 if (vow == "a" and m.dur >= 0.25) else 0)
        elif tier == nt.LOUD and m.dur >= 0.45 and vow in ("a", "o") and m.f0 < 420 and m.f0_slope < 2.5:
            kind = "peak moan"
            s = nt.pick(P.PEAK["falling" if m.f0_tail <= -3 else "plain"], 0)
        elif tier == nt.LOUD and m.dur >= 1.0:
            kind, s = "wail", nt.pick(P.WAIL, 1 if m.dur >= 1.5 else 0)
        else:
            kind = "moan"
            s = nt.pick(P.MOAN[vow], lvl)
            if h_lead or m.lead_breath >= 0.06:
                b = s if s in P.H_BEFORE else s[:2]
                if b in P.H_BEFORE and s.startswith(b):
                    s = P.H_BEFORE[b] + s[len(b):]
                    notes.append("breath before the voice")
            elif m.tail_breath >= 0.08 and s in P.H_AFTER:
                s = P.H_AFTER[s]
                notes.append("air after the voice")
        shift = m.rise_db >= 8 and m.dur >= 0.4 and tier != nt.QUIET

    if shift:
        s = nt.shift(s)
        notes.append("volume arriving inside the sound")
    else:
        s = nt.case(s, tier)
        if m.f0_slope >= 2.5 and kind in ("moan", "cry out", "yelp", "whimper", "hum"):
            s = nt.rise(s, tier)
            notes.append("pitch rising")
        elif m.fall_ms <= 30 and m.dur >= 0.15 and kind not in ("keen", "grunt", "squeal", "yelp", "cry out"):
            s = nt.cut(s)
            notes.append("cut off")
        elif tier == nt.LOUD and sharp and kind in ("moan", "groan", "peak moan"):
            s = nt.spike(s)
    if swallowed:
        s = nt.swallow(s)
        notes.append("swallowed")
    return kind, nt.cap_stacks(s), notes


def spell_breath(kind, m, ph_core, tier):
    notes = []
    if kind == "gasp":
        kind = "gasp"
        s = nt.pick(P.GASP["voiced"], 0) if m.voiced >= 0.2 else nt.pick(P.GASP["catch"], 0)
    elif kind == "sigh" or (kind == "breath" and m.dur >= 0.8 and m.rise_db <= -4):
        kind = "sigh"
        s = nt.pick(P.SIGH, 1 if m.dur >= 1.2 else 0)
    elif kind == "ragged":
        s = nt.pick(P.RAGGED, 0)
    elif kind == "huff" or (kind == "breath" and m.dur < 0.3 and tier != nt.QUIET):
        kind = "huff"
        s = nt.pick(P.HUFF, 0)
    elif kind == "cough":
        s = nt.pick(P.COUGH, 0)
    elif kind == "clear":
        s = nt.pick(P.CLEAR, 0)
    elif kind == "gag":
        s = nt.pick(P.GAG, 0)
    elif kind == "breath" and m.centroid >= 4500 and m.flatness >= 0.3:
        kind = "sharp in through the teeth"
        s = nt.pick(P.SHARP_IN["t" if m.attack_ms <= 20 else "s"], 0)
    elif kind == "breath" and m.dips >= 3 and m.dur >= 0.6:
        kind = "shaky exhale"
        s = nt.pick(P.SHAKY, 1 if m.dips >= 4 else 0)
    elif kind == "breath" and m.voiced >= 0.3:
        kind = "breathy moan"
        s = nt.pick(P.BREATHY, 1 if m.dur >= 0.7 else 0)
    else:
        kind = "pant" if kind in ("pant", "breath") else kind
        s = nt.pick(P.PANT, 0)
    if m.fall_ms <= 30 and m.dur >= 0.3 and kind in ("breathy moan", "sigh"):
        s = nt.cut(s)
        notes.append("cut off")
    if tier == nt.LOUD and kind in ("huff", "breathy moan", "sigh"):
        s = nt.case(s, tier)
    return kind, s, notes


def spell_body(kind, m, tier):
    notes = []
    if kind in ("slap", "clap", "soft", "thwack", "thud", "impact"):
        if kind == "impact":
            # No label: tell it apart by weight and brightness.
            if m.centroid < 900:
                kind = "thud"
            elif tier == nt.LOUD and m.centroid > 2500:
                kind = "thwack"
            else:
                kind = "slap"
        if kind == "slap":
            kind, s = ("smack", P.IMPACT["smack"]) if m.centroid < 1800 else ("slap", P.IMPACT["slap"])
        else:
            s = P.IMPACT[kind]
        s = nt.pick(s, 0)
    elif kind == "wet":
        if m.dur >= 0.35:
            kind, s = "wet, full length", nt.pick(P.WET["seat"], 0)
        elif m.fall_ms <= 20:
            kind, s = "wet, seal breaking", nt.pick(P.WET["seal"], 0)
        elif tier == nt.LOUD or m.low_share > 0.6:
            kind, s = "wet, thick", nt.pick(P.WET["squelch"], 0)
        elif m.attack_ms <= 20:
            kind, s = "wet, parting", nt.pick(P.WET["part"], 0)
        else:
            kind, s = "wet", nt.pick(P.WET["slick"], 0)
    elif kind == "drip":
        s = nt.pick(P.WET["drip"], 0)
    elif kind == "mouth":
        if m.fall_ms <= 20 and m.dur < 0.15:
            kind, s = "mouth, coming off", nt.pick(P.MOUTH["pop"], 0)
        elif m.dur >= 0.3:
            kind, s = "mouth, suction", nt.pick(P.MOUTH["suck"], 0)
        else:
            kind, s = "mouth, the drag", nt.pick(P.MOUTH["drag"], 0)
    elif kind == "bite":
        s = nt.pick(P.BITE, 0)
    else:
        return kind, None, notes
    return kind, nt.case(s, tier, mid_capital=False) if tier == nt.LOUD else s, notes


def spell_room(kind, m, tier):
    if kind == "creak":
        s = nt.pick(P.FURNITURE["creak"], length_level(m.dur, (0.25, 0.6)))
    elif kind == "springs":
        s = nt.pick(P.FURNITURE["springs"], 0)
    elif kind == "zipper":
        s = nt.pick(P.FABRIC["zipper"], 0)
    elif kind == "sheets":
        s = nt.pick(P.FABRIC["sheets"], 0)
    elif kind == "water":
        s = nt.pick(P.FURNITURE["water"], 0)
    elif kind == "headboard":
        s = nt.pick(P.FURNITURE["headboard"], 0)
    elif kind == "hum":
        s = nt.pick(P.ROOM_HUM, 0)
    else:
        return None
    return s.upper() if tier == nt.LOUD else s


# --- Putting it together ---------------------------------------------------


def best(scores, table):
    hits_ = [(p, table[l], l) for l, p in scores.items() if l in table]
    if not hits_:
        return 0.0, None, ""
    p, kind, label = max(hits_, key=lambda x: x[0])
    return p, kind, label


def tier_of(peak_db, ref_db, quiet_gap=18.0, loud_gap=5.0):
    if peak_db <= ref_db - quiet_gap:
        return nt.QUIET
    if peak_db >= ref_db - loud_gap:
        return nt.LOUD
    return nt.MID


def levels(db):
    """The room's floor, the loud reference, and the line a sound has to cross."""
    floor_db = float(np.percentile(db, 20))
    active = db[db > floor_db + 10]
    ref_db = float(np.percentile(active, 95)) if active.size else float(db.max())
    return floor_db, ref_db, max(floor_db + 9, ref_db - 45)


def find(y, words, split_hz=165.0, names=("high voice", "low voice"), log=print):
    """Every sound in the clip that isn't a word."""
    db = audio.rms_db(y)
    floor_db, ref_db, thresh = levels(db)

    word_spans = [(w.start, w.end) for w in words]
    spans = []
    for a, b in regions(db, thresh):
        spans.extend(split_on_dips(db, a, b))
    spans = minus(spans, word_spans)
    log(f"  {len(spans)} stretches of sound outside the words")

    clips = [y[int(a * audio.SR) : int(b * audio.SR)] for a, b in spans]
    scores = audio.classify(clips) if clips else []

    sounds = []
    for (a, b), sc in zip(spans, scores):
        s = one(y, db, a, b, sc, ref_db, split_hz, names)
        if s:
            sounds.append(s)

    # Sharp hits ride under everything else, so they're found on their own,
    # on the percussive part of the sound. Inside a word they're left alone.
    perc, hit_times = hits(y, audio.SR, words)
    taken = [(s.start - 0.05, s.end + 0.05) for s in sounds if s.track in ("body", "room")]
    voiced = [(s.start, s.end) for s in sounds if s.track in ("voice", "breath")]
    pad_words = [(a - 0.06, b + 0.12) for a, b in word_spans]
    hit_times = [t for t in hit_times if not inside(t, pad_words) and not inside(t, taken)]
    log(f"  {len(hit_times)} sharp hits to check")
    hit_clips = [perc[max(0, int((t - 0.03) * audio.SR)) : int((t + 0.2) * audio.SR)] for t in hit_times]
    hit_scores = audio.classify(hit_clips) if hit_clips else []
    for t, sc in zip(hit_times, hit_scores):
        kp, kkind, klabel = best(sc, BODY_LABELS)
        rp, rkind, rlabel = best(sc, ROOM_LABELS)
        vp, _, _ = best(sc, VOICE_LABELS)
        a, b = max(0.0, t - 0.01), t + 0.12
        m = audio.measure(y, db, a, b, pitch=False)
        sharp = m.onset_ms <= 8 and m.decay_ms <= 80
        strong = max(kp, rp) >= 0.08 and max(kp, rp) >= vp
        if inside(t, voiced) and max(kp, rp) < 0.25:
            continue
        if not strong and not (sharp and vp < 0.2):
            continue
        tier = tier_of(m.peak_db, ref_db)
        if rp > kp and rkind:
            s = spell_room(rkind, m, tier)
            src = ROOM_SOURCE.get(rkind, "the room")
            sounds.append(Sound(a, b, "room", rkind, src, s, tier, m, rlabel, rp))
            continue
        wet = any(sc.get(l, 0) >= 0.05 for l in ("Squish", "Liquid", "Slosh", "Splash, splatter"))
        kind = kkind if (kp >= 0.08 and kkind in IMPACT_KINDS) else "impact"
        kind, s, notes = spell_body(kind, m, tier)
        sounds.append(Sound(a, b, "body", kind, "skin", s, tier, m, klabel if kp >= 0.08 else "", kp, notes=notes, wet=wet))

    sounds.sort(key=lambda s: s.start)
    return dedupe(sounds), ref_db, floor_db


ROOM_SOURCE = {"creak": "bed / furniture", "springs": "bed springs", "zipper": "fabric", "sheets": "sheets",
               "water": "water", "headboard": "headboard / wall", "hum": "the room"}


def inside(t, spans):
    return any(a <= t <= b for a, b in spans)


def one(y, db, a, b, sc, ref_db, split_hz, names):
    """Say what one stretch of sound is and spell it."""
    m = audio.measure(y, db, a, b)
    tier = tier_of(m.peak_db, ref_db)
    vp, vkind, vlabel = best(sc, VOICE_LABELS)
    bp, bkind, blabel = best(sc, BREATH_LABELS)
    kp, kkind, klabel = best(sc, BODY_LABELS)
    rp, rkind, rlabel = best(sc, ROOM_LABELS)
    voice = names[0] if m.f0 >= split_hz else names[1] if m.f0 > 0 else "voice"

    # Body and room: the classifier is sure, or it's plainly a hit.
    top_p, top_track = max((vp, "voice"), (bp, "breath"), (kp, "body"), (rp, "room"))
    if top_track == "room" and top_p >= 0.1 and m.voiced < 0.4:
        if not rkind:
            if rlabel in ("Music", "Television"):
                return None  # what's playing in the room isn't the scene's sound
            return Sound(a, b, "room", rlabel.lower(), "the room", None, tier, m, rlabel, rp,
                         notes=["no spelling in the pool"])
        s = spell_room(rkind, m, tier)
        return Sound(a, b, "room", rkind, ROOM_SOURCE.get(rkind, "the room"), s, tier, m, rlabel, rp)
    if (top_track == "body" and top_p >= 0.1 and m.voiced < 0.4) or (impact_like(m) and max(vp, bp) < 0.3):
        kind = kkind if (kp >= 0.08 and kkind) else "impact"
        kind, s, notes = spell_body(kind, m, tier)
        src = "mouth" if kind.startswith("mouth") or kind == "bite" else "wet" if kind.startswith("wet") or kind == "drip" else "skin"
        return Sound(a, b, "body", kind, src, s, tier, m, klabel if kp >= 0.08 else "", kp, notes=notes)

    is_voiced = m.voiced >= 0.35 or (vp >= max(bp, 0.15) and m.voiced >= 0.15)
    if is_voiced:
        if m.dur < 0.1:
            return None  # too short to be a sound anybody made on purpose
        ph = audio.phones(y[int(a * audio.SR) : int(b * audio.SR)])
        ipa = " ".join(t for t, _ in ph)
        core, h_lead, k_end, nasal_end = shape_of(ph)
        notes = []
        if core is None:
            core = shape_from_formants(m)
            if core:
                notes.append("mouth shape from formants")
        if bkind in ("gag", "cough", "clear") and bp > vp:
            kind, s, n2 = spell_breath(bkind, m, core, tier)
            return Sound(a, b, "breath", kind, "throat", s, tier, m, blabel, bp, ipa, core or "", notes + n2)
        kind0 = vkind or "voice"
        if kind0 in ("laugh", "giggle"):
            if kind0 == "giggle":
                s = nt.pick(P.LAUGH["giggle"], 0)
            elif tier == nt.LOUD and m.dur < 0.4:
                s = nt.pick(P.LAUGH["bark"], 1)
            elif m.voiced < 0.5:
                s = nt.pick(P.LAUGH["breathy"], 0)
            else:
                s = nt.pick(P.LAUGH["bark"], 0)
            return Sound(a, b, "voice", "laugh", voice, s, tier, m, vlabel, vp, ipa, core or "", notes)
        if kind0 in ("voice", "cry"):
            kind0 = "moan"
        kind, s, n2 = spell_voice(kind0, m, core, h_lead, k_end, nasal_end, tier, m.f0 >= split_hz)
        return Sound(a, b, "voice", kind, voice, s, tier, m, vlabel or blabel, max(vp, bp), ipa, core or "", notes + n2)

    if m.dur < 0.08:
        return None
    kind0 = bkind if bp >= 0.05 else "breath"
    if bp >= 0.05 and bkind is None:
        return Sound(a, b, "breath", blabel.lower(), "breath", None, tier, m, blabel, bp, notes=["no spelling in the pool"])
    kind, s, notes = spell_breath(kind0, m, None, tier)
    src = "throat" if kind in ("cough", "clear", "gag") else "breath"
    return Sound(a, b, "breath", kind, src, s, tier, m, blabel if bp >= 0.05 else "", bp, notes=notes)


def dedupe(sounds):
    """A hit found twice (once as a stretch, once as an onset) is kept once."""
    out = []
    for s in sounds:
        if out and s.track == out[-1].track and s.kind == out[-1].kind and s.start - out[-1].start < 0.06:
            continue
        out.append(s)
    return out


# --- Runs -----------------------------------------------------------------

IMPACT_KINDS = ("slap", "smack", "clap", "soft", "thwack", "thud")


@dataclass
class Run:
    sounds: list
    spelled: str
    track: str
    source: str
    chop: bool
    note: str = ""

    @property
    def start(self):
        return self.sounds[0].start

    @property
    def end(self):
        return self.sounds[-1].end


def runs(sounds, gap_voice=0.7, gap_body=1.2, max_shown=6):
    """Three or more like sounds close together become one run.

    The voice and the body are two tracks and never go in one string
    (style guide, Two tracks). Breath runs with breath, voice with voice,
    skin with skin.
    """
    lanes = {}
    for s in sounds:
        if not s.spelled:
            continue
        if s.track in ("voice", "breath"):
            lane = (s.track, s.source)
        elif s.kind in IMPACT_KINDS:
            lane = (s.track, "impact")
        else:
            lane = (s.track, s.kind)
        lanes.setdefault(lane, []).append(s)
    groups = []
    for lane, ss in lanes.items():
        gap = gap_voice if lane[0] in ("voice", "breath") else gap_body
        cur = [ss[0]]
        for s in ss[1:]:
            if s.start - cur[-1].end <= gap:
                cur.append(s)
            else:
                groups.append(cur)
                cur = [s]
        groups.append(cur)
    out = []
    for g in groups:
        if len(g) < 3:
            out.extend(g)
            continue
        track = g[0].track
        if track in ("body", "room"):
            # The wet-jump: early drives plap, once she floods, fwap.
            wet_from = next((i for i, s in enumerate(g) if s.wet), None)
            skin = g[0].kind in IMPACT_KINDS and sum(s.kind in ("slap", "smack", "clap") for s in g) * 2 >= len(g)
            parts = [g] if (wet_from in (None, 0) or not skin) else [g[:wet_from], g[wet_from:]]
            for k, part in enumerate(parts):
                if len(part) < 3:
                    out.extend(part)
                    continue
                if skin:
                    # Rhythmic skin on skin is hips: plap dry, fwap once it's wet.
                    wet = (len(parts) == 2 and k == 1) or wet_from == 0
                    base = P.IMPACT["wet" if wet else "dry"].forms[0]
                    src = "skin, rhythmic" + (", wet" if wet else "")
                else:
                    base = part[0].spelled.lower()
                    src = part[0].source
                gaps = np.diff([s.start for s in part])
                every = float(np.median(gaps)) if gaps.size else 0.0
                spelled = nt.join_run([base] * 3, chop=True)
                out.append(Run(part, spelled, track, src, True, f"{len(part)} hits, one every {every:.2f} s"))
            continue
        for i in range(0, len(g), max_shown):
            part = g[i : i + max_shown]
            if len(part) < 3:
                out.extend(part)
                continue
            gaps = [b.start - a.end for a, b in zip(part, part[1:])]
            chop = max(gaps) < 0.15 and max(s.dur for s in part) < 0.25
            # Inside a run the sound changes as it goes; each keeps its own case.
            spelled = nt.limit_spikes([s.spelled.strip("()") for s in part])
            if track == "breath" and all(s.kind in ("huff", "pant") for s in part):
                # Short breaths one after another are a pant: hh-hh-hh-hh.
                spelled = [P.PANT.forms[0]] * len(part)
                chop = True
            climbing = part[-1].m.peak_db - part[0].m.peak_db
            note = f"{len(part)} sounds over {part[-1].end - part[0].start:.1f} s"
            if climbing >= 4:
                note += ", climbing"
            elif climbing <= -4:
                note += ", fading"
            out.append(Run(part, nt.join_run(spelled, chop), track, part[0].source, chop, note))
    out.sort(key=lambda x: x.start)
    return out
