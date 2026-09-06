#!/usr/bin/env bash
# Usage: scripts/run_env.sh {dev|stage|prod} [compose args...]
# Examples:
#   scripts/run_env.sh dev up
#   scripts/run_env.sh stage up -d
#   scripts/run_env.sh prod up -d
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_NAME="${1:-}"
if [[ -z "$ENV_NAME" ]]; then
  echo "Usage: $0 {dev|stage|prod} [compose args...]" >&2
  exit 1
fi
shift

case "$ENV_NAME" in
  dev|stage|prod) ;;
  *)
    echo "Unknown env: $ENV_NAME (use dev, stage, or prod)" >&2
    exit 1
    ;;
esac

ENV_FILE=".env.${ENV_NAME}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy from ${ENV_FILE}.example and set secrets." >&2
  exit 1
fi

# Isolated project name so stacks do not share one default network.
export COMPOSE_PROJECT_NAME="quant-hub-${ENV_NAME}"

exec docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f "docker-compose.${ENV_NAME}.yml" \
  "$@"
