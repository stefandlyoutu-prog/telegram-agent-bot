# Telegram Agent Bot

Telegram-бот с ответами в стиле Cursor-агента: структурно, по-русски, с выбором модели через [OpenRouter](https://openrouter.ai).

## Возможности

- Диалог с памятью (история в SQLite)
- Выбор модели: GPT, Claude, Gemini, DeepSeek, Llama и др.
- Команды: `/start`, `/model`, `/reset`, `/help`
- Длинные ответы автоматически режутся на части

## Быстрый старт

### 1. Токен Telegram

1. Откройте [@BotFather](https://t.me/BotFather)
2. `/newbot` → имя и username
3. Скопируйте токен

### 2. Ключ OpenRouter

1. Зарегистрируйтесь на [openrouter.ai](https://openrouter.ai)
2. [Ключи](https://openrouter.ai/keys) → Create key
3. Пополните баланс (есть бесплатные модели, платные — по тарифу)

### 3. Установка

```bash
cd ~/Projects/telegram-agent-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Отредактируйте `.env`:

```env
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
OPENROUTER_API_KEY=sk-or-v1-...
DEFAULT_MODEL=openai/gpt-4o-mini
```

### 4. Запуск

```bash
python -m bot.main
```

Напишите боту в Telegram — готово.

## Команды в чате

| Команда | Действие |
|---------|----------|
| `/start` | Приветствие и текущая модель |
| `/model` | Кнопки выбора модели |
| `/reset` | Очистить историю |
| `/help` | Справка |

## Свои модели

Список в `bot/config.py` → `AVAILABLE_MODELS`. ID моделей: [openrouter.ai/models](https://openrouter.ai/models).

## Запуск на сервере (фон)

```bash
nohup python -m bot.main >> bot.log 2>&1 &
```

Или через `systemd` / Docker — по желанию.

## Структура

```
telegram-agent-bot/
  bot/
    main.py          # точка входа
    config.py        # настройки и промпт
    handlers/        # команды и чат
    services/        # OpenRouter + SQLite
  data/              # база истории
  .env               # секреты (не коммитить)
```

## Ограничения

- Бот не видит файлы на вашем компьютере — только текст в Telegram
- Стиль задаётся системным промптом в `config.py` — можно править под себя
- Для «как в Cursor» на 100% нужны те же модели и длинный контекст; здесь — максимально близкий тон через промпт + OpenRouter
