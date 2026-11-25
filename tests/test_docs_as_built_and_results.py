"""The docs batch after the qa pass: the results in evals/README.md, the scoped retry in docs/orchestrator.md,
the Unreleased changelog entry, the README and PRIVACY script lists, and design section 4's "As built (2026-11-24)".

Figures are tied to the plan's build log (docs/plans/2026-11-23-big-sweep-in-parts.md, from "## Build log" to the
end), never copied from the docs into a test: each check reads a figure out of the doc and looks for it in the
log's own text. Each check is a function of the text it is given, so a test can change one figure and see the
check notice. Phrase pins fold whitespace and have a deletion mutation (delete the phrase, only that pin fails).
Git comparisons skip when git, HEAD or main isn't there.

Standard library only. No model session is started.
"""
import fnmatch
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPENSIVE = ROOT / "evals-expensive"
PLAN = "docs/plans/2026-11-23-big-sweep-in-parts.md"
AS_BUILT = "### As built (2026-11-24)"
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen"}


def raw(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def fold(text):
    return " ".join(text.split())


def missing(folded, pins):
    return [name for name, phrase in pins if fold(phrase) not in folded]


def delete(folded, phrase):
    out = folded.replace(fold(phrase), "", 1)
    assert out != folded, "phrase not found: %r" % phrase
    return out


def git_show(spec):
    try:
        return subprocess.run(["git", "show", spec], cwd=str(ROOT), capture_output=True, check=True).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        return None


def build_log():
    plan = raw(PLAN)
    return plan[plan.index("## Build log"):]


def joined(values):
    """['a', 'b', 'c'] -> 'a, b and c', as the build log writes a list."""
    return ", ".join(values[:-1]) + " and " + values[-1]


def log_line(log, marker):
    hits = [l for l in log.splitlines() if marker in l]
    assert len(hits) == 1, "%r matches %d lines of the build log" % (marker, len(hits))
    return hits[0]


def log_table(log):
    rows = {}
    for m in re.finditer(r"^\s*\| (\d+) \| ([\w ]+) \| ([\d.]+)KB \| [^|]+ \| ([\d,]+) \|", log, re.M):
        rows[(m.group(1), m.group(2).strip())] = (m.group(3), m.group(4))
    return rows


def log_run_tally(log):
    """(failed run numbers, proved run numbers) read from the log's 'ten loop runs, in one place' line."""
    line = log_line(log, "The ten loop runs, in one place")
    scored = line[line.index("Scored as each was at the time:"): line.index("Every failure")]
    failed, proved = [], []
    for m in re.finditer(r"(\d+)(?: and (\d+))? (failed|proved)", scored):
        (failed if m.group(3) == "failed" else proved).extend(int(n) for n in m.groups()[:2] if n)
    return failed, proved


def loop_report_figures(log):
    """(report sizes in KB, file counts per part) over the log lines that give a loop run's three parts."""
    kbs, files = [], []
    for line in log.splitlines():
        if not re.search(r"three parts|Parts of \d|Part reports of", line) or "The ten loop runs" in line:
            continue
        kbs += [float(k) for k in re.findall(r"(\d+\.\d)KB", line)]
        for m in re.finditer(r"(\d+), (\d+) and (\d+) files", line):
            files += [int(n) for n in m.groups()]
    return kbs, files


FIGURE = re.compile(r"\$\d+\.\d\d|\d[\d,]*(?:\.\d+)?KB|\d[\d,]* (?:seconds|s)\b")


def figures_not_in_log(text, log):
    """Dollar, KB and seconds figures in text that the build log's own text doesn't hold."""
    out = []
    for m in FIGURE.finditer(text):
        fig = re.sub(r" (?:seconds|s)$", "", m.group(0))
        # a whole figure, not the tail of a bigger one (2KB is not in 12KB)
        if not re.search(r"(?<![\d.,])" + re.escape(fig) + r"(?![\d]|\.\d)", log):
            out.append(m.group(0))
    return out


# ---------------------------------------------------------------------------------------------------------------
# evals/README.md: the results on the final text

def evals_section():
    t = raw("evals/README.md")
    return t[t.index("### A big repo read in parts"): t.index("## How a case is built")]


OLD_RESULTS = "**The results, on the text before the review's batch"
NEW_RESULTS = "**The results, on the review's batch"
OLD_SMOKE = "**The smoke and the head-to-head, on the text before the review's batch"
NEW_SMOKE = "**The smoke and the head-to-head, on the review's batch"
AFTER = "**After a change to `investigate`,**"


def readme_results(section):
    """The results on the text before the review's batch: the table and the fix-round paragraphs, then the smoke and head-to-head
    paragraph for that text (the new results sit between them in the file)."""
    return section[section.index(OLD_RESULTS): section.index(NEW_RESULTS)] + "\n" + section[section.index(OLD_SMOKE): section.index(NEW_SMOKE)]


def readme_new_results(section):
    """The results on the review's batch: runs 13, 14, 15 and the harness run, then the smoke and head-to-head after it."""
    return section[section.index(NEW_RESULTS): section.index(OLD_SMOKE)] + "\n" + section[section.index(NEW_SMOKE): section.index(AFTER)]


def readme_problems(section, log):
    """Everything in the new results that the build log doesn't say, as a list of short descriptions."""
    problems = []
    results = fold(readme_results(section))
    # the table: seconds, files and report sizes of each run, against the log's line for that run
    rows = re.findall(r"\| (Headless \d+|Harness) \| ([\d,]+)(?: \(\$([\d.]+)\))? \| ([\d, ]+) \| ([^|]+) \|", results)
    if len(rows) != 3:
        return ["the results table changed shape: %d rows" % len(rows)]
    for name, secs, cost, files, kbs in rows:
        marker = "Run %s: exit 0" % name.split()[1] if name.startswith("Headless") else "the harness run on the final text"
        line = log_line(log, marker)
        if "%s s" % secs not in line:
            problems.append("%s seconds %s" % (name, secs))
        if cost and "$%s" % cost not in line:
            problems.append("%s cost $%s" % (name, cost))
        if joined([f.strip() for f in files.split(",")]) + " files" not in line:
            problems.append("%s files %s" % (name, files))
        if joined([k.strip() for k in kbs.split(",")]) not in line:
            problems.append("%s reports %s" % (name, kbs))
    # the loop result lines
    for need in ("`read: 945 of 945`", "`readers: 945 of 945, once each`", "`LOOP PROVED`"):
        if need not in results:
            problems.append("results no longer says %s" % need)
    for token in ("read: 945 of 945", "readers: 945 of 945, once each", "facts found: 33 of 33", "decoys found: 0 of 5"):
        if token not in log:
            problems.append("the log lacks %r" % token)
    if not re.search(r"all 33 facts, no decoy", results):
        problems.append("the 33 facts")
    # the tally of runs: derive it from the log
    failed, proved = log_run_tally(log)
    started, finished = len(failed) + len(proved) + 1, len(failed) + len(proved)
    if "By run 10, %s headless runs were started and %s finished" % (WORDS[started], WORDS[finished]) not in results:
        problems.append("runs started/finished (log: %d, %d)" % (started, finished))
    if "%s of the %s failed the scorer" % (WORDS[len(failed)].capitalize(), WORDS[finished]) not in results:
        problems.append("runs failed (log: %d of %d)" % (len(failed), finished))
    if "run 8 was stopped by a safety classifier" not in results or "run 8 was stopped by a safety classifier" not in log:
        problems.append("run 8")
    # the part-size paragraph's range and full part
    kbs, files = loop_report_figures(log)
    m = re.search(r"They ran (\d+\.\d)KB to (\d+\.\d)KB, the largest for (\d+) files", fold(section))
    if not m:
        problems.append("the part-report range changed shape")
    else:
        if (float(m.group(1)), float(m.group(2))) != (min(kbs), max(kbs)):
            problems.append("part-report range %s to %s (log: %s to %s)" % (m.group(1), m.group(2), min(kbs), max(kbs)))
        if "%sKB, held %s files" % (m.group(2), m.group(3)) not in log:
            problems.append("the largest report's file count")
    m = re.search(r"A full (\d+)-file part was (\d+\.\d)KB \(loop run (\d+)\)", fold(section))
    if not m:
        problems.append("the full part changed shape")
    elif "%s files, and its report is %sKB" % (m.group(1), m.group(2)) not in log_line(log, "Its second part is a full"):
        problems.append("the full part's figures")
    # the smoke
    m = re.search(r"`nesting-smoke` passed (\d+) of (\d+) graders in (\d+) seconds \(\$([\d.]+)\)", results)
    if not m or "`nesting-smoke` exit 0, %s s, $%s, %s of %s graders" % (m.group(3), m.group(4), m.group(1), m.group(2)) not in log:
        problems.append("the smoke")
    # the head-to-head
    m = re.search(r"ran (\d+) times in ([\d,]+) seconds \(\$([\d.]+) by the harness\)", results)
    if not m or "%s runs: exit 0, %s s, $%s by the harness" % m.groups() not in log:
        problems.append("the head-to-head's time and cost")
    m = re.search(r"found (\d+), (\d+) and (\d+) of (\d+), missed (\d+) and made up (\d+)", results)
    if not m or "found %s, %s and %s of %s, missed %s, made up %s" % m.groups() not in log:
        problems.append("found, missed, made up")
    if "three passes run during the build, two met the bar and one missed it" not in log or "One of the three passes run during the build scored `BAR MISSED`" not in results:
        problems.append("the BAR MISSED count")
    if "`fxctl X`" not in log or "`fxctl X`" not in results:
        problems.append("fxctl X")
    # and every dollar, KB and seconds figure anywhere in the section must be in the log's text
    problems += ["not in the log: %s" % f for f in figures_not_in_log(fold(section), log)]
    return problems


class ReadmeResultsAgreeWithTheBuildLogTest(unittest.TestCase):
    def setUp(self):
        self.log = build_log()
        self.section = evals_section()

    def test_every_figure_in_the_results_is_in_the_build_log(self):
        self.assertEqual(readme_problems(self.section, self.log), [])

    def test_every_dollar_kb_and_seconds_figure_in_the_whole_section_is_in_the_log_and_not_only_in_the_plan_header(self):
        self.assertEqual(figures_not_in_log(fold(self.section), self.log), [])

    def test_a_figure_that_is_only_the_tail_of_another_is_not_found(self):
        self.assertEqual(figures_not_in_log("a 6KB report and $9.80 and 2,992 s", "a 56KB reply, $9.80, 12,992 s"), ["6KB", "2,992 s"])
        self.assertEqual(figures_not_in_log("a 56KB report", "a 56KB reply"), [])

    def test_the_log_tally_is_what_the_readme_and_design_say_it_is(self):
        failed, proved = log_run_tally(self.log)
        self.assertEqual((sorted(failed), sorted(proved)), ([1, 2, 3, 7], [4, 5, 6, 9, 10]))

    def test_the_part_report_range_comes_from_at_least_eight_reports_in_the_log(self):
        kbs, files = loop_report_figures(self.log)
        self.assertGreaterEqual(len(kbs), 18)
        self.assertEqual((min(kbs), max(kbs), min(files), max(files)), (7.6, 29.1, 96, 450))

    def test_which_sizes_ran_with_which_brief_is_what_the_log_table_shows(self):
        text = fold(self.section)
        m = re.search(r"In live sessions, ([\d, ]+) and the full repo ran with the plain brief, .*? and (\d+) and the full repo ran "
                      r"again with the full-path brief\. In the harness, (\d+) and the full repo ran with the full-path brief\. "
                      r"`reply-size-(\d+)` never ran", text)
        self.assertIsNotNone(m, "the which-ran sentence changed shape")
        table = log_table(self.log)
        # the plain-brief sizes and the full-path sizes, derived from the log's table rows (645 is "the full repo")
        plain = sorted(int(f) for f, brief in table if brief == "plain" and f != "645")
        full = sorted(int(f) for f, brief in table if brief == "full paths" and f != "645")
        self.assertIn(("645", "plain"), table)
        self.assertIn(("645", "full paths"), table)
        self.assertEqual(sorted(int(n) for n in re.findall(r"\d+", m.group(1))), plain)
        self.assertEqual([int(m.group(2))], full)
        harness = self.log[self.log.index("Task 3, harness series"):]
        harness = harness[:harness.index("\n")]
        self.assertIn("`reply-size-%s` exit 0" % m.group(3), harness)
        self.assertIn("`reply-size-full` exit 0", harness)
        self.assertIn("full-path brief", harness)
        # 400 never ran: no row of any brief, and no run line of any kind mentions it
        self.assertNotIn(m.group(4), [f for f, _ in table])
        self.assertNotIn("reply-size-%s` exit" % m.group(4), self.log)
        self.assertEqual(sorted(p.name for p in EXPENSIVE.glob("reply-size-%s" % m.group(4))), ["reply-size-%s" % m.group(4)])

    def test_a_size_missing_from_the_plain_list_would_be_seen(self):
        text = fold(self.section).replace("150, 230, 320, 450 and the full repo ran with the plain brief", "150, 230, 450 and the full repo ran with the plain brief")
        m = re.search(r"In live sessions, ([\d, ]+) and the full repo ran with the plain brief", text)
        plain = sorted(int(f) for f, brief in log_table(self.log) if brief == "plain" and f != "645")
        self.assertNotEqual(sorted(int(n) for n in re.findall(r"\d+", m.group(1))), plain)

    def test_a_changed_figure_is_seen(self):
        s = self.section
        for old, new in (("| Headless 9 | 2,992 |", "| Headless 9 | 2,993 |"), ("412, 366, 172", "412, 366, 173"),
                         ("18.6KB, 11.3KB, 13.9KB", "18.6KB, 11.3KB, 13.8KB"), ("2,541 ($9.80)", "2,541 ($9.81)"),
                         ("368, 366, 216", "368, 366, 217"), ("passed\n8 of 8 graders in 59 seconds", "passed\n8 of 8 graders in 60 seconds"),
                         ("They ran 7.6KB to 29.1KB", "They ran 7.6KB to 29.2KB"), ("the largest for 340 files", "the largest for 341 files"),
                         ("A full 450-file part\nwas 15.9KB", "A full 450-file part\nwas 15.8KB"),
                         ("found 48, 48 and 48 of 48", "found 48, 48 and 47 of 48"), ("2,004 seconds", "2,005 seconds"),
                         ("Four of the nine failed", "Three of the nine failed"), ("By run 10, ten headless runs were started", "By run 10, nine headless runs were started"),
                         ("($7.50 by the harness)", "($7.51 by the harness)"), ("(1,840 seconds)", "(1,841 seconds)")):
            with self.subTest(change=new):
                folded_s = s
                if old not in folded_s:
                    # a figure the section wraps: find it on its folded text instead
                    wrapped = fold(s)
                    self.assertIn(fold(old), wrapped, old)
                    mutated = wrapped.replace(fold(old), fold(new), 1)
                else:
                    mutated = folded_s.replace(old, new, 1)
                self.assertNotEqual(readme_problems(mutated, self.log), [])


# ---------------------------------------------------------------------------------------------------------------
# evals/README.md: the harness glob, the commands

class HarnessCommandsTest(unittest.TestCase):
    """The harness runs of the reply-size cases name their two cases outright (no glob: the harness's glob rules are unknown)."""

    @staticmethod
    def harness_commands(section):
        return [l for l in section.splitlines() if l.startswith("claude plugin eval") and "--case" in l and "reply-size" in l]

    def test_the_reply_size_harness_commands_name_exactly_the_two_cases_that_ran_in_the_harness(self):
        cases = [re.search(r"--case (\S+)", c).group(1) for c in self.harness_commands(evals_section())]
        self.assertEqual(cases, ["reply-size-320", "reply-size-full"])
        for case in cases:
            self.assertTrue((EXPENSIVE / case).is_dir(), case)
            self.assertTrue((EXPENSIVE / case / "scaffold.sh").is_file(), case)

    def test_no_case_value_in_the_section_has_a_bracket_class_or_a_star(self):
        values = re.findall(r"--case (?:'([^']*)'|(\S+))", evals_section())
        self.assertGreaterEqual(len(values), 4)
        for quoted, bare in values:
            with self.subTest(case=quoted or bare):
                self.assertIsNone(re.search(r"[\[\]]", quoted or bare))
        self.assertEqual([q or b for q, b in values if "reply-size" in (q or b)], ["reply-size-320", "reply-size-full"])

    def test_each_output_dir_is_read_by_a_measure_reply_harness_line(self):
        lines = evals_section().splitlines()
        for i, cmd in enumerate(self.harness_commands(evals_section())):
            out = re.search(r'--output-dir "([^"]+)"', cmd).group(1)
            with self.subTest(output_dir=out):
                index = lines.index(cmd)
                following = lines[index + 1]
                self.assertIn("measure_reply.py --harness", following)
                self.assertIn('--harness "%s/aggregate-result.json"' % out, following)
        dirs = [re.search(r'--output-dir "([^"]+)"', c).group(1) for c in self.harness_commands(evals_section())]
        self.assertEqual(len(set(dirs)), 2, "each case has its own output dir")

    def test_a_widened_or_bracketed_case_would_be_seen(self):
        bad = evals_section().replace("--case reply-size-full ", "--case 'reply-size-[3f]*' ")
        self.assertIsNotNone(re.search(r"[\[\]]", re.search(r"--case '([^']*)'", bad).group(1)))
        mismatched = evals_section().replace('--harness "$WORK/results/reply-size-full/', '--harness "$WORK/results/reply-size-320/')
        self.assertNotIn('--harness "$WORK/results/reply-size-full/', mismatched)


class SmokeSentenceTest(unittest.TestCase):
    PINS = [
        ("the smoke passed 8 of 8 on the text before the batch", "`nesting-smoke` passed 8 of 8 graders in 59 seconds ($0.42)"),
        ("its one report opened with the 0 line", "That one report opened with `SWEEP IN PARTS: 0 areas not read`"),
        ("why, in the past: the brief's words", "because the smoke's brief said to read its six files \"exactly as you would above the size limit\"."),
        ("the brief now says as for a repo of more than about 150 files, one report, not a sweep in parts",
         "The smoke's brief now says to run it as one area with one area lead, as for a repo of more than about 150 files, and that it still comes back as one report, not a sweep in parts."),
        ("on the new text: 8 of 8 in 50 seconds, and one ordinary report with no parts block",
         "`nesting-smoke` passed 8 of 8 graders in 50 seconds ($0.39), and the report is one ordinary report again: it opens `Mode: full sweep, 1 area lead` and has no `SWEEP IN PARTS` block."),
    ]

    def test_the_old_behaviour_is_described_as_past(self):
        t = fold(evals_section())
        self.assertNotIn("because the smoke's brief says to read its six files", t)
        self.assertNotIn("All 8 graders pass either way", t)
        self.assertLess(t.index("because the smoke's brief said to read its six files"), t.index("The smoke's brief now says to run it as one area"))

    def test_every_pin_holds(self):
        self.assertEqual(missing(fold(evals_section()), self.PINS), [])

    def test_deleting_each_phrase_fails_that_pin_and_only_that_pin(self):
        folded = fold(evals_section())
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(folded, phrase), self.PINS), [name])

    def test_the_zero_line_token_is_on_one_line_and_is_the_fixed_shape(self):
        lines = [l for l in evals_section().splitlines() if "SWEEP IN PARTS: 0 areas not read" in l]
        self.assertEqual(len(lines), 1)
        self.assertEqual(SplitTokenTest.split(evals_section()), [])

    def test_the_log_says_the_same_thing(self):
        log = build_log()
        self.assertIn("opened its one report with `SWEEP IN PARTS: 0 areas not read`", log)


class LiveCommandsTest(unittest.TestCase):
    @staticmethod
    def unmade_dirs(section):
        """(line, folder) for each code line that redirects into "$WORK/<folder>/..." with no mkdir of that folder before the redirect."""
        bad, in_code, made = [], False, set()
        for line in section.splitlines():
            if line.startswith("```"):
                in_code, made = not in_code, set()
                continue
            if not in_code:
                continue
            events = [(m.start(), "make", m.group(1)) for m in re.finditer(r'mkdir -p "\$WORK/(\w+)"', line)]
            events += [(m.start(), "write", m.group(1)) for m in re.finditer(r'> "\$WORK/(\w+)/', line)]
            for _pos, kind, folder in sorted(events):
                if kind == "make":
                    made.add(folder)
                elif folder not in made:
                    bad.append((line[:60], folder))
        return bad

    def test_each_command_that_redirects_into_work_makes_the_folder_first(self):
        section = evals_section()
        self.assertEqual(self.unmade_dirs(section), [])
        self.assertGreaterEqual(len(re.findall(r'> "\$WORK/(?:measure|loop)/', section)), 2)

    def test_the_live_measuring_command_makes_measure_before_its_redirect_on_the_same_line(self):
        line = [l for l in evals_section().splitlines() if '> "$WORK/measure/live-$N.jsonl"' in l][0]
        self.assertLess(line.index('mkdir -p "$WORK/measure"'), line.index('> "$WORK/measure/'))

    def test_a_missing_mkdir_is_seen(self):
        section = evals_section().replace('mkdir -p "$WORK/measure"; ', "", 1)
        self.assertEqual([f for _l, f in self.unmade_dirs(section)], ["measure"])
        moved = evals_section().replace('mkdir -p "$WORK/measure"; ', "", 1).replace("python3 \"$REPO/evals-expensive/measure_reply.py\" --transcript \"$WORK/measure/live",
                                                                                       'mkdir -p "$WORK/measure"\npython3 "$REPO/evals-expensive/measure_reply.py" --transcript "$WORK/measure/live', 1)
        self.assertEqual([f for _l, f in self.unmade_dirs(moved)], ["measure"], "a mkdir after the redirect doesn't count")


class TranscriptFlagTest(unittest.TestCase):
    @staticmethod
    def flags(script):
        src = (EXPENSIVE / script).read_text(encoding="utf-8")
        return set(re.findall(r"add_argument\(\s*\"(--[\w-]+)\"", src))

    def test_the_scoring_command_passes_the_transcript_the_loop_command_writes(self):
        section = evals_section()
        written = re.search(r'--verbose > "(\$WORK/loop/loop-\$R\.jsonl)"', section).group(1)
        check = [l for l in section.splitlines() if "check_parts.py" in l and "python3" in l][0]
        self.assertIn('--transcript "%s"' % written, check)
        self.assertIn("--transcript", self.flags("check_parts.py"))
        self.assertIn("--transcript", self.flags("measure_reply.py"))

    def test_every_flag_in_a_backticked_scoring_phrase_is_a_check_parts_flag(self):
        text = fold(evals_section())
        phrases = re.findall(r"`((?:--[a-z][\w-]*(?: [\w$./-]+)? ?)+)`", text)
        self.assertTrue(any("--transcript" in p for p in phrases))
        for phrase in phrases:
            if "--min-parts" in phrase:
                with self.subTest(phrase=phrase):
                    self.assertLessEqual(set(re.findall(r"--[a-z][\w-]*", phrase)), self.flags("check_parts.py"))

    def test_the_prose_that_says_transcript_checks_names_each_check_the_script_makes(self):
        # the three transcript checks in the README's description are the three the scorer's docstring lists
        doc = (EXPENSIVE / "check_parts.py").read_text(encoding="utf-8")
        text = fold(evals_section())
        self.assertIn("each readable file had one reader started and completed", text)
        self.assertIn("one file-reader task started and completed", fold(doc))
        self.assertIn("each later `investigate` brief is `CONTINUE SWEEP` plus the previous part's block", text)
        self.assertIn("each part file is the report the agent returned", text)


# ---------------------------------------------------------------------------------------------------------------
# fixed tokens, split across lines (rules item 9): the counts line and the labels as well as the six the old test knows

class SplitTokenTest(unittest.TestCase):
    LOOSE = {
        "Areas not read:": r"Areas\s+not\s+read:",
        "Areas read:": r"Areas\s+read:",
        "Whole repo:": r"Whole\s+repo:",
        "SWEEP IN PARTS: <n> areas not read": r"SWEEP\s+IN\s+PARTS:\s+<n>\s+areas\s+not\s+read",
        "SWEEP IN PARTS: <n> files not read": r"SWEEP\s+IN\s+PARTS:\s+<n>\s+files\s+not\s+read",
        "Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>":
            r"Files\s+listed:\s+<n>;\s+read:\s+<n>;\s+skipped:\s+<n>;\s+re-dispatched:\s+<n>;\s+failed:\s+<n>;\s+unread:\s+<n>",
        "CONTINUE SWEEP": r"CONTINUE\s+SWEEP",
        "END OF BLOCK": r"END\s+OF\s+BLOCK",
        "INVESTIGATE REPORT ENDS": r"INVESTIGATE\s+REPORT\s+ENDS",
        "AREA REPORT ENDS": r"AREA\s+REPORT\s+ENDS",
        "STOPPED BEFORE READING": r"STOPPED\s+BEFORE\s+READING",
    }

    @classmethod
    def split(cls, text):
        """Tokens that appear with a line break (or a doubled space) inside them."""
        bad = []
        for token, loose in cls.LOOSE.items():
            if len(re.findall(loose, text)) != len(re.findall(re.escape(token), text)):
                bad.append(token)
        return bad

    def as_built(self):
        t = raw("docs/design.md")
        return t[t.index(AS_BUILT):]

    def test_no_fixed_token_is_split_in_the_docs_or_the_new_design_subsection(self):
        for rel in ("README.md", "docs/orchestrator.md", "evals/README.md", "CONTRIBUTING.md", "PRIVACY.md", "CHANGELOG.md"):
            with self.subTest(file=rel):
                self.assertEqual(self.split(raw(rel)), [])
        with self.subTest(file="docs/design.md, As built (2026-11-24)"):
            self.assertEqual(self.split(self.as_built()), [])

    def test_the_new_subsection_names_the_tokens_it_uses_each_on_one_line(self):
        text = self.as_built()
        for token in ("CONTINUE SWEEP", "INVESTIGATE REPORT ENDS", "SWEEP IN PARTS: 0 areas not read", "STOPPED BEFORE READING"):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_the_checker_sees_a_wrapped_counts_line_and_label(self):
        self.assertEqual(self.split("`Files listed: <n>; read: <n>; skipped: <n>;\nre-dispatched: <n>; failed: <n>; unread: <n>`"),
                         ["Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>"])
        self.assertEqual(self.split("the `Whole\nrepo:` line"), ["Whole repo:"])
        self.assertEqual(self.split("`Areas not\nread:`"), ["Areas not read:"])
        self.assertEqual(self.split("SWEEP IN\nPARTS: <n> files not read"), ["SWEEP IN PARTS: <n> files not read"])
        self.assertEqual(self.split("`Whole repo:` and `Areas read:` and `Areas not read:`"), [])

    def test_the_counts_line_is_one_line_in_the_changelog_entry(self):
        token = "Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>"
        entry = ChangelogTest.unreleased(raw("CHANGELOG.md"))
        self.assertTrue(any(token in line for line in entry.splitlines()))


# ---------------------------------------------------------------------------------------------------------------
# docs/orchestrator.md: the scoped read's one retry

class PinTable(object):
    def test_every_pin_holds_on_the_file_as_it_is(self):
        self.assertEqual(missing(fold(self.text()), self.PINS), [])

    def test_deleting_each_phrase_fails_that_pin_and_only_that_pin(self):
        folded = fold(self.text())
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(folded, phrase), self.PINS), [name])


class OrchestratorScopedRetryTest(PinTable, unittest.TestCase):
    def text(self):
        return raw("docs/orchestrator.md")

    PINS = [
        ("the scoped read leaves the same paths unread: same brief once more",
         "For a scoped read, a report that leaves the same paths unread gets the same brief once more,"),
        ("then stop and name the unread files", "then you stop and tell the user which files are unread."),
    ]

    def bullet(self):
        t = fold(self.text())
        return t[t.index("gets the same brief once more. If that fails too"): t.index("- A report that arrives as a preview")]

    def test_the_scoped_retry_sits_in_the_failure_bullet_and_is_one_retry_not_a_loop(self):
        b = self.bullet()
        self.assertIn("For a scoped read", b)
        self.assertEqual(len(re.findall(r"once more", b)), 2)  # the area retry above it, and this one
        self.assertEqual(len(re.findall(r"once more", b[b.index("For a scoped read"):])), 1)
        # one retry then a stop: no second or third retry, no loop. Saying a single report "came back cut off twice" is a report of what
        # happened, not a retry count, so only "twice" used for retrying is out.
        self.assertNotRegex(b, r"(?i)(?:retr(?:y|ies)|tr(?:y|ies)|send(?:s|ing)?|again|resend)\s+(?:it\s+)?twice|twice\s+(?:more|again)|keeps? (?:trying|going)|until (?:it|they) (?:work|succeed)|as many times")
        self.assertEqual(len(re.findall(r"\btwice\b", b)), len(re.findall(r"cut off twice", b)))

    def test_the_no_loop_check_still_catches_a_retry_twice_wording(self):
        pattern = r"(?i)(?:retr(?:y|ies)|tr(?:y|ies)|send(?:s|ing)?|again|resend)\s+(?:it\s+)?twice|twice\s+(?:more|again)"
        for bad in ("then retry twice", "try it twice", "send the brief again twice", "gets one more go, twice more"):
            with self.subTest(bad=bad):
                self.assertRegex(bad, pattern)
        self.assertNotRegex("tell the user it came back cut off twice", pattern)

    def test_the_scoped_retry_doesnt_tell_the_session_to_ask(self):
        b = self.bullet()
        self.assertNotRegex(b, r"(?i)\bask(?:s|ing)? (?:the user|you)\b|get (?:the user's|an?) (?:ok|okay|approval)")

    def test_a_missing_stop_would_be_seen(self):
        folded = fold(self.text())
        mutated = folded.replace("then you stop and tell the user which files are unread.", "then you carry on.", 1)
        self.assertEqual(missing(mutated, self.PINS), ["then stop and name the unread files"])


# ---------------------------------------------------------------------------------------------------------------
# CHANGELOG.md

class ChangelogTest(unittest.TestCase):
    NUMBERED = re.compile(r"^## \[(\d+\.\d+\.\d+)\][^\n]*\n", re.M)

    @classmethod
    def entries(cls, text):
        """[(heading line, entry text)] for every `## [` entry."""
        starts = [m.start() for m in re.finditer(r"^## \[", text, re.M)] + [len(text)]
        return [(text[a:text.index("\n", a)], text[a:b]) for a, b in zip(starts, starts[1:])]

    @classmethod
    def unreleased(cls, text):
        """The entry for this work, found by what it holds, whatever its heading says: the oldest entry that mentions
        SWEEP IN PARTS (a later release may quote the token, the one that introduced it is this work's)."""
        hits = [e for _h, e in cls.entries(text) if "SWEEP IN PARTS" in e]
        assert hits, "no changelog entry mentions SWEEP IN PARTS"
        return hits[-1]

    @classmethod
    def entry(cls, text, version):
        m = re.search(r"^## \[%s\][^\n]*\n" % re.escape(version), text, re.M)
        if not m:
            return None
        nxt = re.compile(r"^## \[\d+\.\d+\.\d+\]", re.M).search(text, m.end())
        return text[m.start(): nxt.start() if nxt else len(text)]

    def test_the_2_2_0_entry_is_byte_identical_to_mains(self):
        main = git_show("main:CHANGELOG.md")
        if main is None:
            self.skipTest("no main branch to compare with")
        self.assertIsNotNone(self.entry(main, "2.2.0"))
        self.assertEqual(self.entry(raw("CHANGELOG.md"), "2.2.0"), self.entry(main, "2.2.0"))

    def test_the_comparison_with_main_sees_a_one_character_change(self):
        text = raw("CHANGELOG.md")
        i = text.index("## [2.2.0]")
        j = text.index("\n", text.index("\n", i) + 2)
        self.assertNotEqual(self.entry(text[:j] + "." + text[j:], "2.2.0"), self.entry(text, "2.2.0"))

    def test_the_entry_is_found_by_its_content_under_an_unreleased_or_a_numbered_heading(self):
        text = raw("CHANGELOG.md")
        heading = [h for h, e in self.entries(text) if e == self.unreleased(text)][0]
        self.assertTrue(heading.startswith("## [Unreleased]") or self.NUMBERED.match(heading + "\n"), heading)

    def test_every_numbered_entry_that_main_also_has_is_byte_identical_to_mains(self):
        main = git_show("main:CHANGELOG.md")
        if main is None:
            self.skipTest("no main branch to compare with")
        mine = raw("CHANGELOG.md")
        shared = [v for v in re.findall(r"^## \[(\d+\.\d+\.\d+)\]", mine, re.M) if self.entry(main, v) is not None]
        self.assertIn("2.2.0", shared)
        for v in shared:
            with self.subTest(version=v):
                self.assertEqual(self.entry(mine, v), self.entry(main, v))

    def test_that_comparison_sees_an_edited_entry_whichever_version_it_is(self):
        text = raw("CHANGELOG.md")
        for v in re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, re.M)[:3]:
            with self.subTest(version=v):
                i = text.index("## [%s]" % v)
                j = text.index("\n", text.index("\n", i) + 2)
                self.assertNotEqual(self.entry(text[:j] + "." + text[j:], v), self.entry(text, v))

    def test_after_a_release_renames_the_heading_every_content_pin_still_holds(self):
        text = raw("CHANGELOG.md")
        heading = self.entries(text)[0][0]
        released = text.replace(heading, "## [2.3.0] \u2014 2026-12-01", 1)
        if heading == "## [2.3.0] \u2014 2026-12-01":
            self.skipTest("already renamed")
        self.assertNotEqual(released, text)
        self.assertEqual(len(re.findall(r"^## \[Unreleased\]", released, re.M)), 0)
        self.assertEqual(self.NUMBERED.search(released).group(1), "2.3.0")
        entry = fold(self.unreleased(released))
        self.assertEqual(missing(entry, self.PINS), [])
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(entry, phrase), self.PINS), [name])
        block = entry[entry.index("`evals-expensive/check_parts.py` ("): entry.index("All three run by hand")]
        self.assertEqual(len(re.findall(r"(?i)\basked\b", block)), 1)

    PINS = [
        ("the counts line, as the exact fixed token",
         "`Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>`"),
        ("who checks that nobody asked",
         "Whether anybody asked is for the `no-asking` grader and the session's final message, not the scorer."),
        ("the scorer checks reads against the transcript", "its reads checked against the run's own transcript"),
        ("a result is whole when the marker is last", "a result is whole only when the marker is its last line"),
        ("the gone sentence", "reply are gone. Nobody asks the user before a sweep, whatever its size, or between parts (design §4)."),
        ("counts come from a command", "The counts are added with a command, never in the model's head."),
        ("leads one at a time", "Readers go 10 at a time and area leads one at a time, never two leads in one message."),
        ("nothing drawn from skipped folders", "and nothing drawn from their contents"),
    ]

    def entry_text(self):
        return fold(self.unreleased(raw("CHANGELOG.md")))

    def test_every_pin_holds_in_the_unreleased_entry(self):
        self.assertEqual(missing(self.entry_text(), self.PINS), [])

    def test_deleting_each_phrase_fails_that_pin_and_only_that_pin(self):
        folded = self.entry_text()
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(folded, phrase), self.PINS), [name])

    def test_the_entry_does_not_say_the_scorer_checks_that_nobody_asked(self):
        entry = self.entry_text()
        block = entry[entry.index("`evals-expensive/check_parts.py` ("): entry.index("All three run by hand")]
        self.assertEqual(len(re.findall(r"(?i)\basked\b", block)), 1, block)
        self.assertNotRegex(block, r"(?i)nobody asked|no one asked|never asked|without asking")
        # and the same for the evals README's description of the scorer
        bullet = re.search(r"(?ms)^- `check_parts\.py --key.*?(?=^\*\*|\Z)", evals_section()).group(0)
        self.assertNotRegex(bullet, r"(?i)\bask")

    def test_the_old_claim_would_be_seen(self):
        old = self.entry_text().replace(
            "Whether anybody asked is for the `no-asking` grader and the session's final message, not the scorer.", "")
        old = old.replace("the counts and the block right", "the counts and the block right, nobody asked")
        block = old[old.index("`evals-expensive/check_parts.py` ("): old.index("All three run by hand")]
        self.assertRegex(block, r"(?i)nobody asked")


# ---------------------------------------------------------------------------------------------------------------
# README.md and PRIVACY.md

class ScriptListsTest(unittest.TestCase):
    def readme_section(self):
        t = raw("README.md")
        return t[t.index("## What it runs, sends, and fetches"):]

    def readme_scripts(self):
        t = self.readme_section()
        t = t[: t.index("\n## ", 5)] if "\n## " in t[5:] else t
        return set(re.findall(r"\b([a-z][a-z_]+)\.py\b", t))

    def privacy_scripts(self):
        return set(re.findall(r"evals-expensive/([a-z][a-z_]+)\.py", fold(raw("PRIVACY.md"))))

    def on_disk(self):
        return {p.stem for p in EXPENSIVE.glob("*.py")}

    def test_the_readme_names_all_five_scripts_and_each_exists(self):
        self.assertEqual(len(self.readme_scripts()), 5)
        for name in self.readme_scripts():
            with self.subTest(script=name):
                self.assertTrue((EXPENSIVE / (name + ".py")).is_file())

    def test_the_readme_and_privacy_name_the_same_scripts(self):
        self.assertEqual(self.readme_scripts(), self.privacy_scripts())

    def test_both_name_every_script_in_evals_expensive(self):
        self.assertEqual(self.on_disk(), self.readme_scripts())
        self.assertEqual(self.on_disk(), self.privacy_scripts())
        self.assertEqual(self.on_disk(), {"compare", "sync_case", "sync_big_sweep", "check_parts", "measure_reply"})

    def test_the_comparison_sees_a_script_missing_from_either_file(self):
        readme = self.readme_scripts() - {"measure_reply"}
        self.assertNotEqual(readme, self.privacy_scripts())
        self.assertNotEqual(self.privacy_scripts() | {"extra"}, self.readme_scripts())

    def test_what_the_readme_says_each_script_runs_is_what_its_source_does(self):
        text = fold(self.readme_section())
        sync = (EXPENSIVE / "sync_big_sweep.py").read_text(encoding="utf-8")
        check = (EXPENSIVE / "check_parts.py").read_text(encoding="utf-8")
        measure = (EXPENSIVE / "measure_reply.py").read_text(encoding="utf-8")
        self.assertIn("`sync_big_sweep.py` runs the big-sweep scaffold with `--emit-key` and writes generated files under `evals-expensive/`", text)
        self.assertIn('"--emit-key"', sync)
        self.assertRegex(sync, r"subprocess\.run\(\[\"bash\", str\(SCAFFOLD\)")
        self.assertIn("`check_parts.py` runs the fixture's `bin/git ls-files`", text)
        self.assertRegex(check, r'os\.path\.join\(repo, "bin", "git"\)')
        self.assertIn('"ls-files"', check)
        self.assertIn("`measure_reply.py` reads transcripts and result JSON", text)
        self.assertIsNone(re.search(r"(?m)^\s*(?:import|from)\s+subprocess", measure), "measure_reply.py runs nothing")

    def test_every_scaffold_that_builds_a_repo_writes_a_bin_git_wrapper(self):
        scaffolds = sorted(EXPENSIVE.glob("*/scaffold.sh"))
        self.assertGreaterEqual(len(scaffolds), 9)
        builds = 0
        for sc in scaffolds:
            src = sc.read_text(encoding="utf-8")
            if re.search(r"git .*init|init -q", src):
                builds += 1
                with self.subTest(scaffold=str(sc.relative_to(ROOT))):
                    self.assertIn("bin/git", src)
        self.assertEqual(builds, len(scaffolds))
        self.assertIn("scaffolds that builds a repo writes a `bin/git` wrapper", fold(self.readme_section()).replace("Each of the `evals-expensive/` ", ""))

    def test_all_five_scripts_use_no_network(self):
        for name in sorted(self.on_disk()):
            src = (EXPENSIVE / (name + ".py")).read_text(encoding="utf-8")
            with self.subTest(script=name):
                self.assertIsNone(re.search(r"(?m)^\s*(?:import|from)\s+(?:urllib|http|socket|requests|ftplib|smtplib)\b", src))

    def test_privacy_says_what_the_two_scripts_that_run_something_run(self):
        p = fold(raw("PRIVACY.md"))
        self.assertIn("`sync_big_sweep.py` also runs a scaffold and writes generated files under `evals-expensive/`", p)
        self.assertIn("`check_parts.py` runs the fixture's own `bin/git`", p)
        self.assertIn("scaffolds that build a repo each write a `bin/git` wrapper into their scratch fixture", p)
        self.assertNotIn("the eval scaffold writes", p)


# ---------------------------------------------------------------------------------------------------------------
# docs/design.md: section 4's "As built (2026-11-24)"

def design_parts(text):
    """(text before section 4, section 4 up to the As built heading, the As built subsection or '')."""
    start = re.search(r"^## 4\. ", text, re.M).start()
    i = text.find(AS_BUILT)
    return text[:start], text[start: i if i >= 0 else len(text)], text[i:] if i >= 0 else ""


def as_built_problems(sub, log):
    """What the As built subsection says that the build log doesn't."""
    problems = []
    t = fold(sub)
    # the measurement table: seven rows, each equal to the log's row (files, brief) -> (KB, seconds)
    rows = {}
    for m in re.finditer(r"^\| (\d+) \| (plain|full paths) \| ([\d.]+)KB \| ([\d,]+) \|", sub, re.M):
        rows[(m.group(1), m.group(2))] = (m.group(3), m.group(4))
    if len(rows) != 7 or rows != log_table(log):
        problems.append("measurement table: %s vs log %s" % (rows, log_table(log)))
    # the harness's two measurements and the in-session run
    m = re.search(r"`reply-size-(\w+)` took ([\d,]+) s and \$([\d.]+), and `reply-size-(\w+)` ([\d,]+) s and \$([\d.]+)", t)
    if not m:
        problems.append("harness measurements changed shape")
    else:
        for name, secs, cost in ((m.group(1), m.group(2), m.group(3)), (m.group(4), m.group(5), m.group(6))):
            if "`reply-size-%s` exit 0, %s s, $%s" % (name, secs, cost) not in log:
                problems.append("harness %s" % name)
    m = re.search(r"came back whole as about ([\d.]+)KB after ([\d,]+) s", t)
    if not m or "about %sKB of text after %s s" % m.groups() not in log:
        problems.append("in-session run")
    # where previews start, and the two sources
    for fig in ("36KB and 54KB", "35.6KB", "53.7KB", "56KB", "2KB preview"):
        if fig not in t and fig.replace(" preview", "") not in t:
            problems.append("design lacks %s" % fig)
        if fig not in log:
            problems.append("log lacks %s" % fig)
    if "between 36KB and 54KB" not in t or "between 36KB and 54KB" not in log.replace("from 36KB to", "between 36KB and").replace("somewhere between 36KB and 54KB", "between 36KB and 54KB"):
        problems.append("preview range")
    line = log_line(log, "What the stored 2026-11-05 results show")
    sonnet = [float(x) for x in re.findall(r"(\d+\.\d)KB", line.split("With `investigate` on Sonnet")[1])]
    m = re.search(r"on Sonnet the same repo gave (\d+)KB to (\d+)KB", t)
    if not m or (int(m.group(1)), int(m.group(2))) != (round(min(sonnet)), round(max(sonnet))):
        problems.append("Sonnet's range (log: %s to %s)" % (min(sonnet), max(sonnet)))
    if "53.7KB" not in line or "Haiku" not in line:
        problems.append("the 53.7KB report from the Haiku arm")
    # k and the owner's choice
    if "so k = 3" not in log or "k was 3" not in t:
        problems.append("k")
    if "The options were 450 (recommended), 300 and 600" not in log or "chose 450 over 300 and 600" not in t:
        problems.append("the owner's options")
    # the loop runs of record
    m = re.search(r"three parts each \((\d+), (\d+) and (\d+) files; then (\d+), (\d+) and (\d+)\)", t)
    if not m:
        problems.append("loop runs 9 and 10 changed shape")
    else:
        g = m.groups()
        if "(%s, %s and %s files listed" % g[:3] not in log_line(log, "Run 9: exit 0"):
            problems.append("run 9 files")
        if "(%s, %s and %s files listed" % g[3:] not in log_line(log, "Run 10: exit 0"):
            problems.append("run 10 files")
    m = re.search(r"in ([\d,]+) s and ([\d,]+) s\. The harness run on the same text took ([\d,]+) s and \$([\d.]+), passed all (\w+) graders", t)
    if not m:
        problems.append("loop seconds changed shape")
    else:
        if "%s s" % m.group(1) not in log_line(log, "Run 9: exit 0") or "%s s" % m.group(2) not in log_line(log, "Run 10: exit 0"):
            problems.append("loop seconds")
        h = log_line(log, "the harness run on the final text")
        if "%s s, $%s, all %s graders passed" % (m.group(3), m.group(4), m.group(5)) not in h:
            problems.append("harness run's seconds, cost, graders")
    m = re.search(r"parts rebuilt from its kept trace \((\d+), (\d+) and (\d+) files\)", t)
    if not m or "Parts of %s, %s and %s files" % m.groups() not in log_line(log, "the harness run on the final text"):
        problems.append("harness run's files")
    for need in ("33 of 33 facts", "945 of 945 files read once"):
        if need not in t:
            problems.append("design lacks %r" % need)
    for token in ("facts found: 33 of 33", "read: 945 of 945", "readers: 945 of 945, once each"):
        if token not in log:
            problems.append("log lacks %r" % token)
    # the ten runs: ten started, run 8 not counted, four failed and five proved: derived from the log
    failed, proved = log_run_tally(log)
    if "It took %s headless runs" % WORDS[len(failed) + len(proved) + 1] not in t:
        problems.append("ten runs")
    if "Of the other %s, %s failed the scorer and %s proved" % (WORDS[len(failed) + len(proved)], WORDS[len(failed)], WORDS[len(proved)]) not in t:
        problems.append("four failed, five proved")
    if "Run 8 was stopped by a safety classifier while the session saved part 2, and isn't counted" not in t or "run 8 was stopped by a safety classifier" not in log:
        problems.append("run 8")
    # the smoke and the head-to-head
    m = re.search(r"`nesting-smoke` passed (\d+) of (\d+) graders \((\d+) s, \$([\d.]+)\)", t)
    if not m or "`nesting-smoke` exit 0, %s s, $%s, %s of %s graders" % (m.group(3), m.group(4), m.group(1), m.group(2)) not in log:
        problems.append("smoke")
    m = re.search(r"found (\d+) of (\d+) in all three runs, missed (\d+) and made up (\d+), and scored `BAR MET` \(([\d,]+) s, \$([\d.]+)\)", t)
    if not m:
        problems.append("head-to-head changed shape")
    else:
        a, b, miss, made, secs, cost = m.groups()
        if "found %s, %s and %s of %s, missed %s, made up %s" % (a, a, a, b, miss, made) not in log:
            problems.append("head-to-head found/missed/made up")
        if "exit 0, %s s, $%s by the harness" % (secs, cost) not in log:
            problems.append("head-to-head time and cost")
    if "scored `BAR MISSED`" not in t or "`BAR MISSED`" not in log:
        problems.append("BAR MISSED")
    # the part reports of the loop runs
    kbs, files = loop_report_figures(log)
    m = re.search(r"reports ran (\d+\.\d)KB to (\d+\.\d)KB for (\d+) to (\d+) files", t)
    if not m or (float(m.group(1)), float(m.group(2)), int(m.group(3)), int(m.group(4))) != (min(kbs), max(kbs), min(files), max(files)):
        problems.append("part-report range (log: %s to %s KB, %s to %s files)" % (min(kbs), max(kbs), min(files), max(files)))
    m = re.search(r"the largest report, (\d+\.\d)KB, held (\d+) files", t)
    if not m or "%sKB, held %s files" % m.groups() not in log:
        problems.append("the largest report's files")
    m = re.search(r"second part was exactly (\d+) files and (\d+\.\d)KB", t)
    if not m or "%s files, and its report is %sKB" % m.groups() not in log_line(log, "Run 10: exit 0") + " " + log:
        problems.append("the full part")
    earlier = [int(n) for l in log.splitlines() if "Run 10: exit 0" not in l for ns in re.findall(r"(\d+), (\d+) and (\d+) files", l) for n in ns]
    if earlier and max(earlier) >= 450:
        problems.append("a part of 450 files before run 10")
    # the fixture
    key = json.loads((EXPENSIVE / "big-sweep-key.json").read_text(encoding="utf-8"))
    for need in ("990 tracked files, 950 after the vendored folder skipped whole, 945 readable, %d planted facts and %d decoys" % (len(key["facts"]), len(key["decoys"])),
                 "holds 610 files"):
        if need not in t:
            problems.append("design lacks %r" % need)
    for need in ("990 tracked files and 950 after the whole-folder skip", "945", "610"):
        if need not in log:
            problems.append("log lacks %r" % need)
    # the harness
    if "1,125 bytes" not in t or "1,125 bytes" not in log:
        problems.append("the launch notice")
    problems += ["not in the log: %s" % f for f in figures_not_in_log(t, log)]
    return problems


class DesignAsBuiltPlacementTest(unittest.TestCase):
    def setUp(self):
        self.text = raw("docs/design.md")

    def test_exactly_one_new_heading_and_it_is_the_last_heading_in_the_file(self):
        self.assertEqual(self.text.count("\n" + AS_BUILT + "\n"), 1)
        _before, sec4, sub = design_parts(self.text)
        self.assertEqual(re.findall(r"^#{1,6} .*$", sub, re.M), [AS_BUILT])
        self.assertTrue(self.text.rstrip().endswith(sub.rstrip()))

    def test_it_comes_after_every_amended_subsection_of_section_4_and_is_the_last_subsection_of_the_file(self):
        # not tied to which amendment is the last one: a later amendment goes above the As built heading and this still holds
        _before, sec4, sub = design_parts(self.text)
        amended = [m.start() for m in re.finditer(r"^### Amended", sec4, re.M)]
        self.assertGreaterEqual(len(amended), 4)
        self.assertEqual(len(re.findall(r"^### Amended", self.text, re.M)), len(re.findall(r"^### Amended", self.text[:self.text.index(AS_BUILT)], re.M)),
                         "an Amended subsection comes after the As built heading")
        # the heading just before As built (inside section 4) is an Amended one, and nothing sits between them but its text
        headings = re.findall(r"^#{1,6} .*$", sec4, re.M)
        self.assertTrue(headings[-1].startswith("### Amended"), headings[-1])
        self.assertEqual(re.findall(r"^#{1,6} .*$", sub, re.M), [AS_BUILT])
        self.assertTrue(self.text.rstrip().endswith(sub.rstrip()))

    def test_the_subsections_of_section_4_run_parts_one_to_eight_then_the_amendments_in_date_order(self):
        # holds over time: it says nothing about how many amendments there are, only how they are laid out
        _before, sec4, _sub = design_parts(self.text)
        subs = re.findall(r"^### (.*)$", sec4, re.M)
        parts = [h for h in subs if h.startswith("Part ")]
        self.assertEqual([h.split(":")[0] for h in parts], ["Part %d" % n for n in range(1, 9)])
        amended = [h for h in subs if h.startswith("Amended ")]
        self.assertEqual(subs, parts + amended, "every Part comes before every Amended subsection")
        dates = [re.match(r"Amended \((\d{4}-\d{2}-\d{2})\): ", h) for h in amended]
        self.assertTrue(all(dates), amended)
        stamps = [m.group(1) for m in dates]
        self.assertEqual(stamps, sorted(stamps), "the amendments are out of date order")

    def test_the_layout_check_sees_an_amendment_moved_out_of_order(self):
        _before, sec4, _sub = design_parts(self.text)
        subs = re.findall(r"^### (.*)$", sec4, re.M)
        amended = [h for h in subs if h.startswith("Amended ")]
        stamps = [re.match(r"Amended \((\d{4}-\d{2}-\d{2})\)", h).group(1) for h in amended]
        self.assertGreater(len(set(stamps)), 1)
        self.assertNotEqual(list(reversed(stamps)), sorted(stamps))

    def test_section_4_holds_no_other_as_built(self):
        _before, sec4, sub = design_parts(self.text)
        self.assertEqual(re.findall(r"^### As built", sec4, re.M), [])
        self.assertEqual(len(re.findall(r"^### As built", self.text, re.M)), 4)
        self.assertEqual(len(re.findall(r"^### As built", sub, re.M)), 1)


# ---------------------------------------------------------------------------------------------------------------
# the review batch's results: runs 13, 14, 15 and the harness run, the fourth head-to-head pass, the smoke, the tally of fifteen

def fifteen_tally(log):
    """(failed, proved, classifier, stopped by me), each a list of run numbers, from the log's 'fifteen loop runs, in one place' line."""
    line = log_line(log, "The fifteen loop runs, in one place")
    m = re.search(r"failed the scorer, (\d+) \(runs (\d+(?:, \d+)*)\); proved as saved, (\d+) \((\d+(?:, \d+)*)\); "
                  r"stopped by a safety classifier at the session's save and not counted, (\d+) \((\d+(?:, \d+)*);.*?\); "
                  r"stopped by me and not used, (\d+) \((\d+, \d+)\)", line)
    assert m, line
    lists = [[int(n) for n in m.group(i).split(", ")] for i in (2, 4, 6, 8)]
    assert [len(l) for l in lists] == [int(m.group(i)) for i in (1, 3, 5, 7)], "the log's own counts don't match its own lists"
    return lists


def tally_problems(text, log, style):
    """What a doc says about the fifteen runs that the log's line doesn't. style 'readme' or 'built' (they word it differently)."""
    failed, proved, classifier, mine = fifteen_tally(log)
    t = fold(text)
    total = len(failed) + len(proved) + len(classifier) + len(mine)
    if style == "readme":
        want = ("%s were started: %s proved, %s failed the scorer, %s were stopped by the classifier (%s), and %s (%s) were stopped by me"
                % (WORDS[total], WORDS[len(proved)], WORDS[len(failed)], WORDS[len(classifier)], joined([str(n) for n in classifier]),
                   WORDS[len(mine)], joined([str(n) for n in mine])))
    else:
        want = ("Of %s headless runs, %s proved (%s), %s failed the scorer (%s), %s were stopped by the classifier (%s) and %s (%s) were stopped by me"
                % (WORDS[total], WORDS[len(proved)], ", ".join(str(n) for n in proved), WORDS[len(failed)], ", ".join(str(n) for n in failed),
                   WORDS[len(classifier)], ", ".join(str(n) for n in classifier), WORDS[len(mine)], ", ".join(str(n) for n in mine)))
    problems = [] if want in t else ["the fifteen-run sentence differs from the log's line: %r" % want]
    for word in re.findall(r"\b(\w+) (?:more )?headless runs", t):
        if word.lower() in WORDS.values() and word.lower() not in ("ten", "fifteen", "three"):
            problems.append("a run count the log's lines don't give: %s headless runs" % word)
    return problems


def new_results_problems(text, log):
    """Everything in the review batch's results (runs 13, 14, 15, the harness run, the smoke, the head-to-head) that the build log doesn't say."""
    t = fold(text)
    problems = []
    m = re.search(r"Run 14 \(([\d,]+) s\): `LOOP PROVED`, (\d+) of (\d+) facts, `readers: 945 of 945, once each`", t)
    line = log_line(log, "Run 14: exit 0")
    if not m or "exit 0, %s s" % m.group(1) not in line or "facts found: %s of %s" % (m.group(2), m.group(3)) not in line or \
            "readers: 945 of 945, once each" not in line or "`LOOP PROVED`" not in line:
        problems.append("run 14")
    m = re.search(r"Runs 13 and 15 \(([\d,]+) s and ([\d,]+) s\) aren't proofs", t)
    if not m or "exit 0, %s s" % m.group(1) not in log_line(log, "Run 13: exit 0") or \
            "exit 0, %s s" % m.group(2) not in log_line(log, "Run 15 (the review batch's text"):
        problems.append("runs 13 and 15")
    for marker in ("Run 13: exit 0", "Run 15 (the review batch's text"):
        if "safety classifier" not in log_line(log, marker) or "`LOOP PROVED`" not in log_line(log, marker):
            problems.append("the log's line for %s no longer says classifier and LOOP PROVED" % marker)
    m = re.search(r"The harness run \(([\d,]+) s, \$([\d.]+), all six graders passed\): `LOOP FAILED`\. Part 1 reported (\w+) files unread", t)
    line = log_line(log, "The harness loop run on the review batch's text, with the corrected guard")
    if not m or "exit 0, %s s, $%s, all six graders passed" % (m.group(1), m.group(2)) not in line or \
            "unread: %d" % {v: k for k, v in WORDS.items()}.get(m.group(3), -1) not in line or "`LOOP FAILED`" not in line:
        problems.append("the harness run")
    m = re.search(r"`nesting-smoke` passed (\d+) of (\d+) graders in (\d+) seconds \(\$([\d.]+)\), and the report is one ordinary report", t)
    line = log_line(log, "Task 8, fourth pass")
    if not m or "`nesting-smoke` exit 0, %s s, $%s, %s of %s graders" % (m.group(3), m.group(4), m.group(1), m.group(2)) not in line:
        problems.append("the smoke")
    m = re.search(r"head-to-head ran 3 times in ([\d,]+) seconds \(\$([\d.]+)\) and scored `BAR MET`\. It found (\d+), (\d+) and (\d+) of (\d+) and made up nothing", t)
    if not m or "3 runs: exit 0, %s s, $%s by the harness" % (m.group(1), m.group(2)) not in line or \
            "found %s, %s and %s of %s, missed 0, 0 and 3, made up 0" % m.groups()[2:] not in line or "`BAR MET`" not in line:
        problems.append("the head-to-head")
    for need in ("the three planted as \"runbook section\" references", "the nine before found 48 of 48", "the first run on this branch to miss a planted fact"):
        if need not in line:
            problems.append("the log's head-to-head line lost %r" % need)
    if "planted as \"runbook section\" ones" not in t or "first run on the branch to miss a planted fact; the nine before found 48 of 48" not in t:
        problems.append("the missed facts")
    problems += ["not in the log: %s" % f for f in figures_not_in_log(t, log)]
    return problems


class ReadmeReviewBatchResultsTest(unittest.TestCase):
    def setUp(self):
        self.log = build_log()
        self.new = readme_new_results(evals_section())

    def test_every_figure_in_the_review_batch_results_is_in_the_build_log(self):
        self.assertEqual(new_results_problems(self.new, self.log), [])

    def test_a_changed_figure_is_seen(self):
        t = fold(self.new)
        for old, new in (("Run 14 (2,793 s)", "Run 14 (2,794 s)"), ("(2,892 s and 3,065 s)", "(2,892 s and 3,066 s)"),
                         ("(2,361 s, $9.58,", "(2,361 s, $9.59,"), ("graders in 50 seconds ($0.39)", "graders in 51 seconds ($0.39)"),
                         ("2,045 seconds ($7.79)", "2,045 seconds ($7.78)"), ("48, 48 and 45 of 48", "48, 48 and 46 of 48"),
                         ("reported three files unread", "reported two files unread"), ("33 of 33 facts", "32 of 33 facts"),
                         ("the nine before found 48 of 48", "the ten before found 48 of 48")):
            with self.subTest(change=new):
                self.assertIn(old, t)
                self.assertNotEqual(new_results_problems(t.replace(old, new, 1), self.log), [])

    def test_the_old_results_sections_are_still_found_and_are_not_the_new_ones(self):
        old = fold(readme_results(evals_section()))
        self.assertIn("Headless 9", old)
        self.assertNotIn("Run 14", old)
        self.assertNotIn("Run 14", fold(readme_results(evals_section())))
        self.assertNotIn("Headless 9", fold(self.new))

    PINS = [
        ("the batch changed every command, so the proofs ran again", "The batch changed every command the model runs, so the proofs ran again on it."),
        ("three headless runs and a harness run", "Three headless runs (13, 14 and 15) and one harness run"),
        ("runs 13 and 15 aren't proofs: a safety classifier stopped the session's write of the last part",
         "Runs 13 and 15 (2,892 s and 3,065 s) aren't proofs. A safety classifier stopped the session's write of the last part"),
        ("the session stopped and said so", "and the session stopped and said so."),
        ("both score LOOP PROVED on the reports as the agent returned them", "Both score `LOOP PROVED` on the reports as the agent returned them."),
        ("the harness run failed on three files a part reported unread",
         "The harness run (2,361 s, $9.58, all six graders passed): `LOOP FAILED`. Part 1 reported three files unread after an area lead summarised its checklist in groups."),
        ("the transcript shows every one was read", "The transcript shows every one of them was read."),
        ("the bar was met once on the batch's text, twice before it",
         "So two headless proofs in a row, the bar the plan set, was met on the text before the batch, and once on the text after it."),
        ("the head-to-head found 45 of 48 in one run and scored BAR MET",
         "The head-to-head ran 3 times in 2,045 seconds ($7.79) and scored `BAR MET`. It found 48, 48 and 45 of 48 and made up nothing."),
        ("what the third run missed", "The third run read every file and left out the three references planted as \"runbook section\" ones."),
        ("the first run on the branch to miss a planted fact", "It's the first run on the branch to miss a planted fact; the nine before found 48 of 48."),
        ("the smoke's brief now says one area as for a repo of more than about 150 files, one report, not a sweep in parts",
         "as for a repo of more than about 150 files, and that it still comes back as one report, not a sweep in parts."),
        ("the smoke report is one ordinary report with no SWEEP IN PARTS block",
         "the report is one ordinary report again: it opens `Mode: full sweep, 1 area lead` and has no `SWEEP IN PARTS` block."),
    ]

    def test_every_pin_holds_and_each_fails_on_deletion(self):
        t = fold(self.new)
        self.assertEqual(missing(t, self.PINS), [])
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(t, phrase), self.PINS), [name])

    def test_the_fifteen_run_sentence_agrees_with_the_logs_line(self):
        self.assertEqual(tally_problems(readme_new_results(evals_section()), self.log, "readme"), [])

    def test_the_readme_scaffold_sentence_says_what_the_guard_does(self):
        PINS = [
            ("refuses a folder that isn't empty, and an empty one inside a repo that has commits",
             "Its scaffold stops with exit 1 in a folder that isn't empty, and in an empty folder inside a repo that has commits, so run it in an empty folder outside any repo."),
            ("an empty folder under an empty repo builds (the harness's workspace)",
             "An empty folder under an empty repo, which is what the harness's workspace is, builds."),
        ]
        t = fold(evals_section())
        self.assertEqual(missing(t, PINS), [])
        for name, phrase in PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(t, phrase), PINS), [name])
        self.assertNotIn("inside a git repo, so run it", t)  # the first guard's sentence


class DesignAsBuiltReviewResultsTest(unittest.TestCase):
    PINS = [
        ("the proofs ran again on the batch", "The review's batch changed every command the model runs, so the proofs ran again on it: three more headless runs (13, 14 and 15) and a harness run."),
        ("runs 13 and 15 aren't proofs: the classifier stopped the session's write of the last part",
         "Runs 13 and 15 (2,892 s and 3,065 s) aren't proofs. A safety classifier stopped the session's write of the last part."),
        ("both score LOOP PROVED on the reports as returned", "Both score `LOOP PROVED` on the reports as the agent returned them."),
        ("the harness run failed on three files a part reported unread",
         "The harness run (2,361 s, $9.58, all six graders passed) is `LOOP FAILED`. Part 1 reported three files unread after an area lead summarised its checklist, though the transcript shows they were read."),
        ("the bar was met once on the batch's text", "So two headless proofs in a row, the plan's bar, was met on the text before the batch and once on the text after it."),
        ("the smoke on the batch: 8 of 8, one ordinary report", "`nesting-smoke` passed 8 of 8 graders (50 s, $0.39), and its report is one ordinary report with no `SWEEP IN PARTS` block."),
        ("the head-to-head found 48, 48 and 45 of 48 and made up nothing", "The head-to-head scored `BAR MET` (2,045 s, $7.79): it found 48, 48 and 45 of 48 and made up nothing."),
        ("what the third run missed", "The third run read every file and left out the three references planted as \"runbook section\" ones."),
        ("the first run on the branch to miss a planted fact", "It's the first run on the branch to miss a planted fact."),
        ("known limit: the classifier stopped the session's save in runs 8, 13 and 15",
         "A safety classifier stopped the eval session's save of a part in three runs (8, 13 and 15). Nothing was retried or worked around."),
        ("known limit: it's the session copying a report into a file, not investigate",
         "It's the session copying a report of about 12KB into a file, not `investigate`, and a session that keeps a part in its own context never makes that write."),
        ("known limit: a lead's checklist comes back as group summaries",
         "An area lead sometimes returns its checklist as group summaries, not a line a file (runs 2 and 3, and the harness run)."),
        ("known limit: the top level then reports files unread that were read, and it's parked",
         "The top level then takes its word or, as in the harness run, reports files unread that were read. It's §1's checklist, not something this branch changed, and it's parked as a follow-up."),
        ("known limit: the scaffold guard's two checks and the harness workspace",
         "The big-sweep scaffold stops in a folder that isn't empty, and in an empty folder inside a repo that has commits. It builds in an empty folder under a repo with no commits, which is the harness's workspace"),
        ("known limit: the other scaffolds have no guard", "The head-to-head's and the smoke's scaffolds have no guard."),
        ("known limit: the smoke's old wording is past, and the report is now ordinary",
         "The smoke's brief once said to read its six files \"exactly as you would above the size limit\", and on that text its report opened with `SWEEP IN PARTS: 0 areas not read`."),
        ("known limit: the brief was reworded and the report is one ordinary report",
         "The brief was reworded (as you would for a repo of more than about 150 files, and it still comes back as one report), and on the new text the report is one ordinary report."),
    ]

    def sub(self):
        return fold(design_parts(raw("docs/design.md"))[2])

    def test_every_pin_holds_and_each_fails_on_deletion(self):
        t = self.sub()
        self.assertEqual(missing(t, self.PINS), [])
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(t, phrase), self.PINS), [name])

    def test_the_fifteen_run_sentence_agrees_with_the_logs_line(self):
        self.assertEqual(tally_problems(design_parts(raw("docs/design.md"))[2], build_log(), "built"), [])

    def test_every_dollar_kb_and_seconds_figure_in_the_subsection_is_in_the_log(self):
        self.assertEqual(figures_not_in_log(self.sub(), build_log()), [])

    def test_the_two_new_known_limits_are_bullets_of_that_list(self):
        sub = design_parts(raw("docs/design.md"))[2]
        limits = sub[sub.index("**Known limits and what's parked.**"):]
        bullets = [fold(b) for b in ("\n" + limits).split("\n- ")[1:]]
        self.assertEqual(len([b for b in bullets if b.startswith("A safety classifier stopped the eval session's save")]), 1)
        self.assertEqual(len([b for b in bullets if b.startswith("An area lead sometimes returns its checklist as group summaries")]), 1)


class FifteenRunTallyTest(unittest.TestCase):
    def setUp(self):
        self.log = build_log()

    def test_the_log_line_says_what_the_task_says(self):
        self.assertEqual(fifteen_tally(self.log), [[1, 2, 3, 7], [4, 5, 6, 9, 10, 14], [8, 13, 15], [11, 12]])

    def test_the_fifteen_are_each_run_once(self):
        failed, proved, classifier, mine = fifteen_tally(self.log)
        self.assertEqual(sorted(failed + proved + classifier + mine), list(range(1, 16)))

    def test_the_ten_run_tally_is_the_fifteen_run_tally_cut_at_run_10_less_the_classifier_run(self):
        failed10, proved10 = log_run_tally(self.log)
        failed, proved, classifier, _mine = fifteen_tally(self.log)
        self.assertEqual(sorted(failed10), sorted(n for n in failed if n <= 10))
        self.assertEqual(sorted(proved10), sorted(n for n in proved if n <= 10))
        self.assertIn(8, classifier)

    def test_the_docs_count_runs_the_way_the_log_does(self):
        self.assertEqual(tally_problems(readme_new_results(evals_section()), self.log, "readme"), [])
        self.assertEqual(tally_problems(design_parts(raw("docs/design.md"))[2], self.log, "built"), [])

    def test_a_doc_that_miscounts_is_seen(self):
        readme = readme_new_results(evals_section())
        built = design_parts(raw("docs/design.md"))[2]
        for old, new in (("six proved", "seven proved"), ("three were stopped by the classifier (8, 13 and 15)", "two were stopped by the classifier (8 and 15)"),
                         ("two (11 and 12)", "two (11 and 13)"), ("fifteen were started", "fourteen were started")):
            with self.subTest(change=new):
                self.assertNotEqual(tally_problems(fold(readme).replace(old, new, 1), self.log, "readme"), [])
        for old, new in (("six proved (4, 5, 6, 9, 10, 14)", "six proved (4, 5, 6, 9, 10, 13)"), ("Of fifteen headless runs", "Of fourteen headless runs"),
                         ("four failed the scorer (1, 2, 3, 7)", "five failed the scorer (1, 2, 3, 7)")):
            with self.subTest(change=new):
                self.assertNotEqual(tally_problems(fold(built).replace(old, new, 1), self.log, "built"), [])
        self.assertNotEqual(tally_problems(fold(readme) + " Twelve headless runs were started.", self.log, "readme"), [])


class ChangelogScaffoldSentenceTest(unittest.TestCase):
    def test_the_unreleased_entry_says_what_the_scaffold_guard_does(self):
        PINS = [("the guard refuses a folder that isn't empty and an empty one inside a repo that has commits",
                 "The big-sweep scaffold and its six copies stop with exit 1 in a folder that isn't empty, and in an empty folder inside a repo that has commits.")]
        entry = fold(ChangelogTest.unreleased(raw("CHANGELOG.md")))
        self.assertEqual(missing(entry, PINS), [])
        self.assertEqual(missing(delete(entry, PINS[0][1]), PINS), [PINS[0][0]])
        self.assertNotIn("inside a git repo.", entry)


class ChangelogReviewBatchTest(unittest.TestCase):
    """The Unreleased entry's bullets for the paths-and-broken-briefs batch, found by content (as the release-proof tests do)."""

    PINS = [
        ("no path typed into a command: a shell variable through a here-document",
         "`investigate` never types a path from the repo into a command: each path goes into a shell variable through a here-document,"),
        ("the listing is git ls-files -z with a line break in a path printed as the byte 001, so every path is one line and no line can end a here-document",
         "`awk` reads it from its environment, and the listing is `git ls-files -z` with a line break in a path printed as the byte `\\001`, so every path is one line and no line of a listing can end a here-document."),
        ("a name with a quote, a backslash, a command substitution or a leading dash can't break or run",
         "A name with a quote, a backslash, `$(…)` or a leading dash can't break the area commands or run as one,"),
        ("a line reading /END is never pasted into a here-document", "and a line reading `/END` is never pasted into a here-document."),
        ("line counts and the block's count take their paths the same way", "Line counts and the block's count take their paths the same way."),
        ("a cut-off CONTINUE SWEEP brief is answered without reading and the block is copied again",
         "A `CONTINUE SWEEP` brief that arrives cut off is answered without reading, and the session copies the block again;"),
        ("an unreadable area line is dropped and quoted; the Read only list replaces any other scope",
         "an area line that can't be read is dropped and quoted in Coverage; a `Read only these files:` list replaces any other scope."),
        ("a report or part with no last line gets the retry", "A report (or part) with no last line"),
        ("the scorer says readers not checked without a transcript", "without one it says `readers: not checked`"),
        ("the big-sweep scaffold and its six copies carry a guard", "The big-sweep scaffold and its six copies"),
    ]

    def entry(self):
        return fold(ChangelogTest.unreleased(raw("CHANGELOG.md")))

    def test_every_pin_holds_in_the_unreleased_entry(self):
        self.assertEqual(missing(self.entry(), self.PINS), [])

    def test_deleting_each_phrase_fails_that_pin_and_only_that_pin(self):
        folded = self.entry()
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(folded, phrase), self.PINS), [name])

    def test_the_two_new_bullets_are_under_changed_and_the_guard_is_mentioned_under_added(self):
        text = ChangelogTest.unreleased(raw("CHANGELOG.md"))
        changed, added = text.index("### Changed"), text.index("### Added")
        for phrase in ("never types a path from the repo", "arrives cut off is answered without reading"):
            with self.subTest(phrase=phrase):
                self.assertGreater(text.index(phrase), changed)
        self.assertGreater(text.index("The big-sweep scaffold"), min(changed, added))
        self.assertRegex(fold(text), r"(?i)scaffold.{0,80}(?:stop|refus).{0,60}(?:exit 1|empty)")  # loosely: a docs follow-up rewords how


class EvalsReadmeReviewBatchTest(unittest.TestCase):
    PINS = [
        ("the parts say unread and failed are 0 and their numbers add up", "that the parts say unread and failed are 0 and their"),
        ("without a transcript the summary says readers not checked",
         "Without `--transcript` the summary says `readers: not checked`, and the read numbers are the parts' own."),
        ("the scorer lists as the agent lists them, a line break in a path as 001",
         "every tracked file (listed as the agent lists them, a line break in a path as `\\001`)"),
    ]

    def text(self):
        return fold(raw("evals/README.md"))

    def test_pins_hold_and_each_fails_on_deletion(self):
        self.assertEqual(missing(self.text(), self.PINS), [])
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(self.text(), phrase), self.PINS), [name])

    def test_the_readme_says_the_big_sweep_scaffold_guards_where_it_runs_without_pinning_how(self):
        # seen: "Its scaffold stops with exit 1 inside a git repo, so run it in an empty folder outside any repo." (before fix round 2)
        self.assertRegex(self.text(), r"(?i)scaffold.{0,60}(?:stops|refuses).{0,200}empty folder")


class DesignAsBuiltReviewBatchTest(unittest.TestCase):
    PINS = [
        ("the proof says readers not checked without a transcript",
         "Without a transcript the summary says `readers: not checked`, and the read numbers are the parts' own."),
        ("every tracked file outside the skipped folder is in exactly one area", "that every tracked file outside the folder skipped whole is in exactly one area"),
        ("call: the here-document delimiter starts with a slash", "has a delimiter that starts with `/`."),
        ("call: a word delimiter is closed early by a root file of that name", "A word such as `END` is closed early by a root file of that name"),
        ("call: each use is guarded with colon-question-mark", "so an empty or unset variable stops the command where `awk` would match every file."),
        ("call: the uniq pipeline needed a guard in front", "swallowed the stop (the shell's error, exit 0, nothing listed), so a guard,"),
        ("call: the listing maps a line break to 001, so every path is one line",
         "The listing is `git ls-files -z | tr '\\n\\0' '\\001\\n'`: git quotes a path with a backslash or a double quote even with `core.quotepath` off, `-z` never quotes, and a line break in a path becomes `\\001`, so every path is one line. On the 990-file repo it's byte for byte the old listing."),
        ("call: the exactly-once check sorts the listing side because 001 sorts before a tab",
         "The exactly-once check sorts the listing side as well, since `\\001` sorts before a tab and a listing with control characters can be out of byte order."),
        ("second review: a path with a line break and /END closed the here-document and the next line ran",
         "A second review, of the fix itself, found that a path with a line break and `/END` in it closed the here-document a path is pasted into, and the next line ran."),
        ("second review: reproduced in both shells, a planted file was created", "It was reproduced in both shells: a planted file was created."),
        ("second review: the listing maps the line break to 001 and a line reading /END is never pasted",
         "The listing now maps the line break to `\\001`, and a line reading `/END` is never pasted."),
        ("second review: why the first fix's tests missed it", "The first fix's tests had a line-break path whose fragment didn't start with `/`, which is why they missed it."),
        ("second review: shipped on its tests and the gate with no new runs, the runs of record are on the text before it",
         "By the owner's choice (\"Narrow fix, ship\") that last fix was shipped on its tests and the gate, with no new loop, head-to-head or smoke run. The runs of record are on the text before it."),
        ("known limits: a line-break path lists as one line with 001 and a repo holding both names lists them twice",
         "A path with a line break lists as one line with `\\001` in its place and is reported unread; a repo holding both names lists them as one line twice."),
        ("known limits: a control character shows as nothing, so the folder can't be typed to skip it and can stall the first run's check",
         "A control character shows as nothing in what the model reads, so a top-level folder with one in its name looks ordinary, can't be typed to skip it, and can stall the first run's check, which fails closed."),
        ("known limits: what the second review left parked",
         "The second review left these parked, in the build log's Parked list: the scaffold and an inherited `GIT_DIR`; a continuing brief with `END OF BLOCK` twice, an area line twice or no readable area line; the session's count check failing twice; a top-level folder that appears between parts."),
        ("call: line counts through tr and xargs or a here-document, and the block's count between wc -l and the delimiter",
         "Line counts take their paths from a listing piped through `tr '\\n' '\\0' | xargs -0 wc -l --`, or from a here-document, and the block's count from the area lines pasted between `wc -l <<'/END'` and `/END`."),
        ("call: a reported name is looked up with the Grep tool", "A reported name is looked up with the Grep tool, since a `grep` with the name typed in has the same hole."),
        ("call: the scorer says readers not checked and keeps its verdict words", "The scorer says `readers: not checked` without a transcript and keeps its verdict words and exit codes"),
        ("review paragraph: found by an independent review before release", "An independent review before release found that the area commands had the model type repo paths between quotes."),
        ("review paragraph: shown by running three cases", "It was shown by running: a folder named to close the quote ran a planted command, `bob's notes/` was a syntax error, and a path with a backslash matched nothing."),
        ("review paragraph: no run had hit it", "No run of the loop had hit it, because the test repo has no such names."),
        ("known limits: a path with a backtick or a control character is covered by a parent piece", "A path with a backtick or a control character can't be written in an area line, so it is covered by a parent piece"),
    ]

    def sub(self):
        return fold(design_parts(raw("docs/design.md"))[2])

    def test_every_pin_holds_in_the_subsection(self):
        self.assertEqual(missing(self.sub(), self.PINS), [])

    def test_deleting_each_phrase_fails_that_pin_and_only_that_pin(self):
        folded = self.sub()
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(folded, phrase), self.PINS), [name])

    def test_the_seven_new_calls_are_lines_of_the_calls_made_list(self):
        sub = design_parts(raw("docs/design.md"))[2]
        calls = sub[sub.index("**Calls made during the build**"):]
        bullets = ["- " + b for b in ("\n" + calls).split("\n- ")[1:]]
        mine = [b for b in bullets if fold(b)[2:].startswith(("The three-line here-document", "Each use is", "The listing is", "The exactly-once check sorts",
                                                          "Line counts take", "A reported name", "The scorer says"))]
        self.assertEqual(len(mine), 7)

    def test_the_subsection_mentions_the_scaffold_guard_without_pinning_how(self):
        # seen: "The big-sweep scaffold stops inside a repo; the head-to-head's and the smoke's don't." (before fix round 2)
        t = self.sub()
        self.assertRegex(t, r"(?i)big-sweep scaffold (?:stops|refuses)")
        self.assertIn("head-to-head", t[t.index("big-sweep scaffold"):])


class DesignAsBuiltFiguresTest(unittest.TestCase):
    def setUp(self):
        self.log = build_log()
        _b, _s, self.sub = design_parts(raw("docs/design.md"))

    def test_every_figure_in_the_subsection_is_in_the_build_log(self):
        self.assertEqual(as_built_problems(self.sub, self.log), [])

    def test_the_table_has_seven_rows_and_each_is_the_logs(self):
        rows = re.findall(r"^\| (\d+) \| (plain|full paths) \| ", self.sub, re.M)
        self.assertEqual(len(rows), 7)
        self.assertEqual(len(log_table(self.log)), 7)

    def test_a_changed_figure_is_seen(self):
        for old, new in (("| 150 | plain | 11.0KB | 425 |", "| 150 | plain | 11.0KB | 426 |"),
                         ("| 645 | full paths | 27.3KB | 1,840 |", "| 645 | full paths | 27.3KB | 1,841 |"),
                         ("866 s and\n$3.39", "866 s and\n$3.38"), ("1,157 s and $6.07", "1,157 s and $6.08"),
                         ("about 19.5KB after 2,222 s", "about 19.5KB after 2,223 s"),
                         ("(412, 366 and 172 files; then 404, 450 and 96)", "(412, 366 and 173 files; then 404, 450 and 96)"),
                         ("in 2,992 s and\n2,974 s", "in 2,992 s and\n2,975 s"), ("2,541 s and $9.80", "2,541 s and $9.81"),
                         ("(368, 366 and 216 files)", "(368, 366 and 217 files)"),
                         ("Of the other nine, four failed the scorer and five proved", "Of the other nine, five failed the scorer and four proved"),
                         ("It took ten headless runs", "It took nine headless runs"),
                         ("(59 s,\n$0.42)", "(59 s,\n$0.43)"), ("(2,004 s, $7.50)", "(2,004 s, $7.51)"),
                         ("7.6KB to 29.1KB for\n96 to 450 files", "7.6KB to 29.1KB for\n97 to 450 files"),
                         ("the largest report, 29.1KB, held 340 files", "the largest report, 29.1KB, held 341 files"),
                         ("exactly 450\nfiles and 15.9KB", "exactly 450\nfiles and 15.8KB"),
                         ("on Sonnet the same repo gave 17KB to\n27KB", "on Sonnet the same repo gave 17KB to\n28KB"),
                         ("found 48 of 48 in all three runs", "found 47 of 48 in all three runs")):
            with self.subTest(change=new):
                folded = fold(self.sub)
                self.assertIn(fold(old), folded, old)
                mutated = folded.replace(fold(old), fold(new), 1)
                # the table is read line by line, so a table edit is made on the unfolded text
                if old.startswith("|"):
                    mutated = self.sub.replace(old, new, 1)
                self.assertNotEqual(as_built_problems(mutated, self.log), [])

    PINS = [
        ("it replaces the stop", "This section replaces §1 Part 6 (the stop) and the rulings about the stop in §1's \"As built\"."),
        ("the owner chose 450", "so the number went to the owner, who chose 450 over 300 and 600."),
        ("run 8 isn't counted", "Run 8 was stopped by a safety classifier while the session saved part 2, and isn't counted."),
        ("the head-to-head missed once", "One of the three passes run during the build scored `BAR MISSED`"),
        ("why it missed", "`compare.py` read `fxctl X`, a placeholder inside a quoted docstring, as a made-up command."),
        ("the scorer was left alone and the final pass met the bar", "The scorer wasn't changed, and the pass on the final text met the bar."),
        ("a part can reach the preview range", "A full part of dense files can still land where previews start"),
        ("the 22KB was an estimate",
         "The part-size amendment's \"about 22KB\" for 450 files was my estimate, not a measurement, and the amendment was corrected on 2026-11-24."),
        ("ten runs and three fix batches",
         "It took ten headless runs and three fix batches, besides the final review's, to get two proofs in a row on one text."),
        ("the 53.7KB was the Haiku arm", "The 53.7KB the design started from came from the one arm with `investigate` on Haiku"),
        ("every failure was a format or a number", "Every failure was a line's format or a number in a report; none was a file left unread or a sweep that stopped"),
        ("the part size closed at 450", "The part size is closed: 450."),
        ("the owner's own instructions are updated on shipping",
         "is updated when this ships (owner decision 2A), not by this branch."),
    ]

    def test_every_phrase_pin_holds(self):
        self.assertEqual(missing(fold(self.sub), self.PINS), [])

    def test_deleting_each_phrase_fails_that_pin_and_only_that_pin(self):
        folded = fold(self.sub)
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(folded, phrase), self.PINS), [name])


class DesignAsBuiltScannerAndCostTest(unittest.TestCase):
    # built from pieces so this file never spells out what it's looking for (as tests/test_structure.py does)
    EVAL, BT, ICON = "ev" + "al", chr(96), "icon" + ".png"
    ENV = re.escape("os." + "env" + "iron")
    PATTERNS = {
        "the e-v-a-l word right before a backtick": re.compile(EVAL + BT),
        "a line starting with the p-a-s-s word": re.compile(r"^[ \t]*" + "pa" + r"ss([ \t]|$)", re.M),
        "an n-p-x download-and-run command": re.compile("np" + r"x\s+@?[\w.-]"),
        "the whole environment passed along": re.compile(r"\*\*" + ENV + "|dict\\(" + ENV + "\\)|" + ENV + r"\.copy\(\)"),
        "an environment variable read by a computed name": re.compile(ENV + r"\[(?![\"'])"),
        "the icon's file name": re.compile(re.escape(ICON)),
    }
    ASK = re.compile(r"(?i)\b(?:ask|asks|asking|confirm|confirms|approval|approve|permission|ok|okay|go-ahead|wait|waits|hold back|stop and)\b")
    COST = re.compile(r"(?i)\b(?:cost|costs|costing|price|priced|pricing|spend|spending|budget|expensive)\b|\$\d")
    FORBIDS = re.compile(r"(?i)\bno longer\b|\bnever\b|\bnobody\b|\bwithout\b|\bdon't\b|\bdoesn't\b")

    @classmethod
    def scanner_hits(cls, text):
        text = text.replace(chr(92), "")
        return [why for why, p in cls.PATTERNS.items() if p.search(text)]

    @classmethod
    def cost_gates(cls, text):
        """Sentences that pair an asking or waiting word with a cost word and don't forbid it."""
        out = []
        for sentence in re.split(r"(?<=[.!?:])\s+(?=[A-Z`])", fold(text)):
            if cls.ASK.search(sentence) and cls.COST.search(sentence) and not cls.FORBIDS.search(sentence):
                out.append(sentence)
        return out

    def setUp(self):
        _b, _s, self.sub = design_parts(raw("docs/design.md"))

    def test_the_subsection_has_none_of_the_text_the_directory_scanner_flagged(self):
        self.assertEqual(self.scanner_hits(self.sub), [])

    def test_the_eval_command_is_written_with_the_dot_wherever_it_appears(self):
        self.assertEqual(re.findall(r"claude plugin eval(?! \.)", self.sub), [])

    def test_the_subsection_has_no_cost_gate(self):
        self.assertEqual(self.cost_gates(self.sub), [])

    def test_measured_figures_stated_as_facts_are_not_gates(self):
        self.assertEqual(self.cost_gates("The harness ran it twice: `reply-size-320` took 866 s and $3.39, both whole."), [])
        self.assertEqual(self.cost_gates("`investigate` no longer stops, quotes a cost or has the session ask."), [])

    def test_the_checks_see_what_they_should(self):
        for bad in ("Run `claude plugin " + self.EVAL + self.BT + " first.", "\n    " + "pa" + "ss\n", "icon" + ".png", "np" + "x -y thing"):
            with self.subTest(bad=bad):
                self.assertNotEqual(self.scanner_hits(bad), [])
        for bad in ("Ask the user before a sweep that costs more than $5.", "Get an OK first, since a full sweep costs about $9.",
                    "Wait for approval when the run is expensive.", "Hold back if the price is high."):
            with self.subTest(bad=bad):
                self.assertNotEqual(self.cost_gates(bad), [])
        self.assertNotEqual(self.cost_gates(self.sub + " Ask the user before a run that costs more than $5."), [])

    def test_the_stop_is_said_to_be_replaced_without_a_leftover_gate(self):
        self.assertNotIn("above 500", self.sub)
        self.assertNotIn("500-file", self.sub)
        self.assertEqual(len(re.findall(r"STOPPED BEFORE READING", self.sub)), 1)  # only the owner's own instructions line


class NoTestReadsTheDesignForSplitTokensTest(unittest.TestCase):
    """The docs agent noted SWEEP IN / PARTS split across two lines in design text that predates this batch."""

    def test_the_old_split_is_still_there_and_is_outside_the_new_subsection(self):
        text = raw("docs/design.md")
        _b, sec4, sub = design_parts(text)
        split = [m.start() for m in re.finditer(r"SWEEP\s+IN\s+PARTS", text) if "SWEEP IN PARTS" not in text[m.start(): m.end()]]
        self.assertEqual(SplitTokenTest.split(sub), [])
        for i in split:
            self.assertLess(i, len(text) - len(sub), "a split token inside the new subsection")


if __name__ == "__main__":
    unittest.main()
