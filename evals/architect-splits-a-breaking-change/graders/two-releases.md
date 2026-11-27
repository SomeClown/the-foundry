---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:\b(?:[Tt][Ww][Oo]|[Tt][Hh][Rr][Ee][Ee])(?:[ -]|\\n[ \t]*)[Rr][Ee][Ll][Ee][Aa][Ss][Ee]|\ba (?:separate|later) [Rr][Ee][Ll][Ee][Aa][Ss][Ee]\b|\b[Ff][Ii][Rr][Ss][Tt] [Rr][Ee][Ll][Ee][Aa][Ss][Ee]\b(?:[^"\\]|\\.)*?\b[Ss][Ee][Cc][Oo][Nn][Dd] [Rr][Ee][Ll][Ee][Aa][Ss][Ee]\b|\b[Rr][Ee][Ll][Ee][Aa][Ss][Ee][ \t*]*(?:1|A|[Oo]ne)\b(?!\.[0-9])(?:[^"\\]|\\.)*?\b[Rr][Ee][Ll][Ee][Aa][Ss][Ee][ \t*]*(?:2|B|[Tt]wo)\b(?!\.[0-9]))'
match: contains
---
