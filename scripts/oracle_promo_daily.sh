#!/bin/bash
# Ежедневный автопостинг рекламы Оракула. Вызывается launchd/cron.
# Рендерит запланированные ролики, грузит на площадки, шлёт отчёт админу в Telegram.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LOG_DIR="$ROOT/data/video_bot/promo/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%F).log"

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

{
  echo "=== $(date) oracle promo daily ==="
  "$PY" scripts/oracle_video_promo.py run "$@"
  echo "=== done $(date) ==="
} >> "$LOG" 2>&1
