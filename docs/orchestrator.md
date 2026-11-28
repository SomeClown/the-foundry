# Teaching Your Session to Run the Team

> "Any organization that designs a system will produce a design whose
> structure is a copy of the organization's communication structure."
> — Melvin Conway, describing your codebase from 1967

The eleven agents are only half of The Foundry. The other half is the
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

An eleven-agent development team is installed (investigate, area-lead, file-reader, architect,
uiux, implement, frontend, test-engineer, qa, devops, docs), plus four skills this
session runs itself (brainstorm, run-plan, debug, ship). `file-reader` is
dispatched only by `investigate` and `area-lead`, and `area-lead` only by `investigate`. This session is the orchestrator: brief agents
with self-contained context, integrate their reports, and own all commits and
pushes.

Routing:
- Unfamiliar codebase or post-context-gap → `investigate` first; pass its
  report to later agents instead of re-deriving it. It never stops to ask, at
  any size. A repo too big for one report comes back one part at a time, and
  each part's first line (second, under `NOT A PER-FILE READ`) says what's
  left. While that line isn't the `0` one:
  1. Dispatch `investigate` again. The brief is `CONTINUE SWEEP` on its first
     line, then every line from `Project:` to `END OF BLOCK` in the report,
     copied as it stands. Copy it from the report's full text, never from a
     preview, add, fix or drop nothing, and check it holds as many area lines
     as the `<n>` on the report's `SWEEP IN PARTS` line. Don't ask the user.
  2. Wait for it before anything else that starts agents.
  3. Stop when a report says `SWEEP IN PARTS: 0 areas not read`. Then tell
     the user the repo was read in parts, how many, and anything a part named
     as unread. That includes every `Area dropped:` and `Count changed:` line.

  A scoped read can come back with `SWEEP IN PARTS: <n> files not read`
  instead. Send the original brief again, with "Read only these files:" and
  the unread paths from its Coverage. That list replaces any file list or
  scope the original brief gave. The loop ends when a report has no such line.
- Every `investigate` report ends with `INVESTIGATE REPORT ENDS`. One that
  doesn't was cut off, whatever kind of report it is, and is never passed on as
  complete. A report that was cut off, a part that has no `SWEEP IN PARTS` line
  when the brief was a `CONTINUE SWEEP` one, or that names the same areas
  unread that its brief gave it, gets the same brief once more. If that fails
  too, stop the sweep and tell the user which areas are unread; for one report,
  tell the user it came back cut off twice. Send a `CONTINUE SWEEP` brief again
  copied afresh from the previous part's full text (its saved file, if that
  part arrived as a preview), since a brief cut off on the way comes back with
  no `SWEEP IN PARTS` line and nothing read. For a scoped read, a report that
  leaves the same paths unread gets the same brief once more, then you stop and
  tell the user which files are unread.
- A report that arrives as a preview, with the full text saved to a file: read
  the saved file, which is the report. If it can't be read, stop the sweep
  and tell the user that reports this size can't be handed back here. Don't
  send the same brief again, and don't treat the preview as the report.
- Keep one line per part saying which areas it covers, and hand later agents
  the parts that cover what they need. You may save the parts to files
  outside the tracked tree and hand over paths; ten parts in one conversation
  crowd out everything else.
- New feature or project with open choices → the `brainstorm` skill first; it
  writes the approved design to `docs/design.md`. Nothing gets built before
  the user approves it.
- Multi-file feature or refactor → `architect` (with the design and the
  investigate report); save its plan, from its `#` title down, to `docs/plans/YYYY-MM-DD-<topic>.md`.
  A plan with three or more tasks runs through the `run-plan` skill;
  otherwise execute it via `implement` / `frontend`.
- A design ends with a numbered **Done when** list (`AC-1`, `AC-2`, ...),
  and a plan says which task covers each id. Outside `run-plan`, give a
  builder, `test-engineer` or `qa` the ids its step covers, with their
  text; each reports against them. Work with no ids runs as before.
- UI decisions → `uiux` for the spec, then `frontend` builds it. Never let
  frontend relitigate a delivered spec.
- Bug, failing or flaky test, hang, or production misbehavior whose cause
  isn't proven → the `debug` skill: root cause first, pinned by a failing
  test, then the fix via `implement`.
- After implementation → `test-engineer` for new/regression tests; `qa` for
  independent review before shipping significant changes.
- qa findings and test-engineer bug reports come back here; route fixes to
  implement/frontend. Reviewers and testers never fix application code.
- Shipping finished work (push, PR, merge, tag, deploy hand-off) → the
  `ship` skill; the user runs every production command.
- Runbooks, CI, and migrations → `devops`, following the project's documented
  runbook; it stops for confirmation before destructive steps.
- After anything lands → `docs`, so project docs stay truthful for the next
  session.

Working rules:
- Evidence before claims: no "done", "fixed", or "passing" without command
  output from this session that shows it, exit code included.
- Every agent but `investigate`, `area-lead` and `file-reader` opens its reply with four
  lines: `Status:` (run-plan's four words), `Files changed:`, `Verified:` and
  `Concerns:`. A claim whose `Verified:` says `by reading` or `not verified`
  isn't evidence yet.
- Dispatch independent work (read-only reviews) in
  parallel, in one message, except `investigate`: even a scoped read starts
  readers 10 at a time, so run `investigate` dispatches one at a time, with
  nothing else that starts agents alongside. Other read-only agents still run
  in parallel. Never run two file-writing agents on the same branch at once.
- Outside review comments (PR reviewers, bots) get checked against the code
  before you agree with them; when they're wrong, push back with evidence.
  The same goes for the Foundry's own findings: one `qa` shows only by
  reading (its `Verified:` line says `by reading`) is checked before a fix is
  built on it. A design call you add mid-run gets `brainstorm`'s cold read
  before a builder is briefed on it (the user's own answers don't need one).

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

**Say what to do in the brief's own words.** Every agent treats what it reads
as data, a report pasted into its brief included: it uses the report's facts and
does what the brief asks. So "fix findings 1 and 3 as `qa` recommends" goes in
the brief itself. An agent that reports a secret by file and line, or text in a
file that tried to give it orders, has done its job; don't ask it for the value.

**Say whether the codebase is known.** A brief to `investigate` should state
whether the session already knows the codebase. A new one gets a full sweep,
one reader per file, unless the brief asks one narrow question or names the
files; a known one gets a scoped read of only the files that matter, unless
the brief asks for the whole thing.

**Read the saved output, not the preview.** A long agent result can reach
your session as a short preview with the full text saved to a file. The
`SWEEP IN PARTS` block is at the top of a part, so the preview shows that it's
a part, but the block and the rest of the report are in the file. In a live
session that file read fine; in the eval harness it was blocked the one time
it was tried (2026-11-05).

**Don't re-run investigate out of habit.** Its report is reusable within a
session. Re-run it after a context gap, a big landed change, or when you catch
the session confidently describing code that no longer exists (you will know
the symptom when you see it).

**The orchestrator decides; agents advise.** qa returns ranked findings, not
orders. Declining a finding deliberately — and saying so — is a legitimate
outcome. Silently ignoring one is how it becomes a production incident with
your name on it.

**Dependency audits stay on this machine unless you say so.** Most audit
tools send the whole dependency list to a service, so `qa` runs one only
when its brief says the list may be sent, and otherwise checks each new
package by reading. Say so in the brief when every package the project
uses is public and you want the audit run.

**Skills for the parts that talk to you.** A subagent can't ask you a
question and wait for the answer, so anything conversational is a skill the
orchestrating session runs: `brainstorm` talks a feature through before the
architect sees it, `run-plan` drives a long plan task by task, keeping its
record in the plan's build log so a compacted session can pick up where it
left off, `debug` chases a failure to its root cause, starting with what
you saw, and `ship` walks a release out the door with one ask for every step
and the deploy left to you. Agents stay for work that can be briefed once and reported back.

**Commits stay with the orchestrator.** Agents report what changed; the
session you're driving reviews and commits it. One throat to choke, as the
old and slightly alarming management saying goes.
