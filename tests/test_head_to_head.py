"""Free checks on the paid head-to-head's fixture, answer key, and graders.

The head-to-head (evals-expensive/) costs real money, so a fixture bug found
after a run is an expensive way to learn it. These tests build each fixture in
a temp folder (no model runs, nothing here starts a session) and check the
guarantees the comparison leans on: where each planted fact sits, that each
token appears once, that the skipped files hold no facts, and that the graders
and the key match what the scaffold produces.

Standard library only.
"""

import ast
import contextlib
import importlib.util
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
EXPENSIVE = ROOT / "evals-expensive"
H2H = EXPENSIVE / "investigate-head-to-head"
SMOKE = EXPENSIVE / "nesting-smoke"
KEY_PATH = EXPENSIVE / "head-to-head-key.json"

SKIP_CLASSES = {
    "lock file": lambda p: p.endswith(".lock"),
    "vendored folder": lambda p: p.startswith("vendor/"),
    "generated code": lambda p: p.startswith("generated/"),
    "data or fixture file": lambda p: p.startswith(("data/", "fixtures/")),
    "binary": lambda p: p.startswith("assets/"),
}
BIG_LINES = {1100, 1250, 1400, 1640, 1900, 2400}
UNTRACKED = "notes/untracked-scratch.md"


def is_skipped(path):
    return any(test(path) for test in SKIP_CLASSES.values())


def build(case, dest):
    subprocess.run(["bash", str(case / "scaffold.sh")], cwd=dest, check=True, capture_output=True, text=True)


def git(dest, *args):
    out = subprocess.run([str(Path(dest) / "bin" / "git"), *args], cwd=dest, check=True, capture_output=True, text=True)
    return out.stdout


def tree(dest):
    """{relative path: bytes} for every file outside .git."""
    out = {}
    for base, dirs, names in os.walk(dest):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            path = Path(base) / name
            out[str(path.relative_to(dest))] = path.read_bytes()
    return out


def load_sync_case():
    spec = importlib.util.spec_from_file_location("sync_case", EXPENSIVE / "sync_case.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shape_of(token, shapes=None):
    """Which reference shape a gotcha token has: a key of code_shapes, or 'named event'."""
    shapes = shapes or json.loads(KEY_PATH.read_text(encoding="utf-8"))["code_shapes"]
    for name, pattern in shapes.items():
        if re.fullmatch(pattern, token):
            return name
    if re.fullmatch(r"the [A-Z][a-z]+( [a-z]+)+", token):
        return "named event"
    return None


COMMON_WORDS = set((
    "a an the of to in on is are was were be been and or not no it its for with at by from than that this these those as so but if "
    "when after before only more most less never always one two three four five six nine twelve per see there here then them they "
    "we us our you your has have had do does did can could will would should must may might too very just also into over under "
    "past up down out off about what which who how why where while because since until once again still even each every any all "
    "both either neither such own same other another some many much few").split())


def sections(lines):
    return len(range(1, lines + 1, 750))


class Fixtures:
    """Built once for the whole module."""

    @classmethod
    def build(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.a, cls.b, cls.smoke = base / "a", base / "b", base / "smoke"
        for dest, case in ((cls.a, H2H), (cls.b, H2H), (cls.smoke, SMOKE)):
            dest.mkdir()
            build(case, dest)
        cls.key = json.loads(KEY_PATH.read_text(encoding="utf-8"))
        cls.files = tree(cls.a)
        cls.tracked = git(cls.a, "ls-files").splitlines()
        cls.text = {p: b.decode("utf-8", errors="replace") for p, b in cls.files.items() if not p.startswith("bin/")}


def setUpModule():
    Fixtures.build()


def tearDownModule():
    Fixtures.tmp.cleanup()


class CasesAreCompleteTest(unittest.TestCase):
    def test_both_cases_are_complete(self):
        for case in (H2H, SMOKE):
            with self.subTest(case=case.name):
                yaml = (case / "case.yaml").read_text(encoding="utf-8")
                self.assertIn(f"name: {case.name}\n", yaml, "case.yaml's name doesn't match its folder")
                self.assertRegex(yaml, r"scaffold_script:\s*scaffold\.sh")
                self.assertTrue(os.access(case / "scaffold.sh", os.X_OK), "scaffold.sh isn't executable")
                prompt = (case / "prompt.md").read_text(encoding="utf-8")
                self.assertRegex(prompt, r"(?m)^tags: \[[a-z-]+\]$")
                self.assertTrue(list((case / "graders").glob("*.md")), "no graders")

    def test_timeouts_are_inside_the_harness_limit(self):
        # The harness refuses to load a case over 3600 seconds ("execution.timeout_seconds: Number must be less than or equal to 3600").
        for case in (H2H, SMOKE):
            with self.subTest(case=case.name):
                head = (case / "prompt.md").read_text(encoding="utf-8").split("---")[1]
                seconds = int(re.search(r"^timeout_seconds: (\d+)$", head, re.M).group(1))
                self.assertLessEqual(seconds, 3600)

    def test_nesting_smoke_has_its_eight_graders(self):
        names = sorted(p.stem for p in (SMOKE / "graders").glob("*.md"))
        self.assertEqual(names, sorted(["reader-token", "reader-format", "no-fallback", "lead-dispatched", "reader-dispatched",
                                        "bash-reached", "report-kept", "trace-kept"]))
        bash = (SMOKE / "graders" / "bash-reached.md").read_text(encoding="utf-8")
        self.assertIn("type: tool_used\ntool: Bash\ninput_match: bin/git\n", bash)

    def test_no_routine_case_can_pick_these_up(self):
        for name in ("investigate-head-to-head", "nesting-smoke"):
            with self.subTest(case=name):
                self.assertFalse((ROOT / "evals" / name).exists(), "an expensive case sits under evals/")

    def test_scaffold_never_writes_the_key(self):
        self.assertNotIn("head-to-head-key.json", {Path(p).name for p in Fixtures.files})
        self.assertNotIn("head-to-head-key.json", {Path(p).name for p in tree(Fixtures.smoke)})


class FixtureShapeTest(unittest.TestCase):
    def test_git_wrapper_works_and_bin_stays_out_of_the_list(self):
        self.assertTrue(Fixtures.tracked)
        self.assertFalse([p for p in Fixtures.tracked if p.startswith("bin/")])
        self.assertTrue(os.access(Fixtures.a / "bin" / "git", os.X_OK))

    def test_eligible_count_and_skip_classes(self):
        eligible = [p for p in Fixtures.tracked if not is_skipped(p)]
        self.assertTrue(150 < len(eligible) < 500, len(eligible))
        self.assertTrue(170 <= len(eligible) <= 190, len(eligible))
        skipped = [p for p in Fixtures.tracked if is_skipped(p)]
        self.assertLessEqual(len(skipped), 20)
        for name, test in SKIP_CLASSES.items():
            with self.subTest(skip_class=name):
                self.assertTrue([p for p in skipped if test(p)], "no file of this class")
        folders = {p.split("/")[0] for p in eligible if "/" in p}
        self.assertGreaterEqual(len(folders), 12)

    def test_generated_and_vendored_files_say_so(self):
        for path in Fixtures.tracked:
            if path.startswith("generated/"):
                self.assertIn("DO NOT EDIT", Fixtures.text[path].splitlines()[0])
            if path.startswith("vendor/"):
                self.assertIn("Vendored", Fixtures.text[path].splitlines()[0])

    def test_binary_files_are_binary(self):
        for path in Fixtures.tracked:
            if path.startswith("assets/"):
                self.assertIn(b"\x00", Fixtures.files[path])

    def test_normal_files_are_30_to_150_lines_and_big_files_are_exact(self):
        big = {}
        for path in Fixtures.tracked:
            if is_skipped(path):
                continue
            n = len(Fixtures.text[path].splitlines())
            if n > 150:
                big[path] = n
            else:
                with self.subTest(path=path):
                    self.assertGreaterEqual(n, 30)
        self.assertEqual(sorted(big.values()), sorted(BIG_LINES))
        self.assertEqual(sum(sections(n) for n in big.values()), 16)

    def test_exactly_one_untracked_file(self):
        self.assertEqual(git(Fixtures.a, "ls-files", "--others", "--exclude-standard").split(), [UNTRACKED])
        self.assertNotIn(UNTRACKED, Fixtures.tracked)

    def test_two_builds_are_byte_identical(self):
        again = tree(Fixtures.b)
        self.assertEqual(sorted(again), sorted(Fixtures.files))
        for path, blob in Fixtures.files.items():
            if path != "bin/git":
                self.assertEqual(blob, again[path], path)
        self.assertEqual(git(Fixtures.a, "rev-parse", "HEAD"), git(Fixtures.b, "rev-parse", "HEAD"))

    def test_public_surface_is_at_most_600(self):
        count = 0
        for path in Fixtures.tracked:
            if path.endswith(".py") and not path.startswith(("tests/", "vendor/", "generated/")):
                for node in ast.walk(ast.parse(Fixtures.text[path])):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                        count += 1
        count += len(Fixtures.key["routes"]) + len(Fixtures.key["commands"])
        self.assertLessEqual(count, 600)

    def test_every_python_file_compiles(self):
        for path in Fixtures.tracked:
            if path.endswith(".py"):
                with self.subTest(path=path):
                    compile(Fixtures.text[path], path, "exec")

    def test_readme_and_docs_list_no_planted_route_or_code(self):
        docs = [p for p in Fixtures.tracked if p == "README.md" or p.startswith("docs/")]
        self.assertTrue(docs)
        secrets = Fixtures.key["routes"] + Fixtures.key["commands"] + Fixtures.key["codes"]
        for path in docs:
            for token in secrets:
                with self.subTest(path=path, token=token):
                    self.assertNotIn(token, Fixtures.text[path])

    def test_registration_styles_are_mixed(self):
        joined = "\n".join(Fixtures.text.values())
        for marker in ("@bp.route(", ".add_url_rule(", "ROUTE_TABLE = [", "@cli.command("):
            with self.subTest(style=marker):
                self.assertIn(marker, joined)


class PlantedFactsTest(unittest.TestCase):
    def facts(self, placement=None):
        return [f for f in Fixtures.key["facts"] if placement in (None, f["placement"])]

    def test_forty_eight_facts_split_as_planned(self):
        facts = self.facts()
        self.assertEqual(len(facts), 48)
        self.assertEqual(len({f["id"] for f in facts}), 48)
        self.assertEqual(len({f["token"] for f in facts}), 48)
        for placement in ("big-file-middle", "repo-middle"):
            with self.subTest(placement=placement):
                group = self.facts(placement)
                self.assertEqual(len(group), 24)
                self.assertEqual(len([f for f in group if f["kind"] in ("route", "command")]), 12)
                self.assertEqual(len([f for f in group if f["kind"] == "gotcha"]), 12)

    def test_token_shapes(self):
        for f in self.facts():
            with self.subTest(fact=f["id"]):
                if f["kind"] == "route":
                    self.assertRegex(f["token"], r"^/v2/\S+$")
                elif f["kind"] == "command":
                    self.assertRegex(f["token"], r"^fxctl [a-z][a-z0-9-]*$")
                else:
                    self.assertTrue(shape_of(f["token"]), f["token"])

    def test_each_token_is_at_its_line_and_appears_once_in_the_tree(self):
        everything = "\n".join(Fixtures.text.values())
        for f in self.facts():
            with self.subTest(fact=f["id"]):
                lines = Fixtures.text[f["path"]].splitlines()
                self.assertIn(f["token"], lines[f["line"] - 1])
                self.assertEqual(everything.count(f["token"]), 1)

    def test_big_file_facts_sit_in_the_middle_band(self):
        for f in self.facts("big-file-middle"):
            with self.subTest(fact=f["id"]):
                total = len(Fixtures.text[f["path"]].splitlines())
                self.assertIn(total, BIG_LINES)
                self.assertGreaterEqual(f["line"] / total, 0.35)
                self.assertLessEqual(f["line"] / total, 0.65)

    def test_a_fact_sits_in_the_overlap_band_of_the_1640_line_file(self):
        hits = [f for f in self.facts("big-file-middle")
                if len(Fixtures.text[f["path"]].splitlines()) == 1640 and 751 <= f["line"] <= 800]
        self.assertTrue(hits)

    def test_every_big_file_holds_four_facts(self):
        per_file = {}
        for f in self.facts("big-file-middle"):
            per_file.setdefault(f["path"], []).append(f["kind"])
        self.assertEqual(len(per_file), 6)
        for path, kinds in per_file.items():
            with self.subTest(path=path):
                self.assertEqual(sorted(kinds), ["command", "gotcha", "gotcha", "route"])

    def test_repo_facts_are_in_normal_files_ranked_in_the_middle(self):
        eligible = [p for p in Fixtures.tracked if not is_skipped(p)]
        for f in self.facts("repo-middle"):
            with self.subTest(fact=f["id"]):
                path = f["path"]
                self.assertIn(path, Fixtures.tracked)
                self.assertFalse(is_skipped(path))
                n = len(Fixtures.text[path].splitlines())
                self.assertTrue(30 <= n <= 150, n)
                for ranked in (Fixtures.tracked, eligible):
                    self.assertEqual(ranked, sorted(ranked))
                    rank = ranked.index(path) / (len(ranked) - 1)
                    self.assertTrue(0.35 <= rank <= 0.65, rank)
                    self.assertTrue(math.floor(0.35 * len(ranked)) <= ranked.index(path) <= math.ceil(0.65 * len(ranked)))

    def test_no_fact_is_in_a_skipped_or_untracked_file(self):
        for f in self.facts():
            with self.subTest(fact=f["id"]):
                self.assertIn(f["path"], Fixtures.tracked)
                self.assertFalse(is_skipped(f["path"]))
                self.assertNotEqual(f["path"], UNTRACKED)
        for path in [p for p in Fixtures.tracked if is_skipped(p)] + [UNTRACKED]:
            text = Fixtures.text[path]
            with self.subTest(path=path):
                self.assertIsNone(re.search(r"/v2/|fxctl [a-z]", text))
                for token in Fixtures.key["codes"]:
                    self.assertNotIn(token, text)
                for pattern in Fixtures.key["code_shapes"].values():
                    self.assertIsNone(re.search(pattern, text))

    def test_every_route_in_the_tree_is_in_the_key_and_every_decoy_exists(self):
        key = Fixtures.key
        found = set()
        for text in Fixtures.text.values():
            found.update(m.rstrip(".,") for m in re.findall(r"/v2/[A-Za-z0-9_<>/.-]+", text))
        decoys = {d["token"] for d in key["decoys"]}
        self.assertEqual(found, set(key["routes"]) | decoys)
        self.assertFalse(set(key["routes"]) & decoys, "a decoy is also listed as live")
        self.assertEqual(len(key["decoys"]), 6)
        self.assertEqual(sorted(d["kind"] for d in key["decoys"]), ["commented-out"] * 3 + ["documented-removed"] * 3)
        for d in key["decoys"]:
            with self.subTest(decoy=d["id"]):
                self.assertIn(d["token"], Fixtures.text[d["path"]].splitlines()[d["line"] - 1])
        for d in key["decoys"]:
            if d["kind"] == "commented-out":
                self.assertTrue(Fixtures.text[d["path"]].splitlines()[d["line"] - 1].lstrip().startswith("#"))

    def test_commands_and_codes_in_the_tree_are_all_in_the_key(self):
        everything = "\n".join(Fixtures.text.values())
        self.assertEqual(set(re.findall(r"fxctl [a-z][a-z0-9-]*", everything)), set(Fixtures.key["commands"]))
        for name, pattern in Fixtures.key["code_shapes"].items():
            with self.subTest(shape=name):
                found = re.findall(pattern, everything)
                self.assertTrue(found)
                self.assertLessEqual(set(found), set(Fixtures.key["codes"]))
        for f in self.facts():
            self.assertIn(f["token"], Fixtures.key["routes"] + Fixtures.key["commands"] + Fixtures.key["codes"])

    def test_a_planted_token_is_not_a_prefix_of_another_string(self):
        pool = Fixtures.key["routes"] + [d["token"] for d in Fixtures.key["decoys"]] + Fixtures.key["commands"]
        for a in pool:
            for b in pool:
                if a != b:
                    self.assertNotIn(a, b)


class GradersAndKeyTest(unittest.TestCase):
    def test_sync_case_writes_exactly_what_is_committed(self):
        module = load_sync_case()
        expected = module.expected()
        committed = {str(p.relative_to(EXPENSIVE)): p.read_text(encoding="utf-8")
                     for p in (H2H / "graders").glob("*.md")}
        committed["head-to-head-key.json"] = KEY_PATH.read_text(encoding="utf-8")
        self.assertEqual(sorted(committed), sorted(expected), "stale or missing files; run evals-expensive/sync_case.py")
        for rel, text in expected.items():
            with self.subTest(file=rel):
                self.assertEqual(committed[rel], text)

    def test_the_committed_key_is_what_the_scaffold_emits(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "key.json"
            subprocess.run(["bash", str(H2H / "scaffold.sh"), "--emit-key", str(out)], check=True, cwd=tmp)
            self.assertEqual(out.read_text(encoding="utf-8"), KEY_PATH.read_text(encoding="utf-8"))
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["key.json"], "emit-key built something")

    def test_fact_graders_match_their_token_as_a_regex(self):
        for f in Fixtures.key["facts"]:
            with self.subTest(fact=f["id"]):
                text = (H2H / "graders" / ("fact-%s.md" % f["id"])).read_text(encoding="utf-8")
                m = re.search(r"^pattern: (\".*\")$", text, re.M)
                self.assertIsNotNone(m)
                pattern = json.loads(m.group(1))
                self.assertIsNotNone(re.search(pattern, "x " + f["token"] + " y"))
                self.assertIn("type: regex\ntarget: last_message\n", text)
                self.assertIn("match: contains\n", text)
                self.assertIn("flags: i\n", text)

    def test_control_graders_have_the_exact_patterns(self):
        want = {
            "control-report-complete": ("last_message", "END-OF-REPORT"),
            "control-new-roster": ("trace", "the-foundry:file-reader"),
            "control-new-area-leads": ("last_message", "full sweep, ([2-9]|[1-9][0-9]+) area leads"),
            "control-new-no-fallback": ("last_message", "NOT A PER-FILE READ"),
            "control-new-untracked": ("last_message", "notes/untracked-scratch"),
        }
        for name, (target, pattern) in want.items():
            with self.subTest(grader=name):
                text = (H2H / "graders" / (name + ".md")).read_text(encoding="utf-8")
                self.assertIn("target: %s\n" % target, text)
                self.assertIn("pattern: %s\n" % json.dumps(pattern), text)
        no_fallback = (H2H / "graders" / "control-new-no-fallback.md").read_text(encoding="utf-8")
        self.assertIn("match: not_contains", no_fallback)
        keep = (H2H / "graders" / "keep-report.md").read_text(encoding="utf-8")
        self.assertIn("type: llm\nfocus: last_message\n", keep)

    def test_the_area_lead_control_matches_the_mode_line(self):
        pattern = re.compile(r"full sweep, ([2-9]|[1-9][0-9]+) area leads")
        agent = (ROOT / "agents" / "investigate.md").read_text(encoding="utf-8")
        self.assertIn("Mode: full sweep, <N> area leads", agent)
        self.assertTrue(pattern.search("Mode: full sweep, 3 area leads"))
        self.assertTrue(pattern.search("Mode: full sweep, 2 area leads"))
        self.assertIsNone(pattern.search("Mode: full sweep, no area leads"))
        self.assertIsNone(pattern.search("Mode: full sweep, 1 area leads"))
        self.assertTrue(pattern.search("Mode: full sweep, 13 area leads"))
        self.assertTrue(pattern.search("Mode: full sweep, 100 area leads"))
        self.assertIsNone(pattern.search("Mode: full sweep, 0 area leads"))

    def test_the_cases_name_real_agents(self):
        for path in (H2H / "prompt.md", SMOKE / "prompt.md"):
            for ref in re.findall(r"the-foundry:([a-z][\w-]*)", path.read_text(encoding="utf-8")):
                self.assertTrue((ROOT / "agents" / f"{ref}.md").exists(), ref)


class GotchaReferenceTest(unittest.TestCase):
    """One search must not find every gotcha, or the comparison measures grep rather than reading."""

    def gotchas(self):
        return [f for f in Fixtures.key["facts"] if f["kind"] == "gotcha"]

    def comment_lines(self):
        out = []
        for f in self.gotchas():
            line = Fixtures.text[f["path"]].splitlines()[f["line"] - 1]
            self.assertTrue(line.startswith("# "), line)
            out.append(line[2:])
        return out

    def test_there_are_24_references_in_at_least_six_shapes_with_at_most_four_each(self):
        self.assertEqual(len(self.gotchas()), 24)
        counts = {}
        for f in self.gotchas():
            counts[shape_of(f["token"])] = counts.get(shape_of(f["token"]), 0) + 1
        self.assertNotIn(None, counts)
        self.assertGreaterEqual(len(counts), 6, counts)
        for shape, n in counts.items():
            with self.subTest(shape=shape):
                self.assertLessEqual(n, 4)

    def test_no_single_shape_regex_finds_more_than_four_of_the_24(self):
        tokens = [f["token"] for f in self.gotchas()]
        everything = "\n".join(Fixtures.text.values())
        for name, pattern in Fixtures.key["code_shapes"].items():
            with self.subTest(shape=name):
                self.assertLessEqual(len([t for t in tokens if re.search(pattern, t)]), 4)
                self.assertLessEqual(len(re.findall(pattern, everything)), 4)

    def test_no_marker_word_is_shared_across_the_comments(self):
        lines = self.comment_lines()
        counts = {}
        for line in lines:
            for word in set(re.findall(r"[a-z']+", line.lower())):
                counts[word] = counts.get(word, 0) + 1
        for word, n in sorted(counts.items()):
            if word not in COMMON_WORDS:
                with self.subTest(word=word):
                    self.assertLessEqual(n, 6, "%r is in %d of the 24 gotcha comments" % (word, n))

    def test_no_route_token_holds_a_path_parameter(self):
        for token in Fixtures.key["routes"] + [d["token"] for d in Fixtures.key["decoys"]]:
            with self.subTest(token=token):
                self.assertIsNone(re.search(r"[<>{}:*?]", token))
        for f in Fixtures.key["facts"]:
            if f["kind"] == "route":
                self.assertRegex(f["token"], r"^/v2/[a-z]+/[a-z]+/[a-z-]+$")

    def test_the_agent_template_covers_the_shapes_the_prompt_names(self):
        prompt = (H2H / "prompt.md").read_text(encoding="utf-8")
        reader = (ROOT / "agents" / "file-reader.md").read_text(encoding="utf-8")
        self.assertIn("a ticket, incident, change number, or named event", prompt)
        self.assertIn("quoting any ticket, incident, change number, or named event the file cites", reader)
        self.assertNotIn("incident code", prompt)


class AdversarialControlTest(unittest.TestCase):
    """Control graders that could fire, or stay silent, for the wrong reason."""

    def test_area_lead_control_matches_every_lead_count_a_run_could_report(self):
        # The fixture has 13 eligible top-level folders, and an agent that makes one lead per folder reports 13.
        pattern = re.compile(r"full sweep, ([2-9]|[1-9][0-9]+) area leads")
        folders = {p.split("/")[0] for p in Fixtures.tracked if "/" in p and not is_skipped(p)}
        counts = sorted(set(range(2, 21)) | {len(folders)})
        for n in counts:
            with self.subTest(leads=n):
                self.assertTrue(pattern.search("Mode: full sweep, %d area leads" % n),
                                "control-new-area-leads misses a run with %d area leads" % n)

    def test_control_strings_are_not_in_the_prompt_or_the_fixture(self):
        # A baseline run's trace or report would match a control if the brief or the repo said the word itself.
        prompt = (H2H / "prompt.md").read_text(encoding="utf-8")
        words = ["file-reader", "full sweep", "area lead", "NOT A PER-FILE READ", "untracked-scratch"]
        for word in words:
            with self.subTest(where="prompt", word=word):
                self.assertNotIn(word.lower(), prompt.lower())
        for path, text in Fixtures.text.items():
            if path == UNTRACKED:
                continue
            for word in words + ["END-OF-REPORT"]:
                with self.subTest(where=path, word=word):
                    self.assertNotIn(word.lower(), text.lower())
                    self.assertNotIn(word.lower(), path.lower())

    def test_the_untracked_file_is_not_named_in_any_tracked_file(self):
        for path in Fixtures.tracked:
            with self.subTest(path=path):
                self.assertNotIn("untracked-scratch", Fixtures.text[path])
                self.assertNotIn("notes/", Fixtures.text[path])

    def test_both_prompts_allow_agent(self):
        for case in (H2H, SMOKE):
            with self.subTest(case=case.name):
                head = (case / "prompt.md").read_text(encoding="utf-8").split("---")[1]
                tools = re.search(r"^allowed_tools: \[(.*)\]$", head, re.M).group(1).split(", ")
                self.assertIn("Agent", tools)
                self.assertIn("Bash", tools, "nested agents keep Bash only if the session grants it")
                self.assertIn("runs: 1", head)


class AdversarialLeakTest(unittest.TestCase):
    def secrets(self):
        key = Fixtures.key
        return [f["token"] for f in key["facts"]] + [d["token"] for d in key["decoys"]]

    def test_no_token_is_in_a_file_name_or_in_git_metadata(self):
        meta = git(Fixtures.a, "log", "--all", "--format=%H%n%an%n%ae%n%cn%n%ce%n%s%n%b%n%d")
        meta += git(Fixtures.a, "ls-files") + git(Fixtures.a, "branch", "-a") + git(Fixtures.a, "tag")
        meta += (Fixtures.a / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        meta += (Fixtures.a / ".git" / "config").read_text(encoding="utf-8")
        meta += Fixtures.files["bin/git"].decode("utf-8")
        for token in self.secrets():
            with self.subTest(token=token):
                self.assertNotIn(token, meta)
        self.assertNotRegex(meta, r"/v2/|fxctl [a-z]")
        for pattern in Fixtures.key["code_shapes"].values():
            self.assertNotRegex(meta, pattern)

    def test_no_token_is_in_the_prompts(self):
        for case in (H2H, SMOKE):
            text = (case / "prompt.md").read_text(encoding="utf-8")
            for token in self.secrets() + ["NEST-5519"]:
                with self.subTest(case=case.name, token=token):
                    self.assertNotIn(token, text)

    def test_the_fixture_never_names_the_comparison_or_its_answers(self):
        words = ["planted", "decoy", "grader", "evals-expensive", "head-to-head", "sync_case", "answer key", "scaffold"]
        for path, text in Fixtures.text.items():
            for word in words:
                with self.subTest(path=path, word=word):
                    self.assertNotIn(word, text.lower())
                    self.assertNotIn(word, path.lower())

    def test_nothing_on_disk_is_hidden_except_bin_and_the_untracked_file(self):
        on_disk = set(Fixtures.files)
        listed = set(Fixtures.tracked) | {UNTRACKED}
        self.assertEqual(on_disk - listed, {"bin/git"})
        exclude = [l for l in (Fixtures.a / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.startswith("#")]
        self.assertEqual(exclude, ["bin/"])
        self.assertFalse((Fixtures.a / ".gitignore").exists())

    def test_every_listed_path_is_plain_ascii(self):
        for path in Fixtures.tracked + [UNTRACKED]:
            with self.subTest(path=path):
                path.encode("ascii")
                self.assertEqual(path, path.strip())


class AdversarialTokenTest(unittest.TestCase):
    """The scoring is a plain contains check, so a token inside a longer string is a false hit waiting to happen."""

    def tokens(self):
        return [f["token"] for f in Fixtures.key["facts"]]

    def test_every_code_is_unique_and_none_is_a_prefix_of_another(self):
        codes = Fixtures.key["codes"]
        self.assertEqual(len(codes), len(set(codes)))
        for a in codes:
            for b in codes:
                if a != b:
                    self.assertFalse(b.startswith(a), (a, b))

    def test_no_token_is_inside_a_longer_word_or_path(self):
        everything = "\n".join(Fixtures.text.values())
        for token in self.tokens():
            for m in re.finditer(re.escape(token), everything):
                before = everything[m.start() - 1] if m.start() else " "
                after = everything[m.end()] if m.end() < len(everything) else " "
                with self.subTest(token=token):
                    self.assertIsNone(re.match(r"[A-Za-z0-9_-]", before), repr(before))
                    self.assertIsNone(re.match(r"[A-Za-z0-9_/<-]", after), repr(after))

    def test_a_code_digit_string_is_not_reused_as_a_number(self):
        everything = "\n".join(Fixtures.text.values())
        for f in Fixtures.key["facts"]:
            if f["kind"] == "gotcha":
                with self.subTest(token=f["token"]):
                    run = re.search(r"\d{4,}", f["token"])
                    if run:
                        self.assertEqual(len(re.findall(r"(?<!\d)%s(?!\d)" % run.group(0), everything)), 1)

    def test_no_token_is_a_prefix_of_another_token_of_a_different_kind(self):
        tokens = self.tokens() + [d["token"] for d in Fixtures.key["decoys"]]
        for a in tokens:
            for b in tokens:
                if a != b:
                    self.assertFalse(b.startswith(a) or a in b, (a, b))


class AdversarialPlacementTest(unittest.TestCase):
    """Bands hold when a counter is off by one, or when the list an agent sees is a little different."""

    def lists(self):
        tracked = Fixtures.tracked
        eligible = [p for p in tracked if not is_skipped(p)]
        yield "tracked", tracked
        yield "tracked+untracked", sorted(tracked + [UNTRACKED])
        yield "eligible", eligible
        yield "eligible+untracked", sorted(eligible + [UNTRACKED])

    def test_repo_ranks_hold_in_every_list_an_agent_might_build(self):
        for f in Fixtures.key["facts"]:
            if f["placement"] != "repo-middle":
                continue
            for label, ranked in self.lists():
                with self.subTest(fact=f["id"], list=label):
                    rank = ranked.index(f["path"]) / (len(ranked) - 1)
                    self.assertTrue(0.35 <= rank <= 0.65, rank)

    def test_big_file_lines_hold_with_off_by_one_counts(self):
        for f in Fixtures.key["facts"]:
            if f["placement"] != "big-file-middle":
                continue
            total = len(Fixtures.text[f["path"]].splitlines())
            for line in (f["line"] - 1, f["line"], f["line"] + 1):
                for n in (total, total + 1):
                    with self.subTest(fact=f["id"], line=line, total=n):
                        self.assertTrue(0.35 <= line / n <= 0.65)

    def test_big_files_end_with_a_newline_so_the_line_count_is_unambiguous(self):
        for path, blob in Fixtures.files.items():
            if any(len(blob.splitlines()) == n for n in BIG_LINES):
                with self.subTest(path=path):
                    self.assertTrue(blob.endswith(b"\n"))
                    self.assertEqual(blob.count(b"\n"), len(blob.splitlines()))

    def test_big_file_facts_are_not_on_a_section_seam_of_a_different_reader(self):
        # Sections start at 1, 751, 1501, ... (about 800 lines each). A fact inside the overlap is read twice; elsewhere once.
        for f in Fixtures.key["facts"]:
            if f["placement"] == "big-file-middle":
                total = len(Fixtures.text[f["path"]].splitlines())
                starts = list(range(1, total + 1, 750))
                owners = [s for s in starts if s <= f["line"] <= min(s + 799, total)]
                with self.subTest(fact=f["id"]):
                    self.assertTrue(owners)

    def test_ascii_sort_is_git_order(self):
        order = git(Fixtures.a, "ls-files").splitlines()
        self.assertEqual(order, sorted(order, key=lambda p: p.encode("utf-8")))


class AdversarialBuildTest(unittest.TestCase):
    """Builds in a different place, locale, home, and a bare environment."""

    def build_with(self, env_extra, cwd_name="elsewhere", bare=False, gpg=""):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest = base / cwd_name
            dest.mkdir()
            home = base / "home"
            home.mkdir()
            (home / ".gitconfig").write_text("[core]\n\tautocrlf = true\n\twhitespace = trailing-space\n"
                                              + gpg + "[init]\n\tdefaultBranch = trunk\n"
                                              "[user]\n\tname = Someone Else\n\temail = else@example.org\n", encoding="utf-8")
            if bare:
                env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(home)}
            else:
                keep = ("PATH", "LANG", "LC_ALL", "TMPDIR", "TZ", "USER", "SHELL")
                env = {k: v for k, v in os.environ.items() if k in keep}
                env["HOME"] = str(home)
            env.update(env_extra)
            subprocess.run([str(H2H / "scaffold.sh")], cwd=dest, env=env, check=True, capture_output=True, text=True)
            files = tree(dest)
            head = subprocess.run([str(dest / "bin" / "git"), "rev-parse", "HEAD"], cwd=dest, env=env,
                                  check=True, capture_output=True, text=True).stdout
            return files, head

    def assert_same_as_baseline(self, files, head):
        self.assertEqual(sorted(files), sorted(Fixtures.files))
        for path, blob in Fixtures.files.items():
            if path != "bin/git":
                self.assertEqual(blob, files[path], path)
        self.assertEqual(head, git(Fixtures.a, "rev-parse", "HEAD"))

    def test_a_different_tmpdir_locale_timezone_and_git_config_builds_the_same_tree(self):
        with tempfile.TemporaryDirectory() as other_tmp:
            files, head = self.build_with({"TMPDIR": other_tmp, "LC_ALL": "tr_TR.UTF-8", "LANG": "tr_TR.UTF-8",
                                           "TZ": "Pacific/Kiritimati", "PYTHONHASHSEED": "12345"},
                                          cwd_name="a b")
        self.assert_same_as_baseline(files, head)

    def test_a_c_locale_and_bare_environment_builds_the_same_tree(self):
        files, head = self.build_with({"LC_ALL": "C", "LANG": "C"}, cwd_name="x", bare=True)
        self.assert_same_as_baseline(files, head)

    def test_a_user_who_signs_every_commit_can_still_build_it(self):
        # A global commit.gpgsign=true makes the scaffold's own commit fail (exit 128), so the case can't even start.
        files, head = self.build_with({}, gpg="[commit]\n\tgpgsign = true\n")
        self.assert_same_as_baseline(files, head)

    def test_the_built_tree_does_not_depend_on_the_hash_seed(self):
        files, head = self.build_with({"PYTHONHASHSEED": "random"})
        self.assert_same_as_baseline(files, head)


class ScannerTextTest(unittest.TestCase):
    """The directory scanner reads tracked files, and these generate text the plugin ships through a script."""

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

    def test_generated_text_holds_no_scanner_trigger(self):
        smoke = {p: b.decode("utf-8", errors="replace") for p, b in tree(Fixtures.smoke).items() if not p.startswith("bin/")}
        for where, texts in (("head-to-head fixture", Fixtures.text), ("smoke fixture", smoke)):
            for path, text in texts.items():
                text = text.replace(chr(92), "")
                for pattern in self.patterns():
                    with self.subTest(fixture=where, path=path):
                        self.assertIsNone(pattern.search(text))

    def test_the_case_files_hold_no_scanner_trigger(self):
        files = [p for p in EXPENSIVE.rglob("*") if p.is_file() and "results" not in p.parts and p.suffix != ".pyc"]
        self.assertTrue(files)
        for path in files:
            text = path.read_text(encoding="utf-8").replace(chr(92), "")
            for pattern in self.patterns():
                with self.subTest(path=str(path.relative_to(ROOT))):
                    self.assertIsNone(pattern.search(text))


class NestingSmokeFixtureTest(unittest.TestCase):
    def test_token_is_only_in_the_deep_file(self):
        files = {p: b.decode("utf-8", errors="replace") for p, b in tree(Fixtures.smoke).items() if not p.startswith("bin/")}
        holders = [p for p, text in files.items() if "NEST-5519" in text]
        self.assertEqual(holders, ["deep/only_here.py"])
        self.assertEqual(files["deep/only_here.py"].count("NEST-5519"), 1)

    def test_it_is_small_and_git_works(self):
        tracked = git(Fixtures.smoke, "ls-files").split()
        self.assertTrue(5 <= len(tracked) <= 8, tracked)
        self.assertFalse([p for p in tracked if p.startswith("bin/")])
        self.assertEqual(git(Fixtures.smoke, "status", "--short").strip(), "")


class CompareTest(unittest.TestCase):
    """The scorer decides whether the release happens, so every clause, boundary and exit code is pinned here.

    All inputs are synthetic aggregate-result.json files shaped like a saved
    result (cases[].arms.with[], graders[].evidence, costUsd, judgeCostUsd,
    durationSeconds, error, skippedPaidGraders). Saved results are untracked, so
    no test reads one. No case is run and no session is started.
    """

    MARKERS = "commented removed disabled dead deprecated inactive retired".split()

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("compare", EXPENSIVE / "compare.py")
        cls.compare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.compare)
        cls.sync = load_sync_case()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # helpers

    def facts(self):
        return Fixtures.key["facts"]

    def report(self, found=48, extra=(), end=True):
        """A report holding the first `found` planted tokens, then any extra lines."""
        lines = ["# Codebase report"] + ["- %s" % f["token"] for f in self.facts()[:found]] + list(extra)
        if end:
            lines.append("END-OF-REPORT")
        return "\n".join(lines) + "\n"

    def run_of(self, text=None, roster=True, leads=True, fallback=True, untracked=True, error=None,
               skipped=False, evidence=True, cost=1.0, judge=0.25, seconds=100, flip=(), drop=()):
        """One run as the harness saves it. `flip` names fact graders that disagree with the text."""
        text = self.report() if text is None else text
        graders = []
        for f in self.facts():
            name = "fact-" + f["id"]
            if name in drop:
                continue
            graders.append({"name": name, "passed": self.sync_found(f["token"], text) != (f["id"] in flip)})
        for name, ok in (("control-report-complete", "END-OF-REPORT" in text), ("control-new-roster", roster),
                         ("control-new-area-leads", leads), ("control-new-no-fallback", fallback),
                         ("control-new-untracked", untracked)):
            graders.append({"name": name, "passed": ok})
        keep = {"name": "keep-report", "passed": True}
        if evidence is True:
            keep["evidence"] = text
        elif evidence is not None:
            keep["evidence"] = evidence
        graders.append(keep)
        return {"score": 1, "passed": True, "turns": 9, "costUsd": cost, "judgeCostUsd": judge,
                "durationSeconds": seconds, "error": error, "skippedPaidGraders": skipped, "graders": graders}

    def sync_found(self, token, text):
        """What the fact-* grader built by sync_case.py finds, under Python's engine."""
        return re.search(self.sync.fact_pattern(token), text, re.I | re.A) is not None

    def write(self, runs):
        CompareTest.n += 1
        path = Path(self.tmp.name) / ("result-%d.json" % CompareTest.n)
        doc = {"schemaVersion": 1, "cases": [{"name": "investigate-head-to-head", "arms": {"with": runs}}]}
        path.write_text(json.dumps(doc), encoding="utf-8")
        return str(path)

    def go(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.compare.main(list(argv))
        return code, out.getvalue()

    def versus(self, new, base, split=False):
        """Run the bar. `new` and `base` are lists of run dicts; split puts each run in its own file."""
        key = str(KEY_PATH)
        if split:
            new_files = [self.write([r]) for r in new]
            base_files = [self.write([r]) for r in base]
        else:
            new_files, base_files = [self.write(new)], [self.write(base)]
        return self.go("--key", key, "--new", *new_files, "--baseline", *base_files)

    def news(self, found, count=3, **kw):
        return [self.run_of(self.report(found), **kw) for _ in range(count)]

    def bases(self, found, count=3, **kw):
        kw.setdefault("roster", False)
        return [self.run_of(self.report(found), **kw) for _ in range(count)]

    def clause(self, out, number):
        m = re.search(r"^clause %d .*: (PASS|FAIL)$" % number, out, re.M)
        self.assertIsNotNone(m, out)
        return m.group(1)

    def cant_score(self, out, why):
        self.assertRegex(out, r"(?m)^CAN'T SCORE: .*%s" % re.escape(why))
        self.assertNotIn("BAR MET", out)
        self.assertNotIn("BAR MISSED", out)

    # the bar: each clause failing alone

    def test_everything_clear_is_bar_met(self):
        code, out = self.versus(self.news(47), self.bases(36))
        self.assertEqual(code, 0, out)
        self.assertIn("BAR MET", out)
        self.assertEqual([self.clause(out, i) for i in (1, 2, 3)], ["PASS"] * 3)

    def test_only_the_found_clause_fails(self):
        code, out = self.versus(self.news(42), self.bases(36))
        self.assertEqual(code, 1, out)
        self.assertIn("BAR MISSED", out)
        self.assertEqual([self.clause(out, i) for i in (1, 2, 3)], ["FAIL", "PASS", "PASS"])

    def test_only_the_missed_clause_fails(self):
        code, out = self.versus(self.news(44), self.bases(47))
        self.assertEqual(code, 1, out)
        self.assertEqual([self.clause(out, i) for i in (1, 2, 3)], ["PASS", "FAIL", "PASS"])

    def test_only_the_made_up_clause_fails(self):
        fake = ["- a made up call /v2/billing/charges/teleport"]
        new = [self.run_of(self.report(48, extra=fake)) for _ in range(3)]
        code, out = self.versus(new, self.bases(40))
        self.assertEqual(code, 1, out)
        self.assertEqual([self.clause(out, i) for i in (1, 2, 3)], ["PASS", "PASS", "FAIL"])

    # the bar: each boundary passing

    def test_exactly_ninety_percent_found_passes(self):
        # 43, 43, 43, 43, 44 averages 43.2 of 48, exactly 90%
        new = [self.run_of(self.report(n)) for n in (43, 43, 43, 43, 44)]
        code, out = self.versus(new, self.bases(30), split=True)
        self.assertEqual(self.clause(out, 1), "PASS", out)
        self.assertEqual(code, 0, out)

    def test_just_under_ninety_percent_found_fails(self):
        new = [self.run_of(self.report(n)) for n in (43, 43, 43, 43, 43)]
        code, out = self.versus(new, self.bases(30), split=True)
        self.assertEqual(self.clause(out, 1), "FAIL", out)
        self.assertEqual(code, 1, out)

    def test_exactly_half_as_many_missed_passes(self):
        code, out = self.versus(self.news(44), self.bases(40))
        self.assertEqual(self.clause(out, 2), "PASS", out)
        self.assertEqual(code, 0, out)

    def test_a_hair_over_half_as_many_missed_fails(self):
        new = [self.run_of(self.report(n)) for n in (44, 44, 43)]
        code, out = self.versus(new, self.bases(40), split=True)
        self.assertEqual(self.clause(out, 2), "FAIL", out)

    def test_equal_made_up_passes(self):
        fake = ["- /v2/billing/charges/teleport"]
        new = [self.run_of(self.report(47, extra=fake)) for _ in range(3)]
        base = [self.run_of(self.report(36, extra=fake), roster=False) for _ in range(3)]
        code, out = self.versus(new, base)
        self.assertEqual(self.clause(out, 3), "PASS", out)
        self.assertEqual(code, 0, out)

    def test_one_more_made_up_on_average_fails(self):
        new = [self.run_of(self.report(47, extra=["- /v2/billing/charges/teleport"] * 2 + ["- fxctl teleport"])) for _ in range(3)]
        base = [self.run_of(self.report(36, extra=["- /v2/billing/charges/teleport"]), roster=False) for _ in range(3)]
        code, out = self.versus(new, base)
        self.assertEqual(self.clause(out, 3), "FAIL", out)

    def test_means_not_totals_decide(self):
        # new has one run with 1 made up out of 3 (mean 1/3), baseline one run out of 3: equal, so pass
        fake = ["- fxctl teleport"]
        new = [self.run_of(self.report(47, extra=fake))] + self.news(47, 2)
        base = [self.run_of(self.report(36, extra=fake), roster=False)] + self.bases(36, 2)
        code, out = self.versus(new, base, split=True)
        self.assertEqual(self.clause(out, 3), "PASS", out)

    def test_baseline_missing_nothing_means_new_must_miss_nothing(self):
        code, out = self.versus(self.news(48), self.bases(48))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.clause(out, 2), "PASS")
        code, out = self.versus(self.news(47), self.bases(48))
        self.assertEqual(code, 1, out)
        self.assertEqual([self.clause(out, i) for i in (1, 2, 3)], ["PASS", "FAIL", "PASS"])

    # CAN'T SCORE

    def test_fewer_than_three_new_runs(self):
        code, out = self.versus(self.news(47, count=2), self.bases(36))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "fewer than 3 runs")

    def test_fewer_than_three_baseline_runs(self):
        code, out = self.versus(self.news(47), self.bases(36, count=2))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "fewer than 3 runs")

    def test_runs_in_separate_files_all_count(self):
        code, out = self.versus(self.news(47), self.bases(36), split=True)
        self.assertEqual(code, 0, out)

    def test_a_run_with_an_error(self):
        new = self.news(47)
        new[1] = self.run_of(self.report(47), error="timed out")
        code, out = self.versus(new, self.bases(36))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "error")

    def test_a_baseline_run_with_an_error(self):
        base = self.bases(36)
        base[0] = self.run_of(self.report(36), roster=False, error="crashed")
        code, out = self.versus(self.news(47), base)
        self.assertEqual(code, 2, out)
        self.cant_score(out, "error")

    def test_skipped_paid_graders(self):
        code, out = self.versus(self.news(47, skipped=True), self.bases(36))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "skippedPaidGraders")

    def test_missing_evidence(self):
        for evidence in (None, ""):
            with self.subTest(evidence=evidence):
                new = self.news(47)
                new[2] = self.run_of(self.report(47), evidence=evidence)
                code, out = self.versus(new, self.bases(36))
                self.assertEqual(code, 2, out)
                self.cant_score(out, "evidence")

    def test_no_keep_report_grader_at_all(self):
        new = self.news(47)
        new[0]["graders"] = [g for g in new[0]["graders"] if g["name"] != "keep-report"]
        code, out = self.versus(new, self.bases(36))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "evidence")

    def test_evidence_without_the_end_marker(self):
        new = self.news(47)
        new[0] = self.run_of(self.report(47, end=False))
        code, out = self.versus(new, self.bases(36))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "END-OF-REPORT")

    def test_baseline_evidence_without_the_end_marker(self):
        base = self.bases(36)
        base[0] = self.run_of(self.report(36, end=False), roster=False)
        code, out = self.versus(self.news(47), base)
        self.assertEqual(code, 2, out)
        self.cant_score(out, "END-OF-REPORT")

    def test_new_run_failing_each_control(self):
        for kw, why in (({"roster": False}, "control-new-roster"), ({"leads": False}, "control-new-area-leads"),
                        ({"fallback": False}, "control-new-no-fallback")):
            with self.subTest(control=why):
                new = self.news(47)
                new[1] = self.run_of(self.report(47), **kw)
                code, out = self.versus(new, self.bases(36))
                self.assertEqual(code, 2, out)
                self.cant_score(out, why)

    def test_baseline_run_passing_the_roster_control(self):
        base = self.bases(36)
        base[2] = self.run_of(self.report(36), roster=True)
        code, out = self.versus(self.news(47), base)
        self.assertEqual(code, 2, out)
        self.cant_score(out, "control-new-roster")

    def test_baseline_runs_may_fail_the_other_controls(self):
        base = self.bases(36, leads=False, fallback=False)
        code, out = self.versus(self.news(47), base)
        self.assertEqual(code, 0, out)

    def test_untracked_control_only_warns(self):
        code, out = self.versus(self.news(47, untracked=False), self.bases(36))
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"(?i)warning.*control-new-untracked")

    def test_untracked_control_passing_prints_no_warning(self):
        code, out = self.versus(self.news(47), self.bases(36))
        self.assertNotRegex(out, r"(?i)warning")

    def test_fact_grader_disagreeing_with_the_report_text(self):
        for flip in (["big-01"], ["mid-24"]):
            with self.subTest(flip=flip):
                new = self.news(47)
                new[0] = self.run_of(self.report(47), flip=flip)
                code, out = self.versus(new, self.bases(36))
                self.assertEqual(code, 2, out)
                self.cant_score(out, "fact-" + flip[0])

    def test_a_missing_fact_grader(self):
        new = self.news(47)
        new[0] = self.run_of(self.report(47), drop=["fact-big-02"])
        code, out = self.versus(new, self.bases(36))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "fact-big-02")

    def test_an_unreadable_result_file(self):
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        code, out = self.go("--key", str(KEY_PATH), "--new", str(bad), "--baseline", self.write(self.bases(36)))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "bad.json")

    # what the report shows

    def test_per_run_rows_means_placement_and_cost(self):
        new = [self.run_of(self.report(n), cost=2.0, judge=0.5, seconds=s) for n, s in ((46, 100), (47, 200), (48, 300))]
        code, out = self.versus(new, self.bases(40, cost=1.0, judge=0.0, seconds=50), split=True)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"(?m)^new run 1: found 46 missed 2 made up 0 cost \$2\.50 duration 100s$")
        self.assertRegex(out, r"(?m)^baseline run 3: found 40 missed 8 made up 0 cost \$1\.00 duration 50s$")
        self.assertRegex(out, r"(?m)^new mean: found 47\.0+ missed 1\.0+ made up 0\.0+ cost \$2\.50 duration 200s$")
        self.assertRegex(out, r"(?m)^baseline mean: found 40\.0+ missed 8\.0+ ")
        for placement in {f["placement"] for f in self.facts()}:
            self.assertIn(placement, out)

    def test_missed_by_placement_counts_each_placement(self):
        code, out = self.versus(self.news(40), self.bases(30))
        late = [f for f in self.facts()[40:]]
        for placement in {f["placement"] for f in late}:
            want = sum(1 for f in late if f["placement"] == placement)
            self.assertRegex(out, r"(?m)^new missed %s: %d\b" % (re.escape(placement), want))

    def test_made_up_items_are_printed(self):
        new = [self.run_of(self.report(47, extra=["- /v2/billing/charges/teleport", "- fxctl teleport", "- see ticket 9999"])) for _ in range(3)]
        code, out = self.versus(new, self.bases(36))
        for shown in ("/v2/billing/charges/teleport", "fxctl teleport", "ticket 9999"):
            self.assertIn(shown, out)

    # made up: the four kinds, on a single report

    def made_up(self, *lines):
        return self.compare.made_up("\n".join(lines) + "\n", Fixtures.key)

    def test_real_routes_and_their_prefixes_are_not_made_up(self):
        route = Fixtures.key["routes"][0]
        parts = route.split("/")
        self.assertEqual(self.made_up("- " + route), [])
        for cut in range(2, len(parts)):
            prefix = "/".join(parts[:cut])
            with self.subTest(prefix=prefix):
                self.assertEqual(self.made_up("- the " + prefix + " group"), [])

    def test_a_longer_string_than_a_route_is_made_up(self):
        route = Fixtures.key["routes"][0]
        self.assertEqual(len(self.made_up("- " + route + "-extra")), 1)
        self.assertEqual(len(self.made_up("- " + route + "/more")), 1)
        self.assertEqual(len(self.made_up("- /v2/zz")), 1)

    def test_a_route_is_judged_where_it_stops(self):
        route = Fixtures.key["routes"][0]
        self.assertEqual(self.made_up("- `%s`, `%s`." % (route, route)), [])
        self.assertEqual(self.made_up("- (%s)" % route), [])
        self.assertEqual(self.made_up("- %s." % route), [])

    def test_a_made_up_route_is_counted_once_however_often_it_appears(self):
        found = self.made_up("- /v2/zz/nowhere", "- /v2/zz/nowhere again")
        self.assertEqual(found, [("route", "/v2/zz/nowhere")])

    def test_a_command_must_be_in_the_key(self):
        real = Fixtures.key["commands"][0]
        self.assertEqual(self.made_up("- run " + real + " now"), [])
        self.assertEqual(self.made_up("- run `fxctl health`"), [])
        self.assertEqual(self.made_up("- run fxctl zorch now"), [("command", "fxctl zorch")])
        self.assertEqual(self.made_up("- run **fxctl zorch**"), [("command", "fxctl zorch")])

    def test_a_made_up_reference_is_counted_for_every_code_with_a_shape(self):
        key = Fixtures.key
        shaped = 0
        for code in key["codes"]:
            if shape_of(code, key["code_shapes"]) in (None, "named event"):
                continue
            shaped += 1
            fake = re.sub(r"\d(?=\D*$)", lambda m: str((int(m.group()) + 1) % 10), code)
            while fake in key["codes"]:
                fake = re.sub(r"\d(?=\D*$)", lambda m: str((int(m.group()) + 1) % 10), fake)
            with self.subTest(code=code, fake=fake):
                self.assertEqual(self.made_up("- see " + code + " for it"), [])
                self.assertEqual(self.made_up("- see " + fake + " for it"), [("code", fake)])
        self.assertEqual(shaped, 24)

    def test_every_shape_catches_a_made_up_string_and_none_catches_a_real_one(self):
        samples = {"tracker key": "ZQX-1234", "ticket number": "ticket 1234", "change number": "CHG0000001",
                   "issue number": "#12345", "runbook section": "runbook section 9.9", "case number": "audit case 1234567"}
        self.assertEqual(set(samples), set(Fixtures.key["code_shapes"]))
        for name, sample in samples.items():
            with self.subTest(shape=name):
                self.assertEqual(self.made_up("- " + sample), [("code", sample)])

    def test_named_events_cannot_be_made_up(self):
        self.assertEqual(self.made_up("- the Tacoma cutover", "- the Atlantis flood", "- the Boise reprint"), [])

    def test_shapes_do_not_match_real_text_in_the_fixture(self):
        key = Fixtures.key
        allowed = set(key["codes"])
        for path, text in Fixtures.text.items():
            for name, pattern in key["code_shapes"].items():
                for m in re.finditer(pattern, text):
                    with self.subTest(path=path, shape=name):
                        self.assertIn(m.group(0), allowed)

    def test_the_scorer_finds_nothing_made_up_in_the_fixture_itself(self):
        everything = "\n".join(text for path, text in sorted(Fixtures.text.items()))
        self.assertEqual([x for x in self.compare.made_up(everything, Fixtures.key) if x[0] != "decoy"], [])

    def test_no_real_file_path_matches_a_shape(self):
        paths = "\n".join(Fixtures.files)
        for name, pattern in Fixtures.key["code_shapes"].items():
            with self.subTest(shape=name):
                self.assertIsNone(re.search(pattern, paths))
        self.assertEqual(self.compare.made_up(paths, Fixtures.key), [])

    def test_a_real_command_route_or_path_is_not_a_reference(self):
        key = Fixtures.key
        real = key["routes"] + key["commands"] + list(Fixtures.files)
        self.assertEqual(self.compare.made_up("\n".join("- " + r for r in real), key), [])

    def test_a_decoy_on_a_line_without_a_marker_is_made_up(self):
        token = Fixtures.key["decoys"][1]["token"]
        self.assertEqual(self.made_up("- " + token + " flags an aisle"), [("decoy", token)])

    def test_a_decoy_on_a_line_with_a_marker_is_not(self):
        for d in Fixtures.key["decoys"]:
            for word in self.MARKERS:
                with self.subTest(decoy=d["id"], word=word):
                    self.assertEqual(self.made_up("- %s is %s" % (d["token"], word)), [])
                    self.assertEqual(self.made_up("- %s: %s." % (word.upper(), d["token"])), [])

    def test_the_marker_must_be_on_the_same_line(self):
        token = Fixtures.key["decoys"][0]["token"]
        self.assertEqual(self.made_up("- this one is removed", "- " + token + " reassigns"), [("decoy", token)])
        self.assertEqual(self.made_up("- " + token + " reassigns", "- that one is removed"), [("decoy", token)])

    def test_a_marker_inside_a_longer_word_does_not_count(self):
        token = Fixtures.key["decoys"][0]["token"]
        for text in ("- %s has a deadline", "- %s is a recommented thing", "- %s, the undead route"):
            with self.subTest(text=text):
                self.assertEqual(self.made_up(text % token), [("decoy", token)])

    def test_a_decoy_is_counted_once_and_not_also_as_a_route(self):
        token = Fixtures.key["decoys"][2]["token"]
        self.assertEqual(self.made_up("- " + token, "- " + token + " again"), [("decoy", token)])
        self.assertEqual(self.made_up("- " + token + " is dead", "- " + token + " is live"), [("decoy", token)])

    def test_a_decoy_suffix_is_made_up_like_any_other_route(self):
        token = Fixtures.key["decoys"][2]["token"]
        self.assertEqual(self.made_up("- " + token + "-two is removed"), [("route", token + "-two")])

    # --summary

    def test_summary_prints_one_run_without_the_bar(self):
        new = self.run_of(self.report(47, extra=["- fxctl zorch"]), cost=2.0, judge=0.5, seconds=77)
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([new]))
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"found 47 missed 1 made up 1 cost \$2\.50 duration 77s")
        self.assertIn("fxctl zorch", out)
        self.assertIn("control-new-roster", out)
        self.assertNotIn("BAR", out)
        self.assertNotIn("clause", out)

    def test_summary_works_on_a_single_run_and_ignores_the_arm_controls(self):
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([self.run_of(self.report(30), roster=False, leads=False)]))
        self.assertEqual(code, 0, out)

    def test_summary_exits_2_when_the_run_cannot_be_scored(self):
        cases = {
            "error": self.run_of(error="boom"),
            "skippedPaidGraders": self.run_of(skipped=True),
            "evidence": self.run_of(evidence=None),
            "END-OF-REPORT": self.run_of(self.report(47, end=False)),
            "fact-big-01": self.run_of(flip=["big-01"]),
        }
        for why, run in cases.items():
            with self.subTest(why=why):
                code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([run]))
                self.assertEqual(code, 2, out)
                self.cant_score(out, why)

    def test_summary_scores_every_run_in_the_file(self):
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([self.run_of(), self.run_of(self.report(40))]))
        self.assertEqual(code, 0, out)
        self.assertIn("found 48", out)
        self.assertIn("found 40", out)


class CompareAdversarialTest(unittest.TestCase):
    """Adversarial round on the scorer: bar arithmetic, arm mix-ups, run validity, exit codes, made-up prose.

    Tests named `..._today` pin what the scorer does now on prose where the
    right answer is the owner's call; they are characterisation, not a verdict.
    """

    @classmethod
    def setUpClass(cls):
        CompareTest.setUpClass.__func__(cls)
        cls.count = 0
        cls.script = str(EXPENSIVE / "compare.py")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    facts = CompareTest.facts
    sync_found = CompareTest.sync_found
    report = CompareTest.report
    run_of = CompareTest.run_of
    go = CompareTest.go
    clause = CompareTest.clause
    cant_score = CompareTest.cant_score

    def write(self, runs, cases=None):
        type(self).count += 1
        path = Path(self.tmp.name) / ("adv-%d.json" % type(self).count)
        doc = {"schemaVersion": 1, "cases": cases or [{"name": "investigate-head-to-head", "arms": {"with": runs}}]}
        path.write_text(json.dumps(doc), encoding="utf-8")
        return str(path)

    def raw(self, text):
        type(self).count += 1
        path = Path(self.tmp.name) / ("adv-%d.json" % type(self).count)
        path.write_text(text, encoding="utf-8")
        return str(path)

    def runs_found(self, counts, **kw):
        """One run per count, each with its own made-up-free report."""
        return [self.run_of(self.report(n), **kw) for n in counts]

    def bar(self, new_counts, base_counts, new_extra=None, base_extra=None):
        new = [self.run_of(self.report(n, extra=(new_extra or {}).get(i, ()))) for i, n in enumerate(new_counts)]
        base = [self.run_of(self.report(n, extra=(base_extra or {}).get(i, ())), roster=False) for i, n in enumerate(base_counts)]
        return self.go("--key", str(KEY_PATH), "--new", self.write(new), "--baseline", self.write(base))

    def cli(self, *argv):
        r = subprocess.run([sys.executable, "-I", self.script, *argv], capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout, r.stderr

    def made(self, text):
        return [item for kind, item in self.compare.made_up(text, Fixtures.key)]

    # bar arithmetic with real fractions

    def test_three_runs_found_130_of_144_is_over_ninety_percent(self):
        code, out = self.bar([43, 43, 44], [30, 30, 30])
        self.assertEqual(self.clause(out, 1), "PASS", out)
        self.assertEqual(code, 0, out)

    def test_three_runs_found_129_of_144_is_under_ninety_percent(self):
        code, out = self.bar([43, 43, 43], [30, 30, 30])
        self.assertEqual(self.clause(out, 1), "FAIL", out)
        self.assertEqual(code, 1, out)
        self.assertIn("BAR MISSED", out)

    def test_seven_runs_found_303_passes_and_302_fails_clause_one(self):
        self.assertEqual(self.clause(self.bar([43] * 6 + [44], [30] * 7)[1], 1), "FAIL")
        self.assertEqual(self.clause(self.bar([43] * 5 + [44] * 2, [30] * 7)[1], 1), "PASS")

    def test_clause_two_thirds_boundary_new_missed_15_of_31_is_half_or_less(self):
        _, out = self.bar([43, 43, 43], [38, 38, 37])
        self.assertEqual(self.clause(out, 2), "PASS", out)

    def test_clause_two_thirds_boundary_new_missed_16_of_31_is_over_half(self):
        _, out = self.bar([43, 43, 42], [38, 38, 37])
        self.assertEqual(self.clause(out, 2), "FAIL", out)

    def test_clause_two_baseline_missing_an_odd_total_rounds_against_new(self):
        _, out = self.bar([48, 48, 48], [47, 47, 47])
        self.assertEqual(self.clause(out, 2), "PASS", out)
        _, out = self.bar([48, 47, 47], [47, 47, 47])
        self.assertEqual(self.clause(out, 2), "FAIL", out)

    def test_clause_two_baseline_missing_nothing_needs_new_missing_nothing(self):
        _, out = self.bar([48, 48, 48], [48, 48, 48])
        self.assertEqual(self.clause(out, 2), "PASS", out)
        _, out = self.bar([48, 48, 47], [48, 48, 48])
        self.assertEqual(self.clause(out, 2), "FAIL", out)

    def test_clause_three_thirds_boundary_equal_totals_pass_and_one_more_fails(self):
        mk = lambda tag, n: {i: ["see /v2/%s/item%d" % (tag, i) for _ in range(1)] for i in range(n)}
        _, out = self.bar([48, 48, 48], [48, 48, 48], new_extra={0: ["/v2/zz/a"], 1: ["/v2/zz/b"]}, base_extra={0: ["/v2/yy/a"], 2: ["/v2/yy/b"]})
        self.assertEqual(self.clause(out, 3), "PASS", out)
        _, out = self.bar([48, 48, 48], [48, 48, 48], new_extra={0: ["/v2/zz/a"], 1: ["/v2/zz/b"], 2: ["/v2/zz/c"]}, base_extra={0: ["/v2/yy/a"], 2: ["/v2/yy/b"]})
        self.assertEqual(self.clause(out, 3), "FAIL", out)

    def test_the_same_made_up_item_twice_in_one_run_counts_once(self):
        _, out = self.bar([48] * 3, [48] * 3, new_extra={0: ["/v2/zz/a", "again /v2/zz/a"]}, base_extra={0: ["/v2/yy/a"]})
        self.assertEqual(self.clause(out, 3), "PASS", out)

    # arms mixed up, runs dropped or duplicated

    def test_new_split_across_two_files_with_one_and_two_runs_is_pooled(self):
        a = self.write(self.runs_found([48]))
        b = self.write(self.runs_found([48, 48]))
        base = self.write(self.runs_found([30] * 3, roster=False))
        code, out = self.go("--key", str(KEY_PATH), "--new", a, b, "--baseline", base)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(re.findall(r"^new run \d+:", out, re.M)), 3, out)

    def test_one_file_listed_three_times_does_not_make_three_runs(self):
        f = self.write(self.runs_found([48]))
        base = self.write(self.runs_found([30] * 3, roster=False))
        code, out = self.go("--key", str(KEY_PATH), "--new", f, f, f, "--baseline", base)
        self.assertEqual(code, 2, out)
        self.assertRegex(out, r"CAN'T SCORE")

    def test_the_same_file_under_two_spellings_counts_once(self):
        f = self.write(self.runs_found([48]))
        again = str(Path(f).parent / ".." / Path(f).parent.name / Path(f).name)
        base = self.write(self.runs_found([30] * 3, roster=False))
        code, out = self.go("--key", str(KEY_PATH), "--new", f, again, "--baseline", base)
        self.assertEqual(code, 2, out)
        self.cant_score(out, "fewer than 3 runs")

    def test_the_same_file_for_both_arms_cannot_score(self):
        f = self.write(self.runs_found([48] * 3))
        code, out = self.go("--key", str(KEY_PATH), "--new", f, "--baseline", f)
        self.assertEqual(code, 2, out)

    def test_two_identical_run_blocks_in_one_file_are_not_three_runs(self):
        run = self.run_of()
        f = self.write([run, dict(run)])
        base = self.write(self.runs_found([30] * 3, roster=False))
        code, out = self.go("--key", str(KEY_PATH), "--new", f, "--baseline", base)
        self.assertEqual(code, 2, out)

    def test_a_file_holding_two_cases_does_not_silently_pool_the_other_case(self):
        good = self.runs_found([48] * 3)
        other = self.runs_found([0] * 3)
        cases = [{"name": "investigate-head-to-head", "arms": {"with": good}}, {"name": "some-other-case", "arms": {"with": other}}]
        new = self.write(None, cases=cases)
        base = self.write(self.runs_found([30] * 3, roster=False))
        code, out = self.go("--key", str(KEY_PATH), "--new", new, "--baseline", base)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(re.findall(r"^new run \d+:", out, re.M)), 3, out)

    def test_a_file_holding_only_another_case_has_no_runs(self):
        other = self.write(None, cases=[{"name": "some-other-case", "arms": {"with": self.runs_found([48] * 3)}}])
        base = self.write(self.runs_found([30] * 3, roster=False))
        code, out = self.go("--key", str(KEY_PATH), "--new", other, "--baseline", base)
        self.assertEqual(code, 2, out)
        self.cant_score(out, "fewer than 3 runs")

    def test_swapped_arms_cannot_score(self):
        new = self.write(self.runs_found([48] * 3))
        base = self.write(self.runs_found([30] * 3, roster=False))
        code, out = self.go("--key", str(KEY_PATH), "--new", base, "--baseline", new)
        self.assertEqual(code, 2, out)

    def test_arm_mean_uses_every_run_not_the_best(self):
        _, out = self.bar([48, 48, 0 + 20], [30] * 3)
        self.assertEqual(self.clause(out, 1), "FAIL", out)

    # run validity

    def test_control_grader_absent_from_a_new_run_cannot_score(self):
        for control in ("control-new-roster", "control-new-area-leads", "control-new-no-fallback"):
            with self.subTest(control=control):
                run = self.run_of()
                run["graders"] = [g for g in run["graders"] if g["name"] != control]
                base = self.write(self.runs_found([30] * 3, roster=False))
                code, out = self.go("--key", str(KEY_PATH), "--new", self.write([run] + self.runs_found([48, 48])), "--baseline", base)
                self.assertEqual(code, 2, out)
                self.cant_score(out, control)

    def test_control_with_null_passed_in_a_new_run_cannot_score(self):
        run = self.run_of()
        for g in run["graders"]:
            if g["name"] == "control-new-area-leads":
                g["passed"] = None
        base = self.write(self.runs_found([30] * 3, roster=False))
        code, out = self.go("--key", str(KEY_PATH), "--new", self.write([run] + self.runs_found([48, 48])), "--baseline", base)
        self.assertEqual(code, 2, out)

    def test_baseline_without_the_roster_grader_is_scored_not_refused(self):
        base = self.runs_found([30] * 3, roster=False)
        for run in base:
            run["graders"] = [g for g in run["graders"] if g["name"] != "control-new-roster"]
        code, out = self.go("--key", str(KEY_PATH), "--new", self.write(self.runs_found([48] * 3)), "--baseline", self.write(base))
        self.assertEqual(code, 0, out)

    def test_one_baseline_run_passing_the_roster_among_clean_ones_cannot_score(self):
        base = self.runs_found([30] * 2, roster=False) + self.runs_found([30], roster=True)
        code, out = self.go("--key", str(KEY_PATH), "--new", self.write(self.runs_found([48] * 3)), "--baseline", self.write(base))
        self.assertEqual(code, 2, out)

    def test_an_empty_string_error_still_cannot_score(self):
        bad = self.run_of(error="")
        code, out = self.go("--key", str(KEY_PATH), "--new", self.write([bad] + self.runs_found([48, 48])), "--baseline", self.write(self.runs_found([30] * 3, roster=False)))
        self.assertEqual(code, 2, out)

    def test_evidence_that_is_not_text_cannot_score(self):
        for value in (["END-OF-REPORT"], {"a": 1}, 0, "", "   \n"):
            with self.subTest(value=value):
                bad = self.run_of(evidence=value)
                code, out = self.cli("--key", str(KEY_PATH), "--summary", self.write([bad]))[:2]
                self.assertEqual(code, 2, out)

    def test_a_run_with_no_graders_list_cannot_score(self):
        for graders in (None, [], "x"):
            with self.subTest(graders=graders):
                bad = self.run_of()
                bad["graders"] = graders
                code, out = self.cli("--key", str(KEY_PATH), "--summary", self.write([bad]))[:2]
                self.assertEqual(code, 2, out)

    def test_a_fact_grader_the_key_does_not_list_cannot_score(self):
        run = self.run_of()
        run["graders"].append({"name": "fact-zzz-99", "passed": True})
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([run]))
        self.assertEqual(code, 2, out)

    def test_judge_explanation_and_other_graders_evidence_do_not_score_as_found(self):
        tokens = " ".join(f["token"] for f in self.facts())
        text = "# Report\nnothing here\nEND-OF-REPORT\n"
        run = self.run_of(text)
        for g in run["graders"]:
            g["explanation"] = tokens
            if g["name"] != "keep-report":
                g["evidence"] = tokens
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([run]))
        self.assertEqual(code, 0, out)
        self.assertIn("found 0 ", out)

    def test_two_cases_one_run_from_a_run_missing_keep_report_cannot_score(self):
        run = self.run_of()
        run["graders"] = [g for g in run["graders"] if g["name"] != "keep-report"]
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([run]))
        self.assertEqual(code, 2, out)

    # found: honest markdown still scores

    def test_tokens_inside_backticks_bold_links_and_escapes_still_score_found(self):
        lines = []
        for f in self.facts():
            t = f["token"]
            lines.append(["`%s`", "**%s**", "[%s](x.md)", "_%s_", "(%s)", "%s."][len(lines) % 6] % t)
        text = "\n".join(lines) + "\nEND-OF-REPORT\n"
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([self.run_of(text)]))
        self.assertEqual(code, 0, out)
        self.assertIn("found 48 ", out)

    def test_escaped_hash_still_scores_found(self):
        token = next(f["token"] for f in self.facts() if f["token"].startswith("#"))
        text = "\\" + token + "\nEND-OF-REPORT\n"
        run = self.run_of(text)
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([run]))
        self.assertEqual(code, 0, out)
        self.assertIn("found 1 ", out)

    # made up: what real prose does

    def test_a_real_route_its_prefixes_and_markdown_decorations_are_not_made_up(self):
        lines = ["`/v2/billing/charges/preview`", "GET /v2/billing/charges/preview.", "/v2/billing/*", "/v2/billing/charges/",
                 "/v2/billing/charges/{id}", "/v2/billing/invoices/{approve,hold,release}", "(/v2/billing)", "**/v2/billing/charges/preview**",
                 "https://api.example.com/v2/billing/charges/preview?x=1", "/v2/billing/charges/prev", "/v2/ and /v2/*"]
        self.assertEqual(self.made("\n".join(lines)), [])

    def test_a_route_extending_a_real_one_is_made_up(self):
        self.assertEqual(self.made("/v2/billing/charges/preview/extra"), ["/v2/billing/charges/preview/extra"])

    def test_decoy_under_a_removed_heading_is_not_made_up(self):
        decoy = Fixtures.key["decoys"][3]["token"]
        text = "## Removed endpoints\n- %s\n" % decoy
        self.assertEqual(self.made(text), [])

    def test_decoy_with_marker_on_the_next_wrapped_line_is_not_made_up(self):
        decoy = Fixtures.key["decoys"][0]["token"]
        self.assertEqual(self.made("The route %s\nis commented out in the view.\n" % decoy), [])

    def test_decoy_called_obsolete_unused_or_no_longer_routed_is_not_made_up(self):
        decoy = Fixtures.key["decoys"][0]["token"]
        for word in ("obsolete", "unused", "no longer routed", "legacy", "stale", "a stub", "taken out", "taken-out", "Commented out"):
            with self.subTest(word=word):
                self.assertEqual(self.made("- %s is %s\n" % (decoy, word)), [])

    def test_decoy_with_marker_words_in_any_case_or_hyphenated_is_not_made_up(self):
        decoy = Fixtures.key["decoys"][0]["token"]
        for line in ("%s is Commented-out", "%s (DEPRECATED)", "%s: Retired in 2.1", "dead route %s", "%s was removed"):
            with self.subTest(line=line):
                self.assertEqual(self.made(line % decoy), [])

    def test_decoy_stated_live_next_to_a_hyphenated_dead_is_counted(self):
        decoy = Fixtures.key["decoys"][0]["token"]
        self.assertEqual(self.made("%s is a live route behind the dead-letter queue" % decoy), [decoy])

    def test_uncommented_and_deadline_are_not_markers(self):
        decoy = Fixtures.key["decoys"][0]["token"]
        for line in ("%s was uncommented", "%s has a deadline", "%s is undisabled"):
            with self.subTest(line=line):
                self.assertEqual(self.made(line % decoy), [decoy])

    def test_prose_about_the_fxctl_tool_is_not_made_up(self):
        for line in ("fxctl commands are listed below", "The fxctl CLI wraps the API", "fxctl is the operator tool",
                     "run fxctl subcommands from the shell", "fxctl and the API share code", "fxctl (the CLI)"):
            with self.subTest(line=line):
                self.assertEqual(self.made(line), [])

    def test_real_commands_in_markdown_forms_are_not_made_up(self):
        for line in ("`fxctl export-charge`", "fxctl export-charge --dry-run", "fxctl show-config.", "**fxctl health**", "fxctl version"):
            with self.subTest(line=line):
                self.assertEqual(self.made(line), [])

    def test_fxctl_in_backticks_after_the_word_is_not_seen_as_a_command(self):
        self.assertEqual(self.made("fxctl `export-charge`"), [])

    def test_iso_rfc_and_utc_names_are_not_tracker_keys_but_other_prefixes_are(self):
        flagged = []
        for text in ("timestamps are ISO-8601", "see RFC-7231 for the status", "offset UTC-0500", "the TLS-1234 profile"):
            flagged.append(self.made(text))
        self.assertEqual(flagged, [[], [], [], ["TLS-1234"]])

    def test_prose_that_does_not_look_like_a_code_is_not_made_up(self):
        for text in ("UTF-8 text", "Python 3.12", "SHA-256", "HTTP 404", "ticket numbers are tracked", "the case number field", "see section 2.8",
                     "PR 12", "#1234 is four digits", "runbook section", "CHG alone"):
            with self.subTest(text=text):
                self.assertEqual(self.made(text), [])

    def test_ticket_prose_with_a_short_number_is_not_made_up(self):
        self.assertEqual(self.made("there is a ticket 1 in the queue"), [])
        self.assertEqual(self.made("ticket 123 and ticket 12345"), [])

    def test_a_longer_number_is_not_a_shape_hit_and_a_four_digit_ticket_is(self):
        self.assertEqual(self.made("color #1234567 and #123456"), [])
        self.assertEqual(self.made("ticket 1234 and #12345"), ["ticket 1234", "#12345"])

    def test_a_real_code_with_extra_digits_is_not_found_and_only_chg_is_made_up(self):
        self.assertEqual(sorted(self.made("CHG00418729 and ticket 58410")), ["CHG00418729"])
        self.assertFalse(self.compare.token_found("ticket 5841", "ticket 58410"))

    def test_a_clean_fixture_report_in_every_markdown_form_has_no_made_up(self):
        text = self.report()
        self.assertEqual(self.made(text), [])

    # exit codes

    def test_malformed_and_missing_inputs_exit_two_with_a_can_t_score_line(self):
        good = self.write(self.runs_found([48] * 3))
        base = self.write(self.runs_found([30] * 3, roster=False))
        missing = str(Path(self.tmp.name) / "no-such-file.json")
        cases = {
            "malformed json": ("--new", self.raw("{not json"), "--baseline", base),
            "empty file": ("--new", self.raw(""), "--baseline", base),
            "missing file": ("--new", good, "--baseline", missing),
            "json list": ("--new", self.raw("[]"), "--baseline", base),
            "no cases key": ("--new", self.raw("{}"), "--baseline", base),
            "cases not a list": ("--new", self.raw('{"cases": 5}'), "--baseline", base),
            "cases empty": ("--new", self.raw('{"cases": []}'), "--baseline", base),
            "arms missing": ("--new", self.raw('{"cases": [{}]}'), "--baseline", base),
            "with null": ("--new", self.raw('{"cases": [{"arms": {"with": null}}]}'), "--baseline", base),
            "with a string": ("--new", self.raw('{"cases": [{"arms": {"with": "abc"}}]}'), "--baseline", base),
            "runs are null": ("--new", self.raw('{"cases": [{"arms": {"with": [null, null, null]}}]}'), "--baseline", base),
            "runs are strings": ("--new", self.raw('{"cases": [{"arms": {"with": ["a", "b", "c"]}}]}'), "--baseline", base),
            "graders are strings": ("--new", self.raw('{"cases": [{"arms": {"with": [{"graders": ["x"]}, {}, {}]}}]}'), "--baseline", base),
            "empty baseline arm": ("--new", good, "--baseline", self.raw('{"cases": []}')),
        }
        for why, args in cases.items():
            with self.subTest(why=why):
                code, out, err = self.cli("--key", str(KEY_PATH), *args)
                self.assertEqual((code, "CAN'T SCORE" in out), (2, True), "stdout=%r stderr=%r" % (out, err[-300:]))

    def test_a_cost_that_is_not_a_number_exits_two_not_one(self):
        bad = self.run_of()
        bad["costUsd"] = "free"
        code, out, err = self.cli("--key", str(KEY_PATH), "--new", self.write([bad] + self.runs_found([48, 48])), "--baseline", self.write(self.runs_found([30] * 3, roster=False)))
        self.assertEqual((code, "CAN'T SCORE" in out), (2, True), "stdout=%r stderr=%r" % (out, err[-300:]))

    def test_a_malformed_key_exits_two_not_one(self):
        base = self.write(self.runs_found([30] * 3, roster=False))
        new = self.write(self.runs_found([48] * 3))
        for why, text in (("not json", "{"), ("a list", "[]"), ("no facts", "{}"), ("facts not a list", '{"facts": 3}')):
            with self.subTest(why=why):
                code, out, err = self.cli("--key", self.raw(text), "--new", new, "--baseline", base)
                self.assertEqual((code, "CAN'T SCORE" in out), (2, True), "stdout=%r stderr=%r" % (out, err[-300:]))

    def test_a_missing_key_file_exits_two(self):
        code, out, err = self.cli("--key", str(Path(self.tmp.name) / "none.json"), "--summary", self.write(self.runs_found([48])))
        self.assertEqual((code, "CAN'T SCORE" in out), (2, True), err[-300:])

    def test_cant_score_beats_a_failing_bar(self):
        new = self.write(self.runs_found([10] * 3))
        base = self.write(self.runs_found([30] * 2, roster=False) + [self.run_of(error="boom", roster=False)])
        code, out = self.go("--key", str(KEY_PATH), "--new", new, "--baseline", base)
        self.assertEqual(code, 2, out)
        self.cant_score(out, "baseline run 3")

    def test_exit_code_and_printed_verdict_always_agree(self):
        scenarios = (([48] * 3, [30] * 3), ([10] * 3, [30] * 3), ([43, 43, 43], [30] * 3), ([48] * 3, [48] * 3))
        for new, base in scenarios:
            with self.subTest(new=new, base=base):
                code, out = self.bar(new, base)
                verdicts = [v for v in ("BAR MET", "BAR MISSED") if re.search(r"(?m)^%s$" % v, out)]
                self.assertEqual(len(verdicts), 1, out)
                self.assertEqual(code, {"BAR MET": 0, "BAR MISSED": 1}[verdicts[0]], out)

    def test_clause_failures_and_verdict_agree(self):
        code, out = self.bar([48] * 3, [30] * 3, new_extra={0: ["/v2/zz/a"]})
        self.assertEqual((self.clause(out, 3), code), ("FAIL", 1), out)
        self.assertIn("BAR MISSED", out)

    def test_missing_arguments_exit_two_without_a_verdict(self):
        for argv in (["--key", str(KEY_PATH)], ["--key", str(KEY_PATH), "--new"], ["--key", str(KEY_PATH), "--new", "a", "--baseline"]):
            with self.subTest(argv=argv):
                code, out, _ = self.cli(*argv)
                self.assertEqual(code, 2)
                self.assertNotIn("BAR MET", out)
                self.assertNotIn("BAR MISSED", out)

    def test_control_new_untracked_failing_warns_and_does_not_block(self):
        new = self.runs_found([48] * 3, untracked=False)
        code, out = self.go("--key", str(KEY_PATH), "--new", self.write(new), "--baseline", self.write(self.runs_found([30] * 3, roster=False)))
        self.assertEqual(code, 0, out)
        self.assertIn("WARNING", out)

    # key and fact graders

    def test_key_with_a_fact_the_graders_lack_cannot_score(self):
        import copy
        key = copy.deepcopy(Fixtures.key)
        key["facts"].append({"id": "zzz-01", "kind": "route", "placement": "big-file-middle", "path": "x", "line": 1, "token": "/v2/zzz/one"})
        path = self.raw(json.dumps(key))
        code, out = self.go("--key", path, "--summary", self.write(self.runs_found([48])))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "fact-zzz-01")

    def test_every_fact_grader_disagreeing_in_either_direction_cannot_score(self):
        for fid in ("big-01", "mid-24"):
            for text in (self.report(48), self.report(0)):
                with self.subTest(fact=fid, found=text == self.report(48)):
                    run = self.run_of(text, flip=[fid])
                    code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([run]))
                    self.assertEqual(code, 2, out)


class CompareRulingsTest(unittest.TestCase):
    """Fix round 1: what counts as found, what counts as made up, and that nothing crashes into exit 1."""

    @classmethod
    def setUpClass(cls):
        CompareTest.setUpClass.__func__(cls)
        cls.count = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    facts = CompareTest.facts
    sync_found = CompareTest.sync_found
    report = CompareTest.report
    run_of = CompareTest.run_of
    go = CompareTest.go
    cant_score = CompareTest.cant_score

    def write(self, runs):
        type(self).count += 1
        path = Path(self.tmp.name) / ("rul-%d.json" % type(self).count)
        doc = {"cases": [{"name": "investigate-head-to-head", "arms": {"with": runs}}]}
        path.write_text(json.dumps(doc), encoding="utf-8")
        return str(path)

    def made(self, text):
        return [item for kind, item in self.compare.made_up(text, Fixtures.key)]

    def graders(self):
        """{fact id: (pattern, flags)} read from the committed fact-* graders."""
        out = {}
        for f in self.facts():
            text = (H2H / "graders" / ("fact-%s.md" % f["id"])).read_text(encoding="utf-8")
            pattern = json.loads(re.search(r"^pattern: (\".*\")$", text, re.M).group(1))
            self.assertIn("\nflags: i\n", text)
            out[f["id"]] = pattern
        return out

    # found

    FOUND_FORMS = (
        ("as written", lambda t: "see " + t + " here"),
        ("upper case", lambda t: t.upper()),
        ("capitalised at a sentence start", lambda t: t[:1].upper() + t[1:] + " matters."),
        ("lower case", lambda t: t.lower()),
        ("a line break for the space", lambda t: t.replace(" ", "\n")),
        ("a doubled space", lambda t: t.replace(" ", "  ")),
        ("a tab and a break", lambda t: t.replace(" ", " \t\n ")),
        ("bold", lambda t: "**" + t + "**"),
        ("backticks", lambda t: "`" + t + "`"),
        ("a link", lambda t: "[" + t + "](x.md)"),
        ("a trailing full stop or comma", lambda t: t + ". Then " + t + ","),
        ("an escaping backslash", lambda t: "\\" + t),
        ("a slash after", lambda t: t + "/x"),
    )
    MISS_FORMS = (
        ("a digit after", lambda t: t + "2"),
        ("a letter after", lambda t: t + "x"),
        ("a hyphen after", lambda t: t + "-all"),
        ("a letter before", lambda t: "x" + t),
        ("a digit before", lambda t: "7" + t),
        ("split by a letter", lambda t: t[:-1] + "q" + t[-1:]),
    )

    def test_the_found_rule_for_every_fact_and_every_form(self):
        for f in self.facts():
            for name, form in self.FOUND_FORMS:
                with self.subTest(fact=f["id"], form=name):
                    self.assertTrue(self.compare.token_found(f["token"], form(f["token"])))
            for name, form in self.MISS_FORMS:
                with self.subTest(fact=f["id"], miss=name):
                    self.assertFalse(self.compare.token_found(f["token"], form(f["token"])))

    def test_every_fact_grader_pattern_finds_its_token_in_each_form_and_agrees_with_the_scorer(self):
        patterns = self.graders()
        for f in self.facts():
            for group, want in ((self.FOUND_FORMS, True), (self.MISS_FORMS, False)):
                for name, form in group:
                    text = form(f["token"])
                    with self.subTest(fact=f["id"], form=name):
                        got = re.search(patterns[f["id"]], text, re.I | re.A) is not None
                        self.assertEqual(got, want)
                        self.assertEqual(self.compare.token_found(f["token"], text), want)

    def test_a_grader_pattern_uses_nothing_the_harness_engine_lacks(self):
        for fid, pattern in self.graders().items():
            with self.subTest(fact=fid):
                self.assertNotIn("(?<", pattern)
                self.assertNotIn("(?i)", pattern)
                self.assertTrue(pattern.startswith("(^|[^A-Za-z0-9])"))

    def test_the_named_cases_from_the_ruling(self):
        for text, token, want in (("Ticket 5841 is open", "ticket 5841", True), ("The Tacoma cutover ran late", "the Tacoma cutover", True),
                                  ("ticket 58412 is open", "ticket 5841", False), ("ticket\n5841", "ticket 5841", True),
                                  ("/v2/billing/charges/preview-all", "/v2/billing/charges/preview", False),
                                  ("the  Tacoma\ncutover", "the Tacoma cutover", True)):
            with self.subTest(text=text):
                self.assertEqual(self.compare.token_found(token, text), want)

    def test_scorer_and_grader_agree_so_a_cased_or_wrapped_report_scores(self):
        text = "# R\nTicket\n5841 and THE TACOMA CUTOVER\nEND-OF-REPORT\n"
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([self.run_of(text)]))
        self.assertEqual(code, 0, out)
        self.assertIn("found 2 ", out)

    def test_an_old_style_plain_grader_disagreeing_with_the_new_rule_cannot_score(self):
        text = "# R\nTicket 5841\nEND-OF-REPORT\n"
        run = self.run_of(text)
        for g in run["graders"]:
            if g["name"] == "fact-big-03":
                g["passed"] = False
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([run]))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "fact-big-03")

    # made up

    def test_every_ignored_fxctl_word_in_any_case_is_not_a_command(self):
        for word in ("command commands subcommand subcommands cli tool binary entry entrypoint group app program is and or the has was in on").split():
            for form in (word, word.upper(), word.capitalize()):
                with self.subTest(word=form):
                    self.assertEqual(self.made("use the fxctl %s here" % form), [])

    def test_other_fxctl_words_are_still_made_up(self):
        self.assertEqual(self.made("run fxctl zorch"), ["fxctl zorch"])
        self.assertEqual(self.made("run fxctl commands-x"), ["fxctl commands-x"])
        self.assertEqual(self.made("run fxctl toolbox"), ["fxctl toolbox"])

    def test_the_key_carries_the_tightened_shapes(self):
        shapes = Fixtures.key["code_shapes"]
        self.assertEqual(shapes["ticket number"], r"ticket \d{4}\b")
        self.assertEqual(shapes["issue number"], r"#\d{5}\b")
        for prefix in ("ISO", "RFC", "UTC"):
            self.assertIsNone(re.search(shapes["tracker key"], prefix + "-1234"))
        self.assertIsNotNone(re.search(shapes["tracker key"], "PDX-7712"))

    def test_every_marker_word_on_its_own_line_clears_a_decoy(self):
        decoy = Fixtures.key["decoys"][0]["token"]
        words = ("commented removed disabled dead deprecated inactive retired obsolete unused legacy stale stub").split() + ["taken out", "no longer"]
        for word in words:
            with self.subTest(word=word):
                self.assertEqual(self.made("- %s is %s here" % (decoy, word)), [])
                self.assertEqual(self.made("- %s is %s here" % (decoy, word.upper())), [])

    def test_a_marker_on_the_following_continuation_line_clears_a_decoy(self):
        decoy = Fixtures.key["decoys"][0]["token"]
        self.assertEqual(self.made("- %s is\n  stale now" % decoy), [])
        self.assertEqual(self.made("%s\nno longer served" % decoy), [])

    def test_a_marker_on_a_following_list_item_table_row_or_heading_does_not_clear_it(self):
        decoy = Fixtures.key["decoys"][0]["token"]
        for after in ("- the other one is removed", "* removed", "1. removed", "12) removed", "| removed |", "## Removed"):
            with self.subTest(after=after):
                self.assertEqual(self.made("- %s\n%s" % (decoy, after)), [decoy])

    def test_a_marker_two_lines_down_does_not_clear_it(self):
        decoy = Fixtures.key["decoys"][0]["token"]
        self.assertEqual(self.made("%s\nsome words\nit is removed" % decoy), [decoy])

    def test_the_nearest_heading_above_decides(self):
        d0, d1, d2 = (Fixtures.key["decoys"][i]["token"] for i in (0, 1, 2))
        self.assertEqual(self.made("## Removed endpoints\n- %s\n- %s\n\n- %s\n" % (d0, d1, d2)), [])
        self.assertEqual(self.made("## Removed endpoints\n- x\n## Live endpoints\n- %s\n" % d0), [d0])
        self.assertEqual(self.made("## Live endpoints\n- %s\n" % d0), [d0])
        self.assertEqual(self.made("# Removed\n### Notes\n- %s\n" % d0), [d0])
        self.assertEqual(self.made("- %s\n" % d0), [d0])

    def test_a_heading_below_the_decoy_does_not_clear_it(self):
        d0 = Fixtures.key["decoys"][0]["token"]
        self.assertEqual(self.made("## Live\n- %s\n## Removed endpoints\n" % d0), [d0])

    def test_a_hyphenated_compound_is_not_the_marker_but_the_listed_compounds_are(self):
        d0 = Fixtures.key["decoys"][0]["token"]
        for line, want in (("%s dead-letter", [d0]), ("%s is a stub-like thing", [d0]), ("%s is unused-looking", [d0]),
                           ("%s is commented-out", []), ("%s is taken-out", []), ("%s is no-longer there", []),
                           ("%s is dead.", []), ("%s (dead)", []), ("%s: dead", [])):
            with self.subTest(line=line):
                self.assertEqual(self.made(line % d0), want)

    def test_a_marker_word_inside_another_route_on_the_line_does_not_clear_it(self):
        d0 = Fixtures.key["decoys"][0]["token"]
        self.assertEqual(sorted(self.made("- %s next to /v2/zz/removed" % d0)), sorted([d0, "/v2/zz/removed"]))

    def test_the_decoys_own_words_do_not_clear_it(self):
        for d in Fixtures.key["decoys"]:
            with self.subTest(decoy=d["id"]):
                self.assertEqual(self.made("- %s" % d["token"]), [d["token"]])

    def test_every_counted_item_is_printed(self):
        decoy = Fixtures.key["decoys"][0]["token"]
        text = "- %s\n- fxctl zorch\n- /v2/zz/nowhere\n- ticket 1234\n" % decoy
        run = self.run_of(self.report(48, extra=text.splitlines()))
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([run]))
        self.assertEqual(code, 0, out)
        for shown in (decoy, "fxctl zorch", "/v2/zz/nowhere", "ticket 1234"):
            self.assertIn(shown, out)
        self.assertIn("made up 4 ", out)

    # crashes

    def test_a_crash_while_scoring_exits_two_not_one(self):
        runs = [self.run_of(self.report(48)) for _ in range(3)]
        base = [self.run_of(self.report(30), roster=False) for _ in range(3)]
        args = ["--key", str(KEY_PATH), "--new", self.write(runs), "--baseline", self.write(base)]
        with mock.patch.object(self.compare, "made_up", side_effect=RuntimeError("boom")):
            code, out = self.go(*args)
        self.assertEqual(code, 2, out)
        self.cant_score(out, "boom")

    def test_a_crash_while_printing_exits_two_not_one(self):
        runs = [self.run_of(self.report(48)) for _ in range(3)]
        base = [self.run_of(self.report(30), roster=False) for _ in range(3)]
        args = ["--key", str(KEY_PATH), "--new", self.write(runs), "--baseline", self.write(base)]
        with mock.patch.object(self.compare, "report", side_effect=KeyError("x")):
            code, out = self.go(*args)
        self.assertEqual(code, 2, out)
        self.assertNotIn("BAR", out)

    def test_values_of_the_wrong_type_exit_two(self):
        for field, value in (("costUsd", "free"), ("costUsd", True), ("judgeCostUsd", [1]), ("durationSeconds", "slow"), ("durationSeconds", {})):
            with self.subTest(field=field, value=value):
                bad = self.run_of(self.report(48))
                bad[field] = value
                code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([bad]))
                self.assertEqual(code, 2, out)
                self.cant_score(out, field)

    def test_a_grader_entry_that_is_not_an_object_exits_two(self):
        bad = self.run_of(self.report(48))
        bad["graders"].append("fact-big-01")
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([bad]))
        self.assertEqual(code, 2, out)

    def test_a_fact_grader_the_key_does_not_list_exits_two(self):
        bad = self.run_of(self.report(48))
        bad["graders"].append({"name": "fact-big-99", "passed": True})
        code, out = self.go("--key", str(KEY_PATH), "--summary", self.write([bad]))
        self.assertEqual(code, 2, out)
        self.cant_score(out, "fact-big-99")


if __name__ == "__main__":
    unittest.main()
