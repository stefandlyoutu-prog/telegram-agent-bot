#!/usr/bin/env bash
# Mini App + бот через HTTPS-туннель (пока Mac включён).
# Для 24/7 без Mac: ./scripts/deploy_oracle_render.sh → Render Blueprint.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${ORACLE_WEBAPP_PORT:-8787}"
LOG="/tmp/oracle-tunnel.log"
ENV_FILE="$ROOT/.env"

pkill -f "run_oracle_bot" 2>/dev/null || true
pkill -f "run_oracle_webapp" 2>/dev/null || true
pkill -f "run_oracle_cloud" 2>/dev/null || true
pkill -f "nokey@localhost.run" 2>/dev/null || true
sleep 1

echo "Туннель → http://127.0.0.1:${PORT}"
: > "$LOG"
nohup ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=60 \
  -R "80:127.0.0.1:${PORT}" nokey@localhost.run >"$LOG" 2>&1 &

URL=""
for _ in $(seq 1 30); do
  URL=$(grep -oE 'https://[a-z0-9.-]+\.(lhr|sfo|nyc)\.life' "$LOG" 2>/dev/null | head -1 || true)
  [[ -n "$URL" ]] && break
  sleep 1
done

if [[ -z "$URL" ]]; then
  echo "Не удалось получить URL. Смотрите ${LOG}"
  exit 1
fi

echo "HTTPS: ${URL}"

if grep -q '^ORACLE_WEBAPP_URL=' "$ENV_FILE"; then
  sed -i '' "s|^ORACLE_WEBAPP_URL=.*|ORACLE_WEBAPP_URL=${URL}|" "$ENV_FILE"
else
  echo "ORACLE_WEBAPP_URL=${URL}" >>"$ENV_FILE"
fi

export ORACLE_CLOUD=1
export ORACLE_WEBHOOK_URL="$URL"
export ORACLE_WEBAPP_URL="$URL"
export LLM_PROXY="${LLM_PROXY:-}"
export TELEGRAM_PROXY="${TELEGRAM_PROXY:-}"

nohup .venv/bin/python3 scripts/run_oracle_cloud.py >/tmp/oracle-cloud.log 2>&1 &

for _ in $(seq 1 20); do
  curl -sf "${URL}/health" >/dev/null && break
  sleep 0.5
done

curl -sf "${URL}/health" >/dev/null || { echo "Mini App не отвечает"; exit 1; }
echo "Готово: ${URL} (webhook + Mini App). Лог: /tmp/oracle-cloud.log"
