"""v3: трубка «8» (как согнутая силиконовая), разрез вдоль → 2 половинки."""

from __future__ import annotations

import io
import math
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from bot.services.figure8_tube_mesh import (
    add_seam_tongue_groove,
    add_screw_holes,
    build_figure8_tube_shell,
    build_stand_mesh,
    contour_u_leg_specs,
    fig8_centerline,
    path_footprint_mm,
    piezo_floor_corner,
    stand_footprint_mm,
    _fig8_buffer_polygons,
    _finalize as _finalize_mesh,
)

V4_PACK_FILENAME = "figure8-corpus-v14-base-tube-40mm-bambu-pack.zip"
V4_PDF_NAME = "figure8-corpus-v14.pdf"

# Bambu Lab P2S — рабочий объём с запасом под brim/skirt
P2S_BUILD_X = 256.0
P2S_BUILD_Y = 256.0
P2S_BUILD_Z = 256.0
P2S_SAFE_MARGIN = 6.0


@dataclass(frozen=True)
class Figure8CorpusSpec:
    """Трубка-лемниската «8», разрез z=0; подставка отдельно."""

    lemniscate_a_mm: float = 78.0  # амплитуда x=A·sin(t) → ширина ~2A
    tube_bore_radius_mm: float = 20.0  # ширина колеи 40 мм (Ø канала)
    wall_mm: float = 5.0  # стенка под шип-паз (lip ~3.2 мм)
    half_height_mm: float = 40.0  # высота каждой половинки (02 / 03)
    neck_id_mm: float = 12.0
    neck_od_mm: float = 18.0
    neck_height_mm: float = 20.0
    cap_slide_mm: float = 16.0
    screw_m3_mm: float = 1.6
    screw_count: int = 6
    stand_base_mm: float = 4.0
    stand_pillar_mm: float = 16.0
    seam_lip_h_mm: float = 2.4
    seam_lip_t_mm: float = 3.2
    seam_clearance_mm: float = 0.28
    piezo_gasket_od_mm: float = 20.6
    piezo_ceramic_od_mm: float = 16.4
    piezo_pocket_depth_mm: float = 2.85
    piezo_shelf_mm: float = 0.35
    piezo_thickness_mm: float = 2.5

    def path_points(self) -> np.ndarray:
        import numpy as np

        return fig8_centerline(self.lemniscate_a_mm)

    @property
    def tube_outer_radius_mm(self) -> float:
        return self.tube_bore_radius_mm + self.wall_mm

    @property
    def tube_outer_diameter_mm(self) -> float:
        return 2.0 * self.tube_outer_radius_mm

    @property
    def channel_diameter_mm(self) -> float:
        return 2.0 * self.tube_bore_radius_mm

    @property
    def neck_xy_mm(self) -> Tuple[float, float]:
        path = self.path_points()
        i = int(path[:, 1].argmax())
        return float(path[i, 0]), float(path[i, 1])

    @property
    def piezo_corner_xy_mm(self) -> Tuple[float, float]:
        x, y, _, _ = piezo_floor_corner(
            self.lemniscate_a_mm, self.tube_bore_radius_mm, self.tube_outer_radius_mm
        )
        return x, y

    @property
    def piezo_diameter_mm(self) -> float:
        """Ø чёрной прокладки (увлажнитель 20 мм)."""
        return self.piezo_gasket_od_mm

    @property
    def lower_height_mm(self) -> float:
        return self.half_height_mm

    @property
    def upper_shell_mm(self) -> float:
        return self.half_height_mm

    @property
    def footprint_x_mm(self) -> float:
        return path_footprint_mm(self.path_points(), self.tube_outer_radius_mm)[0]

    @property
    def footprint_y_mm(self) -> float:
        return path_footprint_mm(self.path_points(), self.tube_outer_radius_mm)[1]

    @property
    def stand_footprint_x_mm(self) -> float:
        return stand_footprint_mm(self.lemniscate_a_mm, self.tube_bore_radius_mm, self.tube_outer_radius_mm)[0]

    @property
    def stand_footprint_y_mm(self) -> float:
        return stand_footprint_mm(self.lemniscate_a_mm, self.tube_bore_radius_mm, self.tube_outer_radius_mm)[1]

    @property
    def upper_print_height_mm(self) -> float:
        return self.upper_shell_mm

    @property
    def stand_print_height_mm(self) -> float:
        return self.stand_base_mm + self.stand_pillar_mm

    def fits_p2s(self) -> bool:
        return (
            self.stand_footprint_x_mm <= P2S_BUILD_X - P2S_SAFE_MARGIN
            and self.stand_footprint_y_mm <= P2S_BUILD_Y - P2S_SAFE_MARGIN
            and self.lower_height_mm <= P2S_BUILD_Z - P2S_SAFE_MARGIN
            and self.upper_print_height_mm <= P2S_BUILD_Z - P2S_SAFE_MARGIN
            and self.stand_print_height_mm <= P2S_BUILD_Z - P2S_SAFE_MARGIN
        )

    def stand_cradle_xy_mm(self) -> List[Tuple[float, float]]:
        return cradle_centers(self.path_points(), self.tube_outer_radius_mm)

    def screw_xy_mm(self) -> List[Tuple[float, float]]:
        path = self.path_points()
        step = max(len(path) // self.screw_count, 1)
        return [(float(p[0]), float(p[1])) for p in path[::step][: self.screw_count]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lemniscate_a_mm": self.lemniscate_a_mm,
            "tube_bore_mm": self.channel_diameter_mm,
            "footprint_mm": f"{self.footprint_x_mm:.1f} × {self.footprint_y_mm:.1f}",
            "stand_mm": f"{self.stand_footprint_x_mm:.1f} × {self.stand_footprint_y_mm:.1f}",
            "fits_p2s": self.fits_p2s(),
        }


def default_figure8_spec() -> Figure8CorpusSpec:
    spec = Figure8CorpusSpec()
    if not spec.fits_p2s():
        raise RuntimeError("Figure-8 spec does not fit P2S build volume")
    return spec


def _centerline_xy(spec: Figure8CorpusSpec) -> Tuple[List[float], List[float]]:
    pts = spec.path_points()
    return pts[:, 0].tolist(), pts[:, 1].tolist()


def _plan_limits(spec: Figure8CorpusSpec, margin: float = 14.0) -> Tuple[float, float, float, float]:
    pts = spec.path_points()
    ro = spec.tube_outer_radius_mm + 8.0
    return (
        float(pts[:, 0].min()) - ro - margin,
        float(pts[:, 0].max()) + ro + margin,
        float(pts[:, 1].min()) - ro - margin,
        float(pts[:, 1].max()) + ro + margin,
    )


def _tube_buffer_polygons(spec: Figure8CorpusSpec) -> Tuple[Any, Any]:
    la, rb, ro = spec.lemniscate_a_mm, spec.tube_bore_radius_mm, spec.tube_outer_radius_mm
    return _fig8_buffer_polygons(la, rb, ro)


def _infinity_path_xy(spec: Figure8CorpusSpec) -> np.ndarray:
    from bot.services.figure8_tube_mesh import fig8_infinity_path_3d

    return fig8_infinity_path_3d(spec.lemniscate_a_mm, r_bore=spec.tube_bore_radius_mm)


def _render_figure_png(draw_fn, out_path: Path, spec: Figure8CorpusSpec, dpi: int = 160) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x0, x1, y0, y1 = _plan_limits(spec, margin=8.0)
    w_mm = x1 - x0
    h_mm = y1 - y0
    fig_w = max(6.0, min(10.0, w_mm / 22.0))
    fig_h = max(4.5, min(8.0, h_mm / 22.0))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    draw_fn(ax)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.grid(True, alpha=0.25, linewidth=0.5)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _draw_plan_lower(ax, spec: Figure8CorpusSpec) -> None:
    import matplotlib.patches as patches

    cx, cy = _centerline_xy(spec)
    ax.plot(cx, cy, ":", color="#0284c7", linewidth=1.4, label="Ось «8» (лемниската)")
    outer, _ = _tube_buffer_polygons(spec)
    polys = [outer] if outer.geom_type == "Polygon" else list(outer.geoms)
    for j, p in enumerate(polys):
        ax.add_patch(
            patches.Polygon(
                list(p.exterior.coords),
                closed=True,
                facecolor="#93c5fd",
                edgecolor="#1d4ed8",
                linewidth=1.5,
                label="Корпус" if j == 0 else None,
            )
        )
    _, inner = _tube_buffer_polygons(spec)
    polys = [inner] if inner.geom_type == "Polygon" else list(inner.geoms)
    for j, p in enumerate(polys):
        ax.add_patch(
            patches.Polygon(
                list(p.exterior.coords),
                closed=True,
                facecolor="#ffffff",
                edgecolor="#0284c7",
                linewidth=1.2,
                label=f"Канал ∞ Ø{spec.channel_diameter_mm:.0f}" if j == 0 else None,
            )
        )
    path3d = _infinity_path_xy(spec)
    ax.plot(path3d[:, 0], path3d[:, 1], "-", color="#b45309", linewidth=0.8, alpha=0.7)
    ax.annotate(
        "over/under в центре",
        xy=(0, 0),
        xytext=(18, 22),
        fontsize=7,
        color="#b45309",
    )
    ax.axhline(0, color="#dc2626", linewidth=0.9, linestyle="--", label="Шов z=0")
    for x, y in spec.screw_xy_mm():
        ax.add_patch(patches.Circle((x, y), 2.2, fill=False, edgecolor="#dc2626", linewidth=1.2))
    ax.set_title("Нижняя: колея 40 мм, шип, over/under")
    ax.legend(loc="upper right", fontsize=7)


def _draw_plan_upper(ax, spec: Figure8CorpusSpec) -> None:
    import matplotlib.patches as patches

    cx, cy = _centerline_xy(spec)
    ax.plot(cx, cy, ":", color="#166534", linewidth=1.4)
    outer, _ = _tube_buffer_polygons(spec)
    polys = [outer] if outer.geom_type == "Polygon" else list(outer.geoms)
    for p in polys:
        ax.add_patch(patches.Polygon(list(p.exterior.coords), closed=True, facecolor="#86efac", edgecolor="#15803d", linewidth=1.5))
    _, inner = _tube_buffer_polygons(spec)
    polys = [inner] if inner.geom_type == "Polygon" else list(inner.geoms)
    for p in polys:
        ax.add_patch(
            patches.Polygon(list(p.exterior.coords), closed=True, facecolor="#ffffff", edgecolor="#166534", linewidth=1.2)
        )
    ax.annotate("паз шип-паз", xy=(0, 0), xytext=(20, 20), fontsize=7, color="#b45309")
    ax.set_title("Верхняя: канал ∞ + паз по шву")


def _draw_section(ax, spec: Figure8CorpusSpec) -> None:
    import matplotlib.patches as patches

    ro, ri = spec.tube_outer_radius_mm, spec.tube_bore_radius_mm
    ax.add_patch(patches.Arc((0, 0), 2 * ro, 2 * ro, angle=0, theta1=0, theta2=180, color="#15803d", linewidth=2))
    ax.add_patch(patches.Arc((0, 0), 2 * ri, 2 * ri, angle=0, theta1=0, theta2=180, color="#0284c7", linewidth=1.5))
    ax.plot([-ro - 10, ro + 10], [0, 0], "r--", linewidth=1, label="Шов z=0")
    ax.annotate("открытый канал", xy=(0, ri * 0.5), xytext=(ri + 8, ri + 6), arrowprops=dict(arrowstyle="->", color="#0284c7"), fontsize=8)
    ax.set_title("Разрез: один канал ∞, в центре два яруса (Z)".format(spec.channel_diameter_mm))
    ax.set_xlim(-35, 35)
    ax.set_ylim(-18, 18)
    ax.set_aspect("equal", adjustable="box")
    ax.legend(fontsize=8)


def _draw_stand(ax, spec: Figure8CorpusSpec) -> None:
    import matplotlib.patches as patches

    cx, cy = _centerline_xy(spec)
    ax.plot(cx, cy, color="#64748b", linewidth=1.0, linestyle=":")
    outer, _ = _tube_buffer_polygons(spec)
    polys = [outer] if outer.geom_type == "Polygon" else list(outer.geoms)
    for p in polys:
        ax.add_patch(patches.Polygon(list(p.exterior.coords), closed=True, fill=False, edgecolor="#1d4ed8", linewidth=1.2, linestyle="--"))
    fx, fy = spec.stand_footprint_x_mm / 2, spec.stand_footprint_y_mm / 2
    ax.add_patch(patches.Rectangle((-fx, -fy), 2 * fx, 2 * fy, fill=False, edgecolor="#475569", linewidth=1.5, label="Плита"))
    path = spec.path_points()
    ro = spec.tube_outer_radius_mm
    for i, s in enumerate(contour_u_leg_specs(path, ro, lemniscate_a=spec.lemniscate_a_mm, r_bore=spec.tube_bore_radius_mm), start=1):
        tx, ty = s["contact_xy"]
        o = s["outward"][:2]
        t = s["tangent"][:2]
        t = t / (np.linalg.norm(t) + 1e-9)
        # U-метка: дуга внутрь
        ax.plot([tx, tx + o[0] * 8], [ty, ty + o[1] * 8], color="#b45309", linewidth=1.5)
        ax.add_patch(patches.Arc((tx + o[0] * ro * 0.5, ty + o[1] * ro * 0.5), ro * 0.9, ro * 0.9, angle=0, theta1=200, theta2=340, color="#b45309", linewidth=2))
        ax.text(tx + o[0] * 12, ty + o[1] * 12, f"U{i}", fontsize=8, color="#b45309")
    ax.set_title("Подставка: плита + 4 U-ножки по контуру «8»")
    ax.legend(fontsize=8)


def _draw_exploded(ax, spec: Figure8CorpusSpec) -> None:
    import matplotlib.patches as patches

    cx, cy = _centerline_xy(spec)
    s = 0.5
    ax.plot([x * s for x in cx], [y * s + 55 for y in cy], color="#64748b", linewidth=2.5)
    ax.text(0, 72, "③ Верхняя половина + защёлки", ha="center", fontsize=9, fontweight="bold")
    ax.add_patch(patches.Arc((0, 62), 40, 16, angle=0, theta1=0, theta2=180, color="#15803d", linewidth=2.5))
    ax.text(0, 48, "② Нижняя половина", ha="center", fontsize=9, fontweight="bold")
    ax.add_patch(patches.Arc((0, 38), 40, 16, angle=0, theta1=180, theta2=360, color="#1d4ed8", linewidth=2.5))
    ax.text(0, 22, "① Подставка (4 ложа снаружи)", ha="center", fontsize=9, fontweight="bold")
    ax.add_patch(patches.Rectangle((-35, 8), 70, 10, facecolor="#cbd5e1", edgecolor="#475569"))
    ax.set_xlim(-55, 55)
    ax.set_ylim(0, 82)
    ax.axis("off")
    ax.set_title("Сборка: подставка → низ → верх")


def _draw_cap_detail(ax, spec: Figure8CorpusSpec) -> None:
    import matplotlib.patches as patches

    od, nid = spec.neck_od_mm, spec.neck_id_mm
    h = spec.neck_height_mm
    ax.add_patch(patches.Rectangle((-od / 2, 0), od, h, facecolor="#e2e8f0", edgecolor="#334155"))
    ax.add_patch(patches.Rectangle((-nid / 2, 0), nid, h - 1, facecolor="#ffffff", edgecolor="#0284c7"))
    ax.add_patch(patches.Rectangle((-spec.cap_slide_mm / 2, h + 1), spec.cap_slide_mm, 2, facecolor="#fef08a", edgecolor="#854d0e", linewidth=2))
    ax.add_patch(patches.Circle((0, h + 2.5), nid / 2 - 0.5, facecolor="#fef08a", edgecolor="#854d0e"))
    ax.annotate("1. Залить", xy=(0, h * 0.4), xytext=(-40, h * 0.7), arrowprops=dict(arrowstyle="->"), fontsize=9)
    ax.annotate("2. Вставить пробку-задвижку", xy=(0, h + 2), xytext=(20, h + 8), arrowprops=dict(arrowstyle="->"), fontsize=9)
    ax.set_title("Горловина: залив → задвижка Ø{:.0f} закрывает канал".format(nid))
    ax.set_xlim(-45, 45)
    ax.set_ylim(-2, 35)
    ax.set_aspect("equal", adjustable="box")


def build_v3_preview_images(spec: Figure8CorpusSpec | None = None) -> Dict[str, bytes]:
    spec = spec or default_figure8_spec()
    out: Dict[str, bytes] = {}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        jobs = [
            ("plan_stand", _draw_stand),
            ("plan_lower", _draw_plan_lower),
            ("plan_upper", _draw_plan_upper),
            ("section", _draw_section),
            ("exploded", _draw_exploded),
        ]
        for name, fn in jobs:
            path = root / f"{name}.png"

            def _draw(ax, draw_fn=fn) -> None:
                draw_fn(ax, spec)

            _render_figure_png(_draw, path, spec)
            out[name] = path.read_bytes()
    return out


def build_v3_math_rationale(spec: Figure8CorpusSpec | None = None) -> str:
    spec = spec or default_figure8_spec()
    a = spec.lemniscate_a_mm
    return (
        "МАТЕМАТИКА: КОРПУС = ПЕЧАТНАЯ ТРУБКА «8» (как в storyboard)\n"
        "========================================\n\n"
        "В storyboard — силиконовая трубка в канавке; здесь корпус сам является трубкой.\n"
        "Центральная линия: x = A·sin(t), y = 0.72·A·sin(2t) — две петли «8».\n"
        f"A = {a} мм → пересечение в (0,0).\n"
        f"Круглое сечение Ø{spec.channel_diameter_mm:.0f} мм, стенка {spec.wall_mm:.0f} мм, "
        f"разрез z=0 → две половинки.\n"
        f"Габарит «8»: {spec.footprint_x_mm:.0f}×{spec.footprint_y_mm:.0f} мм.\n"
        f"Подставка: {spec.stand_footprint_x_mm:.0f}×{spec.stand_footprint_y_mm:.0f} мм — "
        f"плита + 4 U-ножки по контуру.\n\n"
        "Один замкнутый канал «∞»: полная лемниската, вода по кругу в одном направлении.\n"
        "Перекрёсток: мосты ±X + over/under по Z; в (0,0) — сплошной остров, без общей чаши.\n"
        f"Шип-паз: кольцо на шве {spec.seam_lip_h_mm:.1f} мм + зазор {spec.seam_clearance_mm:.1f} мм; "
        f"6× M3 — основное крепление.\n"
        f"Крепёж: {spec.screw_count}× M3 по линии шва.\n"
        f"В архиве v12 — две половинки-трубки «8» (без подставки).\n"
    )


def build_v3_parts_catalog(spec: Figure8CorpusSpec | None = None) -> List[Tuple[str, str]]:
    spec = spec or default_figure8_spec()
    return [
        (
            "1. Подставка (fig8_stand)",
            f"PETG, {spec.stand_footprint_x_mm:.0f}×{spec.stand_footprint_y_mm:.0f}×{spec.stand_print_height_mm:.0f} мм. "
            f"Плита + 4 U-ножки по контуру «8». Печать: плитой на стол.",
        ),
        (
            "2. Нижняя половина (fig8_body_lower)",
            f"PETG, канал ∞ Ø{spec.channel_diameter_mm:.0f} (замкнутый), шипы, "
            f"{spec.screw_count}× M3. Печать: швом z=0 на стол.",
        ),
        (
            "3. Верхняя половина (fig8_body_upper)",
            f"PETG, пазы шип-паз у кромки канала (к нижней). Печать: швом z=0 на стол.",
        ),
    ]


def build_v3_corpus_pdf(spec: Figure8CorpusSpec | None = None) -> bytes:
    """PDF-презентация v3: чертежи + размеры (без 3MF)."""
    from fpdf import FPDF

    spec = spec or default_figure8_spec()
    images = build_v3_preview_images(spec)

    pdf = FPDF()
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=14)

    font_regular = "/System/Library/Fonts/Supplemental/Arial.ttf"
    font_bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    try:
        pdf.add_font("Arial", "", font_regular)
        pdf.add_font("ArialB", "", font_bold)
        body_font, bold_font = "Arial", "ArialB"
        unicode_ok = True
    except Exception:
        body_font, bold_font = "Helvetica", "Helvetica"
        unicode_ok = False

    usable_w = pdf.w - pdf.l_margin - pdf.r_margin

    def wtxt(text: str, size: int = 11, is_bold: bool = False) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(bold_font if is_bold else body_font, size=size)
        t = (text or "").replace("\r", "").strip()
        if not t:
            return
        if not unicode_ok:
            t = t.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(usable_w, size * 0.45, t)

    def figure_page(caption: str, img_key: str) -> None:
        pdf.add_page()
        pdf.set_xy(pdf.l_margin, pdf.t_margin)
        wtxt(caption, 13, is_bold=True)
        pdf.ln(3)
        img_h = max(60.0, pdf.h - pdf.t_margin - pdf.b_margin - 18.0)
        pdf.image(str(img_paths[img_key]), x=pdf.l_margin, w=usable_w, h=img_h)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        img_paths: Dict[str, Path] = {}
        for key, blob in images.items():
            p = td_path / f"{key}.png"
            p.write_bytes(blob)
            img_paths[key] = p

        pdf.add_page()
        pdf.set_xy(pdf.l_margin, pdf.t_margin)
        wtxt("Корпус «восьмёрки» v3", 20, is_bold=True)
        pdf.ln(2)
        wtxt("Трубка-«8» (лемниската), разрез z=0. Подставка — отдельно. Без горловины.", 10)
        wtxt("Сквозной канал Ø{:.0f} мм, защёлки + 6× M3.".format(spec.channel_diameter_mm), 10)
        pdf.ln(3)
        wtxt(build_v3_math_rationale(spec))

        pdf.add_page()
        pdf.set_xy(pdf.l_margin, pdf.t_margin)
        wtxt("Детали комплекта", 16, is_bold=True)
        for title, desc in build_v3_parts_catalog(spec):
            wtxt(title, 12, is_bold=True)
            wtxt(desc)
            pdf.ln(2)

        for key, caption in [
            ("plan_stand", "Рис. 1 — Подставка (4 ложа снаружи)"),
            ("plan_lower", "Рис. 2 — Нижняя половина + пазы защёлок"),
            ("plan_upper", "Рис. 3 — Верхняя половина + язычки"),
            ("section", "Рис. 4 — Разрез: сквозной канал на шве"),
            ("exploded", "Рис. 5 — Порядок сборки"),
        ]:
            figure_page(caption, key)

        pdf.add_page()
        pdf.set_xy(pdf.l_margin, pdf.t_margin)
        wtxt("Порядок сборки", 16, is_bold=True)
        pdf.ln(2)
        for s in [
            "1. Печать: подставка, нижняя, верхняя (швами/плитой на стол).",
            "2. Поставить подставку на стол.",
            "3. Опустить нижнюю половину «8» сверху в 4 ложа подставки.",
            "4. Совместить верх: шипы в пазы, 6× M3 по шву.",
        ]:
            wtxt(s)
            pdf.ln(1)

    raw = pdf.output()
    return raw if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")


def v3_print_parts() -> List[Dict[str, Any]]:
    return [
        {"id": "fig8_body_lower", "name": "Нижняя половина «8»", "material": "PETG", "orientation": "швом z=0 на стол", "print_qty": 1},
        {"id": "fig8_body_upper", "name": "Верхняя половина «8»", "material": "PETG", "orientation": "швом z=0 на стол", "print_qty": 1},
    ]


def build_v3_part_mesh(part_id: str, spec: Figure8CorpusSpec | None = None):
    """v14: базовая трубка «8», БЕЗ шип-паза и M3 — сначала watertight, потом фичи."""
    spec = spec or default_figure8_spec()
    la = spec.lemniscate_a_mm
    rb, wall, hh = spec.tube_bore_radius_mm, spec.wall_mm, spec.half_height_mm

    if part_id == "fig8_body_lower":
        mesh = build_figure8_tube_shell(
            lemniscate_a=la, r_bore=rb, wall=wall, half_h=hh, upper=False
        )
    elif part_id == "fig8_body_upper":
        mesh = build_figure8_tube_shell(
            lemniscate_a=la, r_bore=rb, wall=wall, half_h=hh, upper=True
        )
    else:
        raise ValueError(f"unknown v3 part: {part_id}")
    return mesh


def build_v3_part_scad(part_id: str, spec: Figure8CorpusSpec | None = None) -> str:
    """Справочный SCAD (основная геометрия — trimesh sweep)."""
    spec = spec or default_figure8_spec()
    return (
        f"// {part_id} — используйте STL/3MF из архива (sweep трубки по «8»)\n"
        f"// lemniscate A={spec.lemniscate_a_mm}, bore Ø{spec.channel_diameter_mm:.0f}\n"
    )


def build_v3_print_order_txt() -> str:
    lines = ["ПОРЯДОК ПЕЧАТИ v3 — корпус восьмёрки", "=" * 34, ""]
    for idx, p in enumerate(v3_print_parts(), start=1):
        lines.append(f"{idx}. {p['name']} — 3mf/{idx:02d}-{p['id']}.3mf")
        lines.append(f"   {p['material']} | ×{p.get('print_qty', 1)} | {p.get('orientation', '')}")
        lines.append("")
    return "\n".join(lines)


async def build_v3_print_pack(profile: Optional[Dict[str, Any]] = None) -> Tuple[bytes, str, int, bool]:
    from bot.services.figure8_tube_mesh import (
        build_figure8_tube_shell,
        verify_figure8_channel,
        verify_figure8_dimensions,
        verify_figure8_part_mesh,
    )

    spec = default_figure8_spec()
    la, rb, wall, hh = (
        spec.lemniscate_a_mm,
        spec.tube_bore_radius_mm,
        spec.wall_mm,
        spec.half_height_mm,
    )

    lower = build_figure8_tube_shell(
        lemniscate_a=la, r_bore=rb, wall=wall, half_h=hh, upper=False
    )
    upper = build_figure8_tube_shell(
        lemniscate_a=la, r_bore=rb, wall=wall, half_h=hh, upper=True
    )
    ok, msg = verify_figure8_dimensions(
        lower, upper, half_h=hh, channel_diameter_mm=spec.channel_diameter_mm
    )
    if not ok:
        raise RuntimeError(f"figure8 dimensions: {msg}")
    ok, msg = verify_figure8_channel(
        lower, upper, lemniscate_a=la, r_bore=rb, half_h=hh
    )
    if not ok:
        raise RuntimeError(f"figure8 channel verification failed: {msg}")

    for pid in ("fig8_body_lower", "fig8_body_upper"):
        part_mesh = build_v3_part_mesh(pid, spec)
        ok, msg = verify_figure8_part_mesh(
            part_mesh, part_name=pid, half_h=hh
        )
        if not ok:
            raise RuntimeError(f"figure8 part mesh failed: {msg}")

    prof = profile or {}
    parts = v3_print_parts()
    buf = io.BytesIO()
    threed = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"pdf/{V4_PDF_NAME}", build_v3_corpus_pdf(spec))
        zf.writestr("guides/print_order.txt", build_v3_print_order_txt())
        zf.writestr("guides/assembly.txt", build_v3_assembly_txt())
        zf.writestr("README.txt", build_v3_pack_readme())

        for idx, part in enumerate(parts, start=1):
            pid = part["id"]
            ordered = f"{idx:02d}-{pid}"
            zf.writestr(f"scad/{ordered}.scad", build_v3_part_scad(pid, spec).encode("utf-8"))
            try:
                mesh = build_v3_part_mesh(pid, spec)
                # 3MF — главный формат: shared vertices, 0 non-manifold edges
                # (STL roundtrip ломает геометрию из-за float32 квантования).
                threemf_bytes = mesh.export(file_type="3mf")
                zf.writestr(f"3mf/{ordered}.3mf", threemf_bytes)
                stl_bytes = mesh.export(file_type="stl")
                zf.writestr(f"stl/{ordered}.stl", stl_bytes)
                threed += 1
            except Exception as exc:
                zf.writestr(f"errors/{ordered}.txt", str(exc))

    return buf.getvalue(), V4_PACK_FILENAME, len(parts), threed > 0


def build_v3_assembly_txt() -> str:
    return (
        "СБОРКА v3\n=========\n\n"
        "1. Нижняя половина (02) на стол швом z=0.\n"
        "2. Верхняя (03) на низ: шипы в пазы, 6× M3 по шву.\n"
        "3. Вода — один контур «∞»; в центре over/under, без смешивания потоков.\n"
    )


def build_v3_pack_readme() -> str:
    return (
        "Корпус-трубка «8» v13 (мосты ±X, без чаши в центре)\n"
        "========================================\n\n"
        "01 fig8_body_lower — нижняя половинка трубки\n"
        "02 fig8_body_upper — верхняя половинка трубки\n\n"
        "Круглый канал Ø40 мм, высота половинки 40 мм, стенка 5 мм, шип-паз.\n"
        "Один контур воды; в центре over/under, без смешивания потоков.\n"
    )


def _normalize_v3_text(text: str) -> str:
    t = (text or "").lower().replace("мф", "mf").replace("м ", "m ")
    return t


def is_v3_3mf_request(text: str, *, pending_preview: bool = False) -> bool:
    """3MF v3 только при явном контексте восьмёрки или после PDF-превью (pending)."""
    t = _normalize_v3_text(text)
    if re.match(r"^\s*присылай\s+3\s*mf\s*\.?\s*$", t, re.I):
        return pending_preview
    if not re.search(r"3\s*mf|stl|печат|файл|архив|zip", t, re.I):
        return False
    if not re.search(r"присылай|отправ|сгенерир|дай|нужен|сделай|печатай", t, re.I):
        return False
    if pending_preview and re.search(r"3\s*mf|stl|файл|архив|zip|печат", t, re.I):
        return True
    return bool(re.search(r"\bv3\b|восьм|figure.?8|корпус.{0,25}восьм|восьм.{0,25}корпус", t, re.I))


def is_v3_print_approval(text: str) -> bool:
    """Подтверждение печати после PDF-превью (без обязательного слова «3mf»)."""
    t = _normalize_v3_text(text).strip()
    if re.search(r"^(ок|okay|yes|да|утверж|подтвер|соглас|делай|go)\b", t, re.I):
        return True
    return bool(
        re.search(
            r"присылай.{0,20}(3\s*mf|stl|файл|архив|zip|печат)|"
            r"отправ.{0,20}(3\s*mf|stl|файл|архив)|"
            r"печатай|можно\s+печат",
            t,
            re.I,
        )
    )


def is_v3_figure8_corpus_request(text: str) -> bool:
    if is_v3_3mf_request(text):
        return False
    t = (text or "").lower()
    if re.search(r"\bv3\b|верси[яи]\s*3|треть", t):
        if re.search(r"восьм|figure.?8|корпус|крыш|труб", t):
            return True
    return bool(
        re.search(
            r"корпус.{0,40}восьм|восьм.{0,40}корпус|"
            r"две\s+половин|верхн.{0,15}нижн.{0,15}крыш|"
            r"горловин.{0,20}залив|шип.?паз|"
            r"трубк.{0,15}8|реально\s+8|"
            r"3[\s-]?я\s+провер",
            t,
            re.I,
        )
    )


def build_v3_intro_message(spec: Figure8CorpusSpec | None = None) -> str:
    spec = spec or default_figure8_spec()
    return (
        "📐 Корпус-трубка «8» — PDF + 3MF\n\n"
        f"Печатная трубка (как силикон в storyboard): A={spec.lemniscate_a_mm:.0f} мм, канал ∞ Ø{spec.channel_diameter_mm:.0f}.\n"
        f"Габарит {spec.footprint_x_mm:.0f}×{spec.footprint_y_mm:.0f} мм.\n"
        f"Подставка отдельно — «8» ставится сверху.\n"
        f"Циркуляция по всей восьмёрке; в центре мост/тоннель; шип-паз + {spec.screw_count}× M3.\n"
        f"Две половинки, over/under в центре, без смешивания потоков.\n\n"
        "PDF + 3MF присылаю сразу."
    )
