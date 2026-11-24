#!/usr/bin/env python3
"""Scores a sweep read in parts: did part-1.md, part-2.md, ... cover the test repo exactly once and find every planted fact?

    check_parts.py --key KEY --repo FIXTURE_DIR --parts DIR [--min-parts N] [--part-size N]

Reads DIR/part-<n>.md in number order and checks, against the key and the fixture's tracked files:
  1. count          at least --min-parts part files
  2. shape          the SWEEP IN PARTS line, the block to END OF BLOCK, the last line
  3. order          n falls, the last part says 0, each block is a strict suffix of the one before,
                    and each part's "Areas read:" lines are exactly what the block dropped
  4. notation       every area line parses and its definition rebuilds to the stated count
  5. exactly once   the areas read hold every tracked file outside the whole-folder skips, once each
  6. coverage       the Mode, Files listed, Areas not read and Whole repo lines
  7. facts          every key fact is found in some part, and no decoy appears in any
  8. part size      only with --part-size N: the stated counts of each part's "Areas read:" lines add up to at most N
                    (a part with one area passes whatever its count); also prints a NOTE: line, never a failure, when a
                    part that isn't the last could have held the next area too

Exit 0 prints LOOP PROVED and a summary (with --part-size, the summary gives the largest part's file count); exit 1 prints LOOP FAILED and one line per failure; exit 2 prints
CAN'T CHECK: <why> (a missing file, an unreadable key, a crash). Standard library only, Python 3.9.

Tolerant of harmless whitespace (trailing spaces, Windows line endings, a blank line after the block), and
of a leading "- " on the Mode, Files listed and Whole repo lines. Exact about every fixed token and the notation.
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
DIR_PIECE = r"`(?P<d>[^`]+/)`(?: \((?P<direct>direct)\))?"
PIECE_RE = re.compile(
    r"(?:" + DIR_PIECE + r"|(?P<root>\(root\)))"
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
        pieces.append((m.group("d").encode("utf-8") if m.group("d") else None, m.group("direct") is not None, excepts,
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
    """The consecutive '- ' lines after lines[i], as (lines, index after them)."""
    out = []
    j = i + 1
    while j < len(lines) and lines[j].lstrip().startswith("-"):
        out.append(lines[j].strip())
        j += 1
    return out, j


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


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--key", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--parts", required=True)
    ap.add_argument("--min-parts", type=int, default=2)
    ap.add_argument("--part-size", type=positive_int, default=None)
    args = ap.parse_args(argv)

    facts, decoys, layout = load_key(args.key)
    tracked = tracked_files(args.repo)
    if len(tracked) != layout["tracked"]:
        raise CantCheck("the fixture tracks %d files, the key says %d; rebuild the fixture" % (len(tracked), layout["tracked"]))
    skipped_dirs = [d.encode("utf-8") for d in layout["skipped_whole"]]
    expected = set(p for p in tracked if not any(p.startswith(d) for d in skipped_dirs))
    parts = read_parts(args.parts)

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
        info = {"name": name, "text": text, "lines": lines, "shape": shape, "read": [], "read_idx": None, "heads": heads}
        infos.append(info)
        if shape is None:
            continue
        n, block, begin = shape
        info["n"], info["block"], info["begin"] = n, block, begin
        idx, _ = find_line(lines, begin, re.compile(r"^Areas read:$"))
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
    skipped_total = sum(layout["skipped_whole"].values())
    for number, info in zip(numbers, infos):
        if info["shape"] is None:
            continue
        name, lines, begin = info["name"], info["lines"], info["begin"]
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
                    fm = re.search(re.escape(folder) + r":\s*(\d+)", w.group(3))
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
                fails.append("%s: a later part must name no untracked path; found %s" % (name, ", ".join(named)))

    # part size
    notes = []
    sizes = []
    if args.part_size is not None:
        counted = [(i, stated_counts(i["read"])) for i in infos if i["shape"] is not None and i["read"]]
        for i, counts in counted:
            if counts is None:
                continue
            sizes.append(sum(counts))
            if sum(counts) > args.part_size and len(counts) > 1:
                fails.append("part size: %s holds %d files in %d areas, over the part size of %d" % (i["name"], sum(counts), len(counts), args.part_size))
        for (i, counts), (j, nxt) in zip(counted, counted[1:]):
            if counts is None or nxt is None or i["n"] == 0:
                continue
            if sum(counts) + nxt[0] <= args.part_size:
                notes.append("NOTE: %s holds %d files and left its next area, %s, which would have fit (%d + %d is at most %d); a refused spawn can end a part early"
                             % (i["name"], sum(counts), AREA_RE.match(j["read"][0].strip()).group(1), sum(counts), nxt[0], args.part_size))

    # facts
    alltext = "\n".join(p[2] for p in parts)
    missing_facts = [f for f in facts if not token_found(f["token"], alltext)]
    for f in missing_facts:
        fails.append("facts: %s (%s, in %s) was not found in any part: expected %r" % (f.get("id", "?"), f.get("kind", "?"), f.get("path", "?"), f["token"]))
    for d in decoys:
        if token_found(d["token"], alltext):
            hit = [p[1] for p in parts if token_found(d["token"], p[2])]
            fails.append("decoys: %s (%s, from %s) appears in %s: %r" % (d.get("id", "?"), d.get("why", "?"), d.get("path", "?"), ", ".join(hit), d["token"]))

    if fails:
        print("LOOP FAILED")
        for line in fails + notes:
            print(line)
        return 1
    print("LOOP PROVED")
    print("parts: %d; areas: %d; files covered: %d of %d; facts found: %d of %d; decoys found: 0 of %d"
          % (len(parts), read_area_count, len(covered), len(expected), len(facts) - len(missing_facts), len(facts), len(decoys))
          + ("; largest part: %d files" % max(sizes) if sizes else ""))
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
