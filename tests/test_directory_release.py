"""Adversarial tests for Task 6: the file-type guard and CONTRIBUTING's release commands.

The guard tests call DirectoryFileRulesTest.refused from test_structure.
The release tests extract the two bash blocks from CONTRIBUTING.md (never
retyped), build a scratch repo in a temp dir, and run them under bash and zsh
with a stub `claude` on PATH. Nothing here touches this repo's refs.
"""

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
import test_structure  # noqa: E402

SHELLS = [s for s in ("bash", "zsh") if shutil.which(s)]
DEV_DIRS = ("tests", "evals", "evals-expensive", "docs/plans")


def refused(paths):
    return test_structure.DirectoryFileRulesTest("test_refused_can_fail").refused(paths)


class RefusedGuardTest(unittest.TestCase):
    def assertRefused(self, path):
        self.assertEqual(refused([path]), [path], f"{path} should be refused")

    def assertKept(self, path):
        self.assertEqual(refused([path]), [], f"{path} should be allowed")

    def test_uppercase_code_suffixes_are_refused(self):
        for p in ("X.PY", "run.SH", "skills/x/Run.Sh", "a/b.JS"):
            with self.subTest(p=p):
                self.assertRefused(p)

    def test_uppercase_allowed_suffixes_are_kept(self):
        for p in ("README.MD", "assets/Icon.PNG", "a/b.JSON", "c.YAML"):
            with self.subTest(p=p):
                self.assertKept(p)

    def test_file_with_no_suffix_is_refused(self):
        for p in ("skills/x/run", "bin/tool", "Makefile", "x/LICENSE.sh"):
            with self.subTest(p=p):
                self.assertRefused(p)

    def test_double_suffix_is_judged_by_the_last_suffix(self):
        self.assertRefused("notes.md.sh")
        self.assertRefused("a.json.py")
        self.assertKept("tool.py.md")

    def test_dotfiles_other_than_gitignore_are_refused(self):
        for p in (".gitattributes", ".npmrc", "skills/.env", ".editorconfig", ".GITIGNORE"):
            with self.subTest(p=p):
                self.assertRefused(p)

    def test_gitignore_and_license_are_kept_even_when_nested(self):
        for p in (".gitignore", "LICENSE", "skills/x/.gitignore", "docs/LICENSE"):
            with self.subTest(p=p):
                self.assertKept(p)

    def test_lookalike_dev_only_prefixes_are_not_exempt(self):
        for p in ("tests-old/x.py", "docs/plans-archive/x.sh", "evalsx/x.sh", "evals-expensive2/x.py", "Tests/x.py", "docs/x.sh"):
            with self.subTest(p=p):
                self.assertRefused(p)

    def test_real_dev_only_prefixes_are_exempt(self):
        for p in ("tests/x.py", "evals/a/scaffold.sh", "evals-expensive/compare.py", "docs/plans/x.sh"):
            with self.subTest(p=p):
                self.assertKept(p)

    def test_dev_only_folder_nested_under_a_shipped_folder_is_not_exempt(self):
        # tests/ means the top-level folder only; skills/x/tests/y.py would ship.
        self.assertRefused("skills/x/tests/y.py")

    def test_svg_is_refused_because_it_is_not_on_the_stated_list(self):
        # The stated list is Markdown, text, JSON, YAML, PNG/JPEG/GIF/WebP/ICO.
        # SVG is not on it, so the guard errs on the side of refusing.
        self.assertRefused("assets/logo.svg")

    def test_every_stated_image_suffix_is_kept(self):
        for ext in ("png", "jpg", "jpeg", "gif", "webp", "ico"):
            with self.subTest(ext=ext):
                self.assertKept(f"assets/i.{ext}")

    def test_order_of_refused_paths_is_preserved(self):
        self.assertEqual(refused(["b.sh", "a.md", "a.py"]), ["b.sh", "a.py"])


def contributing_blocks():
    text = (ROOT / "CONTRIBUTING.md").read_text()
    section = text.split("## Releasing to the plugin directory", 1)[1]
    return re.findall(r"```bash\n(.*?)```", section, re.S)


GIT_ENV_IDENT = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}


class ReleaseCommandsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dist-rehearsal-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        stub = self.bin / "claude"
        stub.write_text('#!/bin/sh\necho "claude $*" >> "$STUB_LOG"\nexit 0\n')
        stub.chmod(0o755)
        self.log = self.tmp / "claude.log"
        self.env = {
            "PATH": f"{self.bin}:{os.getenv('PATH', '')}",
            "HOME": str(self.tmp / "home"),
            "TMPDIR": str(self.tmp / "tmpdir"),
            "STUB_LOG": str(self.log),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            **GIT_ENV_IDENT,
        }
        (self.tmp / "home").mkdir()
        (self.tmp / "tmpdir").mkdir()
        self.n = 0

    def git(self, cwd, *args, check=True):
        r = subprocess.run(["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True)
        if check and r.returncode:
            raise AssertionError(f"git {args} failed: {r.stderr}")
        return r.stdout.strip()

    def make_repo(self, name="repo", tag="v1.0.0", annotated=False, omit=(), extra=()):
        repo = self.tmp / name
        repo.mkdir()
        self.git(repo, "init", "-q", "-b", "main")
        files = [
            ".claude-plugin/plugin.json", "README.md", "LICENSE", ".gitignore",
            "agents/a.md", "skills/s/SKILL.md", "docs/guide.md",
            "docs/plans-archive/old.md", "tests-old/notes.md",
            "tests/test_a.py", "evals/c/case.yaml", "evals/README.md",
            "evals-expensive/compare.py", "docs/plans/p.md", *extra,
        ]
        for f in files:
            if f.split("/")[0] in omit or f in omit:
                continue
            p = repo / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"{f}\n")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", "init")
        if tag:
            if annotated:
                self.git(repo, "tag", "-a", tag, "-m", tag)
            else:
                self.git(repo, "tag", tag)
        return repo

    def run_block(self, shell, repo, index=0, cwd=None):
        return subprocess.run([shell, "-c", contributing_blocks()[index]], cwd=cwd or repo,
                              env=self.env, capture_output=True, text=True)

    def dist_files(self, repo):
        return set(self.git(repo, "ls-tree", "-r", "--name-only", "dist").splitlines())

    def has_dist(self, repo):
        return subprocess.run(["git", "rev-parse", "-q", "--verify", "refs/heads/dist"], cwd=repo,
                              env=self.env, capture_output=True).returncode == 0

    def expected_dist_files(self, repo):
        out = self.git(repo, "ls-tree", "-r", "--name-only", "main").splitlines()
        return {f for f in out if not f.startswith(("tests/", "evals/", "evals-expensive/", "docs/plans/"))}

    # -- the blocks themselves

    def test_contributing_has_exactly_two_bash_blocks_in_the_release_section(self):
        self.assertEqual(len(contributing_blocks()), 2)

    # -- normal case

    def test_normal_build_makes_dist_without_dev_only_folders(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"n-{shell}")
                r = self.run_block(shell, repo)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stderr, "")
                self.assertEqual(self.dist_files(repo), self.expected_dist_files(repo))
                self.assertIn("docs/plans-archive/old.md", self.dist_files(repo))
                self.assertIn("tests-old/notes.md", self.dist_files(repo))
                self.assertEqual(self.git(repo, "log", "-1", "--format=%s", "dist"),
                                 f"dist: v1.0.0 from {self.git(repo, 'rev-parse', '--short', 'main')}")

    def test_annotated_tag_also_builds(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"a-{shell}", annotated=True)
                self.run_block(shell, repo)
                self.assertTrue(self.has_dist(repo))
                self.assertTrue(self.git(repo, "log", "-1", "--format=%s", "dist").startswith("dist: v1.0.0 from "))

    def test_build_works_from_a_feature_branch_checkout(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"f-{shell}")
                self.git(repo, "checkout", "-q", "-b", "feature")
                (repo / "extra.md").write_text("x\n")
                self.git(repo, "add", "-A")
                self.git(repo, "commit", "-q", "-m", "wip")
                self.run_block(shell, repo)
                self.assertNotIn("extra.md", self.dist_files(repo))

    def test_second_block_validates_the_archived_dist_and_reports_exit_zero(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"v-{shell}")
                self.run_block(shell, repo)
                self.log.write_text("")
                r = self.run_block(shell, repo, index=1)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("validate exit=0", r.stdout)
                self.assertIn("directory exit=0", r.stdout)
                calls = self.log.read_text().splitlines()
                self.assertEqual(len(calls), 2)
                self.assertIn("--profile directory --strict", calls[1])
                for c in calls:
                    tdir = Path(c.split()[-1])
                    self.assertTrue((tdir / "agents" / "a.md").exists())
                    self.assertFalse((tdir / "tests").exists())

    # -- main not tagged

    def test_untagged_main_does_not_write_a_dist_commit(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"u-{shell}", tag=None)
                self.run_block(shell, repo)
                self.assertFalse(self.has_dist(repo), "dist was written for an untagged main"
                                 + (": " + self.git(repo, "log", "-1", "--format=[%s]", "dist") if self.has_dist(repo) else ""))

    def test_tag_on_an_older_commit_than_main_does_not_write_a_dist_commit(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"o-{shell}")
                (repo / "new.md").write_text("n\n")
                self.git(repo, "add", "-A")
                self.git(repo, "commit", "-q", "-m", "after tag")
                self.run_block(shell, repo)
                self.assertFalse(self.has_dist(repo), "dist written though main is past the tag")

    def test_any_dist_message_never_has_an_empty_tag(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"m-{shell}", tag=None)
                self.run_block(shell, repo)
                if self.has_dist(repo):
                    self.assertNotRegex(self.git(repo, "log", "-1", "--format=%s", "dist"), r"dist:\s+from")

    # -- other silent failures

    def test_missing_main_branch_does_not_write_an_empty_dist(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"nm-{shell}")
                self.git(repo, "branch", "-m", "main", "master")
                self.run_block(shell, repo)
                self.assertFalse(self.has_dist(repo), "dist written with no main branch")

    def test_a_dev_only_folder_missing_from_main_still_leaves_none_in_dist(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"md-{shell}", omit=("evals-expensive",))
                self.run_block(shell, repo)
                if self.has_dist(repo):
                    leaked = {f for f in self.dist_files(repo) if f.startswith(("tests/", "evals/", "evals-expensive/", "docs/plans/"))}
                    self.assertEqual(leaked, set(), "dev-only files shipped in dist")

    def test_running_from_a_subdirectory_leaves_no_dev_only_files_in_dist(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"sd-{shell}")
                self.run_block(shell, repo, cwd=repo / "agents")
                if self.has_dist(repo):
                    leaked = {f for f in self.dist_files(repo) if f.startswith(("tests/", "evals/", "evals-expensive/", "docs/plans/"))}
                    self.assertEqual(leaked, set(), "dev-only files shipped in dist")

    # -- twice

    def test_second_build_parents_on_the_first_and_keeps_the_same_files(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"t-{shell}")
                self.run_block(shell, repo)
                first = self.git(repo, "rev-parse", "dist")
                files = self.dist_files(repo)
                self.run_block(shell, repo)
                second = self.git(repo, "rev-parse", "dist")
                self.assertNotEqual(first, second)
                self.assertEqual(self.git(repo, "rev-parse", "dist^"), first)
                self.assertEqual(self.dist_files(repo), files)
                self.assertEqual(len(files), len(self.expected_dist_files(repo)))

    def test_dist_follows_main_when_main_changes_between_builds(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"c-{shell}")
                self.run_block(shell, repo)
                (repo / "agents" / "b.md").write_text("b\n")
                self.git(repo, "add", "-A")
                self.git(repo, "commit", "-q", "-m", "more")
                self.git(repo, "tag", "v1.1.0")
                self.run_block(shell, repo)
                self.assertIn("agents/b.md", self.dist_files(repo))
                self.assertTrue(self.git(repo, "log", "-1", "--format=%s", "dist").startswith("dist: v1.1.0 from "))

    # -- dist on the remote only

    def test_dist_on_remote_but_not_local_is_not_replaced_by_an_unrelated_root(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                src = self.make_repo(f"src-{shell}")
                bare = self.tmp / f"bare-{shell}.git"
                self.git(self.tmp, "init", "-q", "--bare", str(bare))
                self.git(src, "remote", "add", "origin", str(bare))
                # An old date keeps the clone's own dist commit from hashing identical to this one.
                self.env["GIT_COMMITTER_DATE"] = "2020-01-01T00:00:00"
                self.run_block(shell, src)
                del self.env["GIT_COMMITTER_DATE"]
                self.git(src, "push", "-q", "origin", "main", "dist", "--tags")
                clone = self.tmp / f"clone-{shell}"
                self.git(self.tmp, "clone", "-q", str(bare), str(clone))
                self.git(clone, "checkout", "-q", "-B", "main", "origin/main")
                self.assertEqual(self.git(clone, "rev-parse", "--abbrev-ref", "HEAD"), "main")
                self.assertFalse(self.has_dist(clone))
                self.git(clone, "rev-parse", "origin/dist")
                self.run_block(shell, clone)
                if self.has_dist(clone):
                    ok = subprocess.run(["git", "merge-base", "--is-ancestor", "origin/dist", "dist"],
                                        cwd=clone, env=self.env).returncode == 0
                    self.assertTrue(ok, "new dist is unrelated to origin/dist; pushing it would be rejected")

    # -- working tree and index untouched

    def test_working_tree_and_index_are_untouched_after_a_build(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"w-{shell}")
                self.run_block(shell, repo)
                self.assertEqual(self.git(repo, "status", "--short"), "")
                self.assertEqual(self.git(repo, "diff", "--cached"), "")
                self.assertEqual(self.git(repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")
                self.assertTrue((repo / "tests" / "test_a.py").exists())
                self.assertFalse((repo / ".git" / "dist-index").exists())

    def test_staged_and_unstaged_work_survive_a_build_byte_for_byte(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"s-{shell}")
                (repo / "README.md").write_text("staged change\n")
                self.git(repo, "add", "README.md")
                (repo / "agents" / "a.md").write_text("unstaged change\n")
                (repo / "untracked.txt").write_text("u\n")
                before = (self.git(repo, "status", "--short"), self.git(repo, "diff", "--cached"),
                          (repo / ".git" / "index").read_bytes())
                self.run_block(shell, repo)
                after = (self.git(repo, "status", "--short"), self.git(repo, "diff", "--cached"),
                         (repo / ".git" / "index").read_bytes())
                self.assertEqual(before, after)
                self.assertNotIn("staged change", "".join(
                    self.git(repo, "show", f"dist:{f}") for f in ("README.md",)))
                self.assertNotIn("untracked.txt", self.dist_files(repo))

    def test_failed_build_leaves_no_temp_index_and_the_real_index_alone(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"fi-{shell}", tag=None)
                before = (repo / ".git" / "index").read_bytes()
                self.run_block(shell, repo)
                self.assertFalse((repo / ".git" / "dist-index").exists())
                self.assertEqual((repo / ".git" / "index").read_bytes(), before)
                self.assertEqual(self.git(repo, "status", "--short"), "")

    def test_build_leaves_no_dist_index_even_in_a_linked_worktree(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                repo = self.make_repo(f"wt-{shell}")
                wt = self.tmp / f"wt-dir-{shell}"
                self.git(repo, "worktree", "add", "-q", "-b", "side", str(wt))
                self.run_block(shell, wt)
                self.assertTrue(self.has_dist(repo))
                self.assertEqual(self.git(wt, "status", "--short"), "")
                self.assertEqual([p for p in (repo / ".git").rglob("dist-index")], [])


if __name__ == "__main__":
    unittest.main()
