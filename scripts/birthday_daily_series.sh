#!/bin/bash
set -euo pipefail

ROOT="/Users/polzovatel/Projects/telegram-agent-bot"
cd "$ROOT"

set -a
[ -f .env ] && source .env
set +a

# Локальный прокси часто выключен и подвешивает медиа/API.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy

# OpenAI квота часто 429 — edge по умолчанию; догон пропусков если Mac был выкл.
export VIDEO_TTS_ENGINE="${VIDEO_TTS_ENGINE:-edge}"
export VIDEO_TTS_POLISH=0
export BIRTHDAY_SKIP_INSTAGRAM="${BIRTHDAY_SKIP_INSTAGRAM:-1}"

mkdir -p data/video_bot/promo/logs
"$ROOT/.venv/bin/python" scripts/birthday_daily_series.py --catch-up --lookback 7 \
  >> "data/video_bot/promo/logs/birthday_daily_series.log" 2>&1
