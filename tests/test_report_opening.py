"""The four opening lines every reporting agent carries, and the two checks the builders gained.

Structure first. Who carries `## How Every Report Opens` is read from the front matter (tools include
Bash and not Agent), never from a list of names. Each carrier has exactly one section, after its report
heading, identical across copies with whitespace folded. The fence is four lines labelled Status, Files
changed, Verified, Concerns in that order, and the words on the Status line (and in the section's own
bullets) equal the bolded words under `Handle the status:` in skills/run-plan/SKILL.md. Then the few
wording pins the plan names, and nothing that merely restates a sentence.

Every rule lives in `problems()` and `pin_problems()` over an in-memory copy of the texts, so a mutation
test edits a copy and asks whether the rule notices. Nothing is written to the repo. Hermetic: temp files
only (via test_security_rules.tools_of), no network, nothing under ~/.claude or ~/.foundry. Standard
library only; runs on Python 3.9 and later.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling test modules import as top-level names

from test_security_rules import agent_texts, fold, tools_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HEADING = "## How Every Report Opens"
REPORT_HEADINGS = ("What to Report Back", "What to Produce", "Output Format")
LABELS = ["Status", "Files changed", "Verified", "Concerns"]
# the pattern test_structure uses to find qa's per-finding label
FINDING_LABEL = re.compile(r"^\s*(\w+): `ran <", re.M)


def run_plan_text():
    return (ROOT / "skills" / "run-plan" / "SKILL.md").read_text(encoding="utf-8")


def carriers_of(texts):
    """Agents that report to the session: Bash in the tools, no Agent."""
    out = []
    for name, text in texts.items():
        tools = tools_of(text, name)
        if "Bash" in tools and "Agent" not in tools:
            out.append(name)
    return out


def section_of(text):
    """The section's text after its heading line, or None. Ends at the next `## ` heading or a rule."""
    start = text.find("\n" + HEADING + "\n")
    if start < 0:
        return None
    body = text[start + len(HEADING) + 2:]
    end = re.search(r"^(## |---$)", body, re.M)
    return body[: end.start()] if end else body


def fence_lines(section):
    blocks = re.findall(r"^```\n(.*?)^```$", section, re.S | re.M)
    return blocks[0].rstrip("\n").split("\n") if blocks else None, len(blocks)


def run_plan_statuses(plan_text):
    """The bolded words in the list under `Handle the status:`, in order."""
    after = plan_text.split("Handle the status:\n", 1)[1]
    words = []
    for line in after.split("\n"):
        m = re.match(r"- \*\*([A-Z_]+)\*\*:", line)
        if m:
            words.append(m.group(1))
        elif line.strip() and not line.startswith(" "):
            break
    return words


def report_heading_at(text):
    hits = [m.start() for h in REPORT_HEADINGS for m in re.finditer(r"^## %s$" % re.escape(h), text, re.M)]
    return hits


def problems(texts, plan_text):
    """Every way the copies break the structural rule; an empty list means they hold."""
    found = []
    statuses = run_plan_statuses(plan_text)
    if sorted(statuses) != sorted(set(statuses)) or len(statuses) < 4:
        found.append("run-plan's status list is odd: %s" % statuses)
    carried = set(carriers_of(texts))
    folded = {}
    for name, text in texts.items():
        count = text.count("\n" + HEADING + "\n")
        if name not in carried:
            if count:
                found.append("%s is not a carrier (no Bash, or it has Agent) but carries the section" % name)
            continue
        if count != 1:
            found.append("%s has %d sections" % (name, count))
            continue
        section = section_of(text)
        folded[name] = fold(section)
        start = text.index("\n" + HEADING + "\n")
        heads = report_heading_at(text)
        if len(heads) != 1:
            found.append("%s has %d report headings" % (name, len(heads)))
        elif heads[0] > start:
            found.append("%s: the section sits before its report heading" % name)
        lines, nblocks = fence_lines(section)
        if lines is None or nblocks != 1:
            found.append("%s: the section has %d fences, wants 1" % (name, nblocks))
            continue
        labels = [l.split(":", 1)[0] for l in lines]
        if labels != LABELS:
            found.append("%s: fence labels are %s" % (name, labels))
            continue
        words = [w.strip() for w in lines[0].split(":", 1)[1].split("|")]
        if words != statuses:
            found.append("%s: Status line says %s, run-plan says %s" % (name, words, statuses))
        bullet_words = re.findall(r"^- `([A-Z_]+)`:", section, re.M)
        if bullet_words != statuses:
            found.append("%s: the section's status bullets are %s, run-plan says %s" % (name, bullet_words, statuses))
        if any(FINDING_LABEL.match(l) for l in lines):
            found.append("%s: a fence line matches the pattern for a per-finding Verified line" % name)
        # a per-finding line elsewhere in the file must still be the first `Verified:` line
        outside = text[:start] + text[start + len(HEADING) + 2 + len(section):]
        if FINDING_LABEL.search(outside):
            first = re.search(r"^Verified:", text, re.M)
            if first is None or first.start() > start:
                found.append("%s: the first `Verified:` line in the file is the section's, not the findings'" % name)
    if len(set(folded.values())) > 1:
        found.append("copies differ between: %s" % sorted(folded))
    return found


def pin_problems(texts, plan_text):
    """The handful of wording pins the plan names."""
    found = []

    def need(cond, msg):
        if not cond:
            found.append(msg)

    def between(text, start, end):
        i = text.index(start)
        return text[i: text.index(end, i + len(start))]

    dev = texts["devops"]
    slot = fold(between(dev, "## What to Report Back", "## How Every Report Opens"))
    need("you can't undo" in slot, "devops lost its stop-before-a-command slot")
    stop = slot[slot.find("you can't undo"):].split(" - ")[0]  # the first stop slot; a later one names NEEDS_CONTEXT too
    need("NEEDS_CONTEXT" in stop, "devops slot lost NEEDS_CONTEXT")

    qa = fold(texts["qa"])
    need("at the top of your report" not in qa, "qa still says 'at the top of your report'")
    need("four opening lines" in qa, "qa's spec section no longer follows the four opening lines")

    impl = texts["implement"]
    steps = fold(between(impl, "## How to Work", "\n## Quality Baseline"))
    need("type checker" in steps and "Never install one" in steps, "implement's How to Work lost the linter/type-checker step")

    te = texts["test-engineer"]
    mid = between(te, "6. **Run what you wrote", "## What Makes a Good Test Here")
    need("**Run new tests more than once.**" in mid, "test-engineer's step 7 isn't between step 6 and What Makes a Good Test")
    need("five times" in fold(mid), "test-engineer's step 7 lost 'five times'")
    need("How many times the new tests ran" in fold(between(te, "## What to Report Back", "## How Every Report Opens")),
         "test-engineer lost the run-count slot")

    need("four opening lines" in fold(plan_text), "run-plan's dispatch lost 'four opening lines'")
    return found


def flat_sub(text, old, new):
    """Replace the first occurrence of `old` however its line breaks fall."""
    pattern = r"\s+".join(re.escape(w) for w in old.split())
    return re.sub(pattern, lambda m: new, text, count=1)


def without_section(text):
    start = text.index("\n" + HEADING + "\n")
    body = section_of(text)
    cut = text[:start] + text[start + len(HEADING) + 2 + len(body):]
    return cut


def with_agent_tool(text):
    assert "  - Bash\n" in text
    return text.replace("  - Bash\n", "  - Bash\n  - Agent\n", 1)


class RealTreeTest(unittest.TestCase):
    def test_the_rule_finds_exactly_the_eight_reporting_agents_and_each_carries_one_section(self):
        texts = agent_texts()
        got = carriers_of(texts)
        self.assertEqual(len(got), 8, got)
        self.assertNotIn("investigate", got)
        self.assertNotIn("file-reader", got)
        for name, text in texts.items():
            with self.subTest(agent=name):
                self.assertEqual(text.count("\n" + HEADING + "\n"), 1 if name in got else 0)

    def test_copies_fence_status_words_and_placement_all_hold(self):
        self.assertEqual(problems(agent_texts(), run_plan_text()), [])

    def test_the_wording_pins_hold(self):
        self.assertEqual(pin_problems(agent_texts(), run_plan_text()), [])

    def test_qas_first_verified_line_is_in_output_formats_findings_block(self):
        text = agent_texts()["qa"]
        first = re.search(r"^Verified:.*$", text, re.M)
        out = text.index("\n## Output Format\n")
        self.assertGreater(first.start(), out)
        self.assertLess(first.start(), text.index("\n" + HEADING + "\n"))
        self.assertIn("`ran <the command or test", first.group(0))

    def test_the_section_is_not_in_investigate_or_file_reader(self):
        texts = agent_texts()
        for name in ("investigate", "file-reader"):
            self.assertNotIn(HEADING, texts[name])


class MutationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = agent_texts()
        cls.plan = run_plan_text()
        assert problems(cls.base, cls.plan) == [] and pin_problems(cls.base, cls.plan) == []

    def mutated(self, **edits):
        texts = dict(self.base)
        for name, fn in edits.items():
            new = fn(texts[name.replace("_", "-")])
            self.assertNotEqual(new, texts[name.replace("_", "-")], "the mutation changed nothing")
            texts[name.replace("_", "-")] = new
        return texts

    def caught(self, texts, plan=None, needle=""):
        found = problems(texts, plan or self.plan)
        self.assertTrue(any(needle in p for p in found), found)

    def test_a_rewrapped_copy_holds(self):
        def rewrap(t):
            body = section_of(t)
            new = body.replace("before anything else, and open a\nreport file", "before anything else,\nand open a report file")
            new = new.replace("\n  for one,", " for one,").replace("\n  check.", " check.")
            return t.replace(body, new, 1)
        texts = self.mutated(docs=rewrap, qa=rewrap)
        self.assertEqual(problems(texts, self.plan), [])

    def test_one_changed_word_in_any_one_copy_fails(self):
        for victim in carriers_of(self.base):
            for old, new in (("before anything else", "after anything else"), ("Never write", "Do write"),
                             ("by reading", "by guessing")):
                with self.subTest(victim=victim, change=old):
                    def edit(t, old=old, new=new):
                        body = section_of(t)
                        self.assertIn(old, body)
                        return t.replace(body, body.replace(old, new, 1), 1)
                    self.caught(self.mutated(**{victim: edit}), needle="differ")

    def test_the_section_added_to_investigate_or_file_reader_fails(self):
        copy = "\n" + HEADING + "\n" + section_of(self.base["architect"])
        for name in ("investigate", "file-reader"):
            with self.subTest(agent=name):
                texts = self.mutated(**{name: lambda t: t.rstrip("\n") + "\n" + copy})
                self.caught(texts, needle="%s is not a carrier" % name)

    def test_docs_given_an_agent_tool_with_the_section_kept_fails(self):
        self.caught(self.mutated(docs=with_agent_tool), needle="docs is not a carrier")

    def test_an_agent_given_bash_without_the_section_fails(self):
        # file-reader gains Bash: the rule from the front matter now makes it a carrier
        texts = self.mutated(file_reader=lambda t: t.replace("  - Read\n", "  - Read\n  - Bash\n", 1))
        self.caught(texts, needle="file-reader has 0 sections")

    def test_the_section_dropped_from_a_carrier_fails(self):
        for victim in carriers_of(self.base):
            with self.subTest(victim=victim):
                self.caught(self.mutated(**{victim: without_section}), needle="%s has 0 sections" % victim)

    def test_the_section_pasted_twice_in_one_agent_fails(self):
        def twice(t):
            body = section_of(t)
            return t.replace(body, body + "\n" + HEADING + "\n" + body, 1)
        self.caught(self.mutated(architect=twice), needle="architect has 2 sections")

    def test_a_section_before_its_report_heading_fails_in_every_carrier(self):
        for victim in carriers_of(self.base):
            with self.subTest(victim=victim):
                def move(t):
                    body = section_of(t)
                    start = t.index("\n" + HEADING + "\n")
                    stripped = t[:start] + t[start + len(HEADING) + 2 + len(body):]
                    head = min(report_heading_at(stripped))
                    block = "\n" + HEADING + "\n" + body.rstrip("\n") + "\n\n---\n\n"
                    return stripped[:head] + block.lstrip("\n") + stripped[head:]
                self.caught(self.mutated(**{victim: move}), needle="%s: the section sits before" % victim)

    def test_qa_with_the_section_above_output_format_fails_even_with_the_fence_line_harmless(self):
        def move(t):
            body = section_of(t)
            start = t.index("\n" + HEADING + "\n")
            stripped = t[:start].rstrip("\n").rstrip("-").rstrip("\n") + "\n"
            i = stripped.index("## Output Format")
            return stripped[:i] + HEADING + "\n" + body.rstrip("\n") + "\n\n---\n\n" + stripped[i:]
        texts = self.mutated(qa=move)
        found = problems(texts, self.plan)
        self.assertTrue(any("sits before its report heading" in p for p in found), found)
        self.assertTrue(any("first `Verified:` line" in p for p in found), found)

    def test_a_fence_with_five_lines_or_labels_out_of_order_fails(self):
        extra = lambda t: t.replace('Concerns: <what', 'Commands run: <x>\nConcerns: <what', 1)  # noqa: E731
        self.caught(self.mutated(implement=extra), needle="implement: fence labels")
        texts = dict(self.base)
        body = section_of(texts["frontend"])
        lines = body.split("\n")
        i = next(n for n, l in enumerate(lines) if l.startswith("Files changed:"))
        lines[i], lines[i + 1] = lines[i + 1], lines[i]
        texts["frontend"] = texts["frontend"].replace(body, "\n".join(lines), 1)
        self.caught(texts, needle="frontend: fence labels")

    def test_a_missing_label_and_a_second_fence_fail(self):
        self.caught(self.mutated(uiux=lambda t: t.replace("Concerns: <what the reader should weigh before relying on this, or \"none\">\n", "", 1)),
                    needle="uiux: fence labels")
        extra = lambda t: t.replace("\n- `Verified` covers", "\n```\nx\n```\n\n- `Verified` covers", 1)  # noqa: E731
        self.caught(self.mutated(devops=extra), needle="devops: the section has 2 fences")

    def test_a_status_line_that_drifts_from_run_plan_fails_in_either_file(self):
        # the fence line changes in one copy
        fence = lambda t: t.replace("NEEDS_CONTEXT | BLOCKED", "NEEDS_INPUT | BLOCKED", 1)  # noqa: E731
        self.caught(self.mutated(docs=fence), needle="docs: Status line says")
        # a bullet changes in one copy
        bullet = lambda t: t.replace("- `BLOCKED`:", "- `STUCK`:", 1)  # noqa: E731
        self.caught(self.mutated(docs=bullet), needle="docs: the section's status bullets")
        # run-plan's bolded word changes, the copies untouched
        plan = self.plan.replace("- **NEEDS_CONTEXT**:", "- **NEEDS_ANSWER**:", 1)
        self.assertNotEqual(plan, self.plan)
        found = problems(self.base, plan)
        self.assertTrue(all(any(n in p for p in found) for n in carriers_of(self.base)), found)
        # run-plan loses a status altogether
        plan = self.plan.replace("- **BLOCKED**:", "- BLOCKED:", 1)
        self.assertNotEqual(plan, self.plan)
        self.assertTrue(problems(self.base, plan))

    def test_a_status_line_in_another_order_fails(self):
        fence = lambda t: t.replace("DONE | DONE_WITH_CONCERNS", "DONE_WITH_CONCERNS | DONE", 1)  # noqa: E731
        self.caught(self.mutated(architect=fence), needle="architect: Status line says")

    def test_a_verified_fence_line_the_findings_pattern_would_match_fails(self):
        mutated = lambda t: t.replace("Verified: <ran `<command>` (exit <n>)", "Verified: `ran <command>` (exit <n>)", 1)  # noqa: E731
        texts = self.mutated(qa=mutated)
        self.assertTrue(FINDING_LABEL.search(section_of(texts["qa"])))
        self.caught(texts, needle="qa: a fence line matches the pattern")
        self.caught(self.mutated(implement=mutated), needle="implement: a fence line matches")

    def test_the_pins_each_catch_their_mutation(self):
        cases = {
            "devops slot": ("devops", lambda t: flat_sub(t, "your status is `NEEDS_CONTEXT`", "go on"), "NEEDS_CONTEXT"),
            "qa top": ("qa", lambda t: flat_sub(t, "Put a spec section first in your report", "Put a spec section at the top of your report"), "top of your report"),
            "qa after": ("qa", lambda t: flat_sub(t, "right after its four opening lines", "right after headers"), "four opening lines"),
            "implement checker": ("implement", lambda t: flat_sub(t, "type checker", "typo"), "type-checker step"),
            "implement install": ("implement", lambda t: flat_sub(t, "Never install one", "Install it"), "type-checker step"),
            "te step moved": ("test-engineer", lambda t: t.replace("**Run new tests more than once.**", "**Rerun.**", 1), "step 7"),
            "te five": ("test-engineer", lambda t: flat_sub(t, "at least five times", "at least twice"), "five times"),
            "te slot": ("test-engineer", lambda t: flat_sub(t, "How many times the new tests ran", "How tests went"), "run-count"),
        }
        for label, (name, fn, needle) in cases.items():
            with self.subTest(pin=label):
                texts = self.mutated(**{name: fn})
                found = pin_problems(texts, self.plan)
                self.assertTrue(any(needle in p for p in found), found)
        self.assertTrue(any("four opening lines" in p for p in
                            pin_problems(self.base, self.plan.replace("four opening lines", "status lines"))))

    def test_test_engineer_step_7_after_what_makes_a_good_test_fails_the_pin(self):
        def move(t):
            i = t.index("7. **Run new tests more than once.**")
            j = t.index("\n## What Makes a Good Test Here")
            step = t[i:j].rstrip("\n") + "\n"
            rest = t[:i] + t[j:]
            k = rest.index("\n---\n", rest.index("## What Makes a Good Test Here"))
            return rest[:k] + "\n" + step + rest[k:]
        found = pin_problems(self.mutated(test_engineer=move), self.plan)
        self.assertTrue(any("step 7" in p for p in found), found)


if __name__ == "__main__":
    unittest.main()
