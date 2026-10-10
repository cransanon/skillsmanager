"""Notation from the style guide, sounds.md section 1, applied to a pool form.

Length: stretch the vowel already in it, three letters of stretch at most.
Volume: case climbs, oh -> Oh -> OH. ! is a spike, one or two in a run.
Tempo: hyphens chop, em dashes carry.
Cut off: em dash at the end.
Rising pitch: ? and ?! at volume.
Swallowed: parentheses.
Case shift inside one sound: ah—AH!
Consonant stacks cap at two before they read as typos.

On the page every sound goes in italics between em dashes: —*glk*—.
"""

import re

from .pool import Spelling

QUIET, MID, LOUD = "quiet", "mid", "loud"
MAX_STRETCH = 3
VOWELS = "aeiou"


def pick(sp: Spelling, level: int) -> str:
    """Pool form for a length level 0..3.

    Pool forms are used first. Past the longest pool form, the hold letter
    is repeated, never more than three letters past the shortest form.
    """
    level = max(0, level)
    if level < len(sp.forms):
        return sp.forms[level]
    form = sp.forms[-1]
    if not sp.hold:
        return form
    base_len = len(sp.forms[0])
    extra = min(level - (len(sp.forms) - 1), MAX_STRETCH - (len(form) - base_len))
    if extra <= 0:
        return form
    i = form.rfind(sp.hold)
    if i < 0:
        return form
    return form[: i + 1] + sp.hold * extra + form[i + 1 :]


def cap_stacks(s: str) -> str:
    """Two of a consonant before a stop is the cap: nngh, not nnnnngh.

    Pool forms that spell a longer stack themselves (hnnng, unnnggh) are
    left as the pool wrote them; this only guards generated stretch.
    """
    return re.sub(r"([bcdfjklnpqrstvwxyz])\1{2,}(?=[gk])", r"\1\1", s)


def has_caps(s: str) -> bool:
    return any(c.isupper() for c in s)


def case(s: str, tier: str, mid_capital: bool = True) -> str:
    """oh -> Oh -> OH. Forms the pool already capitalised keep their case."""
    if has_caps(s):
        return s
    if tier == LOUD:
        return s.upper()
    if tier == MID and mid_capital:
        for i, c in enumerate(s):
            if c.isalpha():
                return s[:i] + c.upper() + s[i + 1 :]
    return s


def spike(s: str) -> str:
    if s.endswith("!") or s.endswith("—"):
        return s
    return s + "!"


def rise(s: str, tier: str) -> str:
    s = s.rstrip("!")
    return s + ("?!" if tier == LOUD else "?")


def cut(s: str) -> str:
    if s.endswith("—") or s.endswith("-"):
        return s
    return s.rstrip("!?") + "—"


def shift(s: str) -> str:
    """ah -> ah—AH!  The volume arriving inside one sound."""
    low = s.lower().rstrip("!?—")
    return f"{low}—{low.upper()}!"


def swallow(s: str) -> str:
    return f"({s.rstrip('!')})"


def page(s: str) -> str:
    """Italic between em dashes. Swallowed sounds keep their parentheses
    inside the italics, as the pool writes them."""
    return f"—*{s}*—"


def join_run(sounds, chop: bool) -> str:
    """A run of three or more. Hyphens chop, em dashes carry."""
    sep = "-" if chop else "—"
    inner = sep.join(x.rstrip("—") for x in sounds)
    return page(inner)


def limit_spikes(sounds, keep: int = 2):
    """! is a spike, one or two in a run, not every sound."""
    out, n = [], 0
    for x in sounds:
        if x.endswith("!") and not x.endswith("!!"):
            n += 1
            if n > keep:
                x = x.rstrip("!")
        out.append(x)
    return out


def stretch_word(word: str, level: int) -> str:
    """A spoken word held long: the vowel stretched, three letters at most.

    The pool's own stretched words (sounds.md 7) are used as written.
    """
    if level <= 0:
        return word
    level = min(level, MAX_STRETCH)
    pool = {"please": "pleaase", "fuck": "fuuuck", "yes": "yesss", "good": "goood"}
    core = re.sub(r"[^A-Za-z']", "", word)
    if core.lower() in pool:
        held = pool[core.lower()]
        if core.isupper():
            held = held.upper()
        elif core[:1].isupper():
            held = held[:1].upper() + held[1:]
        return word.replace(core, held, 1)
    # y is a vowel only after a consonant ("my", "baby"), never leading ("you").
    groups = [m for m in re.finditer(r"[aeiouAEIOU]+|(?<=[b-df-hj-np-tv-zB-DF-HJ-NP-TV-Z])[yY]", word)]
    if not groups:
        return word
    g = groups[-1]
    alpha_end = max(i for i, ch in enumerate(word) if ch.isalpha()) + 1
    # A final silent e is not the held vowel ("please" holds the ea).
    if len(groups) > 1 and g.group().lower() == "e" and g.end() == alpha_end:
        g = groups[-2]
    # A vowel ending the word is held at its end (youuu), otherwise at its start (pleeease).
    at = g.end() - 1 if g.end() == alpha_end else g.start()
    c = word[at]
    return word[: at + 1] + c * level + word[at + 1 :]
