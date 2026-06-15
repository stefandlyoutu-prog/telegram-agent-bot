"""Чертёж-эскиз Г-коннектора 20×20×2 (концепт v1)."""
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, Rectangle, Circle, Arc
import numpy as np

OUT = Path("/Users/polzovatel/Downloads/g-connector-20x20-concept-v1.png")


def draw():
    fig = plt.figure(figsize=(16, 10), facecolor="white")
    fig.suptitle(
        "Г-коннектор 20×20×2 · концепт v1\n"
        "внутренние вставки + M5 + наружные направляющие сверления",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )

    # --- Plan view (top) ---
    ax1 = fig.add_axes([0.04, 0.52, 0.42, 0.42])
    ax1.set_title("Вид сверху (план)", fontsize=11, fontweight="bold")
    ax1.set_aspect("equal")
    ax1.axis("off")

    # Tubes (outer 20)
    ax1.add_patch(Rectangle((-5, -5), 20, 20, fill=False, lw=2, ec="#555"))
    ax1.add_patch(Rectangle((-5, -5), 20, 20, fill=True, fc="#e8e8e8", alpha=0.4))
    ax1.add_patch(Rectangle((-1, -1), 12, 12, fill=False, lw=1, ec="#888", ls="--"))
    ax1.add_patch(Rectangle((-5, 15), 20, 80, fill=False, lw=2, ec="#555"))
    ax1.add_patch(Rectangle((-5, 15), 20, 80, fill=True, fc="#e8e8e8", alpha=0.4))
    ax1.add_patch(Rectangle((-1, 19), 12, 72, fill=False, lw=1, ec="#888", ls="--"))

    # Connector plugs (inner 15.7)
    ax1.add_patch(Rectangle((0.15, 0.15), 15.7, 15.7, fill=True, fc="#1f77b4", alpha=0.55, ec="#0d47a1", lw=1.5))
    ax1.add_patch(Rectangle((0.15, 15.15), 15.7, 25, fill=True, fc="#1f77b4", alpha=0.55, ec="#0d47a1", lw=1.5))

    # Corner core
    ax1.add_patch(Rectangle((0.15, 0.15), 15.7, 15.7, fill=False, ec="#c62828", lw=2.5))

    # Drill bosses (top view as circles on tube walls)
    ax1.add_patch(Circle((10, 0), 5, fill=False, ec="#e65100", lw=2))
    ax1.add_patch(Circle((0, 27), 5, fill=False, ec="#e65100", lw=2))
    ax1.plot(10, 0, "o", color="#e65100", ms=4)
    ax1.plot(0, 27, "o", color="#e65100", ms=4)

    # Bolt axes
    ax1.annotate("", xy=(10, -8), xytext=(10, 8), arrowprops=dict(arrowstyle="<->", color="#c62828", lw=1.5))
    ax1.annotate("", xy=(-8, 27), xytext=(8, 27), arrowprops=dict(arrowstyle="<->", color="#c62828", lw=1.5))
    ax1.text(12, 4, "M5\nось Y", fontsize=8, color="#c62828")
    ax1.text(2, 32, "M5\nось X", fontsize=8, color="#c62828")

    ax1.text(10, -12, "Труба 20×20 (вид сверху)", ha="center", fontsize=9)
    ax1.text(35, 55, "← горизонт.\n    профиль", fontsize=8, color="#333")
    ax1.text(-18, 8, "верт.\nпрофиль", fontsize=8, color="#333", rotation=90, va="center")
    ax1.set_xlim(-22, 95)
    ax1.set_ylim(-18, 98)

    # --- Front view arm 1 ---
    ax2 = fig.add_axes([0.52, 0.52, 0.22, 0.42])
    ax2.set_title("Разрез A-A (гориз. плечо)", fontsize=11, fontweight="bold")
    ax2.set_aspect("equal")
    ax2.axis("off")

    # Tube wall section
    ax2.add_patch(Rectangle((0, 0), 20, 20, fill=True, fc="#ddd", ec="#444", lw=1.5))
    ax2.add_patch(Rectangle((2, 2), 16, 16, fill=True, fc="white", ec="#888", lw=1))
    # Plug inside
    ax2.add_patch(Rectangle((2.15, 2.15), 15.7, 25, fill=True, fc="#1f77b4", alpha=0.6, ec="#0d47a1"))
    # Drill boss on bottom wall
    ax2.add_patch(Rectangle((6, -3), 8, 3, fill=True, fc="#ff9800", ec="#e65100", lw=1.2))
    ax2.add_patch(Circle((10, 10), 2.75, fill=False, ec="#c62828", lw=2))
    ax2.plot([10, 10], [-3, 27], color="#c62828", lw=1.5, ls="--")
    ax2.text(22, 12, "стенка\n2 мм", fontsize=8)
    ax2.text(22, 3, "босс\nØ10", fontsize=8, color="#e65100")
    ax2.text(1, 28, "L=25 мм вставка", fontsize=8)
    ax2.annotate("", xy=(18, 2.15), xytext=(18, 27.15), arrowprops=dict(arrowstyle="<->", color="#333"))
    ax2.set_xlim(-2, 35)
    ax2.set_ylim(-8, 35)

    # --- Isometric sketch (schematic) ---
    ax3 = fig.add_axes([0.76, 0.52, 0.22, 0.42])
    ax3.set_title("Изометрия (схема)", fontsize=11, fontweight="bold")
    ax3.axis("off")
    ax3.set_xlim(0, 10)
    ax3.set_ylim(0, 10)
    # simple iso lines
    pts_h = np.array([[1, 3], [5, 5], [5, 8], [1, 6], [1, 3]])
    pts_v = np.array([[5, 5], [8, 3.5], [8, 6.5], [5, 8], [5, 5]])
    ax3.plot(pts_h[:, 0], pts_h[:, 1], "k-", lw=2)
    ax3.fill(pts_h[:, 0], pts_h[:, 1], color="#e8e8e8", alpha=0.5)
    ax3.plot(pts_v[:, 0], pts_v[:, 1], "k-", lw=2)
    ax3.fill(pts_v[:, 0], pts_v[:, 1], color="#e8e8e8", alpha=0.5)
    ax3.fill([2, 4.5, 4.5, 2], [3.8, 4.8, 6.8, 5.8], color="#1f77b4", alpha=0.7)
    ax3.fill([4.5, 6.8, 6.8, 4.5], [4.8, 3.5, 5.5, 6.8], color="#1f77b4", alpha=0.7)
    ax3.plot([3.2, 3.2], [4.2, 7.5], color="#ff9800", lw=3)
    ax3.plot([5.8, 7.2], [4.2, 3.2], color="#ff9800", lw=3)
    ax3.text(0.5, 0.5, "синий — вставка\nоранж — босс сверления", fontsize=8)

    # --- Spec table ---
    ax4 = fig.add_axes([0.04, 0.04, 0.58, 0.42])
    ax4.axis("off")
    rows = [
        ["Параметр", "Значение", "Примечание"],
        ["Профиль", "20×20×2", "внутр. полость 16×16 мм"],
        ["Вставка (плечо)", "15,7×15,7 × L=25", "зазор 0,15 мм/сторона (PETG)"],
        ["Угол", "90°", "Г-образный, плоскость XY"],
        ["Болт", "M5×20 + шайба", "2 шт., ось ⊥ оси трубы"],
        ["Отверстие", "Ø5,5 мм", "сквозь обе стенки + вставку"],
        ["Босс направляющий", "Ø10 × h3", "ось совпадает с болтом"],
        ["Узел (core)", "20×20×20", "усиление + ребро 45°"],
        ["Материал печати", "PETG / PETG-CF", "100% в зоне вставки"],
        ["Роль узла", "позиционирование", "нагрузка — в основном по профилю"],
    ]
    tbl = ax4.table(cellText=rows, loc="center", cellLoc="left", colWidths=[0.28, 0.22, 0.5])
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 1.6)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#1f4e9a")
            cell.set_text_props(color="white", fontweight="bold")
        elif r % 2 == 0:
            cell.set_facecolor("#f5f5f5")

    # --- Load summary ---
    ax5 = fig.add_axes([0.66, 0.04, 0.32, 0.42])
    ax5.axis("off")
    txt = (
        "Расчёт нагрузок (кратко)\n"
        "─────────────────────\n"
        "Сценарий: шпалера 0,6×2 м,\n"
        "ветер 25 м/с, F≈80–120 Н\n"
        "Случайная: F=500 Н на узел\n\n"
        "M5 (8.8) срез: ~3,5 кН/болт\n"
        "2×M5: >> 500 Н ✓\n\n"
        "PETG на смятие под шайбой:\n"
        "σ_allow≈25 MPa → N≈490 Н/см²\n"
        "шайба Ø16 → ~500 Н (ручная\n"
        "затяжка достаточна для дачи)\n\n"
        "Основной путь силы:\n"
        "1) осевая компрессия профиля\n"
        "2) трение от зажима болтом\n"
        "3) резерв — срез болта + core"
    )
    ax5.text(
        0.05, 0.95, txt, transform=ax5.transAxes, va="top", fontsize=9,
        family="monospace",
        bbox=dict(boxstyle="round", facecolor="#fff8e1", edgecolor="#ffc107"),
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(OUT)


if __name__ == "__main__":
    draw()
