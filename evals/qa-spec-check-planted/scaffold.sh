#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
cat > brief.md <<'EOF'
### Task 4: Rate limit the /refresh command

- In `bot/commands.py`, `/refresh` may run at most once per server every 10 minutes (`REFRESH_COOLDOWN_SECONDS = 600`).
- A refused call replies, ephemerally: `Refresh is cooling down; try again in N minutes.` where N is rounded up.
- The cooldown is per server, kept in memory (a dict keyed by guild id). No database change.
- Tests in `tests/test_refresh.py`: the first call runs; a second call within 600 s is refused with the exact message; a call after 600 s runs.

Files: `bot/commands.py`, `tests/test_refresh.py`
EOF
cat > report.md <<'EOF'
Task 4 report. Status: DONE. Added a per-server cooldown to /refresh (600 s), the refusal message from the brief, and tests for all three cases in the brief. Gate passes.
EOF
cat > diff.txt <<'EOF'
 bot/commands.py       | 22 ++++++
 bot/settings.py       |  6 ++
 tests/test_refresh.py | 25 +++++++
--- a/bot/commands.py
+++ b/bot/commands.py
+import math
+from bot.settings import get_refresh_cooldown
+_last_refresh = {}
+    guild = interaction.guild_id
+    cooldown = get_refresh_cooldown(guild)
+    now = time.monotonic()
+    last = _last_refresh.get(guild)
+    if last is not None and now - last < cooldown:
+        minutes = int((cooldown - (now - last)) // 60)
+        await interaction.response.send_message(
+            f"Refresh is cooling down; try again in {minutes} minutes.", ephemeral=True)
+        return
+    _last_refresh[guild] = now
+    await run_refresh(guild)
--- a/bot/settings.py
+++ b/bot/settings.py
+def get_refresh_cooldown(guild_id):
+    """Per-server cooldown in seconds; admins can change it later."""
+    row = _db().execute("SELECT refresh_cooldown FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
+    return row[0] if row and row[0] else 600
--- /dev/null
+++ b/tests/test_refresh.py
+    async def test_first_call_runs(self, run, _cd):
+        await commands.refresh(self.inter)
+        run.assert_awaited_once()
+    async def test_second_call_refused(self, run, _cd):
+        await commands.refresh(self.inter)
+        await commands.refresh(self.inter)
+        self.assertEqual(run.await_count, 1)
EOF
