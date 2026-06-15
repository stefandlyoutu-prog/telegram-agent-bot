import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Прокси для Telegram, если api.telegram.org недоступен: socks5://127.0.0.1:10808
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip() or None
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://kupiapi.ru/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "") or os.getenv("OPENROUTER_API_KEY", "")
# Прокси только для KupiAPI (пусто = напрямую). Telegram — TELEGRAM_PROXY.
LLM_PROXY = os.getenv("LLM_PROXY", "").strip() or None
LLM_CONNECT_TIMEOUT_SEC = int(os.getenv("LLM_CONNECT_TIMEOUT_SEC", "15"))
GROK_API_KEY = os.getenv("GROK_API_KEY", "") or os.getenv("XAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Запасной LLM, если KupiAPI недоступен (нужен GEMINI_API_KEY)
LLM_GEMINI_FALLBACK = os.getenv("LLM_GEMINI_FALLBACK", "1") not in {"0", "false", "False"}
# auto = Kupi, при сбое → Gemini; gemini = только Google; kupi = без запасного
LLM_PRIMARY = os.getenv("LLM_PRIMARY", "auto").strip().lower() or "auto"
KUPI_CIRCUIT_SEC = int(os.getenv("KUPI_CIRCUIT_SEC", "300"))
GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
# xAI Imagine: grok-imagine-image-quality (ключ с https://console.x.ai, не Groq gsk_)
GROK_IMAGE_MODEL = os.getenv("GROK_IMAGE_MODEL", "grok-imagine-image-quality")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-5.4-mini")
# Единственная модель KupiAPI, которая реально «видит» картинки в тестах
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-5.4-mini")
IMAGE_GENERATION_MODEL = os.getenv("IMAGE_GENERATION_MODEL", "gpt-5.4-nano")
IMAGE_EDIT_MODEL = os.getenv("IMAGE_EDIT_MODEL", VISION_MODEL)
IMAGE_OUTPUT_ENABLED = os.getenv("IMAGE_OUTPUT_ENABLED", "1") not in {"0", "false", "False"}
IMAGE_PROVIDER_ORDER = os.getenv("IMAGE_PROVIDER_ORDER", "auto")
# Бесплатный T2I: https://t2i.mcpcore.xyz (запасной — https://subnp.com)
FREE_T2I_ENABLED = os.getenv("FREE_T2I_ENABLED", "0") not in {"0", "false", "False"}
# AI-генерация картинок (отключено по умолчанию — только Unsplash + шаблон Avito)
GROK_IMAGE_ENABLED = os.getenv("GROK_IMAGE_ENABLED", "0") not in {"0", "false", "False"}
GEMINI_IMAGE_ENABLED = os.getenv("GEMINI_IMAGE_ENABLED", "0") not in {"0", "false", "False"}
LAOZHANG_IMAGE_ENABLED = os.getenv("LAOZHANG_IMAGE_ENABLED", "0") not in {"0", "false", "False"}
FREE_T2I_BASE_URL = os.getenv("FREE_T2I_BASE_URL", "https://t2i.mcpcore.xyz").rstrip("/")
FREE_T2I_FALLBACK_URL = os.getenv("FREE_T2I_FALLBACK_URL", "https://subnp.com").rstrip("/")
FREE_T2I_MODEL = os.getenv("FREE_T2I_MODEL", "turbo")
FREE_T2I_TIMEOUT_SEC = int(os.getenv("FREE_T2I_TIMEOUT_SEC", "120"))
# LaoZhang API — https://api.laozhang.ai (OpenAI-совместимый Images API)
LAOZHANG_API_KEY = os.getenv("LAOZHANG_API_KEY", "").strip()
LAOZHANG_BASE_URL = os.getenv("LAOZHANG_BASE_URL", "https://api.laozhang.ai/v1").rstrip("/")
LAOZHANG_IMAGE_MODEL = os.getenv("LAOZHANG_IMAGE_MODEL", "gpt-image-1")
LAOZHANG_TIMEOUT_SEC = int(os.getenv("LAOZHANG_TIMEOUT_SEC", "300"))
# Unsplash — https://unsplash.com/developers (достаточно Access Key, Public scope)
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
UNSPLASH_ENABLED = os.getenv("UNSPLASH_ENABLED", "1") not in {"0", "false", "False"}
UNSPLASH_TIMEOUT_SEC = int(os.getenv("UNSPLASH_TIMEOUT_SEC", "30"))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "20"))
# Meshy image-to-3D — https://www.meshy.ai (опционально, для STL с фото)
MESHY_API_KEY = os.getenv("MESHY_API_KEY", "").strip()
MESHY_TIMEOUT_SEC = int(os.getenv("MESHY_TIMEOUT_SEC", "300"))
OPENSCAD_PATH = os.getenv("OPENSCAD_PATH", "").strip()
# Маршрутизация задач и самопроверка (выключить позже: SELF_CHECK_ENABLED=0)
TASK_ROUTER_ANNOUNCE = os.getenv("TASK_ROUTER_ANNOUNCE", "1") not in {"0", "false", "False"}
# Не спрашивать принтер/материал — сразу делать (дефолт P2S + PLA из .env)
DEFAULT_AUTO_PROCEED = os.getenv("DEFAULT_AUTO_PROCEED", "1") not in {"0", "false", "False"}
DEFAULT_PRINTER = os.getenv("DEFAULT_PRINTER", "Bambu Lab P2S").strip()
DEFAULT_MATERIAL = os.getenv("DEFAULT_MATERIAL", "PLA").strip()
DEFAULT_NOZZLE_MM = float(os.getenv("DEFAULT_NOZZLE_MM", "0.4"))
DEFAULT_SLICER = os.getenv("DEFAULT_SLICER", "Bambu Studio").strip()
DEFAULT_AMS = os.getenv("DEFAULT_AMS", "1") not in {"0", "false", "False"}
SELF_CHECK_ENABLED = os.getenv("SELF_CHECK_ENABLED", "1") not in {"0", "false", "False"}
SELF_CHECK_MODEL = os.getenv("SELF_CHECK_MODEL", DEFAULT_MODEL)
SELF_CHECK_TIMEOUT_SEC = int(os.getenv("SELF_CHECK_TIMEOUT_SEC", "45"))
# Подставлять оптимальную модель на задачу без «ваша не оптимальна»
AUTO_SWITCH_MODEL = os.getenv("AUTO_SWITCH_MODEL", "1") not in {"0", "false", "False"}
# Google Cloud — ADC (не API-ключ). Speech-to-Text для голосовых.
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "").strip()
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
GCP_SPEECH_ENABLED = os.getenv("GCP_SPEECH_ENABLED", "1") not in {"0", "false", "False"}
GCP_SPEECH_LANGUAGE = os.getenv("GCP_SPEECH_LANGUAGE", "ru-RU").strip() or "ru-RU"
GCP_SPEECH_TIMEOUT_SEC = int(os.getenv("GCP_SPEECH_TIMEOUT_SEC", "25"))
# Запасной STT для голосовых, если Google Speech зависает (Gemini API key)
GCP_STT_GEMINI_FALLBACK = os.getenv("GCP_STT_GEMINI_FALLBACK", "1") not in {"0", "false", "False"}
GCP_STT_KUPI_FALLBACK = os.getenv("GCP_STT_KUPI_FALLBACK", "1") not in {"0", "false", "False"}
GCP_STT_KUPI_MODEL = os.getenv("GCP_STT_KUPI_MODEL", "whisper-1").strip() or "whisper-1"
GCP_TTS_ENABLED = os.getenv("GCP_TTS_ENABLED", "1") not in {"0", "false", "False"}
GCP_TTS_VOICE = os.getenv("GCP_TTS_VOICE", "ru-RU-Chirp3-HD-Charon").strip() or "ru-RU-Chirp3-HD-Charon"
GCP_TTS_LANGUAGE = os.getenv("GCP_TTS_LANGUAGE", "ru-RU").strip() or "ru-RU"
GCP_VISION_ENABLED = os.getenv("GCP_VISION_ENABLED", "1") not in {"0", "false", "False"}
GCP_TRANSLATE_ENABLED = os.getenv("GCP_TRANSLATE_ENABLED", "1") not in {"0", "false", "False"}
GCP_TRANSLATE_TARGET = os.getenv("GCP_TRANSLATE_TARGET", "ru").strip() or "ru"
MESHY_RIG_TIMEOUT_SEC = int(os.getenv("MESHY_RIG_TIMEOUT_SEC", "600"))
# Текст, если бот чего-то не умеет — обучение через Агента
AGENT_CONTACT_HINT = os.getenv(
    "AGENT_CONTACT_HINT",
    "Напишите нашему Агенту в Cursor (или в чат разработки бота), "
    "чтобы он обучил меня этому — укажите, что именно нужно.",
).strip()

LLM_CHAT_URL = f"{LLM_BASE_URL}/chat/completions"
DB_PATH = DATA_DIR / "bot.db"

# Актуальные ID с https://kupiapi.ru/docs
AVAILABLE_MODELS: dict[str, str] = {
    "gpt-5.4-mini": "GPT-5.4 mini (рекомендуется)",
    "gpt-5.4": "GPT-5.4",
    "gpt-5.5": "GPT-5.5",
    "gpt-5.4-nano": "GPT-5.4 nano",
    "claude-haiku-4.5": "Claude Haiku 4.5",
    "claude-sonnet-4.6": "Claude Sonnet 4.6",
    "claude-opus-4.7": "Claude Opus 4.7",
    "gpt-5.5-codex": "GPT-5.5 Codex",
    "deepseek-chat": "DeepSeek Chat",
    "deepseek-reasoner": "DeepSeek Reasoner",
    # старые алиасы → для уже сохранённых в БД
    "gpt-4o-mini": "GPT-5.4 mini",
    "gpt-4o": "GPT-5.4",
    "claude-haiku": "Claude Haiku 4.5",
    "claude-sonnet": "Claude Sonnet 4.6",
    "claude-opus": "Claude Opus 4.7",
    "deepseek-r1": "DeepSeek Reasoner",
}

SYSTEM_PROMPT = """Ты — инженерный ассистент в Telegram, стиль ответов как у агента Cursor.

Главная роль:
- Думай как инженер: цель → требования → ограничения → размеры → материалы → риски → результат.
- Если пользователь пишет «сделай», «спроектируй», «воплоти», «начерти», «собери проект» — не отвечай общими советами, а готовь конкретный результат: расчёт, ТЗ, чертёж, таблицу, файл, проект или список уточнений.
- Не подменяй точную инженерную задачу примитивной болванкой. Если данных мало, явно напиши допущения и сделай версию v0, которую можно уточнять.
- Ты — воплощение инженера: понимаешь, что пользователь хочет получить в реальности, выбираешь правильный инструмент/специализацию и ведёшь задачу к готовому результату.
- Сначала распознай истинную цель пользователя, а не только ключевые слова. «Хочу распечатать и нажать Print» значит нужен практичный файл, материалы, цвета, сборка, риски и проверка в слайсере.
- Если прямой идеальный результат невозможен сейчас, не останавливайся: предложи лучший достижимый путь (процедурный v0, Meshy-скульпт, CAD-деталь, проект ZIP, PDF, таблица, план проверки) и честно назови ограничения.
- Не выдавай мечту за факт: отличай «сделал файл», «сделал процедурный прототип», «нужна ручная настройка в Bambu Studio», «нужны уточнения».

Правила:
- Отвечай на русском, если пользователь пишет по-русски.
- Пиши ясно и по делу: структура, списки, таблицы когда уместно.
- Для инженерных задач указывай единицы измерения, допуски, материал, масштаб, критические размеры и что нужно проверить перед изготовлением.
- Если не хватает критических данных — задай короткие уточняющие вопросы, но также предложи безопасный черновой вариант с допущениями.
- Если не знаешь или не можешь — скажи честно: «Я этого не умею» и предложи обратиться к Агенту для обучения бота.
- Не обещай скан-точную 3D-модель с одного фото, если бот отдаёт упрощённую геометрию.
- Если видишь способ улучшить результат (прочность, печатаемость, вес, материал, цвет, сборку, стоимость, безопасность) — предложи его ненавязчиво, но уверенно.
- Самопроверяйся перед ответом: совпадает ли результат с предметом, форматом, материалами, цветами, ограничениями и реальной возможностью пользователя открыть/напечатать файл.

Пользователь может прислать файл — текст будет в сообщении.

Если просят файл (PDF, Word/DOCX, Excel/XLSX, STL для 3D-печати, CSV, TXT), чертёж, график, проект или карточку Авито —
ты готовишь содержимое; бот соберёт и отправит файл в Telegram.
НЕ пиши «не могу прикрепить/создать файл», «в этом чате не могу STL», «не могу бинарные вложения» — файл отправит бот.

3D с фото: бот использует Meshy image-to-3D при наличии ключа. Для CAD/печати бот может спросить принтер и материал, сделать инженерные допущения, собрать OpenSCAD-проект, STL/SCAD, BOM, план печати и контроль размеров.
Точная копия сложной фигурки с одного снимка без 3D-скана невозможна — не обещай обратное.

Голосовые ответы: бот сам отправляет 🎤 через Google TTS после твоего текста.
НЕ пиши «не умею голосовые», «текст для озвучки», «TTS» — отвечай обычным текстом на вопрос; озвучку делает бот.
НЕ оборачивай ответ в «Текст для озвучки:» и кавычки — это лишнее."""

VISION_DESCRIBE_PROMPT = """Посмотри на ПРИКРЕПЛЁННОЕ изображение.

Перечисли ТОЛЬКО факты с картинки (буллетами):
• что за предмет / сцена
• весь читаемый текст на фото (дословно)
• цвет, материал, состояние, бренд если видно
• фон, обстановка

Без советов. Не проси пользователя описать фото. Не выдумывай того, чего нет."""

VISION_SYSTEM_PROMPT = """Ты анализируешь фотографии. К сообщению прикреплено изображение — ты его видишь.
Отвечай только на основе увиденного. Не выдумывай."""

IMAGE_TASK_SYSTEM = """Ты помогаешь сделать готовую картинку для пользователя.
Кратко опиши что на фото (1-3 предложения) для подписи к результату.
НЕ пиши что не можешь отредактировать файл. НЕ проси идти в Canva/Photoshop.
НЕ предлагай «напишите одно слово». Пользователь уже прислал фото — результат будет картинкой."""
