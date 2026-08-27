# The Foundry

A portable software-development agent team for [Claude Code](https://claude.com/claude-code):
raw requests go in, shipped features come out.

The Foundry is nine specialized subagents plus your orchestrating Claude Code
session as the tenth member. Each agent is a single Markdown file with a strict
tool allowlist, an assigned model tier, and opinionated working instructions.
Drop them into your agents directory and every project you open gets an
investigation specialist, an architect, a designer, implementers, a test
engineer, an adversarial reviewer, a devops hand, and a docs keeper — with the
session you're typing into acting as the lead that briefs them, integrates
their results, and owns every commit.

## Background

This team wasn't designed on a whiteboard — it grew on a real project (a
15-year-old Hugo blog that needed repo surgery, a WordPress-migration content
cleanup across 85 posts, CI hardening, and a full visual retheme). The division
of labor, the model assignments, and the permission boundaries all come from
what actually worked, including the failures: the review agent earns its Opus
tier because it caught a scripted content-cleanup silently destroying 147
Markdown hard line breaks that every automated check had missed.

Design principles that fell out of that experience:

- **Read-only means enforced read-only.** Advisory agents don't have edit
  tools at all — the boundary is the tool allowlist, not a polite instruction.
- **The reviewer must be able to run things.** A QA agent that can't build or
  test the project can only find bugs by squinting. Foundry's `qa` runs the
  suite; that's how it catches what reading misses.
- **Expensive models only where mistakes are subtle.** Planning trade-offs,
  design taste, and missed vulnerabilities get the top-tier agents; execution
  against a good spec doesn't need one.
- **Docs are load-bearing.** The `docs` agent exists because the `investigate`
  agent reads documentation first — stale docs poison every later session.

## The team

| Agent | Role | Writes? | Model |
|---|---|---|---|
| `investigate` | Codebase onboarding — reads a project cold; reports structure, data model, coupling, gotchas | No | sonnet |
| `architect` | Turns a feature request (+ investigate report) into an ordered implementation plan with file-level scope | No | opus |
| `uiux` | Design advisor — aesthetic/creative direction, visual critique in a browser, dataviz, greenfield design systems | No | opus |
| `implement` | General implementer — backend, business logic, APIs, data models | Yes (app code) | sonnet |
| `frontend` | Front-end implementer — templates, components, CSS, client JS; verifies visually in a browser | Yes (UI code) | sonnet |
| `test-engineer` | Writes and runs tests; bootstraps a suite where none exists | Yes (tests only) | sonnet |
| `qa` | Independent review — security, logic bugs, quality; ranked findings; runs builds/tests to verify | No | opus |
| `devops` | Build, CI/CD, migrations, deploys, service config; treats production as hot | Yes (config/infra) | sonnet |
| `docs` | Keeps CLAUDE.md / README / runbooks truthful after changes land | Yes (docs only) | sonnet |

**Model policy:** Opus goes where mistakes are subtle and costly (design
trade-offs, missed vulnerabilities); Sonnet everywhere execution follows a
spec, a runbook, or established patterns. The orchestrating session keeps
whatever top model you run, and can escalate any single spawn via the Agent
tool's per-call `model` override.

**Permission policy:** Tool allowlists are the enforced boundary — read-only
agents have no Edit/Write. Browser tools are held by `frontend` (full set, for
building) and `uiux` (observation set — no form input or scripting, and its
instructions forbid state-changing clicks). `investigate` and `architect`
additionally run with `permissionMode: plan`, which hard-blocks mutations
including through Bash. `qa` and `uiux` deliberately do not run in plan mode —
qa needs to run builds and tests, uiux needs to drive a browser — but their
allowlists still bar file editing.

## The pipeline

Typical full-feature flow (skip stages that don't apply):

```
investigate → architect → implement / frontend (uiux advises) → test-engineer → qa → devops → docs
```

- **New or unfamiliar project:** start with `investigate`.
- **Small fix:** `implement` → `qa` is often enough.
- **UI work:** `uiux` decides, `frontend` executes — spec first, then build.
- **Bug fix:** `implement` fixes, `test-engineer` pins it with a regression test.
- **After anything lands:** `docs`, so the next session isn't lied to.

Division-of-labor rules the agents enforce on themselves:

- Read-only agents (investigate, architect, uiux, qa) never write files.
- test-engineer touches only tests; docs only documentation; devops only
  config/infra. Application-code fixes always route back through
  implement/frontend.
- qa findings go to the orchestrator, which decides what implement fixes —
  the reviewer never fixes its own findings.
- Project-specific implementers can exist per-repo (in that project's
  `.claude/agents/`) and take precedence over the generic ones for their niche.

## Install

Copy the agent files to your user-level agents directory (available in every
project):

```bash
git clone https://github.com/SomeClown/the-foundry.git
mkdir -p ~/.claude/agents
cp the-foundry/agents/*.md ~/.claude/agents/
```

Or into a single project's `.claude/agents/` directory to scope them to that
repo. New Claude Code sessions pick them up automatically — agent definitions
load at session start, so restart any running session.

### Optional: run them as an agent team

Claude Code's experimental agent-teams feature lets the nine run as
coordinating teammates (shared task list, per-agent inboxes) rather than
one-shot subagents. Enable it in `~/.claude/settings.json`:

```json
{
  "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" }
}
```

Then ask your session in natural language:

> "Spawn teammates using the investigate, implement, and qa agent types to
> work through this feature. investigate reports first; qa reviews at the end."

Caveats current as of late 2026: teammates load fresh project context but not
the lead's conversation history (brief them in the spawn prompt); `skills:`
frontmatter isn't applied to teammates (have them load skills via the Skill
tool, which these definitions already do); teammates can't nest teams; and
session resume doesn't restore in-process teammates.

## Optional skill dependencies

The `uiux` agent loads two skills when present — the `frontend-design` skill
(from Anthropic's official plugin marketplace) for aesthetic-direction work,
and the `dataviz` skill for chart specification. Both are optional: the agent
checks for them and falls back to its own design knowledge when they're not
installed. No skills are bundled in this repo.

## Customization

Everything is plain Markdown with YAML frontmatter — edit freely:

- **Models:** change `model:` per agent (`sonnet`, `opus`, `haiku`, `inherit`).
- **Tools:** the `tools:` allowlist is the security boundary; keep it tight.
- **Stack bias:** the instructions are stack-agnostic (they read the project's
  CLAUDE.md and manifests first). If your work is all one stack, saying so in
  each agent's body sharpens them.
- **Version them:** keep `~/.claude/agents` under git. A stray edit to an
  agent definition is otherwise unrecoverable.

## Credits

Built by [Teren Bryson](https://packetqueue.net) — forged, fittingly, by the
team building itself: the agents' own investigate/qa/docs runs shaped their
final form. Developed with Claude Code.

## License

[MIT](LICENSE)
