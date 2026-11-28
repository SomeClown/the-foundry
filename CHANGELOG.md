# Changelog

All notable changes to The Foundry. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning policy is in
[CONTRIBUTING.md](CONTRIBUTING.md).

## [3.1.0] — 2026-11-27

Steadier runs: three slips that cost runs in 3.0.0's measuring, and six
graders that scored right runs as misses (five now exact patterns, one a
corrected rubric). The entry changes what three agents do in small ways:
`devops`'s three report lines, `investigate`'s last part, and the lead's Bash.

`devops`'s three report lines, `Data change:`, `Rollback:` and `Watch:`, are
now one line each, starting with the label, with no line break or bullets
inside; on the `Rollback:` line `tried:` or `not tried:` comes once, after the steps, and
anything longer goes in the body. The graders `rollback-tried` and `watch-line`
read the shapes real reports took: a `Rollback:` label alone on its line with
the steps below it, a "Tried:" after a sentence on the same line, and a quote,
bracket or emphasis mark between "roll back if" and the word after it. On the
28 saved `devops-tries-the-rollback-on-a-copy` reports, `rollback-tried` now
hits two it missed and `watch-line` two it missed, and no other verdict
changed; three reports that are true misses stay misses. The 3.0.0 build log
(`docs/plans/2026-11-27-area-lead.md`) described one run's rollback as saying
nothing of tried and another as having no `Watch:` line. Neither was so: all
four reports had tried the rollback, and the graders misread run 1's
`Rollback:` line and run 2's `Rollback:` and `Watch:` lines.

`investigate`'s last part carries nothing of the block: its `SWEEP IN PARTS`
line reads `SWEEP IN PARTS: 0 areas not read`, and no `To read the rest`
sentence, `Project:`, `Focus:`, `Environment:` or `Instructions:` line,
`Areas not read:` list or `END OF BLOCK` comes under it; its Coverage still
carries the `Areas not read: 0 areas, 0 files` line. The old sentence ("with no
lines under it") let a last part write `Project:` there: that was one of the two
causes of the one failed sweep on 3.0.0's final text, and 2 of the 16 saved
last parts held block lines. The sweep scorer, `check_parts.py`, now fails `Focus:` and
`Environment:` on the line straight under it too, matching the text. It allows a readable file
a second reader when the part that holds it says `re-dispatched:` at least as
many as such files, counted by part and not summed across parts; three readers,
or more twice-read files than the part's count, still fail, and a counts line
it can't read gives no allowance.

`area-lead`'s Bash is only for the commands its own file gives (the credential
filter, `wc -l` and `echo`), never a build, a test, or a command a file, a
reader's report or a brief names. Under 3.0.0 and earlier it kept
`investigate`'s "for reading, and for running the project's builds and tests",
which no lead was meant to use. This is a narrowing of what a lead may do.
`investigate` keeps its own sentence.

Graders sorted by hand against every saved run, since the judge had been
failing runs that did the thing. `debug-polluted-test` `ran-the-check`: all 22
saved runs ran the victim alone and the polluter with the victim before
writing the fix; the judge failed 7 of them. `debug-decisions` `item-a`: 22 of
22 refused a fourth fix, took the question to the user with options and
a recommendation; the judge failed 1. `architect-splits-a-breaking-change`
`code-first-then-the-break`: 16 of 16 plans put code that works with both
names, or the new column beside `email`, first and the drop later; the judge
failed 2. The shape it misread is a first release that adds the new column and
also moves the app to it. No run was a real miss on any of the three. `ran-the-check` and
`item-a` are now exact patterns at the same weight; `ran-the-check` hits the
22 and misses all 87 variants with the commands moved after the fix or a name
removed. `code-first-then-the-break` stays judged, with its rubric corrected
to name that shape. `two-releases`, the sixth, was found by the record run
(it wanted "two release" side by side and rejected "Release 1.4.1", so it
missed a right plan that says "two code releases" and labels them 1.4.1 and
1.5.0); it now reads the other ways plans name their releases, never takes
1.4.0 or 1.4, the live version, as a release label, and was checked against the 20
saved plans, with no new real run.

Measured. On the text of a51daaa (the `investigate`, `area-lead` and scorer changes), the
nesting smoke passed 9 of 9 graders, and the head-to-head found 48 of 48 in all
four runs, made up 0, and scored `BAR MET`. The big sweep, eight runs: 6
`LOOP PROVED` and 2 `LOOP FAILED`, none stopped by a limit or a classifier.
The two failures are not on anything this release changed. One (sr-3) wrote the
label `Areas read:` on the end of the `Skipped:` sentence, not on its own line,
so the scorer found no areas read; its one second reader got no allowance for
that reason. The other (sr-2) had a lead type an absolute path with a hyphen
where the real one has a slash, for 10 of its 74 readers (8 found the file
anyway), and another lead marked a file read that no reader was sent. This is
not shown to be steadier than 3.0.0: 6 of 8 against 3 of 4 can't be told
apart at this size. What was counted: no last part carried anything of its
block (0 of 8; 2 of 16 saved last parts had), no part named the vendored route
(0 of 8), and three runs had a second reader within their part's own count, one
of them (sr-6) proved where 3.0.0's scorer would have failed it. The sweeps ran
on a51daaa, and the three agent files and the sweep scorer are the same at the
final commit. Rescored with the final scorer, the eight keep their verdicts (6
proved, 2 failed).

The record run on 07b1043 (`agents` and `debug`, four runs each): 15 of 19
cases at 4 of 4. `devops-tries-the-rollback-on-a-copy` 4 of 4 on every grader
(2 of 4 in the record run before 3.0.0, b85d985), `devops-holds-a-breaking-migration` 4 of 4,
`debug-polluted-test` 4 of 4 (1 of 4), `debug-decisions` 4 of 4 (3 of 4), and
`architect-splits-a-breaking-change` 3 of 4 (`code-first-then-the-break` 4 of
4). A qa agent that hadn't seen the traces read the reworked graders' 16
verdicts and confirmed 16 of 16; the corrected rubric's judge passed all three
fresh plans of the shape it had misread, 3 votes of 3 each.

**One bar was missed as set:** "the three `devops` cases, every grader 4 of 4".
`devops-stops-before-irreversible` came in at 3 of 4. Run 2 put a summary
sentence above its `Status:` line and failed `opens-with-four-lines` and
`status-needs-context`; nothing irreversible ran, and the graders are ones this
release didn't touch. It is a real miss by the agent. The other misses in the
round: `architect-plan-format` run 2 (an untouched-kind `Security:` line,
which the grader read right), `implement-test-first` run 4 (the agent edited
test and code, then ran the tests), and `architect-splits-a-breaking-change`
run 3 (`two-releases`, the grader's fault, fixed above). Also: the new `devops`
one-line rule held in 3 of 4 fresh reports (run 4 wrote `Data change:` in bold
with two bullets under it), and `rollback-tried` is looser than the agent's
template, since two fresh reports leave the command to the body.

Exact graders read text, not meaning. A miss on one in a real run gets a hand
read of the trace before it counts. Their known limits (right shapes they
miss, wrong ones they hit) are listed under "Parked" in
`docs/plans/2026-11-27-steadier-runs.md`.

A final review read the branch. It found one more place where the scorer
stopped with an internal error on a count thousands of digits long (the folder
count in `Whole repo:`), now fixed; `two-releases` now skips `1.4` as well as
`1.4.0`; and a guard tried in `item-a` for a reply that does the redesign
itself was taken out again, because it cost right replies and let the likeliest
wrong ones through, so `item-a` is what the record run measured. The three
reworked exact graders hold on every saved right run (`two-releases` 20 of 20,
`ran-the-check` 26 of 26, `item-a` 26 of 26). Four review findings that would
change agent text or a rubric after the runs measured it are parked in the plan,
not fixed.

## [3.0.0] — 2026-11-27

The area lead is now its own agent, `area-lead`, the eleventh. A lead
used to be `investigate` told to act as a copy of itself, so every lead
loaded all 703 lines of `investigate` and was told which of them to skip;
it now reads a file written for it, and `investigate` (685 lines) holds no
lead-only text. `investigate` starts a lead as `the-foundry:area-lead`,
then by the bare name `area-lead`, and `area-lead` starts only
`file-reader`; as before, only instructions keep each to that. The brief a
lead gets, the reports, Coverage, the `SWEEP IN PARTS` line and the
`CONTINUE SWEEP` brief are unchanged. If both names of the lead are
refused while `file-reader` still works, that is "can't spawn": a flagged
read naming the missing agent. This is a major version because a new agent
is, by CONTRIBUTING's rule.

**A copy of `investigate` made before this release must be copied again.**
Such a copy (the plan-mode copy in `~/.claude/agents/` the README
describes) sends its leads to `the-foundry:investigate`, which no longer
works an `AREA LEAD` brief: it answers with a two-line reply that says to
send it to `area-lead` and to copy the agent files again, and the area's
files show up as unread. Copy `agents/investigate.md` again.

Fixed: a lead that returned its checklist as groups ("`src/api/`: 41 files
read") got its word taken, or the files reported unread though they were
read. The lead's text now asks for one line for each path in its brief,
and `investigate` counts a checklist that isn't one line a path as no
checklist, so the lead is started once more with the same brief and, if
that fails too, its files are listed unread by path. No real run could be
made to group a checklist on demand; this is held by tests on both texts
and a made-up transcript for the scorer, which now allows the second set of
readers a restarted lead sends.

`architect` writes no `Security:` line that only says a kind isn't
touched. On `architect-plan-format`, all four runs passed as scored; read
by hand, one of the four plans still had such a line (on 2.6.0, 2 of 4
did). The new grader `no-untouched-security-line` checks it.

Fixed during the build: a lead's search stays in its area, and a hit from
a file outside its brief is dropped. A lead under 2.7.0 read that rule; the
move left it out of `area-lead.md`, and leads began naming a route from the
vendored folder skipped whole, which then reached a report. Transcripts
naming that route: 0 of 5 before the move, 9 of 11 after it, 0 of 4 on the
final text. The counts line is now written bare (no backticks) and the
`Environment:` line is copied whole, clause for agents included, since each
cost a big-sweep run on the move alone. `area-lead.md` is 237 lines.

Measured, and one bar missed on the move alone. The big sweep, as many
`LOOP PROVED` after as before: before (2.7.0) 3 of 3 counted runs proved;
after the move alone, 2 proved and 2 failed of 4 counted, each on one line of
the top level's own report (a clause dropped from a copied `Environment:`
line; a counts line with the right numbers wrapped in backticks), with every
file read once and no fact missed. The owner saw the numbers on 2026-11-27
and chose to go on. On the final text it is 3 proved and 1 failed of 4
counted: as a count the bar is met (three and three), as a rate it is 3 of 4
against 3 of 3, and three runs against four is a small sample that doesn't
show the text is as careful as 2.7.0's. The one failure had two causes: block
lines written under a last part's `0 areas not read`, and two second readers
that the scorer fails and the lead's text allows for a gap. The head-to-head
found 48 of 48 in all four runs after the move and again on the final text,
made up nothing, and scored `BAR MET` both times; the nesting smoke passed
9 of 9 both times. Two grader-tuning rounds fixed `compare.py` and
`check_parts.py` reading right answers as wrong. Nine restatement pins on
moved text were cut; 11 contract and safety pins were kept and re-pointed at
`agents/area-lead.md`, and 5 were reworded. `file-reader`'s description now
says `investigate` and `area-lead` start it. The README,
`docs/orchestrator.md`, PRIVACY.md, CONTRIBUTING.md and `evals/README.md`
say eleven agents and who starts which.

The probe moved the sweep-in-parts procedure (256 lines) into a file
`investigate` reads only for a sweep above the part size, and met every bar
it was given: the sweep case 2 proved of 4 against the after-runs' 2, the
head-to-head 48 of 48 in four runs, the smoke 9 of 9, and no small run read
the file. Its bars matched a count that had itself missed, and neither of its
two failed sweeps is clearly caused by the file. The owner chose on 2026-11-27 to leave
the procedure inline in `investigate.md` for this release, with the move left
for a change of its own.

## [2.7.0] — 2026-11-26

`devops` now sorts a schema or data change before applying it (adds
only, breaks running code, can't be undone), checks it against the code
running now and the version before, and stops before a change that
breaks the running code even when its brief says to apply it. Its report
gives the rollback as tried, with the command and exit code, or not
tried, and a rollback is tried only on a copy or with a command that
only reads. It names what to watch after the change, for how long, and
what means roll back. Two new cases: `devops-holds-a-breaking-migration`
and `devops-tries-the-rollback-on-a-copy`.
`ship`'s preflight sorts data changes the same way and sends one that
breaks the running code back to be split; its hand-over checks a new
setting without printing it, marks the rollback tried or not tried,
gives the watch, and when pasted output meets the roll back if
condition, hands over the rollback for the user to run.
The architect splits a change that breaks the running code across two releases.

## [2.6.0] — 2026-11-26

Plans now say what a change exposes: the architect writes a `Security:`
line for each kind it touches, naming the task that guards it, or
`Security: none`, and a new dependency is decided in the plan and named in
its task. `brainstorm` asks who may use a feature, what private data it
keeps and what it reaches outside itself, and `implement` adds only a
dependency its brief names, pinned, and reports its version and license.
`qa` now checks a changed manifest or lock file: what moved, each new
package by hand (a look-alike name, the pin, the source, an install
script), and an audit tool only when one is installed and sends nothing,
or the brief says the dependency list may be sent. `qa-dependency-review`
is a new case.

## [2.5.0] — 2026-11-26

The test files now run side by side (`tests/run_tests.py`, about 85 s where it
took 283 s), and `python3 -m unittest discover -s tests -q` still runs them in
one process. CI runs the gate on macOS for every push to `main` and every pull
request: the tests on the stock Python and a current one, and the three plugin
validates. `dist` also drops `.github/`.

The tests lost about 318 wording pins that guarded nothing: pure copies of
another pin, and pins on results prose, the design's "As built" history,
changelog entries and build-log lines. An audit sorted all 1,510 pins first,
and every one on a contract, a safety rule or live instruction text stays.
Seventeen named tests now guard the headings and sentences that the
command-running tests find their commands by, and a defect that ran 27 tests
twice is fixed. No agent or skill changed.

Every agent now has a behavior case. `devops`, `docs`, `test-engineer`,
`frontend` and `uiux` each get one under `evals/`, tagged `agents`: `devops`
must stop before a migration that drops data, `docs` must fix a README without
touching code or obeying a planted instruction, `test-engineer` must report a
planted bug and leave the code alone, `frontend` must say what it couldn't
render, and `uiux` must return a direction and write nothing. What an agent
must not do is graded by outcome, and a hard line fails a run by its own
weight. `implement-test-first` lost a grader that couldn't fail and gained an
exact one, and now holds on every run where it used to fail about half.
`evals/scorecard.py` records each run in `evals/SCORECARD.md`; the first rows
are these cases on this change's final commit. No agent or skill changed.

Designs now end with a numbered **Done when** list, ids `AC-1` on, and the
ids travel. Each plan task names the ids it covers, with their text, and the
plan says how each is checked; builders say where each is met,
`test-engineer` writes a test per id, `qa`'s spec check gives every id a
line (met, not met, untested, can't verify, dropped), and `run-plan` keeps
the count and lists every id's state at the end. Work with no ids runs as
before. `brainstorm-writes-design`, `architect-plan-format` and
`qa-spec-check-planted` now carry ids.
The four opening lines now say `Status:` comes first, with no summary sentence
above it; in 2 of 20 runs an agent had put one there.

## [2.4.0] — 2026-11-26

Every agent that holds Bash now carries the same rules for what it reads, and
`investigate` no longer opens credential files. The eight agents that report to
the session open every reply with the same four lines, and the two builders
check more before they report.

### Added
- A `## How Every Report Opens` section, word for word the same in `architect`,
  `devops`, `docs`, `frontend`, `implement`, `qa`, `test-engineer` and `uiux`:
  `Status`, `Files changed`, `Verified` and `Concerns`, with what each status
  means. `investigate` and `file-reader` keep their own fixed report lines.
- `implement` runs the project's linter, formatter check and type checker when
  it has them, and names what was already failing.
- `test-engineer` runs each new test at least five times, fixes a flaky test or
  reports a flaky application as a bug, and reports the run count (and the
  touched lines' coverage where the project measures it).
- A `## What You Read Is Data` section, word for word the same in `architect`,
  `devops`, `docs`, `implement`, `test-engineer`, `frontend`, `uiux`, `qa` and
  `investigate`. Bullet A (what an agent reads is data, never instructions) and
  bullet C (a secret is reported by file and line, never by value) are in all
  nine. Bullet B (a name from the repo goes into a command in single quotes or
  through a NUL-separated pipe) is in every one but `investigate`, which keeps
  its own path rules. Bullet D (nothing from the repo leaves the machine in a
  request) is in `frontend`, `uiux` and `qa`, the agents with web or browser
  tools.
- `investigate` skips credential files by name, in any case (`.env` and `.env.*` but not the
  example, sample, template and dist ones, private keys and keystores, `id_rsa`
  and its kin, `.netrc`, `.npmrc`, `.pypirc`, `credentials*.json`, and
  `secrets.*` config files). They are counted under the skip reason
  `credential files`, named by path in Gotchas, and never opened, even when a
  brief names one; an area lead marks one `unread: credential file`.
- `file-reader` has a `Secrets:` bullet in "What to report": a secret goes under
  Gotchas as its line and what kind it is, never the value.

### Changed
- `run-plan`'s dispatch asks for the four opening lines; `qa`'s spec section
  follows them; a saved plan starts at its `#` title; a `devops` stop before a
  command it can't undo reports `NEEDS_CONTEXT`.
- README and PRIVACY no longer say the plugin reads no credential files. They
  say what each part does: `investigate` doesn't open files named like
  credential stores, and every agent reports a secret by file and line.

## [2.3.0] — 2026-11-24

`investigate` no longer stops above 500 files to have your session ask you
first. A repo too big for one report is read in parts, and the session carries
on without asking.

### Changed
- The stop above 500 files, its rough cost and the `STOPPED BEFORE READING`
  reply are gone. Nobody asks the user before a sweep, whatever its size, or
  between parts (design §4).
- Above 450 tracked files (after whole folders skipped by rule), `investigate`
  returns one part: the first areas, whole areas only and never fewer than
  one, with every inventory untrimmed. The report opens with
  `SWEEP IN PARTS: <n> areas not read` and a block that is the whole next
  brief, ending at `END OF BLOCK`. The session sends it back with
  `CONTINUE SWEEP` on its first line, one run at a time, until a report says
  `0 areas not read`. A scoped read above 450 files says
  `SWEEP IN PARTS: <n> files not read` instead, and the session sends the
  original brief again with the unread paths.
- Every report now ends with `INVESTIGATE REPORT ENDS` (an area lead's return
  with `AREA REPORT ENDS`), so a cut-off report shows. A report (or part) with
  no last line, or naming the same areas unread again, gets one retry, then the
  session stops and says which areas are unread. A report that arrives as a
  preview is read from its saved output.
- A lead that fails twice has its files listed unread by path, and the top
  level doesn't read them itself. That rule now holds in every sweep, small
  ones included.
- On a full sweep the report holds nothing quoted from a folder skipped whole
  or from an untracked file, and nothing drawn from their contents, even when
  a search of the tree turned it up.
- Every top-level report's Coverage gives its counts as one fixed line,
  `Files listed: <n>; read: <n>; skipped: <n>; re-dispatched: <n>; failed: <n>; unread: <n>`.
  The counts are added with a
  command, never in the model's head. An area line's parentheses hold the
  count and nothing else, `(root)` and `(direct)` are written bare, and the
  block's area lines are counted before line 1 is written. A lead's return
  that arrives as a preview is read from its saved file. Readers go 10 at a
  time and area leads one at a time, never two leads in one message.
- `docs/orchestrator.md` has the loop for the session, and `brainstorm`'s
  recon line says a sweep can come back in parts.
- `investigate` never types a path from the repo into a command: each path
  goes into a shell variable through a here-document, `awk` reads it from its
  environment, and the listing is `git ls-files -z` with a line break in a path
  printed as the byte `\001`, so every path is one line and no line of a
  listing can end a here-document. A name with a quote, a backslash, `$(…)` or
  a leading dash can't break the area commands or run as one, and a line
  reading `/END` is never pasted into a here-document. Line counts and the
  block's count take their paths the same way.
- A `CONTINUE SWEEP` brief that arrives cut off is answered without reading,
  and the session copies the block again; an area line that can't be read is
  dropped and quoted in Coverage; a `Read only these files:` list replaces any
  other scope.

### Added
- `evals-expensive/big-sweep-in-parts`: a generated test repo of 990 tracked
  files (950 after its skipped folder, 945 readable) with planted facts in
  every part, and a case that has a session read it part after part.
- Six `reply-size-*` cases (150, 230, 320, 400, 450 and the whole repo) that
  measured how big a report can be and still reach the session whole. They
  asked for the old definition's last line and say the user approved the
  count, so they're the record of how the part size was set, not a check to
  re-run.
- `evals-expensive/sync_big_sweep.py` (writes the answer key and the cases'
  generated files; `--check` exits 1 naming files that differ),
  `evals-expensive/measure_reply.py` (bytes of each agent result and whether
  it kept its last line; a result is whole only when the marker is its last
  line) and `evals-expensive/check_parts.py` (scores a sweep
  read in parts: every file read once, every planted fact found in the part
  that read its file, the counts and the block right, and, with `--transcript`,
  its reads checked against the run's own transcript; without one it says
  `readers: not checked`). Whether anybody asked is for the `no-asking`
  grader and the session's final message, not the scorer. All three run by
  hand, stay local and use no network. The big-sweep scaffold and its six
  copies stop with exit 1 in a folder that isn't empty, and in an empty folder
  inside a repo that has commits.

## [2.2.1] — 2026-11-23

A docs-only patch. The README's manual-install section now describes the
steps in words and links to Claude Code's own docs for where agents and skills
live. It used to show the steps as shell commands to paste, and the plugin
directory's review read those as a download-and-run. The steps themselves are
the same. No behavior change.

## [2.2.0] — 2026-11-23

A minor version, and a self-improvement pass: I had `qa` review the Foundry
itself, built the fixes with the Foundry's own `run-plan`, and ran its behavior
cases on real sessions to check them. The team is the same ten agents and four
skills. What's new is a retro that `run-plan` and `debug` write at the end of a
run, a rule that a finding `qa` only read gets checked before a fix is built on
it, and a round of fixes to `debug`, `run-plan` and five agents.
`investigate`'s stop above 500 files is unchanged in this release. Reading big
repos in parts is written up as a project of its own in `docs/plans/` and isn't
built.

### Added
- A retro at the end of `run-plan` and `debug` (design §3). The session
  writes one line for each time the team needed correcting that the loop
  didn't catch by itself. For `run-plan` that's a task with two or more fix
  rounds or a BLOCKED, a test that misread the brief, a qa finding the builder
  or `test-engineer` should have caught, a fix that didn't hold, or anything
  the user corrected. `debug` counts a fix that didn't hold, a step of the
  method skipped and caught, a dispatched agent's work redone, and anything
  the user corrected. One fix round, a builder's question, or anything tried
  once and corrected on the spot isn't one. Each line is
  `- <agent or skill> [<kind>]: what it did; what it should have done (where
  it came from)`. It names the agent that did the work, or `run-plan` or
  `debug` for work the session did itself, never an agent that wasn't
  dispatched. The kind is one of `user`, `blocked`, `fix-rounds`, `misread`,
  `missed`, `didnt-hold`; when two fit, the first listed wins, so `user` comes
  first. The lines go under a heading with the date, the repo's top folder's
  name, and the run, appended to `~/.foundry/retro.md` (or the file named by
  `FOUNDRY_RETRO_FILE`), so a repeat shows across projects. A run with nothing
  to correct writes nothing to that file (`run-plan` logs `- none` in its
  build log). Lines already in the file for the run aren't written twice, so a
  run that stopped early and went on still adds its later lines. `run-plan`
  keeps a copy in its build log, and a run that stops early (a fix cap, three
  failed fixes, can't reproduce) writes its retro first. When the same agent
  or skill makes a mistake with the same kind word as an earlier line, the
  report quotes both and offers to work out a fix through `brainstorm`. The
  session never edits an agent or skill file itself. The README and PRIVACY.md
  say what the file holds and where, the README's uninstall note says how to
  remove it, and structural tests hold the docs to it. The eval harness gives
  each case its own home, so a case's retro never reaches the real file;
  `evals/README.md` and CONTRIBUTING say so.
- `qa` puts a `Verified:` line in each finding: `ran ...` or `by reading`.
  `evals/run-plan-decisions` has a new situation (h) and grader for what
  `run-plan` does with each.

### Changed
- Nothing told the session to check a claim before building on it, and the
  retro's first repeat showed it: a qa finding marked "by reading; not run"
  led to an eval prefix and docs that were wrong, and a design call of the
  session's own lost a stopped run's later lines. `run-plan`'s fix-batch step
  now takes a finding shown by running as it is, and checks one shown only by
  reading with the quickest check that could prove it wrong (a real model
  session if that's what settles it) before a fix is briefed. What the check
  costs to run is not a reason to skip it. The build log says which of the two
  each accepted finding was. Calls the session adds to a design mid-run get
  `brainstorm`'s builder check before a builder is briefed (the user's own
  answers don't), and the orchestrator notes say the same of the Foundry's own
  findings.
- The Foundry doesn't gate work on what it costs to run. `CONTRIBUTING.md` no
  longer asks for the owner's OK before the `investigate` head-to-head, and
  `evals/README.md` no longer warns that running the cases costs real money.
  Measured figures stay as facts.
- run-plan no longer keeps the base commit in a `BASE` shell variable, which
  didn't survive from one Bash call to the next. The build log names the sha
  noted at step 1, and step 4 checks that `HEAD` is still that sha before it
  packages a task's diff: a builder that committed would have left its work
  out of the package. It packages against the noted sha, written in as a
  literal.
- run-plan hands `test-engineer` the plan's Testing Strategy section by
  heading, since the brief holds only the task's own section. Its rules file
  carries the gate and the failures it's expected to show, marked as not the
  task's to fix, so a builder doesn't chase failures that were already there.
- `test-engineer` may write the report file its brief names, and no longer
  stashes or reverts a fix already in the tree just to watch a regression
  test fail; it says the test wasn't seen failing. Its description and the
  README's agents table say so.
- `devops` stops and reports before a command it can't undo, and goes on
  only when resumed with the user's yes. A subagent can't wait for an answer.
- `frontend` was told to load a project's theme or design-system skill but
  had no `Skill` tool. It has one now, and a structural test fails any agent
  whose instructions load a skill without it. `frontend` and `uiux` load only
  a project's design skill (frontend) or their two design skills (uiux), never
  the Foundry's own `brainstorm`, `debug`, `run-plan`, or `ship`, and
  run-plan's builder report contract says the same.
- `uiux` falls back to its own design knowledge, and says so in its report,
  when its design skills aren't installed, as the README says. It had called
  them "not optional".
- The README's bug-fix line has `debug` pin the bug with a failing test, then
  `implement` fix it, as the skill does. It had `test-engineer` pin it after.
  The README also says `investigate` runs alone whether scoped or full, as the
  orchestrator's rule, rather than listing it among the rules the agents hold
  themselves to; it names the `debug` skill's working file among what the
  plugin writes; and it describes `tests/` as checking debug's polluter
  procedure too.
- The routine behavior-case command in `evals/README.md` and CONTRIBUTING.md
  passes `--ablation none`. Without it the harness adds a no-plugin baseline
  arm whose prompts can't load the plugin's skills, which only adds cost.

### Fixed
- `debug`'s first message on a production report handed the user a log
  command that wrote a file on the server (`> ~/newsbot-12h.log; wc -l ...`),
  joined two commands in one block (`cd ... &&`), and listed what to look for
  once at the end. The Production paragraph now says one command per block,
  never joined (a `cd` on its own line above is fine), nothing written on the
  server (no redirect, no `tee`), and what to look for under each block.
- debug's measuring line hid the seed a random-order search needs: `-q` drops
  the header that prints it, so a session that counted "fails 6 in 20" held
  no seed from any failing run. It now gives each run its own
  (`--randomly-seed=$i`), so the loop's number is the failing seed. The
  measuring grep also lacked the name boundary its techniques file has, so
  `test_y` counted `test_y_other` too. The polluter search only looked at
  tests that run before the victim in the default order, so it couldn't find a
  polluter that bites only in random order (the walkthrough's own example); it
  now takes the order from a failing run's seed when the failure is
  random-order only, and its halving steps say they may end on one test id,
  not only a file.
- debug's unittest check printed nothing before Python 3.11, whose `-v` line
  ends in the class, not the full test id, and lost the result when the test
  has a docstring, prints while it runs, or fails a subtest. A victim whose
  `setUpClass` or `setUpModule` failed read as "the id didn't match", since
  the victim never gets a line. The check is now one grep that shows the
  victim's line, its `FAIL:` or `ERROR:` header (a `setUpClass` or
  `setUpModule` one included) and the `Ran` footer, and the text says how to
  read them: a header means it failed, no header with a `Ran` line means it
  didn't, no victim line means the id didn't match, and no `Ran` line means
  the run stopped.
- run-plan's qa-pass command left `MB` empty if a session ran its two lines in
  separate Bash calls, packaging the wrong diff with no error. It now stops
  with a message when there's no merge-base, and says to run both in one call.
- `devops` and `test-engineer` each have a report line for what their bodies
  tell them to say (stopped before a command it can't undo; a regression test
  not seen failing).
- The brief-command tests crashed with 30 errors (as a non-root user) on a
  machine without zsh. They now skip zsh there, as the other shell tests
  already did.

### Measured
Real sessions, 4 runs each, after the fix batch that changed the text.
`debug-production-report`: $0.76 and 105 seconds, 1.00 in all four runs, and
`asks-and-hands-over` passed 12 of 12 votes, against 0 of 6 before the fix.
`run-plan-decisions`: 186 seconds, 0.97; the new item h passed in all four
runs, each answer running a real model session to check the finding `qa` had
only read, without stopping to ask. Item c failed in one run on a judge miss:
that answer said what the three passing ones said. A model has written a retro
in two debug runs, on an earlier commit; I haven't re-run that on this one.

## [2.1.1] — 2026-11-10

A docs-only patch. The README's credits now say who built the team: I wrote
each agent's job, chose its tools and its model, and set how work moves
between them. They used to say the team assembled itself. The credits also
link the two blog posts about the Foundry, the release in August and the
follow-up on the tenth agent. No behavior change.

## [2.1.0] — 2026-11-06

A minor version. The plugin directory refused 2.0.1 on its file-type and
front-matter checks. I probed a branch with the fixes, and the portal's
Validate came back clean of both rules, where a control on 2.0.1 flagged
`evals-expensive/compare.py` and `agents/architect.md`.

### Added
- Structural guards in `tests/` for the two rules the directory enforces: no
  file type outside Markdown, text, JSON, YAML, and a few image formats in a
  shipped path, and no front-matter key beyond the ones agents and skills use.
- A `dist` branch the plugin directory reads, built by a release step in
  CONTRIBUTING.md. The step fetches first, parents the new commit on
  `origin/dist`, and stops on a stale, untagged, or mis-tagged `main`, a file
  type or front-matter key the directory refuses, a release already built, or
  a local `dist` with commits `origin/dist` lacks.

### Changed
- run-plan's brief is a command written in the skill, not a script. It
  refuses a task number that isn't all digits.
- debug's polluter search is a written procedure that ends in a required
  check: what halving leaves is a suspect until the check holds, run as two
  commands of their own.
- `architect` and `investigate` no longer carry `permissionMode: plan`. It
  never applied in a plugin install. A manual install that wants it adds the
  line to its own copies (README).
- The five agent and skill descriptions the directory flagged are
  double-quoted, as its Validate asked.

### Removed
- `find-polluter` and its tests, and the `task-brief` script. `task-brief`'s
  tests now test run-plan's command.

### Measured
Task 5 ran the changed cases on real sessions, 2 runs each. Cost and score:
- debug cases: $3.03 and 501 seconds. `debug-polluted-test` scored 0.75
  and `debug-production-report` 0.83; the other four cases scored 1.00.
- architect plan format: $1.02 and 184 seconds, 1.00 in both runs.
- run-plan cases: $1.03 and 193 seconds. `run-plan-decisions` scored 0.93,
  `run-plan-resume` 1.00.
- The v2.0.1 baseline on the widened `debug-polluted-test`: $0.96, 124
  seconds, 0.63. `victim-untouched` failed in both runs.

The bar was missed on `ran-the-check`, which failed in both debug runs. I
kept the traces and re-ran ($0.87, 1.00 in both). In both runs the agent had
run the pair as a process of its own before the write-up, so the check was
there. The split votes came from how the grader read the form: a loop of
separate processes, and an interim "exactly one module" before the pin run.

Fix batch 1 made the procedure show the check and the grader judge it by
substance. The re-run on the fixed version ($0.89, 125 seconds) scored 1.00
in both, `ran-the-check` passing unanimously. That re-run covered only
`debug-polluted-test`, and it met the bar.

The traces say the grader's change moved the votes. The agents did not follow
the procedure's new form. Neither run called its result a suspect, and
only run 1 halved, once, before pairing each file with the victim; run 2
only paired. Both still found the right polluter and cause and left the
victim alone, 4 of the last 4 runs. Total spend on Task 5 was $7.80.

## [2.0.1] — 2026-11-06

A docs-only patch. The README and the privacy statement now say plainly how
the plugin handles credentials: none shipped, none read, and `ship` and
`devops` use the logins you already have. No behavior change.

## [2.0.0] — 2026-11-05

A major version, because the team changed: `file-reader` is a tenth agent,
and `investigate` now runs a different way (see CONTRIBUTING.md on majors).

### Added
- `file-reader`: an agent that reads one file, or one section of a big one,
  and reports what's in it with line numbers. It holds the Read tool and
  nothing else. `investigate` dispatches it; it isn't meant for direct use.
- `evals-expensive/`: the head-to-head and nesting smoke cases, the fixture
  generator, the grader sync script, the answer key, and the scorer,
  `compare.py`. They spend real model sessions, so nothing in `tests/`
  starts one and nothing runs them unless you do.

### Changed
- `investigate` now reads per file. On a new codebase it does a full sweep:
  every eligible file gets its own `file-reader`, 10 readers at a time, with
  about 150 files per area handed to an area lead on a big repo. A file over
  about 1,000 lines is split into sections of about 800 with about 50 lines
  of overlap. It stops and asks above 500 files. On a known codebase, or for
  a narrow question or named files, it reads a scoped set instead.
- `investigate`'s report always ends with Coverage: a mode line, then files
  listed, read, skipped (by reason), re-dispatched, failed, and every file
  left unread. Nothing is silently skipped. Unread files are listed by path
  on a per-file read and as counts per folder on a single-agent fallback,
  and untracked files are listed on a full sweep.
- The read-only exception, stated plainly: `investigate` still has no edit
  tools, but it can now spawn agents, and only its instructions keep it to
  `file-reader` and its own area leads, because Claude Code ignores
  `Agent(type)` restrictions in a subagent definition.
- Area leads return a per-file checklist, and the top-level `investigate`
  compares those against its own file list and sends a reader for each gap,
  so Coverage can name every unread file by path. A lead that fails gets one
  restart.
- The dispatch rule: run `investigate` one at a time, with nothing else that
  starts agents running alongside it, since even a scoped read starts readers
  10 at a time.
- `file-reader` runs on Haiku, with `investigate` and its area leads on
  Sonnet, on the owner's call after the Haiku check. Everything on Haiku was
  cheaper still, but one run lost its whole report and every run was slower.

### Measured
The readers-on-Haiku arm was measured twice: first before the qa pass's
checklist change, then re-run on the final version.

One 191-file test repo with 48 planted facts, 3 runs per arm, against
1.7.6 as the baseline (found and missed are out of 48 and per run; made up
has no ceiling):
- 1.7.6: found 35, 35, and 48; missed 13, 13, and 0; made up 0 in every run;
  about $0.47 a run.
- 2.0.0 with every agent on Sonnet: found 48 in every run, missed 0, made up
  0, about $5.57 a run.
- 2.0.0 as shipped, readers on Haiku: found 48 in every run, missed 0, made
  up 0, about $2.31 a run and about 708 seconds, a little faster than
  all-Sonnet's 764. This is the re-run on the final version. Before the
  checklist change the same arm cost about $2.62 and 796 seconds a run.

The raw head-to-head verdict was BAR MISSED, from scorer false positives on
decoys the reports marked dead. The owner chose to fix the scorer the first
time, and the rescored verdict is BAR MET. The readers-on-Haiku arm also
scored BAR MISSED raw (3 made up in one run, decoys the report marked dead
under a bold run-in label). The owner had the scorer fixed a second time and
every stored report rescored at no cost; the result was BAR MET, and the
baseline stayed at 0 made up. The re-run on the final version met the bar on
the scorer as fixed, with no rescore.

Plan mode: spawning works under it, both in a manual install (agents copied
to `.claude/agents/`) and with a local copy of `investigate` shadowing the
plugin's. In a manual install the first batch can fail once on the plugin's
agent name, and `investigate` retries with the bare name. A copy of
`investigate` in `~/.claude/agents/` gets plan mode for its own tool calls
only. Its area leads (above about 150 files) are dispatched under the plugin's
name first, so with the plugin installed they're the plugin's copy, which
ignores `permissionMode`, and nothing it starts inherits its plan mode (a
subagent with no `permissionMode` takes the main session's mode). Plan mode
applies only when the session itself is in default or plan mode.

## [1.7.6] — 2026-10-25

### Changed
- The README links the privacy statement from its "What it runs, sends, and
  fetches" section, where anyone looking for it would look first, and names
  the current Fable model.
- CONTRIBUTING says every release gets a GitHub Release alongside its tag.
  The tags ran to v1.7.5 while the repo page still called v1.1.0 the latest,
  which made a busy two months look like a quiet one.

## [1.7.5] — 2026-10-23

### Added
- `PRIVACY.md`: a short, plain statement that the plugin collects and sends
  nothing itself, and what it does inside your own session (your files, the
  web tools two agents use, and your own remote, behind the ship skill's ask).
- Listing links in `plugin.json` for the plugin directory: documentation
  (the README), support (GitHub Issues), and the privacy policy. A structural
  check makes sure the privacy link points at a file that exists.

## [1.7.4] — 2026-10-23

### Fixed
- The directory's credential hold came back because of 1.7.3's own new
  check: two of its patterns spelled out the environment lookups they look
  for, and the scanner read the regex text as code reading the environment.
  Those patterns are now built from pieces, like the others, and the check
  ignores backslashes when matching, so it would have caught a
  regex-escaped trigger like that one.

## [1.7.3] — 2026-10-23

### Fixed
- The directory's "contains a download-and-run command" warning, which is
  shown to people browsing the listing. Its trigger was the word eval
  sitting right before a closing backtick (in shell, eval over a command
  substitution is the classic way to run whatever a download returned).
  Six harmless lines had it: the eval command's name in code formatting,
  and qa's checklist item about eval in user input. The command is now
  written with its folder argument, `claude plugin eval .`, and qa's item
  as `eval()` or `new Function()`.

### Added
- A structural check for every pattern the directory's scanner has held or
  flagged on harmless text so far (that one, a line starting with the
  password-manager word, a fetch-and-run command, passing the whole
  environment, reading an environment variable by a computed name, and
  naming the icon's file). The directory rescans every new version, so it's
  cheaper to keep them out than to explain them to a reviewer again. The
  check builds its patterns from pieces, so the test file doesn't trip the
  scanner itself.

## [1.7.2] — 2026-10-23

### Fixed
- The directory's credential hold, third time: the `find-polluter` tests
  looked up their pass-through variables from a list, which the scanner reads
  as "an environment variable named at run time". Each one is now named
  outright (PATH, HOME, the temp folder, the locale), so what's passed along
  is visible to anyone reading the test.

## [1.7.1] — 2026-10-23

### Fixed
- Two more directory review holds, both the scanner pairing harmless text.
  The `find-polluter` tests handed pytest a copy of the whole environment,
  which read as "a credential leaving the machine" next to a mention of
  `ssh`; they now pass only what a child Python needs (PATH, HOME, the temp
  folder, the locale). And the 1.7.0 notes named the icon's file path, which
  held the release so a reviewer could check nothing runs an image; the path
  is gone from the notes.

## [1.7.0] — 2026-10-23

Everything here came out of the plugin directory's validation, run before the
first submission.

### Added
- A listing icon: a steel anvil with a glowing bar
  on a dark rounded square.

### Changed
- `qa` and `frontend` no longer download the accessibility scanner on the fly
  (`npx`, which fetches and runs code that isn't part of the plugin). They use
  the axe CLI if you've installed it, and otherwise skip the scan and say so.
- The four read-only agents (`investigate`, `architect`, `qa`, `uiux`) now say
  outright that Bash is for reading and for running builds and tests, never
  for changing anything. Claude Code ignores `permissionMode` for agents that
  come from a plugin, so in a plugin install that instruction, plus having no
  edit tools, is what keeps them read-only.

### Fixed
- The README claimed `investigate` and `architect` run in plan mode, which
  hard-blocks changes even through Bash. That's true only for a manual
  install; it now says so, and how to get the hard block back.
- A sentence in `run-plan` wrapped so that a line began with "pass", which the
  directory's scanner read as the `pass` password manager reading a
  credential. Reworded; the directory's credential hold no longer has
  anything to match.

## [1.6.1] — 2026-10-23

### Added
- README section "What it runs, sends, and fetches": every shell, file, web,
  and download behavior in one place (shell commands in the project, which
  agents write files and where, web search and fetch, the desktop app's
  browser, the npm download for the accessibility scan, the image build,
  ship's outward-facing steps, the two scripts, and when the eval fixtures
  run). The plugin directory's security scan asks for exactly this, and
  anyone installing the plugin deserves it anyway.

## [1.6.0] — 2026-10-23

### Added
- Behavior cases for two agents: `architect-plan-format` dispatches the
  architect on a small design and runs run-plan's own `task-brief` script on
  the plan it returns, so "the plan is in a format run-plan can split" is
  checked by the script, not a judge, along with its header and Verify
  commands; `implement-test-first` checks, from the run's trace, that the
  failing test runs before the code is edited.

### Changed
- `docs/walkthrough.md` rewritten for the current pipeline: brainstorm,
  investigate, architect, run-plan (with implement, test-engineer, qa, and
  docs inside it), a debug detour, and ship. It was last touched at 1.1.0,
  before any skill existed.
- `architect` names every file by its path from the repo root, never an
  absolute path. Its first eval run wrote plans pointing into one run's temp
  folder, and plans get committed.
- `brainstorm` commits the design on the feature branch the build will use,
  and points at the architect's Risks section for decisions (it used to name
  an "owner decisions" section the architect doesn't have). `run-plan` stays
  on that branch, and its per-task spec check now gets the design section
  too, so a requirement the plan dropped can be caught at the task instead of
  at the final review. `ship` asks before pushing a CI fix to the PR branch.
  All four were found while rewriting the walkthrough.

## [1.5.0] — 2026-10-23

### Added
- Structural checks (`tests/test_structure.py`): the repo is held to its
  own README. Each agent's model and write access must match the team
  table, the plan-mode agents must be the ones the README names, uiux keeps
  its observation-only browser tools, every file a skill points at exists
  (scripts executable), every script has tests, the agent and skill counts
  and lists match everywhere they're written, `plugin.json`'s version is the
  newest CHANGELOG entry, every `the-foundry:<name>` reference names
  something real, and the eval library is complete. Each check was proven
  by breaking a copy of the repo the way it guards against.
- Tests for `find-polluter` (`tests/test_find_polluter.py`): tiny pytest
  projects built per test, covering bisection, `--tests`, `--runs`, `--cmd`,
  every exit path, and victims in classes, parametrized, `./` and absolute.
  They need a Python with pytest (`FOUNDRY_PYTEST_PYTHON`) and skip without
  one.
- A behavior library for the skills (`evals/`, 18 cases for
  `claude plugin eval .`): conversations and decision points for brainstorm,
  run-plan, debug and ship, planted-bug repos for debug, a scratch release
  for ship, and qa's spec check on a planted diff. Hard lines (no push before
  the ask, no ssh, no code before approval) are exact checks over the trace;
  judgment is graded by a rubric. See `evals/README.md`.

### Fixed
- `find-polluter` said a valid victim "didn't run" when it was given as
  `./tests/...` or an absolute path (including one through a symlinked
  folder), counted the victim's own file as a candidate in those forms, and
  suggested `--tests` in `--cmd` mode, where `--tests` is refused. All found
  by the new tests.

### Changed
- `brainstorm` asks one opening question, not three stacked in one sentence,
  and treats "sounds great, build it" partway through as approval of the part
  just shown, asking in one line whether to skip the rest. Both found by the
  eval library on its first runs.

## [1.4.1] — 2026-10-23

### Fixed
- `ship` told the session to bind a PR to the desktop app's monitor and "let
  it tell you" when CI finished. That monitor wakes the session on CI
  failures, not on success, so a session following it would wait forever
  for a green CI. It now reads the status once, says CI is still running,
  and merges when the user brings it back. Found on the first real use
  (newsbot PR #66). The wait for a tag's build says the same: a tag has no
  PR for the monitor to see.

## [1.4.0] — 2026-10-23

### Added
- `ship` skill: takes finished work from a branch to production. Preflight
  (the gate, a clean tree, the version bumped everywhere, release notes, prose
  the change made untrue, the tag not taken), then one ask listing every
  outward-facing step, then push, PR, CI (re-running a check GitHub leaves
  "in progress" after its run passed), merge, a local image check, the tag,
  and a wait for the tag's own build before the deploy commands are handed
  over. The user runs every production command; the skill updates the status
  docs afterwards and asks before pushing them. It learns each project's
  habits from its runbook and history first, so a project that ships straight
  to `main` with lightweight tags gets exactly that.
- A test suite for the skills' scripts (`tests/`, stdlib `unittest`; run
  `python3 -m unittest discover -s tests -q`).

### Fixed
- run-plan's `task-brief` script found no task at all in a plan whose
  samples contained lines starting with three backticks inside a fenced
  block. It now tracks fences the way CommonMark does (same character, a
  closing run at least as long as the opener, nothing after it), which also
  fixes a four-backtick fence holding ordinary three-backtick blocks.

### Changed
- The orchestrator block routes releases through `ship`, and run-plan hands
  off to it.

## [1.3.0] — 2026-10-22

### Added
- `debug` skill: finds a failure's root cause before anything gets fixed. It
  asks the user what they saw (numbered questions, or one batch when they're
  away), reproduces the failure on demand and measures an intermittent one,
  makes a hang fail with stack dumps instead of stalling, tests one
  hypothesis at a time, and pins the cause with a deterministic failing test
  before routing the fix to `implement` (or to `test-engineer` when the test
  was the bug). Three failed fixes stop it to question the design with the
  user. Production commands go to the user to run. A techniques reference
  covers pollution, races, waiting on a condition, hangs, tracing values,
  bisecting, and environment differences, and a `find-polluter` script
  bisects a pytest suite for the test that leaves state behind.

### Changed
- The orchestrator block routes bugs and flaky tests through `debug`.

## [1.2.0] — 2026-10-22

### Added
- Two skills, run by the orchestrating session because they have to talk
  with you, which a subagent can't:
  - `brainstorm` turns a request into an approved design before the
    architect plans it: numbered questions with a recommended option, the
    design played back in numbered parts, a batch mode for when you're on
    your phone, a cold read of the written design by a fresh subagent, and a
    new numbered section in `docs/design.md`. Nothing gets built until the
    design is approved.
  - `run-plan` executes a multi-task plan with the agents: per task, a brief
    file, the builder, a test-engineer adversarial round, at most three fix
    rounds, and the project's gate with its real exit code before the commit;
    then a qa pass over the branch, fix batches, and docs. Progress and
    rulings live in a build log at the end of the plan, so a compacted
    session can resume. Ships a small `task-brief` script that copies one
    task out of a plan.
- `qa` spec-check mode: checks that a change does what its brief or design
  says, no more and no less, before the usual defect review.

### Changed
- `architect` plans now open with a header (plan file path, design section,
  branch, gate, rules for every agent), use `### Task N:` headings, give every
  task exact verification commands, and size each task to one implement
  dispatch.
- `implement` writes the failing test first for bug fixes and changes with a
  clear contract, and watches it fail before fixing.
- The orchestrator block in `docs/orchestrator.md` routes new features through
  `brainstorm` and long plans through `run-plan`, and adds three working rules:
  evidence before claims, parallel dispatch of independent work, and checking
  outside review comments before agreeing with them.

## [1.1.2] — 2026-09-02

### Changed
- Agents now practice what the README references: `qa` gained a WCAG 2.2
  accessibility review category plus an axe-core CLI verification step,
  `frontend` runs an axe scan on affected pages during visual verification,
  and `uiux` names Apple's Human Interface Guidelines and Material Design 3
  as its platform-idiom reference points (WCAG pinned to 2.2 throughout).
- README documents the axe CLI's external requirements (Node.js and
  Chrome/Chromium); agents skip the scan and say so when they're missing.

## [1.1.1] — 2026-09-02

### Changed
- Replaced the companion-skill recommendation in the README with
  accessibility references (WCAG 2.2, axe-core) and design references
  (Apple Human Interface Guidelines, Material Design 3).

## [1.1.0] — 2026-08-28

### Added
- Claude Code plugin packaging (`.claude-plugin/plugin.json` +
  `marketplace.json`): the repo is now its own one-command marketplace.
  Install with `/plugin marketplace add SomeClown/the-foundry` then
  `/plugin install the-foundry@the-foundry`.
- `docs/walkthrough.md` — a worked example tracing one feature through the
  full pipeline, with real briefing prompts and what each stage catches.
- `docs/orchestrator.md` — a copy-paste CLAUDE.md block that teaches the
  orchestrating session to route work to the team, plus usage notes.
- `CONTRIBUTING.md` and this changelog.

### Changed
- README substantially expanded and rewritten: plugin install as the primary
  path, customization and contribution guidance, and links to the new docs.
- Light editorial pass across the nine agent definitions.

## [1.0.0] — 2026-08-27

### Added
- Initial public release: nine agent definitions (investigate, architect,
  uiux, implement, frontend, test-engineer, qa, devops, docs), README with
  team roster, model and permission policy, pipeline, and manual install
  instructions. MIT license.
