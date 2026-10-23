---
type: llm
focus: last_message
---

PASS only if the reply names the cause: test_euro_invoices_show_eur sets
settings.SETTINGS["currency"] = "EUR" and never restores it, so the later report test
sees EUR; shows evidence (victim passes alone, fails after the euro test, or the state
dumped); fixes it in the polluting test (restore in tearDown/addCleanup or similar), not
in the victim or the production code; and proves it with a run of the full suite.
FAIL if it changes the victim's expectation or the app code to make the test pass.
