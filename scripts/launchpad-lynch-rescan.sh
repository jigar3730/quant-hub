#!/usr/bin/env bash
# Clean Launchpad + Lynch rescan for stock universes.
# Run from host: bash /opt/stacks/quant-hub/scripts/launchpad-lynch-rescan.sh
set -euo pipefail

LOG="/mnt/fast/quant-data/logs/launchpad_lynch_rescan.log"

mkdir -p "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

echo "========== Launchpad+Lynch rescan started $(date -Iseconds) =========="

echo "--- Launchpad: all stock universes ---"
docker exec quant-hub quant-launchpad-all --cache --report both || echo "WARN: launchpad-all returned non-zero"

echo "--- Lynch: stock universes ---"
docker exec quant-hub quant-lynch-all --no-email || echo "WARN: lynch-all returned non-zero"

echo "--- Final status ---"
docker exec quant-hub quant-hub status
echo "========== Launchpad+Lynch rescan finished $(date -Iseconds) =========="
