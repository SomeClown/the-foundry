---
name: brainstorm
description: Talk a new feature, project, or behavior change through with the user before the architect plans it. Use when someone wants something built and the request leaves real choices open (what it should do, who it's for, how far it goes, what it's built with). Asks numbered questions with a recommended option, plays the design back in numbered parts for approval, writes approved designs to docs/design.md, and lets nothing get built until the user approves. Skip it for small, fully specified requests, which just get done.
---

# Brainstorm

> "If I had asked people what they wanted, they would have said faster horses."
> — attributed to Henry Ford, who probably never said it

This skill runs in the main session, because it has to talk with the user and
wait for answers; a subagent can't. Its job is to turn a request into a design
the user has approved, so the architect plans the right thing and the hundred
small decisions nobody mentions get made the way the user would have made them.

The deliverable is a decision record, not a conversation. Keep the talk short
and the questions easy to answer.

---

## 1. Decide whether there's anything to ask

Before replying, sort what you know:

- **Everything that matters is in the request** ("make the retry limit 5", "add
  a `--dry-run` flag that skips the write"). Don't brainstorm. Do it through the
  normal pipeline and say what you did.
- **The intent is clear but a choice or two is open.** Ask those choices as one
  numbered list (section 3), confirm, and go.
- **Something important is missing**: what it's for, who uses it, where it
  stops, what it's built on. Start the conversation.

When in doubt, ask one round. An unasked question about intent costs a rebuild;
an unneeded one costs ten seconds.

## 2. The opening message

Two things, nothing else:

1. One line saying they can skip the questions and have you start. If they take
   it, state any significant "how it gets made" choice you're making (platform,
   language, storage, library) in one plain line each, and go to the pipeline.
   The skill, and its gate, are done.
2. One open question that gets them describing a concrete moment: "Walk me
   through the last time you wished this existed" or "Who's the first person
   who'll use this, and what are they trying to do?" One question, not three
   stacked in a sentence ("who's reading it, what do they get, and why now?"):
   a stacked question makes them pick which part to answer, and the other two
   get lost.

The opening is the only place for open questions. Their own words carry intent
that a menu would flatten, so let them describe first.

## 3. Asking questions after the opening

Ask with numbered questions and lettered options, **recommendation first**:

```
1. Who can trigger a refresh?
   A. Admins only (recommended: matches how the other admin commands work)
   B. Anyone, with a cooldown
   C. Anyone
2. Where do refreshed items go?
   A. The same channel as the digest (recommended)
   B. A new channel set by the admin
```

The user should be able to answer "1A, 2B" and move on. Rules:

- **Two to four options**, each a real choice. Say why the recommended one is
  recommended in a few words; that's the most useful part of the question.
- **Group related questions** into one message, most important first, no more
  than about five at a time.
- **Accept the short answer.** "A (your pick) works" means A. Don't ask them to
  confirm a choice they just made.
- **A guess they can correct** often beats a question: "I'm guessing this
  exists because the 8 a.m. digest keeps missing late news; right?"
- **When they say "you decide" or "what do you think?"**, decide, and record it
  as your call, not theirs.
- **Batch mode.** When the user says they're away, on their phone, or "just
  send me the questions", stop going round by round. Collect every open
  question into one numbered list at the end of a single message, each with
  options and a recommendation, so they can answer the whole thing in one reply.
  Stay in batch mode until they say otherwise.

Never use process jargon on the user ("acceptance criteria", "non-functional
requirements"). Match their vocabulary.

## 4. Ground to cover

This is a checklist for you, not a script to read out. By the time the design
is written, you should know:

- what this is, and why now
- who it serves, and what success looks like to them
- goals, non-goals, and **anti-goals** (what would make it a failure even if it
  technically works)
- what exists today and what they've already tried
- prior art they like or hate
- the details they care about, and the ones they don't

**How it gets made.** Find out early which build choices the user wants to make
(language, framework, storage, hosting, dependencies) and which they're handing
to you. In an existing project the default is whatever the project already
uses; say so rather than asking. Every default you pick gets said out loud, in
one line, before the design is approved. A default they never heard is a
default they couldn't reject.

**Look before you ask.** When looking would answer a question faster than
asking, look. A few reads of the project's code and docs need no permission;
just say what you found, especially when it changes the question. For bigger
recon (web research, an upstream API's docs, an `investigate` dispatch on an
unfamiliar codebase, whose report also feeds the architect later), say what
you'd look for and offer to go.

**Think wide privately.** Before proposing an approach, come up with several
and drop the weak ones, including any that fight what the user said they want.
Show the comparison only when the choice is genuinely theirs.

**Show it when seeing beats reading.** For screens, layouts, or flows, offer a
quick mockup. For real visual direction, the `uiux` agent writes the spec once
the design is approved; brainstorming decides what the screen is for, not what
it looks like.

## 5. Play the design back in numbered parts

As soon as you understand one part well enough to describe it, play it back,
then move to the next part. Number the parts and keep each one to about
150–300 words:

```
Part 2 of 4: what happens when a source fails

<the description>

Guesses I made: the retry window (3 attempts over 10 minutes).
What's wrong or missing?
```

- **Mark your guesses** as guesses. Only what they said goes in as theirs.
- **Each part gets its own approval.** "Part 2 looks right" approves Part 2;
  "looks right except X" means fix X and show the corrected bit, not the whole
  part again.
- **Approval covers what they saw.** Agreeing with an idea in passing is not
  approval of a design you haven't written down.
- In batch mode, send all the parts in one message and ask for approval of each
  by number.

## 6. Size the work

Once the shape is clear, name a size in plain words. The user can override it.

| Size | Where the design lives | Then |
|---|---|---|
| Quick, fully specified | the request | do it |
| Small change | the approved parts, in chat | the pipeline (often `implement` → `qa`) |
| Project | a written section of `docs/design.md` | `architect`, then `run-plan` |

If it grows mid-conversation, stop and say so, then step up a size. If it's
really several independent projects, say that, agree on an order, and
brainstorm one at a time.

## 7. Write the design (project size)

Write it so a capable builder could plan from it without coming back to the
user.

**Where it goes.** In a repo, the project's living design document,
`docs/design.md`, as a **new numbered section** after the last one:

```
## <N>. <Title> (v<next version>, approved YYYY-MM-DD)
```

`<N>` is one more than the last section; the version is the release this will
ship in, if the project versions its releases.

Create the file if the project has none, starting at section 1. Never put
designs in a folder named after a tool (no `docs/superpowers/`, no
`docs/foundry/`); a later reader shouldn't need to know what wrote it. If the
project's CLAUDE.md names a different place, that wins. Outside a repo, ask.

**What it covers:**

- the intent and the why, in a short opening paragraph
- **Owner decisions (date):** what the user decided, as they decided it, with
  their letter choice where one was made
- goals, non-goals, anti-goals
- constraints (compatibility, cost, performance, privacy, deadlines)
- the behavior, part by part, as approved
- **Calls I made:** every default and every "you decide", marked as yours
- what's left to the builder (the architect), stated as such so nobody thinks
  it was forgotten
- open items, if any survive

**Voice.** The design is prose the user will read and probably commit. If a
personal writing-style skill is available (the project's CLAUDE.md names one,
or one like `my-writing-style` is installed), load it and write in that voice.
Plain, specific, and short beats thorough-sounding.

**After implementation**, the section gets an `### As built (YYYY-MM-DD)`
subsection recording what changed from the design during the build. The
`run-plan` skill hands that to the `docs` agent; brainstorm just leaves room
for it.

## 8. The builder check

Before handing the design over, have someone read it cold. Tell the user you're
writing it up, that a reviewer will read it first, and that you may come back
once with a few questions.

Dispatch a fresh `general-purpose` subagent (or `the-foundry:architect`, which
is read-only and plans for a living) with a brief like this, in your own words:

> You're the engineer who has to plan the build of what `docs/design.md` §N
> describes. You can't talk to its author. Read §N, and as much of the rest of
> the document and the repo as you need. List only the questions you'd have to
> guess at, where a wrong guess changes what gets built. For each: the
> question, why it matters, and your best guess. Rank them. Skip wording
> nitpicks and anything §N leaves to the builder. If nothing important is
> left, say "nothing important left".

Sort what comes back:

- **Already answered** by the conversation or the code: put the answer in the
  design.
- **Minor**: a sensible builder could settle it without changing what gets
  built. Settle it and add it to "Calls I made".
- **The user's**: only they can answer it, and the answer changes what gets
  built. Bring these back in **one** message, numbered, with options and a
  recommendation, most important first.

Update the design with their answers, then hand it over with a short list of
the calls you made so they can check those while reading. That's the only
question round the check produces.

## 9. The gate

**Nothing gets built until the user approves the design**: the approved parts
in chat for a small change, the written section for a project. "Built"
includes writing product code, scaffolding, installing dependencies, creating
repos, and dispatching `implement`, `frontend`, `devops`, or `run-plan`.
Reading, recon, and dispatching read-only agents (`investigate`, `architect`
for a builder check, `uiux` for an opinion) are fine.

Two ways through the gate early:

- **They opted out of questions** (section 2). The skill is done.
- **A throwaway spike they asked for.** Build it fast and rough, label it a
  spike, and bring what it taught you back into the conversation. Keeping the
  spike's code is a new request and comes back through the gate.

**"Sounds great, build it" partway through** is ambiguous: it approves the
part they just saw, and it might also mean "stop asking". Don't guess either
way. Ask in one line: skip the rest (you'll state your calls on what's left,
then write it up) or see the remaining parts first? Nothing gets built in the
meantime.

## 10. Hand off

Once the design is approved:

1. Commit the design section on its own, on the feature branch the build will
   use (create it now, `feat/<topic>`, if you're on the default branch), or ask
   first if the project's rules say so. A design commit is cheap insurance
   against a long session losing it.
2. **Small change:** route through the pipeline as usual.
3. **Project:** dispatch `the-foundry:architect` with the design section's path
   and number (plus the investigate report, if there is one). Save the plan it
   returns to `docs/plans/YYYY-MM-DD-<topic>.md`, on the same branch. Anything
   the architect flags as needing a human decision (in its Risks and Coupling
   section) goes to the user in one numbered round; then run the plan with the
   `run-plan` skill.

---

## Red flags

| Thought | What to do instead |
|---|---|
| "I'll ask one open question at a time" | After the opening, ask numbered questions with a recommendation. |
| "I'll keep my defaults quiet to save time" | Say every default in one line. |
| "They liked the idea, so I can start" | Approval covers the parts you showed. Write it, show it, get the yes. |
| "The design is obvious; skip the builder check" | The check costs one subagent. A wrong guess costs a rebuild. |
| "They're on their phone, but I'll keep going round by round" | Batch mode: one message, every question, numbered. |
| "The spike works, so I'll keep it" | Keeping it is a new request. Back through the gate. |
