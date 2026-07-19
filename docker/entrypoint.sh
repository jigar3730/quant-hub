#!/bin/bash
set -e

mkdir -p /app/logs
touch /app/logs/cron.log /app/logs/dashboard.log

printenv | grep -E '^(SMTP_|EMAIL_|TZ=|PATH=|PYTHONPATH=|DATABASE_URL|POSTGRES_)' > /etc/environment 2>/dev/null || true

# Apply schema on startup (idempotent)
quant-hub init-db --quiet >> /app/logs/cron.log 2>&1 || true

case "${1:-scheduler}" in
  scan)
    echo "Running one-time Launchpad daily scan..."
    exec quant-launchpad-daily --universe "${UNIVERSE:-sp500_index}" --no-email
    ;;

  scheduler)
    echo "Starting Streamlit dashboard on port 5000..."
    quant-view --server.port 5000 --server.address 0.0.0.0 > /app/logs/dashboard.log 2>&1 &

    echo "Starting cron scheduler (${TZ})..."
    exec cron -f
    ;;

  *)
    exec "$@"
    ;;
esac
