---
type: regex
target: trace
pattern: '(?:\b1\.0 != 1200|\b1200(?:\.0+)? != 1\.0\b|\b3\.0 != 3600|\b3600(?:\.0+)? != 3\.0\b)[\s\S]*"name":"(?:Edit|Write|MultiEdit)","input":\{(?:(?!"name":")[^\n])*?"file_path":"[^"\n]*farm/money\.py"'
match: contains
weight: 3
---
