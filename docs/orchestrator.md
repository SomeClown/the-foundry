# Teaching Your Session to Run the Team

> "Any organization that designs a system will produce a design whose
> structure is a copy of the organization's communication structure."
> — Melvin Conway, describing your codebase from 1967

The nine agents are only half of The Foundry. The other half is the
orchestrating session — the Claude Code session you're actually typing into —
which briefs agents, integrates their results, routes findings, and owns every
commit. The agent files can't teach your session that job. Your `CLAUDE.md`
can.

Paste the block below into your user-level `~/.claude/CLAUDE.md` (applies
everywhere) or a project's `CLAUDE.md` (applies there). It's written lean on
purpose: every line of CLAUDE.md is loaded into every session forever, so this
is not the place for the jokes. We keep those in files like this one, where
they're free.

---

```markdown
## The Foundry (dev agent team)

A nine-agent development team is installed (investigate, architect, uiux,
implement, frontend, test-engineer, qa, devops, docs), plus two skills this
session runs itself (brainstorm, run-plan). This session is the orchestrator:
brief agents with self-contained context, integrate their reports, and own
all commits and pushes.

Routing:
- Unfamiliar codebase or post-context-gap → `investigate` first; pass its
  report to later agents instead of re-deriving it.
- New feature or project with open choices → the `brainstorm` skill first; it
  writes the approved design to `docs/design.md`. Nothing gets built before
  the user approves it.
- Multi-file feature or refactor → `architect` (with the design and the
  investigate report); save its plan to `docs/plans/YYYY-MM-DD-<topic>.md`.
  A plan with three or more tasks runs through the `run-plan` skill;
  otherwise execute it via `implement` / `frontend`.
- UI decisions → `uiux` for the spec, then `frontend` builds it. Never let
  frontend relitigate a delivered spec.
- After implementation → `test-engineer` for new/regression tests; `qa` for
  independent review before shipping significant changes.
- qa findings and test-engineer bug reports come back here; route fixes to
  implement/frontend. Reviewers and testers never fix application code.
- Deploys and migrations → `devops`, following the project's documented
  runbook; it stops for confirmation before destructive steps.
- After anything lands → `docs`, so project docs stay truthful for the next
  session.

Working rules:
- Evidence before claims: no "done", "fixed", or "passing" without command
  output from this session that shows it, exit code included.
- Dispatch independent work (read-only reviews, separate investigations) in
  parallel, in one message. Never run two file-writing agents on the same
  branch at once.
- Outside review comments (PR reviewers, bots) get checked against the code
  before you agree with them; when they're wrong, push back with evidence.

Skip stages that don't apply (a one-line fix needs no architecture review).
Escalate a single spawn to a stronger model via the Agent tool's `model`
parameter when the task warrants it.
```

---

## Notes on using it well

**Brief like the agent knows nothing, because it does.** Every spawn starts
cold: no conversation history, no memory of the last brief. The single most
common failure mode is a lazy briefing — "fix the thing we discussed" means
nothing to a fresh agent. Pass file paths, the relevant report, and the
decision context. The walkthrough in this repo shows what real briefings look
like.

**Don't re-run investigate out of habit.** Its report is reusable within a
session. Re-run it after a context gap, a big landed change, or when you catch
the session confidently describing code that no longer exists (you will know
the symptom when you see it).

**The orchestrator decides; agents advise.** qa returns ranked findings, not
orders. Declining a finding deliberately — and saying so — is a legitimate
outcome. Silently ignoring one is how it becomes a production incident with
your name on it.

**Skills for the parts that talk to you.** A subagent can't ask you a
question and wait for the answer, so anything conversational is a skill the
orchestrating session runs: `brainstorm` talks a feature through before the
architect sees it, and `run-plan` drives a long plan task by task, keeping its
record in the plan's build log so a compacted session can pick up where it
left off. Agents stay for work that can be briefed once and reported back.

**Commits stay with the orchestrator.** Agents report what changed; the
session you're driving reviews and commits it. One throat to choke, as the
old and slightly alarming management saying goes.
