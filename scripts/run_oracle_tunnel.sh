#!/usr/bin/env bash
# HTTPS-туннель для Mini App (localhost.run → порт 8787)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${ORACLE_WEBAPP_PORT:-8787}"
LOG="/tmp/oracle-tunnel.log"

if ! curl -sf "http://127.0.0.1:${PORT}/" >/dev/null; then
  echo "Mini App не запущен. Сначала:"
  echo "  .venv/bin/python3 scripts/run_oracle_webapp.py"
  exit 1
fi

echo "Поднимаю HTTPS-туннель → http://127.0.0.1:${PORT}"
echo "Лог: ${LOG}"
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=60 \
  -R "80:127.0.0.1:${PORT}" nokey@localhost.run 2>&1 | tee "$LOG"
