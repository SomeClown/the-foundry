"""Pins for `investigate` reading a big repo in parts (design section 4, Task 5 of the big-sweep plan).

Each pin is a meaning-carrying phrase searched for inside the one section of `agents/investigate.md` where
the rule belongs, in the pattern of tests/test_investigate_batch1.py. A mutation test deletes the matched
phrase in memory and requires the pin to stop matching, so a rule that is deleted, or stated twice in its
section, fails. Around the pins: the fence (byte for byte), the fixed tokens (none split across a line),
the order of the sections, the leftovers of the old stop, and a report written exactly as the file's own
templates say, which the scorer in evals-expensive/check_parts.py must accept.

Nothing here starts a model session; the files are read as text. Standard library only, Python 3.9.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVESTIGATE = ROOT / "agents" / "investigate.md"
SCORER = ROOT / "evals-expensive" / "check_parts.py"


def raw():
    return INVESTIGATE.read_text(encoding="utf-8")


def sections(text):
    """Map each `##`/`###` heading to its whitespace-flattened body, up to the next heading."""
    parts = re.split(r"^(#{2,3} .*)$", text, flags=re.M)
    out = {}
    for heading, body in zip(parts[1::2], parts[2::2]):
        out[heading.lstrip("# ").strip()] = " ".join(body.split())
    return out


def without_match(body, pattern):
    m = re.search(pattern, body)
    return body[: m.start()] + body[m.end():]


# (item, section heading, regex). One regex per distinct instruction. Matched case-sensitively.
PINS = [
    # If You're an Area Lead
    ("lead skips the part-size parts of the list", "If You're an Area Lead", r"the list-building and part-size parts of \"Build the File List\""),
    ("lead skips A Sweep in Parts", "If You're an Area Lead", r"You also skip \"A Sweep in Parts\""),

    # If Your Brief Continues a Sweep
    ("marker is checked before the mode", "If Your Brief Continues a Sweep", r"check that before you pick a mode"),
    ("marker wins over the mode rules and known codebase", "If Your Brief Continues a Sweep", r"It wins over the mode rules and over \"known codebase\""),
    ("a continuing run is a full sweep of the named areas", "If Your Brief Continues a Sweep", r"the run is a full sweep of the areas the brief names"),
    ("orientation is repeated", "If Your Brief Continues a Sweep", r"Do \"How to Orient Yourself\" again, since you know nothing"),
    ("Pick a Mode and area building are skipped", "If Your Brief Continues a Sweep", r"Skip \"Pick a Mode\" and area building"),
    ("areas are taken in order and never re-split", "If Your Brief Continues a Sweep", r"Take the areas in the order given and don't re-split them"),
    ("a continuing run names no untracked file anywhere in its report, even one orientation shows", "If Your Brief Continues a Sweep", r"Name no untracked file anywhere in your report, even one your orientation shows you; part 1 listed them"),
    ("whole-folder skips are not redone", "If Your Brief Continues a Sweep", r"Don't redo the whole-folder skips"),
    ("the Instructions line is followed", "If Your Brief Continues a Sweep", r"Follow the brief's `Instructions:` line as part of the brief"),
    ("it goes on to Reading a Part", "If Your Brief Continues a Sweep", r"go to \"Reading a Part\" under \"A Sweep in Parts\""),

    # Build the File List
    ("the part size is 450", "Build the File List", r"The part size is 450 files"),
    ("full sweep judged on tracked files after whole-folder skips", "Build the File List", r"On a full sweep it's judged on tracked files after whole-folder skips"),
    ("scoped judged on the scoped set", "Build the File List", r"in scoped mode, on the scoped set"),
    ("at or under the part size is one report", "Build the File List", r"A list at or under it is one report, built as before"),
    ("above it, see A Sweep in Parts", "Build the File List", r"Above it, see \"A Sweep in Parts\""),
    ("no Agent: see When You Can't Spawn first", "Build the File List", r"\(without the `Agent` tool, see \"When You Can't Spawn\" first\)"),
    ("the part-size test comes before anything walks the list", "Build the File List", r"Make this test before anything walks the whole list"),
    ("a continuing run doesn't list untracked files, and the file says where to look", "Build the File List", r"\(a continuing run doesn't list them; see \"If Your Brief Continues a Sweep\"\)"),
    ("count first, then go to parts without building the list or wc -l", "Build the File List", r"on a full sweep, count first, and above the part size go to \"A Sweep in Parts\" without building the list or running `wc -l` over it"),
    ("part size and the split count the mode's list", "Build the File List", r"The part size, the 150-file split, the gap check, and Coverage's \"files listed\" all count the current mode's list, never the whole repo"),
    ("untracked files don't count toward the part size", "Build the File List", r"They don't count toward the part size or Coverage's \"files listed\""),
    ("untracked files go to 8. Coverage for where", "Build the File List", r"\"8\. Coverage\" says where"),

    # A Sweep in Parts (intro)
    ("above the part size the whole list isn't held", "A Sweep in Parts", r"Above the part size you don't hold the whole list"),
    ("areas come from folder counts", "A Sweep in Parts", r"build areas from folder counts, read the first ones that fit under the part size"),
    ("the rest is named in a block at the top that is sent back as the next brief", "A Sweep in Parts", r"name the rest in a block at the top of your report\. The session sends the block back as the next brief until nothing is left"),

    # Areas
    ("count by folder", "Areas", r"Count tracked files by folder"),
    ("whole-folder skips are by rule or by the brief, counted by reason", "Areas", r"Drop the folders skipped whole, by rule \(vendored code, build output, data\) or because the brief says to leave them out, counting them by reason"),
    ("areas of at most about 150 files, folders first", "Areas", r"Build areas of at most about 150 files from what's left, folders first"),
    ("a range only for a folder subfolders can't divide", "Areas", r"A range is used only for a folder, or a folder's direct files, with more than about 150 files that subfolders can't divide"),
    ("no area holds a skipped folder", "Areas", r"No area may hold a folder skipped whole"),
    ("area line notation", "Areas", r"Write each area as `- <name>: <definition> \(<n> files\)`"),
    ("example: folders joined by plus", "Areas", r"- api: `src/api/` \+ `src/auth/` \(141 files\)"),
    ("example: direct plus root", "Areas", r"- top: `src/` \(direct\) \+ \(root\) \(38 files\)"),
    ("example: except", "Areas", r"- web: `web/` except `web/vendor/` \(96 files\)"),
    ("example: range", "Areas", r"- data-1: `data/` from `data/a001\.py` to `data/k220\.py` \(150 files\)"),
    ("a definition is pieces joined by plus", "Areas", r"A definition is one or more pieces joined by ` \+ `"),
    ("piece: dir", "Areas", r"`dir/` is every tracked file under that folder"),
    ("piece: direct and root", "Areas", r"`dir/` \(direct\) is the tracked files directly in that folder, not in its subfolders\. \(root\) is the files at the root"),
    ("piece: except", "Areas", r"`dir/` except `dir/sub/` leaves a folder out\. It's how an area steps around a folder skipped whole"),
    ("piece: range in byte order, a comparison", "Areas", r"every file of that piece whose path sorts at or after `first` and at or before `last`, in byte order\. It's a comparison, not a search for those two lines"),
    ("not a git pathspec", "Areas", r"This is not a git pathspec"),
    ("count is files matched with no file-by-file skips", "Areas", r"The count is the number of tracked files the definition matches, with no file-by-file skips applied"),
    ("the parentheses hold the count and nothing else, with the example", "Areas", r"The parentheses hold that count and nothing else: `\(70 files\)`, never `\(70 files; 69 read\)`"),
    ("what was read and skipped goes on Files listed and the skip reasons", "Areas", r"What was read and what was skipped go on the `Files listed:` line and the skip reasons after it"),
    ("only paths go in backticks, root and direct are bare", "Areas", r"Only folder and file paths go in backticks\. `\(root\)` and `\(direct\)` are written bare"),
    ("areas ordered by byte order of the first path", "Areas", r"Order the areas by the byte order of each area's first path"),
    ("list command and wrapper", "Areas", r"`<list>` below is `git -c core\.quotepath=off ls-files`, with the brief's wrapper in place of `git`"),
    ("outside git the default find command", "Areas", r"`find \. \\\( -name \.git -o -name node_modules -o -name venv -o -name \.venv \\\) -prune -o -type f -print \| sed 's\|\^\\\./\|\|' \| LC_ALL=C sort`"),
    ("outside git, a bounded variant is allowed", "Areas", r"Outside a git repo it's this command, or a bounded variant of it"),
    ("the find command, default included, goes on Environment", "Areas", r"The find command you use, the default one included, goes on the `Environment:` line so every run lists the same way"),
    ("each piece runs the command under its own comment", "Areas", r"Each piece runs the command under its own comment"),
    ("several pieces run in one group, skips chain one except each", "Areas", r"An area with several pieces runs them in one `\{ \.\.\.; \}` group, and several skipped folders chain one `except` filter each"),
    ("find where a range ends with sed -n", "Areas", r"To find where a range should end, print the nth path of a piece with `<piece> \| sed -n '<n>p'`"),
    ("run the exactly-once check before reading", "Areas", r"On a first run, before you read anything, run the last command\. If it fails, fix the areas and check again\. Don't read while it fails"),

    # Reading a Part
    ("a part is the first areas that fit at or under the part size", "Reading a Part", r"A part is the first areas in order whose counts add up to at or under the part size"),
    ("whole areas only, never fewer than one", "Reading a Part", r"whole areas only, never fewer than one"),
    ("a continuing run picks its part on the brief's counts", "Reading a Part", r"A continuing run picks its part on the counts in its brief"),
    ("each picked area is rebuilt from its definition", "Reading a Part", r"Rebuild each area you picked from its definition with the commands above"),
    ("every area gets its own lead, even a small one", "Reading a Part", r"Every area in a part gets its own lead, even a small one, run one at a time as in \"Run the Readers\""),
    ("after rebuilding, the files skipped one by one are taken out and counted by reason", "Reading a Part", r"Then take out the files skipped one by one \(lock files, generated and build output, data and fixture files, binaries; the list in \"Build the File List\"\), count each by reason, and give each lead only what's left"),
    ("no reader is sent for a skipped file, by you or by a lead", "Reading a Part", r"No reader is sent for a skipped file, by you or by a lead"),
    ("the area line's count doesn't change, skips and all", "Reading a Part", r"The area line's count doesn't change: it's the definition's count, skips and all"),
    ("a file skipped one by one still counts in its area's count and in Files listed, under skipped, and is left out only of what the lead is given", "Reading a Part", r"A file skipped one by one still counts in its area's count and in `Files listed:`, where it goes under `skipped`; it is left out only of what the lead is given"),
    ("Files listed is the part's area counts summed, as Coverage says", "Reading a Part", r"`Files listed:` is the sum of the part's area counts, as \"8\. Coverage\" says"),
    ("a continuing run rebuilds each area it picked", "Reading a Part", r"A continuing run rebuilds each area it picked the same way"),
    ("a different count is read as found, with a Count changed line", "Reading a Part", r"If a count differs from the brief's, read what was found, and say so in Coverage with a `Count changed:` line"),
    ("a rebuilt area is dropped when it matches nothing or its count changed and is now over about 150", "Reading a Part", r"A rebuilt area that matches nothing, or whose count differs from the brief's and is now over about 150 files, is dropped"),
    ("a rebuilt area whose count matches the brief's is read, whatever its size", "Reading a Part", r"A rebuilt area whose count matches the brief's is read, whatever its size"),
    ("a dropped area isn't read, isn't under Areas read, counts for nothing, isn't back in the block", "Reading a Part", r"A dropped area isn't read, isn't under `Areas read:`, counts for nothing in `Files listed:`, and doesn't go back in the block"),
    ("a dropped area gets an Area dropped line and nothing replaces it", "Reading a Part", r"Say so in Coverage with an `Area dropped:` line, and pull nothing in to replace it"),
    ("the rest go back in the block in the order given", "Reading a Part", r"The rest of the areas go back in the block, in the order given"),

    # The Block
    ("every part carries the block, which is the whole next brief", "The Block", r"Every part carries this block, and it's the whole of the next brief"),
    ("the line goes at line 1, or line 2 under the flag", "The Block", r"goes at line 1 of your report, or line 2 under `NOT A PER-FILE READ`"),
    ("the report's sections follow the block", "The Block", r"the report's sections follow it as usual"),
    ("the last part says 0 with no lines under it", "The Block", r"The last part says `SWEEP IN PARTS: 0 areas not read`, with no lines under it"),
    ("a sweep that fits in one report never carries the block", "The Block", r"A sweep that fits in one report never carries the block"),
    ("work out the block's area lines before line 1 and count them", "The Block", r"Work out the block's area lines before you write line 1, and count them"),
    ("the n on line 1 is the number of area lines, no more and no fewer", "The Block", r"The `<n>` on line 1 is the number of area lines in the block, no more and no fewer"),
    ("the block's area lines are counted with a command, as Coverage says of every count, the printf example", "The Block", r"count them with a command, as \"8\. Coverage\" says of every count, for example `printf '%s\\n' '<area line>' '<area line>' \| wc -l`"),
    ("line 1 is written only after the number is in hand", "The Block", r"Write line 1 only after you have the number"),
    ("Environment carries the wrapper or the find command", "The Block", r"`Environment:` carries the git wrapper, or the find command outside git"),

    # A Scoped Read Above the Part Size
    ("a scoped set has no areas", "A Scoped Read Above the Part Size", r"A scoped set isn't made of folders, so it has no areas"),
    ("read the first part's worth, list the rest unread by path", "A Scoped Read Above the Part Size", r"Read the first part's worth, and list the rest unread by path in Coverage"),
    ("the first part's worth is the first 450 paths in byte order", "A Scoped Read Above the Part Size", r"The first part's worth is the first 450 paths of the scoped set in byte order"),
    ("the files-not-read line goes at 1 or 2", "A Scoped Read Above the Part Size", r"`SWEEP IN PARTS: <n> files not read` goes at line 1, or line 2 under `NOT A PER-FILE READ`"),
    ("the n in the files-not-read line counts every path Coverage lists unread", "A Scoped Read Above the Part Size", r"The `<n>` in that line counts every path Coverage lists unread"),
    ("CONTINUE SWEEP is for full sweeps only", "A Scoped Read Above the Part Size", r"`CONTINUE SWEEP` is for full sweeps only"),

    # When a Part Goes Wrong
    ("a refused spawn after the second refusal", "When a Part Goes Wrong", r"A spawn refused mid-part, after the second refusal"),
    ("an area whose lead never started goes back in the block with every later area", "When a Part Goes Wrong", r"an area whose lead never started goes back in the block, with every later area of this part"),
    ("a preview of a lead's return is a pointer to Check Before You Compile, not a second statement", "When a Part Goes Wrong", r"A lead's return that arrives as a preview isn't cut off; see \"Check Before You Compile\""),

    # Run the Readers
    ("readers go 10 at a time in one message", "Run the Readers", r"Send readers 10 at a time, in one message, and wait for all of them before sending the next 10"),
    ("leads go one at a time, never two in one message", "Run the Readers", r"Leads go one at a time: never two in one message"),
    ("a lead is started, its return awaited, then the next started", "Run the Readers", r"Start one, wait for its return, then start the next"),
    ("a sweep in parts takes its areas from its own section", "Run the Readers", r"A sweep in parts takes its areas from \"A Sweep in Parts\" instead"),

    # Check Before You Compile
    ("a cut-off lead return lacks AREA REPORT ENDS", "Check Before You Compile", r"Cut off means its return lacks `AREA REPORT ENDS`"),
    ("a lead's return that arrives as a preview isn't cut off", "Check Before You Compile", r"A return that arrives as a preview, with its full text saved to a file, isn't cut off"),
    ("the saved file is read for the whole return before judging", "Check Before You Compile", r"read the saved file for the whole return before judging it"),
    ("a lead that failed twice has its files listed unread by path", "Check Before You Compile", r"If that fails too, list every file in its area by path as unread in Coverage"),
    ("the failed-lead rule wins over the path check in every sweep", "Check Before You Compile", r"This rule wins over the path check above, in every sweep: you send no readers of your own for a failed lead's files"),
    ("quoting: a full sweep, one report or parts", "Check Before You Compile", r"On a full sweep, in one report or in parts, the report holds nothing drawn from the contents of a folder skipped whole or of an untracked file"),
    ("quoting: the whole tree may be searched, hits there are dropped", "Check Before You Compile", r"You may still search the whole tree for your own checks, but a hit in one of those places is dropped: not quoted, not listed in an inventory, not described in a gotcha or the Coupling Map"),
    ("quoting: Coverage is all the report says of them", "Check Before You Compile", r"Coverage is all the report says of them: a folder skipped whole is counted with its reason, and untracked files are listed by path \(in a sweep in parts, in part 1 only\)"),
    ("quoting: a hit in an unread area is a reference, not checked", "Check Before You Compile", r"A hit in an area a sweep in parts hasn't read yet is different: list it as a reference, not checked, and don't describe what's there"),
    ("quoting: a scoped read is unchanged", "Check Before You Compile", r"A scoped read searches the whole repo for coupling, as it always did"),
    ("quoting: a lead's checks stay in its area", "Check Before You Compile", r"An area lead's own checks stay inside its area"),

    # When You're an Area Lead
    ("a lead applies no part size", "When You're an Area Lead", r"Don't build a list, apply the part size, or split further"),
    ("the lead's findings come first, then the checklist, then AREA REPORT ENDS", "When You're an Area Lead", r"Your findings come first, under your area's name; the checklist comes after them; the last line of your return, after the checklist, is `AREA REPORT ENDS`"),

    # When You Can't Spawn
    ("the only first-line flag, with the parts line under it", "When You Can't Spawn", r"the only one is `NOT A PER-FILE READ`, and a `SWEEP IN PARTS` line goes under it"),
    ("no Agent on a first run: no parts at any size", "When You Can't Spawn", r"With no `Agent` on a first run, there are no parts, at any size"),
    ("no Agent on a first run: flagged single-agent read with per-folder counts", "When You Can't Spawn", r"Do the flagged single-agent read, with unread files as counts per folder, and never write a `SWEEP IN PARTS` line"),
    ("no Agent on a continuing run: a flagged read of the first part's worth, block kept", "When You Can't Spawn", r"With no `Agent` on a continuing run, do a flagged read of the first part's worth of the given areas, and still write the block with the rest"),
    ("no Agent on a continuing run: the report's shape", "When You Can't Spawn", r"The report has the flag on line 1, the block from line 2, the `Mode:` line as for any flagged single-agent read, an `Areas read:` list of the areas it read, and the `Files listed:` line as in any part"),
    ("no Agent on a continuing run: unread files in its areas are listed by path, not as counts per folder", "When You Can't Spawn", r"Unread files inside the areas it took on are listed by path, as in any part, not as counts per folder"),
    ("an unstarted lead goes back in the block, never in Coverage too", "When You Can't Spawn", r"The exception is an area lead that never started in a part: its area goes back in the block \(see \"When a Part Goes Wrong\"\), and the same files never sit both in the block and in Coverage"),

    # What to Produce
    ("the last line of every report, in every mode", "What to Produce", r"The last line of every report, in every mode, is `INVESTIGATE REPORT ENDS`"),

    # 8. Coverage
    ("Coverage is never omitted", "8. Coverage", r"Never omitted, and not subject to the rule above"),
    ("the counts are one line", "8. Coverage", r"every top-level report gives the counts as one line: `Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>`"),
    ("the identity", "8. Coverage", r"Files listed = read \+ skipped \+ failed \+ unread"),
    ("skip reasons follow on the next line", "8. Coverage", r"Skip reasons follow on the next line"),
    ("files listed is the sum of the part's area counts", "8. Coverage", r"Files listed is also the sum of this part's area counts"),
    ("every unread file by path, with two exceptions", "8. Coverage", r"Then every file left unread, by path, with two exceptions"),
    ("unread areas are named by their block line, never file by file", "8. Coverage", r"Areas this run never started are named by their one line in the block, never file by file"),
    ("untracked files in a part go under Whole repo in part 1 only", "8. Coverage", r"Untracked files on a full sweep are listed by path, except in a sweep in parts, where they go under the `Whole repo:` line in part 1 only; a later part names none, whatever its orientation shows"),
    ("notes that belong with the mode line come after Mode and before Files listed, one to a line", "8. Coverage", r"Notes that belong with the mode line \(a failed lead, refused spawns, a request you set aside\) come after the `Mode:` line and before the `Files listed:` line, one to a line"),
    ("a part of a full sweep has the part lines; a scoped read has none", "8. Coverage", r"In a part of a full sweep, Coverage also has these lines"),
    ("the part lines are plain text with no bullet", "8. Coverage", r"written as plain text with no bullet in front of `Areas read:` or `Areas not read:`"),
    ("Areas read has one line per area the part took on, each starting dash", "8. Coverage", r"`Areas read:` on its own line, then one line per area this part took on, each starting `- ` and in the notation from \"Areas\""),
    ("an area whose lead failed twice is on Areas read and counted unread", "8. Coverage", r"An area whose lead failed twice is on it too: its files are listed unread by path and counted as unread"),
    ("a continuing run copies the area lines exactly", "8. Coverage", r"In a continuing run each line is copied exactly as the brief gave it, apart from a count that changed"),
    ("the parentheses of an Areas read line hold the count alone", "8. Coverage", r"The parentheses hold the count alone, as in \"Areas\""),
    ("the mode line counts areas, not restarts", "8. Coverage", r"The mode line's N is the number of these area lines: it counts areas, not restarts"),
    ("the Areas not read line", "8. Coverage", r"`Areas not read: <n> areas, <m> files; see SWEEP IN PARTS at the top\.`"),
    ("the Areas not read line comes straight after the last area line", "8. Coverage", r"on the line straight after the last area line"),
    ("the Areas not read n is the same as line 1's", "8. Coverage", r"The `<n>` is the same as on line 1"),
    ("counts are added with a command, never in your head", "8. Coverage", r"Add counts with a command, never in your head: `echo \$\(\(\d+(?: \+ \d+)+\)\)`"),
    ("the command rule names the Areas not read m and Files listed", "8. Coverage", r"That goes for the `<m>` on the `Areas not read:` line, for `Files listed:` and the numbers after it"),
    ("the command rule covers any total of routes, commands or files", "8. Coverage", r"and for any total you give of routes, commands or files"),
    ("the Areas not read m is the sum of the block's area counts", "8. Coverage", r"The `<m>` is the sum of the block's area counts"),
    ("the Areas not read m is written as one number, never the working", "8. Coverage", r"written as one number \(`554 files`, never `488 \+ 66 = 554 files`\)"),
    ("a note goes on its own line, never starting with a dash", "8. Coverage", r"a note on its own line, never starting with `-`"),
    ("the Count changed line", "8. Coverage", r"`Count changed: <name>: found <n>, the brief said <m>\.`"),
    ("the Area dropped line", "8. Coverage", r"`Area dropped: <name>: now <n> files, the brief said <m>; not read\.`"),
    ("the Whole repo line in part 1", "8. Coverage", r"Part 1 only: `Whole repo: <n> tracked files; <n> in folders skipped whole \(<folder>/: <n>, <reason>; …\); <n> untracked`"),
    ("part 1 lists the untracked files by path", "8. Coverage", r"with the untracked files listed by path"),
    ("Whole repo counts every tracked file before any skip", "8. Coverage", r"The tracked files are every tracked file, before any skip"),
    ("later parts say Whole repo is given in part 1", "8. Coverage", r"Later parts: `Whole repo: given in part 1\.`"),
]

TOKENS = [
    "SWEEP IN PARTS: <n> areas not read",
    "SWEEP IN PARTS: <n> files not read",
    "SWEEP IN PARTS",
    "CONTINUE SWEEP",
    "END OF BLOCK",
    "INVESTIGATE REPORT ENDS",
    "AREA REPORT ENDS",
    "Areas not read:",
    "Areas read:",
    "Whole repo:",
    "Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>",
    "NOT A PER-FILE READ",
    "Count changed:",
    "Area dropped:",
    "Read only these files:",
]

# The fence in "Areas", byte for byte (the range line changed in fix round 1: the string joins force a string comparison).
FENCE = [
    "# count by top-level folder",
    "<list> | LC_ALL=C awk -F/ '{print (NF > 1 ? $1 \"/\" : \"(root)\")}' | LC_ALL=C sort | uniq -c",
    "# count one level down inside <dir>/",
    "<list> | LC_ALL=C awk -v d='<dir>/' 'index($0, d) == 1 {r = substr($0, length(d) + 1); i = index(r, \"/\"); print (i ? d substr(r, 1, i) : d \" (direct)\")}' | LC_ALL=C sort | uniq -c",
    "# <dir>/",
    "<list> | LC_ALL=C awk -v d='<dir>/' 'index($0, d) == 1'",
    "# <dir>/ (direct)",
    "<list> | LC_ALL=C awk -v d='<dir>/' 'index($0, d) == 1 && index(substr($0, length(d) + 1), \"/\") == 0'",
    "# (root)",
    "<list> | LC_ALL=C awk 'index($0, \"/\") == 0'",
    "# except <folder>/, after any piece above",
    "<piece> | LC_ALL=C awk -v x='<folder>/' 'index($0, x) != 1'",
    "# from <first> to <last>, after any piece above",
    "<piece> | LC_ALL=C awk -v a='<first>' -v b='<last>' '($0 \"\") >= (a \"\") && ($0 \"\") <= (b \"\")'",
    "# every file left after the whole-folder skips is in exactly one area",
    "diff <(<list> | LC_ALL=C awk -v x='<skipped>/' 'index($0, x) != 1') <({ <area 1>; <area 2>; <and so on>; } | LC_ALL=C sort) && echo \"each file in exactly one area\"",
]

CONTINUE_TEMPLATE = [
    "CONTINUE SWEEP",
    "Project: <copied from the block>",
    "Focus: <copied from the block>",
    "Environment: <copied from the block>",
    "Instructions: <copied from the block>",
    "Areas not read:",
    "<the block's area lines, copied as given>",
    "END OF BLOCK",
]

SCOPED_SENTENCE = ("> To read the rest, dispatch `investigate` again with the original brief, adding a line "
                   "`Read only these files:` and then the paths listed unread in Coverage, one per line.")


def fence_with(text, first_line):
    """The lines of the fenced block whose first line is first_line, or None."""
    for body in re.findall(r"^```[^\n]*\n(.*?)^```$", text, flags=re.M | re.S):
        lines = body.split("\n")
        if lines and lines[0] == first_line:
            return lines[:-1] if lines[-1] == "" else lines
    return None


def token_pattern(token):
    words = token.split()
    return r"\s+".join("(?:<n>|\\d+)" if w == "<n>" else re.escape(w) for w in words)


def split_occurrences(text, token):
    """Occurrences of the token (words joined by any whitespace) that break across a line."""
    return [m.group(0) for m in re.finditer(token_pattern(token), text) if "\n" in m.group(0)]


def whole_occurrences(text, token):
    return [m.group(0) for m in re.finditer(token_pattern(token), text) if "\n" not in m.group(0)]


class PartsPinsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = raw()
        cls.sections = sections(cls.text)

    def body(self, heading):
        self.assertIn(heading, self.sections, f"heading {heading!r} is gone")
        return self.sections[heading]

    def test_each_pin_is_present_in_its_section(self):
        for item, heading, pattern in PINS:
            with self.subTest(item=item):
                self.assertIsNotNone(re.search(pattern, self.body(heading)), f"'{item}' is missing from '{heading}'")

    def test_each_pin_fails_when_its_phrase_is_deleted(self):
        # Deleting the matched span must leave the pin unmatched: a rule stated twice in its section fails here too.
        for item, heading, pattern in PINS:
            with self.subTest(item=item):
                mutated = without_match(self.body(heading), pattern)
                self.assertIsNone(re.search(pattern, mutated), "the pin still holds with its phrase removed")

    def test_each_pin_is_scoped_to_its_section_a_move_to_another_section_fails(self):
        # Put the phrase into the wrong section only: the pin must not be satisfied by the move.
        for item, heading, pattern in PINS:
            with self.subTest(item=item):
                phrase = re.search(pattern, self.body(heading)).group(0)
                other = next(h for h in self.sections if h != heading and not re.search(pattern, self.sections[h]))
                moved = {h: (without_match(b, pattern) if h == heading else b) for h, b in self.sections.items()}
                moved[other] = moved[other] + " " + phrase
                self.assertIsNone(re.search(pattern, moved[heading]), f"'{item}' is satisfied outside '{heading}'")

    def test_every_heading_the_pins_name_exists_exactly_once(self):
        text = self.text
        for heading in {h for _, h, _ in PINS}:
            with self.subTest(heading=heading):
                pattern = r"^#{2,3} " + re.escape(heading) + r"$"
                self.assertEqual(len(re.findall(pattern, text, flags=re.M)), 1)

    # ------------------------------------------------------------ the shape of the file

    def test_the_sweep_in_parts_sections_come_in_order_between_the_file_list_and_the_readers(self):
        text = self.text
        order = [text.index("\n" + h + "\n") for h in (
            "## Build the File List", "## A Sweep in Parts", "### Areas", "### Reading a Part", "### The Block",
            "### A Scoped Read Above the Part Size", "### When a Part Goes Wrong", "## Run the Readers",
        )]
        self.assertEqual(order, sorted(order))

    def test_the_continue_section_sits_after_the_lead_section_and_before_orientation_and_modes(self):
        text = self.text
        order = [text.index("\n" + h + "\n") for h in (
            "## If You're an Area Lead", "## If Your Brief Continues a Sweep", "## How to Orient Yourself", "## Pick a Mode",
        )]
        self.assertEqual(order, sorted(order))

    def test_the_part_size_test_comes_before_anything_that_walks_the_list(self):
        section = self.text[self.text.index("\n## Build the File List\n"): self.text.index("\n## A Sweep in Parts\n")]
        above = section.index("**Above the part size.**")
        for later in ("Use `git ls-files`", "`wc -l`", "Skip lock files"):
            with self.subTest(later=later):
                self.assertLess(above, section.index(later))

    def test_the_part_size_is_450_everywhere_it_is_named(self):
        # One number, said the same way: no <P> left, no 300, no other part size.
        self.assertNotIn("<P>", self.text)
        self.assertEqual(sorted(set(re.findall(r"\b(?:300|450|500|600)\b", self.text))), ["450"])
        self.assertEqual(len(re.findall(r"\b450\b", " ".join(self.text.split()))), 2)

    def test_the_sum_example_in_coverage_is_real_shell_arithmetic_under_bash_and_zsh(self):
        found = re.findall(r"`(echo \$\(\([^`]*\)\))`", self.body_raw("### 8. Coverage"))
        self.assertEqual(len(found), 1, found)
        command = found[0]
        numbers = [int(n) for n in re.findall(r"\d+", command)]
        self.assertGreaterEqual(len(numbers), 2)
        shells = [["bash", "-c"]]
        if shutil.which("zsh"):
            shells.append(["zsh", "-f", "-c"])
        for shell in shells:
            with self.subTest(shell=shell[0]):
                proc = subprocess.run(shell + [command], capture_output=True, text=True, timeout=30)
                self.assertEqual((proc.returncode, proc.stdout.strip()), (0, str(sum(numbers))), proc.stderr)

    def test_the_block_count_example_is_real_shell_that_counts_the_area_lines_under_bash_and_zsh(self):
        found = re.findall(r"`(printf '%s\\n'[^`]*\| wc -l)`", self.body_raw("### The Block"))
        self.assertEqual(len(found), 1, found)
        self.assertEqual(len(re.findall(r"printf '%s", self.text)), 1)  # one example in the whole file
        template = found[0]
        self.assertEqual(template.count("'<area line>'"), 2)
        lines = ["- docs: `docs/` (22 files)", "- web: `web/` except `web/vendor/` (86 files)", "- top: `(root)` + `scripts/` (70 files)"]
        shells = [["bash", "-c"]]
        if shutil.which("zsh"):
            shells.append(["zsh", "-f", "-c"])
        for n in (2, 3):
            # two placeholders filled with two lines; for three, one more argument before the pipe
            command = template.replace("'<area line>'", "{}").format(*["'%s'" % l for l in lines[:2]])
            if n == 3:
                command = command.replace(" | wc -l", " '%s' | wc -l" % lines[2])
            for shell in shells:
                with self.subTest(lines=n, shell=shell[0]):
                    proc = subprocess.run(shell + [command], capture_output=True, text=True, timeout=30)
                    self.assertEqual((proc.returncode, proc.stdout.strip()), (0, str(n)), proc.stderr)

    # ------------------------------------------------------------ the fence

    def test_the_fence_holds_all_eight_comment_lines_and_every_command_byte_for_byte(self):
        fence = fence_with(self.body_raw("### Areas"), "# count by top-level folder")
        self.assertIsNotNone(fence, "the fence is gone")
        self.assertEqual(fence, FENCE)
        self.assertEqual(len([line for line in fence if line.startswith("# ")]), 8)

    def body_raw(self, heading):
        text = self.text
        at = text.index("\n" + heading + "\n")
        nxt = re.search(r"^#{2,3} ", text[at + 5:], flags=re.M)
        return text[at: at + 5 + nxt.start()] if nxt else text[at:]

    def test_the_range_line_is_the_string_comparison_one(self):
        fence = fence_with(self.body_raw("### Areas"), "# count by top-level folder")
        want = "<piece> | LC_ALL=C awk -v a='<first>' -v b='<last>' '($0 \"\") >= (a \"\") && ($0 \"\") <= (b \"\")'"
        self.assertIn(want, fence)
        self.assertNotIn("'$0 >= a && $0 <= b'", self.text)

    def test_the_fence_check_fails_when_any_line_is_dropped_or_changed(self):
        area = self.body_raw("### Areas")
        for i, line in enumerate(FENCE):
            with self.subTest(line=line[:50]):
                dropped = area.replace(line + "\n", "", 1)
                self.assertNotEqual(fence_with(dropped, "# count by top-level folder"), FENCE)
                changed = area.replace(line + "\n", line + " #\n", 1)
                self.assertNotEqual(fence_with(changed, "# count by top-level folder"), FENCE)
        old = area.replace("'($0 \"\") >= (a \"\") && ($0 \"\") <= (b \"\")'", "'$0 >= a && $0 <= b'")
        self.assertNotEqual(fence_with(old, "# count by top-level folder"), FENCE)

    def test_the_sed_sentence_follows_the_fence(self):
        area = self.body_raw("### Areas")
        after = " ".join(area[area.rindex("```", 0, area.index("An area with several pieces")):].split())
        self.assertRegex(after, r"An area with several pieces .* To find where a range should end, print the nth path of a piece with `<piece> \| sed -n '<n>p'`")

    # ------------------------------------------------------------ templates and one-line sentences

    def test_the_continuing_brief_template_is_exact(self):
        lines = fence_with(self.body_raw("## If Your Brief Continues a Sweep"), "CONTINUE SWEEP")
        self.assertEqual(lines, CONTINUE_TEMPLATE)

    def test_the_continuing_brief_template_check_fails_for_a_dropped_or_reordered_line(self):
        section = self.body_raw("## If Your Brief Continues a Sweep")
        for line in CONTINUE_TEMPLATE[1:]:
            with self.subTest(line=line[:40]):
                self.assertNotEqual(fence_with(section.replace(line + "\n", "", 1), "CONTINUE SWEEP"), CONTINUE_TEMPLATE)
        self.assertNotEqual(fence_with(section.replace("```\nCONTINUE SWEEP\n", "```\nCONTINUE  SWEEP\n"), "CONTINUE SWEEP"), CONTINUE_TEMPLATE)

    def test_the_block_template_carries_the_continue_sentence_on_one_line(self):
        lines = fence_with(self.body_raw("### The Block"), "SWEEP IN PARTS: 3 areas not read")
        self.assertIsNotNone(lines)
        self.assertEqual(lines[1], "To read the rest, dispatch `investigate` again. The brief is `CONTINUE SWEEP` on its first line, "
                                   "then every line from `Project:` to `END OF BLOCK`, copied as it stands.")
        self.assertEqual(lines[-1], "END OF BLOCK")
        self.assertEqual([line.split(":")[0] for line in lines[2:7]], ["Project", "Focus", "Environment", "Instructions", "Areas not read"])

    def test_the_scoped_sentence_is_on_one_line_verbatim(self):
        self.assertIn("\n" + SCOPED_SENTENCE + "\n", self.body_raw("### A Scoped Read Above the Part Size"))

    def test_the_scoped_sentence_check_fails_when_a_word_goes(self):
        section = self.body_raw("### A Scoped Read Above the Part Size")
        for word in ("original", "one per line", "Read only these files:", "paths listed unread in Coverage"):
            with self.subTest(word=word):
                self.assertNotIn("\n" + SCOPED_SENTENCE.replace(word, "", 1) + "\n", section)
                self.assertNotIn(SCOPED_SENTENCE, section.replace(word, "", 1))

    # ------------------------------------------------------------ fixed tokens

    def test_each_fixed_token_is_present_on_one_line(self):
        for token in TOKENS:
            with self.subTest(token=token):
                self.assertTrue(whole_occurrences(self.text, token), f"{token!r} appears nowhere on one line")

    def test_no_fixed_token_is_split_across_two_lines(self):
        for token in TOKENS:
            with self.subTest(token=token):
                self.assertEqual(split_occurrences(self.text, token), [])

    def test_the_split_check_fails_when_a_rewrap_breaks_a_token(self):
        for token in TOKENS:
            if " " not in token:
                continue
            with self.subTest(token=token):
                m = re.search(token_pattern(token), self.text)
                self.assertIsNotNone(m)
                first_space = m.start() + m.group(0).index(" ")
                rewrapped = self.text[:first_space] + "\n" + self.text[first_space + 1:]
                self.assertTrue(split_occurrences(rewrapped, token), "a re-wrap that splits the token goes unseen")

    # ------------------------------------------------------------ leftovers of the stop, and cost gates

    def test_nothing_of_the_old_stop_survives_under_any_spelling(self):
        flat = " ".join(self.text.split())
        pattern = (r"(?i)STOPPED BEFORE READING|500-file|\b500 files|rough cost|approved reading|go-ahead|approv|area breakdown|"
                   r"read no more file contents|exceeds \d|\b(?:300|500)\b|<P>|ask the (?:user|owner)|orchestrator will ask|"
                   r"above 500|over 500|stop wins")
        m = re.search(pattern, flat)
        self.assertIsNone(m, m.group(0) if m else "")

    def test_the_stop_pattern_catches_each_old_sentence(self):
        pattern = (r"(?i)STOPPED BEFORE READING|500-file|\b500 files|rough cost|approved reading|go-ahead|approv|area breakdown|"
                   r"read no more file contents|exceeds \d|\b(?:300|500)\b|<P>|ask the (?:user|owner)|orchestrator will ask|"
                   r"above 500|over 500|stop wins")
        for old in (
            "Reply with a first line of `STOPPED BEFORE READING: <N> files`, then the area breakdown.",
            "If the list exceeds 500 files and your brief doesn't say the user approved reading that many",
            "The 500-file stop, the 150-file split",
            "read no more file contents",
            "a rough cost: the number of readers",
            "You can't ask the user yourself, so the orchestrator will ask, and a go-ahead reaches you as a new brief.",
            "This stop wins over every other first line.",
            "Above 500 files with no `Agent`, stop anyway.",
            "The part size is 300 files.",
        ):
            with self.subTest(old=old[:50]):
                self.assertIsNotNone(re.search(pattern, old))

    def test_no_cost_figure_or_gate_in_the_file(self):
        flat = " ".join(self.text.split())
        m = re.search(r"(?i)\bcents?\b|\$\d+\.\d\d|\bprice|\bpricing|\bbudget|\bafford|get (?:an? )?(?:ok|okay|approval)|ask (?:first|before)|"
                      r"hold back because|too expensive|expensive", flat)
        self.assertIsNone(m, m.group(0) if m else "")

    # ------------------------------------------------------------ rules said once

    def test_a_mode_line_rule_is_not_stated_two_ways(self):
        flat = " ".join(self.text.split())
        self.assertNotRegex(flat, r"counts the leads this run started")
        self.assertEqual(len(re.findall(r"it counts areas, not restarts", flat)), 1)

    def test_the_quoting_rule_does_not_limit_the_search_to_a_part(self):
        self.assertNotRegex(" ".join(self.text.split()), r"in a part, this part's areas")

    def test_untracked_files_in_a_part_are_not_listed_by_path_in_a_second_way(self):
        # Untracked files are placed one way in a sweep in parts: by path under `Whole repo:`, in part 1 only. Three places say
        # "part 1 only" (Coverage twice, the quoting rule once), and the continuing brief says a later part names none anywhere.
        flat = " ".join(self.text.split())
        self.assertEqual(len(re.findall(r"part 1 only", flat, flags=re.I)), 3)
        by_section = dict((h, len(re.findall(r"part 1 only", b, flags=re.I))) for h, b in self.sections.items())
        self.assertEqual(dict((h, n) for h, n in by_section.items() if n), {"8. Coverage": 2, "Check Before You Compile": 1})
        self.assertIn("Name no untracked file anywhere in your report", self.sections["If Your Brief Continues a Sweep"])
        self.assertNotRegex(flat, r"(?i)untracked[^.]{0,80}\bevery part\b")
        # no sentence sends untracked files into a findings section of a part
        self.assertNotRegex(flat, r"(?i)untracked[^.]{0,80}(?:Feature Status|Gotchas|Findings)")

    def test_the_find_command_appears_once_with_its_default_and_goes_on_environment(self):
        flat = " ".join(self.text.split())
        self.assertEqual(flat.count("find . \\( -name .git -o -name node_modules -o -name venv -o -name .venv \\) -prune -o -type f -print"), 1)

    def test_the_failed_lead_rule_is_said_once(self):
        flat = " ".join(self.text.split())
        self.assertEqual(flat.count("you send no readers of your own for a failed lead's files"), 1)

    def test_the_preview_rule_is_said_once_and_only_where_a_one_report_sweep_looks(self):
        # The rule (a lead's return that arrives as a preview isn't cut off) is stated in "Check Before You Compile", which every sweep
        # reads; "When a Part Goes Wrong" only points there, so the two can't drift apart.
        flat = " ".join(self.text.split())
        self.assertEqual(len(re.findall(r"the saved file for the whole return before judging it", flat, flags=re.I)), 1)
        self.assertEqual(len(re.findall(r"arrives as a preview", flat)), 2)
        self.assertEqual(len(re.findall(r"with its full text saved to a file", flat)), 1)
        self.assertIn("the saved file for the whole return", self.sections["Check Before You Compile"])
        wrong = self.sections["When a Part Goes Wrong"]
        self.assertNotIn("saved", wrong)
        self.assertIn("see \"Check Before You Compile\"", wrong)

    def test_the_preview_rule_sits_beside_the_cut_off_definition(self):
        body = self.sections["Check Before You Compile"]
        self.assertEqual(body.index("Cut off means its return lacks `AREA REPORT ENDS`") < body.index("arrives as a preview")
                         < body.index("If that fails too, list every file"), True)


# ---------------------------------------------------------------- fix batch A of the final qa pass: the old inviting sentences are gone

# (item, pattern that must not match the file, the old sentence it is aimed at). Each pattern is shown to catch its old sentence.
OLD_SENTENCES = [
    ("1 an untracked-files ban that reads as a rule about Coverage only", r"Don't list untracked files",
     "Take the areas in the order given and don't re-split them. Don't list untracked files or redo the whole-folder skips."),
    ("3 a dispatch count with no subject", r"\bSend \d+ at a time",
     "Send 10 at a time, in one message, and wait for all of them before sending the next 10."),
    ("4 a rebuilt area dropped on size alone", r"rebuilt area over about 150",
     "A rebuilt area over about 150 files, or one that matches nothing, is dropped: it isn't read."),
    ("5 the exactly-once command for every run, not only a first one", r"(?<!On a first run, )[Bb]efore you read anything, run the last command",
     "Before you read anything, run the last command. If it fails, fix the areas and check again."),
    ("6 part lines for any part, scoped reads included", r"In a part, Coverage also has these lines",
     "In a part, Coverage also has these lines, written as plain text with no bullet in front of `Areas read:`."),
    ("8 two places that claim the line right after Mode", r"(?:on the line right after|in the note after) the `Mode:` line",
     "name the area in a note on the line right after the `Mode:` line."),
    ("8 the refusal count claiming the same line", r"(?:on the line right after|in the note after) the `Mode:` line",
     "and say how many in the note after the `Mode:` line."),
    ("9 the checklist as the first thing a lead returns", r"The checklist comes first",
     "The checklist comes first, and the last line of your return, after it, is `AREA REPORT ENDS`."),
    ("10 the skips applied after the lead sentence", r"Apply the file-by-file skips to the part's files",
     "Every area in a part gets its own lead. Apply the file-by-file skips to the part's files as in \"Build the File List\"."),
]


def precedes(body, first, second):
    a, b = re.search(first, body), re.search(second, body)
    return bool(a and b and a.start() < b.start())


class QaFixAOldSentencesTest(unittest.TestCase):
    """The ten items of qa-fix-A, the negative side: a sentence that invited the old behavior is gone, and the new order holds."""

    @classmethod
    def setUpClass(cls):
        cls.text = raw()
        cls.flat = " ".join(cls.text.split())
        cls.sections = sections(cls.text)

    def test_each_old_inviting_sentence_is_gone(self):
        for item, pattern, _old in OLD_SENTENCES:
            with self.subTest(item=item):
                m = re.search(pattern, self.flat)
                self.assertIsNone(m, m.group(0) if m else "")

    def test_each_negative_pattern_catches_the_old_sentence_it_is_aimed_at(self):
        for item, pattern, old in OLD_SENTENCES:
            with self.subTest(item=item):
                self.assertIsNotNone(re.search(pattern, old), "the pattern would not have caught the old text")

    def test_each_negative_pattern_fires_when_the_old_sentence_is_put_back(self):
        # a mutation of the file's text: append the old sentence to the end and the pattern must see it
        for item, pattern, old in OLD_SENTENCES:
            with self.subTest(item=item):
                self.assertIsNotNone(re.search(pattern, self.flat + " " + old))

    def test_the_exactly_once_command_is_for_a_first_run_only(self):
        # every mention of running the last command before reading carries "On a first run"
        found = re.findall(r"(.{0,20})efore you read anything, run the last command", self.flat)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].endswith("On a first run, b"), found)

    def test_the_continuing_run_has_one_untracked_ban_and_it_is_report_wide(self):
        body = self.sections["If Your Brief Continues a Sweep"]
        self.assertEqual(len(re.findall(r"untracked", body)), 1)  # one ban in the section, not a second way of saying it
        ban = re.search(r"Name no untracked file anywhere in your report[^.]*\.", body)
        self.assertIsNotNone(ban)
        self.assertNotIn("Coverage", ban.group(0))

    def test_the_skips_are_taken_out_before_the_lead_is_mentioned(self):
        body = self.sections["Reading a Part"]
        skips = r"take out the files skipped one by one"
        lead = r"Every area in a part gets its own lead"
        self.assertTrue(precedes(body, skips, lead))
        self.assertTrue(precedes(body, r"No reader is sent for a skipped file", lead))
        self.assertFalse(precedes(body, lead, skips))

    def test_the_order_check_fails_when_the_skips_sentence_moves_after_the_lead_sentence(self):
        body = self.sections["Reading a Part"]
        skips = re.search(r"Then take out the files skipped one by one.*?skips and all\.", body).group(0)
        lead = re.search(r"Every area in a part gets its own lead, even a small one, run one at a time as in \"Run the Readers\"\.", body).group(0)
        swapped = body.replace(skips, "@@").replace(lead, skips).replace("@@", lead)
        self.assertNotEqual(swapped, body)
        self.assertFalse(precedes(swapped, r"take out the files skipped one by one", r"Every area in a part gets its own lead"))

    def test_a_lead_returns_findings_then_the_checklist_then_the_last_line(self):
        body = self.sections["When You're an Area Lead"]
        order = [body.index(x) for x in ("under your area's name", "Also return a **file checklist**", "Your findings come first", "the checklist comes after them",
                                         "the last line of your return, after the checklist, is `AREA REPORT ENDS`")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(len(re.findall(r"is `AREA REPORT ENDS`", body)), 1)

    def test_the_mode_line_note_placement_is_said_once_and_the_two_notes_point_to_it(self):
        self.assertEqual(len(re.findall(r"come after the `Mode:` line and before the `Files listed:` line", self.flat)), 1)
        self.assertEqual(len(re.findall(r"a note that goes with the mode line \(see \"8\. Coverage\"\)", self.flat)), 2)
        self.assertEqual(len(re.findall(r"line right after the `Mode:`", self.flat)), 0)

    def test_the_scoped_read_has_no_part_lines_and_the_part_lines_are_for_a_part_of_a_full_sweep(self):
        self.assertEqual(len(re.findall(r"Coverage also has these lines", self.flat)), 1)
        self.assertIn("In a part of a full sweep, Coverage also has these lines", self.sections["8. Coverage"])

    def test_readers_and_leads_have_their_own_dispatch_rules_in_run_the_readers(self):
        body = self.sections["Run the Readers"]
        self.assertTrue(precedes(body, r"Send readers 10 at a time", r"Leads go one at a time: never two in one message"))
        self.assertEqual(len(re.findall(r"Leads go one at a time", body)), 1)  # a pointer, not a second statement of the rule


# ---------------------------------------------------------------- a report written from the templates, scored


def load_scorer():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_parts_under_test", str(SCORER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def template_lines():
    """Every line the synthetic report copies from the agent file's own templates, extracted, not retyped."""
    text = raw()
    flat_sections = sections(text)
    cov = flat_sections["8. Coverage"]
    block = fence_with(text[text.index("\n### The Block\n"):], "SWEEP IN PARTS: 3 areas not read")
    areas = flat_sections["Areas"]

    def code(pattern, haystack):
        m = re.search(pattern, haystack)
        assert m, pattern
        return m.group(1)

    return {
        "block": block,
        "zero": code(r"`(SWEEP IN PARTS: 0 areas not read)`", flat_sections["The Block"]),
        "area": code(r"Write each area as `(- <name>: <definition> \(<n> files\))`", areas),
        "mode": code(r"`(Mode: full sweep, <N> area leads)`", cov),
        "listed": code(r"(Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>)`", cov),
        "areas_read": code(r"`(Areas read:)` on its own line", cov),
        "not_read": code(r"`(Areas not read: <n> areas, <m> files; see SWEEP IN PARTS at the top\.)`", cov),
        "whole_1": code(r"Part 1 only: `(Whole repo: .*? untracked)`", cov),
        "whole_later": code(r"Later parts: `(Whole repo: given in part 1\.)`", cov),
        "last": code(r"every report, in every mode, is `(INVESTIGATE REPORT ENDS)`", flat_sections["What to Produce"]),
    }


def fill(template, **values):
    """Replace <name> placeholders; <n> takes a list of values in order of appearance, or one value for all."""
    n = values.pop("n", None)
    if n is not None:
        seq = iter(n if isinstance(n, list) else [n] * template.count("<n>"))
        template = re.sub(r"<n>", lambda _m: str(next(seq)), template)
    for key, val in values.items():
        template = template.replace("<%s>" % key, str(val))
    return template


TRACKED = ["a/x.py", "a/y.py", "b/z.py", "c/w.py", "vendor/v.js"]
AREAS = [("a", "`a/`", 2), ("b", "`b/`", 1), ("c", "`c/`", 1)]
UNTRACKED = ["scratch.md"]


class ReportFromTemplatesIsAcceptedByTheScorerTest(unittest.TestCase):
    """A report written exactly as the file's templates say must parse under evals-expensive/check_parts.py.
    If it doesn't, the scorer and the text disagree and one of them has a bug."""

    @classmethod
    def setUpClass(cls):
        cls.t = template_lines()
        cls.scorer = load_scorer()

    def area_line(self, name, definition, count):
        return fill(self.t["area"], name=name, definition=definition, n=count)

    def part(self, number, *, mutate=None):
        """Part `number` of a 3-part sweep (a, b, c read one at a time), built from the templates."""
        read = AREAS[number - 1]
        rest = AREAS[number:]
        block = list(self.t["block"])
        if rest:
            first = block[0].replace("3 areas", "%d areas" % len(rest))
            head = [first, block[1], "Project: a toy repo", "Focus: none", "Environment: none", "Instructions: none", "Areas not read:"]
            area_lines = [self.area_line(*a) for a in rest]
            lines = head + area_lines + ["END OF BLOCK"]
        else:
            lines = [self.t["zero"]]
        lines += ["", "### 1. Project Identity", "A toy repo.", "", "### 8. Coverage"]
        lines.append(fill(self.t["mode"], N=1))
        lines.append(fill(self.t["listed"], n=[read[2], read[2], 0, 0, 0, 0]))
        lines.append("Skip reasons: none in this part.")
        lines.append(self.t["areas_read"])
        lines.append(self.area_line(*read))
        lines.append(fill(self.t["not_read"], n=len(rest), m=sum(a[2] for a in rest)))
        if number == 1:
            whole = fill(self.t["whole_1"], n=[5, 1, 1, 1], folder="vendor", reason="vendored").replace("; …", "")
            lines.append(whole)
            lines += ["- " + p for p in UNTRACKED]
        else:
            lines.append(self.t["whole_later"])
        lines += ["", self.t["last"]]
        text = "\n".join(lines) + "\n"
        return mutate(number, text) if mutate else text

    def score(self, mutate=None):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "repo" / "bin").mkdir(parents=True)
            git = base / "repo" / "bin" / "git"
            git.write_text("#!/bin/sh\nprintf '%s\\n' " + " ".join("'%s'" % p for p in TRACKED) + "\n", encoding="utf-8")
            git.chmod(git.stat().st_mode | stat.S_IXUSR)
            key = {
                "facts": [{"id": "f1", "kind": "route", "path": "a/x.py", "line": 1, "token": "TOKENONE"}],
                "decoys": [{"id": "d1", "why": "vendored", "path": "vendor/v.js", "token": "DECOYONE"}],
                "layout": {"tracked": 5, "skipped_whole": {"vendor/": 1}, "untracked": UNTRACKED},
            }
            (base / "key.json").write_text(json.dumps(key), encoding="utf-8")
            parts = base / "parts"
            parts.mkdir()
            for n in (1, 2, 3):
                text = self.part(n, mutate=mutate)
                if n == 1:
                    text = text.replace("A toy repo.", "A toy repo. Route TOKENONE is here.", 1)
                (parts / ("part-%d.md" % n)).write_text(text, encoding="utf-8")
            done = subprocess.run([sys.executable, "-I", str(SCORER), "--key", str(base / "key.json"), "--repo", str(base / "repo"), "--parts", str(parts)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=60)
            return done.returncode, done.stdout

    def test_the_templates_are_extracted_from_the_file_itself(self):
        self.assertEqual(self.t["block"][0], "SWEEP IN PARTS: 3 areas not read")
        self.assertEqual(self.t["block"][-1], "END OF BLOCK")
        self.assertEqual(self.t["zero"], "SWEEP IN PARTS: 0 areas not read")
        self.assertEqual(self.t["last"], "INVESTIGATE REPORT ENDS")

    def test_a_three_part_report_written_from_the_templates_is_accepted(self):
        code, out = self.score()
        self.assertEqual((code, out.splitlines()[0] if out else ""), (0, "LOOP PROVED"), out)

    def test_each_part_passes_the_scorers_shape_check_on_its_own(self):
        for n in (1, 2, 3):
            with self.subTest(part=n):
                lines = [line.rstrip() for line in self.part(n).split("\n")]
                fails = []
                shape = self.scorer.check_shape("part-%d.md" % n, lines, fails)
                self.assertEqual(fails, [])
                self.assertIsNotNone(shape)
                self.assertEqual(shape[0], 3 - n)

    def test_every_template_line_parses_under_the_scorers_patterns(self):
        s = self.scorer
        part1 = self.part(1).split("\n")
        self.assertTrue(any(s.MODE_RE.match(line) for line in part1))
        self.assertTrue(any(s.LISTED_RE.match(line) for line in part1))
        self.assertTrue(any(s.NOT_READ_RE.match(line) for line in part1))
        self.assertTrue(any(s.WHOLE_RE.match(line) for line in part1))
        self.assertTrue(any(s.AREA_RE.match(line) for line in part1))
        self.assertEqual(self.part(2).split("\n").count(s.WHOLE_LATER), 1)

    def test_the_scorer_is_not_vacuous_a_report_that_breaks_a_template_rule_fails(self):
        cases = {
            "a bullet before Areas read": lambda n, t: t.replace("\nAreas read:\n", "\n- Areas read:\n"),
            "a bullet before Areas not read": lambda n, t: t.replace("\nAreas not read: ", "\n- Areas not read: ") if n < 3 else t,
            "the last line missing": lambda n, t: t.replace("INVESTIGATE REPORT ENDS\n", ""),
            "the identity broken": lambda n, t: t.replace("skipped: 0; re-dispatched: 0; failed: 0; unread: 0", "skipped: 1; re-dispatched: 0; failed: 0; unread: 0"),
            "the block's Instructions line gone": lambda n, t: t.replace("Instructions: none\n", "") if n == 1 else t,
            "an untracked path named in a later part": lambda n, t: t.replace("Whole repo: given in part 1.", "Whole repo: given in part 1. scratch.md") if n == 2 else t,
            "a nonzero count under the last part's line": lambda n, t: t.replace("SWEEP IN PARTS: 0 areas not read\n", "SWEEP IN PARTS: 0 areas not read\nAreas not read:\n") if n == 3 else t,
        }
        for why, mutate in cases.items():
            with self.subTest(why=why):
                code, out = self.score(mutate)
                self.assertEqual(code, 1, out)


if __name__ == "__main__":
    unittest.main()
