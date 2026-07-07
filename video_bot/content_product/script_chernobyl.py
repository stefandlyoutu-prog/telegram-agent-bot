"""Репортаж: Чернобыльская АЭС — факты + Wikimedia."""

from __future__ import annotations

from video_bot.content_product.models import Scene, VideoScript


def chernobyl_report_script() -> VideoScript:
    """Документальный сценарий. media_tag → Wikimedia Commons."""
    return VideoScript(
        topic="Чернобыльская АЭС — репортаж",
        cta="wikimedia commons / исторические архивы",
        meta={"source": "documentary", "media": "wikimedia", "topic_key": "chernobyl", "style": "documentary", "music_profile": "mystical"},
        scenes=[
            Scene(
                "hook",
                ["26 АПРЕЛЯ 1986", "ЧЕРНОБЫЛЬ"],
                "1986",
                "Двадцать шестого апреля тысяча девятьсот восемьдесят шестого. Ночью на четвёртом блоке Чернобыльской станции началась авария.",
                "hook aes",
                cut_sec=2.5,
            ),
            Scene(
                "problem",
                ["ВЗРЫВ", "НА 4-М БЛОКЕ"],
                "ВЗРЫВ",
                "Взрыв и пожар разрушили реактор. В небо ушло радиоактивное облако.",
                "reactor block4 explosion",
                cut_sec=2.4,
            ),
            Scene(
                "agitate",
                ["ГОРОД ПРИПЯТЬ", "116 ТЫСЯЧ ЛЮДЕЙ"],
                "ПРИПЯТЬ",
                "Рядом жил город Припять — сто шестнадцать тысяч человек. Их эвакуировали за сутки.",
                "pripyat city evacuation",
                cut_sec=2.6,
            ),
            Scene(
                "solution",
                ["ЛИКВИДАТОРЫ", "ШЛИ НА СТАНЦИЮ"],
                "ЛИКВИДАТОРЫ",
                "Тысячи людей тушили реактор. Многие получили большую дозу радиации.",
                "liquidators memorial reactor",
                cut_sec=2.5,
            ),
            Scene(
                "proof",
                ["РАДИАЦИЯ", "НА ТЫСЯЧИ ЛЕТ"],
                "РАДИАЦИЯ",
                "Зона отчуждения стала одним из самых заражённых мест на планете.",
                "radiation sign zone",
                cut_sec=2.4,
            ),
            Scene(
                "proof",
                ["КРАСНЫЙ ЛЕС", "МЁРТВЫЕ ДЕРЕВЬЯ"],
                "ЛЕС",
                "Красный лес погиб от радиации. Сегодня там всё ещё опасно.",
                "red forest radiation video",
                cut_sec=2.6,
            ),
            Scene(
                "offer",
                ["САРКОФАГ", "НАД РЕАКТОРОМ"],
                "САРКОФАГ",
                "Над четвёртым блоком построили саркофаг, а позже — новое укрытие.",
                "sarcophagus confinement",
                cut_sec=2.5,
            ),
            Scene(
                "proof",
                ["ПРИПЯТЬ СЕГОДНЯ", "ГОРОД-ПРИЗРАК"],
                "ПРИЗРАК",
                "Припять пустует. Колесо обозрения стоит, как в тот день.",
                "pripyat abandoned",
                cut_sec=2.5,
            ),
            Scene(
                "urgency",
                ["УРОК", "ДЛЯ ВСЕГО МИРА"],
                "УРОК",
                "Чернобыль напомнил: безопасность атомной энергии важнее всего.",
                "aes plant today",
                cut_sec=2.3,
            ),
            Scene(
                "cta",
                ["ПОМНИ", "ИСТОРИЮ"],
                "ПОМНИ",
                "Помни историю. Передавай факты дальше.",
                "memorial",
                cut_sec=2.2,
            ),
        ],
    )
