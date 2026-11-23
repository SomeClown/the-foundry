"""Prove the self-consistency pins in tests/test_structure.py can fail.

These pins hold sentences that agree with each other across agents, skills and docs (a fallback
stated in all its places, a rule in the README that matches the agent file, a flag every command
carries).

Each case copies the files the pins read into a temp tree, undoes one fix there (restoring the
pre-branch wording, or removing the sentence), points test_structure at the copy, and runs the pins.
A mutation that leaves every pin green means a pin is missing. The repo itself is never touched.

Standard library only.
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_structure  # noqa: E402

COPIED = ["agents", "skills", "README.md", "CONTRIBUTING.md", "evals/README.md", "docs/walkthrough.md"]
CLASSES = (test_structure.SelfConsistencyPinsTest, test_structure.AgentFilesTest)


def flat_sub(text, phrase, new="", count=1):
    """Replace a phrase however the file wraps it."""
    pattern = r"\s+".join(re.escape(word) for word in phrase.split())
    result, n = re.subn(pattern, lambda _m: new, text, count=count)
    if n == 0:
        raise AssertionError(f"phrase not found: {phrase!r}")
    return result


def run_pins(root):
    patches = [
        mock.patch.object(test_structure, "ROOT", root),
        mock.patch.object(test_structure, "AGENTS", root / "agents"),
        mock.patch.object(test_structure, "SKILLS", root / "skills"),
        mock.patch.object(test_structure, "README", root / "README.md"),
    ]
    for p in patches:
        p.start()
    try:
        result = unittest.TestResult()
        for cls in CLASSES:
            unittest.defaultTestLoader.loadTestsFromTestCase(cls).run(result)
    finally:
        for p in patches:
            p.stop()
    return result


class SelfConsistencyPinMutationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="consistency-pins-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for rel in COPIED:
            src, dst = ROOT / rel, self.tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy(src, dst)

    def caught(self, rel, edit):
        path = self.tmp / rel
        original = path.read_text(encoding="utf-8")
        mutated = edit(original)
        self.assertNotEqual(original, mutated, "the mutation changed nothing")
        path.write_text(mutated, encoding="utf-8")
        try:
            result = run_pins(self.tmp)
        finally:
            path.write_text(original, encoding="utf-8")
        failed = {str(t).split()[0] for t, _ in result.failures + result.errors}
        self.assertTrue(failed, "the mutation left every pin green")
        return failed

    def assertCaughtBy(self, rel, edit, test_name):
        failed = self.caught(rel, edit)
        self.assertIn(test_name, failed)

    def test_baseline_is_green(self):
        result = run_pins(self.tmp)
        self.assertEqual((result.failures, result.errors), ([], []))

    # uiux
    def test_uiux_load_section_fallback_removed(self):
        self.assertCaughtBy("agents/uiux.md", lambda t: flat_sub(
            t, "If it isn't, say so in your report and work from your own design knowledge:", "Load them before designing:"),
            "test_uiux_falls_back_to_its_own_design_knowledge_in_all_three_places")

    def test_uiux_direction_brief_back_to_load_first(self):
        self.assertCaughtBy("agents/uiux.md", lambda t: flat_sub(
            t, "first when it's installed (see Load Your Skills First), then", "first, then"),
            "test_uiux_falls_back_to_its_own_design_knowledge_in_all_three_places")

    def test_uiux_dataviz_back_to_load_first(self):
        self.assertCaughtBy("agents/uiux.md", lambda t: flat_sub(
            t, "first when it's installed and follow its method", "first and follow its method"),
            "test_uiux_falls_back_to_its_own_design_knowledge_in_all_three_places")

    def test_uiux_dataviz_fallback_sentence_removed(self):
        self.assertCaughtBy("agents/uiux.md", lambda t: flat_sub(
            t, "Without it, work those out from your own design knowledge."),
            "test_uiux_falls_back_to_its_own_design_knowledge_in_all_three_places")

    def test_uiux_gets_a_not_optional(self):
        self.assertCaughtBy("agents/uiux.md", lambda t: t.replace(
            "Load the right skill before designing", "Loading the skill is not optional: load the right skill before designing", 1),
            "test_uiux_has_no_not_optional")

    # devops
    def test_devops_no_longer_stops_before_an_irreversible_command(self):
        self.assertCaughtBy("agents/devops.md", lambda t: flat_sub(
            t, "or any command you can't undo."), "test_devops_stops_before_a_command_it_cant_undo_and_goes_on_only_on_a_yes")

    def test_devops_goes_on_without_a_yes(self):
        self.assertCaughtBy("agents/devops.md", lambda t: flat_sub(
            t, "go on only when you're resumed with the user's yes, relayed through the master agent", "go on"),
            "test_devops_stops_before_a_command_it_cant_undo_and_goes_on_only_on_a_yes")

    def test_devops_report_slot_removed(self):
        self.assertCaughtBy("agents/devops.md", lambda t: flat_sub(
            t, "- If you stopped before a command you can't undo: the exact command, what it will do, and that you're waiting for the user's yes"),
            "test_devops_report_list_has_the_stopped_waiting_for_a_yes_slot")

    # test-engineer
    def test_test_engineer_description_back_to_tests_only(self):
        self.assertCaughtBy("agents/test-engineer.md", lambda t: flat_sub(
            t, "Writes only test files, test configuration, and a report file the brief names, never application code.",
            "Writes only test files and test configuration, never application code."),
            "test_test_engineer_may_write_the_report_file_its_brief_names")

    def test_test_engineer_body_back_to_tests_only(self):
        self.assertCaughtBy("agents/test-engineer.md", lambda t: flat_sub(
            t, "You modify only test files, test configuration, and any report file your brief names.",
            "You modify only test files and test configuration."),
            "test_test_engineer_may_write_the_report_file_its_brief_names")

    def test_test_engineer_told_to_stash_again(self):
        self.assertCaughtBy("agents/test-engineer.md", lambda t: flat_sub(
            t, "if the fix is already in the tree, don't stash or revert it to watch the test fail: say it wasn't seen failing", "stash the fix to watch the test fail"),
            "test_test_engineer_does_not_stash_or_revert_a_fix_already_in_the_tree")

    def test_test_engineer_report_slot_removed(self):
        self.assertCaughtBy("agents/test-engineer.md", lambda t: flat_sub(
            t, "- A regression test whose fix was already in the tree: say it wasn't seen failing"),
            "test_test_engineer_report_list_has_the_not_seen_failing_slot")

    # README
    def test_readme_bug_fix_order_reversed(self):
        self.assertCaughtBy("README.md", lambda t: flat_sub(
            t, "`debug` finds the cause and pins it with a failing test, then `implement` fixes it.",
            "`debug` finds the cause, then `implement` fixes it and writes the test."),
            "test_readme_bug_fix_order_is_pin_then_fix")

    def test_readme_test_engineer_cell_back_to_tests_only(self):
        self.assertCaughtBy("README.md", lambda t: t.replace(
            "Yes (tests, and a report file the brief names)", "Yes (tests only)", 1),
            "test_readme_test_engineer_cell_and_rule_agree_with_the_agent_file")

    def test_readme_test_engineer_rule_back_to_tests_only(self):
        self.assertCaughtBy("README.md", lambda t: flat_sub(
            t, "test-engineer touches only tests (and a report file its brief names);", "test-engineer touches only tests;"),
            "test_readme_test_engineer_cell_and_rule_agree_with_the_agent_file")

    def test_readme_investigate_bullet_back_in_the_self_enforced_list(self):
        def move(t):
            t = flat_sub(t, "One rule is the orchestrator's, since only it can see both sides: `investigate` runs alone, scoped or full, and nothing else that starts agents runs alongside it.", "")
            return t.replace("- Read-only agents (investigate, file-reader, architect, uiux, qa) never write files.\n",
                             "- Read-only agents (investigate, file-reader, architect, uiux, qa) never write files.\n"
                             "- `investigate` runs alone, scoped or full: nothing else that starts agents\n  runs alongside it (the orchestrator's rule, since only it can see both).\n", 1)
        self.assertCaughtBy("README.md", move, "test_readme_describes_the_investigate_rule_as_the_orchestrators")

    # run-plan
    def test_run_plan_gets_its_base_variable_back(self):
        self.assertCaughtBy("skills/run-plan/SKILL.md", lambda t: t.replace(
            "Before packaging, check that", "BASE=$(git rev-parse --short HEAD)\n\nBefore packaging, check that", 1),
            "test_run_plan_keeps_no_base_shell_variable")

    def test_run_plan_rules_file_step_loses_the_gate(self):
        self.assertCaughtBy("skills/run-plan/SKILL.md", lambda t: flat_sub(
            t, "then the gate from step 4 with any failures it's expected to show, marked as not this task's to fix"),
            "test_run_plan_setup_copies_the_gate_and_its_expected_failures_into_the_rules_file")

    def test_run_plan_step_5_loses_the_testing_strategy(self):
        self.assertCaughtBy("skills/run-plan/SKILL.md", lambda t: flat_sub(
            t, "and the plan's Testing Strategy section by heading (the brief holds only the task's own section)", "and the plan"),
            "test_run_plan_step_5_hands_test_engineer_the_testing_strategy_by_heading")

    def test_run_plan_builder_contract_loses_the_skill_rule(self):
        self.assertCaughtBy("skills/run-plan/SKILL.md", lambda t: flat_sub(
            t, "commit, don't dispatch other agents, and don't load the Foundry's own skills (a project's own design skill is fine).",
            "commit, and don't dispatch other agents."),
            "test_run_plan_builder_contract_says_not_to_load_the_foundrys_skills")

    def test_run_plan_qa_pass_loses_the_guard(self):
        self.assertCaughtBy("skills/run-plan/SKILL.md", lambda t: t.replace(
            ' && [ -n "$MB" ] || { echo "no merge-base with <default branch>" >&2; exit 2; }', "", 1),
            "test_run_plan_qa_pass_guards_an_empty_merge_base_in_one_bash_call")

    def test_run_plan_qa_pass_loses_the_same_call_sentence(self):
        self.assertCaughtBy("skills/run-plan/SKILL.md", lambda t: flat_sub(
            t, "Run both lines in the same Bash call: `MB` doesn't carry to the next one, and an empty `MB` would package the wrong diff without an error."),
            "test_run_plan_qa_pass_guards_an_empty_merge_base_in_one_bash_call")

    def test_run_plan_step_4_loses_the_sha_check(self):
        self.assertCaughtBy("skills/run-plan/SKILL.md", lambda t: flat_sub(
            t, "Before packaging, check that `git rev-parse --short HEAD` is the sha noted at step 1."),
            "test_run_plan_step_4_checks_head_against_the_noted_sha_and_packages_against_a_literal")

    def test_run_plan_step_4_literal_command_goes_back_to_head(self):
        self.assertCaughtBy("skills/run-plan/SKILL.md", lambda t: t.replace(
            "git diff --cached --stat abc1234; git diff --cached -U10 abc1234;", "git diff --cached --stat; git diff --cached -U10;", 1),
            "test_run_plan_step_4_checks_head_against_the_noted_sha_and_packages_against_a_literal")

    # frontend and uiux
    def test_frontend_loses_the_never_load_the_foundrys_skills_sentence(self):
        self.assertCaughtBy("agents/frontend.md", lambda t: flat_sub(
            t, "never the Foundry's own `brainstorm`, `debug`, `run-plan`, or `ship`, which belong to the orchestrating session."),
            "test_frontend_and_uiux_never_load_the_foundrys_own_skills")

    def test_uiux_loses_the_never_load_the_foundrys_skills_sentence(self):
        self.assertCaughtBy("agents/uiux.md", lambda t: flat_sub(
            t, "Never load the Foundry's own `brainstorm`, `debug`, `run-plan`, or `ship`: they belong to the orchestrating session."),
            "test_frontend_and_uiux_never_load_the_foundrys_own_skills")

    def test_a_skill_holding_agent_loses_its_limit_even_if_the_wording_changes(self):
        self.assertCaughtBy("agents/frontend.md", lambda t: flat_sub(
            t, "never the Foundry's own `brainstorm`, `debug`, `run-plan`, or `ship`, which belong to the orchestrating session.",
            "never the Foundry's own skills."),
            "test_an_agent_holding_the_skill_tool_says_which_skills_it_loads")

    # evals README and CONTRIBUTING
    def test_evals_readme_command_loses_ablation_none(self):
        self.assertCaughtBy("evals/README.md", lambda t: t.replace(" --ablation none", "", 1),
                            "test_every_eval_command_in_the_docs_carries_ablation_none")

    def test_evals_readme_every_command_loses_ablation_none(self):
        self.assertCaughtBy("evals/README.md", lambda t: t.replace(" --ablation none --scaffold", " --scaffold"),
                            "test_every_eval_command_in_the_docs_carries_ablation_none")

    def test_evals_readme_wrapped_command_loses_ablation_none(self):
        # The first command wraps across lines; the flag may sit on a continuation line.
        def edit(t):
            start = t.index("claude plugin eval . --tag ship")
            end = t.index("\n\n", start)
            return t[:start] + t[start:end].replace("--ablation none ", "") + t[end:]
        self.assertCaughtBy("evals/README.md", edit, "test_every_eval_command_in_the_docs_carries_ablation_none")

    def test_contributing_command_loses_ablation_none(self):
        self.assertCaughtBy("CONTRIBUTING.md", lambda t: t.replace(" --ablation none", "", 1),
                            "test_every_eval_command_in_the_docs_carries_ablation_none")

    # walkthrough
    def test_walkthrough_rules_file_line_loses_the_gate(self):
        self.assertCaughtBy("docs/walkthrough.md", lambda t: flat_sub(
            t, "copies the plan's rules and its gate into a `rules.md`", "copies the plan's rules into a `rules.md`"),
            "test_walkthrough_rules_file_line_mentions_the_gate")

    # D: the Skill-tool test
    def test_frontend_loses_the_skill_tool(self):
        self.assertCaughtBy("agents/frontend.md", lambda t: t.replace("  - Skill\n", "", 1),
                            "test_frontend_and_uiux_hold_the_skill_tool_by_name")

    def test_frontend_loses_the_skill_tool_and_load_it_becomes_use_it(self):
        # qa's hole: both together stayed green with the old test.
        def edit(t):
            t = t.replace("  - Skill\n", "", 1)
            return t.replace("load it before", "use it before", 1)
        failed = self.caught("agents/frontend.md", edit)
        self.assertIn("test_an_agent_that_mentions_loading_or_using_a_skill_holds_the_skill_tool", failed)
        self.assertIn("test_frontend_and_uiux_hold_the_skill_tool_by_name", failed)

    def test_frontend_loses_the_skill_tool_and_stops_mentioning_skills(self):
        # What the structural tests can't catch except by name: the by-name test still does.
        def edit(t):
            t = t.replace("  - Skill\n", "", 1)
            return re.sub(r"If the project ships a skill.*?before\s+editing", "Check the project's theme before editing", t, flags=re.S)
        self.assertCaughtBy("agents/frontend.md", edit, "test_frontend_and_uiux_hold_the_skill_tool_by_name")

    def test_uiux_loses_the_skill_tool(self):
        self.assertCaughtBy("agents/uiux.md", lambda t: t.replace("  - Skill\n", "", 1),
                            "test_frontend_and_uiux_hold_the_skill_tool_by_name")

    def test_an_agent_that_only_mentions_using_a_skill_must_hold_it(self):
        # An agent with no Skill tool whose body says to use a skill.
        self.assertCaughtBy("agents/docs.md", lambda t: t.rstrip("\n") + "\n\nUse the project's style skill when one exists.\n",
                            "test_an_agent_that_mentions_loading_or_using_a_skill_holds_the_skill_tool")


if __name__ == "__main__":
    unittest.main()
