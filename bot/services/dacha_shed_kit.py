"""Сарай 3×4 м — односкатная крыша, профиль 20×20×2, печатные коннекторы, профлист."""

from __future__ import annotations

import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import trimesh

from bot.services.dacha_trellis_kit import (
    CONNECTOR_LABELS_RU as BASE_LABELS,
    CONNECTOR_ORDER as BASE_ORDER,
    SOCKET_DEPTH_MM,
    WALL_MM,
    _add_bolt_hole,
    _arm_along,
    _bool_union,
    _box,
    build_bracket_rung,
    build_corner_90,
    build_foot_base,
    build_corner_post,
    _orient_for_print,
    OUTER_MM,
)

# --- геометрия сарая ---

DEFAULT_LENGTH_MM = 4000.0   # фасад (дверь)
DEFAULT_DEPTH_MM = 3000.0    # глубина, направление стока воды
DEFAULT_FRONT_H_MM = 2400.0
DEFAULT_PITCH_DEG = 15.0
DEFAULT_DOOR_W = 900.0
DEFAULT_DOOR_H = 2000.0
DEFAULT_DOOR_LEFT = 500.0    # от левого угла фасада


@dataclass(frozen=True)
class ShedSpec:
    """Хозблок 3×4, односкат: высокий фасад — дверь, низкий зад — сток."""

    name: str = "Хозблок 3×4 односкат"
    length_mm: float = DEFAULT_LENGTH_MM
    depth_mm: float = DEFAULT_DEPTH_MM
    front_height_mm: float = DEFAULT_FRONT_H_MM
    pitch_deg: float = DEFAULT_PITCH_DEG
    door_width_mm: float = DEFAULT_DOOR_W
    door_height_mm: float = DEFAULT_DOOR_H
    door_offset_left_mm: float = DEFAULT_DOOR_LEFT
    window_width_mm: float = 600.0
    window_height_mm: float = 600.0
    window_offset_from_back_mm: float = 800.0
    window_sill_mm: float = 1000.0
    girt_spacing_mm: float = 800.0
    rafter_spacing_mm: float = 1000.0
    purlin_spacing_mm: float = 800.0

    @property
    def pitch_rad(self) -> float:
        return math.radians(self.pitch_deg)

    @property
    def rise_mm(self) -> float:
        return self.depth_mm * math.tan(self.pitch_rad)

    @property
    def back_height_mm(self) -> float:
        return self.front_height_mm - self.rise_mm

    @property
    def rafter_length_mm(self) -> float:
        return self.depth_mm / math.cos(self.pitch_rad)

    @property
    def roof_slope_length_mm(self) -> float:
        return self.rafter_length_mm

    @property
    def roof_area_m2(self) -> float:
        return (self.length_mm * self.rafter_length_mm) / 1_000_000.0

    @property
    def wall_sheet_area_m2(self) -> float:
        avg_h = (self.front_height_mm + self.back_height_mm) / 2.0
        perim = 2.0 * (self.length_mm + self.depth_mm)
        return (perim * avg_h) / 1_000_000.0

    def rafter_count(self) -> int:
        return int(self.length_mm / self.rafter_spacing_mm) + 1

    def purlin_count_per_slope(self) -> int:
        return int(self.rafter_length_mm / self.purlin_spacing_mm) + 1

    def front_post_x_mm(self) -> Tuple[float, ...]:
        """Стойки фасада: углы + правый косяк двери."""
        d1 = self.door_offset_left_mm
        d2 = d1 + self.door_width_mm
        return (0.0, d2, self.length_mm)

    def back_post_x_mm(self) -> Tuple[float, ...]:
        return (0.0, self.length_mm / 2.0, self.length_mm)

    def girt_rows_front(self) -> int:
        return max(2, int(self.front_height_mm / self.girt_spacing_mm) + 1)

    def girt_rows_back(self) -> int:
        return max(2, int(self.back_height_mm / self.girt_spacing_mm) + 1)

    def profile_cut_list(self) -> List[Tuple[str, float, int]]:
        """Маркировка, длина мм, кол-во."""
        L = self.length_mm
        D = self.depth_mm
        rl = round(self.rafter_length_mm)
        sl = round(self.rafter_length_mm)  # боковой верхний скат
        parts: List[Tuple[str, float, int]] = []

        # Стойки
        n_front = len(self.front_post_x_mm())
        n_back = len(self.back_post_x_mm())
        parts.append(("СТ-Ф (фасад)", self.front_height_mm, n_front))
        parts.append(("СТ-З (зад)", round(self.back_height_mm), n_back))

        # Нижняя обвязка
        parts.append(("НИЗ-Ф", L, 1))
        parts.append(("НИЗ-З", L, 1))
        parts.append(("НИЗ-Б", D, 2))

        # Верхняя обвязка
        parts.append(("ВЕРХ-Ф", L, 1))
        parts.append(("ВЕРХ-З", L, 1))
        parts.append(("СКАТ-Б", sl, 2))

        # Стропила
        parts.append(("СТР", rl, self.rafter_count()))

        # Обрешётка стен (girt) — оценка
        girt_len_side = D
        girt_front = self.girt_rows_front() * 2  # л+п по фасаду не — только горизонтали фасада
        parts.append(("GIRT-Ф", L, self.girt_rows_front()))
        parts.append(("GIRT-З", L, self.girt_rows_back()))
        parts.append(("GIRT-Б", girt_len_side, self.girt_rows_front() + self.girt_rows_back()))

        # Обрешётка крыши (прогоны)
        parts.append(("ПРОГ", L, self.purlin_count_per_slope()))

        # Дверной ригель (двойной = 2 профиля)
        parts.append(("РИГ-Д", self.door_width_mm, 2))
        # Окно — ригель + подоконник
        parts.append(("РИГ-О", self.window_width_mm, 1))
        parts.append(("ПОД-О", self.window_width_mm, 1))

        return parts

    def total_profile_mm(self) -> float:
        return sum(l * q for _, l, q in self.profile_cut_list())

    def sticks_200cm(self) -> float:
        return self.total_profile_mm() / 2000.0

    def connector_counts(self) -> Dict[str, int]:
        n_rafter = self.rafter_count()
        n_girt = (
            self.girt_rows_front()
            + self.girt_rows_back()
            + (self.girt_rows_front() + self.girt_rows_back()) * 2
        )
        return {
            "foot_base": len(self.front_post_x_mm()) + len(self.back_post_x_mm()),
            "corner_90": 8,
            "corner_post": 4,
            "bracket_rung": 0,
            "tee_90": 6,
            "rafter_seat": n_rafter * 2,
            "girt_bracket": n_girt,
            "brace_45": 4,
            "door_frame": 4,
            "lintel_splice": 2,
            "hook": 0,
        }

    def bolt_m5_count(self) -> int:
        return sum(self.connector_counts().values()) * 2 + 20

    def bolt_m6_count(self) -> int:
        return self.rafter_count() * 2 + 8

    def load_summary(self) -> Dict[str, float]:
        """Упрощённые нагрузки, МО."""
        snow_knm2 = 1.5  # kN/m² ≈ 150 kg/m²
        dead_knm2 = 0.05
        total_knm2 = snow_knm2 + dead_knm2
        roof_kn = total_knm2 * self.roof_area_m2
        posts = len(self.front_post_x_mm()) + len(self.back_post_x_mm())
        per_post_kn = roof_kn / posts if posts else 0.0
        wind_knm2 = 0.6
        return {
            "roof_area_m2": round(self.roof_area_m2, 2),
            "wall_sheet_m2": round(self.wall_sheet_area_m2, 1),
            "roof_load_kn": round(roof_kn, 2),
            "post_load_kn": round(per_post_kn, 2),
            "pitch_deg": self.pitch_deg,
            "back_height_mm": round(self.back_height_mm),
            "wind_knm2": wind_knm2,
        }


DEFAULT_SHED = ShedSpec()


# --- доп. коннекторы сарая ---

def build_tee_90() -> trimesh.Trimesh:
    """T-узел: три гильзы (+X +Y +Z)."""
    mesh = _bool_union([_arm_along("x"), _arm_along("y"), _arm_along("z")])
    return _add_bolt_hole(mesh, "y")


def build_rafter_seat() -> trimesh.Trimesh:
    """Седло: стойка +Z, стропило +X (как кronштейн перемычки)."""
    return build_bracket_rung()


def build_girt_bracket() -> trimesh.Trimesh:
    return build_bracket_rung()


def build_brace_45() -> trimesh.Trimesh:
    """Раскос: стойка +Z и плечо под ~45°."""
    arm_z = _arm_along("z")
    arm = _arm_along("x")
    r = trimesh.transformations.rotation_matrix(math.pi / 4, [0, 0, 1])
    arm.apply_transform(r)
    arm.apply_translation([0.0, 0.0, SOCKET_DEPTH_MM * 0.45])
    mesh = _bool_union([arm_z, arm])
    return _add_bolt_hole(mesh, "y")


def build_door_frame() -> trimesh.Trimesh:
    """Усиленный угол проёма двери."""
    corner = build_corner_90()
    pad = _box((OUTER_MM + 10, OUTER_MM + 10, WALL_MM + 2), (0.0, 0.0, 2.0))
    mesh = _bool_union([corner, pad])
    return _add_bolt_hole(mesh, "y")


def build_lintel_splice() -> trimesh.Trimesh:
    """Соединитель двойного ригеля (два профиля рядом)."""
    a1 = _arm_along("x")
    a2 = _arm_along("x")
    a2.apply_translation([0.0, OUTER_MM + 3.0, 0.0])
    tie = _box((SOCKET_DEPTH_MM, OUTER_MM + 8, OUTER_MM), (SOCKET_DEPTH_MM * 0.5, 0.0, 0.0))
    mesh = _bool_union([a1, a2, tie])
    return _add_bolt_hole(mesh, "y")


SHED_CONNECTOR_BUILDERS = {
    "foot_base": build_foot_base,
    "corner_90": build_corner_90,
    "corner_post": build_corner_post,
    "bracket_rung": build_bracket_rung,
    "tee_90": build_tee_90,
    "rafter_seat": build_rafter_seat,
    "girt_bracket": build_girt_bracket,
    "brace_45": build_brace_45,
    "door_frame": build_door_frame,
    "lintel_splice": build_lintel_splice,
}

SHED_CONNECTOR_ORDER = (
    "foot_base",
    "corner_90",
    "corner_post",
    "tee_90",
    "rafter_seat",
    "girt_bracket",
    "brace_45",
    "door_frame",
    "lintel_splice",
)

SHED_CONNECTOR_LABELS = {
    **BASE_LABELS,
    "tee_90": "T-узел 90° (3 гильзы)",
    "rafter_seat": "Седло стропила",
    "girt_bracket": "Кронштейн обрешётки (girt)",
    "brace_45": "Раскос 45°",
    "door_frame": "Угол проёма двери (усил.)",
    "lintel_splice": "Соединитель двойного ригеля",
}


def _orient_shed(key: str, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    if key in SHED_CONNECTOR_BUILDERS and key not in BASE_ORDER:
        m = mesh.copy()
        if key in ("tee_90", "corner_post", "corner_90", "door_frame"):
            m.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
        elif key in ("rafter_seat", "girt_bracket", "lintel_splice"):
            m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
        elif key == "brace_45":
            pass
        m.apply_translation([0.0, 0.0, -float(m.bounds[0][2])])
        return m
    return _orient_for_print(key, mesh)


def export_shed_connectors(out_dir: Path, spec: ShedSpec = DEFAULT_SHED) -> List[Path]:
    counts = spec.connector_counts()
    out_dir.mkdir(parents=True, exist_ok=True)
    for key in SHED_CONNECTOR_ORDER:
        n = counts.get(key, 0)
        if n <= 0 or key not in SHED_CONNECTOR_BUILDERS:
            continue
        proto = _orient_shed(key, SHED_CONNECTOR_BUILDERS[key]())
        (out_dir / f"{key}.stl").write_bytes(proto.export(file_type="stl"))
    lines = ["Коннекторы сарая:", ""]
    for k in SHED_CONNECTOR_ORDER:
        n = counts.get(k, 0)
        if n:
            lines.append(f"  {SHED_CONNECTOR_LABELS.get(k, k)}: {n} шт.")
    (out_dir / "print_quantities.txt").write_text("\n".join(lines), encoding="utf-8")

    parts: List[Tuple[str, int, trimesh.Trimesh]] = []
    idx = 0
    for key in SHED_CONNECTOR_ORDER:
        n = counts.get(key, 0)
        if n <= 0:
            continue
        proto = _orient_shed(key, SHED_CONNECTOR_BUILDERS[key]())
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
        p = out_dir / f"connectors-plate-{i}-of-{len(plates)}.3mf"
        data = scene.export(file_type="3mf")
        p.write_bytes(data if isinstance(data, (bytes, bytearray)) else bytes(data))
        paths.append(p)
    return paths


def _pdf_fonts(pdf) -> Tuple[str, str, bool]:
    font_r = "/System/Library/Fonts/Supplemental/Arial.ttf"
    font_b = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    try:
        pdf.add_font("Ar", "", font_r)
        pdf.add_font("ArB", "", font_b)
        return "Ar", "ArB", True
    except Exception:
        return "Helvetica", "Helvetica", False


def build_shed_pdf(spec: ShedSpec = DEFAULT_SHED) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=14)
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

    def title(t: str) -> None:
        pdf.add_page()
        txt(t, 15, bold=True)
        pdf.ln(2)

    # стр 1
    title(f"{spec.name} — комплект и габариты")
    txt(
        "Профиль: сталь/алюминий 20×20×2 мм. Односкатная крыша: высокий фасад (дверь), "
        "низкий зад — вода и снег уходят назад. Обшивка: профлист С10 на обрешётку.",
        9,
    )
    pdf.ln(1)
    txt("Габариты", 13, bold=True)
    txt(
        f"• В плане: {spec.length_mm/10:.0f}×{spec.depth_mm/10:.0f} см (фасад × глубина)\n"
        f"• Фасад (перед): {spec.front_height_mm/10:.0f} см\n"
        f"• Зад: {loads['back_height_mm']/10:.0f} см\n"
        f"• Уклон крыши: {spec.pitch_deg:.0f}°\n"
        f"• Длина стропила: {spec.rafter_length_mm/10:.1f} см\n"
        f"• Дверь: {spec.door_width_mm/10:.0f}×{spec.door_height_mm/10:.0f} см, "
        f"отступ от левого угла {spec.door_offset_left_mm/10:.0f} см\n"
        f"• Окно: {spec.window_width_mm/10:.0f}×{spec.window_height_mm/10:.0f} см "
        f"на правом боку, подоконник {spec.window_sill_mm/10:.0f} см",
        11,
    )
    pdf.ln(1)
    txt("Нарезка профиля", 13, bold=True)
    for mark, length, qty in spec.profile_cut_list():
        txt(f"  {mark}: {qty} × {length/10:.1f} см", 10)
    txt(f"Итого: {spec.total_profile_mm()/1000:.1f} п.м. (~{spec.sticks_200cm():.1f} палок по 200 см)", 10)

    # стр 2 нагрузки
    title("Нагрузки и прочность (упрощённо, МО)")
    txt(
        f"• Площадь крыши: {loads['roof_area_m2']} м²\n"
        f"• Снег + лист: ~155 kg/m² → на крышу ~{loads['roof_load_kn']*100:.0f} kg "
        f"({loads['roof_load_kn']:.2f} kN)\n"
        f"• На стойку (~{len(spec.front_post_x_mm())+len(spec.back_post_x_mm())} шт.): "
        f"~{loads['post_load_kn']*100:.0f} kg ({loads['post_load_kn']:.2f} kN)\n"
        f"• Ветер на стену: до ~{loads['wind_knm2']} kN/m² — обязательны раскосы brace_45\n"
        f"• Уклон {spec.pitch_deg:.0f}° — компромисс для Подмосковья (не копить снег)\n\n"
        "Рекомендации:\n"
        "— Ригель над дверью — двойной профиль (lintel_splice + 2× РИГ-Д)\n"
        "— Петли двери крепить к стальному профилю, не к пластику\n"
        "— foot_base + анкер M8 в блоки/ленту\n"
        "— Саморезы в лист: шаг ≤300 мм по краю, ≤1000 мм в поле",
        11,
    )

    # стр 3 коннекторы
    title("Коннекторы и крепёж")
    for k in SHED_CONNECTOR_ORDER:
        n = spec.connector_counts().get(k, 0)
        if n:
            txt(f"  {SHED_CONNECTOR_LABELS.get(k, k)}: {n} шт.", 10)
    txt(f"• M5×16 nylock: ~{spec.bolt_m5_count()} шт.", 11)
    txt(f"• M6×25 (стропила, ригели): ~{spec.bolt_m6_count()} шт.", 11)
    txt("• Профлист С10 ~0,5 мм: ~35–40 м² с запасом", 11)
    txt("• Саморезы кровельные 4,8×19 … 5,5×25: ~250 шт.", 11)

    # стр 4 сборка
    title("Порядок сборки")
    steps = [
        (
            "1. Фундамент",
            "6 блоков 40×40 или лента. Разметка 4×3 м. Анкер M8 через foot_base.",
        ),
        (
            "2. Нижняя обвязка",
            "НИЗ-Ф/З/Б на foot_base и corner_90. Проверить диагонали (равны).",
        ),
        (
            "3. Стойки",
            "СТ-Ф на фасад (3 шт.), СТ-З на зад (3 шт.). corner_post на углах.",
        ),
        (
            "4. Раскосы",
            "brace_45 на боковых стенах до обшивки — жёсткость на ветер.",
        ),
        (
            "5. Верхняя обвязка",
            "ВЕРХ-Ф на 240 см, ВЕРХ-З на ~160 см, СКАТ-Б по бокам (наклон). tee_90 на стыках.",
        ),
        (
            "6. Дверной проём",
            "door_frame на углах проёма. РИГ-Д ×2 через lintel_splice на высоте 200 см.",
        ),
        (
            "7. Стропила",
            f"{spec.rafter_count()}× СТР на rafter_seat (перед + зад), шаг {spec.rafter_spacing_mm/10:.0f} см.",
        ),
        (
            "8. Прогоны",
            f"ПРОГ поперёк ската, шаг {spec.purlin_spacing_mm/10:.0f} см. girt_bracket на стенах.",
        ),
        (
            "9. Окно",
            "РИГ-О + ПОД-О на правом боку. Обрамление профилем.",
        ),
        (
            "10. Профлист",
            "Стены: снизу вверх, нахлёст 1 волна. Крыша: от фасада назад, "
            "саморезы в низ волны. Конёк — прижимная планка.",
        ),
    ]
    for t, b in steps:
        txt(t, 12, bold=True)
        txt(b, 10)
        pdf.ln(1)
    txt("Время: 2–3 дня с обшивкой. Каркас за 1 день.", 10)

    # стр 5 печать
    title("Печать коннекторов (Bambu P2S)")
    txt("PETG / PETG-CF. Стенки 4, infill 50 %, узлы foot/door/rafter — 60 %.", 11)
    txt("Файлы connectors-plate-*-of-*.3mf — печатать по очереди.", 11)

    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")


def render_shed_scheme_png(spec: ShedSpec, path: Path) -> None:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(
        f"{spec.name} — схема\n"
        f"уклон {spec.pitch_deg:.0f}°, дверь на фасаде, сток на зад",
        fontsize=13,
        fontweight="bold",
    )

    # plan
    ax = axes[0]
    ax.set_title("План (вид сверху)", fontweight="bold")
    ax.set_aspect("equal")
    L, D = spec.length_mm / 1000, spec.depth_mm / 1000
    ax.add_patch(mpatches.Rectangle((0, 0), L, D, fill=False, lw=2, ec="#333"))
    ax.text(L / 2, -0.15, "ФАСАД (дверь)", ha="center", fontweight="bold")
    ax.text(L / 2, D + 0.12, "ЗАД (низкая стена)", ha="center", fontsize=9)
    dx1 = spec.door_offset_left_mm / 1000
    dx2 = (spec.door_offset_left_mm + spec.door_width_mm) / 1000
    ax.add_patch(mpatches.Rectangle((dx1, -0.02), dx2 - dx1, 0.04, fc="#8B4513"))
    ax.text((dx1 + dx2) / 2, 0.08, "дверь", ha="center", fontsize=8)
    for x in spec.front_post_x_mm():
        ax.plot(x / 1000, 0, "s", color="#1f77b4", ms=8)
    for x in spec.back_post_x_mm():
        ax.plot(x / 1000, D, "s", color="#1f77b4", ms=8)
    ax.annotate("", xy=(L + 0.15, 0), xytext=(L + 0.15, D), arrowprops=dict(arrowstyle="->", color="#00796b", lw=2))
    ax.text(L + 0.25, D / 2, "сток\nводы", fontsize=8, color="#00796b")
    ax.set_xlim(-0.3, L + 0.5)
    ax.set_ylim(-0.35, D + 0.35)
    ax.axis("off")

    # side section
    ax2 = axes[1]
    ax2.set_title("Разрез (бок)", fontweight="bold")
    ax2.set_aspect("equal")
    fh = spec.front_height_mm / 1000
    bh = spec.back_height_mm / 1000
    ax2.plot([0, 0], [0, fh], "b-", lw=3)
    ax2.plot([D, D], [0, bh], "b-", lw=3)
    ax2.plot([0, D], [fh, bh], "r-", lw=2.5)
    ax2.plot([0, D], [0, 0], "k-", lw=2)
    ax2.fill([0, D, D, 0], [0, 0, bh, fh], color="#e3f2fd", alpha=0.4)
    ax2.text(-0.15, fh / 2, f"{spec.front_height_mm/10:.0f} см", fontsize=9)
    ax2.text(D + 0.08, bh / 2, f"{spec.back_height_mm/10:.0f} см", fontsize=9)
    ax2.annotate("", xy=(-0.25, 0), xytext=(-0.25, fh), arrowprops=dict(arrowstyle="<->", color="#333"))
    ax2.text(D / 2, fh + 0.12, f"уклон {spec.pitch_deg:.0f}°", ha="center", fontweight="bold")
    ax2.text(D / 2, -0.12, f"{spec.depth_mm/10:.0f} см", ha="center")
    ax2.set_xlim(-0.5, D + 0.4)
    ax2.set_ylim(-0.25, fh + 0.35)
    ax2.axis("off")

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def build_avito_text(spec: ShedSpec = DEFAULT_SHED) -> str:
    loads = spec.load_summary()
    return (
        f"Каркас хозблока {spec.length_mm/10:.0f}×{spec.depth_mm/10:.0f} м под профлист.\n"
        f"Профиль 20×20×2, односкатная крыша {spec.pitch_deg:.0f}°.\n"
        f"В комплекте: нарезка ~{spec.total_profile_mm()/1000:.0f} п.м., "
        f"печатные коннекторы, PDF-сборка, болты.\n"
        f"Дверь {spec.door_width_mm/10:.0f} см, окно {spec.window_width_mm/10:.0f} см.\n"
        f"Сам сбор каркаса за 1 день. Профлист отдельно (~{loads['wall_sheet_m2']+loads['roof_area_m2']:.0f} м²).\n"
        f"Solnechnogorsk / доставка МО. ~{int(spec.sticks_200cm())} палок 200 см + пластик."
    )


def build_ekonomika_text(spec: ShedSpec = DEFAULT_SHED) -> str:
    sticks = spec.sticks_200cm()
    profile = sticks * (2500 / 9)
    plastic = sum(spec.connector_counts().values()) * 12
    bolts = spec.bolt_m5_count() * 3 + spec.bolt_m6_count() * 5
    cogs = profile + plastic + bolts + 500
    return (
        f"Себестоимость каркаса (ориентир):\n"
        f"  Профиль {sticks:.1f}×200 см: ~{profile:.0f} ₽\n"
        f"  Пластик PETG: ~{plastic:.0f} ₽\n"
        f"  Болты M5/M6: ~{bolts:.0f} ₽\n"
        f"  Упаковка: 500 ₽\n"
        f"  ИТОГО: ~{cogs:.0f} ₽\n"
        f"Продажа каркас (без листа): 28 000 – 38 000 ₽\n"
        f"С профлистом под ключ: 48 000 – 65 000 ₽"
    )


def build_shed_archive(out_dir: Path, spec: ShedSpec = DEFAULT_SHED) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "instrukciya.pdf").write_bytes(build_shed_pdf(spec))
    render_shed_scheme_png(spec, out_dir / "schema-plan-razrez.png")
    (out_dir / "avito.txt").write_text(build_avito_text(spec), encoding="utf-8")
    (out_dir / "ekonomika.txt").write_text(build_ekonomika_text(spec), encoding="utf-8")
    (out_dir / "rezka-profilya.txt").write_text(
        "Нарезка профиля 20×20\n"
        + "=" * 40
        + "\n"
        + "\n".join(
            f"{mark}: {qty} × {length/10:.1f} см"
            for mark, length, qty in spec.profile_cut_list()
        )
        + f"\n\nИтого: {spec.total_profile_mm()/1000:.2f} п.м.\n"
        f"Палок 200 см: ~{spec.sticks_200cm():.1f}\n",
        encoding="utf-8",
    )
    loads = spec.load_summary()
    (out_dir / "nagruzki.txt").write_text(
        f"Нагрузки (упрощённо)\n"
        f"Крыша: {loads['roof_area_m2']} m2, ~{loads['roof_load_kn']*100:.0f} kg\n"
        f"На стойку: ~{loads['post_load_kn']*100:.0f} kg\n"
        f"Уклон: {loads['pitch_deg']} deg\n"
        f"Задняя стена: {loads['back_height_mm']} mm\n",
        encoding="utf-8",
    )
    export_shed_connectors(out_dir, spec)

    zip_path = out_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(out_dir.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(out_dir.parent))
    return zip_path
