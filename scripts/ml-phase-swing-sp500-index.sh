#!/usr/bin/env bash
# ML phase: swing sp500_index scan + scoped labels. Run manually or from cron helpers.
# Usage: docker exec quant-hub bash /app/scripts/ml-phase-swing-sp500-index.sh
set -euo pipefail

LOG="${QUANT_ML_PHASE_LOG:-/app/logs/ml_phase.log}"

log() {
  echo "[$(date -Iseconds)] $*" | tee -a "$LOG"
}

log "========== ML phase: swing sp500_index started =========="

log "--- Swing scan: sp500_index ---"
quant-swing --universe sp500_index --no-email

log "--- ML: warm label cache ---"
quant-ml warm-cache --universe sp500_index || log "WARN: warm-cache exited non-zero"

log "--- ML labels: swing sp500_index (90d window) ---"
quant-ml label --strategy swing --universe sp500_index --since "$(date -d '90 days ago' +%F)" \
  || log "WARN: quant-ml label exited non-zero (expected until forward prices exist)"

log "--- Status ---"
quant-hub status
quant-ml status

log "========== ML phase: swing sp500_index finished =========="
