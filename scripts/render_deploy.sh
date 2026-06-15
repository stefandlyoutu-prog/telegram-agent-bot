#!/usr/bin/env bash
# Полный деплoy @MOracul_bot на Render.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${RENDER_API_KEY:?Задай RENDER_API_KEY}"
: "${GITHUB_REPO:?Задай GITHUB_REPO, например https://github.com/user/telegram-agent-bot}"

export PATH="$HOME/.local/bin:$PATH"
render workspace set tea-d8o5bqog4nts73d0fvvg --confirm -o text >/dev/null

# Секреты из .env (если есть)
set -a
# shellcheck disable=SC1091
[[ -f .env ]] && source .env
set +a

ENV_FLAGS=(
  --env-var "ORACLE_CLOUD=1"
  --env-var "ORACLE_BOT_USERNAME=MOracul_bot"
  --env-var "LLM_BASE_URL=https://kupiapi.ru/v1"
  --env-var "LLM_PROXY="
  --env-var "TELEGRAM_PROXY="
  --env-var "ORACLE_PUSH_ENABLED=1"
  --env-var "ORACLE_FREE_PER_DAY=2"
)
[[ -n "${ORACLE_BOT_TOKEN:-}" ]] && ENV_FLAGS+=(--env-var "ORACLE_BOT_TOKEN=${ORACLE_BOT_TOKEN}")
[[ -n "${GROK_API_KEY:-}" ]] && ENV_FLAGS+=(--env-var "GROK_API_KEY=${GROK_API_KEY}")
[[ -n "${GEMINI_API_KEY:-}" ]] && ENV_FLAGS+=(--env-var "GEMINI_API_KEY=${GEMINI_API_KEY}")
[[ -n "${LLM_API_KEY:-}" ]] && ENV_FLAGS+=(--env-var "LLM_API_KEY=${LLM_API_KEY}")
[[ -n "${MONEY_ADMIN_IDS:-}" ]] && ENV_FLAGS+=(--env-var "MONEY_ADMIN_IDS=${MONEY_ADMIN_IDS}")

echo "Создаю web service moracul..."
OUT=$(render services create \
  --name moracul \
  --type web_service \
  --repo "$GITHUB_REPO" \
  --branch main \
  --runtime python \
  --plan free \
  --region frankfurt \
  --build-command "pip install -r requirements-oracle.txt" \
  --start-command "python scripts/run_oracle_cloud.py" \
  --health-check-path /health \
  "${ENV_FLAGS[@]}" \
  --confirm -o json)

echo "$OUT" | python3 -m json.tool

URL=$(echo "$OUT" | python3 -c "import sys,json; s=json.load(sys.stdin); print(s.get('service',{}).get('serviceDetails',{}).get('url','') or s.get('service',{}).get('url',''))" 2>/dev/null || true)
echo ""
echo "Сервис создан. URL: ${URL:-смотри Render Dashboard}"
echo "После деплоя Mini App: \$RENDER_EXTERNAL_URL (автоматически)"
