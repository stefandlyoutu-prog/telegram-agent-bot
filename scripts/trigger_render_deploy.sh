#!/usr/bin/env bash
# Ручной деплой moracul на Render (если auto-deploy не сработал).
set -euo pipefail
: "${RENDER_API_KEY:?Задай RENDER_API_KEY: https://dashboard.render.com/u/settings#api-keys}"

SERVICE_ID="${RENDER_SERVICE_ID:-}"
if [ -z "$SERVICE_ID" ]; then
  echo "Ищу service moracul…"
  SERVICE_ID=$(curl -sf "https://api.render.com/v1/services?limit=50" \
    -H "Authorization: Bearer ${RENDER_API_KEY}" \
    | python3 -c "
import sys, json
for item in json.load(sys.stdin):
    s = item.get('service') or item
    if s.get('name') == 'moracul':
        print(s['id'])
        break
")
fi
: "${SERVICE_ID:?Не найден service moracul — задай RENDER_SERVICE_ID}"

echo "Deploy moracul ($SERVICE_ID)…"
curl -sf -X POST "https://api.render.com/v1/services/${SERVICE_ID}/deploys" \
  -H "Authorization: Bearer ${RENDER_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"clearCache":"do_not_clear"}' \
  | python3 -m json.tool

echo ""
echo "Проверка (через 3–5 мин):"
echo "  curl -s https://moracul.onrender.com/health"
echo "  curl -sI https://moracul.onrender.com/landing | head -1"
