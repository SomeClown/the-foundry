#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
mkdir -p newsbot docs
printf '"""Daily digest posting."""\n\n\ndef post_digest(guild):\n    pass\n' > newsbot/digest.py
printf '# Design\n\n## 1. Daily digest (approved 2026-09-23)\n\nOne embed per game per day.\n' > docs/design.md
