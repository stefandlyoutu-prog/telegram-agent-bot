import asyncio
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from aiohttp import ClientError, ClientConnectorError

from bot.config import (
    IMAGE_TASK_SYSTEM,
    KUPI_CIRCUIT_SEC,
    LLM_API_KEY,
    LLM_CHAT_URL,
    LLM_CONNECT_TIMEOUT_SEC,
    LLM_PRIMARY,
    LLM_PROXY,
    SYSTEM_PROMPT,
    VISION_DESCRIBE_PROMPT,
    VISION_MODEL,
    VISION_SYSTEM_PROMPT,
)

REFUSAL_PATTERN = re.compile(
    r"не могу.{0,40}(видеть|просматривать|анализировать|увидеть|изображен)|"
    r"опишите.{0,40}(фото|картин|изображен|что изображ)|"
    r"расскажите.{0,40}(предмет|фото|картин|что)|"
    r"недоразумени|"
    r"please describe|can't see|cannot see|don't have.{0,30}image|"
    r"unable to view|не вижу никакого изображения|"
    r"не могу просматривать",
    re.IGNORECASE,
)

OCR_FALLBACK_SYSTEM = """Ты анализируешь фотографии по расшифровке OCR (текст с картинки).

ВАЖНО:
- Тебе УЖЕ передали данные с фото (текст OCR, размер файла).
- ЗАПРЕЩЕНО писать, что ты «не можете видеть/анализировать изображения».
- ЗАПРЕЩЕНО просить пользователя описать фото словами — работай с OCR.
- Если OCR пуст — честно скажи, что надписей не распознано; предложи отправить фото как «Файл» без сжатия.
- Для объявления Авито: используй только факты из OCR и подписи пользователя."""


VISION_TIMEOUT_SEC = 75
OCR_TIMEOUT_SEC = 12


class LLMError(Exception):
    pass


_last_provider = "kupi"
_kupi_down_until = 0.0


def last_llm_provider() -> str:
    return _last_provider


def kupi_circuit_open() -> bool:
    return time.time() < _kupi_down_until


def mark_kupi_down() -> None:
    global _kupi_down_until
    _kupi_down_until = time.time() + max(KUPI_CIRCUIT_SEC, 30)


def _set_provider(name: str) -> None:
    global _last_provider
    _last_provider = name


def _prefer_gemini_first() -> bool:
    from bot.services.gemini_llm import gemini_llm_configured

    if not gemini_llm_configured():
        return False
    if LLM_PRIMARY == "gemini":
        return True
    if LLM_PRIMARY == "kupi":
        return False
    return kupi_circuit_open() or not LLM_API_KEY


def _should_try_gemini_fallback(exc: Exception) -> bool:
    from bot.services.gemini_llm import gemini_llm_configured

    if not gemini_llm_configured():
        return False
    if isinstance(exc, (asyncio.TimeoutError, ClientConnectorError, ClientError)):
        return True
    msg = str(exc).lower()
    if any(x in msg for x in ("401", "403", "неверный ключ", "invalid api key", "authentication")):
        return False
    if isinstance(exc, LLMError):
        if any(
            token in msg
            for token in (
                "таймаут",
                "нет связи",
                "ошибка сети",
                "502",
                "503",
                "504",
                "429",
                "500",
                "524",
                "connect",
                "timeout",
            )
        ):
            return True
        return True
    return False


async def _gemini_chat_fallback(
    messages: List[Dict[str, Any]],
    *,
    system: str,
    temperature: float,
    timeout_sec: int,
    kupi_error: Exception,
) -> str:
    from bot.services.gemini_llm import gemini_chat_completion

    try:
        text = await gemini_chat_completion(
            messages,
            system=system,
            temperature=temperature,
            timeout_sec=timeout_sec,
        )
        _set_provider("gemini")
        return text
    except Exception as ge:
        raise LLMError(
            f"KupiAPI недоступен ({kupi_error}); запасной Gemini тоже не ответил: {ge}"
        ) from ge


async def _gemini_chat_primary(
    messages: List[Dict[str, Any]],
    *,
    system: str,
    temperature: float,
    timeout_sec: int = 120,
) -> str:
    from bot.services.gemini_llm import gemini_chat_completion

    text = await gemini_chat_completion(
        messages,
        system=system,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )
    _set_provider("gemini")
    return text


def _client_timeout(total: int) -> aiohttp.ClientTimeout:
    connect = min(LLM_CONNECT_TIMEOUT_SEC, total)
    return aiohttp.ClientTimeout(
        total=total,
        connect=connect,
        sock_connect=connect,
    )


def _network_error_message(exc: Exception) -> str:
    return (
        "Нет связи с KupiAPI (kupiapi.ru).\n"
        "• Проверьте интернет или включите VPN\n"
        "• Если VPN локальный — добавьте в .env:\n"
        "  LLM_PROXY=socks5://127.0.0.1:10808\n"
        f"• Детали: {exc}"
    )


async def _post_json(payload: dict, *, timeout_sec: int = 180) -> dict:
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    from bot.services.http_client import (
        format_client_error,
        llm_connection_modes,
        proxy_for_request,
        session_kwargs,
    )

    last_err: Optional[Exception] = None
    modes = list(llm_connection_modes())

    for use_proxy in modes:
        label = "прокси" if use_proxy else "напрямую"
        try:
            async with aiohttp.ClientSession(**session_kwargs(use_proxy)) as session:
                async with session.post(
                    LLM_CHAT_URL,
                    json=payload,
                    headers=headers,
                    timeout=_client_timeout(timeout_sec),
                    proxy=proxy_for_request(use_proxy),
                ) as resp:
                    try:
                        data = await resp.json()
                    except Exception:
                        body = await resp.text()
                        raise LLMError(f"API ({resp.status}): {body[:200]}")
                    if resp.status != 200:
                        err = data.get("error", {})
                        msg = (
                            err.get("message", str(data))
                            if isinstance(err, dict)
                            else str(data)
                        )
                        raise LLMError(f"API ({resp.status}): {msg}")
                    return data
        except LLMError:
            raise
        except asyncio.TimeoutError as e:
            last_err = e
            if use_proxy == modes[-1]:
                raise LLMError(
                    f"Таймаут KupiAPI ({timeout_sec} сек). Проверьте интернет."
                ) from e
        except ClientConnectorError as e:
            last_err = e
            if use_proxy == modes[-1]:
                raise LLMError(_network_error_message(e)) from e
        except ClientError as e:
            last_err = e
            if use_proxy == modes[-1]:
                raise LLMError(
                    f"Ошибка сети KupiAPI ({label}): {format_client_error(e)}"
                ) from e

    if last_err:
        raise LLMError(_network_error_message(last_err))
    raise LLMError("Не удалось подключиться к KupiAPI")


async def _request(payload: dict, *, timeout_sec: int = 180) -> str:
    messages = [
        m for m in payload.get("messages", []) if m.get("role") != "system"
    ]
    system = next(
        (
            m.get("content", "")
            for m in payload.get("messages", [])
            if m.get("role") == "system"
        ),
        "",
    )
    system = system if isinstance(system, str) else ""
    temperature = float(payload.get("temperature", 0.7))

    try:
        data = await _post_json(payload, timeout_sec=timeout_sec)
    except LLMError as e:
        mark_kupi_down()
        if _should_try_gemini_fallback(e):
            return await _gemini_chat_fallback(
                messages,
                system=system,
                temperature=temperature,
                timeout_sec=timeout_sec,
                kupi_error=e,
            )
        raise
    choices = data.get("choices") or []
    if not choices:
        mark_kupi_down()
        empty_err = LLMError("Пустой ответ от KupiAPI")
        if _should_try_gemini_fallback(empty_err):
            return await _gemini_chat_fallback(
                messages,
                system=system,
                temperature=temperature,
                timeout_sec=timeout_sec,
                kupi_error=empty_err,
            )
        raise empty_err

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        mark_kupi_down()
        empty_err = LLMError("KupiAPI вернул пустой текст")
        if _should_try_gemini_fallback(empty_err):
            return await _gemini_chat_fallback(
                messages,
                system=system,
                temperature=temperature,
                timeout_sec=timeout_sec,
                kupi_error=empty_err,
            )
        raise empty_err
    _set_provider("kupi")
    return content.strip()


async def _vision_completion_inner(
    user_text: str,
    image_data_url: str,
    *,
    system: str,
    temperature: float,
    timeout_sec: int,
) -> str:
    if not LLM_API_KEY:
        from bot.services.gemini_llm import gemini_llm_configured, gemini_vision_completion

        if gemini_llm_configured():
            return await gemini_vision_completion(
                user_text,
                image_data_url,
                system=system,
                temperature=temperature,
                timeout_sec=timeout_sec,
            )
        raise LLMError("Не задан LLM_API_KEY")

    payload = {
        "model": _normalize_model(VISION_MODEL),
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
        "temperature": temperature,
    }
    try:
        data = await _post_json(payload, timeout_sec=timeout_sec)
    except LLMError as e:
        if _should_try_gemini_fallback(e):
            from bot.services.gemini_llm import gemini_vision_completion

            try:
                return await gemini_vision_completion(
                    user_text,
                    image_data_url,
                    system=system,
                    temperature=temperature,
                    timeout_sec=timeout_sec,
                )
            except Exception as ge:
                raise LLMError(
                    f"KupiAPI vision недоступен ({e}); Gemini vision: {ge}"
                ) from ge
        raise

    choices = data.get("choices") or []
    if not choices:
        raise LLMError("Пустой ответ от модели")

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise LLMError("Модель вернула пустой текст")
    return content.strip()


async def chat_completion(
    messages: List[Dict[str, Any]],
    model: str,
    *,
    system: str = SYSTEM_PROMPT,
    temperature: float = 0.7,
) -> str:
    if _prefer_gemini_first():
        try:
            return await _gemini_chat_primary(
                messages,
                system=system,
                temperature=temperature,
            )
        except Exception as ge:
            if LLM_PRIMARY == "gemini" or not LLM_API_KEY:
                raise LLMError(f"Gemini: {ge}") from ge

    if not LLM_API_KEY:
        from bot.services.gemini_llm import gemini_llm_configured

        if gemini_llm_configured():
            return await _gemini_chat_primary(
                messages,
                system=system,
                temperature=temperature,
            )
        raise LLMError("Не задан LLM_API_KEY")

    payload = {
        "model": _normalize_model(model),
        "messages": [{"role": "system", "content": system}, *messages],
        "temperature": temperature,
    }
    return await _request(payload)


def _normalize_model(model: str) -> str:
    aliases = {
        "gpt-4o-mini": "gpt-5.4-mini",
        "gpt-4o": "gpt-5.4",
        "claude-haiku": "claude-haiku-4.5",
        "claude-sonnet": "claude-sonnet-4.6",
        "claude-opus": "claude-opus-4.7",
    }
    return aliases.get(model, model)


def looks_like_vision_refusal(text: str) -> bool:
    return bool(REFUSAL_PATTERN.search(text))


async def vision_completion(
    user_text: str,
    image_data_url: str,
    *,
    system: str = VISION_SYSTEM_PROMPT,
    temperature: float = 0.5,
    timeout_sec: int = VISION_TIMEOUT_SEC,
) -> str:
    try:
        return await asyncio.wait_for(
            _vision_completion_inner(
                user_text,
                image_data_url,
                system=system,
                temperature=temperature,
                timeout_sec=timeout_sec,
            ),
            timeout=timeout_sec + 5,
        )
    except asyncio.TimeoutError as e:
        raise LLMError(f"Таймаут vision API ({timeout_sec} сек)") from e


async def describe_image_facts(
    image_data: bytes,
    width: int,
    height: int,
) -> Tuple[str, str]:
    """Быстрое описание фото для генерации карточки (без OCR)."""
    from bot.services.vision import detect_mime, to_data_url

    data_url = to_data_url(image_data, detect_mime(image_data))
    size_kb = len(image_data) // 1024
    vision_facts: Optional[str] = None
    vision_error: Optional[str] = None

    try:
        vision_facts = await vision_completion(
            VISION_DESCRIBE_PROMPT,
            data_url,
            system=VISION_SYSTEM_PROMPT,
            temperature=0.3,
            timeout_sec=12,
        )
    except LLMError as e:
        vision_error = str(e)

    facts_parts = [
        f"Метод: vision ({VISION_MODEL}).",
        f"Размер: {width}×{height} px, {size_kb} KB.",
    ]
    if vision_facts and not looks_like_vision_refusal(vision_facts):
        facts_parts.append(f"Описание с фото:\n{vision_facts}")
    elif vision_error:
        facts_parts.append(f"Vision: {vision_error}")
        facts_parts.append(
            "Карточка будет собрана по подписи к фото и локальному макету."
        )
    else:
        facts_parts.append("Vision: без описания — используем подпись пользователя.")

    return "\n\n".join(facts_parts), "vision"


async def _ocr_fallback_answer(
    image_data: bytes,
    width: int,
    height: int,
    user_request: str,
    text_model: str,
) -> Tuple[str, str, str]:
    from bot.services.ocr import extract_text_from_image

    try:
        ocr_text, ocr_conf, engine = await extract_text_from_image(image_data)
    except Exception as e:
        raise LLMError(f"Не удалось распознать текст на фото: {e}") from e

    size_kb = len(image_data) // 1024
    facts_parts = [
        "Метод: OCR (vision API недоступен или отказал).",
        f"Размер: {width}×{height} px, {size_kb} KB.",
        f"OCR ({engine}), уверенность ~{ocr_conf:.0%}.",
    ]

    if ocr_text.strip():
        facts_parts.append(f"Текст на изображении:\n{ocr_text}")
    else:
        facts_parts.append(
            "Текст на изображении: не распознан (пустой OCR). "
            "Отправьте фото как «Файл» без сжатия или добавьте подпись."
        )

    facts = "\n\n".join(facts_parts)
    prompt = (
        f"Данные с фотографии:\n{facts}\n\n"
        f"---\nЗапрос пользователя:\n{user_request}\n\n"
        "Выполни запрос по OCR. Не проси описать фото словами."
    )

    answer = await chat_completion(
        [{"role": "user", "content": prompt}],
        text_model,
        system=OCR_FALLBACK_SYSTEM,
        temperature=0.5,
    )

    if looks_like_vision_refusal(answer):
        answer = await chat_completion(
            [
                {
                    "role": "user",
                    "content": (
                        f"OCR с фото:\n{ocr_text or '(пусто)'}\n\n"
                        f"Запрос: {user_request}\n\n"
                        "Ответь по OCR. Одно предложение: текст с фото уже распознан выше."
                    ),
                }
            ],
            text_model,
            system=OCR_FALLBACK_SYSTEM,
            temperature=0.3,
        )

    if looks_like_vision_refusal(answer):
        raise LLMError(
            "Модель отказалась анализировать фото. Попробуйте /model → GPT-5.4 mini "
            "и /reset. Либо добавьте подпись к фото: что изображено."
        )

    return facts, answer, f"ocr/{engine}"


async def analyze_image_bytes(
    image_data: bytes,
    width: int,
    height: int,
    user_request: str,
    text_model: str,
) -> Tuple[str, str, str]:
    """
    Анализ фото: vision API (картинка в запросе) + OCR как дополнение.
    При отказе vision — fallback на OCR + текстовая модель.
    Возвращает (facts, answer, method).
    """
    from bot.services.ocr import extract_text_from_image
    from bot.services.vision import detect_mime, to_data_url

    data_url = to_data_url(image_data, detect_mime(image_data))
    size_kb = len(image_data) // 1024

    ocr_task = asyncio.create_task(extract_text_from_image(image_data))
    vision_facts: Optional[str] = None
    vision_error: Optional[str] = None

    try:
        vision_facts = await vision_completion(
            VISION_DESCRIBE_PROMPT,
            data_url,
            system=VISION_SYSTEM_PROMPT,
            temperature=0.3,
        )
    except LLMError as e:
        vision_error = str(e)

    try:
        ocr_text, ocr_conf, ocr_engine = await asyncio.wait_for(
            ocr_task, timeout=OCR_TIMEOUT_SEC
        )
    except asyncio.TimeoutError:
        ocr_task.cancel()
        ocr_text, ocr_conf, ocr_engine = "", 0.0, "timeout"
    except Exception as e:
        ocr_text, ocr_conf, ocr_engine = "", 0.0, f"skip ({e})"

    facts_parts = [
        f"Метод: vision API ({VISION_MODEL}).",
        f"Размер: {width}×{height} px, {size_kb} KB.",
    ]
    if vision_facts and not looks_like_vision_refusal(vision_facts):
        facts_parts.append(f"Описание с фото:\n{vision_facts}")
    elif vision_error:
        facts_parts.append(f"Vision: ошибка — {vision_error}")
    else:
        facts_parts.append("Vision: модель не описала изображение.")

    if ocr_text.strip():
        facts_parts.append(f"OCR ({ocr_engine}, ~{ocr_conf:.0%}):\n{ocr_text}")

    facts = "\n\n".join(facts_parts)
    method = "vision"
    if ocr_text.strip():
        method = f"vision+{ocr_engine}"

    vision_ok = vision_facts and not looks_like_vision_refusal(vision_facts)
    if not vision_ok:
        return await _ocr_fallback_answer(
            image_data, width, height, user_request, text_model
        )

    answer_prompt = (
        f"Факты с фотографии:\n{facts}\n\n"
        f"---\nЗапрос пользователя:\n{user_request}\n\n"
        "Выполни запрос по тому, что видно на изображении и в фактах выше. "
        "Не проси пользователя описать фото словами."
    )

    try:
        answer = await vision_completion(
            answer_prompt,
            data_url,
            system=VISION_SYSTEM_PROMPT,
            temperature=0.5,
        )
    except LLMError:
        return await _ocr_fallback_answer(
            image_data, width, height, user_request, text_model
        )

    if looks_like_vision_refusal(answer):
        return await _ocr_fallback_answer(
            image_data, width, height, user_request, text_model
        )

    return facts, answer, method


async def generate_avito_card_copy(
    user_request: str,
    vision_facts: str,
    text_model: str,
) -> "CardCopy":
    """Продающий текст карточки через текстовую модель KupiAPI."""
    import json
    from bot.services.avito_card import CardCopy, _parse_card_copy_fallback

    prompt = (
        f"Запрос пользователя: {user_request}\n\n"
        f"Факты с фото:\n{vision_facts[:2000]}\n\n"
        "Составь продающий текст для карточки товара на Авито.\n"
        "Верни ТОЛЬКО JSON без markdown:\n"
        '{"title":"...","subtitle":"...","bullets":["...","...","..."],"badge":"..."}\n'
        "title — до 50 символов, subtitle — до 70, bullets — 2-3 коротких плюса, "
        'badge — короткий бейдж или пустая строка. Только факты с фото, не выдумывай бренд.'
    )
    try:
        raw = await chat_completion(
            [{"role": "user", "content": prompt}],
            text_model,
            system="Ты копирайтер для объявлений Авито. Отвечай только JSON.",
            temperature=0.5,
        )
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            bullets = data.get("bullets") or []
            if isinstance(bullets, str):
                bullets = [bullets]
            return CardCopy(
                title=str(data.get("title", "Товар"))[:52],
                subtitle=str(data.get("subtitle", ""))[:72],
                bullets=[str(b)[:45] for b in bullets[:3]],
                badge=str(data.get("badge", ""))[:24],
            )
    except Exception:
        pass
    return _parse_card_copy_fallback(user_request, vision_facts)


async def generate_seo_listing_text(
    user_request: str,
    vision_facts: str,
    text_model: str,
    card_method: str = "",
) -> str:
    prompt = (
        f"Запрос: {user_request}\n\n"
        f"Факты о товаре:\n{vision_facts[:2500]}\n\n"
        "Напиши SEO-текст для объявления на Авито на русском.\n"
        "Структура (заголовки ##):\n"
        "## Заголовок объявления\n"
        "## Описание\n"
        "## Преимущества\n"
        "## Характеристики\n"
        "## Для кого\n"
        "Только факты с фото, без выдуманного бренда. Готово для PDF."
    )
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        text_model,
        system="Ты копирайтер Avito. Пиши продающий SEO-текст, без отказов про файлы.",
        temperature=0.5,
    )


async def generate_document_markdown(
    user_request: str,
    context: str,
    text_model: str,
) -> str:
    prompt = (
        f"Запрос пользователя:\n{user_request}\n\n"
        f"Контекст:\n{context[:3500]}\n\n"
        "Подготовь текст документа на русском с заголовками ##.\n"
        "Структура понятная, без отказов про файлы."
    )
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        text_model,
        system="Ты готовишь текст для Word/PDF. Не пиши что не можешь создать файл.",
        temperature=0.5,
    )


async def generate_xlsx_json(
    user_request: str,
    context: str,
    text_model: str,
) -> str:
    prompt = (
        f"Запрос:\n{user_request}\n\nКонтекст:\n{context[:3000]}\n\n"
        "Верни ТОЛЬКО JSON для Excel (без markdown):\n"
        '{"sheets":[{"name":"Лист1","headers":["Колонка1","Колонка2"],'
        '"rows":[["значение1","значение2"]]}]}\n'
        "До 5 листов, до 50 строк. Только факты из запроса. "
        "Если пользователь просит график/диаграмму — добавь отдельный лист chart_data "
        "с колонками для построения графика и краткими расчётными формулами в ячейках как текст."
    )
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        text_model,
        system="Ты готовишь данные для Excel. Ответ — только JSON.",
        temperature=0.4,
    )


async def measure_object_from_photo(
    image_data: bytes,
    width: int,
    height: int,
    user_request: str,
    print_profile: dict,
) -> str:
    """Оценка габаритов предмета на фото (мм) для STL."""
    from bot.services.print_profile import format_profile
    from bot.services.vision import detect_mime, to_data_url

    data_url = to_data_url(image_data, detect_mime(image_data))
    prof = format_profile(print_profile)
    prompt = (
        f"Запрос пользователя: {user_request}\n"
        f"Профиль печати:\n{prof}\n\n"
        "Оцени предмет на фото для 3D-печати. Верни ТОЛЬКО JSON:\n"
        '{"object_name":"...","parts":[{"name":"...","shape_hint":"box|cylinder|sphere|organic",'
        '"width_mm":N,"depth_mm":N,"height_mm":N,"radius_mm":N,"notes":"посадка/печать"}],'
        '"overall_height_mm":N,"confidence":"low|medium|high",'
        '"assumptions":["что предположил"]}\n'
        "Размеры в мм. Если в запросе указана высота — используй её. "
        "Разбей сложный предмет на 3–12 печатаемых деталей.\n"
        "У каждой детали разные габариты (минимум 20% отличия) и разный shape_hint "
        "(cylinder/box/sphere), не копируй одинаковые прямоугольники."
    )
    raw = await vision_completion(
        prompt,
        data_url,
        system=(
            "Ты инженер 3D-печати и метролог. Ответ — только JSON. "
            "Не отказывайся; если не уверен — confidence: low и явные assumptions."
        ),
        temperature=0.25,
        timeout_sec=25,
    )
    return raw


async def generate_stl_batch_specs(
    user_request: str,
    context: str,
    text_model: str,
    *,
    count: int = 1,
    print_profile: Optional[dict] = None,
    photo_measurements: Optional[str] = None,
) -> str:
    from bot.services.print_profile import format_profile

    prof = format_profile(print_profile or {})
    meas = (photo_measurements or "")[:3000]
    prompt = (
        f"Запрос:\n{user_request}\n\nКонтекст:\n{context[:2000]}\n\n"
        f"Профиль печати:\n{prof}\n\n"
        f"Замеры с фото (JSON):\n{meas}\n\n"
        f"Нужно ровно {count} STL-деталей (или столько, сколько в замерах, но не больше {count}).\n"
        "Верни ТОЛЬКО JSON:\n"
        '{"files":[{"name":"part-01","description":"назначение + ориентация в слайсере",'
        '"shape":"cylinder|box|sphere",'
        '"width_mm":N,"depth_mm":N,"height_mm":N,"radius_mm":N,"segments":36,'
        '"tolerance_mm":0.2}]}\n'
        "Размеры в мм, согласованы с замерами. Детали должны стыковаться (пазы/нахлёст в описании). "
        "Учти материал и сопло. Без отказов.\n"
        "ЗАПРЕЩЕНО: одинаковые box 40×40×40 для всех files — у каждой детали свой shape "
        "и размеры (cylinder/box/sphere чередуй)."
    )
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        text_model,
        system=(
            "Ты инженер 3D-печати (FDM). Ответ — только JSON files. "
            "Не пиши что не можешь создать файл."
        ),
        temperature=0.35,
    )


async def generate_stl_spec(
    user_request: str,
    context: str,
    text_model: str,
) -> str:
    prompt = (
        f"Запрос:\n{user_request}\n\nКонтекст:\n{context[:2500]}\n\n"
        "Нужна простая 3D-модель для печати (STL). Верни ОДИН вариант:\n"
        "1) JSON: "
        '{"shape":"box|cylinder|sphere","width_mm":N,"depth_mm":N,"height_mm":N,'
        '"radius_mm":N,"segments":32}\n'
        "2) или полный ASCII STL в блоке ```stl ... ```\n"
        "Размеры в мм, реалистичные для запроса.\n"
        "ЗАПРЕЩЕНО отказывать — только параметры или STL."
    )
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        text_model,
        system=(
            "Ты инженер 3D-печати. Ответ — JSON или ASCII STL. "
            "Никогда не пиши что не можешь прикрепить или создать файл."
        ),
        temperature=0.4,
    )


def _default_card_caption(user_request: str, facts: str) -> str:
    text = f"{user_request}\n{facts}".lower()
    if "ксеноморф" in text or "alien" in text or "чужой" in text:
        return "Фигурка ксеноморфа Alien\n3D-печать\nКоллекционная фигурка"
    first = user_request.strip().splitlines()[0][:80] if user_request.strip() else ""
    if first and "сделай" not in first.lower()[:8]:
        return first
    return "Готовая карточка для Авито по вашему фото."


async def process_image_request(
    image_data: bytes,
    width: int,
    height: int,
    user_request: str,
    text_model: str,
    *,
    produce_image: bool = False,
    with_text: bool = True,
) -> Tuple[str, str, str, Optional[bytes], Optional[str]]:
    """
    Обработка фото.
    Возвращает (facts, answer_text, method, image_bytes|None, image_mime|None).
    """
    from bot.services.image_output import (
        looks_like_text_only_refusal,
        produce_image as make_image,
        wants_image_output,
    )
    from bot.services.vision import detect_mime, to_data_url

    need_image = produce_image or wants_image_output(user_request)
    no_text = bool(re.search(r"без\s+текст", user_request, re.I))

    if need_image:
        facts, _ = await describe_image_facts(image_data, width, height)
        try:
            out_bytes, mime, img_method = await make_image(
                image_data,
                user_request,
                facts,
                with_text=with_text and not no_text,
            )
        except Exception as e:
            raise LLMError(f"Не удалось сделать картинку: {e}") from e

        caption = _default_card_caption(user_request, facts)
        data_url = to_data_url(image_data, detect_mime(image_data))
        caption_prompt = (
            f"Факты с фото:\n{facts[:1200]}\n\n"
            f"Запрос: {user_request}\n\n"
            "Дай короткую подпись к готовой карточке (2-4 строки), без отказов и без инструкций."
        )
        try:
            caption = await vision_completion(
                caption_prompt,
                data_url,
                system=IMAGE_TASK_SYSTEM,
                temperature=0.4,
                timeout_sec=25,
            )
            if looks_like_text_only_refusal(caption):
                caption = _default_card_caption(user_request, facts)
        except LLMError:
            pass

        return facts, caption, img_method, out_bytes, mime

    facts, answer, method = await analyze_image_bytes(
        image_data, width, height, user_request, text_model
    )
    if looks_like_text_only_refusal(answer):
        from bot.services.image_output import render_local_avito_card

        out_bytes, mime = render_local_avito_card(
            image_data, user_request, facts, with_text=True
        )
        return (
            facts,
            "Модель ответила текстом вместо картинки — отправляю локальный макет.",
            "local/card-fallback",
            out_bytes,
            mime,
        )
    return facts, answer, method, None, None
