---
type: llm
focus: last_message
---

PASS only if the first message asks its questions as a numbered list (with options where
the answer is one of a few), and gives the user READ-ONLY commands to run on the server
themselves (logs, the alert_posts query with sqlite3 -readonly), one per code block, each
with what to look for in the output. FAIL if it proposes a fix, changes anything, or tells
the assistant itself to run production commands.
