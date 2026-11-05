---
type: regex
target: last_message
pattern: "(^|[^A-Za-z0-9])fxctl\\s+refresh-toll(?![A-Za-z0-9-])"
match: contains
flags: i
---
