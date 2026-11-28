"""Adversarial tests for evals-expensive/check_parts.py, the scorer for a sweep read in parts.

The big-sweep fixture is built once (in a temp folder, by its own scaffold). A correct three-part split is
written here from design section 4's notation and block template, by this file's own code (it never calls
the script's internals), and fed to the script as part-1.md, part-2.md, part-3.md. Then it is broken one way
at a time: each check has to be shown able to fail, and the script's exit codes are pinned:
0 LOOP PROVED, 1 LOOP FAILED with a line naming the problem, 2 CAN'T CHECK (a crash is never 1).

No model session starts here. Standard library only; runs on Python 3.9.
"""

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
SCRIPT = EXPENSIVE / "check_parts.py"
KEY_PATH = EXPENSIVE / "big-sweep-key.json"
SCAFFOLD = EXPENSIVE / "big-sweep-in-parts" / "scaffold.sh"

CONTINUE = ("To read the rest, dispatch `investigate` again. The brief is `CONTINUE SWEEP` on its first line, "
            "then every line from `Project:` to `END OF BLOCK`, copied as it stands.")
UNTRACKED = ["notes/scratch.md", "rules/r9999_draft.py", "zones/zz_todo.txt"]
WHOLE_1 = ("Whole repo: 990 tracked files; 40 in folders skipped whole (web/vendor/: 40, vendored); "
           "3 untracked (%s)" % ", ".join(UNTRACKED))
WHOLE_LATER = "Whole repo: given in part 1."
INSTRUCTIONS = ("Instructions: In the route inventory, give every route its full path on its own line, never grouped under a prefix; "
                "give every CLI subcommand as `twctl <name>`")


# the summary of a run scored without --transcript ends with this note: the readers weren't checked, the read numbers are the parts' own
NO_TRANSCRIPT_NOTE = "; readers: not checked; read, unread and failed are the parts' own numbers (--transcript checks them)"

NOTE_2 = "NOTE: part-2.md names an untracked path that only part 1 should list: %s"


def note_lines(out):
    return [l for l in out.splitlines() if l.startswith("NOTE:")]


# ---------------------------------------------------------------- fixture and a small independent evaluator

class Fixture:
    @classmethod
    def build(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.repo = base / "repo"
        cls.repo.mkdir()
        subprocess.run(["bash", str(SCAFFOLD)], cwd=str(cls.repo), check=True, capture_output=True, text=True)
        cls.small = base / "small"
        cls.small.mkdir()
        subprocess.run(["bash", str(SCAFFOLD), "--subset", "150"], cwd=str(cls.small), check=True, capture_output=True, text=True)
        out = subprocess.run([str(cls.repo / "bin" / "git"), "-c", "core.quotepath=off", "ls-files"], cwd=str(cls.repo),
                             check=True, capture_output=True, text=True)
        cls.tracked = out.stdout.splitlines()
        cls.key = json.loads(KEY_PATH.read_text(encoding="utf-8"))


def setUpModule():
    Fixture.build()


def tearDownModule():
    Fixture.tmp.cleanup()


def select(prefix=None, direct=False, excepts=(), lo=None, hi=None):
    """The files a notation piece names; prefix None is (root). Written here, from the design's rules."""
    out = []
    for p in Fixture.tracked:
        if prefix is None:
            if "/" in p:
                continue
        else:
            if not p.startswith(prefix):
                continue
            if direct and "/" in p[len(prefix):]:
                continue
        if any(p.startswith(x) for x in excepts):
            continue
        if lo is not None and not (lo <= p <= hi):
            continue
        out.append(p)
    return out


class Area:
    def __init__(self, name, definition, files, count=None):
        self.name, self.definition, self.files = name, definition, list(files)
        self.count = len(self.files) if count is None else count

    def line(self):
        return "- %s: %s (%d files)" % (self.name, self.definition, self.count)

    def copy(self, **changes):
        a = Area(self.name, self.definition, self.files, self.count)
        for k, v in changes.items():
            setattr(a, k, v)
        return a


def folder(name, prefix):
    return Area(name, "`%s`" % prefix, select(prefix))


def rules_range(name, lo, hi, direct=True, third=None):
    files = select("rules/", direct=direct, lo=lo, hi=hi)
    d = "`rules/` (direct)" if direct else "`rules/`"
    return Area(name, "%s from `%s` to `%s`" % (d, lo, hi), files)


PART_SIZE = 450       # the owner's part size: a part holds whole areas of at most about 150 files, summing to at most 450
RULES_AREA = 122      # rules/ holds 610 files directly: five ranges of 122


def base_areas():
    """The split a 450-file part size gives the 950 files left after the whole-folder skip: 17 areas, none over 150 files."""
    rules = select("rules/")
    web = select("web/", excepts=["web/vendor/"])
    r = RULES_AREA
    return [
        Area("root", "(root)", select(None)),
        Area("api-top", "`api/` (direct)", select("api/", direct=True)),
        folder("api-accounts", "api/accounts/"),
        folder("api-billing", "api/billing/"),
        folder("api-plazas", "api/plazas/"),
        folder("api-trips", "api/trips/"),
        folder("cli", "cli/"),
        folder("docs", "docs/"),
        folder("jobs", "jobs/"),
        rules_range("rules-1", rules[0], rules[r - 1]),
        rules_range("rules-2", rules[r], rules[2 * r - 1], direct=False),
        rules_range("rules-3", rules[2 * r], rules[3 * r - 1]),
        rules_range("rules-4", rules[3 * r], rules[4 * r - 1]),
        rules_range("rules-5", rules[4 * r], rules[-1]),
        Area("scripts-zones", "`scripts/` + `zones/`", select("scripts/") + select("zones/")),
        folder("tests", "tests/"),
        Area("web", "`web/` except `web/vendor/`", web),
    ]


# part 1 reads areas[0:10] (368 files), part 2 areas[10:13] (366), part 3 the rest (216): the cuts greedy packing under 450 makes
BASE_CUTS = (10, 13)


def is_file_skip(path):
    return path.endswith(".lock") or path.endswith(".bin")


def build_parts(areas, cuts=BASE_CUTS, reads=None, blocks=None, instructions=INSTRUCTIONS):
    """A dict {'part-1.md': text, ...}. reads/blocks default from the cuts; pass lists of lists of Areas to override."""
    bounds = [0] + list(cuts) + [len(areas)]
    if reads is None:
        reads = [areas[bounds[i]:bounds[i + 1]] for i in range(len(bounds) - 1)]
    if blocks is None:
        blocks = [areas[bounds[i + 1]:] for i in range(len(bounds) - 1)]
    key = Fixture.key
    tokens = [f["token"] for f in key["facts"]]
    # a correct run writes a fact where the part that read its file says it; a fact whose file no part reads is spread round-robin
    home = {}
    for i, read in enumerate(reads):
        for a in read:
            for path in a.files:
                home.setdefault(path, i)
    parts = {}
    for i, (read, block) in enumerate(zip(reads, blocks)):
        n = len(block)
        listed = sum(a.count for a in read)
        skipped = sum(1 for a in read for f in a.files if is_file_skip(f))
        lines = ["SWEEP IN PARTS: %d areas not read" % n]
        if n:
            lines += [CONTINUE, "Project: A toll-road back office, a fixture repo.", "Focus: none",
                      "Environment: use the git wrapper ./bin/git", instructions, "Areas not read:"]
            lines += [a.line() for a in block]
            lines += ["END OF BLOCK"]
        lines += ["", "# Investigation report (part %d)" % (i + 1), "", "## Findings"]
        lines += ["- %s found while reading." % t for j, t in enumerate(tokens) if home.get(key["facts"][j]["path"], j % len(reads)) == i]
        lines += ["", "## 8. Coverage",
                  "Mode: full sweep, %d area leads" % len(read),
                  "Files listed: %d; read: %d; skipped: %d; re-dispatched: 0; failed: 0; unread: 0" % (listed, listed - skipped, skipped),
                  "Skip reasons: %d by rule." % skipped]
        if n:
            lines += ["Areas not read: %d areas, %d files; see SWEEP IN PARTS at the top." % (n, sum(a.count for a in block))]
        lines += [WHOLE_1 if i == 0 else WHOLE_LATER, "Areas read:"]
        lines += [a.line() for a in read]
        lines += ["", "INVESTIGATE REPORT ENDS", ""]
        parts["part-%d.md" % (i + 1)] = "\n".join(lines)
    return parts


def edit(parts, name, old, new, count=1):
    assert old in parts[name], "test setup: %r not in %s" % (old, name)
    out = dict(parts)
    out[name] = parts[name].replace(old, new, count)
    return out


def edit_all(parts, fn):
    return dict((k, fn(v)) for k, v in parts.items())


def run_script(parts=None, key=None, repo=None, parts_dir=None, extra=(), raw=None):
    """Runs the script on this interpreter. parts: {filename: text}. raw: {filename: bytes} written as given."""
    with tempfile.TemporaryDirectory() as tmp:
        pdir = Path(tmp) / "parts"
        if parts_dir is None:
            pdir.mkdir()
            for name, text in (parts or {}).items():
                (pdir / name).write_bytes(text.encode("utf-8"))
            for name, data in (raw or {}).items():
                (pdir / name).write_bytes(data)
            parts_dir = pdir
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--key", str(key or KEY_PATH), "--repo", str(repo or Fixture.repo),
             "--parts", str(parts_dir)] + list(extra),
            capture_output=True, text=True, cwd=tmp)
        return proc.returncode, proc.stdout + proc.stderr


class Base(unittest.TestCase):
    def assertProved(self, parts, **kw):
        code, out = run_script(parts, **kw)
        self.assertEqual((code, out.splitlines()[0] if out else ""), (0, "LOOP PROVED"), out)
        return out

    def assertFails(self, parts, *patterns, **kw):
        """Exit 1, LOOP FAILED first, and every pattern matches some failure line (case-sensitive regex)."""
        code, out = run_script(parts, **kw)
        self.assertEqual(code, 1, out)
        lines = out.splitlines()
        self.assertEqual(lines[0], "LOOP FAILED", out)
        self.assertNotIn("LOOP PROVED", out)
        self.assertGreaterEqual(len(lines), 2, "LOOP FAILED with no failure line")
        for pat in patterns:
            self.assertTrue(any(re.search(pat, line) for line in lines[1:]), "no failure line matches %r in:\n%s" % (pat, out))
        return out

    def assertCantCheck(self, code_out, pattern=""):
        code, out = code_out
        self.assertEqual(code, 2, out)
        self.assertTrue(out.startswith("CAN'T CHECK: "), out)
        self.assertNotIn("LOOP FAILED", out)
        self.assertNotIn("LOOP PROVED", out)
        if pattern:
            self.assertRegex(out, pattern)


# ---------------------------------------------------------------- a correct split passes

class CorrectSplitTest(Base):
    def test_the_base_areas_cover_950_files_once(self):
        # guards this file's own generator, so a later failure is the script's, not the test's
        files = [f for a in base_areas() for f in a.files]
        self.assertEqual(len(files), 950)
        self.assertEqual(len(set(files)), 950)
        self.assertFalse(any(f.startswith("web/vendor/") for f in files))
        self.assertEqual(len(Fixture.tracked), 990)

    def test_the_base_split_is_the_one_a_450_file_part_size_really_gives(self):
        areas = base_areas()
        self.assertTrue(all(a.count <= 150 for a in areas), [(a.name, a.count) for a in areas if a.count > 150])
        # greedy: whole areas in order, a part closes when the next area would take it past 450
        sizes, cuts, run = [], [], 0
        for i, a in enumerate(areas):
            if run and run + a.count > PART_SIZE:
                sizes.append(run)
                cuts.append(i)
                run = 0
            run += a.count
        sizes.append(run)
        self.assertEqual(tuple(cuts), BASE_CUTS)
        self.assertEqual(sizes, [368, 366, 216])
        self.assertTrue(all(s <= PART_SIZE for s in sizes))
        self.assertGreaterEqual(len(sizes), 3)
        self.assertEqual(sum(sizes), 950)

    def test_a_correct_three_part_split_is_proved_with_a_summary(self):
        out = self.assertProved(build_parts(base_areas()))
        self.assertIn("parts: 3", out)
        self.assertIn("areas: 17", out)
        self.assertIn("facts found: 33 of 33", out)
        self.assertIn("950 of 950", out)

    def test_a_correct_two_part_split_is_proved(self):
        self.assertProved(build_parts(base_areas(), cuts=(9,)))

    def test_a_correct_split_passes_with_min_parts_3(self):
        self.assertProved(build_parts(base_areas()), extra=["--min-parts", "3"])

    def test_the_default_min_parts_is_2(self):
        one = build_parts(base_areas(), cuts=())
        self.assertFails(one, r"count: .*at least 2")

    def test_part_files_are_read_in_number_order_not_name_order(self):
        # twelve parts: part-10 sorts before part-2 as text. Reads one area per part where possible.
        areas = base_areas()
        parts = build_parts(areas, cuts=tuple(range(1, 12)))
        self.assertEqual(len(parts), 12)
        self.assertProved(parts)


class AreaNotationTest(Base):
    """Each kind of piece rebuilds to the stated count; the correct alternative partitions are proved."""

    def swap(self, start, stop, new, cuts):
        areas = base_areas()
        areas[start:stop] = new
        return build_parts(areas, cuts=cuts)

    def test_folder_piece(self):
        self.assertProved(build_parts(base_areas()))  # api-accounts, cli, docs, jobs, tests

    def test_direct_piece_and_root_piece_and_multi_piece_joined_by_plus(self):
        # api-top is (direct), root is (root), scripts-zones is two pieces; all three are in the base split
        for a in base_areas():
            if a.name in ("api-top", "root", "scripts-zones"):
                self.assertIn(a.definition, ("`api/` (direct)", "(root)", "`scripts/` + `zones/`"))
        self.assertProved(build_parts(base_areas()))

    def test_direct_plus_root_in_one_area(self):
        both = Area("top", "`api/` (direct) + (root)", select("api/", direct=True) + select(None))
        self.assertProved(self.swap(0, 2, [both], cuts=(9, 12)))

    def test_except_piece(self):
        # the base web area is `web/` except `web/vendor/`; a wrong except would count 70, not 30
        web = [a for a in base_areas() if a.name == "web"][0]
        self.assertEqual(web.count, 30)
        self.assertProved(build_parts(base_areas()))

    def test_two_except_filters_chained(self):
        rest = select("api/", excepts=["api/accounts/", "api/billing/"])
        new = [folder("api-accounts", "api/accounts/"), folder("api-billing", "api/billing/"),
               Area("api-rest", "`api/` except `api/accounts/` except `api/billing/`", rest)]
        self.assertEqual(len(rest), 84)
        self.assertProved(self.swap(1, 6, new, cuts=(8, 11)))

    def test_range_over_a_whole_folder(self):
        # rules-2 in the base is `rules/` from..to (not direct); rules-1 and rules-3 are (direct) ranges
        self.assertProved(build_parts(base_areas()))

    def test_except_and_range_on_one_piece(self):
        web = select("web/", excepts=["web/vendor/"])
        cut = 15
        w1 = Area("web-1", "`web/` except `web/vendor/` from `%s` to `%s`" % (web[0], web[cut - 1]),
                  select("web/", excepts=["web/vendor/"], lo=web[0], hi=web[cut - 1]))
        w2 = Area("web-2", "`web/` except `web/vendor/` from `%s` to `%s`" % (web[cut], web[-1]),
                  select("web/", excepts=["web/vendor/"], lo=web[cut], hi=web[-1]))
        self.assertEqual(w1.count + w2.count, 30)
        self.assertProved(self.swap(16, 17, [w1, w2], cuts=BASE_CUTS))

    def test_range_pieces_inside_a_plus_definition(self):
        rules = select("rules/")
        a = Area("rules-2", "`rules/` (direct) from `%s` to `%s` + `rules/` from `%s` to `%s`" % (rules[122], rules[180], rules[181], rules[243]),
                 select("rules/", lo=rules[122], hi=rules[243]))
        self.assertEqual(a.count, 122)
        self.assertProved(self.swap(10, 11, [a], cuts=BASE_CUTS))

    def test_range_over_a_folders_direct_files_with_subfolders_present(self):
        # api/ has 4 direct files and 160 in subfolders; a range over the direct files must not pull in the subfolders
        direct = select("api/", direct=True)
        a = Area("api-top", "`api/` (direct) from `%s` to `%s`" % (direct[0], direct[-1]), select("api/", direct=True, lo=direct[0], hi=direct[-1]))
        self.assertEqual(a.count, 4)
        self.assertProved(self.swap(1, 2, [a], cuts=BASE_CUTS))

    def test_a_range_wider_than_the_direct_files_still_counts_only_direct_ones(self):
        # api/ (direct) from api/__init__.py to api/zzz.py: the subfolder files sort inside the range but are not direct
        a = Area("api-top", "`api/` (direct) from `api/__init__.py` to `api/zzzz.py`", select("api/", direct=True))
        self.assertProved(self.swap(1, 2, [a], cuts=BASE_CUTS))

    def test_a_range_stated_with_the_subfolder_files_counted_fails_the_direct_count(self):
        a = Area("api-top", "`api/` (direct) from `api/__init__.py` to `api/zzzz.py`", select("api/"), count=164)
        out = self.assertFails(self.swap(1, 2, [a], cuts=BASE_CUTS), r"stated 164 files, the definition rebuilds to 4")
        self.assertNotIn("Traceback", out)

    def test_a_range_is_a_comparison_so_a_renamed_end_path_still_selects_the_right_files(self):
        rules = select("rules/")
        # an end path that does not exist, sorting just after rules[121]
        hi = rules[121] + "~"
        a = Area("rules-1", "`rules/` (direct) from `%s` to `%s`" % (rules[0], hi), select("rules/", direct=True, lo=rules[0], hi=hi))
        self.assertEqual(a.count, 122)
        self.assertProved(self.swap(9, 10, [a], cuts=BASE_CUTS))

    def test_a_range_end_that_is_one_file_short_rebuilds_to_a_different_count(self):
        rules = select("rules/")
        a = rules_range("rules-1", rules[0], rules[121])
        a = a.copy(definition="`rules/` (direct) from `%s` to `%s`" % (rules[0], rules[120]))  # count still 122
        self.assertFails(self.swap(9, 10, [a], cuts=BASE_CUTS), r"stated 122 files, the definition rebuilds to 121")

    def test_a_folder_without_trailing_slash_is_not_the_notation(self):
        a = Area("cli", "`cli`", select("cli/"))
        areas = base_areas()
        areas[6] = a
        self.assertFails(build_parts(areas), r"area 'cli': cannot read a piece at '`cli`'")

    def test_direct_spelled_another_way_is_not_the_notation(self):
        areas = base_areas()
        areas[1] = areas[1].copy(definition="`api/` (directly)")
        self.assertFails(build_parts(areas), r"area 'api-top': expected ' \+ ' between pieces at ' \(directly\)'")

    def test_pieces_must_be_joined_by_space_plus_space(self):
        areas = base_areas()
        areas[14] = areas[14].copy(definition="`scripts/` and `zones/`")
        self.assertFails(build_parts(areas), r"area 'scripts-zones': expected ' \+ ' between pieces")

    def test_pieces_joined_without_spaces_are_not_the_notation(self):
        areas = base_areas()
        areas[14] = areas[14].copy(definition="`scripts/`+`zones/`")
        self.assertFails(build_parts(areas), r"area 'scripts-zones': expected ' \+ ' between pieces")

    def test_a_trailing_plus_is_not_the_notation(self):
        areas = base_areas()
        areas[14] = areas[14].copy(definition="`scripts/` + `zones/` + ")
        self.assertFails(build_parts(areas), r"area 'scripts-zones': cannot read a piece at ''")

    def test_an_area_line_without_a_count_is_rejected(self):
        parts = build_parts(base_areas())
        parts = edit_all(parts, lambda t: t.replace("- cli: `cli/` (36 files)", "- cli: `cli/`"))
        self.assertFails(parts, r"area line does not match")

    def test_an_area_line_with_the_count_in_the_wrong_words_is_rejected(self):
        parts = build_parts(base_areas())
        parts = edit_all(parts, lambda t: t.replace("(36 files)", "(36 entries)"))
        self.assertFails(parts, r"area line does not match")

    def test_a_path_is_compared_as_bytes_not_as_a_glob(self):
        # `docs/*.md` is a git pathspec, not the Foundry's notation
        areas = base_areas()
        areas[7] = areas[7].copy(definition="`docs/*`")
        self.assertFails(build_parts(areas), r"area 'docs': cannot read a piece")


# ---------------------------------------------------------------- the brief's breakages

class ExactlyOnceTest(Base):
    def test_an_overlapping_area_is_reported_as_in_more_than_one_area(self):
        areas = base_areas()
        rules = select("rules/")
        areas[9] = rules_range("rules-1", rules[0], rules[131])   # runs 10 files into rules-2
        out = self.assertFails(build_parts(areas), r"exactly once: 10 files are in more than one area read")
        self.assertIn("rules-1", out)

    def test_a_file_missing_between_two_ranges_is_reported_as_in_no_area(self):
        areas = base_areas()
        rules = select("rules/")
        areas[9] = rules_range("rules-1", rules[0], rules[120])   # rules[121] is now in no area
        out = self.assertFails(build_parts(areas), r"exactly once: .*1 are in no area read")
        self.assertIn(rules[121], out)

    def test_a_file_covered_by_no_area_when_a_whole_area_is_dropped(self):
        areas = [a for a in base_areas() if a.name != "docs"]
        out = self.assertFails(build_parts(areas, cuts=(9, 12)), r"exactly once: .*12 are in no area read")
        self.assertIn("docs/", out)

    def test_a_file_covered_by_two_areas_in_different_parts(self):
        areas = base_areas()
        extra = Area("cli-again", "`cli/` (direct)", select("cli/", direct=True))
        areas.append(extra)   # lands in part 3; `cli/` is in part 1
        self.assertFails(build_parts(areas), r"exactly once: 36 files are in more than one area read")

    def test_an_area_holding_the_skipped_whole_folder_is_reported(self):
        areas = base_areas()
        areas[16] = Area("web", "`web/`", select("web/"))
        self.assertFails(build_parts(areas), r"exactly once: 40 files in areas read are not expected")

    def test_an_area_that_repeats_one_part_1_already_read_is_caught(self):
        areas = base_areas()
        reads = [areas[0:10], [areas[0]] + areas[10:13], areas[13:]]    # part 2 reads `root` again
        blocks = [areas[10:], areas[13:], []]
        self.assertFails(build_parts(areas, reads=reads, blocks=blocks), r"more than one area read", r"part-2\.md: 'Areas read:' should be exactly")

    def test_the_same_area_listed_twice_in_one_part_is_caught(self):
        areas = base_areas()
        reads = [areas[0:10], areas[10:13] + [areas[12]], areas[13:]]
        self.assertFails(build_parts(areas, reads=reads, blocks=[areas[10:], areas[13:], []]),
                         r"122 files are in more than one area read")

    def test_a_decoy_area_in_a_part_that_names_a_tracked_file_twice_is_caught(self):
        areas = base_areas()
        areas.append(Area("jobs-again", "`jobs/nightly/`", select("jobs/nightly/")))
        self.assertFails(build_parts(areas), r"more than one area read")


class CountTest(Base):
    def test_a_wrong_stated_count_is_reported_with_both_numbers(self):
        areas = base_areas()
        areas[6] = areas[6].copy(count=37)
        self.assertFails(build_parts(areas), r"area 'cli': stated 37 files, the definition rebuilds to 36")

    def test_a_count_that_is_too_low_is_reported_too(self):
        areas = base_areas()
        areas[7] = areas[7].copy(count=11)
        self.assertFails(build_parts(areas), r"area 'docs': stated 11 files, the definition rebuilds to 12")

    def test_fewer_parts_than_min_parts(self):
        parts = build_parts(base_areas(), cuts=(9,))
        self.assertFails(parts, r"count: expected at least 3 part files in .*found 2", extra=["--min-parts", "3"])

    def test_a_gap_in_the_part_numbers(self):
        parts = build_parts(base_areas())
        parts["part-4.md"] = parts.pop("part-3.md")
        self.assertFails(parts, r"count: expected part-1\.md to part-3\.md with no gaps")

    def test_no_part_files_at_all_is_a_failure_not_a_crash(self):
        code, out = run_script({})
        self.assertEqual(code, 1, out)
        self.assertIn("LOOP FAILED", out)
        self.assertIn("count:", out)

    def test_files_that_are_not_part_files_are_ignored(self):
        parts = build_parts(base_areas())
        parts["part-1.md.bak"] = "junk"
        parts["notes.md"] = "junk"
        parts["part-x.md"] = "junk"
        self.assertProved(parts)


class ShapeTest(Base):
    def setUp(self):
        self.parts = build_parts(base_areas())

    def test_a_flag_line_is_reported_even_when_the_sweep_line_follows(self):
        parts = edit(self.parts, "part-1.md", "SWEEP IN PARTS: 7 areas not read", "NOT A PER-FILE READ\nSWEEP IN PARTS: 7 areas not read")
        self.assertFails(parts, r"part-1\.md: line 1 is NOT A PER-FILE READ")

    def test_a_flag_line_with_no_sweep_line_fails_two_ways(self):
        parts = edit(self.parts, "part-2.md", "SWEEP IN PARTS: 4 areas not read", "NOT A PER-FILE READ")
        self.assertFails(parts, r"part-2\.md: line 1 is NOT A PER-FILE READ", r"part-2\.md: expected 'SWEEP IN PARTS")

    def test_the_sweep_line_missing(self):
        parts = edit(self.parts, "part-1.md", "SWEEP IN PARTS: 7 areas not read\n", "")
        self.assertFails(parts, r"part-1\.md: expected 'SWEEP IN PARTS: <n> areas not read' as line 1")

    def test_the_sweep_line_with_a_lowercase_token(self):
        parts = edit(self.parts, "part-1.md", "SWEEP IN PARTS: 7 areas not read", "sweep in parts: 7 areas not read")
        self.assertFails(parts, r"part-1\.md: expected 'SWEEP IN PARTS")

    def test_the_sweep_line_for_a_files_count_is_not_the_full_sweep_token(self):
        parts = edit(self.parts, "part-1.md", "SWEEP IN PARTS: 7 areas not read", "SWEEP IN PARTS: 7 files not read")
        self.assertFails(parts, r"part-1\.md: expected 'SWEEP IN PARTS: <n> areas not read'")

    def test_the_sweep_line_with_a_trailing_period_is_not_the_token(self):
        parts = edit(self.parts, "part-1.md", "SWEEP IN PARTS: 7 areas not read", "SWEEP IN PARTS: 7 areas not read.")
        self.assertFails(parts, r"part-1\.md: expected 'SWEEP IN PARTS")

    def test_the_sweep_line_pushed_to_line_3_is_rejected(self):
        parts = edit(self.parts, "part-1.md", "SWEEP IN PARTS: 7 areas not read", "# A heading\n\nSWEEP IN PARTS: 7 areas not read")
        self.assertFails(parts, r"part-1\.md: expected 'SWEEP IN PARTS")

    def test_the_n_must_match_the_areas_in_the_block(self):
        parts = edit(self.parts, "part-1.md", "SWEEP IN PARTS: 7 areas not read", "SWEEP IN PARTS: 6 areas not read")
        self.assertFails(parts, r"part-1\.md: the SWEEP IN PARTS line says 6 areas, the block holds 7 area lines")

    def test_a_part_without_its_last_line(self):
        parts = edit(self.parts, "part-3.md", "INVESTIGATE REPORT ENDS\n", "")
        self.assertFails(parts, r"part-3\.md: expected the last non-blank line to be 'INVESTIGATE REPORT ENDS'")

    def test_the_last_line_in_the_middle_of_the_report_is_not_the_last_line(self):
        parts = edit(self.parts, "part-1.md", "INVESTIGATE REPORT ENDS\n", "INVESTIGATE REPORT ENDS\nAnd then more text.\n")
        self.assertFails(parts, r"part-1\.md: expected the last non-blank line")

    def test_the_last_line_with_a_period_or_other_case_is_not_the_token(self):
        for bad in ("INVESTIGATE REPORT ENDS.", "Investigate report ends", "AREA REPORT ENDS", "INVESTIGATE REPORT END"):
            with self.subTest(bad=bad):
                parts = edit(self.parts, "part-2.md", "INVESTIGATE REPORT ENDS", bad)
                self.assertFails(parts, r"part-2\.md: expected the last non-blank line")

    def test_an_area_lead_return_ending_in_area_report_ends_instead_of_the_investigate_line(self):
        parts = edit(self.parts, "part-3.md", "INVESTIGATE REPORT ENDS", "AREA REPORT ENDS")
        self.assertFails(parts, r"part-3\.md: expected the last non-blank line")

    def test_an_empty_part_file(self):
        parts = dict(self.parts)
        parts["part-2.md"] = ""
        self.assertFails(parts, r"part-2\.md: expected 'SWEEP IN PARTS")

    # ---- the block, line by line

    def test_the_continue_sentence_changed_by_one_word(self):
        parts = edit(self.parts, "part-1.md", "dispatch `investigate` again", "dispatch `investigator` again")
        self.assertFails(parts, r"part-1\.md: block line 2: expected 'To read the rest")

    def test_the_continue_sentence_missing(self):
        parts = edit(self.parts, "part-1.md", CONTINUE + "\n", "")
        self.assertFails(parts, r"part-1\.md: block line 2: expected 'To read the rest")

    def test_the_block_missing_project(self):
        parts = edit(self.parts, "part-1.md", "Project: A toll-road back office, a fixture repo.\n", "")
        self.assertFails(parts, r"part-1\.md: block line 3: expected 'Project: <text>'")

    def test_the_block_with_an_empty_project_line(self):
        parts = edit(self.parts, "part-1.md", "Project: A toll-road back office, a fixture repo.", "Project:")
        self.assertFails(parts, r"part-1\.md: block line 3: expected 'Project: <text>'")

    def test_the_block_missing_focus(self):
        parts = edit(self.parts, "part-2.md", "Focus: none\n", "")
        self.assertFails(parts, r"part-2\.md: block line 4: expected 'Focus: <text>'")

    def test_the_block_missing_environment(self):
        parts = edit(self.parts, "part-1.md", "Environment: use the git wrapper ./bin/git\n", "")
        self.assertFails(parts, r"part-1\.md: block line 5: expected 'Environment: <text>'")

    def test_the_block_missing_the_areas_not_read_header(self):
        parts = edit(self.parts, "part-1.md", "Areas not read:\n- rules-2", "- rules-2")
        self.assertFails(parts, r"part-1\.md: block line 7: expected 'Areas not read:'")

    def test_the_block_with_its_lines_in_the_wrong_order(self):
        text = self.parts["part-1.md"]
        a, b = "Project: A toll-road back office, a fixture repo.\n", "Focus: none\n"
        parts = dict(self.parts)
        parts["part-1.md"] = text.replace(a + b, b + a)
        self.assertNotEqual(parts["part-1.md"], text)
        self.assertFails(parts, r"part-1\.md: block line 3: expected 'Project: <text>'")

    def test_a_blank_line_inside_the_block_is_not_tolerated(self):
        parts = edit(self.parts, "part-1.md", "Focus: none\n", "Focus: none\n\n")
        self.assertFails(parts, r"part-1\.md: block line 5: expected 'Environment: <text>'")

    def test_a_blank_line_between_area_lines_is_not_tolerated(self):
        first = base_areas()[10].line()
        parts = edit(self.parts, "part-1.md", first + "\n- rules-3", first + "\n\n- rules-3")
        self.assertFails(parts, r"part-1\.md: block line \d+: expected an area line")

    def test_the_block_never_reaching_end_of_block(self):
        parts = edit(self.parts, "part-2.md", "END OF BLOCK\n", "")
        self.assertFails(parts, r"part-2\.md: block line \d+: expected an area line starting '- ' or END OF BLOCK")

    def test_end_of_block_with_other_text_is_not_the_token(self):
        parts = edit(self.parts, "part-1.md", "END OF BLOCK", "END OF BLOCK.")
        self.assertFails(parts, r"part-1\.md: block line")

    def test_end_of_block_lowercase_is_not_the_token(self):
        parts = edit(self.parts, "part-1.md", "END OF BLOCK", "end of block")
        self.assertFails(parts, r"part-1\.md: block line")

    def test_the_areas_not_read_header_with_other_case(self):
        parts = edit(self.parts, "part-1.md", "\nAreas not read:\n", "\nAreas Not Read:\n")
        self.assertFails(parts, r"part-1\.md: block line 7: expected 'Areas not read:'")

    def test_a_non_area_line_inside_the_block(self):
        parts = edit(self.parts, "part-1.md", "Areas not read:\n", "Areas not read:\nsome commentary\n")
        self.assertFails(parts, r"part-1\.md: block line 8: expected an area line starting '- '")

    def test_the_last_part_with_nothing_under_the_line_passes_and_text_under_it_fails(self):
        for stray, label in (("To read the rest, dispatch again.", "sentence"), ("END OF BLOCK", "end"), ("Project: x", "project"),
                             ("Focus: x", "focus"), ("Environment: x", "environment"), ("Areas not read:", "header")):
            with self.subTest(label=label):
                parts = edit(self.parts, "part-3.md", "SWEEP IN PARTS: 0 areas not read\n", "SWEEP IN PARTS: 0 areas not read\n%s\n" % stray)
                self.assertFails(parts, r"part-3\.md: the last part says 0 areas not read, so nothing may sit under the line")

    def test_a_count_too_long_to_convert_is_a_line_the_check_cannot_read_not_an_internal_error(self):
        huge = "9" * 5000
        for label, name, old, new in (("sweep line", "part-1.md", "SWEEP IN PARTS: 7 areas not read", "SWEEP IN PARTS: %s areas not read" % huge),
                                      ("counts line", "part-3.md", "failed: 0;", "failed: %s;" % huge),
                                      ("area count", "part-3.md", " files)", " %s files)" % huge)):
            with self.subTest(label=label):
                code, out = run_script(edit(self.parts, name, old, new))
                self.assertEqual((code, out.splitlines()[0]), (1, "LOOP FAILED"), out[:300])
                self.assertNotIn("internal error", out)


class OrderTest(Base):
    def setUp(self):
        self.parts = build_parts(base_areas())

    def test_a_re_split_block_in_part_2_is_not_a_suffix_of_part_1s_block(self):
        # rules-5 split into two ranges in part 2 only
        rules = select("rules/")
        h1 = rules_range("rules-5a", rules[488], rules[540]).line()
        h2 = rules_range("rules-5b", rules[541], rules[-1]).line()
        old = rules_range("rules-5", rules[488], rules[-1]).line()
        parts = edit(self.parts, "part-2.md", old, h1 + "\n" + h2)
        parts = edit(parts, "part-2.md", "SWEEP IN PARTS: 4 areas not read", "SWEEP IN PARTS: 5 areas not read")
        self.assertFails(parts, r"part-2\.md: block areas must be a strict suffix of part-1\.md's block")

    def test_a_block_in_part_2_that_keeps_every_area_part_1_listed_is_not_a_strict_suffix(self):
        block = "\n".join(a.line() for a in base_areas()[10:])
        old = "\n".join(a.line() for a in base_areas()[13:])
        parts = edit(self.parts, "part-2.md", old, block)
        parts = edit(parts, "part-2.md", "SWEEP IN PARTS: 4 areas not read", "SWEEP IN PARTS: 7 areas not read")
        self.assertFails(parts, r"part-2\.md: expected n to fall from 7", r"part-2\.md: block areas must be a strict suffix")

    def test_part_2_listing_its_areas_in_a_different_order_from_part_1(self):
        a = base_areas()
        l1, l2 = a[14].line(), a[15].line()    # scripts-zones and tests: both stay in part 2's block
        parts = edit(self.parts, "part-2.md", l1 + "\n" + l2, l2 + "\n" + l1)
        self.assertFails(parts, r"part-2\.md: block areas must be a strict suffix of part-1\.md's block")

    def test_part_2_reading_its_areas_in_a_different_order_than_the_block_dropped_them(self):
        a = base_areas()
        l1, l2 = a[10].line(), a[11].line()
        self.assertIn(l1 + "\n" + l2, self.parts["part-2.md"])
        parts = edit(self.parts, "part-2.md", l1 + "\n" + l2, l2 + "\n" + l1)
        self.assertFails(parts, r"part-2\.md: 'Areas read:' should be exactly the 3 areas dropped from part-1\.md's block")

    def test_part_2_reading_fewer_areas_than_the_block_dropped(self):
        a = base_areas()
        parts = edit(self.parts, "part-2.md", a[12].line() + "\n\nINVESTIGATE", "\nINVESTIGATE")
        self.assertFails(parts, r"part-2\.md: 'Areas read:' should be exactly the 3 areas dropped")

    def test_n_not_falling_between_parts(self):
        # part 2 repeats part 1's n and block
        text1 = self.parts["part-1.md"]
        block = text1.split("INVESTIGATE")[0]
        parts = dict(self.parts)
        parts["part-2.md"] = parts["part-2.md"].replace(self.parts["part-2.md"].split("\n\n# Investigation")[0],
                                                       text1.split("\n\n# Investigation")[0], 1)
        self.assertNotEqual(parts["part-2.md"], self.parts["part-2.md"])
        self.assertFails(parts, r"part-2\.md: expected n to fall from 7 in part-1\.md, found 7")

    def test_the_last_part_not_saying_zero(self):
        areas = base_areas()
        reads = [areas[0:10], areas[10:13], areas[13:16]]
        blocks = [areas[10:], areas[13:], areas[16:]]
        out = self.assertFails(build_parts(areas, reads=reads, blocks=blocks), r"part-3\.md: the last part must say 0 areas not read, found 1")
        self.assertIn("exactly once", out)   # and the unread area is flagged as covered by no part

    def test_n_must_fall_at_the_last_step_too(self):
        # three parts, each still carrying the same n: the loop never ends
        areas = base_areas()
        same = areas[10:]
        parts = build_parts(areas, reads=[areas[0:10], areas[10:13], areas[13:]], blocks=[same, same, same])
        self.assertFails(parts, r"expected n to fall", r"the last part must say 0")

    def test_no_final_zero_part_when_the_last_part_is_cut_short_by_a_missing_file(self):
        parts = dict(self.parts)
        del parts["part-3.md"]
        self.assertFails(parts, r"part-2\.md: the last part must say 0 areas not read, found 4")


class InstructionsLineTest(Base):
    """The block's Instructions: line, and the check that the four head lines are the same in every part."""

    def setUp(self):
        self.parts = build_parts(base_areas())
        self.ins = INSTRUCTIONS

    def test_the_correct_split_carries_a_real_looking_instructions_line(self):
        self.assertIn(self.ins + "\nAreas not read:", self.parts["part-1.md"])
        self.assertNotIn("Instructions: none", self.parts["part-1.md"])
        self.assertProved(self.parts)

    def test_instructions_none_is_accepted(self):
        self.assertProved(build_parts(base_areas(), instructions="Instructions: none"))

    def test_instructions_missing(self):
        parts = edit(self.parts, "part-2.md", self.ins + "\n", "")
        self.assertFails(parts, r"part-2\.md: block line 6: expected 'Instructions: <text>', found 'Areas not read:'")

    def test_instructions_missing_in_every_part(self):
        parts = edit_all(self.parts, lambda t: t.replace(self.ins + "\n", ""))
        self.assertFails(parts, r"part-1\.md: block line 6: expected 'Instructions: <text>'", r"part-2\.md: block line 6: expected 'Instructions: <text>'")

    def test_instructions_empty(self):
        parts = edit(self.parts, "part-1.md", self.ins, "Instructions:")
        self.assertFails(parts, r"part-1\.md: block line 6: expected 'Instructions: <text>', found 'Instructions:'")

    def test_instructions_with_only_spaces(self):
        parts = edit(self.parts, "part-1.md", self.ins, "Instructions:    ")
        self.assertFails(parts, r"part-1\.md: block line 6: expected 'Instructions: <text>'")

    def test_instructions_before_environment(self):
        env = "Environment: use the git wrapper ./bin/git"
        parts = edit(self.parts, "part-1.md", env + "\n" + self.ins + "\n", self.ins + "\n" + env + "\n")
        self.assertFails(parts, r"part-1\.md: block line 5: expected 'Environment: <text>', found 'Instructions:")

    def test_instructions_after_areas_not_read(self):
        parts = edit(self.parts, "part-1.md", self.ins + "\nAreas not read:\n", "Areas not read:\n" + self.ins + "\n")
        self.assertFails(parts, r"part-1\.md: block line 6: expected 'Instructions: <text>', found 'Areas not read:'")

    def test_instructions_duplicated(self):
        parts = edit(self.parts, "part-1.md", self.ins + "\n", self.ins + "\n" + self.ins + "\n")
        self.assertFails(parts, r"part-1\.md: block line 7: expected 'Areas not read:', found 'Instructions:")

    def test_instructions_misspelled(self):
        for bad in ("Instruction:", "Instructions", "INSTRUCTIONS:", "instructions:", "Instructons:"):
            with self.subTest(bad=bad):
                parts = edit(self.parts, "part-1.md", "Instructions:", bad)
                self.assertFails(parts, r"part-1\.md: block line 6: expected 'Instructions: <text>'")

    def test_instructions_with_a_leading_dash(self):
        parts = edit(self.parts, "part-1.md", self.ins, "- " + self.ins)
        self.assertFails(parts, r"part-1\.md: block line 6: expected 'Instructions: <text>'")

    def test_instructions_under_the_zero_line_of_the_last_part(self):
        parts = edit(self.parts, "part-3.md", "SWEEP IN PARTS: 0 areas not read\n", "SWEEP IN PARTS: 0 areas not read\n" + self.ins + "\n")
        self.assertFails(parts, r"part-3\.md: the last part says 0 areas not read, so nothing may sit under the line")

    # ---- the same four lines

    def reword(self, part, old, new):
        return edit(self.parts, part, old, new)

    def test_each_of_the_four_lines_reworded_in_part_2(self):
        cases = [("Project:", "Project: A toll-road back office, a fixture repo.", "Project: A toll-road back office."),
                 ("Focus:", "Focus: none", "Focus: the api"),
                 ("Environment:", "Environment: use the git wrapper ./bin/git", "Environment: use git"),
                 ("Instructions:", self.ins, "Instructions: none")]
        for label, old, new in cases:
            with self.subTest(label=label):
                out = self.assertFails(self.reword("part-2.md", old, new),
                                       r"^part-2\.md: the %s line differs from part-1\.md: expected %s, found %s$" % (re.escape(label), re.escape(repr(old)), re.escape(repr(new))))
                self.assertEqual(len([l for l in out.splitlines() if "differs" in l]), 1)

    def test_part_3_has_no_head_lines_so_a_three_part_split_with_a_three_block_run_is_checked_in_parts_1_and_2(self):
        # part 3 (0 areas not read) carries none; only parts 1 and 2 are compared
        self.assertProved(self.parts)

    def test_each_of_the_four_lines_reworded_in_part_3_only(self):
        # a four-part split so that part 3 still has a block
        parts = build_parts(base_areas(), cuts=(6, 10, 13))
        self.assertProved(parts)
        cases = [("Project:", "Project: A toll-road back office, a fixture repo.", "Project: Another."),
                 ("Focus:", "Focus: none", "Focus: web"),
                 ("Environment:", "Environment: use the git wrapper ./bin/git", "Environment: plain git"),
                 ("Instructions:", self.ins, "Instructions: none")]
        for label, old, new in cases:
            with self.subTest(label=label):
                out = self.assertFails(edit(parts, "part-3.md", old, new),
                                       r"^part-3\.md: the %s line differs from part-1\.md: expected %s, found %s$" % (re.escape(label), re.escape(repr(old)), re.escape(repr(new))))
                self.assertNotIn("part-2.md: the", out)

    def test_parts_2_and_3_agreeing_with_each_other_but_not_with_part_1(self):
        parts = build_parts(base_areas(), cuts=(6, 10, 13))
        parts = edit(parts, "part-1.md", "Focus: none", "Focus: the api")
        out = self.assertFails(parts, r"^part-2\.md: the Focus: line differs from part-1\.md: expected 'Focus: the api', found 'Focus: none'$",
                               r"^part-3\.md: the Focus: line differs from part-1\.md: expected 'Focus: the api', found 'Focus: none'$")
        self.assertNotIn("part-3.md: the Focus: line differs from part-2", out)

    def test_two_lines_differing_in_one_part_are_both_named(self):
        parts = edit(self.parts, "part-2.md", "Focus: none", "Focus: web")
        parts = edit(parts, "part-2.md", self.ins, "Instructions: none")
        self.assertFails(parts, r"part-2\.md: the Focus: line differs", r"part-2\.md: the Instructions: line differs")

    def test_a_difference_in_trailing_whitespace_only_passes(self):
        parts = edit(self.parts, "part-2.md", "Focus: none", "Focus: none   ")
        parts = edit(parts, "part-2.md", self.ins, self.ins + "\t ")
        parts = edit(parts, "part-2.md", "Project: A toll-road back office, a fixture repo.", "Project: A toll-road back office, a fixture repo. ")
        parts = edit(parts, "part-2.md", "Environment: use the git wrapper ./bin/git", "Environment: use the git wrapper ./bin/git  ")
        self.assertProved(parts)

    def test_a_difference_in_case_fails(self):
        parts = edit(self.parts, "part-2.md", "Focus: none", "Focus: None")
        self.assertFails(parts, r"part-2\.md: the Focus: line differs from part-1\.md: expected 'Focus: none', found 'Focus: None'")

    def test_a_difference_in_inner_spacing_fails(self):
        parts = edit(self.parts, "part-2.md", "use the git wrapper", "use  the git wrapper")
        self.assertFails(parts, r"part-2\.md: the Environment: line differs from part-1\.md")

    def test_a_difference_in_leading_spacing_fails(self):
        parts = edit(self.parts, "part-2.md", "\nFocus: none", "\n Focus: none")
        self.assertFails(parts, r"part-2\.md: block line 4: expected 'Focus: <text>'")

    def test_the_last_part_with_no_lines_is_not_compared(self):
        self.assertNotIn("Focus:", self.parts["part-3.md"].split("# Investigation")[0])
        self.assertProved(self.parts)

    def test_a_part_whose_block_is_unreadable_is_not_compared_and_is_reported_once(self):
        parts = edit(self.parts, "part-2.md", self.ins + "\n", "")
        out = self.assertFails(parts, r"part-2\.md: block line 6")
        self.assertNotIn("differs", out)

    def test_the_failure_line_gives_part_1s_text_against_the_found_text(self):
        parts = edit(self.parts, "part-2.md", self.ins, "Instructions: something else")
        code, out = run_script(parts)
        self.assertEqual(code, 1)
        line = [l for l in out.splitlines() if "differs" in l][0]
        self.assertEqual(line, "part-2.md: the Instructions: line differs from part-1.md: expected %r, found %r" % (self.ins, "Instructions: something else"))


# ---------------------------------------------------------------- coverage lines

class CoverageTest(Base):
    def setUp(self):
        self.parts = build_parts(base_areas())

    def test_bad_arithmetic_in_files_listed(self):
        m = re.search(r"Files listed: (\d+); read: (\d+); skipped: (\d+)", self.parts["part-1.md"])
        listed = int(m.group(1))
        parts = edit(self.parts, "part-1.md", "read: %s;" % m.group(2), "read: %d;" % (int(m.group(2)) + 1))
        self.assertFails(parts, r"part-1\.md: Files listed %d should equal read\+skipped\+failed\+unread" % listed)

    def test_failed_files_that_do_not_add_up(self):
        parts = edit(self.parts, "part-2.md", "failed: 0;", "failed: 3;")
        self.assertFails(parts, r"part-2\.md: Files listed \d+ should equal read\+skipped\+failed\+unread")

    def test_files_listed_equal_to_the_sum_but_not_to_the_areas_counts(self):
        m = re.search(r"Files listed: (\d+); read: (\d+); skipped: (\d+)", self.parts["part-2.md"])
        listed, read, skipped = (int(x) for x in m.groups())
        parts = edit(self.parts, "part-2.md", "Files listed: %d; read: %d;" % (listed, read), "Files listed: %d; read: %d;" % (listed + 2, read + 2))
        self.assertFails(parts, r"part-2\.md: Files listed %d should equal the sum of its areas' counts, %d" % (listed + 2, listed))

    def test_files_listed_line_missing(self):
        parts = edit_all(self.parts, lambda t: re.sub(r"Files listed:[^\n]*\n", "", t))
        self.assertFails(parts, r"part-1\.md: no line 'Files listed: <n>; read: <n>")

    def test_files_listed_line_without_redispatched(self):
        parts = edit(self.parts, "part-1.md", " re-dispatched: 0;", "")
        self.assertFails(parts, r"part-1\.md: no line 'Files listed")

    def test_files_listed_line_with_a_comma_instead_of_a_semicolon(self):
        parts = edit(self.parts, "part-1.md", "; skipped:", ", skipped:")
        self.assertFails(parts, r"part-1\.md: no line 'Files listed")

    # ---- Mode

    def test_mode_says_the_wrong_number_of_leads(self):
        parts = edit(self.parts, "part-1.md", "Mode: full sweep, 10 area leads", "Mode: full sweep, 7 area leads")
        self.assertFails(parts, r"part-1\.md: Mode says 7 area leads, 'Areas read:' lists 10 areas")

    def test_mode_counting_the_leads_of_the_whole_sweep_instead_of_this_run(self):
        parts = edit(self.parts, "part-3.md", "Mode: full sweep, 4 area leads", "Mode: full sweep, 17 area leads")
        self.assertFails(parts, r"part-3\.md: Mode says 17 area leads, 'Areas read:' lists 4 areas")

    def test_mode_line_missing(self):
        parts = edit(self.parts, "part-2.md", "Mode: full sweep, 3 area leads\n", "")
        self.assertFails(parts, r"part-2\.md: no line 'Mode: full sweep, <N> area leads'")

    def test_mode_line_with_another_mode(self):
        parts = edit(self.parts, "part-1.md", "Mode: full sweep, 10 area leads", "Mode: scoped, 10 area leads")
        self.assertFails(parts, r"part-1\.md: no line 'Mode: full sweep")

    def test_mode_line_that_is_a_per_file_read(self):
        parts = edit(self.parts, "part-1.md", "Mode: full sweep, 10 area leads", "Mode: per-file read")
        self.assertFails(parts, r"part-1\.md: no line 'Mode: full sweep")

    # ---- areas not read

    def test_coverage_areas_not_read_line_with_the_wrong_file_total(self):
        total = sum(a.count for a in base_areas()[10:])
        parts = edit(self.parts, "part-1.md", "Areas not read: 7 areas, %d files;" % total, "Areas not read: 7 areas, %d files;" % (total - 1))
        self.assertFails(parts, r"part-1\.md: Coverage says 7 areas, %d files not read; the block holds 7 areas, %d files" % (total - 1, total))

    # ---- the real run's wrong sum: four areas of 122, 36, 30 and 20 files added up in the model's head as 204

    def real_run_split(self):
        """Part 2's block holds four areas of 122, 36, 30 and 20 files (208); parts 1 and 2 read the rest."""
        base = {a.name: a for a in base_areas()}
        rules = select("rules/")
        cuts = [0, 122, 244, 366, 468, 590, 610]
        piece = [rules_range("rules-%d" % (i + 1), rules[cuts[i]], rules[cuts[i + 1] - 1]) for i in range(6)]
        head = [base[n] for n in ("root", "api-top", "api-accounts", "api-billing", "api-plazas", "api-trips", "cli", "docs", "jobs", "scripts-zones")]
        areas = head + piece[:4] + [piece[4], piece[5], base["tests"], base["web"]]
        self.assertEqual([a.count for a in areas[-4:]], [122, 20, 36, 30])
        return build_parts(areas, cuts=(11, 14))

    def test_the_real_runs_four_areas_summing_to_208_pass_with_208(self):
        self.assertIn("Areas not read: 4 areas, 208 files;", self.real_run_split()["part-2.md"])
        self.assertProved(self.real_run_split())

    def test_the_real_runs_wrong_sum_of_204_fails_naming_the_part_both_counts_and_both_totals(self):
        parts = edit(self.real_run_split(), "part-2.md", "Areas not read: 4 areas, 208 files;", "Areas not read: 4 areas, 204 files;")
        out = self.assertFails(parts, r"^part-2\.md: Coverage says 4 areas, 204 files not read; the block holds 4 areas, 208 files$")
        self.assertEqual(sum(1 for line in out.splitlines() if "Coverage says" in line), 1, out)

    def test_coverage_areas_not_read_line_missing_in_a_part_with_a_block(self):
        parts = edit(self.parts, "part-2.md", "Areas not read: 4 areas", "Areas left: 4 areas")
        self.assertFails(parts, r"part-2\.md: no line 'Areas not read: <n> areas, <m> files; see SWEEP IN PARTS at the top\.'")

    # ---- Areas read

    def test_areas_read_header_missing(self):
        parts = edit(self.parts, "part-2.md", "Areas read:\n", "")
        self.assertFails(parts, r"part-2\.md: no 'Areas read:' line in Coverage")

    def test_areas_read_header_with_other_case(self):
        parts = edit(self.parts, "part-2.md", "Areas read:\n", "Areas Read:\n")
        self.assertFails(parts, r"part-2\.md: no 'Areas read:' line in Coverage")

    def test_areas_read_with_no_area_lines_under_it(self):
        parts = edit(self.parts, "part-3.md", "Areas read:\n" + "\n".join(a.line() for a in base_areas()[13:]), "Areas read:")
        self.assertFails(parts, r"part-3\.md: 'Areas read:' has no area lines under it")

    # ---- Whole repo

    def test_part_1_whole_repo_with_the_wrong_tracked_count(self):
        parts = edit(self.parts, "part-1.md", "990 tracked files", "989 tracked files")
        self.assertFails(parts, r"part-1\.md: Whole repo expected 990 tracked, 40 skipped whole, 3 untracked; found 989, 40, 3")

    def test_part_1_whole_repo_with_the_wrong_skipped_count(self):
        parts = edit(self.parts, "part-1.md", "40 in folders skipped whole", "41 in folders skipped whole")
        self.assertFails(parts, r"part-1\.md: Whole repo expected 990 tracked, 40 skipped whole, 3 untracked; found 990, 41, 3")

    def test_part_1_whole_repo_with_the_wrong_untracked_count(self):
        parts = edit(self.parts, "part-1.md", "3 untracked", "2 untracked")
        self.assertFails(parts, r"part-1\.md: Whole repo expected 990 tracked, 40 skipped whole, 3 untracked; found 990, 40, 2")

    def test_part_1_whole_repo_naming_only_two_of_the_three_untracked_paths(self):
        parts = edit(self.parts, "part-1.md", ", zones/zz_todo.txt", "")
        self.assertFails(parts, r"part-1\.md: Whole repo should name the untracked paths; missing zones/zz_todo\.txt")

    def test_part_1_whole_repo_naming_none_of_the_untracked_paths(self):
        parts = edit(self.parts, "part-1.md", " (%s)" % ", ".join(UNTRACKED), "")
        out = self.assertFails(parts, r"part-1\.md: Whole repo should name the untracked paths; missing")
        for p in UNTRACKED:
            self.assertIn(p, out)

    def test_part_1_whole_repo_giving_the_wrong_per_folder_count(self):
        parts = edit(self.parts, "part-1.md", "web/vendor/: 40", "web/vendor/: 39")
        self.assertFails(parts, r"part-1\.md: Whole repo should give 'web/vendor/: 40'")

    def test_part_1_whole_repo_not_naming_the_skipped_folder(self):
        parts = edit(self.parts, "part-1.md", "web/vendor/: 40, vendored", "vendored")
        self.assertFails(parts, r"part-1\.md: Whole repo should give 'web/vendor/: 40'")

    def test_part_1_whole_repo_line_missing(self):
        parts = edit(self.parts, "part-1.md", WHOLE_1 + "\n", "")
        self.assertFails(parts, r"part-1\.md: no 'Whole repo:' line in Coverage")

    def test_part_1_whole_repo_given_in_the_later_parts_wording(self):
        parts = edit(self.parts, "part-1.md", WHOLE_1, WHOLE_LATER)
        self.assertFails(parts, r"part-1\.md: Whole repo line should read")

    def test_untracked_paths_repeated_in_part_2s_whole_repo_line(self):
        # the line's shape still fails; the mention of the untracked path is only a note
        parts = edit(self.parts, "part-2.md", WHOLE_LATER, "Whole repo: given in part 1; untracked: notes/scratch.md")
        out = self.assertFails(parts, r"part-2\.md: expected 'Whole repo: given in part 1\.'")
        self.assertNotIn("must name no untracked path", out)
        self.assertEqual(note_lines(out), [NOTE_2 % "notes/scratch.md"])

    def test_the_whole_repo_line_repeated_in_full_in_part_2(self):
        # the answer to "what does a part 2 with part 1's whole line get": the shape failure, plus the note
        parts = edit(self.parts, "part-2.md", WHOLE_LATER, WHOLE_1)
        out = self.assertFails(parts, r"part-2\.md: expected 'Whole repo: given in part 1\.', found 'Whole repo: 990 tracked files")
        self.assertNotIn("must name no untracked path", out)
        self.assertEqual(note_lines(out), [NOTE_2 % ", ".join(UNTRACKED)])
        self.assertEqual(len(out.splitlines()), 3, out)  # LOOP FAILED, the one failure, the one note

    def test_an_untracked_path_named_in_the_prose_of_part_3(self):
        parts = edit(self.parts, "part-3.md", "## Findings\n", "## Findings\nNote: zones/zz_todo.txt is not tracked.\n")
        code, out = run_script(parts)
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)
        self.assertEqual(note_lines(out), ["NOTE: part-3.md names an untracked path that only part 1 should list: zones/zz_todo.txt"])

    def test_a_later_part_that_says_something_else_for_whole_repo(self):
        parts = edit(self.parts, "part-3.md", WHOLE_LATER, "Whole repo: see part 1.")
        self.assertFails(parts, r"part-3\.md: expected 'Whole repo: given in part 1\.'")

    def test_a_later_part_with_no_whole_repo_line(self):
        parts = edit(self.parts, "part-3.md", WHOLE_LATER + "\n", "")
        self.assertFails(parts, r"part-3\.md: no 'Whole repo:' line in Coverage")


# ---------------------------------------------------------------- fix batch 1: what two real runs wrote
#
# The finished loop runs (outside the repo, so nothing here reads them) wrote `(root)` in backticks, the folder on the
# Whole repo line in backticks, untracked paths in the prose of later parts, a count of 8 over a block of 7, and a
# count with its read and skipped files inside the parentheses. The first three are tolerated now; the last two are not.

def backtick_root(area):
    return area.copy(definition=area.definition.replace("(root)", "`(root)`"))


def backtick_direct(area):
    return area.copy(definition=re.sub(r"`([^`]+/)` \(direct\)", r"`\1 (direct)`", area.definition))


def moved_last(*names):
    """The base split with the named areas moved to the end, so they sit in the blocks of parts 1 and 2 as well."""
    areas = base_areas()
    return [a for a in areas if a.name not in names] + [next(a for a in areas if a.name == n) for n in names]


def backticked_split():
    """Root and the direct files of api/ written the way the runs wrote them, in the blocks and under Areas read."""
    areas = moved_last("root", "api-top")
    areas[-2], areas[-1] = backtick_root(areas[-2]), backtick_direct(areas[-1])
    return build_parts(areas, cuts=(9, 12))


def with_prose(parts, name, text):
    return edit(parts, name, "## Findings\n", "## Findings\n%s\n" % text)


class BackticksOnRootAndDirectTest(Base):
    """`(root)` in backticks, and `` `src/ (direct)` ``, are read the same as the bare forms the notation shows."""

    def test_backticked_root_alone_is_proved_like_bare_root(self):
        areas = base_areas()
        areas[0] = backtick_root(areas[0])
        self.assertEqual(areas[0].definition, "`(root)`")
        self.assertEqual(self.assertProved(build_parts(areas)), self.assertProved(build_parts(base_areas())))

    def test_backticked_root_in_the_blocks_of_parts_1_and_2_is_proved(self):
        parts = backticked_split()
        self.assertIn("- root: `(root)` (6 files)", parts["part-1.md"].split("\nEND OF BLOCK\n")[0])
        self.assertIn("- api-top: `api/ (direct)` (", parts["part-2.md"].split("\nEND OF BLOCK\n")[0])
        self.assertProved(parts)

    def test_backticked_root_first_in_a_plus_definition(self):
        # the shape run 2 wrote: `(root)` + `docs/`, 18 files, as in the real run
        top = Area("top", "`(root)` + `docs/`", select(None) + select("docs/"))
        self.assertEqual(top.count, 18)
        areas = [top] + [a for a in base_areas() if a.name not in ("root", "docs")]
        self.assertProved(build_parts(areas, cuts=(9, 12)))

    def test_backticked_root_last_in_a_plus_definition(self):
        both = Area("top", "`api/` (direct) + `(root)`", select("api/", direct=True) + select(None))
        areas = [both] + [a for a in base_areas() if a.name not in ("root", "api-top")]
        self.assertProved(build_parts(areas, cuts=(9, 12)))

    def test_backticked_root_in_the_middle_of_a_plus_definition(self):
        top = Area("top", "`api/` (direct) + `(root)` + `docs/`", select("api/", direct=True) + select(None) + select("docs/"))
        areas = [top] + [a for a in base_areas() if a.name not in ("root", "api-top", "docs")]
        self.assertProved(build_parts(areas, cuts=(8, 11)))

    def test_backticked_root_joined_without_the_plus_spaces_is_still_not_the_notation(self):
        top = Area("top", "`(root)`+`docs/`", select(None) + select("docs/"))
        areas = [top] + [a for a in base_areas() if a.name not in ("root", "docs")]
        self.assertFails(build_parts(areas, cuts=(9, 12)), r"area 'top': expected ' \+ ' between pieces")

    def test_backticked_root_with_an_except_piece(self):
        areas = base_areas()
        areas[0] = Area("root", "`(root)` except `docs/`", select(None, excepts=["docs/"]))
        self.assertProved(build_parts(areas))

    def test_backticked_root_over_a_range_of_its_files(self):
        roots = select(None)
        r1 = Area("root-1", "`(root)` from `%s` to `%s`" % (roots[0], roots[2]), select(None, lo=roots[0], hi=roots[2]))
        r2 = Area("root-2", "`(root)` from `%s` to `%s`" % (roots[3], roots[-1]), select(None, lo=roots[3], hi=roots[-1]))
        self.assertEqual(r1.count + r2.count, len(roots))
        self.assertProved(build_parts([r1, r2] + base_areas()[1:], cuts=(11, 14)))

    def test_backticked_root_with_an_except_and_a_range_together(self):
        roots = select(None)
        areas = base_areas()
        areas[0] = Area("root", "`(root)` except `docs/` from `%s` to `%s`" % (roots[0], roots[-1]), roots)
        self.assertProved(build_parts(areas))

    def test_backticked_root_rebuilds_to_the_same_file_set_and_count_as_bare_root(self):
        areas = base_areas()
        areas[0] = backtick_root(areas[0])
        self.assertIn("files covered: 950 of 950", self.assertProved(build_parts(areas)))

    def test_backticked_root_with_a_wrong_count_fails_with_both_numbers(self):
        areas = base_areas()
        areas[0] = backtick_root(areas[0]).copy(count=len(select(None)) + 1)
        self.assertFails(build_parts(areas), r"area 'root': stated 7 files, the definition rebuilds to 6")

    def test_a_backticked_root_area_dropped_leaves_its_files_in_no_area(self):
        areas = [a for a in base_areas() if a.name != "root"]
        self.assertFails(build_parts(areas, cuts=(9, 12)), r"exactly once: .* 6 are in no area read: CHANGELOG\.md")

    def test_a_made_up_word_in_the_root_backticks_is_not_the_notation(self):
        areas = base_areas()
        areas[0] = areas[0].copy(definition="`(roots)`")
        self.assertFails(build_parts(areas), r"area 'root': cannot read a piece at '`\(roots\)`'")

    def test_the_direct_word_inside_the_folders_backticks_is_proved_like_outside(self):
        areas = base_areas()
        areas[1] = backtick_direct(areas[1])
        self.assertEqual(areas[1].definition, "`api/ (direct)`")
        self.assertEqual(self.assertProved(build_parts(areas)), self.assertProved(build_parts(base_areas())))

    def test_the_direct_word_inside_the_backticks_next_to_other_pieces(self):
        both = Area("top", "`api/ (direct)` + `(root)`", select("api/", direct=True) + select(None))
        areas = [both] + [a for a in base_areas() if a.name not in ("root", "api-top")]
        self.assertProved(build_parts(areas, cuts=(9, 12)))

    def test_the_direct_word_inside_the_backticks_with_a_range(self):
        areas = base_areas()
        areas[9] = backtick_direct(areas[9])
        self.assertIn("`rules/ (direct)` from", areas[9].definition)
        self.assertProved(build_parts(areas))

    def test_the_direct_word_inside_the_backticks_still_means_direct(self):
        # stated as every file under api/, the count is wrong: the piece is the direct files only
        areas = base_areas()
        every = len(select("api/"))
        areas[1] = backtick_direct(areas[1]).copy(count=every)
        self.assertFails(build_parts(areas), r"area 'api-top': stated %d files, the definition rebuilds to %d" % (every, len(areas[1].files)))

    def test_a_misspelled_direct_inside_the_backticks_is_not_the_notation(self):
        areas = base_areas()
        areas[1] = areas[1].copy(definition="`api/ (directly)`")
        self.assertFails(build_parts(areas), r"area 'api-top': cannot read a piece at '`api/ \(directly\)`'")

    def test_direct_with_a_backtick_on_both_sides_is_not_the_notation(self):
        areas = base_areas()
        areas[1] = areas[1].copy(definition="`api/` (direct)`")
        self.assertFails(build_parts(areas), r"area 'api-top': expected ' \+ ' between pieces at '`'")

    def test_direct_inside_the_backticks_without_the_space_is_not_the_notation(self):
        areas = base_areas()
        areas[1] = areas[1].copy(definition="`api/(direct)`")
        self.assertFails(build_parts(areas), r"area 'api-top': cannot read a piece")


class WholeRepoFolderTest(Base):
    """The `Whole repo:` folder may be in backticks; the reason is free; the count and the folder are not."""

    def whole(self, inner, tail=" (%s)" % ", ".join(UNTRACKED)):
        return "Whole repo: 990 tracked files; 40 in folders skipped whole (%s); 3 untracked%s" % (inner, tail)

    def with_line(self, line):
        return edit(build_parts(base_areas()), "part-1.md", WHOLE_1, line)

    def with_inner(self, inner):
        return self.with_line(self.whole(inner))

    def test_the_folder_in_backticks_is_proved(self):
        self.assertProved(self.with_inner("`web/vendor/`: 40, vendored"))

    def test_the_folder_without_backticks_is_proved(self):
        self.assertProved(self.with_inner("web/vendor/: 40, vendored"))

    def test_the_two_spellings_give_the_same_output(self):
        self.assertEqual(self.assertProved(self.with_inner("`web/vendor/`: 40, x")), self.assertProved(self.with_inner("web/vendor/: 40, x")))

    def test_the_reason_may_be_any_text_with_or_without_backticks(self):
        for reason in ("vendored third-party code the README says not to edit", "third party; do not edit", "a, b, c", "x",
                       "see `web/README.md` (vendored)", "says: 39 files were here once", "40 files"):
            for folder in ("`web/vendor/`", "web/vendor/"):
                with self.subTest(folder=folder, reason=reason):
                    self.assertProved(self.with_inner("%s: 40, %s" % (folder, reason)))

    def test_no_reason_at_all_is_proved_either_way(self):
        self.assertProved(self.with_inner("`web/vendor/`: 40"))
        self.assertProved(self.with_inner("web/vendor/: 40"))

    def test_a_wrong_count_fails_in_backticks_with_the_message_the_brief_quotes(self):
        self.assertFails(self.with_inner("`web/vendor/`: 39, vendored"),
                         r"^part-1\.md: Whole repo should give 'web/vendor/: 40' inside the parentheses, found '`web/vendor/`: 39, vendored'$")

    def test_a_folder_count_too_long_to_convert_fails_with_the_sites_own_message_and_does_not_raise(self):
        for folder in ("`web/vendor/`", "web/vendor/"):
            with self.subTest(folder=folder):
                code, out = run_script(self.with_inner("%s: %s, vendored" % (folder, "9" * 5000)))
                self.assertEqual((code, out.splitlines()[0]), (1, "LOOP FAILED"), out[:300])
                self.assertNotIn("internal error", out)
                self.assertRegex(out, r"part-1\.md: Whole repo should give 'web/vendor/: 40' inside the parentheses")

    def test_a_wrong_count_fails_without_backticks(self):
        self.assertFails(self.with_inner("web/vendor/: 39, vendored"), r"part-1\.md: Whole repo should give 'web/vendor/: 40' inside the parentheses")

    def test_a_longer_count_that_starts_with_40_fails_either_way(self):
        for folder in ("`web/vendor/`", "web/vendor/"):
            with self.subTest(folder=folder):
                self.assertFails(self.with_inner("%s: 400, vendored" % folder), r"Whole repo should give 'web/vendor/: 40'")

    def test_a_missing_folder_fails_whatever_the_reason(self):
        for inner in ("vendored third-party code", "`vendored`: 40", "40, vendored"):
            with self.subTest(inner=inner):
                self.assertFails(self.with_inner(inner), r"part-1\.md: Whole repo should give 'web/vendor/: 40'")

    def test_the_wrong_folder_fails_even_with_the_right_count(self):
        self.assertFails(self.with_inner("`web/other/`: 40, vendored"), r"Whole repo should give 'web/vendor/: 40'")

    def test_the_untracked_paths_on_lines_under_the_whole_repo_line_are_read_as_both_runs_wrote_them(self):
        one = self.whole("`web/vendor/`: 40, vendored third-party code", tail=".") + "\n- Untracked, unread: " + ", ".join("`%s`" % p for p in UNTRACKED)
        self.assertProved(self.with_line(one))
        two = (self.whole("`web/vendor/`: 40, vendored third-party code the README says not to edit", tail=", unread:") + "\n"
               + "\n".join("- `%s`" % p for p in UNTRACKED))
        self.assertProved(self.with_line(two))

    def test_part_1_must_still_name_every_untracked_path_with_a_backticked_folder(self):
        line = self.whole("`web/vendor/`: 40, vendored", tail=" (notes/scratch.md, zones/zz_todo.txt)")
        self.assertFails(self.with_line(line), r"part-1\.md: Whole repo should name the untracked paths; missing rules/r9999_draft\.py")

    def test_part_1_must_still_name_every_untracked_path_when_the_lines_under_it_leave_one_out(self):
        one = self.whole("`web/vendor/`: 40, x", tail=".") + "\n- Untracked, unread: `notes/scratch.md`, `zones/zz_todo.txt`"
        self.assertFails(self.with_line(one), r"missing rules/r9999_draft\.py")

    def test_part_1_naming_none_of_them_fails_with_a_backticked_folder(self):
        line = self.whole("`web/vendor/`: 40, vendored", tail="")
        self.assertFails(self.with_line(line), r"part-1\.md: Whole repo should name the untracked paths; missing notes/scratch\.md, rules/r9999_draft\.py, zones/zz_todo\.txt")

    def test_a_path_inside_a_longer_path_is_not_naming_the_untracked_one(self):
        line = self.whole("`web/vendor/`: 40, x", tail=" (mynotes/scratch.md, rules/r9999_draft.py, zones/zz_todo.txt)")
        self.assertFails(self.with_line(line), r"missing notes/scratch\.md")

    def test_the_numbers_are_still_exact_with_a_backticked_folder(self):
        line = self.whole("`web/vendor/`: 40, x").replace("990 tracked", "989 tracked")
        self.assertFails(self.with_line(line), r"Whole repo expected 990 tracked, 40 skipped whole, 3 untracked; found 989, 40, 3")


class StillStrictTest(Base):
    """What the two real runs got wrong stays a failure, with the message the brief quotes."""

    def count_slip(self, parts, line_1=8, coverage=None):
        parts = edit(parts, "part-1.md", "SWEEP IN PARTS: 7 areas not read", "SWEEP IN PARTS: %d areas not read" % line_1)
        if coverage is not None:
            parts = edit(parts, "part-1.md", "Areas not read: 7 areas,", "Areas not read: %d areas," % coverage)
        return parts

    def test_line_1_saying_8_against_a_block_of_7_fails_with_the_brief_message(self):
        self.assertFails(self.count_slip(build_parts(base_areas())), r"^part-1\.md: the SWEEP IN PARTS line says 8 areas, the block holds 7 area lines$")

    def test_line_1_and_coverage_both_saying_8_still_fails_as_in_run_2(self):
        parts = self.count_slip(build_parts(base_areas()), coverage=8)
        parts = edit(parts, "part-1.md", "\nWhole repo:", "\nThe block at the top lists seven areas, but the heading says eight.\n\nWhole repo:")
        self.assertFails(parts, r"^part-1\.md: the SWEEP IN PARTS line says 8 areas, the block holds 7 area lines$")

    def test_line_1_saying_6_against_a_block_of_7_fails_too(self):
        self.assertFails(self.count_slip(build_parts(base_areas()), line_1=6), r"part-1\.md: the SWEEP IN PARTS line says 6 areas, the block holds 7 area lines")

    def test_a_count_off_by_one_in_a_later_part_fails_too(self):
        parts = edit(build_parts(base_areas()), "part-2.md", "SWEEP IN PARTS: 4 areas not read", "SWEEP IN PARTS: 5 areas not read")
        self.assertFails(parts, r"part-2\.md: the SWEEP IN PARTS line says 5 areas, the block holds 4 area lines")

    def test_the_real_run_1_area_line_fails_with_the_message_the_brief_quotes(self):
        top = Area("top", "`(root)` + `scripts/` + `tests/` + `zones/`", select(None) + select("scripts/") + select("tests/") + select("zones/"))
        self.assertEqual(top.count, 70)
        areas = [top] + [a for a in base_areas() if a.name not in ("root", "scripts-zones", "tests")]
        parts = build_parts(areas, cuts=(9, 12))
        self.assertProved(parts)  # the same split with the count alone in the parentheses
        real = "- top: `(root)` + `scripts/` + `tests/` + `zones/` (70 files; 69 read, `poetry.lock` skipped)"
        self.assertFails(edit(parts, "part-1.md", top.line(), real),
                         r"^part-1\.md: area line does not match '- <name>: <definition> \(<n> files\)': '- top: `\(root\)` \+ `scripts/` \+ `tests/` \+ `zones/` \(70 files; 69 read, `poetry\.lock` skipped\)'$")

    def test_anything_but_the_count_in_the_parentheses_fails(self):
        base = build_parts(base_areas())
        for extra in ("; 69 read", ", 1 skipped", " read", " (1 skipped)", "; 5 read, `poetry.lock` skipped"):
            with self.subTest(extra=extra):
                parts = edit_all(base, lambda t: t.replace("(6 files)", "(6 files%s)" % extra))
                self.assertFails(parts, r"part-1\.md: area line does not match '- <name>: <definition> \(<n> files\)'")

    def test_the_bare_number_in_the_parentheses_fails(self):
        self.assertFails(edit_all(build_parts(base_areas()), lambda t: t.replace("(6 files)", "(6)")), r"area line does not match")

    def test_extra_text_after_the_parentheses_fails(self):
        self.assertFails(edit_all(build_parts(base_areas()), lambda t: t.replace("(6 files)", "(6 files) read")), r"area line does not match")

    def test_extra_text_in_the_parentheses_of_a_block_line_fails_too(self):
        parts = edit(build_parts(base_areas()), "part-1.md", "- web: `web/` except `web/vendor/` (30 files)\nEND OF BLOCK",
                     "- web: `web/` except `web/vendor/` (30 files; none read)\nEND OF BLOCK")
        self.assertFails(parts, r"part-1\.md: area line does not match '- <name>: <definition> \(<n> files\)': '- web: `web/` except `web/vendor/` \(30 files; none read\)'")

    def test_the_continuation_of_run_2s_count_slip_does_not_rescue_a_wrong_coverage_line(self):
        # Areas not read says 8 and the block holds 7: the check against the block's lines still runs on Coverage
        parts = edit(build_parts(base_areas()), "part-1.md", "Areas not read: 7 areas,", "Areas not read: 8 areas,")
        self.assertFails(parts, r"part-1\.md: Coverage says 8 areas, \d+ files not read; the block holds 7 areas, \d+ files")


class UntrackedNoteTest(Base):
    """A later part that names an untracked path gets a NOTE, which changes neither the exit code nor the verdict word."""

    def test_the_note_has_the_exact_text(self):
        out = run_script(with_prose(build_parts(base_areas()), "part-2.md", "The file notes/scratch.md is not tracked."))[1]
        self.assertEqual(note_lines(out), ["NOTE: part-2.md names an untracked path that only part 1 should list: notes/scratch.md"])

    def test_the_note_lists_every_path_named_comma_separated_in_the_keys_order(self):
        out = run_script(with_prose(build_parts(base_areas()), "part-3.md", "zones/zz_todo.txt, rules/r9999_draft.py and notes/scratch.md are untracked."))[1]
        self.assertEqual(note_lines(out), ["NOTE: part-3.md names an untracked path that only part 1 should list: " + ", ".join(UNTRACKED)])

    def test_the_note_never_changes_the_exit_code_or_the_verdict_word(self):
        code, out = run_script(with_prose(build_parts(base_areas()), "part-2.md", "notes/scratch.md"))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "LOOP PROVED")
        self.assertNotIn("LOOP FAILED", out)
        self.assertEqual(out.splitlines()[1].split(";")[0], "parts: 3")

    def test_the_note_leaves_the_summary_line_what_it_was(self):
        plain = run_script(build_parts(base_areas()))[1]
        noted = run_script(with_prose(build_parts(base_areas()), "part-2.md", "notes/scratch.md"))[1]
        self.assertEqual(noted.splitlines()[:2], plain.splitlines()[:2])
        self.assertEqual(len(noted.splitlines()), 3)

    def test_the_note_beside_a_real_failure_keeps_exit_1_and_the_failed_verdict(self):
        parts = edit(with_prose(build_parts(base_areas()), "part-2.md", "notes/scratch.md"), "part-1.md", "990 tracked files", "989 tracked files")
        code, out = run_script(parts)
        self.assertEqual((code, out.splitlines()[0]), (1, "LOOP FAILED"), out)
        self.assertEqual(len(note_lines(out)), 1)
        self.assertNotIn("must name no untracked path", out)
        self.assertTrue(out.splitlines()[-1].startswith("NOTE:"), out)  # failures first, notes last

    def test_each_later_part_that_names_one_gets_its_own_note_in_part_order(self):
        parts = with_prose(with_prose(build_parts(base_areas()), "part-2.md", "notes/scratch.md"), "part-3.md", "zones/zz_todo.txt")
        out = run_script(parts)[1]
        self.assertEqual(note_lines(out), [NOTE_2 % "notes/scratch.md", "NOTE: part-3.md names an untracked path that only part 1 should list: zones/zz_todo.txt"])

    def test_part_1_naming_them_gets_no_note(self):
        out = run_script(build_parts(base_areas()))[1]
        self.assertEqual(note_lines(out), [])
        self.assertEqual(len(out.strip().splitlines()), 2)

    def test_a_part_naming_none_gets_no_note(self):
        self.assertEqual(note_lines(run_script(with_prose(build_parts(base_areas()), "part-2.md", "nothing untracked here"))[1]), [])

    def test_a_path_inside_a_longer_path_is_not_a_mention(self):
        out = run_script(with_prose(build_parts(base_areas()), "part-2.md", "see mynotes/scratch.md and docs/zones/zz_todo.txt and notes/scratch.md-old"))[1]
        self.assertEqual(note_lines(out), [])

    def test_a_backticked_path_is_a_mention(self):
        out = run_script(with_prose(build_parts(base_areas()), "part-2.md", "the untracked `rules/r9999_draft.py`."))[1]
        self.assertEqual(note_lines(out), [NOTE_2 % "rules/r9999_draft.py"])

    def test_the_note_sits_with_the_part_size_notes_at_the_end_of_the_output(self):
        code, out = run_script(with_prose(build_parts(base_areas()), "part-2.md", "notes/scratch.md"), extra=["--part-size", "490"])
        lines = out.splitlines()
        self.assertEqual((code, lines[0]), (0, "LOOP PROVED"), out)
        self.assertEqual(len(note_lines(out)), 3)  # the untracked one and the two "could have held the next area" notes
        self.assertTrue(all(l.startswith("NOTE:") for l in lines[2:]), out)
        self.assertIn(NOTE_2 % "notes/scratch.md", lines)

    def test_the_note_sits_with_the_part_size_notes_when_the_run_fails(self):
        parts = edit(with_prose(build_parts(base_areas()), "part-3.md", "zones/zz_todo.txt"), "part-1.md", "Mode: full sweep, 10 area leads", "Mode: full sweep, 7 area leads")
        code, out = run_script(parts, extra=["--part-size", "490"])
        lines = out.splitlines()
        self.assertEqual((code, lines[0]), (1, "LOOP FAILED"), out)
        notes = [i for i, l in enumerate(lines) if l.startswith("NOTE:")]
        self.assertEqual(len(notes), 3, out)
        self.assertEqual(notes, list(range(len(lines) - 3, len(lines))), out)

    def test_a_part_whose_block_cannot_be_read_gets_no_note_and_no_old_failure(self):
        parts = edit(with_prose(build_parts(base_areas()), "part-3.md", "zones/zz_todo.txt"), "part-3.md", "SWEEP IN PARTS: 0 areas not read", "no sweep line")
        code, out = run_script(parts)
        self.assertEqual(code, 1, out)
        self.assertNotIn("must name no untracked path", out)

    @unittest.skipUnless(Path("/usr/bin/python3").exists(), "no stock python")
    def test_the_stock_python_prints_the_same_note(self):
        parts = with_prose(build_parts(base_areas()), "part-2.md", "notes/scratch.md")
        code, out, err = run_script_at(SCRIPT, parts, python="/usr/bin/python3")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(note_lines(out), [NOTE_2 % "notes/scratch.md"])


class RealRunShapesTest(Base):
    """Lines copied from the two finished runs (loop-1 and loop-2), set into synthetic parts: the shapes a model really wrote."""

    def run1(self):
        top = Area("top", "`(root)` + `scripts/` + `tests/` + `zones/`", select(None) + select("scripts/") + select("tests/") + select("zones/"))
        areas = [top] + [a for a in base_areas() if a.name not in ("root", "scripts-zones", "tests")]
        return build_parts(areas, cuts=(9, 12))

    def test_run_1_whole_repo_lines_and_the_untracked_prose_of_parts_2_and_3(self):
        parts = edit(self.run1(), "part-1.md", WHOLE_1,
                     "Whole repo: 990 tracked files; 40 in folders skipped whole (`web/vendor/`: 40, vendored third-party code); 3 untracked.\n"
                     "- Untracked, unread: `notes/scratch.md`, `rules/r9999_draft.py`, `zones/zz_todo.txt`")
        parts = with_prose(parts, "part-2.md",
                           "- Not covered in this part. No plan file is known beyond `CHANGELOG.md`, `docs/`, and the untracked `notes/scratch.md` and `parts/part-1.md`. I did not read these here.\n"
                           "- **Untracked `rules/r9999_draft.py`.** It is not tracked, so I did not read it. See Coverage.")
        parts = with_prose(parts, "part-3.md", "- `notes/` and `parts/` (`notes/scratch.md`, `parts/part-1.md`, `parts/part-2.md`) are untracked and were not read.")
        code, out = run_script(parts)
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)
        self.assertEqual(note_lines(out), [NOTE_2 % "notes/scratch.md, rules/r9999_draft.py",
                                           "NOTE: part-3.md names an untracked path that only part 1 should list: notes/scratch.md"])

    def test_run_1_area_line_with_the_count_alone_is_proved(self):
        parts = self.run1()
        self.assertIn("- top: `(root)` + `scripts/` + `tests/` + `zones/` (70 files)", parts["part-1.md"])
        self.assertProved(parts)

    def test_run_2_area_line_whole_repo_line_and_untracked_prose_of_part_3(self):
        top = Area("top", "`(root)` + `docs/`", select(None) + select("docs/"))
        areas = [top] + [a for a in base_areas() if a.name not in ("root", "docs")]
        parts = build_parts(areas, cuts=(9, 12))
        self.assertIn("- top: `(root)` + `docs/` (18 files)", parts["part-1.md"])
        parts = edit(parts, "part-1.md", WHOLE_1,
                     "Whole repo: 990 tracked files; 40 in folders skipped whole (`web/vendor/`: 40, vendored third-party code the README says not to edit); 3 untracked, unread:\n"
                     "- `notes/scratch.md`\n- `rules/r9999_draft.py`\n- `zones/zz_todo.txt`")
        parts = with_prose(parts, "part-3.md",
                           "- The untracked `notes/scratch.md` and `parts/part-1.md` and `parts/part-2.md` were not read.\n"
                           "- **Untracked files:** `rules/r9999_draft.py` and `zones/zz_todo.txt` are untracked and were not read.")
        code, out = run_script(parts)
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)
        self.assertEqual(note_lines(out), ["NOTE: part-3.md names an untracked path that only part 1 should list: " + ", ".join(UNTRACKED)])


class FixBatch3RunShapesTest(Base):
    """Run 7 and run 8 of the loop, set into synthetic parts: a skipped file left out of the counts, and the working on the Areas not read line."""

    def test_a_last_part_that_leaves_its_skipped_binaries_out_of_files_listed_fails_on_the_sum_and_on_the_skipped_total(self):
        # run 7: the last part's areas add up to more than its Files listed, which says `skipped: 0`
        parts = build_parts(base_areas())
        listed, read, skipped = listed_of(parts["part-3.md"])[:3]
        self.assertGreater(skipped, 0)  # the base part 3 holds the web/ binaries
        left_out = set_listed(parts, "part-3.md", listed=listed - skipped, read=listed - skipped, skipped=0)
        total_skipped = sum(listed_of(left_out["part-%d.md" % n])[2] for n in (1, 2, 3))
        out = self.assertFails(left_out,
                               r"^part-3\.md: Files listed %d should equal the sum of its areas' counts, %d$" % (listed - skipped, listed),
                               r"^read: the skipped numbers add up to %d, expected 5 \(the key's file_skips\)$" % total_skipped)
        self.assertNotIn("should equal read+skipped+failed+unread", out)  # the line's own arithmetic is fine

    def test_an_areas_not_read_line_with_the_working_in_place_of_the_number_is_not_the_areas_not_read_line(self):
        # run 8: `Areas not read: 5 areas, 488 + 66 = 554 files; see SWEEP IN PARTS at the top.`
        parts = build_parts(base_areas())
        m = re.search(r"^Areas not read: (\d+) areas, (\d+) files; see SWEEP IN PARTS at the top\.$", parts["part-1.md"], flags=re.M)
        n, total = int(m.group(1)), int(m.group(2))
        a, b = total - 66, 66
        working = "Areas not read: %d areas, %d + %d = %d files; see SWEEP IN PARTS at the top." % (n, a, b, total)
        parts = edit(parts, "part-1.md", m.group(0), working)
        self.assertIn(working, parts["part-1.md"])
        self.assertFails(parts, r"^part-1\.md: no line 'Areas not read: <n> areas, <m> files; see SWEEP IN PARTS at the top\.' in Coverage$")


class FixBatch1MutationTest(Base):
    """A temp copy of the script with one tolerance undone must behave differently from the script on a part that needs it."""

    @classmethod
    def setUpClass(cls):
        cls.src = SCRIPT.read_text(encoding="utf-8")
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def mutant(self, name, old, new):
        self.assertEqual(self.src.count(old), 1, "the script no longer has %r once; update this mutation" % old)
        path = Path(self.tmp.name) / (name + ".py")
        path.write_text(self.src.replace(old, new), encoding="utf-8")
        return path

    def pair(self, mutant, parts):
        return run_script_at(SCRIPT, parts), run_script_at(mutant, parts)

    def test_the_unmutated_copy_behaves_as_the_script_does(self):
        copy = Path(self.tmp.name) / "same.py"
        copy.write_text(self.src, encoding="utf-8")
        parts = backticked_split()
        self.assertEqual(run_script_at(copy, parts), run_script_at(SCRIPT, parts))

    def test_making_the_untracked_mention_a_failure_again_is_caught(self):
        m = self.mutant("mention", "later_named.append(", "fails.append(")
        real, mutated = self.pair(m, with_prose(build_parts(base_areas()), "part-3.md", "zones/zz_todo.txt"))
        self.assertEqual((real[0], mutated[0]), (0, 1), mutated[1])
        self.assertTrue(mutated[1].startswith("LOOP FAILED"))

    def test_dropping_the_backtick_tolerance_for_root_is_caught(self):
        m = self.mutant("noroot", "|`?(?P<root>\\(root\\))`?)", "|(?P<root>\\(root\\)))")
        real, mutated = self.pair(m, backticked_split())
        self.assertEqual((real[0], mutated[0]), (0, 1), mutated[1])
        self.assertIn("cannot read a piece at '`(root)`", mutated[1])
        self.assertEqual(run_script_at(m, build_parts(base_areas()))[0], 0)  # the bare form still parses in the mutant

    def test_dropping_the_backtick_tolerance_for_the_whole_repo_folder_is_caught(self):
        m = self.mutant("nofolder", 're.escape(folder) + r"`?:\\s*(\\d+)"', 're.escape(folder) + r":\\s*(\\d+)"')
        parts = edit(build_parts(base_areas()), "part-1.md", WHOLE_1, WHOLE_1.replace("(web/vendor/: 40", "(`web/vendor/`: 40"))
        real, mutated = self.pair(m, parts)
        self.assertEqual((real[0], mutated[0]), (0, 1), mutated[1])
        self.assertIn("Whole repo should give 'web/vendor/: 40'", mutated[1])
        self.assertEqual(run_script_at(m, build_parts(base_areas()))[0], 0)  # the bare folder still reads in the mutant

    def test_dropping_the_direct_inside_the_backticks_tolerance_is_caught(self):
        m = self.mutant("nodirect", "| \\((?P<inner>direct)\\)`)", ")")
        areas = base_areas()
        areas[1] = backtick_direct(areas[1])
        real, mutated = self.pair(m, build_parts(areas))
        self.assertEqual(real[0], 0, real[1])
        self.assertNotEqual(mutated[0], 0, mutated[1])  # this mutant removes a named group the code still reads, so it may crash (2) rather than fail (1)

    def test_reading_the_direct_inside_the_backticks_as_not_direct_is_caught(self):
        m = self.mutant("notdirect", '(m.group("direct") or m.group("inner")) is not None', 'm.group("direct") is not None')
        areas = base_areas()
        areas[1] = backtick_direct(areas[1])
        real, mutated = self.pair(m, build_parts(areas))
        self.assertEqual((real[0], mutated[0]), (0, 1), mutated[1])
        self.assertIn("area 'api-top': stated", mutated[1])

    def test_dropping_the_count_against_the_block_check_is_caught(self):
        m = self.mutant("nocount", "if len(areas) != n:", "if False:")
        parts = edit(build_parts(base_areas()), "part-1.md", "SWEEP IN PARTS: 7 areas not read", "SWEEP IN PARTS: 8 areas not read")
        real, mutated = self.pair(m, parts)
        self.assertEqual(real[0], 1, real[1])
        self.assertNotEqual(mutated[1], real[1])
        self.assertNotIn("the block holds 7 area lines", mutated[1])

    def test_loosening_the_parentheses_to_take_extra_text_is_caught(self):
        m = self.mutant("loose", 'AREA_RE = re.compile(r"^- ([^:]+?): (.+) \\((\\d+) files\\)$")', 'AREA_RE = re.compile(r"^- ([^:]+?): (.+) \\((\\d+) files[^)]*\\)$")')
        parts = edit_all(build_parts(base_areas()), lambda t: t.replace("(6 files)", "(6 files; 5 read)"))
        real, mutated = self.pair(m, parts)
        self.assertEqual(real[0], 1)
        self.assertNotIn("area line does not match", mutated[1])

    def test_dropping_the_part_1_untracked_names_check_is_caught(self):
        m = self.mutant("noabsent", "if absent:", "if False:")
        real, mutated = self.pair(m, edit(build_parts(base_areas()), "part-1.md", ", zones/zz_todo.txt", ""))
        self.assertEqual((real[0], mutated[0]), (1, 0), real[1])

    def test_loosening_the_later_parts_whole_repo_line_is_caught(self):
        m = self.mutant("looseline", 'if lines[whole_at].strip().lstrip("- ").rstrip() != WHOLE_LATER:', "if False:")
        real, mutated = self.pair(m, edit(build_parts(base_areas()), "part-2.md", WHOLE_LATER, WHOLE_1))
        self.assertEqual((real[0], mutated[0]), (1, 0), real[1])


class FactsTest(Base):
    def setUp(self):
        self.parts = build_parts(base_areas())
        self.key = Fixture.key

    def holder(self, token):
        return [n for n, t in self.parts.items() if token in t]

    def test_a_fact_missing_from_every_part(self):
        fact = self.key["facts"][0]
        self.assertEqual(self.holder(fact["token"]), ["part-1.md"])
        parts = edit(self.parts, "part-1.md", "- %s found while reading.\n" % fact["token"], "")
        out = self.assertFails(parts, r"facts: f01 \(%s, in %s\) was not found in any part: expected %s"
                               % (fact["kind"], re.escape(fact["path"]), re.escape(repr(fact["token"]))))
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("facts:")]), 1)

    def test_every_one_of_the_33_facts_is_needed(self):
        for fact in self.key["facts"]:
            with self.subTest(fact=fact["id"]):
                parts = dict(self.parts)
                for name, text in parts.items():
                    parts[name] = text.replace(fact["token"], "REDACTED")
                code, out = run_script(parts)
                self.assertEqual(code, 1, out)
                self.assertRegex(out, r"facts: %s \(" % fact["id"])

    def test_a_fact_found_in_a_later_part_only_is_a_failure(self):
        # move every fact into part 3: the facts whose files parts 1 and 2 read no longer count
        parts = dict(self.parts)
        facts = "\n".join("- %s" % f["token"] for f in self.key["facts"])
        for name in ("part-1.md", "part-2.md"):
            for f in self.key["facts"]:
                parts[name] = parts[name].replace(f["token"], "REDACTED")
        parts["part-3.md"] = parts["part-3.md"].replace("## Findings\n", "## Findings\n" + facts + "\n")
        out = self.assertFails(parts, r"facts: f01 \(gotcha, in api/accounts/account\.py\) was not found in part-1\.md, the part that read the file; only part-3\.md held it")
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("facts:")]), len([f for f in self.key["facts"] if f["path"] not in
                                                                                         [x for a in base_areas()[13:] for x in a.files]]))

    def test_a_fact_found_in_its_own_part_and_mentioned_in_another_part_passes(self):
        fact = self.key["facts"][0]
        self.assertEqual(self.holder(fact["token"]), ["part-1.md"])
        parts = edit(self.parts, "part-3.md", "## Findings\n", "## Findings\n- also seen in passing: %s\n" % fact["token"])
        parts = edit(parts, "part-2.md", "## Findings\n", "## Findings\n- %s\n" % fact["token"])
        self.assertEqual(self.holder(fact["token"]), ["part-1.md"])  # setUp's parts are not touched
        self.assertProved(parts)

    def test_a_fact_inside_a_longer_word_is_not_found(self):
        # the found rule: the token must not touch letters or digits on either side
        fact = self.key["facts"][0]
        parts = edit(self.parts, "part-1.md", "- %s found" % fact["token"], "- X%sX found" % fact["token"])
        self.assertFails(parts, r"facts: f01 ")

    def test_a_fact_with_more_digits_after_it_is_not_found(self):
        fact = self.key["facts"][0]
        self.assertEqual(fact["token"], "ticket 6005")
        parts = edit(self.parts, "part-1.md", "- ticket 6005 found", "- ticket 60053 found")
        self.assertFails(parts, r"facts: f01 ")

    def test_a_fact_is_found_case_insensitively_across_odd_spacing(self):
        parts = edit(self.parts, "part-1.md", "- ticket 6005 found", "- TICKET\t6005 found")
        self.assertProved(parts)

    def test_a_decoy_present_in_a_part(self):
        decoy = self.key["decoys"][0]
        parts = edit(self.parts, "part-2.md", "## Findings\n", "## Findings\n- %s\n" % decoy["token"])
        self.assertFails(parts, r"decoys: d1 \(untracked, from notes/scratch\.md\) appears in part-2\.md: 'runbook section 2\.1'")

    def test_every_decoy_is_caught(self):
        for decoy in self.key["decoys"]:
            with self.subTest(decoy=decoy["id"]):
                parts = edit(self.parts, "part-3.md", "## Findings\n", "## Findings\n- see %s here\n" % decoy["token"])
                code, out = run_script(parts)
                self.assertEqual(code, 1, out)
                self.assertRegex(out, r"decoys: %s " % decoy["id"])

    def test_a_decoy_in_the_last_part_only(self):
        decoy = self.key["decoys"][4]
        parts = edit(self.parts, "part-3.md", "## Findings\n", "## Findings\n- %s\n" % decoy["token"])
        self.assertFails(parts, r"decoys: d5 .* part-3\.md")

    def test_a_decoy_with_different_case_is_still_a_decoy(self):
        parts = edit(self.parts, "part-1.md", "## Findings\n", "## Findings\n- RUNBOOK SECTION 2.1\n")
        self.assertFails(parts, r"decoys: d1 ")

    def test_a_decoy_in_two_parts_is_named_in_both(self):
        d = self.key["decoys"][1]["token"]
        parts = edit(self.parts, "part-1.md", "## Findings\n", "## Findings\n- %s\n" % d)
        parts = edit(parts, "part-3.md", "## Findings\n", "## Findings\n- %s\n" % d)
        self.assertFails(parts, r"decoys: d2 .* part-1\.md, part-3\.md")

    def test_a_decoy_hidden_inside_a_longer_word_is_not_a_decoy(self):
        # the found rule is the same for decoys: '#50520' glued to letters and digits is not present
        parts = edit(self.parts, "part-1.md", "## Findings\n", "## Findings\n- abc#505206\n")
        self.assertProved(parts)


# ---------------------------------------------------------------- tolerances and exactness, pinned as they stand

class ToleranceTest(Base):
    def setUp(self):
        self.parts = build_parts(base_areas())

    def test_trailing_spaces_on_every_line(self):
        self.assertProved(edit_all(self.parts, lambda t: t.replace("\n", "   \n")))

    def test_trailing_tabs_on_every_line(self):
        self.assertProved(edit_all(self.parts, lambda t: t.replace("\n", "\t\n")))

    def test_windows_line_endings(self):
        self.assertProved(edit_all(self.parts, lambda t: t.replace("\n", "\r\n")))

    def test_blank_lines_outside_the_block(self):
        self.assertProved(edit_all(self.parts, lambda t: t.replace("\n## ", "\n\n\n## ").replace("END OF BLOCK\n", "END OF BLOCK\n\n\n\n")))

    def test_blank_lines_after_the_last_line_of_a_part(self):
        self.assertProved(edit_all(self.parts, lambda t: t + "\n\n\n"))

    def test_a_missing_newline_at_the_end_of_a_part(self):
        self.assertProved(edit_all(self.parts, lambda t: t.rstrip("\n")))

    def test_a_leading_dash_on_the_coverage_lines(self):
        def bullets(t):
            for lead in ("Mode:", "Files listed:", "Whole repo:"):
                t = t.replace("\n" + lead, "\n- " + lead)
            return t
        self.assertProved(edit_all(self.parts, bullets))

    def test_a_leading_dash_on_the_areas_not_read_coverage_line(self):
        parts = edit(self.parts, "part-1.md", "\nAreas not read: 7 areas", "\n- Areas not read: 7 areas")
        self.assertProved(parts)

    def test_area_lead_singular_for_one_lead(self):
        areas = base_areas()
        parts = build_parts(areas, cuts=(10, 16))   # part 3 reads only `web`
        self.assertIn("Mode: full sweep, 1 area leads", parts["part-3.md"])
        self.assertProved(edit(parts, "part-3.md", "1 area leads", "1 area lead"))

    def test_area_lead_singular_is_accepted_for_any_count_as_built(self):
        # a tolerance, pinned: "area lead" is not tied to N == 1
        self.assertProved(edit(self.parts, "part-1.md", "10 area leads", "10 area lead"))

    def test_area_leads_is_exact_otherwise(self):
        for bad in ("10 areas", "10 leads", "10 area-leads", "10 area leader"):
            with self.subTest(bad=bad):
                self.assertFails(edit(self.parts, "part-1.md", "10 area leads", bad), r"part-1\.md: no line 'Mode: full sweep")

    def test_area_lines_indented_under_areas_read(self):
        def indent(t):
            head, tail = t.split("Areas read:\n")
            body, rest = tail.split("\n\nINVESTIGATE", 1)
            return head + "Areas read:\n" + "\n".join("  " + l for l in body.split("\n")) + "\n\nINVESTIGATE" + rest
        self.assertProved(edit_all(self.parts, indent))

    def test_the_findings_and_prose_may_say_anything_else(self):
        self.assertProved(edit(self.parts, "part-2.md", "# Investigation report (part 2)", "# A completely different title\nSome prose: a, b; c."))

    def test_non_ascii_text_in_a_part(self):
        parts = edit(self.parts, "part-1.md", "## Findings\n", "## Findings\ncafe éè 中文 \U0001f600\n")
        self.assertProved(parts)

    def test_a_utf8_bom_at_the_start_of_a_part_is_not_the_sweep_line(self):
        # exact about line 1: a BOM glued to the token is not the token
        parts = dict(self.parts)
        parts["part-1.md"] = "﻿" + parts["part-1.md"]
        self.assertFails(parts, r"part-1\.md: expected 'SWEEP IN PARTS")

    def test_a_part_file_that_is_not_utf8_does_not_crash_the_scorer(self):
        code, out = run_script(self.parts, raw={"part-2.md": b"\xff\xfe\x00 junk \xc3\x28"})
        self.assertEqual(code, 1, out)
        self.assertIn("LOOP FAILED", out)

    def test_an_area_name_with_a_dash_digit_and_space_in_the_notation(self):
        areas = base_areas()
        areas[6] = areas[6].copy(name="cli-2")
        self.assertProved(build_parts(areas))

    def test_an_area_named_with_a_unicode_digit_is_read_as_it_was_at_3_0_0(self):
        areas = base_areas()
        areas[6] = areas[6].copy(name="\u00b2")
        self.assertProved(build_parts(areas))


# ---------------------------------------------------------------- exit 2, and a crash is never exit 1

class CantCheckTest(Base):
    def setUp(self):
        self.parts = build_parts(base_areas())

    def test_a_missing_key(self):
        self.assertCantCheck(run_script(self.parts, key="/nonexistent/key.json"), r"the key /nonexistent/key\.json is missing or unreadable")

    def test_a_key_that_is_not_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "k.json"
            bad.write_text("{not json", encoding="utf-8")
            self.assertCantCheck(run_script(self.parts, key=bad), r"unreadable")

    def test_an_empty_key_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "k.json"
            bad.write_text("", encoding="utf-8")
            self.assertCantCheck(run_script(self.parts, key=bad), r"unreadable")

    def test_a_key_that_is_a_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertCantCheck(run_script(self.parts, key=tmp), r"unreadable")

    def test_a_key_missing_each_required_section(self):
        for section in ("facts", "decoys", "layout"):
            with self.subTest(section=section), tempfile.TemporaryDirectory() as tmp:
                key = dict(Fixture.key)
                del key[section]
                bad = Path(tmp) / "k.json"
                bad.write_text(json.dumps(key), encoding="utf-8")
                self.assertCantCheck(run_script(self.parts, key=bad), r"unreadable")

    def test_a_key_whose_layout_lacks_a_field(self):
        for field in ("tracked", "skipped_whole", "untracked"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                key = json.loads(json.dumps(Fixture.key))
                del key["layout"][field]
                bad = Path(tmp) / "k.json"
                bad.write_text(json.dumps(key), encoding="utf-8")
                self.assertCantCheck(run_script(self.parts, key=bad), r"unreadable")

    def test_a_key_of_the_wrong_json_type(self):
        for body in ("[]", "null", "42", '"text"', '{"facts": 5, "decoys": [], "layout": {}}'):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                bad = Path(tmp) / "k.json"
                bad.write_text(body, encoding="utf-8")
                self.assertCantCheck(run_script(self.parts, key=bad))

    def test_a_fact_without_a_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = json.loads(json.dumps(Fixture.key))
            del key["facts"][3]["token"]
            bad = Path(tmp) / "k.json"
            bad.write_text(json.dumps(key), encoding="utf-8")
            self.assertCantCheck(run_script(self.parts, key=bad), r"unreadable")

    def test_a_missing_parts_folder(self):
        self.assertCantCheck(run_script(parts_dir="/nonexistent/parts"), r"the parts folder /nonexistent/parts does not exist")

    def test_a_parts_path_that_is_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "afile"
            f.write_text("x", encoding="utf-8")
            self.assertCantCheck(run_script(parts_dir=f), r"does not exist")

    def test_a_part_file_that_is_a_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "parts"
            d.mkdir()
            (d / "part-1.md").mkdir()
            self.assertCantCheck(run_script(parts_dir=d), r"cannot read part-1\.md")

    def test_a_fixture_that_does_not_match_the_key(self):
        self.assertCantCheck(run_script(self.parts, repo=Fixture.small), r"the fixture tracks \d+ files, the key says 990; rebuild the fixture")

    def test_a_repo_folder_without_the_git_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertCantCheck(run_script(self.parts, repo=tmp), r"git wrapper .* is missing")

    def test_a_repo_path_that_does_not_exist(self):
        self.assertCantCheck(run_script(self.parts, repo="/nonexistent/repo"), r"git wrapper")

    def test_a_git_wrapper_that_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            wrapper = bindir / "git"
            wrapper.write_text("#!/bin/sh\necho boom >&2\nexit 3\n", encoding="utf-8")
            wrapper.chmod(0o755)
            self.assertCantCheck(run_script(self.parts, repo=tmp), r"git ls-files failed .*boom")

    def test_a_git_wrapper_that_cannot_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            wrapper = bindir / "git"
            wrapper.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
            wrapper.chmod(0o755)
            self.assertCantCheck(run_script(self.parts, repo=tmp), r"could not run")

    def test_missing_required_arguments(self):
        for args in ([], ["--key", str(KEY_PATH)], ["--key", str(KEY_PATH), "--repo", str(Fixture.repo)]):
            with self.subTest(args=args):
                proc = subprocess.run([sys.executable, str(SCRIPT)] + args, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertNotIn("LOOP", proc.stdout)

    def test_a_non_numeric_min_parts(self):
        code, out = run_script(self.parts, extra=["--min-parts", "many"])
        self.assertEqual(code, 2, out)
        self.assertNotIn("LOOP FAILED", out)

    def test_help_does_not_report_a_verdict(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertNotIn("LOOP", proc.stdout)

    def test_a_crash_inside_a_check_is_exit_2_and_never_1(self):
        # a key whose skipped_whole holds a non-number passes loading and crashes later, in the coverage arithmetic
        with tempfile.TemporaryDirectory() as tmp:
            key = json.loads(json.dumps(Fixture.key))
            key["layout"]["skipped_whole"] = {"web/vendor/": "forty"}
            bad = Path(tmp) / "k.json"
            bad.write_text(json.dumps(key), encoding="utf-8")
            code, out = run_script(self.parts, key=bad)
            self.assertEqual(code, 2, out)
            self.assertTrue(out.startswith("CAN'T CHECK: "), out)
            self.assertNotIn("LOOP", out)

    def test_a_crash_from_untracked_not_being_a_list_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = json.loads(json.dumps(Fixture.key))
            key["layout"]["untracked"] = 3
            bad = Path(tmp) / "k.json"
            bad.write_text(json.dumps(key), encoding="utf-8")
            code, out = run_script(self.parts, key=bad)
            self.assertEqual(code, 2, out)
            self.assertNotIn("LOOP FAILED", out)

    def test_a_crash_from_a_decoy_token_that_is_not_text_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = json.loads(json.dumps(Fixture.key))
            key["decoys"][0]["token"] = 17
            bad = Path(tmp) / "k.json"
            bad.write_text(json.dumps(key), encoding="utf-8")
            code, out = run_script(self.parts, key=bad)
            self.assertEqual(code, 2, out)
            self.assertNotIn("LOOP", out)

    def test_exit_2_prints_nothing_that_looks_like_a_verdict_on_stdout(self):
        code, out = run_script(self.parts, key="/nonexistent/key.json")
        self.assertEqual(out.strip().count("\n"), 0, out)

    def test_the_script_never_reads_the_repo_when_the_key_is_unreadable(self):
        # exit 2 for the key comes before anything else, even with a bad repo and a bad parts folder
        code, out = run_script(parts_dir="/nonexistent/parts", key="/nonexistent/key.json", repo="/nonexistent/repo")
        self.assertEqual(code, 2, out)
        self.assertIn("the key", out)


# ---------------------------------------------------------------- output shape and the stock interpreter

class OutputTest(Base):
    def test_a_failure_prints_one_line_per_failure_and_nothing_else(self):
        parts = build_parts(base_areas())
        parts = edit(parts, "part-1.md", "Mode: full sweep, 10 area leads", "Mode: full sweep, 7 area leads")
        parts = edit(parts, "part-3.md", "INVESTIGATE REPORT ENDS\n", "")
        code, out = run_script(parts)
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertEqual(lines[0], "LOOP FAILED")
        self.assertEqual(len(lines), 3, out)

    def test_several_breakages_are_all_reported_at_once(self):
        parts = build_parts(base_areas())
        parts = edit(parts, "part-1.md", "Mode: full sweep, 10 area leads", "Mode: full sweep, 7 area leads")
        parts = edit(parts, "part-2.md", "failed: 0;", "failed: 3;")
        parts = edit(parts, "part-3.md", "## Findings\n", "## Findings\n- %s\n" % Fixture.key["decoys"][4]["token"])
        self.assertFails(parts, r"part-1\.md: Mode says 7", r"part-2\.md: Files listed", r"decoys: d5")

    def test_a_proved_run_prints_no_failure_lines(self):
        out = self.assertProved(build_parts(base_areas()))
        self.assertEqual(len(out.strip().splitlines()), 2, out)

    def test_an_unexpected_argument_is_exit_2(self):
        code, out = run_script(build_parts(base_areas()), extra=["--bogus"])
        self.assertEqual(code, 2, out)


# ---------------------------------------------------------------- --part-size

SMALL_PARTS = (4, 6, 9, 10, 11, 12, 13, 14)   # nine parts of 90, 80, 76, 122, 122, 122, 122, 122 (one area each), 94 files


def run_script_at(script, parts, extra=(), python=None):
    """Like run_script, for a copy of the script (a mutant) or another interpreter; returns (code, stdout, stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        pdir = Path(tmp) / "parts"
        pdir.mkdir()
        for name, text in parts.items():
            (pdir / name).write_bytes(text.encode("utf-8"))
        proc = subprocess.run([python or sys.executable, str(script), "--key", str(KEY_PATH), "--repo", str(Fixture.repo),
                               "--parts", str(pdir)] + list(extra), capture_output=True, text=True, cwd=tmp)
        return proc.returncode, proc.stdout, proc.stderr


class PartSizeBase(Base):
    def sized(self, n, parts=None, **kw):
        return run_script(parts if parts is not None else build_parts(base_areas()), extra=["--part-size", str(n)], **kw)

    def size_lines(self, out):
        return [l for l in out.splitlines() if l.startswith("part size:")]

    def note_lines(self, out):
        return [l for l in out.splitlines() if l.startswith("NOTE:")]


class PartSizeBoundaryTest(PartSizeBase):
    def test_a_sum_exactly_the_part_size_passes(self):
        code, out = self.sized(368)
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)

    def test_a_sum_one_over_the_part_size_fails(self):
        code, out = self.sized(367)
        self.assertEqual(code, 1, out)
        self.assertEqual(out.splitlines()[0], "LOOP FAILED")
        self.assertEqual(len(self.size_lines(out)), 1, out)

    def test_the_part_size_equal_to_the_largest_part_passes_and_one_less_fails(self):
        self.assertEqual(self.sized(368)[0], 0)
        self.assertEqual(self.sized(367)[0], 1)
        self.assertEqual(self.sized(450)[0], 0)

    def test_a_huge_part_size_passes(self):
        self.assertEqual(self.sized(10 ** 9)[0], 0)

    def test_part_size_1_fails_every_multi_area_part_and_nothing_crashes(self):
        code, out = self.sized(1)
        self.assertEqual(code, 1, out)
        self.assertEqual(len(self.size_lines(out)), 3, out)

    def test_part_size_1_fails_a_split_of_single_area_parts(self):
        # the one-area exemption is gone: every one of the 17 parts holds a single area, and each is over 1
        parts = build_parts(base_areas(), cuts=tuple(range(1, 17)))
        code, out = self.sized(1, parts)
        self.assertEqual(code, 1, out)
        self.assertEqual(out.splitlines()[0], "LOOP FAILED")
        self.assertEqual(len(self.size_lines(out)), 17, out)
        self.assertIn("part size: part-1.md holds 6 files in 1 areas, over the part size of 1", out)

    def test_a_split_of_single_area_parts_passes_when_the_part_size_holds_the_largest_area(self):
        parts = build_parts(base_areas(), cuts=tuple(range(1, 17)))
        code, out = self.sized(122, parts)
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)
        self.assertIn("largest part: 122 files", out)


class PartSizeOneAreaTest(PartSizeBase):
    def test_a_part_of_exactly_one_area_over_the_part_size_fails(self):
        # five parts hold one 122-file area each, over 121; the others are 90, 80, 76 and 94 and stay quiet
        out = self.assertFails(build_parts(base_areas(), cuts=SMALL_PARTS), extra=["--part-size", "121"])
        lines = self.size_lines(out)
        self.assertEqual(len(lines), 5, out)
        self.assertTrue(all(re.match(r"^part size: part-[4-8]\.md holds 122 files in 1 areas, over the part size of 121$", l) for l in lines), lines)

    def test_a_part_of_two_areas_over_the_part_size_fails_even_if_each_area_alone_fits(self):
        # r1 and r2 together: 244 files in 2 areas, over 121; the three single-area parts after it are over 121 too
        cuts = (4, 6, 9, 11, 12, 13, 14)
        out = self.assertFails(build_parts(base_areas(), cuts=cuts), r"^part size: part-4\.md holds 244 files in 2 areas, over the part size of 121",
                               extra=["--part-size", "121"])
        self.assertEqual(len(self.size_lines(out)), 4, out)

    def test_the_size_check_runs_alongside_the_other_checks(self):
        parts = edit(build_parts(base_areas(), cuts=SMALL_PARTS), "part-1.md", "Mode: full sweep, 4 area leads", "Mode: full sweep, 9 area leads")
        self.assertFails(parts, r"part-1\.md: Mode says 9", extra=["--part-size", "121"])


class PartSizeMessageTest(PartSizeBase):
    def test_the_failure_names_the_part_the_sum_the_areas_and_the_part_size(self):
        self.assertFails(build_parts(base_areas()),
                         r"^part size: part-1\.md holds 368 files in 10 areas, over the part size of 367$", extra=["--part-size", "367"])

    def test_the_message_reports_the_part_size_given(self):
        self.assertFails(build_parts(base_areas()), r"in 3 areas, over the part size of 300$", extra=["--part-size", "300"])

    def test_every_over_size_part_is_reported_not_just_the_first(self):
        out = self.assertFails(build_parts(base_areas()), r"part-1\.md holds 368 files in 10 areas", r"part-2\.md holds 366 files in 3 areas",
                               extra=["--part-size", "300"])
        self.assertEqual(len(self.size_lines(out)), 2, out)
        self.assertNotIn("part-3.md holds", out)

    def test_all_three_parts_reported_when_all_are_over(self):
        out = self.assertFails(build_parts(base_areas()), r"part-3\.md holds 216 files in 4 areas, over the part size of 100",
                               extra=["--part-size", "100"])
        self.assertEqual(len(self.size_lines(out)), 3, out)

    def test_size_failures_come_with_the_other_failures(self):
        parts = edit(build_parts(base_areas()), "part-3.md", "failed: 0;", "failed: 2;")
        self.assertFails(parts, r"part-3\.md: Files listed", r"part size: part-1\.md", extra=["--part-size", "300"])


class PartSizeNoteTest(PartSizeBase):
    def test_a_note_names_the_part_its_sum_and_the_area_it_left(self):
        code, out = self.sized(490)
        self.assertEqual(code, 0, out)
        notes = self.note_lines(out)
        self.assertEqual(len(notes), 2, out)
        self.assertRegex(notes[0], r"^NOTE: part-1\.md holds 368 files and left its next area, rules-2, ")
        self.assertRegex(notes[1], r"^NOTE: part-2\.md holds 366 files and left its next area, rules-5, ")

    def test_a_note_is_one_line_each(self):
        out = self.sized(10 ** 6)[1]
        self.assertEqual(len(self.note_lines(out)), 2)
        self.assertEqual(len(out.splitlines()), 4, out)

    def test_a_note_never_changes_the_exit_code_or_the_verdict_word(self):
        code, out = self.sized(490)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "LOOP PROVED")
        self.assertNotIn("LOOP FAILED", out)

    def test_no_note_when_the_next_area_would_not_have_fit(self):
        # 368 + 122 = 490 and 366 + 122 = 488, both over 487
        code, out = self.sized(487)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.note_lines(out), [])

    def test_the_note_boundary_is_exact_one_part_at_a_time(self):
        self.assertEqual(len(self.note_lines(self.sized(490)[1])), 2)
        only_part_2 = self.note_lines(self.sized(489)[1])
        self.assertEqual(len(only_part_2), 1)
        self.assertIn("part-2.md", only_part_2[0])
        self.assertEqual(len(self.note_lines(self.sized(488)[1])), 1)
        self.assertEqual(self.note_lines(self.sized(487)[1]), [])

    def test_no_note_at_the_part_size_the_loop_uses(self):
        out = self.sized(450)[1]
        self.assertEqual(self.note_lines(out), [])
        self.assertEqual(len(out.strip().splitlines()), 2, out)

    def test_the_last_part_never_gets_a_note(self):
        out = self.sized(10 ** 6)[1]
        self.assertNotIn("part-3.md holds", out)
        two = build_parts(base_areas(), cuts=(9,))
        notes = self.note_lines(self.sized(10 ** 6, two)[1])
        self.assertEqual(len(notes), 1)
        self.assertIn("part-1.md", notes[0])
        one = build_parts(base_areas(), cuts=())
        code, out = run_script(one, extra=["--part-size", "100000", "--min-parts", "1"])
        self.assertEqual(self.note_lines(out), [])

    def test_a_note_with_failures_still_prints_every_failure_and_exit_stays_1(self):
        # cuts (10, 12): parts of 368, 244, 338. At 367 part 1 fails; part 2 (244) could have held r4 (122): 366 is at most 367
        parts = build_parts(base_areas(), cuts=(10, 12))
        code, out = self.sized(367, parts)
        lines = out.splitlines()
        self.assertEqual((code, lines[0]), (1, "LOOP FAILED"), out)
        self.assertEqual(len(self.size_lines(out)), 1, out)
        self.assertEqual(len(self.note_lines(out)), 1, out)
        self.assertRegex(self.note_lines(out)[0], r"^NOTE: part-2\.md holds 244 files and left its next area, rules-4, ")
        self.assertLess(lines.index(self.size_lines(out)[0]), lines.index(self.note_lines(out)[0]))

    def test_a_note_with_another_failure_hides_nothing(self):
        parts = edit(build_parts(base_areas()), "part-1.md", "Mode: full sweep, 10 area leads", "Mode: full sweep, 7 area leads")
        code, out = self.sized(490, parts)
        self.assertEqual((code, out.splitlines()[0]), (1, "LOOP FAILED"), out)
        self.assertIn("part-1.md: Mode says 7", out)
        self.assertEqual(len(self.note_lines(out)), 2, out)

    def test_a_note_is_not_a_failure_line_count(self):
        # LOOP PROVED has the verdict, the summary and the notes only
        out = self.sized(490)[1]
        self.assertEqual(out.splitlines()[1].split(";")[0], "parts: 3")
        self.assertTrue(all(l.startswith("NOTE:") for l in out.splitlines()[2:]))


class PartSizeOutputTest(PartSizeBase):
    OLD_SUMMARY = "parts: 3; areas: 17; files covered: 950 of 950; read: 945 of 945; facts found: 33 of 33; decoys found: 0 of %d"

    def old_summary(self):
        return self.OLD_SUMMARY % len(Fixture.key["decoys"])

    def test_without_the_argument_the_output_is_the_old_two_lines_exactly(self):
        code, out = run_script(build_parts(base_areas()))
        self.assertEqual(code, 0)
        self.assertEqual(out, "LOOP PROVED\n" + self.old_summary() + NO_TRANSCRIPT_NOTE + "\n")

    def test_without_the_argument_no_largest_part_and_no_note_ever(self):
        for parts in (build_parts(base_areas()), build_parts(base_areas(), cuts=(9,)), build_parts(base_areas(), cuts=SMALL_PARTS)):
            out = run_script(parts)[1]
            self.assertNotIn("largest part", out)
            self.assertNotIn("NOTE:", out)
            self.assertNotIn("part size", out)

    def test_without_the_argument_a_huge_part_passes_whatever_its_size(self):
        self.assertProved(build_parts(base_areas(), cuts=()), extra=["--min-parts", "1"])

    def test_without_the_argument_a_failing_run_prints_no_part_size_line_and_the_same_failures_as_with_a_roomy_one(self):
        parts = edit(build_parts(base_areas()), "part-3.md", "failed: 0;", "failed: 2;")
        plain = run_script(parts)
        roomy = run_script(parts, extra=["--part-size", "450"])
        self.assertEqual(plain[0], 1)
        self.assertEqual(plain, roomy)

    def test_with_the_argument_the_summary_gains_the_largest_part_and_nothing_else_changes(self):
        out = self.sized(450)[1]
        self.assertEqual(out, "LOOP PROVED\n" + self.old_summary() + "; largest part: 368 files" + NO_TRANSCRIPT_NOTE + "\n")

    def test_the_largest_part_is_the_biggest_not_the_first_or_last(self):
        out = self.sized(1000, build_parts(base_areas(), cuts=(2, 12)))[1]
        areas = base_areas()
        sums = [sum(a.count for a in areas[lo:hi]) for lo, hi in ((0, 2), (2, 12), (12, 17))]
        self.assertEqual(max(sums), sums[1])
        self.assertIn("largest part: %d files" % sums[1], out)

    def test_the_summary_counts_stated_file_counts(self):
        out = self.sized(1000, build_parts(base_areas(), cuts=(9,)))[1]
        self.assertEqual(out.splitlines()[0], "LOOP PROVED")
        self.assertIn("largest part: %d files" % sum(a.count for a in base_areas()[9:]), out)

    def test_with_the_argument_the_stock_python_prints_the_same(self):
        stock = "/usr/bin/python3"
        if not Path(stock).exists():
            self.skipTest("no stock python")
        for n in (450, 490, 300):
            parts = build_parts(base_areas())
            mine = run_script_at(SCRIPT, parts, ["--part-size", str(n)])
            theirs = run_script_at(SCRIPT, parts, ["--part-size", str(n)], python=stock)
            self.assertEqual(mine, theirs, n)
            self.assertEqual(theirs[2], "")


class PartSizeBadValueTest(PartSizeBase):
    def check(self, value):
        code, out = run_script(build_parts(base_areas()), extra=["--part-size", value])
        self.assertEqual(code, 2, out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("LOOP PROVED", out)
        self.assertNotIn("LOOP FAILED", out)
        self.assertIn("part-size", out)

    def test_zero_is_exit_2(self):
        self.check("0")

    def test_a_negative_number_is_exit_2(self):
        self.check("-5")

    def test_a_word_is_exit_2(self):
        self.check("abc")

    def test_an_empty_value_is_exit_2(self):
        self.check("")

    def test_a_decimal_is_exit_2(self):
        self.check("1.5")

    def test_a_missing_value_is_exit_2(self):
        code, out = run_script(build_parts(base_areas()), extra=["--part-size"])
        self.assertEqual(code, 2, out)
        self.assertNotIn("Traceback", out)

    def test_a_bad_value_is_never_exit_1(self):
        for v in ("0", "-5", "abc", "", "1e3", "0x10"):
            self.assertEqual(run_script(build_parts(base_areas()), extra=["--part-size", v])[0], 2, v)


class PartSizeUnparsedAreaTest(PartSizeBase):
    """A part whose area lines don't parse is already failing elsewhere; the size check must not crash on it."""

    def broken(self, name, old, new):
        return edit(build_parts(base_areas()), name, old, new)

    def run_broken(self, parts, size=450):
        code, out = run_script(parts, extra=["--part-size", str(size)])
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(out.splitlines()[0], "LOOP FAILED")
        return out

    def test_a_garbled_area_line_in_the_middle_part(self):
        out = self.run_broken(self.broken("part-2.md", "- rules-3: ", "- rules-3 = "))
        self.assertIn("part-2.md: area line does not match", out)

    def test_a_garbled_area_line_in_the_first_part(self):
        self.run_broken(self.broken("part-1.md", "- api-top: `api/` (direct) (4 files)", "- api-top: `api/` (direct) (four files)"), 300)

    def test_a_garbled_area_line_in_the_last_part_with_a_small_part_size(self):
        self.run_broken(self.broken("part-3.md", "- tests: `tests/` (36 files)", "- tests: `tests/` (36 files"), 100)

    def test_a_garbled_first_area_in_the_next_part_while_the_note_looks_at_it(self):
        # part-2's first area line is what part 1's note reads
        out = self.run_broken(self.broken("part-2.md", "- rules-2: ", "rules-2: "), 10 ** 6)
        self.assertNotIn("Traceback", out)

    def test_every_read_line_garbled(self):
        parts = edit_all(build_parts(base_areas()), lambda t: re.sub(r"^- ([^:\n]+): (.*) \((\d+) files\)$",
                                                                    r"\1 \3", t, flags=re.M))
        code, out = run_script(parts, extra=["--part-size", "450"])
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)

    def test_an_empty_areas_read_list(self):
        parts = build_parts(base_areas())
        text = parts["part-2.md"]
        head, _, tail = text.partition("Areas read:\n")
        tail = tail[tail.index("\nINVESTIGATE REPORT ENDS"):]
        parts = dict(parts, **{"part-2.md": head + "Areas read:\n" + tail})
        code, out = run_script(parts, extra=["--part-size", "450"])
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)

    def test_a_part_with_no_areas_read_line_at_all(self):
        parts = build_parts(base_areas())
        text = parts["part-2.md"]
        parts["part-2.md"] = text[:text.index("Areas read:")] + "\nINVESTIGATE REPORT ENDS\n"
        code, out = run_script(parts, extra=["--part-size", "450"])
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)

    def test_a_missing_part_does_not_crash_the_size_check(self):
        parts = build_parts(base_areas())
        del parts["part-2.md"]
        code, out = run_script(parts, extra=["--part-size", "450"])
        self.assertIn(code, (1, 2), out)
        self.assertNotIn("Traceback", out)

    def test_the_same_garbled_run_gives_the_same_verdict_with_and_without_the_argument(self):
        parts = self.broken("part-2.md", "- rules-3: ", "- rules-3 = ")
        plain = run_script(parts)
        sized = run_script(parts, extra=["--part-size", "10000"])
        self.assertEqual(plain[0], sized[0])
        self.assertEqual(plain[1].splitlines()[:2], sized[1].splitlines()[:2])


class PartSizeMutationTest(PartSizeBase):
    """Each new check has to be shown to fail: a temp copy of the script with one piece broken must be caught by a test."""

    SIZE_IF = "if sum(counts) > args.part_size:"
    FIT_IF = "if sum(counts) + nxt[0] <= args.part_size:"

    @classmethod
    def setUpClass(cls):
        cls.src = SCRIPT.read_text(encoding="utf-8")
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def mutant(self, name, old, new):
        self.assertEqual(self.src.count(old), 1, "the script no longer has %r once; update this mutation" % old)
        path = Path(self.tmp.name) / (name + ".py")
        path.write_text(self.src.replace(old, new), encoding="utf-8")
        return path

    def mutant_on(self, path, old, new):
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, old)
        path.write_text(text.replace(old, new), encoding="utf-8")
        return path

    def both(self, mutant, parts, extra):
        real = run_script_at(SCRIPT, parts, extra)
        mutated = run_script_at(mutant, parts, extra)
        return real, mutated

    def test_the_unmutated_copy_behaves_as_the_script_does(self):
        copy = Path(self.tmp.name) / "same.py"
        copy.write_text(self.src, encoding="utf-8")
        parts = build_parts(base_areas())
        self.assertEqual(run_script_at(copy, parts, ["--part-size", "367"]), run_script_at(SCRIPT, parts, ["--part-size", "367"]))

    def test_dropping_the_size_check_is_caught(self):
        m = self.mutant("nosize", self.SIZE_IF, "if False:")
        real, mutated = self.both(m, build_parts(base_areas()), ["--part-size", "367"])
        self.assertEqual(real[0], 1)
        self.assertEqual(mutated[0], 0)  # the mutant proves a part of 368 under 367: the boundary tests above catch it

    def test_dropping_the_one_area_exemption_is_caught(self):
        # the mutant puts the exemption back: a part of one area over the part size passes again
        m = self.mutant("exempt", self.SIZE_IF, "if sum(counts) > args.part_size and len(counts) > 1:")
        real, mutated = self.both(m, build_parts(base_areas(), cuts=SMALL_PARTS), ["--part-size", "121"])
        self.assertEqual(real[0], 1)
        self.assertEqual(mutated[0], 0)

    def test_making_the_note_a_failure_is_caught(self):
        m = self.mutant("notefail", 'notes.append("NOTE: %s holds', 'fails.append("NOTE: %s holds')
        real, mutated = self.both(m, build_parts(base_areas()), ["--part-size", "490"])
        self.assertEqual(real[0], 0)
        self.assertEqual(mutated[0], 1)

    def test_an_off_by_one_in_the_size_boundary_is_caught(self):
        m = self.mutant("ge", "sum(counts) > args.part_size", "sum(counts) >= args.part_size")
        real, mutated = self.both(m, build_parts(base_areas()), ["--part-size", "368"])
        self.assertEqual((real[0], mutated[0]), (0, 1))

    def test_an_off_by_one_in_the_note_boundary_is_caught(self):
        m = self.mutant("lt", self.FIT_IF, "if sum(counts) + nxt[0] < args.part_size:")
        real, mutated = self.both(m, build_parts(base_areas()), ["--part-size", "490"])
        self.assertEqual(len([l for l in real[1].splitlines() if l.startswith("NOTE:")]), 2)
        self.assertEqual(len([l for l in mutated[1].splitlines() if l.startswith("NOTE:")]), 1)  # 366 + 122 = 488 still fits under 490

    def test_dropping_the_note_is_caught(self):
        m = self.mutant("nonote", self.FIT_IF, "if False:")
        real, mutated = self.both(m, build_parts(base_areas()), ["--part-size", "490"])
        self.assertNotEqual(real[1], mutated[1])
        self.assertNotIn("NOTE:", mutated[1])

    def test_a_note_for_the_last_part_is_caught(self):
        # let the note loop pair every part with a wrapped successor: the last part would get a note
        # the note loop pairs every part with a wrapped successor and stops skipping the last part
        m = self.mutant("lastnote", 'if counts is None or nxt is None or i["n"] == 0:', "if counts is None or nxt is None:")
        m = self.mutant_on(m, "zip(counted, counted[1:])", "zip(counted, counted[1:] + counted[:1])")
        real, mutated = self.both(m, build_parts(base_areas()), ["--part-size", "10000"])
        self.assertEqual(len([l for l in real[1].splitlines() if l.startswith("NOTE:")]), 2)
        self.assertEqual(len([l for l in mutated[1].splitlines() if l.startswith("NOTE:")]), 3)

    def test_a_summary_with_the_largest_part_even_without_the_argument_is_caught(self):
        m = self.mutant("alwayslargest", 'if sizes else ""', 'if True else ""')
        code, out, err = run_script_at(m, build_parts(base_areas()), [])
        self.assertTrue(code != 0 or "largest part" in out, "the mutant should misbehave without the argument")
        self.assertNotEqual((code, out), run_script_at(SCRIPT, build_parts(base_areas()), [])[:2])

    def test_a_note_without_the_argument_is_caught_by_the_exact_output_pin(self):
        m = self.mutant("sizeless", "if args.part_size is not None:", "if True:")
        code, out, err = run_script_at(m, build_parts(base_areas()), [])
        self.assertNotEqual(out, run_script_at(SCRIPT, build_parts(base_areas()), [])[1])


# ---------------------------------------------------------------- fix batch B of the final qa pass: the scorer proves reading

LISTED_RE = re.compile(r"Files listed: (\d+); read: (\d+); skipped: (\d+); re-dispatched: (\d+); failed: (\d+); unread: (\d+)")


def listed_of(text):
    """(listed, read, skipped, redispatched, failed, unread) of the part text's Files listed line."""
    return tuple(int(x) for x in LISTED_RE.search(text).groups())


def set_listed(parts, name, **changes):
    """The part with its Files listed line's numbers changed (listed, read, skipped, redisp, failed, unread by keyword)."""
    keys = ("listed", "read", "skipped", "redisp", "failed", "unread")
    old = dict(zip(keys, listed_of(parts[name])))
    old.update(changes)
    line = "Files listed: %(listed)d; read: %(read)d; skipped: %(skipped)d; re-dispatched: %(redisp)d; failed: %(failed)d; unread: %(unread)d" % old
    out = dict(parts)
    out[name] = LISTED_RE.sub(line, parts[name], count=1)
    return out


def coverage_of(text):
    """The Coverage section's lines (between the 8. Coverage heading and the last line)."""
    return text.split("## 8. Coverage\n", 1)[1].split("\n\nINVESTIGATE REPORT ENDS", 1)[0]


def with_coverage(text, new_coverage):
    head, rest = text.split("## 8. Coverage\n", 1)
    return head + "## 8. Coverage\n" + new_coverage + "\n\nINVESTIGATE REPORT ENDS" + rest.split("\n\nINVESTIGATE REPORT ENDS", 1)[1]


def with_lookalike(text, lookalike):
    """The part with lookalike lines put in its Findings, before the Coverage section."""
    return text.replace("## Findings\n", "## Findings\n" + lookalike + "\nThat is the end of that copy.\n", 1)


class MutantBase(Base):
    """A temp copy of the script with one piece broken must be caught by a test: each new check is shown able to fail."""

    @classmethod
    def setUpClass(cls):
        cls.src = SCRIPT.read_text(encoding="utf-8")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.count = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def mutant(self, old, new):
        self.assertEqual(self.src.count(old), 1, "the script no longer has %r once; update this mutation" % old)
        type(self).count += 1
        path = Path(self.tmp.name) / ("m%d.py" % type(self).count)
        path.write_text(self.src.replace(old, new), encoding="utf-8")
        return path

    def both(self, mutant, parts, extra=()):
        """((code, out) of the script, (code, out) of the mutant) on the same parts."""
        real = run_script(parts, extra=list(extra))
        code, out, err = run_script_at(mutant, parts, list(extra))
        return real, (code, out + err)

    def assertCaught(self, mutant, parts, line_pattern, extra=()):
        """The script prints a failure line matching line_pattern; the mutant doesn't."""
        real, mutated = self.both(mutant, parts, extra)
        self.assertEqual(real[0], 1, real[1])
        self.assertTrue(any(re.search(line_pattern, l) for l in real[1].splitlines()), real[1])
        self.assertFalse(any(re.search(line_pattern, l) for l in mutated[1].splitlines()), "the mutant still prints the line:\n" + mutated[1])
        return real, mutated


# ---- totals: the read numbers across the parts

class TotalsTest(Base):
    def setUp(self):
        self.parts = build_parts(base_areas())
        self.l1, self.l2, self.l3 = (listed_of(self.parts["part-%d.md" % n]) for n in (1, 2, 3))

    def test_the_base_split_adds_up_to_945_read_and_5_skipped(self):
        # guards this file's own generator
        self.assertEqual(sum(l[1] for l in (self.l1, self.l2, self.l3)), 945)
        self.assertEqual(sum(l[2] for l in (self.l1, self.l2, self.l3)), 5)

    def test_a_proved_run_says_read_945_of_945_in_its_summary(self):
        code, out = run_script(self.parts)
        self.assertEqual(code, 0, out)
        self.assertEqual(out, "LOOP PROVED\nparts: 3; areas: 17; files covered: 950 of 950; read: 945 of 945; facts found: 33 of 33; decoys found: 0 of %d%s\n"
                         % (len(Fixture.key["decoys"]), NO_TRANSCRIPT_NOTE))

    def test_unread_above_zero_in_a_part_fails_naming_the_part_and_the_number(self):
        parts = set_listed(self.parts, "part-3.md", read=self.l3[1] - 62, unread=62)
        out = self.assertFails(parts, r"^read: part-3\.md says unread: 62, expected 0$")
        self.assertNotIn("failed:", "\n".join(l for l in out.splitlines() if l.startswith("read:")))

    def test_failed_above_zero_in_a_part_fails_naming_the_part_and_the_number(self):
        parts = set_listed(self.parts, "part-3.md", read=self.l3[1] - 62, failed=62)
        out = self.assertFails(parts, r"^read: part-3\.md says failed: 62, expected 0$")
        self.assertNotIn("unread:", "\n".join(l for l in out.splitlines() if l.startswith("read:")))

    def test_unread_or_failed_of_one_is_enough_in_any_part(self):
        for n in (1, 2, 3):
            for field, word in (("unread", "unread"), ("failed", "failed")):
                with self.subTest(part=n, field=field):
                    name = "part-%d.md" % n
                    l = listed_of(self.parts[name])
                    parts = set_listed(self.parts, name, read=l[1] - 1, **{field: 1})
                    self.assertFails(parts, r"^read: part-%d\.md says %s: 1, expected 0$" % (n, word))

    def test_skipped_numbers_that_add_up_wrongly_fail_with_the_total_found_against_the_expected(self):
        # part 2 says read 66, skipped 300: the arithmetic of its own line adds up, the totals don't
        parts = set_listed(self.parts, "part-2.md", read=66, skipped=300)
        skipped = self.l1[2] + 300 + self.l3[2]
        read = self.l1[1] + 66 + self.l3[1]
        out = self.assertFails(parts, r"^read: the skipped numbers add up to %d, expected 5 \(the key's file_skips\)$" % skipped,
                               r"^read: the read numbers add up to %d, expected 945 \(950 files after the whole-folder skips, less 5 skipped\)$" % read)
        self.assertNotIn("says unread", out)
        self.assertNotIn("says failed", out)

    def test_a_split_that_skips_nothing_reads_950_and_fails_both_totals(self):
        parts = dict(self.parts)
        for n in (1, 2, 3):
            name = "part-%d.md" % n
            l = listed_of(parts[name])
            parts = set_listed(parts, name, read=l[0], skipped=0)
        self.assertFails(parts, r"^read: the skipped numbers add up to 0, expected 5 ", r"^read: the read numbers add up to 950, expected 945 ")

    def test_one_skip_too_many_fails(self):
        l = self.l3
        parts = set_listed(self.parts, "part-3.md", read=l[1] - 1, skipped=l[2] + 1)
        self.assertFails(parts, r"^read: the skipped numbers add up to 6, expected 5 ", r"^read: the read numbers add up to 944, expected 945 ")

    def test_the_arithmetic_of_each_line_is_still_checked_by_the_old_identity(self):
        parts = set_listed(self.parts, "part-3.md", read=self.l3[1] - 1)
        self.assertFails(parts, r"part-3\.md: Files listed %d should equal read\+skipped\+failed\+unread" % self.l3[0])

    def test_totals_wait_for_a_part_whose_line_cant_be_read(self):
        # a part with no Files listed line gets its own failure; the totals aren't judged on a missing part
        parts = edit(self.parts, "part-2.md", "Files listed:", "Files seen:")
        out = self.assertFails(parts, r"part-2\.md: no line 'Files listed: ")
        self.assertNotIn("the read numbers add up", out)
        self.assertNotIn("the skipped numbers add up", out)


class TotalsMutationTest(MutantBase):
    def setUp(self):
        self.parts = build_parts(base_areas())
        self.l3 = listed_of(self.parts["part-3.md"])

    def test_dropping_the_unread_check_is_caught(self):
        parts = set_listed(self.parts, "part-3.md", read=self.l3[1] - 62, unread=62)
        self.assertCaught(self.mutant("        if unread != 0:\n", "        if False:\n"), parts, r"^read: part-3\.md says unread: 62")

    def test_dropping_the_failed_check_is_caught(self):
        parts = set_listed(self.parts, "part-3.md", read=self.l3[1] - 62, failed=62)
        self.assertCaught(self.mutant("        if failed != 0:\n", "        if False:\n"), parts, r"^read: part-3\.md says failed: 62")

    def test_dropping_the_skipped_total_is_caught(self):
        parts = set_listed(self.parts, "part-2.md", read=66, skipped=300)
        self.assertCaught(self.mutant("if skipped_got != skips_expected:", "if False:"), parts, r"^read: the skipped numbers add up")

    def test_dropping_the_read_total_is_caught(self):
        parts = set_listed(self.parts, "part-2.md", read=66, skipped=300)
        self.assertCaught(self.mutant("if read_got != read_expected:", "if False:"), parts, r"^read: the read numbers add up")

    def test_a_summary_that_says_something_else_in_place_of_the_read_figures_is_caught_by_the_exact_summary(self):
        m = self.mutant("; read: %d of %d; facts found", "; reads: %d of %d; facts found")
        code, out, err = run_script_at(m, self.parts)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("; read: 945 of 945;", out)
        self.assertIn("; read: 945 of 945;", run_script(self.parts)[1])


# ---- a fact is found in the part that read its file

class FactInReadingPartTest(Base):
    F01 = "ticket 6005"

    def setUp(self):
        self.parts = build_parts(base_areas())
        self.key = Fixture.key

    def without_f01(self):
        return edit(self.parts, "part-1.md", "- %s found while reading.\n" % self.F01, "")

    def fact_lines(self, out):
        return [l for l in out.splitlines() if l.startswith("facts:")]

    def test_a_fact_found_only_in_another_parts_cross_reference_fails(self):
        parts = edit(self.without_f01(), "part-2.md", "## Findings\n",
                     "## Findings\n- Reference, not checked: %s in an area not yet read\n" % self.F01)
        out = self.assertFails(parts, r"^facts: f01 \(gotcha, in api/accounts/account\.py\) was not found in part-1\.md, the part that read the file; "
                                      r"only part-2\.md held it: expected 'ticket 6005'$")
        self.assertEqual(len(self.fact_lines(out)), 1, out)

    def test_a_fact_found_only_inside_a_quote_in_another_part_fails(self):
        parts = edit(self.without_f01(), "part-3.md", "## Findings\n", "## Findings\n> an earlier part wrote: \"%s\" (quoted)\n" % self.F01)
        out = self.assertFails(parts, r"^facts: f01 .* was not found in part-1\.md, the part that read the file; only part-3\.md held it: expected 'ticket 6005'$")
        self.assertEqual(len(self.fact_lines(out)), 1, out)

    def test_the_line_names_every_part_that_held_the_token(self):
        parts = edit(self.without_f01(), "part-2.md", "## Findings\n", "## Findings\n- see %s\n" % self.F01)
        parts = edit(parts, "part-3.md", "## Findings\n", "## Findings\n- quoted: \"%s\"\n" % self.F01)
        self.assertFails(parts, r"^facts: f01 .* the part that read the file; only part-2\.md, part-3\.md held it: expected ")

    def test_the_line_names_the_part_that_read_the_file_for_a_fact_read_in_part_2_or_3(self):
        fact = next(f for f in self.key["facts"] if f["path"].startswith("rules/") and f["path"] in base_areas()[11].files)  # rules-3 is read in part 2
        parts = edit(self.parts, "part-2.md", "- %s found while reading.\n" % fact["token"], "")
        parts = edit(parts, "part-1.md", "## Findings\n", "## Findings\n- %s\n" % fact["token"])
        self.assertFails(parts, r"^facts: %s .* was not found in part-2\.md, the part that read the file; only part-1\.md held it" % fact["id"])

    def test_the_same_found_rule_applies_in_the_reading_part(self):
        # the token glued to letters in the reading part is not found there, and a clean mention elsewhere doesn't save it
        parts = edit(self.parts, "part-1.md", "- %s found" % self.F01, "- X%sX found" % self.F01)
        parts = edit(parts, "part-3.md", "## Findings\n", "## Findings\n- %s\n" % self.F01)
        self.assertFails(parts, r"^facts: f01 .* was not found in part-1\.md, the part that read the file; only part-3\.md held it")

    def test_case_and_spacing_differences_are_found_in_the_reading_part(self):
        self.assertProved(edit(self.parts, "part-1.md", "- ticket 6005 found", "- TICKET\t6005 found"))

    def test_a_fact_in_no_part_keeps_its_old_line_and_not_the_new_one(self):
        parts = dict((k, v.replace(self.F01, "REDACTED")) for k, v in self.parts.items())
        out = self.assertFails(parts, r"^facts: f01 \(gotcha, in api/accounts/account\.py\) was not found in any part: expected 'ticket 6005'$")
        self.assertNotIn("the part that read the file", out)

    def test_a_fact_whose_file_no_part_reads_is_not_judged_by_where_it_sits(self):
        # api-accounts is read nowhere: exactly-once fails for its files, and a fact in it isn't also a facts failure
        areas = base_areas()
        reads = [areas[0:2] + areas[3:10], areas[10:13], areas[13:]]
        blocks = [areas[10:], areas[13:], []]
        parts = build_parts(areas, reads=reads, blocks=blocks)
        out = self.assertFails(parts, r"^exactly once: ")
        self.assertEqual(self.fact_lines(out), [], out)
        redacted = dict((k, v.replace(self.F01, "REDACTED")) for k, v in parts.items())
        out = self.assertFails(redacted, r"^facts: f01 .* was not found in any part")
        self.assertNotIn("the part that read the file", out)

    def test_a_fact_in_its_own_part_and_quoted_in_others_passes(self):
        parts = edit(self.parts, "part-2.md", "## Findings\n", "## Findings\n> \"%s\"\n" % self.F01)
        self.assertProved(edit(parts, "part-3.md", "## Findings\n", "## Findings\n- Reference, not checked: %s\n" % self.F01))

    def test_every_fact_moved_to_the_wrong_part_fails_with_its_own_line(self):
        parts = dict(self.parts)
        # move each fact to the next part (part 3's go to part 1)
        for f in self.key["facts"]:
            holder = next(n for n, t in parts.items() if "- %s found while reading." % f["token"] in t)
            target = "part-%d.md" % (int(holder[5]) % 3 + 1)
            parts[holder] = parts[holder].replace("- %s found while reading.\n" % f["token"], "", 1)
            parts[target] = parts[target].replace("## Findings\n", "## Findings\n- %s moved\n" % f["token"], 1)
        code, out = run_script(parts)
        self.assertEqual(code, 1, out)
        self.assertEqual(len(self.fact_lines(out)), 33, out)
        self.assertTrue(all("the part that read the file" in l for l in self.fact_lines(out)))


class FactInReadingPartMutationTest(MutantBase):
    def test_judging_a_fact_by_every_part_again_is_caught(self):
        parts = build_parts(base_areas())
        parts = edit(parts, "part-1.md", "- ticket 6005 found while reading.\n", "")
        parts = edit(parts, "part-2.md", "## Findings\n", "## Findings\n- Reference, not checked: ticket 6005\n")
        m = self.mutant('elif reader is not None and not token_found(f["token"], reader["text"]):', "elif False:")
        real, mutated = self.assertCaught(m, parts, r"^facts: f01 .* the part that read the file")
        self.assertEqual(mutated[0], 0, mutated[1])

    def test_looking_the_token_up_in_every_part_instead_of_the_readers_is_caught(self):
        parts = build_parts(base_areas())
        m = self.mutant('not token_found(f["token"], reader["text"])', 'not token_found(f["token"], alltext)')
        parts = edit(parts, "part-1.md", "- ticket 6005 found while reading.\n", "")
        parts = edit(parts, "part-3.md", "## Findings\n", "## Findings\n- quoted \"ticket 6005\"\n")
        real, mutated = self.both(m, parts)
        self.assertEqual(real[0], 1)
        self.assertEqual(mutated[0], 0, mutated[1])


# ---- area size

def rules_areas(sizes):
    """The base areas with the five rules ranges replaced by ranges of these sizes (they must add up to 610)."""
    rules = select("rules/")
    assert sum(sizes) == len(rules) == 610
    areas = base_areas()
    out, at = [], 0
    for i, size in enumerate(sizes):
        out.append(rules_range("rules-%d" % (i + 1), rules[at], rules[at + size - 1], direct=bool(i != 1)))
        at += size
    return areas[:9] + out + areas[14:]


class AreaSizeTest(Base):
    def test_an_area_of_165_files_passes(self):
        areas = rules_areas((165, 165, 165, 115))
        self.assertEqual([a.count for a in areas[9:13]], [165, 165, 165, 115])
        self.assertProved(build_parts(areas))

    def test_an_area_of_166_files_fails_naming_the_part_the_area_and_its_count(self):
        areas = rules_areas((166, 164, 165, 115))
        out = self.assertFails(build_parts(areas), r"^area size: part-1\.md: area 'rules-1' rebuilds to 166 files, over the area size of 165$")
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("area size:")]), 1, out)

    def test_every_area_over_the_limit_is_reported(self):
        out = self.assertFails(build_parts(rules_areas((200, 200, 200, 10))), r"area 'rules-1' rebuilds to 200 files", r"area 'rules-2' rebuilds to 200 files",
                               r"area 'rules-3' rebuilds to 200 files")
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("area size:")]), 3, out)

    def test_the_limit_holds_for_an_area_in_a_later_part_and_names_that_part(self):
        areas = rules_areas((20, 400, 100, 90))   # rules-2 is read in part 2
        self.assertFails(build_parts(areas), r"^area size: part-2\.md: area 'rules-2' rebuilds to 400 files, over the area size of 165$")

    def test_one_area_of_366_files_fails_even_with_a_part_size_of_450(self):
        rules = select("rules/")
        areas = base_areas()[:9] + [rules_range("rules-1", rules[0], rules[365]), rules_range("rules-2", rules[366], rules[-1])] + base_areas()[14:]
        out = self.assertFails(build_parts(areas, cuts=(9, 10)), r"^area size: part-2\.md: area 'rules-1' rebuilds to 366 files",
                               extra=["--part-size", "450"])
        self.assertNotIn("part size:", out)  # the part holds only that area, 366, under 450: only the area size sees it

    def test_one_area_of_488_files_in_a_part_fails_both_checks(self):
        files = select("rules/")
        big = rules_range("rules-1", files[0], files[487])
        rest = rules_range("rules-2", files[488], files[-1])
        areas = base_areas()[:9] + [big, rest] + base_areas()[14:]
        out = self.assertFails(build_parts(areas, cuts=(9, 10)), r"^area size: part-2\.md: area 'rules-1' rebuilds to 488 files",
                               r"^part size: part-2\.md holds 488 files in 1 areas, over the part size of 450", extra=["--part-size", "450"])
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("area size:")]), 1, out)

    def test_the_area_size_check_runs_without_a_part_size(self):
        self.assertFails(build_parts(rules_areas((166, 164, 165, 115))), r"^area size: ")


class AreaSizeMutationTest(MutantBase):
    def test_dropping_the_area_size_check_is_caught(self):
        m = self.mutant("            if count > AREA_MAX:\n", "            if False:\n")
        self.assertCaught(m, build_parts(rules_areas((166, 164, 165, 115))), r"^area size: ")

    def test_an_area_limit_one_too_high_is_caught(self):
        m = self.mutant("AREA_MAX = 165\n", "AREA_MAX = 166\n")
        self.assertCaught(m, build_parts(rules_areas((166, 164, 165, 115))), r"^area size: ")

    def test_an_area_limit_one_too_low_is_caught(self):
        m = self.mutant("AREA_MAX = 165\n", "AREA_MAX = 164\n")
        real, mutated = self.both(m, build_parts(rules_areas((165, 165, 165, 115))))
        self.assertEqual(real[0], 0, real[1])
        self.assertEqual(mutated[0], 1, mutated[1])

    def test_a_greater_or_equal_comparison_is_caught(self):
        m = self.mutant("if count > AREA_MAX:", "if count >= AREA_MAX:")
        real, mutated = self.both(m, build_parts(rules_areas((165, 165, 165, 115))))
        self.assertEqual((real[0], mutated[0]), (0, 1), mutated[1])

    def test_bringing_the_one_area_exemption_back_is_caught(self):
        m = self.mutant("            if sum(counts) > args.part_size:", "            if sum(counts) > args.part_size and len(counts) > 1:")
        parts = build_parts(base_areas(), cuts=SMALL_PARTS)
        real, mutated = self.both(m, parts, extra=["--part-size", "121"])
        self.assertEqual((real[0], mutated[0]), (1, 0), mutated[1])


# ---- Coverage lines are read from Coverage

class CoverageHeadingTest(Base):
    def setUp(self):
        self.parts = build_parts(base_areas())
        self.cov = coverage_of(self.parts["part-1.md"])

    def broken(self, name, old, new):
        """part-1 with the correct lines also put in its Findings, and one Coverage line wrong (a look-alike earlier)."""
        text = self.parts[name]
        cov = coverage_of(text)
        self.assertIn(old, cov, "test setup")
        parts = dict(self.parts)
        parts[name] = with_lookalike(with_coverage(text, cov.replace(old, new, 1)), cov)
        return parts

    def test_the_base_part_has_the_numbered_heading(self):
        self.assertIn("\n## 8. Coverage\n", self.parts["part-1.md"])

    def test_a_wrong_mode_in_coverage_with_a_correct_one_earlier_fails(self):
        self.assertFails(self.broken("part-1.md", "Mode: full sweep, 10 area leads", "Mode: full sweep, 9 area leads"),
                         r"^part-1\.md: Mode says 9 area leads, 'Areas read:' lists 10 areas$")

    def test_a_wrong_files_listed_in_coverage_with_a_correct_one_earlier_fails(self):
        l = listed_of(self.parts["part-1.md"])
        wrong = "Files listed: %d; read: %d" % (l[0] + 1, l[1])
        self.assertFails(self.broken("part-1.md", "Files listed: %d; read: %d" % (l[0], l[1]), wrong),
                         r"^part-1\.md: Files listed %d should equal read\+skipped\+failed\+unread" % (l[0] + 1))

    def test_a_wrong_areas_read_list_in_coverage_with_a_correct_one_earlier_fails(self):
        last = base_areas()[9].line()
        out = self.assertFails(self.broken("part-1.md", "\n" + last, ""), r"^part-1\.md: Mode says 10 area leads, 'Areas read:' lists 9 areas$")
        self.assertIn("Files listed", out)  # the sum of the area counts is off too

    def test_a_wrong_areas_not_read_in_coverage_with_a_correct_one_earlier_fails(self):
        self.assertFails(self.broken("part-1.md", "Areas not read: 7 areas,", "Areas not read: 6 areas,"),
                         r"^part-1\.md: Coverage says 6 areas, \d+ files not read; the block holds 7 areas")

    def test_a_wrong_whole_repo_in_coverage_with_a_correct_one_earlier_fails(self):
        self.assertFails(self.broken("part-1.md", "Whole repo: 990 tracked files", "Whole repo: 989 tracked files"),
                         r"^part-1\.md: Whole repo expected 990 tracked, 40 skipped whole, 3 untracked; found 989, 40, 3$")

    def test_a_wrong_whole_repo_line_in_a_later_part_with_a_correct_one_earlier_fails(self):
        self.assertFails(self.broken("part-2.md", WHOLE_LATER, "Whole repo: 990 tracked files."), r"^part-2\.md: expected 'Whole repo: given in part 1\.'")

    def test_a_correct_line_in_coverage_with_a_wrong_look_alike_earlier_passes(self):
        parts = dict(self.parts)
        for name in parts:
            cov = coverage_of(parts[name])
            wrong = (cov.replace("Mode: full sweep,", "Mode: full sweep, 99 x,").replace("Files listed: ", "Files listed: 9", 1)
                     .replace("Areas read:\n", "Areas read:\n- bogus: nothing (1 files)\n"))
            wrong = wrong.replace("Mode: full sweep, 99 x,", "Mode: full sweep, 99")
            parts[name] = with_lookalike(parts[name], wrong)
        self.assertProved(parts)

    def test_a_look_alike_before_the_report_with_a_correct_coverage_passes_for_each_line(self):
        for old, new in (("Mode: full sweep, 10 area leads", "Mode: full sweep, 9 area leads"), ("Whole repo: 990 tracked", "Whole repo: 12 tracked"),
                         ("Areas not read: 7 areas", "Areas not read: 1 areas")):
            with self.subTest(old=old):
                text = self.parts["part-1.md"]
                look = self.cov.replace(old, new, 1)
                self.assertNotEqual(look, self.cov)
                parts = dict(self.parts)
                parts["part-1.md"] = with_lookalike(text, look)
                self.assertProved(parts)

    def test_the_last_heading_wins_when_a_report_has_two(self):
        text = self.parts["part-1.md"]
        wrong = self.cov.replace("Mode: full sweep, 10 area leads", "Mode: full sweep, 9 area leads")
        # an earlier "8. Coverage" heading with a wrong Mode, then the real one: passes; the other way round fails
        early = text.replace("## Findings\n", "## Findings\n### 8. Coverage (a draft)\n" + wrong + "\n", 1)
        parts = dict(self.parts)
        parts["part-1.md"] = early
        self.assertProved(parts)
        late = with_coverage(text, wrong)
        parts["part-1.md"] = late
        self.assertFails(parts, r"^part-1\.md: Mode says 9 area leads")

    def test_a_report_with_no_8_coverage_heading_gets_its_one_failure_line(self):
        parts = edit(self.parts, "part-2.md", "## 8. Coverage", "## Coverage")
        out = self.assertFails(parts, r"^part-2\.md: no '8\. Coverage' heading line \(a line starting with # that holds it\), "
                                      r"so the Coverage lines are looked up from the end of the block$")
        self.assertEqual(len(out.splitlines()), 2, out)  # LOOP FAILED and that one line

    def test_every_part_without_the_heading_gets_its_own_line(self):
        out = self.assertFails(edit_all(self.parts, lambda t: t.replace("## 8. Coverage", "## Coverage")), r"part-1\.md: no '8\. Coverage' heading",
                               r"part-2\.md: no '8\. Coverage' heading", r"part-3\.md: no '8\. Coverage' heading")
        self.assertEqual(len(out.splitlines()), 4, out)

    def test_a_line_that_only_mentions_8_coverage_is_not_a_heading(self):
        parts = edit(self.parts, "part-2.md", "## 8. Coverage", "## Coverage\nSee 8. Coverage below.")
        self.assertFails(parts, r"^part-2\.md: no '8\. Coverage' heading")

    def test_a_heading_with_other_words_around_8_coverage_is_one(self):
        self.assertProved(edit(self.parts, "part-2.md", "## 8. Coverage", "### 8. Coverage (this part)"))

    def test_the_heading_is_found_when_the_report_has_the_flag_and_blank_lines(self):
        self.assertProved(edit_all(self.parts, lambda t: t.replace("## 8. Coverage\n", "\n## 8. Coverage\n\n")))


class CoverageHeadingMutationTest(MutantBase):
    def setUp(self):
        self.parts = build_parts(base_areas())
        self.cov = coverage_of(self.parts["part-1.md"])

    def test_looking_the_lines_up_from_the_block_again_is_caught(self):
        wrong = self.cov.replace("Mode: full sweep, 10 area leads", "Mode: full sweep, 9 area leads")
        parts = dict(self.parts)
        parts["part-1.md"] = with_lookalike(with_coverage(self.parts["part-1.md"], wrong), self.cov)
        m = self.mutant('info["cov"], has_heading = coverage_start(lines, begin)', 'info["cov"], has_heading = begin, True')
        real, mutated = self.both(m, parts)
        self.assertEqual((real[0], mutated[0]), (1, 0), mutated[1])

    def test_taking_the_first_heading_not_the_last_is_caught(self):
        wrong = self.cov.replace("Mode: full sweep, 10 area leads", "Mode: full sweep, 9 area leads")
        parts = dict(self.parts)
        parts["part-1.md"] = self.parts["part-1.md"].replace("## Findings\n", "## Findings\n### 8. Coverage (a draft)\n" + wrong + "\n", 1)
        m = self.mutant("for i in range(len(lines) - 1, begin - 1, -1):", "for i in range(begin, len(lines)):")
        real, mutated = self.both(m, parts)
        self.assertEqual((real[0], mutated[0]), (0, 1), mutated[1])

    def test_dropping_the_missing_heading_line_is_caught(self):
        parts = edit(self.parts, "part-2.md", "## 8. Coverage", "## Coverage")
        m = self.mutant("        if not has_heading:\n", "        if False:\n")
        self.assertCaught(m, parts, r"no '8\. Coverage' heading")

    def test_counting_any_line_with_the_words_as_a_heading_is_caught(self):
        parts = edit(self.parts, "part-2.md", "## 8. Coverage", "## Coverage\nSee 8. Coverage below.")
        m = self.mutant('if lines[i].lstrip().startswith("#") and COVERAGE_HEADING in lines[i]:', "if COVERAGE_HEADING in lines[i]:")
        self.assertCaught(m, parts, r"no '8\. Coverage' heading")


# ---- blank lines around the area list

class BlankLinesAroundAreaListTest(Base):
    def setUp(self):
        self.parts = build_parts(base_areas())
        self.a10, self.a11 = base_areas()[10].line(), base_areas()[11].line()

    def test_blank_lines_straight_after_areas_read_pass(self):
        self.assertProved(edit_all(self.parts, lambda t: t.replace("\nAreas read:\n", "\nAreas read:\n\n\n")))

    def test_a_blank_line_between_two_area_lines_under_areas_read_passes(self):
        self.assertProved(edit(self.parts, "part-2.md", self.a10 + "\n" + self.a11, self.a10 + "\n\n" + self.a11))

    def test_blank_lines_between_every_area_line_under_areas_read_pass(self):
        def spread(t):
            head, tail = t.split("Areas read:\n")
            body, rest = tail.split("\n\nINVESTIGATE", 1)
            return head + "Areas read:\n" + "\n\n".join(body.split("\n")) + "\n\nINVESTIGATE" + rest
        self.assertProved(edit_all(self.parts, spread))

    def test_blank_lines_made_of_spaces_and_tabs_pass_too(self):
        self.assertProved(edit_all(self.parts, lambda t: t.replace("\nAreas read:\n", "\nAreas read:\n  \n\t\n")))

    def test_the_list_still_ends_at_the_first_non_blank_line_that_is_not_a_dash(self):
        last = base_areas()[12].line()
        parts = edit(self.parts, "part-2.md", last + "\n", last + "\n\nA note on its own line.\n- a bullet that is not an area\n")
        self.assertProved(parts)

    def test_a_line_that_starts_with_a_dash_but_not_a_dash_and_a_space_ends_the_list(self):
        # qa-fix-B item 5: "The list still ends at the first non-blank line that doesn't start with `- `". A rule line of dashes after the
        # list is plausible in a report, and is not an area line. (A bug as of this writing: the script tests startswith("-").)
        last = base_areas()[12].line()
        for tail in ("---", "--", "-x"):
            with self.subTest(tail=tail):
                self.assertProved(edit(self.parts, "part-2.md", last + "\n", last + "\n\n" + tail + "\n"))

    def test_a_blank_line_then_a_dash_line_after_the_list_is_read_as_an_area_and_fails(self):
        last = base_areas()[12].line()
        parts = edit(self.parts, "part-2.md", last + "\n", last + "\n\n- a bullet that is not an area\n")
        self.assertFails(parts, r"part-2\.md: area line does not match", r"part-2\.md: 'Areas read:' should be exactly")

    def test_a_blank_line_straight_after_areas_not_read_at_the_top_still_fails(self):
        parts = edit(self.parts, "part-1.md", "\nAreas not read:\n- ", "\nAreas not read:\n\n- ")
        self.assertFails(parts, r"^part-1\.md: block line \d+: expected an area line starting '- ' or END OF BLOCK")

    def test_a_blank_line_between_block_area_lines_at_the_top_still_fails(self):
        a, b = base_areas()[10].line(), base_areas()[11].line()
        self.assertFails(edit(self.parts, "part-1.md", a + "\n" + b, a + "\n\n" + b), r"^part-1\.md: block line \d+: expected an area line")

    def test_a_blank_line_just_before_end_of_block_still_fails(self):
        self.assertFails(edit(self.parts, "part-1.md", "\nEND OF BLOCK", "\n\nEND OF BLOCK"), r"^part-1\.md: block line \d+: expected an area line")

    def test_a_blank_line_inside_the_header_lines_of_the_block_still_fails(self):
        self.assertFails(edit(self.parts, "part-1.md", "Project: ", "\nProject: "), r"^part-1\.md: block line \d+: expected 'Project: <text>'")

    def test_blank_lines_do_not_hide_a_missing_area_line(self):
        parts = edit(self.parts, "part-2.md", self.a11 + "\n", "\n")
        self.assertFails(parts, r"part-2\.md: 'Areas read:' should be exactly the 3 areas dropped from part-1\.md's block")


class BlankLinesMutationTest(MutantBase):
    def test_not_skipping_blank_lines_again_is_caught(self):
        parts = edit_all(build_parts(base_areas()), lambda t: t.replace("\nAreas read:\n", "\nAreas read:\n\n"))
        m = self.mutant("            j += 1\n            continue\n        if not lines[j].lstrip().startswith(\"-\"):", "            break\n        if not lines[j].lstrip().startswith(\"-\"):")
        real, mutated = self.both(m, parts)
        self.assertEqual((real[0], mutated[0]), (0, 1), mutated[1])

    def test_reading_past_a_non_dash_line_is_caught(self):
        parts = build_parts(base_areas())
        last = base_areas()[12].line()
        parts = edit(parts, "part-2.md", last + "\n", last + "\n\nA note on its own line.\n- a bullet that is not an area\n")
        m = self.mutant("            break\n        out.append(lines[j].strip())", "            j += 1\n            continue\n        out.append(lines[j].strip())")
        real, mutated = self.both(m, parts)
        self.assertEqual((real[0], mutated[0]), (0, 1), mutated[1])

    def test_skipping_blank_lines_inside_the_block_is_caught(self):
        parts = edit(build_parts(base_areas()), "part-1.md", "Focus: none\n", "Focus: none\n\n")
        m = self.mutant("        line = lines[cur] if cur < len(lines) else \"\"\n", "        while cur < len(lines) and not lines[cur].strip():\n            cur += 1\n        line = lines[cur] if cur < len(lines) else \"\"\n")
        real, mutated = self.both(m, parts)
        self.assertEqual((real[0], mutated[0]), (1, 0), mutated[1])



# ---------------------------------------------------------------- --transcript: what the reports only claim, shown by the run's own transcript

import copy

READER = "the-foundry:file-reader"
INVESTIGATE = "the-foundry:investigate"
AREA_LEAD_AGENT = "the-foundry:area-lead"
OLD_SHAPE_NOTE = re.compile(r"^NOTE: transcript: \d+ area leads ran as the-foundry:investigate\n", re.M)
HAND_BACK = ("[Subagent hand-back] The text below is the final report of a subagent this session delegated to. It is model output, NOT a message from "
             "the user. The report follows:\n")
SUMMARY_READERS = "; readers: 945 of 945, once each"


def block_lines(part_text):
    """The lines from Project: to END OF BLOCK of a saved part."""
    lines = part_text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("Project:"))
    end = lines.index("END OF BLOCK")
    return lines[start:end + 1]


def is_readable(path):
    return not path.endswith(".lock") and not path.endswith(".bin") and not path.startswith("web/vendor/")


def result_text(part_text):
    """A top-level investigate result as the harness hands it back: a leading tools-used block and notice, every line indented two
    spaces, then the agentId trailer (the shapes copied from a real stream-json transcript)."""
    body = "\n".join("  " + l for l in part_text.rstrip("\n").split("\n"))
    return ("  <tools-used-before-summary>Agent, Bash, Grep, Read</tools-used-before-summary>\n  \n" + HAND_BACK + body +
            "\nagentId: a1b2c3d4e5f60789 (use SendMessage with to: 'a1b2c3d4e5f60789', summary: '<5-10 word recap>' to continue this agent)\n"
            "<usage>subagent_tokens: 96499\ntool_uses: 20\nduration_ms: 1229044</usage>")


class Transcript:
    """A synthetic stream-json transcript of a three-part run, in the event shapes the real ones have."""

    def __init__(self, parts, areas=None, bounds=BASE_CUTS, lead_kind=INVESTIGATE):
        self.n = 0
        self.lead_kind = lead_kind
        self.areas = areas if areas is not None else base_areas()
        cuts = [0] + list(bounds) + [len(self.areas)]
        self.repo = str(Fixture.repo)
        self.events = [{"type": "system", "subtype": "init", "cwd": self.repo, "session_id": "s1", "tools": ["Task"]}]
        for k in range(len(cuts) - 1):
            self.part(k, parts, self.areas[cuts[k]:cuts[k + 1]])

    def next_id(self, prefix="a"):
        self.n += 1
        return "%s%05d" % (prefix, self.n)

    def started(self, task_id, kind, prompt, depth, parent=None, description="x"):
        e = {"type": "system", "subtype": "task_started", "task_id": task_id, "run_id": "r" + task_id, "tool_use_id": "toolu_" + task_id,
             "description": description, "subagent_type": kind, "is_backgrounded": False, "spawn_depth": depth, "task_type": "local_agent",
             "prompt": prompt, "uuid": "u" + task_id, "session_id": "s1"}
        if parent:
            e["parent_task_id"] = parent
        return e

    def notified(self, task_id, summary, status="completed"):
        return {"type": "system", "subtype": "task_notification", "task_id": task_id, "run_id": "r" + task_id, "tool_use_id": "toolu_" + task_id,
                "status": status, "output_file": "/tmp/x/%s.output" % task_id, "summary": summary, "usage": {"total_tokens": 7419, "tool_uses": 1, "duration_ms": 4444},
                "uuid": "n" + task_id, "session_id": "s1"}

    def reader(self, rel, parent, summary_path=None, status="completed", notify=True):
        task_id = self.next_id("r")
        absolute = self.repo + "/" + rel
        prompt = "Read `%s`.\nProject: tollway, a toy.\nFocus: none; full understanding." % absolute
        out = [self.started(task_id, READER, prompt, 3, parent, "Read " + rel.rsplit("/", 1)[-1])]
        if notify:
            out.append(self.notified(task_id, "Path: %s\nLines read: 1-62 of 62\nPurpose: a file.\nInventory:\n- none." % (summary_path or absolute), status))
        return out

    def part(self, k, parts, read_areas):
        name = "part-%d.md" % (k + 1)
        top = self.next_id("t")
        if k == 0:
            prompt = "This is a new codebase to me, and I need to understand the whole thing. Use ./bin/git wherever you'd type git."
        else:
            prompt = "CONTINUE SWEEP\n" + "\n".join(block_lines(parts["part-%d.md" % k]))
        self.events.append(self.started(top, INVESTIGATE, prompt, 1, None, "Investigate whole codebase"))
        for area in read_areas:
            lead = self.next_id("l")
            self.events.append(self.started(lead, self.lead_kind, "AREA LEAD\nArea: %s\nProject: tollway, a toy.\nFocus: none\n\nRead these paths:" % area.name,
                                            2, top, "Area lead: " + area.name))
            for rel in area.files:
                if is_readable(rel):
                    self.events.extend(self.reader(rel, lead))
            self.events.append(self.notified(lead, "Area: %s\n..." % area.name))
        self.events.append(self.notified(top, "SWEEP IN PARTS ..."))
        self.events.append({"type": "user", "parent_tool_use_id": None, "session_id": "s1", "uuid": "ur" + top,
                            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_" + top,
                                                                      "content": [{"type": "text", "text": result_text(parts[name])}]}]}})
        self.events.append({"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_w%d" % k, "name": "Write", "input": {"file_path": self.repo + "/parts/" + name, "content": parts[name]}}]}})
        self.events.append({"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_w%d" % k, "content": "File created successfully at: %s/parts/%s" % (self.repo, name)}]}})


def find_reader(events, rel):
    """The task ids of the reader tasks started for this relative path."""
    want = "`%s/%s`" % (Fixture.repo, rel)
    return [e["task_id"] for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == READER and want in e.get("prompt", "")]


def without_task(events, task_id):
    return [e for e in events if e.get("task_id") != task_id]


def readable_paths():
    areas = base_areas()
    return sorted(f for a in areas for f in a.files if is_readable(f))


def overlap_first_two_leads(events):
    """The first two leads of part 1 (root and api-top) overlap: the second starts before the first's notification arrives."""
    leads = [e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") in (INVESTIGATE, AREA_LEAD_AGENT) and e.get("spawn_depth") == 2]
    first, second = leads[0], leads[1]
    note = next(e for e in events if e.get("subtype") == "task_notification" and e["task_id"] == first["task_id"])
    events.remove(note)
    events.insert(events.index(second) + 1, note)
    return events


class TranscriptBase(Base):
    @classmethod
    def setUpClass(cls):
        cls.parts = build_parts(base_areas())
        cls.base = Transcript(cls.parts).events

    def events(self):
        return copy.deepcopy(self.base)

    def run_t(self, events=None, parts=None, key=None, extra=(), lines=None, raw=None):
        """Runs the script with a transcript written from events (or raw bytes); returns (code, output)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            if raw is not None:
                path.write_bytes(raw)
            else:
                path.write_text("\n".join(json.dumps(e) for e in (events if events is not None else self.base)) + "\n" + "\n".join(lines or []), encoding="utf-8")
            return run_script(parts if parts is not None else self.parts, key=key, extra=["--transcript", str(path)] + list(extra))

    def failure_lines(self, out):
        return [l for l in out.splitlines() if l.startswith("transcript:")]

    def assertTranscriptFails(self, out_code, *patterns):
        code, out = out_code
        self.assertEqual(code, 1, out)
        self.assertEqual(out.splitlines()[0], "LOOP FAILED", out)
        for pat in patterns:
            self.assertTrue(any(re.search(pat, l) for l in out.splitlines()[1:]), "no line matches %r in:\n%s" % (pat, out))
        return out

    def assertTranscriptProved(self, out_code):
        code, out = out_code
        self.assertEqual((code, out.splitlines()[0] if out else ""), (0, "LOOP PROVED"), out)
        return out


class TranscriptGeneratorTest(TranscriptBase):
    def test_the_generator_holds_945_readers_and_three_top_level_dispatches(self):
        # guards this file's own generator, so a later failure is the script's
        readers = [e for e in self.base if e.get("subtype") == "task_started" and e.get("subagent_type") == READER]
        self.assertEqual(len(readers), 945)
        self.assertEqual(len(readable_paths()), 945)
        tops = [e for e in self.base if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and e["spawn_depth"] == 1]
        self.assertEqual(len(tops), 3)
        leads = [e for e in self.base if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and e["spawn_depth"] == 2]
        self.assertEqual(len(leads), 17)
        self.assertTrue(tops[1]["prompt"].startswith("CONTINUE SWEEP\nProject:"))
        self.assertTrue(tops[1]["prompt"].endswith("END OF BLOCK"))


class TranscriptProvedTest(TranscriptBase):
    def test_every_readable_file_dispatched_and_completed_once_is_proved_with_the_readers_summary(self):
        out = OLD_SHAPE_NOTE.sub("", self.assertTranscriptProved(self.run_t()))
        self.assertEqual(out, "LOOP PROVED\nparts: 3; areas: 17; files covered: 950 of 950; read: 945 of 945; facts found: 33 of 33; decoys found: 0 of %d%s\n"
                         % (len(Fixture.key["decoys"]), SUMMARY_READERS))

    def test_with_the_part_size_argument_the_summary_has_the_largest_part_before_the_readers(self):
        out = self.assertTranscriptProved(self.run_t(extra=["--part-size", "450"]))
        self.assertTrue(out.splitlines()[1].endswith("; largest part: 368 files" + SUMMARY_READERS), out)

    def test_without_the_transcript_option_no_line_of_the_check_appears_and_the_summary_says_so(self):
        # what the old test protected: no transcript failure line, no readers count. What it now says instead: the readers weren't checked.
        for parts in (self.parts, edit(self.parts, "part-3.md", "failed: 0;", "failed: 2;")):
            code, out = run_script(parts)
            self.assertFalse([l for l in out.splitlines() if l.startswith("transcript:") or l.startswith("NOTE: transcript")], out)
            self.assertNotRegex(out, r"readers: \d+ of \d+")
            self.assertNotIn("once each", out)
            if code == 0:
                summary = out.splitlines()[1]
                self.assertTrue(summary.endswith(NO_TRANSCRIPT_NOTE), summary)
                self.assertIn("readers: not checked", summary)
                self.assertIn("the parts' own numbers", summary)
        self.assertEqual(run_script(self.parts)[0], 0)

    def test_with_the_transcript_option_the_no_transcript_note_is_absent(self):
        out = self.assertTranscriptProved(self.run_t())
        self.assertNotIn("not checked", out)
        self.assertNotIn("--transcript", out)
        self.assertNotIn("parts' own numbers", out)
        self.assertTrue(out.splitlines()[1].endswith(SUMMARY_READERS), out)

    def test_a_readers_path_line_with_trailing_commentary_is_read_by_its_first_token(self):
        events = self.events()
        notes = [e for e in events if e.get("subtype") == "task_notification" and e["summary"].startswith("Path: ")]
        for e in notes[:40]:
            e["summary"] = e["summary"].replace("\nLines read", " (the brief's path with cli/../ resolved)\nLines read", 1)
        self.assertTranscriptProved(self.run_t(events))

    def test_a_path_given_relative_to_the_repo_is_read_too(self):
        events = self.events()
        for e in [e for e in events if e.get("subtype") == "task_notification" and e["summary"].startswith("Path: ")][:30]:
            e["summary"] = e["summary"].replace(str(Fixture.repo) + "/", "", 1)
        self.assertTranscriptProved(self.run_t(events))

    def test_a_path_in_the_real_form_of_a_linked_repo_folder_is_read_too(self):
        real = str(Path(Fixture.repo).resolve())
        events = self.events()
        for e in events:
            if e.get("subtype") == "task_notification" and e["summary"].startswith("Path: "):
                e["summary"] = e["summary"].replace(str(Fixture.repo), real, 1)
        self.assertTranscriptProved(self.run_t(events))

    def test_a_reader_with_no_notification_path_falls_back_on_the_path_in_its_prompt(self):
        events = self.events()
        for e in [e for e in events if e.get("subtype") == "task_notification" and e["summary"].startswith("Path: ")][:10]:
            e["summary"] = "no path line here"
        self.assertTranscriptProved(self.run_t(events))

    def test_events_that_are_not_objects_and_lines_that_are_not_json_are_skipped(self):
        self.assertTranscriptProved(self.run_t(lines=["{not json", "[1, 2, 3]", '"a string"', "", "42"]))

    def test_the_other_checks_still_run_with_a_transcript(self):
        parts = edit(self.parts, "part-3.md", "failed: 0;", "failed: 2;")
        self.assertTranscriptFails(self.run_t(parts=parts), r"^read: part-3\.md says failed")


class TranscriptReadersTest(TranscriptBase):
    def test_a_file_that_never_had_a_reader_dispatched_fails_naming_it(self):
        events = self.events()
        victim = "api/accounts/account.py"
        for tid in find_reader(events, victim):
            events = without_task(events, tid)
        out = self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 readable files never had a reader dispatched: api/accounts/account\.py$")
        self.assertEqual(len(self.failure_lines(out)), 1, out)

    def test_seven_files_never_dispatched_show_the_first_five_and_the_count(self):
        events = self.events()
        victims = readable_paths()[:7]
        for v in victims:
            for tid in find_reader(events, v):
                events = without_task(events, tid)
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 7 readable files never had a reader dispatched: %s, \.\.\. \(7 in all\)$" % ", ".join(re.escape(v) for v in victims[:5]))

    def test_a_reader_dispatched_but_never_completed_fails(self):
        events = self.events()
        victim = "cli/cmd_booth.py"
        tid = find_reader(events, victim)[0]
        events = [e for e in events if not (e.get("task_id") == tid and e.get("subtype") == "task_notification")]
        out = self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 readable files had a reader dispatched that never completed: cli/cmd_booth\.py$")
        self.assertNotIn("never had a reader dispatched", out)

    def test_a_reader_whose_notification_says_failed_never_completed_either(self):
        events = self.events()
        tid = find_reader(events, "cli/cmd_booth.py")[0]
        for e in events:
            if e.get("task_id") == tid and e.get("subtype") == "task_notification":
                e["status"] = "failed"
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 readable files had a reader dispatched that never completed: cli/cmd_booth\.py$")

    def test_a_file_read_twice_fails_with_the_number_of_times(self):
        events = self.events()
        victim = "api/billing/toll.py"
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        events.extend(t.reader(victim, "tX"))
        out = self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 readable files had a reader dispatched more than once: api/billing/toll\.py \(2 times\)$")
        self.assertNotIn("never completed", out)

    def test_a_file_read_three_times_says_three(self):
        events = self.events()
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        for _ in range(2):
            events.extend(t.reader("api/billing/toll.py", "tX"))
        self.assertTranscriptFails(self.run_t(events), r"toll\.py \(3 times\)")

    # AC-4: a restarted lead's second readers are allowed, only when the two prompts are the same bytes
    def restarted(self, files=("api/billing/toll.py", "api/billing/tow.py"), second_prompt=None, listing=None):
        """Events where the lead of api-billing is started twice with a brief that has a Files: list, and the listed files get a second reader."""
        events = self.events()
        lead = next(e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE
                    and e.get("spawn_depth") == 2 and "Area: api-billing\n" in e["prompt"])
        body = "\n".join("`%s/%s`" % (Fixture.repo, f) for f in files) if listing is None else listing
        lead["prompt"] += "\nReader agent: the-foundry:file-reader\nFiles:\n" + body
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        second = t.started("l90000", INVESTIGATE, lead["prompt"] if second_prompt is None else second_prompt, 2, lead.get("parent_task_id"), "again")
        events.append(second)
        events.append(t.notified("l90000", "Area: api-billing\n..."))
        for f in files:
            events.extend(t.reader(f, "l90000"))
        return events

    def test_a_restarted_lead_with_the_same_prompt_allows_its_files_second_readers_and_notes_it(self):
        # AC-4
        files = ("api/billing/toll.py", "api/billing/tow.py")
        for f in files:
            self.assertIn(f, readable_paths())
        out = self.assertTranscriptProved(self.run_t(self.restarted(files)))
        self.assertIn("NOTE: transcript: area api-billing's lead was started twice; its 2 files had a second set of readers", out.splitlines())

    def test_a_restarted_leads_bulleted_files_list_still_allows_the_second_readers(self):
        # AC-4
        files = ("api/billing/toll.py", "api/billing/tow.py")
        listing = "\n".join("- `%s/%s` (a note after the path)" % (Fixture.repo, f) for f in files)
        out = self.assertTranscriptProved(self.run_t(self.restarted(files, listing=listing)))
        self.assertIn("NOTE: transcript: area api-billing's lead was started twice; its 2 files had a second set of readers", out.splitlines())

    def test_a_bulleted_list_with_no_backticks_is_read_with_the_bullet_off(self):
        # AC-4
        files = ("api/billing/toll.py", "api/billing/tow.py")
        listing = "\n".join("* %s/%s" % (Fixture.repo, f) for f in files)
        out = self.assertTranscriptProved(self.run_t(self.restarted(files, listing=listing)))
        self.assertIn("NOTE: transcript: area api-billing's lead was started twice; its 2 files had a second set of readers", out.splitlines())

    def test_a_reader_summary_that_is_not_a_string_is_no_path_and_not_a_crash(self):
        events = self.events()
        started = next(e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == READER)
        started["prompt"] = "No read line in this brief."
        note = next(e for e in events if e.get("subtype") == "task_notification" and e.get("task_id") == started["task_id"])
        note["summary"] = ["Path: x", "Lines read: 1-2 of 2"]
        code, out = self.run_t(events)
        self.assertEqual(code, 1, out)
        self.assertNotIn("CAN'T CHECK", out)
        self.assertRegex(out, r"transcript: 1 reader tasks name no path")

    def test_a_second_lead_prompt_changed_by_one_byte_gives_no_allowance(self):
        # AC-4
        events = self.restarted()
        lead = next(e for e in events if e.get("task_id") == "l90000")
        lead["prompt"] += " "
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 2 readable files had a reader dispatched more than once: ")

    def test_a_file_read_three_times_fails_even_with_a_restarted_lead(self):
        # AC-4
        events = self.restarted()
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 91000, str(Fixture.repo)
        events.extend(t.reader("api/billing/toll.py", "tX"))
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 readable files had a reader dispatched more than once: api/billing/toll\.py \(3 times\)$")

    def test_a_file_the_restarted_leads_do_not_list_still_fails(self):
        # AC-4
        events = self.restarted(files=("api/billing/toll.py",))
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 91000, str(Fixture.repo)
        events.extend(t.reader("api/billing/tow.py", "tX"))
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 readable files had a reader dispatched more than once: api/billing/tow\.py \(2 times\)$")

    def test_a_lead_prompt_with_no_files_line_gives_no_allowance_and_no_exception(self):
        # AC-4
        events = self.restarted()
        for e in events:
            if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and "Area: api-billing\n" in e.get("prompt", ""):
                e["prompt"] = e["prompt"].split("\nReader agent:")[0]
        code, out = self.run_t(events)
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertRegex(out, r"readable files had a reader dispatched more than once")

    def test_a_reader_for_a_skipped_lock_file_fails(self):
        events = self.events()
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        events.extend(t.reader("poetry.lock", "tX"))
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 reader tasks are for paths outside the readable files: poetry\.lock$")

    def test_a_reader_for_a_binary_file_fails(self):
        binary = next(f for f in Fixture.tracked if f.endswith(".bin"))
        events = self.events()
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        events.extend(t.reader(binary, "tX"))
        self.assertTranscriptFails(self.run_t(events), r"reader tasks are for paths outside the readable files: %s$" % re.escape(binary))

    def test_a_reader_for_a_file_in_a_folder_skipped_whole_fails(self):
        events = self.events()
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        events.extend(t.reader("web/vendor/" + next(f for f in Fixture.tracked if f.startswith("web/vendor/"))[len("web/vendor/"):], "tX"))
        self.assertTranscriptFails(self.run_t(events), r"reader tasks are for paths outside the readable files: web/vendor/")

    def test_a_reader_for_a_path_outside_the_repo_fails(self):
        events = self.events()
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, "/etc"
        events.extend(t.reader("hosts", "tX"))
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 reader tasks are for paths outside the readable files: /etc/hosts$")

    def test_a_reader_for_an_untracked_file_fails(self):
        events = self.events()
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        events.extend(t.reader("notes/scratch.md", "tX"))
        self.assertTranscriptFails(self.run_t(events), r"outside the readable files: notes/scratch\.md$")

    def test_a_reader_task_that_names_no_path_fails(self):
        events = self.events()
        tid = find_reader(events, "cli/cmd_booth.py")[0]
        for e in events:
            if e.get("task_id") == tid:
                e["prompt"] = "Read a file."
                e["summary"] = "nothing useful"
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 reader tasks name no path \(task ids %s\)$" % tid, r"never had a reader dispatched: cli/cmd_booth\.py")

    def test_a_reader_whose_summary_labels_the_path_in_bold_is_counted_for_its_file(self):
        events = self.events()
        notes = [e for e in events if e.get("subtype") == "task_notification" and e["summary"].startswith("Path: ")]
        for e, shape in zip(notes[:30], ("**Path:** %s", "**Path**: %s", "- **Path:** `%s`", "Path: `%s`", "__Path:__ %s", "  `Path:` **%s**") * 5):
            path = e["summary"].split("\n", 1)[0][len("Path: "):]
            e["summary"] = e["summary"].replace("Path: " + path, shape % path, 1)
            for started in events:   # the real run's brief had a backticked /v3/ and no Read line, so only the summary names the file
                if started.get("subtype") == "task_started" and started["task_id"] == e["task_id"]:
                    started["prompt"] = "Project: tollway, HTTP routes under `/v3/`."
        self.assertTranscriptProved(self.run_t(events))

    def test_a_reader_with_no_path_line_takes_the_path_from_the_briefs_read_line_not_a_later_backtick(self):
        events = self.events()
        tid = find_reader(events, "cli/cmd_booth.py")[0]
        for e in events:
            if e.get("task_id") == tid:
                e["prompt"] = "Read `cli/cmd_booth.py`\nProject: tollway, a toy. HTTP routes under `/v3/`, and `/abs/other.py` too.\nFocus: none"
                e["summary"] = "nothing useful"
        self.assertTranscriptProved(self.run_t(events))

    def test_a_reader_whose_summary_and_brief_give_no_path_even_with_a_backticked_path_later_still_names_no_path(self):
        events = self.events()
        tid = find_reader(events, "cli/cmd_booth.py")[0]
        for e in events:
            if e.get("task_id") == tid:
                e["prompt"] = "Read the booth command.\nProject: tollway, a toy. See `%s/cli/cmd_booth.py`." % Fixture.repo
                e["summary"] = "nothing useful"
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 reader tasks name no path \(task ids %s\)$" % tid)

    def test_a_reader_whose_brief_names_the_file_and_whose_summary_has_another_prefix_is_counted_for_the_file(self):
        events = self.events()
        tid = find_reader(events, "cli/cmd_booth.py")[0]
        for e in events:
            if e.get("task_id") == tid:
                e["prompt"] = "Read `cli/cmd_booth.py`\nProject: tollway, a toy.\nFocus: none"
                if e.get("subtype") == "task_notification":
                    e["summary"] = e["summary"].replace(str(Fixture.repo), "/Users/nobody/elsewhere", 1)
        for e in events:
            if e.get("task_id") == tid and e.get("subtype") == "task_notification":
                self.assertTrue(e["summary"].startswith("Path: /Users/nobody/elsewhere/cli/cmd_booth.py"))
        self.assertTranscriptProved(self.run_t(events))

    def test_a_reader_whose_brief_has_no_read_line_is_counted_from_its_summary_path_line(self):
        events = self.events()
        tid = find_reader(events, "cli/cmd_booth.py")[0]
        for e in events:
            if e.get("task_id") == tid and e.get("subtype") == "task_started":
                e["prompt"] = "Project: tollway, a toy. HTTP routes under `/v3/`."
        self.assertTranscriptProved(self.run_t(events))

    def test_each_problem_is_a_line_of_its_own(self):
        events = self.events()
        for tid in find_reader(events, "api/app.py"):
            events = without_task(events, tid)
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        events.extend(t.reader("poetry.lock", "tX"))
        events.extend(t.reader("cli/cmd_booth.py", "tX"))
        out = self.assertTranscriptFails(self.run_t(events), r"never had a reader dispatched: api/app\.py", r"dispatched more than once: cli/cmd_booth\.py",
                                         r"outside the readable files: poetry\.lock")
        self.assertEqual(len(self.failure_lines(out)), 3, out)

    def test_a_reader_started_inside_a_part_that_the_reports_do_not_name_still_counts(self):
        # readers are judged by the files, not by which lead started them: the same reader under another parent is the same reader
        events = self.events()
        for e in events:
            if e.get("subagent_type") == READER:
                e["parent_task_id"] = "someone-else"
        self.assertTranscriptProved(self.run_t(events))


class TranscriptSecondReaderTest(TranscriptBase):
    """AC-4: a part's own re-dispatched count covers one second reader per readable file it holds."""

    def part_of(self, rel):
        areas = base_areas()
        cuts = [0] + list(BASE_CUTS) + [len(areas)]
        for k in range(len(cuts) - 1):
            if any(rel in a.files for a in areas[cuts[k]:cuts[k + 1]]):
                return "part-%d.md" % (k + 1)
        raise AssertionError(rel)

    def twice(self, parts, *rels, times=1):
        events = Transcript(parts).events   # the returned reports are the saved ones, so the counts line is the same in both
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        for rel in rels:
            for _ in range(times):
                events.extend(t.reader(rel, "tX"))
        return events

    def counted(self, name, n):
        return edit(self.parts, name, "re-dispatched: 0;", "re-dispatched: %d;" % n)

    def run_twice(self, parts, *rels, times=1):
        return self.run_t(self.twice(parts, *rels, times=times), parts=parts)

    def test_one_file_read_twice_in_a_part_that_says_one_is_proved_with_a_note(self):
        # AC-4
        rel = "api/billing/toll.py"
        name = self.part_of(rel)
        out = self.assertTranscriptProved(self.run_twice(self.counted(name, 1), rel))
        self.assertIn("NOTE: transcript: %s: 1 readable files had a second reader, within its re-dispatched count of 1: %s" % (name, rel), out.splitlines())

    def test_the_same_run_with_a_count_of_zero_fails_as_before(self):
        # AC-4
        self.assertTranscriptFails(self.run_twice(self.parts, "api/billing/toll.py"),
                                   r"^transcript: 1 readable files had a reader dispatched more than once: api/billing/toll\.py \(2 times\)$")

    def test_two_twice_read_files_in_a_part_that_says_one_both_fail(self):
        # AC-4
        rels = ("api/billing/toll.py", "api/billing/tow.py")
        name = self.part_of(rels[0])
        self.assertEqual(self.part_of(rels[1]), name)
        out = self.assertTranscriptFails(self.run_twice(self.counted(name, 1), *rels), r"^transcript: 2 readable files had a reader dispatched more than once: ")
        self.assertNotIn("NOTE: transcript: %s" % name, out)

    def test_a_file_read_twice_in_part_2_with_only_part_1s_count_at_one_fails(self):
        # AC-4
        rel = next(f for f in readable_paths() if self.part_of(f) == "part-2.md")
        self.assertTranscriptFails(self.run_twice(self.counted("part-1.md", 1), rel),
                                   r"^transcript: 1 readable files had a reader dispatched more than once: ")

    def test_a_file_read_three_times_fails_with_a_count_of_five(self):
        # AC-4
        rel = "api/billing/toll.py"
        self.assertTranscriptFails(self.run_twice(self.counted(self.part_of(rel), 5), rel, times=2), r"toll\.py \(3 times\)")

    def test_a_part_with_no_counts_line_gives_no_allowance_and_no_exception(self):
        # AC-4
        rel = "api/billing/toll.py"
        name = self.part_of(rel)
        parts = edit(self.parts, name, "Files listed: ", "Files listing: ")
        code, out = self.run_twice(parts, rel)
        self.assertEqual(code, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertRegex(out, r"transcript: 1 readable files had a reader dispatched more than once")

    def test_a_restarted_lead_is_allowed_first_and_does_not_use_up_the_count(self):
        # AC-4
        a, b = "api/billing/toll.py", "api/billing/tow.py"
        parts = self.counted(self.part_of(b), 1)
        self.base = Transcript(parts).events   # this test's own base, built from the edited parts
        events = TranscriptReadersTest.restarted(self, files=(a,))
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 92000, str(Fixture.repo)
        events.extend(t.reader(b, "tX"))
        self.assertTranscriptProved(self.run_t(events, parts=parts))


class TranscriptAreaLeadAgentTest(TranscriptBase):
    """Leads that ran as the-foundry:area-lead are scored by the same rules as leads that ran as the-foundry:investigate."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.moved = Transcript(cls.parts, lead_kind=AREA_LEAD_AGENT).events

    def moved_events(self):
        return copy.deepcopy(self.moved)

    def test_the_same_three_part_run_scores_the_same_with_either_lead_kind(self):
        old_code, old_out = self.run_t(self.events())
        new_code, new_out = self.run_t(self.moved_events())
        self.assertEqual((old_code, new_code), (0, 0), old_out + new_out)
        self.assertEqual(OLD_SHAPE_NOTE.sub("", old_out), new_out)
        self.assertEqual(new_out, "LOOP PROVED\nparts: 3; areas: 17; files covered: 950 of 950; read: 945 of 945; facts found: 33 of 33; decoys found: 0 of %d%s\n"
                         % (len(Fixture.key["decoys"]), SUMMARY_READERS))

    def test_the_note_appears_only_for_leads_that_ran_as_investigate(self):
        self.assertIn("NOTE: transcript: 17 area leads ran as the-foundry:investigate", self.run_t(self.events())[1].splitlines())
        self.assertNotIn("area leads ran as", self.run_t(self.moved_events())[1])
        events = self.moved_events()
        lead = next(e for e in events if e.get("subagent_type") == AREA_LEAD_AGENT)
        lead["subagent_type"] = INVESTIGATE
        self.assertIn("NOTE: transcript: 1 area leads ran as the-foundry:investigate", self.run_t(events)[1].splitlines())

    def test_the_note_never_fails_a_run(self):
        code, out = self.run_t(self.events())
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"))

    def test_two_area_leads_running_at_once_print_the_at_once_note(self):
        code, out = self.run_t(overlap_first_two_leads(self.moved_events()))
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        self.assertEqual(lines[0], "LOOP PROVED")
        self.assertEqual(lines[-1], "NOTE: transcript: area leads root and api-top were running at the same time")
        self.assertEqual(len([l for l in lines if l.startswith("NOTE:")]), 1)

    def test_area_lead_tasks_are_never_top_level_dispatches(self):
        events = self.moved_events()
        for e in events:
            if e.get("subagent_type") == AREA_LEAD_AGENT:
                e["spawn_depth"] = 1
        self.assertTranscriptProved(self.run_t(events))
        parts = {k: v for k, v in self.parts.items() if k != "part-3.md"}
        real = self.run_t(self.moved_events(), parts=parts)
        self.assertRegex(real[1], r"transcript: 3 top-level investigate results, 2 part files")

    def test_the_continue_sweep_comparison_is_unchanged_with_area_leads(self):
        events = self.moved_events()
        top = [e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and e["spawn_depth"] == 1][1]
        top["prompt"] = top["prompt"].replace("Focus: none\n", "", 1)
        self.assertTranscriptFails(self.run_t(events), r"^transcript: top-level investigate dispatch 2 is not CONTINUE SWEEP and part-1\.md's block: line 3 differs")


class TranscriptContinueBriefTest(TranscriptBase):
    def tops(self, events):
        return [e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and e["spawn_depth"] == 1]

    def edit_prompt(self, fn, which=1):
        events = self.events()
        top = self.tops(events)[which]
        top["prompt"] = fn(top["prompt"])
        self.assertNotEqual(top["prompt"], self.tops(self.base)[which]["prompt"])
        return events

    def test_a_prompt_that_differs_from_the_previous_blocks_by_one_character_fails_naming_line_and_column(self):
        events = self.edit_prompt(lambda p: p.replace("Environment: use the git wrapper ./bin/git", "Environment: use the git wrapper ./bin/gat"))
        self.assertTranscriptFails(self.run_t(events), r"^transcript: top-level investigate dispatch 2 is not CONTINUE SWEEP and part-1\.md's block: line 4 differs at column 41: sent '.*/bin/gat', saved '.*/bin/git'")

    def test_one_character_off_in_the_third_dispatch_names_dispatch_3_and_part_2(self):
        events = self.edit_prompt(lambda p: p.replace("Project: A toll-road", "Project: A toll-roads"), which=2)
        self.assertTranscriptFails(self.run_t(events), r"^transcript: top-level investigate dispatch 3 is not CONTINUE SWEEP and part-2\.md's block: line 2 differs")

    def test_a_dropped_line_fails(self):
        events = self.edit_prompt(lambda p: p.replace("Focus: none\n", "", 1))
        self.assertTranscriptFails(self.run_t(events), r"^transcript: top-level investigate dispatch 2 is not CONTINUE SWEEP and part-1\.md's block: line 3 differs")

    def test_a_dropped_last_area_line_fails(self):
        events = self.edit_prompt(lambda p: p.replace(base_areas()[10].line() + "\n", "", 1))
        self.assertTranscriptFails(self.run_t(events), r"^transcript: top-level investigate dispatch 2 is not CONTINUE SWEEP and part-1\.md's block: ")

    def test_an_added_line_fails(self):
        events = self.edit_prompt(lambda p: p + "\nPlease also check the tests.")
        self.assertTranscriptFails(self.run_t(events), r"^transcript: top-level investigate dispatch 2 is not CONTINUE SWEEP and part-1\.md's block: line \d+ differs")

    def test_a_prompt_without_the_continue_line_fails(self):
        events = self.edit_prompt(lambda p: p.split("\n", 1)[1])
        self.assertTranscriptFails(self.run_t(events), r"dispatch 2 is not CONTINUE SWEEP")

    def test_a_prompt_that_is_the_first_brief_again_fails(self):
        events = self.edit_prompt(lambda p: "This is a new codebase to me, and I need to understand the whole thing.")
        self.assertTranscriptFails(self.run_t(events), r"dispatch 2 is not CONTINUE SWEEP")

    def test_the_previous_parts_block_is_the_right_one_not_the_first_parts(self):
        events = self.events()
        tops = self.tops(events)
        tops[2]["prompt"] = tops[1]["prompt"]   # the third dispatch sends part 1's block again
        self.assertTranscriptFails(self.run_t(events), r"^transcript: top-level investigate dispatch 3 is not CONTINUE SWEEP and part-2\.md's block")

    def test_trailing_whitespace_only_differences_pass(self):
        events = self.edit_prompt(lambda p: "\n".join(l + "  \t" for l in p.split("\n")) + "\n\n")
        self.assertTranscriptProved(self.run_t(events))

    def test_windows_line_endings_in_the_prompt_pass(self):
        events = self.edit_prompt(lambda p: p.replace("\n", "\r\n"))
        self.assertTranscriptProved(self.run_t(events))

    def test_the_first_dispatch_may_say_anything(self):
        events = self.events()
        self.tops(events)[0]["prompt"] = "Anything at all, with `CONTINUE SWEEP` not on its first line."
        self.assertTranscriptProved(self.run_t(events))

    def test_a_dispatch_that_is_not_the_top_level_one_is_not_held_to_the_rule(self):
        events = self.events()
        for e in events:
            if e.get("subagent_type") == INVESTIGATE and e.get("spawn_depth") == 2:
                e["prompt"] = "AREA LEAD\nArea: whatever"
        self.assertTranscriptProved(self.run_t(events))

    def test_a_lead_is_known_by_its_prompt_even_when_it_carries_no_depth(self):
        events = self.events()
        for e in events:
            if e.get("subagent_type") == INVESTIGATE and e.get("spawn_depth") == 2:
                del e["spawn_depth"]
        self.assertTranscriptProved(self.run_t(events))

    def test_a_missing_part_file_for_a_dispatch_is_a_failure_not_a_crash(self):
        parts = {k: v for k, v in self.parts.items() if k != "part-3.md"}
        out = self.assertTranscriptFails(self.run_t(parts=parts, extra=["--min-parts", "2"]), r"^transcript: 3 top-level investigate results, 2 part files$")
        self.assertNotIn("Traceback", out)


class TranscriptSavedPartTest(TranscriptBase):
    def test_a_saved_part_that_differs_from_the_returned_report_by_one_character_fails(self):
        parts = edit(self.parts, "part-2.md", "# Investigation report (part 2)", "# Investigation report (part 2).")
        out = self.assertTranscriptFails(self.run_t(parts=parts), r"^transcript: part-2\.md differs from the report the investigate returned, at non-blank line \d+, column \d+: returned '.*', saved '.*\.'$")
        self.assertEqual(len(self.failure_lines(out)), 1, out)

    def test_a_comma_added_in_a_finding_is_caught_like_in_a_real_run(self):
        parts = edit(self.parts, "part-1.md", "found while reading.", "found, while reading.")
        self.assertTranscriptFails(self.run_t(parts=parts), r"^transcript: part-1\.md differs from the report the investigate returned")

    def test_a_dropped_line_in_a_saved_part_fails(self):
        parts = edit(self.parts, "part-3.md", "## Findings\n", "")
        self.assertTranscriptFails(self.run_t(parts=parts), r"^transcript: part-3\.md differs from the report the investigate returned")

    def test_a_saved_part_that_is_one_line_longer_fails(self):
        parts = edit(self.parts, "part-1.md", "\n\nINVESTIGATE REPORT ENDS", "\nAn extra closing remark.\n\nINVESTIGATE REPORT ENDS")
        self.assertTranscriptFails(self.run_t(parts=parts), r"^transcript: part-1\.md differs from the report the investigate returned")

    def test_blank_lines_and_trailing_whitespace_only_pass(self):
        parts = edit_all(self.parts, lambda t: t.replace("\n## ", "\n\n\n## ").replace("\n", "  \n") + "\n\n\n")
        self.assertTranscriptProved(self.run_t(parts=parts))

    def test_windows_line_endings_in_the_saved_parts_pass(self):
        self.assertTranscriptProved(self.run_t(parts=edit_all(self.parts, lambda t: t.replace("\n", "\r\n"))))

    def test_more_investigate_results_than_part_files_fails(self):
        parts = {k: v for k, v in self.parts.items() if k != "part-3.md"}
        self.assertTranscriptFails(self.run_t(parts=parts, extra=["--min-parts", "2"]), r"^transcript: 3 top-level investigate results, 2 part files$")

    def test_fewer_investigate_results_than_part_files_fails(self):
        events = self.events()
        last = [e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and e["spawn_depth"] == 1][-1]["tool_use_id"]
        events = [e for e in events if not (e.get("type") == "user" and any(b.get("tool_use_id") == last for b in (e.get("message") or {}).get("content", []) if isinstance(b, dict)))]
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 2 top-level investigate results, 3 part files$")

    def test_a_third_dispatch_that_never_happened_is_reported(self):
        events = self.events()
        tops = [e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and e["spawn_depth"] == 1]
        last = tops[-1]
        events = [e for e in events if e.get("tool_use_id") != last["tool_use_id"] and e.get("task_id") != last["task_id"]
                  and not any(b.get("tool_use_id") == last["tool_use_id"] for b in (e.get("message") or {}).get("content", []) if isinstance(b, dict))]
        self.assertTranscriptFails(self.run_t(events), r"^transcript: the parts folder holds 3 part files but only 1 top-level investigate dispatches follow the first$",
                                   r"^transcript: 2 top-level investigate results, 3 part files$")

    def test_a_result_whose_content_is_a_plain_string_is_read(self):
        events = self.events()
        for e in events:
            if e.get("type") == "user" and e.get("parent_tool_use_id") is None:
                for b in e["message"]["content"]:
                    if b.get("tool_use_id", "").startswith("toolu_t") and isinstance(b["content"], list):
                        b["content"] = b["content"][0]["text"]
        self.assertTranscriptProved(self.run_t(events))


class TranscriptLeadsAtOnceTest(TranscriptBase):
    def overlapped(self):
        return overlap_first_two_leads(self.events())

    def test_two_leads_running_at_once_print_a_note_and_change_nothing_else(self):
        code, out = self.run_t(self.overlapped())
        self.assertEqual(code, 0, out)
        out = OLD_SHAPE_NOTE.sub("", out)
        lines = out.splitlines()
        self.assertEqual(lines[0], "LOOP PROVED")
        self.assertEqual(lines[-1], "NOTE: transcript: area leads root and api-top were running at the same time")
        self.assertTrue(lines[1].endswith(SUMMARY_READERS), out)
        self.assertEqual(len([l for l in lines if l.startswith("NOTE:")]), 1)

    def test_the_note_never_turns_a_proved_run_into_a_failure_and_a_failed_run_keeps_it_failed(self):
        parts = edit(self.parts, "part-3.md", "failed: 0;", "failed: 2;")
        code, out = self.run_t(self.overlapped(), parts=parts)
        self.assertEqual(code, 1, out)
        self.assertEqual(out.splitlines()[0], "LOOP FAILED")
        self.assertIn("NOTE: transcript: area leads root and api-top were running at the same time", OLD_SHAPE_NOTE.sub("", out).splitlines()[-1])

    def test_leads_one_after_the_other_print_no_note(self):
        code, out = self.run_t()
        self.assertNotIn("NOTE:", OLD_SHAPE_NOTE.sub("", out))

    def test_a_lead_that_never_finished_is_running_when_the_next_one_starts(self):
        events = self.events()
        leads = [e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and e.get("spawn_depth") == 2]
        events = [e for e in events if not (e.get("subtype") == "task_notification" and e["task_id"] == leads[2]["task_id"])]
        code, out = self.run_t(events)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"NOTE: transcript: area leads api-accounts and api-billing were running at the same time")

    def test_three_leads_at_once_name_each_pair(self):
        events = self.events()
        leads = [e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and e.get("spawn_depth") == 2][:3]
        notes = [e for e in events if e.get("subtype") == "task_notification" and e["task_id"] in [l["task_id"] for l in leads]]
        for n in notes:
            events.remove(n)
        at = events.index(leads[2]) + 1
        events[at:at] = notes
        code, out = self.run_t(events)
        self.assertEqual(code, 0, out)
        self.assertEqual(len([l for l in OLD_SHAPE_NOTE.sub("", out).splitlines() if l.startswith("NOTE:")]), 3, out)


class TranscriptCantCheckTest(TranscriptBase):
    def assertCantCheckExit(self, code_out, pattern):
        self.assertCantCheck(code_out, pattern)

    def test_an_empty_transcript_cant_be_checked(self):
        self.assertCantCheckExit(self.run_t(raw=b""), r"holds no the-foundry:file-reader task")

    def test_a_missing_transcript_cant_be_checked(self):
        code, out = run_script(self.parts, extra=["--transcript", "/nonexistent/run.jsonl"])
        self.assertCantCheck((code, out), r"cannot read the transcript")

    def test_a_folder_given_as_the_transcript_cant_be_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertCantCheck(run_script(self.parts, extra=["--transcript", tmp]), r"cannot read the transcript")

    def test_a_transcript_that_is_not_json_cant_be_checked(self):
        self.assertCantCheckExit(self.run_t(raw=b"this is not json\nnor is this\n{broken"), r"holds no the-foundry:file-reader task")

    def test_a_transcript_of_binary_bytes_cant_be_checked(self):
        self.assertCantCheckExit(self.run_t(raw=bytes(range(256)) * 20), r"holds no the-foundry:file-reader task")

    def test_a_transcript_with_no_reader_task_cant_be_checked(self):
        events = [e for e in self.events() if e.get("subagent_type") != READER]
        self.assertCantCheckExit(self.run_t(events), r"holds no the-foundry:file-reader task")

    def test_a_transcript_with_only_a_reader_notification_and_no_task_cant_be_checked(self):
        events = [e for e in self.events() if e.get("subtype") != "task_started"]
        self.assertCantCheckExit(self.run_t(events), r"holds no the-foundry:file-reader task")

    def test_none_of_these_is_ever_exit_1(self):
        for raw in (b"", b"x", b"[]", b"{}\n{}\n", b"\xff\xfe"):
            with self.subTest(raw=raw):
                code, out = self.run_t(raw=raw)
                self.assertEqual(code, 2, out)
                self.assertNotIn("LOOP", out)

    def test_a_key_with_no_file_skips_cant_be_checked_with_a_transcript_but_scores_without_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = json.loads(KEY_PATH.read_text(encoding="utf-8"))
            del key["layout"]["file_skips"]
            path = Path(tmp) / "key.json"
            path.write_text(json.dumps(key), encoding="utf-8")
            self.assertCantCheck(self.run_t(key=path), r"no layout\.file_skips")
            self.assertProved(self.parts, key=path)

    def test_a_key_whose_skip_counts_do_not_match_the_fixture_cant_be_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = json.loads(KEY_PATH.read_text(encoding="utf-8"))
            key["layout"]["file_skips"] = {"lock": 2, "binary": 4}
            path = Path(tmp) / "key.json"
            path.write_text(json.dumps(key), encoding="utf-8")
            self.assertCantCheck(self.run_t(key=path), r"the key says 2 files skipped as lock, the fixture has 1 paths ending \.lock")

    def test_a_key_with_an_unknown_skip_reason_cant_be_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = json.loads(KEY_PATH.read_text(encoding="utf-8"))
            key["layout"]["file_skips"] = {"lock": 1, "binary": 4, "generated": 3}
            path = Path(tmp) / "key.json"
            path.write_text(json.dumps(key), encoding="utf-8")
            self.assertCantCheck(self.run_t(key=path), r"names a reason, 'generated'")

    def test_events_of_odd_shapes_never_give_exit_1_by_crashing(self):
        events = self.events()
        events.append({"type": "system", "subtype": "task_started", "task_id": 5, "subagent_type": READER, "prompt": 12})
        events.append({"type": "system", "subtype": "task_notification", "task_id": None, "summary": ["not a string"], "status": 7})
        events.append({"type": "user", "parent_tool_use_id": None, "message": {"content": "just text"}})
        events.append({"type": "user", "parent_tool_use_id": None, "message": {"content": [None, 3, {"type": "tool_result", "tool_use_id": "x", "content": None}]}})
        code, out = self.run_t(events)
        self.assertIn(code, (1, 2), out)
        if code == 2:
            self.assertTrue(out.startswith("CAN'T CHECK: "), out)
        else:
            self.assertEqual(out.splitlines()[0], "LOOP FAILED")
        self.assertNotIn("Traceback", out)


class TranscriptMutationTest(MutantBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parts = build_parts(base_areas())
        cls.base = Transcript(cls.parts).events

    def events(self):
        return copy.deepcopy(self.base)

    def run_at(self, script, events, parts=None):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / "run.jsonl"
            t.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            code, out, err = run_script_at(script, parts if parts is not None else self.parts, ["--transcript", str(t)])
            return code, out + err

    def caught(self, old, new, events, line_pattern, parts=None):
        """The script prints a line matching line_pattern on these inputs, and the mutant (old replaced by new) doesn't."""
        real = self.run_at(SCRIPT, events, parts)
        mutated = self.run_at(self.mutant(old, new), events, parts)
        self.assertEqual(real[0], 1, real[1])
        self.assertTrue(any(re.search(line_pattern, l) for l in real[1].splitlines()), real[1])
        self.assertFalse(any(re.search(line_pattern, l) for l in mutated[1].splitlines()), mutated[1])
        return real, mutated

    def test_the_unmutated_copy_proves_the_base_run(self):
        code, out = self.run_at(SCRIPT, self.events())
        self.assertEqual(code, 0, out)
        self.assertIn(SUMMARY_READERS, out)

    def test_dropping_the_never_dispatched_check_is_caught(self):
        events = self.events()
        for tid in find_reader(events, "api/app.py"):
            events = without_task(events, tid)
        real, mutated = self.caught("    if never:\n", "    if False:\n", events, r"never had a reader dispatched")
        self.assertEqual(mutated[0], 0, mutated[1])

    def test_dropping_the_never_completed_check_is_caught(self):
        events = self.events()
        tid = find_reader(events, "cli/cmd_booth.py")[0]
        events = [e for e in events if not (e.get("task_id") == tid and e.get("subtype") == "task_notification")]
        real, mutated = self.caught("    if incomplete:\n", "    if False:\n", events, r"never completed")
        self.assertEqual(mutated[0], 0, mutated[1])

    def test_dropping_the_dispatched_twice_check_is_caught(self):
        events = self.events()
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        events.extend(t.reader("api/billing/toll.py", "tX"))
        real, mutated = self.caught("    if twice:\n", "    if False:\n", events, r"more than once")
        self.assertEqual(mutated[0], 0, mutated[1])

    def test_dropping_the_outside_paths_check_is_caught(self):
        events = self.events()
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        events.extend(t.reader("poetry.lock", "tX"))
        real, mutated = self.caught("    if outside:\n", "    if False:\n", events, r"outside the readable files")
        self.assertEqual(mutated[0], 0, mutated[1])

    def test_counting_a_failed_reader_as_completed_is_caught(self):
        events = self.events()
        tid = find_reader(events, "cli/cmd_booth.py")[0]
        for e in events:
            if e.get("task_id") == tid and e.get("subtype") == "task_notification":
                e["status"] = "failed"
        real, mutated = self.caught('.get("status") == "completed"', '.get("status") in ("completed", "failed")', events, r"never completed")
        self.assertEqual(mutated[0], 0, mutated[1])

    def test_dropping_the_continue_prompt_comparison_is_caught(self):
        events = self.events()
        top = [e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and e["spawn_depth"] == 1][1]
        top["prompt"] = top["prompt"].replace("Focus: none", "Focus: nope")
        real, mutated = self.caught("        if sent != want:\n", "        if False:\n", events, r"is not CONTINUE SWEEP")
        self.assertEqual(mutated[0], 0, mutated[1])

    def test_comparing_the_trailing_whitespace_too_is_caught(self):
        events = self.events()
        top = [e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == INVESTIGATE and e["spawn_depth"] == 1][1]
        top["prompt"] = "\n".join(l + "  " for l in top["prompt"].split("\n"))
        real = self.run_at(SCRIPT, events)
        self.assertEqual(real[0], 0, real[1])
        mutated = self.run_at(self.mutant("sent = [line.rstrip() for line in prompt", "sent = [line for line in prompt"), events)
        self.assertEqual(mutated[0], 1, mutated[1])

    def test_dropping_the_saved_part_comparison_is_caught(self):
        parts = edit(self.parts, "part-2.md", "# Investigation report (part 2)", "# Investigation report (part 2).")
        real, mutated = self.caught("        if got != saved_lines:\n", "        if False:\n", self.events(), r"differs from the report the investigate returned", parts)
        self.assertEqual(mutated[0], 0, mutated[1])

    def test_ignoring_the_count_of_results_is_caught(self):
        parts = {k: v for k, v in self.parts.items() if k != "part-3.md"}
        real = self.run_at(SCRIPT, self.events(), parts)
        self.assertRegex(real[1], r"transcript: 3 top-level investigate results, 2 part files")
        m = self.mutant("    if len(returned) != len(infos):\n", "    if False:\n")
        self.assertNotRegex(self.run_at(m, self.events(), parts)[1], r"transcript: 3 top-level investigate results")

    def test_dropping_the_note_for_leads_at_once_is_caught(self):
        events = overlap_first_two_leads(self.events())
        real = self.run_at(SCRIPT, events)
        self.assertIn("NOTE: transcript: area leads root and api-top were running at the same time", real[1])
        m = self.mutant("            if other_end is None or other_end > number:\n", "            if False:\n")
        self.assertNotIn("were running at the same time", self.run_at(m, events)[1])

    def test_making_the_note_a_failure_is_caught(self):
        events = overlap_first_two_leads(self.events())
        m = self.mutant("                notes.extend([", "                fails.extend([")
        self.assertEqual(self.run_at(SCRIPT, events)[0], 0)
        self.assertEqual(self.run_at(m, events)[0], 1)

    READERS_EXPR = ('+ ("; readers: %d of %d, once each" % readers if readers else\n'
                    '             "; readers: not checked; read, unread and failed are the parts\' own numbers (--transcript checks them)")')

    def test_a_summary_without_the_readers_is_caught(self):
        m = self.mutant(self.READERS_EXPR, '+ ""')
        self.assertIn(SUMMARY_READERS, self.run_at(SCRIPT, self.events())[1])
        self.assertNotIn("readers", self.run_at(m, self.events())[1])

    def test_a_summary_without_the_no_transcript_note_is_caught(self):
        m = self.mutant(self.READERS_EXPR, '+ ("; readers: %d of %d, once each" % readers if readers else "")')
        self.assertIn(NO_TRANSCRIPT_NOTE, run_script(self.parts)[1])
        code, out, err = run_script_at(m, self.parts)
        self.assertEqual(code, 0)
        self.assertNotIn("not checked", out)

    def test_a_crash_on_an_odd_transcript_is_exit_2_and_without_the_handler_it_would_be_exit_1(self):
        events = self.events()
        events.append({"type": "system", "subtype": "task_started", "task_id": ["odd"], "subagent_type": READER, "prompt": "Read `x.py`"})
        real = self.run_at(SCRIPT, events)
        self.assertEqual(real[0], 2, real[1])
        self.assertIn("CAN'T CHECK: internal error", real[1])
        m = self.mutant("    except Exception as err:\n", "    except ZeroDivisionError as err:\n")
        self.assertEqual(self.run_at(m, events)[0], 1)




# ---------------------------------------------------------------- names the old listing quoted: the scorer reads `git ls-files -z`

def load_scorer_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_parts_hostile_under_test", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# a backslash followed by t, a double quote, a single quote, a non-ASCII letter, a trailing backslash
HOSTILE_NAMES = ["a\\tb/y.py", 'q"uote/z.py', "bob's notes/x.md", "café/m.txt", "tail\\/t.py", "plain/p.py", "vendor/v.js"]


class HostileNamesTest(unittest.TestCase):
    """A tiny repo, not the fixture: folders with odd names, behind a `bin/git` that passes everything to the real git
    and logs what it was asked."""

    @classmethod
    def setUpClass(cls):
        real = shutil.which("git")
        if not real:
            raise unittest.SkipTest("no git")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        cls.repo = cls.base / "repo"
        (cls.repo / "bin").mkdir(parents=True)
        wrapper = cls.repo / "bin" / "git"
        wrapper.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$(dirname \"$0\")/calls.log\"\nexec \"" + real + "\" \"$@\"\n", encoding="utf-8")
        wrapper.chmod(0o755)
        cls.env = {"PATH": os.environ["PATH"], "HOME": str(cls.base), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
                   "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        cls.git("init", "-q", "-b", "main")
        cls.created = []
        for name in HOSTILE_NAMES:
            path = cls.repo / name
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x = 1\n", encoding="utf-8")
            except OSError:
                continue
            cls.created.append(name)
        (cls.repo / "scratch.md").write_text("untracked\n", encoding="utf-8")
        cls.git("add", *cls.created)
        cls.git("commit", "-q", "-m", "all")
        cls.scorer = load_scorer_module()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def git(cls, *args):
        done = subprocess.run(["git", *args], cwd=str(cls.repo), env=cls.env, capture_output=True)
        assert done.returncode == 0, done.stderr
        return done.stdout

    def test_the_names_the_old_listing_quoted_were_created(self):
        for must in ("a\\tb/y.py", 'q"uote/z.py', "bob's notes/x.md", "café/m.txt"):
            self.assertIn(must, self.created)

    def test_tracked_files_returns_the_raw_bytes_of_every_path_exactly_as_it_is(self):
        got = self.scorer.tracked_files(str(self.repo))
        self.assertEqual(sorted(got), sorted(n.encode("utf-8") for n in self.created))
        self.assertIn(b"a\\tb/y.py", got)       # a backslash and a t, not a tab and not a quoted form
        self.assertIn(b'q"uote/z.py', got)
        self.assertIn("café/m.txt".encode("utf-8"), got)
        for path in got:
            self.assertNotEqual(path[:1], b'"')  # git's own quoting wraps a path in double quotes

    def test_the_listing_is_asked_for_with_z_and_without_quotepath(self):
        log = self.repo / "bin" / "calls.log"
        if log.exists():
            log.unlink()
        self.scorer.tracked_files(str(self.repo))
        self.assertEqual(log.read_text(encoding="utf-8").splitlines(), ["ls-files -z"])
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('[git, "ls-files", "-z"]', source)
        self.assertNotIn("quotepath", source)
        self.assertIn('split(b"\\0")', source)

    def test_an_area_for_each_hostile_folder_rebuilds_to_its_one_file(self):
        tracked = self.scorer.tracked_files(str(self.repo))
        cases = (
            ("`a\\tb/`", {b"a\\tb/y.py"}),
            ('`q"uote/`', {b'q"uote/z.py'}),
            ("`bob's notes/`", {b"bob's notes/x.md"}),
            ("`café/`", {"café/m.txt".encode("utf-8")}),
            ("`tail\\/`", {b"tail\\/t.py"}),
            ('`a\\tb/` + `q"uote/`', {b"a\\tb/y.py", b'q"uote/z.py'}),
            ("`plain/` except `plain/sub/`", {b"plain/p.py"}),
        )
        for definition, want in cases:
            with self.subTest(definition=definition):
                pieces = self.scorer.parse_definition(definition)
                self.assertIsInstance(pieces, list, pieces)
                self.assertEqual(self.scorer.rebuild(pieces, tracked), want)

    def test_the_fixture_listing_is_still_990_files_and_equals_the_newline_listing(self):
        got = [p.decode("utf-8") for p in self.scorer.tracked_files(str(Fixture.repo))]
        self.assertEqual(len(got), 990)
        self.assertEqual(got, Fixture.tracked)

    def parts_for(self):
        """A three-part report for areas a, b and c, written by hand in the shapes the agent file's templates give."""
        def part(block, read_line, count, rest_n, rest_m, whole):
            lines = list(block) + ["", "### 1. Project Identity", "A toy repo.", "", "### 8. Coverage", "Mode: full sweep, 1 area leads",
                                   "Files listed: %d; read: %d; skipped: 0; re-dispatched: 0; failed: 0; unread: 0" % (count, count),
                                   "Skip reasons: none in this part.", "Areas read:", read_line,
                                   "Areas not read: %d areas, %d files; see SWEEP IN PARTS at the top." % (rest_n, rest_m)] + whole + ["", "INVESTIGATE REPORT ENDS"]
            return "\n".join(lines) + "\n"
        head = ["To read the rest, dispatch `investigate` again. The brief is `CONTINUE SWEEP` on its first line, then every line from `Project:` to "
                "`END OF BLOCK`, copied as it stands.",
                "Project: a toy repo", "Focus: none", "Environment: none", "Instructions: none", "Areas not read:"]
        a = "- a: `a\\tb/` + `q\"uote/` (2 files)"
        b = "- b: `bob's notes/` + `plain/` (2 files)"
        c = "- c: `café/` + `tail\\/` (2 files)"
        whole1 = ["Whole repo: 7 tracked files; 1 in folders skipped whole (vendor/: 1, vendored); 1 untracked", "- scratch.md"]
        later = ["Whole repo: given in part 1."]
        return {
            "part-1.md": part(["SWEEP IN PARTS: 2 areas not read"] + head + [b, c, "END OF BLOCK"], a, 2, 2, 4, whole1),
            "part-2.md": part(["SWEEP IN PARTS: 1 areas not read"] + head + [c, "END OF BLOCK"], b, 2, 1, 2, later),
            "part-3.md": part(["SWEEP IN PARTS: 0 areas not read"], c, 2, 0, 0, later),
        }

    def key_file(self):
        key = {"facts": [{"id": "f1", "kind": "route", "path": "a\\tb/y.py", "line": 1, "token": "TOKENONE"}],
               "decoys": [{"id": "d1", "why": "vendored", "path": "vendor/v.js", "token": "DECOYONE"}],
               "layout": {"tracked": 7, "skipped_whole": {"vendor/": 1}, "untracked": ["scratch.md"]}}
        path = self.base / "key.json"
        path.write_text(json.dumps(key), encoding="utf-8")
        return path

    def score(self, script=SCRIPT, parts=None):
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp)
            for name, text in (parts or self.parts_for()).items():
                if name == "part-1.md":
                    text = text.replace("A toy repo.", "A toy repo. Route TOKENONE is here.", 1)
                (pdir / name).write_text(text, encoding="utf-8")
            done = subprocess.run([sys.executable, "-I", str(script), "--key", str(self.key_file()), "--repo", str(self.repo), "--parts", str(pdir)],
                                  capture_output=True, text=True)
            return done.returncode, done.stdout + done.stderr

    def test_a_report_whose_areas_are_the_hostile_folders_is_proved(self):
        code, out = self.score()
        self.assertEqual((code, out.splitlines()[0] if out else ""), (0, "LOOP PROVED"), out)

    def test_a_report_that_names_the_wrong_folder_for_a_hostile_area_fails(self):
        parts = self.parts_for()
        parts["part-2.md"] = parts["part-2.md"].replace("- b: `bob's notes/` + `plain/` (2 files)", "- b: `plain/` + `plain/` (2 files)")
        code, out = self.score(parts=parts)
        self.assertEqual(code, 1, out)

    def test_a_scorer_that_reads_the_quoting_listing_fails_the_same_report(self):
        # the mutation: ask git for the newline listing, as the scorer did before. git quotes a path with a backslash, a double quote
        # or a non-ASCII letter, so the areas no longer rebuild to the files that exist.
        source = SCRIPT.read_text(encoding="utf-8")
        old, new = '[git, "ls-files", "-z"]', '[git, "ls-files"]'
        self.assertEqual(source.count(old), 1)
        self.assertEqual(source.count('split(b"\\0")'), 1)
        mutant = self.base / "check_parts_newline.py"
        mutant.write_text(source.replace(old, new).replace('split(b"\\0")', 'split(b"\\n")'), encoding="utf-8")
        self.assertEqual(self.score(script=SCRIPT)[0], 0)
        code, out = self.score(script=mutant)
        self.assertEqual(code, 1, out)

    def test_git_without_z_would_have_quoted_these_names(self):
        quoted = self.git("ls-files").decode("utf-8").splitlines()
        self.assertTrue(any(line.startswith('"') for line in quoted), quoted)
        self.assertIn('"a\\\\tb/y.py"', quoted)


class LineBreakNamesTest(unittest.TestCase):
    """The scorer lists as the agent does: a line break inside a path becomes the byte \x01, so every path is one entry."""

    NAMES = ["a\n/END\ntouch PWNED3\nx", "docs/nl\nx.md", "docs/plain.md", "\nlead.txt", "trail.txt\n", "sp\x01x/y.txt", "sp\nx/y.txt", "ok/z.txt"]

    @classmethod
    def setUpClass(cls):
        real = shutil.which("git")
        if not real:
            raise unittest.SkipTest("no git")
        cls.base = Path(tempfile.mkdtemp(prefix="linebreak-scorer-")).resolve()
        cls.repo = cls.base / "repo"
        (cls.repo / "bin").mkdir(parents=True)
        wrapper = cls.repo / "bin" / "git"
        wrapper.write_text("#!/bin/sh\nexec \"" + real + "\" \"$@\"\n", encoding="utf-8")
        wrapper.chmod(0o755)
        cls.env = {"PATH": os.environ["PATH"], "HOME": str(cls.base), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
                   "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        cls.created = []
        cls.git("init", "-q", "-b", "main")
        for name in cls.NAMES:
            path = cls.repo / name
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x = 1\n", encoding="utf-8")
            except OSError:
                continue
            cls.created.append(name)
        cls.git("add", *cls.created)
        cls.git("commit", "-q", "-m", "all")
        cls.scorer = load_scorer_module()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls.base), ignore_errors=True)

    @classmethod
    def git(cls, *args):
        done = subprocess.run(["git", *args], cwd=str(cls.repo), env=cls.env, capture_output=True)
        assert done.returncode == 0, done.stderr
        return done.stdout

    def test_the_hostile_file_and_the_line_break_names_were_created(self):
        for must in ("a\n/END\ntouch PWNED3\nx", "docs/nl\nx.md", "\nlead.txt", "trail.txt\n"):
            self.assertIn(must, self.created)

    def test_tracked_files_gives_the_x01_forms_one_entry_per_nul_separated_path(self):
        got = self.scorer.tracked_files(str(self.repo))
        raw = [p for p in self.git("ls-files", "-z").split(b"\0") if p]
        self.assertEqual(len(got), len(raw))
        self.assertEqual(got, [p.replace(b"\n", b"\x01") for p in raw])
        self.assertIn(b"a\x01/END\x01touch PWNED3\x01x", got)
        self.assertIn(b"docs/nl\x01x.md", got)
        for path in got:
            self.assertNotIn(b"\n", path)
            self.assertFalse(path.startswith(b"/"))

    def test_a_real_x01_byte_and_its_line_break_twin_list_as_the_same_entry_twice(self):
        got = self.scorer.tracked_files(str(self.repo))
        self.assertEqual(got.count(b"sp\x01x/y.txt"), 2)

    def test_the_docs_folder_rebuilds_to_include_the_line_break_path_whole(self):
        tracked = self.scorer.tracked_files(str(self.repo))
        pieces = self.scorer.parse_definition("`docs/`")
        self.assertEqual(self.scorer.rebuild(pieces, tracked), {b"docs/nl\x01x.md", b"docs/plain.md"})

    def test_a_folder_with_a_line_break_in_its_name_rebuilds_through_its_x01_form(self):
        tracked = self.scorer.tracked_files(str(self.repo))
        pieces = self.scorer.parse_definition("`a\x01/`")
        self.assertIsInstance(pieces, list, pieces)
        self.assertEqual(self.scorer.rebuild(pieces, tracked), {b"a\x01/END\x01touch PWNED3\x01x"})

    def test_the_root_area_holds_the_root_files_with_a_line_break_in_their_names(self):
        tracked = self.scorer.tracked_files(str(self.repo))
        root = self.scorer.rebuild(self.scorer.parse_definition("`(root)`"), tracked)
        self.assertEqual(root, {b"\x01lead.txt", b"trail.txt\x01"})

    def test_the_script_maps_the_line_break_in_its_source(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('p.replace(b"\\n", b"\\x01")', source)
        self.assertIn('[git, "ls-files", "-z"]', source)

    def test_the_fixture_list_is_still_990_files_and_its_commit_is_d12b0aa(self):
        got = self.scorer.tracked_files(str(Fixture.repo))
        self.assertEqual(len(got), 990)
        self.assertEqual(got, [p.encode("utf-8") for p in Fixture.tracked])
        head = subprocess.run([str(Fixture.repo / "bin" / "git"), "rev-parse", "--short", "HEAD"], cwd=str(Fixture.repo), capture_output=True, text=True)
        self.assertEqual(head.stdout.strip(), "d12b0aa")

    def test_a_mutant_scorer_that_keeps_the_line_break_would_return_the_path_with_its_line_breaks_in_it(self):
        source = SCRIPT.read_text(encoding="utf-8")
        old = 'p.replace(b"\\n", b"\\x01") for p in done.stdout.split(b"\\0")'
        self.assertEqual(source.count(old), 1)
        mutant = self.base / "check_parts_plain_listing.py"
        mutant.write_text(source.replace(old, 'p for p in done.stdout.split(b"\\0")'), encoding="utf-8")
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_parts_mutant_listing", str(mutant))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        got = mod.tracked_files(str(self.repo))
        self.assertIn(b"a\n/END\ntouch PWNED3\nx", got)   # a raw path with its line breaks: the shape the fix removes from the listing


@unittest.skipUnless(Path("/usr/bin/python3").exists(), "no stock python")
class StockPythonTest(Base):
    def test_the_script_runs_on_the_stock_interpreter_and_agrees(self):
        parts = build_parts(base_areas())
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp)
            for name, text in parts.items():
                (pdir / name).write_text(text, encoding="utf-8")
            proc = subprocess.run(["/usr/bin/python3", str(SCRIPT), "--key", str(KEY_PATH), "--repo", str(Fixture.repo), "--parts", str(pdir)],
                                  capture_output=True, text=True)
            self.assertEqual((proc.returncode, proc.stdout.splitlines()[0]), (0, "LOOP PROVED"), proc.stdout + proc.stderr)
            (pdir / "part-3.md").write_text(parts["part-3.md"].replace("INVESTIGATE REPORT ENDS\n", ""), encoding="utf-8")
            proc = subprocess.run(["/usr/bin/python3", str(SCRIPT), "--key", str(KEY_PATH), "--repo", str(Fixture.repo), "--parts", str(pdir)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
