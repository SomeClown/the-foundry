---
type: llm
focus: last_message
---

PASS only if the reply identifies parse_amount as where the value first goes wrong (a
price with a thousands comma and no cents is cut at the comma, so "$1,200" becomes 1.0),
says a failing test was written and seen failing before the fix, fixes parse_amount (not
invoice_total or the formatting), and proves it with the test passing. It may mention the
unrelated currency-test pollution as a separate bug, but must not fold a fix for it into
this one. FAIL if the fix is at a layer other than parsing.
