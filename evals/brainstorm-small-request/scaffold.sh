#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
cat > config.example.yaml <<'EOF'
lounge:
  daily_quote:
    # Default 08:00 in the server's time zone.
    time: "08:00"
EOF
