"""Чертежи наборов 20×20 — 5 форматов A–E (PNG для PDF)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D


@dataclass(frozen=True)
class FrameSpec:
    id: str
    title: str
    width_mm: float  # спереди — ширина
    height_mm: float
    depth_mm: float
    rung_heights_mm: Tuple[float, ...]  # пусто = грядка без перекладин
    parts_table: Tuple[Tuple[str, str, str], ...]


SPECS = {
    "shpalera": FrameSpec(
        id="shpalera",
        title="Шпалера «Томат-2»",
        width_mm=600,
        height_mm=2000,
        depth_mm=60,
        rung_heights_mm=(100, 300, 550, 800, 950),
        parts_table=(
            ("Стойка СТ-В", "2", "200 см"),
            ("Перекладина ПР-Г", "5", "60 см"),
            ("Угол 90°", "4", "—"),
            ("Кронштейн", "6", "—"),
            ("Опора", "2", "—"),
        ),
    ),
    "gryadka": FrameSpec(
        id="gryadka",
        title="Грядка 200×100×25 см",
        width_mm=2000,
        height_mm=250,
        depth_mm=1000,
        rung_heights_mm=(),
        parts_table=(
            ("Длинная ДЛ-2М", "2", "200 см"),
            ("Короткая КР-1М", "2", "100 см"),
            ("Стойка СТ-25", "4", "25 см"),
            ("Угол corner_post", "4", "—"),
            ("Кронштейн", "4", "—"),
        ),
    ),
    "drovnica": FrameSpec(
        id="drovnica",
        title="Дровница 120×100 см",
        width_mm=1200,
        height_mm=1000,
        depth_mm=400,
        rung_heights_mm=(100, 300, 550, 800, 950),
        parts_table=(
            ("Стойка СТ-В", "2", "100 см"),
            ("Полка ПР-Г", "5", "120 см"),
            ("Угол 90°", "4", "—"),
            ("Кронштейн", "6", "—"),
            ("Опора", "2", "—"),
        ),
    ),
    "stoyka": FrameSpec(
        id="stoyka",
        title="Стойка инвентаря 180 см",
        width_mm=800,
        height_mm=1800,
        depth_mm=300,
        rung_heights_mm=(200, 600, 1000, 1400, 1700),
        parts_table=(
            ("Стойка СТ-В", "2", "180 см"),
            ("Перекладина", "4", "80 см"),
            ("Угол 90°", "4", "—"),
            ("Кронштейн", "4", "—"),
            ("Опора", "2", "—"),
            ("Крюк", "4", "—"),
        ),
    ),
}


def _style_ax(ax):
    ax.set_aspect("equal")
    ax.axis("off")


def _corner_rungs(spec: FrameSpec) -> set:
    if not spec.rung_heights_mm:
        return set()
    return {spec.rung_heights_mm[0], spec.rung_heights_mm[-1]}


def render_a(spec: FrameSpec, path: Path) -> None:
    W, H, D = spec.width_mm, spec.height_mm, spec.depth_mm
    corners = _corner_rungs(spec)
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.5))
    fig.suptitle(f"A — Три отдельных вида · {spec.title}", fontsize=13, fontweight="bold")

    ax = axes[0]
    _style_ax(ax)
    ax.set_title("Спереди", fontweight="bold")
    if spec.rung_heights_mm:
        ax.plot([0, 0, W, W], [0, H, H, 0], "b-", lw=3)
        for y in spec.rung_heights_mm:
            ax.plot([0, W], [y, y], "g-", lw=2)
            ax.text(-max(60, W * 0.05), y, f"{int(y)}", va="center", fontsize=8)
    else:
        ax.add_patch(mpatches.Rectangle((0, 0), W, H, fill=False, edgecolor="b", lw=3))
    ax.axhline(0, color="#8B4513", lw=3)
    ax.annotate("", xy=(W, -H * 0.06), xytext=(0, -H * 0.06), arrowprops=dict(arrowstyle="<->", lw=1.2))
    ax.text(W / 2, -H * 0.1, f"{int(W)} мм", ha="center", fontweight="bold")
    ax.annotate("", xy=(W * 1.05, 0), xytext=(W * 1.05, H), arrowprops=dict(arrowstyle="<->", lw=1.2))
    ax.text(W * 1.08, H / 2, f"{int(H)} мм", va="center", fontweight="bold")
    ax.set_xlim(-W * 0.15, W * 1.2)
    ax.set_ylim(-H * 0.15, H * 1.05)

    ax = axes[1]
    _style_ax(ax)
    ax.set_title("Сбоку", fontweight="bold")
    ax.add_patch(mpatches.Rectangle((0, 0), D, H, fill=False, edgecolor="#2a9d8f", lw=3))
    if spec.rung_heights_mm:
        for y in spec.rung_heights_mm:
            ax.plot([0, D], [y, y], "g-", lw=1.5, alpha=0.7)
    ax.annotate("", xy=(0, -H * 0.08), xytext=(D, -H * 0.08), arrowprops=dict(arrowstyle="<->", lw=1.2))
    ax.text(D / 2, -H * 0.12, f"{int(D)} мм", ha="center", fontweight="bold")
    ax.set_xlim(-D * 0.1, D * 1.15)
    ax.set_ylim(-H * 0.15, H * 1.05)

    ax = axes[2]
    _style_ax(ax)
    ax.set_title("Сверху", fontweight="bold")
    ax.add_patch(mpatches.Rectangle((0, 0), W, D, fill=False, edgecolor="#7b2cbf", lw=3))
    ax.annotate("", xy=(0, -D * 0.15), xytext=(W, -D * 0.15), arrowprops=dict(arrowstyle="<->", lw=1.2))
    ax.text(W / 2, -D * 0.22, f"{int(W)} мм", ha="center", fontweight="bold")
    ax.set_xlim(-W * 0.08, W * 1.08)
    ax.set_ylim(-D * 0.35, D * 1.2)

    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_b(spec: FrameSpec, path: Path) -> None:
    W, H, D = spec.width_mm, spec.height_mm, spec.depth_mm

    def iso(x, y, z):
        return x - 0.45 * z, y + 0.35 * z

    fig, ax = plt.subplots(figsize=(10, 8))
    _style_ax(ax)
    ax.set_title(f"B — 3D-схема (изометрия) · {spec.title}", fontsize=13, fontweight="bold", pad=14)

    front = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
    for p in front:
        ax.plot(*iso(p[0], p[1], 0), color="#1f4e9a", lw=2.5)
    back = [(W, 0), (W, H), (0, H)]
    for p in back:
        ax.plot(*iso(p[0], p[1], D), color="#1f4e9a", lw=2.5)
    for i, p in enumerate(front[:-1]):
        ax.plot([iso(p[0], p[1], 0)[0], iso(p[0], p[1], D)[0]],
                [iso(p[0], p[1], 0)[1], iso(p[0], p[1], D)[1]], color="#1f4e9a", lw=1.2, alpha=0.6)

    if spec.rung_heights_mm:
        for rh in spec.rung_heights_mm:
            ax.plot([iso(0, rh, 0)[0], iso(W, rh, 0)[0]], [iso(0, rh, 0)[1], iso(W, rh, 0)[1]], "g-", lw=2)
    else:
        ax.plot([iso(0, H, 0)[0], iso(W, H, 0)[0]], [iso(0, H, 0)[1], iso(W, H, 0)[1]], "g-", lw=2)
        ax.plot([iso(0, 0, 0)[0], iso(0, H, 0)[0]], [iso(0, 0, 0)[1], iso(0, H, 0)[1]], "g-", lw=1.5, alpha=0.5)

    ax.text(*iso(W / 2, -H * 0.08, 0), f"{int(W)} мм", ha="center", fontsize=10)
    ax.text(*iso(-W * 0.12, H / 2, 0), f"{int(H)} мм", fontsize=10)
    ax.text(*iso(W * 1.02, D * 0.3, D * 0.5), f"{int(D)} мм", fontsize=10)
    pad = max(W, H, D) * 0.25
    ax.set_xlim(-pad, W + pad * 2)
    ax.set_ylim(-pad, H + pad)
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_c(spec: FrameSpec, path: Path) -> None:
    W, H = spec.width_mm, spec.height_mm
    fig, ax = plt.subplots(figsize=(10, 8))
    _style_ax(ax)
    ax.set_title(f"C — Схема IKEA (номера) · {spec.title}", fontsize=13, fontweight="bold", pad=14)

    if spec.rung_heights_mm:
        ax.plot([0, 0, W, W], [0, H, H, 0], "k-", lw=2)
        for y in spec.rung_heights_mm:
            ax.plot([0, W], [y, y], "k-", lw=1.5)
    else:
        ax.add_patch(mpatches.Rectangle((0, 0), W, H, fill=False, edgecolor="k", lw=2.5))

    notes = [
        (W + W * 0.08, H * 0.5, "1 — стойки\n(см. таблицу)"),
        (W / 2, -H * 0.06, "2 — перемычины"),
        (W / 2, H + H * 0.04, "3 — углы / кронштейны"),
    ]
    for x, y, t in notes:
        ax.text(x, y, t, fontsize=10, ha="center",
                bbox=dict(boxstyle="round", facecolor="#fff3cd", edgecolor="#856404"))

    rows = ["Деталь | Кол | Длина"] + [f"{a} | {b} | {c}" for a, b, c in spec.parts_table]
    ax.text(0.02, 0.02, "\n".join(rows), transform=ax.transAxes, fontsize=9,
            verticalalignment="bottom", family="monospace",
            bbox=dict(facecolor="white", edgecolor="gray", alpha=0.95))

    ax.set_xlim(-W * 0.2, W * 1.25)
    ax.set_ylim(-H * 0.12, H * 1.1)
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_d(spec: FrameSpec, path: Path) -> None:
    W, H = spec.width_mm, spec.height_mm
    corners = _corner_rungs(spec)
    fig_h = max(8, H / 250)
    fig, ax = plt.subplots(figsize=(7, fig_h))
    _style_ax(ax)
    ax.set_title(f"D — Вид спереди (крупно) · {spec.title}", fontsize=13, fontweight="bold")

    if spec.rung_heights_mm:
        ax.plot([0, 0], [0, H], color="#1f4e9a", lw=5)
        ax.plot([W, W], [0, H], color="#1f4e9a", lw=5)
        for y in spec.rung_heights_mm:
            c = "#e74c3c" if y in corners else "#f39c12"
            ax.plot([0, W], [y, y], color=c, lw=3.5)
    else:
        ax.add_patch(mpatches.Rectangle((0, 0), W, H, fill=False, edgecolor="#1f4e9a", lw=5))

    ax.axhline(0, color="#8B4513", lw=4)
    ax.annotate("", xy=(0, -H * 0.05), xytext=(W, -H * 0.05), arrowprops=dict(arrowstyle="<->", lw=2))
    ax.text(W / 2, -H * 0.08, f"{int(W)} мм", ha="center", fontsize=12, fontweight="bold")
    ax.annotate("", xy=(W * 1.04, 0), xytext=(W * 1.04, H), arrowprops=dict(arrowstyle="<->", lw=2))
    ax.text(W * 1.07, H / 2, f"{int(H)} мм", va="center", fontsize=12, fontweight="bold")

    if spec.rung_heights_mm:
        leg = [
            Line2D([0], [0], color="#e74c3c", lw=4, label="Угол 90 (низ/верх)"),
            Line2D([0], [0], color="#f39c12", lw=4, label="Кронштейн"),
            Line2D([0], [0], color="#1f4e9a", lw=4, label="Стойка"),
        ]
        ax.legend(handles=leg, loc="upper right", fontsize=9)
    ax.set_xlim(-W * 0.2, W * 1.2)
    ax.set_ylim(-H * 0.12, H * 1.05)
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_e(spec: FrameSpec, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.axis("off")
    ax.set_title(f"E — Таблица + фото · {spec.title}", fontsize=13, fontweight="bold", pad=12)

    rows = [["Деталь", "Кол-во", "Длина"]] + [list(r) for r in spec.parts_table]
    tbl = ax.table(cellText=rows, loc="center", cellLoc="center")
    tbl.scale(1.15, 2.0)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#1f4e9a")
            cell.set_text_props(color="white", fontweight="bold")
        else:
            cell.set_facecolor("#f8f9fa" if r % 2 else "white")

    ax.text(
        0.5, 0.06,
        "Вместо чертежа приложите 3–5 фото:\n"
        "• собранное изделие на участке\n"
        "• комплектация в коробке\n"
        "• узел (коннектор + труба) крупным планом",
        transform=ax.transAxes, ha="center", fontsize=11,
        bbox=dict(boxstyle="round", facecolor="#d4edda", edgecolor="#28a745"),
    )
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


RENDERERS = {
    "A": render_a,
    "B": render_b,
    "C": render_c,
    "D": render_d,
    "E": render_e,
}


def render_format(spec: FrameSpec, fmt: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    RENDERERS[fmt](spec, path)
