#!/usr/bin/env bash
# Install the headless Chromium shell and its system packages for Playwright, with a time limit
# per attempt and up to three attempts. On 2026-10-26 a scheduled capture hung here until the
# job timed out and the day's update was captured only by a backup run (ADR 0024).
#
# `timeout` stops the Playwright command but not the apt-get it starts as root, which keeps the
# package lock after a timed-out attempt. On 2026-11-04 that made attempts 2 and 3 fail at once
# with "Could not get lock". So between attempts, wait for apt-get and dpkg to finish; the next
# attempt then finds the packages already installed (ADR 0024).
set -uo pipefail
# Defaults below; the environment overrides them only in tests.
ATTEMPTS=${ATTEMPTS:-3}
ATTEMPT_LIMIT=${ATTEMPT_LIMIT:-180}  # seconds per attempt
LOCK_WAIT=${LOCK_WAIT:-180}          # seconds to wait for a leftover package install between attempts
PAUSE=${PAUSE:-15}
POLL=${POLL:-5}

wait_for_apt() {
  local waited=0
  while pgrep -x apt-get >/dev/null || pgrep -x dpkg >/dev/null; do
    if (( waited >= LOCK_WAIT )); then
      echo "package install still running after ${LOCK_WAIT} s" >&2
      return 1
    fi
    sleep "$POLL"
    waited=$((waited + POLL))
  done
  if (( waited > 0 )); then echo "waited ${waited} s for a leftover package install" >&2; fi
  return 0
}

for attempt in $(seq "$ATTEMPTS"); do
  if timeout "$ATTEMPT_LIMIT" uv run --frozen playwright install --with-deps --only-shell chromium; then
    exit 0
  fi
  echo "browser install attempt ${attempt} failed or took over ${ATTEMPT_LIMIT} s" >&2
  if (( attempt < ATTEMPTS )); then
    wait_for_apt
    sleep "$PAUSE"
  fi
done
echo "browser install failed after ${ATTEMPTS} attempts" >&2
exit 1
