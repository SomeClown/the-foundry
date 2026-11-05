#!/usr/bin/env python3
"""Scores the paid head-to-head: today's investigate against the per-file one.

    compare.py --key KEY --new RESULT [RESULT ...] --baseline RESULT [RESULT ...]
    compare.py --key KEY --summary RESULT

RESULT is an aggregate-result.json from the harness. Each run is at
cases[].arms.with[]; its report is the `evidence` of the `keep-report` grader
and its cost is costUsd + judgeCostUsd. KEY is head-to-head-key.json.

The bar (docs/design.md, Part 8), on the means across each arm's runs:
  1. new found is at least 90% of the planted facts
  2. new missed is at most half of baseline missed
  3. new made up is at most baseline made up

Exit 0 prints BAR MET, 1 prints BAR MISSED, 2 prints CAN'T SCORE: <why>. Any
crash while scoring is also a CAN'T SCORE, never an exit 1.

Found: a fact is found when its token appears, ignoring case, with any run of
whitespace (a line break too) standing for a space in the token, and with no
letter or digit just before it and no letter, digit or hyphen just after it.
The fact-* graders (sync_case.py) use the same rule; the two must agree.

Only runs of the investigate-head-to-head case count, and a file listed twice
counts once.

Made up counts each distinct item once per run: a route-shaped string that is
no real route (or strict prefix of one), an fxctl word that is no real command
and not plain prose (IGNORED_WORDS), a reference of one of the key's
code_shapes that is no real code, and a decoy route listed live. A decoy is
listed live when none of DEAD_WORDS is on its own line, on the next line (when
that is no new list item or heading), on an ancestor list item, on the
lead-in line of its list (when that ends with a colon), or on the nearest heading
or bold label line above. A decoy is judged by that rule alone, not also as an unknown route.

Standard library only.
"""

import argparse
import json
import os
import re
import sys
from fractions import Fraction

END = "END-OF-REPORT"
MIN_RUNS = 3
FOUND_SHARE = Fraction(9, 10)
ROUTE = re.compile(r"/v2/[a-z0-9_/-]*[a-z0-9]")
COMMAND = re.compile(r"\bfxctl ([A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*)")
# Whole words only: a hyphen joins words ("dead-letter" is not "dead"), except in these compounds.
DEAD_WORDS = re.compile(
    r"(?<![\w-])(?:commented[ -]out|taken[ -]out|no[ -]longer|commented|removed|disabled|dead|deprecated|inactive|"
    r"retired|obsolete|unused|legacy|stale|stub)(?![\w-])", re.I)
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)]|\|)\s")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
# A line that is only bold text, with an optional colon inside or after it.
LABEL = re.compile(r"^\s*(\*\*|__)(?:(?!\1).)+\1\s*:?\s*$")
IGNORED_WORDS = set((
    "command commands subcommand subcommands cli tool binary entry entrypoint group app program is and or the has was in on").split())
CASE = "investigate-head-to-head"
# JavaScript's \s, so the Python check and the harness's regex agree on what a space is.
SPACE = "[ \\t\\n\\v\\f\\r\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff]+"
NEW_MUST_PASS = ("control-new-roster", "control-new-area-leads", "control-new-no-fallback")
CONTROLS = ("control-report-complete",) + NEW_MUST_PASS + ("control-new-untracked",)


class CantScore(Exception):
    """A result the scorer can't score; the message says why."""


def token_found(token, text):
    """The found rule, the same one the fact-* grader pattern spells in JavaScript."""
    body = SPACE.join(re.escape(part) for part in re.split(" +", token))
    return re.search("(?:^|[^A-Za-z0-9])" + body + "(?![A-Za-z0-9-])", text, re.I | re.A) is not None


def line_without_routes(line):
    return ROUTE.sub(" ", line)


def has_dead_word(line):
    return DEAD_WORDS.search(line_without_routes(line)) is not None


def indent_of(line):
    return len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())


def is_label(line):
    """A line that is only bold text (and maybe a colon): it heads the lines under it like a heading."""
    return LABEL.match(line) is not None


def lead_in_line(lines, i):
    """The line that introduces the list block holding lines[i], when it ends with a colon, else None."""
    start = i
    for j in range(i - 1, -1, -1):
        line = lines[j]
        if not line.strip() or HEADING.match(line) or not (LIST_ITEM.match(line) or indent_of(line) > 0):
            break
        start = j
    j = start - 1
    if j >= 0 and not lines[j].strip():
        j -= 1
    if j < 0 or not lines[j].strip() or LIST_ITEM.match(lines[j]) or HEADING.match(lines[j]):
        return None
    return lines[j] if lines[j].rstrip(" *_`").endswith(":") else None


def decoy_listed_live(lines, i):
    """Whether the decoy on lines[i] is stated as live: no dead word near it."""
    if has_dead_word(lines[i]):
        return False
    if i + 1 < len(lines) and not LIST_ITEM.match(lines[i + 1]) and not HEADING.match(lines[i + 1]) and has_dead_word(lines[i + 1]):
        return False
    if LIST_ITEM.match(lines[i]):
        depth = indent_of(lines[i])
        for j in range(i - 1, -1, -1):
            line = lines[j]
            if HEADING.match(line) or is_label(line):
                break
            if LIST_ITEM.match(line):
                if indent_of(line) < depth:
                    if has_dead_word(line):
                        return False
                    depth = indent_of(line)
            elif line.strip() and indent_of(line) < depth:
                break
    if LIST_ITEM.match(lines[i]) or indent_of(lines[i]) > 0:
        lead_in = lead_in_line(lines, i)
        if lead_in is not None and has_dead_word(lead_in):
            return False
    for j in range(i - 1, -1, -1):
        if HEADING.match(lines[j]) or is_label(lines[j]):
            # Underscores are word characters, so the __ of a label is blanked before the marker is looked for.
            return not has_dead_word(lines[j].replace("__", " ") if is_label(lines[j]) else lines[j])
    return True


def made_up(text, key):
    """Every made-up item in a report, as (kind, item), each distinct item once."""
    routes = set(key["routes"])
    decoys = {d["token"] for d in key["decoys"]}
    known = routes | decoys
    found = []

    def add(kind, item):
        if (kind, item) not in found:
            found.append((kind, item))

    for m in ROUTE.finditer(text):
        route = m.group(0)
        if route in decoys:
            continue
        if route not in routes and not any(k.startswith(route) and k != route for k in known):
            add("route", route)
    for m in COMMAND.finditer(text):
        command = "fxctl " + m.group(1)
        if command not in key["commands"] and m.group(1).lower() not in IGNORED_WORDS:
            add("command", command)
    codes = set(key["codes"])
    for pattern in key["code_shapes"].values():
        for m in re.finditer(pattern, text):
            if m.group(0) not in codes:
                add("code", m.group(0))
    lines = text.splitlines()
    for i, line in enumerate(lines):
        for m in ROUTE.finditer(line):
            if m.group(0) in decoys and decoy_listed_live(lines, i):
                add("decoy", m.group(0))
    return found


def check_key(key):
    """The key must have the shape the scorer reads, so a bad one is a CAN'T SCORE and not a crash."""
    if not isinstance(key, dict):
        raise CantScore("the key is not a JSON object")
    for field in ("facts", "decoys"):
        items = key.get(field)
        if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
            raise CantScore("the key's %s is not a list of objects" % field)
    for fact in key["facts"]:
        if not all(isinstance(fact.get(f), str) for f in ("id", "token", "placement")):
            raise CantScore("a fact in the key lacks a text id, token or placement")
    if not key["facts"]:
        raise CantScore("the key has no facts")
    if not all(isinstance(d.get("token"), str) for d in key["decoys"]):
        raise CantScore("a decoy in the key lacks a text token")
    for field in ("routes", "commands", "codes"):
        items = key.get(field)
        if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
            raise CantScore("the key's %s is not a list of text" % field)
    shapes = key.get("code_shapes")
    if not isinstance(shapes, dict):
        raise CantScore("the key's code_shapes is not an object")
    for name, pattern in shapes.items():
        try:
            re.compile(pattern)
        except (re.error, TypeError) as e:
            raise CantScore("the key's code shape %r is not a regex: %s" % (name, e))


def load_runs(paths):
    """The runs of the head-to-head case in each distinct file, in order."""
    runs = []
    seen = set()
    for path in paths:
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            for case in doc["cases"]:
                if isinstance(case, dict) and case.get("name") == CASE:
                    found = case["arms"]["with"]
                    if not isinstance(found, list) or not all(isinstance(r, dict) for r in found):
                        raise TypeError("arms.with is not a list of runs")
                    runs.extend(found)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            raise CantScore("cannot read %s: %s" % (path, e))
    return runs


def grader_map(run, label):
    graders = run.get("graders")
    if not isinstance(graders, list) or not all(isinstance(g, dict) for g in graders):
        raise CantScore("%s has no graders list" % label)
    return {g.get("name"): g for g in graders}


def number(run, field, label):
    value = run.get(field)
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CantScore("%s has a %s that is not a number: %r" % (label, field, value))
    return float(value)


def score_run(run, key, label):
    """Scores one run, or raises CantScore saying why it can't."""
    if run.get("error") is not None:
        raise CantScore("%s has an error: %s" % (label, run["error"]))
    if run.get("skippedPaidGraders"):
        raise CantScore("%s has skippedPaidGraders true" % label)
    graders = grader_map(run, label)
    text = (graders.get("keep-report") or {}).get("evidence")
    if not isinstance(text, str) or not text.strip():
        raise CantScore("%s has missing evidence (no keep-report text)" % label)
    if END not in text:
        raise CantScore("%s evidence has no %s" % (label, END))
    ids = {fact["id"] for fact in key["facts"]}
    for name in graders:
        if isinstance(name, str) and name.startswith("fact-") and name[5:] not in ids:
            raise CantScore("%s has a %s grader the key doesn't list" % (label, name))
    found, missed = set(), []
    for fact in key["facts"]:
        name = "fact-" + fact["id"]
        grader = graders.get(name)
        if grader is None:
            raise CantScore("%s has no %s grader to check against" % (label, name))
        here = token_found(fact["token"], text)
        if bool(grader.get("passed")) != here:
            raise CantScore("%s: %s says %s but the report text says %s" % (
                label, name, "found" if grader.get("passed") else "not found", "found" if here else "not found"))
        if here:
            found.add(fact["id"])
        else:
            missed.append(fact)
    items = made_up(text, key)
    return {
        "label": label,
        "found": len(found),
        "missed": len(missed),
        "made_up": len(items),
        "missed_facts": missed,
        "made_up_items": items,
        "cost": number(run, "costUsd", label) + number(run, "judgeCostUsd", label),
        "seconds": number(run, "durationSeconds", label),
        "controls": {name: (graders[name].get("passed") if name in graders else None) for name in CONTROLS},
    }


def score_arm(name, paths, key):
    runs = load_runs(paths)
    if len(runs) < MIN_RUNS:
        raise CantScore("%s arm has fewer than %d runs (%d)" % (name, MIN_RUNS, len(runs)))
    scored = [score_run(run, key, "%s run %d" % (name, i)) for i, run in enumerate(runs, 1)]
    for s in scored:
        roster = s["controls"]["control-new-roster"]
        if name == "new":
            for control in NEW_MUST_PASS:
                if not s["controls"][control]:
                    raise CantScore("%s failed %s" % (s["label"], control))
        elif roster:
            raise CantScore("%s passed control-new-roster, so it ran the new agents" % s["label"])
    return scored


def mean(scored, field):
    return sum(Fraction(s[field]) for s in scored) / len(scored)


def row(s):
    return "%s: found %d missed %d made up %d cost $%.2f duration %.0fs" % (
        s["label"], s["found"], s["missed"], len(s["made_up_items"]), s["cost"], s["seconds"])


def print_made_up(s):
    for kind, item in s["made_up_items"]:
        print("  %s made up: %s %s" % (s["label"], kind, item))


def report(key, new, base):
    facts = len(key["facts"])
    print("Per-run rows")
    for s in new + base:
        print(row(s))
    print()
    means = {}
    for name, scored in (("new", new), ("baseline", base)):
        m = {f: mean(scored, f) for f in ("found", "missed", "made_up", "cost", "seconds")}
        means[name] = m
        print("%s mean: found %.2f missed %.2f made up %.2f cost $%.2f duration %.0fs" % (
            name, m["found"], m["missed"], m["made_up"], m["cost"], m["seconds"]))
        print("%s total cost $%.2f" % (name, sum(s["cost"] for s in scored)))
    print()
    n, b = means["new"], means["baseline"]
    clauses = (
        (1, "new found %.2f is at least 90%% of %d facts" % (n["found"], facts), n["found"] >= FOUND_SHARE * facts),
        (2, "new missed %.2f is at most half of baseline missed %.2f" % (n["missed"], b["missed"]), n["missed"] * 2 <= b["missed"]),
        (3, "new made up %.2f is at most baseline made up %.2f" % (n["made_up"], b["made_up"]), n["made_up"] <= b["made_up"]),
    )
    for number, what, ok in clauses:
        print("clause %d (%s): %s" % (number, what, "PASS" if ok else "FAIL"))
    print()
    placements = sorted({f["placement"] for f in key["facts"]})
    for name, scored in (("new", new), ("baseline", base)):
        for placement in placements:
            total = sum(1 for f in key["facts"] if f["placement"] == placement)
            missed = Fraction(sum(1 for s in scored for f in s["missed_facts"] if f["placement"] == placement), len(scored))
            print("%s missed %s: %.2f of %d facts per run" % (name, placement, missed, total))
    print()
    for s in new + base:
        print_made_up(s)
    for s in new:
        if s["controls"]["control-new-untracked"] is False:
            print("WARNING: %s failed control-new-untracked (it never named the untracked file)" % s["label"])
    return all(ok for _, _, ok in clauses)


def summary(key, path):
    runs = load_runs([path])
    if not runs:
        raise CantScore("%s holds no runs" % path)
    for i, run in enumerate(runs, 1):
        s = score_run(run, key, "run %d" % i)
        print(row(s))
        print_made_up(s)
        for name, passed in s["controls"].items():
            print("  %s: %s" % (name, "missing" if passed is None else "PASS" if passed else "FAIL"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score the investigate head-to-head.")
    parser.add_argument("--key", required=True)
    parser.add_argument("--new", nargs="+")
    parser.add_argument("--baseline", nargs="+")
    parser.add_argument("--summary")
    args = parser.parse_args(argv)
    if args.summary is None and not (args.new and args.baseline):
        parser.error("give --new and --baseline, or --summary")
    if args.summary is not None and (args.new or args.baseline):
        parser.error("--summary can't be combined with --new or --baseline")
    try:
        try:
            with open(args.key, encoding="utf-8") as f:
                key = json.load(f)
        except (OSError, ValueError) as e:
            raise CantScore("cannot read the key %s: %s" % (args.key, e))
        check_key(key)
        if args.summary is not None:
            summary(key, args.summary)
            return 0
        new = score_arm("new", args.new, key)
        base = score_arm("baseline", args.baseline, key)
        met = report(key, new, base)
    except CantScore as e:
        print("CAN'T SCORE: %s" % e)
        return 2
    except Exception as e:
        # An unhandled crash exits 1, which reads as BAR MISSED, so it must never get that far.
        print("CAN'T SCORE: scoring crashed (%s: %s)" % (type(e).__name__, e))
        return 2
    print("BAR MET" if met else "BAR MISSED")
    return 0 if met else 1


if __name__ == "__main__":
    sys.exit(main())
