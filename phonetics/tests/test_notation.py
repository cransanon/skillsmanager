"""The notation rules from sounds.md section 1, and the page format.

    python tests/test_notation.py
    python tests/test_notation.py path/to/clip.sounds.md   # also checks an output file
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from scribe import notation as nt  # noqa: E402
from scribe import pool as P  # noqa: E402

OUTPUT = None

# A spelled sound on the page: em dash, italics, em dash. Inside: no asterisk.
SOUND = re.compile(r"—\*([^*]+)\*—")


class Stretch(unittest.TestCase):
    def test_pool_forms_first(self):
        self.assertEqual(nt.pick(P.MOAN["a"], 0), "ah")
        self.assertEqual(nt.pick(P.MOAN["a"], 1), "ahh")
        self.assertEqual(nt.pick(P.MOAN["a"], 2), "ahhh")

    def test_three_letters_of_stretch_at_most(self):
        for sp in (P.MOAN["a"], P.MOAN["o"], P.GROAN["o"], P.WHIMPER["m"], P.MOAN["aa"]):
            longest = nt.pick(sp, 10)
            self.assertLessEqual(len(longest) - len(sp.forms[0]), nt.MAX_STRETCH, longest)

    def test_no_hold_never_grows(self):
        self.assertEqual(nt.pick(P.PEAK["plain"], 3), "AWH")
        self.assertEqual(nt.pick(P.IMPACT["dry"], 3), "plap")

    def test_consonant_stack_cap(self):
        self.assertEqual(nt.cap_stacks("nnnnngh"), "nngh")
        self.assertEqual(nt.cap_stacks("nngh"), "nngh")
        self.assertEqual(nt.cap_stacks("mmmmh"), "mmmmh")  # a held hum isn't a stack before a stop


class Case(unittest.TestCase):
    def test_case_climbs(self):
        self.assertEqual(nt.case("oh", nt.QUIET), "oh")
        self.assertEqual(nt.case("oh", nt.MID), "Oh")
        self.assertEqual(nt.case("oh", nt.LOUD), "OH")

    def test_pool_caps_kept(self):
        self.assertEqual(nt.case("AWHuh", nt.QUIET), "AWHuh")
        self.assertEqual(nt.case("Ah!!", nt.LOUD), "Ah!!")

    def test_shift_inside_one_sound(self):
        self.assertEqual(nt.shift("ah"), "ah—AH!")


class Marks(unittest.TestCase):
    def test_rise(self):
        self.assertEqual(nt.rise("ah", nt.MID), "ah?")
        self.assertEqual(nt.rise("AH!", nt.LOUD), "AH?!")

    def test_cut(self):
        self.assertEqual(nt.cut("ah"), "ah—")
        self.assertEqual(nt.cut("ah!"), "ah—")

    def test_swallow(self):
        self.assertEqual(nt.swallow("mm"), "(mm)")

    def test_spikes_one_or_two_in_a_run(self):
        out = nt.limit_spikes(["ah!", "OH!", "AH!", "OH!"])
        self.assertEqual(sum(x.endswith("!") for x in out), 2)

    def test_scream_marks_untouched(self):
        self.assertEqual(nt.limit_spikes(["Ah!!", "Aahh!!", "AAAHH!!"]), ["Ah!!", "Aahh!!", "AAAHH!!"])


class Page(unittest.TestCase):
    def test_single(self):
        self.assertEqual(nt.page("glk"), "—*glk*—")

    def test_run_carries_on_em_dashes(self):
        self.assertEqual(nt.join_run(["UNH", "UNH", "UNH"], chop=False), "—*UNH—UNH—UNH*—")

    def test_run_chops_on_hyphens(self):
        self.assertEqual(nt.join_run(["hh"] * 4, chop=True), "—*hh-hh-hh-hh*—")

    def test_cut_sound_in_run_has_no_double_dash(self):
        self.assertEqual(nt.join_run(["ah—", "AH", "oh"], chop=False), "—*ah—AH—oh*—")


class Words(unittest.TestCase):
    def test_pool_words(self):
        self.assertEqual(nt.stretch_word("please", 1), "pleaase")
        self.assertEqual(nt.stretch_word("Fuck", 2), "Fuuuck")
        self.assertEqual(nt.stretch_word("yes,", 1), "yesss,")

    def test_vowel_held(self):
        self.assertEqual(nt.stretch_word("no", 2), "nooo")
        self.assertEqual(nt.stretch_word("stop", 1), "stoop")

    def test_leading_y_is_not_a_vowel(self):
        self.assertEqual(nt.stretch_word("you,", 2), "youuu,")
        self.assertEqual(nt.stretch_word("YOU", 1), "YOUU")
        self.assertEqual(nt.stretch_word("baby", 1), "babyy")

    def test_final_silent_e_skipped(self):
        self.assertEqual(nt.stretch_word("there", 1), "theere")

    def test_never_past_three(self):
        self.assertEqual(nt.stretch_word("no", 9), "noooo")

    def test_level_zero(self):
        self.assertEqual(nt.stretch_word("stop", 0), "stop")


class Output(unittest.TestCase):
    """Checks a written transcript, when one is given."""

    def setUp(self):
        if not OUTPUT:
            self.skipTest("no output file given")
        with open(OUTPUT, encoding="utf-8") as fh:
            self.text = fh.read()

    def test_every_sound_italic_between_em_dashes(self):
        # Any italic run that isn't wrapped —* *— is a sound off the format.
        for m in re.finditer(r"(?<![—*])\*(?!\*)([^*\n]+)(?<!\*)\*(?![—*])", self.text):
            word = m.group(1)
            # Leaned-on words inside a spoken line are italics on purpose.
            line = self.text[self.text.rfind("\n", 0, m.start()) + 1 : self.text.find("\n", m.end())]
            self.assertIn('"', line, f"bare italics outside a spoken line: {word!r}")

    def test_no_sound_left_unanchored(self):
        # On the page, each sound line names what made it in bold.
        page = self.text.split("## On the page", 1)[1].split("## Every sound", 1)[0]
        for line in page.splitlines():
            if SOUND.search(line):
                self.assertRegex(line, r"^`\d\d:\d\d\.\d` \*\*[^*]+\*\* — ", line)

    def test_voice_and_body_never_in_one_string(self):
        body = {"plap", "fwap", "paf", "clap", "smack", "slap", "thwack", "thud", "slk", "shlup", "schlk",
                "schlick", "slick", "squelch", "schlorp", "crk", "sqk", "tok"}
        for m in SOUND.finditer(self.text):
            parts = re.split(r"[—\-]", m.group(1).lower())
            kinds = {p.strip("!?() ") in body for p in parts if p.strip("!?() ")}
            self.assertLessEqual(len(kinds), 1, m.group(0))


if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        OUTPUT = sys.argv.pop(1)
    unittest.main(verbosity=2)
