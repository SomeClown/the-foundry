---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?\b(?:jsonschema|fastjsonschema|pydantic|cerberus)\b'
match: contains
---
