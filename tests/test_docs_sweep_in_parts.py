"""Task 10: the docs say what `investigate` now does (a big repo is read in parts, no stop, no asking).

Pins, each with a deletion mutation, for docs/orchestrator.md, README.md, CHANGELOG.md, evals/README.md,
CONTRIBUTING.md and PRIVACY.md. Phrase pins fold whitespace, so a re-wrap passes and a deleted sentence fails.
A pin table is a list of (name, phrase); the mutation test deletes each phrase from the folded text and
checks that exactly that pin reports missing. Numbers that must agree with another file (the part size, the
measured figures, the flags and pass words of the scripts) are read out of that file, never retyped here.
The 2.2.0 CHANGELOG entry is compared with git's HEAD and skipped when git or HEAD isn't there.

Standard library only. No model session is started.
"""
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPENSIVE = ROOT / "evals-expensive"

# rules item 9: the fixed tokens, each on one line wherever it appears
TOKENS = [
    "SWEEP IN PARTS: <n> areas not read",
    "SWEEP IN PARTS: <n> files not read",
    "CONTINUE SWEEP",
    "END OF BLOCK",
    "INVESTIGATE REPORT ENDS",
    "AREA REPORT ENDS",
    "Areas not read:",
    "Areas read:",
    "Whole repo:",
    "Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>",
]
DOCS = ["README.md", "docs/orchestrator.md", "evals/README.md", "CONTRIBUTING.md", "PRIVACY.md", "CHANGELOG.md"]


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


def part_size():
    m = re.search(r"The part size is (\d[\d,]*) files", raw("agents/investigate.md"))
    assert m, "agents/investigate.md no longer states the part size"
    return m.group(1).replace(",", "")


class PinTable(object):
    """Mixin: self.PINS, self.text() and the two generic tests."""

    def test_every_pin_holds_on_the_file_as_it_is(self):
        self.assertEqual(missing(fold(self.text()), self.PINS), [])

    def test_deleting_each_phrase_fails_that_pin_and_only_that_pin(self):
        folded = fold(self.text())
        for name, phrase in self.PINS:
            with self.subTest(pin=name):
                self.assertEqual(missing(delete(folded, phrase), self.PINS), [name])


class OrchestratorLoopTest(PinTable, unittest.TestCase):
    """docs/orchestrator.md carries design Part 6: the loop, the scoped form, the retry, the preview, the parts."""

    def text(self):
        return raw("docs/orchestrator.md")

    PINS = [
        ("never stops to ask", "It never stops to ask, at any size."),
        ("loop sends CONTINUE SWEEP first, then Project: to END OF BLOCK, copied as it stands",
         "The brief is `CONTINUE SWEEP` on its first line, then every line from `Project:` to `END OF BLOCK` in the report, copied as it stands."),
        ("loop does not ask the user", "Don't ask the user."),
        ("one run at a time", "Wait for it before anything else that starts agents."),
        ("loop ends on 0 areas", "Stop when a report says `SWEEP IN PARTS: 0 areas not read`."),
        ("then tells the user it was read in parts", "Then tell the user the repo was read in parts, how many, and anything a part named as unread."),
        ("the loop runs while the line isn't the 0 one", "While that line isn't the `0` one:"),
        ("scoped form line", "`SWEEP IN PARTS: <n> files not read`"),
        ("scoped form resends the original brief with the paths",
         "Send the original brief again, with \"Read only these files:\" and the unread paths from its Coverage."),
        ("scoped loop ends when the line is gone", "The loop ends when a report has no such line."),
        ("every report ends with its last line", "Every `investigate` report ends with `INVESTIGATE REPORT ENDS`."),
        ("retry: no SWEEP IN PARTS line on a continuing brief",
         "that has no `SWEEP IN PARTS` line when the brief was a `CONTINUE SWEEP` one"),
        ("retry: same areas again", "or that names the same areas unread that its brief gave it, gets the same brief once more."),
        ("then stop and report", "If that fails too, stop the sweep and tell the user which areas are unread;"),
        ("the block is copied from the full text, never a preview, nothing added, fixed or dropped, and its area lines counted",
         "Copy it from the report's full text, never from a preview, add, fix or drop nothing, and check it holds as many area lines as the `<n>` on the report's `SWEEP IN PARTS` line."),
        ("the end-of-sweep summary includes every Area dropped and Count changed line",
         "That includes every `Area dropped:` and `Count changed:` line."),
        ("the scoped list replaces any file list or scope the original brief gave",
         "That list replaces any file list or scope the original brief gave."),
        ("a report without its last line was cut off, whatever its kind, and is never passed on as complete",
         "One that doesn't was cut off, whatever kind of report it is, and is never passed on as complete."),
        ("one report that came back cut off twice is told to the user",
         "for one report, tell the user it came back cut off twice."),
        ("the block is copied afresh from the previous part's full text before the retry",
         "Send a `CONTINUE SWEEP` brief again copied afresh from the previous part's full text (its saved file, if that part arrived as a preview)"),
        ("preview: read the saved file", "read the saved file, which is the report."),
        ("preview: unreadable means stop and say so",
         "If it can't be read, stop the sweep and tell the user that reports this size can't be handed back here."),
        ("preview: no resend, preview isn't the report",
         "Don't send the same brief again, and don't treat the preview as the report."),
        ("a line per part", "Keep one line per part saying which areas it covers"),
        ("parts may be saved outside the tracked tree", "You may save the parts to files outside the tracked tree and hand over paths"),
        ("notes: read the saved output, not the preview", "**Read the saved output, not the preview.**"),
        ("notes: the block is in the file", "the block and the rest of the report are in the file"),
    ]

    def region(self):
        t = fold(self.text())
        return t[t.index("Unfamiliar codebase or post-context-gap"): t.index("New feature or project with open choices")]

    ASKS = (r"(?i)ask(?:s|ing)? (?:the user|you|them|the owner)(?! to)|get (?:the user's|an?|their) (?:ok|okay|approval|go-ahead)"
            r"|wait(?:s|ing)? for (?:the user|an? (?:answer|ok|okay|approval|yes))|confirm with the user|check with the user")

    def test_no_stop_token_anywhere_in_the_orchestrator_notes(self):
        self.assertNotIn("STOPPED BEFORE READING", self.text())

    def test_the_investigate_routing_text_never_tells_the_session_to_ask_before_or_between_parts(self):
        region = self.region()
        for m in re.finditer(self.ASKS, region):
            # the only asking words allowed are the ones that forbid it
            self.assertTrue(region[max(0, m.start() - 6): m.start()].lower().endswith("don't "), region[m.start() - 40: m.end() + 40])
        # and the saved-output paragraph
        t = fold(self.text())
        para = t[t.index("**Read the saved output, not the preview.**"): t.index("**Don't re-run investigate out of habit.**")]
        self.assertIsNone(re.search(self.ASKS, para), para)

    def test_an_asking_sentence_added_to_the_loop_is_caught_by_the_forbidden_pattern(self):
        for bad in ("Ask the user before the next part.", "Wait for the user's okay between parts.",
                    "Get an OK from the user before you send CONTINUE SWEEP.", "Confirm with the user first."):
            with self.subTest(bad=bad):
                self.assertIsNotNone(re.search(self.ASKS, bad))

    def test_a_stop_token_put_back_is_seen_by_the_orchestrator_check(self):
        self.assertIn("STOPPED BEFORE READING", self.text() + "\nIf it replies `STOPPED BEFORE READING`, ask the user.")


class FixedTokensTest(unittest.TestCase):
    """Rules item 9: the fixed tokens are spelled as in the rule and none is split across two lines."""

    LOOSE = {
        "SWEEP IN PARTS": r"SWEEP\s+IN\s+PARTS",
        "CONTINUE SWEEP": r"CONTINUE\s+SWEEP",
        "END OF BLOCK": r"END\s+OF\s+BLOCK",
        "INVESTIGATE REPORT ENDS": r"INVESTIGATE\s+REPORT\s+ENDS",
        "AREA REPORT ENDS": r"AREA\s+REPORT\s+ENDS",
        "STOPPED BEFORE READING": r"STOPPED\s+BEFORE\s+READING",
    }

    def bad_spellings(self, text, name):
        """Occurrences of the token that aren't spelled exactly, on one line."""
        exact = len(re.findall(re.escape(name), text))
        loose = len(re.findall(self.LOOSE[name], text))
        return loose - exact

    def test_no_token_is_split_across_lines_or_respelled_in_the_docs(self):
        for rel in DOCS:
            text = raw(rel)
            for name in self.LOOSE:
                with self.subTest(file=rel, token=name):
                    self.assertEqual(self.bad_spellings(text, name), 0)

    def test_every_sweep_in_parts_line_in_the_docs_has_one_of_the_fixed_shapes(self):
        shape = re.compile(r"SWEEP IN PARTS: (?:<n>|\d+) (?:areas|files) not read")
        for rel in DOCS:
            for m in re.finditer(r"SWEEP IN PARTS:", raw(rel)):
                with self.subTest(file=rel):
                    self.assertIsNotNone(shape.match(raw(rel), m.start()), raw(rel)[m.start(): m.start() + 50])

    def test_the_checker_sees_a_wrapped_token(self):
        wrapped = "send `CONTINUE\nSWEEP` on the first line"
        self.assertEqual(self.bad_spellings(wrapped, "CONTINUE SWEEP"), 1)
        self.assertEqual(self.bad_spellings("a `CONTINUE SWEEP` b", "CONTINUE SWEEP"), 0)
        self.assertEqual(self.bad_spellings("INVESTIGATE\nREPORT ENDS", "INVESTIGATE REPORT ENDS"), 1)
        self.assertEqual(self.bad_spellings("Stopped before reading", "STOPPED BEFORE READING"), 0)


class ReadmePartsTest(PinTable, unittest.TestCase):
    """README.md: the part size, the read-in-parts sentence, 'without asking you', and the measured cost figures."""

    def text(self):
        return raw("README.md")

    @property
    def PINS(self):
        return [
            ("the part size is the agent's",
             "A repo with more than %s tracked files to read, not counting folders skipped whole such as vendored code, is read in parts" % part_size()),
            ("each report says which areas are left", "each report covers whole areas and says which areas are left"),
            ("the session carries on without asking", "your session sends the next brief without asking you"),
            ("the cost sentence has its own subject", "A per-file sweep costs more than one agent reading everything"),
            ("measured: 191 files", "on one test repo of 191 files"),
            ("measured: new cost and time", "about $2.31 and about 710 seconds a run"),
            ("measured: old cost and time", "about $0.47 and 109 seconds for 1.7.6's single-agent read"),
            ("measured: dated", "dated 2026-11-05"),
        ]

    def test_the_stop_clause_is_gone_and_the_cost_sentence_has_not_lost_its_subject(self):
        t = fold(self.text())
        self.assertNotRegex(t, r"(?i)stops above|so your session can ask you first|That costs more")

    def test_the_part_size_is_read_from_the_agent_file_and_is_a_number(self):
        self.assertRegex(part_size(), r"^\d+$")
        # a different size in the README would fail the first pin
        self.assertNotIn("more than 300 tracked files", fold(self.text()))

    def test_a_wrong_part_size_in_the_readme_is_caught(self):
        folded = fold(self.text()).replace("more than %s tracked files" % part_size(), "more than 300 tracked files")
        self.assertEqual(missing(folded, self.PINS), ["the part size is the agent's"])


class ChangelogTest(unittest.TestCase):
    NUMBERED = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.M)

    SAMPLE = "# Changelog\n\n## [Unreleased]\n\nnew\n\n## [1.2.0] \u2014 2026-01-02\n\nb\n\n## [1.1.0] \u2014 2026-01-01\n\na\n"

    @classmethod
    def unreleased_problems(cls, text):
        """What is wrong with the Unreleased heading: more than one, or one that isn't above every numbered heading.
        None at all is fine (the heading is renamed to a version at a release)."""
        starts = [m.start() for m in re.finditer(r"^## \[Unreleased\]", text, re.M)]
        numbered = [m.start() for m in cls.NUMBERED.finditer(text)]
        problems = []
        if len(starts) > 1:
            problems.append("more than one Unreleased heading")
        if starts and numbered and starts[0] > min(numbered):
            problems.append("Unreleased is below a numbered heading")
        return problems

    def test_at_most_one_unreleased_heading_and_it_sits_above_every_numbered_one(self):
        self.assertEqual(self.unreleased_problems(raw("CHANGELOG.md")), [])

    def test_the_unreleased_heading_is_not_taken_for_a_version(self):
        text = raw("CHANGELOG.md")
        self.assertNotIn("Unreleased", [m.group(1) for m in self.NUMBERED.finditer(text)])

    def test_the_position_check_on_a_sample_sees_each_fault_and_allows_a_release(self):
        s = self.SAMPLE
        self.assertEqual(self.unreleased_problems(s), [])
        # after a release: no Unreleased heading at all
        released = s.replace("## [Unreleased]", "## [1.3.0] \u2014 2026-02-01", 1)
        self.assertEqual(self.unreleased_problems(released), [])
        self.assertEqual(len(self.NUMBERED.findall(released)), len(self.NUMBERED.findall(s)) + 1)
        # a second heading, and a heading moved below the newest version, are seen
        self.assertEqual(self.unreleased_problems(s + "\n## [Unreleased]\n"), ["more than one Unreleased heading"])
        below = s.replace("## [Unreleased]", "## [Xx]", 1).replace("## [1.2.0]", "## [Unreleased]\n\n## [1.2.0]", 1)
        self.assertEqual(self.unreleased_problems(below), [])  # still above every numbered heading
        moved = s.replace("## [Unreleased]\n\nnew\n\n", "", 1).replace("## [1.1.0]", "## [Unreleased]\n\n## [1.1.0]", 1)
        self.assertEqual(self.unreleased_problems(moved), ["Unreleased is below a numbered heading"])

    def test_the_newest_numbered_heading_is_the_plugin_version(self):
        version = json.loads(raw(".claude-plugin/plugin.json"))["version"]
        self.assertEqual(self.NUMBERED.search(raw("CHANGELOG.md")).group(1), version)

    @staticmethod
    def entry(text, version):
        m = re.search(r"^## \[%s\][^\n]*\n" % re.escape(version), text, re.M)
        if not m:
            return None
        nxt = re.compile(r"^## \[\d+\.\d+\.\d+\]", re.M).search(text, m.end())
        return text[m.start(): nxt.start() if nxt else len(text)]

    def test_the_2_2_0_entry_is_byte_identical_to_head(self):
        try:
            head = subprocess.run(["git", "show", "HEAD:CHANGELOG.md"], cwd=str(ROOT), capture_output=True, check=True).stdout.decode("utf-8")
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("no git history to compare with")
        self.assertIsNotNone(self.entry(head, "2.2.0"))
        self.assertEqual(self.entry(raw("CHANGELOG.md"), "2.2.0"), self.entry(head, "2.2.0"))

    def test_the_entry_comparison_sees_a_one_character_change(self):
        text = raw("CHANGELOG.md")
        edited = text.replace("## [2.2.0]", "## [2.2.0]", 1)
        self.assertEqual(self.entry(edited, "2.2.0"), self.entry(text, "2.2.0"))
        i = text.index("## [2.2.0]")
        j = text.index("\n", text.index("\n", i) + 2)
        edited = text[:j] + " " + text[j:]
        self.assertNotEqual(self.entry(edited, "2.2.0"), self.entry(text, "2.2.0"))


def script_flags(script):
    src = (EXPENSIVE / script).read_text(encoding="utf-8")
    flags, required = set(), set()
    for m in re.finditer(r"add_argument\(([^)]*)\)", src):
        args = m.group(1)
        names = re.findall(r"\"(--[\w-]+)\"", args)
        flags.update(names)
        if "required=True" in args:
            required.update(names)
    return flags, required


def scripts_called(text, commands_only=False):
    """[(script, flags used)] for each line in text that calls one of the three scripts (or compare.py)."""
    out = []
    for line in text.splitlines():
        if commands_only and "python3 " not in line:
            continue
        for m in re.finditer(r"(measure_reply|check_parts|sync_big_sweep|compare)\.py\b", line):
            out.append((m.group(1) + ".py", set(re.findall(r"(?<![\w-])(--[a-z][\w-]*)", line[m.end():]))))
    return out


class EvalsReadmeTest(unittest.TestCase):
    SCRIPTS = ["measure_reply.py", "check_parts.py", "sync_big_sweep.py"]

    def section(self):
        t = raw("evals/README.md")
        return t[t.index("### A big repo read in parts"): t.index("## How a case is built")]

    def test_it_names_the_loop_case_the_reply_size_cases_and_the_three_scripts(self):
        text = self.section()
        self.assertIn("`big-sweep-in-parts`", text)
        sizes = sorted(p.name[len("reply-size-"):] for p in EXPENSIVE.glob("reply-size-*") if p.is_dir())
        self.assertGreaterEqual(len(sizes), 6)
        for size in sizes:
            with self.subTest(size=size):
                self.assertIn(("`reply-size-%s`" if size == sizes[0] else "`-%s`") % size, text)
        for case in ("reply-size-320", "reply-size-full"):
            self.assertIn("--case %s " % case, text)
        for script in self.SCRIPTS:
            with self.subTest(script=script):
                self.assertIn(script, text)
                self.assertTrue((EXPENSIVE / script).is_file())

    def test_every_command_that_calls_a_script_uses_flags_the_script_has(self):
        calls = scripts_called(self.section())
        self.assertGreaterEqual(len(calls), 6)
        for script, used in calls:
            have, _ = script_flags(script)
            with self.subTest(script=script, used=sorted(used)):
                self.assertLessEqual(used, have)

    def test_every_command_passes_the_flags_the_script_requires(self):
        for script, used in scripts_called(self.section(), commands_only=True):
            _, required = script_flags(script)
            if script == "measure_reply.py":
                required = {"--marker"}
            with self.subTest(script=script, used=sorted(used)):
                self.assertLessEqual(required, used)

    def test_the_prose_bullets_name_real_flags_too(self):
        bullets = re.findall(r"(?ms)^- `(sync_big_sweep|measure_reply|check_parts)\.py(.*?)(?=^- `|^\*\*|\Z)", self.section())
        self.assertEqual(len(bullets), 3)
        for name, body in bullets:
            used = set(re.findall(r"(?<![\w-])(--[a-z][\w-]*)", body))
            with self.subTest(script=name, used=sorted(used)):
                self.assertTrue(used)
                self.assertLessEqual(used, script_flags(name + ".py")[0])

    def test_a_flag_the_script_does_not_have_would_be_seen(self):
        self.assertFalse({"--parts-dir"} <= script_flags("check_parts.py")[0])
        used = scripts_called("python3 evals-expensive/check_parts.py --key K --parts-dir P")[0][1]
        self.assertFalse(used <= script_flags("check_parts.py")[0])

    def test_the_argparse_read_finds_the_flags_the_readme_relies_on(self):
        self.assertEqual(script_flags("check_parts.py")[0] & {"--key", "--repo", "--parts", "--min-parts", "--part-size"},
                         {"--key", "--repo", "--parts", "--min-parts", "--part-size"})
        self.assertIn("--check", script_flags("sync_big_sweep.py")[0])
        self.assertLessEqual({"--transcript", "--harness", "--marker"}, script_flags("measure_reply.py")[0])
        self.assertLessEqual({"--key", "--new", "--baseline"}, script_flags("compare.py")[0])

    def test_the_scoring_line_uses_min_parts_3_and_the_agents_part_size(self):
        text = self.section()
        self.assertIn("--min-parts 3 --part-size %s --transcript" % part_size(), text)
        for m in re.finditer(r"--part-size (\d+)", raw("evals/README.md")):
            self.assertEqual(m.group(1), part_size())
        self.assertIn("reads a repo with more than %s tracked files to read, not counting folders skipped whole such as vendored code, in parts"
                      % part_size(), fold(text))

    def test_the_pass_words_are_spelled_as_the_scripts_print_them(self):
        loop = (EXPENSIVE / "check_parts.py").read_text(encoding="utf-8")
        cmp_ = (EXPENSIVE / "compare.py").read_text(encoding="utf-8")
        proved = re.search(r'print\("(LOOP PROVED)"\)', loop).group(1)
        failed = re.search(r'print\("(LOOP FAILED)"\)', loop).group(1)
        cant_check = re.search(r'print\("(CAN\'T CHECK:)', loop).group(1)
        met = re.search(r'print\("(BAR MET)" if', cmp_).group(1)
        cant_measure = re.search(r'"(CAN\'T MEASURE:)', (EXPENSIVE / "measure_reply.py").read_text(encoding="utf-8")).group(1)
        text = self.section()
        for word in (proved, failed, cant_check, met, cant_measure):
            with self.subTest(word=word):
                self.assertIn(word, text)

    def test_the_readme_gives_the_exit_codes_the_scripts_have(self):
        text = fold(self.section())
        self.assertIn("Exit 0 prints `LOOP PROVED`, exit 1 prints `LOOP FAILED` with a line for each failure, and exit 2 prints `CAN'T CHECK:`", text)
        self.assertIn("Exit 0 when it parsed something, 2 with `CAN'T MEASURE:` when it didn't.", text)
        self.assertIn("exits 1, or exits 0 when none does", text)

    def test_every_evals_expensive_path_it_names_exists(self):
        text = raw("evals/README.md")
        sizes = [p.name[len("reply-size-"):] for p in EXPENSIVE.glob("reply-size-*")]
        seen = 0
        for m in re.finditer(r"evals-expensive/([\w./$*{}-]*[\w/*$])", text):
            rel = m.group(1)
            variants = [rel]
            if "$N" in rel:
                variants = [rel.replace("$N", s) for s in sizes]
            for v in variants:
                if "$" in v or "<" in v:
                    continue
                seen += 1
                with self.subTest(path="evals-expensive/" + v):
                    if "*" in v:
                        self.assertTrue(list(EXPENSIVE.glob(v)), v)
                    else:
                        self.assertTrue((EXPENSIVE / v).exists(), v)
        self.assertGreater(seen, 10)

    def test_a_missing_path_would_be_seen(self):
        self.assertFalse((EXPENSIVE / "reply-size-999" / "scaffold.sh").exists())
        self.assertTrue((EXPENSIVE / "reply-size-150" / "scaffold.sh").exists())


class EvalsReadmeAgreesWithTheBuildLogTest(unittest.TestCase):
    """Figures in evals/README.md's new section that also appear in the plan's build log must match it.
    A figure that appears in neither the plan nor the design is a finding."""

    PLAN = "docs/plans/2026-11-23-big-sweep-in-parts.md"

    def setUp(self):
        self.plan = raw(self.PLAN)
        self.log = self.plan[self.plan.index("## Build log"):]
        t = raw("evals/README.md")
        self.section = fold(t[t.index("### A big repo read in parts"): t.index("## How a case is built")])

    def table(self):
        rows = {}
        for m in re.finditer(r"^\s*\| (\d+) \| ([\w ]+) \| ([\d.]+)KB \| [^|]+ \| ([\d,]+) \|", self.log, re.M):
            rows[(m.group(1), m.group(2).strip())] = (m.group(3), m.group(4))
        return rows

    def test_the_150_file_report_is_the_plain_briefs_and_not_the_full_path_ones(self):
        # the qa pass's finding: the 150-file figure was once given as a full-path run
        self.assertEqual(self.table()[("150", "plain")], ("11.0", "425"))
        self.assertNotIn(("150", "full paths"), self.table())
        self.assertNotRegex(self.section, r"11\.0KB for 150 files[^.]*full route paths")

    def test_the_fixture_counts_are_the_plans_and_the_keys(self):
        for figure in ("990 tracked files", "950", "945 readable", "610"):
            with self.subTest(figure=figure):
                self.assertIn(figure.split()[0], self.plan)
        facts = json.loads((EXPENSIVE / "big-sweep-key.json").read_text(encoding="utf-8"))["facts"]
        self.assertIn("%d planted facts" % len(facts), self.section)
        self.assertIn("all %d facts found" % len(facts), self.section)

    def test_what_it_says_the_reply_size_prompts_ask_for_is_what_they_ask_for(self):
        self.assertIn("a last line of `TAIL-MARK-6620`", self.section)
        for prompt in sorted(EXPENSIVE.glob("reply-size-*/prompt.md")):
            body = prompt.read_text(encoding="utf-8")
            with self.subTest(case=prompt.parent.name):
                self.assertIn("TAIL-MARK-6620", body)
                self.assertRegex(body, r"(?i)approved")

    def test_the_timeout_is_the_cases_and_the_harness_limit(self):
        prompt = (EXPENSIVE / "big-sweep-in-parts" / "prompt.md").read_text(encoding="utf-8")
        m = re.search(r"timeout_seconds: (\d+)", prompt)
        self.assertIn("%s-second timeout" % m.group(1), self.section)
        self.assertIn("over %s" % m.group(1), self.section)

    def test_every_measured_figure_in_the_section_is_in_the_plan_or_the_design(self):
        sources = self.plan + raw("docs/design.md")
        for m in re.finditer(r"\$\d+(?:\.\d+)?|\d[\d,]*(?:\.\d+)?KB|\d[\d,]* seconds|TAIL-MARK-\d+", self.section):
            fig = m.group(0).replace(" seconds", "")
            with self.subTest(figure=m.group(0)):
                self.assertIn(fig, sources)


class ContributingAndPrivacyTest(unittest.TestCase):
    CONTRIB = [
        ("names the loop case", "A change to `investigate` also gets the `big-sweep-in-parts` loop there"),
        ("names the scorer", "is scored by `check_parts.py`"),
    ]
    PRIVACY = [
        ("sync script", "`evals-expensive/sync_big_sweep.py`"),
        ("measure script", "`evals-expensive/measure_reply.py`"),
        ("check script", "`evals-expensive/check_parts.py`"),
        ("by hand, local, no network", "run only when you run them by hand, stay local, use no network"),
    ]

    def test_contributing_names_the_loop_case(self):
        folded = fold(raw("CONTRIBUTING.md"))
        self.assertEqual(missing(folded, self.CONTRIB), [])
        self.assertTrue((EXPENSIVE / "big-sweep-in-parts" / "prompt.md").is_file())
        self.assertTrue((EXPENSIVE / "check_parts.py").is_file())

    def test_privacy_names_the_three_scripts_and_each_exists(self):
        folded = fold(raw("PRIVACY.md"))
        self.assertEqual(missing(folded, self.PRIVACY), [])
        for script in ("sync_big_sweep.py", "measure_reply.py", "check_parts.py", "compare.py", "sync_case.py"):
            with self.subTest(script=script):
                self.assertIn("evals-expensive/" + script, folded)
                self.assertTrue((EXPENSIVE / script).is_file())

    def test_deleting_each_contributing_or_privacy_phrase_is_caught(self):
        for pins, rel in ((self.CONTRIB, "CONTRIBUTING.md"), (self.PRIVACY, "PRIVACY.md")):
            folded = fold(raw(rel))
            for name, phrase in pins:
                with self.subTest(file=rel, pin=name):
                    self.assertEqual(missing(delete(folded, phrase), pins), [name])

    def test_the_privacy_scripts_really_use_no_network(self):
        for script in ("sync_big_sweep.py", "measure_reply.py", "check_parts.py"):
            src = (EXPENSIVE / script).read_text(encoding="utf-8")
            with self.subTest(script=script):
                self.assertIsNone(re.search(r"(?m)^\s*(?:import|from)\s+(?:urllib|http|socket|requests|ftplib|smtplib)\b", src))


if __name__ == "__main__":
    unittest.main()
