"""Prove the retro pins (RetroTest in tests/test_structure.py) can fail.

Each case copies the files the pins read into a temp tree, undoes one thing there, points test_structure
at the copy, and runs RetroTest. A mutation that leaves every pin green means a pin is missing. The
repo itself is never touched; no retro file is read or written.

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

COPIED = ["agents", "skills", "README.md", "PRIVACY.md", "CONTRIBUTING.md", "evals/README.md", "docs"]


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
        unittest.defaultTestLoader.loadTestsFromTestCase(test_structure.RetroTest).run(result)
    finally:
        for p in patches:
            p.stop()
    return result


class RetroPinMutationTest(unittest.TestCase):
    RUN = "skills/run-plan/SKILL.md"
    DEBUG = "skills/debug/SKILL.md"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="retro-pins-"))
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

    def assertCaughtBy(self, rel, edit, test_name=None):
        failed = self.caught(rel, edit)
        if test_name:
            self.assertIn(test_name, failed)

    def test_baseline_is_green(self):
        result = run_pins(self.tmp)
        self.assertEqual((result.failures, result.errors), ([], []))

    # The path and the variable
    def test_either_skill_goes_back_to_the_old_path(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace("~/.foundry/retro.md", "~/.claude/foundry-retro.md", 1))

    def test_either_skill_loses_the_variable_from_the_resolve_command(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace('F="${FOUNDRY_RETRO_FILE:-$HOME/.foundry/retro.md}"; case', 'F="$HOME/.foundry/retro.md"; case', 1),
                                    "test_both_skills_carry_the_resolve_command_and_an_append_that_resolves_itself")

    def test_either_skill_loses_the_relative_path_case(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace('case "$F" in /*) ;; *) F="$PWD/$F" ;; esac; printf', 'printf', 1),
                                    "test_both_skills_carry_the_resolve_command_and_an_append_that_resolves_itself")

    def test_either_skill_drops_the_resolve_step_sentence(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "The Read and Write tools don't expand a shell expression, so resolve the path first, with one Bash call:", "Resolve the path:"),
                                    "test_both_skills_carry_the_shared_retro_text")

    # The append command
    def test_either_skill_makes_the_append_a_rewrite(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace('cat >> "$F" <<', 'cat > "$F" <<', 1),
                                    "test_both_skills_carry_the_resolve_command_and_an_append_that_resolves_itself")

    def test_either_skill_loses_the_retro_exit_line(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace('echo "retro exit=$?"\n', "", 1),
                                    "test_both_skills_carry_the_resolve_command_and_an_append_that_resolves_itself")

    def test_either_skill_loses_the_mkdir(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace('mkdir -p "$(dirname "$F")" && ', "", 1))

    def test_either_skill_drops_the_append_never_rewrite_rule(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "Append, never rewrite: two sessions can finish together, and a rewrite loses one's lines."),
                                    "test_both_skills_carry_the_shared_retro_text")

    # qa's holes: the can't-be-written sentence, read the file first
    def test_either_skill_drops_the_not_written_say_so_and_go_on_sentence(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "If the exit isn't 0, say in the report that the retro wasn't written, and go on."),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_both_skills_drop_the_not_written_sentence_together(self):
        sentence = "If the exit isn't 0, say in the report that the retro wasn't written, and go on."
        for rel in (self.RUN, self.DEBUG):
            path = self.tmp / rel
            path.write_text(flat_sub(path.read_text(encoding="utf-8"), sentence), encoding="utf-8")
        failed = {str(t).split()[0] for t, _ in (lambda r: r.failures + r.errors)(run_pins(self.tmp))}
        self.assertIn("test_both_skills_carry_the_shared_retro_text", failed)

    def test_either_skill_drops_read_the_file_first(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "Read the file at the path it prints (a missing file is fine: treat it as empty; a long one, read to the end)."),
                                    "test_both_skills_carry_the_shared_retro_text")

    # Kind words and the line's shape
    def test_a_kind_word_is_renamed_in_one_skill(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace("[didnt-hold]", "[did-not-hold]"),
                                    "test_both_skills_name_exactly_the_same_six_kind_words")

    def test_a_seventh_kind_word_appears_in_one_skill(self):
        def add(t):
            return t.replace("- run-plan [user]:", "- run-plan [slow]: ran long; should have stopped (Task 7)\n- run-plan [user]:", 1) \
                if "- run-plan [user]:" in t else t.replace("- debug [user]:", "- debug [slow]: ran long; should have stopped (step 3)\n- debug [user]:", 1)
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, add, "test_both_skills_name_exactly_the_same_six_kind_words")

    def test_a_kind_word_is_dropped_in_one_skill(self):
        def drop(t):
            return re.sub(r"^- \S+ \[misread\]:.*\n", "", t, count=1, flags=re.M)
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, drop, "test_both_skills_name_exactly_the_same_six_kind_words")

    def test_the_example_entry_uses_an_unknown_kind(self):
        def edit(t):
            head, sep, rest = t.partition("<<'FOUNDRY_RETRO_END'")
            return head + sep + re.sub(r"\[[\w-]+\]", "[oops]", rest, count=1)
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, edit, "test_the_example_entry_in_the_append_uses_a_real_kind_word")

    def test_the_line_shape_changes_in_one_skill(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace("what it did; what it should have done (where it came from)", "what it did and the evidence", 1),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_debug_goes_back_to_ending_a_line_with_the_evidence(self):
        self.assertCaughtBy(self.DEBUG, lambda t: flat_sub(t, "what it should have done, and where it came from", "what it should have done, and the evidence, with no code"),
                            "test_debug_lines_end_with_where_they_came_from_not_the_evidence")

    # What counts as a correction
    def test_run_plan_counts_every_fix_round_again(self):
        self.assertCaughtBy(self.RUN, lambda t: flat_sub(t, "a task that took two or more fix rounds, or came back BLOCKED", "a task that needed fix rounds"),
                            "test_each_skill_carries_its_own_retro_text_in_the_retro_section")

    def test_run_plan_counts_needs_context_again(self):
        self.assertCaughtBy(self.RUN, lambda t: flat_sub(t, "One fix round, or a builder's NEEDS_CONTEXT question, is the loop working: leave it out."),
                            "test_each_skill_carries_its_own_retro_text_in_the_retro_section")

    def test_debug_counts_a_one_go_fix_again(self):
        self.assertCaughtBy(self.DEBUG, lambda t: flat_sub(t, "A fix that took one go is the loop working: leave it out."),
                            "test_each_skill_carries_its_own_retro_text_in_the_retro_section")

    def test_a_correction_kind_is_dropped_from_the_list(self):
        for rel, phrase in ((self.RUN, "a test that misread the brief"), (self.RUN, "anything the user corrected"),
                            (self.DEBUG, "a dispatched agent's work redone"), (self.DEBUG, "anything the user corrected")):
            with self.subTest(skill=rel, phrase=phrase):
                # The phrase may also occur earlier in the skill, so cut it inside the retro text.
                marker = "### Retro" if rel == self.RUN else "### The retro"
                self.assertCaughtBy(rel, lambda t: t[:t.index(marker)] + flat_sub(t[t.index(marker):], phrase),
                                    "test_each_skill_carries_its_own_retro_text_in_the_retro_section")

    # Dedupe, repeat rule, never edit
    def test_either_skill_drops_the_line_level_dedupe(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "Drop them from your lines. None left: skip the append."),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_either_skill_drops_the_heading_lookup(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "Find any heading with the same project and run as the one you're about to write, whatever its date, and the lines under it"),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_repeat_rule_loses_the_kind_word(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "the same agent or skill with the same kind word as an earlier line", "the same agent or skill as an earlier line"),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_repeat_rule_stops_offering_brainstorm(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace("the user through `brainstorm`", "the user", 1),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_repeat_rule_stops_quoting_both(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "the report quotes both lines and offers", "the report offers"),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_either_skill_drops_never_edit_an_agent_or_skill(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "Never edit an agent or skill file yourself, here or in the plugin's install folder: a fix goes through the user and the repo's own review."),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_either_skill_drops_the_secrets_rule(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "and no code, file contents, or secrets", ""),
                                    "test_both_skills_carry_the_shared_retro_text")

    # Early stops
    def test_run_plan_section_5_stops_pointing_at_the_retro(self):
        self.assertCaughtBy(self.RUN, lambda t: flat_sub(t, "write the retro first (see \"Retro\" in section 4: the build log's section, then the append), put any repeat in the message,", "put any repeat in the message,"),
                            "test_each_skill_points_at_the_retro_from_where_it_stops_resumes_and_closes")

    def test_run_plan_section_5_stops_naming_the_one_write_outside_the_branch(self):
        self.assertCaughtBy(self.RUN, lambda t: flat_sub(t, "The one write outside the branch that doesn't stop the run is the retro's append to `~/.foundry/retro.md` (or `FOUNDRY_RETRO_FILE`)."),
                            "test_each_skill_points_at_the_retro_from_where_it_stops_resumes_and_closes")

    def test_debug_loses_the_pointer_at_cant_reproduce(self):
        def edit(t):
            return t.replace(' Write the retro before you stop (see "The retro" in section 7).\n\n## 3.', "\n\n## 3.", 1)
        self.assertCaughtBy(self.DEBUG, lambda t: flat_sub(t, "Write the retro before you stop (see \"The retro\" in section 7).", "", count=1),
                            "test_debug_stops_write_the_retro_first_at_both_stops")

    def test_debug_loses_the_pointer_at_three_failed_fixes(self):
        def edit(t):
            at = t.rindex('Write the retro before you stop')
            end = t.index("\n\n", at)
            return t[:at] + "Then stop." + t[end:]
        self.assertCaughtBy(self.DEBUG, edit, "test_debug_stops_write_the_retro_first_at_both_stops")

    def test_a_stop_repeats_the_retro_command_so_it_could_be_written_twice(self):
        def edit(t):
            return t.replace("## 7. Close it out", "```\nmkdir -p x && cat >> y <<'FOUNDRY_RETRO_END'\nz\nFOUNDRY_RETRO_END\n```\n\n## 7. Close it out", 1)
        self.assertCaughtBy(self.DEBUG, edit, "test_the_two_stops_point_at_the_retro_text_and_do_not_repeat_it_so_it_is_written_once")

    def test_none_goes_to_the_cross_project_file(self):
        self.assertCaughtBy(self.RUN, lambda t: t.replace("\n- implement [fix-rounds]: edited the victim test, not the polluter, and needed three rounds; should have fixed the polluter (Task 3, fix rounds 1 to 3)\nFOUNDRY_RETRO_END", "\n- none\nFOUNDRY_RETRO_END", 1),
                            "test_a_clean_run_never_sends_none_to_the_cross_project_file")

    def test_run_plan_clean_run_instruction_changes(self):
        self.assertCaughtBy(self.RUN, lambda t: flat_sub(t, "Nothing goes to the cross-project file.", ""),
                            "test_each_skill_carries_its_own_retro_text_in_the_retro_section")

    def test_debug_writes_none_for_a_clean_hunt(self):
        self.assertCaughtBy(self.DEBUG, lambda t: flat_sub(t, "Nothing needed correcting: write nothing.", "Nothing needed correcting: write `- none`."),
                            "test_each_skill_carries_its_own_retro_text_in_the_retro_section")

    def test_run_plan_resuming_loses_the_retro_paragraph(self):
        self.assertCaughtBy(self.RUN, lambda t: flat_sub(t, "**The retro picks up where it stopped.**", "**The retro.**"),
                            "test_each_skill_points_at_the_retro_from_where_it_stops_resumes_and_closes")

    def test_debug_close_out_loses_its_retro_bullet(self):
        self.assertCaughtBy(self.DEBUG, lambda t: flat_sub(t, "A hunt that needed none writes nothing."),
                            "test_each_skill_points_at_the_retro_from_where_it_stops_resumes_and_closes")

    # The marker, the date, the project name, the slug, the tie-break, copy as written
    def test_the_marker_goes_back_to_RETRO(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace("FOUNDRY_RETRO_END", "RETRO"),
                                    "test_both_skills_carry_the_resolve_command_and_an_append_that_resolves_itself")

    def test_the_marker_loses_its_quotes_so_the_heredoc_expands(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace("<<'FOUNDRY_RETRO_END'", "<<FOUNDRY_RETRO_END", 1),
                                    "test_both_skills_carry_the_resolve_command_and_an_append_that_resolves_itself")

    def test_the_no_line_may_be_the_marker_sentence_is_dropped(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "No line of the entry may be that marker, or the shell would run the lines after it:", ""),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_marker_in_the_sentence_changes_but_not_in_the_command(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace("between the `FOUNDRY_RETRO_END` markers", "between the `RETRO` markers", 1),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_date_source_is_dropped(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "The date is today's, from `date +%F`, as `YYYY-MM-DD`."),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_date_command_changes(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace("`date +%F`", "`date`", 1),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_already_written_check_goes_back_to_the_same_date(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "as the one you're about to write, whatever its date,", "as the one you're about to write, on the same date,"),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_whatever_the_date_clause_is_dropped(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, ", whatever its date,", ""),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_project_command_changes_or_goes(self):
        for rel in (self.RUN, self.DEBUG):
            for new in ('basename "$PWD"', 'basename "$(git rev-parse --show-prefix)"', "the folder"):
                with self.subTest(skill=rel, new=new):
                    self.assertCaughtBy(rel, lambda t: t.replace('basename "$(git rev-parse --show-toplevel)"', new, 1),
                                        "test_both_skills_carry_the_shared_retro_text")

    def test_the_no_repo_fallback_is_dropped(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "; outside a git repo, the working folder's name"),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_subfolder_clause_is_dropped(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, ", not the subfolder you're in"),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_heading_goes_back_to_project_folders_name(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: t.replace("<date> | <project> |", "<date> | <project folder's name> |", 1),
                                    "test_each_skill_carries_its_own_retro_text_in_the_retro_section")

    def test_debug_run_name_rule_is_dropped_or_changed(self):
        sentence = "The slug is the working file's name when the hunt has one (`debug-<slug>.md`), otherwise a short name for the bug, two or three words joined by hyphens; a resumed hunt uses the name already in the file for it."
        self.assertCaughtBy(self.DEBUG, lambda t: flat_sub(t, sentence), "test_each_skill_carries_its_own_retro_text_in_the_retro_section")
        for old, new in (("otherwise a short name for the bug, two or three words joined by hyphens", "otherwise any name"),
                         ("a resumed hunt uses the name already in the file for it", "a resumed hunt picks a new name"),
                         ("The slug is the working file's name when the hunt has one", "The slug is a name")):
            with self.subTest(old=old):
                self.assertCaughtBy(self.DEBUG, lambda t: flat_sub(t, old, new), "test_each_skill_carries_its_own_retro_text_in_the_retro_section")

    def test_the_tie_break_sentence_is_dropped(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "When two fit, use the one listed first, so the same mistake gets the same word each time:", "Pick one:"),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_tie_break_says_last_instead_of_first(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "use the one listed first", "use the one listed last"),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_the_kind_words_are_reordered_in_one_skill(self):
        # The tie-break depends on the order, so a swap in one skill must fail.
        def swap(t):
            pair = re.search(r"(^- \S+ \[blocked\]:.*\n)(^- \S+ \[fix-rounds\]:.*\n)", t, re.M)
            self.assertIsNotNone(pair)
            return t.replace(pair.group(0), pair.group(2) + pair.group(1), 1)
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, swap, "test_both_skills_name_exactly_the_same_six_kind_words")

    def test_the_copy_as_written_sentence_is_dropped(self):
        for rel in (self.RUN, self.DEBUG):
            with self.subTest(skill=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "Copy lines as first written, never reworded, or the check can't tell they're there"),
                                    "test_both_skills_carry_the_shared_retro_text")

    def test_run_plan_loses_the_copy_from_the_build_log_pointer(self):
        self.assertCaughtBy(self.RUN, lambda t: flat_sub(t, "(copy them from the build log's Retro section)"),
                            "test_each_skill_carries_its_own_retro_text_in_the_retro_section")


    # Who may write it
    def test_brainstorm_is_told_to_write_it(self):
        self.assertCaughtBy("skills/brainstorm/SKILL.md", lambda t: t.rstrip("\n") + "\n\nAppend a retro to `~/.foundry/retro.md`.\n",
                            "test_no_other_skill_writes_it")

    def test_ship_is_told_to_write_it(self):
        self.assertCaughtBy("skills/ship/SKILL.md", lambda t: t.rstrip("\n") + "\n\nSet FOUNDRY_RETRO_FILE and append.\n",
                            "test_no_other_skill_writes_it")

    def test_docs_agent_is_told_to_append_to_the_retro_file(self):
        self.assertCaughtBy("agents/docs.md", lambda t: t.rstrip("\n") + "\n\nAppend a line to `~/.foundry/retro.md` when you finish.\n",
                            "test_no_agent_and_no_references_file_mentions_the_retro_file")

    def test_any_agent_mentions_the_variable(self):
        self.assertCaughtBy("agents/implement.md", lambda t: t.rstrip("\n") + "\n\nSet FOUNDRY_RETRO_FILE first.\n",
                            "test_no_agent_and_no_references_file_mentions_the_retro_file")

    def test_the_techniques_file_is_told_to_copy_the_retro_elsewhere(self):
        self.assertCaughtBy("skills/debug/references/techniques.md", lambda t: t.rstrip("\n") + "\n\nCopy the retro file to a shared drive.\n",
                            "test_no_agent_and_no_references_file_mentions_the_retro_file")

    def test_the_techniques_file_names_the_path(self):
        self.assertCaughtBy("skills/debug/references/techniques.md", lambda t: t.rstrip("\n") + "\n\ncp ~/.foundry/retro.md /tmp/x\n",
                            "test_no_agent_and_no_references_file_mentions_the_retro_file")

    # Leftovers of the first design anywhere in the shipped tree
    def test_the_old_path_comes_back_in_a_doc(self):
        for rel in ("docs/walkthrough.md", "docs/orchestrator.md", "evals/README.md", "CONTRIBUTING.md", "agents/qa.md"):
            with self.subTest(file=rel):
                self.assertCaughtBy(rel, lambda t: t.rstrip("\n") + "\n\nSee ~/.claude/foundry-retro.md.\n",
                                    "test_the_first_designs_path_and_wording_are_gone_from_the_shipped_tree")

    def test_claude_config_dir_comes_back_in_a_skill(self):
        self.assertCaughtBy("skills/ship/SKILL.md", lambda t: t.rstrip("\n") + "\n\nUses ${CLAUDE_CONFIG_DIR:-$HOME/.claude}.\n",
                            "test_the_first_designs_path_and_wording_are_gone_from_the_shipped_tree")

    def test_the_old_none_sentence_comes_back(self):
        self.assertCaughtBy(self.DEBUG, lambda t: t.rstrip("\n").replace("\n---\n\n## Red flags", "\n`- none` if nothing did.\n\n---\n\n## Red flags", 1),
                            "test_the_first_designs_path_and_wording_are_gone_from_the_shipped_tree")

    # README and PRIVACY
    def test_readme_and_privacy_lose_the_path_or_variable(self):
        for rel in ("README.md", "PRIVACY.md"):
            for needle in ("~/.foundry/retro.md", "FOUNDRY_RETRO_FILE"):
                with self.subTest(doc=rel, needle=needle):
                    def edit(t):
                        first = t.index("one file outside") if False else 0
                        return t.replace(needle, "X", 1) if t.count(needle) == 1 else t.replace(needle, "X")
                    self.assertCaughtBy(rel, edit, "test_readme_and_privacy_say_where_and_what")

    def test_readme_and_privacy_lose_what_an_entry_holds(self):
        for rel in ("README.md", "PRIVACY.md"):
            with self.subTest(doc=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "the date, the project folder's name, the plan file's name or the bug's short name, and one line per correction", "some notes"),
                                    "test_readme_and_privacy_say_where_and_what")

    def test_readme_and_privacy_lose_the_clean_run_sentence(self):
        for rel in ("README.md", "PRIVACY.md"):
            with self.subTest(doc=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "A run with nothing to correct writes nothing."),
                                    "test_readme_and_privacy_say_where_and_what")

    def test_readme_and_privacy_say_none_can_be_there(self):
        for rel in ("README.md", "PRIVACY.md"):
            with self.subTest(doc=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "The instructions tell the session to keep code, file contents and secrets out of it.", "No code, file contents or secrets are in it."),
                                    "test_readme_and_privacy_say_where_and_what")

    def test_readme_and_privacy_lose_the_committed_copy(self):
        for rel in ("README.md", "PRIVACY.md"):
            with self.subTest(doc=rel):
                self.assertCaughtBy(rel, lambda t: flat_sub(t, "which is committed with the plan"),
                                    "test_readme_and_privacy_say_where_and_what")

    def test_readme_loses_one_file_outside_your_project(self):
        self.assertCaughtBy("README.md", lambda t: flat_sub(t, "it's the one file the plugin writes outside your project"),
                            "test_readme_says_it_is_the_one_file_written_outside_the_project_and_how_to_remove_it")

    def test_readme_uninstall_loses_the_removal_command(self):
        self.assertCaughtBy("README.md", lambda t: t.replace("`rm -r ~/.foundry` takes it away.", "", 1),
                            "test_readme_says_it_is_the_one_file_written_outside_the_project_and_how_to_remove_it")

    def test_readme_uninstall_loses_that_the_file_stays(self):
        self.assertCaughtBy("README.md", lambda t: flat_sub(t, "The one thing it leaves behind is the retro file, if your runs have written one:"),
                            "test_readme_says_it_is_the_one_file_written_outside_the_project_and_how_to_remove_it")

    def test_readme_debug_row_goes_back_to_the_same_short_retro(self):
        self.assertCaughtBy("README.md", lambda t: flat_sub(t, "It ends by adding any corrections the hunt needed to `~/.foundry/retro.md`, in the same line shape as `run-plan`.", "It ends with the same short retro as run-plan."),
                            "test_readme_skill_rows_say_where_the_retro_goes")

    def test_readme_run_plan_row_loses_where_the_retro_goes(self):
        self.assertCaughtBy("README.md", lambda t: flat_sub(t, "(in the build log, and in `~/.foundry/retro.md`)"),
                            "test_readme_skill_rows_say_where_the_retro_goes")

    def test_privacy_says_it_stores_nothing_again(self):
        self.assertCaughtBy("PRIVACY.md", lambda t: flat_sub(
            t, "The Foundry doesn't collect or send any data. The one thing it stores is a file on your own machine, described below.",
            "The Foundry doesn't collect, store, or send any data."),
            "test_privacy_no_longer_says_it_stores_nothing")

    def test_privacy_says_it_sends_the_file_somewhere(self):
        self.assertCaughtBy("PRIVACY.md", lambda t: flat_sub(t, "and nothing sends it anywhere"),
                            "test_privacy_no_longer_says_it_stores_nothing")

    # Eval commands
    def test_the_eval_commands_lose_the_retro_prefix(self):
        for rel in ("evals/README.md", "CONTRIBUTING.md"):
            with self.subTest(doc=rel):
                self.assertCaughtBy(rel, lambda t: re.sub(r'FOUNDRY_RETRO_FILE="\$\(mktemp\)" (?=claude plugin eval \. --tag)', "", t, count=1),
                                    "test_the_eval_commands_that_run_skills_set_the_retro_file_to_a_scratch_path")

    def test_the_eval_commands_point_the_retro_at_the_real_file(self):
        for rel in ("evals/README.md", "CONTRIBUTING.md"):
            with self.subTest(doc=rel):
                self.assertCaughtBy(rel, lambda t: t.replace('FOUNDRY_RETRO_FILE="$(mktemp)" claude plugin eval .', 'claude plugin eval .', 1),
                                    "test_the_eval_commands_that_run_skills_set_the_retro_file_to_a_scratch_path")

    def test_the_eval_docs_lose_the_reason(self):
        for rel in ("evals/README.md", "CONTRIBUTING.md"):
            with self.subTest(doc=rel):
                self.assertCaughtBy(rel, lambda t: t.replace("~/.foundry/retro.md", "the real file"), "test_the_eval_docs_say_why")


if __name__ == "__main__":
    unittest.main()
