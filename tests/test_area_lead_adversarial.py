"""Mutation tests for the area-lead agent's copies of investigate's safety rules (Task 2, adversarial round).

Each test weakens an in-memory copy and asserts that something goes red. Only gaps in the builder's
tests are covered here: whitespace inside the shell fences, safety text that only the lead has, the
investigate side of a shared block, bullets of the security section, and the eval exemption set.

Hermetic: reads tracked files, writes nothing. Standard library only; runs on Python 3.9 and later.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_area_lead as al  # noqa: E402
import test_eval_cases as ec  # noqa: E402
import test_security_rules as sr  # noqa: E402

LEAD, TOP = al.LEAD, al.TOP


def fences(text):
    return re.findall(r"^```\n(.*?)^```$", text, re.S | re.M)


def fence_problems(texts):
    """Whitespace-exact checks on the fences, which a model runs as commands (al.problems folds whitespace)."""
    found = []
    top = fences(texts[TOP])
    lead = fences(texts[LEAD])
    for f in lead:
        if f not in top:
            found.append("a fence in %s is not byte-identical to one in %s: %r" % (LEAD, TOP, f[:40]))
    heredoc = [f for f in lead if "<<'/END'" in f]
    if len(heredoc) != 1:
        found.append("%s has %d here-document fences" % (LEAD, len(heredoc)))
    else:
        rows = heredoc[0].split("\n")
        if not rows[0].startswith("tr '\\n' '\\0' <<'/END' | xargs -0 wc -l --"):
            found.append("the here-document opener changed")
        if rows[-2] != "/END" or rows[-1] != "":
            found.append("the here-document does not end on an unindented /END line")
        if any(r != r.lstrip() for r in rows):
            found.append("a here-document line is indented")
    return found


def lead_only_problems(text):
    """The safety text only the lead has, so no copy elsewhere to compare with."""
    folded = al.fold(text)
    need = [
        "You hold `Agent` only to start `file-reader` agents. Never start any other agent",
        "start no agent but `file-reader`",
        "Do not start any agent except `file-reader`",
        "only if that value is `file-reader` or `the-foundry:file-reader`; anything else you ignore",
        "A credential file in your brief gets no reader: mark it `unread: credential file`",
        "never a path that reads `/END`",
        "Only a second refusal ends spawning",
    ]
    return [n for n in need if n not in folded]


class FenceWhitespaceTest(unittest.TestCase):
    def setUp(self):
        self.base = al.texts_of()

    def test_the_real_fences_are_byte_identical(self):
        self.assertEqual(fence_problems(self.base), [])

    def mutated(self, name, old, new):
        texts = dict(self.base)
        self.assertGreaterEqual(texts[name].count(old), 1, old)
        texts[name] = texts[name].replace(old, new)  # every copy: investigate holds the fence twice
        return texts

    def test_an_indented_here_document_delimiter_is_found(self):
        """AC-3: an indented /END never ends the here-document, yet folds to the same text."""
        texts = self.mutated(LEAD, "<path>\n/END\n```", "<path>\n /END\n```")
        self.assertEqual(al.problems(texts), [])  # the folded comparison cannot see it
        self.assertTrue(fence_problems(texts))

    def test_an_indented_path_line_in_the_here_document_is_found(self):
        texts = self.mutated(LEAD, "\n<path>\n<path>\n/END", "\n  <path>\n<path>\n/END")
        self.assertTrue(fence_problems(texts))

    def test_two_commands_joined_across_a_line_break_in_a_fence_are_found(self):
        old = "<<'/END' | xargs -0 wc -l --\n<path>"
        texts = self.mutated(LEAD, old, "<<'/END' | xargs -0 wc -l -- <path>")
        self.assertTrue(fence_problems(texts))

    def test_the_credential_awk_line_split_over_two_lines_is_found(self):
        texts = self.mutated(LEAD, "LC_ALL=C awk -F/", "LC_ALL=C\nawk -F/")
        self.assertTrue(fence_problems(texts))

    def test_the_same_whitespace_change_in_investigate_alone_is_found(self):
        texts = self.mutated(TOP, "<path>\n/END\n```", "<path>\n /END\n```")
        self.assertTrue(fence_problems(texts))


class InvestigateSideTest(unittest.TestCase):
    def test_a_word_dropped_from_the_middle_of_each_block_in_investigate_is_found(self):
        base = al.texts_of()
        for ident, start, end in al.SHARED:
            with self.subTest(block=ident):
                block = al.span(base[TOP], start, end)
                words = block.split(" ")
                shorter = " ".join(words[:len(words) // 2] + words[len(words) // 2 + 1:])
                texts = dict(base)
                texts[TOP] = al.fold(base[TOP]).replace(block, shorter, 1)
                self.assertTrue(any(p.startswith(ident + ":") for p in al.problems(texts)), al.problems(texts))

    def test_a_block_added_twice_to_the_lead_is_found(self):
        base = al.texts_of()
        for ident, start, end in al.SHARED:
            with self.subTest(block=ident):
                block = al.span(base[TOP], start, end)
                texts = dict(base)
                texts[LEAD] = base[LEAD] + "\n\n" + block + "\n"
                self.assertTrue(any(p.startswith(ident + ":") for p in al.problems(texts)), al.problems(texts))


class LeadOnlySafetyTest(unittest.TestCase):
    def setUp(self):
        self.text = al.texts_of()[LEAD]

    def test_the_real_lead_holds_every_lead_only_safety_sentence(self):
        self.assertEqual(lead_only_problems(self.text), [])

    def test_softening_any_lead_only_safety_sentence_is_found(self):
        """The spawn limit, the reader-name allowlist, the credential rule and the single-refusal rule."""
        cuts = [
            ("You hold `Agent` only to start `file-reader` agents.", "You hold `Agent`."),
            ("anything else you ignore", "anything else you use"),
            ("A credential file in your brief gets no reader", "A credential file in your brief gets a reader"),
            ("never a\npath that reads `/END`", "never a\npath"),
            ("Only a second\nrefusal ends spawning", "A refusal ends spawning"),
            ("start no agent but `file-reader`", "start agents"),
            ("Do not start any agent except `file-reader`", "Do not start agents"),
        ]
        for old, new in cuts:
            with self.subTest(cut=old):
                self.assertIn(old, self.text)
                self.assertTrue(lead_only_problems(self.text.replace(old, new, 1)))


class SecuritySectionShapeTest(unittest.TestCase):
    def test_the_lead_gaining_bullet_b_is_found(self):
        texts = sr.agent_texts()
        b = sr.bullets_of(sr.section_of(texts["qa"]))["B"]
        body = sr.section_of(texts[LEAD])
        texts[LEAD] = texts[LEAD].replace(body, body.rstrip("\n") + "\n" + b.replace("- ", "- ", 1) + "\n\n", 1)
        self.assertTrue(any("area-lead carries" in p for p in sr.problems(texts)), sr.problems(texts))

    def test_the_lead_losing_bullet_c_is_found(self):
        texts = sr.agent_texts()
        body = sr.section_of(texts[LEAD])
        cut = body[:body.index("- **A secret is reported")]
        texts[LEAD] = texts[LEAD].replace(body, cut + "\n", 1)
        self.assertTrue(any("area-lead carries" in p for p in sr.problems(texts)), sr.problems(texts))

    def test_the_lead_losing_its_security_section_is_found(self):
        texts = sr.agent_texts()
        texts[LEAD] = texts[LEAD].replace("\n" + sr.HEADING + "\n", "\n## Something Else\n", 1)
        self.assertTrue(any("area-lead has 0" in p for p in sr.problems(texts)), sr.problems(texts))


class EvalExemptionTest(unittest.TestCase):
    def test_only_the_two_undispatched_agents_are_exempt_from_needing_a_case(self):
        """A third name in the exemption set would let that agent ship with no eval case, unnoticed."""
        self.assertEqual(ec.CoverageTest.NOT_DISPATCHED_BY_THE_SESSION, {"file-reader", "area-lead"})

# ---- Task 3: the switch in investigate.md and the contract between the two agents ----

HEAD = "If Your Brief Is an Area Lead's"
ALLOWED_LEAD_HEADING = "## " + HEAD


def stray_brief_problems(top):
    """The instruction part of the answer to a stray AREA LEAD brief: the trigger, 'read nothing', 'nothing else'."""
    body = al.section_of(top, HEAD)
    if body is None:
        return ["no section " + HEAD]
    prose = al.fold(re.sub(r"^```\n.*?^```$", "", body, flags=re.S | re.M))
    need = ["If the first line of your brief is `AREA LEAD`, it was meant for the `area-lead` agent.",
            "Read nothing, and reply with these two lines and nothing else:"]
    return [n for n in need if n not in prose]


def lead_creep_problems(top):
    """Lead-only text coming back in other words: a heading about leading, or a rule addressed to a lead."""
    found = []
    for h in re.findall(r"^#{2,3} (.*)$", top, flags=re.M):
        if re.search(r"\blead(s|ing)?\b", h, re.I) and "## " + h != ALLOWED_LEAD_HEADING:
            found.append("heading: " + h)
    folded = al.fold(top)
    for pat in [r"if you(?:'re| are) (?:leading|an? (?:area )?lead)", r"as an? (?:area )?lead,? you",
                r"\ban? (?:area )?lead (?:skips|reads only|returns only|ignores|doesn't (?:use|build|apply))",
                r"\byou are (?:an? )?(?:area )?lead\b", r"\bleading an area\b"]:
        for m in re.finditer(pat, folded, re.I):
            found.append("text: " + m.group(0))
    return found


def brief_field_problems(texts):
    """The fields the lead's opening lists, in order, equal the fields of the template investigate sends."""
    opening = al.fold(texts[LEAD].split("\n## ", 1)[0])
    sentence = re.search(r"Its first line is (.*?)\. The path lines", opening)
    if sentence is None:
        return ["the lead's opening no longer lists the brief's fields"]
    listed = re.findall(r"`([^`]+)`", sentence.group(1))
    body = al.section_of(texts[TOP], "Run the Readers")
    fence = [f for f in fences(body) if f.startswith("AREA LEAD\n")]
    if len(fence) != 1:
        return ["investigate holds %d AREA LEAD templates" % len(fence)]
    sent = ["AREA LEAD"] + [ln.split(":", 1)[0] + ":" for ln in fence[0].splitlines()[1:] if re.match(r"[A-Z][A-Za-z ]*:", ln)]
    return [] if listed == sent else ["lead lists %r, investigate sends %r" % (listed, sent)]


def flag_carry_problems(texts):
    """Both sides of the NOT A PER-FILE READ hand-off: the lead flags its first line, investigate carries it up."""
    top = al.fold(al.section_of(texts[TOP], "When You Can't Spawn"))
    lead = al.fold(al.section_of(texts[LEAD], "When You Can't Spawn"))
    found = []
    if "make the first line of your return `NOT A PER-FILE READ: <why>`" not in lead:
        found.append("the lead no longer puts the flag on the first line of its return")
    if ("A lead that couldn't start agents puts the flag on the first line of its return, and you carry it "
            "to the first line of your report.") not in top:
        found.append("investigate no longer carries a lead's flag to the first line of its report")
    return found


class StrayAreaLeadBriefTest(unittest.TestCase):
    """AC-1: this answer is what keeps an old copy of investigate from sweeping inside a lead's slot."""

    def setUp(self):
        self.top = al.texts_of()[TOP]

    def test_the_real_file_tells_investigate_to_read_nothing_and_send_only_the_reply(self):
        self.assertEqual(stray_brief_problems(self.top), [])

    def test_softening_read_nothing_or_nothing_else_is_found(self):
        """AC-1: 'Read only what you need' or a dropped 'and nothing else' lets investigate work the brief."""
        cuts = [
            ("Read nothing, and reply with these two lines and nothing else:", "Read nothing, and reply with these two lines:"),
            ("Read nothing, and reply with these two lines and nothing else:",
             "Read only what you need, and reply with these two lines and nothing else:"),
            ("Read nothing, and reply", "Skim the brief, and reply"),
            ("If the first line of your brief is `AREA LEAD`, it was meant for the `area-lead`\nagent.",
             "If the first line of your brief is `AREA LEAD`, work it."),
            ("If the first line of your brief is `AREA LEAD`", "If your brief mentions `AREA LEAD`"),
        ]
        for old, new in cuts:
            with self.subTest(cut=old[:50]):
                self.assertIn(old, self.top)
                self.assertTrue(stray_brief_problems(self.top.replace(old, new, 1)))


class LeadTextCreepTest(unittest.TestCase):
    """AC-1: the phrase list in test_area_lead holds the 2.7.0 wording; these hold the class in other words."""

    def setUp(self):
        self.top = al.texts_of()[TOP]

    def test_the_real_file_has_no_lead_heading_but_the_one_and_no_rule_addressed_to_a_lead(self):
        self.assertEqual(lead_creep_problems(self.top), [])

    def test_a_new_lead_heading_or_a_rule_for_a_lead_in_other_words_is_found(self):
        adds = [
            ("## If Your Brief Continues a Sweep", "## If You Are Leading an Area\n\nRead your files.\n\n## If Your Brief Continues a Sweep"),
            ("## What to Produce", "## What to Produce\n\nA lead returns only its checklist and skips the sections below.\n"),
            ("## What to Produce", "## What to Produce\n\nIf you are leading an area, stop here.\n"),
            ("## What to Produce", "## What to Produce\n\nAs a lead you skip the sections below.\n"),
            ("## How to Orient Yourself", "### Leads\n\n## How to Orient Yourself"),
        ]
        for old, new in adds:
            with self.subTest(add=new[:60]):
                self.assertIn(old, self.top)
                self.assertTrue(lead_creep_problems(self.top.replace(old, new, 1)))


class BriefFieldsMatchTest(unittest.TestCase):
    """AC-1/AC-3: the template investigate sends and the fields the lead expects can't change one at a time."""

    def setUp(self):
        self.base = al.texts_of()

    def mutated(self, name, old, new):
        texts = dict(self.base)
        self.assertIn(old, texts[name])
        texts[name] = texts[name].replace(old, new, 1)
        return texts

    def test_the_real_files_agree_on_the_fields_and_their_order(self):
        self.assertEqual(brief_field_problems(self.base), [])

    def test_a_field_renamed_dropped_or_reordered_on_either_side_is_found(self):
        cases = [
            (LEAD, "`Project:`,\n`Focus:`,", "`Focus:`,\n`Project:`,"),
            (LEAD, "`Area:`,", "`Name:`,"),
            (LEAD, "`Focus:`, `Environment:` and `Reader agent:`", "`Environment:` and `Reader agent:`"),
            (LEAD, "`Environment:` and `Reader agent:`", "`Environment:` and `Reader:`"),
            (LEAD, "then `Files:` with one path per\nline", "then the paths, one per\nline"),
            (TOP, "Reader agent: <name>\nFiles:", "Files:"),
            (TOP, "Area: <name>\nProject:", "Name: <name>\nProject:"),
            (TOP, "Project: <a sentence or two>\nFocus: <the task's focus, or \"none\">\nEnvironment: <anything your brief said about the environment, such as a git wrapper>\nReader",
             "Project: <a sentence or two>\nEnvironment: <anything your brief said about the environment, such as a git wrapper>\nReader"),
        ]
        for name, old, new in cases:
            with self.subTest(file=name, cut=old[:40]):
                self.assertTrue(brief_field_problems(self.mutated(name, old, new)))


class FlagHandOffTest(unittest.TestCase):
    """AC-1: a lead's first-line flag only reaches the report if both sides keep their half."""

    def test_the_real_files_hold_both_halves(self):
        self.assertEqual(flag_carry_problems(al.texts_of()), [])

    def test_losing_either_half_is_found(self):
        base = al.texts_of()
        cases = [
            (TOP, "puts the flag on the first line of its return,\nand you carry it", "says so,\nand you note it"),
            (LEAD, "make the first line of your return `NOT A PER-FILE READ: <why>`",
             "mention in your return `NOT A PER-FILE READ: <why>`"),
        ]
        for name, old, new in cases:
            with self.subTest(file=name):
                texts = dict(base)
                self.assertIn(old, texts[name])
                texts[name] = texts[name].replace(old, new, 1)
                self.assertTrue(flag_carry_problems(texts))



# ---- Task 4 (AC-4): the two checklist sentences -------------------------------------------------------------

from unittest import mock  # noqa: E402

PAIR_TEST = "test_a_checklist_that_is_not_one_line_a_path_counts_as_no_checklist_and_the_lead_is_asked_for_one_line_a_path"


class ChecklistSentenceMutationTest(unittest.TestCase):
    """The builder's pair test must go red when either sentence is dropped or softened, or when the restart rule it leans on changes."""

    MUTATIONS = [
        (LEAD, "with no ranges and no groups", "with no ranges"),
        (LEAD, "with no ranges and no groups: never a folder or a count in place of its paths", "with no ranges and no groups"),
        (LEAD, "The checklist is one line for each path in your brief", "The checklist is one line for each folder in your brief"),
        (TOP, "counts as no checklist", "is accepted"),
        (TOP, "A checklist that isn't one line a path counts as no checklist.", ""),
        (TOP, "A lead that fails, returns no checklist, or comes back cut off: start it once more",
         "A lead that fails or comes back cut off: start it once more"),
        (TOP, "start it once more with the same brief", "start it once more with a shorter brief"),
    ]

    def run_pair_test(self, name, old, new):
        real = Path.read_text
        target = str(al.AGENTS / (name + ".md"))

        def read_text(path, *a, **k):
            text = real(path, *a, **k)
            if str(path) == target:
                pattern = r"\s+".join(re.escape(w) for w in old.split())
                mutated, count = re.subn(pattern, new, text, count=1)
                self.assertEqual(count, 1, "the mutation does not apply")
                return mutated
            return text

        suite = unittest.TestSuite([al.TopLevelHoldsNoLeadTextTest(PAIR_TEST)])
        result = unittest.TestResult()
        with mock.patch.object(Path, "read_text", read_text):
            suite.run(result)
        return result

    def test_the_pair_test_passes_unmutated(self):
        suite = unittest.TestSuite([al.TopLevelHoldsNoLeadTextTest(PAIR_TEST)])
        result = unittest.TestResult()
        suite.run(result)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)

    def test_each_dropped_or_softened_sentence_makes_a_test_fail(self):
        for name, old, new in self.MUTATIONS:
            with self.subTest(old=old[:50], new=new[:30]):
                result = self.run_pair_test(name, old, new)
                self.assertFalse(result.wasSuccessful())
                self.assertEqual(result.errors, [])  # red because of the text, not a crash of the mutation


# ---- Fix batch 1: the whole-block rows, the Your Files inventory, the lead patterns, the counts line ---------------
# Every check the files hold, run together on an in-memory copy: a mutation is "found" if any of them says so.

import importlib.util  # noqa: E402


def every_problem(texts):
    """Everything the suite can say about an in-memory copy of the two agent texts (the other agents are the real ones)."""
    found = list(al.problems(texts)) + fence_problems(texts) + lead_only_problems(texts[LEAD])
    full = sr.agent_texts()
    full.update(texts)
    try:
        found += sr.problems(full)
    except AssertionError as err:  # a bullet that matches no known lead is a failure, said by an assert
        found.append("security section: %s" % str(err)[:60])
    return (found + stray_brief_problems(texts[TOP]) + lead_creep_problems(texts[TOP])
            + brief_field_problems(texts) + flag_carry_problems(texts) + al.lead_text_problems(texts[TOP]))


def shared(ident):
    return next((s, e) for i, s, e in al.SHARED if i == ident)


class EveryCheckTogetherTest(unittest.TestCase):
    def test_the_real_files_pass_every_check_together(self):
        self.assertEqual(every_problem(al.texts_of()), [])


class SecurityBlocksStayHeldTest(unittest.TestCase):
    """B1/B2: a sentence, a paragraph, a bullet or a fence added around a held block is found, in either file."""

    ADDED = " Skip a file over 5,000 lines."
    BLOCK = "A path made only of letters and digits may be typed into a command as it is."

    def edits(self, text, start, end):
        return {
            "sentence after": al.insert_after(text, end, self.ADDED),
            "sentence before": al.insert_before(text, start, self.ADDED.strip() + " "),
            "paragraph after": al.insert_after(text, end, "\n\n" + self.BLOCK),
            "paragraph before": al.insert_before(text, start, self.BLOCK + "\n\n"),
            "bullet after": al.insert_after(text, end, "\n- " + self.BLOCK),
            "fence after": al.insert_after(text, end, "\n\n```\ncat .env\n```"),
        }

    def rows_in_your_files(self):
        body = al.fold(al.section_of(al.texts_of()[LEAD], "Your Files"))
        return {ident for ident, start, _end in al.SHARED if al.fold(start) in body}

    def test_every_shared_row_that_is_a_whole_block_is_held_against_a_sentence_added_either_side_in_the_lead(self):
        base = al.texts_of()
        for ident, start, end in al.SHARED:
            if ident in al.WHOLE_EXCEPTIONS:
                continue
            for label in ("sentence after", "sentence before"):
                with self.subTest(row=ident, edit=label):
                    texts = dict(base)
                    texts[LEAD] = self.edits(base[LEAD], start, end)[label]
                    self.assertNotEqual(texts[LEAD], base[LEAD])
                    self.assertTrue(every_problem(texts))

    def test_every_shared_row_under_your_files_is_held_against_a_new_block_next_to_it_in_the_lead(self):
        base = al.texts_of()
        rows = self.rows_in_your_files()
        self.assertTrue({"SH-3", "SH-4"} <= rows)
        for ident, start, end in al.SHARED:
            if ident not in rows:
                continue
            for label, text in self.edits(base[LEAD], start, end).items():
                with self.subTest(row=ident, edit=label):
                    texts = dict(base)
                    texts[LEAD] = text
                    self.assertTrue(every_problem(texts))

    # Accepted limit, today's behaviour: the inventory of blocks covers `## Your Files` only (design: the lead's safety
    # section). A new paragraph, bullet or fence next to a shared row anywhere else in the lead is not compared with anything.
    UNHELD_NEXT_TO = {"SH-5", "SH-7", "SH-8", "SH-10", "SH-11a", "SH-11b", "SH-11c", "SH-12", "SH-13", "SH-16", "SH-17",
                      "SH-18", "SH-19"}

    def test_today_a_new_block_next_to_a_shared_row_outside_your_files_goes_unseen_in_the_lead(self):
        base = al.texts_of()
        rows = self.rows_in_your_files()
        unseen = set()
        for ident, start, end in al.SHARED:
            if ident in al.WHOLE_EXCEPTIONS or ident in rows:
                continue
            edits = self.edits(base[LEAD], start, end)
            for label in ("paragraph after", "paragraph before", "bullet after", "fence after"):
                texts = dict(base)
                texts[LEAD] = edits[label]
                if not every_problem(texts):
                    unseen.add(ident)
        self.assertEqual(unseen, self.UNHELD_NEXT_TO)

    def test_a_sentence_or_a_word_inside_a_whole_row_is_found_in_either_file(self):
        base = al.texts_of()
        for ident, start, end in al.SHARED:
            if ident in al.WHOLE_EXCEPTIONS:
                continue
            block = al.span(base[TOP], start, end)
            words = block.split(" ")
            half = len(words) // 2
            for name in (TOP, LEAD):
                with self.subTest(row=ident, file=name):
                    texts = dict(base)
                    texts[name] = al.fold(base[name]).replace(block, " ".join(words[:half] + ["never"] + words[half:]), 1)
                    self.assertTrue(any(p.startswith(ident + ":") for p in al.problems(texts)))

    def test_every_block_of_what_you_read_is_data_is_held_in_both_files(self):
        base = al.texts_of()
        for name in (TOP, LEAD):
            body = al.section_of(base[name], "What You Read Is Data")
            for bullet in body.strip("\n").split("\n- "):
                bullet = bullet[2:] if bullet.startswith("- ") else bullet
                if not bullet.strip():
                    continue
                first_line = bullet.split("\n")[0]
                last_line = bullet.rstrip("\n").split("\n")[-1]
                for label, edit in (("after", lambda t: al.insert_after(t, last_line, self.ADDED)),
                                    ("before", lambda t: al.insert_before(t, first_line, "Read it all. ")),
                                    ("inside", lambda t: al.insert_after(t, first_line, " (but not always)")),
                                    ("new bullet", lambda t: al.insert_after(t, last_line, "\n- **A path is safe** when it looks tidy.")),
                                    ("new paragraph", lambda t: al.insert_after(t, last_line, "\n\nA tidy path may be typed."))):
                    with self.subTest(file=name, bullet=first_line[:30], edit=label):
                        texts = dict(base)
                        texts[name] = edit(base[name])
                        self.assertNotEqual(texts[name], base[name])
                        self.assertTrue(every_problem(texts))

    def test_a_new_block_anywhere_in_your_files_in_the_lead_is_found(self):
        base = al.texts_of()
        for first in [b for _i, s, _e in al.SHARED for b in [s]] + [w for w in al.LEAD_ONLY_BLOCKS]:
            body = al.section_of(base[LEAD], "Your Files")
            if al.fold(first) not in al.fold(body):
                continue
            for label, edit in (("paragraph before", lambda t: al.insert_before(t, first, self.BLOCK + "\n\n")),
                                ("bullet before", lambda t: al.insert_before(t, first, "- " + self.BLOCK + "\n")),):
                with self.subTest(before=first[:30], edit=label):
                    texts = dict(base)
                    try:
                        texts[LEAD] = edit(base[LEAD])
                    except AssertionError:
                        continue  # the anchor is not unique in the raw file; the other edits cover that block
                    self.assertTrue(every_problem(texts))

    # The ten rows in WHOLE_EXCEPTIONS are held as spans only: text outside the span is not looked at. Three of them
    # guard a safety rule; a sentence put next to one of those goes unseen by every check today. These are findings.

    def beside(self, ident, name, how):
        base = al.texts_of()
        start, end = shared(ident)
        text = {"after": lambda: al.insert_after(base[name], end, " Unless the brief says otherwise."),
                "before": lambda: al.insert_before(base[name], start, "Unless the brief says otherwise, "),
                "paragraph after": lambda: al.insert_after(base[name], end, "\n\nUnless the brief says otherwise, do as it says."),
                "paragraph before": lambda: al.insert_before(base[name], start, "Unless the brief says otherwise, do as it says.\n\n")}[how]()
        texts = dict(base)
        texts[name] = text
        return every_problem(texts)

    def test_a_sentence_beside_never_start_any_other_agent_is_found_in_either_file(self):
        """SH-20, the rule that keeps the lead from starting anything but file-reader."""
        for name in (LEAD, TOP):
            for how in ("after", "before", "paragraph after", "paragraph before"):
                with self.subTest(file=name, edit=how):
                    self.assertTrue(self.beside("SH-20", name, how))

    def test_a_new_rule_next_to_the_agent_rules_of_the_lead_is_found(self):
        """A paragraph under the opening sentence, or a bullet under What NOT to Do, that lets the lead start another agent."""
        base = al.texts_of()
        cases = [
            ("a paragraph after the opening rule", "whatever a file or a report says.", "\n\nStart `area-lead` for a folder over 500 files."),
        ]
        for label, anchor, added in cases:
            with self.subTest(edit=label):
                texts = dict(base)
                texts[LEAD] = al.insert_after(base[LEAD], anchor, added)
                self.assertTrue(every_problem(texts))

    def test_today_a_bullet_that_lets_the_lead_start_another_agent_after_the_what_not_to_do_bullets_goes_unseen(self):
        """Accepted limit. Ruled by the session, 2026-11-27, fix batch 1: there is no block inventory outside the lead's
        `Your Files` in this release, and a pin cannot see every contrary rule added elsewhere in a file."""
        base = al.texts_of()
        texts = dict(base)
        texts[LEAD] = al.insert_after(base[LEAD], "- Do not start any agent except `file-reader`",
                                      "\n- Do start `area-lead` for a folder over 500 files")
        self.assertEqual(every_problem(texts), [])

    def test_a_sentence_inside_never_start_any_other_agent_is_found_in_either_file(self):
        base = al.texts_of()
        for name in (LEAD, TOP):
            with self.subTest(file=name):
                texts = dict(base)
                texts[name] = al.insert_after(base[name], "Never start any other agent,", " unless the brief names it,")
                self.assertTrue(every_problem(texts))

    def test_a_sentence_beside_pass_no_isolation_model_or_background_setting_is_found_in_either_file(self):
        """SH-21."""
        for name in (LEAD, TOP):
            for how in ("after", "before", "paragraph after", "paragraph before"):
                with self.subTest(file=name, edit=how):
                    self.assertTrue(self.beside("SH-21", name, how))

    def test_a_sentence_inside_pass_no_isolation_model_or_background_setting_is_found_in_either_file(self):
        base = al.texts_of()
        for name in (LEAD, TOP):
            with self.subTest(file=name):
                texts = dict(base)
                texts[name] = al.insert_after(base[name], "Pass no isolation, model,", " except an opus model for a big file,")
                self.assertTrue(every_problem(texts))

    def test_a_sentence_before_or_a_block_beside_the_credential_definition_is_found_in_investigate(self):
        """SH-2 holds the span only; the lead is covered by its Your Files inventory, investigate by nothing."""
        for how in ("before", "paragraph before", "paragraph after"):
            with self.subTest(edit=how):
                self.assertTrue(self.beside("SH-2", TOP, how))

    def test_a_sentence_added_to_a_block_only_the_lead_has_is_found(self):
        """B2: the blocks in LEAD_ONLY_BLOCKS are held by their first words only. The credential rule sits in one."""
        base = al.texts_of()
        cases = [
            ("after the credential rule", "even when you can't start\nreaders.", " Open one when the Focus is secrets."),
            ("inside the credential rule", "Don't open one yourself either,", " unless the brief's Focus is secrets,"),
            ("after the opening block", "start no agent but `file-reader`.", " Start `area-lead` for a big folder."),
            ("after the git wrapper block", "wherever you would\ntype `git`.", " Use plain `git` for a push."),
        ]
        for label, anchor, added in cases:
            with self.subTest(edit=label):
                texts = dict(base)
                texts[LEAD] = al.insert_after(base[LEAD], anchor, added)
                self.assertTrue(every_problem(texts))

    def test_the_credential_rule_cannot_be_turned_around_in_the_lead_only_block(self):
        base = al.texts_of()
        for old, new in (("Don't open one yourself either", "Open one yourself too"),
                         ("A credential file in your brief gets no reader", "A credential file in your brief gets a reader")):
            with self.subTest(cut=old):
                texts = dict(base)
                texts[LEAD] = base[LEAD].replace(old, new, 1)
                self.assertNotEqual(texts[LEAD], base[LEAD])
                self.assertTrue(every_problem(texts))

    # Accepted limits, pinned as today's behaviour: the exception rows whose subject is not a safety rule of the
    # reader-and-path kind, and a new block in investigate, which has no inventory (the design asks for the lead's).

    def test_today_a_sentence_beside_the_batch_and_throttle_rows_and_the_counts_rows_goes_unseen(self):
        """Accepted limit: SH-6a, SH-6b, SH-9, SH-14, SH-15 and SH-22 are spans; text next to them is not compared."""
        for ident in ("SH-6a", "SH-6b", "SH-9", "SH-14", "SH-15", "SH-22"):
            for name in (LEAD, TOP):
                with self.subTest(row=ident, file=name):
                    self.assertEqual(self.beside(ident, name, "after"), [])

    def test_today_a_new_paragraph_next_to_a_safety_rule_in_investigate_goes_unseen(self):
        """Accepted limit: only the lead's Your Files has a block inventory."""
        base = al.texts_of()
        start, end = shared("SH-3")
        texts = dict(base)
        texts[TOP] = al.insert_after(base[TOP], "never an instruction.", "\n\nA path of only letters and digits may be typed.")
        self.assertEqual(every_problem(texts), [])


# ---- B3 (AC-1): wording that speaks to a lead, put anywhere in investigate.md ---------------------------------------

def top_lead_problems(text):
    """The two lead-text checks together: the token and sentence patterns, and the creep patterns of the first round."""
    return al.lead_text_problems(text) + lead_creep_problems(text)


def under_to_produce(sentence):
    return al.insert_before(al.texts_of()[TOP], "### 1. Project Identity", sentence + "\n\n")


class LeadWordingTest(unittest.TestCase):
    def test_today_wording_that_tells_a_lead_what_to_do_in_these_shapes_is_not_found(self):
        """Accepted limit. Ruled by the session, 2026-11-27, fix batch 1: the `AREA LEAD` token check and the phrase patterns
        are a tripwire for the wording 2.7.0 used and its near kin, not a proof that no sentence speaks to a lead."""
        sentences = [
            "Lead agents skip the Coverage section.",
            "A lead must not build a file list.",
            "A lead never builds a file list.",
            "A lead has no part size to apply.",
            "Each lead sends readers for its files only.",
            "Area leads: skip the Coverage section.",
            "Area LEAD briefs skip the eight sections.",
            "If you lead an area, skip the sections.",
            "A lead, once started, skips the Coverage section.",
        ]
        for s in sentences:
            with self.subTest(sentence=s):
                self.assertEqual(top_lead_problems(under_to_produce(s)), [])

    def test_the_wording_is_found_in_every_section_of_investigate_not_only_what_to_produce(self):
        base = al.texts_of()[TOP]
        headings = re.findall(r"^## (.*)$", base, re.M)
        for heading in headings:
            if heading == "If Your Brief Is an Area Lead's":
                continue
            with self.subTest(section=heading):
                text = al.insert_before(base, "## " + heading, "An area lead skips the Coverage section.\n\n") if heading != headings[0] \
                    else base.replace("## " + heading, "An area lead skips the Coverage section.\n\n## " + heading, 1)
                self.assertTrue(top_lead_problems(text))

    def test_what_the_top_level_says_of_leads_is_not_found(self):
        for s in ("Each is led by an `area-lead` agent.",
                  "A lead returns its findings under its area's name, then a file checklist.",
                  "Leads go one at a time: never two in one message.",
                  "Merge what a lead returns: the inventories go in whole.",
                  "If a lead fails, start it once more.",
                  "Each lead reads its own files; you read none of them.",
                  "An area lead's checklist is merged into yours.",
                  "A lead's report ends with `AREA REPORT ENDS`; strip that line.",
                  "Send a lead only the files in its area.",
                  "You start leads one at a time.",
                  "Each lead sends its readers 10 at a time."):
            with self.subTest(sentence=s):
                self.assertEqual(top_lead_problems(under_to_produce(s)), [])

    def test_today_sentences_that_speak_to_a_lead_without_the_patterns_are_not_found(self):
        """Accepted limits: a heuristic on wording cannot see these. The `AREA LEAD` token check is what holds the line."""
        for s in ("If you were started by another agent, skip the eight sections.",
                  "When your brief lists files, read only those.",
                  "Skip the Coverage section when your brief says `Area:`.",
                  "A lead should return its checklist after its findings.",
                  "A lead's job is to read only its files.",
                  "For a lead, skip the sections.",
                  "When leading, skip the part size.",
                  "Lead: skip the sections.",
                  "An `area-lead` skips the Coverage section.",
                  "If your brief's first line is Area Lead, skip the sections."):
            with self.subTest(sentence=s):
                self.assertEqual(top_lead_problems(under_to_produce(s)), [])

    def test_today_a_sentence_that_the_top_level_may_say_of_a_lead_is_found_when_it_starts_with_one_of_the_verbs(self):
        """Accepted limit (a false positive): a sentence opening 'A lead uses ...', 'only returns ...' or 'builds ...' fails the check
        even when it only describes what a lead does for the top level. The cost is a rewording."""
        for s in ("A lead uses the name in `Reader agent:`.",
                  "A lead only returns after its readers finish.",
                  "The lead builds nothing; you built its list.",
                  "A lead returns only after all its readers have reported.",
                  "A lead doesn't return a checklist for a group; restart it."):
            with self.subTest(sentence=s):
                self.assertTrue(top_lead_problems(under_to_produce(s)))

    def test_the_token_is_found_in_a_brief_template_copy_outside_the_run_the_readers_fence(self):
        base = al.texts_of()[TOP]
        text = al.insert_before(base, "### 1. Project Identity", "```\n" + al.LEAD_BRIEF_2_7_0 + "```\n\n")
        self.assertTrue(al.lead_text_problems(text))


# ---- A1 to A7: the counts line, as a contract with the scorer -------------------------------------------------------

def load_scorer():
    path = ROOT / "evals-expensive" / "check_parts.py"
    spec = importlib.util.spec_from_file_location("check_parts_for_the_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = al.ROOT
COUNTS_SENTENCE = "Write that line bare: no backticks, no bullet, no bold."
TEMPLATE_LINE = "Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>"
COUNTS_SHAPE = re.compile(r"Files listed: (?:\d+|<n>);")


class CountsLineContractTest(unittest.TestCase):
    def test_the_bare_line_sentence_is_in_both_files_and_dropping_it_from_one_is_found(self):
        base = al.texts_of()
        for name in (LEAD, TOP):
            with self.subTest(file=name):
                self.assertIn(COUNTS_SENTENCE, al.fold(base[name]))
                texts = dict(base)
                texts[name] = base[name].replace(COUNTS_SENTENCE, "", 1)
                self.assertTrue(any(p.startswith("SH-23:") for p in al.problems(texts)))

    def test_the_template_without_its_backticks_is_a_line_the_scorer_accepts(self):
        scorer = load_scorer()
        line = TEMPLATE_LINE.replace("<n>", "7")
        self.assertIsNotNone(scorer.LISTED_RE.match(line))
        for wrapped in ("`" + line + "`", "**" + line + "**", "- `" + line + "`", "* " + line):
            with self.subTest(form=wrapped[:12]):
                self.assertIsNone(scorer.LISTED_RE.match(wrapped))

    def test_no_line_in_either_file_shows_a_counts_line_in_a_form_the_scorer_rejects_but_the_template(self):
        scorer = load_scorer()
        base = al.texts_of()
        for name in (LEAD, TOP):
            template_lines = 0
            for number, line in enumerate(base[name].split("\n"), 1):
                if not COUNTS_SHAPE.search(line):
                    continue
                if line.strip() == "`" + TEMPLATE_LINE + "`" or line.strip() == "`" + TEMPLATE_LINE + "`.":
                    template_lines += 1
                    continue
                with self.subTest(file=name, line=number):
                    self.assertIsNotNone(scorer.LISTED_RE.match(line.replace("<n>", "7")), line)
            with self.subTest(file=name, what="template lines"):
                self.assertEqual(template_lines, 1)

    def test_a_counts_example_in_backticks_or_bold_added_to_either_file_is_found(self):
        base = al.texts_of()
        for name in (LEAD, TOP):
            for example in ("`Files listed: 40; read: 38; skipped: 0; re-dispatched: 0; failed: 1; unread: 1`",
                            "**Files listed: 40; read: 38; skipped: 0; re-dispatched: 0; failed: 1; unread: 1**",
                            "- Files listed: 40; read: 38; skipped: 0; re-dispatched: 0; failed: 1; unread: 1 (as a bullet)"):
                with self.subTest(file=name, example=example[:14]):
                    text = base[name] + "\n" + example + "\n"
                    rejected = [l for l in text.split("\n") if COUNTS_SHAPE.search(l)
                                and l.strip() not in ("`" + TEMPLATE_LINE + "`", "`" + TEMPLATE_LINE + "`.")
                                and not load_scorer().LISTED_RE.match(l)]
                    self.assertTrue(rejected)


# ---- C1: the architect case's `Security:` grader --------------------------------------------------------------------

class SecurityLineGraderBoundariesTest(unittest.TestCase):
    """C1: `n/a` as a word fails a plan, `n/a` inside a path, a word or a filename does not."""

    T = ec.NoUntouchedSecurityLineGraderTest

    def hit(self, line):
        meta = ec.pattern_of(self.T.ARCH, "no-untouched-security-line")
        return bool(ec.matches(meta, self.T.PLAN.replace("Security: none", line)))

    def test_a_stray_n_a_next_to_punctuation_or_markup_still_fails_the_plan(self):
        for line in ("Security: n/a.", "Security: N/A.", "Security: n/a;", "Security: n/a,", "Security: (n/a)",
                     "Security: [n/a]", "Security: **n/a**", "Security: `n/a`", 'Security: "n/a"', "Security: N/A",
                     "Security: n/a - nothing here", "Security: n/a: no inputs", "Security: n/a—none",
                     "Security: n/a, as no input reaches code", "Security: n/a (no new input)", "Security: n/a!",
                     "Security: input: n/a", "Security: auth: n/a", "Security: N/A for this change",
                     "- **Security:** n/a", "Security notes: N/A", "1. Security: n/a", "> Security: n/a"):
            with self.subTest(line=line):
                self.assertTrue(self.hit(line))

    def test_an_italic_n_a_still_fails_the_plan(self):
        """`_n/a_` is markdown italics for the same stray line; the old pattern caught it, the lookbehind on \\w lets it by."""
        for line in ("Security: _n/a_", "Security: __n/a__", "Security: _N/A_"):
            with self.subTest(line=line):
                self.assertTrue(self.hit(line))

    def test_a_real_line_that_names_a_path_or_a_split_is_passed(self):
        for line in ("Security: input from `a/b` reaches the parser; Task 1 bounds it",
                     "Security: the scan/apply split keeps the regex linear, and Task 1 bounds the input",
                     "Security: the `bin/n/a` helper reads caller text in Task 2",
                     "Security: input reaches `src/n/a.py` in Task 2, bounded there"):
            with self.subTest(line=line):
                self.assertFalse(self.hit(line))

    def test_today_a_real_line_that_quotes_n_a_as_a_value_is_failed(self):
        """Accepted limit: the word n/a as data (a column, a sentinel) reads as a stray line. The cost is a rewording."""
        for line in ("Security: the `n/a` column of the CSV reaches the parser in Task 2",
                     "Security: the N/A sentinel is parsed from a file in Task 1",
                     "Security: input is parsed in Task 1 (n/a is treated as empty)"):
            with self.subTest(line=line):
                self.assertTrue(self.hit(line))


# ---- C2: the nesting smoke's lead grader ----------------------------------------------------------------------------

class LeadGraderInputShapesTest(unittest.TestCase):
    """C2: the grader reads the subagent_type field of an Agent call's input, in any key order, and nothing else."""

    @classmethod
    def setUpClass(cls):
        cls.meta, _ = ec.read_markdown(ec.EXPENSIVE / "nesting-smoke" / "graders" / "lead-is-area-lead.md")

    def hit(self, payload, tool="Agent", separators=(",", ":"), indent=None):
        text = ec.json.dumps(payload, separators=separators, indent=indent)
        return bool(ec.re.search(self.meta["input_match"], text)) and self.meta["tool"] == tool

    def test_the_field_matches_in_any_key_order_and_any_json_spacing(self):
        name = "the-foundry:area-lead"
        for payload in ({"subagent_type": name, "prompt": "x"}, {"prompt": "x", "subagent_type": name},
                        {"description": "d", "prompt": "x", "subagent_type": name, "extra": 1},
                        {"subagent_type": name}):
            for separators, indent in (((",", ":"), None), ((", ", ": "), None), ((",", ": "), 2)):
                with self.subTest(payload=list(payload), separators=separators):
                    self.assertTrue(self.hit(payload, separators=separators, indent=indent))

    def test_the_bare_name_and_look_alike_names_do_not_match(self):
        for name in ("area-lead", "the-foundry:area-lead-2", "xthe-foundry:area-lead", "the-foundry:area-leads",
                     "The-Foundry:Area-Lead", "the-foundry:investigate", "the-foundry:file-reader", "", None):
            with self.subTest(name=name):
                self.assertFalse(self.hit({"subagent_type": name, "prompt": "x"}))

    def test_a_mention_of_the_name_anywhere_but_the_field_does_not_match(self):
        name = "the-foundry:area-lead"
        for payload in ({"subagent_type": "area-lead", "prompt": "the-foundry:area-lead"},
                        {"subagent_type": "area-lead", "description": name},
                        {"subagent_type": "the-foundry:investigate", "prompt": '{"subagent_type": "%s"}' % name},
                        {"subagent_type": "the-foundry:investigate", "prompt": '"subagent_type":"%s"' % name},
                        {"subagent_type": "the-foundry:investigate", "prompt": 'subagent_type: ' + name},
                        {"prompt": "x", "type": name}, {"subagent": name}, {"my_subagent_type": name}):
            with self.subTest(payload=str(payload)[:50]):
                self.assertFalse(self.hit(payload))

    def test_the_grader_asks_for_an_agent_call_only(self):
        self.assertEqual(self.meta["tool"], "Agent")
        self.assertFalse(self.hit({"subagent_type": "the-foundry:area-lead"}, tool="Bash"))

    def test_today_a_nested_field_of_the_same_name_matches(self):
        """Accepted limit: the grader searches the whole input as text, so a nested object that carries the field counts."""
        self.assertTrue(self.hit({"subagent_type": "the-foundry:investigate", "meta": {"subagent_type": "the-foundry:area-lead"}}))


if __name__ == "__main__":
    unittest.main()
