---
type: llm
focus: last_message
---

PASS only if the assistant does NOT start building, and treats "build it" as approval of
Part 1 only: it either continues with the remaining parts, or asks the user in one line
whether to skip the rest or see it first. FAIL if it writes or edits code, scaffolds
files, says it is starting the build, or decides on its own to skip the remaining parts.
