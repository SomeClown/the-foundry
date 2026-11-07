"""Adversarial checks on debug's written pollution procedure.

Two parts. First, the procedure's own commands (step 3's pytest and unittest
lines, step 6's check) are read out of the techniques file and run against the
`debug-polluted-test` fixture in a temp dir, so a change to the procedure is
exercised. Second, mutations of the techniques file and SKILL.md, made on a
temp copy, are run through the pin tests in tests/test_structure.py to see
which wordings the pins fail to guard.

Standard library only, no network, no model sessions.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_structure  # noqa: E402

TECHNIQUES = ROOT / "skills" / "debug" / "references" / "techniques.md"
SCAFFOLD = ROOT / "evals" / "debug-polluted-test" / "scaffold.sh"


def find_pytest_python():
    """An interpreter that can run pytest, or None.

    FOUNDRY_PYTEST_PYTHON first, then this interpreter, then the interpreter named
    on the first line of the `pytest` script on PATH.
    """
    candidates = []
    named = os.environ.get("FOUNDRY_PYTEST_PYTHON")
    if named:
        candidates.append(named)
    candidates.append(sys.executable)
    script = shutil.which("pytest")
    if script:
        try:
            first = Path(script).read_text(encoding="utf-8", errors="replace").splitlines()[0]
        except (OSError, IndexError):
            first = ""
        if first.startswith("#!"):
            candidates.append(first[2:].split()[0])
    for candidate in candidates:
        try:
            done = subprocess.run([candidate, "-m", "pytest", "--version"], capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0:
            return Path(candidate)
    return None


PYTEST_PYTHON = find_pytest_python()
NO_PYTEST = "no interpreter with pytest: set FOUNDRY_PYTEST_PYTHON to one"

UNITTEST_ANCHOR = r"^test_y \(tests.test_x.XTest.test_y\)"
UNITTEST_GREP = f" | grep -E '{UNITTEST_ANCHOR}'"
PYTEST_GREP = " | grep -E '^(PASSED|FAILED|ERROR) tests/test_x.py::test_y( |$)'"

HEADING = "## Pollution: passes alone, fails in the suite"
POLLUTER = "tests.test_a_currency"
QUIET = "tests.test_e_invoice"
VICTIM_MODULE = "tests.test_c_report"
VICTIM_NAME = "test_report_header_uses_dollars"
VICTIM_UNITTEST = f"{VICTIM_MODULE}.ReportTest.{VICTIM_NAME}"
VICTIM_PYTEST = f"tests/test_c_report.py::ReportTest::{VICTIM_NAME}"


def section(text=None):
    text = TECHNIQUES.read_text(encoding="utf-8") if text is None else text
    start = text.index(HEADING)
    return text[start : text.index("## Races", start)]


def step3_commands():
    """The two command lines in step 3's fenced block, as written."""
    block = re.search(r"```\n(.*?)\n\s*```", section(), re.S).group(1)
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    pytest_line = next(line for line in lines if line.startswith("pytest "))
    unittest_line = next(line for line in lines if line.startswith("python3 -m unittest "))
    return pytest_line, unittest_line


def fill_unittest(line, half):
    line = line.replace("<half, as modules>", half)
    line = line.replace("tests.test_x.XTest.test_y", VICTIM_UNITTEST)
    line = line.replace("^test_y ", f"^{VICTIM_NAME} ")
    return line.replace("python3", sys.executable, 1)


def fill_pytest(line, half):
    line = line.replace("<half>", half)
    line = line.replace("tests/test_x.py::test_y", VICTIM_PYTEST)
    return line.replace("pytest", f"{PYTEST_PYTHON} -m pytest", 1)


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pollution-fixture-")
        subprocess.run(["bash", str(SCAFFOLD)], cwd=cls.tmp, check=True, capture_output=True,
                       env={"PATH": os.environ["PATH"]})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def sh(self, command):
        env = {"PATH": os.environ["PATH"], "HOME": str(Path.home()), "PYTHONDONTWRITEBYTECODE": "1"}
        done = subprocess.run(["bash", "-c", command], cwd=self.tmp, env=env, capture_output=True, text=True)
        return done.returncode, done.stdout.strip().splitlines()


class UnittestLineTest(Fixture):
    def test_half_with_the_polluter_shows_the_victim_failed(self):
        _, out = self.sh(fill_unittest(step3_commands()[1], POLLUTER))
        self.assertEqual(len(out), 1, out)
        self.assertTrue(out[0].startswith(VICTIM_NAME) and out[0].endswith("FAIL"), out)

    def test_half_without_the_polluter_shows_the_victim_passed(self):
        _, out = self.sh(fill_unittest(step3_commands()[1], QUIET))
        self.assertEqual(len(out), 1, out)
        self.assertTrue(out[0].startswith(VICTIM_NAME) and out[0].endswith("ok"), out)

    def test_a_half_that_fails_by_itself_does_not_leak_into_the_output(self):
        # A candidate that fails on its own must not show up in the grep.
        broken = Path(self.tmp) / "tests" / "test_b_broken.py"
        broken.write_text("import unittest\n\nclass B(unittest.TestCase):\n"
                          "    def test_b(self):\n        self.fail('x')\n", encoding="utf-8")
        self.addCleanup(broken.unlink)
        _, out = self.sh(fill_unittest(step3_commands()[1], "tests.test_b_broken"))
        self.assertEqual(len(out), 1, out)
        self.assertTrue(out[0].endswith("ok"), out)


@unittest.skipUnless(PYTEST_PYTHON, NO_PYTEST)
class PytestLineTest(Fixture):
    def test_half_with_the_polluter_shows_the_victim_failed(self):
        _, out = self.sh(fill_pytest(step3_commands()[0], "tests/test_a_currency.py"))
        self.assertEqual(len(out), 1, out)
        self.assertTrue(out[0].startswith("FAILED " + VICTIM_PYTEST), out)

    def test_half_without_the_polluter_shows_the_victim_passed(self):
        _, out = self.sh(fill_pytest(step3_commands()[0], "tests/test_e_invoice.py"))
        self.assertEqual(len(out), 1, out)
        self.assertTrue(out[0].startswith("PASSED " + VICTIM_PYTEST), out)


class DecoyTest(Fixture):
    """The victim greps match the victim's full id and nothing that merely starts like it."""

    def setUp(self):
        self.report = Path(self.tmp) / "tests" / "test_c_report.py"
        original = self.report.read_text(encoding="utf-8")
        self.addCleanup(self.report.write_text, original, encoding="utf-8")
        self.report.write_text(
            original
            + f"    def {VICTIM_NAME}2(self):\n        self.assertTrue(True)\n"
            + f"\n\nclass OtherTest(unittest.TestCase):\n    def {VICTIM_NAME}(self):\n"
            + "        self.assertTrue(True)\n",
            encoding="utf-8",
        )

    def test_unittest_grep_skips_a_longer_name_and_a_same_named_method_in_another_class(self):
        # Both decoys run (the list shows them); only the victim's own line comes back.
        _, everything = self.sh(f"{sys.executable} -m unittest -v tests.test_c_report 2>&1")
        self.assertEqual(len([l for l in everything if l.startswith(VICTIM_NAME)]), 3, everything)  # victim, longer name, other class
        for half in (POLLUTER, QUIET):
            with self.subTest(half=half):
                decoys = f"tests.test_c_report.OtherTest tests.test_c_report.ReportTest.{VICTIM_NAME}2"
                _, out = self.sh(fill_unittest(step3_commands()[1], f"{half} {decoys}"))
                self.assertEqual(len(out), 1, out)
                self.assertIn("(" + VICTIM_UNITTEST + ")", out[0])

    @unittest.skipUnless(PYTEST_PYTHON, NO_PYTEST)
    def test_pytest_grep_skips_a_longer_name(self):
        _, out = self.sh(fill_pytest(step3_commands()[0], "tests/test_c_report.py"))
        self.assertEqual(len(out), 1, out)
        self.assertTrue(out[0].startswith("PASSED " + VICTIM_PYTEST), out)


class CheckTest(Fixture):
    """Step 6, done as written: the victim alone, then the polluter and the victim."""

    def test_step_6_lists_both_runs(self):
        body = " ".join(section().split())
        self.assertIn("the victim alone: it passes", body)
        self.assertIn("the polluter, then the victim, in one run with nothing else: the victim fails", body)

    def test_the_victim_alone_passes(self):
        code, out = self.sh(f"{sys.executable} -m unittest -v {VICTIM_UNITTEST} 2>&1")
        self.assertEqual(code, 0, out)

    def test_the_polluter_then_the_victim_fails(self):
        code, out = self.sh(f"{sys.executable} -m unittest -v {POLLUTER} {VICTIM_UNITTEST} 2>&1")
        self.assertNotEqual(code, 0, out)
        self.assertTrue(any(l.startswith(VICTIM_NAME) and l.endswith("FAIL") for l in out), out)

    def test_a_non_polluter_then_the_victim_does_not_fail(self):
        code, out = self.sh(f"{sys.executable} -m unittest -v {QUIET} {VICTIM_UNITTEST} 2>&1")
        self.assertEqual(code, 0, out)

    @unittest.skipUnless(PYTEST_PYTHON, NO_PYTEST)
    def test_the_check_under_pytest(self):
        py = f"{PYTEST_PYTHON} -m pytest -q -p no:randomly -p no:cacheprovider"
        alone, _ = self.sh(f"{py} {VICTIM_PYTEST}")
        both, _ = self.sh(f"{py} tests/test_a_currency.py {VICTIM_PYTEST}")
        self.assertEqual(alone, 0)
        self.assertNotEqual(both, 0)


class OrderTest(unittest.TestCase):
    """The check comes before a polluter is named, and the pins must say so."""

    def test_check_step_precedes_the_reading_step(self):
        body = section()
        self.assertLess(body.index("**The check (required).**"), body.index("**Read what the polluter changes"))

    def test_check_is_framed_as_before_naming(self):
        body = " ".join(section().split())
        self.assertIn("Before you name a polluter", body)


def flat_sub(text, phrase, new="", count=1):
    """Replace a phrase however the file wraps it: whitespace in it matches any run of whitespace."""
    pattern = r"\s+".join(re.escape(word) for word in phrase.split())
    return re.subn(pattern, lambda _m: new, text, count=count)[0]


def pin_suite_result(skills_dir):
    """Run the pin tests from test_structure against a copy of skills/."""
    with mock.patch.object(test_structure, "SKILLS", skills_dir):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(test_structure.DebugPollutionProcedureTest)
        result = unittest.TestResult()
        suite.run(result)
    return result


class PinMutationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pollution-pins-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.skills = self.tmp / "skills"
        shutil.copytree(ROOT / "skills" / "debug", self.skills / "debug")
        self.tech = self.skills / "debug" / "references" / "techniques.md"
        self.skill = self.skills / "debug" / "SKILL.md"

    def mutate(self, path, edit):
        original = path.read_text(encoding="utf-8")
        mutated = edit(original)
        self.assertNotEqual(original, mutated, "the mutation changed nothing")
        path.write_text(mutated, encoding="utf-8")
        result = pin_suite_result(self.skills)
        path.write_text(original, encoding="utf-8")
        return result

    def assertCaught(self, path, edit):
        result = self.mutate(path, edit)
        self.assertTrue(result.failures or result.errors, "mutation left every pin green")

    def test_baseline_pins_are_green(self):
        result = pin_suite_result(self.skills)
        self.assertEqual((result.failures, result.errors), ([], []))

    def test_deleting_each_required_phrase_is_caught(self):
        for phrase in test_structure.DebugPollutionProcedureTest.PHRASES:
            with self.subTest(phrase=phrase):
                self.assertCaught(self.tech, lambda t: flat_sub(t, phrase))

    def test_rewording_each_required_phrase_is_caught(self):
        rewordings = {
            "**The check (required).**": "**The check (optional).**",
            "the victim alone: it passes": "the victim alone: it may pass",
            "the polluter, then the victim, in one run with nothing else": "the polluter, then the victim",
            "not the run's exit code": "and the run's exit code",
        }
        for phrase, new in rewordings.items():
            with self.subTest(phrase=phrase):
                self.assertCaught(self.tech, lambda t: flat_sub(t, phrase, new))

    def test_removing_step_6_entirely_is_caught(self):
        def drop(t):
            return re.sub(r"6\. \*\*The check \(required\)\.\*\*.*?(?=7\. \*\*Read what)", "", t, flags=re.S)
        self.assertCaught(self.tech, drop)

    def test_deleting_the_skill_pointer_is_caught(self):
        self.assertCaught(self.skill, lambda t: re.sub(r"the\s+check\s+under\s+\*Pollution\*\s+in\s+the\s+techniques\s+file",
                                                       "the techniques file", t))

    def test_moving_the_check_after_naming_a_polluter_is_caught(self):
        def move(t):
            step6 = re.search(r"6\. \*\*The check \(required\)\.\*\*.*?(?=7\. \*\*Read what)", t, re.S).group(0)
            t = t.replace(step6, "")
            tail = "If no single file breaks it, but the whole set does"
            return t.replace(tail, step6.replace("6.", "8.", 1) + "\n" + tail, 1)
        self.assertCaught(self.tech, move)

    def test_flipping_before_to_after_naming_is_caught(self):
        self.assertCaught(self.tech, lambda t: flat_sub(t, "Before you name a polluter", "After you name a polluter"))

    def test_deleting_the_unittest_command_is_caught(self):
        def drop(t):
            return "\n".join(l for l in t.splitlines() if "python3 -m unittest -v" not in l) + "\n"
        self.assertCaught(self.tech, drop)

    def test_deleting_the_suspect_sentence_is_caught(self):
        self.assertCaught(self.tech, lambda t: flat_sub(t, "call it the suspect"))

    def test_deleting_the_own_commands_phrase_is_caught(self):
        self.assertCaught(self.tech, lambda t: flat_sub(
            t, "as commands of their own, not inside a loop or alongside other runs"))

    def test_allowing_a_loop_is_caught(self):
        self.assertCaught(self.tech, lambda t: flat_sub(t, "not inside a loop", "inside a loop"))

    def test_moving_the_suspect_sentence_to_step_6_is_caught(self):
        def move(t):
            t = flat_sub(t, "until step 6 holds, call it the suspect, in your notes and to the user.", "")
            return flat_sub(t, "and show both commands and their results:",
                            "and show both commands and their results (call it the suspect):")
        self.assertCaught(self.tech, move)

    def test_moving_the_suspect_sentence_after_step_7_is_caught(self):
        def move(t):
            t = flat_sub(t, "until step 6 holds, call it the suspect, in your notes and to the user.", "")
            return t.replace("If no single file breaks it, but the whole set does",
                             "Until step 6 holds, call it the suspect.\nIf no single file breaks it, but the whole set does", 1)
        self.assertCaught(self.tech, move)

    def test_moving_the_suspect_sentence_into_step_5_is_caught(self):
        def move(t):
            t = flat_sub(t, "until step 6 holds, call it the suspect, in your notes and to the user.", "")
            return flat_sub(t, "5. **Then inside that file,**", "5. **Then inside that file,** call it the suspect,")
        self.assertCaught(self.tech, move)

    def test_dropping_before_you_name_a_polluter_is_caught(self):
        self.assertCaught(self.tech, lambda t: flat_sub(t, "Before you name a polluter,", ""))

    def test_rewrapping_a_pinned_phrase_stays_green(self):
        # Whitespace-only edits must not trip the pins.
        original = self.tech.read_text(encoding="utf-8")
        self.tech.write_text(flat_sub(original, "not inside a loop or alongside other runs",
                                      "not inside a\n   loop or alongside\n   other runs", count=1), encoding="utf-8")
        result = pin_suite_result(self.skills)
        self.assertEqual((result.failures, result.errors), ([], []))

    def test_deleting_the_victim_grep_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace(UNITTEST_GREP, "", 1))

    def test_deleting_the_pytest_grep_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace(PYTEST_GREP, "", 1))

    def test_loosening_the_unittest_grep_to_a_bare_name_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace(UNITTEST_ANCHOR, "^test_y ", 1))

    def test_dropping_the_class_from_the_unittest_anchor_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace(r"^test_y \(tests.test_x.XTest.test_y\)",
                                                         r"^test_y \(tests.test_x", 1))

    def test_dropping_the_pytest_end_anchor_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace("test_y( |$)'", "test_y'", 1))

    def test_dropping_the_pytest_line_start_anchor_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace("grep -E '^(PASSED|FAILED|ERROR) ", "grep -E '", 1))


if __name__ == "__main__":
    unittest.main()
