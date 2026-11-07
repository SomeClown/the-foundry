"""Adversarial tests for the brief command in skills/run-plan/SKILL.md."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from test_task_brief import brief_command  # noqa: E402

SHELLS = {"bash": ("bash", "-c"), "zsh": ("zsh", "-f", "-c")}
NOCLOBBER = {"bash": "set -o noclobber\n", "zsh": "setopt noclobber\n"}
PLANS = (
    ROOT / "docs" / "plans" / "2026-11-06-directory-file-rules.md",
    ROOT / "docs" / "plans" / "2026-11-05-per-file-investigation.md",
)
BASE = "75ad32e"


def run(plan_bytes, n, shell=("bash", "-c"), plan_name="plan.md", out_parts=("out",), env_extra=None):
    """Run the shipped command. Returns (exit code, brief bytes or None, stdout, stderr, out dir)."""
    with tempfile.TemporaryDirectory() as tmp:
        plan = Path(tmp) / plan_name
        plan.write_bytes(plan_bytes)
        out = Path(tmp).joinpath(*out_parts)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PLAN": str(plan),
            "N": str(n),
            "OUT": str(out),
        }
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            [*shell, brief_command()], capture_output=True, text=True, env=env, cwd=tmp
        )
        brief = out / f"task-{n}-brief.md"
        data = brief.read_bytes() if brief.exists() else None
        return proc.returncode, data, proc.stdout, proc.stderr, out


class AdversarialBriefTest(unittest.TestCase):
    def assertBrief(self, plan, n, expected, **kw):
        code, data, _, err, _ = run(plan, n, **kw)
        self.assertEqual(code, 0, err)
        self.assertEqual(data, expected)

    def assertMissing(self, plan, n, **kw):
        code, data, _, err, _ = run(plan, n, **kw)
        self.assertNotEqual(code, 0)
        self.assertIsNone(data)
        return err

    def test_crlf_plan_copied_byte_for_byte(self):
        plan = b"### Task 1: One\r\n\r\nbody\r\n\r\n### Task 2: Two\r\n"
        self.assertBrief(plan, 1, b"### Task 1: One\r\n\r\nbody\r\n\r\n")

    def test_crlf_fenced_task_heading_stays_hidden(self):
        plan = b"### Task 1: One\r\n\r\n```\r\n### Task 2: fake\r\n```\r\n\r\n### Task 3: T\r\n"
        self.assertMissing(plan, 2)

    def test_crlf_closing_fence_never_closes_like_the_old_script(self):
        # Same as the old script: a CRLF closing fence never closes, so the rest is hidden.
        plan = b"### Task 1: One\r\n```\r\ncode\r\n```\r\n### Task 2: Two\r\nbody\r\n"
        self.assertBrief(plan, 1, plan)

    def test_unclosed_tilde_fence_hides_everything_after(self):
        plan = b"~~~\n### Task 1: hidden\nx\n"
        self.assertMissing(plan, 1)

    def test_task_before_unclosed_tilde_fence_runs_to_eof(self):
        plan = b"### Task 1: One\n\n~~~\n### Task 2: hidden\n"
        self.assertBrief(plan, 1, plan)
        self.assertMissing(plan, 2)

    def test_n_zero(self):
        plan = b"### Task 0: Zero\nz\n### Task 1: One\n"
        self.assertBrief(plan, 0, b"### Task 0: Zero\nz\n")

    def test_n_zero_missing_fails(self):
        self.assertMissing(b"### Task 1: One\n", 0)

    def test_n1_with_task_10_and_11(self):
        plan = b"### Task 10: Ten\na\n### Task 11: Eleven\nb\n### Task 1: One\nc\n### Task 2: T\n"
        self.assertBrief(plan, 1, b"### Task 1: One\nc\n")
        self.assertBrief(plan, 11, b"### Task 11: Eleven\nb\n")

    def test_n1_does_not_match_task_10_or_11_only(self):
        self.assertMissing(b"### Task 10: Ten\na\n### Task 11: Eleven\nb\n", 1)

    def test_n_with_leading_zero_does_not_match_plain_number(self):
        self.assertMissing(b"### Task 1: One\nx\n", "01")

    def test_plan_path_with_spaces(self):
        self.assertBrief(b"### Task 1: One\nx\n", 1, b"### Task 1: One\nx\n", plan_name="my plan file.md")

    def test_out_does_not_exist_yet_nested(self):
        self.assertBrief(b"### Task 1: One\nx\n", 1, b"### Task 1: One\nx\n", out_parts=("a", "b", "c"))

    def test_out_with_spaces(self):
        self.assertBrief(b"### Task 1: One\nx\n", 1, b"### Task 1: One\nx\n", out_parts=("my out", "dir x"))

    def test_output_line_shows_path_with_spaces_and_count(self):
        code, _, out, err, outdir = run(b"### Task 1: One\nx\n", 1, out_parts=("my out",))
        self.assertEqual(code, 0, err)
        self.assertEqual(out, f"{outdir}/task-1-brief.md (2 lines)\n")

    def test_last_task_with_trailing_newline(self):
        self.assertBrief(b"### Task 1: One\n### Task 2: Two\nlast\n", 2, b"### Task 2: Two\nlast\n")

    def test_last_task_without_trailing_newline_gains_one_like_the_old_script(self):
        # Same as the old script: awk adds the missing final newline.
        plan = b"### Task 1: One\n### Task 2: Two\nlast"
        self.assertBrief(plan, 2, b"### Task 2: Two\nlast\n")

    def test_heading_last_line_without_newline_gains_one_like_the_old_script(self):
        self.assertBrief(b"### Task 1: One", 1, b"### Task 1: One\n")

    def test_empty_plan_fails(self):
        self.assertMissing(b"", 1)

    def test_h1_task_ends_only_at_h1_or_next_task(self):
        plan = b"# Task 1: One\n## sub\nbody\n# Other\nout\n"
        self.assertBrief(plan, 1, b"# Task 1: One\n## sub\nbody\n")

    def test_h4_task_ends_at_h3(self):
        plan = b"#### Task 1: One\nbody\n##### deeper\nd\n### Up\nout\n"
        self.assertBrief(plan, 1, b"#### Task 1: One\nbody\n##### deeper\nd\n")

    def test_h4_task_ends_at_next_task_of_other_level(self):
        plan = b"#### Task 1: One\nbody\n###### Task 2: Two\nout\n"
        self.assertBrief(plan, 1, b"#### Task 1: One\nbody\n")

    def test_task_with_double_space_matches(self):
        self.assertBrief(b"### Task  2: Two\nx\n", 2, b"### Task  2: Two\nx\n")

    def test_task_with_tab_matches(self):
        self.assertBrief(b"### Task\t2: Two\nx\n", 2, b"### Task\t2: Two\nx\n")

    def test_task_with_tab_after_hashes_matches(self):
        self.assertBrief(b"###\tTask 2: Two\nx\n", 2, b"###\tTask 2: Two\nx\n")

    def test_four_space_indented_backticks_do_not_hide_a_task(self):
        plan = b"### Task 1: One\n    ```\n### Task 2: Two\nx\n"
        self.assertBrief(plan, 2, b"### Task 2: Two\nx\n")

    def test_indented_heading_is_not_a_heading(self):
        self.assertMissing(b"  ### Task 1: One\nx\n", 1)

    def test_heading_in_html_comment_matches_like_the_old_script(self):
        # Old script has no HTML-comment handling either: a heading inside a comment counts.
        plan = b"### Task 1: One\n<!--\n### Task 2: Two\nx\n-->\n"
        self.assertBrief(plan, 2, b"### Task 2: Two\nx\n-->\n")

    def test_task_heading_needs_space_after_hashes(self):
        self.assertMissing(b"###Task 1: One\nx\n", 1)

    def test_task_name_is_case_sensitive(self):
        self.assertMissing(b"### task 1: One\nx\n", 1)

    def test_task_number_followed_by_letter_is_not_a_distinct_task(self):
        self.assertBrief(b"### Task 1a: One\nx\n", 1, b"### Task 1a: One\nx\n")

    def test_stale_brief_removed_when_task_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            stale = out / "task-2-brief.md"
            stale.write_text("old")
            plan = Path(tmp) / "p.md"
            plan.write_text("### Task 1: One\n")
            proc = subprocess.run(
                ["bash", "-c", brief_command()], capture_output=True, text=True,
                env={"PATH": os.environ["PATH"], "PLAN": str(plan), "N": "2", "OUT": str(out)},
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(stale.exists())

    def test_non_numeric_n_is_rejected(self):
        # The old script rejected a non-numeric task number (exit 2).
        plan = b"### Task 1: One\nx\n### Task 2: Two\ny\n"
        for bad in ("1|2", ".", "[0-9]", "1 ", "a"):
            with self.subTest(n=bad):
                code, _, _, _, out = run(plan, bad)
                self.assertNotEqual(code, 0)
                self.assertEqual(list(out.glob("*")) if out.exists() else [], [])

    def test_empty_n_is_rejected(self):
        # Old script rejected an empty number. Here "Task  2" (two spaces) matches N="".
        code, _, _, _, out = run(b"### Task  2: Two\nx\n", "")
        self.assertNotEqual(code, 0)

    def test_unset_out_stops_with_a_message_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "p.md"
            plan.write_text("### Task 1: One\nx\n")
            before = sorted(os.listdir(tmp))
            proc = subprocess.run(
                ["bash", "-c", brief_command()], capture_output=True, text=True, cwd=tmp,
                env={"PATH": os.environ["PATH"], "PLAN": str(plan), "N": "1"},
            )
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn("OUT is not set", proc.stderr)
            self.assertEqual(proc.stdout, "")
            self.assertEqual(sorted(os.listdir(tmp)), before)
            self.assertFalse(os.path.exists("/task-1-brief.md"))

    def test_plan_that_is_a_directory_fails_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            proc = subprocess.run(
                ["bash", "-c", brief_command()], capture_output=True, text=True,
                env={"PATH": os.environ["PATH"], "PLAN": tmp, "N": "1", "OUT": str(out)},
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse((out / "task-1-brief.md").exists())

    def test_plan_path_starting_with_dash_is_not_an_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "-plan.md").write_text("### Task 1: One\nx\n")
            out = Path(tmp) / "out"
            proc = subprocess.run(
                ["bash", "-c", brief_command()], capture_output=True, text=True, cwd=tmp,
                env={"PATH": os.environ["PATH"], "PLAN": "-plan.md", "N": "1", "OUT": str(out)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_set_u_and_errexit_shells(self):
        # Behaves the same when the caller's shell has -e and -u on.
        plan = b"### Task 1: One\nx\n"
        self.assertBrief(plan, 1, plan, shell=("bash", "-euc"))

    def test_posix_sh(self):
        plan = b"### Task 1: One\n\n```\n# c\n```\n\n### Task 2: Two\n"
        self.assertBrief(plan, 1, b"### Task 1: One\n\n```\n# c\n```\n\n", shell=("sh", "-c"))

    @unittest.skipIf(shutil.which("dash") is None, "dash not installed")
    def test_dash(self):
        plan = b"### Task 1: One\n\n```\n# c\n```\n\n### Task 2: Two\n"
        self.assertBrief(plan, 1, b"### Task 1: One\n\n```\n# c\n```\n\n", shell=("dash", "-c"))

    @unittest.skipIf(shutil.which("zsh") is None, "zsh not installed")
    def test_zsh_missing_task_fails(self):
        err = self.assertMissing(b"### Task 1: One\n", 2, shell=("zsh", "-f", "-c"))
        self.assertIn("no heading for Task 2", err)

    @unittest.skipIf(shutil.which("zsh") is None, "zsh not installed")
    def test_zsh_path_with_spaces_and_crlf(self):
        plan = b"### Task 1: One\r\nx\r\n"
        self.assertBrief(plan, 1, plan, shell=("zsh", "-f", "-c"), plan_name="a b.md", out_parts=("o u t",))

    @unittest.skipIf(shutil.which("zsh") is None, "zsh not installed")
    def test_zsh_interactive_style_options_off(self):
        # zsh with a "!" in the plan path (history expansion is off in -c, but check).
        plan = b"### Task 1: One\nx\n"
        self.assertBrief(plan, 1, plan, shell=("zsh", "-f", "-c"), plan_name="hey!.md")

    def test_nul_free_binary_bytes_copied_exactly(self):
        plan = b"### Task 1: One\n\xff\xfe caf\xc3\xa9 \\n \\t %s\n"
        self.assertBrief(plan, 1, plan)

    def test_backslashes_preserved(self):
        plan = b"### Task 1: One\nC:\\new\\table \\\\ \\n\n"
        self.assertBrief(plan, 1, plan)

    def test_duplicate_task_headings_copy_both_sections(self):
        plan = b"### Task 1: A\na\n### Task 2: B\nb\n### Task 1: C\nc\n"
        self.assertBrief(plan, 1, b"### Task 1: A\na\n### Task 1: C\nc\n")

    def test_stdout_is_only_the_output_line(self):
        code, _, out, err, _ = run(b"### Task 1: One\nx\n", 1)
        self.assertEqual(code, 0)
        self.assertEqual(out.count("\n"), 1, repr(out))

    def test_fence_with_tab_indent_is_not_a_fence(self):
        plan = b"### Task 1: One\n\t```\n### Task 2: Two\nx\n"
        self.assertBrief(plan, 2, b"### Task 2: Two\nx\n")


def run_shell(shell, env, cwd, prefix=""):
    """Run the shipped command under the named shell with exactly this environment."""
    return subprocess.run([*SHELLS[shell], prefix + brief_command()], capture_output=True, env=env, cwd=cwd)


def base_env(plan, n, out, **extra):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PLAN": str(plan), "N": str(n), "OUT": str(out)}
    env.update(extra)
    return env


def base_command():
    """The brief command as it stood at the base commit, for a byte-for-byte comparison."""
    done = subprocess.run(["git", "-C", str(ROOT), "show", f"{BASE}:skills/run-plan/SKILL.md"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        return None
    text = done.stdout
    start = text.index("### Step 2: Write the brief")
    end = text.index("### Step 3", start)
    return re.findall(r"^```bash\n(.*?)^```$", text[start:end], re.S | re.M)[0]


class ShellCase(unittest.TestCase):
    def tmp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return Path(d.name)


class NoclobberTest(ShellCase):
    """A shell with noclobber on must still get a fresh brief, never the old file."""

    PLAN = b"### Task 1: One\nfresh\n### Task 2: Two\ny\n"

    def test_present_task_overwrites_the_existing_brief(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                tmp = self.tmp()
                (tmp / "plan.md").write_bytes(self.PLAN)
                out = tmp / "out"
                out.mkdir()
                (out / "task-1-brief.md").write_text("stale and much longer than the fresh text\nmore\nmore\n")
                done = run_shell(shell, base_env(tmp / "plan.md", 1, out), tmp, NOCLOBBER[shell])
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual((out / "task-1-brief.md").read_bytes(), b"### Task 1: One\nfresh\n")
                self.assertEqual(done.stdout, f"{out}/task-1-brief.md (2 lines)\n".encode())

    def test_missing_task_removes_the_existing_brief(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                tmp = self.tmp()
                (tmp / "plan.md").write_bytes(self.PLAN)
                out = tmp / "out"
                out.mkdir()
                (out / "task-3-brief.md").write_text("stale\n")
                done = run_shell(shell, base_env(tmp / "plan.md", 3, out), tmp, NOCLOBBER[shell])
                self.assertNotEqual(done.returncode, 0)
                self.assertIn(b"no heading for Task 3", done.stderr)
                self.assertFalse((out / "task-3-brief.md").exists())

    def test_noclobber_with_no_existing_brief_still_works(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                tmp = self.tmp()
                (tmp / "plan.md").write_bytes(self.PLAN)
                done = run_shell(shell, base_env(tmp / "plan.md", 2, tmp / "out"), tmp, NOCLOBBER[shell])
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual((tmp / "out" / "task-2-brief.md").read_bytes(), b"### Task 2: Two\ny\n")


class LocaleTest(ShellCase):
    """Bytes that are not valid UTF-8 are copied whatever the user's locale."""

    PLAN = b"### Task 1: One\nbad \xff\xfe \xc3 \xe2\x82 caf\xc3\xa9\ntail\n### Task 2: Two\n"
    TASK = b"### Task 1: One\nbad \xff\xfe \xc3 \xe2\x82 caf\xc3\xa9\ntail\n"

    def test_invalid_utf8_is_copied_byte_for_byte_in_a_utf8_locale(self):
        for shell in SHELLS:
            for var in ("LC_ALL", "LANG"):
                with self.subTest(shell=shell, var=var):
                    tmp = self.tmp()
                    (tmp / "plan.md").write_bytes(self.PLAN)
                    out = tmp / "out"
                    done = run_shell(shell, base_env(tmp / "plan.md", 1, out, **{var: "en_US.UTF-8"}), tmp)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertEqual((out / "task-1-brief.md").read_bytes(), self.TASK)
                    self.assertEqual(done.stdout, f"{out}/task-1-brief.md (3 lines)\n".encode())
                    self.assertNotIn(b"towc", done.stderr)
                    self.assertNotIn(b"could not read", done.stderr)

    def test_valid_multibyte_text_is_copied_in_a_utf8_locale(self):
        plan = "### Task 1: Caf\u00e9\nna\u00efve \u2014 \u65e5\u672c\n".encode()
        tmp = self.tmp()
        (tmp / "plan.md").write_bytes(plan)
        done = run_shell("bash", base_env(tmp / "plan.md", 1, tmp / "o", LC_ALL="en_US.UTF-8"), tmp)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((tmp / "o" / "task-1-brief.md").read_bytes(), plan)


class GuardTest(ShellCase):
    """An empty or unset PLAN or OUT stops with a message, exit 2, and writes nothing anywhere."""

    def check(self, shell, drop, empty):
        tmp = self.tmp()
        work = tmp / "work"
        work.mkdir()
        (work / "plan.md").write_text("### Task 1: One\nx\n")
        env = base_env(work / "plan.md", 1, work / "out")
        if empty:
            env[drop] = ""
        else:
            del env[drop]
        before = sorted(os.listdir(work))
        done = run_shell(shell, env, work)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn(f"{drop} is not set".encode(), done.stderr)
        self.assertEqual(done.stdout, b"")
        self.assertEqual(sorted(os.listdir(work)), before, "the command wrote into its working dir")
        self.assertFalse(os.path.exists("/task-1-brief.md"))
        self.assertFalse(os.path.exists("/-brief.md"))

    def test_each_variable_unset_or_empty_under_each_shell(self):
        for shell in SHELLS:
            for drop in ("PLAN", "OUT"):
                for empty in (False, True):
                    with self.subTest(shell=shell, var=drop, empty=empty):
                        self.check(shell, drop, empty)

    def test_empty_plan_does_not_read_stdin(self):
        tmp = self.tmp()
        env = base_env("", 1, tmp / "out")
        done = subprocess.run(["bash", "-c", brief_command()], input=b"### Task 1: One\nx\n", env=env,
                              cwd=tmp, capture_output=True)
        self.assertEqual(done.returncode, 2)
        self.assertFalse((tmp / "out").exists())

    def test_missing_plan_says_it_cannot_be_read(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                tmp = self.tmp()
                done = run_shell(shell, base_env(tmp / "nope.md", 1, tmp / "out"), tmp)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn(b"can't read the plan", done.stderr)
                self.assertNotIn(b"no heading", done.stderr)
                self.assertEqual(done.stdout, b"")
                self.assertFalse((tmp / "out" / "task-1-brief.md").exists())

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_unreadable_plan_says_it_cannot_be_read(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                tmp = self.tmp()
                plan = tmp / "plan.md"
                plan.write_text("### Task 1: One\nx\n")
                plan.chmod(0)
                self.addCleanup(plan.chmod, 0o644)
                done = run_shell(shell, base_env(plan, 1, tmp / "out"), tmp)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn(b"can't read the plan", done.stderr)
                self.assertFalse((tmp / "out" / "task-1-brief.md").exists())

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_unreadable_plan_leaves_an_existing_brief_alone(self):
        # The guard fires before any write: an existing brief is left as it was.
        tmp = self.tmp()
        plan = tmp / "plan.md"
        plan.write_text("### Task 1: One\nx\n")
        plan.chmod(0)
        self.addCleanup(plan.chmod, 0o644)
        out = tmp / "out"
        out.mkdir()
        (out / "task-1-brief.md").write_text("old\n")
        done = run_shell("bash", base_env(plan, 1, out), tmp)
        self.assertEqual(done.returncode, 2)
        self.assertEqual((out / "task-1-brief.md").read_text(), "old\n")


class SuccessOutputTest(ShellCase):
    """Every task of both real plans: same output line, same bytes, under both shells."""

    @staticmethod
    def task_numbers(plan):
        nums = []
        for m in re.finditer(r"^#+[ \t]+Task[ \t]+([0-9]+)", plan.read_text(encoding="utf-8"), re.M):
            if m.group(1) not in nums:
                nums.append(m.group(1))
        return nums

    def test_output_line_and_bytes_for_every_task(self):
        old = base_command()
        for plan in PLANS:
            data = plan.read_bytes()
            for n in self.task_numbers(plan):
                for shell in SHELLS:
                    with self.subTest(plan=plan.name, task=n, shell=shell):
                        tmp = self.tmp()
                        out = tmp / "out"
                        done = run_shell(shell, base_env(plan, n, out), tmp)
                        self.assertEqual(done.returncode, 0, done.stderr)
                        brief = (out / f"task-{n}-brief.md").read_bytes()
                        self.assertTrue(brief.startswith(b"#"), brief[:40])
                        self.assertRegex(brief.split(b"\n", 1)[0].decode(), rf"^#+[ \t]+Task[ \t]+{n}\b")
                        self.assertIn(brief, data, "the brief is not a contiguous slice of the plan")
                        lines = brief.count(b"\n")
                        self.assertEqual(done.stdout, f"{out}/task-{n}-brief.md ({lines} lines)\n".encode())
                        self.assertNotIn(b"could not read", done.stderr)
                        if old is not None:
                            out2 = tmp / "out-old"
                            before = subprocess.run([*SHELLS[shell], old], capture_output=True, cwd=tmp,
                                                    env=base_env(plan, n, out2))
                            self.assertEqual(before.returncode, 0, before.stderr)
                            self.assertEqual((out2 / f"task-{n}-brief.md").read_bytes(), brief)
                            self.assertEqual(before.stdout.replace(str(out2).encode(), b"OUT"),
                                             done.stdout.replace(str(out).encode(), b"OUT"))

    def test_both_plans_have_tasks(self):
        for plan in PLANS:
            self.assertGreaterEqual(len(self.task_numbers(plan)), 5, plan)


if __name__ == "__main__":
    unittest.main()
