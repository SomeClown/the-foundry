"""Security in planning: the `Security:` label, the dependency decision and their hand-offs.

AC-9: the label, the dependency hand-off and the rules that depend on them hold the same across the
architect, frontend, implement, qa and brainstorm texts. Every rule lives in `problems()` over an
in-memory dict of texts, so a mutation test edits a copy and asks whether the rule notices. Nothing is
written to the repo. Hermetic; standard library only; runs on Python 3.9 and later.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling test modules import as top-level names

from test_security_rules import agent_texts, fold  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AUDIT_LINE = "Audit: ran `<command>` (exit <n>) | not run:"
SEND_CONDITION = "says the list may be sent"


def all_texts():
    texts = dict(agent_texts())
    texts["brainstorm"] = (ROOT / "skills" / "brainstorm" / "SKILL.md").read_text(encoding="utf-8")
    texts["orchestrator"] = (ROOT / "docs" / "orchestrator.md").read_text(encoding="utf-8")
    return texts


def between(text, start, end):
    """The text from `start` to the next `end` after it, or "" when either is missing."""
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    return text[i:j] if j >= 0 else ""


def problems(texts):
    """Every way the texts break a rule; an empty list means they hold."""
    found = []
    arch = between(texts.get("architect", ""), "### 4. Risks and Coupling", "### 5. Testing Strategy")
    for needle in ("`Security:`", "`Security: none`"):
        if needle not in arch:
            found.append("architect's section 4 doesn't hold %s" % needle)
    if "since frontend adds none" not in fold(texts.get("architect", "")):
        found.append("architect doesn't say that frontend adds no dependency")
    if "Do not add dependencies" not in texts.get("frontend", ""):
        found.append("frontend lost 'Do not add dependencies', which architect's hand-off relies on")
    spec = between(texts.get("qa", ""), "## Spec-Check Mode", "Put a spec section first")
    if "`Security:`" not in spec:
        found.append("qa's spec check doesn't treat a `Security:` line as a requirement")
    step = fold(between(texts.get("implement", ""), "4. **Make the change.**", "5. **Handle data changes"))
    for needle in ("your brief doesn't name", "NEEDS_CONTEXT"):
        if needle not in step:
            found.append("implement's step 4 doesn't hold %r" % needle)
    ground = fold(between(texts.get("brainstorm", ""), "## 4. Ground to cover", "## 5."))
    if "who may use it" not in ground:
        found.append("brainstorm's ground to cover doesn't ask who may use it")
    look = between(texts.get("qa", ""), "## What to Look For", "## Spec-Check Mode")
    if "\n### Dependencies\n" not in look:
        found.append("qa has no '### Dependencies' subsection under What to Look For")
    else:
        fence = re.search(r"^```\n(.*?)^```$", look[look.index("\n### Dependencies\n"):], re.S | re.M)
        lines = fence.group(1).rstrip("\n").split("\n") if fence else []
        if len(lines) != 2 or not lines[0].startswith("Dependencies: ") or not lines[1].startswith(AUDIT_LINE):
            found.append("qa's Dependencies fence isn't the Dependencies line and the Audit line: %s" % lines)
    qa_deps = fold(between(texts.get("qa", ""), "### Dependencies", "### Logic Bugs"))
    for name, text in (("qa's Dependencies subsection", qa_deps), ("orchestrator", fold(texts.get("orchestrator", "")))):
        if SEND_CONDITION not in text:
            found.append("%s doesn't hold %r" % (name, SEND_CONDITION))
    return found


class RealTreeTest(unittest.TestCase):
    def test_the_texts_hold_every_rule(self):
        self.assertEqual(problems(all_texts()), [])


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

    def test_architects_none_line_broken_fails(self):
        """AC-1: a plan that touches nothing writes `Security: none`."""
        texts = self.mutated("architect", lambda t: t.replace("`Security: none`", "`Security:` none", 1))
        self.caught(texts, "architect's section 4")

    def test_frontend_allowed_dependencies_fails(self):
        """AC-2: the dependency goes to implement because frontend adds none."""
        texts = self.mutated("frontend", lambda t: t.replace("Do not add dependencies", "Add few dependencies", 1))
        self.caught(texts, "frontend lost")

    def test_the_security_bullet_removed_from_qa_fails(self):
        """AC-6: qa's spec check counts the guards a Security line names."""
        def drop(t):
            i = t.index("- **Security lines count.**")
            j = t.index("- **Nothing extra.**")
            return t[:i] + t[j:]
        self.caught(self.mutated("qa", drop), "qa's spec check")

    def test_implement_flagging_a_dependency_fails(self):
        """AC-4: a dependency the brief doesn't name is a NEEDS_CONTEXT stop."""
        texts = self.mutated("implement", lambda t: t.replace("NEEDS_CONTEXT stop", "flag", 1))
        self.caught(texts, "implement's step 4")

    def test_brainstorm_without_who_may_use_it_fails(self):
        """AC-3: brainstorm asks who may use the feature."""
        texts = self.mutated("brainstorm", lambda t: t.replace("who may use it", "who it is for", 1))
        self.caught(texts, "brainstorm's ground")

    def test_the_audit_line_changed_in_qas_fence_fails(self):
        """AC-5, AC-9: qa reports an Audit line in the shape the graders read."""
        texts = self.mutated("qa", lambda t: t.replace("Audit: ran", "Audit run:", 1))
        self.caught(texts, "qa's Dependencies fence")

    def test_the_send_condition_missing_from_the_orchestrator_fails(self):
        """AC-5, AC-9: the orchestrator note and qa name the same send condition."""
        texts = self.mutated("orchestrator", lambda t: fold(t).replace(SEND_CONDITION, "says so", 1))
        self.caught(texts, "orchestrator doesn't hold")

    def test_a_rewrapped_architect_paragraph_still_holds(self):
        def rewrap(t):
            return t.replace("touches none gets one line: `Security: none`.", "touches none gets one line:\n`Security: none`.", 1)
        self.assertEqual(problems(self.mutated("architect", rewrap)), [])

    def test_a_missing_section_gives_a_message_not_a_crash(self):
        self.assertEqual(between("no headings", "## A", "## B"), "")


if __name__ == "__main__":
    unittest.main()
