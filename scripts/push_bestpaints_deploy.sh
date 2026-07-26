#!/usr/bin/env bash
# Интерактивный push BestPaints → GitHub → Render (moracul)
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
ROOT="$HOME/Projects/telegram-agent-bot"
cd "$ROOT"

echo "════════════════════════════════════════"
echo "  Деплой BestPaints на moracul.ru"
echo "════════════════════════════════════════"
echo ""

# 1) GitHub token
if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "Нужен GitHub Personal Access Token (scope: repo)"
  echo "Создать: https://github.com/settings/tokens"
  echo ""
  read -r -s -p "Вставь токен и нажми Enter: " GITHUB_TOKEN
  echo ""
fi
: "${GITHUB_TOKEN:?токен пустой}"

echo "→ git push origin main…"
git push "https://${GITHUB_TOKEN}@github.com/stefandlyoutu-prog/telegram-agent-bot.git" HEAD:main
echo "✓ код на GitHub"

# 2) Render deploy (optional if auto-deploy)
if [ -n "${RENDER_API_KEY:-}" ]; then
  echo "→ триггер Render deploy…"
  bash "$ROOT/scripts/trigger_render_deploy.sh" || true
elif command -v render >/dev/null && render whoami >/dev/null 2>&1; then
  echo "→ Render CLI залогинен, жду auto-deploy от GitHub…"
else
  echo "→ Render: auto-deploy с GitHub (если включён)."
  echo "  Или: render login && затем trigger_render_deploy.sh"
fi

echo ""
echo "Через 3–5 мин открой:"
echo "  https://moracul.ru/bestpaints/"
echo "  логин: bestpaints"
echo "  пароль: ZamerBp2026!"
echo ""
echo -n "Проверка health: "
sleep 2
curl -sS "https://moracul.onrender.com/health" | head -c 200 || true
echo ""
echo ""
read -r -p "Enter чтобы закрыть… "
