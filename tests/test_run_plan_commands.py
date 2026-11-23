"""Run the two shell blocks of skills/run-plan/SKILL.md that package diffs, in a scratch repo.

The qa pass (section 4) packages the whole branch against the merge-base; Step 4 packages a task's
diff, against the sha noted at step 1 when a builder committed. Both blocks are read out of the
Markdown as written, their placeholders filled in, and run under bash and `zsh -f`.

Standard library only; git is the only tool used besides the shells. No network.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "run-plan" / "SKILL.md"
SHELLS = [("bash", ["bash", "-c"]), ("zsh -f", ["zsh", "-f", "-c"])]


def blocks_between(start_marker, end_marker):
    text = SKILL.read_text(encoding="utf-8")
    start = text.index(start_marker)
    end = text.index(end_marker, start) if end_marker else len(text)
    return re.findall(r"^```\n(.*?)^```$", text[start:end], re.S | re.M)


def qa_pass_block():
    blocks = blocks_between("Package the whole branch:", "Then dispatch `the-foundry:qa`")
    assert len(blocks) == 1, blocks
    return blocks[0]


def literal_sha_block():
    blocks = blocks_between("Before packaging, check that", "For a task that later tasks build on")
    assert len(blocks) == 1, blocks
    return blocks[0]


def plain_step_4_block():
    blocks = blocks_between("Package the task's diff every time", "Before packaging, check that")
    assert len(blocks) == 1, blocks
    return blocks[0]


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="run-plan-cmds-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.work = self.tmp / "work"
        self.repo.mkdir()
        self.work.mkdir()
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(self.tmp),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        self.git("init", "-q", "-b", "main")

    def git(self, *args):
        done = subprocess.run(["git", *args], cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def commit(self, name, text, message):
        (self.repo / name).write_text(text, encoding="utf-8")
        self.git("add", name)
        self.git("commit", "-q", "-m", message)

    def run_block(self, argv, command):
        done = subprocess.run(argv + [command], cwd=self.repo, env=self.env, capture_output=True, text=True)
        return done

    def shells(self):
        for name, argv in SHELLS:
            if shutil.which(argv[0]):
                yield name, argv


class QaPassBlockTest(Repo):
    def fill(self, default_branch):
        return qa_pass_block().replace("<default branch>", default_branch).replace("<work dir>", str(self.work))

    def package(self):
        path = self.work / "branch-diff.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def feature_branch(self):
        self.commit("a.txt", "base\n", "base")
        self.git("checkout", "-q", "-b", "feat")
        self.commit("b.txt", "one\n", "first builder commit")
        self.commit("c.txt", "two\n", "second builder commit")

    def test_a_good_merge_base_packages_the_log_the_stat_and_the_diff(self):
        self.feature_branch()
        for name, argv in self.shells():
            with self.subTest(shell=name):
                (self.work / "branch-diff.txt").unlink(missing_ok=True)
                done = self.run_block(argv, self.fill("main"))
                self.assertEqual(done.returncode, 0, done.stderr)
                text = self.package()
                self.assertIn("first builder commit", text)
                self.assertIn("second builder commit", text)
                self.assertNotIn("base", text.split("diff --git")[0])  # the log and stat leave the base commit out
                self.assertIn("b.txt", text)
                self.assertIn("c.txt", text)
                self.assertIn("+two", text)
                self.assertNotIn("a.txt", text)  # the base commit is not part of the branch

    def test_an_unknown_default_branch_stops_with_a_message_and_writes_nothing(self):
        self.feature_branch()
        for name, argv in self.shells():
            with self.subTest(shell=name):
                (self.work / "branch-diff.txt").unlink(missing_ok=True)
                done = self.run_block(argv, self.fill("no-such-branch"))
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn("no merge-base with no-such-branch", done.stderr)
                self.assertIsNone(self.package())

    def test_unrelated_histories_stop_with_a_message_and_write_nothing(self):
        self.commit("a.txt", "base\n", "base")
        self.git("checkout", "-q", "--orphan", "feat")
        self.commit("z.txt", "other\n", "an unrelated root")
        for name, argv in self.shells():
            with self.subTest(shell=name):
                (self.work / "branch-diff.txt").unlink(missing_ok=True)
                done = self.run_block(argv, self.fill("main"))
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn("no merge-base with main", done.stderr)
                self.assertIsNone(self.package())

    def test_the_second_line_alone_fails_loudly_and_packages_nothing(self):
        # The text says to run both lines in one Bash call. If a session splits them, MB is empty:
        # the second line must not exit 0 with a wrong diff.
        self.feature_branch()
        second = self.fill("main").splitlines()[1]
        self.assertIn("$MB", second)
        for name, argv in self.shells():
            with self.subTest(shell=name):
                (self.work / "branch-diff.txt").unlink(missing_ok=True)
                done = self.run_block(argv, second)
                self.assertNotEqual(done.returncode, 0, "the second line alone exited 0")
                self.assertIn("fatal", done.stderr)
                self.assertEqual(self.package(), "", "a wrong diff was packaged without an error")

    def test_the_block_stays_two_lines_and_guards_an_empty_merge_base(self):
        lines = [l for l in qa_pass_block().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[0].startswith("MB=$(git merge-base "), lines[0])
        self.assertIn('[ -n "$MB" ]', lines[0])
        self.assertIn("exit 2", lines[0])


class Step4BlockTest(Repo):
    def fill(self, block, sha=None):
        block = block.replace("<work dir>", str(self.work)).replace("task-N-diff", "task-1-diff")
        return block.replace("abc1234", sha) if sha else block

    def package(self):
        path = self.work / "task-1-diff.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def builder_commits_then_stages_more(self):
        self.commit("base.txt", "base\n", "base")
        noted = self.git("rev-parse", "--short", "HEAD")
        self.commit("committed.txt", "committed by the builder\n", "builder commit against the contract")
        (self.repo / "staged.txt").write_text("left in the tree\n", encoding="utf-8")
        return noted

    def test_the_literal_sha_package_holds_both_the_committed_and_the_staged_work(self):
        noted = self.builder_commits_then_stages_more()
        for name, argv in self.shells():
            with self.subTest(shell=name):
                (self.work / "task-1-diff.txt").unlink(missing_ok=True)
                done = self.run_block(argv, self.fill(literal_sha_block(), noted))
                self.assertEqual(done.returncode, 0, done.stderr)
                text = self.package()
                self.assertIn("committed.txt", text)
                self.assertIn("+committed by the builder", text)
                self.assertIn("staged.txt", text)
                self.assertIn("+left in the tree", text)
                self.assertNotIn("base.txt", text)

    def test_the_plain_command_drops_the_committed_work_which_is_why_the_check_exists(self):
        # The control: against HEAD, a builder's commit silently leaves the package.
        self.builder_commits_then_stages_more()
        done = self.run_block(["bash", "-c"], self.fill(plain_step_4_block()))
        self.assertEqual(done.returncode, 0, done.stderr)
        text = self.package()
        self.assertIn("staged.txt", text)
        self.assertNotIn("committed.txt", text)

    def test_the_literal_sha_command_names_a_literal_and_no_shell_variable(self):
        block = literal_sha_block()
        self.assertIn("abc1234", block)
        self.assertNotRegex(block, r"\$[A-Za-z_{(]")

    def test_with_no_builder_commit_the_literal_sha_is_head_and_matches_the_plain_package(self):
        self.commit("base.txt", "base\n", "base")
        noted = self.git("rev-parse", "--short", "HEAD")
        (self.repo / "staged.txt").write_text("left in the tree\n", encoding="utf-8")
        done = self.run_block(["bash", "-c"], self.fill(literal_sha_block(), noted))
        self.assertEqual(done.returncode, 0, done.stderr)
        literal = self.package()
        self.git("reset", "-q")
        (self.work / "task-1-diff.txt").unlink()
        done = self.run_block(["bash", "-c"], self.fill(plain_step_4_block()))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(literal, self.package())


if __name__ == "__main__":
    unittest.main()
