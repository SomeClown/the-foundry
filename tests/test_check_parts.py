"""Adversarial tests for evals-expensive/check_parts.py, the scorer for a sweep read in parts.

The big-sweep fixture is built once (in a temp folder, by its own scaffold). A correct three-part split is
written here from design section 4's notation and block template, by this file's own code (it never calls
the script's internals), and fed to the script as part-1.md, part-2.md, part-3.md. Then it is broken one way
at a time: each check has to be shown able to fail, and the script's exit codes are pinned:
0 LOOP PROVED, 1 LOOP FAILED with a line naming the problem, 2 CAN'T CHECK (a crash is never 1).

No model session starts here. Standard library only; runs on Python 3.9.
"""

import json
import re
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
        lines += ["- %s found while reading." % t for j, t in enumerate(tokens) if j % len(reads) == i]
        lines += ["", "## Coverage",
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
                             ("Areas not read:", "header")):
            with self.subTest(label=label):
                parts = edit(self.parts, "part-3.md", "SWEEP IN PARTS: 0 areas not read\n", "SWEEP IN PARTS: 0 areas not read\n%s\n" % stray)
                self.assertFails(parts, r"part-3\.md: the last part says 0 areas not read, so nothing may sit under the line")


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
        parts = edit(self.parts, "part-2.md", WHOLE_LATER, "Whole repo: given in part 1; untracked: notes/scratch.md")
        self.assertFails(parts, r"part-2\.md: expected 'Whole repo: given in part 1\.'", r"part-2\.md: a later part must name no untracked path; found notes/scratch\.md")

    def test_the_whole_repo_line_repeated_in_full_in_part_2(self):
        parts = edit(self.parts, "part-2.md", WHOLE_LATER, WHOLE_1)
        out = self.assertFails(parts, r"part-2\.md: expected 'Whole repo: given in part 1\.'", r"part-2\.md: a later part must name no untracked path")
        self.assertIn("rules/r9999_draft.py", out)

    def test_an_untracked_path_named_in_the_prose_of_part_3(self):
        parts = edit(self.parts, "part-3.md", "## Findings\n", "## Findings\nNote: zones/zz_todo.txt is not tracked.\n")
        self.assertFails(parts, r"part-3\.md: a later part must name no untracked path; found zones/zz_todo\.txt")

    def test_a_later_part_that_says_something_else_for_whole_repo(self):
        parts = edit(self.parts, "part-3.md", WHOLE_LATER, "Whole repo: see part 1.")
        self.assertFails(parts, r"part-3\.md: expected 'Whole repo: given in part 1\.'")

    def test_a_later_part_with_no_whole_repo_line(self):
        parts = edit(self.parts, "part-3.md", WHOLE_LATER + "\n", "")
        self.assertFails(parts, r"part-3\.md: no 'Whole repo:' line in Coverage")


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

    def test_a_fact_found_in_a_later_part_only_counts(self):
        # move every fact into part 3: still proved
        parts = dict(self.parts)
        facts = "\n".join("- %s" % f["token"] for f in self.key["facts"])
        for name in ("part-1.md", "part-2.md"):
            for f in self.key["facts"]:
                parts[name] = parts[name].replace(f["token"], "REDACTED")
        parts["part-3.md"] = parts["part-3.md"].replace("## Findings\n", "## Findings\n" + facts + "\n")
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
