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

UNITTEST_ID = r"test_y \(tests\.test_x\.XTest(\.test_y)?\)"
UNITTEST_SETUP = r"ERROR: setUp(Class|Module) \(tests\.test_x(\.XTest)?\)"
UNITTEST_REGEX = rf"^({UNITTEST_ID}|(FAIL|ERROR): {UNITTEST_ID}|{UNITTEST_SETUP}|Ran [0-9]+ test)"
UNITTEST_GREP = f" | grep -E '{UNITTEST_REGEX}'"

FAILED, DIDNT_FAIL, NO_MATCH, NO_RESULT = "failed", "didn't fail", "didn't match", "no result"


def read_unittest_output(lines):
    """Step 3's four readings of the unittest grep's output, and nothing smarter.

    A `FAIL:` or `ERROR:` line for the victim, or an `ERROR: setUpClass` / `setUpModule` line
    naming its class or module: it failed. No `Ran` line: the run stopped, no result. No victim
    line (and no setUp line): the id or class didn't match. The victim's line and `Ran`, no
    header: it didn't fail. (The grep only lets the victim's own lines through, so any line that is not a
    header or the `Ran` line is the victim's.)
    """
    if any(l.startswith(("FAIL: ", "ERROR: ")) for l in lines):
        return FAILED
    if not any(l.startswith("Ran ") for l in lines):
        return NO_RESULT
    if not any(not l.startswith("Ran ") for l in lines):
        return NO_MATCH
    return DIDNT_FAIL


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
    # The grep escapes its dots, so its id is rewritten on its own (it appears twice).
    assert line.count(UNITTEST_ID) == 2, line
    line = line.replace(UNITTEST_ID, rf"{VICTIM_NAME} \(tests\.test_c_report\.ReportTest(\.{VICTIM_NAME})?\)")
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
    def only_the_victims_lines(self, out):
        for line in out:
            self.assertRegex(line, rf"^(FAIL: |ERROR: )?{VICTIM_NAME} \(tests\.test_c_report\.ReportTest|^Ran ")

    def test_half_with_the_polluter_reads_failed(self):
        _, out = self.sh(fill_unittest(step3_commands()[1], POLLUTER))
        self.assertEqual(read_unittest_output(out), FAILED, out)
        self.only_the_victims_lines(out)

    def test_half_without_the_polluter_reads_didnt_fail(self):
        _, out = self.sh(fill_unittest(step3_commands()[1], QUIET))
        self.assertEqual(read_unittest_output(out), DIDNT_FAIL, out)
        self.only_the_victims_lines(out)

    def test_a_half_that_fails_by_itself_does_not_leak_into_the_output(self):
        # A candidate that fails on its own must not show up in the grep.
        broken = Path(self.tmp) / "tests" / "test_b_broken.py"
        broken.write_text("import unittest\n\nclass B(unittest.TestCase):\n"
                          "    def test_b(self):\n        self.fail('x')\n", encoding="utf-8")
        self.addCleanup(broken.unlink)
        _, out = self.sh(fill_unittest(step3_commands()[1], "tests.test_b_broken"))
        self.assertEqual(read_unittest_output(out), DIDNT_FAIL, out)
        self.only_the_victims_lines(out)


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
                self.assertEqual(read_unittest_output(out), FAILED if half == POLLUTER else DIDNT_FAIL, out)
                for line in out:
                    # The longer name and the other class never come back.
                    self.assertRegex(line, rf"^(FAIL: |ERROR: )?{VICTIM_NAME} \(tests\.test_c_report\.ReportTest|^Ran ")
                    self.assertNotIn(VICTIM_NAME + "2", line)
                    self.assertNotIn("OtherTest", line)

    @unittest.skipUnless(PYTEST_PYTHON, NO_PYTEST)
    def test_pytest_grep_skips_a_longer_name(self):
        _, out = self.sh(fill_pytest(step3_commands()[0], "tests/test_c_report.py"))
        self.assertEqual(len(out), 1, out)
        self.assertTrue(out[0].startswith("PASSED " + VICTIM_PYTEST), out)


class CheckTest(Fixture):
    """Step 6, done as written: the victim alone, then the polluter and the victim."""

    def test_step_6_lists_both_runs(self):
        body = " ".join(section().split())
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


SHELLS = {"bash": ["bash", "-c"], "zsh -f": ["zsh", "-f", "-c"]}


def available_shells():
    return {name: argv for name, argv in SHELLS.items() if shutil.which(argv[0])}


def unittest_pythons():
    """Interpreters to run the unittest line against: this one, the system one, the one on PATH.

    Python 3.11 changed the id in `-v` output, so each format is covered by the interpreter
    that prints it. On the gate's two lines that is 3.14 (new format) on the first and 3.9 (old
    format) on the second; where the system interpreter exists, both lines run both, and the
    canned-output tests below cover both formats on any machine.
    """
    found, seen = [], set()
    for candidate in (sys.executable, "/usr/bin/python3", shutil.which("python3")):
        if not candidate or not os.path.exists(candidate):
            continue
        done = subprocess.run([candidate, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
                              capture_output=True, text=True)
        version = done.stdout.strip()
        if done.returncode == 0 and version not in seen:
            seen.add(version)
            found.append(candidate)
    return found


def grep_part(line):
    """The grep after `2>&1 | ` in step 3's unittest line, as written."""
    return line.rpartition("2>&1 | ")[2]


def run_in(shell_argv, command, cwd=None, stdin=None):
    env = {"PATH": os.environ["PATH"], "HOME": str(Path.home()), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(shell_argv + [command], cwd=cwd, env=env, input=stdin, capture_output=True, text=True)
    return done.stdout.rstrip("\n").splitlines()


class CannedOutputTest(unittest.TestCase):
    """The grep fed whole runs as each Python prints them, so both id formats run on every machine.

    Python 3.11+ prints `test_y (tests.test_x.XTest.test_y) ... ok`; before 3.11 the parentheses
    end at the class. With a docstring the result moves to the next line, in both. The grep's
    output is read with the four readings of step 3's paragraph and nothing smarter.
    """

    FORMATS = {"new": "tests.test_x.XTest.test_y", "old": "tests.test_x.XTest"}
    RAN = "Ran 5 tests in 0.001s"

    @staticmethod
    def decoy_ids(fmt):
        new = fmt == "new"
        return [
            ("test_y_other", "tests.test_x.XTest.test_y_other" if new else "tests.test_x.XTest"),
            ("test_y", "tests.test_x.OtherTest.test_y" if new else "tests.test_x.OtherTest"),
            ("test_y", "tests.test_x.XTestMore.test_y" if new else "tests.test_x.XTestMore"),
            ("test_y", "tests.test_x2.XTest.test_y" if new else "tests.test_x2.XTest"),
            ("test_y", "tests.other.XTest.test_y" if new else "tests.other.XTest"),
            ("xtest_y", "tests.test_x.XTest.test_y" if new else "tests.test_x.XTest"),
        ]

    def run_text(self, fmt, victim_lines, headers):
        """A whole -v run: decoy lines, the victim's lines, then the failure sections and the trailer."""
        ident = self.FORMATS[fmt]
        decoys = self.decoy_ids(fmt)
        body = [f"{name} ({where}) ... FAIL" for name, where in decoys]
        body += ["  test_y (" + ident + ") (i=0) ... FAIL", "Random line", "Ranked 3 tests", " Ran 3 tests"]
        body[3:3] = victim_lines
        sections = []
        for name, where in decoys:
            sections += ["=" * 70, f"FAIL: {name} ({where})", "-" * 70, "Traceback (most recent call last):"]
        # Setup and teardown headers that are not the victim's own class or module.
        for header in ("ERROR: setUpClass (tests.test_x.OtherTest)", "ERROR: setUpClass (tests.test_x2.XTest)",
                       "ERROR: setUpClass (tests.other.XTest)", "ERROR: setUpClass (tests.test_x.XTestMore)",
                       "ERROR: setUpModule (tests.test_x2)", "ERROR: setUpModule (tests.test_w)",
                       "ERROR: tearDownClass (tests.test_x.XTest)", "ERROR: tearDownModule (tests.test_x)",
                       "ERROR: setUpClass (tests.test_x.XTest.test_y)", " ERROR: setUpClass (tests.test_x.XTest)"):
            sections += ["=" * 70, header, "-" * 70]
        for header in headers:
            sections += ["=" * 70, header, "-" * 70, "Traceback (most recent call last):", "AssertionError: x"]
        return "\n".join(body + [""] + sections + ["", "-" * 70, self.RAN, "", "FAILED (failures=7)", ""])

    def check(self, fmt, victim_lines, headers, reading, expected_lines=None):
        text = self.run_text(fmt, victim_lines, headers)
        for shell in available_shells():
            with self.subTest(fmt=fmt, shell=shell, victim=victim_lines, headers=headers):
                out = run_in(SHELLS[shell], grep_part(step3_commands()[1]), stdin=text)
                self.assertEqual(read_unittest_output(out), reading, out)
                if expected_lines is not None:
                    self.assertEqual(out, expected_lines)

    def test_a_passing_victim_in_both_formats_reads_didnt_fail(self):
        for fmt, ident in self.FORMATS.items():
            line = f"test_y ({ident}) ... ok"
            self.check(fmt, [line], [], DIDNT_FAIL, [line, self.RAN])

    def test_a_failing_victim_in_both_formats_reads_failed(self):
        for fmt, ident in self.FORMATS.items():
            for header in ("FAIL", "ERROR"):
                line = f"test_y ({ident}) ... {header}"
                self.check(fmt, [line], [f"{header}: test_y ({ident})"], FAILED,
                           [line, f"{header}: test_y ({ident})", self.RAN])

    def test_a_docstring_victim_in_both_formats(self):
        # With a docstring the verdict is on the docstring's line, which the grep doesn't need.
        for fmt, ident in self.FORMATS.items():
            for doc in ("Checks the total.", "Checks a ... b.", "Checks ..."):
                name = f"test_y ({ident})"
                self.check(fmt, [name, f"{doc} ... ok"], [], DIDNT_FAIL, [name, self.RAN])
                self.check(fmt, [name, f"{doc} ... FAIL"], [f"FAIL: {name}", doc], FAILED,
                           [name, f"FAIL: {name}", self.RAN])

    def test_noise_between_the_name_and_the_verdict_is_settled_by_the_header(self):
        for fmt, ident in self.FORMATS.items():
            line = f"test_y ({ident}) ... noise"
            self.check(fmt, [line], [f"FAIL: test_y ({ident})"], FAILED)
            self.check(fmt, [line], [], DIDNT_FAIL)

    def test_a_failing_subtest_reads_failed_in_both_formats(self):
        for fmt, ident in self.FORMATS.items():
            self.check(fmt, [f"test_y ({ident}) ... "],
                       [f"FAIL: test_y ({ident}) (i=0)", f"FAIL: test_y ({ident}) (i=1)"], FAILED)

    def test_a_failing_setUpClass_or_setUpModule_of_the_victim_reads_failed(self):
        # The header names the class or module, and the victim never gets a line.
        for fmt in self.FORMATS:
            for header in ("ERROR: setUpClass (tests.test_x.XTest)", "ERROR: setUpModule (tests.test_x)"):
                self.check(fmt, [], [header], FAILED, [header, self.RAN])
                self.check(fmt, [], [header], FAILED, [header, self.RAN])

    def test_a_failing_setUpClass_with_no_ran_line_reads_failed_not_no_result(self):
        # A header for the victim settles it even if the run was cut off afterwards.
        text = "ERROR: setUpClass (tests.test_x.XTest)\n"
        for shell in available_shells():
            with self.subTest(shell=shell):
                out = run_in(SHELLS[shell], grep_part(step3_commands()[1]), stdin=text)
                self.assertEqual(read_unittest_output(out), FAILED, out)

    def test_tearDownClass_and_tearDownModule_headers_do_not_change_the_victims_reading(self):
        # The victim passed; the class's teardown failing afterwards is not its failure.
        for fmt, ident in self.FORMATS.items():
            line = f"test_y ({ident}) ... ok"
            self.check(fmt, [line], [], DIDNT_FAIL, [line, self.RAN])

    def test_no_victim_line_reads_didnt_match(self):
        for fmt in self.FORMATS:
            self.check(fmt, [], [], NO_MATCH, [self.RAN])

    def test_a_run_with_no_ran_line_reads_no_result(self):
        for fmt, ident in self.FORMATS.items():
            for text in (f"test_y ({ident}) ... ", f"test_y ({ident}) ... \n", f"test_y ({ident})"):
                for shell in available_shells():
                    with self.subTest(fmt=fmt, shell=shell, text=text):
                        out = run_in(SHELLS[shell], grep_part(step3_commands()[1]), stdin=text)
                        self.assertEqual(read_unittest_output(out), NO_RESULT, out)

    def test_other_ids_and_lookalike_lines_never_come_back(self):
        for fmt in self.FORMATS:
            text = self.run_text(fmt, [], [])
            for shell in available_shells():
                with self.subTest(fmt=fmt, shell=shell):
                    out = run_in(SHELLS[shell], grep_part(step3_commands()[1]), stdin=text)
                    self.assertEqual(out, [self.RAN])


class UnittestLineRealRunTest(unittest.TestCase):
    """Step 3's unittest line, run on real unittest output, read with the four readings.

    The fixture holds one victim, XTest.test_y in tests/test_x.py, whose body changes per case.
    Next to it, all failing (so a leak shows): XTest.test_y_other, OtherTest.test_y, a
    XTest.test_y in tests/test_w.py, and one in tests/test_b.py (a half that fails by itself).
    """

    HALF = "tests.test_b tests.test_w tests.test_x.XTest.test_y_other tests.test_x.OtherTest"
    DOCS = [None, "Checks the total.", "Checks a ... b.",
            "Checks the total.\n\n        Second paragraph, more detail.\n        "]
    DECOY_NAMES = ("test_y_other", "OtherTest", "test_w", "test_b", "test_v")

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="unittest-line-")
        tests = Path(cls.tmp) / "tests"
        tests.mkdir()
        (tests / "__init__.py").write_text("", encoding="utf-8")
        for name in ("test_w", "test_b"):
            (tests / f"{name}.py").write_text(
                "import unittest\n\n\nclass XTest(unittest.TestCase):\n    def test_y(self):\n"
                "        self.fail('decoy')\n", encoding="utf-8")
        cls.pythons = unittest_pythons()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def victim_source(self, body, doc=None, decorator=None, in_class=(), before_class=()):
        lines = ["import os", "import sys", "import unittest", ""] + list(before_class) + ["", "class XTest(unittest.TestCase):"]
        lines += [f"    {l}" for l in in_class]
        if decorator:
            lines.append(f"    {decorator}")
        lines.append("    def test_y(self):")
        if doc is not None:
            lines.append('        """' + doc + '"""')
        lines += ["        " + b for b in body.splitlines()]
        lines += ["", "    def test_y_other(self):", "        self.fail('decoy')", "", "",
                  "class OtherTest(unittest.TestCase):", "    def test_y(self):", "        self.fail('decoy')", ""]
        return "\n".join(lines)

    def write_victim(self, body, where="tests/test_x.py", **kw):
        path = Path(self.tmp) / where
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.victim_source(body, **kw), encoding="utf-8")

    def line(self, python, victim="tests.test_x.XTest.test_y", half=None, module="tests.test_x"):
        half = self.HALF if half is None else half
        head, sep, tail = step3_commands()[1].partition(" 2>&1 | ")
        head = head.replace("<half, as modules>", half)
        if victim is not None:
            head = head.replace("tests.test_x.XTest.test_y", victim)
        tail = tail.replace(r"tests\.test_x\.XTest", module.replace(".", r"\.") + r"\.XTest")
        return (head + sep + tail).replace("python3", python, 1)

    def run_line(self, python, shell, **kw):
        return run_in(SHELLS[shell], self.line(python, **kw), cwd=self.tmp)

    def every_combination(self):
        shells = available_shells()
        self.assertIn("bash", shells)
        self.assertTrue(self.pythons)
        for python in self.pythons:
            for shell in shells:
                yield python, shell

    def assert_reading(self, reading, headers=0, docs=(None,), **kw):
        """Every Python and shell: the grep's output reads as `reading`, shows `headers` failure
        headers, and shows nothing from a decoy."""
        for doc in docs:
            for python, shell in self.every_combination():
                with self.subTest(python=python, shell=shell, doc=doc):
                    out = self.run_line(python, shell, **kw)
                    self.assertEqual(read_unittest_output(out), reading, out)
                    self.assertEqual(len([l for l in out if l.startswith(("FAIL: ", "ERROR: "))]), headers, out)
                    for line in out:
                        for name in self.DECOY_NAMES:
                            self.assertNotIn(name, line, out)

    def case(self, body, reading, headers=0, decorator=None, docs=None, **kw):
        docs = self.DOCS if docs is None else docs
        for doc in docs:
            self.write_victim(body, doc=doc, decorator=decorator, **{k: v for k, v in kw.items() if k in ("in_class", "before_class")})
            self.assert_reading(reading, headers, docs=(doc,), **{k: v for k, v in kw.items() if k not in ("in_class", "before_class")})

    def test_a_passing_victim_reads_didnt_fail(self):
        self.case("pass", DIDNT_FAIL)

    def test_a_failing_victim_reads_failed(self):
        self.case("self.fail('boom')", FAILED, headers=1)

    def test_a_victim_that_errors_reads_failed(self):
        self.case("raise RuntimeError('boom')", FAILED, headers=1)

    def test_an_error_in_setUp_reads_failed(self):
        self.case("pass", FAILED, headers=1, in_class=["def setUp(self):", "    raise RuntimeError('setUp')"])

    def test_an_error_in_tearDown_reads_failed(self):
        self.case("pass", FAILED, headers=1, in_class=["def tearDown(self):", "    raise RuntimeError('tearDown')"])

    def test_a_skipped_victim_reads_didnt_fail(self):
        # Known and accepted: a skip shows no header.
        self.case("pass", DIDNT_FAIL, decorator='@unittest.skip("victim")')

    def test_an_expected_failure_victim_reads_didnt_fail(self):
        # Known and accepted: an expected failure shows no header.
        self.case("self.fail('known')", DIDNT_FAIL, decorator="@unittest.expectedFailure")

    def test_an_unexpected_success_victim_reads_didnt_fail(self):
        # Known and accepted: unittest's header is `UNEXPECTED SUCCESS:`, not FAIL: or ERROR:.
        self.case("pass", DIDNT_FAIL, decorator="@unittest.expectedFailure")

    def test_a_victim_that_prints_while_it_fails_reads_failed(self):
        self.case("print('noise', file=sys.stderr, flush=True)\nself.fail('boom')", FAILED, headers=1)

    def test_a_victim_that_prints_while_it_passes_reads_didnt_fail(self):
        self.case("print('noise', file=sys.stderr, flush=True)", DIDNT_FAIL)

    def test_a_failing_subtest_reads_failed(self):
        self.case("for i in range(2):\n    with self.subTest(i=i):\n        self.assertEqual(i, 5)",
                  FAILED, headers=2)

    def test_a_victim_that_kills_the_process_reads_no_result(self):
        self.case("sys.stdout.flush()\nos._exit(3)", NO_RESULT)

    def test_the_victim_as_the_only_test_reads_in_both_ways(self):
        self.write_victim("pass")
        self.assert_reading(DIDNT_FAIL, half="")
        self.write_victim("self.fail('boom')")
        self.assert_reading(FAILED, headers=1, half="")

    def test_decoys_and_the_failing_half_really_run(self):
        # Without this the decoy checks could pass because the decoys never ran.
        self.write_victim("pass")
        for python, shell in self.every_combination():
            with self.subTest(python=python, shell=shell):
                everything = run_in(
                    SHELLS[shell], f"{python} -m unittest -v {self.HALF} tests.test_x.XTest.test_y 2>&1", cwd=self.tmp)
                self.assertEqual(len([l for l in everything if l.endswith(" ... FAIL")]), 4, everything)
                headers = [l for l in everything if l.startswith("FAIL: ")]
                for name in ("test_y_other", "OtherTest", "tests.test_w", "tests.test_b"):
                    self.assertTrue(any(name in h for h in headers), (name, headers))

    def test_a_wrong_id_reads_didnt_match(self):
        self.write_victim("self.fail('boom')")
        wrong = {
            "wrong class": "tests.test_x.NopeTest.test_y",
            "wrong module": "tests.test_nope.XTest.test_y",
            "wrong method": "tests.test_x.XTest.test_nope",
            "decoy method name": "tests.test_x.XTest.test_y_other",
        }
        for label, victim in wrong.items():
            with self.subTest(wrong=label):
                self.assert_reading(NO_MATCH, victim=victim)

    def test_a_same_named_class_in_another_module_is_not_the_victim(self):
        # tests.test_x.XTest.test_y fails here; the victim lives in a nested package and passes.
        self.write_victim("self.fail('decoy: the same name in another module')")
        self.write_victim("pass", where="tests/pkg/test_x.py")
        (Path(self.tmp) / "tests" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        self.addCleanup(shutil.rmtree, Path(self.tmp) / "tests" / "pkg", ignore_errors=True)
        self.assert_reading(DIDNT_FAIL, victim="tests.pkg.test_x.XTest.test_y", module="tests.pkg.test_x",
                            half=self.HALF + " tests.test_x")
        self.write_victim("self.fail('boom')", where="tests/pkg/test_x.py")
        self.assert_reading(FAILED, headers=1, victim="tests.pkg.test_x.XTest.test_y", module="tests.pkg.test_x",
                            half=self.HALF + " tests.test_x")

    def test_a_victim_named_by_file_path_still_reads(self):
        # unittest turns tests/test_x.py into the dotted module name, so the ids still match.
        self.write_victim("pass")
        self.assert_reading(DIDNT_FAIL, victim="tests/test_x.py", half="tests.test_b")
        self.write_victim("self.fail('boom')")
        self.assert_reading(FAILED, headers=1, victim="tests/test_x.py", half="tests.test_b")

    def test_a_victim_printing_a_fake_failure_header_fools_the_reading(self):
        # A passing victim whose output has a line that starts `FAIL: test_y (...)` reads as failed.
        # Accepted limit: it takes a test that prints a failure header on a line of its own.
        self.write_victim("print('\\nFAIL: test_y (tests.test_x.XTest.test_y)', file=sys.stderr, flush=True)")
        for python, shell in self.every_combination():
            with self.subTest(python=python, shell=shell):
                out = self.run_line(python, shell)
                self.assertEqual(read_unittest_output(out), FAILED, out)

    def test_a_victim_printing_a_fake_ran_line_before_dying_fools_the_reading(self):
        # The run stopped, but a printed line starting `Ran 3 tests` supplies the Ran line, so it
        # reads "didn't fail" instead of "no result". Accepted limit, same kind of test as above.
        self.write_victim("print('\\nRan 3 tests in 0.001s', file=sys.stderr, flush=True)\nos._exit(3)")
        for python, shell in self.every_combination():
            with self.subTest(python=python, shell=shell):
                out = self.run_line(python, shell)
                self.assertEqual(read_unittest_output(out), DIDNT_FAIL, out)

    def test_a_failing_setUpClass_reads_failed(self):
        # unittest's header names the class and the victim has no line; both Pythons.
        self.write_victim("pass", in_class=["@classmethod", "def setUpClass(cls):", "    raise RuntimeError('class')"])
        # A half without the victim's class (the default half runs one of its methods, which would
        # set the class up a second time and show a second header).
        self.assert_reading(FAILED, headers=1, half="tests.test_b")

    def test_a_failing_setUpModule_reads_failed(self):
        self.write_victim("pass", before_class=["", "def setUpModule():", "    raise RuntimeError('module')"])
        self.assert_reading(FAILED, headers=1)

    def test_a_setUpClass_inherited_from_a_base_class_reads_failed(self):
        # The header names the victim's class, not the base class, so the grep sees it.
        (Path(self.tmp) / "tests" / "base.py").write_text(
            "import unittest\n\n\nclass Base(unittest.TestCase):\n    @classmethod\n"
            "    def setUpClass(cls):\n        raise RuntimeError('base')\n", encoding="utf-8")
        self.addCleanup((Path(self.tmp) / "tests" / "base.py").unlink)
        (Path(self.tmp) / "tests" / "test_x.py").write_text(
            "import unittest\nfrom tests.base import Base\n\n\nclass XTest(Base):\n    def test_y(self):\n"
            "        pass\n", encoding="utf-8")
        self.assert_reading(FAILED, headers=1, half="")

    def test_a_failing_setUpClass_in_a_decoy_class_is_not_the_victims(self):
        source = self.victim_source("pass").replace(
            "class OtherTest(unittest.TestCase):",
            "class OtherTest(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n"
            "        raise RuntimeError('decoy')\n")
        (Path(self.tmp) / "tests" / "test_x.py").write_text(source, encoding="utf-8")
        self.assertIn("setUpClass", source)
        self.assert_reading(DIDNT_FAIL)

    def test_failing_setUpClass_and_setUpModule_in_another_module_are_not_the_victims(self):
        self.write_victim("pass")
        for body in ("import unittest\n\n\ndef setUpModule():\n    raise RuntimeError('decoy')\n\n\n"
                     "class XTest(unittest.TestCase):\n    def test_y(self):\n        pass\n",
                     "import unittest\n\n\nclass XTest(unittest.TestCase):\n    @classmethod\n"
                     "    def setUpClass(cls):\n        raise RuntimeError('decoy')\n    def test_y(self):\n"
                     "        pass\n"):
            path = Path(self.tmp) / "tests" / "test_v.py"
            path.write_text(body, encoding="utf-8")
            with self.subTest(body=body.splitlines()[2]):
                self.assert_reading(DIDNT_FAIL, half=self.HALF + " tests.test_v")
            path.unlink()

    def test_a_failing_tearDownClass_or_tearDownModule_reads_didnt_fail(self):
        # Odd corner, pinned as it stands: the victim passed, and only its class's teardown failed.
        self.write_victim("pass", in_class=["@classmethod", "def tearDownClass(cls):", "    raise RuntimeError('t')"])
        self.assert_reading(DIDNT_FAIL)
        self.write_victim("pass", before_class=["", "def tearDownModule():", "    raise RuntimeError('t')"])
        self.assert_reading(DIDNT_FAIL)

    def test_a_module_that_fails_to_import_reads_didnt_match(self):
        # Odd corner, pinned as it stands: unittest reports `_FailedTest` under the module's last
        # name, so there is no victim line and "didn't match, fix it" is what the text says. The
        # module is the thing to fix, which the reading does send the reader to look at.
        (Path(self.tmp) / "tests" / "test_x.py").write_text("import no_such_module_anywhere\n", encoding="utf-8")
        self.assert_reading(NO_MATCH, headers=0)

    def test_a_module_with_a_syntax_error_reads_no_result(self):
        (Path(self.tmp) / "tests" / "test_x.py").write_text("def (:\n", encoding="utf-8")
        self.assert_reading(NO_RESULT)

    def test_a_setUpClass_that_skips_reads_didnt_match(self):
        # Odd corner, pinned as it stands: a SkipTest in setUpClass leaves no victim line, no header
        # and `Ran 0 tests`, so it reads like a wrong id, where a skipped test reads "didn't fail".
        self.write_victim("pass", in_class=["@classmethod", "def setUpClass(cls):", "    raise unittest.SkipTest('s')"])
        self.assert_reading(NO_MATCH)


class SeededLoopRunTest(unittest.TestCase):
    """SKILL.md's seeded loop, run against a suite whose victim fails only after a polluter, in random order."""

    LOOP = re.compile(r"`(for i in \$\(seq \d+\); do pytest -q -rA --randomly-seed=\$i .*?; done)`", re.S)

    @classmethod
    def setUpClass(cls):
        cls.python = None
        named = os.environ.get("FOUNDRY_PYTEST_PYTHON")
        for candidate in [c for c in (named, sys.executable) if c]:
            try:
                done = subprocess.run([candidate, "-c", "import pytest, pytest_randomly"], capture_output=True)
            except OSError:
                continue
            if done.returncode == 0:
                cls.python = candidate
                break
        if cls.python is None:
            raise unittest.SkipTest("no interpreter with pytest and pytest-randomly: set FOUNDRY_PYTEST_PYTHON to one")
        cls.tmp = tempfile.mkdtemp(prefix="seeded-loop-")
        tests = Path(cls.tmp) / "tests"
        tests.mkdir()
        (Path(cls.tmp) / "state.py").write_text("dirty = False\n", encoding="utf-8")
        (Path(cls.tmp) / "conftest.py").write_text("", encoding="utf-8")
        (tests / "test_x.py").write_text(
            "import state\n\n\ndef test_y():\n    assert not state.dirty\n\n\n"
            "def test_y_other():\n    assert not state.dirty\n", encoding="utf-8")
        (tests / "test_z.py").write_text(
            "import state\n\n\ndef test_polluter():\n    state.dirty = True\n\n\n"
            "def test_innocent_1():\n    pass\n\n\ndef test_innocent_2():\n    pass\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "tmp", ""), ignore_errors=True)

    def loop(self):
        skill = (ROOT / "skills" / "debug" / "SKILL.md").read_text(encoding="utf-8")
        found = self.LOOP.search(skill)
        self.assertIsNotNone(found, "SKILL.md has no seeded pytest loop")
        cmd = " ".join(found.group(1).split())
        return cmd.replace("pytest -q -rA", f"{self.python} -m pytest -q -rA -p no:cacheprovider", 1)

    def test_the_loop_prints_the_victims_own_outcome_with_a_seed_and_a_failing_seed_reproduces(self):
        for shell in available_shells():
            with self.subTest(shell=shell):
                out = run_in(SHELLS[shell], self.loop(), cwd=self.tmp)
                self.assertEqual(len(out), 20, out)  # one line per run: test_y_other is not counted
                for i, line in enumerate(out, 1):
                    self.assertRegex(line, rf"^seed {i}: (PASSED|FAILED) tests/test_x.py::test_y( |$)")
                failing = [int(l.split(":")[0].split()[1]) for l in out if ": FAILED " in l]
                self.assertTrue(failing, f"no run failed in 20 seeds, so the fixture proves nothing: {out}")
                self.assertTrue([l for l in out if ": PASSED " in l], out)
                seed = failing[0]
                listed = run_in(SHELLS[shell], f"{self.python} -m pytest --collect-only -q -p no:cacheprovider "
                                f"--randomly-seed={seed}", cwd=self.tmp)
                ids = [l for l in listed if "::" in l]
                above = ids[: ids.index("tests/test_x.py::test_y")]
                self.assertIn("tests/test_z.py::test_polluter", above)
                again = run_in(SHELLS[shell], f"{self.python} -m pytest -q -rA -p no:randomly -p no:cacheprovider "
                               f"{' '.join(above)} tests/test_x.py::test_y 2>&1 | grep -E "
                               "'^(PASSED|FAILED|ERROR) tests/test_x.py::test_y( |$)'", cwd=self.tmp)
                self.assertEqual(len(again), 1, again)
                self.assertTrue(again[0].startswith("FAILED tests/test_x.py::test_y"), again)


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
            "in that order.": "in any order.",
            "the test ids above the victim": "the test files above the victim",
            "names its seed": "may print a seed",
            "lists that order)": "lists the order)",
            "line for the victim: it failed": "line for the victim: it didn't fail",
            "and no such header: it didn't fail": "and no such header: it failed",
            "no victim line, and no `setUpClass` or `setUpModule` line either: the id or class didn't match":
                "no victim line: the victim passed",
            "the victim never ran because its setup failed": "the victim passed but its setup failed",
            "so there's no result": "so it passed",
            "so only these lines count": "so any line counts",
            "nothing to open: go to step 6": "nothing to open: go to step 5",
            "(one test id, if the candidates were ids from a random-order run)": "(one file)",
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

    def test_deleting_the_unittest_grep_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace(UNITTEST_GREP, "", 1))

    def test_deleting_the_pytest_grep_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace(PYTEST_GREP, "", 1))

    def test_loosening_the_unittest_grep_to_a_bare_name_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace(UNITTEST_REGEX, "^test_y ", 1))

    def test_dropping_the_class_from_either_alternative_is_caught(self):
        # Once for the victim's own line, once for the header: each has its own copy of the id.
        for which in (1, 2):
            with self.subTest(copy=which):
                self.assertCaught(self.tech, lambda t: self.nth_replace(
                    t, r"tests\.test_x\.XTest(\.test_y)?\)", r"tests\.test_x\.)", which))

    def test_dropping_the_optional_test_name_from_either_alternative_is_caught(self):
        # Without (\.test_y)? the line prints nothing before Python 3.11.
        for which in (1, 2):
            with self.subTest(copy=which):
                self.assertCaught(self.tech, lambda t: self.nth_replace(
                    t, r"XTest(\.test_y)?\)", r"XTest\.test_y\)", which))

    def test_dropping_the_closing_paren_from_either_alternative_is_caught(self):
        # Without it XTest also matches XTestMore.
        for which in (1, 2):
            with self.subTest(copy=which):
                self.assertCaught(self.tech, lambda t: self.nth_replace(
                    t, r"XTest(\.test_y)?\)", r"XTest(\.test_y)?", which))

    def test_dropping_the_header_alternative_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace(
            rf"|(FAIL|ERROR): {UNITTEST_ID}", "", 1))

    def test_dropping_the_setup_alternative_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace("|" + UNITTEST_SETUP, "", 1))

    def test_dropping_class_or_module_from_the_setup_alternative_is_caught(self):
        for old, new in (("setUp(Class|Module)", "setUpClass"), ("setUp(Class|Module)", "setUpModule")):
            with self.subTest(keep=new):
                self.assertCaught(self.tech, lambda t: t.replace(old, new, 1))

    def test_dropping_the_module_name_from_the_setup_alternative_is_caught(self):
        # Without tests.test_x, any module's setUp failure would read as the victim's.
        self.assertCaught(self.tech, lambda t: t.replace(r"setUp(Class|Module) \(tests\.test_x(\.XTest)?\)", r"setUp(Class|Module) \(tests", 1))

    def test_dropping_the_optional_class_from_the_setup_alternative_is_caught(self):
        # Without (\.XTest)? a setUpClass line never matches; without the group's ? setUpModule never does.
        self.assertCaught(self.tech, lambda t: t.replace(r"test_x(\.XTest)?\)|Ran", r"test_x\.XTest\)|Ran", 1))
        self.assertCaught(self.tech, lambda t: t.replace(r"test_x(\.XTest)?\)|Ran", r"test_x\)|Ran", 1))

    def test_dropping_the_setup_alternatives_closing_paren_is_caught(self):
        # Without it XTest would also match XTestMore.
        self.assertCaught(self.tech, lambda t: t.replace(r"test_x(\.XTest)?\)|Ran", r"test_x(\.XTest)?|Ran", 1))

    def test_dropping_error_from_the_header_alternative_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace("(FAIL|ERROR): ", "FAIL: ", 1))

    def test_dropping_the_ran_alternative_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace("|Ran [0-9]+ test", "", 1))

    def test_dropping_the_line_start_anchor_from_the_unittest_grep_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace("grep -E '^(test_y", "grep -E '(test_y", 1))

    def test_swapping_the_grep_back_to_the_old_one_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace(UNITTEST_GREP, r" | grep -E '^test_y \(tests.test_x.XTest.test_y\)'", 1))

    def test_swapping_the_grep_for_the_awk_line_is_caught(self):
        awk = r" | awk '/^test_y \(tests\.test_x\.XTest(\.test_y)?\)/ { if ($0 !~ / \.\.\. /) getline; print }'"
        self.assertCaught(self.tech, lambda t: t.replace(UNITTEST_GREP, awk, 1))

    @staticmethod
    def nth_replace(text, old, new, n):
        """Replace the nth occurrence of old."""
        at = -1
        for _ in range(n):
            at = text.index(old, at + 1)
        return text[:at] + new + text[at + len(old):]

    def test_dropping_the_pytest_end_anchor_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace("test_y( |$)'", "test_y'", 1))

    def test_dropping_the_pytest_line_start_anchor_is_caught(self):
        self.assertCaught(self.tech, lambda t: t.replace("grep -E '^(PASSED|FAILED|ERROR) ", "grep -E '", 1))

    # The seeded loop and the name boundary on every measuring grep (SKILL.md).
    MEASURING = "grep -E '^(PASSED|FAILED|ERROR) tests/test_x.py::test_y( |$)'"

    def test_deleting_the_plain_measuring_grep_is_caught(self):
        # The vacuous version of the boundary test stayed green with this line gone.
        def drop(t):
            return t.replace("pytest -q -rA 2>&1 | " + self.MEASURING, "pytest -q -rA", 1)
        self.assertCaught(self.skill, drop)

    def test_deleting_every_measuring_grep_is_caught(self):
        def drop(t):
            return re.sub(r"\| grep -E '\^\(PASSED[^']*'", "", t)
        self.assertCaught(self.skill, drop)

    def test_removing_the_boundary_from_a_grep_variant_is_caught(self):
        def edit(t):
            return t.replace(self.MEASURING, "grep -cE '^(PASSED|FAILED|ERROR) tests/test_x.py::test_y'", 1)
        self.assertCaught(self.skill, edit)

    def test_removing_the_boundary_from_the_loops_grep_is_caught(self):
        def edit(t):
            head, loop = t.split("--randomly-seed=$i", 1)
            return head + "--randomly-seed=$i" + loop.replace("test_y( |$)'", "test_y'", 1)
        self.assertCaught(self.skill, edit)

    def test_loosening_the_plain_grep_only_is_caught(self):
        self.assertCaught(self.skill, lambda t: t.replace("test_y( |$)'", "test_y'", 1))

    def test_deleting_the_seed_option_from_the_loop_is_caught(self):
        self.assertCaught(self.skill, lambda t: t.replace(" --randomly-seed=$i", "", 1))

    def test_hardcoding_the_seed_in_the_loop_is_caught(self):
        self.assertCaught(self.skill, lambda t: t.replace("--randomly-seed=$i", "--randomly-seed=1", 1))

    def test_dropping_the_seed_label_from_the_loop_is_caught(self):
        self.assertCaught(self.skill, lambda t: t.replace(' | sed "s/^/seed $i: /"', "", 1))

    def test_deleting_the_loop_is_caught(self):
        def drop(t):
            return re.sub(r"\n  When the order is random.*?; done`\)\.", "", t, flags=re.S)
        self.assertCaught(self.skill, drop)

    def test_pointing_step_1_back_at_the_hidden_header_is_caught(self):
        self.assertCaught(self.tech, lambda t: flat_sub(
            t, "a failing run of the seeded loop in skill section 2 names its seed",
            "pytest-randomly prints its seed at the top of each run"))

    def test_deleting_the_collect_command_is_caught(self):
        self.assertCaught(self.tech, lambda t: flat_sub(
            t, "`pytest --collect-only -q --randomly-seed=<seed>` lists that order"))

    def test_deleting_the_random_order_candidates_sentence_is_caught(self):
        self.assertCaught(self.tech, lambda t: flat_sub(
            t, "For a random-order failure, the candidates are the test ids above the victim in the failing run's list, in that order."))

    def test_deleting_each_of_the_four_readings_is_caught(self):
        readings = [
            "a `FAIL:` or `ERROR:` line for the victim: it failed",
            "So is an `ERROR: setUpClass` or `ERROR: setUpModule` line naming the victim's class or module",
            "the victim never ran because its setup failed",
            "the victim's own line and the `Ran` line, and no such header: it didn't fail",
            "no victim line, and no `setUpClass` or `setUpModule` line either: the id or class didn't match, so fix it before you trust the run",
            "no `Ran` line: the run stopped before it finished, so there's no result",
        ]
        for reading in readings:
            with self.subTest(reading=reading):
                self.assertCaught(self.tech, lambda t: flat_sub(t, reading))

    def test_deleting_the_four_readings_paragraph_is_caught(self):
        self.assertCaught(self.tech, lambda t: re.sub(
            r"\n   The unittest line works whichever way.*?no `Ran` line:[^\n]*\n[^\n]*\n", "\n", t, flags=re.S))

    def test_swapping_two_readings_is_caught(self):
        def swap(t):
            t = flat_sub(t, "line for the victim: it failed (", "@@A (")
            t = flat_sub(t, "and no such header: it didn't fail", "line for the victim: it failed")
            return flat_sub(t, "@@A", "and no such header: it didn't fail")
        self.assertCaught(self.tech, swap)

    def test_deleting_the_step_4_test_id_clause_is_caught(self):
        self.assertCaught(self.tech, lambda t: flat_sub(
            t, "(one test id, if the candidates were ids from a random-order run)"))

    def test_deleting_the_step_5_test_id_sentence_is_caught(self):
        self.assertCaught(self.tech, lambda t: flat_sub(
            t, "If step 4 already ended on one test id, there is nothing to open: go to step 6."))



if __name__ == "__main__":
    unittest.main()
