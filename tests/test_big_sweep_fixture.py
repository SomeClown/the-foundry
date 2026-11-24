"""Free checks on the big-sweep fixture, its answer key, its case files and its sync script.

The big-sweep loop case (evals-expensive/big-sweep-in-parts) runs a real model session, so a fixture
bug found after a run is an expensive way to learn it. These tests build every fixture in a temp
folder (no model runs, nothing here starts a session) and check what the case leans on: the file
counts and layout, byte-identical builds, where each planted fact and decoy sits, that each token
appears once, that no skipped, vendored or untracked file holds a fact, the --subset builds, the case
files, and that sync_big_sweep.py writes exactly what is committed.

Standard library only; runs on Python 3.9.
"""

import filecmp
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPENSIVE = ROOT / "evals-expensive"
CASE = EXPENSIVE / "big-sweep-in-parts"
SCAFFOLD = CASE / "scaffold.sh"
KEY_PATH = EXPENSIVE / "big-sweep-key.json"
SYNC = EXPENSIVE / "sync_big_sweep.py"

UNTRACKED = ["notes/scratch.md", "rules/r9999_draft.py", "zones/zz_todo.txt"]
ROOT_FILES = ["CHANGELOG.md", "Makefile", "README.md", "main.py", "poetry.lock", "pyproject.toml"]
SUBSET_SIZES = (150, 230, 320, 400, 450)
STOCK_PYTHON = "/usr/bin/python3"


def is_whole_skip(path):
    return path.startswith("web/vendor/")


def is_skipped(path):
    return is_whole_skip(path) or path.endswith(".lock") or path.endswith(".bin")


def run_scaffold(dest, *args, env=None, check=True):
    return subprocess.run(["bash", str(SCAFFOLD), *args], cwd=str(dest), env=env, check=check,
                          capture_output=True, text=True)


def git(dest, *args):
    out = subprocess.run([str(Path(dest) / "bin" / "git"), *args], cwd=str(dest), check=True, capture_output=True, text=True)
    return out.stdout


def tree(dest):
    """{relative path: bytes} for every file outside .git."""
    out = {}
    for base, dirs, names in os.walk(str(dest)):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            path = Path(base) / name
            out[str(path.relative_to(dest))] = path.read_bytes()
    return out


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Fixtures:
    """Built once for the whole module."""

    @classmethod
    def build(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.a, cls.b = base / "a", base / "b"
        for dest in (cls.a, cls.b):
            dest.mkdir()
            run_scaffold(dest)
        cls.subsets = {}
        for n in SUBSET_SIZES:
            dest = base / ("subset%d" % n)
            dest.mkdir()
            run_scaffold(dest, "--subset", str(n))
            cls.subsets[n] = dest
        cls.key = json.loads(KEY_PATH.read_text(encoding="utf-8"))
        cls.files = tree(cls.a)
        cls.tracked = git(cls.a, "ls-files").splitlines()
        cls.untracked = git(cls.a, "ls-files", "--others", "--exclude-standard").split()
        cls.text = {p: b.decode("utf-8", errors="replace") for p, b in cls.files.items() if not p.startswith("bin/")}
        cls.eligible = [p for p in cls.tracked if not is_skipped(p)]
        cls.everything = "\n".join(cls.text.values())


def setUpModule():
    Fixtures.build()


def tearDownModule():
    Fixtures.tmp.cleanup()


def count_under(prefix, direct=False):
    paths = [p for p in Fixtures.tracked if p.startswith(prefix)]
    if direct:
        paths = [p for p in paths if "/" not in p[len(prefix):]]
    return len(paths)


class CountsAndLayoutTest(unittest.TestCase):
    def test_tracked_counts_are_690_650_and_645(self):
        self.assertEqual(len(Fixtures.tracked), 690)
        self.assertEqual(len([p for p in Fixtures.tracked if not is_whole_skip(p)]), 650)
        self.assertEqual(len(Fixtures.eligible), 645)

    def test_the_briefs_verify_command_lines(self):
        # the brief's own pipeline: ls-files count, then the count with web/vendor/ removed (quotepath off), then untracked
        self.assertEqual(git(Fixtures.a, "-c", "core.quotepath=off", "ls-files").count("\n"), 690)
        kept = [p for p in git(Fixtures.a, "-c", "core.quotepath=off", "ls-files").splitlines() if not p.startswith("web/vendor/")]
        self.assertEqual(len(kept), 650)
        self.assertEqual(Fixtures.untracked, UNTRACKED)

    def test_root_holds_exactly_the_six_files(self):
        self.assertEqual(sorted(p for p in Fixtures.tracked if "/" not in p), ROOT_FILES)

    def test_folder_counts_match_the_brief(self):
        self.assertEqual(count_under("api/"), 164)
        self.assertEqual(sorted(p[4:] for p in Fixtures.tracked if p.startswith("api/") and p.count("/") == 1),
                         ["__init__.py", "app.py", "auth.py", "errors.py"])
        for sub in ("accounts", "billing", "plazas", "trips"):
            with self.subTest(sub=sub):
                self.assertEqual(count_under("api/%s/" % sub), 40)
        self.assertEqual(count_under("cli/"), 36)
        self.assertEqual(count_under("cli/", direct=True), 36)
        self.assertEqual(count_under("docs/"), 12)
        self.assertEqual(count_under("docs/", direct=True), 12)
        self.assertEqual(count_under("jobs/"), 28)
        self.assertEqual(count_under("jobs/", direct=True), 4)
        self.assertEqual(count_under("jobs/nightly/"), 24)
        self.assertEqual(count_under("rules/"), 310)
        self.assertEqual(count_under("rules/", direct=True), 310)
        self.assertEqual(count_under("scripts/"), 8)
        self.assertEqual(count_under("scripts/", direct=True), 8)
        self.assertEqual(count_under("tests/"), 36)
        self.assertEqual(count_under("tests/", direct=True), 36)
        self.assertEqual(count_under("zones/"), 20)
        self.assertEqual(count_under("zones/", direct=True), 20)

    def test_web_layout(self):
        self.assertEqual(count_under("web/"), 70)
        self.assertEqual(count_under("web/", direct=True), 6)
        self.assertEqual(count_under("web/views/"), 20)
        self.assertEqual(count_under("web/assets/"), 4)
        self.assertEqual(count_under("web/vendor/"), 40)
        for path in Fixtures.tracked:
            if path.startswith("web/"):
                self.assertTrue(path.count("/") <= 2, path)

    def test_the_folders_add_up_to_the_total(self):
        parts = sum(count_under(p) for p in ("api/", "cli/", "docs/", "jobs/", "rules/", "scripts/", "tests/", "web/", "zones/"))
        self.assertEqual(parts + 6, 690)
        self.assertEqual({p.split("/")[0] for p in Fixtures.tracked if "/" in p},
                         {"api", "cli", "docs", "jobs", "rules", "scripts", "tests", "web", "zones"})

    def test_rules_is_flat_and_numbered_one_to_310(self):
        names = sorted(p[len("rules/"):] for p in Fixtures.tracked if p.startswith("rules/"))
        self.assertTrue(all("/" not in n for n in names))
        numbers = []
        for name in names:
            m = re.fullmatch(r"r(\d{4})_[a-z]+\.py", name)
            self.assertIsNotNone(m, name)
            numbers.append(int(m.group(1)))
        self.assertEqual(numbers, list(range(1, 311)))
        self.assertTrue(names[-1].startswith("r0310_"))

    def test_the_last_eligible_path_in_byte_order_is_in_zones(self):
        ordered = sorted(Fixtures.eligible, key=lambda p: p.encode("utf-8"))
        self.assertEqual(Fixtures.eligible, ordered)
        self.assertTrue(ordered[-1].startswith("zones/"), ordered[-1])
        self.assertNotIn("zones/zz_todo.txt", ordered)

    def test_exactly_three_untracked_files_and_only_bin_is_excluded(self):
        self.assertEqual(Fixtures.untracked, UNTRACKED)
        for path in UNTRACKED:
            self.assertNotIn(path, Fixtures.tracked)
            self.assertTrue((Fixtures.a / path).is_file())
        exclude = [l for l in (Fixtures.a / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.startswith("#")]
        self.assertEqual(exclude, ["bin/"])
        self.assertFalse((Fixtures.a / ".gitignore").exists())
        self.assertEqual(git(Fixtures.a, "status", "--short").split("\n")[:-1].count("?? bin/"), 0)

    def test_nothing_on_disk_is_hidden_except_bin_and_the_untracked_files(self):
        self.assertEqual(set(Fixtures.files) - set(Fixtures.tracked) - set(UNTRACKED), {"bin/git"})

    def test_the_worktree_is_clean_apart_from_the_untracked_files(self):
        status = [l for l in git(Fixtures.a, "status", "--short").splitlines()]
        self.assertEqual(sorted(l[3:] for l in status), sorted(["notes/", "rules/r9999_draft.py", "zones/zz_todo.txt"]))
        self.assertTrue(all(l.startswith("?? ") for l in status), status)

    def test_one_commit_with_a_fixed_date(self):
        self.assertEqual(len(git(Fixtures.a, "log", "--format=%H").split()), 1)
        self.assertEqual(git(Fixtures.a, "log", "-1", "--format=%at|%ct").strip(), "1795424400|1795424400")

    def test_git_wrapper_works_and_bin_stays_out_of_the_list(self):
        self.assertFalse([p for p in Fixtures.tracked if p.startswith("bin/")])
        self.assertTrue(os.access(str(Fixtures.a / "bin" / "git"), os.X_OK))

    def test_every_path_is_plain_ascii_and_sorts_in_git_order(self):
        for path in Fixtures.tracked + UNTRACKED:
            with self.subTest(path=path):
                path.encode("ascii")
                self.assertEqual(path, path.strip())
        self.assertEqual(Fixtures.tracked, sorted(Fixtures.tracked, key=lambda p: p.encode("utf-8")))


class FileContentTest(unittest.TestCase):
    def test_lock_file_binaries_and_vendored_files_say_what_they_are(self):
        self.assertTrue(Fixtures.text["poetry.lock"].strip())
        for path in Fixtures.tracked:
            if path.startswith("web/assets/"):
                with self.subTest(path=path):
                    self.assertTrue(path.endswith(".bin"))
                    self.assertIn(b"\x00", Fixtures.files[path])
            if path.startswith("web/vendor/"):
                with self.subTest(path=path):
                    self.assertIn("endored", Fixtures.text[path].splitlines()[0])

    def test_normal_files_are_30_to_120_lines_and_none_is_over_1000(self):
        for path in Fixtures.tracked:
            if path.endswith(".bin"):
                continue
            n = len(Fixtures.text[path].splitlines())
            self.assertLess(n, 1000, path)
            if not is_skipped(path):
                with self.subTest(path=path):
                    self.assertTrue(30 <= n <= 120, n)

    def test_untracked_files_are_text_and_not_empty(self):
        for path in UNTRACKED:
            with self.subTest(path=path):
                self.assertTrue(Fixtures.text[path].strip())

    def test_every_generated_python_file_compiles(self):
        for path, text in Fixtures.text.items():
            if path.endswith(".py"):
                with self.subTest(path=path):
                    compile(text, path, "exec")

    def test_docs_and_readme_hold_no_planted_token(self):
        docs = [p for p in Fixtures.tracked if p == "README.md" or p.startswith("docs/")]
        self.assertEqual(len([p for p in docs if p.startswith("docs/")]), 12)
        tokens = [f["token"] for f in Fixtures.key["facts"]] + [d["token"] for d in Fixtures.key["decoys"]]
        for path in docs:
            for token in tokens:
                with self.subTest(path=path, token=token):
                    self.assertNotIn(token, Fixtures.text[path])
            with self.subTest(path=path, what="route or command shape"):
                self.assertIsNone(re.search(r"/v3/[a-z]+/[a-z]+|twctl [a-z]", Fixtures.text[path]))

    def test_the_fixture_is_tollway_and_never_the_head_to_head(self):
        self.assertIn("tollway", Fixtures.text["README.md"].lower())
        self.assertIn("twctl", Fixtures.everything)
        self.assertIn("/v3/", Fixtures.everything)
        self.assertNotIn("fxctl", Fixtures.everything)
        self.assertNotIn("/v2/", Fixtures.everything)

    def test_the_fixture_never_names_the_comparison_or_its_answers(self):
        words = ["planted", "decoy", "grader", "evals-expensive", "big-sweep", "sync_big_sweep", "answer key", "scaffold", "the-foundry"]
        for path, text in Fixtures.text.items():
            for word in words:
                with self.subTest(path=path, word=word):
                    self.assertNotIn(word, text.lower())
                    self.assertNotIn(word, path.lower())


class BuildDeterminismTest(unittest.TestCase):
    def assert_same_as_baseline(self, files, head):
        self.assertEqual(sorted(files), sorted(Fixtures.files))
        for path, blob in Fixtures.files.items():
            if path != "bin/git":
                self.assertEqual(blob, files[path], path)
        self.assertEqual(head, git(Fixtures.a, "rev-parse", "HEAD"))

    def build_with(self, env_extra, cwd_name="elsewhere", path_override=None, gitconfig=""):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest = base / cwd_name
            dest.mkdir()
            home = base / "home"
            home.mkdir()
            (home / ".gitconfig").write_text("[core]\n\tautocrlf = true\n[init]\n\tdefaultBranch = trunk\n" + gitconfig +
                                              "[user]\n\tname = Someone Else\n\temail = else@example.org\n", encoding="utf-8")
            keep = ("PATH", "LANG", "LC_ALL", "TMPDIR", "TZ", "USER", "SHELL")
            env = {k: v for k, v in os.environ.items() if k in keep}
            env["HOME"] = str(home)
            if path_override:
                env["PATH"] = path_override + os.pathsep + env.get("PATH", "")
            env.update(env_extra)
            run_scaffold(dest, env=env)
            files = tree(dest)
            head = subprocess.run([str(dest / "bin" / "git"), "rev-parse", "HEAD"], cwd=str(dest), env=env,
                                  check=True, capture_output=True, text=True).stdout
            return files, head

    def test_two_builds_are_byte_identical_with_the_same_commit(self):
        again = tree(Fixtures.b)
        self.assertEqual(sorted(again), sorted(Fixtures.files))
        for path, blob in Fixtures.files.items():
            if path != "bin/git":
                self.assertEqual(blob, again[path], path)
        self.assertEqual(git(Fixtures.a, "rev-parse", "HEAD"), git(Fixtures.b, "rev-parse", "HEAD"))

    def test_a_different_place_locale_timezone_hash_seed_and_git_config_builds_the_same_tree(self):
        files, head = self.build_with({"LC_ALL": "C", "LANG": "C", "TZ": "Pacific/Kiritimati", "PYTHONHASHSEED": "12345"},
                                      cwd_name="a b", gitconfig="[commit]\n\tgpgsign = true\n")
        self.assert_same_as_baseline(files, head)

    def test_a_random_hash_seed_builds_the_same_tree(self):
        files, head = self.build_with({"PYTHONHASHSEED": "random"})
        self.assert_same_as_baseline(files, head)

    @unittest.skipUnless(os.access(STOCK_PYTHON, os.X_OK), "no /usr/bin/python3")
    def test_the_stock_python_builds_the_same_tree_as_the_default(self):
        with tempfile.TemporaryDirectory() as shim:
            os.symlink(STOCK_PYTHON, os.path.join(shim, "python3"))
            files, head = self.build_with({}, path_override=shim)
        self.assert_same_as_baseline(files, head)


class PlantedFactsTest(unittest.TestCase):
    def facts(self, kind=None):
        return [f for f in Fixtures.key["facts"] if kind in (None, f["kind"])]

    def prefix(self, prefix, direct=False):
        out = [f for f in self.facts() if f["path"].startswith(prefix)]
        if direct:
            out = [f for f in out if "/" not in f["path"][len(prefix):]]
        return out

    def test_the_key_has_the_briefs_fields(self):
        key = Fixtures.key
        self.assertEqual(sorted(key), ["decoys", "facts", "layout"])
        for f in key["facts"]:
            self.assertEqual(sorted(f), ["id", "kind", "line", "path", "token"])
            self.assertIn(f["kind"], ("route", "command", "gotcha"))
        for d in key["decoys"]:
            self.assertEqual(sorted(d), ["id", "path", "token", "why"])
            self.assertIn(d["why"], ("vendored", "untracked"))
        self.assertEqual(sorted(key["layout"]), ["after_whole_folder_skips", "file_skips", "skipped_whole", "tracked", "untracked"])

    def test_the_key_layout_matches_the_built_repo(self):
        layout = Fixtures.key["layout"]
        self.assertEqual(layout["tracked"], 690)
        self.assertEqual(layout["after_whole_folder_skips"], 650)
        self.assertEqual(layout["skipped_whole"], {"web/vendor/": 40})
        self.assertEqual(layout["file_skips"], {"lock": 1, "binary": 4})
        self.assertEqual(layout["untracked"], UNTRACKED)
        self.assertEqual(layout["tracked"], len(Fixtures.tracked))
        self.assertEqual(layout["untracked"], Fixtures.untracked)
        self.assertEqual(layout["tracked"] - layout["skipped_whole"]["web/vendor/"] - sum(layout["file_skips"].values()), 645)

    def test_there_are_33_facts_with_unique_ids_and_tokens(self):
        facts = self.facts()
        self.assertEqual(len(facts), 33)
        self.assertEqual([f["id"] for f in facts], ["f%02d" % i for i in range(1, 34)])
        self.assertEqual(len({f["token"] for f in facts}), 33)

    def test_the_decoy_ids_are_d1_to_d5(self):
        self.assertEqual([d["id"] for d in Fixtures.key["decoys"]], ["d%d" % i for i in range(1, 6)])

    def test_facts_per_place_match_the_brief(self):
        def n(prefix, direct=False):
            return len(self.prefix(prefix, direct))

        self.assertEqual(n("main.py"), 1)
        self.assertEqual([f["kind"] for f in self.prefix("api/app.py")], ["route"])
        for sub in ("accounts", "billing", "plazas", "trips"):
            with self.subTest(sub=sub):
                self.assertEqual(n("api/%s/" % sub), 2)
        self.assertEqual(n("api/"), 1 + 8)
        self.assertEqual([f["kind"] for f in self.prefix("cli/")], ["command", "command"])
        self.assertEqual(n("jobs/", direct=True), 1)
        self.assertEqual(n("jobs/nightly/"), 1)
        self.assertEqual(n("rules/"), 12)
        self.assertEqual([f["kind"] for f in self.prefix("scripts/")], ["command"])
        self.assertEqual([f["kind"] for f in self.prefix("tests/")], ["gotcha"])
        self.assertEqual([f["kind"] for f in self.prefix("web/views/")], ["route"])
        self.assertEqual([f["kind"] for f in self.prefix("web/", direct=True)], ["gotcha"])
        self.assertEqual(n("web/"), 2)
        self.assertEqual(n("zones/"), 3)
        self.assertEqual(n("docs/") + n("web/vendor/") + n("web/assets/"), 0)
        total = 1 + 1 + 8 + 2 + 2 + 12 + 1 + 1 + 2 + 3
        self.assertEqual(total, 33)

    def test_each_token_is_at_its_keyed_line_and_appears_once_in_the_tree(self):
        for f in self.facts():
            with self.subTest(fact=f["id"]):
                self.assertIn(f["path"], Fixtures.text)
                lines = Fixtures.text[f["path"]].splitlines()
                self.assertTrue(1 <= f["line"] <= len(lines))
                self.assertIn(f["token"], lines[f["line"] - 1])
                self.assertEqual(Fixtures.everything.count(f["token"]), 1)
                self.assertEqual(Fixtures.text[f["path"]].count(f["token"]), 1)

    def test_each_token_has_the_shape_of_its_kind(self):
        gotcha = [r"^TWY-\d{4}$", r"^ticket \d{4}$", r"^CHG\d{7}$", r"^#\d{5}$", r"^runbook section \d+\.\d+$"]
        for f in self.facts():
            with self.subTest(fact=f["id"]):
                if f["kind"] == "route":
                    self.assertRegex(f["token"], r"^/v3/[a-z]+/[a-z]+/[a-z]+$")
                elif f["kind"] == "command":
                    self.assertRegex(f["token"], r"^twctl [a-z][a-z0-9-]*$")
                else:
                    self.assertTrue(any(re.search(p, f["token"]) for p in gotcha), f["token"])

    def test_no_token_sits_inside_a_longer_word_or_path(self):
        for f in self.facts():
            for m in re.finditer(re.escape(f["token"]), Fixtures.everything):
                before = Fixtures.everything[m.start() - 1] if m.start() else " "
                after = Fixtures.everything[m.end()] if m.end() < len(Fixtures.everything) else " "
                with self.subTest(fact=f["id"]):
                    self.assertIsNone(re.match(r"[A-Za-z0-9_-]", before), repr(before))
                    self.assertIsNone(re.match(r"[A-Za-z0-9_/<-]", after), repr(after))

    def test_no_token_is_a_substring_of_another(self):
        tokens = [f["token"] for f in self.facts()] + [d["token"] for d in Fixtures.key["decoys"]]
        for a in tokens:
            for b in tokens:
                if a != b:
                    self.assertNotIn(a, b)

    def test_no_fact_is_in_a_skipped_vendored_or_untracked_file(self):
        for f in self.facts():
            with self.subTest(fact=f["id"]):
                self.assertIn(f["path"], Fixtures.tracked)
                self.assertFalse(is_skipped(f["path"]), f["path"])
                self.assertNotIn(f["path"], UNTRACKED)
                self.assertNotIn(f["path"], Fixtures.untracked)
        for path in [p for p in Fixtures.tracked if is_skipped(p)] + UNTRACKED:
            with self.subTest(path=path):
                for f in self.facts():
                    self.assertNotIn(f["token"], Fixtures.text[path])
                if path in ("poetry.lock",) or path.endswith(".bin"):
                    self.assertIsNone(re.search(r"/v3/|twctl ", Fixtures.text[path]))

    def test_every_route_command_and_code_in_the_tree_is_a_fact_or_a_decoy(self):
        decoys = Fixtures.key["decoys"]
        known = {f["token"] for f in self.facts()} | {d["token"] for d in decoys}
        routes = set(re.findall(r"/v3/[a-z][a-z0-9_-]*/[a-z][a-z0-9_/-]*", Fixtures.everything))
        commands = set(re.findall(r"twctl [a-z][a-z0-9-]*", Fixtures.everything))
        codes = set()
        for pattern in (r"\bTWY-\d{4}\b", r"ticket \d{4}\b", r"\bCHG\d{7}\b", r"#\d{5}\b", r"runbook section \d+\.\d+"):
            codes.update(re.findall(pattern, Fixtures.everything))
        self.assertEqual(routes | commands | codes, known)

    def test_a_fact_sits_in_rules_at_every_fifty_file_stretch(self):
        names = sorted(p for p in Fixtures.tracked if p.startswith("rules/"))
        ranks = {names.index(f["path"]) + 1 for f in self.prefix("rules/")}
        self.assertEqual(len(ranks), 12)
        for start in range(1, 311, 50):
            with self.subTest(stretch="%d-%d" % (start, start + 49)):
                self.assertTrue([r for r in ranks if start <= r < start + 50], sorted(ranks))

    def test_rules_facts_include_the_first_and_the_last_file_and_are_evenly_spaced(self):
        names = sorted(p for p in Fixtures.tracked if p.startswith("rules/"))
        ranks = sorted(names.index(f["path"]) + 1 for f in self.prefix("rules/"))
        self.assertEqual(ranks[0], 1)
        self.assertEqual(ranks[-1], 310)
        gaps = {b - a for a, b in zip(ranks, ranks[1:])}
        self.assertTrue(max(gaps) - min(gaps) <= 1, gaps)
        self.assertTrue(10 <= min(gaps), gaps)
        self.assertEqual(self.prefix("rules/")[-1]["path"].split("/")[1][:5], "r0310")

    def test_a_fact_sits_in_the_last_eligible_file_in_byte_order(self):
        last = sorted(Fixtures.eligible, key=lambda p: p.encode("utf-8"))[-1]
        self.assertIn(last, [f["path"] for f in self.facts()])

    def test_every_part_of_any_plausible_size_holds_facts_and_so_does_the_last(self):
        paths = {f["path"] for f in self.facts()}
        for size in (150, 200, 300, 450):
            parts = [Fixtures.eligible[i:i + size] for i in range(0, len(Fixtures.eligible), size)]
            for i, part in enumerate(parts):
                with self.subTest(size=size, part=i + 1):
                    self.assertTrue(paths & set(part))
        # and the final stretch of 45 files, the shortest tail a 300-file part leaves
        self.assertTrue(paths & set(Fixtures.eligible[-45:]))

    def test_each_api_subfolder_and_each_eligible_top_folder_holds_a_fact(self):
        paths = [f["path"] for f in self.facts()]
        for folder in ("api/accounts/", "api/billing/", "api/plazas/", "api/trips/", "cli/", "jobs/nightly/", "rules/",
                       "scripts/", "tests/", "web/views/", "zones/"):
            with self.subTest(folder=folder):
                self.assertTrue([p for p in paths if p.startswith(folder)])
        self.assertTrue([p for p in paths if p.startswith("jobs/") and "/" not in p[5:]])
        self.assertTrue([p for p in paths if p.startswith("web/") and "/" not in p[4:]])

    def test_the_key_is_what_the_scaffold_emits_and_emitting_builds_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "key.json"
            run_scaffold(tmp, "--emit-key", str(out))
            self.assertEqual(out.read_text(encoding="utf-8"), KEY_PATH.read_text(encoding="utf-8"))
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["key.json"])

    def test_the_scaffold_never_writes_the_key_into_the_workspace(self):
        for dest in [Fixtures.a] + list(Fixtures.subsets.values()):
            names = {Path(p).name for p in tree(dest)}
            self.assertNotIn("big-sweep-key.json", names)
            self.assertFalse([n for n in names if n.endswith(".json") and "key" in n])
        tokens = [f["token"] for f in self.facts()]
        meta = git(Fixtures.a, "log", "--all", "--format=%H%n%an%n%ae%n%s%n%b") + git(Fixtures.a, "ls-files")
        meta += Fixtures.files["bin/git"].decode("utf-8")
        for token in tokens:
            self.assertNotIn(token, meta)


class DecoyTest(unittest.TestCase):
    def test_there_are_five_decoys_two_vendored_and_three_untracked(self):
        decoys = Fixtures.key["decoys"]
        self.assertEqual(len(decoys), 5)
        self.assertEqual(sorted(d["why"] for d in decoys), ["untracked"] * 3 + ["vendored"] * 2)
        self.assertEqual(sorted(d["path"] for d in decoys if d["why"] == "untracked"), UNTRACKED)
        for d in decoys:
            if d["why"] == "vendored":
                self.assertTrue(d["path"].startswith("web/vendor/"))

    def test_each_decoy_exists_where_keyed_and_appears_once_in_the_whole_tree(self):
        for d in Fixtures.key["decoys"]:
            with self.subTest(decoy=d["id"]):
                self.assertIn(d["token"], Fixtures.text[d["path"]])
                self.assertEqual(Fixtures.text[d["path"]].count(d["token"]), 1)
                self.assertEqual(Fixtures.everything.count(d["token"]), 1)

    def test_vendored_decoys_are_tracked_and_untracked_decoys_are_not(self):
        for d in Fixtures.key["decoys"]:
            with self.subTest(decoy=d["id"]):
                if d["why"] == "vendored":
                    self.assertIn(d["path"], Fixtures.tracked)
                else:
                    self.assertNotIn(d["path"], Fixtures.tracked)
                    self.assertIn(d["path"], Fixtures.untracked)

    def test_a_decoy_is_never_a_fact_token(self):
        facts = {f["token"] for f in Fixtures.key["facts"]}
        for d in Fixtures.key["decoys"]:
            self.assertNotIn(d["token"], facts)
        self.assertEqual({f["path"] for f in Fixtures.key["facts"]} & {d["path"] for d in Fixtures.key["decoys"]}, set())

    def test_the_untracked_file_in_the_flat_folder_is_not_numbered_into_the_rules(self):
        self.assertTrue((Fixtures.a / "rules" / "r9999_draft.py").is_file())
        self.assertEqual(count_under("rules/"), 310)


class SubsetTest(unittest.TestCase):
    def expected(self, n):
        rest = sorted((p for p in Fixtures.eligible if "/" in p), key=lambda p: p.encode("utf-8"))
        return sorted(["CHANGELOG.md", "Makefile", "README.md", "main.py", "pyproject.toml"] + rest[:n - 5])

    def test_each_subset_has_exactly_n_tracked_files(self):
        for n, dest in Fixtures.subsets.items():
            with self.subTest(n=n):
                self.assertEqual(len(git(dest, "ls-files").splitlines()), n)

    def test_each_subset_is_the_five_root_files_plus_the_first_paths_in_byte_order(self):
        for n, dest in Fixtures.subsets.items():
            with self.subTest(n=n):
                self.assertEqual(git(dest, "ls-files").splitlines(), self.expected(n))

    def test_a_subset_has_no_vendor_lock_binary_or_untracked_file(self):
        for n, dest in Fixtures.subsets.items():
            with self.subTest(n=n):
                self.assertEqual(git(dest, "ls-files", "--others", "--exclude-standard").split(), [])
                on_disk = {p for p in tree(dest) if p != "bin/git"}
                self.assertEqual(on_disk, set(git(dest, "ls-files").splitlines()))
                for path in on_disk:
                    self.assertFalse(is_skipped(path), path)
                    self.assertNotIn(path, UNTRACKED)
                self.assertFalse((dest / "poetry.lock").exists())
                self.assertFalse((dest / "notes").exists())
                self.assertEqual(git(dest, "status", "--short").strip(), "")

    def test_subset_files_are_byte_identical_to_the_full_build(self):
        for n, dest in Fixtures.subsets.items():
            for path in git(dest, "ls-files").splitlines():
                with self.subTest(n=n, path=path):
                    self.assertEqual((dest / path).read_bytes(), Fixtures.files[path])

    def test_a_subset_keeps_the_scaffolds_git_wrapper_and_date(self):
        for n, dest in Fixtures.subsets.items():
            with self.subTest(n=n):
                self.assertTrue(os.access(str(dest / "bin" / "git"), os.X_OK))
                self.assertEqual(git(dest, "log", "-1", "--format=%at").strip(), "1795424400")

    def test_the_biggest_subset_is_every_eligible_file_and_one_more_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_scaffold(tmp, "--subset", "645")
            self.assertEqual(sorted(git(tmp, "ls-files").splitlines()),
                             sorted(Fixtures.eligible))
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scaffold(tmp, "--subset", "646", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((Path(tmp) / ".git").exists())

    def test_the_smallest_subset_is_the_five_root_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_scaffold(tmp, "--subset", "5")
            self.assertEqual(git(tmp, "ls-files").splitlines(), ["CHANGELOG.md", "Makefile", "README.md", "main.py", "pyproject.toml"])

    def test_a_subset_below_five_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scaffold(tmp, "--subset", "4", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((Path(tmp) / ".git").exists())

    def test_a_bad_subset_value_or_a_missing_one_exits_two_and_builds_nothing(self):
        for args in (["--subset", "abc"], ["--subset", ""], ["--subset"], ["--subset", "-5"], ["--subset", "1.5"], ["--subset", "15 0"]):
            with self.subTest(args=args):
                with tempfile.TemporaryDirectory() as tmp:
                    result = run_scaffold(tmp, *args, check=False)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("usage", result.stderr)
                    self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_emit_key_without_a_path_exits_two_and_builds_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scaffold(tmp, "--emit-key", check=False)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_the_subset_line_is_one_line_and_a_non_empty_value_acts_like_the_flag(self):
        lines = SCAFFOLD.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines.count('SUBSET=""'), 1)
        self.assertLess(lines.index('SUBSET=""'), 30, "SUBSET should sit near the top")
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "scaffold.sh"
            copy.write_text("\n".join('SUBSET="230"' if l == 'SUBSET=""' else l for l in lines) + "\n", encoding="utf-8")
            dest = Path(tmp) / "out"
            dest.mkdir()
            subprocess.run(["bash", str(copy)], cwd=str(dest), check=True, capture_output=True)
            self.assertEqual(git(dest, "ls-files").splitlines(), self.expected(230))
            self.assertEqual(git(dest, "ls-files", "--others", "--exclude-standard").split(), [])


class ScannerTextTest(unittest.TestCase):
    """The directory scanner reads tracked files; the scaffold and the text it generates ship through it."""

    def patterns(self):
        EVAL, BT, ICON = "ev" + "al", chr(96), "icon" + ".png"
        ENV = re.escape("os." + "env" + "iron")
        return [
            re.compile(EVAL + BT),
            re.compile(r"^[ \t]*" + "pa" + r"ss([ \t]|$)", re.M),
            re.compile("np" + r"x\s+@?[\w.-]"),
            re.compile(r"\*\*" + ENV + "|dict\\(" + ENV + "\\)|" + ENV + r"\.copy\(\)"),
            re.compile(ENV + r"\[(?![\"'])"),
            re.compile(re.escape(ICON)),
        ]

    def test_the_generated_fixture_holds_no_scanner_trigger(self):
        for path, text in Fixtures.text.items():
            text = text.replace(chr(92), "")
            for pattern in self.patterns():
                with self.subTest(path=path):
                    self.assertIsNone(pattern.search(text))

    def test_every_subset_holds_no_scanner_trigger(self):
        for n, dest in Fixtures.subsets.items():
            for path, blob in tree(dest).items():
                if path == "bin/git":
                    continue
                text = blob.decode("utf-8", errors="replace").replace(chr(92), "")
                for pattern in self.patterns():
                    with self.subTest(n=n, path=path):
                        self.assertIsNone(pattern.search(text))

    def test_the_case_files_the_scaffold_and_the_sync_script_hold_no_scanner_trigger(self):
        files = [p for p in CASE.rglob("*") if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts]
        files += [SYNC, KEY_PATH]
        self.assertTrue(len(files) >= 10, files)
        for path in files:
            text = path.read_text(encoding="utf-8").replace(chr(92), "")
            for pattern in self.patterns():
                with self.subTest(path=str(path.relative_to(ROOT))):
                    self.assertIsNone(pattern.search(text))

    def test_this_test_file_holds_no_scanner_trigger(self):
        text = Path(__file__).read_text(encoding="utf-8").replace(chr(92), "")
        for pattern in self.patterns():
            self.assertIsNone(pattern.search(text))


class CaseFilesTest(unittest.TestCase):
    def head(self):
        return (CASE / "prompt.md").read_text(encoding="utf-8").split("---")[1]

    def test_case_yaml_holds_the_briefs_values(self):
        yaml = (CASE / "case.yaml").read_text(encoding="utf-8")
        self.assertRegex(yaml, r'(?m)^schema_version: "1\.1"$')
        self.assertIn("name: big-sweep-in-parts\n", yaml)
        self.assertRegex(yaml, r"(?m)^context:\n  scaffold_script: scaffold\.sh$")

    def test_the_scaffold_is_executable_and_the_case_is_not_under_evals(self):
        self.assertTrue(os.access(str(SCAFFOLD), os.X_OK))
        self.assertTrue(SCAFFOLD.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\n"))
        self.assertFalse((ROOT / "evals" / "big-sweep-in-parts").exists())
        for sub in (ROOT / "evals").iterdir() if (ROOT / "evals").is_dir() else []:
            self.assertNotIn("big-sweep", sub.name)
        self.assertTrue(CASE.is_dir() and CASE.parent == EXPENSIVE)

    def test_the_prompt_front_matter_is_exact(self):
        head = self.head()
        for line in ("runs: 1", "tags: [big-sweep]", "max_turns: 40", "timeout_seconds: 3600",
                     "allowed_tools: [Agent, Read, Glob, Grep, Bash, Write]"):
            with self.subTest(line=line):
                self.assertIn("\n%s\n" % line, head)
        self.assertLessEqual(int(re.search(r"^timeout_seconds: (\d+)$", head, re.M).group(1)), 3600)

    def test_the_prompt_body_is_the_briefs_text_verbatim(self):
        body = (CASE / "prompt.md").read_text(encoding="utf-8").split("---", 2)[2].strip()
        want_intro = (
            "You're the session a user is working in, and they want to get to know the repo in the current directory. "
            "Dispatch the the-foundry:investigate agent with the brief below, and follow through on what its report tells you "
            "until the whole codebase has been read. Each time investigate returns a report, save it, complete and word for word, "
            "to `parts/part-<n>.md` (n counting from 1) with the Write tool before you do anything else. If a result arrives as a "
            "preview with the full text saved to a file, read that file and save the full text. Don't read the code yourself. "
            "When you're finished, reply with one line per saved file: its path and the report's first line.")
        want_brief = (
            'Brief for the agent: "This is a new codebase to me, and I need to understand the whole thing. In this sandbox the plain '
            '`git` command is blocked: use `./bin/git` wherever you\'d type `git`, and tell any agent you brief to do the same."')
        self.assertEqual(body.split("\n\n"), [want_intro, want_brief])

    def test_the_prompt_names_a_real_agent_and_no_planted_token(self):
        text = (CASE / "prompt.md").read_text(encoding="utf-8")
        for ref in re.findall(r"the-foundry:([a-z][\w-]*)", text):
            self.assertTrue((ROOT / "agents" / ("%s.md" % ref)).exists(), ref)
        for f in Fixtures.key["facts"]:
            self.assertNotIn(f["token"], text)
        for word in ("NOT A PER-FILE READ", "CONTINUE SWEEP", "SWEEP IN PARTS", "file-reader"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_the_prompt_asks_nothing_about_cost_or_permission(self):
        text = (CASE / "prompt.md").read_text(encoding="utf-8").lower()
        for word in ("cost", "price", "permission", "approval", "ask the user"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_the_six_graders_exist_and_nothing_else(self):
        self.assertEqual(sorted(p.name for p in (CASE / "graders").iterdir()),
                         ["continued.md", "finished.md", "no-asking.md", "no-fallback.md", "parts-saved.md", "roster.md"])

    def test_each_grader_has_the_briefs_exact_fields(self):
        def read(name):
            return (CASE / "graders" / name).read_text(encoding="utf-8")

        self.assertIn("type: tool_used\ntool: Agent\ninput_match: CONTINUE SWEEP\nmin: 2\n", read("continued.md"))
        finished = read("finished.md")
        for want in ("type: regex\n", "target: trace\n", 'pattern: "SWEEP IN PARTS: 0 areas not read"\n', "match: contains\n"):
            self.assertIn(want, finished)
        self.assertIn("type: file_exists\npath: parts/part-1.md\n", read("parts-saved.md"))
        roster = read("roster.md")
        for want in ("type: regex\n", "target: trace\n", 'pattern: "the-foundry:file-reader"\n', "match: contains\n"):
            self.assertIn(want, roster)
        fallback = read("no-fallback.md")
        for want in ("type: regex\n", "target: last_message\n", 'pattern: "NOT A PER-FILE READ"\n', "match: not_contains\n"):
            self.assertIn(want, fallback)
        asking = read("no-asking.md")
        self.assertIn("type: llm\nfocus: last_message\n", asking)
        self.assertIn("PASS only if the message lists saved report files and does not ask the user whether to continue, "
                      "for permission, or for approval of a size or cost. FAIL if it asks any of those or stops with parts "
                      "unread and no failure named.", asking)

    def test_every_grader_is_front_matter_that_closes(self):
        for path in (CASE / "graders").glob("*.md"):
            with self.subTest(grader=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                self.assertGreaterEqual(text.count("\n---\n"), 1)

    def test_the_finished_pattern_is_a_literal_that_matches_the_fixed_token(self):
        text = (CASE / "graders" / "finished.md").read_text(encoding="utf-8")
        pattern = json.loads(re.search(r'^pattern: (".*")$', text, re.M).group(1))
        self.assertTrue(re.search(pattern, "SWEEP IN PARTS: 0 areas not read"))
        self.assertIsNone(re.search(pattern, "SWEEP IN PARTS: 3 areas not read"))
        self.assertIsNone(re.search(pattern, "SWEEP IN PARTS: 10 areas not read"))


class SyncScriptTest(unittest.TestCase):
    def run_sync(self, script, *args):
        return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)

    def committed(self):
        out = {"big-sweep-key.json": KEY_PATH.read_text(encoding="utf-8")}
        for p in (CASE / "graders").glob("*.md"):
            out["big-sweep-in-parts/graders/" + p.name] = p.read_text(encoding="utf-8")
        for folder in sorted(EXPENSIVE.glob("reply-size-*")):
            for p in folder.rglob("*"):
                if p.is_file() and "__pycache__" not in p.parts:
                    out[str(p.relative_to(EXPENSIVE))] = p.read_text(encoding="utf-8")
        return out

    def copy_of_the_case(self, tmp):
        """A private copy of evals-expensive's big-sweep files so --check can be run against a changed one."""
        dest = Path(tmp) / "evals-expensive"
        shutil.copytree(str(CASE), str(dest / "big-sweep-in-parts"), ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(str(KEY_PATH), str(dest / "big-sweep-key.json"))
        shutil.copy(str(SYNC), str(dest / "sync_big_sweep.py"))
        return dest

    def test_check_exits_zero_on_the_committed_files_and_writes_nothing(self):
        before = {str(p): sha(p) for p in EXPENSIVE.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        result = self.run_sync(SYNC, "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("differs", result.stdout)
        after = {str(p): sha(p) for p in EXPENSIVE.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        self.assertEqual(before, after)

    def test_out_writes_exactly_what_is_committed_and_touches_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_sync(SYNC, "--out", tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            written = {str(p.relative_to(tmp)): p.read_text(encoding="utf-8") for p in Path(tmp).rglob("*") if p.is_file()}
            self.assertEqual(written, self.committed())
            self.assertEqual(len(written), 43, sorted(written))

    def test_out_does_not_write_into_the_repo(self):
        before = sorted(str(p) for p in EXPENSIVE.rglob("*") if "__pycache__" not in p.parts)
        with tempfile.TemporaryDirectory() as tmp:
            self.run_sync(SYNC, "--out", tmp)
        self.assertEqual(before, sorted(str(p) for p in EXPENSIVE.rglob("*") if "__pycache__" not in p.parts))

    def test_out_into_a_missing_nested_folder_creates_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "deep" / "er"
            result = self.run_sync(SYNC, "--out", str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "big-sweep-key.json").is_file())

    def test_out_removes_a_stale_grader_and_a_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_sync(SYNC, "--out", tmp)
            stale = Path(tmp) / "big-sweep-in-parts" / "graders" / "old-one.md"
            stale.write_text("x", encoding="utf-8")
            first = {str(p): sha(p) for p in Path(tmp).rglob("*") if p.is_file() and p != stale}
            self.run_sync(SYNC, "--out", tmp)
            self.assertFalse(stale.exists())
            self.assertEqual(first, {str(p): sha(p) for p in Path(tmp).rglob("*") if p.is_file()})

    def test_check_names_a_changed_grader_and_exits_one_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.copy_of_the_case(tmp)
            target = dest / "big-sweep-in-parts" / "graders" / "roster.md"
            target.write_text(target.read_text(encoding="utf-8").replace("file-reader", "file-readers"), encoding="utf-8")
            before = {str(p): sha(p) for p in dest.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
            result = self.run_sync(dest / "sync_big_sweep.py", "--check")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("big-sweep-in-parts/graders/roster.md", result.stdout)
            self.assertNotIn("graders/finished.md", result.stdout)
            self.assertEqual(before, {str(p): sha(p) for p in dest.rglob("*") if p.is_file() and "__pycache__" not in p.parts})

    def test_check_names_a_changed_key_and_a_missing_grader_and_every_file_that_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.copy_of_the_case(tmp)
            key = dest / "big-sweep-key.json"
            key.write_text(key.read_text(encoding="utf-8").replace("f01", "f99"), encoding="utf-8")
            (dest / "big-sweep-in-parts" / "graders" / "no-asking.md").unlink()
            result = self.run_sync(dest / "sync_big_sweep.py", "--check")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("big-sweep-key.json", result.stdout)
            self.assertIn("graders/no-asking.md", result.stdout)
            self.assertFalse((dest / "big-sweep-in-parts" / "graders" / "no-asking.md").exists(), "--check wrote a file")

    def test_check_flags_an_extra_whitespace_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.copy_of_the_case(tmp)
            target = dest / "big-sweep-in-parts" / "graders" / "continued.md"
            target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            result = self.run_sync(dest / "sync_big_sweep.py", "--check")
            self.assertEqual(result.returncode, 1)
            self.assertIn("graders/continued.md", result.stdout)

    def test_a_write_in_a_copy_then_check_agrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.copy_of_the_case(tmp)
            (dest / "big-sweep-in-parts" / "graders" / "finished.md").write_text("junk", encoding="utf-8")
            self.assertEqual(self.run_sync(dest / "sync_big_sweep.py", "--check").returncode, 1)
            self.assertEqual(self.run_sync(dest / "sync_big_sweep.py").returncode, 0)
            self.assertEqual(self.run_sync(dest / "sync_big_sweep.py", "--check").returncode, 0)
            self.assertTrue(filecmp.cmp(str(dest / "big-sweep-in-parts" / "graders" / "finished.md"),
                                        str(CASE / "graders" / "finished.md"), shallow=False))

    def test_the_sync_script_is_standard_library_only_and_compiles_on_old_python(self):
        text = SYNC.read_text(encoding="utf-8")
        compile(text, str(SYNC), "exec")
        spec = importlib.util.spec_from_file_location("sync_big_sweep", str(SYNC))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdlib = set(getattr(sys, "stdlib_module_names", ()))
        for name in re.findall(r"(?m)^(?:import|from) ([a-z_]+)", text):
            if stdlib:
                self.assertIn(name, stdlib, name)
        self.assertNotRegex(text, r"(?m)removeprefix|removesuffix|^\s*match\s")

    def test_the_committed_graders_match_the_expected_set_of_the_script(self):
        spec = importlib.util.spec_from_file_location("sync_big_sweep2", str(SYNC))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.expected(), self.committed())
        self.assertEqual(len(module.expected()), 43)

    @unittest.skipUnless(os.access(STOCK_PYTHON, os.X_OK), "no /usr/bin/python3")
    def test_the_sync_check_also_passes_under_the_stock_python(self):
        result = subprocess.run([STOCK_PYTHON, str(SYNC), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ScaffoldSourceTest(unittest.TestCase):
    def test_the_scaffold_has_no_second_copy_of_the_key_and_no_network_use(self):
        text = SCAFFOLD.read_text(encoding="utf-8")
        for word in ("curl ", "wget ", "http://", "https://", "claude -p", "claude plugin"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_the_scaffold_uses_a_fixed_seed_and_a_fixed_commit_date(self):
        text = SCAFFOLD.read_text(encoding="utf-8")
        self.assertRegex(text, r"SEED = \d+")
        self.assertIn("2026-11-23T09:00:00 +0000", text)
        self.assertIn("--emit-key", text)

    def test_no_stray_pyc_or_state_is_left_in_the_workspace_after_a_build(self):
        names = [p for p in Fixtures.files if "__pycache__" in p or p.endswith(".pyc")]
        self.assertEqual(names, [])


if __name__ == "__main__":
    unittest.main()
