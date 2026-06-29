#!/usr/bin/env bash
# ML phase: swing sp500 scan + scoped labels. Run manually or from cron helpers.
# Usage: docker exec quant-hub ml-phase-swing-sp500
#        bash /opt/stacks/quant-hub/scripts/ml-phase-swing-sp500.sh  (on host via docker exec)
set -euo pipefail

LOG="${QUANT_ML_PHASE_LOG:-/app/logs/ml_phase.log}"

log() {
  echo "[$(date -Iseconds)] $*" | tee -a "$LOG"
}

log "========== ML phase: swing sp500 started =========="

log "--- Swing scan: sp500 ---"
quant-swing --universe sp500 --no-email

log "--- ML: warm label cache ---"
quant-ml warm-cache --universe sp500 || log "WARN: warm-cache exited non-zero"

log "--- ML labels: swing sp500 (90d window) ---"
quant-ml label --strategy swing --universe sp500 --since "$(date -d '90 days ago' +%F)" \
  || log "WARN: quant-ml label exited non-zero (expected until forward prices exist)"

log "--- Status ---"
quant-hub status
quant-ml status

log "========== ML phase: swing sp500 finished =========="
