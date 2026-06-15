"""Честные границы возможностей бота и обращение к Агенту."""

from bot.config import AGENT_CONTACT_HINT


def agent_learn_hint(topic: str = "") -> str:
    extra = f" ({topic})" if topic else ""
    return (
        f"\n\n🤖 Я этого пока не умею{extra}. "
        f"{AGENT_CONTACT_HINT}"
    )


def stl_quality_disclaimer(
    *,
    from_photo: bool,
    meshy: bool = False,
    text_to_3d: bool = False,
    meshy_hint: str = "",
) -> str:
    extra = f"\n· {meshy_hint}" if meshy_hint else ""
    if meshy and text_to_3d:
        return (
            "🧊 STL для Bambu (Meshy → remesh → repair).\n"
            "Готово в мм, модель на столе."
            + extra
        )
    if meshy:
        return (
            "🧊 STL (Meshy image-to-3D).\n"
            "Проверьте масштаб в слайсере перед печатью."
            + extra
        )
    if from_photo:
        return (
            "🧊 STL по фото (параметрическая модель с замерами).\n"
            "Это не 3D-скан: форма упрощена, размеры — по оценке с одного ракурса.\n"
            "Для максимальной точности пришлите 4–8 фото с разных сторон "
            "или укажите точный размер в мм в подписи."
        )
    return "🧊 STL для 3D-печати (параметрическая модель)."
