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
DECISIONS = ROOT / "evals" / "ship-decisions"
KINDS = ("**adds only**", "**breaks running code**", "**can't be undone**")
OFF_PRODUCTION = "never on production"
ROLL_BACK_IF = "roll back if"
WATCH_DEFAULT = "30 minutes"
NOT_TRIED = "not tried"
NO_SERVICE = "nothing to watch: no running service"
NO_TOOL_FOR_A_TRY = "Never run the project's migration tool for a try"
PATH_IN_COMMAND = "with the copy's path written in each command"
DOWN_DIR_CHECK = '[ -d "$T" ]'
ROLLBACK_SHAPE = "tried: `<command>` (exit <n>) | not tried: <why>"
WATCH_SHAPE = "; for <how long>; roll back if <condition>"
BOTH_FIRST = "first the code that works with both"
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
                   (OFF_PRODUCTION, NO_TOOL_FOR_A_TRY, PATH_IN_COMMAND, "unless your brief names a scratch database", WATCH_DEFAULT, ROLL_BACK_IF))
    found += lacks("devops's Data Changes and Rollbacks section", between(devops, "## Data Changes and Rollbacks", "## Hard Rules"),
                   (DOWN_DIR_CHECK,))
    found += lacks("devops's Data Changes and Rollbacks section", section,
                   ("can't tell whether it reads the thing", "is no stop", "where that code reads",
                    "not tried, unless your brief names a scratch database", "Never create one on the production host",
                    BOTH_FIRST, "no running service on this data"))
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
    ship = texts.get("ship", "")
    preflight = folded_between(ship, "## 2. Preflight", "## 3. One ask")
    found += lacks("ship's preflight", preflight, KINDS + ("no data change", NO_SERVICE, "send it back to be split"))
    found += lacks("ship's preflight", preflight, ("isn't ready for one release", "both work on the changed data", BOTH_FIRST))
    handover = folded_between(ship, "## 8. Hand over the deploy", "## 9. Close the loop")
    found += lacks("ship's hand-over", handover,
                   (NOT_TRIED, OFF_PRODUCTION, ROLL_BACK_IF, WATCH_DEFAULT, "what to look at", "for how long"))
    found += lacks("ship's hand-over", handover, ("never the value", "Run nothing on the server yourself"))
    found += lacks("ship's hand-over", handover,
                   ("grep -c", "nothing else goes out until it does", "give the rollback command again", "for them to run",
                    "whether the previous version runs on the changed data"))
    count_check = handover.find("prints a count and never the value")
    if not 0 <= count_check < handover.find("2. **The deploy command**"):
        found.append("ship's hand-over doesn't put the count check in item 1, before the deploy command")
    flags = ship[ship.find("## Red flags"):] if "## Red flags" in ship else ""
    rows = {
        '| "The rollback is just the previous tag"': "tried or not tried",
        '| "It answered once, so it\'s fine"': ROLL_BACK_IF,
        '| "One error line is probably nothing"': ROLL_BACK_IF,
    }
    for start, cell in rows.items():
        row = [line for line in flags.split("\n") if line.startswith(start)]
        if not row:
            found.append("ship's Red flags has no row starting %s" % start)
        elif cell not in row[0].strip().strip("|").split("|")[-1]:
            found.append("ship's Red flags row %s doesn't hold %r in its last cell" % (start, cell))
    ship_all = fold(ship)
    for word in PLAIN:
        if word in ship_all.lower():
            found.append("ship uses %r, not a plain word" % word)
    if SLO.search(ship_all):
        found.append("ship uses SLO, not a plain word")
    section = folded_between(texts.get("architect", ""), "### 3. Data / Schema Changes", "### 4. Risks and Coupling")
    found += lacks("architect's section 3", section, ("breaks the code running now", "two releases", BOTH_FIRST))
    return found


def situation_problems(prompt_text, grader_stems):
    """Every way the ship-decisions prompt and its graders disagree; an empty list means they match."""
    found = []
    letters = [m.group(1) for m in re.finditer(r"^([a-z])\. (.+)$", prompt_text, re.M)]
    want = [chr(c) for c in range(ord("a"), ord("k") + 1)]
    if letters != want:
        found.append("the prompt's situations are %s, not a to k with no gap" % letters)
    stems = sorted(grader_stems)
    if stems != ["item-" + c for c in want]:
        for c in want:
            if "item-" + c not in stems:
                found.append("no grader item-%s for situation %s" % (c, c))
        found.append("the grader stems are %s, not item-a to item-k" % stems)
    for stem in stems:
        path = DECISIONS / "graders" / (stem + ".md")
        body = fold(path.read_text(encoding="utf-8")) if path.is_file() else ""
        if not body.startswith("--- type: llm focus: last_message ---"):
            found.append("%s isn't a last_message llm grader" % stem)
        if "item (%s)" % stem[-1] not in body:
            found.append("%s doesn't judge item (%s)" % (stem, stem[-1]))
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

    def caught(self, texts, needle, who="devops"):
        found = problems(texts)
        self.assertTrue(any(needle in p and who in p for p in found), found)

    def test_a_renamed_kind_fails(self):
        """AC-1, AC-12: the three kinds keep their labels."""
        texts = self.mutated("devops", lambda t: t.replace("**breaks running code**", "**breaking**", 1))
        self.caught(texts, "**breaks running code**")

    def test_a_try_that_runs_the_migration_tool_fails(self):
        """AC-3, AC-12: a try never runs the project's migration tool."""
        texts = self.mutated("devops", lambda t: re.sub(r"Never\s+run\s+the\s+project's\s+migration\s+tool\s+for\s+a\s+try", "Run the project's migration tool for a try", t, 1))
        self.caught(texts, NO_TOOL_FOR_A_TRY)

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

    def test_ships_preflight_loses_a_label_fails(self):
        """AC-5, AC-12: ship sorts with the same three labels as devops."""
        texts = self.mutated("ship", lambda t: t.replace("**can't be undone**", "**irreversible**", 1))
        self.caught(texts, "**can't be undone**", "ship")

    def test_ships_hand_over_without_roll_back_if_fails(self):
        """AC-6, AC-7, AC-12: the watch in section 8 names a roll back if condition."""
        def drop(t):
            i, j = t.index("## 8. Hand over the deploy"), t.index("## 9. Close the loop")
            return t[:i] + t[i:j].replace(ROLL_BACK_IF, "revert when") + t[j:]
        self.caught(self.mutated("ship", drop), ROLL_BACK_IF, "ship")

    def test_a_hand_over_that_prints_the_value_fails(self):
        """AC-6, AC-12: the check for a new secret never prints the value."""
        texts = self.mutated("ship", lambda t: t.replace("never the value", "the value", 1))
        self.caught(texts, "never the value", "ship")

    def test_a_red_flag_row_removed_fails(self):
        """AC-7, AC-12: the red-flag rows stay."""
        def drop(t):
            i = t.index('| "It answered once')
            return t[:i] + t[t.index("\n", i) + 1:]
        self.caught(self.mutated("ship", drop), "It answered once", "ship")

    def test_a_jargon_word_in_ships_hand_over_fails(self):
        """AC-12: plain words only."""
        texts = self.mutated("ship", lambda t: t.replace("## 9. Close the loop", "canary\n\n## 9. Close the loop", 1))
        self.caught(texts, "canary", "ship")

    def test_one_release_in_the_architects_section_3_fails(self):
        """AC-13: the architect splits a breaking change across two releases."""
        texts = self.mutated("architect", lambda t: t.replace("two releases", "one release", 1))
        self.caught(texts, "two releases", "architect")

    def test_devops_and_ship_hold_the_same_three_labels(self):
        """AC-12: the labels are typed the same in both files."""
        devops = folded_between(self.base["devops"], "## Data Changes and Rollbacks", "## Hard Rules")
        ship = folded_between(self.base["ship"], "## 2. Preflight", "## 3. One ask")
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assertIn(kind, devops)
                self.assertIn(kind, ship)

    def test_a_line_break_moved_inside_ships_phrase_still_holds(self):
        def rewrap(t):
            return t.replace("send it\n  back to be split", "send\n  it back to be split", 1)
        self.assertEqual(problems(self.mutated("ship", rewrap)), [])

    def test_a_line_break_moved_inside_a_phrase_still_holds(self):
        def rewrap(t):
            return t.replace("with the copy's path written in each command", "with the copy's path\n  written in each command", 1)
        self.assertEqual(problems(self.mutated("devops", rewrap)), [])

    def test_a_missing_section_gives_a_message_not_a_crash(self):
        self.assertEqual(between("no headings", "## A", "## B"), "")
        self.assertTrue(problems({"devops": "no headings"}))


class ShipDecisionsSituationsTest(unittest.TestCase):
    def real(self):
        prompt = (DECISIONS / "prompt.md").read_text(encoding="utf-8")
        return prompt, [p.stem for p in (DECISIONS / "graders").glob("*.md")]

    def test_the_real_files_agree(self):
        """AC-11: situations a to k each have a grader that judges its own item."""
        prompt, stems = self.real()
        self.assertEqual(situation_problems(prompt, stems), [])

    def test_a_missing_grader_names_its_situation(self):
        """AC-11: a situation with no grader is reported."""
        prompt, stems = self.real()
        found = situation_problems(prompt, [s for s in stems if s != "item-k"])
        self.assertTrue(any("item-k" in p and "situation k" in p for p in found), found)


if __name__ == "__main__":
    unittest.main()
