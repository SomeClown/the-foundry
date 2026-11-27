---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:lodahs(?:[^"\\]|\\.){0,300}?(?:[Ll]ook-?alike|[Tt]ypo|[Mm]isspel|should be|wrong package)|(?:[Ll]ook-?alike|[Tt]ypo|[Mm]isspel|should be|wrong package)(?:[^"\\]|\\.){0,300}?lodahs|lodahs(?:[^"\\]|\\.){0,120}?\blodash\b|\blodash\b(?:[^"\\]|\\.){0,120}?lodahs)'
match: contains
weight: 2
---
