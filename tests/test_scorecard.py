"""Tests for evals/scorecard.py: it turns harness result JSON into rows of evals/SCORECARD.md.

Each test runs the script with the running Python on synthetic result files in
temp folders. Nothing touches evals/SCORECARD.md, nothing needs the network or
a model session.

Standard library only.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "evals" / "scorecard.py"
HEADER = "| Started (UTC) | Plugin | Commit | Claude Code | Case | Runs | Fully passed | Graders failed | Cost |"
RULE = "|---|---|---|---|---|---|---|---|---|"
SCORECARD = "# Scorecard\n\nIntro line.\n\n" + HEADER + "\n" + RULE + "\n"
TAIL = "\nText after the table.\n"


def grader(name, passed=True, explanation="ok"):
    return {"name": name, "passed": passed, "weight": 1, "explanation": explanation}


def run(graders=None, error=None, cost=0.1, judge=0.0):
    return {
        "score": 1.0, "passed": True, "error": error, "costUsd": cost, "judgeCostUsd": judge,
        "graders": graders if graders is not None else [grader("a")],
    }


def result(cases, plugins=None, started="2026-11-26T08:54:40.345Z", claude="2.1.318", **extra):
    data = {
        "schemaVersion": 1, "claudeVersion": claude, "startedAt": started, "partial": False,
        "suite": {"plugins": plugins if plugins is not None else [{"name": "the-foundry", "version": "2.3.0"}]},
        "cases": [{"name": n, "arms": {"with": runs}} for n, runs in cases],
    }
    data.update(extra)
    return data


class ScorecardTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.card = self.dir / "SCORECARD.md"
        self.card.write_text(SCORECARD, encoding="utf-8")

    def write(self, data, name="aggregate-result.json", folder=None):
        base = self.dir if folder is None else self.dir / folder
        base.mkdir(parents=True, exist_ok=True)
        path = base / name
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    def go(self, *args, commit="abc1234", card=None):
        cmd = [sys.executable, "-B", str(SCRIPT)]
        if commit is not None:
            cmd += ["--commit", commit]
        cmd += ["--scorecard", str(card or self.card)]
        cmd += [str(a) for a in args]
        return subprocess.run(cmd, capture_output=True, text=True)

    def rows(self):
        return [l for l in self.card.read_text(encoding="utf-8").splitlines() if l.startswith("| 20")]


class WorkedExampleTest(ScorecardTestCase):
    def test_the_three_rows_of_the_plans_verify(self):
        data = result([
            ("architect-plan-format", [run(cost=0.6, judge=0.07), run(cost=0.6, judge=0.07)]),
            ("implement-test-first", [
                run(cost=0.2, judge=0.0),
                run([grader("dispatched-implement"), grader("test-first-report", False, "judge votes: FAIL FAIL PASS")], cost=0.19, judge=0.01),
            ]),
            ("qa-spec-check-planted", [run(cost=0.3, judge=0.02), run(cost=0.3, judge=0.02)]),
        ])
        path = self.write(data)
        proc = self.go(path, "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = proc.stdout.splitlines()
        self.assertEqual(
            out[0],
            "| 2026-11-26 08:54 | 2.3.0 | abc1234 | 2.1.318 | architect-plan-format | 2 | 2 | none | $1.34 |",
        )
        self.assertEqual(
            out[1],
            "| 2026-11-26 08:54 | 2.3.0 | abc1234 | 2.1.318 | implement-test-first | 2 | 1 | test-first-report (1) | $0.40 |",
        )
        self.assertEqual(
            out[2],
            "| 2026-11-26 08:54 | 2.3.0 | abc1234 | 2.1.318 | qa-spec-check-planted | 2 | 2 | none | $0.64 |",
        )
        self.assertEqual(out[3], "dry run: 3 rows, nothing written")
        self.assertEqual(self.card.read_text(encoding="utf-8"), SCORECARD)


class RowFormatTest(ScorecardTestCase):
    def one(self, runs, **kw):
        proc = self.go(self.write(result([("c", runs)], **kw)), "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout.splitlines()[0].split(" | ")

    def test_a_run_with_an_error_is_not_fully_passed(self):
        cells = self.one([run(error=None), run(error="timed out")])
        self.assertEqual(cells[5:8], ["2", "1", "run error (1)"])

    def test_skipped_and_failed_formats(self):
        runs = [
            run([grader("x", False, "skipped: needs a key"), grader("y", False, "no match")]),
            run([grader("x", False, "skipped: needs a key")]),
        ]
        cells = self.one(runs)
        self.assertEqual(cells[7], "x (2 skipped), y (1)")

    def test_failed_items_sort_by_count_then_name(self):
        runs = [
            run([grader("b", False), grader("a", False), grader("c", False)], error=None),
            run([grader("c", False), grader("b", False)], error="boom"),
            run([grader("c", False)]),
        ]
        cells = self.one(runs)
        self.assertEqual(cells[7], "c (3), b (2), a (1), run error (1)")

    def test_a_bar_in_a_cell_is_escaped(self):
        cells = self.one([run([grader("a|b", False)])])
        self.assertEqual(cells[7], "a\\|b (1)")

    def test_the_plugin_is_picked_by_name(self):
        plugins = [{"name": "other", "version": "9.9.9"}, {"name": "the-foundry", "version": "2.3.0"}]
        self.assertEqual(self.one([run()], plugins=plugins)[1], "2.3.0")

    def test_a_null_judge_cost_counts_as_zero(self):
        r = run(cost=0.25)
        r["judgeCostUsd"] = None
        self.assertEqual(self.one([r])[8].rstrip(" |"), "$0.25")


class WritingTest(ScorecardTestCase):
    def test_a_file_path_or_a_folder_both_work_and_files_go_in_order(self):
        first = self.write(result([("one", [run()])], started="2026-11-26T08:00:00Z"), folder="first")
        self.write(result([("two", [run()]), ("three", [run()])], started="2026-11-26T09:00:00Z"), folder="second")
        proc = self.go(first, self.dir / "second")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        cases = [r.split(" | ")[4] for r in self.rows()]
        self.assertEqual(cases, ["one", "two", "three"])
        self.assertIn("recorded 3 rows in " + str(self.card), proc.stdout)

    def test_a_second_run_adds_nothing_and_leaves_the_file_alone(self):
        path = self.write(result([("one", [run()])]))
        self.assertEqual(self.go(path).returncode, 0)
        before = self.card.read_bytes()
        proc = self.go(path)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("nothing new: every row is already recorded", proc.stdout)
        self.assertEqual(self.card.read_bytes(), before)

    def test_dry_run_writes_nothing(self):
        path = self.write(result([("one", [run()])]))
        proc = self.go(path, "--dry-run")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.card.read_text(encoding="utf-8"), SCORECARD)

    def test_rows_land_after_the_table_and_the_text_after_it_is_kept(self):
        self.card.write_text(SCORECARD + TAIL, encoding="utf-8")
        path = self.write(result([("one", [run()]), ("two", [run()])]))
        self.assertEqual(self.go(path).returncode, 0)
        text = self.card.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(SCORECARD))
        self.assertTrue(text.endswith(TAIL), text)
        lines = text.splitlines()
        rule = lines.index(RULE)
        self.assertTrue(lines[rule + 1].startswith("| 2026"))
        self.assertTrue(lines[rule + 2].startswith("| 2026"))
        self.assertEqual(lines[rule + 3], "")

    def test_a_new_row_goes_after_an_existing_one(self):
        self.assertEqual(self.go(self.write(result([("one", [run()])]))).returncode, 0)
        self.assertEqual(self.go(self.write(result([("two", [run()])], started="2026-11-27T00:00:00Z"), name="b.json")).returncode, 0)
        self.assertEqual([r.split(" | ")[4] for r in self.rows()], ["one", "two"])

    def test_the_same_case_on_another_commit_is_a_new_row(self):
        path = self.write(result([("one", [run()])]))
        self.go(path)
        self.go(path, commit="def5678")
        self.assertEqual(len(self.rows()), 2)

    def test_a_commit_is_lowercased(self):
        path = self.write(result([("one", [run()])]))
        proc = self.go(path, "--dry-run", commit="ABC1234")
        self.assertIn(" | abc1234 | ", proc.stdout)


class RefusalTest(ScorecardTestCase):
    def refuses(self, proc, why=None):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertTrue(proc.stdout.startswith("CAN'T RECORD: "), proc.stdout)
        if why:
            self.assertIn(why, proc.stdout)
        self.assertEqual(self.card.read_text(encoding="utf-8"), SCORECARD)

    def test_a_missing_file(self):
        self.refuses(self.go(self.dir / "nope.json"))

    def test_bad_json(self):
        self.refuses(self.go(self.write("{not json")))

    def test_schema_version_2(self):
        self.refuses(self.go(self.write(result([("c", [run()])], schemaVersion=2))), "schemaVersion")

    def test_partial(self):
        self.refuses(self.go(self.write(result([("c", [run()])], partial=True))), "partial")

    def test_no_foundry_plugin(self):
        data = result([("c", [run()])], plugins=[{"name": "other", "version": "1"}])
        self.refuses(self.go(self.write(data)), "the-foundry")

    def test_a_case_with_no_with_arm(self):
        data = result([("c", [run()])])
        data["cases"][0]["arms"] = {"without": [run()]}
        self.refuses(self.go(self.write(data)), "with")

    def test_a_malformed_commit(self):
        path = self.write(result([("c", [run()])]))
        for bad in ("xyz", "abc12", "g" * 8, "a" * 41):
            with self.subTest(commit=bad):
                self.refuses(self.go(path, commit=bad), "commit")

    def test_a_scorecard_without_the_header(self):
        self.card.write_text("# Scorecard\n", encoding="utf-8")
        proc = self.go(self.write(result([("c", [run()])])))
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stdout.startswith("CAN'T RECORD: "))
        self.assertEqual(self.card.read_text(encoding="utf-8"), "# Scorecard\n")

    def test_a_missing_scorecard(self):
        proc = self.go(self.write(result([("c", [run()])])), card=self.dir / "missing.md")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stdout.startswith("CAN'T RECORD: "))

    def test_hostile_input_exits_2_never_1(self):
        hostile = [
            {"schemaVersion": 1, "partial": False},
            {"schemaVersion": 1, "partial": False, "suite": {"plugins": [{"name": "the-foundry"}]}, "cases": [{"name": "c", "arms": {"with": [{}]}}], "startedAt": "garbage"},
            [],
            "null",
        ]
        for i, data in enumerate(hostile):
            with self.subTest(i=i):
                proc = self.go(self.write(data, name="h%d.json" % i))
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_one_bad_file_writes_nothing_even_when_an_earlier_one_is_fine(self):
        good = self.write(result([("c", [run()])]), folder="good")
        bad = self.write("{", folder="bad")
        self.refuses(self.go(good, bad))


class ScorecardFileTest(unittest.TestCase):
    def test_header_matches_the_script_and_every_row_has_nine_cells(self):
        text = (ROOT / "evals" / "SCORECARD.md").read_text(encoding="utf-8")
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('HEADER = "%s"' % HEADER, source)
        self.assertIn('RULE = "%s"' % RULE, source)
        lines = text.splitlines()
        self.assertIn(HEADER, lines)
        start = lines.index(HEADER)
        self.assertEqual(lines[start + 1], RULE)
        for line in lines[start + 2:]:
            if not line.startswith("|"):
                break
            cells = re.split(r"(?<!\\)\|", line.strip())[1:-1]
            with self.subTest(row=line):
                self.assertEqual(len(cells), 9)

    def test_the_script_imports_no_network_or_subprocess_module(self):
        source = SCRIPT.read_text(encoding="utf-8")
        found = re.findall(
            r"(?m)^\s*(?:import|from)\s+(?:urllib|http|socket|requests|ftplib|smtplib|subprocess|ssl|asyncio)\b", source
        )
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
