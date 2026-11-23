"""Prove the pins on debug's Production paragraph (ProductionParagraphTest in tests/test_structure.py) can fail.

Each case copies skills/debug into a temp tree, changes the paragraph there, points test_structure at the
copy, and runs the pins. A mutation that leaves every pin green means a clause is unpinned. The repo
itself is never touched.

Standard library only.
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_structure  # noqa: E402


def flat_sub(text, phrase, new="", count=1):
    pattern = r"\s+".join(re.escape(word) for word in phrase.split())
    result, n = re.subn(pattern, lambda _m: new, text, count=count)
    if n == 0:
        raise AssertionError(f"phrase not found: {phrase!r}")
    return result


def run_pins(skills_dir):
    with mock.patch.object(test_structure, "SKILLS", skills_dir):
        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(test_structure.ProductionParagraphTest).run(result)
    return result


class ProductionPinMutationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="production-pins-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.skills = self.tmp / "skills"
        shutil.copytree(ROOT / "skills" / "debug", self.skills / "debug")
        self.skill = self.skills / "debug" / "SKILL.md"

    def caught(self, edit):
        original = self.skill.read_text(encoding="utf-8")
        mutated = edit(original)
        self.assertNotEqual(original, mutated, "the mutation changed nothing")
        self.skill.write_text(mutated, encoding="utf-8")
        try:
            result = run_pins(self.skills)
        finally:
            self.skill.write_text(original, encoding="utf-8")
        self.assertTrue(result.failures or result.errors, "the mutation left every pin green")

    def test_baseline_is_green(self):
        result = run_pins(self.skills)
        self.assertEqual((result.failures, result.errors), ([], []))

    def test_each_clause_deleted_is_caught(self):
        for clause in test_structure.ProductionParagraphTest.CLAUSES:
            with self.subTest(clause=clause[:60]):
                self.caught(lambda t: flat_sub(t, clause))

    def test_the_old_sentence_comes_back(self):
        self.caught(lambda t: flat_sub(
            t, "one command per block, never two commands joined with `;` or `&&` (a `cd` into the right folder on its own line above the command is fine). Under each block, say what you're looking for in its output.",
            "one per block, and say what you're looking for in the output."))

    def test_joined_commands_are_allowed_again(self):
        self.caught(lambda t: flat_sub(t, "never two commands joined with `;` or `&&`", "joined with `;` if short"))

    def test_the_cd_allowance_is_dropped_or_widened(self):
        self.caught(lambda t: flat_sub(t, "(a `cd` into the right folder on its own line above the command is fine)"))
        self.caught(lambda t: flat_sub(t, "a `cd` into the right folder on its own line above the command is fine", "a `cd` joined with `&&` is fine"))

    def test_what_to_look_for_goes_to_the_end_instead_of_under_each_block(self):
        self.caught(lambda t: flat_sub(t, "Under each block, say what you're looking for in its output.", "At the end, say what you're looking for."))

    def test_read_only_allows_a_redirect_or_tee(self):
        self.caught(lambda t: flat_sub(t, "no redirect into a file, no `tee`", "a redirect into a file is fine"))
        self.caught(lambda t: flat_sub(t, "no redirect into a file, no `tee`", "no redirect into a file"))
        self.caught(lambda t: flat_sub(t, "Read-only means nothing is written on the server either: ", "Read-only means no change to the app: "))

    def test_the_output_is_no_longer_pasted_back(self):
        self.caught(lambda t: flat_sub(t, "The user pastes the output back, or the part around the time in question.", "Ask them to save it to a file."))

    def test_the_user_stops_running_the_commands(self):
        self.caught(lambda t: flat_sub(t, "The user runs every production command.", "You run the read-only production commands."))

    def test_changing_production_state_is_allowed(self):
        self.caught(lambda t: flat_sub(t, "Never change production state to investigate it.", "Change production state if it helps."))

    def test_the_clauses_are_reordered(self):
        self.caught(lambda t: flat_sub(t, "Anything that opens an editor uses `vi`. Never change production state to investigate it.",
                                       "Never change production state to investigate it. Anything that opens an editor uses `vi`."))


if __name__ == "__main__":
    unittest.main()
