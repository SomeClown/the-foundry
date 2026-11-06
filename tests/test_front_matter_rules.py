"""Adversarial checks for the front-matter rules (Task 1 of directory-file-rules).

Two halves. The first drives tests/test_structure.py's `front_matter` parser
with tricky values (quotes, escapes, `#`, colons). The second copies the
tracked tree to a temp dir, breaks a rule there, and runs the real keys test
in the copy, to prove the guard fails when it should. Nothing touches the
working tree, nothing needs the network or a model session.

Standard library only.
"""

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_structure as ts  # noqa: E402

ROOT = ts.ROOT
KEYS_TEST = "test_structure.AgentFilesTest.test_front_matter_keys_are_the_ones_the_directory_takes"
VALID_TEST = "test_structure.AgentFilesTest.test_every_agent_has_valid_front_matter"

AGENT = """---
name: {name}
description: "A test agent."
tools:
  - Read
model: haiku
{extra}---
body
"""


def parse(text):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.md"
        p.write_text(text, encoding="utf-8")
        # relative_to(ROOT) is only used in error messages; give errors a usable path
        try:
            return ts.front_matter(p)
        except ValueError:
            raise AssertionError("parser error path")


def desc(raw_value_line):
    return parse(f"---\nname: x\n{raw_value_line}\n---\n").get("description")


class QuoteParserTest(unittest.TestCase):
    def test_escaped_quote_is_unescaped(self):
        self.assertEqual(desc(r'description: "say \"hi\" now"'), 'say "hi" now')

    def test_escaped_backslash_is_unescaped(self):
        self.assertEqual(desc(r'description: "a\\b"'), "a\\b")

    def test_backslash_then_quote_sequence(self):
        # \\\" is backslash, then quote
        self.assertEqual(desc(r'description: "a\\\"b"'), 'a\\"b')

    def test_escaped_backslash_at_end_of_value(self):
        self.assertEqual(desc(r'description: "ends with \\"'), "ends with \\")

    def test_unterminated_quote_is_not_silently_accepted(self):
        # "abc\" is an unterminated string in YAML (the last quote is escaped).
        with self.assertRaises(AssertionError):
            desc(r'description: "abc\"')

    def test_single_quoted_value_loses_its_quotes(self):
        # YAML reads 'it''s fine' as: it's fine
        self.assertEqual(desc("description: 'plain text'"), "plain text")

    def test_hash_inside_double_quotes_is_kept(self):
        self.assertEqual(desc('description: "uses # inside"'), "uses # inside")

    def test_colon_inside_double_quotes_is_kept(self):
        self.assertEqual(desc('description: "Read-only: never writes"'), "Read-only: never writes")

    def test_empty_quoted_value_reads_as_empty(self):
        self.assertFalse(desc('description: ""'))

    def test_lone_quote_char_is_not_stripped_to_nothing(self):
        self.assertEqual(desc('description: "'), '"')

    def test_inner_quotes_without_outer_quotes_are_untouched(self):
        self.assertEqual(desc('description: say "hi" twice'), 'say "hi" twice')

    def test_quote_at_both_ends_only_for_matching_pair(self):
        self.assertEqual(desc("description: \"mixed'"), "\"mixed'")

    def test_key_with_space_before_colon_is_still_seen(self):
        # `permissionMode : plan` is valid YAML; the guard must not be blind to it.
        self.assertIn("permissionMode", parse("---\nname: x\npermissionMode : plan\n---\n"))

    def test_quoted_key_is_still_seen(self):
        self.assertIn("permissionMode", parse('---\nname: x\n"permissionMode": plan\n---\n'))

    def test_underscore_key_is_still_seen(self):
        self.assertIn("_hooks", parse("---\nname: x\n_hooks: y\n---\n"))


class ShippedValuesTest(unittest.TestCase):
    """Guards on the real files, so the quoting can't rot back into invalid YAML."""

    def raw_front_matter_lines(self):
        for path in [*sorted(ts.AGENTS.glob("*.md")), *sorted(ts.SKILLS.glob("*/SKILL.md"))]:
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                yield path.relative_to(ROOT), line

    def test_no_unquoted_value_holds_a_colon_space_or_comment(self):
        for rel, line in self.raw_front_matter_lines():
            m = re.match(r"^([A-Za-z][\w-]*):\s*(.+)$", line)
            if not m:
                continue
            value = m.group(2).strip()
            if value[0] in "\"'":
                continue
            with self.subTest(file=str(rel), key=m.group(1)):
                self.assertNotIn(": ", value, "unquoted ': ' is invalid YAML")
                self.assertNotRegex(value, r"\s#", "unquoted ' #' starts a YAML comment")

    def test_no_value_is_single_quoted(self):
        for rel, line in self.raw_front_matter_lines():
            m = re.match(r"^([A-Za-z][\w-]*):\s*'", line)
            with self.subTest(file=str(rel), line=line[:40]):
                self.assertIsNone(m, "the parser doesn't unquote single-quoted values")

    def test_double_quoted_values_only_use_the_two_escapes_the_parser_knows(self):
        for rel, line in self.raw_front_matter_lines():
            m = re.match(r'^([A-Za-z][\w-]*):\s*"(.*)"\s*$', line)
            if not m:
                continue
            with self.subTest(file=str(rel), key=m.group(1)):
                body = m.group(2)
                self.assertNotRegex(body, r'(?<!\\)(\\\\)*"', "an unescaped inner quote")
                self.assertNotRegex(re.sub(r"\\[\\\"]", "", body), r"\\", "a backslash escape the parser can't read")

    def test_every_quoted_value_closes_on_its_own_line(self):
        for rel, line in self.raw_front_matter_lines():
            m = re.match(r'^([A-Za-z][\w-]*):\s*"', line)
            if not m:
                continue
            with self.subTest(file=str(rel), key=m.group(1)):
                self.assertTrue(re.search(r'(?<!\\)(\\\\)*"\s*$', line), "quote doesn't close")

    def test_no_parsed_description_keeps_a_stray_backslash_or_edge_quote(self):
        for kind, table in (("agent", ts.agents()), ("skill", ts.skills())):
            for name, fm in table.items():
                d = fm["description"]
                with self.subTest(**{kind: name}):
                    self.assertFalse(d.startswith('"') and d.endswith('"'), "quotes survived parsing")
                    self.assertNotIn("\\", d)
                    self.assertEqual(d, d.strip())

    def test_tools_lists_are_plain_lists_of_nonempty_strings(self):
        for name, fm in ts.agents().items():
            with self.subTest(agent=name):
                self.assertIsInstance(fm["tools"], list)
                self.assertTrue(all(isinstance(t, str) and t for t in fm["tools"]))

    def test_no_stray_permission_mode_anywhere_in_shipped_front_matter(self):
        for rel, line in self.raw_front_matter_lines():
            with self.subTest(file=str(rel)):
                self.assertNotRegex(line, r"(?i)permission[-_ ]?mode")


class MutatedCopyTest(unittest.TestCase):
    """Break a rule in a throwaway copy of the tracked tree; the guard must fail there."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.copy = Path(cls.tmp.name) / "repo"
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True)
        for rel in out.stdout.splitlines():
            src = ROOT / rel
            if not src.exists() or not (rel.startswith(("agents/", "skills/", "tests/", "docs/", ".claude-plugin/", "evals/"))
                                        or rel in ("README.md", "CHANGELOG.md")):
                continue
            dst = cls.copy / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_test(self, which):
        return subprocess.run(
            [sys.executable, "-m", "unittest", which],
            cwd=self.copy / "tests", capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def mutate(self, rel, fn):
        path = self.copy / rel
        original = path.read_text(encoding="utf-8")
        self.addCleanup(path.write_text, original, encoding="utf-8")
        path.write_text(fn(original), encoding="utf-8")

    def add_agent(self, extra, name="newbie"):
        path = self.copy / "agents" / f"{name}.md"
        path.write_text(AGENT.format(name=name, extra=extra), encoding="utf-8")
        self.addCleanup(path.unlink)

    def assertGuardFails(self, which, *needles):
        r = self.run_test(which)
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, f"guard stayed green:\n{out[-800:]}")
        for n in needles:
            self.assertIn(n, out)

    def test_copy_is_green_before_any_mutation(self):
        r = self.run_test(KEYS_TEST)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_extra_key_added_to_a_skill_fails_the_keys_test(self):
        self.mutate("skills/ship/SKILL.md", lambda t: t.replace("\nname: ship\n", "\nname: ship\nallowed-tools: Bash\n", 1))
        self.assertGuardFails(KEYS_TEST, "allowed-tools", "ship")

    def test_tools_key_added_to_a_skill_fails_the_keys_test(self):
        self.mutate("skills/debug/SKILL.md", lambda t: t.replace("\nname: debug\n", "\nname: debug\nmodel: opus\n", 1))
        self.assertGuardFails(KEYS_TEST, "model", "debug")

    def test_permission_mode_in_a_new_agent_fails_the_keys_test(self):
        self.add_agent("permissionMode: plan\n")
        self.assertGuardFails(KEYS_TEST, "permissionMode", "newbie")

    def test_permission_mode_back_in_architect_fails_the_keys_test(self):
        self.mutate("agents/architect.md", lambda t: t.replace("model: opus\n", "model: opus\npermissionMode: plan\n", 1))
        self.assertGuardFails(KEYS_TEST, "permissionMode", "architect")

    def test_permission_mode_with_space_before_colon_fails_the_keys_test(self):
        self.add_agent("permissionMode : plan\n")
        self.assertGuardFails(KEYS_TEST, "permissionMode")

    def test_quoted_permission_mode_key_fails_the_keys_test(self):
        self.add_agent('"permissionMode": plan\n')
        self.assertGuardFails(KEYS_TEST, "permissionMode")

    def test_empty_valued_permission_mode_fails_the_keys_test(self):
        self.add_agent("permissionMode:\n")
        self.assertGuardFails(KEYS_TEST, "permissionMode")

    def test_hooks_key_in_a_new_agent_fails_the_keys_test(self):
        self.add_agent("hooks: x\n")
        self.assertGuardFails(KEYS_TEST, "hooks")

    def test_agent_with_emptied_tools_list_fails_the_valid_front_matter_test(self):
        def empty(t):
            return re.sub(r"(?m)^tools:\n(?:  - .*\n)+", "tools:\n", t, count=1)
        self.mutate("agents/qa.md", empty)
        self.assertGuardFails(VALID_TEST, "qa")

    def test_agent_with_tools_removed_entirely_fails_the_valid_front_matter_test(self):
        def drop(t):
            return re.sub(r"(?m)^tools:\n(?:  - .*\n)+", "", t, count=1)
        self.mutate("agents/qa.md", drop)
        self.assertGuardFails(VALID_TEST, "qa")

    def test_readme_losing_the_sentence_fails_the_readme_test(self):
        self.mutate("README.md", lambda t: t.replace("No agent carries `permissionMode`", "Two agents carry `permissionMode`"))
        self.assertGuardFails("test_structure.AgentFilesTest.test_readme_says_no_agent_carries_permission_mode", "permissionMode")

    def test_readme_sentence_split_across_lines_still_passes(self):
        self.mutate("README.md", lambda t: t.replace("No agent carries `permissionMode`", "No agent\ncarries `permissionMode`"))
        r = self.run_test("test_structure.AgentFilesTest.test_readme_says_no_agent_carries_permission_mode")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
