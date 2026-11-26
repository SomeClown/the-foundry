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
    ("list command and wrapper", "Areas", r"`<list>` below is `git ls-files -z \| tr '\\n\\0' '\\001\\n'`, with the brief's wrapper in place of `git`"),
    ("outside git the default find command", "Areas", r"`find \. \\\( -name \.git -o -name node_modules -o -name venv -o -name \.venv \\\) -prune -o -type f -print0 \| tr '\\n\\0' '\\001\\n' \| sed 's\|\^\\\./\|\|' \| LC_ALL=C sort`"),
    ("outside git, a bounded variant is allowed", "Areas", r"Outside a git repo it's this command, or a bounded variant of it"),
    ("the find command, default included, goes on Environment", "Areas", r"The find command you use, the default one included, goes on the `Environment:` line so every run lists the same way"),
    ("each piece runs the command under its own comment", "Areas", r"Each piece runs the command under its own comment"),
    ("several pieces run in one group, skips chain one except each", "Areas", r"An area with several pieces runs them in one `\{ \.\.\.; \}` group, and several skipped folders chain one `except` filter each, before the `sort` on the listing side"),
    ("find where a range ends with sed -n", "Areas", r"To find where a range should end, print the nth path of a piece with `<piece> \| sed -n '<n>p'`"),
    ("run the exactly-once check before reading", "Areas", r"On a first run, before you read anything, run the last command\. If it fails, fix the areas and check again\. Don't read while it fails"),

    # Reading a Part
    ("a part is the first areas that fit at or under the part size", "Reading a Part", r"A part is the first areas in order whose counts add up to at or under the part size"),
    ("whole areas only, never fewer than one", "Reading a Part", r"whole areas only, never fewer than one"),
    ("a continuing run picks its part on the brief's counts", "Reading a Part", r"A continuing run picks its part on the counts in its brief"),
    ("each picked area is rebuilt from its definition", "Reading a Part", r"Rebuild each area you picked from its definition with the commands above"),
    ("every area gets its own lead, even a small one", "Reading a Part", r"Every area in a part gets its own lead, even a small one, run one at a time as in \"Run the Readers\""),
    ("after rebuilding, the files skipped one by one are taken out and counted by reason", "Reading a Part", r"Then take out the files skipped one by one \(lock files, generated and build output, data and fixture files, binaries, credential files; the list in \"Build the File List\"\), count each by reason, and give each lead only what's left"),
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
    ("the block's area lines are counted with a command, as Coverage says of every count, pasted into a here-document", "The Block", r"count them with a command, as \"8\. Coverage\" says of every count: paste the area lines, as they'll stand in the block, between `wc -l <<'/END'` and `/END`, since an area line holds paths and is never typed between quotes"),
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
    # the batch of 2026-11-24: paths go into commands without being typed into them, and a brief that arrives broken
    # Pick a Mode
    ("a Read only these files line is exactly the scope and replaces any other file list or scope", "Pick a Mode", r"A brief with a `Read only these files:` line reads exactly the paths under it; that list replaces any other file list or scope in the brief"),

    # Build the File List
    ("the file list prints every path on a line of its own: git ls-files -z through the line-break mapping", "Build the File List", r"Use `git ls-files -z \| tr '\\n\\0' '\\001\\n'`, which prints every path exactly as it is on a line of its own, a line break inside a path printed as the byte `\\001`, or a bounded `find` outside a git repo"),
    ("the untracked listing has the same mapping", "Build the File List", r"\(`git ls-files --others --exclude-standard -z \| tr '\\n\\0' '\\001\\n'`\) in Coverage as unread"),
    ("never type a path into a command, between quotes or not", "Build the File List", r"Never type a path into a command, between quotes or not"),
    ("the reason: a quote, a dollar-paren, a backtick or a backslash is read as code", "Build the File List", r"Paths come from the repo, and a quote, `\$\(`, a backtick or a backslash in one would be read by the shell or by `awk` as code"),
    ("paths come from a listing or a here-document that ends only at a line that is exactly /END, which no path is", "Build the File List", r"whose quoted `'/END'` makes the shell take every line as it is until a line that is exactly `/END`, which no path is"),
    ("line counts: a listing piped through tr and xargs -0, or paths pasted one per line with no indent", "Build the File List", r"Line counts go the same way: pipe a listing in, `<listing> \| tr '\\n' '\\0' \| xargs -0 wc -l --`, or, for paths you were given, paste them one per line, with no indent"),

    # Areas
    ("each path goes into a variable of its own, three lines per path, the trailing slash kept, no indent, never a line that reads /END", "Areas", r"Put each path a command needs into a variable of its own, `p1`, `p2` and so on, as \"Build the File List\" says of every path: one block of three lines per path, with the path on the middle line exactly as the listing printed it or the area line gives it, a folder's trailing `/` included, no indent, and never a path that reads `/END` \(see \"Build the File List\"\):"),
    ("the variables are set in the same Bash call as the commands", "Areas", r"Set the variables in the same Bash call as the commands that use them"),
    ("a command names its variable where the fence has a var placeholder", "Areas", r"with a variable's name where the command says `<dir var>`, `<folder var>`, `<first var>`, `<last var>` or `<skipped var>`"),
    ("awk reads the path from ENVIRON and the colon-question-mark stops the command on an empty variable", "Areas", r"`awk` reads the path from `ENVIRON`, which leaves backslashes alone, and `:\?` stops the command when a variable is empty"),
    ("a path with a backtick or a control character is never a piece, a skipped folder or a range end", "Areas", r"A path with a backtick or a control character in it \(a tab, a line break\) can't be written in an area line, so it is never a piece, a skipped folder or a range end"),
    ("use a piece that holds it without naming it, or end the range beside it", "Areas", r"Use a piece that holds it without naming it, such as the folder above it, or end the range on the path beside it"),
    ("a top-level folder named so is skipped whole in part 1 with that reason", "Areas", r"A top-level folder with such a name is skipped whole in part 1, with the reason \"name can't be written in an area line\""),
    ("a line break in a path shows as the byte 001, so the path is one line like any other", "Areas", r"A line break in a path shows in the listing as `\\001`, so the path is one line like any other: it goes in whatever area holds it, and `wc -l` and the reader sent for it report no such file"),

    # Reading a Part
    ("an area line that can't be read as one is dropped, with the Area dropped form for such a line", "Reading a Part", r"An area line that can't be read as one \(no `\(<n> files\)` at its end, or a definition that doesn't follow \"Areas\"\) is dropped the same way, with the `Area dropped:` form for such a line \(see \"8\. Coverage\"\)"),
    ("a listing that fails or prints nothing drops no area: every area goes back, nothing is read, a note gives the error", "Reading a Part", r"If the listing itself fails or prints nothing, no area is dropped: put every area back in the block, read nothing else, and give the error in a note that goes with the mode line \(see \"8\. Coverage\"\)"),

    # The Block
    ("a brief without Instructions is carried on as none", "The Block", r"A brief without the line is carried on as `Instructions: none`"),
    ("a brief without Project, Focus or Environment is carried on as none with a note naming it", "The Block", r"One without `Project:`, `Focus:` or `Environment:` carries that line on as `none` the same way, with a note that goes with the mode line \(see \"8\. Coverage\"\) naming it"),

    # When a Part Goes Wrong
    ("an area put back after refused spawns has left the part", "When a Part Goes Wrong", r"Those areas have left the part: they aren't under `Areas read:`, in `Files listed:` or in the mode line's N"),

    # If Your Brief Continues a Sweep
    ("the brief is checked whole before anything runs", "If Your Brief Continues a Sweep", r"Check that the brief is whole before you run anything"),
    ("no END OF BLOCK line or no area line means cut off: nothing is read and the reply is two lines", "If Your Brief Continues a Sweep", r"If it has no line that says `END OF BLOCK`, or no area line before it, it was cut off on the way: read nothing, and reply with these two lines and nothing else"),
    ("the cut-off reply isn't a part: no block, no sections, no Coverage", "If Your Brief Continues a Sweep", r"That reply isn't a part: it carries no block, no sections and no Coverage"),
    ("a whole brief lacking a line is carried on, and an unreadable area line is dropped", "If Your Brief Continues a Sweep", r"A whole brief that lacks a line before the areas is carried on as \"The Block\" says, and an area line that can't be read is dropped as \"Reading a Part\" says"),

    # Check Before You Compile
    ("coupling claims are checked with the Grep tool, never a grep with the name typed in", "Check Before You Compile", r"check coupling claims with the Grep tool for the referenced name, never a `grep` with the name typed into it"),

    # When You're an Area Lead
    ("a lead's line counts take its brief's paths in a here-document, and never a path that reads /END", "When You're an Area Lead", r"Get line counts with `wc -l` for the big-file rule, with your brief's paths in a here-document as \"Build the File List\" shows, and never a path that reads `/END`"),
    ("the rule: never paste a line that reads /END, once its backticks and the spaces at its ends are off, into a here-document", "Build the File List", r"Never paste a line that reads `/END`, once its backticks and the spaces at its ends are off, into a here-document"),
    ("why: it can only come from text changed on the way, so leave it out and name it unread", "Build the File List", r"it can only come from text changed on the way, so leave it out and name it unread"),

    # 8. Coverage
    ("the one reply without Coverage is the one for a cut-off continuing brief", "8. Coverage", r"The one reply without it is the one for a cut-off `CONTINUE SWEEP` brief \(see \"If Your Brief Continues a Sweep\"\)"),
    ("an area put back after refused spawns isn't under Areas read", "8. Coverage", r"An area put back in the block after refused spawns isn't one of them \(see \"When a Part Goes Wrong\"\)"),
    ("the Area dropped form for a line that can't be read as an area line", "8. Coverage", r"`Area dropped: <the line as given>; can't be read as an area line; not read\.`"),
    ("the per-folder counts are for a top-level single-agent report on a first run only", "8. Coverage", r"The per-folder counts apply only to a top-level single-agent report on a first run, never to a continuing run without `Agent` \(see \"When You Can't Spawn\"\) or to a lead's checklist"),
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

# The fence in "Areas", byte for byte. Each command takes its paths from a variable (set by the variable block above it),
# which awk reads from ENVIRON; `:?` stops the command when the variable is empty or unset.
FENCE = [
    "# count by top-level folder",
    "<list> | LC_ALL=C awk -F/ '{print (NF > 1 ? $1 \"/\" : \"(root)\")}' | LC_ALL=C sort | uniq -c",
    "# count one level down inside <dir>/",
    ": \"${<dir var>:?}\" && <list> | d=\"$<dir var>\" LC_ALL=C awk 'BEGIN {d = ENVIRON[\"d\"]} index($0, d) == 1 {r = substr($0, length(d) + 1); i = index(r, \"/\"); print (i ? d substr(r, 1, i) : d \" (direct)\")}' | LC_ALL=C sort | uniq -c",
    "# <dir>/",
    "<list> | d=\"${<dir var>:?}\" LC_ALL=C awk 'index($0, ENVIRON[\"d\"]) == 1'",
    "# <dir>/ (direct)",
    "<list> | d=\"${<dir var>:?}\" LC_ALL=C awk 'BEGIN {d = ENVIRON[\"d\"]} index($0, d) == 1 && index(substr($0, length(d) + 1), \"/\") == 0'",
    "# (root)",
    "<list> | LC_ALL=C awk 'index($0, \"/\") == 0'",
    "# except <folder>/, after any piece above",
    "<piece> | x=\"${<folder var>:?}\" LC_ALL=C awk 'index($0, ENVIRON[\"x\"]) != 1'",
    "# from <first> to <last>, after any piece above",
    "<piece> | a=\"${<first var>:?}\" b=\"${<last var>:?}\" LC_ALL=C awk '($0 \"\") >= (ENVIRON[\"a\"] \"\") && ($0 \"\") <= (ENVIRON[\"b\"] \"\")'",
    "# every file left after the whole-folder skips is in exactly one area",
    "diff <(<list> | x=\"${<skipped var>:?}\" LC_ALL=C awk 'index($0, ENVIRON[\"x\"]) != 1' | LC_ALL=C sort) <({ <area 1>; <area 2>; <and so on>; } | LC_ALL=C sort) && echo \"each file in exactly one area\"",
]

# The variable block above the fence: three lines per path, the path on the middle one.
VAR_BLOCK = ["IFS= read -r p1 <<'/END'", "<path>", "/END"]

# The one reply for a continuing brief that arrives cut off: two lines, in one fence.
CUT_OFF_REPLY = [
    "This CONTINUE SWEEP brief has no END OF BLOCK line, or no area line, so nothing was read. Send it again with the whole block, copied from the previous part's full text.",
    "INVESTIGATE REPORT ENDS",
]

# The pasted-paths form of a line count, in "Build the File List".
WC_FENCE = ["tr '\\n' '\\0' <<'/END' | xargs -0 wc -l --", "<path>", "<path>", "/END"]

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

    def test_the_coverage_heading_the_scorer_looks_for_is_the_agents(self):
        heading = load_scorer().COVERAGE_HEADING
        lines = [line for line in raw().split("\n") if re.fullmatch(r"#{2,3} " + re.escape(heading), line)]
        self.assertEqual(len(lines), 1,
                         "agents/investigate.md: no single heading line '## %s' or '### %s' (found %d); the scorer finds the Coverage lines by it" % (heading, heading, len(lines)))

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
        for later in ("Use `git ls-files -z | tr", "`wc -l`", "Skip lock files"):
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

    def test_the_block_count_is_a_real_here_document_that_counts_the_area_lines_under_bash_and_zsh(self):
        found = re.findall(r"between `(wc -l <<'/END')` and `/END`", " ".join(self.body_raw("### The Block").split()))
        self.assertEqual(len(found), 1, found)
        self.assertEqual(len(re.findall(r"printf '%s", self.text)), 0)  # no example that types the lines between quotes
        header = found[0]
        lines = ["- docs: `docs/` (22 files)", "- web: `web/` except `web/vendor/` (86 files)", "- top: `(root)` + `scripts/` (70 files)",
                 "- odd: `bob's notes/` + `$(echo MARKER)/` + `a\\tb/` + `x'; echo MARKER; '/` (4 files)"]
        shells = [["bash", "-c"]]
        if shutil.which("zsh"):
            shells.append(["zsh", "-f", "-c"])
        for n in (1, 2, 3, 4):
            command = "\n".join([header] + lines[:n] + ["/END"])
            for shell in shells:
                with self.subTest(lines=n, shell=shell[0]):
                    proc = subprocess.run(shell + [command], capture_output=True, text=True, timeout=30)
                    self.assertEqual((proc.returncode, proc.stdout.strip(), proc.stderr), (0, str(n), ""))

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
        self.assertNotIn("'$0 >= a && $0 <= b'", self.text)
        self.assertNotIn("$0 >= ENVIRON", self.text)  # each side joined with "" so the comparison is of strings

    def test_the_fence_check_fails_when_any_line_is_dropped_or_changed(self):
        area = self.body_raw("### Areas")
        for i, line in enumerate(FENCE):
            with self.subTest(line=line[:50]):
                dropped = area.replace(line + "\n", "", 1)
                self.assertNotEqual(fence_with(dropped, "# count by top-level folder"), FENCE)
                changed = area.replace(line + "\n", line + " #\n", 1)
                self.assertNotEqual(fence_with(changed, "# count by top-level folder"), FENCE)
        old = area.replace("'($0 \"\") >= (ENVIRON[\"a\"] \"\") && ($0 \"\") <= (ENVIRON[\"b\"] \"\")'", "'$0 >= ENVIRON[\"a\"] && $0 <= ENVIRON[\"b\"]'")
        self.assertNotEqual(old, area)
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
        wrong = self.sections["When a Part Goes Wrong"]
        self.assertNotIn("saved", wrong)

    def test_the_preview_rule_sits_beside_the_cut_off_definition(self):
        body = self.sections["Check Before You Compile"]
        self.assertEqual(body.index("Cut off means its return lacks `AREA REPORT ENDS`") < body.index("arrives as a preview")
                         < body.index("If that fails too, list every file"), True)


# ---------------------------------------------------------------- paths without typing, and a brief that arrives broken


def raw_section(text, heading):
    """The raw body of a section, up to the next `##`/`###` heading (comment lines in fences start with one `#`)."""
    at = text.index("\n" + heading + "\n")
    nxt = re.search(r"^#{2,3} ", text[at + 5:], flags=re.M)
    return text[at: at + 5 + nxt.start()] if nxt else text[at:]


class PathsAndBrokenBriefTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = raw()
        cls.sections = sections(cls.text)

    # ---- the variable block and the pasted-paths fence

    def test_the_variable_block_comes_before_the_command_fence_and_both_are_under_areas(self):
        area = raw_section(self.text, "### Areas")
        self.assertLess(area.index(VAR_BLOCK[0]), area.index("# count by top-level folder"))
        self.assertLess(area.index("Put each path a command needs into a variable"), area.index(VAR_BLOCK[0]))
        self.assertLess(area.index(VAR_BLOCK[0]), area.index("Set the variables in the same Bash call"))

    def test_the_pasted_paths_fence_is_in_the_file_list_section_and_holds_two_path_lines(self):
        section = raw_section(self.text, "## Build the File List")
        self.assertLess(section.index("Never type a path into a command"), section.index(WC_FENCE[0]))
        self.assertLess(section.index("Get line counts with `wc -l`."), section.index("Never type a path into a command"))

    def test_the_never_type_a_path_rule_comes_before_the_first_command_that_takes_a_path(self):
        text = self.text
        rule = text.index("Never type a path into a command")
        self.assertLess(rule, text.index("## A Sweep in Parts"))
        self.assertLess(rule, text.index(VAR_BLOCK[0]))

    # ---- the reply to a brief that was cut off

    def test_the_cut_off_reply_is_exactly_two_lines_in_one_fence(self):
        section = raw_section(self.text, "## If Your Brief Continues a Sweep")
        self.assertEqual(fence_with(section, CUT_OFF_REPLY[0]), CUT_OFF_REPLY)

    def test_the_cut_off_reply_check_fails_when_a_word_goes_a_line_is_added_or_the_fence_splits(self):
        section = raw_section(self.text, "## If Your Brief Continues a Sweep")
        block = "\n".join(CUT_OFF_REPLY) + "\n"
        self.assertIn(block, section)
        for label, mutated in (
            ("the last line gone", block.replace("INVESTIGATE REPORT ENDS\n", "")),
            ("a third line", block + "Mode: single agent\n"),
            ("the order swapped", "\n".join(reversed(CUT_OFF_REPLY)) + "\n"),
            ("END OF BLOCK dropped from the sentence", block.replace("no END OF BLOCK line, or no area line", "no area line")),
            ("the previous part's full text dropped", block.replace(", copied from the previous part's full text", "")),
            ("nothing was read dropped", block.replace(", so nothing was read", "")),
            ("the sentence wrapped onto two lines", block.replace("brief has no END", "brief has\nno END")),
            ("the two lines in two fences", block.replace("\nINVESTIGATE", "\n```\n\n```\nINVESTIGATE")),
        ):
            with self.subTest(mutation=label):
                self.assertNotEqual(fence_with(section.replace(block, mutated, 1), CUT_OFF_REPLY[0]), CUT_OFF_REPLY)

    def test_the_wholeness_check_follows_the_template_and_the_not_a_part_sentence_follows_the_reply(self):
        section = raw_section(self.text, "## If Your Brief Continues a Sweep")
        order = [section.index("CONTINUE SWEEP\nProject:"), section.index("Check that the brief is whole"),
                 section.index(CUT_OFF_REPLY[0]), section.index("That reply isn't a part")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(len(set(order)), 4)

    def test_the_marker_check_still_comes_before_the_wholeness_check(self):
        # the section's first sentence checks for the marker; the wholeness check runs after it
        section = raw_section(self.text, "## If Your Brief Continues a Sweep")
        self.assertLess(section.index("CONTINUE SWEEP"), section.index("Check that the brief is whole"))

    def test_the_cut_off_reply_is_said_in_one_place_and_pointed_to_from_coverage(self):
        flat = " ".join(self.text.split())
        self.assertEqual(flat.count("This CONTINUE SWEEP brief has no END OF BLOCK line"), 1)
        self.assertEqual(flat.count("Check that the brief is whole before you run anything"), 1)
        self.assertEqual(len(re.findall(r"cut-off `CONTINUE SWEEP` brief", self.sections["8. Coverage"])), 1)

    # ---- the unreadable-line form of Area dropped

    def test_the_unreadable_line_form_follows_the_named_form_in_coverage_and_is_one_line_in_one_note(self):
        body = self.sections["8. Coverage"]
        named = body.index("`Area dropped: <name>: now <n> files, the brief said <m>; not read.`")
        broken = body.index("`Area dropped: <the line as given>; can't be read as an area line; not read.`")
        self.assertLess(named, broken)
        self.assertEqual(len(re.findall(r"Area dropped: <the line as given>", self.text)), 1)

    def test_the_per_folder_counts_exception_is_said_once_and_the_old_unqualified_sentence_is_gone(self):
        flat = " ".join(self.text.split())
        self.assertEqual(flat.count("The per-folder counts apply only to"), 1)
        self.assertNotIn("single-agent report, never to a lead's checklist", flat)

    def test_no_sentence_types_a_path_between_quotes_in_a_command_the_model_runs(self):
        flat = " ".join(self.text.split())
        for old in ("-v d='", "-v x='", "-v a='", "-v b='", "'<dir>/'", "'<folder>/'", "'<skipped>/'", "'<first>'", "'<last>'",
                    "core.quotepath", "printf '%s\\n' '"):
            with self.subTest(old=old):
                self.assertNotIn(old, flat)


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
        self.assertEqual(len(re.findall(r"a note that goes with the mode line \(see \"8\. Coverage\"\)", self.flat)), 4)
        # one each: a failed lead, refused spawns (When You Can't Spawn), the missing Project/Focus/Environment line, the failed listing
        where = dict((h, len(re.findall(r"a note that goes with the mode line \(see \"8\. Coverage\"\)", b))) for h, b in self.sections.items())
        self.assertEqual(dict((h, n) for h, n in where.items() if n),
                         {"The Block": 1, "Reading a Part": 1, "Check Before You Compile": 1, "When You Can't Spawn": 1})
        self.assertEqual(len(re.findall(r"line right after the `Mode:`", self.flat)), 0)

    def test_the_scoped_read_has_no_part_lines_and_the_part_lines_are_for_a_part_of_a_full_sweep(self):
        self.assertEqual(len(re.findall(r"Coverage also has these lines", self.flat)), 1)

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
            git.write_text("#!/bin/sh\nprintf '%s\\0' " + " ".join("'%s'" % p for p in TRACKED) + "\n", encoding="utf-8")
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
