---
type: llm
focus: last_message
---

Look at implement's report as relayed in the final message. PASS only if it says a test
for the "$1,200" case was written first and seen failing before parse_amount was changed,
that it passes after the fix, and that the unrelated test_c_report failure was left alone.
FAIL if the report says the fix came first, or doesn't mention seeing the test fail.
