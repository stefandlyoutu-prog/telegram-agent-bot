#!/bin/bash
# Догон промо при включении Mac / логине / каждые N часов (launchd).
# Если комп был выключен в 10:30 — при включении выгрузит пропущенные birthday + порцию VK.
set -u

ROOT="/Users/polzovatel/Projects/telegram-agent-bot"
cd "$ROOT" || exit 1

LOG_DIR="$ROOT/data/video_bot/promo/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/catchup_on_login.log"
LOCK="$ROOT/data/video_bot/promo/catchup.lock"
STAMP="$ROOT/data/video_bot/promo/catchup.last"

{
  echo "=== $(date) promo catchup start ==="

  # Не гоняем параллельно
  if [ -f "$LOCK" ]; then
    old_pid=$(cat "$LOCK" 2>/dev/null || true)
    if [ -n "${old_pid:-}" ] && kill -0 "$old_pid" 2>/dev/null; then
      echo "already running pid=$old_pid — exit"
      exit 0
    fi
    rm -f "$LOCK"
  fi
  echo $$ > "$LOCK"
  trap 'rm -f "$LOCK"' EXIT

  # Анти-дребезг: не чаще раза в 20 минут (StartInterval + wake)
  if [ -f "$STAMP" ]; then
    last=$(cat "$STAMP" 2>/dev/null || echo 0)
    now=$(date +%s)
    if [ $((now - last)) -lt 1200 ]; then
      echo "skip: ran $((now - last))s ago"
      exit 0
    fi
  fi

  set -a
  # shellcheck disable=SC1091
  [ -f .env ] && source .env
  set +a

  # Локальный прокси часто выключен и рвёт DNS/TLS
  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy

  export VIDEO_TTS_ENGINE="${VIDEO_TTS_ENGINE:-edge}"
  export VIDEO_TTS_POLISH=0
  export UPLOAD_POST_SKIP_INSTAGRAM="${UPLOAD_POST_SKIP_INSTAGRAM:-1}"
  export BIRTHDAY_SKIP_INSTAGRAM="${BIRTHDAY_SKIP_INSTAGRAM:-1}"
  export BIRTHDAY_SERIES_START="${BIRTHDAY_SERIES_START:-2026-07-20}"

  PY="$ROOT/.venv/bin/python"
  [ -x "$PY" ] || PY=python3
  export PYTHONUNBUFFERED=1

  # Ждём сеть (после сна DNS поднимается не сразу)
  ok_net=0
  for i in $(seq 1 36); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 https://api.upload-post.com 2>/dev/null || echo 000)
    if echo "$code" | grep -qE '^(200|301|302|400|401|403|404)$'; then
      ok_net=1
      echo "network ok (upload-post http $code) after try $i"
      break
    fi
    echo "wait network try=$i code=$code"
    sleep 5
  done
  if [ "$ok_net" != 1 ]; then
    echo "no network — abort"
    exit 1
  fi

  echo "--- birthday catch-up (lookback 10) ---"
  "$PY" scripts/birthday_daily_series.py --catch-up --lookback 10 || echo "birthday catch-up exit=$?"

  echo "--- VK backlog batch ---"
  "$PY" scripts/oracle_video_promo.py run --platforms vk --limit 4 || echo "vk exit=$?"

  # Если после полудня — подготовить завтрашний TikTok dropoff (идемпотентно)
  hour=$(date +%H)
  if [ "$hour" -ge 12 ]; then
    echo "--- tiktok dropoff (tomorrow) ---"
    "$PY" scripts/tiktok_daily_dropoff.py || echo "dropoff exit=$?"
  fi

  date +%s > "$STAMP"
  echo "=== $(date) promo catchup done ==="
} >> "$LOG" 2>&1
