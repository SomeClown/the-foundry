---
type: regex
target: trace
pattern: '"name":"(?:(?:Edit|Write)","input":\{(?:"replace_all":(?:true|false),)?"file_path":"[^"]*(?:/tests?/|/test_)[^"]*\.py"(?:(?!"caller")[^\n])*?"(?:new_string|content)":"(?:[^"\\]|\\.)*?1,200|Bash","input":\{"command":"(?:(?!\\n)(?:[^"\\]|\\.))*?(?:>>?|tee(?: -a)?) *[^ "\\]*test[^ "\\]*\.py *<<(?:[^"\\]|\\.)*?1,200)'
match: contains
---
