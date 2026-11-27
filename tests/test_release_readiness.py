"""Release readiness: the data-change sort, the rollback line and the watch line in `devops`.

AC-12: the words the agent and the ship skill share (the three labels, `not tried`, `never on
production`, `roll back if`, the 30-minute default, the no-service line) are held the same in both. Every
rule lives in `problems()` over an in-memory dict of texts, so a mutation test edits a copy and asks
whether the rule notices. Nothing is written to the repo. Hermetic; standard library only; runs on
Python 3.9 and later.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling test modules import as top-level names

from test_security_in_planning import between, folded_between  # noqa: E402
from test_security_rules import agent_texts, fold  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KINDS = ("**adds only**", "**breaks running code**", "**can't be undone**")
OFF_PRODUCTION = "never on production"
ROLL_BACK_IF = "roll back if"
WATCH_DEFAULT = "30 minutes"
NOT_TRIED = "not tried"
NO_SERVICE = "nothing to watch: no running service"
COPY_CHECK = "confirm the tool will open the copy"
ROLLBACK_SHAPE = "tried: `<command>` (exit <n>) | not tried: <why>"
WATCH_SHAPE = "; for <how long>; roll back if <condition>"
PLAIN = ("expand and contract", "canary", "blast radius")
SLO = re.compile(r"\bSLO\b")


def all_texts():
    texts = dict(agent_texts())
    texts["ship"] = (ROOT / "skills" / "ship" / "SKILL.md").read_text(encoding="utf-8")
    return texts


def lacks(name, text, needles):
    """One message for each needle the text doesn't hold."""
    return ["%s doesn't hold %r" % (name, needle) for needle in needles if needle not in text]


def problems(texts):
    """Every way the texts break a rule; an empty list means they hold."""
    found = []
    devops = texts.get("devops", "")
    section = folded_between(devops, "## Data Changes and Rollbacks", "## Hard Rules")
    found += lacks("devops's Data Changes and Rollbacks section", section,
                   KINDS + ("even when your brief says to apply it", "Treat the change as breaking running code"))
    found += lacks("devops's Data Changes and Rollbacks section", section,
                   (OFF_PRODUCTION, COPY_CHECK, "unless your brief names a scratch database", WATCH_DEFAULT, ROLL_BACK_IF))
    rules = folded_between(devops, "## Hard Rules", "## What to Report Back")
    found += lacks("devops's Hard Rules", rules, ("breaks the code running now", OFF_PRODUCTION))
    report = between(devops, "## What to Report Back", "## How Every Report Opens")
    fence = re.search(r"^```\n(.*?)^```$", report, re.S | re.M)
    lines = fence.group(1).rstrip("\n").split("\n") if fence else []
    heads = ("Data change: ", "Rollback: ", "Watch: ")
    if len(lines) != 3 or not all(line.startswith(head) for line, head in zip(lines, heads)):
        found.append("devops's report fence isn't the Data change, Rollback and Watch lines: %s" % lines)
    else:
        for needle in ("adds only", "breaks running code", "can't be undone"):
            if needle not in lines[0]:
                found.append("devops's Data change line doesn't hold %r" % needle)
        if ROLLBACK_SHAPE not in lines[1]:
            found.append("devops's Rollback line doesn't hold %r" % ROLLBACK_SHAPE)
        if WATCH_SHAPE not in lines[2]:
            found.append("devops's Watch line doesn't hold %r" % WATCH_SHAPE)
    slot = "If you stopped before a change that breaks the code running now"
    folded = fold(report)
    found += lacks("devops's What to Report Back", folded, ("`Data change: none; %s`" % NO_SERVICE, slot))
    if "NEEDS_CONTEXT" not in folded[folded.find(slot) + len(slot):][:300]:
        found.append("devops's stop slot isn't followed by NEEDS_CONTEXT")
    verify = folded_between(devops, "4. **Verify after.**", "5. **Leave an audit trail.**")
    found += lacks("devops's step 4", verify, ("the thing the change touched", "only reads"))
    work = folded_between(devops, "## How to Work", "## How Every Report Opens")
    for word in PLAIN:
        if word in work.lower():
            found.append("devops uses %r, not a plain word" % word)
    if SLO.search(work):
        found.append("devops uses SLO, not a plain word")
    return found


class RealTreeTest(unittest.TestCase):
    def test_the_texts_hold_every_rule(self):
        """AC-12: the shared words and the report shape hold in the real texts."""
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
        self.assertTrue(any(needle in p and "devops" in p for p in found), found)

    def test_a_renamed_kind_fails(self):
        """AC-1, AC-12: the three kinds keep their labels."""
        texts = self.mutated("devops", lambda t: t.replace("**breaks running code**", "**breaking**", 1))
        self.caught(texts, "**breaks running code**")

    def test_a_dropped_copy_check_fails(self):
        """AC-3, AC-12: a try runs only after confirming the tool opens the copy."""
        texts = self.mutated("devops", lambda t: re.sub(r"confirm\s+the\s+tool\s+will\s+open\s+the\s+copy", "use the copy", t, 1))
        self.caught(texts, COPY_CHECK)

    def test_the_hard_rule_removed_fails(self):
        """AC-3, AC-12: the Hard Rules bullet keeps a try off production."""
        def drop(t):
            i = t.index("- **Try a rollback only on a copy")
            j = t.index("- **Never** put secrets")
            return t[:i] + t[j:]
        self.caught(self.mutated("devops", drop), "Hard Rules")

    def test_the_condition_dropped_from_the_watch_line_fails(self):
        """AC-4, AC-12: the Watch line in the fence names a roll back if condition."""
        texts = self.mutated("devops", lambda t: t.replace("roll back if <condition>", "<condition>", 1))
        self.caught(texts, "Watch line")

    def test_the_stop_slot_removed_fails(self):
        """AC-2, AC-12: the report names the stop before a breaking change."""
        def drop(t):
            i = t.index("- If you stopped before a change that breaks")
            j = t.index("- ", i + 2)
            return t[:i] + t[j:]
        self.caught(self.mutated("devops", drop), "What to Report Back")

    def test_the_verify_step_loosened_fails(self):
        """AC-4, AC-12: step 4 checks the thing the change touched."""
        texts = self.mutated("devops", lambda t: t.replace("the thing the change touched", "the service", 1))
        self.caught(texts, "step 4")

    def test_a_jargon_word_in_step_4_fails(self):
        """AC-12: plain words only."""
        texts = self.mutated("devops", lambda t: t.replace("the changed page).", "the changed page), canary.", 1))
        self.caught(texts, "canary")

    def test_a_line_break_moved_inside_a_phrase_still_holds(self):
        def rewrap(t):
            return t.replace("confirm the\n  tool will open the copy", "confirm\n  the tool will open the copy", 1)
        self.assertEqual(problems(self.mutated("devops", rewrap)), [])

    def test_a_missing_section_gives_a_message_not_a_crash(self):
        self.assertEqual(between("no headings", "## A", "## B"), "")
        self.assertTrue(problems({"devops": "no headings"}))


if __name__ == "__main__":
    unittest.main()
