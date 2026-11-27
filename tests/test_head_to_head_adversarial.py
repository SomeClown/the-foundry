"""Adversarial round on the decoy_listed_live tuning in evals-expensive/compare.py: a plain sentence straight above a
list is its lead-in whatever it ends with, and "must not come back" / "must not return" are dead phrases.

Each loosening can only turn a live decoy into a cleared one, so the question is whether a made-up decoy (one listed
as live, which the scorer must count) can now pass. Tests named ..._today pin an accepted limit; the others must hold.
Loads compare.py and the key from evals-expensive; no network, no model session. Standard library only.
"""

import importlib.util
import json
import unittest
from pathlib import Path

EXPENSIVE = Path(__file__).resolve().parent.parent / "evals-expensive"
spec = importlib.util.spec_from_file_location("compare_under_test", EXPENSIVE / "compare.py")
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)
KEY = json.loads((EXPENSIVE / "head-to-head-key.json").read_text(encoding="utf-8"))
TOKEN = KEY["decoys"][0]["token"]
LIVE = [("decoy", TOKEN)]


def decoys(*lines):
    return [x for x in compare.made_up("\n".join(lines) + "\n", KEY) if x[0] == "decoy"]


def item(indent=0):
    return " " * indent + "- `%s`" % TOKEN


class MustNotReturnInsideALongerPhraseTest(unittest.TestCase):
    def test_must_not_return_followed_by_what_is_not_returned_does_not_make_the_list_dead(self):
        # "must not return an error" says the routes work; a decoy listed under it is a live claim and must score as made up
        for sentence in ("These calls must not return an error:", "These calls must not return an error.", "These calls must not return errors.",
                         "Everything below must not return a 5xx.", "Calls that must not return errors are these:"):
            for lines in ((sentence, item()), (sentence, "", item())):
                with self.subTest(lines=lines):
                    self.assertEqual(decoys(*lines), LIVE)

    def test_must_not_return_an_error_on_a_parent_bullet_does_not_clear_the_decoys_under_it(self):
        self.assertEqual(decoys("- These routes are live and must not return 404:", item(2)), LIVE)

    def test_the_documents_own_wording_still_clears(self):
        for sentence in ("They are three paths that must not return:", "Three paths that must not come back."):
            with self.subTest(sentence=sentence):
                self.assertEqual(decoys(sentence, item()), [])


class StraightAboveLeadInTest(unittest.TestCase):
    def test_a_live_sentence_straight_above_a_list_leaves_the_decoy_live(self):
        for lines in (("These routes are live.", item()), ("These routes are live:", item()), ("These routes are live", item(2))):
            with self.subTest(lines=lines):
                self.assertEqual(decoys(*lines), LIVE)

    def test_a_dead_sentence_two_lines_above_with_a_blank_between_does_not_clear_a_list_with_no_colon(self):
        self.assertEqual(decoys("These routes were removed.", "", item()), LIVE)

    def test_a_dead_sentence_above_a_live_colon_lead_in_does_not_clear(self):
        # the lead-in is the nearest line, with or without a blank line before the dead sentence
        for between in ((), ("",)):
            with self.subTest(between=between):
                self.assertEqual(decoys("The old gateway is deprecated.", *between, "The live routes:", item()), LIVE)

    def test_a_dead_word_two_lines_above_with_the_live_colon_line_in_between_does_not_clear(self):
        self.assertEqual(decoys("- Routes:", "  - group a", item(4)), LIVE)

    def test_a_nested_list_under_a_dead_parent_is_cleared(self):
        self.assertEqual(decoys("- Removed routes:", "  - group a", item(4)), [])

    # accepted limits: the lead-in is read as one line, so a dead word about something else in it clears the list. The
    # colon form did this before the tuning; the straight-above form only extends it to a sentence with no colon.

    def test_a_dead_word_about_something_else_in_a_colon_lead_in_clears_the_list_today(self):
        self.assertEqual(decoys("The removed dashboard aside, these routes are live:", item()), [])

    def test_a_dead_word_about_something_else_in_a_plain_sentence_straight_above_clears_the_list_today(self):
        self.assertEqual(decoys("The removed dashboard aside, these routes are live.", item()), [])
        self.assertEqual(decoys("Grep found nothing removed.", "- `%s` serves traffic" % TOKEN), [])


if __name__ == "__main__":
    unittest.main()
