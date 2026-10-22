#!/usr/bin/env bash
# PostToolUse hook: ruff-check an edited Python file inside the dev container.
# Exit 2 sends the violations back to Claude; anything else stays silent.
set -uo pipefail

file=$(jq -r '.tool_input.file_path // empty')
root="${CLAUDE_PROJECT_DIR:-$(pwd)}"

[[ "$file" == *.py ]] || exit 0
rel="${file#"$root"/}"
[[ "$rel" == src/* || "$rel" == tests/* ]] || exit 0
docker inspect -f '{{.State.Running}}' quant-hub-dev 2>/dev/null | grep -q true || exit 0

if ! out=$(docker exec quant-hub-dev ruff check --no-cache --quiet --output-format concise "/app/$rel" 2>&1); then
  echo "ruff found issues in $rel:" >&2
  echo "$out" >&2
  exit 2
fi
