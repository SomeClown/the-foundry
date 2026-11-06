# Design

Approved designs for the Foundry, newest last. Each section records what the
owner decided and why; an "As built" subsection records what changed during
the build.

## 1. Per-file investigation (v2.0.0, approved 2026-11-05)

`investigate` reads a codebase as one agent holding everything in one context,
and on a large codebase that's where accuracy goes: material in the middle of
a long context gets used less reliably than material at either end, the
"lost in the middle" effect. This change gives each file its own reader, so no
reader has to hold more than one file, and investigate compiles what they
report. Keeping contexts small is a welcome side effect, not the point. I
haven't measured the effect on these models, and the research I know of is
older than they are, so the build has to prove the gain before it ships
(Part 8).

**Owner decisions (2026-11-05):**

- The main goal is accuracy, by avoiding lost in the middle. Protecting the
  main session's context is a good secondary goal.
- One agent per file. Each reports up, never to another reader.
- 1A: investigate runs the readers, not the orchestrator, and accepts the
  read-only exception that comes with it.
- 2A: a new tenth agent, `file-reader`, holding only the `Read` tool. Adding
  an agent makes this a major version.
- 3A: on a new codebase, every tracked text file except lock files and
  generated, vendored, or data files.
- 4A: on a known codebase, one agent per file for the files in the task's
  scope only.
- 5B: readers run on Sonnet.
- Approved with the direction: big files split into sections, a middle layer
  of area leads on big repos, a gap check, line citations that investigate
  re-reads, and a head-to-head test against today's investigate.
- Approved assumptions: 10 readers at a time, a stop above 500 files, a
  codebase counts as new unless the brief says otherwise, and the report
  contents in Part 3.
- From the cold read, 1A: a one-question brief reads only the relevant files,
  one agent per file, even on a new codebase.
- From the cold read, 2A: the test's bar, as written in Part 8.

**Goals**

- Find more of what's actually in a large codebase than today's investigate
  does, by a margin the test can show.
- Report plainly what was read, what was skipped, and what failed.

**Non-goals**

- Changing `qa`, `architect`, or `uiux`.
- Saving tokens. This costs more in total, and that's accepted. Bundling very
  small files is a later question if the test shows real waste.
- Having readers work out how files relate. That stays investigate's job.

**Anti-goals** (a failure even if it technically works)

- Shipping it when it doesn't clearly beat today's investigate.
- A reader that can write, spawn agents, or talk to another reader.
- A silent gap: a file nobody read that the report doesn't mention.
- Rollups that trim a route or endpoint inventory to save space.

**Constraints** (from the Claude Code subagent docs, checked 2026-11-05, and a
live nesting test the same day)

- Subagents can nest up to three layers below the main session.
- At that limit Claude Code silently withholds the `Agent` tool, and the
  owner's environment can lower the limit.
- At 20 running subagents in a session, the next spawn fails rather than
  waits, and the error says not to retry.
- `Agent(type)` restrictions are ignored inside a subagent definition, so
  "spawn only `file-reader`" can only be an instruction.
- Plugin agents ignore `permissionMode`.
- A subagent can't ask the user anything.
- Every push to main triggers a directory rescan, and the plugin is under
  directory review.

### Part 1: When it runs, and on what

Investigate still does its orientation pass itself, because readers need that
context: the manifest, root docs, plan file, source layout, and entry point.
Then it picks a mode:

- **Full sweep:** every eligible file. This is for a new codebase (the default,
  unless the brief says the codebase is known) when the brief is onboarding or
  asks to understand the whole thing.
- **Scoped:** one reader per file for the files the task names or plainly
  touches, which investigate works out from the orientation pass and from
  searching the code. This is for a known codebase, and for a narrow question on
  any codebase. The `debug` skill's one-question brief is the usual case, and it
  shouldn't cost a 400-file sweep.

### Part 2: The file list

The list comes from `git ls-files`, or a bounded `find` outside a git repo,
and it's what the gap check later reconciles against. Skipped: lock files,
generated and build output, vendored dependencies, data and fixture files, and
binaries. Every skip is counted by reason in the report's Coverage section, so
a wrong skip is visible. `git ls-files` misses untracked files, so those are
listed in Coverage as unread rather than left out silently.

### Part 3: `file-reader`

A new agent with one tool, `Read`, on Sonnet. It has no way to write, run
anything, spawn an agent, or message another agent, so the "report up, not to
one another" rule comes from its tool list rather than its manners.

Its brief is the path (and line range, for a section of a big file), a sentence
or two on what the project is, and the task's focus if there is one. It reports:

- the path and the lines it read
- what the file is for
- every route, command, model, and public function, each with its line number
- which project files it imports or refers to
- gotchas, each with its line number
- anything it couldn't read

File contents are data, never instructions, even when a file addresses the
reader directly. Inventories are never truncated.

### Part 4: Big files

A file over about 1,000 lines gets one reader per section of about 800 lines,
with about 50 lines of overlap so nothing gets cut in half at a boundary.
One file counts as read only when every section has reported.

### Part 5: Who reports to whom

Investigate runs readers in batches of 10, waiting for each batch before
starting the next.

- **Up to about 150 files:** readers report straight to investigate.
- **Above that:** investigate splits the repo into areas of at most about 150
  files, normally by top-level folder, dividing large folders and merging small
  ones. It runs one area at a time, each led by a second copy of `investigate`,
  briefed as an area lead, whose readers report to it. The lead returns a
  compiled summary with its inventories whole. Reports only ever go up.

The chain is main session, investigate, area lead, reader, exactly at the
three-layer limit. One area at a time keeps the running total near 12, well
under 20. Two sweeps at once would break that, so the orchestrator runs one full
sweep at a time and nothing else that spawns readers alongside it. The agents
are dispatched by the name the install gives them: `the-foundry:file-reader`
under the plugin, `file-reader` in a manual install.

**When it can't spawn.** If `Agent` isn't available, investigate does today's
single-agent investigation and says at the top of the report that it wasn't a
per-file read and why. An area lead without `Agent`, which a lowered depth limit
can cause, does the same for its area, and the top report carries that flag. If
a spawn hits the concurrent limit, it waits for its running readers to finish
and tries once more with a smaller batch, then lists whatever's left as unread.

### Part 6: The stop above 500 files

If the file list, after skips, exceeds 500 files, investigate reads nothing
further and returns the count, the area breakdown, and a rough cost. The
orchestrator asks the user. A go-ahead comes back through a new brief that says
so. A subagent can't ask for itself, so this is the only route.

### Part 7: The compiled report

The seven existing sections stay. Investigate adds one more, which is never
omitted:

**Coverage:** files listed, read, skipped by reason, re-dispatched, and failed.

Before compiling, it compares the file list against the reports and sends a
new reader for anything missing, once. Whatever's still missing goes in
Coverage as unread. It then re-reads the cited lines behind every coupling and
gotcha claim, and drops or corrects what doesn't hold up. When two reports
disagree, it reads the code rather than choosing one.

With area leads, each lead does the gap check and the re-reads for its own area.
The top-level investigate only checks claims that cross areas, since doing all of
it at the top would rebuild the long context this design exists to avoid.

### Part 8: Proving it works

The first thing the build does, on its feature branch and before any docs, is
put the new agents in place and run a head-to-head test: a fixture codebase of
more than 150 files, so area leads get exercised, with routes and gotchas planted
in the middle of big files and in the middle of the repo, run against today's
investigate and the new one, at least three runs each. Until the docs catch up,
the structural tests that compare the team table and counts against the agent
files are expected to fail, and the build log says so.

How it runs, from a read of `evals/README.md` (no eval has been run yet):

- A smoke test comes first, because three nested layers under
  `claude plugin eval .` haven't been tried. If they don't work there, the test
  moves to a scratch project driven with `claude -p`.
- The baseline is a checkout of 1.7.6 run as its own target, since the harness
  only compares against no plugin. The comparison happens outside the harness.
- Each planted fact gets its own check against the final report only. Checking
  the full trace would count a raw file read as finding the fact.
- The fixture needs the `./bin/git` wrapper, since plain `git` is blocked in the
  sandbox, and the brief has to pass that along to area leads.
- The case lives outside the routine library (`--eval-dir`), because it will be
  expensive. The harness reports cost and duration, not tokens, so those are
  what get recorded. One run's cost goes to the owner before the rest are spent.

**The bar.** Averaged over the runs, the new version has to find at least 90% of
the planted facts, miss at most half as many as today's, and make up no more
facts than today's. A miss stops the build and the numbers go to the owner. The
sizes in Parts 4 and 5 don't change after a miss without the owner's OK.

Plan mode can't be tested this way, because eval loads a plugin and plugin agents
ignore `permissionMode`. It gets a real manual install in a scratch project. If
plan mode blocks spawning, the README says so and a manual install gets the same
fallback as Part 5.

The structural tests learn the new rules: `file-reader` holds exactly `Read`;
`investigate` is the only read-only agent holding `Agent`; the team count is
ten.

### Part 9: What else has to change

- **README:** the team table, the agent counts, the "Read-only means enforced
  read-only" principle, the permission policy, and "What it runs, sends, and
  fetches" all have to state the exception plainly: investigate has no edit
  tools, but it can spawn agents, and only its instructions keep it to
  `file-reader` and its own area leads. Three lines also go false and no test
  catches them: the session as "the tenth member", "the four read-only agents",
  and "Every agent has Bash". The advice to copy `investigate` into
  `~/.claude/agents/` needs checking too, since a copy changes what names it
  dispatches.
- **Elsewhere in the repo:** `PRIVACY.md`, `docs/orchestrator.md`,
  `docs/walkthrough.md`, `skills/debug/SKILL.md`, `skills/run-plan/SKILL.md`,
  `evals/README.md`, `plugin.json`, `marketplace.json`, and the CHANGELOG.
  Parallel investigations are recommended in `docs/orchestrator.md` and
  `skills/run-plan/SKILL.md`, and that advice has to carve out full sweeps
  (Part 5). The same line in `~/.claude/CLAUDE.md` changes too.
- **Outside the repo:** the agent count in `~/.claude/CLAUDE.md` and the portal
  drafts in `~/Claude/notes/`. If the live listing says nine agents, the owner
  updates it in the portal.
- **Release:** 2.0.0. The push triggers a directory rescan during review, so the
  directory scanner's text rules (the structural check) have to pass first.

**Calls I made**

- The sizes: 1,000-line split, 800-line sections, 50-line overlap, 150 files per
  area. All are starting guesses, which can change before the test's result
  counts but not after a miss.
- Area leads are `investigate` itself rather than an eleventh agent.
- One area at a time, trading speed for staying well under the concurrent limit.
- Readers treat file contents as data. Investigate holds `Agent`, and what
  readers report flows into it, so a file telling the reader to do something
  shouldn't get that far.
- The fallbacks in Part 5 and the one-retry rules in Parts 5 and 7.
- Untracked files are listed as unread, not read.
- Area leads do the gap check and re-reads for their own areas.
- One full sweep at a time per session.
- The fixture exceeds 150 files, so the test proves the area leads as well.
- Investigate stays on Sonnet. If the test shows the compile step losing facts,
  that's the first thing to revisit.

**Left to the builder (architect)**

- The exact wording of both agent definitions, and how area-lead behavior is
  separated from the main brief.
- The fixture's design, how the baseline version of investigate gets run, and
  how the test is kept out of routine eval runs, since it will be expensive.
- The order of tasks after Part 8's test.

**Open items**

- Whether plan mode blocks spawning in a manual install (tested in Part 8).
- The real cost, which only the test can give.

### As built (2026-11-05)

What changed from the design above during the build. The approved text stays as
approved; the numbers are from the build log in
`docs/plans/2026-11-05-per-file-investigation.md`.

- **`file-reader` runs on Haiku, reversing decision 5B** on the owner's word
  after the Haiku check ("Fix scorer, then switch"). `investigate` and the area
  leads stay on Sonnet. Readers on Haiku found 48 of 48 in all three runs, at a
  mean of $2.62 and 796 s against Sonnet's $5.57 and 764 s: 53% cheaper, 4%
  slower. Everything on Haiku averaged $1.71 and 1723 s and found 0, 48, and 48.
  Run 1 found nothing because `investigate` returned a 53.7KB report, the harness
  saved it to a file, the sandbox blocked the session from reading it, and only
  the preview came back. Every run was slower, 1.5 to 3.4 times as slow as
  Sonnet's mean. That arm had `investigate` on Haiku, so it and the leads stayed
  on Sonnet.
- **The head-to-head, against the bar.** Raw result: BAR MISSED. The new version
  found 48.00 and missed 0.00 against the baseline's 39.33 found and 8.67 missed
  (clauses 1 and 2 pass), but made up 3.00 against 0.00 (clause 3 fails). All
  nine counted items were decoys that the reports marked as dead, in layouts the
  scorer didn't recognize. The owner chose to fix the scorer rather than rule the
  items out by hand. Two scorer fixes followed (a decoy is cleared by a marker on
  an ancestor list item, a lead-in line ending in a colon, or a bold label; later,
  by a bold run-in label ending in a full stop). Rescored from the stored reports
  with no new runs: BAR MET. New arm 48.00 found, 0.00 missed, 0.00 made up, $5.57,
  764 s; baseline 39.33 found, 8.67 missed, 0.00 made up, $0.47, 109 s. The
  readers-on-Haiku arm was rescored to 48/48/48 found and 0 made up, BAR MET.
  Everything on Haiku stayed BAR MISSED.
- **Part 7 amendment (qa fix batch 1).** Area leads return a per-file checklist,
  and the top-level `investigate` reconciles those checklists against its file
  list by path. This closes a silent gap the design's own anti-goals rule out: a
  lead could report an area as done with files unread. A failed or cut-off lead
  gets one restart. The head-to-head measured the definition as it stood before
  this change, and the owner had the readers arm re-run on the final definition. It met the
  bar: 48/48/48 found, 0 missed, 0 made up, $2.31 and 708 s a run.
- **The nesting limit can be raised or lowered.** The constraint "can lower the
  limit" above is wrong; the owner's environment can do either.
- **Line-number accuracy on Haiku was never measured.** Two Haiku runs report a
  reader that was off by one on a line number, which a lead corrected by grep.
- **The reader's gotcha template mirrors the test prompt's fact shapes.** This
  came from Task 3 and no ruling recorded it.
- **Rulings that changed what got built:**
  - Mode: on a new codebase, a full sweep unless the brief asks one narrow
    question or names files; on a known one, scoped unless the brief asks for the
    whole thing. A focus alone doesn't make a read scoped. In scoped mode the stop,
    the split, the gap check, and Coverage count the scoped set.
  - A fourth mode line, `Mode: single agent, not a per-file read`, for the
    fallback. Leads' Coverage has no mode line.
  - On a fallback, unread files are given as a count per folder, not by path. A
    lead that fell back keeps the mode line, and the first-line flag names its
    area.
  - A stop reply (STOPPED BEFORE READING) takes precedence over the not-a-per-file
    flag, and carries no Coverage section.
  - Dispatch-name order: the plugin name `the-foundry:file-reader` first, then
    `file-reader`, treating "not found" as a naming miss rather than a failure to
    spawn. Leads are given the working name on a `Reader agent:` line, limited to
    the two reader names.
  - Concurrency retry continues in batches of 5 for readers; leads stay one at a
    time. After a second refusal there is no first-line flag, and the unstarted
    files are listed by path in Coverage.
  - Untracked files are listed, not read, on a full sweep, and read when a scoped
    read names them. They don't count toward the 500-file stop.
  - Plan mode (Task 9): spawning works in a manual install and in a shadow copy
    of `investigate`. In a manual install the first batch fails once under the
    plugin name before the bare name works, and `investigate` mentions the
    plan-mode notice on its first line.
  - Full sweeps run one at a time unless each brief says the codebase is known or
    asks one narrow question.

## 2. Directory file rules (v2.1.0, approved 2026-11-06)

The plugin directory refused 2.0.1 on two checks that only Verified
organizations get past, and there's no way to apply to become one. The plugin
may ship only Markdown, text, JSON, YAML, and images (plus a license, a
readme, `.gitignore`, and the icon), and its frontmatter may use only keys on
an allowed list. The Foundry ships two scripts, `find-polluter` and
`task-brief`, and keeps 21 more files of Python and shell in its tests and
evals. Two agents carry `permissionMode`. This change makes what the
directory installs pass both checks, without losing the tests and evals that
hold the repo to its own README, and without making the two skills that used
the scripts less exact than they are.

**Owner decisions (2026-11-06):** the owner took every recommendation in the
plan (`docs/plans/2026-11-06-directory-file-rules.md`, §4):

- 1C: the directory reads a `dist` branch, built from `main` at each release
  without `tests/`, `evals/`, `evals-expensive/`, or `docs/plans/`. The repo
  root stays the plugin folder, and `main` keeps everything.
- 2: probe first. A probe branch holding the 27 files `dist` would hold gets
  the portal's Validate, without a submission, before any code changes.
- 3: this design section, approved before Task 1.
- 4: widen the `debug-polluted-test` fixture so halving actually happens, add
  a grader that requires the final check, and run a v2.0.1 baseline on it.
- 5: about $5.65 of evals forecast, capped at $11 with the baseline.
- 6: version 2.1.0.
- 7: drop `permissionMode`. The README tells manual-install users how to add
  it to their own copies.
- 8: the GitHub marketplace keeps `"source": "./"` on `main`.
- 9: leave the non-blocking warnings, except what moving the dev files off
  the shipped tree fixes anyway.

**Goals**

- Everything the directory installs passes its file-type and frontmatter
  checks, and a test fails if that ever stops being true.
- run-plan's brief stays a byte-exact copy of the plan's task.
- debug still names the right polluter, and proves it before naming it.

**Non-goals**

- Changing what any agent does, or what users of the GitHub marketplace get.
- Becoming a Verified organization.
- Rewording §1. It's an approved record; this section supersedes it on
  `permissionMode`.

**Anti-goals** (a failure even if it technically works)

- A program disguised as Markdown: a heredoc to write out and run, or code
  renamed to an allowed extension.
- A brief the model writes out by hand, where a value can drift.
- Naming a polluter without the check: the victim passes alone, and fails
  run right after the polluter with nothing else.
- A `dist` branch anyone edits by hand.

**The behavior**

- **The brief.** run-plan's SKILL.md gives a short `awk` command, run through
  Bash, that copies Task N out of the plan from its heading to the next task
  heading or the next heading at the same level or higher, skipping headings
  inside code fences. It prints the same `<path> (<N> lines)` line the script
  did.
- **The polluter search.** debug's techniques file gives a written halving
  procedure, using the project's own test runner, that reads the victim's own
  result, not the run's exit code, and ends in the required check.
- **Frontmatter.** Agents use `name`, `description`, `tools`, and `model`;
  skills use `name` and `description`. A test holds them to that.
- **`dist`.** CONTRIBUTING gives the commands that build it from a tagged
  `main`, and the release validates its export before the push. A test pins
  the four left-out folders to those commands, and another fails if a
  shipped path holds a file type the directory refuses.

**The probe (2026-11-06).** The portal's Validate, run on
`probe/directory-rules` at 7bc9414 without submitting, passed with neither
finding, and the form took the branch. The same form run on `main` at
341a16f, as a control, did flag both, naming `evals-expensive/compare.py` and
`agents/architect.md · permissionMode`, so Validate does run these checks.

**Calls I made**

- `permissionMode` is the frontmatter key the portal objects to. The
  submission's report named no key; the control run above named it.
- `docs/plans/` leaves the shipped tree with the tests and evals. It's build
  history, not something a user needs, and it holds a line the scanner
  flagged.
- `dist` carries no history from `main`: each commit's parent is the previous
  `dist` commit.

**Left to the builder:** everything the plan specifies, task by task.

**Open:** whether the existing submission can switch its branch to `dist`
while it shows "Needs changes", or needs a withdraw and resubmit with the
same repo and path. The Settings tab's branch field is enabled, but its note
says the branch can't change under review. That gets settled at ship time.
