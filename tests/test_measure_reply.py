"""Tests for evals-expensive/measure_reply.py and the reply-size cases that sync_big_sweep.py writes.

Every transcript, harness result and saved file is built in a temp folder. Nothing here starts a model
session. Standard library only; runs on Python 3.9.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPENSIVE = ROOT / "evals-expensive"
MEASURE = EXPENSIVE / "measure_reply.py"
SYNC = EXPENSIVE / "sync_big_sweep.py"
BIG_SCAFFOLD = EXPENSIVE / "big-sweep-in-parts" / "scaffold.sh"
STOCK_PYTHON = "/usr/bin/python3"

MARKER = "TAIL-MARK-6620"
SIZES = [("150", "150"), ("230", "230"), ("320", "320"), ("400", "400"), ("450", "450"), ("full", "")]


def tool_use(use_id, name="Agent", agent="the-foundry:investigate", prompt="Look at the repo.\nSecond line."):
    return {"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": use_id, "name": name, "input": {"subagent_type": agent, "prompt": prompt}}]}}


def tool_result(use_id, content, parent=None, extra=None):
    event = {"type": "user", "parent_tool_use_id": parent, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": use_id, "content": content}]}}
    event.update(extra or {})
    return event


def final(text):
    return {"type": "result", "subtype": "success", "result": text}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write_jsonl(self, events, name="t.jsonl", raw_lines=None):
        path = self.tmp / name
        lines = [json.dumps(e) for e in events] + list(raw_lines or [])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def run_measure(self, *args, python=None):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([python or sys.executable, str(MEASURE), *args], capture_output=True, text=True, env=env)

    def transcript(self, events, marker=MARKER, **kw):
        return self.run_measure("--transcript", str(self.write_jsonl(events, **kw)), "--marker", marker)

    def rows(self, result):
        """Tab-split output lines (everything but the final-result line)."""
        return [line.split("\t") for line in result.stdout.splitlines()]

    def one(self, content, **kw):
        result = self.transcript([tool_use("a1"), tool_result("a1", content), final("done")], **kw)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.rows(result)[0]


class TranscriptShapeTest(Base):
    def test_a_whole_inline_result_is_five_fields_ending_in_whole(self):
        row = self.one("Report body\n%s\n" % MARKER)
        self.assertEqual(row, ["top", "the-foundry:investigate", "Look at the repo.", str(len(("Report body\n%s\n" % MARKER).encode())), "whole"])

    def test_a_preview_result_is_not_whole_and_carries_its_first_300_characters_on_one_line(self):
        text = "Output too large (56KB).\nsecond\tline " + "x" * 400
        row = self.one(text)
        self.assertEqual(row[4], "not-whole")
        self.assertEqual(len(row), 6)
        self.assertEqual(row[5], " ".join(text.split())[:300])
        self.assertNotIn("\n", row[5])

    def test_nested_results_say_nested_and_top_ones_say_top(self):
        events = [
            tool_use("top1"),
            tool_use("n1", agent="the-foundry:file-reader", prompt="Read a.py"),
            tool_result("n1", "summary\nAREA REPORT ENDS", parent="top1"),
            tool_result("top1", "all\n%s" % MARKER),
            final("the answer"),
        ]
        result = self.transcript(events)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = self.rows(result)
        self.assertEqual([r[0] for r in rows[:2]], ["nested", "top"])
        self.assertEqual(rows[0][1:3], ["the-foundry:file-reader", "Read a.py"])
        self.assertEqual(rows[0][4], "whole")
        self.assertEqual(rows[1][4], "whole")

    def test_a_sidechain_flagged_result_counts_as_nested_in_a_session_transcript(self):
        events = [tool_use("s1"), tool_result("s1", "x\n" + MARKER, extra={"isSidechain": True})]
        result = self.transcript(events)
        self.assertEqual(self.rows(result)[0][0], "nested")

    def test_the_final_result_text_is_printed_after_the_rows(self):
        result = self.transcript([tool_use("a1"), tool_result("a1", MARKER), final("FINAL TEXT")])
        self.assertEqual(result.stdout.splitlines()[-1], "FINAL TEXT")

    def test_a_transcript_without_a_final_result_message_still_exits_zero(self):
        result = self.transcript([tool_use("a1"), tool_result("a1", MARKER)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)

    def test_only_the_first_line_of_the_dispatch_prompt_is_shown_with_tabs_flattened(self):
        events = [tool_use("a1", prompt="Dispatch\tthe agent\nsecond\nthird"), tool_result("a1", MARKER)]
        row = self.rows(self.transcript(events))[0]
        self.assertEqual(row[2], "Dispatch the agent")
        self.assertEqual(len(row), 5)

    def test_the_task_tool_name_counts_like_agent(self):
        events = [tool_use("a1", name="Task"), tool_result("a1", MARKER)]
        self.assertEqual(self.rows(self.transcript(events))[0][4], "whole")

    def test_a_result_given_as_a_list_of_text_blocks_is_read(self):
        row = self.one([{"type": "text", "text": "part one"}, {"type": "text", "text": MARKER}])
        self.assertEqual(row[4], "whole")

    def test_other_tools_results_are_not_listed(self):
        events = [tool_use("b1", name="Bash"), tool_result("b1", "ls output"), tool_use("a1"), tool_result("a1", MARKER)]
        self.assertEqual(len(self.rows(self.transcript(events))), 1)

    def test_garbage_lines_in_the_jsonl_are_skipped(self):
        path = self.write_jsonl([tool_use("a1"), tool_result("a1", MARKER)], raw_lines=["{not json", "[1,2]", ""])
        result = self.run_measure("--transcript", str(path), "--marker", MARKER)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_agent_dispatch_with_no_subagent_type_still_lists(self):
        event = tool_use("a1")
        event["message"]["content"][0]["input"] = {"prompt": "p"}
        row = self.rows(self.transcript([event, tool_result("a1", MARKER)]))[0]
        self.assertEqual(row[0], "top")
        self.assertEqual(row[4], "whole")

    def test_the_tool_result_of_an_error_is_still_measured(self):
        row = self.one("Agent type 'x' not found.")
        self.assertEqual(row[4], "not-whole")


class TranscriptErrorTest(Base):
    def assert_cant_measure(self, result):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith("CAN'T MEASURE: "), result.stdout)

    def test_a_transcript_with_no_agent_result_exits_two(self):
        events = [tool_use("b1", name="Bash"), tool_result("b1", "x"), final("done")]
        self.assert_cant_measure(self.transcript(events))

    def test_a_dispatch_that_never_got_a_result_exits_two(self):
        self.assert_cant_measure(self.transcript([tool_use("a1"), final("done")]))

    def test_a_result_for_an_unknown_tool_use_id_exits_two(self):
        self.assert_cant_measure(self.transcript([tool_result("ghost", MARKER)]))

    def test_an_empty_file_exits_two(self):
        path = self.tmp / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        self.assert_cant_measure(self.run_measure("--transcript", str(path), "--marker", MARKER))

    def test_a_missing_file_exits_two(self):
        self.assert_cant_measure(self.run_measure("--transcript", str(self.tmp / "nope.jsonl"), "--marker", MARKER))

    def test_a_directory_instead_of_a_file_exits_two_not_a_traceback(self):
        result = self.run_measure("--transcript", str(self.tmp), "--marker", MARKER)
        self.assert_cant_measure(result)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_file_of_only_garbage_exits_two(self):
        path = self.tmp / "junk.jsonl"
        path.write_text("hello\nworld\n", encoding="utf-8")
        self.assert_cant_measure(self.run_measure("--transcript", str(path), "--marker", MARKER))

    def test_no_marker_is_a_usage_error_not_a_zero(self):
        result = self.run_measure("--transcript", str(self.write_jsonl([tool_use("a1"), tool_result("a1", MARKER)])))
        self.assertNotEqual(result.returncode, 0)

    def test_giving_both_sources_is_a_usage_error(self):
        path = self.write_jsonl([tool_use("a1"), tool_result("a1", MARKER)])
        result = self.run_measure("--transcript", str(path), "--harness", str(path), "--marker", MARKER)
        self.assertNotEqual(result.returncode, 0)


class BytesAndMarkerTest(Base):
    def test_bytes_are_utf8_bytes_not_characters(self):
        text = "héllo ☃ \U0001F600\n%s" % MARKER
        row = self.one(text)
        self.assertEqual(row[3], str(len(text.encode("utf-8"))))
        self.assertNotEqual(row[3], str(len(text)))

    def test_a_marker_inside_a_longer_word_is_not_whole(self):
        for text in ("NOT" + MARKER, MARKER + "X", MARKER + "-2", "pre" + MARKER + "post"):
            with self.subTest(text=text):
                self.assertEqual(self.one("body\n" + text)[4], "not-whole")

    def test_a_marker_inside_a_sentence_is_not_whole(self):
        self.assertEqual(self.one("The last line should be %s, right?" % MARKER)[4], "not-whole")

    def test_a_marker_on_its_own_line_is_whole_even_with_trailing_blank_lines_and_spaces(self):
        self.assertEqual(self.one("body\n  %s  \n\n\n" % MARKER)[4], "whole")

    def test_a_crlf_line_ending_still_counts_as_a_whole_line(self):
        self.assertEqual(self.one("body\r\n%s\r\n" % MARKER)[4], "whole")

    def test_the_two_report_end_lines_count_without_the_marker(self):
        for end in ("INVESTIGATE REPORT ENDS", "AREA REPORT ENDS"):
            with self.subTest(end=end):
                self.assertEqual(self.one("body\n" + end)[4], "whole")

    def test_a_report_end_line_inside_a_longer_line_is_not_whole(self):
        self.assertEqual(self.one("see INVESTIGATE REPORT ENDS soon")[4], "not-whole")
        self.assertEqual(self.one("AREA REPORT ENDS.")[4], "not-whole")

    def test_the_marker_given_on_the_command_line_is_the_one_used(self):
        self.assertEqual(self.one("body\nOTHER-MARK", marker="OTHER-MARK")[4], "whole")
        self.assertEqual(self.one("body\n" + MARKER, marker="OTHER-MARK")[4], "not-whole")

    def test_a_whole_inline_result_gets_no_saved_fields_even_if_it_names_a_path(self):
        row = self.one("Full output saved to: /tmp/x.txt\n" + MARKER)
        self.assertEqual(len(row), 5)

    def test_a_not_whole_result_with_no_saved_notice_has_exactly_six_fields(self):
        self.assertEqual(len(self.one("just a cut-off report")), 6)


WRAPPER_TRAILER = "agentId: a1b2c3d4e5f6 (use SendMessage with to: 'a1b2c3d4e5f6' to continue this agent)\n<usage>total_tokens: 41230\ntool_uses: 12\nduration_ms: 91000</usage>"
TOOLS_BLOCK = "<tools-used-before-summary>Read x12, Bash x3</tools-used-before-summary>"
ENDS = (MARKER, "INVESTIGATE REPORT ENDS", "AREA REPORT ENDS")


class WholeMeansTheLastLineTest(Base):
    """`whole` only when the marker or a report-end line is the last non-blank line once the harness's wrapper is off."""

    def nested(self, content):
        events = [tool_use("top1"), tool_use("n1", agent="the-foundry:investigate", prompt="AREA LEAD\nArea: web"), tool_result("n1", content, parent="top1"),
                  tool_result("top1", MARKER), final("done")]
        result = self.transcript(events)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.rows(result)[0]
        self.assertEqual(row[0], "nested")
        return row

    def test_each_end_line_counts_as_the_last_line_at_either_depth(self):
        for end in ENDS:
            with self.subTest(end=end, depth="top"):
                self.assertEqual(self.one("report\n%s\n" % end)[4], "whole")
            with self.subTest(end=end, depth="nested"):
                self.assertEqual(self.nested("report\n%s\n" % end)[4], "whole")

    def test_an_end_line_in_the_middle_of_a_cut_off_report_is_not_whole_at_either_depth(self):
        for end in ENDS:
            text = "part one\n%s\nthen the report goes on and is cut off mid-sent" % end
            with self.subTest(end=end, depth="top"):
                self.assertEqual(self.one(text)[4], "not-whole")
            with self.subTest(end=end, depth="nested"):
                self.assertEqual(self.nested(text)[4], "not-whole")

    def test_a_cut_off_report_gets_its_preview_fields_and_a_whole_one_gets_none(self):
        row = self.one("%s\nmore text after the marker" % MARKER)
        self.assertEqual(row[4], "not-whole")
        self.assertEqual(len(row), 6)
        self.assertEqual(len(self.one("more\n%s" % MARKER)), 5)

    def test_a_wrapper_trailer_after_the_last_line_does_not_hide_it(self):
        for end in ENDS:
            with self.subTest(end=end):
                self.assertEqual(self.one("report\n%s\n%s" % (end, WRAPPER_TRAILER))[4], "whole")

    def test_a_tools_used_block_in_the_trailer_does_not_hide_it_either(self):
        self.assertEqual(self.one("report\n%s\n%s\n%s" % (MARKER, WRAPPER_TRAILER, TOOLS_BLOCK))[4], "whole")
        self.assertEqual(self.one("report\n%s\n%s\n%s" % (MARKER, TOOLS_BLOCK, WRAPPER_TRAILER))[4], "whole")

    def test_a_leading_tools_used_block_is_off_the_report_text_too(self):
        text = "  %s\n  \n[Subagent hand-back] report\n%s\n%s" % (TOOLS_BLOCK, MARKER, WRAPPER_TRAILER)
        self.assertEqual(self.one(text)[4], "whole")

    def test_a_marker_that_only_the_wrapper_carries_is_not_whole(self):
        self.assertEqual(self.one("cut off report\nagentId: x1\n%s" % MARKER)[4], "not-whole")
        self.assertEqual(self.one("cut off report\n%s\n%s" % (WRAPPER_TRAILER, MARKER))[4], "not-whole")
        self.assertEqual(self.one("cut off report\n<tools-used-before-summary>%s</tools-used-before-summary>" % MARKER)[4], "not-whole")

    def test_a_cut_off_report_with_the_marker_mid_way_and_a_trailer_is_not_whole(self):
        self.assertEqual(self.one("part one\n%s\ncut off here\n%s" % (MARKER, WRAPPER_TRAILER))[4], "not-whole")

    def test_an_agent_id_that_is_not_at_the_start_of_a_line_is_not_a_wrapper(self):
        self.assertEqual(self.one("see agentId: abc for details\n%s" % MARKER)[4], "whole")
        self.assertEqual(self.one("%s\nthe line agentId: abc is quoted here" % MARKER)[4], "not-whole")

    def test_the_byte_count_is_still_the_whole_results_bytes_wrapper_included(self):
        text = "report \u2603\n%s\n%s" % (MARKER, WRAPPER_TRAILER)
        row = self.one(text)
        self.assertEqual(row[3], str(len(text.encode("utf-8"))))
        self.assertGreater(int(row[3]), len(("report \u2603\n%s\n" % MARKER).encode("utf-8")))

    def test_an_empty_result_and_a_wrapper_only_result_are_not_whole(self):
        self.assertEqual(self.one("")[4], "not-whole")
        self.assertEqual(self.one(WRAPPER_TRAILER)[4], "not-whole")

    def test_the_output_gains_nothing_new(self):
        row = self.one("report\n%s\n%s" % (MARKER, WRAPPER_TRAILER))
        self.assertEqual(len(row), 5)
        self.assertEqual(row[:3], ["top", "the-foundry:investigate", "Look at the repo."])


class WholeMeansTheLastLineMutationTest(Base):
    """A temp copy of the script with one piece broken must be caught by a test above."""

    def mutant(self, old, new):
        src = MEASURE.read_text(encoding="utf-8")
        self.assertEqual(src.count(old), 1, "the script no longer has %r once; update this mutation" % old)
        path = self.tmp / "mutant.py"
        path.write_text(src.replace(old, new), encoding="utf-8")
        return path

    def verdict(self, script, content):
        path = self.write_jsonl([tool_use("a1"), tool_result("a1", content), final("f")])
        result = subprocess.run([sys.executable, str(script), "--transcript", str(path), "--marker", MARKER], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()[0].split("\t")[4]

    def test_the_unmutated_copy_behaves_like_the_script(self):
        same = self.mutant("return bool(lines) and lines[-1] in markers", "return bool(lines) and lines[-1] in markers")
        for text in ("x\n%s" % MARKER, "%s\nmore" % MARKER, "x\n%s\n%s" % (MARKER, WRAPPER_TRAILER)):
            self.assertEqual(self.verdict(same, text), self.verdict(MEASURE, text))

    def test_counting_a_marker_anywhere_again_is_caught(self):
        m = self.mutant("return bool(lines) and lines[-1] in markers", "return any(line in markers for line in lines)")
        text = "part one\n%s\ncut off here" % MARKER
        self.assertEqual(self.verdict(MEASURE, text), "not-whole")
        self.assertEqual(self.verdict(m, text), "whole")

    def test_not_taking_the_wrapper_off_is_caught(self):
        m = self.mutant("    cut = AGENT_ID_LINE.search(text)\n", "    cut = None\n")
        text = "report\n%s\n%s" % (MARKER, WRAPPER_TRAILER)
        self.assertEqual(self.verdict(MEASURE, text), "whole")
        self.assertEqual(self.verdict(m, text), "not-whole")

    def test_not_taking_the_tools_used_block_off_is_caught(self):
        m = self.mutant("    return TOOLS_USED.sub(\"\", text)\n", "    return text\n")
        text = "report\n%s\n%s" % (MARKER, TOOLS_BLOCK)
        self.assertEqual(self.verdict(MEASURE, text), "whole")
        self.assertEqual(self.verdict(m, text), "not-whole")

    def test_dropping_one_of_the_two_report_end_lines_is_caught(self):
        m = self.mutant('REPORT_ENDS = ("INVESTIGATE REPORT ENDS", "AREA REPORT ENDS")', 'REPORT_ENDS = ("INVESTIGATE REPORT ENDS",)')
        self.assertEqual(self.verdict(MEASURE, "x\nAREA REPORT ENDS"), "whole")
        self.assertEqual(self.verdict(m, "x\nAREA REPORT ENDS"), "not-whole")


class SavedFileTest(Base):
    def saved(self, body, name="saved.txt", data=None):
        path = self.tmp / name
        path.write_bytes(data if data is not None else body.encode("utf-8"))
        return path

    def notice(self, path, wrapper=True, text="Output too large (56KB). Full output saved to: %s"):
        inner = (text % path) + "\n\nPreview (first 2KB):\nSection 1 ...\n"
        return "<persisted-output>\n%s</persisted-output>" % inner if wrapper else inner

    def test_a_preview_whose_saved_file_ends_with_the_marker_is_saved_whole(self):
        path = self.saved("# Report\nbody\n%s\n" % MARKER)
        row = self.one(self.notice(path))
        self.assertEqual(row[4], "not-whole")
        self.assertEqual(row[-3:], [str(path), str(path.stat().st_size), "saved-whole"])
        self.assertEqual(len(row), 9)

    def test_trailing_blank_lines_after_the_marker_in_the_saved_file_still_count(self):
        path = self.saved("body\n%s\n\n  \n\n" % MARKER)
        self.assertEqual(self.one(self.notice(path))[-1], "saved-whole")

    def test_a_saved_file_ending_in_a_report_end_line_is_saved_whole(self):
        for end in ("INVESTIGATE REPORT ENDS", "AREA REPORT ENDS"):
            with self.subTest(end=end):
                path = self.saved("body\n%s\n" % end)
                self.assertEqual(self.one(self.notice(path))[-1], "saved-whole")

    def test_a_saved_file_cut_short_is_saved_not_whole_with_its_size(self):
        path = self.saved("# Report\nhalf a sentence that stops mid-")
        row = self.one(self.notice(path))
        self.assertEqual(row[-3:], [str(path), str(path.stat().st_size), "saved-not-whole"])

    def test_an_empty_saved_file_is_saved_not_whole_with_size_zero(self):
        path = self.saved("")
        self.assertEqual(self.one(self.notice(path))[-2:], ["0", "saved-not-whole"])

    def test_a_missing_saved_path_is_saved_missing_and_does_not_crash(self):
        path = self.tmp / "gone.txt"
        row = self.one(self.notice(path))
        self.assertEqual(row[-3], str(path))
        self.assertEqual(row[-1], "saved-missing")

    def test_a_saved_path_that_is_a_folder_is_saved_missing_not_a_traceback(self):
        result = self.transcript([tool_use("a1"), tool_result("a1", self.notice(self.tmp)), final("x")])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows(result)[0][-1], "saved-missing")

    def test_the_saved_size_is_utf8_bytes_not_characters(self):
        body = "héllo ☃ \U0001F600\n%s\n" % MARKER
        path = self.saved(body)
        row = self.one(self.notice(path))
        self.assertEqual(row[-2], str(len(body.encode("utf-8"))))
        self.assertNotEqual(row[-2], str(len(body)))
        self.assertEqual(row[-1], "saved-whole")

    def test_a_marker_in_the_middle_of_the_saved_file_but_not_last_is_saved_not_whole(self):
        path = self.saved("intro\n%s\nmore text after it\n" % MARKER)
        self.assertEqual(self.one(self.notice(path))[-1], "saved-not-whole")

    def test_a_marker_inside_a_longer_last_line_of_the_saved_file_is_saved_not_whole(self):
        path = self.saved("intro\nNOT%s\n" % MARKER)
        self.assertEqual(self.one(self.notice(path))[-1], "saved-not-whole")

    def test_a_saved_file_that_is_not_valid_utf8_does_not_crash(self):
        path = self.saved("", data=b"\xff\xfe\xfa bad bytes\n" + MARKER.encode() + b"\n")
        row = self.one(self.notice(path))
        self.assertEqual(row[-2], str(path.stat().st_size))
        self.assertEqual(row[-1], "saved-whole")

    def test_a_notice_without_the_persisted_output_wrapper_is_still_read(self):
        path = self.saved("x\n%s\n" % MARKER)
        self.assertEqual(self.one(self.notice(path, wrapper=False))[-1], "saved-whole")

    def test_a_notice_whose_wording_differs_a_little_is_still_read(self):
        path = self.saved("x\n%s\n" % MARKER)
        for wording in ("Output too large (56KB). Full output saved to: %s",
                        "Output too large (1.2MB). Full output saved to:   %s",
                        "output saved to: %s",
                        "FULL OUTPUT SAVED TO: %s",
                        "Result too large (56KB). Full result saved to: %s"):
            with self.subTest(wording=wording):
                row = self.one(self.notice(path, text=wording))
                self.assertEqual(row[-1], "saved-whole", row)
                self.assertEqual(row[-3], str(path))

    def test_a_notice_with_crlf_line_endings_gives_a_clean_path(self):
        path = self.saved("x\n%s\n" % MARKER)
        text = "Output too large (56KB). Full output saved to: %s\r\n\r\nPreview:\r\n..." % path
        row = self.one(text)
        self.assertEqual(row[-3], str(path))
        self.assertEqual(row[-1], "saved-whole")

    def test_a_path_with_a_space_in_it_is_read_whole(self):
        path = self.saved("x\n%s\n" % MARKER, name="my report.txt")
        row = self.one(self.notice(path))
        self.assertEqual(row[-3], str(path))
        self.assertEqual(row[-1], "saved-whole")

    def test_saved_fields_are_tab_separated_so_the_row_splits_into_nine(self):
        path = self.saved("x\n" + MARKER)
        self.assertEqual(len(self.one(self.notice(path))), 9)

    def test_each_not_whole_result_gets_its_own_saved_fields(self):
        good = self.saved("x\n%s\n" % MARKER, name="good.txt")
        cut = self.saved("x cut", name="cut.txt")
        events = [tool_use("a1"), tool_use("a2"),
                  tool_result("a1", self.notice(good)), tool_result("a2", self.notice(cut)), final("f")]
        rows = self.rows(self.transcript(events))
        self.assertEqual(rows[0][-1], "saved-whole")
        self.assertEqual(rows[1][-1], "saved-not-whole")


class HarnessTest(Base):
    def run_of(self, evidence, trace=None, extra_graders=()):
        run = {"graders": [{"name": "received-line", "evidence": "x"}, *extra_graders]}
        if evidence is not None:
            run["graders"].append({"name": "keep-report", "evidence": evidence})
        if trace is not None:
            run["tracePath"] = trace
        return run

    def harness(self, cases, name="aggregate-result.json", marker=MARKER):
        path = self.tmp / name
        path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
        return self.run_measure("--harness", str(path), "--marker", marker)

    def case(self, name, runs):
        return {"name": name, "arms": {"with": runs}}

    def report(self, body, tail=MARKER):
        return "RECEIVED: preview Output too large\nSAVED OUTPUT: read\n%s\n%s\nEND-OF-REPORT" % (body, tail)

    def test_a_run_prints_case_received_saved_bytes_and_marker_present(self):
        evidence = self.report("# Heading\nbody")
        result = self.harness([self.case("reply-size-230", [self.run_of(evidence)])])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = result.stdout.splitlines()[0].split("\t")
        expected_bytes = len(("# Heading\nbody\n" + MARKER).encode())
        self.assertEqual(row[0], "reply-size-230")
        self.assertEqual(row[1], "RECEIVED: preview Output too large")
        self.assertEqual(row[2], "SAVED OUTPUT: read")
        self.assertEqual(row[3], str(expected_bytes))
        self.assertEqual(row[4], "marker-present")

    def test_a_report_without_the_marker_says_marker_missing(self):
        evidence = "RECEIVED: whole\nSAVED OUTPUT: none\nbody cut off\nEND-OF-REPORT"
        row = self.harness([self.case("reply-size-full", [self.run_of(evidence)])]).stdout.splitlines()[0].split("\t")
        self.assertEqual(row[3], str(len("body cut off")))
        self.assertEqual(row[4], "marker-missing")

    def test_report_bytes_are_utf8_bytes(self):
        body = "café ☃"
        evidence = "RECEIVED: whole\nSAVED OUTPUT: none\n%s\n%s\nEND-OF-REPORT" % (body, MARKER)
        row = self.harness([self.case("reply-size-150", [self.run_of(evidence)])]).stdout.splitlines()[0].split("\t")
        self.assertEqual(row[3], str(len((body + "\n" + MARKER).encode("utf-8"))))

    def test_the_marker_inside_a_longer_word_in_the_report_is_marker_missing(self):
        evidence = self.report("body", tail="NOT" + MARKER)
        row = self.harness([self.case("reply-size-150", [self.run_of(evidence)])]).stdout.splitlines()[0].split("\t")
        self.assertEqual(row[4], "marker-missing")

    def test_text_after_end_of_report_is_not_counted(self):
        evidence = self.report("body") + "\nextra after the end\nmore"
        row = self.harness([self.case("reply-size-150", [self.run_of(evidence)])]).stdout.splitlines()[0].split("\t")
        self.assertEqual(row[3], str(len(("body\n" + MARKER).encode())))

    def test_a_missing_trace_path_is_reported_not_a_crash(self):
        run = self.run_of(self.report("b"), trace=str(self.tmp / "no-such-trace.jsonl"))
        result = self.harness([self.case("reply-size-150", [run])])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("trace: missing", result.stdout)

    def test_a_run_with_no_trace_path_key_is_reported_not_a_crash(self):
        result = self.harness([self.case("reply-size-150", [self.run_of(self.report("b"))])])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("trace: missing", result.stdout)

    def test_an_existing_trace_is_analysed_after_the_run_row(self):
        trace = self.write_jsonl([tool_use("a1"), tool_result("a1", "x\n" + MARKER), final("done")], name="trace.jsonl")
        result = self.harness([self.case("reply-size-400", [self.run_of(self.report("b"), trace=str(trace))])])
        lines = result.stdout.splitlines()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(lines[0].startswith("reply-size-400\t"))
        self.assertIn("top\tthe-foundry:investigate\tLook at the repo.", "\n".join(lines[1:]))
        self.assertIn("whole", lines[1])

    def test_an_existing_trace_with_no_agent_result_is_reported_without_failing_the_run(self):
        trace = self.write_jsonl([final("x")], name="trace.jsonl")
        result = self.harness([self.case("reply-size-400", [self.run_of(self.report("b"), trace=str(trace))])])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CAN'T MEASURE", result.stdout)

    def test_cases_that_are_not_reply_size_are_ignored(self):
        cases = [self.case("big-sweep-in-parts", [self.run_of(self.report("b"))]),
                 self.case("reply-size-320", [self.run_of(self.report("b"))])]
        lines = self.harness(cases).stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(not l.startswith("big-sweep") for l in lines))

    def test_every_run_of_every_reply_size_case_gets_a_row(self):
        cases = [self.case("reply-size-150", [self.run_of(self.report("a")), self.run_of(self.report("b"))]),
                 self.case("reply-size-full", [self.run_of(self.report("c"))])]
        result = self.harness(cases)
        rows = [l.split("\t")[0] for l in result.stdout.splitlines() if l.startswith("reply-size")]
        self.assertEqual(rows, ["reply-size-150", "reply-size-150", "reply-size-full"])

    def test_a_run_with_no_keep_report_grader_says_so_and_does_not_crash(self):
        result = self.harness([self.case("reply-size-150", [self.run_of(None)])])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no keep-report evidence", result.stdout)

    def test_evidence_without_received_or_saved_lines_does_not_crash(self):
        result = self.harness([self.case("reply-size-150", [self.run_of("just text\nEND-OF-REPORT")])])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_result_with_no_reply_size_case_exits_two(self):
        result = self.harness([self.case("big-sweep-in-parts", [self.run_of(self.report("b"))])])
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stdout.startswith("CAN'T MEASURE: "))

    def test_a_result_with_no_cases_exits_two(self):
        path = self.tmp / "empty.json"
        path.write_text("{}", encoding="utf-8")
        result = self.run_measure("--harness", str(path), "--marker", MARKER)
        self.assertEqual(result.returncode, 2)

    def test_a_missing_harness_file_exits_two(self):
        result = self.run_measure("--harness", str(self.tmp / "nope.json"), "--marker", MARKER)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stdout.startswith("CAN'T MEASURE: "))

    def test_a_harness_file_that_is_not_json_exits_two(self):
        path = self.tmp / "bad.json"
        path.write_text("{oops", encoding="utf-8")
        result = self.run_measure("--harness", str(path), "--marker", MARKER)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_json_list_at_the_top_exits_two_not_a_traceback(self):
        path = self.tmp / "list.json"
        path.write_text("[1, 2]", encoding="utf-8")
        result = self.run_measure("--harness", str(path), "--marker", MARKER)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_case_whose_arms_are_malformed_does_not_crash(self):
        result = self.harness([{"name": "reply-size-150", "arms": 7}, self.case("reply-size-full", [self.run_of(self.report("b"))])])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(os.access(STOCK_PYTHON, os.X_OK), "no /usr/bin/python3")
class StockPythonTest(Base):
    def test_the_script_runs_under_the_stock_python(self):
        saved = self.tmp / "s.txt"
        saved.write_text("x\n%s\n" % MARKER, encoding="utf-8")
        text = "Output too large. Full output saved to: %s\npreview" % saved
        path = self.write_jsonl([tool_use("a1"), tool_result("a1", text), final("f")])
        result = self.run_measure("--transcript", str(path), "--marker", MARKER, python=STOCK_PYTHON)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows(result)[0][-1], "saved-whole")


class ReplySizeCopiesTest(Base):
    """The six reply-size cases, checked against what sync_big_sweep.py writes with --out."""

    def written(self):
        out = self.tmp / "out"
        result = subprocess.run([sys.executable, str(SYNC), "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return out

    def test_out_writes_every_reply_size_file_byte_identical_to_the_committed_one(self):
        out = self.written()
        names = sorted(str(p.relative_to(out)) for p in out.rglob("reply-size-*/**/*") if p.is_file())
        self.assertEqual(len(names), 6 * 6, names)
        for rel in names:
            with self.subTest(file=rel):
                self.assertEqual((out / rel).read_bytes(), (EXPENSIVE / rel).read_bytes())

    def test_the_committed_reply_size_folders_hold_exactly_the_six_cases_and_their_files(self):
        folders = sorted(p.name for p in EXPENSIVE.glob("reply-size-*"))
        self.assertEqual(folders, ["reply-size-" + s for s, _ in SIZES])
        for folder, _ in SIZES:
            with self.subTest(folder=folder):
                files = sorted(str(p.relative_to(EXPENSIVE / ("reply-size-" + folder))) for p in (EXPENSIVE / ("reply-size-" + folder)).rglob("*") if p.is_file())
                self.assertEqual(files, ["case.yaml", "graders/keep-report.md", "graders/received-line.md",
                                         "graders/saved-line.md", "prompt.md", "scaffold.sh"])

    def test_each_scaffold_copy_differs_from_the_big_sweep_scaffold_only_on_line_14(self):
        base = BIG_SCAFFOLD.read_bytes().split(b"\n")
        self.assertEqual(base[13], b'SUBSET=""')
        for suffix, subset in SIZES:
            with self.subTest(case=suffix):
                copy = (EXPENSIVE / ("reply-size-" + suffix) / "scaffold.sh").read_bytes().split(b"\n")
                self.assertEqual(len(copy), len(base))
                self.assertEqual(copy[13], ('SUBSET="%s"' % subset).encode())
                self.assertEqual(copy[:13] + copy[14:], base[:13] + base[14:])

    def test_the_full_case_scaffold_is_byte_identical_to_the_big_sweep_one(self):
        self.assertEqual((EXPENSIVE / "reply-size-full" / "scaffold.sh").read_bytes(), BIG_SCAFFOLD.read_bytes())

    def test_out_writes_the_scaffold_copies_executable_like_the_original(self):
        out = self.written()
        for suffix, _ in SIZES:
            with self.subTest(case=suffix):
                self.assertTrue(os.access(str(out / ("reply-size-" + suffix) / "scaffold.sh"), os.X_OK))

    def test_the_committed_scaffold_copies_keep_the_big_sweeps_exec_bit(self):
        want = os.stat(str(BIG_SCAFFOLD)).st_mode & 0o111
        for suffix, _ in SIZES:
            with self.subTest(case=suffix):
                self.assertEqual(os.stat(str(EXPENSIVE / ("reply-size-" + suffix) / "scaffold.sh")).st_mode & 0o111, want)

    def test_each_prompt_has_the_exact_front_matter_and_the_marker_and_brief(self):
        for suffix, _ in SIZES:
            text = (EXPENSIVE / ("reply-size-" + suffix) / "prompt.md").read_text(encoding="utf-8")
            with self.subTest(case=suffix):
                head, _, body = text[4:].partition("\n---\n")
                self.assertTrue(text.startswith("---\n"))
                self.assertEqual(head.splitlines(), ["runs: 1", "tags: [reply-size]", "max_turns: 12",
                                                     "timeout_seconds: 3600", "allowed_tools: [Agent, Read, Glob, Grep, Bash]"])
                self.assertTrue(body.lstrip().startswith("Dispatch the the-foundry:investigate agent on the repo in the current directory"))
                self.assertIn("`RECEIVED: whole` if the agent result you got ends with the line `TAIL-MARK-6620`", body)
                self.assertIn("SAVED OUTPUT: read", body)
                self.assertIn("SAVED OUTPUT: blocked", body)
                self.assertIn("SAVED OUTPUT: none", body)
                self.assertIn("adding only a last line that says END-OF-REPORT. Don't read the code yourself.", body)
                self.assertIn("use `./bin/git` wherever you'd type `git`", body)
                self.assertIn("The user approved reading every file, whatever the count.", body)

    def test_the_six_prompts_are_identical_and_the_cases_are_named_for_their_folders(self):
        prompts = {(EXPENSIVE / ("reply-size-" + s) / "prompt.md").read_bytes() for s, _ in SIZES}
        self.assertEqual(len(prompts), 1)
        for suffix, _ in SIZES:
            with self.subTest(case=suffix):
                yaml = (EXPENSIVE / ("reply-size-" + suffix) / "case.yaml").read_text(encoding="utf-8")
                self.assertIn("name: reply-size-%s\n" % suffix, yaml)
                self.assertIn("scaffold_script: scaffold.sh", yaml)

    def test_each_case_has_the_three_briefed_graders(self):
        for suffix, _ in SIZES:
            base = EXPENSIVE / ("reply-size-" + suffix) / "graders"
            with self.subTest(case=suffix):
                keep = (base / "keep-report.md").read_text(encoding="utf-8")
                self.assertIn("type: llm", keep)
                self.assertIn("focus: last_message", keep)
                for name, pattern in (("received-line.md", "RECEIVED: (whole|preview)"), ("saved-line.md", "SAVED OUTPUT: (read|blocked|none)")):
                    text = (base / name).read_text(encoding="utf-8")
                    self.assertIn("type: regex", text)
                    self.assertIn("target: last_message", text)
                    self.assertIn(pattern, text)
                    self.assertIn("match: contains", text)

    def _copy_tree(self):
        dest = self.tmp / "copy" / "evals-expensive"
        shutil.copytree(str(EXPENSIVE), str(dest), ignore=shutil.ignore_patterns("__pycache__"))
        return dest

    def _check(self, dest):
        return subprocess.run([sys.executable, str(dest / "sync_big_sweep.py"), "--check"], capture_output=True, text=True)

    def test_check_names_a_reply_size_scaffold_that_drifted_from_the_big_sweep_one(self):
        dest = self._copy_tree()
        target = dest / "reply-size-320" / "scaffold.sh"
        target.write_text(target.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
        result = self._check(dest)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("reply-size-320/scaffold.sh", result.stdout)
        self.assertEqual(result.stdout.count("differs:"), 1, result.stdout)

    def test_check_names_a_wrong_subset_value_in_a_copy(self):
        dest = self._copy_tree()
        target = dest / "reply-size-150" / "scaffold.sh"
        target.write_text(target.read_text(encoding="utf-8").replace('SUBSET="150"', 'SUBSET="151"'), encoding="utf-8")
        result = self._check(dest)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("reply-size-150/scaffold.sh", result.stdout)

    def test_check_names_a_missing_reply_size_grader_and_a_changed_prompt(self):
        dest = self._copy_tree()
        (dest / "reply-size-full" / "graders" / "saved-line.md").unlink()
        prompt = dest / "reply-size-230" / "prompt.md"
        prompt.write_text(prompt.read_text(encoding="utf-8").replace("max_turns: 12", "max_turns: 13"), encoding="utf-8")
        result = self._check(dest)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("reply-size-full/graders/saved-line.md", result.stdout)
        self.assertIn("reply-size-230/prompt.md", result.stdout)

    def test_check_names_a_missing_reply_size_folder(self):
        dest = self._copy_tree()
        shutil.rmtree(str(dest / "reply-size-400"))
        result = self._check(dest)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stdout.count("reply-size-400/"), 6, result.stdout)

    def test_check_passes_on_a_clean_copy_and_reports_forty_three_files(self):
        result = self._check(self._copy_tree())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("43 files match", result.stdout)

    def test_out_into_a_folder_with_an_old_reply_size_scaffold_overwrites_it(self):
        out = self.tmp / "out"
        (out / "reply-size-150").mkdir(parents=True)
        (out / "reply-size-150" / "scaffold.sh").write_text("old", encoding="utf-8")
        subprocess.run([sys.executable, str(SYNC), "--out", str(out)], capture_output=True, text=True, check=True)
        self.assertEqual((out / "reply-size-150" / "scaffold.sh").read_bytes(), (EXPENSIVE / "reply-size-150" / "scaffold.sh").read_bytes())


if __name__ == "__main__":
    unittest.main()
