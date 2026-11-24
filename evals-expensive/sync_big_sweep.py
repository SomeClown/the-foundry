"""Writes the big-sweep answer key, its graders and the six reply-size cases.

The fixture's scaffold is the source of truth. This asks it for the key
(`scaffold.sh --emit-key`), then writes `big-sweep-key.json` and the case's
graders, so they can't drift from the fixture. It also writes the six
`reply-size-*` cases whole (scaffold copy, case.yaml, prompt.md, graders), so
`--check` covers every file in them. Run it after any change to the scaffold:

    python3 evals-expensive/sync_big_sweep.py

`--check` writes nothing: it names every file that differs from what's
committed and exits 1, or exits 0 when none does. `--out DIR` writes somewhere
else (the tests use it). Standard library only.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE = "big-sweep-in-parts"
SCAFFOLD = HERE / CASE / "scaffold.sh"
SUBSET_LINE = 'SUBSET=""'

# Case folder suffix -> the SUBSET value its scaffold copy carries (empty: the full repo).
REPLY_SIZES = [("150", "150"), ("230", "230"), ("320", "320"), ("400", "400"), ("450", "450"), ("full", "")]

CASE_YAML = 'schema_version: "1.1"\nname: %s\ncontext:\n  scaffold_script: scaffold.sh\n'

REPLY_PROMPT = (
    "---\nruns: 1\ntags: [reply-size]\nmax_turns: 12\ntimeout_seconds: 3600\n"
    "allowed_tools: [Agent, Read, Glob, Grep, Bash]\n---\n\n"
    "Dispatch the the-foundry:investigate agent on the repo in the current directory with the brief below, "
    "and wait for it. Then, before anything else, write two lines. Line 1: `RECEIVED: whole` if the agent "
    "result you got ends with the line `TAIL-MARK-6620`, otherwise `RECEIVED: preview`, followed by the "
    "notice that came with the result, quoted word for word. Line 2: `SAVED OUTPUT: read`, "
    "`SAVED OUTPUT: blocked` (and what blocked it), or `SAVED OUTPUT: none`; if there was a saved file, "
    "try to open it with Read before you write this line. Then reply with the report, complete and word "
    "for word, from the saved output if that's where the whole text is, adding only a last line that says "
    "END-OF-REPORT. Don't read the code yourself.\n\n"
    "Brief for the agent: \"This is a new codebase to me, and I need to understand the whole thing. In this "
    "sandbox the plain `git` command is blocked: use `./bin/git` wherever you'd type `git`, and tell any "
    "agent you brief to do the same. In the route inventory, give every route its full path on its own line, "
    "never grouped under a prefix. Give every CLI subcommand as `twctl <name>`. When a gotcha's source cites a "
    "ticket, incident, change number, or named event, quote that reference word for word next to the gotcha. "
    "The user approved reading every file, whatever the count. Make the "
    "last line of your report exactly `TAIL-MARK-6620`.\"\n"
)

KEEP_REPORT = (
    "---\ntype: llm\nfocus: last_message\n---\n\n"
    "PASS only if the message is a codebase report with section headings. FAIL if it's a refusal or a short summary.\n"
)

NO_ASKING_RUBRIC = (
    "PASS only if the message lists saved report files and does not ask the user whether to continue, "
    "for permission, or for approval of a size or cost. FAIL if it asks any of those or stops with parts "
    "unread and no failure named."
)


def regex_grader(target, pattern, match):
    return "---\ntype: regex\ntarget: %s\npattern: %s\nmatch: %s\n---\n" % (target, pattern, match)


def load_key():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "key.json"
        subprocess.run(["bash", str(SCAFFOLD), "--emit-key", str(path)], check=True)
        return path.read_text(encoding="utf-8")


def scaffold_copy(subset):
    """The big-sweep scaffold with only line 14's SUBSET value changed."""
    with open(str(SCAFFOLD), encoding="utf-8", newline="") as handle:
        text = handle.read()
    lines = text.split("\n")
    if lines[13] != SUBSET_LINE:
        raise SystemExit("CAN'T SYNC: line 14 of the scaffold is not %s" % SUBSET_LINE)
    lines[13] = 'SUBSET="%s"' % subset
    return "\n".join(lines)


def reply_size_files():
    files = {}
    for suffix, subset in REPLY_SIZES:
        name = "reply-size-" + suffix
        files[name + "/case.yaml"] = CASE_YAML % name
        files[name + "/prompt.md"] = REPLY_PROMPT
        files[name + "/scaffold.sh"] = scaffold_copy(subset)
        files[name + "/graders/keep-report.md"] = KEEP_REPORT
        files[name + "/graders/received-line.md"] = regex_grader("last_message", '"RECEIVED: (whole|preview)"', "contains")
        files[name + "/graders/saved-line.md"] = regex_grader("last_message", '"SAVED OUTPUT: (read|blocked|none)"', "contains")
    return files


def expected():
    """Everything this script owns, as {path relative to evals-expensive: text}."""
    graders = CASE + "/graders/"
    files = reply_size_files()
    files.update({
        "big-sweep-key.json": load_key(),
        graders + "continued.md": "---\ntype: tool_used\ntool: Agent\ninput_match: CONTINUE SWEEP\nmin: 2\n---\n",
        graders + "finished.md": regex_grader("trace", '"SWEEP IN PARTS: 0 areas not read"', "contains"),
        graders + "parts-saved.md": "---\ntype: file_exists\npath: parts/part-1.md\n---\n",
        graders + "roster.md": regex_grader("trace", '"the-foundry:file-reader"', "contains"),
        graders + "no-fallback.md": regex_grader("last_message", '"NOT A PER-FILE READ"', "not_contains"),
        graders + "no-asking.md": "---\ntype: llm\nfocus: last_message\n---\n\n" + NO_ASKING_RUBRIC + "\n",
    })
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=HERE, help="folder to write into (default: evals-expensive)")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if any file differs from what's committed")
    args = parser.parse_args()
    files = expected()
    if args.check:
        differ = []
        for rel, text in sorted(files.items()):
            path = HERE / rel
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                differ.append(rel)
        for rel in differ:
            print("differs: evals-expensive/%s" % rel)
        if differ:
            return 1
        print("%d files match" % len(files))
        return 0
    wanted = {args.out / rel for rel in files}
    folders = {args.out / CASE / "graders"}
    folders.update(args.out / rel.rsplit("/", 1)[0] for rel in files if rel.startswith("reply-size-"))
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
        if folder.name == "graders":
            for stale in folder.glob("*.md"):
                if stale not in wanted:
                    stale.unlink()
    for path in sorted(wanted):
        with open(str(path), "w", encoding="utf-8", newline="") as handle:
            handle.write(files[str(path.relative_to(args.out))])
        if path.name == "scaffold.sh":
            path.chmod(0o755)
    print("wrote %d files under %s" % (len(files), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
