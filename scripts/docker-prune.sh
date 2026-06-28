#!/bin/bash
#
# Periodic Docker housekeeping for the ALAFIA dev stack.
#
# Reclaims Docker build cache (unused for >72h) and dangling images so the
# Docker VM disk never fills up. A full disk previously crash-looped Postgres
# ("No space left on device" → end-of-recovery PANIC); see WORKLOG 2026-06-10.
#
# SAFETY: prunes build cache + dangling images only. It NEVER touches volumes
# (the `pgdata` Postgres volume) or images in use by running containers.
#
# Scheduled by ~/Library/LaunchAgents/com.alafia.docker-prune.plist (launchd —
# macOS's cron). Logs to ~/Library/Logs/alafia-docker-prune.log.

set -u

DOCKER=/usr/local/bin/docker
LOG="$HOME/Library/Logs/alafia-docker-prune.log"
CACHE_KEEP="72h"   # keep build cache used within this window (fast rebuilds)

ts() { date '+%Y-%m-%d %H:%M:%S'; }

{
  echo "[$(ts)] docker-prune starting"

  if ! "$DOCKER" info >/dev/null 2>&1; then
    echo "[$(ts)] Docker daemon not running — skipping this run"
    echo "[$(ts)] docker-prune done"
    exit 0
  fi

  echo "[$(ts)] before:"
  "$DOCKER" system df 2>&1 | sed 's/^/    /'

  # Build cache older than the keep window (the big disk consumer).
  "$DOCKER" builder prune -af --filter "until=${CACHE_KEEP}" 2>&1 | tail -1 | sed 's/^/    builder: /'
  # Dangling (untagged) images left behind by rebuilds.
  "$DOCKER" image prune -f 2>&1 | tail -1 | sed 's/^/    images: /'
  # Stopped/exited containers.
  "$DOCKER" container prune -f 2>&1 | tail -1 | sed 's/^/    containers: /'

  echo "[$(ts)] after:"
  "$DOCKER" system df 2>&1 | sed 's/^/    /'
  echo "[$(ts)] docker-prune done"
} >> "$LOG" 2>&1
