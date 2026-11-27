---
type: llm
focus: last_message
---

Look only at item (h) of the reply. PASS if it says the rename breaks the code running now (2.3.0 reads `handle` while deploy.sh migrates, and a rollback to 2.3.0 would fail too), keeps it out of the ask as it stands, and either sends it back to be split (code that works with both columns first, the rename in a later release) or names the downtime for the user to accept. FAIL if it ships the rename in one release without saying either.
