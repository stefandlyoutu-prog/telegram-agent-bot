"""Правила озвучки без LLM: ударения, без имён ботов."""

from __future__ import annotations

import re

_BOT_PATTERNS = re.compile(
    r"@?\s*M[_\s-]?onetest[_\s-]?bot|"
    r"эм[\s-]?онетест|"
    r"M_onetest|"
    r"MoRoZov|"
    r"t\.me/\S+",
    re.I,
)

_WORD_FIX: list[tuple[str, str]] = [
    (r"\bВи\s*Ка\b", "ВКонтакте"),
    (r"\bВК\b", "ВКонтакте"),
    (r"\bТик\s*Ток\b", "ТикТок"),
    (r"\bЮ\s*Туб\b", "Ютуб"),
    (r"\bYouTube\b", "Ютуб"),
    (r"\bрефералка\b", "бонус за друзей"),
    (r"\bлиды\b", "заявки"),
    (r"\bпартнёрки\b", "партнёрские программы"),
    (r"\bАвито\b", "Авито"),
    (r"[«»„""]", ""),
]

_PHRASE_FIX: list[tuple[str, str]] = [
    (r"доход\s+в\s+сети", "заработать в интернете"),
    (r"телеграм[\s-]?боте", "Телеграме"),
    (r"телеграм[\s-]?бот", "бот в Телеграме"),
    (r"центр\s+твоего\s+дохода", "центр твоего заработка"),
    (r"Чернобыльской\s+станции", "атомной электростанции"),
    (r"заражённых", "опасных"),
    (r"отчуждения", "запретной зоны"),
    (r"эвакуировали", "вывезли"),
    (r"ликвидаторы", "спасатели"),
    (r"саркофаг", "защитный купол"),
    (r"радиоактивное", "опасное"),
    (r"\bАЭС\b", "атомная станция"),
    (r"Припять", "Припяти"),
]


def normalize_voice_text(text: str) -> str:
    t = _BOT_PATTERNS.sub("", text)
    t = re.sub(r"https?://\S+", "", t)
    t = t.replace("@", "").replace("_", " ")
    for pat, repl in _WORD_FIX:
        t = re.sub(pat, repl, t, flags=re.I)
    for pat, repl in _PHRASE_FIX:
        t = re.sub(pat, repl, t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" .,")
    t = re.sub(r"\s{2,}", " ", t)
    return t
