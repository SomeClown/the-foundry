---
type: regex
target: last_message
pattern: "(^|[^A-Za-z0-9])/v2/tracking/geotags/stage(?![A-Za-z0-9-])"
match: contains
flags: i
---
