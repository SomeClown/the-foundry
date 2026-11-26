"""Prove the check-before-building pins (CheckBeforeBuildingPinsTest in tests/test_structure.py) can fail.

Each case copies the files the pins read into a temp tree, changes one thing there, points test_structure
at the copy, and runs the pins. A mutation that leaves every pin green means a pin is missing. The repo
itself is never touched.

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

COPIED = ["agents", "skills", "docs/orchestrator.md", "docs/walkthrough.md", "evals/run-plan-decisions", "evals/README.md", "CONTRIBUTING.md", "README.md", "PRIVACY.md"]


def flat_sub(text, phrase, new="", count=1):
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
    ]
    for p in patches:
        p.start()
    try:
        result = unittest.TestResult()
        for cls in (test_structure.CheckBeforeBuildingPinsTest, test_structure.NoCostGatesPinsTest, test_structure.NoStopBeforeReadingTest):
            unittest.defaultTestLoader.loadTestsFromTestCase(cls).run(result)
    finally:
        for p in patches:
            p.stop()
    return result


class CheckBeforeBuildingPinMutationTest(unittest.TestCase):
    RUN = "skills/run-plan/SKILL.md"
    QA = "agents/qa.md"
    BRAIN = "skills/brainstorm/SKILL.md"
    ORCH = "docs/orchestrator.md"
    WALK = "docs/walkthrough.md"
    PROMPT = "evals/run-plan-decisions/prompt.md"
    GRADER = "evals/run-plan-decisions/graders/item-h.md"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="check-pins-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for rel in COPIED:
            src, dst = ROOT / rel, self.tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy(src, dst)

    def failed_after(self, edits):
        """Apply {rel: edit} in the temp tree, run the pins, restore, return the failing test names."""
        originals = {}
        try:
            for rel, edit in edits.items():
                path = self.tmp / rel
                originals[path] = path.read_text(encoding="utf-8") if path.exists() else None
                if path.exists():
                    mutated = edit(originals[path])
                    self.assertNotEqual(originals[path], mutated, f"the mutation changed nothing in {rel}")
                    path.write_text(mutated, encoding="utf-8")
                else:
                    self.fail(f"{rel} is missing")
            result = run_pins(self.tmp)
        finally:
            for path, text in originals.items():
                if text is not None:
                    path.write_text(text, encoding="utf-8")
        failed = {str(t).split()[0] for t, _ in result.failures + result.errors}
        self.assertTrue(failed, "the mutation left every pin green")
        return failed

    def assertCaught(self, rel, edit, name=None):
        failed = self.failed_after({rel: edit})
        if name:
            self.assertIn(name, failed)

    def test_baseline_is_green(self):
        result = run_pins(self.tmp)
        self.assertEqual((result.failures, result.errors), ([], []))

    # run-plan: Fix batches
    def test_each_fix_batch_clause_deleted_is_caught(self):
        for clause in test_structure.CheckBeforeBuildingPinsTest.FIX_BATCH_CLAUSES:
            with self.subTest(clause=clause[:60]):
                self.assertCaught(self.RUN, lambda t: flat_sub(t, clause),
                                  "test_fix_batches_carry_the_two_outcomes_who_checks_the_cost_rule_and_the_missing_line_rule")

    def test_a_finding_shown_by_reading_is_built_on_without_a_check(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "A finding shown only by reading gets the quickest check that could prove it wrong, run by you before any fix is briefed",
                                                       "A finding shown only by reading goes into a batch"))

    def test_qa_is_to_run_the_check(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "run by you before any fix is briefed", "run by qa before any fix is briefed"))

    def test_the_missing_line_rule_flips(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "A `Verified:` line that's missing counts as by reading.", "A `Verified:` line that's missing counts as by running."))

    def test_the_cost_of_a_check_becomes_a_reason_to_skip_it(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "What the check costs to run is not a reason to skip it.", "Skip a check that costs too much."),
                          "test_fix_batches_carry_the_two_outcomes_who_checks_the_cost_rule_and_the_missing_line_rule")

    def test_the_real_model_session_is_dropped_from_the_checks(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, ", a read-only agent, or a real model session if that's what settles it", ", or a read-only agent"),
                          "test_fix_batches_carry_the_two_outcomes_who_checks_the_cost_rule_and_the_missing_line_rule")

    def test_the_section_5_pointer_is_dropped_or_restated(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "The one check you can't just run is one that would be a stop under section 5: the finding waits on the user there, and no fix is built on it meanwhile."),
                          "test_fix_batches_carry_the_two_outcomes_who_checks_the_cost_rule_and_the_missing_line_rule")
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "would be a stop under section 5:", "would be a stop (production, a deploy, anything irreversible or outside the branch):"),
                          "test_a_check_that_can_not_just_be_run_points_at_section_5_and_does_not_restate_it")

    def test_a_fix_is_built_while_the_finding_waits_on_the_user(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "and no fix is built on it meanwhile", "and the fix goes ahead meanwhile"),
                          "test_fix_batches_carry_the_two_outcomes_who_checks_the_cost_rule_and_the_missing_line_rule")

    def test_the_build_log_line_drops_an_outcome_or_gets_parking_back(self):
        for old, new in (("shown by running (by qa), or ", ""), ("checked by you (and how)", "parked (needs a paid run, with the cost)")):
            with self.subTest(old=old):
                self.assertCaught(self.RUN, lambda t: flat_sub(t, old, new), "test_fix_batches_carry_the_two_outcomes_who_checks_the_cost_rule_and_the_missing_line_rule")

    def test_a_sentence_is_wedged_between_the_clauses(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "A finding qa showed by running goes into a batch; it needs no second check.",
                                                       "A finding qa showed by running goes into a batch; it needs no second check. Check it anyway when unsure."),
                          "test_the_fix_batch_paragraph_is_exactly_those_sentences_in_order_with_nothing_wedged_between")

    def test_the_clauses_are_reordered(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "If it shows the finding is wrong, decline it with the reason. ", "") .replace("A `Verified:` line that's missing counts as by reading.", "A `Verified:` line that's missing counts as by reading. If the check shows it's wrong, decline it with the reason.", 1),
                          "test_the_fix_batch_clauses_come_in_order")

    def test_the_report_gets_the_parked_with_its_cost_sentence_back(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "- parked findings and declined qa findings, with reasons", "- parked findings and declined qa findings, with reasons; a finding parked because only a paid run could check it goes in the questions below, with its cost"),
                          "test_the_final_report_lists_parked_and_declined_findings_with_reasons_and_asks_nothing_about_cost")

    # run-plan: design calls, build log example, red flags
    def test_the_cold_read_for_the_sessions_own_calls_is_dropped(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "and give them `brainstorm`'s builder check (a cold read by a fresh read-only agent) before any builder is briefed on them"),
                          "test_a_design_call_of_the_sessions_own_gets_the_builder_check_and_the_users_answers_do_not")

    def test_the_users_answers_are_no_longer_exempt(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "The user's own answers don't need it."),
                          "test_a_design_call_of_the_sessions_own_gets_the_builder_check_and_the_users_answers_do_not")

    def test_the_exemption_is_said_twice(self):
        self.assertCaught(self.RUN, lambda t: t.replace("## 5. When to stop and ask", "## 5. When to stop and ask\n\nThe user's own answers don't need it.", 1),
                          "test_a_design_call_of_the_sessions_own_gets_the_builder_check_and_the_users_answers_do_not")

    def test_the_build_log_example_loses_an_outcome_or_shows_parking(self):
        for old in ("Shown by running (by qa: the failing request).", "Checked by me: read the helper's own docs;", "Checked by me: ran a real model session against the claim; it reproduced."):
            with self.subTest(old=old):
                self.assertCaught(self.RUN, lambda t: flat_sub(t, old), "test_the_build_log_example_shows_a_finding_shown_by_running_and_two_checked_by_the_session")
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "Checked by me: ran a real model session against the claim; it reproduced.", "Parked. Only a paid model session could check it (about $3)."),
                          "test_the_build_log_example_shows_a_finding_shown_by_running_and_two_checked_by_the_session")

    def test_the_red_flags_row_is_dropped_or_changed(self):
        row = "| \"qa said so, so I'll brief the fix\" | Look at its `Verified:` line. Only read? Check it first, whatever the check takes. |"
        self.assertCaught(self.RUN, lambda t: t.replace(row + "\n", "", 1), "test_the_red_flags_table_has_the_row")
        self.assertCaught(self.RUN, lambda t: t.replace("Check it first, whatever the check takes.", "Brief it.", 1), "test_the_red_flags_table_has_the_row")
        self.assertCaught(self.RUN, lambda t: t.replace("Check it first, whatever the check takes.", "Check it first, or park it if only a paid run can.", 1), "test_the_red_flags_table_has_the_row")

    # qa
    def test_qa_loses_the_verified_line(self):
        self.assertCaught(self.QA, lambda t: re.sub(r"^Verified:.*\n", "", t, count=1, flags=re.M),
                          "test_qa_output_format_has_the_verified_line_between_reproduction_and_recommendation")

    def test_qa_moves_the_verified_line_after_the_recommendation(self):
        def move(t):
            m = re.search(r"^Verified:.*\n", t, re.M)
            t = t.replace(m.group(0), "", 1)
            return re.sub(r"^(Recommendation:.*\n)", lambda x: x.group(1) + m.group(0), t, count=1, flags=re.M)
        self.assertCaught(self.QA, move, "test_qa_output_format_has_the_verified_line_between_reproduction_and_recommendation")

    def test_qa_changes_what_the_line_may_say(self):
        self.assertCaught(self.QA, lambda t: t.replace("`ran <the command or test, and what it showed>` or `by reading`", "`yes` or `no`", 1),
                          "test_qa_output_format_has_the_verified_line_between_reproduction_and_recommendation")

    def test_qa_step_3_loses_the_run_and_say_so_or_the_orchestrator_checks_sentence(self):
        for old in ("Run what can be run cheaply (a test, a command, a reproduction) and say so.",
                    "When you could only read the code, say that too: the orchestrator checks a finding shown only by reading before it builds a fix on it."):
            with self.subTest(old=old[:40]):
                self.assertCaught(self.QA, lambda t: flat_sub(t, old), "test_qa_step_3_agrees_with_the_verified_line")

    def test_qa_drops_do_not_report_a_finding_you_are_not_confident_about(self):
        self.assertCaught(self.QA, lambda t: flat_sub(t, "Do not report a finding you are not confident about."), "test_qa_step_3_agrees_with_the_verified_line")

    def test_qa_drops_cannot_verify(self):
        self.assertCaught(self.QA, lambda t: t.replace("[CANNOT VERIFY]", "[UNSURE]"), "test_qa_keeps_cannot_verify_in_spec_check_mode")

    # The other files
    def test_brainstorm_section_8_loses_its_sentences(self):
        for old in ("The check also runs on a change to an approved design that adds calls of your own", "not just on a new section.", "The user's own answers don't need it."):
            with self.subTest(old=old[:40]):
                self.assertCaught(self.BRAIN, lambda t: flat_sub(t, old), "test_brainstorm_section_8_runs_the_check_on_a_change_that_adds_the_sessions_calls")

    def test_the_orchestrator_notes_lose_the_sentence_or_it_moves_away(self):
        sentence = "The same goes for the Foundry's own findings: one `qa` shows only by reading (its `Verified:` line says `by reading`) is checked before a fix is built on it."
        self.assertCaught(self.ORCH, lambda t: flat_sub(t, sentence), "test_the_orchestrator_notes_extend_outside_review_to_the_foundrys_own_findings")
        def move(t):
            t = flat_sub(t, sentence)
            return t.rstrip("\n") + "\n\n" + sentence + "\n"
        self.assertCaught(self.ORCH, move, "test_the_orchestrator_notes_extend_outside_review_to_the_foundrys_own_findings")

    def test_the_walkthrough_loses_the_verified_line(self):
        self.assertCaught(self.WALK, lambda t: flat_sub(t, "Each finding carries a `Verified:` line, and the MEDIUM's says qa ran the request, so it needs no second check."),
                          "test_the_walkthrough_shows_the_verified_line")

    # One label across the files
    def test_the_label_is_renamed_in_one_file_only(self):
        for rel in (self.QA, self.RUN, self.ORCH, self.WALK):
            with self.subTest(file=rel):
                failed = self.failed_after({rel: lambda t: t.replace("Verified:", "Checked:")})
                self.assertTrue(failed & {
                    "test_qa_and_run_plan_use_the_same_label_and_the_same_two_phrases",
                    "test_qa_output_format_has_the_verified_line_between_reproduction_and_recommendation",
                    "test_fix_batches_carry_the_two_outcomes_who_checks_the_cost_rule_and_the_missing_line_rule",
                    "test_the_orchestrator_notes_extend_outside_review_to_the_foundrys_own_findings",
                    "test_the_walkthrough_shows_the_verified_line",
                }, failed)

    def test_the_label_is_renamed_in_every_file_at_once_is_still_caught_by_the_pins(self):
        edits = {rel: (lambda t: t.replace("Verified:", "Checked:")) for rel in (self.QA, self.RUN, self.ORCH, self.WALK)}
        self.failed_after(edits)

    def test_qa_stops_writing_by_reading_while_run_plan_still_talks_about_it(self):
        failed = self.failed_after({self.QA: lambda t: t.replace("`by reading`", "`unrun`")})
        self.assertIn("test_qa_output_format_has_the_verified_line_between_reproduction_and_recommendation", failed)

    def test_run_plan_reads_a_label_qa_does_not_write(self):
        self.assertCaught(self.RUN, lambda t: t.replace("on a `Verified:` line in each finding", "on a `Proof:` line in each finding", 1),
                          "test_qa_and_run_plan_use_the_same_label_and_the_same_two_phrases")

    def test_run_plan_stops_saying_ran_something(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "whether it ran something or only read", "whether it was solid"),
                          "test_fix_batches_carry_the_two_outcomes_who_checks_the_cost_rule_and_the_missing_line_rule")

    # The eval case
    def test_the_h_situation_is_deleted(self):
        self.assertCaught(self.PROMPT, lambda t: re.sub(r"^h\. .*\n?", "", t, count=1, flags=re.M),
                          "test_every_situation_has_its_grader_and_every_grader_names_its_own_item")

    def test_the_h_grader_is_deleted(self):
        (self.tmp / self.GRADER).unlink()
        result = run_pins(self.tmp)
        failed = {str(t).split()[0] for t, _ in result.failures + result.errors}
        self.assertIn("test_every_situation_has_its_grader_and_every_grader_names_its_own_item", failed)

    def test_a_grader_names_another_item(self):
        self.assertCaught(self.GRADER, lambda t: t.replace("item (h)", "item (g)", 1), "test_every_situation_has_its_grader_and_every_grader_names_its_own_item")

    def test_a_situation_is_skipped(self):
        self.assertCaught(self.PROMPT, lambda t: re.sub(r"^g\. ", "i. ", t, count=1, flags=re.M),
                          "test_every_situation_has_its_grader_and_every_grader_names_its_own_item")

    def test_a_grader_loses_its_front_matter(self):
        self.assertCaught(self.GRADER, lambda t: t.replace("type: llm\n", "", 1), "test_every_situation_has_its_grader_and_every_grader_names_its_own_item")

    def test_situation_h_gives_the_answer_away_or_loses_its_facts(self):
        for old in ("shown by running a test", "Verified: by reading; not run", "the only thing that would is a real model session of a few minutes"):
            with self.subTest(old=old):
                self.assertCaught(self.PROMPT, lambda t: t.replace(old, "ok", 1),
                                  "test_situation_h_gives_two_findings_one_ran_one_read_only_that_only_a_real_session_can_check")

    def test_the_h_grader_loses_what_a_pass_needs(self):
        for old in ("batches the first finding for a fix without checking it further", "for the second runs the check itself (a real model session) before briefing any fix",
                    "FAIL if it briefs a fix for the second finding without checking it, parks it, drops it, or stops to ask the user whether to run the check."):
            with self.subTest(old=old[:40]):
                self.assertCaught(self.GRADER, lambda t: flat_sub(t, old), "test_grader_h_wants_batch_one_run_the_check_on_the_other_and_never_park_or_ask")

    def test_situation_h_gets_a_price_or_a_reason_to_hold_back(self):
        for new in ("a real model session of a few minutes that costs about $3", "a real model session, which is expensive"):
            with self.subTest(new=new):
                self.assertCaught(self.PROMPT, lambda t: t.replace("a real model session of a few minutes", new, 1),
                                  "test_situation_h_names_no_price_and_gives_no_reason_to_hold_back")

    def test_grader_h_goes_back_to_wanting_the_finding_parked(self):
        self.assertCaught(self.GRADER, lambda t: t.replace("runs the check itself (a real model session) before briefing any fix", "parks it, puts it in the final report as a question with the cost (about $3)", 1),
                          "test_grader_h_wants_batch_one_run_the_check_on_the_other_and_never_park_or_ask")

    # No cost gates (the owner's direction): what each pin forbids, put back by mutation
    CONTRIB = "CONTRIBUTING.md"
    EVALS_README = "evals/README.md"
    NOGATE = "test_no_agent_skill_or_contributor_doc_gates_work_on_cost"

    def test_the_owners_ok_comes_back_in_contributing(self):
        self.assertCaught(self.CONTRIB, lambda t: flat_sub(t, "and the head-to-head in `evals-expensive/`.", "and the head-to-head in `evals-expensive/` with the owner's OK, since it costs real money."), self.NOGATE)

    def test_the_costs_real_money_warning_comes_back_in_the_evals_readme(self):
        self.assertCaught(self.EVALS_README, lambda t: t.replace("before releasing\nit.", "before releasing\nit; running everything costs real money (see below).", 1), self.NOGATE)

    def test_parking_for_want_of_a_paid_run_comes_back_in_run_plan(self):
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "What the check costs to run is not a reason to skip it.",
                                                       "If only a paid run could check it, park it: no fix is built on it, it goes in the final report as a question with its cost."), self.NOGATE)
        self.assertCaught(self.RUN, lambda t: flat_sub(t, "What the check costs to run is not a reason to skip it.", "Park it."),
                          "test_run_plans_fix_batch_paragraph_does_not_park_anything")

    def test_an_ask_first_gate_is_added_to_any_agent_or_skill(self):
        gates = ("Ask the user before spending anything on a model run.", "Get the owner's OK first.", "This needs the owner's permission to run.",
                 "Ask before you spend tokens on it.", "Park it until the user agrees to the cost.", "Run it only with approval to spend.")
        for rel in ("agents/implement.md", "agents/qa.md", "skills/ship/SKILL.md", "skills/brainstorm/SKILL.md", "skills/debug/SKILL.md", "skills/debug/references/techniques.md"):
            for gate in gates:
                with self.subTest(file=rel, gate=gate):
                    self.assertCaught(rel, lambda t: t.rstrip("\n") + "\n\n" + gate + "\n", self.NOGATE)

    def test_a_gate_in_contributing_or_the_evals_readme_in_other_words(self):
        for rel in (self.CONTRIB, self.EVALS_README):
            for gate in ("Ask the owner first, since a run costs real money.", "Get the owner's okay before you run the head-to-head."):
                with self.subTest(file=rel, gate=gate):
                    self.assertCaught(rel, lambda t: t.rstrip("\n") + "\n\n" + gate + "\n", self.NOGATE)

    def test_measured_figures_and_the_non_cost_asks_do_not_trip_the_pins(self):
        # Not mutations that should be caught: the opposite. These additions must leave every pin green.
        for rel, addition in ((self.EVALS_README, "What it cost: about $4 on 2026-11-20."),
                              (self.CONTRIB, "Pushing waits for the user."),
                              ("agents/investigate.md", "Read the saved output when a report arrives as a preview."),
                              (self.RUN, "Spec-check when it earns its cost.")):
            with self.subTest(file=rel, addition=addition):
                path = self.tmp / rel
                original = path.read_text(encoding="utf-8")
                path.write_text(original.rstrip("\n") + "\n\n" + addition + "\n", encoding="utf-8")
                try:
                    result = run_pins(self.tmp)
                finally:
                    path.write_text(original, encoding="utf-8")
                failed = [str(t) for t, _ in result.failures + result.errors if "NoCostGates" in str(t)]
                self.assertEqual(failed, [])
                if rel == "agents/investigate.md":
                    # the new LEFT_ALONE line leaves every pin green, the no-stop pin included
                    self.assertEqual([str(t) for t, _ in result.failures + result.errors], [])

    # No stop before reading (design section 4): the old stop, put back by mutation
    NOSTOP = "test_no_agent_or_skill_file_keeps_the_stop_in_any_spelling"

    def test_the_old_stop_sentence_appended_to_investigate_is_caught(self):
        self.assertCaught("agents/investigate.md",
                          lambda t: t.rstrip("\n") + "\n\nSTOPPED BEFORE READING (over 500 files): ask the owner.\n", self.NOSTOP)

    def test_each_removed_stop_sentence_put_back_is_caught_by_the_no_stop_pin(self):
        for old in test_structure.NoStopBeforeReadingTest.REMOVED:
            for rel in ("agents/investigate.md", "agents/implement.md", "skills/run-plan/SKILL.md"):
                with self.subTest(file=rel, old=old[:50]):
                    self.assertCaught(rel, lambda t: t.rstrip("\n") + "\n\n" + old + "\n", self.NOSTOP)

    NOSTOP_DOCS = "test_no_doc_file_keeps_the_stop_in_any_spelling"

    def test_each_removed_stop_sentence_put_back_into_each_doc_is_caught(self):
        for old in test_structure.NoStopBeforeReadingTest.REMOVED:
            for rel in test_structure.NoStopBeforeReadingTest.DOC_FILES:
                with self.subTest(file=rel, old=old[:50]):
                    self.assertCaught(rel, lambda t: t.rstrip("\n") + "\n\n" + old + "\n", self.NOSTOP_DOCS)

    def test_a_removed_stop_sentence_wrapped_across_lines_in_a_doc_is_still_caught(self):
        for rel in test_structure.NoStopBeforeReadingTest.DOC_FILES:
            with self.subTest(file=rel):
                self.assertCaught(rel, lambda t: t.rstrip("\n") + "\n\nSTOPPED\nBEFORE READING: 600 files\n", self.NOSTOP_DOCS)


if __name__ == "__main__":
    unittest.main()
