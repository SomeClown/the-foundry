# Changelog

All notable changes to The Foundry. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning policy is in
[CONTRIBUTING.md](CONTRIBUTING.md).

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
