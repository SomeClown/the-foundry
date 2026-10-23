#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
real_git=""
for candidate in "$(xcrun --find git 2>/dev/null || true)" /Library/Developer/CommandLineTools/usr/bin/git "$(command -v git)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then real_git="$candidate"; break; fi
done
[ -n "$real_git" ] || { echo "no git found" >&2; exit 1; }
mkdir -p bin
printf '#!/bin/sh\nexec "%s" "$@"\n' "$real_git" > bin/git
chmod +x bin/git
G="./bin/git -c user.name=Owner -c user.email=owner@example.com"

mkdir -p tally tests docs/plans
: > tally/__init__.py
: > tests/__init__.py
cat > tally/core.py <<'EOF'
"""Word counting. Lowercases everything and keeps only runs of letters."""

import re

_WORD = re.compile(r"[a-z]+")


def count_words(text):
    counts = {}
    for word in _WORD.findall(text.lower()):
        counts[word] = counts.get(word, 0) + 1
    return counts
EOF
cat > tests/test_core.py <<'EOF'
import unittest

from tally.core import count_words


class CountTest(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(count_words("a b a"), {"a": 2, "b": 1})
EOF
cat > docs/design.md <<'EOF'
# tally design

## 1. Counting (v0.1.0, approved 2026-10-01)

Count words in text; a word is a run of letters, case-folded.

## 2. Top words (v0.2.0, approved 2026-10-23)

Owner decisions (2026-10-23):
- `top_words(text, n=10)` in `tally/core.py` returns `(word, count)` tuples, highest count first, ties alphabetical, at most n long.
- `n` below 1 raises `ValueError("n must be a positive integer")`.
- Version 0.2.0 (`tally/__init__.py` gets `__version__ = "0.2.0"`).

Non-goals: stemming, stop words. Anti-goal: a new dependency.
EOF
printf '# tally\n\nPython 3, standard library only.\n\n- Gate: `python3 -B -m unittest discover -s tests -q` (must exit 0).\n- Designs in docs/design.md, plans in docs/plans/.\n' > CLAUDE.md
$G init -q -b main && $G add -A && $G commit -qm "tally 0.1.0"
