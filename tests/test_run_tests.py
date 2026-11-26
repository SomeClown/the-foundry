"""tests/run_tests.py: the runner that runs every test file as its own process, side by side.

Each test copies the runner into <tmp>/tests/ beside small fixture modules and runs the copy with
sys.executable, from a working directory that is neither the fixture root nor the repo. What it pins:
the exit codes (0, 1, 2, 130), the lines the gate's grep shows (one Ran, one status), the counts summed
across files (checked against `python -m unittest discover -s tests` on the same fixture), and the
process-group kill of a file that hangs, ignores SIGTERM or leaves a child behind.

Hermetic: temp dirs only, no network. The one environment change is PYTHONIOENCODING, set for one
test through mock.patch.dict so the runner's child inherits it (the runner gets no env= by design).
Waits use files as handshakes with generous upper bounds, never a fixed sleep as the proof; every
`sleep 300` a fixture starts is killed in cleanup even when the test fails.
Standard library only; runs on Python 3.9 and later.
"""
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
RUNNER_SRC = ROOT / "tests" / "run_tests.py"

GATE_GREP = re.compile(r"^(FAIL|ERROR):|^Ran |^OK|^FAILED")
RAN_LINE = re.compile(r"^Ran (\d+) tests? in [\d.]+s$", re.M)
STATUS_LINE = re.compile(r"^(OK|FAILED)(?: \((.*)\))?$", re.M)

HEAD = "import os\nimport sys\nimport time\nimport unittest\n"


def module(body):
    return HEAD + textwrap.dedent(body)


def passing(n=1):
    tests = "".join("    def test_%d(self):\n        self.assertTrue(True)\n" % i for i in range(n))
    return module("class T(unittest.TestCase):\n") + tests


# Starts `sleep 300` with inherited stdout, hands over both pids by an atomic rename, then hangs.
HANG_BODY = """
    HERE = os.path.dirname(os.path.abspath(__file__))
    %s
    import subprocess

    class T(unittest.TestCase):
        def test_hang(self):
            child = subprocess.Popen(["sleep", "300"])
            tmp = os.path.join(HERE, "pids.tmp")
            with open(tmp, "w") as f:
                f.write("%%d %%d" %% (child.pid, os.getpid()))
            os.replace(tmp, os.path.join(HERE, "pids"))
            time.sleep(300)
"""
HANG = module(HANG_BODY % "")
HANG_IGNORING_SIGTERM = module(HANG_BODY % "import signal; signal.signal(signal.SIGTERM, signal.SIG_IGN)")


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def gate_lines(text):
    return [line for line in text.splitlines() if GATE_GREP.match(line)]


def closing(text):
    """(Ran total, {status key: n}, status word) from the last Ran and status lines of an output."""
    ran = RAN_LINE.findall(text)
    status = STATUS_LINE.findall(text)
    counts = {}
    if status and status[-1][1]:
        for key, val in re.findall(r"([a-z ]+)=(\d+)", status[-1][1]):
            counts[key.strip()] = int(val)
    return (int(ran[-1]) if ran else None), counts, (status[-1][0] if status else None)


class RunnerCase(unittest.TestCase):
    def fixture(self, files, packages=()):
        """A fresh <tmp>/tests/ holding a copy of the runner and the given {name: text} files."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        (root / "tests").mkdir()
        shutil.copy(RUNNER_SRC, root / "tests" / "run_tests.py")
        for name, text in files.items():
            if isinstance(text, bytes):
                (root / "tests" / name).write_bytes(text)
            else:
                (root / "tests" / name).write_text(text, encoding="utf-8")
        for pkg in packages:
            (root / "tests" / pkg).mkdir()
            (root / "tests" / pkg / "__init__.py").write_text("", encoding="utf-8")
        return root

    def elsewhere(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name).resolve()

    def run_runner(self, root, *args, timeout=120):
        """Run the fixture's runner copy from an unrelated directory; returns the CompletedProcess."""
        return subprocess.run(
            [sys.executable, str(root / "tests" / "run_tests.py"), *args],
            cwd=str(self.elsewhere()), stdin=subprocess.DEVNULL, capture_output=True,
            text=True, errors="replace", timeout=timeout,
        )

    def discover(self, root):
        return subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=str(root), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
        )

    def kill_pids_on_cleanup(self, root):
        def cleanup():
            try:
                pids = [int(p) for p in (root / "tests" / "pids").read_text().split()]
            except (OSError, ValueError):
                return
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    continue
        self.addCleanup(cleanup)

    def read_pids(self, root):
        text = (root / "tests" / "pids").read_text()
        return [int(p) for p in text.split()]

    def assert_gone_within(self, pids, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and any(alive(p) for p in pids):
            time.sleep(0.05)
        self.assertEqual([p for p in pids if alive(p)], [], "processes still running after the runner returned")


class AllGoodTest(RunnerCase):
    def test_skips_of_every_kind_are_counted_and_the_gate_grep_shows_one_ran_and_one_ok_line(self):
        root = self.fixture({
            "test_a.py": module("""
                class T(unittest.TestCase):
                    def test_one(self):
                        self.assertTrue(True)

                    @unittest.skip("decorated")
                    def test_two(self):
                        self.assertTrue(False)
            """),
            "test_b.py": module("""
                class T(unittest.TestCase):
                    @classmethod
                    def setUpClass(cls):
                        raise unittest.SkipTest("class level")

                    def test_one(self):
                        self.assertTrue(False)
            """),
            "test_c.py": module("""
                raise unittest.SkipTest("module level")
            """),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        grep = gate_lines(got.stdout)
        self.assertEqual(len(grep), 2, grep)
        self.assertRegex(grep[0], r"^Ran 3 tests in \d+\.\d{3}s$")  # a: 2, b: none (class skipped), c: 1
        self.assertEqual(grep[1], "OK (skipped=3)")
        want = closing(self.discover(root).stderr)
        self.assertEqual(closing(got.stdout)[:2], want[:2])

    def test_progress_lines_say_ok_with_the_count_and_the_skips_and_never_start_with_a_gate_word(self):
        root = self.fixture({
            "test_a.py": passing(2),
            "test_b.py": module("""
                class T(unittest.TestCase):
                    @unittest.skip("x")
                    def test_one(self):
                        self.assertTrue(True)
            """),
        })
        got = self.run_runner(root)
        progress = [l for l in got.stdout.splitlines() if l.startswith("module ")]
        self.assertEqual(len(progress), 2, got.stdout)
        self.assertTrue(any(re.fullmatch(r"module test_a: ok, 2 tests, \d+\.\ds", l) for l in progress), progress)
        self.assertTrue(any(re.fullmatch(r"module test_b: ok, 1 tests, 1 skipped, \d+\.\ds", l) for l in progress), progress)
        self.assertRegex(got.stdout, r"(?m)^runner: 2 test files, \d+ at a time, 0 failed$")


class FailureShapesTest(RunnerCase):
    def test_one_failing_test_exits_1_and_the_other_files_are_still_summed(self):
        root = self.fixture({
            "test_bad.py": module("""
                class T(unittest.TestCase):
                    def test_a(self):
                        self.assertEqual(1, 2)

                    def test_b(self):
                        self.assertTrue(True)
            """),
            "test_good.py": passing(3),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        grep = gate_lines(got.stdout)
        self.assertEqual(len(grep), 3, grep)
        self.assertTrue(grep[0].startswith("FAIL: test_a (test_bad.T"), grep)
        self.assertRegex(grep[1], r"^Ran 5 tests in ")
        self.assertEqual(grep[2], "FAILED (failures=1)")
        self.assertIn("module test_bad: failed (exit 1), 2 tests", got.stdout)
        self.assertRegex(got.stdout, r"(?m)^runner: 2 test files, \d+ at a time, 1 failed$")

    def test_an_import_error_is_one_error_line_and_one_error_in_the_total(self):
        root = self.fixture({
            "test_imp.py": "import no_such_module_for_the_runner_tests\n",
            "test_good.py": passing(1),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        grep = gate_lines(got.stdout)
        self.assertEqual(len(grep), 3, grep)
        self.assertTrue(grep[0].startswith("ERROR: test_imp"), grep)
        self.assertEqual(grep[2], "FAILED (errors=1)")

    def test_a_syntax_error_is_one_error_line_and_one_error_in_the_total(self):
        root = self.fixture({"test_syn.py": "def broken(:\n", "test_good.py": passing(1)})
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        grep = gate_lines(got.stdout)
        self.assertEqual(len(grep), 3, grep)
        self.assertTrue(grep[0].startswith("ERROR: test_syn"), grep)
        self.assertEqual(grep[2], "FAILED (errors=1)")

    def test_a_file_that_exits_mid_run_is_one_error_naming_its_exit_code_or_missing_summary(self):
        root = self.fixture({
            "test_die.py": module("""
                class T(unittest.TestCase):
                    def test_die(self):
                        os._exit(3)
            """),
            "test_good.py": passing(2),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        grep = gate_lines(got.stdout)
        self.assertEqual(len(grep), 3, grep)
        self.assertIn(grep[0], ("ERROR: test_die (exit 3)", "ERROR: test_die (no summary)"))
        self.assertRegex(grep[1], r"^Ran 2 tests in ")
        self.assertEqual(grep[2], "FAILED (errors=1)")

    def test_an_empty_file_is_an_error_that_says_no_tests_ran_on_every_python(self):
        root = self.fixture({"test_empty.py": "", "test_good.py": passing(1)})
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        grep = gate_lines(got.stdout)
        self.assertEqual(grep[0], "ERROR: test_empty (no tests ran)")
        self.assertEqual(grep[-1], "FAILED (errors=1)")
        self.assertIn("module test_empty: failed (no tests ran), 0 tests", got.stdout)

    def test_unexpected_success_fails_the_run_and_shows_in_the_closing_counts(self):
        root = self.fixture({
            "test_x.py": module("""
                class T(unittest.TestCase):
                    @unittest.expectedFailure
                    def test_wrongly_passes(self):
                        self.assertTrue(True)

                    @unittest.expectedFailure
                    def test_rightly_fails(self):
                        self.assertTrue(False)
            """),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        ran, counts, word = closing(got.stdout)
        self.assertEqual((ran, word), (2, "FAILED"))
        self.assertEqual(counts.get("unexpected successes"), 1, counts)
        self.assertEqual(counts.get("expected failures"), 1, counts)

    def test_expected_failures_alone_keep_the_run_green(self):
        root = self.fixture({
            "test_x.py": module("""
                class T(unittest.TestCase):
                    @unittest.expectedFailure
                    def test_rightly_fails(self):
                        self.assertTrue(False)
            """),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        self.assertEqual(gate_lines(got.stdout)[-1], "OK (expected failures=1)")

    def test_counts_add_up_when_several_files_fail_in_different_ways(self):
        root = self.fixture({
            "test_fail.py": module("""
                class T(unittest.TestCase):
                    def test_a(self):
                        self.assertTrue(False)

                    def test_b(self):
                        self.assertTrue(True)
            """),
            "test_err.py": module("""
                class T(unittest.TestCase):
                    def test_a(self):
                        raise RuntimeError("boom")

                    @unittest.skip("x")
                    def test_b(self):
                        self.assertTrue(True)
            """),
            "test_imp.py": "import no_such_module_for_the_runner_tests\n",
            "test_die.py": module("""
                class T(unittest.TestCase):
                    def test_die(self):
                        os._exit(7)
            """),
            "test_empty.py": "",
            "test_good.py": passing(3),
        })
        got = self.run_runner(root, "-j", "3")
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        # Ran: 2 + 2 + 1 (the import error) + 0 + 0 + 3. Errors: boom, import, die (runner's), empty (runner's).
        self.assertEqual(closing(got.stdout), (8, {"failures": 1, "errors": 4, "skipped": 1}, "FAILED"))
        self.assertRegex(got.stdout, r"(?m)^runner: 6 test files, 3 at a time, 5 failed$")

    def test_a_failing_file_and_a_hanging_file_in_one_run_both_report_and_the_rest_still_count(self):
        root = self.fixture({
            "test_bad.py": module("""
                class T(unittest.TestCase):
                    def test_a(self):
                        self.assertTrue(False)
            """),
            "test_hang.py": HANG,
            "test_good.py": passing(2),
        })
        self.kill_pids_on_cleanup(root)
        started = time.monotonic()
        got = self.run_runner(root, "-j", "3", "--timeout", "3")
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        grep = gate_lines(got.stdout)
        self.assertTrue(any(l.startswith("FAIL: test_a (test_bad.T") for l in grep), grep)
        self.assertIn("ERROR: test_hang (timed out after 3s)", grep)
        self.assertEqual(closing(got.stdout), (3, {"failures": 1, "errors": 1}, "FAILED"))
        self.assert_gone_within(self.read_pids(root))


class HangTest(RunnerCase):
    def test_a_hang_is_killed_with_its_stray_child_and_reported_as_a_timeout(self):
        root = self.fixture({"test_hang.py": HANG})
        self.kill_pids_on_cleanup(root)
        started = time.monotonic()
        got = self.run_runner(root, "--timeout", "3")
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        self.assertIn("ERROR: test_hang (timed out after 3s)", gate_lines(got.stdout))
        self.assertIn("module test_hang: failed (timed out after 3s)", got.stdout)
        pids = self.read_pids(root)
        self.assertEqual(len(pids), 2)
        self.assert_gone_within(pids)

    def test_a_child_that_ignores_sigterm_is_killed_after_the_grace_period(self):
        root = self.fixture({"test_stubborn.py": HANG_IGNORING_SIGTERM})
        self.kill_pids_on_cleanup(root)
        started = time.monotonic()
        got = self.run_runner(root, "--timeout", "2")
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 30)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        self.assertIn("ERROR: test_stubborn (timed out after 2s)", gate_lines(got.stdout))
        self.assertGreaterEqual(elapsed, 2)
        self.assert_gone_within(self.read_pids(root))


class InterruptTest(RunnerCase):
    def test_ctrl_c_exits_130_and_leaves_nothing_running(self):
        root = self.fixture({"test_hang.py": HANG, "test_good.py": passing(1)})
        self.kill_pids_on_cleanup(root)
        out = tempfile.TemporaryFile()
        self.addCleanup(out.close)
        proc = subprocess.Popen(
            [sys.executable, str(root / "tests" / "run_tests.py")], cwd=str(self.elsewhere()),
            stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL),
        )
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.monotonic() + 60
        while not (root / "tests" / "pids").exists() and time.monotonic() < deadline and proc.poll() is None:
            time.sleep(0.05)
        self.assertTrue((root / "tests" / "pids").exists(), "the hanging test never started")
        pids = self.read_pids(root)
        proc.send_signal(signal.SIGINT)
        self.assertEqual(proc.wait(timeout=30), 130)
        self.assert_gone_within(pids)


class ParityWithDiscoverTest(RunnerCase):
    def test_same_ran_failures_errors_skips_and_ids_as_discover_even_from_another_directory(self):
        root = self.fixture({
            "helper_mod.py": "VALUE = 42\n",
            "test_one.py": module("""
                import helper_mod

                class T(unittest.TestCase):
                    def test_imports_a_sibling(self):
                        self.assertEqual(helper_mod.VALUE, 42)

                    def test_working_directory_is_the_fixture_root(self):
                        root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
                        self.assertEqual(os.path.realpath(os.getcwd()), root)
            """),
            "test_two.py": module("""
                class T(unittest.TestCase):
                    def test_f(self):
                        self.assertEqual("a", "b")

                    def test_e(self):
                        raise ValueError("x")

                    @unittest.skip("s")
                    def test_s(self):
                        self.assertTrue(True)

                    @unittest.expectedFailure
                    def test_x(self):
                        self.assertTrue(False)
            """),
            "test_three.py": module("""
                class T(unittest.TestCase):
                    @classmethod
                    def setUpClass(cls):
                        raise unittest.SkipTest("c")

                    def test_a(self):
                        self.assertTrue(True)
            """),
            "test_four.py": module("raise unittest.SkipTest('m')\n"),
        })
        got = self.run_runner(root)
        want = self.discover(root)
        self.assertEqual(got.returncode, 1)
        self.assertEqual(want.returncode, 1)
        self.assertEqual(closing(got.stdout), closing(want.stderr), got.stdout)
        ids = lambda text: sorted(l for l in text.splitlines() if re.match(r"(FAIL|ERROR): ", l))  # noqa: E731
        self.assertEqual(ids(got.stdout), ids(want.stderr))
        self.assertEqual(len(ids(got.stdout)), 2)

    def test_the_summed_total_equals_discover_on_a_larger_mixed_fixture(self):
        files = {"test_f%d.py" % i: passing(i + 1) for i in range(6)}
        files["test_skips.py"] = module("""
            class T(unittest.TestCase):
                @unittest.skipIf(True, "x")
                def test_a(self):
                    self.assertTrue(True)

                @unittest.skipUnless(False, "y")
                def test_b(self):
                    self.assertTrue(True)
        """)
        root = self.fixture(files)
        got = self.run_runner(root, "-j", "4")
        want = self.discover(root)
        self.assertEqual((got.returncode, want.returncode), (0, 0))
        self.assertEqual(closing(got.stdout)[:2], closing(want.stderr)[:2])
        self.assertEqual(closing(got.stdout)[0], 23)


class OutputHandlingTest(RunnerCase):
    def test_tests_that_print_ok_and_ran_lines_do_not_change_the_summary(self):
        root = self.fixture({
            "test_noisy.py": module("""
                class T(unittest.TestCase):
                    def test_a(self):
                        print("Ran 5 tests in 0.1s")
                        print("OK")
                        self.assertTrue(True)

                    def test_b(self):
                        self.assertTrue(True)

                    def test_c(self):
                        self.assertTrue(True)
            """),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        grep = gate_lines(got.stdout)
        self.assertEqual(len(grep), 2, grep)
        self.assertRegex(grep[0], r"^Ran 3 tests in ")
        self.assertEqual(grep[1], "OK")

    def test_a_failing_test_that_prints_ok_still_reports_its_failure_in_the_closing_line(self):
        root = self.fixture({
            "test_noisy.py": module("""
                class T(unittest.TestCase):
                    def test_a(self):
                        print("OK")
                        self.assertTrue(False)
            """),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        self.assertEqual(closing(got.stdout), (1, {"failures": 1}, "FAILED"))

    def test_flushed_ok_and_ran_lines_printed_mid_run_do_not_change_the_summary(self):
        root = self.fixture({
            "test_noisy.py": module("""
                class T(unittest.TestCase):
                    def test_a(self):
                        print("Ran 9 tests in 0.1s", flush=True)
                        print("OK", flush=True)
                        self.assertTrue(True)
            """),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        self.assertEqual(closing(got.stdout)[:2], (1, {}))

    def test_docstring_lines_under_verbose_do_not_change_the_summary(self):
        root = self.fixture({
            "test_docs.py": module('''
                class T(unittest.TestCase):
                    def test_a(self):
                        """Ran 7 tests in 0.2s"""
                        self.assertTrue(True)

                    def test_b(self):
                        """OK"""
                        self.assertTrue(True)

                    def test_c(self):
                        """FAILED (failures=9)"""
                        self.assertTrue(True)
            '''),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        self.assertEqual(closing(got.stdout)[:2], (3, {}))
        self.assertEqual(got.stdout.count("\nRan "), 1)

    def test_output_that_is_not_utf8_does_not_crash_the_runner(self):
        root = self.fixture({
            "test_bytes.py": module("""
                class T(unittest.TestCase):
                    def test_a(self):
                        sys.stdout.buffer.write(b"\\xff\\xfe bad \\x80\\n")
                        sys.stdout.flush()
                        sys.stderr.buffer.write(b"\\xc3\\x28 worse\\n")
                        sys.stderr.flush()
                        self.assertTrue(False)
            """),
        })
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        self.assertNotIn("Traceback", got.stderr)
        self.assertEqual(closing(got.stdout), (1, {"failures": 1}, "FAILED"))

    def test_output_that_is_not_utf8_does_not_crash_the_runner_when_its_own_stdout_is_ascii(self):
        root = self.fixture({
            "test_bytes.py": module("""
                class T(unittest.TestCase):
                    def test_a(self):
                        sys.stdout.buffer.write(b"\\xff\\xfe bad \\x80\\n")
                        sys.stdout.flush()
                        self.assertTrue(False)
            """),
        })
        with mock.patch.dict(os.environ, {"PYTHONIOENCODING": "ascii"}):
            got = self.run_runner(root)
        self.assertNotIn("Traceback", got.stderr)
        self.assertEqual(closing(got.stdout), (1, {"failures": 1}, "FAILED"), got.stdout + got.stderr)

    def test_megabytes_of_output_from_a_passing_and_a_failing_file_are_handled(self):
        chatter = module("""
            class T(unittest.TestCase):
                def test_a(self):
                    line = "y" * 99 + "\\n"
                    for _ in range(50000):
                        sys.stdout.write(line)
                    sys.stdout.flush()
                    self.assertTrue(%s)
        """)
        root = self.fixture({"test_loud_ok.py": chatter % "True", "test_loud_bad.py": chatter % "False"})
        started = time.monotonic()
        got = self.run_runner(root)
        self.assertLess(time.monotonic() - started, 60)
        self.assertEqual(got.returncode, 1, got.stderr)
        self.assertGreater(len(got.stdout), 4_000_000)
        self.assertEqual(closing(got.stdout), (2, {"failures": 1}, "FAILED"))


class ConcurrencyTest(RunnerCase):
    MEET = """
        HERE = os.path.dirname(os.path.abspath(__file__))

        def meet(me, other):
            flags = os.path.join(HERE, "flags")
            os.makedirs(flags, exist_ok=True)
            open(os.path.join(flags, me), "w").close()
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                if os.path.exists(os.path.join(flags, other)):
                    return True
                time.sleep(0.02)
            return False

        class T(unittest.TestCase):
            def test_meets_the_other_file(self):
                self.assertTrue(meet(%r, %r))
    """

    def meeting_files(self):
        return {
            "test_p1.py": module(self.MEET % ("one", "two")),
            "test_p2.py": module(self.MEET % ("two", "one")),
        }

    def test_two_files_that_wait_for_each_other_pass_two_at_a_time(self):
        got = self.run_runner(self.fixture(self.meeting_files()), "-j", "2")
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        self.assertIn("2 at a time", got.stdout)

    def test_the_same_two_files_fail_one_at_a_time(self):
        got = self.run_runner(self.fixture(self.meeting_files()), "-j", "1")
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        self.assertIn("1 at a time", got.stdout)

    def test_two_runners_at_once_on_the_same_fixture_both_finish_with_their_own_summary(self):
        root = self.fixture({"test_a.py": passing(2), "test_b.py": passing(3)})
        outs = [tempfile.TemporaryFile() for _ in range(2)]
        for o in outs:
            self.addCleanup(o.close)
        procs = [
            subprocess.Popen([sys.executable, str(root / "tests" / "run_tests.py")], cwd=str(self.elsewhere()),
                             stdin=subprocess.DEVNULL, stdout=o, stderr=subprocess.STDOUT)
            for o in outs
        ]
        self.addCleanup(lambda: [p.kill() for p in procs if p.poll() is None])
        for p in procs:
            self.assertEqual(p.wait(timeout=120), 0)
        for o in outs:
            o.seek(0)
            self.assertEqual(closing(o.read().decode())[:2], (5, {}))


class ArgumentsTest(RunnerCase):
    def test_named_files_run_alone_in_any_of_the_three_spellings(self):
        root = self.fixture({"test_a.py": passing(1), "test_b.py": passing(2), "test_c.py": passing(4)})
        got = self.run_runner(root, "test_a", "tests/test_b.py")
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        self.assertEqual(closing(got.stdout)[0], 3)
        self.assertNotIn("test_c", got.stdout)
        got = self.run_runner(root, "test_c.py")
        self.assertEqual(closing(got.stdout)[0], 4)

    def test_naming_a_file_twice_runs_it_once(self):
        root = self.fixture({"test_a.py": passing(2)})
        got = self.run_runner(root, "test_a", "test_a.py", "tests/test_a.py")
        self.assertEqual(closing(got.stdout)[0], 2)
        self.assertEqual(got.stdout.count("module test_a: ok"), 1)

    def test_a_bad_option_value_exits_2_before_running_anything(self):
        root = self.fixture({"test_a.py": passing(1)})
        for args in (["-j", "0"], ["--jobs", "-1"], ["--jobs", "many"], ["--timeout", "0"], ["--timeout", "1.5"]):
            with self.subTest(args=args):
                got = self.run_runner(root, *args)
                self.assertEqual(got.returncode, 2, got.stdout + got.stderr)
                self.assertNotIn("module test_a", got.stdout)

    def test_an_unknown_file_exits_2_and_names_it_on_stderr(self):
        root = self.fixture({"test_a.py": passing(1)})
        got = self.run_runner(root, "test_a", "nope")
        self.assertEqual(got.returncode, 2, got.stdout + got.stderr)
        self.assertIn("error: no test file tests/nope.py", got.stderr)
        self.assertNotIn("module test_a", got.stdout)

    def test_a_path_that_climbs_or_descends_is_refused_with_exit_2(self):
        root = self.fixture({"test_a.py": passing(1)})
        (root / "tests" / "sub").mkdir()
        (root / "tests" / "sub" / "test_in.py").write_text(passing(1), encoding="utf-8")
        for arg in ("sub/test_in", "../tests/test_a", "tests/sub/test_in.py"):
            with self.subTest(arg=arg):
                self.assertEqual(self.run_runner(root, arg).returncode, 2)

    def test_a_package_folder_under_tests_exits_2_with_the_reason(self):
        root = self.fixture({"test_a.py": passing(1)}, packages=("pkg",))
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 2, got.stdout + got.stderr)
        self.assertIn("error: tests/pkg is a package; discover would run it and this runner does not", got.stderr)
        self.assertEqual(self.run_runner(root, "test_a").returncode, 2)

    def test_a_folder_without_init_py_is_not_a_package(self):
        root = self.fixture({"test_a.py": passing(1)})
        (root / "tests" / "plain").mkdir()
        self.assertEqual(self.run_runner(root).returncode, 0)

    def test_no_test_files_at_all_exits_2(self):
        got = self.run_runner(self.fixture({}))
        self.assertEqual(got.returncode, 2, got.stdout + got.stderr)

    def test_files_run_and_print_in_name_order_for_the_failure_dumps(self):
        bad = module("""
            class T(unittest.TestCase):
                def test_a(self):
                    self.assertTrue(False)
        """)
        root = self.fixture({"test_b.py": bad, "test_a.py": bad, "test_c.py": bad})
        got = self.run_runner(root, "-j", "3")
        dumps = re.findall(r"(?m)^module (test_\w) output:$", got.stdout)
        self.assertEqual(dumps, ["test_a", "test_b", "test_c"])


class OddFileNameTest(RunnerCase):
    def test_a_name_with_non_ascii_letters_runs_like_any_other(self):
        root = self.fixture({"test_café.py": passing(2)})
        got = self.run_runner(root)
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        self.assertEqual(closing(got.stdout)[0], 2)

    def test_names_unittest_cannot_load_are_a_loud_failure_never_a_green_run_or_a_traceback(self):
        for name in ("test_sp ace.py", "test_quo'te.py", "test_dollar$x.py", "test_brack[1].py", "test-dash.py"):
            with self.subTest(name=name):
                root = self.fixture({name: passing(1), "test_good.py": passing(1)})
                got = self.run_runner(root)
                self.assertNotIn("Traceback", got.stderr)
                self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
                self.assertIn("ERROR: %s (no tests ran)" % name[:-3], got.stdout)
                self.assertEqual(closing(got.stdout)[:2], (1, {"errors": 1}))


if __name__ == "__main__":
    unittest.main()
