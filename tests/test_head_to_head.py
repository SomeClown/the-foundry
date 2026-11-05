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
import importlib.util
import json
import math
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
