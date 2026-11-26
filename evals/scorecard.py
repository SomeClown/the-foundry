#!/usr/bin/env python3
"""Add rows to evals/SCORECARD.md from the harness's aggregate-result.json files.

    python3 evals/scorecard.py --commit SHA [--scorecard PATH] [--dry-run] RESULT [RESULT ...]

RESULT is an aggregate-result.json, or a folder that holds one. One row is
written per case, per file, in file and case order. Every input is read and
checked before anything is written; a file the script can't use prints
"CAN'T RECORD: <file>: <reason>" and exits 2 with nothing written. Nothing here
exits 1: the script records and gates nothing.

It reads local files only. No network, no subprocess, no model session.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HEADER = "| Started (UTC) | Plugin | Commit | Claude Code | Case | Runs | Fully passed | Graders failed | Cost |"
RULE = "|---|---|---|---|---|---|---|---|---|"
PLUGIN = "the-foundry"
RESULT_NAME = "aggregate-result.json"
COMMIT_RE = re.compile(r"[0-9a-f]{7,40}")


class Refused(Exception):
    """A file the script can't record; the message follows "CAN'T RECORD: <file>: "."""

    def __init__(self, where, why):
        super().__init__("%s: %s" % (where, why))


def cell(value):
    return str(value).replace("|", "\\|")


def split_row(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def number(value, where, what):
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Refused(where, "%s isn't a number" % what)
    return float(value)


def started_text(value, where):
    if not isinstance(value, str):
        raise Refused(where, "startedAt is missing")
    try:
        when = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise Refused(where, "startedAt isn't a timestamp: %r" % value)
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc)
    return when.strftime("%Y-%m-%d %H:%M")


def failed_text(runs, where):
    counts = {}
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("graders"), list):
            raise Refused(where, "a run has no grader list")
        if run.get("error") is not None:
            counts[("run error", False)] = counts.get(("run error", False), 0) + 1
        for g in run["graders"]:
            if not isinstance(g, dict) or not isinstance(g.get("name"), str):
                raise Refused(where, "a grader has no name")
            if g.get("passed") is True:
                continue
            explanation = g.get("explanation")
            skipped = isinstance(explanation, str) and explanation.startswith("skipped:")
            key = (g["name"], skipped)
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return "none"
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1]))
    return ", ".join("%s (%d%s)" % (name, n, " skipped" if skipped else "") for (name, skipped), n in items)


def fully_passed(run):
    return run.get("error") is None and all(g.get("passed") is True for g in run["graders"])


def rows_for(path, commit):
    where = str(path)
    if path.is_dir():
        path = path / RESULT_NAME
        where = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise Refused(where, "can't read it (%s)" % err.strerror)
    except UnicodeDecodeError:
        raise Refused(where, "not UTF-8 text")
    try:
        data = json.loads(text)
    except ValueError:
        raise Refused(where, "not JSON")
    if not isinstance(data, dict):
        raise Refused(where, "not a JSON object")
    version = data.get("schemaVersion")
    if isinstance(version, bool) or version != 1:
        raise Refused(where, "schemaVersion is %r, not 1" % (version,))
    if data.get("partial") is True:
        raise Refused(where, "the run is partial")
    suite = data.get("suite")
    plugins = suite.get("plugins") if isinstance(suite, dict) else None
    plugin = next((p for p in plugins or [] if isinstance(p, dict) and p.get("name") == PLUGIN), None)
    if plugin is None:
        raise Refused(where, "no suite.plugins entry named %s" % PLUGIN)
    started = started_text(data.get("startedAt"), where)
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise Refused(where, "no cases list")
    rows = []
    for case in cases:
        name = case.get("name") if isinstance(case, dict) else None
        arms = case.get("arms") if isinstance(case, dict) else None
        runs = arms.get("with") if isinstance(arms, dict) else None
        if not isinstance(name, str) or not isinstance(runs, list):
            raise Refused(where, "case %r has no arms.with list" % (name,))
        cost = 0.0
        for run in runs:
            if not isinstance(run, dict):
                raise Refused(where, "case %s: a run isn't an object" % name)
            cost += number(run.get("costUsd"), where, "costUsd")
            cost += number(run.get("judgeCostUsd"), where, "judgeCostUsd")
        failed = failed_text(runs, where)
        fully = sum(1 for run in runs if fully_passed(run))
        cells = [
            started, plugin.get("version"), commit, data.get("claudeVersion"), name,
            len(runs), fully, failed, "$%.2f" % cost,
        ]
        rows.append([cell("" if c is None else c) for c in cells])
    return rows


def insert_rows(card_text, new_rows):
    """Return the scorecard text with the new rows added, and how many were new."""
    lines = card_text.split("\n")
    if HEADER not in lines:
        raise Refused("scorecard", "no table header line")
    start = lines.index(HEADER)
    end = start
    while end + 1 < len(lines) and lines[end + 1].startswith("|"):
        end += 1
    seen = {(c[0], c[4], c[2]) for c in (split_row(l) for l in lines[start + 2:end + 1]) if len(c) >= 5}
    fresh = []
    for row in new_rows:
        key = (row[0], row[4], row[2])
        if key not in seen:
            seen.add(key)
            fresh.append(row)
    lines[end + 1:end + 1] = ["| " + " | ".join(r) + " |" for r in fresh]
    return "\n".join(lines), fresh


def write_atomic(path, text):
    folder = path.parent
    fd, tmp = tempfile.mkstemp(dir=str(folder), prefix=".scorecard-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, str(path))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def record(args):
    commit = args.commit.lower()
    if not COMMIT_RE.fullmatch(commit):
        raise Refused("--commit", "%r isn't 7 to 40 hex digits" % args.commit)
    card = Path(args.scorecard)
    try:
        with open(str(card), encoding="utf-8", newline="") as handle:
            card_text = handle.read()
    except OSError as err:
        raise Refused(str(card), "can't read it (%s)" % err.strerror)
    new_rows = []
    for result in args.results:
        new_rows.extend(rows_for(Path(result), commit))
    try:
        text, fresh = insert_rows(card_text, new_rows)
    except Refused as err:
        raise Refused(str(card), str(err).split(": ", 1)[1])
    for row in fresh:
        print("| " + " | ".join(row) + " |")
    if args.dry_run:
        print("dry run: %d rows, nothing written" % len(fresh))
    elif fresh:
        write_atomic(card, text)
        print("recorded %d rows in %s" % (len(fresh), card))
    else:
        print("nothing new: every row is already recorded")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Add rows to evals/SCORECARD.md from harness results.")
    parser.add_argument("--commit", required=True, help="the commit the run used (7 to 40 hex digits)")
    parser.add_argument("--scorecard", default=str(Path(__file__).resolve().parent / "SCORECARD.md"))
    parser.add_argument("--dry-run", action="store_true", help="print the rows, write nothing")
    parser.add_argument("results", nargs="+", metavar="RESULT", help="an aggregate-result.json, or a folder holding one")
    args = parser.parse_args(argv)
    try:
        record(args)
    except Refused as err:
        print("CAN'T RECORD: %s" % err)
        return 2
    except Exception as err:  # never exit 1: an unexpected failure is a refusal too
        print("CAN'T RECORD: unexpected %s: %s" % (type(err).__name__, err))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
