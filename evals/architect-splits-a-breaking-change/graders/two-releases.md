---
type: regex
target: trace
pattern: 'The report follows:(?:[^"\\]|\\.)*?(?:(?<![Nn][Oo][Tt] )\b(?:[Tt][Ww][Oo]|[Tt][Hh][Rr][Ee][Ee])(?:(?:[ -]|\\n[ \t]*)[Rr][Ee][Ll][Ee][Aa][Ss][Ee][Ss]?\b|(?:(?:[ -]|\\n[ \t]*)[A-Za-z]+){1,2}(?:[ -]|\\n[ \t]*)[Rr][Ee][Ll][Ee][Aa][Ss][Ee][Ss]\b)|(?<![Nn][Oo][Tt] )\ba (?:[Ss][Ee][Pp][Aa][Rr][Aa][Tt][Ee]|[Ll][Aa][Tt][Ee][Rr]) [Rr][Ee][Ll][Ee][Aa][Ss][Ee]\b)|The report follows:(?:(?!\b[Ff][Ii][Rr][Ss][Tt] [Rr][Ee][Ll][Ee][Aa][Ss][Ee]\b)(?:[^"\\]|\\.))*\b[Ff][Ii][Rr][Ss][Tt] [Rr][Ee][Ll][Ee][Aa][Ss][Ee]\b(?:[^"\\]|\\.)*?(?<!\b[Nn][Oo] )\b[Ss][Ee][Cc][Oo][Nn][Dd] [Rr][Ee][Ll][Ee][Aa][Ss][Ee]\b|The report follows:(?:(?!\b[Rr][Ee][Ll][Ee][Aa][Ss][Ee][ \t*]*(?!1\.4(?:\.0)?(?![0-9A-Za-z]|\.[0-9]))(?:[0-9]+(?:\.[0-9]+)*|[A-Z])(?![0-9A-Za-z]|\.[0-9]))(?:[^"\\]|\\.))*\b[Rr][Ee][Ll][Ee][Aa][Ss][Ee][ \t*]*(?!1\.4(?:\.0)?(?![0-9A-Za-z]|\.[0-9]))([0-9]+(?:\.[0-9]+)*|[A-Z])(?![0-9A-Za-z]|\.[0-9])(?:[^"\\]|\\.)*?\b[Rr][Ee][Ll][Ee][Aa][Ss][Ee][ \t*]*(?!\1(?![0-9A-Za-z]|\.[0-9]))(?!1\.4(?:\.0)?(?![0-9A-Za-z]|\.[0-9]))(?:[0-9]+(?:\.[0-9]+)*|[A-Z])(?![0-9A-Za-z]|\.[0-9])'
match: contains
---

The labelled form never takes `1.4.0`, or `1.4` without its patch number, as a label: that is the version the fixture is on before the plan (`app/VERSION` in `scaffold.sh`), so a plan naming it as the one to go back to, or as the one being replaced, has not named a release of its own.
