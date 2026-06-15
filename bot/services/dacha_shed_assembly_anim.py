"""GIF-анимация пошаговой сборки сарая 3×3."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from bot.services.dacha_shed_v3_stable import ShedV3StableSpec

FrameSpec = Tuple[str, Dict[str, Any], int]  # caption, draw_flags, duration_ms


def _assembly_frames() -> List[FrameSpec]:
    """Кадры анимации: подпись, флаги отрисовки, длительность."""
    off = dict(
        show_foundation=False,
        show_foot_pads=False,
        show_bottom_frame=False,
        show_posts=False,
        show_top_frame=False,
        show_roof=False,
        show_braces=False,
        show_purlins=False,
        show_door=False,
        show_plan_dims=False,
    )
    base = dict(show_foundation=True, show_plan_dims=True)

    return [
        ("Шаг 1. Разложите детали на земле\n(палки 200 / 150 / 100 см, пластик, болты)", off, 2500),
        ("Шаг 2. Бетонные блоки в углах\nи посередине передней и задней стороны", {**off, **base}, 2800),
        (
            "Шаг 2. Оранжевая «Опора на блок»\n"
            "→ держит СТОЙКУ, не обвязку!\n"
            "Анкер M8 в блок",
            {**off, **base, "show_foot_pads": True},
            3500,
        ),
        (
            "Шаг 3. Нижняя обвязка — квадрат 3×3 м\n"
            "лежит НА ЗЕМЛЕ (коричневые палки)\n"
            "В опору НЕ вставляется",
            {
                **off,
                **base,
                "show_foot_pads": True,
                "show_bottom_frame": True,
            },
            4000,
        ),
        ("ПОЯСНЕНИЕ · вид сбоку у угла", {"_corner_view": True}, 5000),
        (
            "Шаг 3+4. Совместите: обвязка вокруг блоков\n"
            "Углы рамы — над блоками",
            {**off, **base, "show_foot_pads": True, "show_bottom_frame": True},
            3500,
        ),
        (
            "Шаг 4. Стойки 200 см (оранжевые)\n"
            "Низ → в опору на блок\n"
            "Та же палка → через уголок на обвязке",
            {
                **off,
                **base,
                "show_foot_pads": True,
                "show_bottom_frame": True,
                "show_posts": True,
                "highlight_posts": True,
            },
            4500,
        ),
        (
            "Шаг 5. Раскосы — крест на каждой стене\n"
            "без них каркас шатается",
            {
                **off,
                **base,
                "show_foot_pads": True,
                "show_bottom_frame": True,
                "show_posts": True,
                "show_braces": True,
            },
            3000,
        ),
        (
            "Шаг 6. Верхняя обвязка\n"
            "перед выше, зад ниже — уклон крыши",
            {
                **off,
                **base,
                "show_foot_pads": True,
                "show_bottom_frame": True,
                "show_posts": True,
                "show_braces": True,
                "show_top_frame": True,
            },
            3000,
        ),
        (
            "Шаг 7. Дверной проём на фасаде",
            {
                **off,
                **base,
                "show_foot_pads": True,
                "show_bottom_frame": True,
                "show_posts": True,
                "show_braces": True,
                "show_top_frame": True,
                "show_door": True,
            },
            2500,
        ),
        (
            "Шаг 8. Стропила + шаг 9. обрешётка",
            {
                **off,
                **base,
                "show_foot_pads": True,
                "show_bottom_frame": True,
                "show_posts": True,
                "show_braces": True,
                "show_top_frame": True,
                "show_door": True,
                "show_roof": True,
                "show_purlins": True,
            },
            3500,
        ),
        (
            "Шаг 10. Профлист на стены и крышу\n"
            "Готово!",
            {
                **off,
                **base,
                "show_foot_pads": True,
                "show_bottom_frame": True,
                "show_posts": True,
                "show_braces": True,
                "show_top_frame": True,
                "show_door": True,
                "show_roof": True,
                "show_purlins": True,
            },
            4000,
        ),
    ]


def _draw_corner_explainer(ax) -> None:
    """2D-схема: как стойка соединяет опору и обвязку."""
    from matplotlib.patches import Rectangle

    ax.set_facecolor("#f5f5f5")
    ax.set_xlim(-0.5, 4.5)
    ax.set_ylim(-0.5, 5.5)
    ax.axis("off")

    # земля
    ax.fill([-0.2, 4.2, 4.2, -0.2], [-0.05, -0.05, 0, 0], color="#8d6e63")
    ax.text(2.0, -0.35, "ЗЕМЛЯ", ha="center", fontsize=11, color="#5d4037")

    # блок
    ax.add_patch(Rectangle(
        (0.6, 0), 1.2, 0.35, facecolor="#bdbdbd", edgecolor="#616161", lw=2,
    ))
    ax.text(1.2, 0.17, "блок", ha="center", va="center", fontsize=9)

    # опора
    ax.add_patch(Rectangle(
        (0.85, 0.35), 0.7, 0.25, facecolor="#ff9800", edgecolor="#e65100", lw=2,
    ))
    ax.annotate("Опора на блок\n(стойка вставляется\nСЮДА снизу)", xy=(1.2, 0.47), xytext=(2.8, 0.9),
                fontsize=10, color="#e65100", fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#e65100", lw=1.5))

    # обвязка горизонталь
    ax.plot([0, 3.5], [0.75, 0.75], color="#6d4c2a", lw=8, solid_capstyle="butt")
    ax.plot([0, 0], [0.75, 2.5], color="#6d4c2a", lw=8, solid_capstyle="butt")
    ax.annotate("Нижняя обвязка\n(на земле, горизонтально)", xy=(1.8, 0.75), xytext=(2.5, 1.5),
                fontsize=10, color="#6d4c2a", fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#6d4c2a", lw=1.5))

    # стойка
    ax.plot([0, 0], [0.35, 4.5], color="#c4a574", lw=12, solid_capstyle="butt")
    ax.annotate("Стойка 200 см\nодна палка!", xy=(0, 2.5), xytext=(-0.45, 3.2),
                fontsize=10, color="#8b6914", fontweight="bold", ha="right",
                arrowprops=dict(arrowstyle="->", color="#8b6914", lw=1.5))

    ax.text(2.0, 5.1, "Обвязка НЕ вставляется в опору.\n"
            "Стойка соединяет их: низ в опору, середина через уголок на обвязке.",
            ha="center", fontsize=11, fontweight="bold",
            bbox=dict(boxstyle="round", facecolor="white", edgecolor="#333"))


def _render_frame_pil(spec: "ShedV3StableSpec", caption: str, flags: Dict[str, Any]):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from PIL import Image, ImageDraw

    from bot.services.dacha_shed_blueprints import draw_isometric_shed

    fig, ax = plt.subplots(figsize=(10, 7.2))
    ax.axis("off")
    fig.patch.set_facecolor("#ececec")

    if flags.pop("_corner_view", False):
        ax.set_facecolor("#f5f5f5")
        fig.patch.set_facecolor("#f5f5f5")
        _draw_corner_explainer(ax)
    else:
        ax.set_facecolor("#ececec")
        draw_isometric_shed(ax, spec, **flags)

    fig.text(
        0.5, 0.97, caption,
        ha="center", va="top", fontsize=11, fontweight="bold",
        bbox=dict(boxstyle="round", facecolor="#fffde7", edgecolor="#f9a825", pad=0.6),
    )

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def build_assembly_gif(spec: "ShedV3StableSpec", path: Path) -> Path:
    """Собрать GIF пошаговой сборки."""
    from PIL import Image

    frames_data = _assembly_frames()
    images: List[Image.Image] = []
    durations: List[int] = []

    for caption, flags, duration in frames_data:
        flags_copy = dict(flags)
        img = _render_frame_pil(spec, caption, flags_copy)
        images.append(img)
        durations.append(duration)

    path.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        path,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    return path
