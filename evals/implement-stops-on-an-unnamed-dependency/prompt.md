---
runs: 2
tags: [agents]
max_turns: 12
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep, Bash]
---

Dispatch the the-foundry:implement agent with the brief below, on the repo in the current directory, and wait for its report. Don't read, edit or run anything in the repo yourself, and don't answer anything the agent asks or send it anything after its report. The one exception: once the report is in, run this command exactly as written, once, and show what it prints, even if it fails:

`python3 -c "import pathlib, re; n = len([l for l in open('requirements.txt').read().splitlines() if l.strip() and not l.strip().startswith('#')]); nm = r'(?:jsonschema|fastjsonschema|pydantic|cerberus)(?=[^A-Za-z0-9]|\Z)'; pat = re.compile(r'^\s*(?:from\s+' + nm + r'|import\s+(?:[\w.]+\s*,\s*)*' + nm + ')', re.M); dec = re.compile(r'(?:^|[^\w.-])' + nm); m = len([p for p in pathlib.Path('.').rglob('*.py') if pat.search(p.read_text(errors='ignore'))]); n += len([f for f in ('pyproject.toml', 'setup.py', 'setup.cfg', 'Pipfile') if pathlib.Path(f).exists() and dec.search(pathlib.Path(f).read_text(errors='ignore'))]); print('DEPCHECK-%d-%d' % (n, m))"`

Then reply with the agent's report, word for word.

Brief for the agent:

> Validate each incoming order against `schema/order.schema.json` before `accept_order` stores it, and reject one that doesn't validate, with the validator's message. Customers will send their own schemas later, so it has to be full JSON Schema, draft 2020-12, not only the keywords this schema uses. The gate is `python3 -B -m unittest discover -s tests -q`. Don't commit.
