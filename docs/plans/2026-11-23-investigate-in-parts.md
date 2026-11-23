# investigate: no stop above 500 files, and a big sweep read in parts

*Status: not approved as a design yet. The owner has made three decisions
(below). A draft amendment was written and read cold twice; the second read
found four calls missing before a builder could start. This file keeps the
decisions, the draft, and the cold read's findings, so the work can be picked
up as its own project: a `brainstorm` round on the missing calls, a design
section in `docs/design.md`, an architect plan, then `run-plan`.*

## Owner decisions (2026-11-23)

- **The stop goes.** "Remove investigate's stop above 500 files too?" "Yes,
  remove it." It follows the owner's direction the same day that the Foundry
  doesn't gate work on what it costs to run or ask before spending: "The time
  used (cost) is a consequence of whatever the team is building. I don't need
  that constraint present in the team."
- **1A: a sweep too big for one report is read in parts, without asking.**
  `investigate` reads about 300 files' worth of areas, reports those whole,
  and names the areas it hasn't read; the session sends it straight back for
  the next part until the repo is covered. (The 300 was my call, from one
  measured report. The second cold read questions it: see finding 3.)
- **2A: the orchestrator updates the `STOPPED BEFORE READING` line in the
  owner's global `~/.claude/CLAUDE.md` when this ships.**

Not chosen: letting `investigate` write area reports to files (breaks "never
writes files"), and accepting cut inventories on very large repos (breaks
"never trim").

## Why this is a project and not a paragraph

The first cold read found the stop hid a limit that isn't about cost. A report
carries every inventory whole (design §1 Part 7), and one reply can only be so
long. The one measured report was 53.7KB for 191 files, and in that run it
reached its caller as a preview only (design §1, As built 2026-11-05). Without
the stop and without parts, a big sweep dies with nothing returned or comes
back cut off with no sign of it. So removing the stop means building parts,
and parts touch the modes, the report format, Coverage, the orchestrator's
loop, and three skills that dispatch `investigate`.

## The draft amendment (as read by the second cold read)

Line numbers in the findings below that say "design" refer to this draft as it
sat at `docs/design.md` lines 339 to 418 before it was moved here.

### Amended (2026-11-23): no stop above 500 files; a big sweep is read in parts

**Owner decisions (2026-11-23):**

- The stop in Part 6 goes. The owner's direction that day was that the Foundry
  doesn't gate work on what it costs to run, or ask before spending: "The time
  used (cost) is a consequence of whatever the team is building." The stop
  existed to quote a rough cost and have the session ask first, so it is a
  cost gate.
- 1A: when a sweep is too big for one report, `investigate` reads it in
  parts, without asking. It reads about 300 files' worth of areas, reports
  those whole, and names the areas it hasn't read. The session sends it
  straight back for the next part until the repo is covered.
- 2A: the orchestrator updates the `STOPPED BEFORE READING` line in the
  owner's global `~/.claude/CLAUDE.md` when this ships.

**Why parts.** A cold read of the first draft of this amendment found that the
stop also hid a limit that has nothing to do with cost. A report has to carry
every inventory whole (Part 7), and one reply can only be so long. The one
measured report was 53.7KB for 191 files (As built, above), and in that run the
report came back to its caller as a preview only. Without the stop and without
parts, a big sweep would die with nothing returned, or come back cut off with
no sign of it, which is the silent gap this design exists to prevent.

**What changes**

- There is no `STOPPED BEFORE READING` reply, no rough cost, and no brief that
  has to say the user approved a size. The orchestrator never asks the user
  before a sweep, whatever its size.
- **A part** is whole areas adding up to at most about 300 files. Areas are
  built as in Part 5 (at most about 150 files each), so a part is normally two
  areas. A list of about 300 files or fewer is one part, and nothing about
  that case changes.
- **Above that,** `investigate` builds the list and the areas, reads the
  first part's areas as Part 5 says (one area at a time, each behind an area
  lead), and returns a report that is whole for what it read: every inventory
  untrimmed, the gap check done, Coverage complete for the files in those
  areas.
- **The report names what's left.** Right after the `Mode:` line, a note lists
  every area not read in this run, each with the paths that define it and its
  file count, exactly enough for the next brief to name it. Those areas' files
  are not listed by path in Coverage: an unread area is given as its name and
  count. That is the one exception to "every file left unread, by path", and
  it applies only to areas this run was never going to read.
- **The orchestrator sends it back.** When a report names areas not read, the
  orchestrating session dispatches `investigate` again with a brief that
  names the next areas, as the report gave them, one run at a time, until a
  report names none. It doesn't ask the user. It keeps every part's report
  and hands later agents the parts that cover what they need.
- **A brief that continues a sweep** names its areas. `investigate` treats it
  as a full sweep whose list is those areas' files: same readers, same gap
  check, same Coverage, and the same parts rule if the named areas come to
  more than about 300 files.
- **A lead that fails twice** has its files listed as unread, by path, as
  today. The top level doesn't then send its own readers for them: the
  failed-lead rule wins over the path check, or one bad lead would pull about
  150 reader reports into the top level.

**Calls I made**

- About 300 files a part. One measured report (191 files, 53.7KB) is all there
  is to go on, and 300 leaves room under a reply's limit. The old stop let one
  report cover up to 500 files, which was never measured.
- The parts rule counts the current mode's list, as the stop did: a scoped
  read of more than about 300 files is read in parts too.
- Everything else in Parts 1 to 5 and 7 stays: areas, one area at a time,
  readers in batches of 10, the gap check, "never trim an inventory, at any
  layer". A bigger repo is more parts, one after another.
- For the areas a run won't read, `investigate` needs names and counts, not
  every path. On a very large repo it gets those by counting, not by holding
  the whole file list.
- `NOT A PER-FILE READ` stays as the one first-line flag. With no `Agent`,
  a large repo gets the flagged single-agent read it always would have below
  500 files; it no longer stops to say `Agent` is missing.
- Tests stop treating the stop as allowed text, and a pin keeps it from
  coming back.
- Not measured: nothing above 191 files has been run. The two existing eval
  cases use a repo under 200 files, so they show the change didn't break the
  one-part case, not that parts work. A fixture of several hundred files is
  the next thing to build.

## The second cold read's findings

By `the-foundry:architect`, read-only, against `agents/investigate.md` at
bd7fe14. Each is a question a builder would have to guess at, with the
reader's best guess. Findings 1 to 4 need a call before a builder can start.
All of them are "by reading": check any that a fix gets built on.

1. **Does a continuing brief name every area still unread, or only the next
   part's?** If only the next part's, the part-2 run reads everything it was
   given, names no unread areas, and the session stops with parts 3 onward
   never read and nothing to show it. The draft also doesn't say whether a
   continuing run uses the named areas as given or re-splits them; a re-split
   breaks the names the session is tracking. *Best guess:* every continuing
   brief carries every area still unread; `investigate` reads the first part's
   worth of them, as given, never re-splitting, and names the rest.
2. **How does `investigate` recognise a continuing brief, and which mode
   wins?** The existing mode rules send it to scoped mode twice over: a brief
   that names the files to read is scoped (`agents/investigate.md` "Pick a
   Mode"), and a session on part 2 knows the codebase, which is scoped unless
   the brief asks for the whole thing (`docs/orchestrator.md`). Scoped mode
   trims to what the task plainly touches and writes `Mode: scoped`. Nothing
   says whether a continuing run repeats orientation, and untracked files
   would be listed again in every part. *Best guess:* a first-line marker in
   the brief (for example `CONTINUE SWEEP`), checked before orientation the way
   `AREA LEAD` is, with precedence over "Pick a Mode"; run orientation again;
   mode line `Mode: full sweep, <N> area leads` with N the leads run in this
   part; untracked files listed in part 1 only. The tests only check the four
   mode tokens exist, and the one grader on mode lines
   (`control-new-area-leads`) runs on a one-part fixture. A scoped read of more
   than a part's worth becomes a full sweep from part 2 on: say so or give it
   its own wording.
3. **What tells the caller a report is one part of several, and does it arrive
   intact?** The loop depends on the note after `Mode:`, which sits in
   section 8, the end of the report. The draft's own evidence is that a 53.7KB
   report for 191 files reached its caller as a preview only; a 300-file part
   is about 85KB, and the end is what a preview drops. That evidence supports
   "300 fits a reply's output limit" at best, not "300 reaches the caller".
   The line after `Mode:` is also already used twice (a failed lead's area;
   the count of unstarted files after a refused spawn). *Best guess:* a fixed
   token on its own line, for example `Areas not read: <n>`, one area per line
   after it; one more fixed line near the top (for example line 2:
   `PART: <n> areas not read; see Coverage`), which needs the owner's OK since
   the design limits flags to the first line; a sentence in
   `docs/orchestrator.md` to read the whole saved output when a report came
   back as a preview; pin the token in tests. **The part size has to come from
   a measurement of what reaches the caller, on a fixture of several hundred
   files.**
4. **What exactly are "the paths that define" an area, and can a later run
   rebuild the same file set?** A merged area is a list of folders. Root-level
   files have no folder. A flat folder of 2,000 files can only be divided into
   file lists, which brings back per-path listing. Skipping is partly
   judgement, so a continuing run may re-skip differently and get a different
   count. Nothing checks across parts that the parts cover the whole list, so
   a file no definition captures drops out silently. *Best guess:* an area is
   one of three shapes: a set of folder prefixes (every tracked file under
   them); `(root files)`; or, for a folder that can't be divided by subfolder,
   a contiguous range of the sorted `git ls-files -- <folder>` output given as
   its first and last path. The definitions cover the whole list with no
   overlaps, and the count is a check: a continuing run whose rebuilt count
   differs says so in Coverage.
5. **Coverage arithmetic.** Nothing defines whether "files listed" in a part
   means the whole list or this part's areas, and skips would be counted again
   in every part. *Best guess:* within a run, listed = read + unread by path +
   the counts of unread areas; part 1 counts skips and untracked files for the
   whole repo; a continuing run counts only files inside its named areas and
   says its skips were counted in part 1; state the cross-part sum.
6. **"Count, not hold" on a very large repo.** The agent follows text
   literally, and "by counting" gives no method. Counts taken before the
   judgement skips are approximate. The gap check works within a part; unread
   areas get none until their own run, and no run checks across parts.
   *Best guess:* state the commands (`git ls-files | wc -l`; per top-level
   folder with `awk -F/ '{print (NF>1?$1:"(root)")}' | sort | uniq -c`; one
   level deeper to divide a folder), apply only the skips a path can show, say
   the counts are before the judgement skips, and list paths only for the
   current part's areas.
7. **A refused spawn mid-part.** The current part's unstarted areas are listed
   unread by path, not named as areas, so the loop never sends them again,
   while later parts' areas do get retried. *Best guess:* name them in the
   unread-areas note too. Keep the failed-lead rule (a lead that fails twice:
   files listed unread by path, and the top level doesn't re-send readers for
   them).
8. **Who else has to know about parts.** `skills/brainstorm/SKILL.md` (recon
   on an unfamiliar codebase is a full sweep), `skills/debug/SKILL.md` and
   `skills/run-plan/SKILL.md` dispatch `investigate`, and
   `docs/orchestrator.md` isn't loaded into a session: only the owner's global
   CLAUDE.md carries the loop rule. A brainstorm recon in another user's
   session would take part 1 for the whole codebase unless the report says
   it's one part. *Best guess:* with finding 3's signal in place, one sentence
   each in the agent's description, `docs/orchestrator.md` and brainstorm's
   recon line; debug and run-plan need nothing.
9. **The single-agent fallback.** Parts are defined as areas behind leads, and
   a run without `Agent` has none. *Best guess:* no parts: one flagged report
   with unread files as counts per folder, as now; say so in "When You Can't
   Spawn".
10. **Contradictions.** The preview evidence against "300 leaves room"
    (finding 3). "Nothing about that case changes" is false for small repos,
    since the failed-lead rule now applies to them too (harmless if applied
    everywhere). The mode collision (finding 2).

## From the first cold read, still true

- Every place that depends on the stop: `agents/investigate.md` (the area-lead
  skip of "the 500-file parts"; "The 500-file stop ... count the current
  mode's list"; untracked files "don't count toward the 500-file stop"; the
  stop paragraph itself with its 1.2-cents figure and "this stop wins over
  every other first line"; the lead's "don't ... apply the 500-file stop"; the
  list of first-line flags; "a STOPPED reply carries no Coverage");
  `README.md` about line 301 (deleting the stop sentence leaves "That costs
  more" with nothing to refer to); `docs/orchestrator.md` about lines 32 to
  35; and the tests: `tests/test_structure.py` (the "exceeds 500 files" and
  `STOPPED BEFORE READING: <N> files` pins, and `NoCostGatesPinsTest`'s
  docstring and `LEFT_ALONE` list, which name the stop as allowed text),
  `tests/test_check_before_building_pin_mutations.py` (adds the stop sentence
  and expects green), `tests/test_investigate_batch1.py`.
- The `evals-expensive/` graders check only `NOT A PER-FILE READ` and
  `END-OF-REPORT` plus the facts; the head-to-head fixture is held at 170 to
  190 eligible files, so neither case reaches the sizes this opens up.
- One area at a time keeps the agents running at once near 12 at any size;
  only the time grows.
- With no `Agent`, "reading it yourself" is the old selective read with unread
  files as counts per folder; it doesn't try to read thousands of files.
