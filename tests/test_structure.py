"""Structural checks: the repo agrees with itself.

The README makes promises about the team (who can write, which model each
agent runs, which agents are locked into plan mode, how many agents and
skills there are), and the agent and skill files either keep them or they
don't. Nothing used to check. These tests read the files and fail on drift,
which so far has meant "three skills" lingering in three places after a fourth
landed, a skill pointing at a script that moved, and the kind of thing a
release preflight only catches if someone thinks to grep for it.

Standard library only. The front-matter parser handles the subset these files
use (scalar `key: value` lines and one-level `- item` lists), not all of YAML.
"""

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "agents"
SKILLS = ROOT / "skills"
README = ROOT / "README.md"
ORCHESTRATOR = ROOT / "docs" / "orchestrator.md"
CHANGELOG = ROOT / "CHANGELOG.md"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
EVALS = ROOT / "evals"

MODELS = {"opus", "sonnet", "haiku", "inherit"}
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
NUMBER_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
    7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve",
}


def front_matter(path):
    """Return the front matter of a Markdown file as a dict (lists for `- item` blocks)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise AssertionError(f"{path.relative_to(ROOT)}: no front matter")
    data, key = {}, None
    for line in lines[1:]:
        if line.strip() == "---":
            return data
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and key:
            if not isinstance(data[key], list):
                data[key] = []
            data[key].append(item.group(1).strip())
            continue
        pair = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if pair:
            key, value = pair.group(1), pair.group(2).strip()
            data[key] = value.strip('"') if value else []
    raise AssertionError(f"{path.relative_to(ROOT)}: front matter never closes")


def agents():
    return {p.stem: front_matter(p) for p in sorted(AGENTS.glob("*.md"))}


def skills():
    return {p.parent.name: front_matter(p) for p in sorted(SKILLS.glob("*/SKILL.md"))}


def readme_team_table():
    """Rows of the README's team table: {agent: {"writes": ..., "model": ...}}."""
    rows = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"`[\w-]+`", cells[0]):
            rows[cells[0].strip("`")] = {"writes": cells[2], "model": cells[3]}
    return rows


class AgentFilesTest(unittest.TestCase):
    def test_every_agent_has_valid_front_matter(self):
        self.assertTrue(agents(), "no agents found")
        for name, fm in agents().items():
            with self.subTest(agent=name):
                self.assertEqual(fm.get("name"), name, "name must match the file name")
                self.assertTrue(fm.get("description"), "description is empty")
                self.assertIn(fm.get("model"), MODELS)
                tools = fm.get("tools")
                self.assertIsInstance(tools, list, "tools must be a list")
                self.assertTrue(tools, "tools list is empty")
                self.assertEqual(len(tools), len(set(tools)), "a tool is listed twice")

    def test_readme_team_table_matches_the_agent_files(self):
        table, files = readme_team_table(), agents()
        self.assertEqual(set(table), set(files), "README team table and agents/ list different agents")
        for name, row in table.items():
            with self.subTest(agent=name):
                fm = files[name]
                self.assertEqual(row["model"], fm["model"], "README model column disagrees")
                writes = WRITE_TOOLS & set(fm["tools"])
                if row["writes"].startswith("No"):
                    self.assertFalse(writes, f"README says read-only, but tools include {sorted(writes)}")
                else:
                    self.assertTrue(writes, "README says it writes, but it has no Edit or Write tool")

    def test_plan_mode_agents_are_the_ones_the_readme_names(self):
        text = README.read_text(encoding="utf-8")
        m = re.search(r"((?:`[\w-]+`(?:,|\s+and)?\s+)+)also carry\s+`permissionMode: plan`", text)
        self.assertIsNotNone(m, "README no longer names the plan-mode agents")
        named = set(re.findall(r"`([\w-]+)`", m.group(1)))
        in_files = {n for n, fm in agents().items() if fm.get("permissionMode") == "plan"}
        self.assertEqual(named, in_files)

    def test_uiux_browser_tools_are_observation_only(self):
        # README: uiux holds the observation set, "no form input or scripting".
        tools = set(agents()["uiux"]["tools"])
        for banned in ("mcp__Claude_Browser__form_input", "mcp__Claude_Browser__javascript_tool"):
            self.assertNotIn(banned, tools)


class SkillFilesTest(unittest.TestCase):
    def test_every_skill_has_valid_front_matter(self):
        self.assertTrue(skills(), "no skills found")
        for name, fm in skills().items():
            with self.subTest(skill=name):
                self.assertEqual(fm.get("name"), name, "name must match the directory")
                description = fm.get("description") or ""
                self.assertTrue(description, "description is empty")
                self.assertLessEqual(len(description), 1024, "description is over 1024 characters")

    def test_files_a_skill_points_at_exist(self):
        for path in sorted(SKILLS.glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            for ref in sorted(set(re.findall(r"`((?:scripts|references)/[\w./-]+)", text))):
                target = path.parent / ref
                with self.subTest(skill=path.parent.name, ref=ref):
                    self.assertTrue(target.exists(), f"{ref} doesn't exist")
                    if ref.startswith("scripts/"):
                        self.assertTrue(os.access(target, os.X_OK), f"{ref} isn't executable")
                        self.assertTrue(target.read_text(encoding="utf-8").startswith("#!"), f"{ref} has no shebang")

    def test_every_script_is_tested(self):
        # A script nobody tests is how the task-brief fence bug shipped.
        tests = " ".join(p.read_text(encoding="utf-8") for p in (ROOT / "tests").glob("test_*.py"))
        for script in sorted(SKILLS.glob("*/scripts/*")):
            with self.subTest(script=script.name):
                self.assertTrue(script.name in tests, f"no test mentions {script.name}")


class DocsAgreeTest(unittest.TestCase):
    def test_counts_match(self):
        n_agents, n_skills = NUMBER_WORDS[len(agents())], NUMBER_WORDS[len(skills())]
        readme = README.read_text(encoding="utf-8")
        orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")
        plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
        marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        checks = [
            ("README", readme, rf"is {n_agents} specialized subagents"),
            ("README", readme, rf"\b{n_skills} skills that session runs itself"),
            ("README install", readme, rf"{n_agents} agents and {n_skills} skills are now available"),
            ("orchestrator", orchestrator, rf"A {n_agents}-agent development team"),
            ("orchestrator", orchestrator, rf"plus {n_skills} skills this\s+session runs itself"),
            ("plugin.json", plugin["description"], rf"{n_agents} specialized subagents"),
            ("marketplace.json", marketplace["description"], rf"{n_agents}-agent"),
        ]
        for where, text, pattern in checks:
            with self.subTest(where=where, pattern=pattern):
                self.assertRegex(text, pattern)

    def test_every_skill_is_documented_everywhere(self):
        readme = README.read_text(encoding="utf-8")
        orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")
        description = json.loads(PLUGIN.read_text(encoding="utf-8"))["description"]
        for name in skills():
            with self.subTest(skill=name):
                self.assertIn(f"| `{name}` |", readme, "missing from the README's skills table")
                self.assertIn(f"/the-foundry:{name}", readme, "missing from the README's install list")
                self.assertIn(f"`{name}`", orchestrator, "missing from the orchestrator block")
                self.assertIn(name, description, "missing from plugin.json's description")

    def test_marketplace_entry_matches_plugin_json(self):
        plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
        entries = json.loads(MARKETPLACE.read_text(encoding="utf-8"))["plugins"]
        entry = next(e for e in entries if e["name"] == plugin["name"])
        self.assertEqual(entry["description"], plugin["description"])

    def test_version_matches_the_newest_changelog_entry(self):
        version = json.loads(PLUGIN.read_text(encoding="utf-8"))["version"]
        headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", CHANGELOG.read_text(encoding="utf-8"), re.M)
        self.assertTrue(headings, "CHANGELOG has no version headings")
        self.assertEqual(headings[0], version, "plugin.json's version isn't the newest CHANGELOG entry")
        as_tuples = [tuple(map(int, h.split("."))) for h in headings]
        self.assertEqual(as_tuples, sorted(set(as_tuples), reverse=True), "CHANGELOG versions out of order or repeated")

    def test_namespaced_references_point_at_real_agents_and_skills(self):
        known = set(agents()) | set(skills())
        files = [README, ORCHESTRATOR, *AGENTS.glob("*.md"), *SKILLS.glob("*/SKILL.md"), *SKILLS.glob("*/references/*.md"),
                 *EVALS.glob("*/prompt.md")]
        for path in files:
            for ref in sorted(set(re.findall(r"the-foundry:([a-z][\w-]*)", path.read_text(encoding="utf-8")))):
                with self.subTest(file=str(path.relative_to(ROOT)), ref=ref):
                    self.assertIn(ref, known, f"the-foundry:{ref} names nothing that exists")


def eval_cases():
    return sorted(p.parent for p in EVALS.glob("*/prompt.md"))


class EvalLibraryTest(unittest.TestCase):
    """evals/ holds the behavior cases `claude plugin eval .` runs; see evals/README.md."""

    def test_every_case_is_complete(self):
        self.assertTrue(eval_cases(), "no eval cases found")
        for case in eval_cases():
            with self.subTest(case=case.name):
                fm = front_matter(case / "prompt.md")
                self.assertTrue(fm.get("tags"), "prompt.md has no tags")
                self.assertTrue(list((case / "graders").glob("*.md")), "no graders")
                yaml = case / "case.yaml"
                if yaml.exists():
                    text = yaml.read_text(encoding="utf-8")
                    self.assertIn(f"name: {case.name}", text, "case.yaml's name doesn't match its folder")
                    m = re.search(r"scaffold_script:\s*(\S+)", text)
                    if m:
                        script = case / m.group(1)
                        self.assertTrue(script.exists(), f"{m.group(1)} doesn't exist")
                        self.assertTrue(os.access(script, os.X_OK), f"{m.group(1)} isn't executable")
                        self.assertNotIn("..", m.group(1), "scaffold must live inside the case folder")

    def test_every_skill_has_cases(self):
        tagged = set()
        for case in eval_cases():
            tagged.update(t.strip() for t in front_matter(case / "prompt.md")["tags"].strip("[]").split(","))
        for name in skills():
            with self.subTest(skill=name):
                self.assertIn(name, tagged, f"no eval case is tagged {name}")


class DirectoryScannerTest(unittest.TestCase):
    """Text the plugin directory's scanner has held or flagged before.

    Each of these held or flagged a release of the Foundry (1.7.0 to 1.7.3),
    every time on harmless text, and the directory rescans every new version.
    So they're cheaper to keep out than to explain to a reviewer again.
    """

    def tracked_text_files(self):
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True)
        for rel in out.stdout.splitlines():
            path = ROOT / rel
            if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                continue
            yield rel, path.read_text(encoding="utf-8", errors="replace")

    def test_no_known_scanner_triggers(self):
        # Built from pieces, so this file never spells out what it's looking for.
        EVAL, BT, ICON = "ev" + "al", chr(96), "icon" + ".png"
        ENV = re.escape("os." + "env" + "iron")
        patterns = {
            "the e-v-a-l word right before a backtick (read as running a download)": re.compile(EVAL + BT),
            "a line starting with the p-a-s-s word (read as a password manager)": re.compile(r"^[ \t]*" + "pa" + r"ss([ \t]|$)", re.M),
            "an n-p-x download-and-run command": re.compile("np" + r"x\s+@?[\w.-]"),
            "the whole environment passed along": re.compile(r"\*\*" + ENV + "|dict\\(" + ENV + "\\)|" + ENV + r"\.copy\(\)"),
            "an environment variable read by a computed name": re.compile(ENV + r"\[(?![\"'])"),
            "the icon's file name (holds the release for a reviewer)": re.compile(re.escape(ICON)),
        }
        for rel, text in self.tracked_text_files():
            # The scanner reads a regex-escaped trigger (a backslash before each
            # dot or bracket) as the real thing, so match with backslashes removed.
            text = text.replace(chr(92), "")
            for why, pattern in patterns.items():
                m = pattern.search(text)
                with self.subTest(file=rel, pattern=why):
                    self.assertTrue(m is None, f"{rel}: {why}: {m.group(0) if m else ''!r}")


if __name__ == "__main__":
    unittest.main()
