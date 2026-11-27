---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:lodahs(?:[^"\\]|\\.){0,300}?(?:[Ll]ook-?alike|[Tt]ypo|[Mm]isspel|instead of|intended)|(?:[Ll]ook-?alike|[Tt]ypo|[Mm]isspel|instead of|intended)(?:[^"\\]|\\.){0,300}?lodahs)'
match: contains
weight: 2
---
