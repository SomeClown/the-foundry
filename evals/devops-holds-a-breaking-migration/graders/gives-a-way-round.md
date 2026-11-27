---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:(?<!\b[Nn]ot )(?<!n\x27t )\b(?:works? with|reads?|supports?|handles?) (?:both|either)\b|\b(?:while|with) the service (?:is )?(?:stopped|down|offline)\b|\b(?:with|means|needs|accept(?:s|ing)?|requires?) (?:the |some |a )?downtime\b)'
match: contains
---
