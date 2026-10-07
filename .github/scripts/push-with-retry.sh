#!/usr/bin/env bash
# Push the current branch; on a non-fast-forward, rebase onto the remote and retry (E06).
set -euo pipefail
branch="${1:-$(git rev-parse --abbrev-ref HEAD)}"
for attempt in 1 2 3 4; do
  if git push origin "HEAD:${branch}"; then
    exit 0
  fi
  if [ "$attempt" -eq 4 ]; then
    break
  fi
  echo "push rejected (attempt ${attempt}); rebasing onto origin/${branch}"
  git pull --rebase origin "${branch}"
  sleep $((attempt * 5))
done
echo "push failed after 3 retries" >&2
exit 1
