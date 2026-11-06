"""Tests for the brief command in skills/run-plan/SKILL.md (fence handling, task boundaries, failures)."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "run-plan" / "SKILL.md"
REAL_PLAN = ROOT / "docs" / "plans" / "2026-11-05-per-file-investigation.md"

FENCE = "`" * 3


def brief_command():
    """Return the body of the one bash block between Step 2 and Step 3 of the skill."""
    text = SKILL.read_text()
    start = text.index("### Step 2: Write the brief")
    end = text.index("### Step 3", start)
    blocks = re.findall(r"^```bash\n(.*?)^```$", text[start:end], re.S | re.M)
    if len(blocks) != 1:
        raise AssertionError(f"expected one bash block in Step 2, found {len(blocks)}")
    return blocks[0]


class TaskBriefTest(unittest.TestCase):
    def run_brief(self, plan_text, n, shell="bash"):
        """Write plan_text to a temp dir, run the brief command, return (exit code, brief text or None, stdout, stderr)."""
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.md"
            if plan_text is not None:
                plan.write_text(plan_text)
            return self.run_command(plan, n, Path(tmp) / "out", shell)

    def run_command(self, plan, n, outdir, shell="bash"):
        argv = [shell, "-f", "-c"] if shell == "zsh" else [shell, "-c"]
        proc = subprocess.run(
            [*argv, brief_command()],
            capture_output=True,
            text=True,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PLAN": str(plan),
                "N": str(n),
                "OUT": str(outdir),
            },
        )
        brief = Path(outdir) / f"task-{n}-brief.md"
        text = brief.read_text() if brief.exists() else None
        return proc.returncode, text, proc.stdout, proc.stderr

    def assertBrief(self, plan_text, n, expected):
        code, text, _, err = self.run_brief(plan_text, n)
        self.assertEqual(code, 0, err)
        self.assertEqual(text, expected)

    def assertMissing(self, plan_text, n):
        code, text, _, _ = self.run_brief(plan_text, n)
        self.assertNotEqual(code, 0)
        self.assertIsNone(text)

    def test_literal_backtick_sample_inside_fence(self):
        # A fence whose content line starts with three backticks must not flip state.
        plan = (
            "# Plan\n\n"
            "```\n"
            "```\\nCODE\\n```\n"
            "```\n\n"
            "### Task 1: One\n\n"
            "Do it.\n"
        )
        self.assertBrief(plan, 1, "### Task 1: One\n\nDo it.\n")

    def test_four_backtick_fence_hides_inner_fence_and_fake_task(self):
        plan = (
            "# Plan\n\n"
            "### Task 1: Real\n\n"
            "````\n"
            "```\n"
            "code\n"
            "```\n"
            "### Task 9: fake\n"
            "````\n\n"
            "after\n"
        )
        self.assertBrief(plan, 1, plan.split("# Plan\n\n", 1)[1])
        self.assertMissing(plan, 9)

    def test_tilde_fence_containing_backtick_lines(self):
        plan = (
            "### Task 1: Tilde\n\n"
            "~~~\n"
            "```\n"
            "### Task 2: fake\n"
            "~~~\n\n"
            "tail\n\n"
            "### Task 3: Three\n"
        )
        self.assertBrief(
            plan, 1,
            "### Task 1: Tilde\n\n~~~\n```\n### Task 2: fake\n~~~\n\ntail\n\n",
        )
        self.assertMissing(plan, 2)

    def test_closing_fence_must_match_character(self):
        # A tilde line does not close a backtick fence.
        plan = (
            "### Task 1: One\n\n"
            "```\n"
            "~~~\n"
            "### Task 2: fake\n"
            "```\n\n"
            "end\n"
        )
        self.assertMissing(plan, 2)
        self.assertEqual(self.run_brief(plan, 1)[1], plan)

    def test_closing_fence_must_be_at_least_as_long(self):
        plan = (
            "### Task 1: One\n\n"
            "````\n"
            "```\n"
            "### Task 2: fake\n"
            "````\n\n"
            "### Task 3: Three\n"
        )
        self.assertMissing(plan, 2)
        self.assertEqual(self.run_brief(plan, 3)[0], 0)

    def test_closing_fence_cannot_have_trailing_text(self):
        # "```js" inside a fence is content, not a closer.
        plan = (
            "### Task 1: One\n\n"
            "```\n"
            "```js\n"
            "### Task 2: fake\n"
            "```\n\n"
            "### Task 3: Three\n"
        )
        self.assertMissing(plan, 2)
        self.assertEqual(self.run_brief(plan, 3)[0], 0)

    def test_closing_fence_allows_trailing_whitespace(self):
        plan = (
            "### Task 1: One\n\n"
            "```\n"
            "code\n"
            "```  \t\n\n"
            "### Task 2: Two\n"
        )
        self.assertBrief(plan, 1, "### Task 1: One\n\n```\ncode\n```  \t\n\n")

    def test_indented_fences_one_to_three_spaces(self):
        for indent in (" ", "  ", "   "):
            with self.subTest(indent=len(indent)):
                plan = (
                    "### Task 1: One\n\n"
                    f"{indent}```\n"
                    "### Task 2: fake\n"
                    f"{indent}```\n\n"
                    "### Task 3: Three\n"
                )
                self.assertMissing(plan, 2)
                self.assertEqual(self.run_brief(plan, 3)[0], 0)

    def test_four_space_indent_is_not_a_fence(self):
        # Indented code: the backticks do not open a fence, so Task 2 is real.
        plan = (
            "### Task 1: One\n\n"
            "    ```\n\n"
            "### Task 2: Two\n\n"
            "body\n"
        )
        self.assertBrief(plan, 1, "### Task 1: One\n\n    ```\n\n")
        self.assertBrief(plan, 2, "### Task 2: Two\n\nbody\n")

    def test_four_space_indent_does_not_close_fence(self):
        plan = (
            "### Task 1: One\n\n"
            "```\n"
            "    ```\n"
            "### Task 2: fake\n"
            "```\n\n"
            "### Task 3: Three\n"
        )
        self.assertMissing(plan, 2)
        self.assertEqual(self.run_brief(plan, 3)[0], 0)

    def test_backtick_info_string_with_backtick_is_not_a_fence(self):
        plan = (
            "### Task 1: One\n\n"
            "```foo`bar\n\n"
            "### Task 2: Two\n\n"
            "body\n"
        )
        self.assertBrief(plan, 1, "### Task 1: One\n\n```foo`bar\n\n")
        self.assertBrief(plan, 2, "### Task 2: Two\n\nbody\n")

    def test_tilde_info_string_may_contain_backtick(self):
        plan = (
            "### Task 1: One\n\n"
            "~~~foo`bar\n"
            "### Task 2: fake\n"
            "~~~\n\n"
            "### Task 3: Three\n"
        )
        self.assertMissing(plan, 2)
        self.assertEqual(self.run_brief(plan, 3)[0], 0)

    def test_comment_inside_fence_does_not_end_task(self):
        plan = (
            "### Task 1: One\n\n"
            "```bash\n"
            "# a comment\n"
            "echo hi\n"
            "```\n\n"
            "still task 1\n\n"
            "### Task 2: Two\n"
        )
        self.assertBrief(
            plan, 1,
            "### Task 1: One\n\n```bash\n# a comment\necho hi\n```\n\nstill task 1\n\n",
        )

    def test_unclosed_fence_runs_to_end_of_file(self):
        plan = "### Task 1: One\n\n```\n### Task 2: fake\n"
        self.assertBrief(plan, 1, plan)
        self.assertMissing(plan, 2)

    def test_task_1_is_not_task_10(self):
        plan = (
            "### Task 10: Ten\n\nten body\n\n"
            "### Task 1: One\n\none body\n\n"
            "### Task 2: Two\n\ntwo body\n"
        )
        self.assertBrief(plan, 1, "### Task 1: One\n\none body\n\n")
        self.assertBrief(plan, 10, "### Task 10: Ten\n\nten body\n\n")
        self.assertBrief(plan, 2, "### Task 2: Two\n\ntwo body\n")

    def test_task_ends_at_higher_level_heading(self):
        plan = (
            "## 2. Tasks\n\n"
            "### Task 1: One\n\nbody\n\n"
            "## 3. Next\n\nnot in task\n"
        )
        self.assertBrief(plan, 1, "### Task 1: One\n\nbody\n\n")

    def test_task_includes_lower_level_headings(self):
        plan = (
            "### Task 1: One\n\n"
            "#### Step\n\nstep body\n\n"
            "### Task 2: Two\n"
        )
        self.assertBrief(plan, 1, "### Task 1: One\n\n#### Step\n\nstep body\n\n")

    def test_prints_path_and_line_count(self):
        code, _, out, _ = self.run_brief("### Task 1: One\n\nbody\n", 1)
        self.assertEqual(code, 0)
        self.assertRegex(out, r"/out/task-1-brief\.md \(3 lines\)\n$")

    def test_missing_task_fails_and_writes_nothing(self):
        code, text, _, err = self.run_brief("### Task 1: One\n\nbody\n", 2)
        self.assertNotEqual(code, 0)
        self.assertIsNone(text)
        self.assertIn("no heading for Task 2", err)

    def test_missing_plan_fails_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, text, _, _ = self.run_command(Path(tmp) / "nope.md", 1, Path(tmp) / "out")
        self.assertNotEqual(code, 0)
        self.assertIsNone(text)

    def test_command_is_the_one_bash_block_in_step_2(self):
        self.assertIn('awk -v n="$N"', brief_command())

    def real_slice(self, n):
        lines = REAL_PLAN.read_text().splitlines(keepends=True)
        start = next(i for i, l in enumerate(lines) if l.startswith(f"### Task {n}:"))
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i].startswith(("### Task", "### 3."))),
            len(lines),
        )
        return "".join(lines[start:end])

    def test_real_plan_round_trip(self):
        plan = REAL_PLAN.read_text()
        for n in (1, 2, 12):
            with self.subTest(task=n):
                self.assertBrief(plan, n, self.real_slice(n))

    @unittest.skipIf(shutil.which("zsh") is None, "zsh not installed")
    def test_same_brief_under_zsh(self):
        code, text, _, err = self.run_brief(REAL_PLAN.read_text(), 2, shell="zsh")
        self.assertEqual(code, 0, err)
        self.assertEqual(text, self.real_slice(2))


if __name__ == "__main__":
    unittest.main()
