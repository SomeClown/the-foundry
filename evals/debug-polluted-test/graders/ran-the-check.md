---
type: llm
focus: trace
---

PASS only if, before naming test_euro_invoices_show_eur as the polluter, the trace shows
test_report_header_uses_dollars run on its own and passing, and run in one command right
after test_a_currency with no other test file in that command, and failing. FAIL if either
run is missing, or comes only after the polluter was named.
