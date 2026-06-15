#!/usr/bin/env python3
"""Образцы чертежей шпалеры — 4 стиля на выбор."""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path("/Users/polzovatel/Downloads/chertezhi-vybor")
OUT.mkdir(parents=True, exist_ok=True)

# мм
W, H = 600, 2000
RUNGS = [100, 300, 550, 800, 950]
DEPTH = 60


def _style_ax(ax):
    ax.set_aspect("equal")
    ax.axis("off")


def sample_a_three_panels():
    """A: три отдельных вида — без наложения."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 6))
    fig.suptitle("A. Три отдельных вида (понятнее всего)", fontsize=14, fontweight="bold")

    # Спереди
    ax = axes[0]
    _style_ax(ax)
    ax.set_title("Спереди", fontsize=12, fontweight="bold")
    ax.plot([0, 0, W, W, 0], [0, H, H, 0, 0], "b-", lw=3)
    ax.plot([0, W], [0, 0], "brown", lw=4)
    for y in RUNGS:
        ax.plot([0, W], [y, y], "g-", lw=2)
        ax.text(-80, y, f"{y}", va="center", fontsize=9)
    ax.annotate("", xy=(W, -120), xytext=(0, -120), arrowprops=dict(arrowstyle="<->", lw=1.5))
    ax.text(W / 2, -160, f"{W} мм", ha="center", fontsize=11, fontweight="bold")
    ax.annotate("", xy=(W + 80, 0), xytext=(W + 80, H), arrowprops=dict(arrowstyle="<->", lw=1.5))
    ax.text(W + 120, H / 2, f"{H} мм", va="center", fontsize=11, fontweight="bold")
    ax.set_xlim(-150, W + 200)
    ax.set_ylim(-220, H + 80)

    # Сбоку
    ax = axes[1]
    _style_ax(ax)
    ax.set_title("Сбоку", fontsize=12, fontweight="bold")
    ax.plot([0, DEPTH, DEPTH, 0, 0], [0, 0, H, H, 0], "b-", lw=3)
    for y in RUNGS:
        ax.plot([0, DEPTH], [y, y], "g-", lw=2)
    ax.annotate("", xy=(0, -100), xytext=(DEPTH, -100), arrowprops=dict(arrowstyle="<->", lw=1.5))
    ax.text(DEPTH / 2, -140, f"{DEPTH} мм глубина", ha="center", fontsize=11, fontweight="bold")
    ax.set_xlim(-40, DEPTH + 60)
    ax.set_ylim(-180, H + 40)

    # Сверху
    ax = axes[2]
    _style_ax(ax)
    ax.set_title("Сверху", fontsize=12, fontweight="bold")
    rect = mpatches.Rectangle((0, 0), W, DEPTH, fill=False, edgecolor="purple", lw=3)
    ax.add_patch(rect)
    ax.plot([0, W], [DEPTH / 2, DEPTH / 2], "b--", lw=1)
    ax.annotate("", xy=(0, -40), xytext=(W, -40), arrowprops=dict(arrowstyle="<->", lw=1.5))
    ax.text(W / 2, -70, f"{W} мм", ha="center", fontsize=11, fontweight="bold")
    ax.set_xlim(-60, W + 60)
    ax.set_ylim(-100, DEPTH + 60)

    fig.tight_layout()
    fig.savefig(OUT / "A-tri-vida.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def sample_b_isometric():
    """B: одна изометрия — как выглядит готовое."""
    fig, ax = plt.subplots(figsize=(10, 8))
    _style_ax(ax)
    ax.set_title("B. Одна 3D-схема (изометрия)", fontsize=14, fontweight="bold", pad=20)

    def iso(x, y, z):
        return x - 0.5 * z, y + 0.35 * z

    zd = DEPTH
    pts_front = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
    pts_back = [(p[0], p[1], zd) for p in [(0, 0), (W, 0), (W, H), (0, H)]]
    pts_back.append(pts_back[0])

    for p in pts_front:
        ax.plot(*iso(p[0], p[1], 0), "b-", lw=2.5)
    for i, p in enumerate(pts_back[:-1]):
        x, y = iso(*p)
        x0, y0 = iso(pts_front[i][0], pts_front[i][1], 0)
        ax.plot([x0, x], [y0, y], "b-", lw=1.5, alpha=0.7)
    for p in pts_back:
        ax.plot(*iso(p[0], p[1], p[2] if len(p) > 2 else zd), "b-", lw=2)

    for rh in RUNGS:
        ax.plot([iso(0, rh, 0)[0], iso(W, rh, 0)[0]], [iso(0, rh, 0)[1], iso(W, rh, 0)[1]], "g-", lw=2)
        ax.plot([iso(W, rh, 0)[0], iso(W, rh, zd)[0]], [iso(W, rh, 0)[1], iso(W, rh, zd)[1]], "g-", lw=1, alpha=0.6)

    ax.text(iso(W / 2, -150, 0)[0], iso(W / 2, -150, 0)[1], f"ширина {W} мм", ha="center", fontsize=11)
    ax.text(iso(-120, H / 2, 0)[0], iso(-120, H / 2, 0)[1], f"высота\n{H} мм", ha="center", fontsize=11)
    ax.text(iso(W + 40, 40, zd / 2)[0], iso(W + 40, 40, zd / 2)[1], f"глубина\n{DEPTH} мм", fontsize=10)

    ax.set_xlim(-400, 900)
    ax.set_ylim(-300, 1400)
    fig.savefig(OUT / "B-izometriya.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def sample_c_ikea():
    """C: схема IKEA — номера деталей."""
    fig, ax = plt.subplots(figsize=(10, 9))
    _style_ax(ax)
    ax.set_title("C. Схема «как IKEA» — номера в кружках", fontsize=14, fontweight="bold", pad=16)

    ax.plot([0, 0, W, W], [0, H, H, 0], "k-", lw=2)
    for y in RUNGS:
        ax.plot([0, W], [y, y], "k-", lw=1.5)

    labels = [
        (W + 40, H / 2, "① 2× стойка\n200 см"),
        (W / 2, -80, "② 5× перекладина\n60 см"),
        (W / 2, H + 50, "③ 4× угол 90°\n④ 6× кронштейн"),
        (-60, 50, "⑤ 2× опора"),
    ]
    for x, y, t in labels:
        ax.text(x, y, t, fontsize=11, va="center", ha="center",
                bbox=dict(boxstyle="round", facecolor="#fff3cd", edgecolor="#856404"))

    for i, y in enumerate(RUNGS[:2]):
        ax.add_patch(plt.Circle((0, y), 28, fill=True, color="#e74c3c", zorder=5))
        ax.text(0, y, str(3), ha="center", va="center", color="white", fontweight="bold", fontsize=12)

    ax.set_xlim(-200, W + 200)
    ax.set_ylim(-150, H + 120)

    table = (
        "Таблица в инструкции:\n"
        "① СТ-В — 2 шт × 2000 мм\n"
        "② ПР-Г — 5 шт × 600 мм\n"
        "③ Угол 90° — 4 шт\n"
        "④ Кронштейн — 6 шт\n"
        "⑤ Опора — 2 шт"
    )
    ax.text(0.02, 0.02, table, transform=ax.transAxes, fontsize=10,
            verticalalignment="bottom", family="monospace",
            bbox=dict(facecolor="white", alpha=0.9, edgecolor="gray"))

    fig.savefig(OUT / "C-ikea-nomera.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def sample_d_front_only():
    """D: только спереди — крупно."""
    fig, ax = plt.subplots(figsize=(8, 12))
    _style_ax(ax)
    ax.set_title("D. Только вид спереди — крупно", fontsize=14, fontweight="bold")

    ax.plot([0, 0], [0, H], color="#1f4e9a", lw=6, solid_capstyle="round")
    ax.plot([W, W], [0, H], color="#1f4e9a", lw=6, solid_capstyle="round")
    ax.axhline(0, color="#8B4513", lw=5, label="земля")
    colors = {100: "#e74c3c", 950: "#e74c3c", 300: "#f39c12", 550: "#f39c12", 800: "#f39c12"}
    for y in RUNGS:
        ax.plot([0, W], [y, y], color=colors.get(y, "#27ae60"), lw=4)

    ax.annotate("стойка 200 см", xy=(0, H * 0.5), xytext=(-200, H * 0.5),
                arrowprops=dict(arrowstyle="->", lw=1.5), fontsize=12, fontweight="bold")
    ax.annotate("перекладина 60 см", xy=(W / 2, 550), xytext=(W / 2, 1200),
                arrowprops=dict(arrowstyle="->", lw=1.5), fontsize=12, ha="center", fontweight="bold")
    ax.annotate("", xy=(0, -80), xytext=(W, -80), arrowprops=dict(arrowstyle="<->", lw=2))
    ax.text(W / 2, -130, "600 мм между стойками", ha="center", fontsize=14, fontweight="bold")
    ax.annotate("", xy=(W + 60, 0), xytext=(W + 60, H), arrowprops=dict(arrowstyle="<->", lw=2))
    ax.text(W + 100, H / 2, "2000 мм\nвысота", va="center", fontsize=14, fontweight="bold")

    legend = [
        Line2D([0], [0], color="#e74c3c", lw=4, label="Угол 90° (низ и верх)"),
        Line2D([0], [0], color="#f39c12", lw=4, label="Кронштейн (середина)"),
        Line2D([0], [0], color="#1f4e9a", lw=4, label="Стойка"),
    ]
    ax.legend(handles=legend, loc="upper right", fontsize=11)
    ax.set_xlim(-280, W + 180)
    ax.set_ylim(-180, H + 80)
    fig.savefig(OUT / "D-tolko-speredi.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def sample_e_table_photo():
    """E: без чертежа — таблица (макет страницы)."""
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.axis("off")
    ax.set_title("E. Без чертежа — таблица + ваше фото", fontsize=14, fontweight="bold")

    rows = [
        ["Деталь", "Кол-во", "Длина"],
        ["Стойка СТ-В", "2", "200 см"],
        ["Перекладина ПР-Г", "5", "60 см"],
        ["Угол 90°", "4", "—"],
        ["Кронштейн", "6", "—"],
        ["Опора", "2", "—"],
    ]
    table = ax.table(cellText=rows, loc="center", cellLoc="center")
    table.scale(1.2, 2.2)
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_facecolor("#1f4e9a")
            cell.set_text_props(color="white", fontweight="bold")
        else:
            cell.set_facecolor("#f8f9fa" if row % 2 else "white")

    ax.text(0.5, 0.08,
            "Вместо чертежа — 3–5 фото:\n"
            "собранная шпалера на грядке, комплект в коробке, узел крупным планом",
            transform=ax.transAxes, ha="center", fontsize=11,
            bbox=dict(boxstyle="round", facecolor="#d4edda", edgecolor="#28a745"))
    fig.savefig(OUT / "E-tablica-foto.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    sample_a_three_panels()
    sample_b_isometric()
    sample_c_ikea()
    sample_d_front_only()
    sample_e_table_photo()
    print(f"OK: {OUT}")
    for p in sorted(OUT.glob("*.png")):
        print(f"  {p.name}")
