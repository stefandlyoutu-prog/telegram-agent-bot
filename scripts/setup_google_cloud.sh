#!/usr/bin/env bash
# Одноразовая настройка Google Cloud для бота (Speech-to-Text, ADC).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GCLOUD="${HOME}/google-cloud-sdk/bin/gcloud"
PYTHON="${HOME}/miniconda3/bin/python"
ENV_FILE="${ROOT}/.env"

export CLOUDSDK_PYTHON="${PYTHON}"

if [[ ! -x "${GCLOUD}" ]]; then
  echo "❌ gcloud не найден в ~/google-cloud-sdk"
  exit 1
fi
if [[ ! -x "${PYTHON}" ]]; then
  echo "❌ Python (miniconda3) не найден"
  exit 1
fi

echo "=== 1/4 Вход в Google (ADC) ==="
echo "Откроется браузер — войдите в аккаунт, с которым оплачен Google Cloud."
echo "Скопируйте код из браузера и вставьте сюда, когда попросит."
"${GCLOUD}" auth application-default login

echo ""
echo "=== 2/4 Проект GCP ==="
CURRENT="$("${GCLOUD}" config get-value project 2>/dev/null || true)"
read -r -p "ID проекта GCP [${CURRENT}]: " PROJECT
PROJECT="${PROJECT:-${CURRENT}}"
if [[ -z "${PROJECT}" ]]; then
  echo "❌ Укажите GCP_PROJECT_ID (console.cloud.google.com → выберите проект → ID сверху)"
  exit 1
fi
"${GCLOUD}" config set project "${PROJECT}"

echo ""
echo "=== 3/4 Включение Speech-to-Text API ==="
"${GCLOUD}" services enable speech.googleapis.com --project="${PROJECT}"

echo ""
echo "=== 4/4 Запись в .env бота ==="
touch "${ENV_FILE}"
grep -q '^GCP_PROJECT_ID=' "${ENV_FILE}" 2>/dev/null && \
  sed -i.bak "s|^GCP_PROJECT_ID=.*|GCP_PROJECT_ID=${PROJECT}|" "${ENV_FILE}" || \
  echo "GCP_PROJECT_ID=${PROJECT}" >> "${ENV_FILE}"
grep -q '^GCP_SPEECH_ENABLED=' "${ENV_FILE}" 2>/dev/null && \
  sed -i.bak "s|^GCP_SPEECH_ENABLED=.*|GCP_SPEECH_ENABLED=1|" "${ENV_FILE}" || \
  echo "GCP_SPEECH_ENABLED=1" >> "${ENV_FILE}"
grep -q '^CLOUDSDK_PYTHON=' "${ENV_FILE}" 2>/dev/null && \
  sed -i.bak "s|^CLOUDSDK_PYTHON=.*|CLOUDSDK_PYTHON=${PYTHON}|" "${ENV_FILE}" || \
  echo "CLOUDSDK_PYTHON=${PYTHON}" >> "${ENV_FILE}"
rm -f "${ENV_FILE}.bak"

echo ""
echo "✅ Готово. Перезапустите бота и проверьте /gcp в Telegram."
echo "   Проект: ${PROJECT}"
