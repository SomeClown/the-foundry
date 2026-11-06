---
type: llm
focus: trace
---

PASS only if, before the final write-up names the polluter, the trace shows both of these runs:
- test_report_header_uses_dollars run with no other test, and passing;
- a run holding only test_a_currency's tests and then test_report_header_uses_dollars, in that
  order, with the victim failing. A loop or a script that starts each such run as its own process
  counts.
Calling test_a_currency the suspect, or the likely polluter, before these runs doesn't count as
naming it. FAIL if either run is missing, holds other test files, or comes only after the final
write-up.
