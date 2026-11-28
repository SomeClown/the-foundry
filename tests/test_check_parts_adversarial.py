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
    # the brief's Read line is the dispatch and wins over the summary, so the reader is sent outside in its brief (summary kept in step)
    reader = first_reader(events)
    reader["prompt"] = reader["prompt"].replace(reader["prompt"].split("`")[1], "/elsewhere/nothing.md", 1)
    notification(events, reader["task_id"])["summary"] = "Path: /elsewhere/nothing.md\nLines read: 1-1 of 1"
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


# ---- The brief's Read line wins over the reader's summary (tuning round) ---------------------------------------
# A reader's dispatch is the brief's first line, Read `<path>`; the summary's Path line is read only when the brief
# has none. What the check is for: every readable file had a reader dispatched, once. Nothing here restates the
# pattern; each test sends a wrong run and asks whether it still fails (or pins an accepted limit, named _today).

class BriefReadLineTest(TranscriptBase):
    FILE = "cli/cmd_booth.py"
    OTHER = "api/app.py"

    def change(self, rel, prompt=None, summary=None, events=None):
        events = events if events is not None else self.events()
        tid = tcp.find_reader(events, rel)[0]
        for e in events:
            if e.get("task_id") == tid:
                if e["subtype"] == "task_started" and prompt is not None:
                    e["prompt"] = prompt
                if e["subtype"] == "task_notification" and summary is not None:
                    e["summary"] = summary
        return events

    def failures(self, events):
        code, out = self.run_t(events)
        self.assertEqual((code, out.splitlines()[0]), (1, "LOOP FAILED"), out)
        return self.failure_lines(out)

    def test_a_brief_naming_a_file_outside_the_repo_fails_even_when_the_summary_names_the_right_file(self):
        events = self.change(self.FILE, prompt="Read `/etc/passwd`\nProject: tollway, a toy.")
        lines = self.failures(events)
        self.assertTrue(any("never had a reader dispatched: cli/cmd_booth.py" in l for l in lines), lines)
        self.assertTrue(any("outside the readable files: /etc/passwd" in l for l in lines), lines)

    def test_a_reader_briefed_for_one_file_and_reporting_another_readable_one_is_counted_for_the_brief_today(self):
        # accepted limit: the dispatch is what the check is for, and nothing compares it with the summary. The file it
        # reports is dispatched on its own anyway; were it not, that file would fail as never dispatched (next test).
        events = self.change(self.FILE, prompt="Read `%s`\nProject: tollway, a toy." % self.FILE, summary="Path: %s\nLines read: 1-5 of 5" % self.OTHER)
        self.assertTranscriptProved(self.run_t(events))

    def test_a_file_only_a_summary_reports_having_read_is_still_never_dispatched(self):
        events = self.change(self.FILE, prompt="Read `%s`\nx" % self.FILE, summary="Path: %s\nLines read: 1-5 of 5" % self.OTHER)
        for tid in tcp.find_reader(events, self.OTHER):
            events = tcp.without_task(events, tid)
        self.assertTrue(any("never had a reader dispatched: api/app.py" in l for l in self.failures(events)))

    def test_a_brief_with_two_read_lines_is_counted_for_the_first_only_so_the_second_file_still_needs_its_own_reader(self):
        events = self.change(self.FILE, prompt="Read `%s`\nRead `%s`\nProject: tollway, a toy." % (self.FILE, self.OTHER))
        for tid in tcp.find_reader(events, self.OTHER):
            events = tcp.without_task(events, tid)
        lines = self.failures(events)
        self.assertEqual([l for l in lines if "never had a reader" in l], ["transcript: 1 readable files never had a reader dispatched: api/app.py"])

    def test_two_section_readers_of_one_file_are_still_dispatched_more_than_once(self):
        # the scorer read a section reader's summary path as the file before this tuning, so two of them counted twice then too
        events = self.events()
        tid = tcp.find_reader(events, self.FILE)[0]
        idx = [k for k, e in enumerate(events) if e.get("task_id") == tid]
        twin = copy.deepcopy([events[k] for k in idx])
        for e in twin:
            e["task_id"] += "s"
            e["tool_use_id"] += "s"
        for e in events:
            if e.get("task_id") == tid and e["subtype"] == "task_started":
                e["prompt"] = "Read `%s` lines 1 to 30\nProject: tollway, a toy." % self.FILE
        for e in twin:
            if e["subtype"] == "task_started":
                e["prompt"] = "Read `%s` lines 31 to 62\nProject: tollway, a toy." % self.FILE
        events[idx[-1] + 1:idx[-1] + 1] = twin
        self.assertIn("transcript: 1 readable files had a reader dispatched more than once: cli/cmd_booth.py (2 times)", self.failures(events))

    def test_a_read_line_path_with_a_space_inside_the_backticks_is_counted_for_the_file(self):
        events = self.change(self.FILE, prompt="Read `%s `\nx" % self.FILE, summary="nothing useful")
        self.assertTranscriptProved(self.run_t(events))

    def test_a_read_line_with_no_backticks_is_not_a_dispatch_so_a_summary_outside_the_repo_fails_it(self):
        events = self.change(self.FILE, prompt="Read %s\nx" % self.FILE, summary="Path: /elsewhere/nothing.md\nLines read: 1-1 of 1")
        lines = self.failures(events)
        self.assertTrue(any("never had a reader dispatched: cli/cmd_booth.py" in l for l in lines), lines)
        self.assertTrue(any("outside the readable files: /elsewhere/nothing.md" in l for l in lines), lines)

    def test_a_read_line_that_is_not_the_first_line_is_not_a_dispatch(self):
        events = self.change(self.FILE, prompt="Please start.\nRead `%s`\nx" % self.FILE, summary="Path: /elsewhere/nothing.md\nLines read: 1-1 of 1")
        lines = self.failures(events)
        self.assertTrue(any("outside the readable files: /elsewhere/nothing.md" in l for l in lines), lines)

    def test_a_prompt_that_is_not_a_string_is_a_brief_with_no_read_line_so_the_summary_path_line_counts(self):
        for bad in (5, ["Read `%s`" % self.FILE], {"a": 1}):
            with self.subTest(prompt=bad):
                self.assertTranscriptProved(self.run_t(self.change(self.FILE, prompt=bad)))

    def test_a_prompt_that_is_not_a_string_and_a_summary_with_no_path_line_names_no_path(self):
        for bad in (5, ["Read `%s`" % self.FILE], {"a": 1}):
            with self.subTest(prompt=bad):
                events = self.change(self.FILE, prompt=bad, summary="nothing useful")
                tid = next(e["task_id"] for e in events if e.get("subtype") == "task_started" and e.get("prompt") == bad)
                self.assertTranscriptFails(self.run_t(events), r"^transcript: 1 reader tasks name no path \(task ids %s\)$" % tid)

    def test_a_prompt_of_none_or_empty_falls_back_on_the_summary(self):
        for bad in (None, ""):
            with self.subTest(prompt=bad):
                self.assertTranscriptProved(self.run_t(self.change(self.FILE, prompt=bad)))


# ---- Fix batch 1 (D1, D2): odd Files: lines, and non-string fields ---------------------------------------------------
# Each test sends a restarted lead whose Files: list is in an odd shape, with a second reader for one file, and asks
# whether the scorer allows it (right run: LOOP PROVED with the NOTE) or fails it (wrong run: LOOP FAILED), and never raises.

TOLL = "api/billing/toll.py"
TOW = "api/billing/tow.py"


def listing(body):
    """A prompt edit: the Files: list is replaced by the body (the restart copies the edited text to both leads)."""
    return lambda p: p.split("Files:\n")[0] + "Files:\n" + body


class FilesLineShapesTest(RestartBase):
    def run_shape(self, body, second=(TOLL,)):
        events = self.restart(listed=[TOLL], second=list(second), prompt_edit=listing(body))
        code, out = self.run_t(events)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("CAN'T CHECK", out)
        self.assertIn(code, (0, 1), out)
        return code, out

    def path(self, rel=TOLL):
        return "%s/%s" % (Fixture.repo, rel)

    def allowed(self, body, **kw):
        code, out = self.run_shape(body, **kw)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines()[0], "LOOP PROVED")
        self.assertIn("lead was started twice", out)

    def refused(self, body, **kw):
        code, out = self.run_shape(body, **kw)
        self.assertEqual(code, 1, out)
        self.assertNotIn("LOOP PROVED", out)
        self.assertNotIn("was started twice", out)

    def test_each_bullet_mark_gets_the_allowance_with_and_without_backticks(self):
        for mark in ("-", "*", "+"):
            for fmt in ("%s", "`%s`"):
                with self.subTest(mark=mark, fmt=fmt):
                    self.allowed("%s %s" % (mark, fmt % self.path()))

    def test_an_indented_or_tabbed_bullet_gets_the_allowance(self):
        for lead in ("  - ", "\t* ", "    + "):
            with self.subTest(lead=repr(lead)):
                self.allowed(lead + self.path())
                self.allowed(lead + "`%s`" % self.path())

    def test_bold_around_the_backticks_gets_the_allowance(self):
        self.allowed("- **`%s`**" % self.path())

    def test_two_backticked_paths_on_a_line_take_the_first_and_the_second_gets_nothing(self):
        self.allowed("- `%s` (was `%s`)" % (self.path(TOLL), self.path(TOW)))
        self.refused("- `%s` (was `%s`)" % (self.path(TOW), self.path(TOLL)))

    def test_a_path_named_only_in_a_note_gets_no_allowance(self):
        self.refused("- `%s` (replaces `%s`)" % (self.path(TOW), self.path(TOLL)))
        self.refused("(see %s)\n- `%s`" % (self.path(TOLL), self.path(TOW)))

    def test_a_line_that_is_only_a_note_is_no_path_and_does_not_end_the_list(self):
        self.allowed("(none yet)\n`%s`" % self.path())
        self.refused("(%s)" % self.path())

    def test_an_empty_line_ends_the_list(self):
        self.refused("\n`%s`" % self.path())
        self.refused("`%s`\n\n`%s`" % (self.path(TOW), self.path(TOLL)))

    def test_a_path_with_spaces_in_backticks_is_read_whole_and_does_not_raise(self):
        self.refused("- `%s`" % self.path("api/billing/toll file.py"))
        self.refused("- %s" % self.path("api/billing/toll file.py"))

    def test_a_path_in_backticks_with_a_trailing_note_inside_the_line_gets_the_allowance(self):
        self.allowed("`%s` - billing tolls, 40 lines" % self.path())

    def test_empty_backticks_and_stray_marks_do_not_raise_and_get_nothing(self):
        for body in ("``", "-", "- ", "* `", "`", "- ``\n- ` `", "\x00", "-\t"):
            with self.subTest(body=repr(body)):
                self.refused(body)

    def test_today_an_unbackticked_path_with_a_trailing_note_or_a_numbered_item_gets_no_allowance(self):
        """Accepted limit: a right run in these shapes fails (the scorer errs to failing). The lead's template says backticks."""
        self.refused("- %s (a note)" % self.path())
        self.refused("1. %s" % self.path())

    def test_a_second_reader_for_a_file_the_odd_list_does_not_name_still_fails_the_run(self):
        for body in ("- `%s`" % self.path(TOW), "* %s" % self.path(TOW), "+ `%s` `%s`" % (self.path(TOW), self.path(TOLL)),
                     "Files: `%s`" % self.path(TOLL).replace(TOLL, "x/%s" % TOLL)):
            with self.subTest(body=body[:40]):
                self.refused(body)


class NonStringFieldsTest(TranscriptBase):
    """D2: a value that is not a string, in a field the transcript check reads, is empty or ignored, never a crash."""

    ODD = (None, 5, 1.5, True, [], {}, ["x"], {"a": 1})

    def first(self, kind, subtype="task_started"):
        return next(e for e in self.events_ref if e.get("subtype") == subtype and e.get("subagent_type") == kind)

    def run_with(self, change):
        events = self.events()
        self.events_ref = events
        change(events)
        return self.run_t(events)

    def assertNoCrash(self, code_out, what):
        code, out = code_out
        self.assertNotIn("Traceback", out, what)
        self.assertNotIn("internal error", out, what)
        self.assertIn(code, (0, 1), "%s: %s" % (what, out[:200]))

    def test_every_field_the_check_reads_from_a_reader_or_a_lead_may_be_any_json_value(self):
        for kind in (READER, INVESTIGATE):
            for field in ("prompt", "subagent_type", "spawn_depth", "parent_task_id", "tool_use_id"):
                for odd in self.ODD:
                    if field in ("tool_use_id",) and isinstance(odd, (list, dict)):
                        continue  # unhashable ids are a separate finding, below
                    with self.subTest(kind=kind, field=field, value=repr(odd)):
                        def change(events, kind=kind, field=field, odd=odd):
                            self.first(kind)[field] = odd
                        self.assertNoCrash(self.run_with(change), field)

    def test_every_field_the_check_reads_from_a_notification_may_be_any_json_value(self):
        for field in ("status", "summary", "subtype", "usage"):
            for odd in self.ODD:
                with self.subTest(field=field, value=repr(odd)):
                    def change(events, field=field, odd=odd):
                        note = next(e for e in events if e.get("subtype") == "task_notification")
                        note[field] = odd
                    self.assertNoCrash(self.run_with(change), field)

    def test_a_reader_that_never_completes_because_its_status_is_not_a_string_is_not_proved(self):
        for odd in self.ODD:
            with self.subTest(value=repr(odd)):
                def change(events, odd=odd):
                    reader = next(e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == READER)
                    note = next(e for e in events if e.get("subtype") == "task_notification" and e["task_id"] == reader["task_id"])
                    note["status"] = odd
                code, out = self.run_with(change)
                self.assertEqual(code, 1, out)
                self.assertRegex(out, r"never completed")

    def test_a_readable_files_reader_whose_type_is_not_a_string_is_not_counted(self):
        for odd in self.ODD:
            with self.subTest(value=repr(odd)):
                def change(events, odd=odd):
                    reader = next(e for e in events if e.get("subtype") == "task_started" and e.get("subagent_type") == READER)
                    reader["subagent_type"] = odd
                code, out = self.run_with(change)
                self.assertEqual(code, 1, out)
                self.assertRegex(out, r"never had a reader dispatched")

    def assertCantCheckNotProved(self, code_out, what):
        """The scorer's stated answer to a transcript it can't read: exit 2 and a CAN'T CHECK line, never LOOP PROVED."""
        code, out = code_out
        self.assertNotIn("Traceback", out, what)
        self.assertNotIn("LOOP PROVED", out, what)
        self.assertIn(code, (1, 2), "%s: %s" % (what, out[:200]))
        if code == 2:
            self.assertTrue(out.startswith("CAN'T CHECK"), out[:200])

    # The next three are accepted limits. Ruled by the session, 2026-11-27, fix batch 1: exit 2 with `CAN'T CHECK:
    # internal error` is the scorer's stated answer to a transcript it can't read, and it never scores such a run as proved.

    def test_today_the_text_of_a_tool_result_block_that_is_not_a_string_is_cant_check(self):
        for odd in self.ODD:
            with self.subTest(value=repr(odd)):
                def change(events, odd=odd):
                    for e in events:
                        content = (e.get("message") or {}).get("content") if isinstance(e.get("message"), dict) else None
                        for block in content if isinstance(content, list) else []:
                            if isinstance(block, dict) and block.get("type") == "tool_result" and isinstance(block.get("content"), list):
                                for b in block["content"]:
                                    if isinstance(b, dict) and "text" in b:
                                        b["text"] = odd
                self.assertCantCheckNotProved(self.run_with(change), "text")

    def test_today_a_task_id_or_tool_use_id_that_is_a_list_or_an_object_is_cant_check(self):
        for field in ("task_id", "tool_use_id"):
            for odd in ([], {}, ["x"], {"a": 1}):
                for kind in (READER, INVESTIGATE):
                    with self.subTest(field=field, kind=kind, value=repr(odd)):
                        def change(events, field=field, odd=odd, kind=kind):
                            self.first(kind)[field] = odd
                        if (field, kind) == ("tool_use_id", READER):
                            # the check never reads a reader's tool_use_id, so the run is still scored
                            self.assertNoCrash(self.run_with(change), field)
                        else:
                            self.assertCantCheckNotProved(self.run_with(change), field)

    def test_today_a_tool_result_whose_tool_use_id_is_a_list_is_cant_check(self):
        def change(events):
            for e in events:
                content = (e.get("message") or {}).get("content") if isinstance(e.get("message"), dict) else None
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        block["tool_use_id"] = ["x"]
        self.assertCantCheckNotProved(self.run_with(change), "tool_use_id")


class LeadWithNoTypeTest(TranscriptBase):
    def test_today_a_lead_whose_type_is_not_a_string_is_the_same_as_a_lead_that_never_ran_and_the_run_still_proves(self):
        """Accepted limit: the scorer counts what the readers did, not that every area had a lead. A lead dropped from the
        transcript, or one whose type is None or a number, gives LOOP PROVED with a NOTE that fewer leads ran."""
        for odd in (None, 5, [], {}):
            with self.subTest(value=repr(odd)):
                events = self.events()
                lead = next(e for e in events if e.get("subtype") == "task_started" and e.get("spawn_depth") == 2
                            and e.get("subagent_type") == INVESTIGATE)
                lead["subagent_type"] = odd
                code, out = self.run_t(events)
                self.assertEqual(code, 0, out)
                self.assertIn("NOTE: transcript: 16 area leads ran as the-foundry:investigate", out)


# ---- Tasks 1 and 2 of the steadier-runs batch (AC-3, AC-4) -----------------------------------------------------------

import importlib.util  # noqa: E402
import re  # noqa: E402


def load_scorer():
    spec = importlib.util.spec_from_file_location("check_parts_steadier_adv", str(tcp.SCRIPT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ZERO_LINE = "SWEEP IN PARTS: 0 areas not read\n"
AREA_LINE = "- api-billing: `api/billing/` (3 files)"
NOT_READ_ZERO = "Areas not read: 0 areas, 0 files; see SWEEP IN PARTS at the top."


class LastPartBlockLinesTest(tcp.Base):
    """AC-3: a last part says 0 areas not read and carries nothing of the block under that line."""

    def setUp(self):
        self.parts = tcp.build_parts(tcp.base_areas())

    def under(self, stray, blank=False):
        return tcp.edit(self.parts, "part-3.md", ZERO_LINE, ZERO_LINE + ("\n" if blank else "") + stray + "\n")

    LINES = (
        ("the To read the rest sentence", tcp.CONTINUE),
        ("a short To read the rest", "To read the rest, dispatch again."),
        ("Project", "Project: A toll-road back office, a fixture repo."),
        ("Focus", "Focus: none"),
        ("Environment", "Environment: use the git wrapper ./bin/git"),
        ("Instructions", "Instructions: read it all."),
        ("an Areas not read list", "Areas not read:\n" + AREA_LINE),
        ("the Areas not read header alone", "Areas not read:"),
        ("END OF BLOCK", "END OF BLOCK"),
    )

    def test_each_block_line_under_the_zero_line_of_a_last_part_fails(self):
        """AC-3."""
        for label, stray in self.LINES:
            with self.subTest(line=label):
                self.assertFails(self.under(stray), r"^part-3\.md: the last part says 0 areas not read, so nothing may sit under the line")

    def test_each_block_line_after_a_blank_line_under_the_zero_line_fails(self):
        """AC-3: the scorer looks at the next non-blank line, so a blank line in between hides nothing."""
        for label, stray in self.LINES:
            with self.subTest(line=label):
                self.assertFails(self.under(stray, blank=True), r"part-3\.md: the last part says 0 areas not read")

    def test_the_whole_block_pasted_under_the_zero_line_fails(self):
        """AC-3."""
        block = "\n".join([tcp.CONTINUE, "Project: x", "Focus: none", "Environment: none", "Instructions: none", "Areas not read:", AREA_LINE, "END OF BLOCK"])
        self.assertFails(self.under(block), r"part-3\.md: the last part says 0 areas not read")

    def test_a_right_last_part_whose_coverage_says_zero_areas_not_read_is_proved(self):
        """AC-3: the Coverage line the text asks of a last part must not fail on that line."""
        parts = tcp.edit(self.parts, "part-3.md", "\n" + tcp.WHOLE_LATER, "\n" + NOT_READ_ZERO + "\n" + tcp.WHOLE_LATER)
        out = self.assertProved(parts)
        self.assertNotIn("Areas not read", out)

    def test_the_same_coverage_line_as_a_bullet_is_proved(self):
        """AC-3."""
        parts = tcp.edit(self.parts, "part-3.md", "\n" + tcp.WHOLE_LATER, "\n- " + NOT_READ_ZERO + "\n" + tcp.WHOLE_LATER)
        self.assertProved(parts)

    def test_a_coverage_zero_line_with_a_wrong_number_fails(self):
        """AC-3: a last part that says 0 areas holds 0 of them, so 1 areas or 5 files in Coverage is a mismatch."""
        for wrong in ("Areas not read: 1 areas, 0 files; see SWEEP IN PARTS at the top.", "Areas not read: 0 areas, 5 files; see SWEEP IN PARTS at the top."):
            with self.subTest(line=wrong):
                parts = tcp.edit(self.parts, "part-3.md", "\n" + tcp.WHOLE_LATER, "\n" + wrong + "\n" + tcp.WHOLE_LATER)
                self.assertFails(parts, r"part-3\.md: Coverage says \d+ areas, \d+ files not read; the block holds 0 areas, 0 files")

    def test_today_a_last_part_whose_coverage_drops_the_zero_line_is_proved(self):
        """Accepted limit, today's behaviour: the text asks every last part for the Coverage zero line, but the scorer
        requires the line only where areas are left (n > 0). Task 1's brief puts no such check on the scorer."""
        self.assertNotIn(NOT_READ_ZERO, self.parts["part-3.md"])
        self.assertProved(self.parts)

    def test_the_flag_line_above_the_sweep_line_fails_the_flag_and_still_checks_the_block_lines(self):
        """AC-3: NOT A PER-FILE READ on line 1 is a flagged single-agent read; a Focus line under the zero line still fails."""
        flagged = tcp.edit(self.parts, "part-3.md", ZERO_LINE, "NOT A PER-FILE READ\n" + ZERO_LINE)
        self.assertFails(flagged, r"^part-3\.md: line 1 is NOT A PER-FILE READ")
        both = tcp.edit(flagged, "part-3.md", ZERO_LINE, ZERO_LINE + "Focus: x\n")
        out = self.assertFails(both, r"^part-3\.md: line 1 is NOT A PER-FILE READ", r"part-3\.md: the last part says 0 areas not read")
        self.assertNotIn("Traceback", out)

    def test_a_blank_line_before_the_zero_line_is_not_a_failure_and_a_stray_line_under_it_still_is(self):
        """AC-3."""
        self.assertProved(tcp.edit(self.parts, "part-3.md", ZERO_LINE, "\n\n" + ZERO_LINE))
        self.assertFails(tcp.edit(self.parts, "part-3.md", ZERO_LINE, "\n\n" + ZERO_LINE + "Environment: x\n"), r"the last part says 0 areas not read")

    def test_today_a_block_line_that_is_not_the_next_non_blank_line_goes_unseen(self):
        """Accepted limit, today's behaviour: only the next non-blank line under the zero line is looked at. END OF BLOCK
        after the report's heading, an indented Project line, or a bullet, a lowercase or a backticked block line is not
        compared with anything. The brief lists the start of each line, not a search of the whole part."""
        cases = {
            "after the report heading": tcp.edit(self.parts, "part-3.md", "# Investigation report (part 3)\n", "# Investigation report (part 3)\nEND OF BLOCK\n"),
            "indented Project": self.under("  Project: x"),
            "bulleted Focus": self.under("- Focus: x"),
            "lowercase environment": self.under("environment: x"),
            "backticked Instructions": self.under("`Instructions: x`"),
        }
        for label, parts in cases.items():
            with self.subTest(case=label):
                code, out = tcp.run_script(parts)
                self.assertNotRegex(out, r"the last part says 0 areas not read")
                self.assertNotIn("Traceback", out)


class InProcessSecondReaderTest(unittest.TestCase):
    """AC-4: the allowance, called directly, so a path or a count the fixture can't hold can be tried. It never raises."""

    REPO = "/repo"

    @classmethod
    def setUpClass(cls):
        cls.mod = load_scorer()

    def score(self, tracked, infos, readers, leads=()):
        """Runs check_transcript on a hand-made transcript; returns (fails, notes). readers: relative paths, one task each."""
        events, n = [(0, {"type": "system", "subtype": "init", "cwd": self.REPO})], 0
        for rel in readers:
            n += 1
            tid = "r%d" % n
            events.append((n, {"type": "system", "subtype": "task_started", "task_id": tid, "subagent_type": READER, "spawn_depth": 3,
                               "prompt": "Read `%s/%s`.\nProject: x\n" % (self.REPO, rel)}))
            events.append((n, {"type": "system", "subtype": "task_notification", "task_id": tid, "status": "completed", "summary": "Path: x"}))
        for prompt in leads:
            n += 1
            tid = "l%d" % n
            events.append((n, {"type": "system", "subtype": "task_started", "task_id": tid, "subagent_type": AREA_LEAD_AGENT, "spawn_depth": 2, "prompt": prompt}))
            events.append((n, {"type": "system", "subtype": "task_notification", "task_id": tid, "status": "completed", "summary": "done"}))
        fails, notes = [], []
        layout = {"file_skips": {}, "skipped_whole": {}}
        self.mod.check_transcript(events, self.REPO, tracked, layout, infos, fails, notes)
        return fails, notes

    def part(self, name, files, redispatched=None):
        info = {"name": name, "lines": [], "shape": None, "files": set(f.encode("utf-8") if isinstance(f, str) else f for f in files)}
        if redispatched is not None:
            info["redispatched"] = redispatched
        return info

    def twice_lines(self, fails):
        return [f for f in fails if "had a reader dispatched more than once" in f]

    def test_a_count_equal_to_the_twice_read_files_passes_and_one_less_fails(self):
        """AC-4: the boundary is 'at most', per part."""
        files = ["a.py", "b.py", "c.py"]
        tracked = [f.encode() for f in files]
        readers = files + files
        fails, notes = self.score(tracked, [self.part("part-1.md", files, 3)], readers)
        self.assertEqual(self.twice_lines(fails), [])
        self.assertEqual([n for n in notes if "second reader" in n],
                         ["NOTE: transcript: part-1.md: 3 readable files had a second reader, within its re-dispatched count of 3: a.py, b.py, c.py"])
        fails, notes = self.score(tracked, [self.part("part-1.md", files, 2)], readers)
        self.assertEqual(len(self.twice_lines(fails)), 1)
        self.assertIn("3 readable files had a reader dispatched more than once", self.twice_lines(fails)[0])
        self.assertEqual([n for n in notes if "second reader" in n], [])

    def test_a_count_of_two_does_not_cover_a_file_read_three_times(self):
        """AC-4: three readers fail whatever the count."""
        tracked = [b"a.py", b"b.py"]
        fails, notes = self.score(tracked, [self.part("part-1.md", ["a.py", "b.py"], 2)], ["a.py", "a.py", "a.py", "b.py", "b.py"])
        line = self.twice_lines(fails)
        self.assertEqual(len(line), 1, fails)
        self.assertIn("a.py (3 times)", line[0])
        self.assertNotIn("b.py", line[0], "the file with two readers is within the count and is not named")

    def test_a_file_three_times_read_does_not_use_up_the_count_of_a_file_read_twice(self):
        """AC-4: a.py (3 readers) fails; b.py (2 readers) is covered by the part's 1."""
        tracked = [b"a.py", b"b.py"]
        fails, notes = self.score(tracked, [self.part("part-1.md", ["a.py", "b.py"], 1)], ["a.py", "a.py", "a.py", "b.py", "b.py"])
        self.assertEqual(len(self.twice_lines(fails)), 1)
        self.assertIn("1 readable files had a reader dispatched more than once: a.py (3 times)", fails[0])
        self.assertTrue([n for n in notes if "part-1.md: 1 readable files had a second reader" in n])

    def test_a_file_in_no_part_gets_no_allowance(self):
        """AC-4."""
        fails, notes = self.score([b"a.py", b"b.py"], [self.part("part-1.md", ["a.py"], 9), self.part("part-2.md", [], 9)], ["a.py", "b.py", "b.py"])
        self.assertIn("b.py (2 times)", self.twice_lines(fails)[0])
        self.assertEqual(self.twice_lines(fails)[0].count("b.py"), 1)
        self.assertFalse([n for n in notes if "b.py" in n])

    def test_a_count_in_the_wrong_part_gives_no_allowance(self):
        """AC-4: the count of a part covers only the files that part holds, so a 9 in part 2 does not cover part 1's file."""
        fails, notes = self.score([b"a.py", b"b.py"], [self.part("part-1.md", ["a.py"], 0), self.part("part-2.md", ["b.py"], 9)], ["a.py", "a.py", "b.py"])
        self.assertIn("a.py (2 times)", self.twice_lines(fails)[0])
        self.assertEqual([n for n in notes if "second reader" in n], [])
        fails, notes = self.score([b"a.py", b"b.py"], [self.part("part-1.md", ["a.py"], 9), self.part("part-2.md", ["b.py"], 0)], ["a.py", "a.py", "b.py", "b.py"])
        self.assertIn("1 readable files had a reader dispatched more than once: b.py (2 times)", self.twice_lines(fails)[0])

    def test_each_part_is_judged_on_its_own_count_and_each_gets_its_own_note_in_part_order(self):
        """AC-4."""
        infos = [self.part("part-2.md", ["b.py"], 1), self.part("part-1.md", ["a.py"], 1)]
        fails, notes = self.score([b"a.py", b"b.py"], infos, ["a.py", "a.py", "b.py", "b.py"])
        self.assertEqual(self.twice_lines(fails), [])
        got = [n for n in notes if "second reader" in n]
        self.assertEqual(got, sorted(got))
        self.assertEqual(len(got), 2)

    def test_a_part_with_no_redispatched_key_gives_no_allowance_and_no_exception(self):
        """AC-4: the key is missing from a part whose counts line wasn't read."""
        fails, notes = self.score([b"a.py"], [self.part("part-1.md", ["a.py"], None)], ["a.py", "a.py"])
        self.assertEqual(len(self.twice_lines(fails)), 1)

    def test_a_huge_count_covers_a_file_and_does_not_raise(self):
        """AC-4."""
        fails, notes = self.score([b"a.py"], [self.part("part-1.md", ["a.py"], 10 ** 40)], ["a.py", "a.py"])
        self.assertEqual(self.twice_lines(fails), [])
        self.assertTrue([n for n in notes if "within its re-dispatched count of %d" % 10 ** 40 in n], notes)

    def test_a_non_ascii_path_gets_the_allowance_and_is_named_in_the_note(self):
        """AC-4: the scorer compares bytes, so a UTF-8 name must find its part."""
        name = "déjà/テスト ☃.py"
        fails, notes = self.score([name.encode("utf-8")], [self.part("part-1.md", [name], 1)], [name, name])
        self.assertEqual(self.twice_lines(fails), [])
        self.assertTrue([n for n in notes if n.endswith(": " + name)], notes)

    def test_a_non_ascii_path_over_the_count_fails_with_its_name(self):
        """AC-4."""
        name = "über/é.py"
        fails, notes = self.score([name.encode("utf-8")], [self.part("part-1.md", [name], 0)], [name, name])
        self.assertIn("%s (2 times)" % name, self.twice_lines(fails)[0])

    def test_today_a_tracked_path_that_is_not_utf8_gets_no_allowance_and_does_not_raise(self):
        """Accepted limit, today's behaviour: the readable set is decoded with replacement characters, so a name that is
        not UTF-8 never matches the bytes the part holds. It fails as before; it must not raise."""
        raw = b"caf\xe9.py"
        shown = raw.decode("utf-8", "replace")
        fails, notes = self.score([raw], [self.part("part-1.md", [raw], 5)], [shown, shown])
        self.assertEqual(len(self.twice_lines(fails)), 1, fails)
        self.assertEqual([n for n in notes if "second reader" in n], [])

    def test_today_a_file_that_two_parts_hold_is_judged_by_the_first_part_in_the_list(self):
        """Accepted limit, today's behaviour: a file in two parts' sets belongs to the first part found. (That is a failure
        elsewhere, in the area checks; this pins only which count the allowance reads.)"""
        infos = [self.part("part-1.md", ["a.py"], 0), self.part("part-2.md", ["a.py"], 1)]
        fails, notes = self.score([b"a.py"], infos, ["a.py", "a.py"])
        self.assertEqual(len(self.twice_lines(fails)), 1)
        infos.reverse()
        fails, notes = self.score([b"a.py"], infos, ["a.py", "a.py"])
        self.assertEqual(self.twice_lines(fails), [])

    def lead_prompt(self, rel_files, area="x"):
        return "AREA LEAD\nArea: %s\nProject: p\nFiles:\n%s\n" % (area, "\n".join("`%s/%s`" % (self.REPO, f) for f in rel_files))

    def test_a_restart_that_explains_two_files_leaves_the_count_for_a_third(self):
        """AC-4: a and b are explained by a restarted lead; c is covered by the part's 1."""
        files = ["a.py", "b.py", "c.py"]
        prompt = self.lead_prompt(["a.py", "b.py"])
        fails, notes = self.score([f.encode() for f in files], [self.part("part-1.md", files, 1)], files + ["a.py", "b.py", "c.py"], leads=[prompt, prompt])
        self.assertEqual(self.twice_lines(fails), [])
        self.assertTrue([n for n in notes if "area x's lead was started twice; its 2 files" in n], notes)
        self.assertTrue([n for n in notes if "part-1.md: 1 readable files had a second reader, within its re-dispatched count of 1: c.py" in n], notes)

    def test_a_restart_does_not_make_the_count_cover_two_more_files(self):
        """AC-4: a is explained; b and c are not, and 2 files are over a count of 1."""
        files = ["a.py", "b.py", "c.py"]
        prompt = self.lead_prompt(["a.py"])
        fails, notes = self.score([f.encode() for f in files], [self.part("part-1.md", files, 1)], files + files, leads=[prompt, prompt])
        self.assertIn("2 readable files had a reader dispatched more than once: b.py (2 times), c.py (2 times)", self.twice_lines(fails)[0])

    def test_a_restarted_file_with_three_readers_still_fails_whatever_the_count(self):
        """AC-4."""
        prompt = self.lead_prompt(["a.py"])
        fails, notes = self.score([b"a.py"], [self.part("part-1.md", ["a.py"], 9)], ["a.py"] * 3, leads=[prompt, prompt])
        self.assertIn("a.py (3 times)", self.twice_lines(fails)[0])

    def test_a_long_list_of_covered_files_is_cut_short_in_the_note_not_in_the_count(self):
        """AC-4: the note names five paths and says how many in all."""
        files = ["f%d.py" % i for i in range(8)]
        fails, notes = self.score([f.encode() for f in files], [self.part("part-1.md", files, 8)], files + files)
        self.assertEqual(self.twice_lines(fails), [])
        note = next(n for n in notes if "second reader" in n)
        self.assertIn("8 readable files had a second reader, within its re-dispatched count of 8: f0.py, f1.py, f2.py, f3.py, f4.py, ... (8 in all)", note)


class SecondReaderCountLineTest(tcp.TranscriptBase):
    """AC-4: the count is read from the part's own Files listed line, the way the scorer reads every line of Coverage."""

    FILE = "api/billing/toll.py"

    def part_name(self, rel):
        areas = tcp.base_areas()
        cuts = [0] + list(tcp.BASE_CUTS) + [len(areas)]
        for k in range(len(cuts) - 1):
            if any(rel in a.files for a in areas[cuts[k]:cuts[k + 1]]):
                return "part-%d.md" % (k + 1)
        raise AssertionError(rel)

    def counts_line(self, name):
        return re.search(r"^Files listed: .*$", self.parts[name], re.M).group(0)

    def run_with(self, parts, rel=None, times=1):
        rel = rel or self.FILE
        events = Transcript(parts).events   # the returned reports are the saved ones
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        for _ in range(times):
            events.extend(t.reader(rel, "tX"))
        return self.run_t(events, parts=parts)

    def reword(self, make):
        name = self.part_name(self.FILE)
        line = self.counts_line(name)
        return tcp.edit(self.parts, name, line, make(line)), name

    def with_count(self, value):
        return self.reword(lambda line: line.replace("re-dispatched: 0;", "re-dispatched: %s;" % value))

    def test_a_count_of_one_in_the_plain_line_covers_the_file(self):
        """AC-4: the baseline the shapes below are measured against."""
        parts, name = self.with_count("1")
        out = self.assertTranscriptProved(self.run_with(parts))
        self.assertIn("%s: 1 readable files had a second reader, within its re-dispatched count of 1: %s" % (name, self.FILE), out)

    def test_the_counts_line_as_a_bullet_still_covers_the_file(self):
        """AC-4: LISTED_RE takes a leading '- ', as it does for the other numbers."""
        parts, _ = self.reword(lambda line: "- " + line.replace("re-dispatched: 0;", "re-dispatched: 1;"))
        self.assertTranscriptProved(self.run_with(parts))

    def test_the_counts_line_with_leading_spaces_still_covers_the_file(self):
        """AC-4."""
        parts, _ = self.reword(lambda line: "   " + line.replace("re-dispatched: 0;", "re-dispatched: 1;"))
        self.assertTranscriptProved(self.run_with(parts))

    def test_the_counts_line_in_backticks_is_not_read_and_covers_nothing(self):
        """AC-4: no allowance, and the run fails on the counts line itself and on the second reader, with no exception."""
        parts, _ = self.reword(lambda line: "`" + line.replace("re-dispatched: 0;", "re-dispatched: 1;") + "`")
        out = self.assertTranscriptFails(self.run_with(parts), r"reader dispatched more than once", r"no line 'Files listed")
        self.assertNotIn("Traceback", out)
        self.assertNotIn("internal error", out)

    def test_a_count_that_is_not_a_number_gives_no_allowance_and_does_not_raise(self):
        """AC-4."""
        for bad in ("many", "-1", "1.5", "", "one", "0x1", "1,000", "+1"):
            with self.subTest(count=bad):
                parts, _ = self.with_count(bad)
                code, out = self.run_with(parts)
                self.assertEqual(code, 1, out)
                self.assertNotIn("internal error", out)
                self.assertNotIn("Traceback", out)
                self.assertRegex(out, r"readable files had a reader dispatched more than once")
                self.assertNotIn("had a second reader, within", out)

    def test_a_count_of_a_huge_number_covers_the_file_and_does_not_raise(self):
        """AC-4: thirty digits."""
        parts, _ = self.with_count("9" * 30)
        out = self.assertTranscriptProved(self.run_with(parts))
        self.assertIn("within its re-dispatched count of %s" % ("9" * 30), out)

    def test_a_count_of_thousands_of_digits_does_not_end_the_run_in_an_internal_error(self):
        """AC-4: model-written text must never reach CAN'T CHECK: internal error. int() of a very long digit string raises
        ValueError on current Pythons (the limit is 4300 digits)."""
        parts, _ = self.with_count("9" * 5000)
        code, out = self.run_with(parts)
        self.assertNotIn("internal error", out)
        self.assertIn(code, (0, 1), out)

    def test_a_count_in_other_digit_scripts_is_read_as_a_number_and_does_not_raise(self):
        """AC-4: the regex takes any Unicode digit, and int() reads it. Arabic-Indic one covers the file, as 1 does."""
        parts, _ = self.with_count("١")
        out = self.assertTranscriptProved(self.run_with(parts))
        self.assertIn("count of 1: ", out)

    def test_two_counts_lines_in_one_part_use_the_first_today(self):
        """Accepted limit, today's behaviour: the scorer reads the first Files listed line of the Coverage and nothing of a
        second one, so a first line of 0 followed by a line of 1 gives no allowance and the reverse gives one."""
        name = self.part_name(self.FILE)
        line = self.counts_line(name)
        one = line.replace("re-dispatched: 0;", "re-dispatched: 1;")
        low_first = tcp.edit(self.parts, name, line, line + "\n" + one)
        code, out = self.run_with(low_first)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"reader dispatched more than once")
        high_first = tcp.edit(self.parts, name, line, one + "\n" + line)
        self.assertTranscriptProved(self.run_with(high_first))

    def test_a_count_in_the_wrong_part_gives_no_allowance(self):
        """AC-4: part 3 says 1, the file is in part 1."""
        name = self.part_name(self.FILE)
        other = "part-3.md" if name != "part-3.md" else "part-1.md"
        line = self.counts_line(other)
        parts = tcp.edit(self.parts, other, line, line.replace("re-dispatched: 0;", "re-dispatched: 1;"))
        self.assertTranscriptFails(self.run_with(parts), r"1 readable files had a reader dispatched more than once: %s \(2 times\)" % re.escape(self.FILE))

    def test_a_count_of_two_does_not_cover_a_file_read_three_times(self):
        """AC-4."""
        parts, _ = self.with_count("2")
        self.assertTranscriptFails(self.run_with(parts, times=2), r"%s \(3 times\)" % re.escape(self.FILE))

    def test_a_count_of_five_with_three_twice_read_files_in_a_part_that_says_two_fails(self):
        """AC-4: over the count, all three stay failures, and the count is not spent on some of them."""
        rels = ["api/billing/toll.py", "api/billing/tow.py", "api/billing/%s" % next(f for f in tcp.base_areas()[3].files if f not in ("api/billing/toll.py", "api/billing/tow.py") and tcp.is_readable(f)).split("/")[-1]]
        name = self.part_name(rels[0])
        line = self.counts_line(name)
        parts = tcp.edit(self.parts, name, line, line.replace("re-dispatched: 0;", "re-dispatched: 2;"))
        events = Transcript(parts).events
        t = Transcript.__new__(Transcript)
        t.n, t.repo = 90000, str(Fixture.repo)
        for rel in rels:
            events.extend(t.reader(rel, "tX"))
        out = self.assertTranscriptFails(self.run_t(events, parts=parts), r"^transcript: 3 readable files had a reader dispatched more than once")
        self.assertNotIn("had a second reader, within", out)

    def test_a_note_never_changes_the_exit_code_or_the_first_line(self):
        """AC-4."""
        parts, _ = self.with_count("1")
        code, out = self.run_with(parts)
        self.assertEqual((code, out.splitlines()[0]), (0, "LOOP PROVED"))


# ---------------------------------------------------------------- fix batch 1 (3.0.1): digits that int() cannot convert

class DigitFieldsNeverReachInternalErrorTest(tcp.Base):
    """Fix batch 1, A1 and A2: no numeric field of a part, in any digit script, ends the run in `CAN'T CHECK: internal error`.
    Model-written text is a failure line (exit 1) or a count the check reads, never a raised ValueError. Each case is
    (part, text in the base part, text with a `{}` for the number). The base parts are tcp.build_parts(tcp.base_areas())."""

    FIELDS = (
        ("part-1.md", "SWEEP IN PARTS: 7 areas", "SWEEP IN PARTS: {} areas"),
        ("part-1.md", "Mode: full sweep, 10 area", "Mode: full sweep, {} area"),
        ("part-1.md", "Files listed: 368;", "Files listed: {};"),
        ("part-1.md", "read: 367;", "read: {};"),
        ("part-1.md", "skipped: 1; re-d", "skipped: {}; re-d"),
        ("part-1.md", "re-dispatched: 0;", "re-dispatched: {};"),
        ("part-1.md", "failed: 0; unread: 0\nSkip", "failed: {}; unread: 0\nSkip"),
        ("part-1.md", "unread: 0\nSkip reasons: 1", "unread: {}\nSkip reasons: 1"),
        ("part-1.md", "Areas not read: 7 areas, 582 files", "Areas not read: {} areas, 582 files"),
        ("part-1.md", "7 areas, 582 files", "7 areas, {} files"),
        ("part-1.md", "Whole repo: 990 tracked", "Whole repo: {} tracked"),
        ("part-1.md", "; 40 in folders", "; {} in folders"),
        ("part-1.md", "; 3 untracked", "; {} untracked"),
        ("part-1.md", "web/vendor/: 40,", "web/vendor/: {},"),
        ("part-1.md", "- root: (root) (6 files)", "- root: (root) ({} files)"),
        ("part-1.md", "from `rules/r0123_ledger.py` to `rules/r0244_queue.py` (122 files)",
         "from `rules/r0123_ledger.py` to `rules/r0244_queue.py` ({} files)"),
        ("part-3.md", "SWEEP IN PARTS: 0 areas", "SWEEP IN PARTS: {} areas"),
        ("part-3.md", "Mode: full sweep, 4 area", "Mode: full sweep, {} area"),
        ("part-3.md", "- web: `web/` except `web/vendor/` (30 files)", "- web: `web/` except `web/vendor/` ({} files)"),
    )

    def sweep(self, digits, fields=None):
        base = tcp.build_parts(tcp.base_areas())
        for name, old, new in (fields or self.FIELDS):
            with self.subTest(field=new.replace("{}", "<n>")[:50]):
                code, out = tcp.run_script(tcp.edit(base, name, old, new.replace("{}", digits)))
                self.assertNotIn("internal error", out, out[:200])
                self.assertNotIn("Traceback", out)
                self.assertIn(code, (0, 1), out[:200])

    def test_five_thousand_ascii_digits_in_any_numeric_field_fail_a_line_and_do_not_raise(self):
        """A1: the folder count in Whole repo was the one field that raised; the others are read through `fit`."""
        self.sweep("9" * 5000)

    def test_five_thousand_arabic_indic_digits_in_any_numeric_field_do_not_raise(self):
        """FAULT, fails at the staged scorer (it passed at HEAD): `fit` now judges ASCII groups only, so a group of Unicode
        digits that `\\d` still matches reaches a bare int() and raises ValueError on Python 3.11 and later.
        Reproduction: part 1 line 1 `SWEEP IN PARTS: <5000 x U+0669> areas not read`; 18 of the 19 fields do it (all but the folder count in Whole repo). Python 3.9 has no such limit, so the test passes there."""
        self.sweep("\u0669" * 5000)

    def test_five_thousand_fullwidth_digits_in_a_few_fields_do_not_raise(self):
        """FAULT, as above, with U+FF19."""
        self.sweep("\uff19" * 5000, self.FIELDS[:3] + self.FIELDS[8:9] + self.FIELDS[14:15])

    def test_a_negative_an_exponent_and_a_decimal_are_a_failure_line_never_a_raise(self):
        """No field reads a sign, an exponent or a point: the regex wants digits only, so the line fails to parse."""
        base = tcp.build_parts(tcp.base_areas())
        for digits in ("-5", "+5", "1e3", "1.5", "0x10", "1_0", " 5", "\u00b2", "\u2460", "\u00bd"):
            for name, old, new in self.FIELDS[:3] + self.FIELDS[10:11] + self.FIELDS[14:15]:
                with self.subTest(digits=ascii(digits), field=new[:30]):
                    code, out = tcp.run_script(tcp.edit(base, name, old, new.replace("{}", digits)))
                    self.assertNotIn("internal error", out)
                    self.assertNotIn("Traceback", out)
                    self.assertEqual(code, 1, out[:200])

    def test_a_short_count_in_arabic_indic_digits_is_read_as_a_number(self):
        """A2: only the too-long case changed. A folder count of U+0664 U+0660 (40) reads as 40, as at 3.0.0."""
        base = tcp.build_parts(tcp.base_areas())
        out = self.assertProved(tcp.edit(base, "part-1.md", "web/vendor/: 40,", "web/vendor/: \u0664\u0660,"))
        self.assertNotIn("internal error", out)

    def test_areas_named_with_unicode_digits_parse_as_they_did_at_3_0_0(self):
        """A2: a name is the part before the first colon, never a count. Superscript, Arabic-Indic, full-width and circled
        digits, and a mix, all prove (the circled one and U+00B2 failed at HEAD, which is the fault A2 mends)."""
        for name in ("\u00b2", "\u0663", "x\u00b2", "\u0661\u0662", "\uff14\uff10", "\u2460", "\u00bd", "cli-\u00b2", "\u0663 files"):
            with self.subTest(name=ascii(name)):
                areas = tcp.base_areas()
                areas[6] = areas[6].copy(name=name)
                self.assertProved(tcp.build_parts(areas))


if __name__ == "__main__":
    unittest.main()
