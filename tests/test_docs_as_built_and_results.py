"""What is left of the docs batch after the qa pass, and after the pins on history were cut.

Kept: the checks that read a figure, a command or a flag out of a doc and look for it in another file (the build
log, the scripts, the plan's own table) without retyping it; the harness and live commands in evals/README.md; the
README and PRIVACY script lists; the scoped retry in docs/orchestrator.md; the CHANGELOG comparison with main; the
layout of design section 4; the scanner check on the design's "As built" subsection; the tally of the fifteen runs
against the log. The sentences of the history itself (the results prose, the "As built" subsection, the changelog
entry, the build log) are no longer pinned: HistorySectionsTest only checks that each is found and holds something.

Each check is a function of the text it is given, so a test can change one figure and see the check notice. Git
comparisons skip when git, HEAD or main isn't there.

Standard library only. No model session is started.
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPENSIVE = ROOT / "evals-expensive"
PLAN = "docs/plans/2026-11-23-big-sweep-in-parts.md"
AS_BUILT = "### As built (2026-11-24)"


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


class ReadmeResultsAgreeWithTheBuildLogTest(unittest.TestCase):
    def setUp(self):
        self.log = build_log()
        self.section = evals_section()

    def test_every_dollar_kb_and_seconds_figure_in_the_whole_section_is_in_the_log_and_not_only_in_the_plan_header(self):
        self.assertEqual(figures_not_in_log(fold(self.section), self.log), [])

    def test_a_figure_that_is_only_the_tail_of_another_is_not_found(self):
        self.assertEqual(figures_not_in_log("a 6KB report and $9.80 and 2,992 s", "a 56KB reply, $9.80, 12,992 s"), ["6KB", "2,992 s"])
        self.assertEqual(figures_not_in_log("a 56KB report", "a 56KB reply"), [])


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

    def test_the_evals_readme_scorer_bullet_says_nothing_about_asking(self):
        bullet = re.search(r"(?ms)^- `check_parts\.py --key.*?(?=^\*\*|\Z)", evals_section()).group(0)
        self.assertNotRegex(bullet, r"(?i)\bask")


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
    }

    @classmethod
    def split(cls, text):
        """Tokens that appear with a line break (or a doubled space) inside them."""
        bad = []
        for token, loose in cls.LOOSE.items():
            if len(re.findall(loose, text)) != len(re.findall(re.escape(token), text)):
                bad.append(token)
        return bad


    def test_no_fixed_token_is_split_in_the_docs_or_the_new_design_subsection(self):
        for rel in ("README.md", "docs/orchestrator.md", "evals/README.md", "CONTRIBUTING.md", "PRIVACY.md", "CHANGELOG.md"):
            with self.subTest(file=rel):
                self.assertEqual(self.split(raw(rel)), [])

    def test_the_checker_sees_a_wrapped_counts_line_and_label(self):
        self.assertEqual(self.split("`Files listed: <n>; read: <n>; skipped: <n>;\nre-dispatched: <n>; failed: <n>; unread: <n>`"),
                         ["Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>"])
        self.assertEqual(self.split("the `Whole\nrepo:` line"), ["Whole repo:"])
        self.assertEqual(self.split("`Areas not\nread:`"), ["Areas not read:"])
        self.assertEqual(self.split("SWEEP IN\nPARTS: <n> files not read"), ["SWEEP IN PARTS: <n> files not read"])
        self.assertEqual(self.split("`Whole repo:` and `Areas read:` and `Areas not read:`"), [])


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
        return set(re.findall(r"evals(?:-expensive)?/([a-z][a-z_]+)\.py", fold(raw("PRIVACY.md"))))

    def on_disk(self):
        return {p.stem for p in EXPENSIVE.glob("*.py")} | {p.stem for p in (ROOT / "evals").glob("*.py")}

    def test_the_readme_names_all_six_scripts_and_each_exists(self):
        self.assertEqual(len(self.readme_scripts()), 6)
        for name in self.readme_scripts():
            with self.subTest(script=name):
                self.assertTrue((EXPENSIVE / (name + ".py")).is_file() or (ROOT / "evals" / (name + ".py")).is_file())

    def test_the_readme_and_privacy_name_the_same_scripts(self):
        self.assertEqual(self.readme_scripts(), self.privacy_scripts())

    def test_both_name_every_script_in_evals_and_evals_expensive(self):
        self.assertEqual(self.on_disk(), self.readme_scripts())
        self.assertEqual(self.on_disk(), self.privacy_scripts())
        self.assertEqual(self.on_disk(), {"compare", "sync_case", "sync_big_sweep", "check_parts", "measure_reply", "scorecard"})

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
            folder = EXPENSIVE if (EXPENSIVE / (name + ".py")).is_file() else ROOT / "evals"
            src = (folder / (name + ".py")).read_text(encoding="utf-8")
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
    """(text before section 4, section 4 up to the As built heading, the As built subsection or '').

    The As built subsection runs to the next top-level section (a line starting "## "), or to the end of the file."""
    start = re.search(r"^## 4\. ", text, re.M).start()
    i = text.find(AS_BUILT)
    if i < 0:
        return text[:start], text[start:], ""
    nxt = re.compile(r"^## ", re.M).search(text, i)
    return text[:start], text[start:i], text[i: nxt.start() if nxt else len(text)]


class DesignAsBuiltPlacementTest(unittest.TestCase):
    def setUp(self):
        self.text = raw("docs/design.md")

    def test_exactly_one_new_heading_and_it_is_the_last_heading_in_section_4(self):
        self.assertEqual(self.text.count("\n" + AS_BUILT + "\n"), 1)
        _before, sec4, sub = design_parts(self.text)
        self.assertEqual(re.findall(r"^#{1,6} .*$", sub, re.M), [AS_BUILT])
        self.assertNotRegex(sub, r"(?m)^## ")

    def test_it_comes_after_every_amended_subsection_of_section_4_and_is_the_last_subsection_of_section_4(self):
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
        self.assertNotRegex(sub, r"(?m)^## ")

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


def as_built_table(sub):
    """The measurement table of the As built subsection: (files, brief) -> (KB, seconds), read line by line."""
    rows = {}
    for m in re.finditer(r"^\| (\d+) \| (plain|full paths) \| ([\d.]+)KB \| ([\d,]+) \|", sub, re.M):
        rows[(m.group(1), m.group(2))] = (m.group(3), m.group(4))
    return rows


class DesignAsBuiltFiguresTest(unittest.TestCase):
    def setUp(self):
        self.log = build_log()
        _b, _s, self.sub = design_parts(raw("docs/design.md"))

    def test_the_table_has_seven_rows_and_each_is_the_logs(self):
        rows = as_built_table(self.sub)
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows, log_table(self.log))

    def test_a_changed_table_row_is_seen(self):
        rows = as_built_table(self.sub)
        self.assertEqual(len(rows), 7)
        for (files, brief), (kb, secs) in sorted(rows.items()):
            row = "| %s | %s | %sKB | %s |" % (files, brief, kb, secs)
            self.assertEqual(self.sub.count(row), 1, row)
            with self.subTest(row=row, change="seconds"):
                bumped = "{:,}".format(int(secs.replace(",", "")) + 1)
                self.assertNotEqual(as_built_table(self.sub.replace(row, row.replace("| %s |" % secs, "| %s |" % bumped))), log_table(self.log))
            with self.subTest(row=row, change="report size"):
                self.assertNotEqual(as_built_table(self.sub.replace(row, row.replace("%sKB" % kb, "%.1fKB" % (float(kb) + 0.1)))), log_table(self.log))
            with self.subTest(row=row, change="row dropped"):
                self.assertNotEqual(as_built_table(self.sub.replace(row, "")), log_table(self.log))


# ---------------------------------------------------------------------------------------------------------------
# the tally of the fifteen runs, against the build log's own line

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


class DesignAsBuiltReviewResultsTest(unittest.TestCase):

    def sub(self):
        return fold(design_parts(raw("docs/design.md"))[2])

    def test_every_dollar_kb_and_seconds_figure_in_the_subsection_is_in_the_log(self):
        self.assertEqual(figures_not_in_log(self.sub(), build_log()), [])


class FifteenRunTallyTest(unittest.TestCase):
    def setUp(self):
        self.log = build_log()

    def test_the_fifteen_are_each_run_once(self):
        failed, proved, classifier, mine = fifteen_tally(self.log)
        self.assertEqual(sorted(failed + proved + classifier + mine), list(range(1, 16)))

    def test_the_ten_run_tally_is_the_fifteen_run_tally_cut_at_run_10_less_the_classifier_run(self):
        failed10, proved10 = log_run_tally(self.log)
        failed, proved, classifier, _mine = fifteen_tally(self.log)
        self.assertEqual(sorted(failed10), sorted(n for n in failed if n <= 10))
        self.assertEqual(sorted(proved10), sorted(n for n in proved if n <= 10))
        self.assertIn(8, classifier)


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

    @classmethod
    def scanner_hits(cls, text):
        text = text.replace(chr(92), "")
        return [why for why, p in cls.PATTERNS.items() if p.search(text)]

    def setUp(self):
        _b, _s, self.sub = design_parts(raw("docs/design.md"))

    def test_the_subsection_has_none_of_the_text_the_directory_scanner_flagged(self):
        self.assertEqual(self.scanner_hits(self.sub), [])

    def test_the_eval_command_is_written_with_the_dot_wherever_it_appears(self):
        self.assertEqual(re.findall(r"claude plugin eval(?! \.)", self.sub), [])

    def test_the_checks_see_what_they_should(self):
        for bad in ("Run `claude plugin " + self.EVAL + self.BT + " first.", "\n    " + "pa" + "ss\n", "icon" + ".png", "np" + "x -y thing"):
            with self.subTest(bad=bad):
                self.assertNotEqual(self.scanner_hits(bad), [])


class HistorySectionsTest(unittest.TestCase):
    """The history this file used to pin sentence by sentence is still where it was, and not empty. Each section is
    found by its heading or its locator, holds more than 200 characters once whitespace is folded, and (the changelog
    entry excepted) holds at least one dollar, KB or seconds figure."""

    SECTIONS = (
        ("the results in evals/README.md, under its big-repo heading", evals_section, True),
        ("the As built subsection of docs/design.md", lambda: design_parts(raw("docs/design.md"))[2], True),
        ("the changelog entry for this work, found by ChangelogTest's locator", lambda: ChangelogTest.unreleased(raw("CHANGELOG.md")), False),
        ("the build log of the plan", build_log, True),
    )

    def test_each_history_section_is_there_and_not_empty(self):
        for name, load, has_figures in self.SECTIONS:
            with self.subTest(section=name):
                try:
                    text = fold(load())
                except (ValueError, AssertionError, AttributeError) as error:
                    self.fail("%s is gone or its heading or locator changed (%s)" % (name, type(error).__name__))
                self.assertGreater(len(text), 200, "%s is empty or nearly: %d characters" % (name, len(text)))
                if has_figures:
                    self.assertIsNotNone(FIGURE.search(text), "%s holds no dollar, KB or seconds figure" % name)


if __name__ == "__main__":
    unittest.main()
