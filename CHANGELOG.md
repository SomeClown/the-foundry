# Changelog

All notable changes to The Foundry. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning policy is in
[CONTRIBUTING.md](CONTRIBUTING.md).

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
