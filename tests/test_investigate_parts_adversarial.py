"""Adversarial round on Task 1 of the steadier-runs batch (AC-3): the text of `investigate` about a last part.

Each test changes an in-memory copy of agents/investigate.md and asks the pins of tests/test_investigate_parts.py
whether one of them goes red. Nothing is written; no model session starts. Standard library only, Python 3.9.
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_investigate_parts as ip  # noqa: E402

ZERO_SENTENCE = "nothing of the block comes under it"
COVERAGE_CLAUSE = (" The report's sections follow it, and its Coverage still gives\n"
                   "`Areas not read: 0 areas, 0 files; see SWEEP IN PARTS at the top.`")
NONE_LEFT = "With none left, this\npart is the last, and its block is only the line `SWEEP IN PARTS: 0 areas not read`\n(see \"The Block\")."


def red_pins(text):
    """The names of the pins that no longer match their section of this text."""
    sections = ip.sections(text)
    return [item for item, heading, pattern in ip.PINS if heading not in sections or not re.search(pattern, sections[heading])]


class LastPartTextMutationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = ip.raw()

    def mutate(self, old, new):
        self.assertIn(old, self.text, "test setup: the anchor is gone from the file")
        return self.text.replace(old, new, 1)

    def test_the_real_file_has_no_red_pin(self):
        self.assertEqual(red_pins(self.text), [])

    def test_turning_the_new_sentence_around_is_found(self):
        """AC-3: 'something of the block comes under it'."""
        self.assertTrue(red_pins(self.mutate(ZERO_SENTENCE, "something of the block comes under it")))

    def test_other_ways_to_let_block_lines_under_the_zero_line_are_found(self):
        """AC-3."""
        for label, new in (("some", "some of the block comes under it"), ("only", "only the Project line comes under it"),
                           ("the block comes", "the block comes under it"), ("a block", "a block may come under it")):
            with self.subTest(change=label):
                self.assertTrue(red_pins(self.mutate(ZERO_SENTENCE, new)))

    def test_dropping_the_coverage_clause_is_found(self):
        """AC-3: the last part's Coverage still carries the zero line."""
        self.assertTrue(red_pins(self.mutate(COVERAGE_CLAUSE, "")))

    def test_turning_the_coverage_clause_around_is_found(self):
        """AC-3."""
        self.assertTrue(red_pins(self.mutate("its Coverage still gives", "its Coverage never gives")))

    def test_dropping_any_one_of_the_six_things_is_found(self):
        """AC-3: each of the six lines the last part leaves out is named; take one out and a pin goes red."""
        six = ("no `To read the rest` sentence", "no `Project:`", "`Focus:`", "`Environment:`", "`Instructions:`",
               "no `Areas not read:` list", "`END OF BLOCK`")
        section = ip.sections(self.text)
        phrase = re.search(r"no `To read the rest` sentence, .*?`END OF BLOCK`", section["The Block"]).group(0)
        for item in six:
            with self.subTest(dropped=item):
                self.assertIn(item, phrase)
                mutated = dict(section)
                mutated["The Block"] = section["The Block"].replace(phrase, phrase.replace(item, "", 1), 1)
                self.assertTrue([i for i, h, pat in ip.PINS if not re.search(pat, mutated[h])])

    def test_the_reading_a_part_clause_turned_around_or_dropped_is_found(self):
        """AC-3."""
        self.assertTrue(red_pins(self.mutate(NONE_LEFT, "")))
        self.assertTrue(red_pins(self.mutate("its block is only the line", "its block is the whole block and the line")))
        self.assertTrue(red_pins(self.mutate("this\npart is the last", "this\npart is not the last")))

    def test_the_old_sentence_is_gone_and_not_hidden_in_other_words(self):
        """AC-3: 'no lines under it' (the old wording) does not stand beside the new."""
        flat = " ".join(self.text.split())
        self.assertNotIn("with no lines under it", flat)

    def test_every_fixed_token_of_the_new_sentence_stays_on_one_line(self):
        for token in ("SWEEP IN PARTS: 0 areas not read", "END OF BLOCK", "Areas not read:", "To read the rest"):
            with self.subTest(token=token):
                self.assertEqual(sum(1 for line in self.text.split("\n") if token in line), len(re.findall(re.escape(token), self.text)))

    # Accepted limit, today's behaviour: a pin matches a phrase inside its section and nothing else. Text added after the
    # phrase, which lets a last part carry a block line again, is compared with nothing. No brief promises a check of it.

    def test_today_a_sentence_added_after_the_zero_sentence_that_lets_end_of_block_back_in_goes_unseen(self):
        mutated = self.mutate("A sweep\nthat fits in one report never carries the block.",
                              "The last part may carry `END OF BLOCK`. A sweep\nthat fits in one report never carries the block.")
        self.assertEqual(red_pins(mutated), [])

    def test_today_a_clause_added_after_the_reading_a_part_clause_goes_unseen(self):
        mutated = self.mutate('(see "The Block").', '(see "The Block"), then `END OF BLOCK`.')
        self.assertEqual(red_pins(mutated), [])


if __name__ == "__main__":
    unittest.main()
