"""Технические схемы сарая 3×3 — изометрия, план, разрезы (как на чертежах)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from bot.services.dacha_shed_v3_stable import ShedV3StableSpec

Point = Tuple[float, float, float]

# масштаб: метры в координатах модели
COS30 = math.cos(math.radians(30))
SIN30 = math.sin(math.radians(30))


def iso_xy(x: float, y: float, z: float) -> Tuple[float, float]:
    """Изометрия: X — ширина фасада, Y — глубина, Z — высота."""
    return (x - y) * COS30, (x + y) * SIN30 + z


def _draw_line_iso(ax, p0: Point, p1: Point, *, color="#333", lw=1.2, alpha=1.0, zorder=2):
    x0, y0 = iso_xy(*p0)
    x1, y1 = iso_xy(*p1)
    ax.plot([x0, x1], [y0, y1], color=color, lw=lw, alpha=alpha, solid_capstyle="round", zorder=zorder)


def _wall_top_z(spec: "ShedV3StableSpec", y: float) -> float:
    fh = spec.front_height_mm / 1000.0
    bh = spec.back_height_mm / 1000.0
    d = spec.depth_mm / 1000.0
    t = y / d if d else 0.0
    return fh + (bh - fh) * t


def _post_positions(spec: "ShedV3StableSpec") -> List[Point]:
    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    pts: List[Point] = []
    for x in (0.0, L / 2.0, L):
        pts.append((x, 0.0, 0.0))
        pts.append((x, D, 0.0))
    return pts


def _rafter_xs(spec: "ShedV3StableSpec") -> List[float]:
    L = spec.length_mm / 1000.0
    n = spec.rafter_count_n
    if n <= 1:
        return [0.0, L]
    return [L * i / (n - 1) for i in range(n)]


def _dim_h(ax, x: float, z0: float, z1: float, label: str, offset: float = 0.35):
    ax.annotate(
        "",
        xy=(x, z0),
        xytext=(x, z1),
        arrowprops=dict(arrowstyle="<->", color="#111", lw=0.9),
    )
    ax.text(x + offset, (z0 + z1) / 2, label, fontsize=9, va="center", fontweight="bold")


def _dim_v(ax, z: float, y0: float, y1: float, label: str, offset: float = 0.25):
    ax.annotate(
        "",
        xy=(y0, z),
        xytext=(y1, z),
        arrowprops=dict(arrowstyle="<->", color="#111", lw=0.9),
    )
    ax.text((y0 + y1) / 2, z + offset, label, fontsize=9, ha="center", fontweight="bold")


def draw_isometric_shed(
    ax,
    spec: "ShedV3StableSpec",
    *,
    show_foundation: bool = True,
    show_foot_pads: bool = False,
    show_bottom_frame: bool = True,
    show_posts: bool = True,
    show_top_frame: bool = True,
    show_roof: bool = True,
    show_braces: bool = True,
    show_purlins: bool = True,
    show_door: bool = True,
    show_dimensions: bool = False,
    show_plan_dims: bool = True,
    highlight_posts: bool = False,
) -> None:
    """Рисует каркас в изометрии на переданных axes."""
    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    fh = spec.front_height_mm / 1000.0
    bh = spec.back_height_mm / 1000.0
    fd = 0.15

    wood = "#c4a574"
    wood_d = "#8b6914"
    plate = "#6d4c2a"
    conc = "#9e9e9e"
    post_color = "#e65100" if highlight_posts else wood

    def post_height_at(x: float, y: float) -> float:
        if y < 0.05:
            return fh
        if y > D - 0.05:
            return bh
        return _wall_top_z(spec, y)

    if show_foundation:
        for x, y, _ in _post_positions(spec):
            bx = [x - 0.12, x + 0.12, x + 0.12, x - 0.12]
            bz = [0, 0, fd, fd]
            poly = [iso_xy(bx[i], y, bz[i]) for i in range(4)]
            xs = [p[0] for p in poly] + [poly[0][0]]
            ys = [p[1] for p in poly] + [poly[0][1]]
            ax.fill(xs, ys, color=conc, ec="#616161", lw=0.8, zorder=1)
            if show_foot_pads:
                px = [x - 0.08, x + 0.08, x + 0.08, x - 0.08]
                pz = [fd, fd, fd + 0.04, fd + 0.04]
                ppoly = [iso_xy(px[i], y, pz[i]) for i in range(4)]
                pxs = [p[0] for p in ppoly] + [ppoly[0][0]]
                pys = [p[1] for p in ppoly] + [ppoly[0][1]]
                ax.fill(pxs, pys, color="#ff9800", ec="#e65100", lw=1.0, zorder=2)

    if show_bottom_frame:
        for (x0, y0), (x1, y1) in [
            ((0, 0), (L, 0)),
            ((L, 0), (L, D)),
            ((L, D), (0, D)),
            ((0, D), (0, 0)),
        ]:
            _draw_line_iso(ax, (x0, y0, fd), (x1, y1, fd), color=plate, lw=3.5, zorder=3)

    if show_posts:
        for x, y, _ in _post_positions(spec):
            h = post_height_at(x, y)
            _draw_line_iso(ax, (x, y, fd), (x, y, h), color=post_color, lw=4.0, zorder=4)

    if show_top_frame:
        for (x0, y0), (x1, y1) in [
            ((0, 0), (L, 0)),
            ((L, 0), (L, D)),
            ((L, D), (0, D)),
            ((0, D), (0, 0)),
        ]:
            z0, z1 = _wall_top_z(spec, y0), _wall_top_z(spec, y1)
            _draw_line_iso(ax, (x0, y0, z0), (x1, y1, z1), color=plate, lw=3.5, zorder=5)

    if show_braces:
        for y in (0.0, D):
            zt = fh if y < 0.1 else bh
            _draw_line_iso(ax, (0, y, fd + 0.3), (L, y, zt - 0.2), color=wood_d, lw=2.0, zorder=3)
            _draw_line_iso(ax, (L, y, fd + 0.3), (0, y, zt - 0.2), color=wood_d, lw=2.0, zorder=3)
        for x in (0.0, L):
            _draw_line_iso(ax, (x, 0, fd + 0.3), (x, D, bh - 0.2), color=wood_d, lw=1.8, zorder=3)
            _draw_line_iso(ax, (x, D, bh - 0.2), (x, 0, fd + 0.3), color=wood_d, lw=1.8, zorder=3)

    if show_roof:
        for x in _rafter_xs(spec):
            zf = _wall_top_z(spec, 0.0)
            zb = _wall_top_z(spec, D)
            _draw_line_iso(ax, (x, 0, zf), (x, D, zb), color=wood, lw=3.0, zorder=6)

    if show_purlins and show_roof:
        for frac in (0.35, 0.72):
            y = D * frac
            z = _wall_top_z(spec, y)
            _draw_line_iso(ax, (0, y, z + 0.05), (L, y, z + 0.05), color=plate, lw=2.5, zorder=7)

    if show_door and show_posts:
        dx0 = spec.door_offset_left_mm / 1000.0
        dx1 = dx0 + spec.door_width_mm / 1000.0
        dh = spec.door_height_mm / 1000.0
        _draw_line_iso(ax, (dx0, 0, fd), (dx0, 0, dh), color="#8B4513", lw=2.5, zorder=8)
        _draw_line_iso(ax, (dx1, 0, fd), (dx1, 0, dh), color="#8B4513", lw=2.5, zorder=8)
        _draw_line_iso(ax, (dx0, 0, dh), (dx1, 0, dh), color="#8B4513", lw=2.5, zorder=8)

    if show_plan_dims:
        p0 = iso_xy(0, -0.35, 0)
        p1 = iso_xy(L, -0.35, 0)
        ax.annotate("", xy=p0, xytext=p1, arrowprops=dict(arrowstyle="<->", color="#c00", lw=1.2))
        ax.text((p0[0] + p1[0]) / 2, p0[1] - 0.12, f"{spec.length_mm:.0f}", fontsize=10, color="#c00", ha="center", fontweight="bold")
        p0 = iso_xy(L + 0.25, 0, 0)
        p1 = iso_xy(L + 0.25, D, 0)
        ax.annotate("", xy=p0, xytext=p1, arrowprops=dict(arrowstyle="<->", color="#c00", lw=1.2))
        ax.text((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, f"{spec.depth_mm:.0f}", fontsize=10, color="#c00", fontweight="bold")

    if show_dimensions and show_posts:
        p0 = iso_xy(-0.35, 0, fd)
        p1 = iso_xy(-0.35, 0, fh)
        ax.annotate("", xy=p0, xytext=p1, arrowprops=dict(arrowstyle="<->", color="#c00", lw=1.2))
        ax.text(p0[0] - 0.15, (p0[1] + p1[1]) / 2, f"{spec.front_height_mm:.0f}", fontsize=10, color="#c00", fontweight="bold")

    ax.autoscale()
    ax.set_aspect("equal")


def render_isometric_frame(
    spec: "ShedV3StableSpec",
    path: Path,
    *,
    show_foundation: bool = True,
    show_foot_pads: bool = False,
    show_bottom_frame: bool = True,
    show_posts: bool = True,
    show_top_frame: bool = True,
    show_roof: bool = True,
    show_braces: bool = True,
    show_purlins: bool = True,
    show_door: bool = True,
    show_dimensions: bool = False,
    show_plan_dims: bool = True,
    for_embed: bool = False,
    title: str = "",
    subtitle: str = "",
) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 7.5) if for_embed else (12, 8))
    ax.set_facecolor("#ececec")
    if title and not for_embed:
        ax.set_title(f"{title}\n{subtitle or spec.name}", fontsize=13, fontweight="bold", pad=10)
    ax.axis("off")

    draw_isometric_shed(
        ax,
        spec,
        show_foundation=show_foundation,
        show_foot_pads=show_foot_pads,
        show_bottom_frame=show_bottom_frame,
        show_posts=show_posts,
        show_top_frame=show_top_frame,
        show_roof=show_roof,
        show_braces=show_braces,
        show_purlins=show_purlins,
        show_door=show_door,
        show_dimensions=show_dimensions,
        show_plan_dims=show_plan_dims,
    )

    if not for_embed:
        ax.text(
            0.02, 0.02,
            "Профиль 20×20 · PETG · палки 1/1,5/2 м · "
            f"уклон {spec.pitch_deg:.1f}°",
            transform=ax.transAxes, fontsize=8, va="bottom",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.85),
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    pad = 0.05 if for_embed else 0.1
    fig.savefig(path, dpi=180, bbox_inches="tight", pad_inches=pad, facecolor="#ececec")
    plt.close(fig)


def render_plan_blueprint(spec: "ShedV3StableSpec", path: Path) -> None:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.set_facecolor("white")
    ax.set_title("План · вид сверху · 3×3 м", fontsize=14, fontweight="bold")
    ax.set_aspect("equal")

    # сетка осей A-B / 1-2
    ax.axhline(0, color="#ccc", lw=0.5)
    ax.axhline(D, color="#ccc", lw=0.5)
    ax.axvline(0, color="#ccc", lw=0.5)
    ax.axvline(L, color="#ccc", lw=0.5)
    ax.text(-0.25, D / 2, "A", fontsize=12, fontweight="bold")
    ax.text(-0.25, -0.15, "B", fontsize=12, fontweight="bold")
    ax.text(L / 2, -0.35, "1", fontsize=12, fontweight="bold", ha="center")
    ax.text(L + 0.15, D / 2, "2", fontsize=12, fontweight="bold")

    ax.add_patch(mpatches.Rectangle((0, 0), L, D, fill=False, ec="#1a1a1a", lw=2.5))
    for x in spec.front_post_x_mm():
        ax.plot(x / 1000, 0, "ks", ms=10, mfc="#1f77b4")
        ax.plot(x / 1000, D, "ks", ms=10, mfc="#1f77b4")

    dx0 = spec.door_offset_left_mm / 1000.0
    dx1 = dx0 + spec.door_width_mm / 1000.0
    ax.add_patch(mpatches.Rectangle((dx0, -0.08), dx1 - dx0, 0.12, fc="#8B4513", ec="#5d3a1a", lw=1.5))
    ax.text((dx0 + dx1) / 2, -0.22, "ДВЕРЬ", ha="center", fontsize=9, fontweight="bold")

    ax.annotate("", xy=(0, -0.55), xytext=(L, -0.55), arrowprops=dict(arrowstyle="<->", lw=1.2))
    ax.text(L / 2, -0.65, f"{spec.length_mm:.0f}", ha="center", fontweight="bold")
    ax.annotate("", xy=(-0.55, 0), xytext=(-0.55, D), arrowprops=dict(arrowstyle="<->", lw=1.2))
    ax.text(-0.75, D / 2, f"{spec.depth_mm:.0f}", rotation=90, va="center", fontweight="bold")

    ax.annotate("", xy=(L + 0.2, 0), xytext=(L + 0.2, D), arrowprops=dict(arrowstyle="->", color="#00796b", lw=2))
    ax.text(L + 0.35, D / 2, "сток\nводы", fontsize=8, color="#00796b")

    ax.set_xlim(-0.9, L + 0.6)
    ax.set_ylim(-0.85, D + 0.35)
    ax.axis("off")
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_section_front(spec: "ShedV3StableSpec", path: Path) -> None:
    """Разрез 1-1 — фасад."""
    import matplotlib.pyplot as plt

    L = spec.length_mm / 1000.0
    fh = spec.front_height_mm / 1000.0
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.set_facecolor("white")
    ax.set_title("Разрез 1-1 · фасад (дверь)", fontsize=14, fontweight="bold")

    ax.plot([0, L], [0, 0], "k-", lw=2)
    for x in spec.front_post_x_mm():
        ax.plot([x / 1000, x / 1000], [0, fh], color="#1f77b4", lw=4)
    ax.plot([0, L], [fh, fh], color="#6d4c2a", lw=3)

    dx0 = spec.door_offset_left_mm / 1000.0
    dx1 = dx0 + spec.door_width_mm / 1000.0
    dh = spec.door_height_mm / 1000.0
    ax.plot([dx0, dx0], [0, dh], color="#8B4513", lw=3)
    ax.plot([dx1, dx1], [0, dh], color="#8B4513", lw=3)
    ax.plot([dx0, dx1], [dh, dh], color="#8B4513", lw=3)

    _dim_h(ax, -0.25, 0, fh, f"{spec.front_height_mm:.0f}")
    ax.annotate("", xy=(0, -0.35), xytext=(L, -0.35), arrowprops=dict(arrowstyle="<->", lw=1.2))
    ax.text(L / 2, -0.45, f"{spec.length_mm:.0f}", ha="center", fontweight="bold")

    for z, lab in [(0, "±0"), (1.0, "1000"), (dh, f"{spec.door_height_mm:.0f}")]:
        ax.plot([-0.08, L + 0.08], [z, z], color="#eee", lw=0.5, ls="--")
        if z > 0:
            ax.text(L + 0.12, z, lab, fontsize=8, va="center")

    ax.set_xlim(-0.5, L + 0.4)
    ax.set_ylim(-0.55, fh + 0.45)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_section_side(spec: "ShedV3StableSpec", path: Path) -> None:
    """Разрез 2-2 — бок (односкат)."""
    import matplotlib.pyplot as plt

    D = spec.depth_mm / 1000.0
    fh = spec.front_height_mm / 1000.0
    bh = spec.back_height_mm / 1000.0
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.set_facecolor("white")
    ax.set_title("Разрез 2-2 · бок (уклон крыши)", fontsize=14, fontweight="bold")

    ax.plot([0, 0], [0, fh], color="#1f77b4", lw=4)
    ax.plot([D, D], [0, bh], color="#1f77b4", lw=4)
    ax.plot([0, D], [0, 0], "k-", lw=2)
    ax.plot([0, D], [fh, bh], color="#c62828", lw=3)
    ax.fill([0, D, D, 0], [0, 0, bh, fh], color="#e3f2fd", alpha=0.35)

    for x in _rafter_xs(spec):
        pass  # side view single rafter line already roof slope

    _dim_h(ax, -0.3, 0, fh, f"{spec.front_height_mm:.0f}")
    _dim_h(ax, D + 0.15, 0, bh, f"{spec.back_height_mm:.0f}")
    _dim_v(ax, fh + 0.25, 0, D, f"{spec.depth_mm:.0f}")
    ax.text(D / 2, fh + 0.38, f"уклон {spec.pitch_deg:.1f}°", ha="center", fontweight="bold")

    ax.set_xlim(-0.55, D + 0.45)
    ax.set_ylim(-0.35, fh + 0.55)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _step_flags(step: int) -> dict:
    """Флаги визуализации — строго по номеру шага IKEA."""
    base = dict(
        show_foundation=True,
        show_foot_pads=False,
        show_bottom_frame=False,
        show_posts=False,
        show_top_frame=False,
        show_roof=False,
        show_braces=False,
        show_purlins=False,
        show_door=False,
        show_dimensions=False,
        show_plan_dims=True,
        for_embed=True,
    )
    table = {
        1: dict(show_foundation=True),
        2: dict(show_foundation=True, show_foot_pads=True),
        3: dict(show_bottom_frame=True),
        4: dict(show_bottom_frame=True, show_posts=True, show_dimensions=True),
        5: dict(show_bottom_frame=True, show_posts=True, show_braces=True, show_dimensions=True),
        6: dict(show_bottom_frame=True, show_posts=True, show_braces=True, show_top_frame=True, show_dimensions=True),
        7: dict(show_bottom_frame=True, show_posts=True, show_braces=True, show_top_frame=True, show_door=True, show_dimensions=True),
        8: dict(show_bottom_frame=True, show_posts=True, show_braces=True, show_top_frame=True, show_door=True, show_roof=True, show_dimensions=True),
        9: dict(show_bottom_frame=True, show_posts=True, show_braces=True, show_top_frame=True, show_door=True, show_roof=True, show_purlins=True, show_dimensions=True),
        10: dict(show_bottom_frame=True, show_posts=True, show_braces=True, show_top_frame=True, show_door=True, show_roof=True, show_purlins=True, show_dimensions=True),
    }
    kw = {**base, **table.get(step, table[10])}
    return kw


def render_assembly_step_iso(
    spec: "ShedV3StableSpec",
    path: Path,
    step: int,
    title: str,
) -> None:
    render_isometric_frame(spec, path, title="", **(_step_flags(step)))


def build_schemes_pdf(spec: "ShedV3StableSpec", pages_dir: Path) -> bytes:
    """PDF: титул + изометрия + план + разрезы + шаги сборки."""
    from fpdf import FPDF
    from bot.services.dacha_shed_kit import _pdf_fonts

    pages_dir.mkdir(parents=True, exist_ok=True)

    render_isometric_frame(
        spec,
        pages_dir / "00-isometric-full.png",
        show_dimensions=True,
        for_embed=False,
        title="Изометрия каркаса 3×3 м",
    )
    render_plan_blueprint(spec, pages_dir / "01-plan.png")
    render_section_front(spec, pages_dir / "02-section-front.png")
    render_section_side(spec, pages_dir / "03-section-side.png")

    step_titles = [
        "Разложите детали",
        "6 опор на блоки",
        "Нижний периметр",
        "6 стоек",
        "8 раскосов",
        "Верхняя обвязка",
        "Дверной проём",
        "4 стропила",
        "Обрешётка",
        "Профлист",
    ]
    for i, t in enumerate(step_titles, start=1):
        render_assembly_step_iso(spec, pages_dir / f"step-{i:02d}.png", i, t)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    bf, bb, uni = _pdf_fonts(pdf)

    def txt(s: str, size: int = 11, bold: bool = False, ln: bool = True) -> None:
        pdf.set_font(bb if bold else bf, size=size)
        t = s.replace("\r", "")
        w = pdf.w - 24
        if uni:
            pdf.multi_cell(w, size * 0.42, t)
        else:
            pdf.multi_cell(w, size * 0.42, t.encode("latin-1", "replace").decode("latin-1"))
        if ln:
            pdf.ln(1)

    # титул
    pdf.add_page()
    txt("Схемы и чертежи", 18, bold=True)
    txt(spec.name, 14, bold=True)
    txt("Профиль 20×20×2 · палки 1 / 1,5 / 2 м без резки", 11)
    sc = spec.stick_counts()
    txt(
        f"План {spec.length_mm/10:.0f}×{spec.depth_mm/10:.0f} м · "
        f"фасад {spec.front_height_mm/10:.0f} см · зад {spec.back_height_mm/10:.0f} см · "
        f"уклон {spec.pitch_deg:.1f}°",
        11,
    )
    txt(f"Палки: 200 см × {sc[2000]}, 150 см × {sc[1500]}, 100 см × {sc[1000]}", 10)

    sheets = [
        ("00-isometric-full.png", "Изометрия — общий вид каркаса"),
        ("01-plan.png", "План 1:100 (мм на чертеже)"),
        ("02-section-front.png", "Разрез 1-1 — фасад"),
        ("03-section-side.png", "Разрез 2-2 — бок"),
    ]
    for fname, caption in sheets:
        pdf.add_page()
        p = pages_dir / fname
        if p.exists():
            pdf.image(str(p), x=10, y=22, w=190, h=135)
        pdf.set_y(162)
        txt(caption, 11, bold=True)

    pdf.add_page()
    txt("Сборка — этапы (изометрия)", 14, bold=True)
    for i, t in enumerate(step_titles, start=1):
        pdf.add_page()
        p = pages_dir / f"step-{i:02d}.png"
        txt(f"Шаг {i}. {t}", 13, bold=True)
        pdf.ln(2)
        if p.exists():
            pdf.image(str(p), x=10, y=32, w=190, h=118)

    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")


def build_ikea_pdf_with_schemes(
    spec: "ShedV3StableSpec",
    steps: list,
    pages_dir: Path,
) -> bytes:
    """IKEA-PDF: словарь деталей → шаги со схемами."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    from bot.services.dacha_shed_kit import _pdf_fonts
    from bot.services.dacha_shed_parts_ru import full_kit_catalog

    pages_dir.mkdir(parents=True, exist_ok=True)

    for st in steps:
        render_assembly_step_iso(
            spec,
            pages_dir / f"ikea-step-{st.number:02d}.png",
            st.number,
            st.title,
        )

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_margins(14, 14, 14)
    bf, bb, uni = _pdf_fonts(pdf)
    page_w = pdf.w - 28
    img_w = page_w
    img_x = 14
    img_y_step = 28
    img_h = 118

    left = pdf.l_margin

    def write_lines(text: str, size: int = 10, bold: bool = False, line_h: Optional[float] = None) -> None:
        pdf.set_x(left)
        pdf.set_font(bb if bold else bf, size=size)
        lh = line_h or size * 0.45
        t = text.replace("\r", "")
        if uni:
            pdf.multi_cell(page_w, lh, t, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.multi_cell(
                page_w,
                lh,
                t.encode("latin-1", "replace").decode("latin-1"),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

    def write_parts(parts: list) -> None:
        write_lines("Детали для этого шага:", 10, bold=True)
        pdf.ln(1)
        badge_w = 7
        text_x = left + badge_w + 3
        text_w = page_w - badge_w - 3
        for lbl, qty in parts[:10]:
            pdf.set_fill_color(198, 40, 40)
            y0 = pdf.get_y()
            pdf.rect(left, y0 + 0.5, badge_w, badge_w, style="F")
            pdf.set_text_color(255, 255, 255)
            pdf.set_font(bb, size=9)
            pdf.set_xy(left, y0 + 0.5)
            if uni:
                pdf.cell(badge_w, badge_w, str(qty), align="C")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(bf, size=10)
            pdf.set_xy(text_x, y0)
            pdf.multi_cell(text_w, 10 * 0.45, f"× {lbl}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def write_catalog_pages() -> None:
        pdf.add_page()
        write_lines("Словарь деталей", 18, bold=True)
        pdf.ln(2)
        write_lines(
            f"{spec.name}\n"
            "Здесь все детали из коробки. На каждом шаге ниже — только то, "
            "что нужно для этого шага.",
            10,
        )
        pdf.ln(2)
        write_lines("Металлические палки (труба 20×20×2 мм):", 11, bold=True)
        pdf.ln(1)
        for pid in ("profil_200", "profil_150", "profil_100"):
            row = next(r for r in full_kit_catalog(spec) if r.part_id == pid)
            write_lines(f"• {row.name} — {row.qty} шт.", 10, bold=True)
            write_lines(f"  {row.desc}", 9)
            write_lines(f"  Размер: {row.size}", 9)
            pdf.ln(1)
        pdf.ln(1)
        write_lines("Пластиковые соединители (печатаются на 3D-принтере):", 11, bold=True)
        pdf.ln(1)
        plastic_ids = (
            "foot_base", "corner_90", "corner_post", "tee_90", "inline_splice",
            "brace_45", "door_frame", "lintel_splice", "rafter_seat", "girt_bracket",
        )
        catalog = {r.part_id: r for r in full_kit_catalog(spec)}
        for pid in plastic_ids:
            row = catalog[pid]
            write_lines(f"• {row.name} — {row.qty} шт.", 10, bold=True)
            write_lines(f"  {row.desc}", 9)
            write_lines(f"  Материал: {row.size}", 9)
            pdf.ln(0.5)
        if pdf.get_y() > 240:
            pdf.add_page()
        pdf.ln(1)
        write_lines("Крепёж и обшивка:", 11, bold=True)
        pdf.ln(1)
        for pid in ("blok", "bolt_m8", "bolt_m5", "proflist", "samorez"):
            row = catalog[pid]
            write_lines(f"• {row.name} — {row.qty} шт.", 10, bold=True)
            write_lines(f"  {row.desc}", 9)
            write_lines(f"  {row.size}", 9)
            pdf.ln(0.5)

    write_catalog_pages()

    # --- шаги ---
    for st in steps:
        pdf.add_page()
        write_lines(f"Шаг {st.number} — {st.title}", 14, bold=True)
        pdf.ln(2)

        img_path = pages_dir / f"ikea-step-{st.number:02d}.png"
        if img_path.exists():
            pdf.image(str(img_path), x=img_x, y=img_y_step, w=img_w, h=img_h)

        pdf.set_y(img_y_step + img_h + 6)
        pdf.set_x(left)
        write_lines(st.body, 10)
        if getattr(st, "connect", ""):
            pdf.ln(2)
            write_lines("Как соединять:", 10, bold=True)
            write_lines(st.connect, 10)
        pdf.ln(3)
        write_parts(st.parts)

    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")
