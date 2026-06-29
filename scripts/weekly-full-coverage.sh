#!/usr/bin/env bash
# Weekly full coverage: breakout + swing + Lynch across all configured universes.
# Intended for cron (Saturday overnight) or manual: docker exec quant-hub weekly-full-coverage
set -euo pipefail

LOG="${QUANT_WEEKLY_COVERAGE_LOG:-/app/logs/weekly_coverage.log}"

log() {
  echo "[$(date -Iseconds)] $*" | tee -a "$LOG"
}

log "========== Weekly full coverage started =========="

log "--- Breakout: all universes ---"
quant-scan-all --cache --report both

log "--- Swing: all universes ---"
quant-swing-all --no-email

log "--- Lynch: stock universes (skips lynch_enabled: false) ---"
quant-lynch-all --no-email

log "========== Weekly full coverage finished =========="
