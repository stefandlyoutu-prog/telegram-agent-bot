#!/usr/bin/env bash
# Установка Marzban (панель Xray VLESS+Reality) на чистый Ubuntu 22.04/24.04 VPS.
#
# Запускать НА САМОМ VPS от root (по SSH), не на своём компьютере:
#   ssh root@<IP_VPS>
#   curl -sSL https://raw.githubusercontent.com/<your-repo>/main/scripts/setup_marzban_vps.sh | bash
#   (или скопируй файл на сервер и запусти `bash setup_marzban_vps.sh`)
#
# Что делает:
#   1. Обновляет систему, ставит зависимости (curl, socat, docker).
#   2. Устанавливает Marzban (SQLite) через официальный скрипт Gozargah/Marzban-scripts.
#   3. Генерирует приватный/публичный ключ и shortId для Reality.
#   4. Подставляет готовый inbound VLESS+Reality в xray_config.json.
#   5. Перезапускает Marzban.
#
# ПОСЛЕ скрипта нужно руками (см. docs/VPN_BOT_SPEC.md):
#   - создать sudo-админа:  marzban cli admin create --sudo
#   - открыть панель по адресу http(s)://<IP>:8000/dashboard/ и убедиться, что видно ноду/инбаунд
#   - (рекомендуется) привязать домен + TLS для панели, см. официальный гайд Marzban
#   - прописать MARZBAN_BASE_URL / MARZBAN_USERNAME / MARZBAN_PASSWORD в Render (сервис vpnbot)

set -euo pipefail

REALITY_DEST="${REALITY_DEST:-www.microsoft.com:443}"
REALITY_SERVER_NAME="${REALITY_SERVER_NAME:-www.microsoft.com}"
XRAY_CONFIG="/var/lib/marzban/xray_config.json"

echo "== 1/5: apt update && upgrade =="
apt-get update -y && apt-get upgrade -y
apt-get install -y curl socat ca-certificates gnupg lsb-release ufw

echo "== 2/5: firewall (22 SSH, 443 Reality, 8000 панель) =="
ufw allow 22/tcp || true
ufw allow 443/tcp || true
ufw allow 8000/tcp || true
ufw --force enable || true

echo "== 3/5: установка Marzban (SQLite) через официальный скрипт =="
if ! command -v marzban >/dev/null 2>&1; then
  sudo bash -c "$(curl -sL https://github.com/Gozargah/Marzban-scripts/raw/master/marzban.sh)" @ install
fi

echo "Ждём поднятия контейнера Marzban…"
sleep 15

CONTAINER_NAME=$(docker ps --format '{{.Names}}' | grep -i marzban | head -n1 || true)
if [ -z "${CONTAINER_NAME}" ]; then
  echo "!! Контейнер marzban не найден в 'docker ps'. Проверь установку руками: marzban logs" >&2
  exit 1
fi
echo "Контейнер: ${CONTAINER_NAME}"

echo "== 4/5: генерация ключей Reality =="
KEYS_OUTPUT=$(docker exec "${CONTAINER_NAME}" xray x25519)
PRIVATE_KEY=$(echo "${KEYS_OUTPUT}" | grep -i "Private key:" | awk '{print $NF}')
PUBLIC_KEY=$(echo "${KEYS_OUTPUT}" | grep -i "Public key:" | awk '{print $NF}')
SHORT_ID=$(openssl rand -hex 8)

if [ -z "${PRIVATE_KEY}" ] || [ -z "${PUBLIC_KEY}" ]; then
  echo "!! Не удалось сгенерировать x25519-ключи. Вывод команды:" >&2
  echo "${KEYS_OUTPUT}" >&2
  exit 1
fi

echo "Private key: ${PRIVATE_KEY}"
echo "Public key:  ${PUBLIC_KEY}  (публичный ключ понадобится клиентам — Marzban сам добавит его в ссылку подписки)"
echo "Short ID:    ${SHORT_ID}"

echo "== 5/5: запись xray_config.json с инбаундом VLESS TCP REALITY =="
mkdir -p "$(dirname "${XRAY_CONFIG}")"
cat > "${XRAY_CONFIG}" <<JSON
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "tag": "VLESS TCP REALITY",
      "listen": "0.0.0.0",
      "port": 443,
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "tcpSettings": {},
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "${REALITY_DEST}",
          "xver": 0,
          "serverNames": ["${REALITY_SERVER_NAME}"],
          "privateKey": "${PRIVATE_KEY}",
          "shortIds": ["${SHORT_ID}"]
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": ["http", "tls", "quic"]
      }
    }
  ],
  "outbounds": [
    {
      "protocol": "freedom",
      "tag": "DIRECT"
    },
    {
      "protocol": "blackhole",
      "tag": "BLOCK"
    }
  ]
}
JSON

echo "Перезапуск Marzban…"
marzban restart

cat <<EOF

========================================================
Marzban установлен и настроен с инбаундом VLESS+Reality.

Дальше руками:
  1) marzban cli admin create --sudo     # создать логин/пароль для API/панели
  2) Открой панель:  http://<IP_ЭТОГО_VPS>:8000/dashboard/
  3) В Render (сервис vpnbot) пропиши:
       MARZBAN_BASE_URL=http://<IP_ЭТОГО_VPS>:8000
       MARZBAN_USERNAME=<логин из шага 1>
       MARZBAN_PASSWORD=<пароль из шага 1>
       MARZBAN_INBOUNDS=VLESS TCP REALITY

  Рекомендуется (не обязательно для старта): привязать домен + HTTPS
  для панели — см. https://github.com/Gozargah/Marzban#how-to-secure-panel
========================================================
EOF
