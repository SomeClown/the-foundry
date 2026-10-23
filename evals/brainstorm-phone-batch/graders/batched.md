---
type: llm
focus: last_message
---

PASS only if the message puts ALL the remaining open questions into one numbered list,
each with options and a recommendation, and makes clear the user can answer everything
in one reply (e.g. "1A 2B 3A"). FAIL if it asks one question and waits, or defers questions
to later messages without saying so.
