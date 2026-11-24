#!/usr/bin/env python3
"""Scores a sweep read in parts: did part-1.md, part-2.md, ... cover the test repo exactly once and find every planted fact?

    check_parts.py --key KEY --repo FIXTURE_DIR --parts DIR [--min-parts N] [--part-size N] [--transcript FILE]

Reads DIR/part-<n>.md in number order and checks, against the key and the fixture's tracked files:
  1. count          at least --min-parts part files
  2. shape          the SWEEP IN PARTS line, the block to END OF BLOCK, the last line
  3. order          n falls, the last part says 0, each block is a strict suffix of the one before,
                    and each part's "Areas read:" lines are exactly what the block dropped
  4. notation       every area line parses and its definition rebuilds to the stated count
  5. exactly once   the areas read hold every tracked file outside the whole-folder skips, once each
  6. coverage       the Mode, Files listed, Areas read, Areas not read and Whole repo lines, looked up after the report's
                    last "8. Coverage" heading
  7. facts          every key fact is found, and no decoy appears in any part; a fact is found in the part whose areas
                    read its file
  8. part size      only with --part-size N: the stated counts of each part's "Areas read:" lines add up to at most N;
                    also prints a NOTE: line, never a failure, when a part that isn't the last could have held the next
                    area too
  9. area size      no area read holds more than AREA_MAX files
 10. read           across the parts: unread and failed are 0, the skipped numbers add up to the key's file_skips, and
                    the read numbers add up to the files left after the whole-folder skips minus those
 11. transcript     only with --transcript FILE, the run's `claude -p --output-format stream-json --verbose` transcript:
                    every readable file had one file-reader task started and completed, each later top-level
                    `investigate` dispatch is CONTINUE SWEEP plus the previous part's block as saved, and (a NOTE:, never
                    a failure) no two area leads ran at the same time; and each part file is the report its top-level
                    `investigate` returned (blank lines and trailing whitespace aside), one result per part file

Also prints a NOTE: line, never a failure, for a later part that names an untracked path (only part 1 lists them).
Parses `(root)` in backticks, a folder-and-(direct) pair inside one pair of backticks, and a `Whole repo:` folder in backticks.

Exit 0 prints LOOP PROVED and a summary (with --part-size, the summary gives the largest part's file count); exit 1 prints LOOP FAILED and one line per failure; exit 2 prints
CAN'T CHECK: <why> (a missing file, an unreadable key, an unreadable transcript, a crash). Standard library only, Python 3.9.
The script runs <repo>/bin/git, so it is for fixtures it was built to score.

Tolerant of harmless whitespace (trailing spaces, Windows line endings, a blank line after the block, blank lines
around the area lines under "Areas read:"), and of a leading "- " on the Mode, Files listed and Whole repo lines. Exact about every fixed token and the notation.
"""

import argparse
import json
import os
import re
import subprocess
import sys

# Copied from compare.py (not imported): the whitespace class and the found rule.
SPACE = "[ \\t\\n\\v\\f\\r\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff]+"

FLAG = "NOT A PER-FILE READ"
LAST_LINE = "INVESTIGATE REPORT ENDS"
SWEEP_RE = re.compile(r"^SWEEP IN PARTS: (\d+) areas not read$")
CONTINUE_SENTENCE = ("To read the rest, dispatch `investigate` again. The brief is `CONTINUE SWEEP` on its first line, "
                     "then every line from `Project:` to `END OF BLOCK`, copied as it stands.")
AREA_RE = re.compile(r"^- ([^:]+?): (.+) \((\d+) files\)$")
DIR_PIECE = r"`(?P<d>[^`]+/)(?:`(?: \((?P<direct>direct)\))?| \((?P<inner>direct)\)`)"
PIECE_RE = re.compile(
    r"(?:" + DIR_PIECE + r"|`?(?P<root>\(root\))`?)"
    r"(?P<excepts>(?: except `[^`]+/`)*)"
    r"(?: from `(?P<a>[^`]+)` to `(?P<b>[^`]+)`)?"
)
EXCEPT_RE = re.compile(r" except `([^`]+/)`")
MODE_RE = re.compile(r"^(?:- )?Mode: full sweep, (\d+) area leads?$")
LISTED_RE = re.compile(r"^(?:- )?Files listed: (\d+); read: (\d+); skipped: (\d+); re-dispatched: (\d+); failed: (\d+); unread: (\d+)$")
NOT_READ_RE = re.compile(r"^(?:- )?Areas not read: (\d+) areas, (\d+) files; see SWEEP IN PARTS at the top\.$")
WHOLE_RE = re.compile(r"^(?:- )?Whole repo: (\d+) tracked files; (\d+) in folders skipped whole \((.*)\); (\d+) untracked")
WHOLE_LATER = "Whole repo: given in part 1."
PART_FILE_RE = re.compile(r"^part-(\d+)\.md$")
COVERAGE_HEADING = "8. Coverage"
# The design says an area holds "at most about 150" files; this is that plus a tenth.
AREA_MAX = 165
READER = "the-foundry:file-reader"
INVESTIGATE = "the-foundry:investigate"
AREA_LEAD = "AREA LEAD"
CONTINUE = "CONTINUE SWEEP"
FILE_SKIP_SUFFIXES = {"lock": ".lock", "binary": ".bin"}


class CantCheck(Exception):
    """Something the scorer can't score; the message says why."""


def token_found(token, text):
    """The found rule from compare.py's token_found."""
    body = SPACE.join(re.escape(part) for part in re.split(" +", token))
    return re.search("(?:^|[^A-Za-z0-9])" + body + "(?![A-Za-z0-9-])", text, re.I | re.A) is not None


def load_key(path):
    try:
        with open(path, encoding="utf-8") as f:
            key = json.load(f)
        facts, decoys, layout = key["facts"], key["decoys"], key["layout"]
        for item in facts + decoys:
            item["token"]
        layout["tracked"]
        layout["skipped_whole"].items()
        layout["untracked"][:]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        raise CantCheck("the key %s is missing or unreadable (%s: %s)" % (path, type(err).__name__, err))
    return facts, decoys, layout


def tracked_files(repo):
    repo = os.path.abspath(repo)
    git = os.path.join(repo, "bin", "git")
    if not os.path.isfile(git):
        raise CantCheck("the fixture's git wrapper %s is missing; build the fixture with its scaffold" % git)
    try:
        done = subprocess.run([git, "-c", "core.quotepath=off", "ls-files"], cwd=repo,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    except (OSError, subprocess.SubprocessError) as err:
        raise CantCheck("could not run %s (%s)" % (git, err))
    if done.returncode != 0:
        raise CantCheck("git ls-files failed in %s: %s" % (repo, done.stderr.decode("utf-8", "replace").strip()))
    return [p for p in done.stdout.split(b"\n") if p]


def read_parts(parts_dir):
    """[(number, filename, lines)] in number order; lines are right-trimmed with line endings normalized."""
    if not os.path.isdir(parts_dir):
        raise CantCheck("the parts folder %s does not exist" % parts_dir)
    found = []
    for name in os.listdir(parts_dir):
        m = PART_FILE_RE.match(name)
        if m:
            found.append((int(m.group(1)), name))
    found.sort()
    parts = []
    for number, name in found:
        try:
            with open(os.path.join(parts_dir, name), "rb") as f:
                text = f.read().decode("utf-8", "replace")
        except OSError as err:
            raise CantCheck("cannot read %s (%s)" % (name, err))
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        parts.append((number, name, text, [line.rstrip() for line in text.split("\n")]))
    return parts


def parse_definition(definition):
    """The list of pieces, each (dir bytes or None, direct, excepts, from, to), or a string naming what's wrong."""
    pieces = []
    pos = 0
    while True:
        m = PIECE_RE.match(definition, pos)
        if not m:
            return "cannot read a piece at %r" % definition[pos:pos + 40]
        excepts = [e.encode("utf-8") for e in EXCEPT_RE.findall(m.group("excepts"))]
        a = m.group("a")
        b = m.group("b")
        pieces.append((m.group("d").encode("utf-8") if m.group("d") else None, (m.group("direct") or m.group("inner")) is not None, excepts,
                       a.encode("utf-8") if a is not None else None, b.encode("utf-8") if b is not None else None))
        pos = m.end()
        if pos == len(definition):
            return pieces
        if not definition.startswith(" + ", pos):
            return "expected ' + ' between pieces at %r" % definition[pos:pos + 40]
        pos += 3


def rebuild(pieces, tracked):
    files = set()
    for d, direct, excepts, a, b in pieces:
        for path in tracked:
            if d is None:
                if b"/" in path:
                    continue
            else:
                if not path.startswith(d):
                    continue
                if direct and b"/" in path[len(d):]:
                    continue
            if any(path.startswith(x) for x in excepts):
                continue
            if a is not None and not (a <= path <= b):
                continue
            files.add(path)
    return files


def area_lines_after(lines, i):
    """The '- ' lines after lines[i], blank lines between them skipped, as (lines, index after them)."""
    out = []
    j = i + 1
    while j < len(lines):
        if lines[j].lstrip().startswith("-") and not lines[j].lstrip().startswith("- "):
            break   # a rule line, a bare dash: not an area line
        if not lines[j].strip():
            j += 1
            continue
        if not lines[j].lstrip().startswith("-"):
            break
        out.append(lines[j].strip())
        j += 1
    return out, j


def coverage_start(lines, begin):
    """(index to look up the Coverage lines from, whether the heading was found): after the last '8. Coverage' heading."""
    for i in range(len(lines) - 1, begin - 1, -1):
        if lines[i].lstrip().startswith("#") and COVERAGE_HEADING in lines[i]:
            return i + 1, True
    return begin, False


def check_shape(name, lines, fails, heads=None):
    """Returns (n, block area lines, index where the report's sections begin) or None when the block can't be read."""
    at = 0
    while at < len(lines) and not lines[at].strip():
        at += 1
    if at < len(lines) and lines[at] == FLAG:
        fails.append("%s: line 1 is %s, so the run was a flagged single-agent read; expected a full sweep with the SWEEP IN PARTS line on line 1" % (name, FLAG))
        at += 1
    first = lines[at] if at < len(lines) else ""
    m = SWEEP_RE.match(first)
    if not m:
        fails.append("%s: expected 'SWEEP IN PARTS: <n> areas not read' as line %d, found %r" % (name, at + 1, first))
        return None
    n = int(m.group(1))
    last = [line for line in lines if line.strip()]
    if not last or last[-1].strip() != LAST_LINE:
        fails.append("%s: expected the last non-blank line to be %r, found %r (the report was cut off?)" % (name, LAST_LINE, last[-1] if last else ""))
    if n == 0:
        nxt = next((line for line in lines[at + 1:] if line.strip()), "")
        if nxt.startswith(("To read the rest", "Project:", "Instructions:", "Areas not read:", "END OF BLOCK")):
            fails.append("%s: the last part says 0 areas not read, so nothing may sit under the line; found %r" % (name, nxt))
        return 0, [], at + 1
    expect = [("sentence", CONTINUE_SENTENCE), ("Project:", None), ("Focus:", None), ("Environment:", None), ("Instructions:", None), ("Areas not read:", "Areas not read:")]
    cur = at + 1
    for label, exact in expect:
        line = lines[cur] if cur < len(lines) else ""
        if exact is not None:
            if line != exact:
                fails.append("%s: block line %d: expected %r, found %r" % (name, cur + 1, exact, line))
                return None
        elif not line.startswith(label) or not line[len(label):].strip():
            fails.append("%s: block line %d: expected '%s <text>', found %r" % (name, cur + 1, label, line))
            return None
        if heads is not None and exact is None:
            heads[label] = line
        cur += 1
    areas = []
    while cur < len(lines) and lines[cur] != "END OF BLOCK":
        if not lines[cur].startswith("- "):
            fails.append("%s: block line %d: expected an area line starting '- ' or END OF BLOCK, found %r" % (name, cur + 1, lines[cur]))
            return None
        areas.append(lines[cur])
        cur += 1
    if cur >= len(lines):
        fails.append("%s: the block never reaches END OF BLOCK" % name)
        return None
    if len(areas) != n:
        fails.append("%s: the SWEEP IN PARTS line says %d areas, the block holds %d area lines" % (name, n, len(areas)))
    return n, areas, cur + 1


def find_line(lines, start, regex):
    for i in range(start, len(lines)):
        m = regex.match(lines[i].strip())
        if m:
            return i, m
    return None, None


def short(items, limit=5):
    shown = ", ".join(items[:limit])
    return shown + (", ... (%d in all)" % len(items) if len(items) > limit else "")


def positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("%r is not a whole number" % text)
    if value < 1:
        raise argparse.ArgumentTypeError("%r is not a positive whole number" % text)
    return value


def stated_counts(read):
    """The stated file counts of a part's 'Areas read:' lines, or None when a line doesn't parse."""
    counts = []
    for line in read:
        m = AREA_RE.match(line.strip())
        if not m:
            return None
        counts.append(int(m.group(3)))
    return counts


def read_transcript(path):
    """The system events of a stream-json transcript, in file order, as [(line number, event)]."""
    events = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for number, raw in enumerate(f):
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    events.append((number, event))
    except OSError as err:
        raise CantCheck("cannot read the transcript %s (%s)" % (path, err))
    if not any(e.get("type") == "system" and e.get("subtype") == "task_started" and e.get("subagent_type") == READER for _n, e in events):
        raise CantCheck("the transcript %s holds no %s task" % (path, READER))
    return events


def readable_files(tracked, layout):
    """The tracked files a reader should have been dispatched for: outside the whole-folder skips and the file skips.

    The key counts the file skips by reason, not by name, so the names come from the tracked list: 'lock' is a
    path ending .lock, 'binary' one ending .bin. A count that differs from the key's is a fixture this can't score."""
    skipped_dirs = [d.encode("utf-8") for d in layout["skipped_whole"]]
    left = [p for p in tracked if not any(p.startswith(d) for d in skipped_dirs)]
    skipped = set()
    for reason, count in layout["file_skips"].items():
        suffix = FILE_SKIP_SUFFIXES.get(reason)
        if suffix is None:
            raise CantCheck("the key's file_skips names a reason, %r, that this script can't turn into file names" % reason)
        named = [p for p in left if p.endswith(suffix.encode("utf-8"))]
        if len(named) != count:
            raise CantCheck("the key says %d files skipped as %s, the fixture has %d paths ending %s" % (count, reason, len(named), suffix))
        skipped.update(named)
    return set(left) - skipped


def first_difference(sent, saved):
    """A sentence naming the first line where two lists of lines differ."""
    for i in range(max(len(sent), len(saved))):
        a = sent[i] if i < len(sent) else "(no line)"
        b = saved[i] if i < len(saved) else "(no line)"
        if a != b:
            col = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
            lo = max(0, col - 20)
            return "line %d differs at column %d: sent %r, saved %r" % (i + 1, col + 1, a[lo:col + 40], b[lo:col + 40])
    return "the lines are the same"


def report_lines(text):
    """A tool result's report as non-blank, right-trimmed lines: the wrapper off, from the SWEEP IN PARTS line, the two-space indent off."""
    cut = re.search(r"^agentId:", text, re.M)
    if cut:
        text = text[:cut.start()]
    text = re.sub(r"<tools-used-before-summary>.*?</tools-used-before-summary>", "", text, flags=re.S)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start = next((i for i, line in enumerate(lines) if line.strip().startswith("SWEEP IN PARTS:")), 0)
    return [(line[2:] if line.startswith("  ") else line).rstrip() for line in lines[start:] if line.strip()]


def check_transcript(events, repo, tracked, layout, infos, fails, notes):
    """Checks the transcript against the key and the parts; returns (readers completed, readers expected) when it all holds."""
    if "file_skips" not in layout:
        raise CantCheck("the key has no layout.file_skips, so the readable files can't be derived for the transcript check")
    readable = set(p.decode("utf-8", "replace") for p in readable_files(tracked, layout))
    prefixes = set()
    for root in [repo] + [e.get("cwd") for _n, e in events if e.get("subtype") == "init" and isinstance(e.get("cwd"), str)]:
        for form in (os.path.abspath(root), os.path.realpath(root)):
            prefixes.add(form.rstrip("/") + "/")

    def relative(path):
        for prefix in prefixes:
            if path.startswith(prefix):
                return path[len(prefix):]
        return path

    started, done, tops, leads, results = {}, {}, [], [], {}
    for number, e in events:
        if e.get("type") == "user" and e.get("parent_tool_use_id") is None:
            content = (e.get("message") or {}).get("content") if isinstance(e.get("message"), dict) else None
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    body = block.get("content")
                    if isinstance(body, list):
                        body = "\n".join(b.get("text", "") for b in body if isinstance(b, dict))
                    results[block.get("tool_use_id")] = body if isinstance(body, str) else ""
        if e.get("type") != "system":
            continue
        if e.get("subtype") == "task_started":
            kind, prompt = e.get("subagent_type"), e.get("prompt") if isinstance(e.get("prompt"), str) else ""
            started[e.get("task_id")] = (number, e)
            if kind == INVESTIGATE:
                depth = e.get("spawn_depth")
                if prompt.startswith(AREA_LEAD) or (isinstance(depth, int) and depth > 1):
                    leads.append((number, e.get("task_id"), prompt))
                else:
                    tops.append((prompt, e.get("tool_use_id")))
        elif e.get("subtype") == "task_notification":
            done[e.get("task_id")] = (number, e)

    dispatched = {}   # relative path -> [task ids]
    unreadable = []
    for task_id, (_number, e) in started.items():
        if e.get("subagent_type") != READER:
            continue
        note = done.get(task_id, (None, {}))[1]
        m = re.search(r"^Path: (\S+)", note.get("summary") or "", re.M) or re.search(r"`(/[^`\n]+)`", e.get("prompt") or "")
        if not m:
            unreadable.append(task_id)
            continue
        dispatched.setdefault(relative(m.group(1).strip().strip("`")), []).append(task_id)
    if unreadable:
        fails.append("transcript: %d reader tasks name no path (task ids %s)" % (len(unreadable), short([str(t) for t in unreadable])))
    never = sorted(readable - set(dispatched))
    if never:
        fails.append("transcript: %d readable files never had a reader dispatched: %s" % (len(never), short(never)))
    incomplete = sorted(path for path, ids in dispatched.items() if path in readable and not any(done.get(t, (0, {}))[1].get("status") == "completed" for t in ids))
    if incomplete:
        fails.append("transcript: %d readable files had a reader dispatched that never completed: %s" % (len(incomplete), short(incomplete)))
    twice = sorted(path for path, ids in dispatched.items() if path in readable and len(ids) > 1)
    if twice:
        fails.append("transcript: %d readable files had a reader dispatched more than once: %s" % (len(twice), short(["%s (%d times)" % (p, len(dispatched[p])) for p in twice])))
    outside = sorted(set(dispatched) - readable)
    if outside:
        fails.append("transcript: %d reader tasks are for paths outside the readable files: %s" % (len(outside), short(outside)))

    # each later top-level dispatch is CONTINUE SWEEP and the previous part's block
    for k, (prompt, _id) in enumerate(tops[1:], start=1):
        label = "top-level investigate dispatch %d" % (k + 1)
        if k > len(infos):
            fails.append("transcript: %s has no part-%d.md to compare with" % (label, k))
            continue
        prev = infos[k - 1]
        lines = prev["lines"]
        start = next((j for j in range(len(lines)) if lines[j].startswith("Project:")), None) if prev["shape"] is not None else None
        end = next((j for j in range(start, len(lines)) if lines[j] == "END OF BLOCK"), None) if start is not None else None
        if end is None:
            fails.append("transcript: %s can't be compared: %s has no block from Project: to END OF BLOCK" % (label, prev["name"]))
            continue
        want = [CONTINUE] + lines[start:end + 1]
        sent = [line.rstrip() for line in prompt.replace("\r\n", "\n").replace("\r", "\n").rstrip().split("\n")]
        if sent != want:
            fails.append("transcript: %s is not CONTINUE SWEEP and %s's block: %s" % (label, prev["name"], first_difference(sent, want)))
    if len(tops) - 1 < len(infos) - 1:
        fails.append("transcript: the parts folder holds %d part files but only %d top-level investigate dispatches follow the first" % (len(infos), len(tops) - 1))

    # each part file is the report the top-level investigate returned
    returned = [results[tid] for _p, tid in tops if tid in results]
    if len(returned) != len(infos):
        fails.append("transcript: %d top-level investigate results, %d part files" % (len(returned), len(infos)))
    for text, info in zip(returned, infos):
        got = report_lines(text)
        saved_lines = [line.rstrip() for line in info["lines"] if line.strip()]
        if got != saved_lines:
            i = next((j for j in range(min(len(got), len(saved_lines))) if got[j] != saved_lines[j]), min(len(got), len(saved_lines)))
            a = got[i] if i < len(got) else "(no line)"
            b = saved_lines[i] if i < len(saved_lines) else "(no line)"
            col = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
            lo = max(0, col - 30)
            fails.append("transcript: %s differs from the report the investigate returned, at non-blank line %d, column %d: returned %r, saved %r"
                         % (info["name"], i + 1, col + 1, a[lo:col + 40], b[lo:col + 40]))

    # one area lead at a time (a NOTE, never a failure)
    running = []
    for number, task_id, prompt in sorted(leads):
        m = re.search(r"^Area: (\S+)", prompt, re.M)
        area = m.group(1) if m else str(task_id)
        for other_end, other in running:
            if other_end is None or other_end > number:
                notes.extend(["NOTE: transcript: area leads %s and %s were running at the same time" % (other, area)])
        running.append((done[task_id][0] if task_id in done else None, area))

    if fails:
        return None
    return len(dispatched), len(readable)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--key", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--parts", required=True)
    ap.add_argument("--min-parts", type=int, default=2)
    ap.add_argument("--part-size", type=positive_int, default=None)
    ap.add_argument("--transcript", default=None)
    args = ap.parse_args(argv)

    facts, decoys, layout = load_key(args.key)
    tracked = tracked_files(args.repo)
    if len(tracked) != layout["tracked"]:
        raise CantCheck("the fixture tracks %d files, the key says %d; rebuild the fixture" % (len(tracked), layout["tracked"]))
    skipped_dirs = [d.encode("utf-8") for d in layout["skipped_whole"]]
    expected = set(p for p in tracked if not any(p.startswith(d) for d in skipped_dirs))
    parts = read_parts(args.parts)
    events = read_transcript(args.transcript) if args.transcript else None

    fails = []
    if len(parts) < args.min_parts:
        fails.append("count: expected at least %d part files in %s, found %d" % (args.min_parts, args.parts, len(parts)))
    numbers = [p[0] for p in parts]
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        fails.append("count: expected part-1.md to part-%d.md with no gaps, found numbers %s" % (len(numbers), numbers))

    infos = []       # per part: dict
    validated = {}   # area line text -> first place seen
    area_total = 0
    for number, name, text, lines in parts:
        heads = {}
        shape = check_shape(name, lines, fails, heads)
        info = {"name": name, "text": text, "lines": lines, "shape": shape, "read": [], "read_idx": None, "heads": heads, "files": set(), "areas": []}
        infos.append(info)
        if shape is None:
            continue
        n, block, begin = shape
        info["n"], info["block"], info["begin"] = n, block, begin
        info["cov"], has_heading = coverage_start(lines, begin)
        if not has_heading:
            fails.append("%s: no '%s' heading line (a line starting with # that holds it), so the Coverage lines are looked up from the end of the block" % (name, COVERAGE_HEADING))
        idx, _ = find_line(lines, info["cov"], re.compile(r"^Areas read:$"))
        if idx is None:
            fails.append("%s: no 'Areas read:' line in Coverage" % name)
        else:
            info["read"], _ = area_lines_after(lines, idx)
            info["read_idx"] = idx
            if not info["read"]:
                fails.append("%s: 'Areas read:' has no area lines under it" % name)

    # order
    shaped = [i for i in infos if i["shape"] is not None]
    for prev, cur in zip(shaped, shaped[1:]):
        if not cur["n"] < prev["n"]:
            fails.append("%s: expected n to fall from %d in %s, found %d" % (cur["name"], prev["n"], prev["name"], cur["n"]))
        pb, cb = prev["block"], cur["block"]
        if len(cb) < len(pb) and pb[len(pb) - len(cb):] == cb:
            dropped = [a.strip() for a in pb[:len(pb) - len(cb)]]
            if cur["read"] != dropped:
                fails.append("%s: 'Areas read:' should be exactly the %d areas dropped from %s's block (%s); found %d lines (%s)"
                             % (cur["name"], len(dropped), prev["name"], short([d[:40] for d in dropped], 3),
                                len(cur["read"]), short([r[:40] for r in cur["read"]], 3)))
        else:
            fails.append("%s: block areas must be a strict suffix of %s's block (%d lines): found %d lines starting %r"
                         % (cur["name"], prev["name"], len(pb), len(cb), cb[0].strip()[:60] if cb else ""))
    if shaped:
        if shaped[-1]["n"] != 0:
            fails.append("%s: the last part must say 0 areas not read, found %d" % (shaped[-1]["name"], shaped[-1]["n"]))
        if infos[-1]["shape"] is None:
            fails.append("%s: the last part's block is unreadable, so the loop can't be shown to end" % infos[-1]["name"])

    # same four lines in every part that has them
    withheads = [i for i in infos if i["heads"] and len(i["heads"]) == 4]
    for cur in withheads[1:]:
        first = withheads[0]
        for label in ("Project:", "Focus:", "Environment:", "Instructions:"):
            if cur["heads"][label] != first["heads"][label]:
                fails.append("%s: the %s line differs from %s: expected %r, found %r"
                             % (cur["name"], label, first["name"], first["heads"][label], cur["heads"][label]))

    # notation and the rebuilt sets
    covered = {}  # path -> list of area names
    read_area_count = 0
    for info in infos:
        if info["shape"] is None:
            continue
        for kind, group in (("block", info["block"] if info is infos[0] else []), ("read", info["read"])):
            for line in group:
                line = line.strip()
                if line in validated:
                    rebuilt = validated[line]
                else:
                    rebuilt = None
                    m = AREA_RE.match(line)
                    if not m:
                        fails.append("%s: area line does not match '- <name>: <definition> (<n> files)': %r" % (info["name"], line))
                    else:
                        pieces = parse_definition(m.group(2))
                        if isinstance(pieces, str):
                            fails.append("%s: area %r: %s" % (info["name"], m.group(1), pieces))
                        else:
                            rebuilt = (m.group(1), rebuild(pieces, tracked), int(m.group(3)))
                            if len(rebuilt[1]) != rebuilt[2]:
                                fails.append("%s: area %r: stated %d files, the definition rebuilds to %d" % (info["name"], m.group(1), rebuilt[2], len(rebuilt[1])))
                    validated[line] = rebuilt
                if kind == "read":
                    read_area_count += 1
                    if rebuilt is not None:
                        info["files"].update(rebuilt[1])
                        info["areas"].append((rebuilt[0], len(rebuilt[1])))
                        for path in rebuilt[1]:
                            covered.setdefault(path, []).append(rebuilt[0])
                        info.setdefault("counts", []).append(rebuilt[2])
                    else:
                        info.setdefault("counts", []).append(None)

    # exactly once
    if covered or any(i["read"] for i in infos):
        got = set(covered)
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        dup = sorted(p for p, areas in covered.items() if len(areas) > 1)
        show = lambda paths: short([p.decode("utf-8", "replace") for p in paths])
        if missing:
            fails.append("exactly once: expected all %d files outside the whole-folder skips, %d are in no area read: %s" % (len(expected), len(missing), show(missing)))
        if extra:
            fails.append("exactly once: %d files in areas read are not expected (untracked or in a skipped folder): %s" % (len(extra), show(extra)))
        if dup:
            fails.append("exactly once: %d files are in more than one area read: %s (areas %s)" % (
                len(dup), show(dup), short(sorted(set(a for p in dup for a in covered[p])))))
    else:
        fails.append("exactly once: no area was read in any part")

    # coverage
    later_named = []
    skipped_total = sum(layout["skipped_whole"].values())
    for number, info in zip(numbers, infos):
        if info["shape"] is None:
            continue
        name, lines, begin = info["name"], info["lines"], info["cov"]
        _, m = find_line(lines, begin, MODE_RE)
        if not m:
            fails.append("%s: no line 'Mode: full sweep, <N> area leads' in Coverage" % name)
        elif int(m.group(1)) != len(info["read"]):
            fails.append("%s: Mode says %s area leads, 'Areas read:' lists %d areas" % (name, m.group(1), len(info["read"])))
        _, m = find_line(lines, begin, LISTED_RE)
        if not m:
            fails.append("%s: no line 'Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>' in Coverage" % name)
        else:
            listed, read, skipped, _redisp, failed, unread = [int(x) for x in m.groups()]
            info["listed"] = (read, skipped, failed, unread)
            if listed != read + skipped + failed + unread:
                fails.append("%s: Files listed %d should equal read+skipped+failed+unread = %d+%d+%d+%d = %d"
                             % (name, listed, read, skipped, failed, unread, read + skipped + failed + unread))
            counts = info.get("counts", [])
            if counts and None not in counts and listed != sum(counts):
                fails.append("%s: Files listed %d should equal the sum of its areas' counts, %d" % (name, listed, sum(counts)))
        block_files = sum(int(AREA_RE.match(a.strip()).group(3)) for a in info["block"] if AREA_RE.match(a.strip()))
        _, m = find_line(lines, begin, NOT_READ_RE)
        if m:
            if (int(m.group(1)), int(m.group(2))) != (info["n"], block_files):
                fails.append("%s: Coverage says %s areas, %s files not read; the block holds %d areas, %d files" % (name, m.group(1), m.group(2), info["n"], block_files))
        elif info["n"] > 0:
            fails.append("%s: no line 'Areas not read: <n> areas, <m> files; see SWEEP IN PARTS at the top.' in Coverage" % name)
        whole_at, m = find_line(lines, begin, re.compile(r"^(?:- )?Whole repo:"))
        if whole_at is None:
            fails.append("%s: no 'Whole repo:' line in Coverage" % name)
        elif number == 1:
            w = WHOLE_RE.match(lines[whole_at].strip())
            if not w:
                fails.append("%s: Whole repo line should read 'Whole repo: <n> tracked files; <n> in folders skipped whole (<folder>/: <n>, <reason>; ...); <n> untracked', found %r" % (name, lines[whole_at].strip()))
            else:
                want = (layout["tracked"], skipped_total, len(layout["untracked"]))
                got = (int(w.group(1)), int(w.group(2)), int(w.group(4)))
                if got != want:
                    fails.append("%s: Whole repo expected %d tracked, %d skipped whole, %d untracked; found %d, %d, %d" % ((name,) + want + got))
                for folder, count in layout["skipped_whole"].items():
                    fm = re.search(re.escape(folder) + r"`?:\s*(\d+)", w.group(3))
                    if not fm or int(fm.group(1)) != count:
                        fails.append("%s: Whole repo should give '%s: %d' inside the parentheses, found %r" % (name, folder, count, w.group(3)))
            rest = "\n".join(lines[whole_at:])
            absent = [p for p in layout["untracked"] if not re.search(r"(?<![\w./-])" + re.escape(p) + r"(?![\w/-])", rest)]
            if absent:
                fails.append("%s: Whole repo should name the untracked paths; missing %s" % (name, ", ".join(absent)))
        else:
            if lines[whole_at].strip().lstrip("- ").rstrip() != WHOLE_LATER:
                fails.append("%s: expected %r, found %r" % (name, WHOLE_LATER, lines[whole_at].strip()))
            named = [p for p in layout["untracked"] if re.search(r"(?<![\w./-])" + re.escape(p) + r"(?![\w/-])", info["text"])]
            if named:
                later_named.append("NOTE: %s names an untracked path that only part 1 should list: %s" % (name, ", ".join(named)))

    # area size
    for info in infos:
        for area, count in info["areas"]:
            if count > AREA_MAX:
                fails.append("area size: %s: area %r rebuilds to %d files, over the area size of %d" % (info["name"], area, count, AREA_MAX))

    # read: the totals across the parts
    counted = "file_skips" in layout and "after_whole_folder_skips" in layout   # a key without the counts is only held to unread and failed
    skips_expected = sum(layout["file_skips"].values()) if counted else 0
    read_expected = layout["after_whole_folder_skips"] - skips_expected if counted else len(expected)
    totals = [(i["name"], i["listed"]) for i in infos if "listed" in i]
    for name, (_r, _s, failed, unread) in totals:
        if unread != 0:
            fails.append("read: %s says unread: %d, expected 0" % (name, unread))
        if failed != 0:
            fails.append("read: %s says failed: %d, expected 0" % (name, failed))
    read_got = sum(v[0] for _n, v in totals)
    if counted and totals and len(totals) == len([i for i in infos if i["shape"] is not None]):
        skipped_got = sum(v[1] for _n, v in totals)
        if skipped_got != skips_expected:
            fails.append("read: the skipped numbers add up to %d, expected %d (the key's file_skips)" % (skipped_got, skips_expected))
        if read_got != read_expected:
            fails.append("read: the read numbers add up to %d, expected %d (%d files after the whole-folder skips, less %d skipped)"
                         % (read_got, read_expected, layout["after_whole_folder_skips"], skips_expected))

    # part size
    notes = list(later_named)
    sizes = []
    if args.part_size is not None:
        counted = [(i, stated_counts(i["read"])) for i in infos if i["shape"] is not None and i["read"]]
        for i, counts in counted:
            if counts is None:
                continue
            sizes.append(sum(counts))
            if sum(counts) > args.part_size:
                fails.append("part size: %s holds %d files in %d areas, over the part size of %d" % (i["name"], sum(counts), len(counts), args.part_size))
        for (i, counts), (j, nxt) in zip(counted, counted[1:]):
            if counts is None or nxt is None or i["n"] == 0:
                continue
            if sum(counts) + nxt[0] <= args.part_size:
                notes.append("NOTE: %s holds %d files and left its next area, %s, which would have fit (%d + %d is at most %d); a refused spawn can end a part early"
                             % (i["name"], sum(counts), AREA_RE.match(j["read"][0].strip()).group(1), sum(counts), nxt[0], args.part_size))

    # facts
    alltext = "\n".join(p[2] for p in parts)
    reader_of = {}  # path -> the part whose areas read it
    for info in infos:
        for path in info["files"]:
            reader_of.setdefault(path, info)
    missing_facts = []
    for f in facts:
        reader = reader_of.get(str(f.get("path", "")).encode("utf-8"))
        if not token_found(f["token"], alltext):
            missing_facts.append(f)
            fails.append("facts: %s (%s, in %s) was not found in any part: expected %r" % (f.get("id", "?"), f.get("kind", "?"), f.get("path", "?"), f["token"]))
        elif reader is not None and not token_found(f["token"], reader["text"]):
            missing_facts.append(f)
            elsewhere = [p[1] for p in parts if token_found(f["token"], p[2])]
            fails.append("facts: %s (%s, in %s) was not found in %s, the part that read the file; only %s held it: expected %r"
                         % (f.get("id", "?"), f.get("kind", "?"), f.get("path", "?"), reader["name"], ", ".join(elsewhere), f["token"]))
    for d in decoys:
        if token_found(d["token"], alltext):
            hit = [p[1] for p in parts if token_found(d["token"], p[2])]
            fails.append("decoys: %s (%s, from %s) appears in %s: %r" % (d.get("id", "?"), d.get("why", "?"), d.get("path", "?"), ", ".join(hit), d["token"]))

    readers = None
    if events is not None:
        readers = check_transcript(events, args.repo, tracked, layout, infos, fails, notes)

    if fails:
        print("LOOP FAILED")
        for line in fails + notes:
            print(line)
        return 1
    print("LOOP PROVED")
    print("parts: %d; areas: %d; files covered: %d of %d; read: %d of %d; facts found: %d of %d; decoys found: 0 of %d"
          % (len(parts), read_area_count, len(covered), len(expected), read_got, read_expected, len(facts) - len(missing_facts), len(facts), len(decoys))
          + ("; largest part: %d files" % max(sizes) if sizes else "")
          + ("; readers: %d of %d, once each" % readers if readers else ""))
    for line in notes:
        print(line)
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except CantCheck as err:
        print("CAN'T CHECK: %s" % err)
        code = 2
    except SystemExit as err:
        code = 2 if err.code not in (0, None) else 0
    except Exception as err:
        print("CAN'T CHECK: internal error, %s: %s" % (type(err).__name__, err))
        code = 2
    sys.exit(code)
