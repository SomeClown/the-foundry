# Changelog

All notable changes to The Foundry. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning policy is in
[CONTRIBUTING.md](CONTRIBUTING.md).

## [Unreleased]

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
