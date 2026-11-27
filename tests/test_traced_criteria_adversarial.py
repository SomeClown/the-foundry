"""Adversarial round on the traced acceptance criteria (Tasks 1 and 2 of the plan
docs/plans/2026-11-26-traced-acceptance-criteria.md).

Covers, by id (the design's Done when items this round attacks):
- AC-4: qa's spec check gives each id a line in one of five shapes, and `NOT MET` or `UNTESTED` makes it GAPS.
- AC-7: three eval cases carry ids and have exact graders, and tests hold the graders and the label names to the agent texts.
- AC-8: the shared `## How Every Report Opens` section says `Status:` is the first line, with no summary sentence above it, in all eight carriers.

Two kinds of test live here. A plain assertion states what the rule or grader should do; if it fails,
the failure is a gap to report. A test whose name says "is accepted today" or "is refused today" pins what
the code does now, so a change to it is noticed; those are decisions, not claims of correctness.

Nothing is written to the repo and nothing under ~/.claude or ~/.foundry is read. The node checks skip when
node isn't installed. Standard library only; Python 3.9 and later.
"""
import io
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_eval_cases as T  # noqa: E402
import test_traced_criteria as TC  # noqa: E402
from test_security_rules import agent_texts, fold  # noqa: E402

ROOT = TC.ROOT
ARCH, BRAIN, QA = T.TracedCriteriaCaseTest.ARCH, T.TracedCriteriaCaseTest.BRAIN, T.TracedCriteriaCaseTest.QA
QA_GRADERS = ("ac-1-met", "ac-2-not-met", "ac-3-untested")
ARCH_GRADERS = ("covers-line", "coverage-lines")
ALL_GRADERS = [(QA, n) for n in QA_GRADERS] + [(ARCH, n) for n in ARCH_GRADERS] + [(BRAIN, "done-when-list")]


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = TC.all_texts()
        assert TC.problems(cls.base) == []

    def edited(self, name, fn):
        texts = dict(self.base)
        new = fn(texts[name])
        self.assertNotEqual(new, texts[name], "the edit changed nothing")
        texts[name] = new
        return texts

    def appended(self, name, extra):
        return self.edited(name, lambda t: t + extra)

    def assertCaught(self, texts, needle):
        found = TC.problems(texts)
        self.assertTrue(any(needle in p for p in found), found)

    def assertQuiet(self, texts):
        self.assertEqual(TC.problems(texts), [])


class LabelSpellingTest(Base):
    """AC-7: the label names are held to the agent texts (rules a and b)."""

    def test_covers_with_the_colon_inside_the_bold_is_not_the_label(self):
        texts = self.edited("frontend", lambda t: t.replace(TC.COVERS, "**Covers:**"))
        self.assertCaught(texts, "frontend doesn't mention")

    def test_covers_with_no_bold_is_not_the_label(self):
        texts = self.edited("qa", lambda t: t.replace(TC.COVERS, "Covers"))
        self.assertCaught(texts, "qa doesn't mention")

    def test_a_done_whenever_prefix_is_accepted_today(self):
        # the session ruled the label is the prefix `**Done when`; this pins what that lets through
        texts = self.edited("orchestrator", lambda t: t.replace(TC.DONE_WHEN, "**Done whenever"))
        self.assertQuiet(texts)

    def test_a_done_when_in_a_code_span_is_accepted_today(self):
        texts = self.edited("qa", lambda t: t.replace(TC.DONE_WHEN, "`**Done when"))
        self.assertQuiet(texts)

    def test_a_done_when_in_an_unrelated_sentence_is_accepted_today(self):
        texts = self.edited("architect", lambda t: t.replace(TC.DONE_WHEN, "the **Done when of the tea"))
        self.assertQuiet(texts)

    def test_covers_in_a_code_span_is_accepted_today(self):
        texts = self.edited("run-plan", lambda t: t.replace(TC.COVERS, "`**Covers**`"))
        self.assertQuiet(texts)

    def test_a_missing_agent_is_a_problem_not_a_crash(self):
        texts = dict(self.base)
        del texts["frontend"]
        self.assertCaught(texts, "frontend doesn't mention")
        self.assertCaught(texts, "lacks the")


class IdSpellingTest(Base):
    """AC-7: every `AC-` in the texts is a well-formed id (rule f)."""

    def test_these_spellings_are_caught(self):
        for spelling in ("AC1", "AC-1a", "AC-", "AC-x", "AC-n1", "AC12"):
            with self.subTest(spelling=spelling):
                self.assertCaught(self.appended("brainstorm", "\nSee %s now.\n" % spelling), "writes an id as")

    def test_an_id_at_a_line_end_with_no_number_is_caught(self):
        self.assertCaught(self.appended("architect", "\nthe id is AC-"), "writes an id as")

    def test_well_formed_ids_pass(self):
        for good in ("AC-1", "AC-10", "AC-n", "AC-N", "AC-1:", "(AC-2)", "`AC-3`"):
            with self.subTest(good=good):
                self.assertQuiet(self.appended("brainstorm", "\nSee %s now.\n" % good))

    def test_a_leading_zero_id_is_caught(self):
        self.assertCaught(self.appended("brainstorm", "\nSee AC-01 now.\n"), "writes an id as")

    def test_a_space_before_the_dash_is_caught(self):
        self.assertCaught(self.appended("brainstorm", "\nSee AC -1 now.\n"), "writes an id")

    def test_a_lowercase_id_is_caught(self):
        self.assertCaught(self.appended("brainstorm", "\nSee ac-1 now.\n"), "writes an id")


class IdStateRuleTest(Base):
    """AC-4: the id states other texts name are qa's five (rule d)."""

    def test_invented_states_are_caught_in_each_of_the_three_texts(self):
        for name in ("run-plan", "architect", "orchestrator"):
            for state in ("MISSING", "PARTIAL", "HALF MET", "NOT YET MET"):
                with self.subTest(text=name, state=state):
                    self.assertCaught(self.appended(name, "\nAC-2 %s here.\n" % state), "names the id state %r" % state)

    def test_an_invented_state_on_the_line_after_its_id_is_quiet_today(self):
        # a recorded ruling: rule (d) reads a state from the id's own line only, and the loss was accepted
        self.assertQuiet(self.appended("run-plan", "\nthe id AC-2\nMISSING again\n"))

    def test_a_state_after_a_template_id_is_caught(self):
        self.assertCaught(self.appended("orchestrator", "\nAC-n BLOCKED when\n"), "'BLOCKED'")

    def test_the_five_real_states_are_quiet(self):
        text = "\nAC-2 MET and AC-2 NOT MET, AC-2 UNTESTED, AC-2 CANNOT VERIFY, AC-2 DROPPED.\n"
        for name in ("run-plan", "architect", "orchestrator"):
            with self.subTest(text=name):
                self.assertQuiet(self.appended(name, text))

    def test_not_met_followed_by_a_capitalized_word_is_quiet(self):
        for tail in ("Then the", "Every other", "Tasks 2 and 4"):
            with self.subTest(tail=tail):
                self.assertQuiet(self.appended("run-plan", "\n`AC-2 NOT MET`. %s rest.\n" % tail))

    def test_an_id_that_opens_a_sentence_is_quiet(self):
        for sentence in ("AC-2 IS covered by Task 1.", "AC-2 is met.", "AC-2 stays."):
            with self.subTest(sentence=sentence):
                self.assertQuiet(self.appended("orchestrator", "\n%s\n" % sentence))

    def test_a_state_line_followed_by_an_all_caps_word_on_the_next_line_is_quiet(self):
        # the rule folds line breaks, so `AC-2 MET` then a line holding `API notes` reads as the state `MET API`
        self.assertQuiet(self.appended("run-plan", "\n`AC-2 MET`\nAPI notes follow.\n"))
        self.assertQuiet(self.appended("run-plan", "\nit says AC-2 MET\nAPI notes follow.\n"))

    def test_a_state_followed_by_an_all_caps_word_in_the_same_sentence_is_quiet(self):
        self.assertQuiet(self.appended("run-plan", "\nAC-2 MET, see the README.\n"))


class FixRoundOneTest(Base):
    """AC-4 and AC-7: holes the fix round might have opened in rules (d) and (f)."""

    def test_a_valid_state_wrapped_between_its_words_is_quiet(self):
        self.assertQuiet(self.appended("run-plan", "\nA finding of `AC-2 NOT\nMET` keeps the id.\n"))

    def test_an_id_at_a_line_end_then_a_caps_word_on_the_next_line_is_quiet(self):
        self.assertQuiet(self.appended("run-plan", "\nit covers AC-2\nAPI work.\n"))

    def test_the_word_ac_before_a_line_break_and_a_bullet_is_quiet(self):
        self.assertQuiet(self.appended("orchestrator", "\nthe unit is ac\n- a bullet\n"))


class SpecFenceRuleTest(Base):
    """AC-4: qa's spec fence holds the five id shapes, in order, then the four bracket lines (rule c)."""

    def qa_edit(self, fn):
        return self.edited("qa", fn)

    def test_two_id_lines_swapped_are_caught(self):
        def swap(t):
            a, b = "AC-n UNTESTED file:line: met, but no test asserts it and no reason is recorded\n", "AC-n CANNOT VERIFY: why\n"
            return t.replace(a + b, b + a, 1)
        self.assertCaught(self.qa_edit(swap), "out of shape")

    def test_an_id_line_after_the_bracket_lines_is_caught(self):
        def move(t):
            return t.replace("AC-n DROPPED\n", "", 1).replace("[CANNOT VERIFY] requirement", "AC-n DROPPED\n[CANNOT VERIFY] requirement", 1)
        self.assertCaught(self.qa_edit(move), "out of shape")

    def test_each_one_line_missing_is_caught(self):
        for needle in ("AC-n MET file", "AC-n NOT MET:", "AC-n UNTESTED", "AC-n CANNOT VERIFY:", "AC-n DROPPED", "[MISSING]",
                       "[EXTRA]", "[DIFFERENT]", "[CANNOT VERIFY] requirement"):
            with self.subTest(line=needle):
                def drop(t, needle=needle):
                    lines = t.split("\n")
                    i = next(n for n, l in enumerate(lines) if l.startswith(needle))
                    del lines[i]
                    return "\n".join(lines)
                self.assertCaught(self.qa_edit(drop), "out of shape")

    def test_an_extra_id_shape_is_caught(self):
        add = lambda t: t.replace("AC-n DROPPED\n", "AC-n DROPPED\nAC-n PARTIAL: some\n", 1)  # noqa: E731
        self.assertCaught(self.qa_edit(add), "out of shape")

    def test_a_duplicated_id_shape_is_caught(self):
        add = lambda t: t.replace("AC-n DROPPED\n", "AC-n DROPPED\nAC-n DROPPED\n", 1)  # noqa: E731
        self.assertCaught(self.qa_edit(add), "out of shape")

    def test_a_trailing_word_on_the_dropped_line_is_caught(self):
        add = lambda t: t.replace("AC-n DROPPED\n", "AC-n DROPPED today\n", 1)  # noqa: E731
        self.assertCaught(self.qa_edit(add), "out of shape")

    def test_another_fence_between_the_anchor_and_the_spec_fence_is_caught(self):
        add = lambda t: t.replace("(see How Every Report Opens):\n", "(see How Every Report Opens):\n\n```\nsome other fence\n```\n", 1)  # noqa: E731
        self.assertCaught(self.qa_edit(add), "out of shape")

    def test_the_anchor_sentence_gone_is_caught(self):
        self.assertCaught(self.qa_edit(lambda t: t.replace("Put a spec section first", "Put a spec part first")), "no spec fence")

    def test_an_unclosed_fence_is_caught(self):
        def unclose(t):
            i = t.index("Put a spec section first")
            j = t.index("\n```\n", t.index("[CANNOT VERIFY] requirement", i)) + 1
            return t[:j] + t[j + 4:]
        texts = self.qa_edit(unclose)
        self.assertTrue(TC.problems(texts))

    def test_a_changed_first_fence_line_is_caught(self):
        # the fence helper drops line one as the `Spec:` line without looking at it
        self.assertCaught(self.qa_edit(lambda t: t.replace("Spec: MATCHES | GAPS\nAC-n MET", "Whatever\nAC-n MET", 1)), "spec")

    def test_the_closing_sentence_dropped_is_caught(self):
        # AC-4: `NOT MET` or `UNTESTED` makes it GAPS; no rule holds the sentence that says so
        drop = lambda t: t.replace("Any `NOT MET` or `UNTESTED` line makes it GAPS.", "", 1)  # noqa: E731
        self.assertTrue(TC.problems(self.qa_edit(drop)))

    def test_a_state_renamed_inside_the_fence_is_caught_in_two_places(self):
        texts = self.qa_edit(lambda t: t.replace("AC-n NOT MET:", "AC-n MISSING:", 1))
        found = TC.problems(texts)
        self.assertTrue(any("out of shape" in p for p in found), found)
        self.assertTrue(any("names the id state 'NOT MET'" in p for p in found), found)


class BulletRuleTest(Base):
    """AC-3 and AC-4 depend on it: implement and frontend say the same Covers bullet (rule e)."""

    def test_whitespace_only_differences_hold(self):
        for old, new in (("one line per id:", "one  line   per id:"), ("one line per id:\n", "one line\n  per id:\n"),
                         ("one line per id:", "one\tline per id:")):
            with self.subTest(new=repr(new)):
                self.assertQuiet(self.edited("frontend", lambda t: t.replace(old, new, 1)))

    def test_one_word_differing_in_implement_is_caught(self):
        self.assertCaught(self.edited("implement", lambda t: t.replace("one line per id", "a line per id", 1)), "differs")

    def test_each_of_the_two_code_spans_changed_is_caught(self):
        for old, new in (("`AC-n: met at <file:line>`", "`AC-n: met at <file>`"), ("`AC-n: not met: <why>`", "`AC-n: not met`")):
            with self.subTest(old=old):
                self.assertCaught(self.edited("frontend", lambda t: t.replace(old, new, 1)), "differs")

    def test_the_em_dash_as_a_hyphen_is_caught_in_either_agent(self):
        for name in ("implement", "frontend"):
            with self.subTest(agent=name):
                self.assertCaught(self.edited(name, lambda t: t.replace(TC.COVERS_BULLET, TC.COVERS_BULLET.replace("—", "-"), 1)), "lacks")

    def test_an_en_dash_is_caught(self):
        self.assertCaught(self.edited("frontend", lambda t: t.replace(TC.COVERS_BULLET, TC.COVERS_BULLET.replace("—", "–"), 1)), "lacks")

    def test_an_extra_wrapped_line_in_the_bullet_is_caught(self):
        add = lambda t: t.replace("`AC-n: not met: <why>`\n", "`AC-n: not met: <why>`\n  and then some\n", 1)  # noqa: E731
        self.assertCaught(self.edited("frontend", add), "differs")

    def test_a_dash_swapped_deeper_in_the_bullet_is_caught(self):
        self.assertCaught(self.edited("implement", lambda t: t.replace("`AC-n: met at", "`AC-n; met at", 1)), "differs")

    def test_a_non_breaking_space_difference_is_folded_away_today(self):
        # the plan compares the bullets "whitespace folded", and a non-breaking space is whitespace
        self.assertQuiet(self.edited("frontend", lambda t: t.replace("one line per id:", "one\u00a0line per id:", 1)))

    def test_the_bullet_text_is_not_empty_and_stops_at_the_next_bullet(self):
        for name in ("implement", "frontend"):
            with self.subTest(agent=name):
                b = TC.covers_bullet(self.base[name])
                self.assertIn("one line per id", b)
                self.assertNotIn("How it was verified", b)

    def test_the_bullet_changed_in_both_agents_the_same_way_is_still_equal(self):
        def both(t):
            return t.replace("one line per id", "one line for each id", 1)
        texts = self.edited("implement", both)
        texts["frontend"] = both(texts["frontend"])
        self.assertQuiet(texts)


class RulesBiteTest(Base):
    """Each rule, (a) to (g), fails on its own mutation and says so under its own name."""

    MUTATIONS = {
        "a": ("frontend", lambda t: t.replace(TC.COVERS, "**Cover**"), "doesn't mention %s" % TC.COVERS),
        "b": ("orchestrator", lambda t: t.replace(TC.DONE_WHEN, "**Done"), "doesn't mention %s" % TC.DONE_WHEN),
        "c": ("qa", lambda t: t.replace("AC-n UNTESTED ", "AC-n UNTESTED_ ", 1), "out of shape"),
        "d": ("architect", lambda t: t + "\nAC-3 PENDING\n", "names the id state 'PENDING'"),
        "e": ("frontend", lambda t: t.replace("per id:", "per ids:", 1), "differs between"),
        "f": ("run-plan", lambda t: t + "\nAC1\n", "writes an id as"),
        "g": ("architect", lambda t: t.replace("`AC-n: Task N; test`", "`AC-n: Task`", 1), "coverage line"),
    }

    def test_each_mutation_is_reported_by_its_own_rule(self):
        for rule, (name, fn, needle) in sorted(self.MUTATIONS.items()):
            with self.subTest(rule=rule):
                found = TC.problems(self.edited(name, fn))
                self.assertTrue(found, "rule (%s) did not notice its mutation" % rule)
                self.assertTrue(any(needle in p for p in found), found)

    def test_with_a_rule_removed_its_mutation_goes_unnoticed(self):
        # a copy of problems() with one rule's lines left out: the mutation must then slip through, so the rule is what catches it
        src = Path(TC.__file__).read_text(encoding="utf-8")
        body = src[src.index("def problems(texts):"):src.index("class RealTreeTest")]
        cuts = {
            "a": ("    for name in COVERS_IN:\n", "    for name in DONE_WHEN_IN:\n"),
            "b": ("    for name in DONE_WHEN_IN:\n", "    fence = spec_fence"),
            "e": ("    a, b = covers_bullet", "    for name, text in texts.items():\n"),
            "f": ("    for name, text in texts.items():\n", '    if "`AC-n: Task N; test`"'),
            "g": ('    if "`AC-n: Task N; test`"', "    return found"),
        }
        for rule, (start, end) in cuts.items():
            with self.subTest(rule=rule):
                i = body.index(start)
                j = body.index(end, i + len(start))
                gutted = body[:i] + body[j:]
                scope = dict(vars(TC))
                exec(compile(gutted, "<gutted %s>" % rule, "exec"), scope)
                name, fn, needle = self.MUTATIONS[rule]
                texts = self.edited(name, fn)
                self.assertEqual(scope["problems"](self.base), [])
                self.assertFalse(any(needle in p for p in scope["problems"](texts)))
                self.assertTrue(any(needle in p for p in TC.problems(texts)))


NODE = shutil.which("node")


class GraderFixtureTest(unittest.TestCase):
    """AC-7: a grader can't be satisfied by the case's own fixture or prompt, raw or JSON-escaped."""

    def corpus(self, case):
        fx = T.Fixture(self, case)
        items = []
        for p in sorted(fx.dir.rglob("*")):
            if p.is_file() and ".git" not in p.relative_to(fx.dir).parts:
                items.append((str(p.relative_to(fx.dir)), p.read_text(encoding="utf-8", errors="replace")))
        items.append(("prompt.md", (T.EVALS / case / "prompt.md").read_text(encoding="utf-8")))
        out = []
        for name, text in items:
            out.append((name, text))
            out.append((name + " (json)", json.dumps(text)))
            out.append((name + " (json, no ascii escape)", json.dumps(text, ensure_ascii=False)))
            out.append((name + " (as a trace event)", json.dumps({"type": "user", "content": text}, separators=(",", ":"))))
            out.append((name + " (as a hand-back)", T.hand_back(text)))
        return out

    def test_no_new_grader_matches_any_fixture_file_or_prompt_of_its_case(self):
        for case, name in ALL_GRADERS:
            meta = T.pattern_of(case, name)
            for label, text in self.corpus(case):
                with self.subTest(grader=name, text=label):
                    self.assertFalse(T.matches(meta, text), "%s matches %s" % (name, label))

    def test_no_grader_matches_an_agent_skill_or_doc_text_a_session_may_load(self):
        texts = dict(TC.all_texts())
        for p in sorted((ROOT / "skills").glob("*/SKILL.md")) + [ROOT / "README.md", ROOT / "docs" / "orchestrator.md"]:
            if p.exists():
                texts[str(p.relative_to(ROOT))] = p.read_text(encoding="utf-8")
        for case, name in ALL_GRADERS:
            if name == "done-when-list":
                continue  # it reads the written design file, never the trace
            meta = T.pattern_of(case, name)
            for label, text in sorted(texts.items()):
                for form, body in (("raw", text), ("json", json.dumps(text)), ("hand-back", T.hand_back(text))):
                    with self.subTest(grader=name, text=label, form=form):
                        self.assertFalse(T.matches(meta, body))


def spec(*lines):
    return "\n".join(("Spec: GAPS",) + lines)


class QaGraderShapeTest(unittest.TestCase):
    """AC-4 and AC-7: the three qa graders read the id lines of a hand-back and refuse the wrong ones."""

    def grader(self, name):
        return T.pattern_of(QA, name)

    def hit(self, name, report):
        return bool(T.matches(self.grader(name), T.hand_back(report)))

    def test_decorated_id_lines_match(self):
        for line in ("AC-1 MET f.py:1; t", "- AC-1 MET f.py:1; t", "  AC-1 MET f.py:1; t", "> AC-1 MET f.py:1; t",
                     "**AC-1 MET** f.py:1", "`AC-1 MET` f.py:1", "* AC-1 MET f.py:1", "> - AC-1 MET"):
            with self.subTest(line=line):
                self.assertTrue(self.hit("ac-1-met", spec(line)))

    def test_a_bold_id_followed_by_the_state_matches(self):
        for line in ("**AC-1** MET f.py:1", "- **AC-1** MET f.py:1", "AC-1: MET f.py:1", "- `AC-1` MET f.py:1"):
            with self.subTest(line=line):
                self.assertTrue(self.hit("ac-1-met", spec(line)))

    def test_a_numbered_list_id_line_matches(self):
        self.assertTrue(self.hit("ac-1-met", spec("1. AC-1 MET f.py:1")))

    def test_the_state_of_another_id_does_not_satisfy_a_grader(self):
        self.assertFalse(self.hit("ac-1-met", spec("AC-2 MET f.py:1", "AC-3 MET f.py:2")))
        self.assertFalse(self.hit("ac-2-not-met", spec("AC-1 NOT MET: x", "AC-3 NOT MET: y")))
        self.assertFalse(self.hit("ac-3-untested", spec("AC-1 UNTESTED f.py:1: x", "AC-2 UNTESTED f.py:2: x")))

    def test_a_wrong_state_for_the_right_id_does_not_satisfy(self):
        self.assertFalse(self.hit("ac-1-met", spec("AC-1 NOT MET: x")))
        self.assertFalse(self.hit("ac-1-met", spec("AC-1 UNTESTED f.py:1: x")))
        self.assertFalse(self.hit("ac-1-met", spec("AC-1 CANNOT VERIFY: x")))
        self.assertFalse(self.hit("ac-2-not-met", spec("AC-2 MET f.py:1; t")))
        self.assertFalse(self.hit("ac-2-not-met", spec("AC-2 UNTESTED f.py:1: x")))
        self.assertFalse(self.hit("ac-3-untested", spec("AC-3 NOT MET: x")))

    def test_longer_ids_and_words_do_not_stand_in(self):
        self.assertFalse(self.hit("ac-1-met", spec("AC-11 MET f.py:1")))
        self.assertFalse(self.hit("ac-1-met", spec("AC-1 METHOD f.py:1")))
        self.assertFalse(self.hit("ac-1-met", spec("AC-1 METAL")))
        self.assertFalse(self.hit("ac-2-not-met", spec("AC-22 NOT MET: x")))
        self.assertFalse(self.hit("ac-2-not-met", spec("AC-2 NOT METHODICAL")))
        self.assertFalse(self.hit("ac-3-untested", spec("AC-33 UNTESTED f.py:1: x")))
        self.assertFalse(self.hit("ac-3-untested", spec("AC-3 UNTESTEDLY")))

    def test_an_id_in_the_middle_of_a_line_does_not_satisfy_a_grader(self):
        self.assertFalse(self.hit("ac-1-met", spec("the check says AC-1 MET, I think")))
        self.assertFalse(self.hit("ac-2-not-met", spec("Summary: AC-2 NOT MET: x")))

    def test_a_state_word_lowercased_does_not_satisfy_a_grader(self):
        self.assertFalse(self.hit("ac-1-met", spec("AC-1 met f.py:1")))
        self.assertFalse(self.hit("ac-2-not-met", spec("AC-2 not met: x")))

    def test_the_first_line_of_the_report_counts_after_the_frame(self):
        # the frame sentence ends in a newline and the report's own first line is indented
        self.assertTrue(self.hit("ac-1-met", "AC-1 MET f.py:1; t"))

    def test_a_line_in_an_unframed_raw_trace_still_matches(self):
        for name, text in (("ac-1-met", "x\nAC-1 MET f"), ("ac-2-not-met", "x\n  AC-2 NOT MET: y"), ("ac-3-untested", "x\n- AC-3 UNTESTED f")):
            with self.subTest(grader=name):
                self.assertTrue(T.matches(self.grader(name), text))

    def test_an_id_line_at_the_very_start_of_a_trace_does_not_match(self):
        # no newline before it; a real trace always has a frame first
        self.assertFalse(T.matches(self.grader("ac-1-met"), "AC-1 MET f"))

    def test_crlf_line_endings_still_match(self):
        self.assertTrue(T.matches(self.grader("ac-2-not-met"), "x\r\nAC-2 NOT MET: y"))

    def test_the_weights_are_two_on_the_two_heavy_graders_only(self):
        self.assertEqual([T.pattern_of(QA, n).get("weight", 1) for n in QA_GRADERS], [1, 2, 2])


class ArchitectGraderShapeTest(unittest.TestCase):
    """AC-7: covers-line and coverage-lines read the plan as a trace carries it."""

    def covers(self, text):
        return bool(T.matches(T.pattern_of(ARCH, "covers-line"), text))

    def coverage(self, text):
        return bool(T.matches(T.pattern_of(ARCH, "coverage-lines"), text))

    def both_forms(self, text):
        return (text, json.dumps(text), json.dumps(text, ensure_ascii=False))

    def test_covers_then_sub_bullets_match_raw_and_escaped(self):
        for text in self.both_forms("- **Covers:**\n  - AC-1: the pairs.\n  - AC-2: n.\n"):
            with self.subTest(text=text[:30]):
                self.assertTrue(self.covers(text))

    def test_covers_without_a_colon_then_sub_bullets_match(self):
        for text in self.both_forms("- **Covers**\n  - AC-1: the pairs.\n"):
            self.assertTrue(self.covers(text))

    def test_covers_with_blank_lines_before_the_bullets_match(self):
        for text in self.both_forms("- **Covers:**\n\n  - AC-1: x\n"):
            self.assertTrue(self.covers(text))

    def test_covers_with_an_em_dash_matches_raw(self):
        self.assertTrue(self.covers("- **Covers** — AC-1: the pairs."))
        self.assertTrue(self.covers("- **Covers** —\n  - AC-1: the pairs."))
        self.assertTrue(self.covers(json.dumps("- **Covers** —\n  - AC-1: x", ensure_ascii=False)))

    def test_covers_with_an_em_dash_matches_in_ascii_escaped_json(self):
        # json.dumps escapes the dash as — by default, and the T.hand_back helper does the same
        self.assertTrue(self.covers(json.dumps("- **Covers** — AC-1: the pairs.")))
        self.assertTrue(self.covers(json.dumps("- **Covers** —\n  - AC-1: the pairs.")))

    def test_covers_with_bold_and_code_decorations_match(self):
        for text in ("**Covers:** `AC-1`", "**Covers:** **AC-1**", "**Covers** - AC-1", "**Covers:**\n  * AC-1: x", "**Covers:**\n- `AC-1: x`"):
            with self.subTest(text=text):
                self.assertTrue(self.covers(text))

    def test_covers_with_none_or_prose_does_not_match(self):
        for text in ("- **Covers** — none: groundwork", "**Covers** the ids; AC-1 is here", "**Covers:** none\n  - Files: AC-1",
                     "**Covers**: nothing\n\nAC-1: later"):
            with self.subTest(text=text):
                self.assertFalse(self.covers(text))

    def test_covers_label_without_bold_does_not_match(self):
        self.assertFalse(self.covers("Covers: AC-1"))
        self.assertFalse(self.covers("**Cover** AC-1"))

    def test_covers_then_a_task_heading_then_an_id_does_not_match(self):
        self.assertFalse(self.covers("**Covers:** none\n### Task 2\nAC-1"))

    def test_a_multi_digit_id_after_covers_matches(self):
        self.assertTrue(self.covers("**Covers:** AC-12: x"))

    def test_coverage_needs_all_three_ids(self):
        full = ["AC-1: Task 1; test", "AC-2: Task 1; test", "AC-3: Task 2; test"]
        for drop in range(3):
            text = "\n".join(l for n, l in enumerate(full) if n != drop)
            for form in self.both_forms(text):
                with self.subTest(dropped=drop):
                    self.assertFalse(self.coverage(form))
        for form in self.both_forms("\n".join(full)):
            self.assertTrue(self.coverage(form))

    def test_coverage_with_a_task_list_matches(self):
        for line in ("AC-1: Tasks 2 and 4; test", "AC-1: Tasks 1, 2; command: x", "`AC-1: Task 3; by hand: y`", "**AC-1**: Task 1; test",
                     "- AC-1: Task 1; test", "§16 AC-1: Task 1; test"):
            with self.subTest(line=line):
                text = line + "\nAC-2: Task 1; test\nAC-3: Task 1; test"
                for form in self.both_forms(text):
                    self.assertTrue(self.coverage(form))

    def test_a_longer_id_does_not_stand_in_for_a_shorter_one(self):
        text = "AC-10: Task 1; test\nAC-2: Task 1; test\nAC-3: Task 1; test"
        self.assertFalse(self.coverage(text))
        text = "AC-1: Task 1; test\nAC-20: Task 1; test\nAC-3: Task 1; test"
        self.assertFalse(self.coverage(text))
        text = "AC-1: Task 1; test\nAC-2: Task 1; test\nAC-30: Task 1; test"
        self.assertFalse(self.coverage(text))

    def test_a_dropped_or_taskless_line_does_not_count(self):
        full = "AC-1: Task 1; test\nAC-2: Task 1; test\n"
        self.assertFalse(self.coverage(full + "AC-3: dropped"))
        self.assertFalse(self.coverage(full + "AC-3: no task yet"))
        self.assertFalse(self.coverage(full + "AC-3 — Task 2; test"))
        self.assertFalse(self.coverage(full + "AC-3: task 2; test"))

    def test_a_covers_sub_bullet_with_a_task_word_counts_as_a_coverage_line_today(self):
        # the pattern looks for `AC-n: Task N` anywhere, so a Covers sub-bullet that mentions a task satisfies it
        text = "**Covers:**\n  - AC-1: Task 1 returns the pairs.\n  - AC-2: Task 2 raises.\n  - AC-3: Task 3 sets the version."
        self.assertTrue(self.coverage(text))

    def test_a_colon_inside_the_bold_is_refused_today(self):
        self.assertFalse(self.coverage("**AC-1:** Task 1\n**AC-2:** Task 1\n**AC-3:** Task 1"))

    def test_the_weight_is_three(self):
        self.assertEqual(T.pattern_of(ARCH, "coverage-lines")["weight"], 3)


class DoneWhenGraderShapeTest(unittest.TestCase):
    """AC-1 and AC-7: done-when-list reads the written design file."""

    def hit(self, text):
        return bool(T.matches(T.pattern_of(BRAIN, "done-when-list"), text))

    def test_a_list_under_section_three_matches_in_each_label_spelling(self):
        for label in ("**Done when:**", "**Done when**", "**Done when:** (approved)"):
            with self.subTest(label=label):
                self.assertTrue(self.hit("## 3. Recap (v1)\n\nx\n\n%s\n- AC-1: a\n- AC-2: b\n" % label))

    def test_a_numbered_list_with_bold_ids_matches(self):
        self.assertTrue(self.hit("## 3. Recap\n**Done when:**\n1. **AC-1:** a\n2. **AC-2:** b\n"))

    def test_a_done_when_list_in_an_earlier_section_does_not_match(self):
        design = "## 1. A\n**Done when:**\n- AC-1: a\n- AC-2: b\n\n## 2. B\nText.\n\n## 3. C\nNo list yet.\n"
        self.assertFalse(self.hit(design))

    def test_a_list_under_a_later_section_does_not_match(self):
        design = "## 3. C\nNo list.\n\n## 4. D\n**Done when:**\n- AC-1: a\n- AC-2: b\n"
        self.assertFalse(self.hit(design))

    def test_a_list_under_section_three_when_an_earlier_section_has_one_matches(self):
        design = "## 1. A\n**Done when:**\n- AC-1: a\n\n## 3. C\n**Done when:**\n- AC-1: a\n- AC-2: b\n"
        self.assertTrue(self.hit(design))

    def test_longer_ids_do_not_stand_in(self):
        self.assertFalse(self.hit("## 3. C\n**Done when:**\n- AC-10: a\n- AC-20: b\n"))
        self.assertFalse(self.hit("## 3. C\n**Done when:**\n- AC-1: a\n"))
        self.assertFalse(self.hit("## 3. C\n**Done when:**\n- AC-2: b\n- AC-1: a\n"))

    def test_the_header_for_section_three_in_another_shape_matches(self):
        self.assertTrue(self.hit("## 3. Recap\n**Done when:**\n- AC-1: a\n- AC-2: b"))
        self.assertTrue(self.hit("## 3. Recap\n\n**Done when:**\r\n- AC-1: a\r\n- AC-2: b"))

    def test_a_third_level_header_for_section_three_does_not_match(self):
        self.assertFalse(self.hit("### 3. Recap\n**Done when:**\n- AC-1: a\n- AC-2: b\n"))

    def test_a_list_with_the_label_in_plain_text_does_not_match(self):
        self.assertFalse(self.hit("## 3. Recap\nDone when:\n- AC-1: a\n- AC-2: b\n"))

    def test_a_section_three_wording_inside_a_sentence_does_not_match(self):
        # the pattern starts at a second-level `## 3. ` heading at a line start
        self.assertFalse(self.hit("see ## 3. above. **Done when** AC-1 and AC-2"))

    def test_a_subheading_inside_section_three_keeps_the_list_in_section_three(self):
        self.assertTrue(self.hit("## 3. C\n### 3.1 Part\n**Done when:**\n- AC-1: a\n- AC-2: b\n"))


@unittest.skipUnless(NODE, "node isn't installed")
class PatternEngineTest(unittest.TestCase):
    """AC-7: the six patterns mean the same in JavaScript, the engine the harness uses."""

    CORPUS = [
        T.hand_back(T.TracedCriteriaCaseTest.SPEC),
        T.hand_back("Spec: GAPS\n**AC-1 MET** f\n- AC-2 NOT MET: x\n> AC-3 UNTESTED f: x"),
        T.hand_back("Spec: MATCHES\nAC-11 MET f\nAC-1 METHOD\nAC-22 NOT MET: x\nAC-3 untested"),
        json.dumps(T.TracedCriteriaCaseTest.PLAN),
        json.dumps("- **Covers** — AC-1: x\nAC-1: Tasks 2 and 4\nAC-2: Task 1\nAC-3: Task 1"),
        "- **Covers:**\n  - AC-1: x",
        "**Covers** AC-1\nAC-10: Task 1\nAC-2: Task 1\nAC-3: Task 1",
        "## 3. Recap\n**Done when:**\n- AC-1: a\n- AC-2: b\n",
        "## 3. Recap\r\n**Done when:**\r\n- AC-1: a\r\n- AC-2: b\r\n",
        "## 4. D\n**Done when:**\n- AC-1: a\n- AC-2: b\n",
    ]

    def test_node_agrees_with_python_on_every_pattern_and_text(self):
        pats = []
        for case, name in ALL_GRADERS:
            pats.append([name, str(T.pattern_of(case, name)["pattern"])])
        script = (
            "const [pats, texts] = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
            "console.log(JSON.stringify(pats.map(([n, p]) => texts.map(t => new RegExp(p).test(t)))));"
        )
        out = subprocess.run([NODE, "-e", script], input=json.dumps([pats, self.CORPUS]), capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout)
        for row, (name, pattern) in zip(got, pats):
            for hit, text in zip(row, self.CORPUS):
                with self.subTest(grader=name, text=text[:40]):
                    self.assertEqual(hit, re.search(pattern, text) is not None)

    def test_the_existing_javascript_compile_test_runs_and_is_not_skipped(self):
        suite = unittest.TestSuite([T.PatternTest("test_every_pattern_compiles_in_javascript")])
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(result.skipped, [])


class ReportOpeningSentenceTest(unittest.TestCase):
    """AC-8: the `Status:` first-line sentence is in the eight carriers and nowhere else."""

    SENTENCE = "`Status:` is the first line of each, with no summary sentence above it"
    CARRIERS = ("architect", "devops", "docs", "frontend", "implement", "qa", "test-engineer", "uiux")

    def test_the_sentence_is_in_each_carrier_once_inside_the_opening_section(self):
        texts = agent_texts()
        for name in self.CARRIERS:
            with self.subTest(agent=name):
                t = fold(texts[name])
                self.assertEqual(t.count(self.SENTENCE), 1)
                head = t.index("## How Every Report Opens")
                self.assertGreater(t.index(self.SENTENCE), head)
                self.assertLess(t.index(self.SENTENCE) - head, 600)

    def test_the_sentence_sits_right_after_the_lead_in_and_before_the_fence(self):
        for name, text in agent_texts().items():
            if name not in self.CARRIERS:
                continue
            with self.subTest(agent=name):
                i = text.index("## How Every Report Opens")
                section = text[i:text.index("```", text.index("```", i) + 3) + 3]
                self.assertLess(fold(section).index("report file your brief names with them too."), fold(section).index(self.SENTENCE))
                self.assertLess(fold(section).index(self.SENTENCE), fold(section).index("```"))

    def test_no_other_agent_carries_the_sentence_or_its_key_phrases(self):
        for name, text in agent_texts().items():
            if name in self.CARRIERS:
                continue
            with self.subTest(agent=name):
                t = fold(text)
                for phrase in ("no summary sentence", "Status:` is the first line", "## How Every Report Opens"):
                    self.assertNotIn(phrase, t)

    def test_investigate_and_file_reader_exist_and_lack_the_sentence(self):
        texts = agent_texts()
        for name in ("investigate", "file-reader"):
            self.assertIn(name, texts)
            self.assertNotIn("summary sentence", texts[name])
            self.assertNotIn("Open your reply with these four lines", texts[name])

    def test_the_sentence_is_in_no_skill_or_doc_but_the_carriers_and_their_plan_log(self):
        for p in sorted((ROOT / "skills").glob("*/SKILL.md")):
            with self.subTest(skill=p.parent.name):
                self.assertNotIn("with no summary sentence above it", fold(p.read_text(encoding="utf-8")))

    def test_exactly_eight_agents_carry_the_sentence(self):
        have = sorted(n for n, t in agent_texts().items() if "no summary sentence above it" in fold(t))
        self.assertEqual(have, sorted(self.CARRIERS))

    def test_the_sentence_fits_the_80_column_rule_in_every_carrier(self):
        for name in self.CARRIERS:
            with self.subTest(agent=name):
                text = (ROOT / "agents" / (name + ".md")).read_text(encoding="utf-8")
                i = text.index("## How Every Report Opens")
                for line in text[i:i + 700].split("\n"):
                    self.assertLess(len(line), 80, line)


if __name__ == "__main__":
    unittest.main()
