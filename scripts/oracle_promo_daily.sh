#!/bin/bash
# Ежедневный автопостинг рекламы Оракула. Вызывается launchd/cron.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LOG_DIR="$ROOT/data/video_bot/promo/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%F).log"

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

# Прокси 127.0.0.1:10808 часто выключен — ломает LLM/TTS
if ! curl -s --connect-timeout 2 -x "${HTTP_PROXY:-http://127.0.0.1:10808}" https://api.openai.com >/dev/null 2>&1; then
  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
fi

{
  echo "=== $(date) oracle promo daily ==="
  # YouTube — только сегодня; VK — догоняем backlog (без --today-only)
  "$PY" scripts/oracle_video_promo.py run --platforms youtube --today-only --limit 2 "$@"
  "$PY" scripts/oracle_video_promo.py run --platforms vk --limit 2 "$@"
  echo "=== done $(date) ==="
} >> "$LOG" 2>&1
