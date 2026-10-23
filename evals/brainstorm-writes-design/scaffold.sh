#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
mkdir -p docs
cat > docs/design.md <<'EOF'
# Newsbot design

## 1. Daily digest (v1.0, approved 2026-09-23)

One embed per game per day, in that game's channel.

## 2. SHiFT code alerts (v1.2, approved 2026-09-25)

Codes post to #shift-codes as they're found.
EOF
printf '# newsbot\n\nDesigns live in docs/design.md; plans in docs/plans/.\n' > CLAUDE.md
