"""Measures how big an agent's report can be and still reach the session that dispatched it.

    measure_reply.py --transcript FILE.jsonl --marker M
    measure_reply.py --harness aggregate-result.json --marker M

--transcript reads a `claude -p --output-format stream-json --verbose` transcript,
or a session transcript from ~/.claude/projects/. For every Agent/Task tool
result it prints one tab-separated line:

    depth (top|nested), subagent type, first line of the dispatch prompt,
    UTF-8 bytes of the result's text, whole|not-whole

A result is `whole` when the marker (or INVESTIGATE REPORT ENDS or AREA REPORT
ENDS, at either depth) is the last non-blank line of the
report text: the result with the harness's wrapper taken off, which is anything
from a line starting `agentId:` on and a `<tools-used-before-summary>` block. A
marker in the middle of a cut-off report doesn't count. A `not-whole` line adds the first 300
characters of the text on one line, which is where a preview notice shows. When
that text names a saved file ("Full output saved to: /path"), the line adds
three more fields: the path, the file's size in UTF-8 bytes, and saved-whole
(the marker is the file's last non-blank line), saved-not-whole, or
saved-missing. After the lines comes the final `result` message's text.

--harness reads a stored harness result and prints, for each run of each
reply-size-* case: the case, the RECEIVED: and SAVED OUTPUT: lines, the bytes of
the report between line 3 and END-OF-REPORT (from the keep-report evidence), and
whether the marker is in it. When the run's tracePath still exists it follows
with the transcript analysis of that file.

Exits 0 when it parsed something, 2 with `CAN'T MEASURE: <why>` when it didn't.
Standard library only.
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPORT_ENDS = ("INVESTIGATE REPORT ENDS", "AREA REPORT ENDS")
AGENT_ID_LINE = re.compile(r"^agentId:", re.MULTILINE)
TOOLS_USED = re.compile(r"<tools-used-before-summary>.*?</tools-used-before-summary>", re.DOTALL)
SAVED_TO = re.compile(r"saved to:[ \t]*([^\r\n]*)", re.IGNORECASE)
PREVIEW_CHARS = 300


class CantMeasure(Exception):
    """Nothing could be parsed; main() turns it into exit 2."""


def one_line(text):
    return " ".join(text.split())


def has_marker_line(text, markers):
    """True when any marker is a whole line of the text (surrounding blanks ignored)."""
    return any(line.strip() in markers for line in text.splitlines())


def report_text(text):
    """The result's text without the harness's wrapper: from the `agentId:` line on, and any tools-used block."""
    cut = AGENT_ID_LINE.search(text)
    if cut:
        text = text[:cut.start()]
    return TOOLS_USED.sub("", text)


def ends_with_marker(text, markers):
    """True when the last non-blank line of the report text is one of the markers."""
    lines = [line.strip() for line in report_text(text).splitlines() if line.strip()]
    return bool(lines) and lines[-1] in markers


def block_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def saved_path(text):
    match = SAVED_TO.search(text)
    if not match:
        return None
    path = match.group(1).strip().strip("`'\"").strip()
    return path or None


def saved_status(path, markers):
    """(size in bytes or None, saved-whole | saved-not-whole | saved-missing)."""
    target = Path(path).expanduser()
    try:
        data = target.read_bytes()
    except OSError:
        return None, "saved-missing"
    lines = [line.strip() for line in data.decode("utf-8", errors="replace").splitlines() if line.strip()]
    whole = bool(lines) and lines[-1] in markers
    return len(data), "saved-whole" if whole else "saved-not-whole"


def read_events(path):
    events = []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
    except OSError as err:
        raise CantMeasure("can't read %s (%s)" % (path, err.strerror or err))
    return events


def content_blocks(event):
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []


def analyse_transcript(path, marker):
    """Returns the output lines for a transcript; raises CantMeasure when there is no Agent result."""
    events = read_events(path)
    dispatches = {}
    lines = []
    final = None
    for event in events:
        kind = event.get("type")
        if kind == "result" and isinstance(event.get("result"), str):
            final = event["result"]
        if kind == "assistant":
            for block in content_blocks(event):
                if block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                    given = block.get("input") if isinstance(block.get("input"), dict) else {}
                    dispatches[block.get("id")] = (str(given.get("subagent_type") or "?"), str(given.get("prompt") or ""))
        elif kind == "user":
            nested = event.get("parent_tool_use_id") is not None or bool(event.get("isSidechain"))
            for block in content_blocks(event):
                if block.get("type") != "tool_result" or block.get("tool_use_id") not in dispatches:
                    continue
                agent, prompt = dispatches[block["tool_use_id"]]
                text = block_text(block.get("content"))
                first = (prompt.splitlines() or [""])[0].replace("\t", " ")
                fields = ["nested" if nested else "top", agent, first, str(len(text.encode("utf-8")))]
                markers = (marker,) + REPORT_ENDS
                if ends_with_marker(text, markers):
                    fields.append("whole")
                else:
                    fields.append("not-whole")
                    fields.append(one_line(text)[:PREVIEW_CHARS])
                    path_named = saved_path(text)
                    if path_named:
                        size, status = saved_status(path_named, (marker,) + REPORT_ENDS)
                        fields.extend([path_named, "-" if size is None else str(size), status])
                lines.append("\t".join(fields))
    if not lines:
        raise CantMeasure("no Agent or Task tool result in %s" % path)
    if final is not None:
        lines.append(final)
    return lines


def first_line_with(prefix, lines):
    for line in lines:
        if line.strip().startswith(prefix):
            return line.strip()
    return "(no %s line)" % prefix.rstrip(":")


def keep_report_evidence(run):
    for grader in run.get("graders") or []:
        if isinstance(grader, dict) and grader.get("name") == "keep-report" and isinstance(grader.get("evidence"), str):
            return grader["evidence"]
    return None


def analyse_harness(path, marker):
    markers = (marker,) + REPORT_ENDS
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as err:
        raise CantMeasure("can't read %s (%s)" % (path, err.strerror or err))
    except ValueError as err:
        raise CantMeasure("%s is not JSON (%s)" % (path, err))
    cases = data.get("cases") if isinstance(data, dict) else None
    out = []
    for case in cases if isinstance(cases, list) else []:
        name = str(case.get("name", "")) if isinstance(case, dict) else ""
        if not name.startswith("reply-size-"):
            continue
        arms = case.get("arms")
        runs = []
        if isinstance(arms, dict):
            for arm in arms.values():
                runs.extend(arm if isinstance(arm, list) else [])
        elif isinstance(arms, list):
            runs = arms
        for run in runs:
            if not isinstance(run, dict):
                continue
            evidence = keep_report_evidence(run)
            if evidence is None:
                out.append("\t".join([name, "(no keep-report evidence)", "-", "-", "-"]))
            else:
                lines = evidence.splitlines()
                report = []
                for line in lines[2:]:
                    if line.strip() == "END-OF-REPORT":
                        break
                    report.append(line)
                body = "\n".join(report)
                out.append("\t".join([
                    name,
                    first_line_with("RECEIVED:", lines),
                    first_line_with("SAVED OUTPUT:", lines),
                    str(len(body.encode("utf-8"))),
                    "marker-present" if has_marker_line(body, markers) else "marker-missing",
                ]))
            trace = run.get("tracePath")
            if not trace or not Path(str(trace)).is_file():
                out.append("trace: missing (%s)" % (trace or "no tracePath"))
                continue
            try:
                out.extend("  " + line for line in analyse_transcript(str(trace), marker))
            except CantMeasure as err:
                out.append("trace: CAN'T MEASURE: %s" % err)
    if not out:
        raise CantMeasure("no reply-size-* case with a run in %s" % path)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--transcript", help="a stream-json or session transcript (.jsonl)")
    source.add_argument("--harness", help="a harness aggregate-result.json")
    parser.add_argument("--marker", required=True, help="the line that ends the whole report")
    args = parser.parse_args()
    try:
        if args.transcript:
            lines = analyse_transcript(args.transcript, args.marker)
        else:
            lines = analyse_harness(args.harness, args.marker)
    except CantMeasure as err:
        print("CAN'T MEASURE: %s" % err)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
