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


if __name__ == "__main__":
    unittest.main()


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
