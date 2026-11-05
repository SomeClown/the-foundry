"""Writes the head-to-head answer key and its graders from the scaffold's key.

The fixture's scaffold is the source of truth. This asks it for the key
(`scaffold.sh --emit-key`), then writes `head-to-head-key.json` and one grader
per planted fact plus the control graders, so the graders can't drift from the
fixture. Run it after any change to the scaffold:

    python3 evals-expensive/sync_case.py

Standard library only. `--out DIR` writes somewhere else (the tests use it).
"""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE = "investigate-head-to-head"
SCAFFOLD = HERE / CASE / "scaffold.sh"
REGEX_SPECIALS = set("\\^$.*+?()[]{}|")

KEEP_RUBRIC = "PASS only if the message is a codebase report with section headings. FAIL if it's a refusal or a short summary."

CONTROLS = {
    "control-report-complete": ("last_message", "END-OF-REPORT", "contains"),
    "control-new-roster": ("trace", "the-foundry:file-reader", "contains"),
    "control-new-area-leads": ("last_message", "full sweep, ([2-9]|[1-9][0-9]+) area leads", "contains"),
    "control-new-no-fallback": ("last_message", "NOT A PER-FILE READ", "not_contains"),
    "control-new-untracked": ("last_message", "notes/untracked-scratch", "contains"),
}


def escape(token):
    """Escape for a JavaScript regex; slashes and dashes stay plain."""
    return "".join("\\" + ch if ch in REGEX_SPECIALS else ch for ch in token)


def regex_grader(target, pattern, match):
    return "---\ntype: regex\ntarget: %s\npattern: %s\nmatch: %s\n---\n" % (target, json.dumps(pattern), match)


def load_key():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "key.json"
        subprocess.run(["bash", str(SCAFFOLD), "--emit-key", str(path)], check=True)
        return path.read_text(encoding="utf-8")


def expected():
    """Everything this script owns, as {path relative to evals-expensive: text}."""
    key_text = load_key()
    key = json.loads(key_text)
    out = {"head-to-head-key.json": key_text}
    graders = CASE + "/graders/"
    for fact in key["facts"]:
        out[graders + "fact-%s.md" % fact["id"]] = regex_grader("last_message", escape(fact["token"]), "contains")
    for name, (target, pattern, match) in CONTROLS.items():
        out[graders + name + ".md"] = regex_grader(target, pattern, match)
    out[graders + "keep-report.md"] = "---\ntype: llm\nfocus: last_message\n---\n\n" + KEEP_RUBRIC + "\n"
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=HERE, help="folder to write into (default: evals-expensive)")
    args = parser.parse_args()
    files = expected()
    graders = args.out / CASE / "graders"
    graders.mkdir(parents=True, exist_ok=True)
    wanted = {args.out / rel for rel in files}
    for stale in graders.glob("*.md"):
        if stale not in wanted:
            stale.unlink()
    for path in wanted:
        path.write_text(files[str(path.relative_to(args.out))], encoding="utf-8")
    print("wrote %d files under %s" % (len(files), args.out))


if __name__ == "__main__":
    main()
