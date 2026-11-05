---
type: regex
target: last_message
pattern: "(^|[^A-Za-z0-9])/v2/fleet/trailers/freeze(?![A-Za-z0-9-])"
match: contains
flags: i
---
