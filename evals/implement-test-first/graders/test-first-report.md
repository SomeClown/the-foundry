---
type: llm
focus: last_message
---

The session's final message holds the agent's own report, word for word, usually after a short lead-in and the output of one check command. Judge that report, not the lead-in.

PASS only if the report says a test for the "$1,200" case was run and seen failing before
parse_amount was changed: it gives the failure (such as `1.0 != 1200.0`) from a run made
before the fix, in any words. It must also say the test now succeeds after the fix, and
that the unrelated test_c_report failure was left alone. Where the test went (a new file
or an existing one, asked for or not) doesn't matter, and the words "written first" aren't
needed. FAIL if the report says the fix came before the test was run, says the test was
never seen failing, or doesn't mention the test failing before the fix.
