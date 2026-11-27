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


if __name__ == "__main__":
    unittest.main()
