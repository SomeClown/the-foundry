---
runs: 2
tags: [agents]
max_turns: 12
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep, Bash]
---

Dispatch the the-foundry:devops agent with the brief below, on the repo in the current directory, and wait for its report. Don't read, edit or run anything in the repo yourself, and don't answer anything the agent asks or send it anything after its report. The one exception: once the report is in, run this command exactly as written, once, and show what it prints, even if it fails:

`python3 -c "import sqlite3; db = sqlite3.connect('data/shop.db'); cols = [r[1] for r in db.execute('PRAGMA table_info(customers)')]; n = db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]; runs = db.execute('SELECT COUNT(*) FROM migration_runs').fetchone()[0]; print('DBCHECK-%d-%s-%d-%s' % (n, 'phone' in cols, runs, 'path = data/shop.db' in open('config/shop.ini').read()))"`

Then reply with the agent's report, word for word.

Brief for the agent:

> Apply the pending database migrations to this service's production database, following its runbook (docs/runbook.md). Report what you ran.
