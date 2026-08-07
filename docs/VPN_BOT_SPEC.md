# VPN-бот (аналог @siriusvpnbot) — спецификация

Обновлено: 2026-08-04.

## Идея

Свой VPN-сервис без написания клиентского приложения с нуля:

- **Сервер**: [Marzban](https://github.com/Gozargah/Marzban) (панель + REST API) поверх
  Xray-core с инбаундом **VLESS + Reality** — сейчас лучше всего живёт под DPI-блокировками
  в РФ, т.к. маскируется под обычный HTTPS-сайт (в примере — `www.microsoft.com`).
- **Клиент**: НЕ пишем свой — пользователь ставит готовое приложение
  ([Happ](https://happ.su/), [v2rayNG](https://github.com/2dust/v2rayNG),
  [Hiddify](https://github.com/hiddify/hiddify-app)) и импортирует **подписочную ссылку**,
  которую выдаёт бот. Все три поддерживают протокол VLESS/Reality из коробки.
- **Бот** (`vpn_bot/`, aiogram, как `oracle_bot/`): `/start`, тарифы, оплата Робокасса,
  выдача/продление ключа через Marzban API, QR-код + ссылка подписки, пробный период.

Если позже понадобится «свой брендированный клиент» — реалистичный путь: white-label форк
Happ/v2rayNG/Hiddify (это открытые исходники) под своей иконкой/названием, а не написание
VPN-протокола с нуля. Это отдельная задача на недели, не блокирует запуск бота.

## Архитектура

```
Telegram user ──▶ vpn_bot (Render, webhook)
                     │  aiogram + FastAPI, SQLite (users/invoices/subscriptions)
                     │
                     ├──▶ Робокасса (оплата картой/СБП)
                     │
                     └──▶ Marzban REST API (VPS) ──▶ Xray-core (VLESS+Reality, порт 443)
                                                         │
                                                         ▼
                                                  клиент пользователя
                                            (Happ / v2rayNG / Hiddify) ──▶ интернет
```

Бот и VPN-нода — **разные машины**: бот живёт на Render (как остальные боты в репо),
VPN-нода — на отдельном VPS за рубежом (близко к РФ по задержке — обычно Европа).

## Тарифы (по умолчанию, меняются через `VPN_TARIFFS` в Render без деплоя)

| Тариф | Дней | Цена |
|-------|------|------|
| 1 месяц | 30 | 199₽ |
| 3 месяца | 90 | 499₽ |
| 12 месяцев | 365 | 1499₽ |
| Пробный период | 3 (`VPN_TRIAL_DAYS`) | бесплатно, 1 раз на пользователя |

Формат `VPN_TARIFFS` — JSON-список:
```json
[{"id":"m1","title":"1 месяц","days":30,"price_rub":199}, ...]
```

## Код

| Файл | Роль |
|------|------|
| `vpn_bot/config.py` | env-переменные: токен, тарифы, доступ к Marzban, Робокасса |
| `vpn_bot/storage.py` | SQLite: users, invoices, subscriptions |
| `vpn_bot/marzban_client.py` | REST-клиент Marzban (login, create/get/modify user) |
| `vpn_bot/access.py` | выдача/продление ключа (пробный период + оплаченный тариф) |
| `vpn_bot/robokassa.py` | ссылка на оплату + проверка подписи колбэков |
| `vpn_bot/keyboards.py`, `handlers.py` | UI бота |
| `vpn_bot/main.py` | локальный запуск (long polling) |
| `vpn_bot/cloud.py`, `webapp.py`, `scripts/run_vpn_cloud.py` | облачный режим (webhook, Render) |
| `scripts/setup_marzban_vps.sh` | установка Marzban+Xray Reality на чистый VPS |

## Deployment — что нужно сделать руками (не может агент)

1. **Арендовать VPS** за рубежом (карта/крипта — см. `docs/USER_TODO.md`).
2. **Запустить `scripts/setup_marzban_vps.sh` на VPS** по SSH (скопировать файл или через
   `curl` из своего форка/репо — см. комментарий в начале скрипта).
3. Создать sudo-админа панели: `marzban cli admin create --sudo`.
4. В Render, сервис **`vpnbot`** (уже описан в `render.yaml`), задать:
   - `VPN_BOT_TOKEN`, `VPN_BOT_USERNAME` — токен нового бота у @BotFather
   - `MARZBAN_BASE_URL=http://<IP_VPS>:8000`, `MARZBAN_USERNAME`, `MARZBAN_PASSWORD`
   - `VPN_ROBOKASSA_LOGIN/PASSWORD1/PASSWORD2` (можно тот же магазин Робокассы, что у Оракула,
     либо отдельный — тогда счета будут разделены по продуктам)
   - `VPN_WEBHOOK_URL` — публичный адрес сервиса на Render (после первого деплоя)
5. Задеплоить Blueprint на Render (или добавить сервис вручную, если Blueprint уже применён).
6. В Робокассе (Настройки магазина) указать:
   - ResultURL: `https://<vpnbot>.onrender.com/robokassa/result`
   - SuccessURL: `https://<vpnbot>.onrender.com/robokassa/success`
   - FailURL: `https://<vpnbot>.onrender.com/robokassa/fail`

## Инструкция для пользователя бота («Как подключить»)

1. Установить Happ (happ.su) / v2rayNG / Hiddify.
2. В боте открыть «🔑 Мой ключ» — придёт ссылка подписки + QR.
3. В приложении: «Добавить подписку по ссылке» (или Import from clipboard) → вставить ссылку.
4. Обновить список серверов → «Подключить».

## Дальнейшее развитие (не сделано, при желании — отдельные задачи)

- Несколько VPN-нод (страны) через Marzban Node — сейчас 1 сервер = 1 страна.
- White-label клиент (форк Happ/v2rayNG) под своим брендом.
- Реферальная программа / автопродление / напоминания об истечении ключа (пуши).
- Отдельный Робокасса-магазин, если не хочешь мешать с оракулом.
- Юридический момент: продажа VPN-доступа как услуги — при заметных объёмах платежей
  разумно оформить как самозанятый/ИП (как уже сделано для Оракула, см. `ORACLE_SELFEMPLOYED_*`).
