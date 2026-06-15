"""Визуал сборки в стиле Napkin — одна картинка, все шаги."""

from __future__ import annotations

from pathlib import Path

from bot.services.dacha_shed_v3_stable import DEFAULT_SHED_V3


def render_napkin_assembly(path: Path, spec=DEFAULT_SHED_V3) -> Path:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Circle, Wedge
    from bot.services.dacha_shed_blueprints import draw_isometric_shed

    bg = "#faf8f5"
    accent = "#2563eb"
    warn = "#f59e0b"
    text = "#1e293b"
    muted = "#64748b"

    fig = plt.figure(figsize=(14, 22), facecolor=bg)
    fig.suptitle(
        "Хозблок 3×3 м — сборка за 10 шагов",
        fontsize=22, fontweight="bold", color=text, y=0.985,
    )
    fig.text(
        0.5, 0.965,
        "Опора на блок ≠ обвязка. Стойка соединяет их.",
        ha="center", fontsize=13, color=accent, fontweight="bold",
    )

    grid = fig.add_gridspec(6, 2, hspace=0.55, wspace=0.25,
                             left=0.06, right=0.94, top=0.94, bottom=0.03)

    steps = [
        ("1", "Проверка", "44×150 · 6×200 · 2×100 см\n+ пластик и болты", None),
        ("2", "6 опор", "Блок → опора (оранж.) → анкер M8\nДержит СТОЙКУ", dict(show_foundation=True, show_foot_pads=True, show_plan_dims=False)),
        ("3", "Обвязка низ", "Квадрат 3×3 на ЗЕМЛЕ\nуголок для стойки на углах", dict(show_foundation=True, show_foot_pads=True, show_bottom_frame=True, show_plan_dims=False)),
        ("4", "6 стоек", "Низ → опора\nта же палка → обвязка", dict(show_foundation=True, show_foot_pads=True, show_bottom_frame=True, show_posts=True, highlight_posts=True, show_plan_dims=False)),
        ("5", "Раскосы", "X на каждой стене\n8 шт.", dict(show_foundation=True, show_bottom_frame=True, show_posts=True, show_braces=True, show_plan_dims=False)),
        ("6", "Обвязка верх", "Перед 200 см · зад 150 см", dict(show_foundation=True, show_bottom_frame=True, show_posts=True, show_braces=True, show_top_frame=True, show_plan_dims=False)),
        ("7", "Дверь", "100×200 см · 50–150 см", dict(show_foundation=True, show_bottom_frame=True, show_posts=True, show_top_frame=True, show_door=True, show_plan_dims=False)),
        ("8–9", "Крыша", "Стропила + обрешётка", dict(show_foundation=True, show_bottom_frame=True, show_posts=True, show_top_frame=True, show_roof=True, show_purlins=True, show_plan_dims=False)),
        ("10", "Профлист", "Стены → крыша", dict(show_foundation=True, show_bottom_frame=True, show_posts=True, show_top_frame=True, show_roof=True, show_purlins=True, show_plan_dims=False)),
    ]

    for i, (num, title, desc, flags) in enumerate(steps):
        row, col = divmod(i, 2)
        if i >= 8:
            break
        ax = fig.add_subplot(grid[row, col])
        ax.set_facecolor("white")
        ax.axis("off")
        # карточка
        card = FancyBboxPatch(
            (0.02, 0.02), 0.96, 0.96,
            boxstyle="round,pad=0.02,rounding_size=0.04",
            facecolor="white", edgecolor="#e2e8f0", linewidth=2,
            transform=ax.transAxes, zorder=0,
        )
        ax.add_patch(card)
        # номер
        ax.add_patch(Circle((0.12, 0.88), 0.07, transform=ax.transAxes,
                            facecolor=accent, edgecolor="none", zorder=2))
        ax.text(0.12, 0.88, num, transform=ax.transAxes, ha="center", va="center",
                fontsize=14, fontweight="bold", color="white", zorder=3)
        ax.text(0.24, 0.88, title, transform=ax.transAxes, ha="left", va="center",
                fontsize=13, fontweight="bold", color=text, zorder=3)
        ax.text(0.5, 0.12, desc, transform=ax.transAxes, ha="center", va="bottom",
                fontsize=9, color=muted, zorder=3, linespacing=1.35)

        if flags:
            mini = ax.inset_axes([0.08, 0.22, 0.84, 0.58])
            mini.set_facecolor("#f8fafc")
            mini.axis("off")
            draw_isometric_shed(mini, spec, **flags)
        elif num == "1":
            ax.text(0.5, 0.5, "КОМПЛЕКТ\n\nРазложить\nи посчитать",
                    transform=ax.transAxes, ha="center", va="center",
                    fontsize=16, color=muted)

    # большой блок «главное» — вид сбоку
    ax_big = fig.add_subplot(grid[4:, :])
    ax_big.set_facecolor("#fffbeb")
    ax_big.axis("off")
    ax_big.add_patch(FancyBboxPatch(
        (0.01, 0.02), 0.98, 0.96, boxstyle="round,pad=0.01,rounding_size=0.02",
        facecolor="#fffbeb", edgecolor=warn, linewidth=3, transform=ax_big.transAxes,
    ))
    ax_big.text(0.5, 0.92, "ГЛАВНОЕ: как соединяются опора и обвязка (вид сбоку у угла)",
                transform=ax_big.transAxes, ha="center", fontsize=15, fontweight="bold", color=warn)

    # схема слева
    sx = 0.08
    ax_big.plot([sx, sx], [0.15, 0.78], color="#c4a574", lw=14, solid_capstyle="butt",
                transform=ax_big.transAxes)
    ax_big.text(sx, 0.82, "стойка\n200 см", transform=ax_big.transAxes, ha="center",
                fontsize=11, fontweight="bold", color="#8b6914")
    ax_big.plot([sx - 0.06, sx + 0.18], [0.42, 0.42], color="#6d4c2a", lw=10,
                solid_capstyle="butt", transform=ax_big.transAxes)
    ax_big.text(sx + 0.22, 0.42, "← нижняя обвязка\n   (на земле)", transform=ax_big.transAxes,
                va="center", fontsize=11, fontweight="bold", color="#6d4c2a")
    ax_big.add_patch(Rectangle((sx - 0.04, 0.08), 0.08, 0.12, transform=ax_big.transAxes,
                               facecolor="#ff9800", edgecolor="#e65100", lw=2))
    ax_big.add_patch(Rectangle((sx - 0.05, 0.02), 0.1, 0.08, transform=ax_big.transAxes,
                               facecolor="#bdbdbd", edgecolor="#616161", lw=2))
    ax_big.text(sx, 0.05, "блок", transform=ax_big.transAxes, ha="center", fontsize=8)
    ax_big.text(sx, 0.14, "опора", transform=ax_big.transAxes, ha="center", fontsize=8, color="#e65100")
    ax_big.fill_between([0, 0.35], [0, 0], [0.02, 0.02], color="#8d6e63", transform=ax_big.transAxes)
    ax_big.text(0.17, 0.01, "земля", transform=ax_big.transAxes, ha="center", fontsize=9, color="#5d4037")

    # стрелки и пояснения справа
    bullets = [
        "1. Опора на блок — только под стойку (фундамент).",
        "2. Обвязка — горизонтальный квадрат на земле, в опору НЕ вставляется.",
        "3. Одна стойка: низ в опору, та же палка через уголок на обвязке.",
        "4. Сначала блоки + опоры → обвязка на земле → стойки.",
    ]
    for j, line in enumerate(bullets):
        ax_big.text(0.42, 0.72 - j * 0.14, f"• {line}", transform=ax_big.transAxes,
                    fontsize=12, color=text, va="top")

    ax_big.annotate("", xy=(0.22, 0.55), xytext=(0.22, 0.35),
                    xycoords="axes fraction", textcoords="axes fraction",
                    arrowprops=dict(arrowstyle="->", color=accent, lw=2.5))
    ax_big.text(0.24, 0.45, "одна\nпалка", transform=ax_big.transAxes, fontsize=10,
                color=accent, fontweight="bold")

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    return path


if __name__ == "__main__":
    out = Path("/Users/polzovatel/Downloads/dacha-shed-v4-stable/instrukcii/sborka-napkin.png")
    p = render_napkin_assembly(out)
    print(p, p.stat().st_size // 1024, "KB")
