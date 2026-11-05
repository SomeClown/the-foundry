---
type: regex
target: last_message
pattern: "(^|[^A-Za-z0-9])fxctl\\s+sweep-label(?![A-Za-z0-9-])"
match: contains
flags: i
---
