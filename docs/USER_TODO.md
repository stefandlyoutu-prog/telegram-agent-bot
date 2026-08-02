# Список дел для вас (когда сядете за комп)

Обновлено: 2026-07-23. Агент делает всё, что можно без вас; ниже — только то, где нужен человек.

## Срочно / доступы

1. **OpenAI / KupiAPI billing** — квота 429. Без этого голос и LLM-скрипты роликов падают на fallback.
   - https://platform.openai.com/account/billing
2. ~~**YouTube OAuth**~~ — обновлён 2026-08-02; Shorts снова льются. При `invalid_grant` снова: `python scripts/youtube_authorize.py`.
2b. **TikTok охват** — после пачки постов (~1 просмотр) автопост на паузе 48ч; дальше 1 ролик/день через `tiktok_daily_dropoff.py`. Проверить статус аккаунта в TikTok Studio.
2c. **Render env** — при правке env через API только `PUT .../env-vars/{KEY}` по одному ключу. Bulk PUT затирает все переменные.
3. **Новый Instagram** (старый `moracul_taro` отключён навсегда 19.07.2026):
   - другая почта + телефон;
   - прогрев 5–7 дней руками;
   - Creator → подключить в https://www.upload-post.com/ ;
   - написать агенту «инста готова» → включим `BIRTHDAY_SKIP_INSTAGRAM=0`.
4. **Google Search Console** для `https://moracul.ru` — подтвердить, отправить sitemap:
   - https://search.google.com/search-console
   - sitemap: `https://moracul.ru/sitemap.xml`
5. **Яндекс.Вебмастер** для `moracul.ru`:
   - https://webmaster.yandex.ru/

## Сайт / SEO (после доступов)

6. Проверить на проде после деплоя:
   - canonical статей = `https://moracul.ru/blog/...` (не onrender);
   - главная открывается, CTA ведёт с `src_*`.
7. Если Render деплоит из `m-oracul` — смержить/задеплоить SEO-сайт из monorepo (или дать агенту доступ к Render).
8. Решить приоритет внедрения с агентом: **калькулятор на сайте** (число судьбы / совместимость) или сначала ещё контент.

## Контент / деньги

9. Пополнить баланс LLM (см. п.1), иначе качество озвучки/сценариев хуже.
10. Проверить оплату в боте: 24 intent → 2 оплаты — усилить пейволл/лимит (агент может сделать в коде после ОКшего «да»).
11. Bio/ссылки на всех живых площадках → `https://moracul.ru/?src=...` + бот.

## Не трогать без нужды

- Ежедневная серия «рождённые N-го» — LaunchAgent 10:30 (VK+TikTok).
- Instagram в автопосте выключен специально.
- Upload-Post platforms = только `tiktok`.

## Деплой сайта (критично для SEO)

12. **Задеплоить monorepo на Render** (прод сейчас на коммите `b6bbbc6`, SEO-правки локально):
    - https://dashboard.render.com/
    - сервис `moracul` → Manual Deploy после `git push` из `telegram-agent-bot`
    - либо сказать агенту «запушь и задеплой» (нужен ваш OK на push).
13. На проде после деплоя проверить:
    - https://moracul.ru/blog/chislo-sudby — canonical = `https://moracul.ru/...` (не onrender)
    - в исходнике главной нет `SearchAction` и нет Instagram в `sameAs`

## Статус выгрузок (2026-07-23 утро)

| Канал | Birthday 20–23 | Бэклог плана |
|-------|----------------|--------------|
| VK | ✅ все 4 дня | ~51 posted / ~59 planned / 7 failed (догоняем) |
| TikTok | ✅ все 4 дня | ~18 posted / ~86 planned |
| YouTube | ❌ `invalid_grant` | ~27 posted / 71 planned / 22 failed |
| Instagram | ❌ аккаунт мёртв | автопост вырезан |

Файлы: `data/video_bot/promo/birthday_series/state.json`, `oracle_plan.json`.
## Автодогон при выключенном Mac

14. **Уже настроено на Mac:** LaunchAgent `com.oracle.promo-catchup`
    - при логине (`RunAtLoad`)
    - каждые 3 часа (`StartInterval`)
    - догоняет birthday (lookback 10 дней) + порцию VK + TikTok dropoff после 12:00
    - лог: `data/video_bot/promo/logs/catchup_on_login.log`
15. Не выключайте Mac сразу после включения — дайте 15–40 мин на рендер/выгрузку.
16. Если Mac выкл неделями — при первом включении догонит birthday; VK бэклог идёт порциями.

Скрипт: `scripts/promo_catchup_on_login.sh` · plist: `scripts/com.oracle.promo-catchup.plist`

## Сделать руками сегодня (деньги)

### OpenAI — иначе сценарии/бот тупят
1. Открой https://platform.openai.com/account/billing
2. Нажми **Add payment method** / **Add to credit balance**
3. Пополни минимум **$10–20**
4. Проверь https://platform.openai.com/usage что usage идёт

### YouTube Shorts — токен сдох (invalid_grant)
1. Открой https://console.cloud.google.com/apis/credentials
2. Убедись что OAuth Client (Desktop) жив, YouTube Data API v3 включён
3. В терминале на Mac:
```bash
cd ~/Projects/telegram-agent-bot
source .venv/bin/activate
# Client ID/Secret уже в .env — если нет, вставь:
# export YOUTUBE_CLIENT_ID=...
# export YOUTUBE_CLIENT_SECRET=...
.venv/bin/python scripts/youtube_authorize.py
```
4. Войди в Google аккаунт канала → Разрешить
5. Скопируй напечатанный `refresh_token` в `.env` как `YOUTUBE_REFRESH_TOKEN=...`
6. Напиши агенту «ютуб токен обновил»

### Instagram
1. Новая почта + телефон (не старый moracul_taro)
2. Создай аккаунт → прогрев 5–7 дней руками
3. Подключи в https://www.upload-post.com/
4. Напиши «инста готова»

### SEO индексирование
1. https://search.google.com/search-console → добавь `https://moracul.ru`
2. Отправь sitemap: `https://moracul.ru/sitemap.xml`
3. https://webmaster.yandex.ru/ → то же для moracul.ru

