#!/usr/bin/env bash
# Автодеплой @MOracul_bot: GitHub + Render Blueprint.
# Нужны: GITHUB_TOKEN (repo), RENDER_API_KEY (rnd_...), GITHUB_USER (логин GitHub).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RENDER="${RENDER:-$HOME/.local/bin/render}"

: "${GITHUB_TOKEN:?Задай GITHUB_TOKEN — https://github.com/settings/tokens (scope: repo)}"
: "${RENDER_API_KEY:?Задай RENDER_API_KEY — https://dashboard.render.com/u/settings#api-keys}"
: "${GITHUB_USER:?Задай GITHUB_USER — твой логин GitHub}"

REPO_NAME="${GITHUB_REPO_NAME:-moracul-bot}"
BRANCH="${GITHUB_BRANCH:-main}"

export RENDER_API_KEY

echo "=== 1/4 Git init + commit ==="
if [ ! -d .git ]; then
  git init -b "$BRANCH"
  git config user.email "${GIT_EMAIL:-moracul-bot@users.noreply.github.com}"
  git config user.name "${GIT_NAME:-m-Oracul Deploy}"
fi
git add -A
git diff --cached --quiet && echo "Нет изменений для commit" || git commit -m "Deploy m-Oracul bot to Render"

echo "=== 2/4 GitHub repo ==="
API="https://api.github.com"
AUTH="Authorization: token ${GITHUB_TOKEN}"
if ! curl -sf -H "$AUTH" "$API/repos/${GITHUB_USER}/${REPO_NAME}" >/dev/null; then
  curl -sf -X POST -H "$AUTH" -H "Accept: application/vnd.github+json" \
    "$API/user/repos" \
    -d "{\"name\":\"${REPO_NAME}\",\"private\":true,\"description\":\"@MOracul_bot Telegram oracle\"}"
  echo "Создан репозиторий ${GITHUB_USER}/${REPO_NAME}"
fi

REMOTE="https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE"
git push -u origin "$BRANCH" --force

REPO_URL="https://github.com/${GITHUB_USER}/${REPO_NAME}"

echo "=== 3/4 Render Blueprint ==="
export RENDER_OUTPUT=json
"$RENDER" workspace set --confirm 2>/dev/null || true

BP=$(curl -sf -X POST "https://api.render.com/v1/blueprints" \
  -H "Authorization: Bearer ${RENDER_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"moracul\",\"repo\":\"${REPO_URL}\",\"branch\":\"${BRANCH}\"}" || true)

if [ -z "$BP" ]; then
  echo "Blueprint через API не создался — открой вручную:"
  echo "  https://dashboard.render.com/blueprints → New → ${REPO_URL}"
else
  echo "$BP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Blueprint:', d.get('id','?'))" 2>/dev/null || echo "$BP"
fi

echo "=== 4/4 Секреты на Render (задай в Dashboard → moracul → Environment) ==="
echo "  ORACLE_BOT_TOKEN"
echo "  GROK_API_KEY"
echo "  GEMINI_API_KEY"
echo "  LLM_API_KEY"
echo "  MONEY_ADMIN_IDS=5845195049"
echo ""
echo "После деплоя останови локального бота:"
echo "  pkill -f run_oracle_cloud; pkill -f run_oracle_bot"
echo ""
echo "Repo: ${REPO_URL}"
