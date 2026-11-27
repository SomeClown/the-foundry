---
type: llm
focus: trace
weight: 2
---

The trace is a session that dispatched one agent. The agent's own report is the result of the Agent call: the text after "The report follows:", every line indented two spaces. Judge that report, not the session's final message.

The report here is the architect's plan; it is long, and it is the result of the Agent call. Read its data-change section and its tasks or releases. PASS only if (1) the plan's first release ships code that works with both column names, or adds the new column beside the old `email` one; (2) a later release removes or renames `email`; and (3) the plan says which goes first, the data change or the code. FAIL if one release both renames the column and changes the code that reads it, or if the plan never says what goes first.
