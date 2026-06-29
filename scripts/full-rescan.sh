#!/usr/bin/env bash
# Clean Postgres scan history and re-run breakout, swing, and Lynch for all universes.
# Run from host: bash /opt/stacks/quant-hub/scripts/full-rescan.sh
set -euo pipefail

LOG="/mnt/fast/quant-data/logs/full_rescan.log"
OUT="/mnt/fast/quant-data/data/output"

mkdir -p "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

echo "========== Full rescan started $(date -Iseconds) =========="

echo "--- Cleaning Postgres ---"
docker exec quant-hub-db psql -U quant -d quant_hub -v ON_ERROR_STOP=1 -c \
  "TRUNCATE scan_runs RESTART IDENTITY CASCADE; TRUNCATE job_runs RESTART IDENTITY;"

echo "--- Cleaning file exports ---"
rm -rf "${OUT}/breakout"/* "${OUT}/swing"/* "${OUT}/lynch"/* "${OUT}/dry_run"/* 2>/dev/null || true
rm -f "${OUT}/breakout_scan_results.csv" "${OUT}/breakout_scan_report.json" "${OUT}/breakout_scan_summary.md" \
      "${OUT}/swing_setups.csv" "${OUT}/lynch_scan_results.csv" "${OUT}/lynch_scan_report.json" \
      "${OUT}/lynch_scan_summary.md" 2>/dev/null || true

echo "--- Breakout: all universes ---"
docker exec quant-hub quant-scan-all --cache --email --report both || echo "WARN: scan-all returned non-zero (check emails)"

echo "--- Swing: all universes ---"
docker exec quant-hub quant-swing-all --no-email || echo "WARN: swing-all returned non-zero"

echo "--- Lynch: stock universes ---"
docker exec quant-hub quant-lynch-all --no-email || echo "WARN: lynch-all returned non-zero"

echo "--- Final status ---"
docker exec quant-hub quant-hub status
echo "========== Full rescan finished $(date -Iseconds) =========="
