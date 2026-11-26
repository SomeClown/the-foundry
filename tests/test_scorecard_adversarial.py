"""Hostile and odd input for evals/scorecard.py (docs/plans/2026-11-26-eval-case-per-agent.md, section 5).

What the script must hold to, whatever it is fed:
- it writes only the scorecard it was given (never a stray temp file, never
  the default evals/SCORECARD.md when another path was named or on a dry run);
- it never ends with a traceback, and never exits 1 (a refusal is 2);
- it writes nothing when it refuses;
- a second run of the same input adds no row.

Standard library only. The helpers come from tests/test_scorecard.py.
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_scorecard as S  # noqa: E402

ROOT = S.ROOT
SCRIPT = S.SCRIPT
DEFAULT_CARD = ROOT / "evals" / "SCORECARD.md"


class AdversarialCase(S.ScorecardTestCase):
    def listing(self):
        return sorted(p.name for p in self.dir.iterdir())

    def clean(self, proc):
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        self.assertIn(proc.returncode, (0, 2), proc.stdout + proc.stderr)

    def ran(self, name, case_runs=None, **kw):
        return self.write(S.result([(name, case_runs if case_runs is not None else [S.run()])], **kw))


class DuplicateRowsTest(AdversarialCase):
    def test_names_with_bars_and_backslashes_are_not_recorded_twice(self):
        for name in ("a|b", "a\\|b", "a\\\\|b", "a\\", "|", "||", "a  b", "café"):
            with self.subTest(name=name):
                self.card.write_text(S.SCORECARD, encoding="utf-8")
                path = self.ran(name)
                first = self.go(path)
                second = self.go(path)
                self.assertEqual((first.returncode, second.returncode), (0, 0), first.stdout + second.stdout)
                self.assertIn("nothing new", second.stdout)
                self.assertEqual(len(self.rows()), 1)

    def test_a_case_name_with_a_space_at_either_end_is_not_recorded_twice(self):
        for name in (" lead", "trail ", " both "):
            with self.subTest(name=name):
                self.card.write_text(S.SCORECARD, encoding="utf-8")
                path = self.ran(name)
                self.go(path)
                second = self.go(path)
                self.assertEqual(second.returncode, 0)
                self.assertEqual(len(self.rows()), 1, "a second run of the same file added a row:\n" + "\n".join(self.rows()))

    def test_the_same_file_given_twice_and_as_a_folder_adds_one_row(self):
        path = self.ran("one")
        proc = self.go(path, path, self.dir)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(len(self.rows()), 1)
        self.assertIn("recorded 1 rows", proc.stdout)

    def test_the_same_case_in_two_files_with_different_start_times_is_two_rows(self):
        first = self.write(S.result([("one", [S.run()])], started="2026-11-26T08:00:00Z"), folder="a")
        second = self.write(S.result([("one", [S.run()])], started="2026-11-26T09:00:00Z"), folder="b")
        self.assertEqual(self.go(first, second).returncode, 0)
        self.assertEqual(len(self.rows()), 2)

    def test_a_hand_edited_row_with_other_spacing_still_counts_as_recorded(self):
        self.card.write_text(S.SCORECARD + "|2026-11-26 08:54|  2.3.0|abc1234 |2.1.318| one |1|1|none|$0.10|\n", encoding="utf-8")
        before = self.card.read_bytes()
        proc = self.go(self.ran("one"))
        self.assertIn("nothing new", proc.stdout)
        self.assertEqual(self.card.read_bytes(), before)


class OddValuesTest(AdversarialCase):
    def one_row(self, **kw):
        proc = self.go(self.write(S.result(**kw)), "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout.splitlines()[0]

    def test_a_case_with_no_runs_is_a_row_of_zeros(self):
        row = self.one_row(cases=[("empty", [])])
        self.assertTrue(row.endswith("| empty | 0 | 0 | none | $0.00 |"), row)

    def test_null_costs_count_as_zero(self):
        r = S.run(cost=None)
        r["judgeCostUsd"] = None
        row = self.one_row(cases=[("c", [r])])
        self.assertTrue(row.endswith("| $0.00 |"), row)

    def test_a_cost_that_is_not_a_finite_number_of_zero_or_more_is_written_n_a_and_the_row_is_recorded(self):
        for why, value in (("text", "0.10"), ("negative", -1), ("true", True), ("a list", [1])):
            with self.subTest(why=why):
                self.card.write_text(S.SCORECARD, encoding="utf-8")
                r = S.run()
                r["costUsd"] = value
                proc = self.go(self.write(S.result([("c", [r])])))
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(len(self.rows()), 1)
                self.assertTrue(self.rows()[0].endswith("| n/a |"), self.rows())

    def test_nan_and_infinite_costs_are_written_n_a(self):
        for text in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(cost=text):
                self.card.write_text(S.SCORECARD, encoding="utf-8")
                raw = json.dumps(S.result([("c", [S.run()])])).replace('"costUsd": 0.1', '"costUsd": ' + text)
                proc = self.go(self.write(raw))
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertTrue(self.rows()[0].endswith("| n/a |"), self.rows())

    def test_one_bad_cost_among_good_ones_makes_the_case_n_a_and_a_good_case_keeps_its_figure(self):
        bad = S.run()
        bad["judgeCostUsd"] = "x"
        proc = self.go(self.write(S.result([("bad", [S.run(cost=0.5), bad]), ("good", [S.run(cost=0.5)])])))
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(self.rows()[0].endswith("| n/a |"))
        self.assertTrue(self.rows()[1].endswith("| $0.50 |"))

    def test_a_line_break_in_a_cell_is_written_as_one_space(self):
        for name in ("a\nb", "a\r\nb", "a\rb", "a\u2028b", "a\x85b"):
            with self.subTest(name=repr(name)):
                self.card.write_text(S.SCORECARD, encoding="utf-8")
                self.assertEqual(self.go(self.write(S.result([(name, [S.run()])]))).returncode, 0)
                self.assertEqual(len(self.card.read_text(encoding="utf-8").split("\n")), len(S.SCORECARD.split("\n")) + 1)
                self.assertIn("| a b |", self.rows()[0])

    def test_a_result_with_no_cases_says_so_on_stderr_exits_1_and_writes_nothing(self):
        path = self.write(S.result([]))
        proc = self.go(path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("no cases in " + str(path), proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(self.card.read_text(encoding="utf-8"), S.SCORECARD)

    def test_a_start_time_with_an_offset_is_written_in_utc(self):
        for started, want in (("2026-11-26T23:30:00+05:00", "2026-11-26 18:30"), ("2026-11-26T00:30:00-02:00", "2026-11-26 02:30"),
                              ("2026-11-26T08:54:40.345Z", "2026-11-26 08:54"), ("2026-11-26T08:54:40+00:00", "2026-11-26 08:54")):
            with self.subTest(started=started):
                self.assertTrue(self.one_row(cases=[("c", [S.run()])], started=started).startswith("| " + want + " |"))

    def test_a_run_with_no_error_key_is_a_clean_run(self):
        r = S.run()
        del r["error"]
        row = self.one_row(cases=[("c", [r])])
        self.assertIn("| 1 | 1 | none |", row)

    def test_a_grader_that_failed_with_no_explanation_is_named(self):
        r = S.run([{"name": "x", "passed": False}])
        self.assertIn("| 1 | 0 | x (1) |", self.one_row(cases=[("c", [r])]))

    def test_a_skipped_grader_that_passed_is_not_listed(self):
        r = S.run([S.grader("j", True, "skipped: no judge")])
        self.assertIn("| 1 | 1 | none |", self.one_row(cases=[("c", [r])]))

    def test_a_skipped_paid_grader_is_counted_apart_from_a_failed_one_of_the_same_name(self):
        runs = [S.run([S.grader("j", False, "skipped: no judge")]), S.run([S.grader("j", False, "judge votes: FAIL FAIL PASS")])]
        row = self.one_row(cases=[("c", runs)])
        self.assertIn("| 2 | 0 | j (1), j (1 skipped) |", row)

    def test_the_plugin_listed_twice_takes_the_first_and_none_refuses(self):
        two = [{"name": "the-foundry", "version": "1.0.0"}, {"name": "the-foundry", "version": "2.0.0"}]
        self.assertIn("| 1.0.0 |", self.one_row(cases=[("c", [S.run()])], plugins=two))
        proc = self.go(self.write(S.result([("c", [S.run()])], plugins=[])))
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stdout.startswith("CAN'T RECORD: "))

    def test_unicode_in_a_case_name_is_kept(self):
        row = self.one_row(cases=[("café-日本", [S.run()])])
        self.assertIn("| café-日本 |", row)


class NeverCrashesTest(AdversarialCase):
    def hostile(self):
        base = S.result([("c", [S.run()])])

        def with_(**kw):
            data = json.loads(json.dumps(base))
            data.update(kw)
            return data

        return {
            "cases null": with_(cases=None),
            "cases is a string": with_(cases="x"),
            "a case is a string": with_(cases=["x"]),
            "a case without a name": with_(cases=[{"arms": {"with": []}}]),
            "a case name that is a number": with_(cases=[{"name": 7, "arms": {"with": []}}]),
            "arms is a list": with_(cases=[{"name": "c", "arms": []}]),
            "with is a dict": with_(cases=[{"name": "c", "arms": {"with": {}}}]),
            "a run is a string": with_(cases=[{"name": "c", "arms": {"with": ["x"]}}]),
            "a run has no graders": with_(cases=[{"name": "c", "arms": {"with": [{"error": None}]}}]),
            "graders is a dict": with_(cases=[{"name": "c", "arms": {"with": [{"graders": {}}]}}]),
            "a grader is a string": with_(cases=[{"name": "c", "arms": {"with": [{"graders": ["x"]}]}}]),
            "a grader name is a number": with_(cases=[{"name": "c", "arms": {"with": [{"graders": [{"name": 3, "passed": False}]}]}}]),
            "plugins is a string": with_(suite={"plugins": "the-foundry"}),
            "plugins hold strings": with_(suite={"plugins": ["the-foundry"]}),
            "suite is a list": with_(suite=[]),
            "startedAt a number": with_(startedAt=1764000000),
            "startedAt empty": with_(startedAt=""),
            "startedAt null": with_(startedAt=None),
            "schemaVersion null": with_(schemaVersion=None),
            "schemaVersion true": with_(schemaVersion=True),
            "schemaVersion a list": with_(schemaVersion=[1]),
            "partial a string true": with_(partial="true"),
        }

    def test_hostile_documents_never_end_in_a_traceback_or_exit_1_or_write_outside_the_scorecard(self):
        for why, data in self.hostile().items():
            with self.subTest(why=why):
                self.card.write_text(S.SCORECARD, encoding="utf-8")
                path = self.write(data, name="h.json")
                before = self.listing()
                proc = self.go(path)
                self.clean(proc)
                self.assertEqual(self.listing(), before, "the script left a file behind")
                if proc.returncode == 2:
                    self.assertTrue(proc.stdout.startswith("CAN'T RECORD: "), proc.stdout)
                    self.assertEqual(self.card.read_text(encoding="utf-8"), S.SCORECARD)

    def test_text_that_is_not_json_refuses(self):
        raw = {
            "empty": b"", "binary": b"\x00\x01\x02", "not utf-8": b"\xff\xfe{}", "a byte order mark": b"\xef\xbb\xbf{}",
            "deep nesting": b"[" * 100000 + b"]" * 100000, "deep nesting in an object": b'{"schemaVersion":1,"x":' + b"[" * 100000 + b"]" * 100000 + b"}",
            "NaN version": b'{"schemaVersion":NaN}', "a bare word": b"yes", "an array": b"[]", "null": b"null", "a number": b"1",
            "truncated": json.dumps(S.result([("c", [S.run()])])).encode()[:-15],
        }
        for why, data in raw.items():
            with self.subTest(why=why):
                path = self.dir / "r.json"
                path.write_bytes(data)
                proc = self.go(path)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stdout + proc.stderr)
                self.assertTrue(proc.stdout.startswith("CAN'T RECORD: "), proc.stdout)
                self.assertEqual(self.card.read_text(encoding="utf-8"), S.SCORECARD)

    def test_a_folder_with_no_result_file_names_the_file_it_looked_for(self):
        (self.dir / "empty").mkdir()
        proc = self.go(self.dir / "empty")
        self.assertEqual(proc.returncode, 2)
        self.assertIn(str(self.dir / "empty" / "aggregate-result.json"), proc.stdout)

    def test_a_bad_command_line_exits_2_and_writes_nothing(self):
        path = self.ran("c")
        for why, cmd in (("no commit", [sys.executable, "-B", str(SCRIPT), "--scorecard", str(self.card), str(path)]),
                         ("no result", [sys.executable, "-B", str(SCRIPT), "--commit", "abc1234", "--scorecard", str(self.card)]),
                         ("commit eats a flag", [sys.executable, "-B", str(SCRIPT), "--commit", "--dry-run", str(path)]),
                         ("an unknown flag", [sys.executable, "-B", str(SCRIPT), "--commit", "abc1234", "--nope", str(path)])):
            with self.subTest(why=why):
                proc = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(self.card.read_text(encoding="utf-8"), S.SCORECARD)

    def test_odd_commit_arguments_refuse_before_anything_is_read(self):
        path = self.ran("c")
        for commit in ("", "abc123", "abc1234 ", "abc1234\n", " abc1234", "abcdefg", "a" * 41, "abc1234|x", "$(touch pwned)abc1234",
                       "abc1234;ls", "ａｂｃ1234", "٠" * 8, "0x1234567", "abc-1234", "../abc1234"):
            with self.subTest(commit=commit):
                proc = self.go(path, commit=commit)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertTrue(proc.stdout.startswith("CAN'T RECORD: --commit"), proc.stdout)
                self.assertEqual(self.card.read_text(encoding="utf-8"), S.SCORECARD)
        self.assertFalse((self.dir / "pwned").exists())

    def test_the_longest_commit_and_uppercase_are_fine(self):
        path = self.ran("c")
        proc = self.go(path, "--dry-run", commit="ABCDEF0123456789" * 2 + "ABCDEF01")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(" | " + ("abcdef0123456789" * 2 + "abcdef01") + " | ", proc.stdout)

    def test_a_scorecard_path_that_is_a_folder_refuses(self):
        proc = self.go(self.ran("c"), card=self.dir)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertTrue(proc.stdout.startswith("CAN'T RECORD: "))

    @unittest.skipIf(not hasattr(os, "geteuid") or os.geteuid() == 0, "folder permissions don't stop root")
    def test_a_folder_it_cannot_write_in_refuses_and_leaves_no_temp_file(self):
        path = self.ran("c")
        os.chmod(str(self.dir), 0o555)
        try:
            proc = self.go(path)
        finally:
            os.chmod(str(self.dir), 0o755)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("CAN'T RECORD: ", proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(self.listing(), ["SCORECARD.md", "aggregate-result.json"])
        self.assertEqual(self.card.read_text(encoding="utf-8"), S.SCORECARD)


class WritesOnlyTheScorecardTest(AdversarialCase):
    def test_a_successful_write_leaves_no_stray_file_and_the_inputs_alone(self):
        path = self.ran("c")
        before = path.read_bytes()
        self.assertEqual(self.go(path).returncode, 0)
        self.assertEqual(self.listing(), ["SCORECARD.md", "aggregate-result.json"])
        self.assertEqual(path.read_bytes(), before)

    def test_a_dry_run_and_a_refusal_leave_the_folder_exactly_as_it_was(self):
        path = self.ran("c")
        before = self.listing()
        self.assertEqual(self.go(path, "--dry-run").returncode, 0)
        self.assertEqual(self.go(path, commit="zzz").returncode, 2)
        self.assertEqual(self.go(self.dir / "missing.json").returncode, 2)
        self.assertEqual(self.listing(), before)
        self.assertEqual(self.card.read_text(encoding="utf-8"), S.SCORECARD)

    def test_the_default_scorecard_is_never_touched_by_a_dry_run_or_a_run_that_names_another(self):
        before = DEFAULT_CARD.read_bytes()
        path = self.ran("c")
        dry = subprocess.run([sys.executable, "-B", str(SCRIPT), "--commit", "abc1234", "--dry-run", str(path)],
                             capture_output=True, text=True)
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertIn("dry run: 1 rows, nothing written", dry.stdout)
        self.assertEqual(self.go(path).returncode, 0)
        self.assertEqual(DEFAULT_CARD.read_bytes(), before)

    def test_a_dry_run_with_a_missing_scorecard_still_refuses(self):
        proc = self.go(self.ran("c"), "--dry-run", card=self.dir / "none.md")
        self.assertEqual(proc.returncode, 2)

    def test_the_rest_of_the_scorecard_is_byte_identical_and_its_mode_is_kept(self):
        head = "# T\r\nline\ttab café \n\n" + S.HEADER + "\n" + S.RULE + "\n| old | row |\n"
        tail = "\nafter  \n\n\n"
        self.card.write_bytes((head + tail).encode("utf-8"))
        os.chmod(str(self.card), 0o640)
        self.assertEqual(self.go(self.ran("c")).returncode, 0)
        new = self.card.read_bytes().decode("utf-8")
        self.assertTrue(new.startswith(head), new)
        self.assertTrue(new.endswith(tail), new)
        self.assertEqual(new.count("| 2026-11-26 08:54 |"), 1)
        self.assertEqual(os.stat(str(self.card)).st_mode & 0o777, 0o640)

    def test_a_table_at_the_very_end_of_a_file_with_no_final_newline_takes_the_row(self):
        self.card.write_text(S.SCORECARD.rstrip("\n"), encoding="utf-8")
        self.assertEqual(self.go(self.ran("c")).returncode, 0)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.card.read_text(encoding="utf-8").splitlines()[:1], ["# Scorecard"])

    def test_a_pipe_table_above_the_scorecards_own_is_not_touched(self):
        above = "| a | b |\n|---|---|\n| 2026-11-26 08:54 | x | abc1234 | x | c |\n\n"
        self.card.write_text(above + S.SCORECARD, encoding="utf-8")
        self.assertEqual(self.go(self.ran("c")).returncode, 0)
        self.assertTrue(self.card.read_text(encoding="utf-8").startswith(above + S.SCORECARD))
        self.assertEqual(len(self.rows()), 2)


if __name__ == "__main__":
    unittest.main()
