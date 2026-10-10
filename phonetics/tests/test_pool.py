"""Every spelling the transcriber can put down is in the style guide's pool.

    python tests/test_pool.py [path/to/style-guide]

Finds the style guide from the argument, $STYLE_GUIDE_DIR, or the synced
skills folder. Skips when it can't find one.
"""

import glob
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from scribe import pool  # noqa: E402


def style_guide_dir():
    for c in [os.environ.get("STYLE_GUIDE_DIR", "")] + glob.glob(
        os.path.expanduser("~/.claude/skills/**/style-guide"), recursive=True
    ):
        if c and os.path.exists(os.path.join(c, "references", "sounds.md")):
            return c
    return None


def pool_text(d):
    text = ""
    for f in ("sounds.md", "room-sounds.md"):
        with open(os.path.join(d, "references", f), encoding="utf-8") as fh:
            text += fh.read()
    return text


def in_pool(form, text):
    """The form stands as its own spelling in the pool, not inside a longer one."""
    return re.search(r"(?<![A-Za-z])" + re.escape(form) + r"(?![A-Za-z])", text) is not None


class PoolTest(unittest.TestCase):
    def setUp(self):
        self.dir = style_guide_dir()
        if not self.dir:
            self.skipTest("style guide not found; set STYLE_GUIDE_DIR")
        self.text = pool_text(self.dir)

    def test_every_form_is_in_the_pool(self):
        missing = [f for f in pool.every_form() if not in_pool(f, self.text)]
        self.assertEqual(missing, [], f"not in the pool: {missing}")

    def test_negative_control(self):
        # The check above has to be able to fail: made-up and stretched-past-
        # the-pool forms are caught, and a short form isn't found inside a longer one.
        self.assertFalse(in_pool("blorpf", self.text))
        self.assertFalse(in_pool("plapp", self.text))
        self.assertFalse(in_pool("schlorpp", self.text))
        self.assertTrue(in_pool("plap", self.text))


if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        os.environ["STYLE_GUIDE_DIR"] = sys.argv.pop(1)
    unittest.main(verbosity=2)
