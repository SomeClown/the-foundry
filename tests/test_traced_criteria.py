"""Acceptance criteria that travel by id: AC-1, AC-2, ... from a design to a plan to tests to the spec check.

The rules are read from the agent and skill texts, never from a list of agent names beyond the six that
carry a **Covers** line. Every rule lives in `problems()` over an in-memory dict of texts (the agents, plus
`run-plan`, `brainstorm` and `orchestrator`), so a mutation test edits a copy and asks whether the rule
notices. Nothing is written to the repo. Hermetic: no network, nothing under ~/.claude or ~/.foundry.
Standard library only; runs on Python 3.9 and later.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling test modules import as top-level names

from test_security_rules import agent_texts, fold  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COVERS = "**Covers**"
DONE_WHEN = "**Done when"  # the bold label, with its colon inside (`**Done when:**`) or outside
COVERS_IN = ("architect", "implement", "frontend", "test-engineer", "qa", "run-plan")
DONE_WHEN_IN = ("brainstorm", "architect", "qa", "run-plan", "orchestrator")
# the state is the capitalized words after the id on its own line, single spaces between them, never across a line break
STATE_RE = re.compile(r"AC-(?:n|[0-9]+)[ \t]+([A-Z]{3,}(?: [A-Z]{3,})*)\b")
ID_RE = re.compile(r"AC-(?:n|N|[1-9][0-9]*)\b")
# every spelling that looks like an id: AC1, ac-1, AC -1, AC-01, AC-x, a bare `AC-`
LOOKS_LIKE_ID = re.compile(r"\b[Aa][Cc](?:[ \t]*-[ \t]*\w*|[0-9]\w*)")
GAPS_SENTENCE = "Any `NOT MET` or `UNTESTED` line makes it GAPS."
COVERS_BULLET = "- **Covers** — when the brief has"
FENCE_SHAPE = [
    re.compile(r"Spec: MATCHES \| GAPS$"),
    re.compile(r"AC-n MET "),
    re.compile(r"AC-n NOT MET:"),
    re.compile(r"AC-n UNTESTED "),
    re.compile(r"AC-n CANNOT VERIFY:"),
    re.compile(r"AC-n DROPPED$"),
    re.compile(r"\[MISSING\]"),
    re.compile(r"\[EXTRA\]"),
    re.compile(r"\[DIFFERENT\]"),
    re.compile(r"\[CANNOT VERIFY\]"),
]


def all_texts():
    texts = dict(agent_texts())
    texts["run-plan"] = (ROOT / "skills" / "run-plan" / "SKILL.md").read_text(encoding="utf-8")
    texts["brainstorm"] = (ROOT / "skills" / "brainstorm" / "SKILL.md").read_text(encoding="utf-8")
    texts["orchestrator"] = (ROOT / "docs" / "orchestrator.md").read_text(encoding="utf-8")
    return texts


def spec_fence(qa):
    """The lines of the first fence after `Put a spec section first` (the `Spec:` line first), or None."""
    i = qa.find("Put a spec section first")
    if i < 0:
        return None
    m = re.search(r"^```\n(.*?)^```$", qa[i:], re.S | re.M)
    return m.group(1).rstrip("\n").split("\n") if m else None


def qa_states(qa):
    """The five state names in qa's fence, from the lines that start `AC-n`."""
    lines = spec_fence(qa) or []
    return {m.group(1).strip() for m in (STATE_RE.match(l) for l in lines) if m}


def covers_bullet(text):
    """The bullet that starts `- **Covers** — when the brief has`, whitespace folded, or None."""
    i = text.find(COVERS_BULLET)
    if i < 0:
        return None
    m = re.search(r"\n(?=- |\n|#)", text[i:])
    return fold(text[i: i + m.start()] if m else text[i:])


def text_of(texts, name):
    return texts.get(name, "")


def problems(texts):
    """Every way the texts break a rule; an empty list means they hold."""
    found = []
    for name in COVERS_IN:
        if COVERS not in texts.get(name, ""):
            found.append("%s doesn't mention %s" % (name, COVERS))
    for name in DONE_WHEN_IN:
        if DONE_WHEN not in texts.get(name, ""):
            found.append("%s doesn't mention %s" % (name, DONE_WHEN))
    fence = spec_fence(texts.get("qa", ""))
    if fence is None:
        found.append("qa has no spec fence after 'Put a spec section first'")
    else:
        kinds = [next((n for n, rx in enumerate(FENCE_SHAPE) if rx.match(l)), None) for l in fence]
        if kinds != list(range(len(FENCE_SHAPE))):
            found.append("qa's spec fence lines are out of shape or order: %s" % fence)
    allowed = qa_states(texts.get("qa", ""))
    if len(allowed) != 5:
        found.append("qa names %d id states, wants 5: %s" % (len(allowed), sorted(allowed)))
    for name in ("run-plan", "architect", "orchestrator"):
        for m in STATE_RE.finditer(text_of(texts, name)):
            state = m.group(1).strip()
            line_end = text_of(texts, name).find("\n", m.end())
            at_line_end = not text_of(texts, name)[m.end(): line_end if line_end >= 0 else None].strip()
            wrapped = at_line_end and any((a + " ").startswith(state + " ") for a in allowed)
            if state not in allowed and not wrapped:
                found.append("%s names the id state %r, which qa doesn't have" % (name, state))
    a, b = covers_bullet(texts.get("implement", "")), covers_bullet(texts.get("frontend", ""))
    if a is None or b is None:
        found.append("implement or frontend lacks the %r bullet" % COVERS_BULLET)
    elif a != b:
        found.append("the Covers bullet differs between implement and frontend")
    for name, text in texts.items():
        for m in LOOKS_LIKE_ID.finditer(text):
            if not ID_RE.match(text[m.start():]):
                found.append("%s writes an id as %r" % (name, m.group(0)))
    if GAPS_SENTENCE not in fold(texts.get("qa", "")):
        found.append("qa lost the sentence that a NOT MET or UNTESTED line makes it GAPS")
    if "`AC-n: Task N; test`" not in texts.get("architect", ""):
        found.append("architect lost the `AC-n: Task N; test` coverage line")
    return found


class RealTreeTest(unittest.TestCase):
    def test_the_texts_hold_every_rule(self):
        self.assertEqual(problems(all_texts()), [])

    def test_the_six_agents_and_skills_exist(self):
        texts = all_texts()
        for name in COVERS_IN + DONE_WHEN_IN:
            self.assertIn(name, texts)


class MutationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = all_texts()
        assert problems(cls.base) == []

    def mutated(self, name, fn):
        texts = dict(self.base)
        new = fn(texts[name])
        self.assertNotEqual(new, texts[name], "the mutation changed nothing")
        texts[name] = new
        return texts

    def caught(self, texts, needle):
        found = problems(texts)
        self.assertTrue(any(needle in p for p in found), found)

    def test_a_covers_label_dropped_from_any_of_the_six_fails(self):
        for name in COVERS_IN:
            with self.subTest(agent=name):
                texts = self.mutated(name, lambda t: t.replace(COVERS, "**Cover**"))
                self.caught(texts, "%s doesn't mention %s" % (name, COVERS))

    def test_a_done_when_label_dropped_from_any_of_the_five_fails(self):
        for name in DONE_WHEN_IN:
            with self.subTest(agent=name):
                texts = self.mutated(name, lambda t: t.replace(DONE_WHEN, "**Done"))
                self.caught(texts, "%s doesn't mention %s" % (name, DONE_WHEN))

    def test_qas_fence_missing_a_line_or_out_of_order_fails(self):
        self.caught(self.mutated("qa", lambda t: t.replace("AC-n DROPPED\n", "", 1)), "out of shape")
        swap = lambda t: t.replace("AC-n MET ", "AC-n @@ ", 1).replace("AC-n NOT MET:", "AC-n MET ", 1).replace("AC-n @@ ", "AC-n NOT MET:", 1)  # noqa: E731
        self.caught(self.mutated("qa", swap), "out of shape")

    def test_an_id_state_run_plan_has_and_qa_lacks_fails(self):
        def rename(t):
            return t.replace("`AC-2 NOT MET`", "`AC-2 MISSING`", 1)
        texts = self.mutated("run-plan", rename)
        self.caught(texts, "names the id state 'MISSING'")

    def test_an_id_state_in_architect_or_orchestrator_outside_qas_five_fails(self):
        texts = self.mutated("orchestrator", lambda t: t + "\nAC-1 PENDING for now\n")
        self.caught(texts, "names the id state 'PENDING'")
        texts = self.mutated("architect", lambda t: t + "\nAC-2 BROKEN here\n")
        self.caught(texts, "names the id state 'BROKEN'")

    def test_one_changed_word_in_the_frontend_bullet_fails(self):
        texts = self.mutated("frontend", lambda t: t.replace("one line per id", "a line per id", 1))
        self.caught(texts, "differs between implement and frontend")

    def test_the_bullet_missing_from_either_builder_fails(self):
        texts = self.mutated("implement", lambda t: t.replace(COVERS_BULLET, "- **Covers** - when the brief has", 1))
        self.caught(texts, "lacks the")

    def test_a_rewrapped_bullet_still_holds(self):
        texts = self.mutated("frontend", lambda t: t.replace("one line per id:\n", "one line\n  per id:\n", 1))
        self.assertEqual(problems(texts), [])

    def test_an_id_written_without_its_dash_or_digit_fails(self):
        self.caught(self.mutated("brainstorm", lambda t: t + "\nSee AC1 above.\n"), "writes an id as")
        self.caught(self.mutated("run-plan", lambda t: t + "\nSee AC-x above.\n"), "writes an id as")

    def test_the_gaps_sentence_dropped_from_qa_fails(self):
        texts = self.mutated("qa", lambda t: t.replace(GAPS_SENTENCE, "", 1))
        self.caught(texts, "makes it GAPS")

    def test_a_changed_first_fence_line_fails(self):
        texts = self.mutated("qa", lambda t: t.replace("Spec: MATCHES | GAPS\nAC-n MET", "Whatever\nAC-n MET", 1))
        self.caught(texts, "spec fence")

    def test_other_id_spellings_fail(self):
        for bad in ("AC-01", "ac-1", "AC -1"):
            with self.subTest(spelling=bad):
                self.caught(self.mutated("brainstorm", lambda t: t + "\nSee %s now.\n" % bad), "writes an id as")

    def test_a_state_never_runs_over_a_line_break(self):
        texts = self.mutated("run-plan", lambda t: t + "\n`AC-2 MET`\nAPI notes follow.\n")
        self.assertEqual(problems(texts), [])

    def test_architect_without_the_coverage_line_shape_fails(self):
        texts = self.mutated("architect", lambda t: t.replace("`AC-n: Task N; test`", "`AC-n: Task N`", 1))
        self.caught(texts, "coverage line")


if __name__ == "__main__":
    unittest.main()
