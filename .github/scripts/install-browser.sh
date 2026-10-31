#!/usr/bin/env bash
# Install the headless Chromium shell and its system packages for Playwright, with a time limit
# per attempt and up to three attempts. On 2026-10-26 a scheduled capture hung here until the
# job timed out and the day's update was captured only by a backup run (ADR 0024).
set -uo pipefail
for attempt in 1 2 3; do
  if timeout 180 uv run --frozen playwright install --with-deps --only-shell chromium; then
    exit 0
  fi
  echo "browser install attempt ${attempt} failed or took over 3 minutes" >&2
  sleep 15
done
echo "browser install failed after 3 attempts" >&2
exit 1
