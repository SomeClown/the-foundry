# The Foundry

> "Never send a human to do a machine's job."
> — Agent Smith, who was, in fairness, the villain

A portable software-development agent team for [Claude Code](https://claude.com/claude-code):
raw requests go in, shipped features come out.

The Foundry is nine specialized subagents plus your orchestrating Claude Code
session as the tenth member. Each agent is a single Markdown file with a strict
tool allowlist, an assigned model tier, and opinionated working instructions.
Install it, and every project you open gets an investigation specialist, an
architect, a designer, two implementers, a test engineer, an adversarial
reviewer, a devops hand, and a docs keeper: the session you're typing into acts
as the lead that briefs them, integrates their results, and owns every commit--essentially, your project manager, which is something I have thought about building as well (a PM agent). Not sure yet if I really need it, as I use Fable 5 as the orchestration layer, and it seems to do very well with minimal token consumption.

To be fair, you do not need nine agents to write software. I wrote software for decades with zero agents and an amount of coffee that my doctor politely describes as "concerning." What you get from nine agents is the same thing you get from nine specialists anywhere: nobody has to be mediocre at everything, and the reviewer isn't grading their own homework. You also need strict boundaries and guardrails, the same as managing any team, to keep the agents in their own lanes. I seem to have achieved that here, but I am still testing, so take your own safety precautions and make sure you feel comfortable with what the team is doing.

## Background

This team wasn't designed on a whiteboard. It developed organically across two
real projects running side by side: [PacketQueue](https://packetqueue.net), a
15-year-old WordPress blog, moving to Hugo, that needed repo surgery, a WordPress-migration content cleanup across 85 posts, CI hardening, and a full visual re-theme; and a
[pool-league scheduler](https://github.com/SomeClown/pool-league-scheduler), a
more traditional Flask web app with real users, a production deploy, and an
honest-to-goodness constraint-satisfaction problem living in it. Agents were
born on one project, hardened on the other, and promoted to the shared roster
once they'd proved out on both. The division of labor, the model assignments,
and the permission boundaries all come from what actually worked, including
the failures: the review agent earns its top-tier model because it caught a
scripted content cleanup silently destroying 147 Markdown hard line breaks on
the blog that every automated check had missed, then caught a CSRF hole in the
scheduler before it shipped. Nothing builds faith in an adversarial reviewer
quite like watching it catch you doing something half-assed. Twice.

Design principles that came out of that experience:

- **Read-only means enforced read-only.** Advisory agents don't have edit
  tools at all: the boundary is the tool allowlist, not a polite instruction.
  Asking an eager LLM to please not edit files is like asking a Labrador to
  please not acknowledge the mailman. Take away the tools instead.
- **The reviewer must be able to run things.** A QA agent that can't build or
  test the project can only find bugs by squinting. Foundry's `qa` runs the
  suite; that's how it catches what reading misses.
- **Expensive models only where mistakes are subtle.** Planning trade-offs,
  design taste, and missed vulnerabilities get the top-tier agents; execution
  against a good spec doesn't need one. More on this below.
- **Docs are load-bearing.** The `docs` agent exists because the `investigate`
  agent reads documentation first — stale docs poison every later session.

## The team

> "Nine people can't make a baby in a month."
> — Fred Brooks, who clearly never had proper tool allowlists

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
spec, a runbook, or established patterns. This is the same logic as staffing a
hospital: the diagnostician gets paid more than the phlebotomist, and both of
them would make a hash of the other's job. The orchestrating session keeps
whatever top model you run--I have found success with Fable 5, myself... YMMV--and can escalate any single spawn via the Agent tool's per-call `model` override.

**Permission policy:** Tool allowlists are the enforced boundary — read-only
agents have no Edit/Write. Browser tools are held by `frontend` (full set, for
building) and `uiux` (observation set — no form input or scripting, and its
instructions forbid state-changing clicks; it's a critic in the gallery, not a
visitor doing errands). `investigate` and `architect` additionally run with
`permissionMode: plan`, which hard-blocks mutations including through Bash.
`qa` and `uiux` deliberately do not run in plan mode — qa needs to run builds
and tests, uiux needs to drive a browser — but their allowlists still bar file
editing.

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
  the reviewer never fixes its own findings. (Quis custodiet ipsos custodes?
  The orchestrator. That's the whole org chart.)
- Project-specific implementers can exist per-repo (in that project's
  `.claude/agents/`) and take precedence over the generic ones for their niche.

Want to see the whole thing run end to end? There's a
[worked example](docs/walkthrough.md) tracing one real-shaped feature through
every stage, with the actual briefing prompts. And
[docs/orchestrator.md](docs/orchestrator.md) has a copy-paste block that
teaches your own session to route work to the team without being asked.

## Install

### As a plugin (recommended)

The repo is its own one-plugin marketplace. Two commands, from inside any
Claude Code session:

```
/plugin marketplace add SomeClown/the-foundry
/plugin install the-foundry@the-foundry
```

Or from your shell:

```bash
claude plugin marketplace add SomeClown/the-foundry
claude plugin install the-foundry@the-foundry
```

That's it. The nine agents are now available in every project, they update
when you ask the plugin manager to update, and uninstalling is one command
instead of an archaeology expedition through your home directory.

### Manually (the artisanal method)

If plugins aren't your thing, the agent files work fine copied straight into
your user-level agents directory:

```bash
git clone https://github.com/SomeClown/the-foundry.git
mkdir -p ~/.claude/agents
cp the-foundry/agents/*.md ~/.claude/agents/
```

Or into a single project's `.claude/agents/` directory to scope them to that
repo. New Claude Code sessions pick them up automatically — agent definitions
load at session start, so restart any running session. Note that user-level
`.claude/agents/` definitions override same-named plugin agents, which is a
feature: install the plugin, then shadow any agent you want to customize.

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

**Caveats current as of late 2026**: teammates load fresh project context but not
the lead's conversation history (brief them in the spawn prompt); `skills:`
front-matter isn't applied to teammates (have them load skills via the Skill
tool, which these definitions already do); teammates can't nest teams; and
session resume doesn't restore in-process teammates.

## Optional skill dependencies

The `uiux` agent loads two skills when present — the `frontend-design` skill
(from Anthropic's official plugin marketplace) for aesthetic-direction work,
and the `dataviz` skill for chart specification. Both are optional: the agent
checks for them and falls back to its own design knowledge when they're not
installed. No skills are bundled in this repo.

Worth pairing with the team but not part of it: an accessibility audit
baseline. The `uiux` agent critiques against [WCAG 2.2](https://www.w3.org/TR/WCAG22/),
and Deque's [axe-core](https://github.com/dequelabs/axe-core) — the engine
under Lighthouse, Pa11y, and most other scanners — gives `qa` and `frontend`
a runnable check (`@axe-core/cli`, or Lighthouse in Chrome DevTools) rather
than an aspiration. For design judgment, the `uiux` agent's taste is anchored
in the two references the industry actually agrees on:
[Apple's Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines)
and [Material Design 3](https://m3.material.io/). Automated a11y scanning
catches well under half of real WCAG issues, so keyboard and screen-reader
passes still need a human — or at least an agent told to pretend to be one.

## Customization

Everything is plain Markdown with YAML front-matter — edit freely:

- **Models:** change `model:` per agent (`sonnet`, `opus`, `haiku`, `inherit`).
- **Tools:** the `tools:` allowlist is the security boundary; keep it tight.
  Every tool you add is a thing the agent will eventually do at the least
  convenient moment.
- **Stack bias:** the instructions are stack-agnostic (they read the project's
  CLAUDE.md and manifests first). If your work is all one stack, saying so in
  each agent's body sharpens them.
- **Version them:** keep your agents under git, whether via this plugin or
  your own fork. A stray edit to an agent definition is otherwise
  unrecoverable, and you will not remember what the prompt said last Tuesday.

If you improve an agent in a way that isn't specific to your setup, send it
back — see [CONTRIBUTING.md](CONTRIBUTING.md). Changes are tracked in the
[CHANGELOG](CHANGELOG.md).

## Credits

I'd be remiss not to mention Tony Mattke over at [Router Jockey](https://routerjockey.com), who not only is a great friend who inspired me to move to Hugo, but also has some amazing content on his blog. He deep dives into a variety of topics, all well worth a gander. One series of articles I'd highly recommend, if you're not overly comfortable with version control, begins here: [Git for Network Engineers](https://routerjockey.com/git-for-network-engineers-part-1/). 

Project built by [Teren Bryson](https://packetqueue.net) — forged, fittingly, by the
team building itself: the agents' own investigate/qa/docs runs shaped their
final form. Developed with Claude Code, mostly in my highly customized terminal (oh-my-zsh, heavily customized vim, etc., with a tad bit of a JetBrains IDE. More on that coming in a later entry).

And yes, I know: a team of machines doing the software jobs, assembled by the
machines themselves, distributed so more machines can do it elsewhere. Agent
Smith was the villain. I've decided not to worry about it.

## License

[MIT](LICENSE)
