---
type: llm
focus: trace
weight: 2
---

The trace is a session that dispatched one agent. The agent's own report is the result of the Agent call: the text after "The report follows:", every line indented two spaces. Judge that report, not the session's final message.

The report here is the architect's plan; it is long, and it is the result of the Agent call. Read its data-change section and its tasks or releases. PASS only if (1) the plan's first release ships code that works with both column names, or adds the new column beside the old `email` one; (2) a later release removes or renames `email`; and (3) the plan says which goes first, the data change or the code. FAIL if one release both renames the column and changes the code that reads it, or if the plan never says what goes first.

Read the first release by what it does to `email`, not by whether it also switches the code. These count as (1), and a plan that has one of them with (2) and (3) passes:
- Release 1 (or A) adds `contact_email` beside `email`, backfills it, keeps the two in sync with triggers, and then the app (1.5.0) reads `contact_email`. Nothing in that release removes or renames `email`, so it is not "one release that renames the column and changes the code". The drop of `email` comes in release 2 (or B), after the new code is running. Two saved right plans were failed for exactly this shape; it passes.
- Release 1 ships code that works with either column name, a later release renames the column in place with the data change, and a last step removes the fallback. This is the code-first order and it passes.

The order in (3) counts in any wording: "the data change goes first", "data first", "the code goes first", "code first", or a line such as "Order: data change, then code, then the breaking data change". Which goes first can differ by release; one stated order for the first release is enough.

FAIL only for a plan whose single release both removes or renames `email` and ships the code that reads the new name, a plan that removes or renames `email` in its first release, whether in the migration that adds the new column or in another one, or a plan that never says what goes first.
