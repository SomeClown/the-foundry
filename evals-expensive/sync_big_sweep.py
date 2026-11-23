"""Writes the big-sweep answer key and its graders from the scaffold's key.

The fixture's scaffold is the source of truth. This asks it for the key
(`scaffold.sh --emit-key`), then writes `big-sweep-key.json` and the case's
graders, so they can't drift from the fixture. Run it after any change to the
scaffold:

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


def expected():
    """Everything this script owns, as {path relative to evals-expensive: text}."""
    graders = CASE + "/graders/"
    return {
        "big-sweep-key.json": load_key(),
        graders + "continued.md": "---\ntype: tool_used\ntool: Agent\ninput_match: CONTINUE SWEEP\nmin: 2\n---\n",
        graders + "finished.md": regex_grader("trace", '"SWEEP IN PARTS: 0 areas not read"', "contains"),
        graders + "parts-saved.md": "---\ntype: file_exists\npath: parts/part-1.md\n---\n",
        graders + "roster.md": regex_grader("trace", '"the-foundry:file-reader"', "contains"),
        graders + "no-fallback.md": regex_grader("last_message", '"NOT A PER-FILE READ"', "not_contains"),
        graders + "no-asking.md": "---\ntype: llm\nfocus: last_message\n---\n\n" + NO_ASKING_RUBRIC + "\n",
    }


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
    graders = args.out / CASE / "graders"
    graders.mkdir(parents=True, exist_ok=True)
    wanted = {args.out / rel for rel in files}
    for stale in graders.glob("*.md"):
        if stale not in wanted:
            stale.unlink()
    for path in sorted(wanted):
        path.write_text(files[str(path.relative_to(args.out))], encoding="utf-8")
    print("wrote %d files under %s" % (len(files), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
