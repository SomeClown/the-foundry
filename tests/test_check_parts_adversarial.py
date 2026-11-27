"""Adversarial round on Task 1 of the area-lead plan: evals-expensive/check_parts.py scores a lead that ran as
the-foundry:area-lead exactly as it scores one that ran as the-foundry:investigate.

Four real runs are scored before the move and four after, so the two shapes must give the same verdict, exit code
and summary for every check that looks at leads, readers or top-level dispatches, apart from the one NOTE that
says leads ran the old way. The new shape must not hide a failure, the old rule must stand for old transcripts, and
look-alike types must not be taken for a lead.

This file imports the helpers of tests/test_check_parts.py and edits nothing there. No model session starts.
Standard library only; runs on Python 3.9.
"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_check_parts import (  # noqa: E402
    AREA_LEAD_AGENT, INVESTIGATE, OLD_SHAPE_NOTE, READER, Fixture, Transcript, TranscriptBase,
    edit, overlap_first_two_leads,
)


def setUpModule():
    Fixture.build()


def tearDownModule():
    Fixture.tmp.cleanup()


LEAD_KINDS = (INVESTIGATE, AREA_LEAD_AGENT)


def started(events, kinds=LEAD_KINDS, depth=None):
    return [e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") in kinds
            and (depth is None or e.get("spawn_depth") == depth)]


def leads_of(events):
    return started(events, LEAD_KINDS, 2)


def notification(events, task_id):
    return next(e for e in events if e.get("subtype") == "task_notification" and e["task_id"] == task_id)


def first_reader(events):
    return next(e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == READER)


# each: (name, change to the events, change to the parts or None); all find leads by depth, not by type, so they fit both shapes

def m_none(events):
    return events


def m_overlap(events):
    return overlap_first_two_leads(events)


def m_unfinished_lead(events):
    events.remove(notification(events, leads_of(events)[2]["task_id"]))
    return events


def m_reader_twice(events):
    reader = first_reader(events)
    dup = copy.deepcopy(reader)
    dup["task_id"] = reader["task_id"] + "dup"
    dup["tool_use_id"] = "toolu_" + dup["task_id"]
    note = copy.deepcopy(notification(events, reader["task_id"]))
    note["task_id"] = dup["task_id"]
    events[events.index(reader) + 1:events.index(reader) + 1] = [dup, note]
    return events


def m_file_with_no_reader(events):
    reader = first_reader(events)
    note = notification(events, reader["task_id"])
    events.remove(reader)
    events.remove(note)
    return events


def m_reader_never_completes(events):
    events.remove(notification(events, first_reader(events)["task_id"]))
    return events


def m_reader_outside(events):
    notification(events, first_reader(events)["task_id"])["summary"] = "Path: /elsewhere/nothing.md\nLines read: 1-1 of 1"
    return events


def m_reader_parent_unknown(events):
    for e in events:
        if e.get("subagent_type") == READER:
            e["parent_task_id"] = "someone-else"
    return events


def m_continue_edited(events):
    top = started(events, (INVESTIGATE,), 1)[1]
    top["prompt"] = top["prompt"].replace("Focus: none\n", "", 1)
    return events


def m_last_lead_unfinished_and_overlap(events):
    return m_unfinished_lead(m_overlap(events))


def p_drop_part_3(parts):
    return {k: v for k, v in parts.items() if k != "part-3.md"}


def p_part_2_failed(parts):
    return edit(parts, "part-2.md", "failed: 0;", "failed: 2;")


CHECKS = [
    ("proved run", m_none, None),
    ("two leads at once", m_overlap, None),
    ("a lead that never finished", m_unfinished_lead, None),
    ("a reader sent twice", m_reader_twice, None),
    ("a file with no reader", m_file_with_no_reader, None),
    ("a reader that never completes", m_reader_never_completes, None),
    ("a reader for a path outside the readable files", m_reader_outside, None),
    ("readers whose parent is unknown", m_reader_parent_unknown, None),
    ("the CONTINUE SWEEP comparison", m_continue_edited, None),
    ("the part-file count", m_none, p_drop_part_3),
    ("the part-file count with a missing part and a lead overlap", m_overlap, p_drop_part_3),
    ("a failed part with leads unfinished and at once", m_last_lead_unfinished_and_overlap, p_part_2_failed),
]


class Shapes(TranscriptBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.old = Transcript(cls.parts, lead_kind=INVESTIGATE).events
        cls.new = Transcript(cls.parts, lead_kind=AREA_LEAD_AGENT).events

    def old_events(self):
        return copy.deepcopy(self.old)

    def new_events(self):
        return copy.deepcopy(self.new)

    def both(self, change, parts_change=None):
        parts = parts_change(self.parts) if parts_change else self.parts
        return (self.run_t(change(self.old_events()), parts=parts),
                self.run_t(change(self.new_events()), parts=parts))


class SameRunTwoShapesTest(Shapes):
    def test_every_lead_reader_and_top_level_check_gives_the_same_verdict_exit_code_and_summary_in_both_shapes(self):
        for name, change, parts_change in CHECKS:
            with self.subTest(check=name):
                (old_code, old_out), (new_code, new_out) = self.both(change, parts_change)
                self.assertEqual(old_code, new_code, old_out + "\n---\n" + new_out)
                self.assertEqual(OLD_SHAPE_NOTE.sub("", old_out), new_out)
                # the old shape says so in one line and only that line; the new shape never does
                self.assertEqual(len(OLD_SHAPE_NOTE.findall(old_out)), 1, old_out)
                self.assertNotIn("area leads ran as", new_out)

    def test_the_two_shapes_do_not_pass_everything_the_checks_have_to_fail_in_both(self):
        # guards the table above: the broken runs really fail (exit 1) in both shapes, so equal output is not equal silence
        for name, change, parts_change in CHECKS:
            if name in ("proved run", "two leads at once", "a lead that never finished", "readers whose parent is unknown"):
                continue
            with self.subTest(check=name):
                (old_code, _o), (new_code, new_out) = self.both(change, parts_change)
                self.assertEqual((old_code, new_code), (1, 1), new_out)
                self.assertEqual(new_out.splitlines()[0], "LOOP FAILED")


class NewShapeCannotHideAFailureTest(Shapes):
    def test_an_area_lead_task_in_place_of_a_top_level_dispatch_is_not_one_and_the_run_fails(self):
        for which in (0, 1, 2):
            with self.subTest(top=which):
                events = self.new_events()
                started(events, (INVESTIGATE,), 1)[which]["subagent_type"] = AREA_LEAD_AGENT
                code, out = self.run_t(events)
                self.assertEqual(code, 1, out)
                self.assertRegex(out, r"transcript: 2 top-level investigate results, 3 part files")

    def test_an_area_lead_task_is_never_a_reader(self):
        events = self.new_events()
        first_reader(events)["subagent_type"] = AREA_LEAD_AGENT
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 readable files never had a reader dispatched")

    def test_an_area_lead_task_never_joins_the_top_level_dispatches_whatever_its_depth_or_prompt(self):
        for depth in (1, 2, 3, None):
            for prompt in ("Read the area.", "CONTINUE SWEEP\nProject: x", ""):
                with self.subTest(depth=depth, prompt=prompt[:10]):
                    events = self.new_events()
                    for e in started(events, (AREA_LEAD_AGENT,)):
                        e["prompt"] = prompt
                        if depth is None:
                            e.pop("spawn_depth")
                        else:
                            e["spawn_depth"] = depth
                    self.assertTranscriptProved(self.run_t(events))

    def test_readers_started_by_an_area_lead_count_like_readers_started_by_an_old_shape_lead(self):
        # a file read by a reader whose parent is an area-lead lead is read; take it away and the run fails the same way in both shapes
        for events, label in ((self.old_events(), "old"), (self.new_events(), "new")):
            with self.subTest(shape=label):
                reader = first_reader(events)
                parent = next(e for e in events if e.get("task_id") == reader["parent_task_id"])
                self.assertIn(parent["subagent_type"], LEAD_KINDS)
                note = notification(events, reader["task_id"])
                events.remove(reader)
                events.remove(note)
                self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 readable files never had a reader dispatched")

    def test_an_area_lead_run_with_no_lead_at_all_is_still_scored_on_its_readers(self):
        events = [e for e in self.new_events() if e.get("subagent_type") != AREA_LEAD_AGENT and e.get("task_id") not in
                  {l["task_id"] for l in started(self.new_events(), (AREA_LEAD_AGENT,))}]
        code, out = self.run_t(events)
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)
        self.assertNotIn("NOTE:", out)


class MixedShapesTest(Shapes):
    def mixed(self, pick):
        events = self.old_events()
        for i, lead in enumerate(leads_of(events)):
            if pick(i):
                lead["subagent_type"] = AREA_LEAD_AGENT
        return events

    def test_a_run_with_some_leads_each_way_is_proved_and_the_note_counts_only_the_old_ones(self):
        code, out = self.run_t(self.mixed(lambda i: i % 2 == 0))
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)
        self.assertIn("NOTE: transcript: 8 area leads ran as the-foundry:investigate", out.splitlines())
        self.assertEqual(OLD_SHAPE_NOTE.sub("", out), self.run_t(self.new_events())[1])

    def test_one_old_lead_among_new_ones_gives_the_note_with_a_count_of_one(self):
        code, out = self.run_t(self.mixed(lambda i: i != 4))
        self.assertEqual(code, 0, out)
        self.assertIn("NOTE: transcript: 1 area leads ran as the-foundry:investigate", out.splitlines())

    def test_an_old_lead_and_a_new_lead_running_at_once_print_the_at_once_note(self):
        events = overlap_first_two_leads(self.mixed(lambda i: i == 1))
        code, out = self.run_t(events)
        self.assertEqual(code, 0, out)
        self.assertIn("NOTE: transcript: area leads root and api-top were running at the same time", out.splitlines())
        self.assertIn("NOTE: transcript: 16 area leads ran as the-foundry:investigate", out.splitlines())

    def test_a_mixed_run_fails_where_the_pure_runs_fail(self):
        for change, parts_change in ((m_file_with_no_reader, None), (m_continue_edited, None), (m_none, p_drop_part_3)):
            with self.subTest(change=change.__name__):
                events = change(self.mixed(lambda i: i % 2 == 0))
                parts = parts_change(self.parts) if parts_change else self.parts
                code, out = self.run_t(events, parts=parts)
                pure_code, pure_out = self.run_t(change(self.new_events()), parts=parts)
                self.assertEqual(code, pure_code)
                self.assertEqual(OLD_SHAPE_NOTE.sub("", out), pure_out)


class OldRuleStillStandsTest(Shapes):
    def test_an_investigate_task_at_depth_one_whose_prompt_does_not_start_area_lead_is_a_top_level_dispatch(self):
        for prompt in ("Please act as a helper for the AREA LEAD later.", " AREA LEAD\nArea: x", "area lead\nArea: x", "Area: x\nAREA LEAD"):
            with self.subTest(prompt=prompt[:20]):
                events = self.old_events()
                extra = copy.deepcopy(started(events, (INVESTIGATE,), 1)[0])
                extra.update({"task_id": "tx1", "tool_use_id": "toolu_tx1", "prompt": prompt, "spawn_depth": 1})
                extra.pop("parent_task_id", None)
                events.append(extra)
                self.assertTranscriptFails(self.run_t(events), r"^transcript: top-level investigate dispatch 4 can't be compared: part-3\.md has no block")

    def test_an_investigate_task_at_depth_one_whose_prompt_starts_area_lead_is_a_lead_not_a_top_level_dispatch(self):
        events = self.old_events()
        extra = copy.deepcopy(started(events, (INVESTIGATE,), 1)[0])
        extra.update({"task_id": "tx1", "tool_use_id": "toolu_tx1", "prompt": "AREA LEAD\nArea: extra", "spawn_depth": 1})
        events.append(extra)
        code, out = self.run_t(events)
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)
        self.assertIn("NOTE: transcript: 18 area leads ran as the-foundry:investigate", out.splitlines())

    def test_an_investigate_task_deeper_than_one_is_a_lead_whatever_its_prompt(self):
        events = self.old_events()
        extra = copy.deepcopy(started(events, (INVESTIGATE,), 1)[0])
        extra.update({"task_id": "tx1", "tool_use_id": "toolu_tx1", "prompt": "not a lead prompt", "spawn_depth": 3})
        events.append(extra)
        code, out = self.run_t(events)
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)
        self.assertIn("NOTE: transcript: 18 area leads ran as the-foundry:investigate", out.splitlines())


class LookAlikeTypesTest(Shapes):
    def retyped(self, kind, shape="new", overlap=False):
        events = self.new_events() if shape == "new" else self.old_events()
        if overlap:
            events = overlap_first_two_leads(events)
        for e in started(events, LEAD_KINDS, 2):
            e["subagent_type"] = kind
        return events

    def test_a_lookalike_type_is_neither_a_lead_nor_a_top_level_dispatch_nor_a_reader(self):
        for kind in ("the-foundry:area-lead-2", "the-foundry:area-leads", "the-foundry:Area-Lead", "other:area-lead", "the-foundry:area-lead "):
            with self.subTest(kind=kind):
                code, out = self.run_t(self.retyped(kind))
                # nothing counted: the run is still scored on its readers and its top-level dispatches, and says nothing about leads
                self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)
                self.assertNotIn("area leads ran as", out)

    def test_a_lookalike_type_does_not_take_part_in_the_at_once_note(self):
        events = self.retyped("the-foundry:area-lead-2", overlap=True)
        self.assertNotIn("were running at the same time", self.run_t(events)[1])

    def test_the_bare_area_lead_name_of_a_manual_install_is_not_counted_as_a_lead(self):
        # FINDING (characterized, not endorsed): `area-lead` with no plugin prefix is ignored whole. A run whose leads carry the bare
        # name scores PROVED, prints no at-once NOTE for leads that overlap, and prints no NOTE saying which shape ran.
        events = self.retyped("area-lead", overlap=True)
        code, out = self.run_t(events)
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"), out)
        self.assertNotIn("NOTE:", out)
        prefixed = self.run_t(overlap_first_two_leads(self.new_events()))[1]
        self.assertIn("were running at the same time", prefixed)

    def test_a_bare_name_task_in_place_of_a_top_level_dispatch_is_ignored_and_the_run_fails_on_the_count(self):
        events = self.new_events()
        started(events, (INVESTIGATE,), 1)[2]["subagent_type"] = "area-lead"
        self.assertTranscriptFails(self.run_t(events), r"^transcript: 2 top-level investigate results, 3 part files")


if __name__ == "__main__":
    unittest.main()


# ---- Task 4 (AC-4): the restarted-lead allowance in the twice-read check --------------------------------------

import test_check_parts as tcp  # noqa: E402


def area_files(name):
    return [f for f in next(a for a in tcp.base_areas() if a.name == name).files if tcp.is_readable(f)]


class RestartBase(TranscriptBase):
    """Builds transcripts where a lead is started twice with one brief and second readers follow."""

    def restart(self, area="api-billing", listed=None, second=None, readers_parent="restart", prompt_edit=None,
                second_kind=INVESTIGATE, first_kind=None, extra_leads=0, events=None, base=90000):
        events = events if events is not None else self.events()
        first = next(e for e in events if e.get("subtype") == "task_started" and e.get("spawn_depth") == 2
                     and e.get("subagent_type") in LEAD_KINDS and ("Area: %s\n" % area) in e["prompt"])
        files = area_files(area)
        listed = files if listed is None else listed
        body = "\n".join("`%s/%s`" % (Fixture.repo, f) if f.startswith("api") else f for f in listed)
        first["prompt"] += "\nReader agent: the-foundry:file-reader\nFiles:\n" + body
        if first_kind:
            first["subagent_type"] = first_kind
        if prompt_edit is not None:
            first["prompt"] = prompt_edit(first["prompt"])   # both leads carry the edited text, so the prompts stay byte-identical
        prompt = first["prompt"]
        t = Transcript.__new__(Transcript)
        t.n, t.repo = base, str(Fixture.repo)
        ids = []
        for k in range(1 + extra_leads):
            lid = "l%d_%d" % (base, k)
            ids.append(lid)
            events.append(t.started(lid, second_kind, prompt, 2, first.get("parent_task_id"), "again"))
            events.append(t.notified(lid, "Area: %s\n..." % area))
        parent = {"restart": ids[0], "top": first.get("parent_task_id"), "first": first["task_id"]}.get(readers_parent, readers_parent)
        for f in (files if second is None else second):
            events.extend(t.reader(f, parent))
        return events


class AllowanceHoleTest(RestartBase):
    def test_a_second_reader_with_no_restarted_lead_still_fails(self):
        """AC-4: one lead lists the file, nobody restarted it, a stray second reader reads it."""
        events = self.restart(extra_leads=0)
        restart_lead = next(e for e in events if e.get("task_id") == "l90000_0")
        events = [e for e in events if e.get("task_id") != restart_lead["task_id"]]
        self.assertTranscriptFails(self.run_t(events), r"readable files had a reader dispatched more than once")

    def test_a_restart_of_a_restart_with_two_readers_each_still_fails(self):
        """AC-4: three leads with one brief; every file then has three readers."""
        events = self.restart(extra_leads=1)
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 95000, str(Fixture.repo)
        for f in area_files("api-billing"):
            events.extend(t.reader(f, "l90000_1"))
        out = self.assertTranscriptFails(self.run_t(events), r"\(3 times\)")
        self.assertNotIn("NOTE: transcript: area api-billing", out)

    def test_a_path_that_is_a_substring_of_a_listed_path_gets_no_allowance(self):
        """AC-4: the list holds api/billing/toll.py.bak and x/api/billing/toll.py, never toll.py itself."""
        files = area_files("api-billing")
        listed = [f for f in files if f != "api/billing/toll.py"] + ["api/billing/toll.py.bak", "x/api/billing/toll.py"]
        out = self.assertTranscriptFails(self.run_t(self.restart(listed=listed, second=["api/billing/toll.py"])),
                                         r"^transcript: 1 readable files had a reader dispatched more than once: api/billing/toll\.py \(2 times\)$")
        self.assertNotIn("was started twice", out)

    def test_a_path_named_after_the_blank_line_that_ends_the_list_gets_no_allowance(self):
        """AC-4: text after the list, even a line that is exactly the path, is not part of it."""
        files = area_files("api-billing")
        listed = [f for f in files if f != "api/billing/toll.py"]
        events = self.restart(listed=listed, second=["api/billing/toll.py"],
                              prompt_edit=lambda p: p)  # the listing is edited below, before the restart copies it
        for e in events:
            if e.get("subagent_type") in LEAD_KINDS and "Files:\n" in e.get("prompt", ""):
                e["prompt"] += "\n\napi/billing/toll.py\nSee api/billing/toll.py"
        self.assertTranscriptFails(self.run_t(events), r"api/billing/toll\.py \(2 times\)")

    def test_a_second_reader_started_by_the_top_level_is_allowed_today(self):
        """AC-4 finding: the allowance never looks at who started the second reader. This pins what the scorer does now:
        a restarted lead exists, yet the second readers have the top level as parent, and the run still proves."""
        out = self.assertTranscriptProved(self.run_t(self.restart(readers_parent="top")))
        self.assertIn("NOTE: transcript: area api-billing's lead was started twice; its %d files had a second set of readers"
                      % len(area_files("api-billing")), out.splitlines())


class ParserNeverRaisesTest(RestartBase):
    def check(self, prompt_edit, allowed, second=("api/billing/toll.py",)):
        events = self.restart(second=list(second), prompt_edit=prompt_edit, listed=["api/billing/toll.py"])
        code, out = self.run_t(events)
        self.assertNotIn("Traceback", out)
        self.assertIn(code, (0, 1), out)
        self.assertEqual("was started twice" in out, allowed, out)
        if not allowed:
            self.assertEqual(code, 1, out)
        return out

    def test_a_prompt_with_no_files_line_gets_no_allowance(self):
        self.check(lambda p: p.split("\nReader agent:")[0], False)

    def test_an_empty_files_list_gets_no_allowance(self):
        self.check(lambda p: p.split("Files:\n")[0] + "Files:\n\n", False)

    def test_files_given_inline_on_the_header_line_gets_no_allowance(self):
        self.check(lambda p: p.split("Files:\n")[0] + "Files: api/billing/toll.py\n", False)

    def test_a_prompt_with_no_area_line_gets_no_allowance(self):
        self.check(lambda p: p.replace("Area: api-billing\n", ""), False)

    def test_an_area_line_with_no_name_gets_no_allowance(self):
        self.check(lambda p: p.replace("Area: api-billing\n", "Area: \n"), False)

    def test_control_characters_and_a_huge_line_do_not_raise(self):
        self.check(lambda p: p + "\n\x00\x1b[31m\x07\x08﻿ " + "z" * 2000000, True)

    def test_a_non_string_prompt_does_not_raise_and_gets_no_allowance(self):
        events = self.restart(listed=["api/billing/toll.py"], second=["api/billing/toll.py"])
        for e in events:
            if e.get("subagent_type") in LEAD_KINDS and "Files:\n" in e.get("prompt", ""):
                e["prompt"] = 12345
        code, out = self.run_t(events)
        self.assertNotIn("Traceback", out)
        self.assertEqual(code, 1, out)
        self.assertNotIn("was started twice", out)

    def test_windows_line_endings_get_the_same_allowance(self):
        self.check(lambda p: p, True)  # baseline
        events = self.restart(listed=["api/billing/toll.py"], second=["api/billing/toll.py"])
        for e in events:
            if e.get("subagent_type") in LEAD_KINDS and "Files:\n" in e.get("prompt", ""):
                e["prompt"] = e["prompt"].replace("\n", "\r\n")
        code, out = self.run_t(events)
        self.assertNotIn("Traceback", out)
        self.assertEqual(code, 0, out)
        self.assertIn("NOTE: transcript: area api-billing's lead was started twice; its 1 files had a second set of readers", out.splitlines())

    def test_a_repeated_area_line_uses_one_name_and_a_repeated_files_line_does_not_raise(self):
        out = self.check(lambda p: p.replace("Area: api-billing\n", "Area: api-billing\nArea: other\n") + "\nFiles:\napi/billing/tow.py", True)
        self.assertIn("area api-billing's lead", out)


class LeadShapesAndNoteTest(RestartBase):
    def test_every_pair_of_lead_shapes_with_one_brief_gets_the_same_verdict_and_note(self):
        seen = {}
        for first in LEAD_KINDS:
            for second in LEAD_KINDS:
                events = self.restart(first_kind=first, second_kind=second)
                code, out = self.run_t(events)
                lines = [l for l in out.splitlines() if "ran as the-foundry:investigate" not in l]
                seen[(first, second)] = (code, lines)
        self.assertEqual(len(set(str(v) for v in seen.values())), 1, seen)
        code, lines = seen[(INVESTIGATE, AREA_LEAD_AGENT)]
        self.assertEqual(code, 0, lines)

    def test_the_old_shape_prompt_with_the_area_lead_prefix_is_found_at_depth_two_for_a_restart(self):
        events = self.restart(first_kind=INVESTIGATE, second_kind=AREA_LEAD_AGENT)
        self.assertEqual(self.run_t(events)[0], 0)

    def test_one_note_per_restarted_area_with_its_own_count_and_nothing_else_changes(self):
        base_code, base_out = self.run_t(self.events())
        events = self.restart("api-billing", events=self.events())
        events = self.restart("cli", events=events, base=96000)
        code, out = self.run_t(events)
        lines = out.splitlines()
        notes = [l for l in lines if "was started twice" in l]
        self.assertEqual(sorted(notes), sorted([
            "NOTE: transcript: area api-billing's lead was started twice; its %d files had a second set of readers" % len(area_files("api-billing")),
            "NOTE: transcript: area cli's lead was started twice; its %d files had a second set of readers" % len(area_files("cli")),
        ]))
        self.assertEqual((code, lines[0]), (base_code, "LOOP PROVED"))
        self.assertFalse([l for l in lines if l.startswith("transcript:")], out)
        rest = [l for l in lines if "was started twice" not in l and "area leads ran as" not in l]  # two more leads ran, so that count moves
        self.assertEqual(rest, [l for l in base_out.splitlines() if "area leads ran as" not in l])
