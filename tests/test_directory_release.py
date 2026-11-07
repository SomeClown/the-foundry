"""Adversarial tests for Task 6: the file-type guard and CONTRIBUTING's release commands.

The guard tests call DirectoryFileRulesTest.refused from test_structure.
The release tests extract the two bash blocks from CONTRIBUTING.md (never
retyped), build a scratch repo in a temp dir, and run them under bash and zsh
with a stub `claude` on PATH. Nothing here touches this repo's refs.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_structure  # noqa: E402

SHELLS = ("bash", "zsh")
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

GOOD_AGENT = "---\nname: a\ndescription: d\ntools: Read\nmodel: haiku\n---\nbody\n"
GOOD_SKILL = "---\nname: s\ndescription: d\n---\nbody\n"


def plugin_json(version):
    return json.dumps({"name": "x", "version": version}, indent=2) + "\n"


def git_env(tmp):
    return {
        "PATH": f"{tmp / 'bin'}:{os.getenv('PATH', '')}",
        "HOME": str(tmp / "home"),
        "TMPDIR": str(tmp / "tmpdir"),
        "STUB_LOG": str(tmp / "claude.log"),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        **GIT_ENV_IDENT,
    }


def git_run(cwd, env, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)
    if check and r.returncode:
        raise AssertionError(f"git {args} failed: {r.stderr}")
    return r.stdout.strip()


def default_files(version="1.0.0"):
    return {
        ".claude-plugin/plugin.json": plugin_json(version), "README.md": "r\n", "LICENSE": "l\n",
        ".gitignore": "x\n", "agents/a.md": GOOD_AGENT, "skills/s/SKILL.md": GOOD_SKILL,
        "docs/guide.md": "g\n", "docs/plans-archive/old.md": "o\n", "tests-old/notes.md": "n\n",
        "tests/test_a.py": "t\n", "evals/c/case.yaml": "c\n", "evals/README.md": "e\n",
        "evals-expensive/compare.py": "c\n", "docs/plans/p.md": "p\n",
    }


class ReleaseCommandsTest(unittest.TestCase):
    """Runs CONTRIBUTING's build block (extracted, never retyped) in scratch clones.

    Every repo has a local bare `origin` with main pushed; this repo is never touched.
    """

    @classmethod
    def setUpClass(cls):
        cls.shared = Path(tempfile.mkdtemp(prefix="dist-template-")).resolve()
        (cls.shared / "bin").mkdir()
        (cls.shared / "home").mkdir()
        (cls.shared / "tmpdir").mkdir()
        env = git_env(cls.shared)
        cls.template = cls._build(cls.shared, env, "tpl", "v1.0.0", False, default_files("1.0.0"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.shared, True)

    @staticmethod
    def _build(tmp, env, name, tag, annotated, files):
        repo = tmp / name
        bare = tmp / f"{name}-origin.git"
        repo.mkdir()
        git_run(repo, env, "init", "-q", "-b", "main")
        for f, content in files.items():
            p = repo / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        git_run(repo, env, "add", "-A")
        git_run(repo, env, "commit", "-q", "-m", "init")
        if tag:
            git_run(repo, env, *(["tag", "-a", tag, "-m", tag] if annotated else ["tag", tag]))
        git_run(tmp, env, "init", "-q", "--bare", "-b", "main", str(bare))
        git_run(repo, env, "remote", "add", "origin", str(bare))
        git_run(repo, env, "push", "-q", "origin", "main")
        return repo

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dist-rehearsal-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "bin").mkdir()
        stub = self.tmp / "bin" / "claude"
        stub.write_text('#!/bin/sh\necho "claude $*" >> "$STUB_LOG"\nexit 0\n')
        stub.chmod(0o755)
        self._local = threading.local()
        (self.tmp / "home").mkdir()
        (self.tmp / "tmpdir").mkdir()
        self.env = git_env(self.tmp)

    def git(self, cwd, *args, check=True):
        return git_run(cwd, self.env, *args, check=check)

    def make_repo(self, name="repo", tag="v1.0.0", annotated=False, omit=(), extra=None):
        """A repo plus a bare origin with main pushed. Default shape is copied, not rebuilt."""
        if tag == "v1.0.0" and not annotated and not omit and not extra:
            repo = self.tmp / name
            shutil.copytree(self.template, repo)
            bare = self.tmp / f"{name}-origin.git"
            shutil.copytree(self.shared / "tpl-origin.git", bare)
            self.git(repo, "remote", "set-url", "origin", str(bare))
            return repo
        version = tag[1:] if tag and tag.startswith("v") else "1.0.0"
        files = default_files(version)
        for f in list(files):
            if f.split("/")[0] in omit or f in omit:
                del files[f]
        files.update(extra or {})
        return self._build(self.tmp, self.env, name, tag, annotated, files)

    def origin(self, repo):
        return Path(self.git(repo, "remote", "get-url", "origin"))

    def run_block(self, shell, repo, index=0, cwd=None):
        env = {**self.env, "STUB_LOG": str(self.log_for(shell))}
        argv = [shell, "-f", "-c"] if shell == "zsh" else [shell, "-c"]
        return subprocess.run([*argv, contributing_blocks()[index]], cwd=cwd or repo,
                              env=env, capture_output=True, text=True)

    def log_for(self, shell):
        return self.tmp / f"claude-{shell}.log"

    def subTest(self, msg=None, **params):
        """Worker threads (one per shell) collect failures instead of touching unittest's shared state."""
        if threading.current_thread() is threading.main_thread():
            return super().subTest(msg, **params)
        return self._collect(params)

    @contextmanager
    def _collect(self, params):
        try:
            yield
        except Exception:
            self._local.failures.append(f"{params}: {traceback.format_exc(limit=-3)}")

    def shells(self, body):
        """Run body(shell) for bash and zsh at once (the block is subprocess-bound), report each as a subtest."""
        results = {}

        def work(shell):
            self._local.failures = []
            try:
                body(shell)
            except Exception:
                self._local.failures.append(traceback.format_exc())
            results[shell] = self._local.failures

        present = [s for s in SHELLS if shutil.which(s)]
        threads = [threading.Thread(target=work, args=(s,)) for s in present]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for shell in SHELLS:
            with self.subTest(shell=shell):
                if shell not in results:
                    self.skipTest(f"{shell} is not installed")
                if results[shell]:
                    self.fail("\n".join(results[shell]))

    def dist_files(self, repo):
        return set(self.git(repo, "ls-tree", "-r", "--name-only", "dist").splitlines())

    def dist_rev(self, repo):
        r = subprocess.run(["git", "rev-parse", "-q", "--verify", "refs/heads/dist"], cwd=repo,
                           env=self.env, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None

    def expected_dist_files(self, repo):
        out = self.git(repo, "ls-tree", "-r", "--name-only", "main").splitlines()
        return {f for f in out if not f.startswith(("tests/", "evals/", "evals-expensive/", "docs/plans/"))}

    def leaked(self, repo):
        return {f for f in self.dist_files(repo) if f.startswith(("tests/", "evals/", "evals-expensive/", "docs/plans/"))}

    def assert_built(self, repo, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNotNone(self.dist_rev(repo), "the block exited 0 but wrote no dist")
        self.assertFalse(list((repo / ".git").rglob("dist-index")), "temp index left behind")

    def assert_stopped(self, repo, r, before, *needles):
        """A stop: non-zero exit, message on stderr, dist exactly as it was, no temp index."""
        self.assertNotEqual(r.returncode, 0, f"the block should have stopped; stdout={r.stdout!r}")
        self.assertEqual(self.git(repo, "status", "--short"), "", "a stop disturbed the working tree or index")
        self.assertEqual(self.dist_rev(repo), before, "a stop changed dist")
        self.assertFalse(list((repo / ".git").rglob("dist-index")), "temp index left behind")
        for n in needles:
            self.assertIn(n, r.stderr)

    def reset_main(self, repo, files=None, rm=(), tag="v1.0.0", annotated=False, version=None):
        """Put local main on origin/main plus one commit with these changes; retag. Drops local dist."""
        self.git(repo, "checkout", "-q", "-f", "main")
        self.git(repo, "reset", "-q", "--hard", "origin/main")
        self.git(repo, "clean", "-fdq")
        self.git(repo, "branch", "-D", "dist", check=False)
        files = dict(files or {})
        if version is not None:
            files[".claude-plugin/plugin.json"] = plugin_json(version)
        for f, content in files.items():
            p = repo / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        for f in rm:
            (repo / f).unlink()
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "--allow-empty", "-m", "case")
        self.git(repo, "tag", "-f", *(["-a", "-m", tag] if annotated else []), tag)

    def release(self, repo, tag, files=None):
        """Commit a new release on main: bump plugin.json, add files, tag, push main and tags."""
        files = dict(files or {})
        files[".claude-plugin/plugin.json"] = plugin_json(tag[1:])
        for f, content in files.items():
            p = repo / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", tag)
        self.git(repo, "tag", tag)
        self.git(repo, "push", "-q", "origin", "main", "--tags")

    def clone(self, repo, name):
        c = self.tmp / name
        self.git(self.tmp, "clone", "-q", str(self.origin(repo)), str(c))
        return c

    # -- the blocks themselves

    def test_contributing_has_exactly_two_bash_blocks_in_the_release_section(self):
        self.assertEqual(len(contributing_blocks()), 2)

    # -- normal case

    def test_normal_build_makes_dist_without_dev_only_folders(self):
        def body(shell):
            repo = self.make_repo(f"n-{shell}")
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            self.assertEqual(r.stderr, "")
            self.assertEqual(self.dist_files(repo), self.expected_dist_files(repo))
            self.assertIn("docs/plans-archive/old.md", self.dist_files(repo))
            self.assertIn("tests-old/notes.md", self.dist_files(repo))
            self.assertEqual(self.git(repo, "log", "-1", "--format=%s", "dist"),
                             f"dist: v1.0.0 from {self.git(repo, 'rev-parse', '--short', 'main')}")
            self.assertEqual(self.git(repo, "rev-list", "--count", "dist"), "1")
            self.assertEqual(self.git(repo, "rev-list", "--parents", "-n", "1", "dist").split(), [self.dist_rev(repo)],
                             "the first release should be a root commit")
        self.shells(body)

    def test_annotated_tag_also_builds(self):
        def body(shell):
            repo = self.make_repo(f"a-{shell}", annotated=True)
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            self.assertTrue(self.git(repo, "log", "-1", "--format=%s", "dist").startswith("dist: v1.0.0 from "))
        self.shells(body)

    def test_annotated_tag_that_disagrees_with_plugin_json_stops(self):
        def body(shell):
            repo = self.make_repo(f"am-{shell}", annotated=True)
            self.reset_main(repo, tag="v9.9.9", annotated=True)
            self.git(repo, "tag", "-d", "v1.0.0")
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None, "v9.9.9", "1.0.0")
        self.shells(body)

    def test_build_works_from_a_feature_branch_that_changed_tests(self):
        def body(shell):
            repo = self.make_repo(f"f-{shell}")
            self.git(repo, "checkout", "-q", "-b", "feature")
            (repo / "tests" / "test_a.py").write_text("committed change\n")
            (repo / "extra.md").write_text("x\n")
            self.git(repo, "add", "-A")
            self.git(repo, "commit", "-q", "-m", "wip")
            (repo / "tests" / "test_a.py").write_text("staged change\n")
            self.git(repo, "add", "tests/test_a.py")
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            self.assertNotIn("extra.md", self.dist_files(repo))
            self.assertEqual(self.leaked(repo), set())
            self.assertEqual(self.git(repo, "show", ":tests/test_a.py"), "staged change")
        self.shells(body)

    def test_second_block_validates_the_archived_dist_and_reports_exit_zero(self):
        def body(shell):
            repo = self.make_repo(f"v-{shell}")
            self.assert_built(repo, self.run_block(shell, repo))
            self.log_for(shell).write_text("")
            r = self.run_block(shell, repo, index=1)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("validate exit=0", r.stdout)
            self.assertIn("directory exit=0", r.stdout)
            calls = self.log_for(shell).read_text().splitlines()
            self.assertEqual(len(calls), 2)
            self.assertIn("--profile directory --strict", calls[1])
            for c in calls:
                tdir = Path(c.split()[-1])
                self.assertTrue((tdir / "agents" / "a.md").exists())
                self.assertFalse((tdir / "tests").exists())
        self.shells(body)

    # -- a. the tag against plugin.json

    def test_tag_that_disagrees_with_plugin_json_stops_and_names_both(self):
        def body(shell):
            repo = self.make_repo(f"tv-{shell}")
            self.reset_main(repo, tag="v9.9.9")
            self.git(repo, "tag", "-d", "v1.0.0")
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None, "v9.9.9", "1.0.0")
        self.shells(body)

    def test_tag_without_the_v_prefix_stops(self):
        def body(shell):
            repo = self.make_repo(f"tn-{shell}")
            self.reset_main(repo, tag="1.0.0")
            self.git(repo, "tag", "-d", "v1.0.0")
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None, "1.0.0")
        self.shells(body)

    def test_plugin_json_without_a_version_stops(self):
        def body(shell):
            repo = self.make_repo(f"tnv-{shell}")
            self.reset_main(repo, files={".claude-plugin/plugin.json": '{"name": "x"}\n'})
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None)
        self.shells(body)

    def test_plugin_json_is_read_from_main_not_the_working_tree(self):
        def body(shell):
            repo = self.make_repo(f"tw-{shell}")
            (repo / ".claude-plugin" / "plugin.json").write_text(plugin_json("7.7.7"))
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
        self.shells(body)

    # -- untagged / misplaced tag / no main

    def test_untagged_main_does_not_write_a_dist_commit(self):
        def body(shell):
            repo = self.make_repo(f"u-{shell}", tag=None)
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None, "tag")
        self.shells(body)

    def test_tag_on_an_older_commit_than_main_does_not_write_a_dist_commit(self):
        def body(shell):
            repo = self.make_repo(f"o-{shell}")
            (repo / "new.md").write_text("n\n")
            self.git(repo, "add", "-A")
            self.git(repo, "commit", "-q", "-m", "after tag")
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None)
        self.shells(body)

    def test_missing_main_branch_does_not_write_an_empty_dist(self):
        def body(shell):
            repo = self.make_repo(f"nm-{shell}")
            self.git(repo, "branch", "-m", "main", "master")
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None)
        self.shells(body)

    # -- b. files the directory refuses, judged on the built tree

    def test_refused_files_in_the_built_tree_stop_the_build(self):
        # One build with all of them: the message lists every refused path, so each is judged in it.
        refused_cases = ["skills/s/run", "skills/s/x.py", "skills/s/x.sh", "skills/s/.md",
                         "docs/plans-archive/x.sh", "skills/s/tests/y.py", "Makefile",
                         "skills/s/notes.md.sh", ".gitattributes", "skills/s/LICENSE.sh"]

        def body(shell):
            repo = self.make_repo(f"rf-{shell}")
            self.reset_main(repo, files={p: "x\n" for p in refused_cases})
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None)
            for path in refused_cases:
                with self.subTest(path=path):
                    self.assertRegex(r.stderr, r"(?m)^" + re.escape(path) + r"$|[ :]" + re.escape(path) + r"(\s|$)")
        self.shells(body)

    def test_each_refused_file_alone_stops_the_build(self):
        # A few singly, so one path can't be hidden by another's listing.
        def body(shell):
            repo = self.make_repo(f"rs-{shell}")
            for path in ("skills/s/run", "skills/s/.md"):
                with self.subTest(path=path):
                    self.reset_main(repo, files={path: "x\n"})
                    r = self.run_block(shell, repo)
                    self.assert_stopped(repo, r, None, path)
        self.shells(body)

    def test_allowed_files_in_the_built_tree_do_not_stop_the_build(self):
        allowed_cases = ["skills/s/NOTES.MD", "assets/Icon.PNG", "a/b.JSON", "skills/s/LICENSE",
                         "skills/s/.gitignore", "assets/i.webp", "assets/i.ico", "c.yml", "n.txt",
                         "assets/with space.md", "a/i.jpeg", "a/i.gif", "a/i.jpg", "a/i.yaml"]

        def body(shell):
            repo = self.make_repo(f"af-{shell}")
            self.reset_main(repo, files={p: "x\n" for p in allowed_cases})
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            for path in allowed_cases:
                with self.subTest(path=path):
                    self.assertIn(path, self.dist_files(repo))
        self.shells(body)

    def test_a_refused_file_in_a_dev_only_folder_is_removed_not_refused(self):
        def body(shell):
            repo = self.make_repo(f"dv-{shell}")
            self.reset_main(repo, files={"tests/run.sh": "x\n", "evals/c/scaffold.sh": "x\n",
                                         "evals-expensive/noext": "x\n", "docs/plans/gen.py": "x\n"})
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            self.assertEqual(self.leaked(repo), set())
        self.shells(body)

    # -- c. front-matter keys

    def test_front_matter_keys_the_directory_refuses_stop_the_build(self):
        # One build holding a bad file per case; the message names "<path>: <key>" for each.
        bad = {
            "permissionMode in an agent": ("agents/b1.md", "---\nname: a\ndescription: d\npermissionMode: plan\n---\nb\n", "permissionMode"),
            "tools in a skill": ("skills/b2/SKILL.md", "---\nname: s\ndescription: d\ntools: Read\n---\nb\n", "tools"),
            "model in a skill": ("skills/b3/SKILL.md", "---\nname: s\ndescription: d\nmodel: haiku\n---\nb\n", "model"),
            "space before the colon": ("agents/b4.md", "---\nname: a\ndescription: d\npermissionMode : plan\n---\nb\n", "permissionMode"),
            "quoted key": ("agents/b5.md", '---\nname: a\ndescription: d\n"permissionMode": plan\n---\nb\n', "permissionMode"),
            "single-quoted key": ("agents/b6.md", "---\nname: a\ndescription: d\n'permissionMode': plan\n---\nb\n", "permissionMode"),
            "CRLF front matter": ("agents/b7.md", "---\r\nname: a\r\ndescription: d\r\npermissionMode: plan\r\n---\r\nb\r\n", "permissionMode"),
            "hooks in a skill": ("skills/b8/SKILL.md", "---\nname: s\ndescription: d\nhooks: x\n---\nb\n", "hooks"),
            "first line of the block": ("agents/b9.md", "---\nmcpServers: x\nname: a\n---\nb\n", "mcpServers"),
            "key after a description with colons": ("agents/b10.md", "---\nname: a\ndescription: a: b: c\nskills: x\n---\nb\n", "skills"),
        }

        def body(shell):
            repo = self.make_repo(f"fm-{shell}")
            self.reset_main(repo, files={path: content for path, content, _ in bad.values()})
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None, "front-matter")
            for label, (path, _, key) in bad.items():
                with self.subTest(case=label):
                    self.assertIn(f"{path}: {key}", r.stderr)
        self.shells(body)

    def test_each_bad_front_matter_key_alone_stops_the_build(self):
        # Alone, so a stop for one file can't stand in for another. The quoted forms are the risky ones.
        cases = {
            "quoted key": ("agents/a.md", '---\nname: a\ndescription: d\n"permissionMode": plan\n---\nb\n'),
            "single-quoted key": ("agents/a.md", "---\nname: a\ndescription: d\n'permissionMode': plan\n---\nb\n"),
        }

        def body(shell):
            repo = self.make_repo(f"fa-{shell}")
            for label, (path, content) in cases.items():
                with self.subTest(case=label):
                    self.reset_main(repo, files={path: content})
                    r = self.run_block(shell, repo)
                    self.assert_stopped(repo, r, None, path, "permissionMode")
        self.shells(body)

    def test_front_matter_the_directory_takes_does_not_stop_the_build(self):
        good = {
            "after the closing marker": ("agents/g1.md", GOOD_AGENT + "permissionMode: plan\n---\nhooks: x\n"),
            "indented and list lines inside the block": ("agents/g2.md", "---\nname: a\ndescription: >\n  multi: line\ntools:\n  - Read\nmodel: haiku\n---\nb\n"),
            "no front matter": ("agents/g3.md", "just text\npermissionMode: plan\n"),
            "CRLF, clean": ("agents/g4.md", "---\r\nname: a\r\ndescription: d\r\ntools: Read\r\nmodel: haiku\r\n---\r\nb\r\n"),
            "agent with only name and description": ("agents/g5.md", "---\nname: a\ndescription: d\n---\n"),
            "skill with name and description": ("skills/g6/SKILL.md", GOOD_SKILL),
            "other markdown in a skill folder with other keys": ("skills/s/notes.md", "---\ntools: x\n---\n"),
        }

        def body(shell):
            repo = self.make_repo(f"fg-{shell}")
            self.reset_main(repo, files={path: content for path, content in good.values()})
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
        self.shells(body)

    def test_a_valid_yaml_key_with_a_space_before_the_colon_does_not_stop_the_build(self):
        def body(shell):
            repo = self.make_repo(f"fs-{shell}")
            self.reset_main(repo, files={"agents/a.md": "---\nname : a\ndescription: d\n---\nb\n"})
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
        self.shells(body)

    def test_one_bad_file_among_many_good_ones_is_still_found(self):
        def body(shell):
            repo = self.make_repo(f"fb-{shell}")
            self.reset_main(repo, files={"agents/b.md": GOOD_AGENT, "agents/c.md": GOOD_AGENT,
                                         "skills/t/SKILL.md": GOOD_SKILL,
                                         "skills/u/SKILL.md": "---\nname: u\ndescription: d\nallowed-tools: x\n---\n"})
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None, "skills/u/SKILL.md", "allowed-tools")
        self.shells(body)

    # -- main stale against origin

    def test_stale_main_on_an_old_tag_with_a_script_and_permission_mode_stops(self):
        # The qa reviewer's HIGH: main left on an old release whose tree the directory refused.
        old = {"skills/debug/scripts/find-polluter": "#!/bin/sh\n",
               "agents/a.md": "---\nname: a\ndescription: d\npermissionMode: plan\n---\nb\n"}

        def body(shell):
            repo = self.make_repo(f"st-{shell}", tag="v0.9.0", extra=old)
            self.release(repo, "v1.0.0", files={"agents/a.md": GOOD_AGENT})
            self.git(repo, "rm", "-q", "-f", "skills/debug/scripts/find-polluter")
            self.git(repo, "commit", "-q", "-m", "drop script")
            self.git(repo, "push", "-q", "origin", "main")
            other = self.clone(repo, f"st-other-{shell}")
            # the owner's clone: main parked on v0.9.0, remote-tracking refs not yet refreshed
            self.git(other, "checkout", "-q", "-B", "main", "v0.9.0")
            self.git(other, "update-ref", "refs/remotes/origin/main", "v0.9.0")
            before = self.dist_rev(other)
            r = self.run_block(shell, other)
            self.assert_stopped(other, r, before, "origin/main")
            self.assertEqual(r.stdout, "")
        self.shells(body)

    def test_main_parked_on_an_old_tag_with_origin_equal_still_stops_on_the_tree(self):
        old = {"skills/debug/scripts/find-polluter": "#!/bin/sh\n",
               "agents/a.md": "---\nname: a\ndescription: d\npermissionMode: plan\n---\nb\n"}

        def body(shell):
            repo = self.make_repo(f"se-{shell}", tag="v2.0.1", extra=old)
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None, "skills/debug/scripts/find-polluter")
        self.shells(body)

    def test_main_ahead_of_origin_main_is_fine(self):
        def body(shell):
            repo = self.make_repo(f"ah-{shell}")
            (repo / "new.md").write_text("n\n")
            self.git(repo, "add", "-A")
            self.git(repo, "commit", "-q", "-m", "unpushed")
            self.git(repo, "tag", "-f", "v1.0.0")
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            self.assertIn("new.md", self.dist_files(repo))
        self.shells(body)

    def test_main_diverged_from_origin_main_stops(self):
        def body(shell):
            repo = self.make_repo(f"dm-{shell}")
            other = self.clone(repo, f"dm-other-{shell}")
            (other / "o.md").write_text("o\n")
            self.git(other, "add", "-A")
            self.git(other, "commit", "-q", "-m", "other")
            self.git(other, "push", "-q", "origin", "main")
            (repo / "m.md").write_text("m\n")
            self.git(repo, "add", "-A")
            self.git(repo, "commit", "-q", "-m", "mine")
            self.git(repo, "tag", "-f", "v1.0.0")
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None, "origin/main")
        self.shells(body)

    def test_failed_fetch_stops_and_writes_nothing(self):
        def body(shell):
            repo = self.make_repo(f"ff-{shell}")
            self.git(repo, "remote", "set-url", "origin", str(self.tmp / "does-not-exist.git"))
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None, "fetch")
        self.shells(body)

    def test_no_origin_remote_stops(self):
        def body(shell):
            repo = self.make_repo(f"no-{shell}")
            self.git(repo, "remote", "remove", "origin")
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, None, "fetch")
        self.shells(body)

    # -- other silent failures

    def test_a_dev_only_folder_missing_from_main_still_leaves_none_in_dist(self):
        def body(shell):
            repo = self.make_repo(f"md-{shell}", omit=("evals-expensive",))
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            self.assertEqual(self.leaked(repo), set())
        self.shells(body)

    def test_running_from_a_subdirectory_leaves_no_dev_only_files_in_dist(self):
        def body(shell):
            repo = self.make_repo(f"sd-{shell}")
            r = self.run_block(shell, repo, cwd=repo / "agents")
            self.assert_built(repo, r)
            self.assertEqual(self.leaked(repo), set())
        self.shells(body)

    # -- parent selection

    def test_rerunning_the_same_release_says_already_built_and_stacks_nothing(self):
        def body(shell):
            repo = self.make_repo(f"rr-{shell}")
            self.assert_built(repo, self.run_block(shell, repo))
            first = self.dist_rev(repo)
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, first, "already built")
            self.assertEqual(self.git(repo, "rev-list", "--count", "dist"), "1")
            self.assertEqual(self.dist_files(repo), self.expected_dist_files(repo))
        self.shells(body)

    def test_rerunning_a_release_whose_dist_is_already_pushed_says_already_built(self):
        def body(shell):
            repo = self.make_repo(f"rp-{shell}")
            self.assert_built(repo, self.run_block(shell, repo))
            self.git(repo, "push", "-q", "origin", "dist")
            first = self.dist_rev(repo)
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, first, "already built")
        self.shells(body)

    def test_a_new_release_parents_on_the_previous_dist_and_follows_main(self):
        def body(shell):
            repo = self.make_repo(f"c-{shell}")
            self.assert_built(repo, self.run_block(shell, repo))
            first = self.dist_rev(repo)
            self.release(repo, "v1.1.0", files={"agents/b.md": GOOD_AGENT})
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            self.assertEqual(self.git(repo, "rev-parse", "dist^"), first)
            self.assertIn("agents/b.md", self.dist_files(repo))
            self.assertTrue(self.git(repo, "log", "-1", "--format=%s", "dist").startswith("dist: v1.1.0 from "))
            self.assertEqual(self.leaked(repo), set())
        self.shells(body)

    def remote_dist_setup(self, shell, tag):
        """repo built v1.0.0 and pushed dist; a second clone is on main at `tag` with no local dist."""
        src = self.make_repo(f"src-{shell}")
        self.assert_built(src, self.run_block(shell, src))
        self.git(src, "push", "-q", "origin", "dist")
        remote_dist = self.dist_rev(src)
        self.release(src, tag, files={"agents/b.md": GOOD_AGENT})
        clone = self.clone(src, f"clone-{shell}")
        self.git(clone, "checkout", "-q", "-B", "main", "origin/main")
        self.assertIsNone(self.dist_rev(clone))
        self.assertEqual(self.git(clone, "rev-parse", "origin/dist"), remote_dist)
        return src, clone, remote_dist

    def test_dist_on_remote_but_not_local_becomes_the_parent_of_the_new_dist(self):
        def body(shell):
            _, clone, remote_dist = self.remote_dist_setup(shell, "v1.1.0")
            r = self.run_block(shell, clone)
            self.assert_built(clone, r)
            self.assertEqual(self.git(clone, "rev-parse", "dist^"), remote_dist)
            self.assertIn("agents/b.md", self.dist_files(clone))
        self.shells(body)

    def test_dist_on_remote_but_not_local_with_the_same_release_says_already_built(self):
        def body(shell):
            src = self.make_repo(f"sr-{shell}")
            self.assert_built(src, self.run_block(shell, src))
            self.git(src, "push", "-q", "origin", "dist", "--tags")
            clone = self.clone(src, f"cr-{shell}")
            self.git(clone, "checkout", "-q", "-B", "main", "origin/main")
            self.git(clone, "fetch", "-q", "--tags")
            r = self.run_block(shell, clone)
            self.assert_stopped(clone, r, None, "already built")
        self.shells(body)

    def test_local_dist_behind_the_remote_is_fine_and_the_remote_is_the_parent(self):
        def body(shell):
            repo = self.make_repo(f"lb-{shell}")
            self.assert_built(repo, self.run_block(shell, repo))
            self.git(repo, "push", "-q", "origin", "dist")
            old = self.dist_rev(repo)
            other = self.clone(repo, f"lb-other-{shell}")
            self.git(other, "checkout", "-q", "-B", "main", "origin/main")
            self.release(other, "v1.1.0", files={"agents/b.md": GOOD_AGENT})
            self.assert_built(other, self.run_block(shell, other))
            self.git(other, "push", "-q", "origin", "dist")
            newer = self.dist_rev(other)
            self.git(repo, "pull", "-q", "--ff-only", "origin", "main")
            self.git(repo, "fetch", "-q", "--tags")
            self.assertEqual(self.dist_rev(repo), old)
            self.release(other, "v1.2.0", files={"agents/c.md": GOOD_AGENT})
            self.git(repo, "pull", "-q", "--ff-only", "origin", "main")
            self.git(repo, "fetch", "-q", "--tags")
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            self.assertEqual(self.git(repo, "rev-parse", "dist^"), newer)
        self.shells(body)

    def test_a_stale_remote_tracking_dist_is_refreshed_by_the_fetch(self):
        def body(shell):
            repo = self.make_repo(f"sf-{shell}")
            self.assert_built(repo, self.run_block(shell, repo))
            self.git(repo, "push", "-q", "origin", "dist")
            other = self.clone(repo, f"sf-other-{shell}")
            self.git(other, "checkout", "-q", "-B", "main", "origin/main")
            self.release(other, "v1.1.0", files={"agents/b.md": GOOD_AGENT})
            self.assert_built(other, self.run_block(shell, other))
            self.git(other, "push", "-q", "origin", "dist")
            newer = self.dist_rev(other)
            self.release(other, "v1.2.0", files={"agents/c.md": GOOD_AGENT})
            # bring main and the tag over, leaving refs/remotes/origin/dist behind
            self.git(repo, "fetch", "-q", "origin", "refs/heads/main:refs/remotes/origin/main",
                     "refs/tags/v1.2.0:refs/tags/v1.2.0")
            self.git(repo, "merge", "-q", "--ff-only", "origin/main")
            stale = self.git(repo, "rev-parse", "origin/dist")
            self.assertNotEqual(stale, newer, "setup: the tracking ref should be stale")
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            self.assertEqual(self.git(repo, "rev-parse", "origin/dist"), newer)
            self.assertEqual(self.git(repo, "rev-parse", "dist^"), newer)
        self.shells(body)

    def unpushed_local_dist(self, shell, name):
        """Built and pushed v1.0.0; built v1.1.0 locally and did not push it."""
        repo = self.make_repo(f"{name}-{shell}")
        self.assert_built(repo, self.run_block(shell, repo))
        self.git(repo, "push", "-q", "origin", "dist")
        self.release(repo, "v1.1.0", files={"agents/b.md": GOOD_AGENT})
        self.assert_built(repo, self.run_block(shell, repo))
        return repo

    def test_local_dist_ahead_of_the_remote_stops(self):
        def body(shell):
            repo = self.unpushed_local_dist(shell, "da")
            self.release(repo, "v1.2.0", files={"agents/c.md": GOOD_AGENT})
            before = self.dist_rev(repo)
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, before, "local dist has commits origin/dist lacks")
        self.shells(body)

    def test_local_dist_diverged_from_the_remote_stops(self):
        def body(shell):
            repo = self.make_repo(f"dd-{shell}")
            self.assert_built(repo, self.run_block(shell, repo))
            self.git(repo, "push", "-q", "origin", "dist")
            other = self.clone(repo, f"dd-other-{shell}")
            self.git(other, "checkout", "-q", "-B", "main", "origin/main")
            self.release(other, "v1.1.0", files={"agents/b.md": GOOD_AGENT})
            self.assert_built(other, self.run_block(shell, other))
            self.git(other, "push", "-q", "origin", "dist")
            tree = self.git(repo, "rev-parse", "dist^{tree}")
            mine = self.git(repo, "commit-tree", tree, "-p", "dist", "-m", "hand-made")
            self.git(repo, "update-ref", "refs/heads/dist", mine)
            self.git(repo, "pull", "-q", "--ff-only", "origin", "main")
            self.git(repo, "fetch", "-q", "--tags")
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, mine, "local dist has commits origin/dist lacks")
        self.shells(body)

    def test_rerun_after_a_failed_validate_with_an_unpushed_local_dist_stops_on_the_local_dist(self):
        # Pins current behavior: the local dist (v1.1.0, never pushed) is ahead of origin/dist
        # (v1.0.0), so a re-run of v1.1.0 says "local dist has commits", not "already built".
        def body(shell):
            repo = self.unpushed_local_dist(shell, "rv")
            built = self.dist_rev(repo)
            r = self.run_block(shell, repo)
            self.assert_stopped(repo, r, built, "local dist has commits origin/dist lacks")
            self.assertNotIn("already built", r.stderr)
            self.assertEqual(self.git(repo, "rev-list", "--count", "dist"), "2")
        self.shells(body)

    # -- working tree and index untouched

    def test_working_tree_and_index_are_untouched_after_a_build(self):
        def body(shell):
            repo = self.make_repo(f"w-{shell}")
            self.assert_built(repo, self.run_block(shell, repo))
            self.assertEqual(self.git(repo, "status", "--short"), "")
            self.assertEqual(self.git(repo, "diff", "--cached"), "")
            self.assertEqual(self.git(repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")
            self.assertTrue((repo / "tests" / "test_a.py").exists())
            self.assertFalse((repo / ".git" / "dist-index").exists())
        self.shells(body)

    def test_staged_and_unstaged_work_survive_a_build_byte_for_byte(self):
        def body(shell):
            repo = self.make_repo(f"s-{shell}")
            (repo / "README.md").write_text("staged change\n")
            self.git(repo, "add", "README.md")
            (repo / "agents" / "a.md").write_text("unstaged change\n")
            (repo / "untracked.txt").write_text("u\n")
            before = (self.git(repo, "status", "--short"), self.git(repo, "diff", "--cached"),
                      (repo / ".git" / "index").read_bytes())
            r = self.run_block(shell, repo)
            self.assert_built(repo, r)
            after = (self.git(repo, "status", "--short"), self.git(repo, "diff", "--cached"),
                     (repo / ".git" / "index").read_bytes())
            self.assertEqual(before, after)
            self.assertNotIn("staged change", self.git(repo, "show", "dist:README.md"))
            self.assertNotIn("untracked.txt", self.dist_files(repo))
        self.shells(body)

    def test_build_leaves_no_dist_index_even_in_a_linked_worktree(self):
        def body(shell):
            repo = self.make_repo(f"wt-{shell}")
            wt = self.tmp / f"wt-dir-{shell}"
            self.git(repo, "worktree", "add", "-q", "-b", "side", str(wt))
            r = self.run_block(shell, wt)
            self.assert_built(repo, r)
            self.assertEqual(self.git(wt, "status", "--short"), "")
            self.assertEqual([p for p in (repo / ".git").rglob("dist-index")], [])
        self.shells(body)


if __name__ == "__main__":
    unittest.main()
