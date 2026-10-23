"""Tests for skills/debug/scripts/find-polluter (bisecting for a test that breaks another).

The script drives pytest, and the interpreter running these tests may not have it. The
pytest interpreter is FOUNDRY_PYTEST_PYTHON if set, else sys.executable if it can import
pytest; with neither, the whole module is skipped. The script itself always runs under
sys.executable and is handed the pytest interpreter with --python.
"""
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "debug" / "scripts" / "find-polluter"

SKIP_REASON = "set FOUNDRY_PYTEST_PYTHON to a Python with pytest"


def _can_import_pytest(python):
    try:
        proc = subprocess.run(
            [python, "-c", "import pytest"],
            capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except OSError:
        return False
    return proc.returncode == 0


def _find_pytest_python():
    """Return (interpreter or None, skip reason)."""
    configured = os.environ.get("FOUNDRY_PYTEST_PYTHON")
    if configured:
        if _can_import_pytest(configured):
            return configured, ""
        return None, f"FOUNDRY_PYTEST_PYTHON={configured} cannot import pytest; {SKIP_REASON}"
    if _can_import_pytest(sys.executable):
        return sys.executable, ""
    return None, SKIP_REASON


PYTEST_PYTHON, _REASON = _find_pytest_python()

# Test-file bodies. app.py (module-level state) is written by the fixture.
CLEAN = "def test_ok():\n    assert True\n"
POLLUTER = "import app\n\n\ndef test_pollutes():\n    app.FLAG = True\n"
VICTIM = "import app\n\n\ndef test_victim():\n    assert not app.FLAG\n"
FAILS_ALONE = "def test_broken():\n    assert 1 == 2\n"

VICTIM_ID = "tests/test_victim.py::test_victim"


@unittest.skipUnless(PYTEST_PYTHON, _REASON)
class FindPolluterTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.write("app.py", "FLAG = False\nOTHER = False\n")
        self.write("pytest.ini", "[pytest]\n")
        self.write("conftest.py", "")

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def env(self):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("PYTEST_ADDOPTS", None)
        return env

    def run_script(self, *args, python=True):
        """Run find-polluter in the temp project; return the CompletedProcess."""
        cmd = [sys.executable, str(SCRIPT)]
        if python:
            cmd += ["--python", PYTEST_PYTHON]
        cmd += list(args)
        return subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, env=self.env())

    # -- file level -------------------------------------------------------

    def test_finds_polluting_file_among_clean_files(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_a_clean.py", CLEAN)
        self.write("tests/test_b_clean.py", CLEAN)
        self.write("tests/test_c_polluter.py", POLLUTER)
        self.write("tests/test_d_clean.py", CLEAN)
        self.write("tests/test_e_clean.py", CLEAN)
        proc = self.run_script(VICTIM_ID)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_c_polluter.py\n", proc.stdout)
        self.assertIn("5 candidates", proc.stdout)

    def test_file_level_result_hints_at_the_next_step(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_polluter.py", POLLUTER)
        self.write("tests/test_clean.py", CLEAN)
        proc = self.run_script(VICTIM_ID)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(
            f"next: find-polluter {VICTIM_ID} --tests tests/test_polluter.py", proc.stdout
        )
        self.assertIn("to find the test inside it", proc.stdout)

    def test_victims_own_file_is_not_a_candidate(self):
        # The victim's file also holds a polluting test; file level must skip that file.
        self.write("tests/test_victim.py", VICTIM + "\n\n" + POLLUTER.split("\n\n\n", 1)[1])
        self.write("tests/test_clean.py", CLEAN)
        proc = self.run_script(VICTIM_ID)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("1 candidates", proc.stdout)
        self.assertIn("don't break the victim", proc.stdout)

    def test_candidates_can_be_given_by_hand(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_a_polluter.py", POLLUTER)
        self.write("tests/test_b_clean.py", CLEAN)
        proc = self.run_script(VICTIM_ID, "tests/test_b_clean.py")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        proc = self.run_script(VICTIM_ID, "tests/test_b_clean.py", "tests/test_a_polluter.py")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_a_polluter.py\n", proc.stdout)

    # -- --tests narrowing ------------------------------------------------

    def test_tests_flag_narrows_to_the_polluting_test_in_a_file(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write(
            "tests/test_polluter.py",
            "import app\n\n\n"
            "def test_one():\n    assert True\n\n\n"
            "def test_two():\n    assert True\n\n\n"
            "def test_three_sets_flag():\n    app.FLAG = True\n\n\n"
            "def test_four():\n    assert True\n",
        )
        proc = self.run_script(VICTIM_ID, "--tests", "tests/test_polluter.py")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_polluter.py::test_three_sets_flag\n", proc.stdout)
        self.assertIn("4 candidates", proc.stdout)
        self.assertNotIn("next:", proc.stdout)

    def test_tests_on_victims_own_file_finds_an_earlier_test(self):
        self.write(
            "tests/test_victim.py",
            "import app\n\n\n"
            "def test_first():\n    assert True\n\n\n"
            "def test_second_sets_flag():\n    app.FLAG = True\n\n\n"
            "def test_victim():\n    assert not app.FLAG\n",
        )
        proc = self.run_script(VICTIM_ID, "--tests", "tests/test_victim.py")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_victim.py::test_second_sets_flag\n", proc.stdout)
        self.assertIn("2 candidates", proc.stdout)

    def test_tests_on_victims_own_file_ignores_later_tests(self):
        # The only polluter runs after the victim, so it cannot be the cause.
        self.write(
            "tests/test_victim.py",
            "import app\n\n\n"
            "def test_first():\n    assert True\n\n\n"
            "def test_victim():\n    assert not app.FLAG\n\n\n"
            "def test_zlate_sets_flag():\n    app.FLAG = True\n",
        )
        proc = self.run_script(VICTIM_ID, "--tests", "tests/test_victim.py")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("1 candidates", proc.stdout)
        self.assertNotIn("polluter:", proc.stdout)

    def test_tests_on_victims_own_file_with_victim_first_has_no_candidates(self):
        self.write(
            "tests/test_victim.py",
            VICTIM + "\n\ndef test_later():\n    assert True\n",
        )
        proc = self.run_script(VICTIM_ID, "--tests", "tests/test_victim.py")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("no candidates", proc.stderr)

    # -- nothing to find --------------------------------------------------

    def test_victim_failing_on_its_own_is_not_pollution(self):
        self.write("tests/test_victim.py", "def test_victim():\n    assert 1 == 2\n")
        self.write("tests/test_polluter.py", POLLUTER)
        proc = self.run_script(VICTIM_ID)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("not pollution", proc.stdout)
        self.assertNotIn("polluter:", proc.stdout)

    def test_candidates_that_do_not_break_the_victim_exit_1(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_a_clean.py", CLEAN)
        self.write("tests/test_b_clean.py", CLEAN)
        proc = self.run_script(VICTIM_ID)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("don't break the victim", proc.stdout)
        self.assertNotIn("polluter:", proc.stdout)

    def test_candidate_that_fails_by_itself_is_not_the_polluter(self):
        # Failing files sit in the first half, the real polluter in the second. Judging by
        # pytest's exit code would blame the failing files; the JUnit check must not.
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_a_fails.py", FAILS_ALONE)
        self.write("tests/test_b_fails.py", FAILS_ALONE)
        self.write("tests/test_c_clean.py", CLEAN)
        self.write("tests/test_d_polluter.py", POLLUTER)
        proc = self.run_script(VICTIM_ID)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_d_polluter.py\n", proc.stdout)

    def test_failing_candidates_alone_do_not_count_as_pollution(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_a_fails.py", FAILS_ALONE)
        proc = self.run_script(VICTIM_ID)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("don't break the victim", proc.stdout)

    def test_two_tests_needed_together_lists_narrowed_candidates(self):
        # The victim fails only with both flags set; each is set by a different file.
        self.write(
            "tests/test_victim.py",
            "import app\n\n\ndef test_victim():\n    assert not (app.FLAG and app.OTHER)\n",
        )
        self.write("tests/test_1_sets_flag.py", POLLUTER)
        self.write("tests/test_2_clean.py", CLEAN)
        self.write(
            "tests/test_3_sets_other.py",
            "import app\n\n\ndef test_sets_other():\n    app.OTHER = True\n",
        )
        self.write("tests/test_4_clean.py", CLEAN)
        self.write("tests/test_5_clean.py", CLEAN)
        self.write("tests/test_6_clean.py", CLEAN)
        proc = self.run_script(VICTIM_ID)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("takes tests from both", proc.stdout)
        self.assertNotIn("polluter:", proc.stdout)
        listed = [line.strip() for line in proc.stdout.splitlines() if line.startswith("  tests/")]
        self.assertEqual(
            listed,
            ["tests/test_1_sets_flag.py", "tests/test_2_clean.py", "tests/test_3_sets_other.py"],
        )

    # -- victim node-id forms --------------------------------------------

    def test_victim_inside_a_class(self):
        self.write(
            "tests/test_x.py",
            "import app\n\n\nclass TestC:\n    def test_y(self):\n        assert not app.FLAG\n",
        )
        self.write("tests/test_clean.py", CLEAN)
        self.write("tests/test_polluter.py", POLLUTER)
        proc = self.run_script("tests/test_x.py::TestC::test_y")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_polluter.py\n", proc.stdout)

    def test_parametrized_victim(self):
        self.write(
            "tests/test_p.py",
            "import app\nimport pytest\n\n\n"
            "@pytest.mark.parametrize('n', [1, 2])\n"
            "def test_y(n):\n    assert not (app.FLAG and n == 2)\n",
        )
        self.write("tests/test_clean.py", CLEAN)
        self.write("tests/test_polluter.py", POLLUTER)
        proc = self.run_script("tests/test_p.py::test_y[2]")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_polluter.py\n", proc.stdout)

    def test_parametrized_victim_reads_only_its_own_case(self):
        # Pollution breaks test_y[2] but test_y[1] stays green, so [1] has nothing to find.
        self.write(
            "tests/test_p.py",
            "import app\nimport pytest\n\n\n"
            "@pytest.mark.parametrize('n', [1, 2])\n"
            "def test_y(n):\n    assert not (app.FLAG and n == 2)\n",
        )
        self.write("tests/test_polluter.py", POLLUTER)
        proc = self.run_script("tests/test_p.py::test_y[1]")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("don't break the victim", proc.stdout)

    def test_victim_in_a_nested_test_directory(self):
        self.write(
            "tests/sub/test_victim.py", VICTIM
        )
        self.write("tests/test_polluter.py", POLLUTER)
        proc = self.run_script("tests/sub/test_victim.py::test_victim")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_polluter.py\n", proc.stdout)

    def test_wrong_test_name_exits_2_victim_didnt_run(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_clean.py", CLEAN)
        proc = self.run_script("tests/test_victim.py::test_nope")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("didn't run", proc.stderr)

    def test_wrong_file_exits_2_victim_didnt_run(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_clean.py", CLEAN)
        proc = self.run_script("tests/test_missing.py::test_victim")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("didn't run", proc.stderr)

    def test_victim_with_dot_slash_prefix_is_found(self):
        # pytest writes the classname "tests.test_victim"; a leading "./" must not change it.
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_polluter.py", POLLUTER)
        proc = self.run_script("./" + VICTIM_ID)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_polluter.py\n", proc.stdout)

    def test_victim_with_absolute_path_is_found(self):
        # The resolved form; the symlinked form has its own test below.
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_polluter.py", POLLUTER)
        proc = self.run_script(f"{self.root.resolve()}/{VICTIM_ID}")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_polluter.py\n", proc.stdout)

    def test_victim_with_absolute_path_through_a_symlinked_directory_is_found(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_polluter.py", POLLUTER)
        links = tempfile.TemporaryDirectory()
        self.addCleanup(links.cleanup)
        link = Path(links.name) / "project-link"
        link.symlink_to(self.root, target_is_directory=True)
        proc = self.run_script(f"{link}/{VICTIM_ID}")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_polluter.py\n", proc.stdout)

    def test_victims_own_file_is_not_a_candidate_when_given_with_dot_slash(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_clean.py", CLEAN)
        self.write("tests/test_polluter.py", POLLUTER)
        proc = self.run_script("./" + VICTIM_ID)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("2 candidates", proc.stdout)

    def test_victims_own_file_is_not_a_candidate_when_given_as_absolute_path(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_clean.py", CLEAN)
        self.write("tests/test_polluter.py", POLLUTER)
        proc = self.run_script(f"{self.root.resolve()}/{VICTIM_ID}")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("2 candidates", proc.stdout)

    # -- usage errors -----------------------------------------------------

    def test_runs_zero_is_a_usage_error(self):
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_polluter.py", POLLUTER)
        proc = self.run_script(VICTIM_ID, "--runs", "0")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("--runs", proc.stderr)

    def test_cmd_without_tests_placeholder_is_a_usage_error(self):
        proc = self.run_script("victim", "--cmd", "true", "a", "b", python=False)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("{tests}", proc.stderr)

    def test_cmd_placeholder_must_be_its_own_word(self):
        proc = self.run_script("victim", "--cmd", "run x{tests}", "a", "b", python=False)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_tests_with_cmd_is_a_usage_error(self):
        proc = self.run_script("victim", "--tests", "tests/test_a.py", "--cmd", "run {tests}", python=False)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("--cmd", proc.stderr)

    def test_no_candidates_is_a_usage_error(self):
        self.write("tests/test_victim.py", VICTIM)
        proc = self.run_script(VICTIM_ID)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("no candidates", proc.stderr)

    # -- --cmd mode -------------------------------------------------------

    def cmd_template(self, script_body):
        """Write check.py and return a --cmd template that runs it with {tests}."""
        self.write("check.py", script_body)
        return f"{shlex.quote(sys.executable)} check.py {{tests}}"

    def test_cmd_mode_nonzero_exit_counts_as_victim_failing(self):
        # Fails only when "bad" ran before the victim (the victim is always the last argument).
        template = self.cmd_template(
            "import sys\n"
            "args = sys.argv[1:]\n"
            "sys.exit(1 if 'bad' in args[:-1] else 0)\n"
        )
        proc = self.run_script(
            "--cmd", template, "victim", "one", "two", "bad", "three", "four", python=False
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: bad\n", proc.stdout)
        self.assertIn("5 candidates", proc.stdout)

    def test_cmd_mode_victim_failing_alone_is_not_pollution(self):
        template = self.cmd_template("import sys\nsys.exit(3)\n")
        proc = self.run_script("--cmd", template, "victim", "one", "two", python=False)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("not pollution", proc.stdout)

    def test_cmd_mode_candidates_that_do_not_break_it_exit_1(self):
        template = self.cmd_template("import sys\nsys.exit(0)\n")
        proc = self.run_script("--cmd", template, "victim", "one", "two", python=False)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("don't break the victim", proc.stdout)

    def test_cmd_mode_file_result_has_no_tests_flag_hint(self):
        # --tests is refused with --cmd, so a file-level result must not suggest it.
        template = self.cmd_template(
            "import sys\n"
            "args = sys.argv[1:]\n"
            "sys.exit(1 if 'bad.py' in args[:-1] else 0)\n"
        )
        proc = self.run_script("--cmd", template, "victim", "ok.py", "bad.py", python=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: bad.py\n", proc.stdout)
        self.assertNotIn("next:", proc.stdout)

    def test_cmd_mode_needs_candidates(self):
        template = self.cmd_template("import sys\nsys.exit(0)\n")
        proc = self.run_script("--cmd", template, "victim", python=False)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("no candidates", proc.stderr)

    # -- --runs -----------------------------------------------------------

    def write_flaky_project(self):
        """The polluter sets the flag only on its even-numbered executions (a counter file
        in the project root tracks them), so one run per check misses it, two runs catch it."""
        self.write("tests/test_victim.py", VICTIM)
        self.write("tests/test_a_clean.py", CLEAN)
        self.write(
            "tests/test_b_flaky_polluter.py",
            "import pathlib\n\nimport app\n\n\n"
            "def test_sometimes_pollutes():\n"
            "    counter = pathlib.Path(__file__).resolve().parent.parent / 'count.txt'\n"
            "    n = int(counter.read_text()) + 1 if counter.exists() else 1\n"
            "    counter.write_text(str(n))\n"
            "    if n % 2 == 0:\n"
            "        app.FLAG = True\n",
        )

    def test_single_run_misses_a_polluter_that_acts_only_sometimes(self):
        self.write_flaky_project()
        proc = self.run_script(VICTIM_ID)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("--runs", proc.stdout)
        self.assertIn("1 run(s) per check", proc.stdout)

    def test_runs_flag_finds_a_polluter_that_acts_only_sometimes(self):
        self.write_flaky_project()
        proc = self.run_script(VICTIM_ID, "--runs", "2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("polluter: tests/test_b_flaky_polluter.py\n", proc.stdout)
        self.assertIn("2 run(s) per check", proc.stdout)


if __name__ == "__main__":
    unittest.main()
