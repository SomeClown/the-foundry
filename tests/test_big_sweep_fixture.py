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
SUBSET_SIZES = (150, 230, 320, 400, 450, 600, 900, 945)
LATE_RULES_FROM = 311   # rules/r0311 to r0610 carry the ordinary routes and commands added with the growth
TRACKED, AFTER_WHOLE, READABLE = 990, 950, 945
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


# The committed answer key's facts and decoys as the 990-file build wrote them (growing rules/ from 310 to 610 files
# shifted the seeded draws, so every token and most paths differ from the 690-file build; the owner accepted that).
# What must not move is the layout, the ids and the per-folder counts: see FactDistributionTest.
# A later change may move line numbers, never these.
GOLDEN_FACTS = [
    ('f01', 'gotcha', 'api/accounts/account.py', 'ticket 6005'),
    ('f02', 'route', 'api/accounts/trailer.py', '/v3/accounts/ledgers/reopen'),
    ('f03', 'route', 'api/app.py', '/v3/gateway/balances/cancel'),
    ('f04', 'route', 'api/billing/bridge.py', '/v3/billing/permits/refresh'),
    ('f05', 'gotcha', 'api/billing/export.py', 'CHG1134393'),
    ('f06', 'gotcha', 'api/plazas/deposit.py', '#70513'),
    ('f07', 'route', 'api/plazas/tow.py', '/v3/plazas/booths/split'),
    ('f08', 'route', 'api/trips/axle.py', '/v3/trips/speeds/cancel'),
    ('f09', 'gotcha', 'api/trips/refund.py', 'runbook section 4.2'),
    ('f10', 'command', 'cli/cmd_booth.py', 'twctl reprice-class'),
    ('f11', 'command', 'cli/cmd_weight.py', 'twctl reprice-axle'),
    ('f12', 'gotcha', 'jobs/nightly/commuter_close.py', 'TWY-7179'),
    ('f13', 'command', 'jobs/runner.py', 'twctl confirm-ledger'),
    ('f14', 'gotcha', 'main.py', 'TWY-5256'),
    ('f15', 'gotcha', 'rules/r0001_vehicle.py', 'ticket 2107'),
    ('f16', 'route', 'rules/r0056_span.py', '/v3/rules/permits/assign'),
    ('f17', 'command', 'rules/r0112_receipt.py', 'twctl cancel-batch'),
    ('f18', 'gotcha', 'rules/r0167_ramp.py', 'CHG3081312'),
    ('f19', 'route', 'rules/r0222_discount.py', '/v3/rules/classes/thaw'),
    ('f20', 'command', 'rules/r0278_entry.py', 'twctl lock-account'),
    ('f21', 'gotcha', 'rules/r0333_waiver.py', '#76355'),
    ('f22', 'route', 'rules/r0389_height.py', '/v3/rules/vaults/unlock'),
    ('f23', 'command', 'rules/r0444_payment.py', 'twctl defer-audit'),
    ('f24', 'gotcha', 'rules/r0499_refund.py', 'runbook section 1.4'),
    ('f25', 'route', 'rules/r0555_camera.py', '/v3/rules/imports/reassign'),
    ('f26', 'command', 'rules/r0610_vehicle.py', 'twctl sweep-sensor'),
    ('f27', 'command', 'scripts/export_ledger.py', 'twctl purge-carpool'),
    ('f28', 'gotcha', 'tests/test_sync.py', 'TWY-7816'),
    ('f29', 'gotcha', 'web/session.py', 'ticket 8293'),
    ('f30', 'route', 'web/views/lien.py', '/v3/web/permits/purge'),
    ('f31', 'route', 'zones/z04_camera.py', '/v3/zones/bridges/split'),
    ('f32', 'command', 'zones/z11_discount.py', 'twctl reprice-batch'),
    ('f33', 'gotcha', 'zones/z20_cashier.py', 'CHG4677291'),
]
GOLDEN_DECOYS = [
    ('d1', 'untracked', 'notes/scratch.md', 'runbook section 2.1'),
    ('d2', 'untracked', 'rules/r9999_draft.py', '/v3/drafts/fines/merge'),
    ('d3', 'vendored', 'web/vendor/conelib.py', '#50520'),
    ('d4', 'vendored', 'web/vendor/speedlib.py', '/v3/legacy/imports/reassign'),
    ('d5', 'untracked', 'zones/zz_todo.txt', 'twctl split-balance'),
]

ROUTE_DECORATOR = re.compile(r'^@route\("([^"]+)"\)', re.M)
COMMAND_DECORATOR = re.compile(r'^@command\("([^"]+)"\)', re.M)
PUBLIC_DEF = re.compile(r"^def ([A-Za-z][A-Za-z0-9_]*)\(", re.M)
ROUTE_HOMES = ("api/", "web/views/")
COMMAND_HOMES = ("cli/", "scripts/", "jobs/")
LATE_RULES_ROUTES, LATE_RULES_COMMANDS, LATE_RULES_CAP = 60, 90, 2


def late_rules(path):
    """rules/r0311_x.py to rules/r0610_x.py: the files the growth gave ordinary routes and commands."""
    m = re.fullmatch(r"rules/r(\d{4})_[a-z]+\.py", path)
    return bool(m) and LATE_RULES_FROM <= int(m.group(1)) <= 610


def in_route_home(path):
    return path.startswith(ROUTE_HOMES) or late_rules(path)


def in_command_home(path):
    return path.startswith(COMMAND_HOMES) or late_rules(path)
CODE_FOLDERS = ("api/", "api/accounts/", "api/billing/", "api/plazas/", "api/trips/", "cli/", "jobs/", "jobs/nightly/",
                "rules/", "scripts/", "tests/", "web/", "web/views/", "zones/")

FUNCTIONS_BAND = (1.1, 1.7)
ROUTES_BAND = (0.15, 0.25)
COMMANDS_BAND = (0.25, 0.35)
SUBSET_FUNCTIONS_FLOOR = 1.1


def known_tokens(key):
    return {f["token"] for f in key["facts"]} | {d["token"] for d in key["decoys"]}


def ordinary_list(texts, key):
    """{"route": [(path, token)], "command": [(path, token)]} for every decorated route and command that is not a fact or decoy."""
    known = known_tokens(key)
    out = {"route": [], "command": []}
    for path in sorted(texts):
        if not path.endswith(".py"):
            continue
        for kind, rx in (("route", ROUTE_DECORATOR), ("command", COMMAND_DECORATOR)):
            for token in rx.findall(texts[path]):
                if token not in known:
                    out[kind].append((path, token))
    return out


def ordinary_tokens(texts, key):
    return {kind: {t for _p, t in found} for kind, found in ordinary_list(texts, key).items()}


def public_names(texts):
    return [(path, name) for path in sorted(texts) if path.endswith(".py") for name in PUBLIC_DEF.findall(texts[path])]


def measure(texts, readable, key):
    """Counts over the readable files only."""
    mine = {p: texts[p] for p in readable}
    py = [p for p in readable if p.endswith(".py")]
    found = ordinary_list(mine, key)
    return {"files": len(readable), "py": len(py), "functions": len(public_names(mine)),
            "routes": len(found["route"]), "commands": len(found["command"])}


def band_failures(m, subset=False):
    """Names each density band the counts fall outside of (an empty list means all hold)."""
    fails = []
    per_py = m["functions"] / float(m["py"])
    if subset:
        if per_py < SUBSET_FUNCTIONS_FLOOR:
            fails.append("subset functions %.3f" % per_py)
        return fails
    for name, value, (low, high) in (("functions", per_py, FUNCTIONS_BAND),
                                     ("routes", m["routes"] / float(m["files"]), ROUTES_BAND),
                                     ("commands", m["commands"] / float(m["files"]), COMMANDS_BAND)):
        if value < low:
            fails.append("%s low %.3f" % (name, value))
        if value > high:
            fails.append("%s high %.3f" % (name, value))
    return fails


def load_check_parts():
    spec = importlib.util.spec_from_file_location("check_parts_for_fixture_tests", str(EXPENSIVE / "check_parts.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    def test_tracked_counts_are_990_950_and_945(self):
        self.assertEqual(len(Fixtures.tracked), TRACKED)
        self.assertEqual(len([p for p in Fixtures.tracked if not is_whole_skip(p)]), AFTER_WHOLE)
        self.assertEqual(len(Fixtures.eligible), READABLE)

    def test_the_briefs_verify_command_lines(self):
        # the brief's own pipeline: ls-files count, then the count with web/vendor/ removed (quotepath off), then untracked
        self.assertEqual(git(Fixtures.a, "-c", "core.quotepath=off", "ls-files").count("\n"), TRACKED)
        kept = [p for p in git(Fixtures.a, "-c", "core.quotepath=off", "ls-files").splitlines() if not p.startswith("web/vendor/")]
        self.assertEqual(len(kept), AFTER_WHOLE)
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
        self.assertEqual(count_under("rules/"), 610)
        self.assertEqual(count_under("rules/", direct=True), 610)
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
        self.assertEqual(parts + 6, TRACKED)
        self.assertEqual({p.split("/")[0] for p in Fixtures.tracked if "/" in p},
                         {"api", "cli", "docs", "jobs", "rules", "scripts", "tests", "web", "zones"})

    def test_rules_is_flat_and_numbered_one_to_610(self):
        names = sorted(p[len("rules/"):] for p in Fixtures.tracked if p.startswith("rules/"))
        self.assertTrue(all("/" not in n for n in names))
        numbers = []
        for name in names:
            m = re.fullmatch(r"r(\d{4})_[a-z]+\.py", name)
            self.assertIsNotNone(m, name)
            numbers.append(int(m.group(1)))
        self.assertEqual(numbers, list(range(1, 611)))
        self.assertTrue(names[-1].startswith("r0610_"))

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
        self.assertEqual(self.exclude_lines(Fixtures.a), ["bin/", "parts/"])
        self.assertFalse((Fixtures.a / ".gitignore").exists())
        self.assertEqual(git(Fixtures.a, "status", "--short").split("\n")[:-1].count("?? bin/"), 0)

    @staticmethod
    def exclude_lines(dest):
        return [l for l in (Path(dest) / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("#")]

    def test_every_subset_build_excludes_bin_and_parts_too(self):
        for n, dest in Fixtures.subsets.items():
            with self.subTest(subset=n):
                self.assertEqual(self.exclude_lines(dest), ["bin/", "parts/"])

    def test_the_fixtures_commit_is_the_one_it_built_before_parts_was_excluded(self):
        # .git/info/exclude is not part of any commit: adding parts/ to it must not move the fixture's one commit
        self.assertEqual(git(Fixtures.a, "rev-parse", "HEAD").strip(), "d12b0aac5a683a846287ed4360e03a3bba53a964")

    def test_a_parts_folder_made_in_a_built_fixture_does_not_show_as_untracked(self):
        # the reports a session saves into parts/ must not change what a later part sees as untracked
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "fx"
            dest.mkdir()
            run_scaffold(dest)
            before = git(dest, "ls-files", "--others", "--exclude-standard").split()
            (dest / "parts").mkdir()
            (dest / "parts" / "part-1.md").write_text("SWEEP IN PARTS: 2 areas not read\n", encoding="utf-8")
            (dest / "parts" / "nested").mkdir()
            (dest / "parts" / "nested" / "part-2.md").write_text("x\n", encoding="utf-8")
            after = git(dest, "ls-files", "--others", "--exclude-standard").split()
            self.assertEqual(before, UNTRACKED)
            self.assertEqual(after, UNTRACKED)
            self.assertNotIn("parts/", git(dest, "status", "--short"))

    def test_a_folder_that_is_not_parts_still_shows_as_untracked(self):
        # the exclude names parts/ and bin/ only: a stray report folder under another name is still seen
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "fx"
            dest.mkdir()
            run_scaffold(dest)
            (dest / "reports").mkdir()
            (dest / "reports" / "part-1.md").write_text("x\n", encoding="utf-8")
            self.assertEqual(git(dest, "ls-files", "--others", "--exclude-standard").split(), sorted(UNTRACKED + ["reports/part-1.md"]))

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
        self.assertEqual(layout["tracked"], TRACKED)
        self.assertEqual(layout["after_whole_folder_skips"], AFTER_WHOLE)
        self.assertEqual(layout["skipped_whole"], {"web/vendor/": 40})
        self.assertEqual(layout["file_skips"], {"lock": 1, "binary": 4})
        self.assertEqual(layout["untracked"], UNTRACKED)
        self.assertEqual(layout["tracked"], len(Fixtures.tracked))
        self.assertEqual(layout["untracked"], Fixtures.untracked)
        self.assertEqual(layout["tracked"] - layout["skipped_whole"]["web/vendor/"] - sum(layout["file_skips"].values()), READABLE)

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

    def test_every_reference_code_in_the_tree_is_a_fact_or_a_decoy(self):
        known = {f["token"] for f in self.facts()} | {d["token"] for d in Fixtures.key["decoys"]}
        codes = set()
        for pattern in (r"\bTWY-\d{4}\b", r"ticket \d{4}\b", r"\bCHG\d{7}\b", r"#\d{5}\b", r"runbook section \d+\.\d+"):
            codes.update(re.findall(pattern, Fixtures.everything))
        self.assertEqual(codes, {t for t in known if not t.startswith(("/v3/", "twctl "))})

    def test_every_route_and_command_in_the_tree_is_a_fact_a_decoy_or_an_ordinary_one(self):
        known = {f["token"] for f in self.facts()} | {d["token"] for d in Fixtures.key["decoys"]}
        ordinary = ordinary_tokens(Fixtures.text, Fixtures.key)
        routes = set(re.findall(r"/v3/[a-z][a-z0-9_-]*/[a-z][a-z0-9_/-]*", Fixtures.everything))
        commands = set(re.findall(r"twctl [a-z][a-z0-9-]*", Fixtures.everything))
        self.assertEqual(routes | commands, {t for t in known if t.startswith(("/v3/", "twctl "))} | ordinary["route"] | ordinary["command"])

    def rules_ranks(self):
        names = sorted(p for p in Fixtures.tracked if p.startswith("rules/"))
        return sorted(names.index(f["path"]) + 1 for f in self.prefix("rules/"))

    def test_a_fact_sits_in_every_56_file_stretch_of_rules(self):
        # 12 facts over 610 files, first and last included: the gaps are 55 or 56, so the real guarantee is that
        # every run of 56 consecutive rules files holds a fact (not 50: a run of 50 can miss one)
        ranks = self.rules_ranks()
        self.assertEqual(len(set(ranks)), 12)
        for start in range(1, 610 - 56 + 2):
            self.assertTrue([r for r in ranks if start <= r < start + 56], (start, ranks))

    def test_a_run_of_55_rules_files_can_miss_every_fact_so_56_is_the_real_bound(self):
        ranks = self.rules_ranks()
        gaps = [b - a for a, b in zip(ranks, ranks[1:])]
        self.assertEqual(max(gaps), 56)
        start = ranks[gaps.index(56)] + 1     # the 55 files strictly between two facts 56 apart
        self.assertFalse([r for r in ranks if start <= r < start + 55])

    def test_rules_facts_include_the_first_and_the_last_file_and_are_evenly_spaced(self):
        ranks = self.rules_ranks()
        self.assertEqual(ranks[0], 1)
        self.assertEqual(ranks[-1], 610)
        gaps = {b - a for a, b in zip(ranks, ranks[1:])}
        self.assertTrue(max(gaps) - min(gaps) <= 1, gaps)
        self.assertEqual(gaps, {55, 56})
        self.assertEqual(self.prefix("rules/")[0]["path"].split("/")[1][:5], "r0001")
        self.assertEqual(self.prefix("rules/")[-1]["path"].split("/")[1][:5], "r0610")

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
        # and the final stretch of 45 files, the tail a 450-file part size leaves (945 = 450 + 450 + 45)
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
        self.assertEqual(count_under("rules/"), 610)


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
            run_scaffold(tmp, "--subset", "945")
            self.assertEqual(sorted(git(tmp, "ls-files").splitlines()),
                             sorted(Fixtures.eligible))
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scaffold(tmp, "--subset", "946", check=False)
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
            '`git` command is blocked: use `./bin/git` wherever you\'d type `git`, and tell any agent you brief to do the same. '
            'In the route inventory, give every route its full path on its own line, never grouped under a prefix. '
            'Give every CLI subcommand as `twctl <name>`. When a gotcha\'s source cites a ticket, incident, change number, '
            'or named event, quote that reference word for word next to the gotcha."')
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


THREE_SENTENCES = (
    "In the route inventory, give every route its full path on its own line, never grouped under a prefix. "
    "Give every CLI subcommand as `twctl <name>`. When a gotcha's source cites a ticket, incident, change number, "
    "or named event, quote that reference word for word next to the gotcha.")
REPLY_PROMPTS = [EXPENSIVE / ("reply-size-" + n) / "prompt.md" for n in ("150", "230", "320", "400", "450", "full")]


class BriefRequestsTest(unittest.TestCase):
    """The three requests (full route paths, `twctl <name>`, quote the reference) in the seven eval prompts."""

    def test_each_reply_size_prompt_holds_the_three_sentences_once_in_place(self):
        before = "tell any agent you brief to do the same. "
        after = " The user approved reading every file"
        for path in REPLY_PROMPTS:
            with self.subTest(prompt=path.parent.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text.count(THREE_SENTENCES), 1)
                self.assertEqual(text.count("never grouped under a prefix"), 1)
                self.assertIn(before + THREE_SENTENCES + after, text)
                self.assertLess(text.index("tell any agent you brief"), text.index("never grouped"))
                self.assertLess(text.index("quote that reference word for word"), text.index("The user approved reading every file"))

    def test_the_tail_mark_sentence_is_still_last_in_each_reply_size_prompt(self):
        for path in REPLY_PROMPTS:
            with self.subTest(prompt=path.parent.name):
                text = path.read_text(encoding="utf-8").rstrip("\n")
                self.assertTrue(text.endswith("Make the last line of your report exactly `TAIL-MARK-6620`.\""), text[-120:])
                self.assertGreater(text.rindex("TAIL-MARK-6620"), text.index("quote that reference word for word"))
                self.assertEqual(text.rindex("TAIL-MARK-6620"), text.index("exactly `TAIL-MARK-6620`") + len("exactly `"))

    def test_the_big_sweep_prompt_holds_the_three_sentences_once_inside_the_quoted_brief(self):
        text = (CASE / "prompt.md").read_text(encoding="utf-8")
        self.assertEqual(text.count(THREE_SENTENCES), 1)
        self.assertEqual(text.count("never grouped under a prefix"), 1)
        brief = text.split('Brief for the agent: "', 1)[1]
        self.assertTrue(brief.rstrip("\n").endswith(THREE_SENTENCES + '"'), brief[-200:])
        self.assertEqual(brief.count('"'), 1)   # the quote opens before it and closes once, after the sentences
        self.assertIn("tell any agent you brief to do the same. " + THREE_SENTENCES, brief)

    def test_none_of_the_seven_prompts_says_fxctl_and_all_say_twctl(self):
        for path in REPLY_PROMPTS + [CASE / "prompt.md"]:
            with self.subTest(prompt=str(path.relative_to(EXPENSIVE))):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("fxctl", text)
                self.assertEqual(text.count("`twctl <name>`"), 1)

    def test_the_sentences_add_no_cost_or_permission_wording(self):
        low = THREE_SENTENCES.lower()
        for word in ("cost", "price", "ask", "approve", "permission", "ok "):
            self.assertNotIn(word, low)

    def test_sync_check_catches_a_hand_edit_to_each_reply_size_prompt(self):
        for path in REPLY_PROMPTS:
            with self.subTest(prompt=path.parent.name), tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "evals-expensive"
                shutil.copytree(str(CASE), str(dest / "big-sweep-in-parts"), ignore=shutil.ignore_patterns("__pycache__"))
                for folder in EXPENSIVE.glob("reply-size-*"):
                    shutil.copytree(str(folder), str(dest / folder.name))
                shutil.copy(str(KEY_PATH), str(dest / "big-sweep-key.json"))
                shutil.copy(str(SYNC), str(dest / "sync_big_sweep.py"))
                run = lambda: subprocess.run([sys.executable, str(dest / "sync_big_sweep.py"), "--check"], capture_output=True, text=True)
                self.assertEqual(run().returncode, 0)
                target = dest / path.parent.name / "prompt.md"
                target.write_text(target.read_text(encoding="utf-8").replace("never grouped under a prefix", "grouped under a prefix"), encoding="utf-8")
                result = run()
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("differs: evals-expensive/%s/prompt.md" % path.parent.name, result.stdout)


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


def subset_texts(n):
    dest = Fixtures.subsets[n]
    return {p: b.decode("utf-8", errors="replace") for p, b in tree(dest).items() if p != "bin/git"}


class InventoryDensityTest(unittest.TestCase):
    """The fix gave the generated files a public inventory in the head-to-head's proportions: bands, not exact numbers."""

    def full(self):
        return measure(Fixtures.text, Fixtures.eligible, Fixtures.key)

    def test_the_full_fixture_sits_inside_every_density_band(self):
        m = self.full()
        self.assertEqual(m["files"], READABLE)
        self.assertEqual(band_failures(m), [], m)

    def test_the_reported_ratios_hold_1_40_functions_0_200_routes_and_0_299_commands_a_readable_file(self):
        m = self.full()
        self.assertEqual(round(m["functions"] / float(m["files"]), 2), 1.40, m)
        self.assertEqual(round(m["routes"] / float(m["files"]), 3), 0.200, m)
        self.assertEqual(round(m["commands"] / float(m["files"]), 3), 0.299, m)
        self.assertEqual((m["py"], m["functions"], m["routes"], m["commands"]), (929, 1323, 189, 283))

    def test_public_functions_per_readable_python_file_are_between_1_1_and_1_7(self):
        m = self.full()
        self.assertTrue(FUNCTIONS_BAND[0] <= m["functions"] / float(m["py"]) <= FUNCTIONS_BAND[1], m)

    def test_ordinary_routes_per_readable_file_are_between_0_15_and_0_25(self):
        m = self.full()
        self.assertTrue(ROUTES_BAND[0] <= m["routes"] / float(m["files"]) <= ROUTES_BAND[1], m)

    def test_ordinary_commands_per_readable_file_are_between_0_25_and_0_35(self):
        m = self.full()
        self.assertTrue(COMMANDS_BAND[0] <= m["commands"] / float(m["files"]) <= COMMANDS_BAND[1], m)

    def test_the_150_file_subset_has_at_least_1_1_public_functions_per_file(self):
        texts = subset_texts(150)
        readable = [p for p in texts if not p.startswith(".git/")]
        m = measure(texts, readable, Fixtures.key)
        self.assertEqual(m["files"], 150)
        self.assertEqual(band_failures(m, subset=True), [], m)

    def test_every_subset_has_public_functions_and_no_planted_only_inventory(self):
        for n in SUBSET_SIZES:
            with self.subTest(n=n):
                texts = subset_texts(n)
                m = measure(texts, list(texts), Fixtures.key)
                self.assertGreaterEqual(m["functions"] / float(m["py"]), SUBSET_FUNCTIONS_FLOOR, m)

    def test_every_code_folder_holds_public_functions(self):
        names = public_names({p: Fixtures.text[p] for p in Fixtures.eligible})
        for folder in CODE_FOLDERS:
            with self.subTest(folder=folder):
                self.assertTrue([n for p, n in names if p.startswith(folder)], folder)

    def test_public_functions_are_spread_unevenly_some_files_none_some_four_or_more(self):
        counts = [len(PUBLIC_DEF.findall(Fixtures.text[p])) for p in Fixtures.eligible if p.endswith(".py")]
        self.assertTrue(any(c == 0 for c in counts))
        self.assertTrue(any(c >= 4 for c in counts))
        self.assertGreater(len(set(counts)), 3)

    # -- each band can fail: mutate the generated tree and the bands report it --------------------

    def mutated(self, change):
        texts = {p: (change(p, t) if p.endswith(".py") else t) for p, t in Fixtures.text.items()}
        return band_failures(measure(texts, Fixtures.eligible, Fixtures.key))

    def test_mutation_making_every_public_function_private_trips_the_functions_low_band(self):
        fails = self.mutated(lambda p, t: re.sub(r"^def ([A-Za-z])", r"def _\1", t, flags=re.M))
        self.assertTrue([f for f in fails if f.startswith("functions low")], fails)

    def test_mutation_adding_two_public_functions_to_every_python_file_trips_the_functions_high_band(self):
        fails = self.mutated(lambda p, t: t + "\n\ndef extra_one(x):\n    return x\n\n\ndef extra_two(x):\n    return x\n")
        self.assertTrue([f for f in fails if f.startswith("functions high")], fails)

    def test_mutation_unrouting_every_ordinary_route_trips_the_routes_low_band(self):
        fails = self.mutated(lambda p, t: re.sub(r'^@route\(', "@routed(", t, flags=re.M))
        self.assertTrue([f for f in fails if f.startswith("routes low")], fails)

    def test_mutation_adding_routes_to_every_eighth_file_trips_the_routes_high_band(self):
        order = {p: i for i, p in enumerate(sorted(Fixtures.eligible))}
        fails = self.mutated(lambda p, t: t + '\n@route("/v3/mut/a/b%d")\ndef mut_b(request):\n    return 1\n' % order.get(p, 1)
                             if order.get(p, 1) % 8 == 0 else t)
        self.assertTrue([f for f in fails if f.startswith("routes high")], fails)

    def test_mutation_uncommanding_every_ordinary_command_trips_the_commands_low_band(self):
        fails = self.mutated(lambda p, t: re.sub(r'^@command\(', "@commanded(", t, flags=re.M))
        self.assertTrue([f for f in fails if f.startswith("commands low")], fails)

    def test_mutation_adding_commands_to_every_seventh_file_trips_the_commands_high_band(self):
        order = {p: i for i, p in enumerate(sorted(Fixtures.eligible))}
        fails = self.mutated(lambda p, t: t + '\n@command("twctl mut-c%d")\ndef mut_c(args):\n    return 0\n' % order.get(p, 1)
                             if order.get(p, 1) % 7 == 0 else t)
        self.assertTrue([f for f in fails if f.startswith("commands high")], fails)

    def test_mutation_of_the_counts_diluting_the_files_trips_the_low_bands(self):
        m = dict(self.full())
        m["files"] *= 2
        m["py"] *= 2
        fails = band_failures(m)
        self.assertEqual(sorted(f.split()[0] + " " + f.split()[1] for f in fails), ["commands low", "functions low", "routes low"])

    def test_mutation_stripping_the_150_subset_trips_its_floor(self):
        texts = {p: re.sub(r"^def ([A-Za-z])", r"def _\1", t, flags=re.M) if p.endswith(".py") else t
                 for p, t in subset_texts(150).items()}
        fails = band_failures(measure(texts, list(texts), Fixtures.key), subset=True)
        self.assertTrue(fails, fails)

    def test_the_bands_hold_for_the_numbers_the_fix_reported_and_fail_just_outside(self):
        base = {"files": 945, "py": 929, "functions": 1323, "routes": 189, "commands": 283}
        self.assertEqual(band_failures(base), [])
        self.assertTrue(band_failures(dict(base, functions=int(929 * 1.1) - 2)))
        self.assertTrue(band_failures(dict(base, functions=int(929 * 1.7) + 2)))
        self.assertTrue(band_failures(dict(base, routes=int(945 * 0.15) - 1)))
        self.assertTrue(band_failures(dict(base, routes=int(945 * 0.25) + 2)))
        self.assertTrue(band_failures(dict(base, commands=int(945 * 0.25) - 1)))
        self.assertTrue(band_failures(dict(base, commands=int(945 * 0.35) + 2)))


class OrdinaryInventoryRulesTest(unittest.TestCase):
    """The fix's rules for the ordinary routes, commands and public functions it added."""

    def ordinary(self):
        return ordinary_list(Fixtures.text, Fixtures.key)

    def test_ordinary_routes_and_commands_exist_and_have_the_shapes_of_their_kind(self):
        found = self.ordinary()
        self.assertTrue(found["route"] and found["command"])
        for _path, token in found["route"]:
            self.assertRegex(token, r"^/v3/[a-z]+/[a-z]+/[a-z]+$")
        for _path, token in found["command"]:
            self.assertRegex(token, r"^twctl [a-z][a-z0-9-]*$")

    def test_ordinary_routes_sit_in_api_web_views_or_the_late_rules_and_commands_in_cli_scripts_jobs_or_the_late_rules(self):
        found = self.ordinary()
        for path, token in found["route"]:
            with self.subTest(path=path, token=token):
                self.assertTrue(in_route_home(path), path)
        for path, token in found["command"]:
            with self.subTest(path=path, token=token):
                self.assertTrue(in_command_home(path), path)

    def test_rules_r0001_to_r0310_hold_no_ordinary_route_or_command(self):
        found = self.ordinary()
        early = [p for p, _t in found["route"] + found["command"] if p.startswith("rules/") and not late_rules(p)]
        self.assertEqual(early, [])

    def test_the_late_rules_hold_60_ordinary_routes_and_90_ordinary_commands_at_most_2_of_each_a_file(self):
        found = self.ordinary()
        for kind, total in (("route", LATE_RULES_ROUTES), ("command", LATE_RULES_COMMANDS)):
            per_file = {}
            for path, _t in found[kind]:
                if path.startswith("rules/"):
                    per_file[path] = per_file.get(path, 0) + 1
            with self.subTest(kind=kind):
                self.assertEqual(sum(per_file.values()), total)
                self.assertTrue(all(late_rules(p) for p in per_file), sorted(per_file)[:3])
                self.assertLessEqual(max(per_file.values()), LATE_RULES_CAP)

    def test_every_50_file_stretch_of_the_late_rules_holds_an_ordinary_route_and_an_ordinary_command(self):
        # measured, not promised by the brief: it is what lets each part of a sweep that reads a rules range report both
        found = self.ordinary()
        for kind in ("route", "command"):
            numbers = {int(p[7:11]) for p, _t in found[kind] if p.startswith("rules/")}
            for start in range(LATE_RULES_FROM, 610 - 50 + 2):
                with self.subTest(kind=kind, start=start):
                    self.assertTrue([n for n in numbers if start <= n < start + 50])

    def test_no_ordinary_route_or_command_sits_in_docs_vendor_untracked_lock_or_binary_files(self):
        found = self.ordinary()
        bad = [p for p, _t in found["route"] + found["command"]
               if p.startswith("docs/") or is_skipped(p) or p in UNTRACKED or p not in Fixtures.eligible]
        self.assertEqual(bad, [])

    def test_only_known_tokens_appear_in_files_outside_the_ordinary_homes(self):
        known = known_tokens(Fixtures.key)
        for path, text in Fixtures.text.items():
            if path in Fixtures.eligible and path.endswith(".py") and (path.startswith(ROUTE_HOMES + COMMAND_HOMES) or late_rules(path)):
                continue
            found = set(re.findall(r"/v3/[a-z][a-z0-9_-]*/[a-z][a-z0-9_/-]*", text)) | set(re.findall(r"twctl [a-z][a-z0-9-]*", text))
            with self.subTest(path=path):
                self.assertEqual(found - known, set())

    def test_docs_hold_no_route_and_no_command_planted_or_ordinary(self):
        for path in Fixtures.tracked:
            if path.startswith("docs/"):
                with self.subTest(path=path):
                    self.assertNotIn("/v3/", Fixtures.text[path])
                    self.assertNotIn("twctl", Fixtures.text[path])
                    self.assertIsNone(re.search(r"^@(route|command)\(", Fixtures.text[path], re.M))

    def test_every_ordinary_route_path_and_command_name_is_unique_in_the_tree(self):
        found = self.ordinary()
        for kind in ("route", "command"):
            tokens = [t for _p, t in found[kind]]
            self.assertEqual(len(tokens), len(set(tokens)), kind)
            for token in tokens:
                with self.subTest(token=token):
                    self.assertEqual(Fixtures.everything.count(token), 1)

    def test_no_ordinary_route_or_command_equals_contains_or_sits_inside_a_planted_or_decoy_token(self):
        known = known_tokens(Fixtures.key)
        found = self.ordinary()
        for _p, ordinary in found["route"] + found["command"]:
            for token in known:
                with self.subTest(ordinary=ordinary, token=token):
                    self.assertNotIn(token, ordinary)
                    self.assertNotIn(ordinary, token)

    def test_no_public_function_name_equals_contains_or_sits_inside_a_planted_or_decoy_token(self):
        known = known_tokens(Fixtures.key)
        for path, name in public_names(Fixtures.text):
            for token in known:
                with self.subTest(path=path, name=name, token=token):
                    self.assertNotIn(token, name)
                    self.assertNotIn(name, token)

    def test_a_public_function_name_is_defined_once_per_file(self):
        for path, text in Fixtures.text.items():
            if path.endswith(".py"):
                names = PUBLIC_DEF.findall(text)
                with self.subTest(path=path):
                    self.assertEqual(len(names), len(set(names)))

    def test_generated_function_bodies_use_return_and_no_line_starts_with_the_bare_keyword(self):
        word = "pa" + "ss"
        for path, text in Fixtures.text.items():
            if path.endswith(".py"):
                with self.subTest(path=path):
                    self.assertIsNone(re.search(r"^[ \t]*" + word + r"([ \t]|$)", text, re.M))

    def test_a_planted_fact_is_still_a_route_or_command_the_ordinary_ones_do_not_reuse(self):
        # the planted tokens stay decorated exactly once, apart from the ordinary ones
        found = self.ordinary()
        ordinary = {t for kind in found.values() for _p, t in kind}
        for f in Fixtures.key["facts"]:
            if f["kind"] != "gotcha":
                with self.subTest(fact=f["id"]):
                    self.assertNotIn(f["token"], ordinary)
                    rx = ROUTE_DECORATOR if f["kind"] == "route" else COMMAND_DECORATOR
                    self.assertEqual(rx.findall(Fixtures.text[f["path"]]).count(f["token"]), 1)


class WhatMustNotChangeTest(unittest.TestCase):
    """The fix changed what the files contain, never where they are or what is planted."""

    def test_the_33_facts_keep_their_ids_kinds_paths_and_tokens(self):
        got = [(f["id"], f["kind"], f["path"], f["token"]) for f in Fixtures.key["facts"]]
        self.assertEqual(got, GOLDEN_FACTS)

    def test_the_five_decoys_keep_their_ids_reasons_paths_and_tokens(self):
        got = [(d["id"], d["why"], d["path"], d["token"]) for d in Fixtures.key["decoys"]]
        self.assertEqual(got, GOLDEN_DECOYS)

    def test_each_planted_and_decoy_token_appears_exactly_once_in_the_whole_tree_and_in_its_file(self):
        for _id, _kind, path, token in GOLDEN_FACTS + GOLDEN_DECOYS:
            with self.subTest(token=token):
                self.assertEqual(Fixtures.everything.count(token), 1)
                self.assertEqual(Fixtures.text[path].count(token), 1)

    def test_a_decoy_sits_only_in_a_vendored_or_untracked_file_and_a_fact_in_neither(self):
        for _id, why, path, token in GOLDEN_DECOYS:
            self.assertTrue(path.startswith("web/vendor/") if why == "vendored" else path in UNTRACKED, path)
        for _id, _kind, path, token in GOLDEN_FACTS:
            self.assertFalse(is_skipped(path) or path in UNTRACKED, path)

    def test_the_layout_in_the_key_is_the_one_the_brief_gave(self):
        self.assertEqual(Fixtures.key["layout"], {"tracked": TRACKED, "after_whole_folder_skips": AFTER_WHOLE, "skipped_whole": {"web/vendor/": 40},
                                                  "file_skips": {"lock": 1, "binary": 4}, "untracked": UNTRACKED})

    def test_vendored_lock_and_binary_files_and_untracked_ones_hold_only_their_decoys(self):
        known = known_tokens(Fixtures.key)
        for path in [p for p in Fixtures.tracked if is_skipped(p)] + UNTRACKED:
            text = Fixtures.text[path]
            with self.subTest(path=path):
                self.assertEqual((set(re.findall(r"/v3/[a-z][a-z0-9_/-]*", text)) | set(re.findall(r"twctl [a-z][a-z0-9-]*", text))) - known, set())
                if not any(d[2] == path for d in GOLDEN_DECOYS):
                    self.assertIsNone(re.search(r"^@(route|command)\(", text, re.M))

    def test_the_150_subset_has_exactly_150_readable_files_and_its_python_compiles(self):
        texts = subset_texts(150)
        self.assertEqual(len([p for p in texts]), 150)
        for path, text in texts.items():
            if path.endswith(".py"):
                with self.subTest(path=path):
                    compile(text, path, "exec")

    def test_every_subset_file_is_between_30_and_120_lines(self):
        for n in SUBSET_SIZES:
            for path, text in subset_texts(n).items():
                if not path.startswith(("README", "CHANGELOG", "Makefile", "pyproject")):
                    with self.subTest(n=n, path=path):
                        self.assertTrue(30 <= len(text.splitlines()) <= 120, path)

    def test_the_emitted_key_equals_the_committed_key_with_the_same_golden_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "key.json"
            subprocess.run(["bash", str(SCAFFOLD), "--emit-key", str(target)], cwd=tmp, check=True, capture_output=True, text=True)
            emitted = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(emitted, Fixtures.key)
        self.assertEqual([(f["id"], f["kind"], f["path"], f["token"]) for f in emitted["facts"]], GOLDEN_FACTS)


class FactDistributionTest(unittest.TestCase):
    """What the growth must not move: the plan's table, read from the key and not from the golden tokens."""

    def kinds(self, prefix, direct=False):
        out = []
        for f in Fixtures.key["facts"]:
            if f["path"].startswith(prefix) and not (direct and "/" in f["path"][len(prefix):]):
                out.append(f["kind"])
        return sorted(out)

    def test_ids_run_f01_to_f33_in_path_order(self):
        facts = Fixtures.key["facts"]
        self.assertEqual([f["id"] for f in facts], ["f%02d" % i for i in range(1, 34)])
        self.assertEqual([f["path"] for f in facts], sorted(f["path"] for f in facts))

    def test_each_api_subfolder_holds_one_route_and_one_gotcha(self):
        for sub in ("accounts", "billing", "plazas", "trips"):
            with self.subTest(sub=sub):
                self.assertEqual(self.kinds("api/%s/" % sub), ["gotcha", "route"])

    def test_the_other_folders_hold_the_kinds_the_plan_gives(self):
        self.assertEqual(self.kinds("main.py"), ["gotcha"])
        self.assertEqual(self.kinds("api/app.py"), ["route"])
        self.assertEqual(self.kinds("cli/"), ["command", "command"])
        self.assertEqual(self.kinds("jobs/", direct=True), ["command"])
        self.assertEqual(self.kinds("jobs/nightly/"), ["gotcha"])
        self.assertEqual(self.kinds("scripts/"), ["command"])
        self.assertEqual(self.kinds("tests/"), ["gotcha"])
        self.assertEqual(self.kinds("web/views/"), ["route"])
        self.assertEqual(self.kinds("web/", direct=True), ["gotcha"])
        self.assertEqual(self.kinds("zones/"), ["command", "gotcha", "route"])

    def test_the_12_rules_facts_cycle_gotcha_route_command(self):
        facts = [f for f in Fixtures.key["facts"] if f["path"].startswith("rules/")]
        self.assertEqual([f["kind"] for f in facts], ["gotcha", "route", "command"] * 4)

    def test_the_three_zones_facts_are_the_4th_the_11th_and_the_last_file(self):
        zones = sorted(p for p in Fixtures.eligible if p.startswith("zones/"))
        got = [f["path"] for f in Fixtures.key["facts"] if f["path"].startswith("zones/")]
        self.assertEqual(got, [zones[3], zones[10], zones[19]])
        self.assertEqual(zones[19], sorted(Fixtures.eligible, key=lambda p: p.encode("utf-8"))[-1])

    def test_the_decoys_are_one_in_each_untracked_file_and_two_in_the_vendored_folder(self):
        decoys = Fixtures.key["decoys"]
        self.assertEqual(sorted(d["path"] for d in decoys if d["why"] == "untracked"), UNTRACKED)
        vendored = [d["path"] for d in decoys if d["why"] == "vendored"]
        self.assertEqual(len(vendored), 2)
        self.assertTrue(all(p.startswith("web/vendor/") for p in vendored))


class ReplySizeCopiesTest(unittest.TestCase):
    """The six reply-size scaffolds are byte copies of the big-sweep scaffold with one line changed."""

    SIZES = (("150", 150), ("230", 230), ("320", 320), ("400", 400), ("450", 450), ("full", None))

    def test_each_copy_differs_from_the_scaffold_in_line_14_only(self):
        main = SCAFFOLD.read_text(encoding="utf-8").split("\n")
        for suffix, n in self.SIZES:
            with self.subTest(copy=suffix):
                copy = (EXPENSIVE / ("reply-size-" + suffix) / "scaffold.sh").read_text(encoding="utf-8").split("\n")
                self.assertEqual(len(copy), len(main))
                diff = [i + 1 for i, (a, b) in enumerate(zip(main, copy)) if a != b]
                self.assertEqual(diff, [] if n is None else [14])
                self.assertEqual(copy[13], 'SUBSET=""' if n is None else 'SUBSET="%d"' % n)

    def test_sync_out_writes_the_same_copies_that_are_committed(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(SYNC), "--out", tmp], check=True, capture_output=True, text=True)
            for suffix, _n in self.SIZES:
                with self.subTest(copy=suffix):
                    name = "reply-size-%s/scaffold.sh" % suffix
                    self.assertEqual((Path(tmp) / name).read_bytes(), (EXPENSIVE / name).read_bytes())

    def test_sync_check_exits_zero_and_names_nothing(self):
        result = subprocess.run([sys.executable, str(SYNC), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("differs", result.stdout)

    def test_each_copy_builds_the_repo_its_name_says(self):
        for suffix, n in self.SIZES:
            with self.subTest(copy=suffix), tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp)
                subprocess.run(["bash", str(EXPENSIVE / ("reply-size-" + suffix) / "scaffold.sh")], cwd=str(dest),
                               check=True, capture_output=True, text=True)
                tracked = git(dest, "ls-files").splitlines()
                if n is None:
                    self.assertEqual(tracked, Fixtures.tracked)
                else:
                    self.assertEqual(tracked, git(Fixtures.subsets[n], "ls-files").splitlines())
                    self.assertEqual(len(tracked), n)


class FoundRuleTest(unittest.TestCase):
    """check_parts.py's found rule must not be fooled by an ordinary token."""

    @classmethod
    def setUpClass(cls):
        cls.rule = staticmethod(load_check_parts().token_found)

    def test_the_rule_finds_a_token_and_can_be_fooled_by_a_path_that_contains_it(self):
        # control: proves the rule is live and shows what a "contains" collision would cost
        self.assertTrue(self.rule("/v3/accounts/fleets/unlock", "see `/v3/accounts/fleets/unlock` here"))
        self.assertTrue(self.rule("/v3/accounts/fleets/unlock", "- /v3/accounts/fleets/unlock/extra"))
        self.assertTrue(self.rule("twctl hold-trailer", "run Twctl   hold-trailer now"))
        self.assertFalse(self.rule("TWY-1718", "TWY-17189"))

    def test_no_ordinary_route_command_or_function_name_counts_as_finding_a_planted_or_decoy_token(self):
        found = ordinary_list(Fixtures.text, Fixtures.key)
        samples = [t for _p, t in found["route"] + found["command"]] + [n for _p, n in public_names(Fixtures.text)]
        self.assertGreater(len(samples), 1000)
        known = sorted(known_tokens(Fixtures.key))
        blob = "\n".join("- `%s` (%s)" % (s, "api/x.py") for s in samples)
        for token in known:
            with self.subTest(token=token):
                self.assertFalse(self.rule(token, blob))
                for s in samples:
                    if token.lower() in s.lower() or s.lower() in token.lower():
                        self.fail("%r and %r overlap" % (s, token))

    def test_no_planted_or_decoy_token_is_found_anywhere_in_the_tree_outside_its_own_line(self):
        for token in sorted(known_tokens(Fixtures.key)):
            rest = "\n".join(line for text in Fixtures.text.values() for line in text.splitlines() if token not in line)
            with self.subTest(token=token):
                self.assertFalse(self.rule(token, rest))


if __name__ == "__main__":
    unittest.main()
