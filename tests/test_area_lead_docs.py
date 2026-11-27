"""AC-6: the docs count eleven agents, and the lines that say who starts which agent name the area lead.

Contract pins only: each check looks for a name or a count, never a sentence. Hermetic: reads tracked files.
Standard library only.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def raw(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def fold(text):
    return " ".join(text.split())


DOCS = ["README.md", "docs/orchestrator.md", "PRIVACY.md", "CONTRIBUTING.md", "evals/README.md"]
TEN = re.compile(r"\bten[ -](?:specialized |specialist )?(?:agents?|-agent)\b|\bten-agent\b|\btenth agent\b", re.I)


class AgentCountTest(unittest.TestCase):
    def test_no_current_doc_counts_ten_agents(self):
        for rel in DOCS:
            for n, line in enumerate(raw(rel).splitlines(), 1):
                if TEN.search(line) and "tenth agent, the four skills" not in line:
                    self.fail("%s:%d still counts ten agents: %s" % (rel, n, line.strip()))

    def test_the_readme_and_orchestrator_count_eleven(self):
        self.assertIn("eleven specialized subagents", fold(raw("README.md")))
        self.assertIn("eleven agents", fold(raw("docs/orchestrator.md")))

    def test_there_are_eleven_agent_files(self):
        self.assertEqual(len(list((ROOT / "agents").glob("*.md"))), 11)


class WhoStartsWhomTest(unittest.TestCase):
    def test_the_orchestrator_says_file_reader_is_dispatched_only_by_investigate_and_area_lead(self):
        text = fold(raw("docs/orchestrator.md"))
        m = re.search(r"`file-reader` is dispatched only by ([^.]*)\.", text)
        self.assertIsNotNone(m)
        self.assertIn("`investigate`", m.group(1))
        self.assertIn("`area-lead`", m.group(1))

    def test_the_orchestrator_says_area_lead_is_started_only_by_investigate(self):
        self.assertRegex(fold(raw("docs/orchestrator.md")), r"`area-lead` only by `investigate`")

    def test_the_readme_has_investigate_start_both_and_area_lead_start_only_file_reader(self):
        text = fold(raw("README.md"))
        self.assertIn("`investigate` starts `file-reader` and `area-lead`", text)
        self.assertIn("`area-lead` starts only `file-reader`", text)

    def test_the_readme_has_no_line_saying_investigate_starts_only_file_reader(self):
        text = fold(raw("README.md"))
        self.assertNotRegex(text, r"`investigate` (?:starts|spawns) only `file-reader`")

    def test_the_readme_agent_table_has_an_area_lead_row_that_holds_no_edit_tools(self):
        rows = [l for l in raw("README.md").splitlines() if l.startswith("| `area-lead` |")]
        self.assertEqual(len(rows), 1)
        self.assertIn("| No |", rows[0])

    def test_privacy_names_area_lead_next_to_investigate(self):
        text = fold(raw("PRIVACY.md"))
        m = re.search(r"`investigate` starts .*?(?=Nothing is copied)", text)
        self.assertIsNotNone(m)
        self.assertIn("`area-lead`", m.group(0))

    def test_contributing_names_all_three_agents_in_the_a_change_to_line(self):
        text = fold(raw("CONTRIBUTING.md"))
        m = re.search(r"A change to `investigate`[^.]*", text)
        self.assertIsNotNone(m)
        self.assertIn("`area-lead`", m.group(0))
        self.assertIn("`file-reader`", m.group(0))

    def test_every_every_agent_but_line_names_area_lead(self):
        seen = 0
        for rel in ["README.md", "docs/orchestrator.md"]:
            for line in raw(rel).splitlines():
                if re.search(r"Every agent but `?investigate", line):
                    seen += 1
                    self.assertIn("area-lead", line, "%s: %s" % (rel, line.strip()))
        self.assertGreaterEqual(seen, 2)

    def test_every_read_only_list_in_the_readme_names_area_lead(self):
        for n, line in enumerate(raw("README.md").splitlines(), 1):
            if re.search(r"[Rr]ead-only agents? \(|read-only agents \(investigate", line):
                self.assertIn("area-lead", line, "README.md:%d" % n)


class EvalsReadmeRevParseTest(unittest.TestCase):
    def test_every_rev_parse_line_naming_investigate_and_file_reader_also_names_area_lead(self):
        lines = [l for l in raw("evals/README.md").splitlines()
                 if "rev-parse" in l and "agents/investigate.md" in l and "agents/file-reader.md" in l]
        self.assertGreaterEqual(len(lines), 2)
        for l in lines:
            self.assertIn("HEAD:agents/area-lead.md", l)

    def test_the_head_to_head_after_a_change_is_four_runs(self):
        self.assertRegex(fold(raw("evals/README.md")), r"--runs 4\b")


class ChangelogTopEntryTest(unittest.TestCase):
    def setUp(self):
        self.text = raw("CHANGELOG.md")
        self.first = re.search(r"^## .*$", self.text, re.M).group(0)

    def test_the_top_entry_is_unreleased(self):
        self.assertEqual(self.first, "## [Unreleased]")

    def test_the_top_entry_says_an_old_copy_of_investigate_must_be_copied_again(self):
        m = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", self.text, re.M | re.S)
        self.assertIsNotNone(m)
        entry = fold(m.group(1))
        self.assertIn("copy of `investigate` made before this release must be copied again", entry)

    def test_the_top_entry_names_the_new_agent_and_the_major_version(self):
        m = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", self.text, re.M | re.S)
        entry = fold(m.group(1))
        self.assertIn("`area-lead`", entry)
        self.assertRegex(entry, r"major version|3\.0\.0")


if __name__ == "__main__":
    unittest.main()
