"""Сарай v2 — только палки 1 / 1,5 / 2 м (без резки), IKEA-PDF сборки."""

from __future__ import annotations

import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import trimesh

from bot.services.dacha_shed_kit import (
    SHED_CONNECTOR_BUILDERS,
    SHED_CONNECTOR_LABELS,
    SHED_CONNECTOR_ORDER,
    ShedSpec,
    _orient_shed,
    _pdf_fonts,
    render_shed_scheme_png,
)
from bot.services.dacha_trellis_kit import (
    SOCKET_DEPTH_MM,
    _add_bolt_hole,
    _arm_along,
    _bool_union,
)

STICK_MM = (1000, 1500, 2000)
SPLICE_OVERLAP_MM = 56.0  # две гильзы по ~28 мм


@dataclass(frozen=True)
class BeamAssembly:
    """Сборная балка из стандартных палок."""

    label: str
    segments_mm: Tuple[int, ...]
    qty: int = 1
    note: str = ""

    @property
    def splices(self) -> int:
        return max(0, len(self.segments_mm) - 1) * self.qty

    @property
    def nominal_mm(self) -> float:
        return sum(self.segments_mm) * self.qty

    def describe(self) -> str:
        segs = "+".join(f"{s/10:.0f}" for s in self.segments_mm)
        sp = f" + {self.splices}× стык" if self.splices else ""
        return f"{self.label}: {self.qty}× ({segs}){sp}"


def build_inline_splice() -> trimesh.Trimesh:
    """Стык в линию: 2 м + 2 м / 2 м + 1 м и т.д."""
    a1 = _arm_along("x")
    a2 = _arm_along("x")
    a2.apply_translation([SOCKET_DEPTH_MM * 0.82, 0.0, 0.0])
    mesh = _bool_union([a1, a2])
    return _add_bolt_hole(mesh, "y")


# Регистрация в общем каталоге (runtime patch для экспорта v2)
SHED_V2_EXTRA_BUILDERS = {"inline_splice": build_inline_splice}
SHED_V2_EXTRA_LABELS = {"inline_splice": "Стык в линию (2 м+2 м / 2 м+1 м)"}


@dataclass(frozen=True)
class ShedNoCutSpec:
    """
    Хозблок 4×3 м, односкат.
    Палки только 100 / 150 / 200 см, стыковка inline_splice.
    Фасад 200 см, зад 150 см, уклон ~9,5° (сток назад).
    """

    name: str = "Хозблок 4×3 (без резки)"
    length_mm: int = 4000
    depth_mm: int = 3000
    front_height_mm: int = 2000
    back_height_mm: int = 1500
    door_width_mm: int = 1000
    door_height_mm: int = 2000
    door_offset_left_mm: int = 500
    rafter_count_n: int = 5
    girt_rows: int = 2

    @property
    def rise_mm(self) -> float:
        return float(self.front_height_mm - self.back_height_mm)

    @property
    def pitch_deg(self) -> float:
        return math.degrees(math.atan(self.rise_mm / self.depth_mm))

    @property
    def rafter_slope_mm(self) -> float:
        return math.hypot(self.depth_mm, self.rise_mm)

    def span_4m(self) -> Tuple[int, ...]:
        return (2000, 2000)

    def span_3m(self) -> Tuple[int, ...]:
        return (2000, 1000)

    def span_rafter(self) -> Tuple[int, ...]:
        return (1500, 1500)

    def beam_list(self) -> List[BeamAssembly]:
        s4 = self.span_4m()
        s3 = self.span_3m()
        sr = self.span_rafter()
        beams = [
            BeamAssembly("НИЗ-Ф (перед)", s4, 1),
            BeamAssembly("НИЗ-З (зад)", s4, 1),
            BeamAssembly("НИЗ-Б (бок)", s3, 2),
            BeamAssembly("СТ-Ф стойка", (2000,), len(self.front_post_x())),
            BeamAssembly("СТ-З стойка", (1500,), len(self.back_post_x())),
            BeamAssembly("ВЕРХ-Ф", s4, 1),
            BeamAssembly("ВЕРХ-З", s4, 1),
            BeamAssembly("СКАТ-Б боковой наклонный", sr, 2),
            BeamAssembly("СТР стропило", sr, self.rafter_count_n, "концы в rafter_seat ~10 см"),
            BeamAssembly("GIRT фасад", s4, self.girt_rows),
            BeamAssembly("GIRT зад", s4, 1),
            BeamAssembly("GIRT бок", s3, self.girt_rows * 2),
            BeamAssembly("ПРОГ крыши", s4, 3),
            BeamAssembly("РИГ-Д (над дверью)", (1000,), 2, "двойной ригель"),
            BeamAssembly("РИГ-О окно", (1000,), 1),
            BeamAssembly("ПОД-О окно", (1000,), 1),
        ]
        return beams

    def front_post_x(self) -> Tuple[int, ...]:
        return (0, self.door_offset_left_mm + self.door_width_mm, self.length_mm)

    def back_post_x(self) -> Tuple[int, ...]:
        return (0, self.length_mm // 2, self.length_mm)

    def front_post_x_mm(self) -> Tuple[float, ...]:
        return tuple(float(x) for x in self.front_post_x())

    def back_post_x_mm(self) -> Tuple[float, ...]:
        return tuple(float(x) for x in self.back_post_x())

    def stick_counts(self) -> Dict[int, int]:
        c = {1000: 0, 1500: 0, 2000: 0}
        for b in self.beam_list():
            for seg in b.segments_mm:
                c[seg] += b.qty
        return c

    def inline_splice_count(self) -> int:
        return sum(b.splices for b in self.beam_list())

    def connector_counts(self) -> Dict[str, int]:
        n_posts_f = len(self.front_post_x())
        n_posts_b = len(self.back_post_x())
        n_girt = self.girt_rows * 3 + self.girt_rows * 2 + 1
        return {
            "foot_base": n_posts_f + n_posts_b,
            "corner_90": 8,
            "corner_post": 4,
            "tee_90": 6,
            "rafter_seat": self.rafter_count_n * 2,
            "girt_bracket": n_girt,
            "brace_45": 4,
            "door_frame": 4,
            "lintel_splice": 2,
            "inline_splice": self.inline_splice_count(),
        }

    def to_legacy_spec(self) -> ShedSpec:
        return ShedSpec(
            name=self.name,
            length_mm=float(self.length_mm),
            depth_mm=float(self.depth_mm),
            front_height_mm=float(self.front_height_mm),
            pitch_deg=self.pitch_deg,
            door_width_mm=float(self.door_width_mm),
            door_height_mm=float(self.door_height_mm),
            door_offset_left_mm=float(self.door_offset_left_mm),
            girt_spacing_mm=1000.0,
            rafter_spacing_mm=1000.0,
            purlin_spacing_mm=1000.0,
        )

    def load_summary(self) -> Dict[str, float]:
        spec = self.to_legacy_spec()
        # override back height (legacy calc differs slightly)
        loads = spec.load_summary()
        loads["back_height_mm"] = self.back_height_mm
        loads["pitch_deg"] = round(self.pitch_deg, 1)
        return loads


DEFAULT_SHED_NOCUT = ShedNoCutSpec()


def _orient_v2(key: str, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    if key == "inline_splice":
        m = mesh.copy()
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
        m.apply_translation([0.0, 0.0, -float(m.bounds[0][2])])
        return m
    return _orient_shed(key, mesh)


def export_shed_v2_connectors(
    out_dir: Path,
    spec: ShedNoCutSpec = DEFAULT_SHED_NOCUT,
    *,
    stl_dir: Path | None = None,
    plates_dir: Path | None = None,
    quantities_path: Path | None = None,
) -> List[Path]:
    builders = {**SHED_CONNECTOR_BUILDERS, **SHED_V2_EXTRA_BUILDERS}
    labels = {**SHED_CONNECTOR_LABELS, **SHED_V2_EXTRA_LABELS}
    order = SHED_CONNECTOR_ORDER + ("inline_splice",)
    counts = spec.connector_counts()
    stl_out = stl_dir or out_dir
    plates_out = plates_dir or out_dir
    qty_path = quantities_path or out_dir / "print_quantities.txt"
    stl_out.mkdir(parents=True, exist_ok=True)
    plates_out.mkdir(parents=True, exist_ok=True)
    qty_path.parent.mkdir(parents=True, exist_ok=True)

    for key in order:
        n = counts.get(key, 0)
        if n <= 0 or key not in builders:
            continue
        proto = _orient_v2(key, builders[key]())
        (stl_out / f"{key}.stl").write_bytes(proto.export(file_type="stl"))

    lines = ["Коннекторы сарая v2 (без резки):", ""]
    for k in order:
        n = counts.get(k, 0)
        if n:
            lines.append(f"  {labels.get(k, k)}: {n} шт.")
    qty_path.write_text("\n".join(lines), encoding="utf-8")

    parts: List[Tuple[str, int, trimesh.Trimesh]] = []
    idx = 0
    for key in order:
        n = counts.get(key, 0)
        if n <= 0:
            continue
        proto = _orient_v2(key, builders[key]())
        for _ in range(n):
            parts.append((key, idx, proto.copy()))
            idx += 1

    from bot.services.dacha_trellis_kit import _pack_parts_on_bed

    plates: List[trimesh.Scene] = []
    per = 6
    for start in range(0, len(parts), per):
        plates.append(_pack_parts_on_bed(parts[start : start + per]))

    paths: List[Path] = []
    for i, scene in enumerate(plates, start=1):
        p = plates_out / f"connectors-plate-{i}-of-{len(plates)}.3mf"
        data = scene.export(file_type="3mf")
        p.write_bytes(data if isinstance(data, (bytes, bytearray)) else bytes(data))
        paths.append(p)
    return paths


# --- IKEA-style step illustrations ---

@dataclass(frozen=True)
class IkeaStep:
    number: int
    title: str
    body: str
    parts: Tuple[Tuple[str, int], ...]  # (label, qty)
    connect: str = ""  # «Как соединять» — отдельный блок в PDF


def ikea_steps(spec: ShedNoCutSpec = DEFAULT_SHED_NOCUT) -> List[IkeaStep]:
    return [
        IkeaStep(
            1,
            "Разложите детали",
            "Проверьте палки по длине (1 / 1,5 / 2 м) и коннекторы. "
            "Резать профиль не нужно — только стыковать inline_splice.",
            (
                ("200 см", spec.stick_counts()[2000]),
                ("150 см", spec.stick_counts()[1500]),
                ("100 см", spec.stick_counts()[1000]),
                ("inline_splice", spec.inline_splice_count()),
                ("foot_base", spec.connector_counts()["foot_base"]),
            ),
        ),
        IkeaStep(
            2,
            "Опоры на фундамент",
            "На каждый угол и стойку — foot_base. Анкер M8 в блок 40×40. "
            "6 опор: 3 спереди, 3 сзади.",
            (("foot_base", 6), ("M8 анкер", 6)),
        ),
        IkeaStep(
            3,
            "Нижняя рама — перед",
            "Соедините 2×200 см через inline_splice. "
            "На концах corner_90. Положите на передние foot_base.",
            (("200 см", 2), ("inline_splice", 1), ("corner_90", 2)),
        ),
        IkeaStep(
            4,
            "Нижняя рама — зад и бока",
            "Зад: 2×200 см + стык. Бока: 200+100 см + стык ×2. "
            "Замкните прямоугольник 4×3 м. Диагонали равны.",
            (("200 см", 4), ("100 см", 2), ("inline_splice", 3), ("corner_90", 4)),
        ),
        IkeaStep(
            5,
            "Стойки фасада",
            "3× палки 200 см вертикально на переднюю раму. "
            "Углы — corner_post. Средняя — правый косяк двери.",
            (("200 см", 3), ("corner_post", 2), ("M5", 12)),
        ),
        IkeaStep(
            6,
            "Стойки задней стены",
            "3× палки 150 см на заднюю раму. Зад ниже — сюда стекает вода.",
            (("150 см", 3), ("M5", 12)),
        ),
        IkeaStep(
            7,
            "Раскосы",
            "brace_45 на каждую боковую стену (4 шт.). "
            "Ставить до обшивки — иначе каркас «качается».",
            (("brace_45", 4), ("150 см", 4)),
        ),
        IkeaStep(
            8,
            "Верхняя обвязка",
            "Перед: 2×200 см + стык на 200 см. Зад: то же на 150 см. "
            "Боковые скаты: 150+150 см + стык.",
            (("200 см", 4), ("150 см", 4), ("inline_splice", 4), ("tee_90", 4)),
        ),
        IkeaStep(
            9,
            "Дверной проём",
            "door_frame на углах. Над проёмом 2×100 см через lintel_splice (двойной ригель). "
            "Проём 100×200 см.",
            (("door_frame", 4), ("100 см", 2), ("lintel_splice", 1)),
        ),
        IkeaStep(
            10,
            "Стропила",
            f"{spec.rafter_count_n}× (150+150 см + стык). rafter_seat на перед и зад. "
            "Шаг 100 см. Концы заходят в седло ~10 см.",
            (
                ("150 см", spec.rafter_count_n * 2),
                ("inline_splice", spec.rafter_count_n),
                ("rafter_seat", spec.rafter_count_n * 2),
            ),
        ),
        IkeaStep(
            11,
            "Обрешётка под лист",
            "girt_bracket на стены (2 ряда). Прогоны крыши: 2×200 см + стык, 3 шт. "
            "Шаг ~100 см.",
            (("girt_bracket", spec.connector_counts()["girt_bracket"]), ("200 см", 6)),
        ),
        IkeaStep(
            12,
            "Профлист",
            "Стены снизу вверх, нахлёст 1 волна. Крыша — от фасада назад. "
            "Саморез 5,5×25 в низ волны, шаг ≤30 см по краю.",
            (("профлист С10", 1), ("саморез", 250)),
        ),
    ]


def _iso_project(x: float, y: float, z: float) -> Tuple[float, float]:
    """Простая изометрия."""
    return (x - y) * 0.866, (x + y) * 0.5 - z


def _draw_stick(ax, p0, p1, color="#555", lw=4, label=None):
    x0, y0 = _iso_project(*p0)
    x1, y1 = _iso_project(*p1)
    ax.plot([x0, x1], [y0, y1], color=color, lw=lw, solid_capstyle="round")
    if label:
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, label, fontsize=8, ha="center", color=color)


def render_ikea_step_png(step: IkeaStep, spec: ShedNoCutSpec, path: Path) -> None:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_title(f"Шаг {step.number} — {step.title}", fontsize=13, fontweight="bold", pad=12)
    ax.axis("off")

    n = step.number
    L, D = spec.length_mm / 1000, spec.depth_mm / 1000
    fh = spec.front_height_mm / 1000
    bh = spec.back_height_mm / 1000

    title_l = step.title.lower()

    if n == 1 or "разлож" in title_l:
        ax.text(0.5, 0.85, "Комплектация", transform=ax.transAxes, ha="center", fontsize=14, fontweight="bold")
        y = 0.72
        for lbl, qty in step.parts:
            ax.text(0.15, y, f"  {lbl}", transform=ax.transAxes, fontsize=11)
            circ = mpatches.Circle((0.72, y + 0.01), 0.025, transform=ax.transAxes, fc="#c62828", ec="white", lw=2)
            ax.add_patch(circ)
            ax.text(0.72, y + 0.01, str(qty), transform=ax.transAxes, ha="center", va="center", color="white", fontsize=9, fontweight="bold")
            y -= 0.08
    elif "опор" in title_l:
        scale = 0.08
        ox, oy = -1.5, -0.5
        pts = [(0, 0), (L / 2, 0), (L, 0), (0, D), (L / 2, D), (L, D)]
        for (x0, y0), (x1, y1) in [
            ((0, 0), (L, 0)), ((L, 0), (L, D)), ((L, D), (0, D)), ((0, D), (0, 0)),
        ]:
            _draw_stick(ax, (ox + x0 * scale, oy + y0 * scale, 0), (ox + x1 * scale, oy + y1 * scale, 0), "#ccc", 3)
        for px, py in pts:
            cx, cy = _iso_project(ox + px * scale, oy + py * scale, 0)
            ax.add_patch(mpatches.RegularPolygon((cx, cy), numVertices=4, radius=0.08, fc="#ff9800", ec="#e65100"))
        ax.text(0, -1.2, f"квадрат {L:.0f}×{D:.0f} м", fontsize=9, ha="center")
    elif "периметр" in title_l or ("рама" in title_l and "верх" not in title_l and "ниж" not in title_l):
        scale = 0.08
        ox, oy = -1.5, -0.5
        for (x0, y0), (x1, y1) in [
            ((0, 0), (L, 0)), ((L, 0), (L, D)), ((L, D), (0, D)), ((0, D), (0, 0)),
        ]:
            _draw_stick(ax, (ox + x0 * scale, oy + y0 * scale, 0), (ox + x1 * scale, oy + y1 * scale, 0), "#1f77b4", 5)
        ax.text(0, -1.2, "150+150 см + стык на каждой стороне", fontsize=9, color="#1f77b4")
    elif "стойк" in title_l:
        count = 3 if L <= 3.5 else 3
        for i in range(count):
            x = i * 1.2
            _draw_stick(ax, (x, 0, 0), (x, 0, fh), "#1f77b4", 6, "200")
        ax.plot([-0.2, 2.6], [0, 0], "k-", lw=2)
        ax.text(1.0, -0.35, "СТОЙКИ 200 см", ha="center", fontweight="bold")
    elif "раскос" in title_l:
        _draw_stick(ax, (0, 0, 0), (0, 0, fh), "#1f77b4", 5)
        _draw_stick(ax, (0, 0, fh), (0.8, 0, 0.3), "#4caf50", 4, "45°")
        _draw_stick(ax, (0, 0, 0.3), (0.8, 0, fh - 0.2), "#4caf50", 3)
        ax.text(0.4, -0.4, "8× brace_45", ha="center", color="#4caf50", fontweight="bold")
    elif "верх" in title_l or "обвяз" in title_l:
        _draw_stick(ax, (0, 0, 0), (2.5, 0, 0), "#1f77b4", 4)
        _draw_stick(ax, (0, 0, 0), (0, 0, fh), "#1f77b4", 4)
        _draw_stick(ax, (2.5, 0, 0), (0, 1.5, bh), "#c62828", 3)
        ax.text(1.2, 0.5, f"перед {int(fh*100)} → зад {int(bh*100)} см", fontsize=10, ha="center")
    elif "двер" in title_l:
        ax.add_patch(mpatches.Rectangle((0.3, 0.1), 1.0, 1.6, fill=False, lw=3, ec="#8B4513"))
        ax.add_patch(mpatches.Rectangle((0.25, 1.65), 1.1, 0.12, fc="#795548"))
        ax.text(0.8, 0.9, "дверь", ha="center", fontsize=12, color="#8B4513")
        ax.text(0.8, 1.85, "2×100 ригель", ha="center", fontsize=9)
    elif "строп" in title_l:
        _draw_stick(ax, (0, 0, fh), (1.5, 0, bh), "#c62828", 5)
        _draw_stick(ax, (0.5, 0, fh), (2.0, 0, bh), "#c62828", 5)
        ax.text(1.0, 0.2, "150+150 + стык", ha="center", fontweight="bold")
    elif "обреш" in title_l or "прогон" in title_l:
        for z in [0.4, 0.9, 1.4]:
            _draw_stick(ax, (0, 0, z), (2, 0, z), "#607d8b", 3)
        _draw_stick(ax, (0, 0, 0), (0, 0, 1.6), "#1f77b4", 4)
        ax.text(1.0, -0.35, "girt + прогоны", ha="center")
    elif "профлист" in title_l:
        ax.add_patch(mpatches.Polygon([[0, 0.2], [2.2, 0.2], [2.0, 1.5], [0.2, 1.3]], closed=True, fc="#90a4ae", ec="#455a64", lw=2))
        ax.text(1.1, 0.8, "профлист", ha="center", fontsize=12, fontweight="bold", color="white")
    else:
        ax.text(0.5, 0.5, step.title, transform=ax.transAxes, ha="center", fontsize=12)

    # parts legend (IKEA circles)
    ax.text(0.02, 0.02, "Детали:", transform=ax.transAxes, fontsize=9, fontweight="bold")
    lx = 0.02
    ly = -0.06
    for i, (lbl, qty) in enumerate(step.parts[:5]):
        circ = mpatches.Circle((lx + 0.04, ly), 0.018, transform=ax.transAxes, fc="#c62828", ec="white", lw=1.5)
        ax.add_patch(circ)
        ax.text(lx + 0.04, ly, str(qty), transform=ax.transAxes, ha="center", va="center", color="white", fontsize=7, fontweight="bold")
        ax.text(lx + 0.09, ly - 0.008, lbl, transform=ax.transAxes, fontsize=8)
        ly -= 0.055

    ax.text(0.5, -0.18, step.body, transform=ax.transAxes, ha="center", fontsize=9, wrap=True,
            bbox=dict(boxstyle="round", facecolor="#fff9c4", edgecolor="#fbc02d"))

    ax.set_xlim(-2, 3)
    ax.set_ylim(-1.5, 2.5)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def build_shed_nocut_text_pdf(spec: ShedNoCutSpec = DEFAULT_SHED_NOCUT) -> bytes:
    """Текстовая инструкция v2 (без резки)."""
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(14, 14, 14)
    bf, bb, uni = _pdf_fonts(pdf)
    w = pdf.w - 28
    loads = spec.load_summary()

    def txt(s: str, size: int = 11, bold: bool = False) -> None:
        pdf.set_font(bb if bold else bf, size=size)
        t = s.replace("\r", "")
        if uni:
            pdf.multi_cell(w, size * 0.42, t)
        else:
            pdf.multi_cell(w, size * 0.42, t.encode("latin-1", "replace").decode("latin-1"))
        pdf.ln(0.5)

    pdf.add_page()
    txt(f"{spec.name} — инструкция v2", 16, bold=True)
    txt("Профиль 20×20×2. Только палки 100 / 150 / 200 см. Резка не требуется.", 10)
    pdf.ln(2)
    txt("Габариты", 13, bold=True)
    txt(
        f"• План {spec.length_mm/10:.0f}×{spec.depth_mm/10:.0f} см\n"
        f"• Фасад {spec.front_height_mm/10:.0f} см, зад {spec.back_height_mm/10:.0f} см\n"
        f"• Уклон {spec.pitch_deg:.1f}° (сток на зад)\n"
        f"• Дверь {spec.door_width_mm/10:.0f}×{spec.door_height_mm/10:.0f} см\n"
        f"• Стропило по скату: 150+150 см + стык",
        11,
    )
    pdf.ln(1)
    txt("Палки (складские длины)", 13, bold=True)
    sc = spec.stick_counts()
    txt(f"  200 см: {sc[2000]} шт.\n  150 см: {sc[1500]} шт.\n  100 см: {sc[1000]} шт.", 11)
    txt(f"  inline_splice (стык): {spec.inline_splice_count()} шт.", 11)
    pdf.ln(1)
    txt("Сборные балки", 13, bold=True)
    for b in spec.beam_list():
        txt(f"  {b.describe()}", 10)
    pdf.ln(1)
    txt("Нагрузки", 13, bold=True)
    txt(
        f"Крыша ~{loads['roof_area_m2']} m², ~{loads['roof_load_kn']*100:.0f} kg. "
        f"На стойку ~{loads['post_load_kn']*100:.0f} kg. Раскосы обязательны.",
        11,
    )
    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")


def build_shed_ikea_pdf(
    spec: ShedNoCutSpec = DEFAULT_SHED_NOCUT,
    step_images_dir: Path | None = None,
    steps: List[IkeaStep] | None = None,
) -> bytes:
    from fpdf import FPDF

    if step_images_dir is None:
        step_images_dir = Path("/tmp/shed-ikea-steps")
    step_images_dir.mkdir(parents=True, exist_ok=True)

    if steps is None:
        steps = ikea_steps(spec)
    for st in steps:
        render_ikea_step_png(st, spec, step_images_dir / f"step_{st.number:02d}.png")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(12, 12, 12)
    bf, bb, uni = _pdf_fonts(pdf)
    w = pdf.w - 24

    def txt(s: str, size: int = 11, bold: bool = False) -> None:
        pdf.set_font(bb if bold else bf, size=size)
        t = s.replace("\r", "")
        if uni:
            pdf.multi_cell(w, size * 0.42, t)
        else:
            pdf.multi_cell(w, size * 0.42, t.encode("latin-1", "replace").decode("latin-1"))

    # cover
    pdf.add_page()
    txt("Сборка хозблока", 20, bold=True)
    txt(spec.name, 14, bold=True)
    txt("Инструкция IKEA — по шагам с картинками", 12)
    pdf.ln(4)
    txt("Инструмент: ключ 8/10, отвёртка, уровень, маркер, дрель.", 11)
    txt("Время каркаса: 1–2 дня. Обшивка: +1 день.", 11)
    sc = spec.stick_counts()
    pdf.ln(2)
    txt("В коробке профиля:", 12, bold=True)
    txt(f"200 см × {sc[2000]}   |   150 см × {sc[1500]}   |   100 см × {sc[1000]}", 11)

    for st in steps:
        pdf.add_page()
        img = step_images_dir / f"step_{st.number:02d}.png"
        pdf.set_font(bb, size=16)
        if uni:
            pdf.cell(0, 10, f"Шаг {st.number}  {st.title}", ln=True)
        pdf.ln(2)
        if img.exists():
            pdf.image(str(img), x=12, y=pdf.get_y(), w=186)
            pdf.ln(118)
        txt(st.body, 10)

    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")


def build_shed_nocut_archive(
    out_dir: Path,
    spec: ShedNoCutSpec,
    *,
    steps_fn=ikea_steps,
    avito_tagline: str = "",
) -> Path:
    from bot.services.dacha_shed_pack_layout import ShedPackDirs, write_pack_readme, write_pechat_txt

    dirs = ShedPackDirs.create(out_dir)
    write_pack_readme(dirs, kit_name=spec.name)
    write_pechat_txt(dirs)

    ikea_dir = dirs.instrukcii / "ikea-steps-png"
    steps = steps_fn(spec)

    (dirs.instrukcii / "instrukciya.pdf").write_bytes(build_shed_nocut_text_pdf(spec))
    (dirs.instrukcii / "instrukciya-IKEA.pdf").write_bytes(build_shed_ikea_pdf(spec, ikea_dir, steps=steps))

    legacy = spec.to_legacy_spec()
    render_shed_scheme_png(legacy, dirs.instrukcii / "schema-plan-razrez.png")

    sc = spec.stick_counts()
    (dirs.tehnika / "profil-bez-rezki.txt").write_text(
        "Профиль — только складские длины (без резки)\n"
        + "=" * 45
        + "\n\n"
        + f"200 см: {sc[2000]} шт.\n"
        + f"150 см: {sc[1500]} шт.\n"
        + f"100 см: {sc[1000]} шт.\n\n"
        + f"Стыки inline_splice: {spec.inline_splice_count()} шт.\n\n"
        + "Сборные балки:\n"
        + "\n".join(f"  {b.describe()}" for b in spec.beam_list())
        + "\n",
        encoding="utf-8",
    )

    loads = spec.load_summary()
    (dirs.tehnika / "nagruzki.txt").write_text(
        f"Уклон: {loads['pitch_deg']} deg\n"
        f"Крыша: {loads['roof_area_m2']} m2\n"
        f"На стойку: ~{loads['post_load_kn']*100:.0f} kg\n",
        encoding="utf-8",
    )

    if hasattr(spec, "stability_text"):
        (dirs.tehnika / "ustoychivost.txt").write_text(spec.stability_text(), encoding="utf-8")  # type: ignore[attr-defined]

    tag = f" {avito_tagline}" if avito_tagline else ""
    (dirs.prodazha / "avito.txt").write_text(
        f"Хозблок {spec.length_mm/10:.0f}×{spec.depth_mm/10:.0f} м — каркас под профлист.\n"
        f"Без резки: палки 1 / 1,5 / 2 м + стыковые коннекторы.\n"
        f"2 PDF: обычная + IKEA пошагово с картинками.\n"
        f"200 см×{sc[2000]}, 150 см×{sc[1500]}, 100 см×{sc[1000]}.{tag}\n"
        f"Solnechnogorsk, доставка МО.",
        encoding="utf-8",
    )

    export_shed_v2_connectors(
        out_dir,
        spec,
        stl_dir=dirs.pechat_stl,
        plates_dir=dirs.pechat_3mf,
        quantities_path=dirs.pechat / "print_quantities.txt",
    )

    zip_path = out_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(out_dir.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(out_dir.parent))
    return zip_path


def build_shed_v2_archive(out_dir: Path, spec: ShedNoCutSpec = DEFAULT_SHED_NOCUT) -> Path:
    return build_shed_nocut_archive(out_dir, spec)
