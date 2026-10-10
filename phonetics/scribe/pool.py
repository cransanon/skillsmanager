"""The spellings the transcriber is allowed to put on the page.

Every form below is copied from the style guide's sound pool:
style-guide/references/sounds.md and room-sounds.md. The transcriber never
builds a sound out of letters on its own. It picks a form from this table,
then applies the notation from sounds.md section 1 on top (stretch, case,
chop, cut, rise, swallow).

A sound with no spelling in the pool is reported by name and left unspelled.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Spelling:
    # Forms short to long, verbatim from the pool.
    forms: tuple
    # Letter that may be held longer than the longest pool form
    # ("stretch the vowel already in it", sounds.md 1). None = never stretched.
    hold: str | None = None
    # Where in the pool it comes from.
    where: str = ""


S = Spelling

# --- Her voice / his voice (sounds.md 2, 3) -------------------------------

MOAN = {
    "a": S(("ah", "ahh", "ahhh"), "h", "2 Moan"),
    "aa": S(("aah", "aaah"), "a", "2 Moan"),
    "o": S(("oh", "ohh"), "h", "2 Moan / 3 Groan"),
    "u": S(("ooh", "ooooh"), None, "2 Moan"),
}
PEAK = {
    "plain": S(("AWH",), None, "2 Peak moan"),
    "falling": S(("AWHuh",), None, "2 Peak moan"),
}
CRY = {
    "a": S(("ah!", "aah!"), None, "2 Cry out"),
    "o": S(("oh!",), None, "2 Cry out"),
}
SCREAM = S(("Ah!!", "Aahh!!", "AAAHH!!"), None, "2 Scream")
WAIL = S(("aahh", "aaaahhh"), None, "2 Wail")
YELP = {
    "a": S(("ah!",), None, "2 Yelp"),
    "o": S(("ow!",), None, "2 Yelp"),
    "cut": S(("ahk",), None, "2 Yelp"),
}
SQUEAL = {
    "i": S(("ih!",), None, "2 Squeal"),
    "n": S(("nnh!",), None, "2 Squeal"),
}
KEEN = {
    "i": S(("ihhhh—",), None, "2 Keen"),
    "n": S(("nnnnhh—",), None, "2 Keen"),
}
GROAN = {
    "uh": S(("uhh", "uuhhhh"), None, "2 Groan / 3 Groan"),
    "o": S(("ohh",), "h", "2 Groan / 3 Groan"),
    "n": S(("unh",), None, "2 Groan"),
}
GRUNT = {
    "n": S(("hng", "hnnng"), None, "2 Grunt / 3 Short grunt"),
    "uh": S(("unh",), None, "3 Thrust grunt"),
    "gut": S(("ungh", "unnnggh"), None, "2 Guttural / 3 From the gut"),
    "o": S(("oogh", "oooghhh"), None, "2 Guttural / 3 From the gut"),
    "cut": S(("ugh",), None, "2 Grunt / 3 Short grunt"),
    "teeth": S(("ngh",), None, "2 Grunt"),
    "air": S(("khh",), None, "2 Grunt"),
}
STRAIN = S(("UHN!",), None, "2 Strain")
WHIMPER = {
    "m": S(("mm",), "m", "2 Whimper"),
    "n": S(("nnh", "nnnnh"), None, "2 Whimper"),
    "mn": S(("mn",), None, "2 Whimper"),
}
WHINE = S(("ehh", "ehhhhh"), None, "2 Whine")
SWALLOWED = S(("ngh", "nngh"), None, "2 Swallowed moan")
HUM = S(("mm", "mmh", "mmmmh"), None, "2 Hum")
MUFFLED = S(("mmph", "mmmphh"), None, "2 Muffled")
LIMIT = S(("mmpf", "mmpfff"), None, "2 The limit")

# "H before the sound" and "H after the sound" (sounds.md 4 Breath).
H_BEFORE = {"ah": "hah", "oh": "hoh", "nnh": "hnnh", "uhh": "huhh"}
H_AFTER = {"ahh": "ahh-hh", "ohh": "ohh-h"}

# --- Breath (sounds.md 4) --------------------------------------------------

GASP = {
    "voiced": S(("hah!",), None, "4 Gasp"),
    "catch": S(("hhk!", "h-hhk!"), None, "4 Gasp"),
}
SHARP_IN = {
    "s": S(("sss—",), None, "4 Sharp in through the teeth"),
    "t": S(("tss—",), None, "4 Sharp in through the teeth"),
}
PANT = S(("hh",), None, "4 Pant")
RAGGED = S(("hh…hh", "h-hh—hh…hh"), None, "4 Ragged")
SHAKY = S(("ha-a-a", "h-ha-a-a-h"), None, "4 Shaky exhale")
BREATHY = S(("hahh", "haaahh"), None, "4 Breathy moan")
HUFF = S(("hff", "huff"), None, "4 Huff / 3 Hard breath out")
SIGH = S(("haa", "haaah"), None, "4 Sigh")
CAUGHT = S(("h-", "hh-"), None, "4 Caught")

# --- Throat (sounds.md 5) --------------------------------------------------

CATCH = S(("hk-", "hhk—"), None, "5 Choke / catch")
GAG = S(("glk glk",), None, "5 Gag")
ROUGH = S(("kh", "hrk"), None, "5 Rough break")
SWALLOW = S(("gllp",), None, "5 Swallow")
COUGH = S(("khh— hh— kh",), None, "5 Cough / sputter")
CLEAR = S(("khm", "ahem"), None, "5 Clearing her throat")
NOSE = S(("hnh",), None, "5 Nose exhale")
SCOFF = S(("hmph",), None, "4 Scoff")

# --- Laughing (sounds.md 6) ------------------------------------------------

LAUGH = {
    "breathy": S(("heh", "hehh"), None, "6 Breathy"),
    "bark": S(("hah", "HA"), None, "6 Bark"),
    "giggle": S(("hih-hih", "hh—hah"), None, "6 Giggle"),
}

# --- The body's track (sounds.md 9, 11, 12, 13) ---------------------------

MOUTH = {
    "drag": S(("slk",), None, "9 Mouth on him"),
    "suck": S(("shlup",), None, "9 Mouth on him"),
    "full": S(("mnomph",), None, "9 Mouth on him"),
    "seal": S(("schlk",), None, "9 Mouth on him"),
    "pop": S(("pop",), None, "9 Mouth on him"),
    "spit": S(("pth",), None, "9 Mouth on him"),
}
IMPACT = {
    "dry": S(("plap",), None, "11 Skin and impact"),
    "wet": S(("fwap",), None, "11 Skin and impact (the wet-jump)"),
    "soft": S(("paf",), None, "11 Skin and impact"),
    "clap": S(("clap",), None, "11 Skin and impact"),
    "smack": S(("smack",), None, "11 Skin and impact"),
    "slap": S(("slap",), None, "11 Skin and impact"),
    "thwack": S(("thwack",), None, "11 Skin and impact"),
    "thud": S(("thud",), None, "11 Skin and impact"),
}
WET = {
    "part": S(("schlick",), None, "12 Wet"),
    "slick": S(("slick",), None, "12 Wet"),
    "seal": S(("schlk",), None, "12 Wet"),
    "squelch": S(("squelch",), None, "12 Wet"),
    "seat": S(("schlorp",), None, "12 Wet"),
    "drip": S(("drip",), None, "12 Wet"),
    "tick": S(("tck",), None, "12 Wet"),
}
BITE = S(("chmp",), None, "13 Bite")

# --- Fabric, furniture, room (sounds.md 14, 15; room-sounds.md) -----------

FABRIC = {
    "zipper": S(("zzzzip",), None, "room-sounds"),
    "sheets": S(("shff", "fss"), None, "14 Fabric"),
    "elastic": S(("snap",), None, "14 Fabric"),
    "buckle": S(("clnk",), None, "room-sounds"),
}
FURNITURE = {
    "creak": S(("crk", "creak", "creeeak"), None, "15 Furniture / room-sounds"),
    "springs": S(("sqk", "sqk-sqk"), None, "15 Furniture"),
    "drop": S(("poomf",), None, "15 Furniture"),
    "headboard": S(("tok",), None, "15 Furniture"),
    "wall": S(("thmp",), None, "15 Furniture"),
    "scrape": S(("skrrk",), None, "room-sounds"),
    "knock": S(("tk",), None, "15 Furniture / room-sounds"),
    "water": S(("pshhh",), None, "15 Furniture (shower)"),
}
ROOM_HUM = S(("mmmmmm",), None, "room-sounds (the fridge under the quiet)")


def every_form():
    """Every base form in the table, for the pool check."""
    out = []

    def walk(v):
        if isinstance(v, Spelling):
            out.extend(v.forms)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)

    for name, v in globals().items():
        if name.isupper():
            if name in ("H_BEFORE", "H_AFTER"):
                out.extend(v.values())
            else:
                walk(v)
    return out
