#!/usr/bin/env bash
# Stage only data/ and commit with a `data:` message if anything changed.
set -euo pipefail
msg="$1"
git add -A data/
if git diff --cached --quiet; then
  echo "nothing to commit for: ${msg}"
  exit 0
fi
git commit -m "data: ${msg}"
