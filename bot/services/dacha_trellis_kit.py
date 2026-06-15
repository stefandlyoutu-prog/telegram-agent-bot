"""Набор «шпалера для дачи» — коннекторы 20×20, PDF, 3MF, текст Avito."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import trimesh

# Обычный квадратный профиль 20×20 мм (не v-slot)
PROFILE_NOMINAL_MM = 20.0
PROFILE_CLEARANCE_MM = 0.35  # зазор на люфт/окраску
PROFILE_INNER_MM = PROFILE_NOMINAL_MM + 2 * PROFILE_CLEARANCE_MM
SOCKET_DEPTH_MM = 28.0
WALL_MM = 3.5
OUTER_MM = PROFILE_INNER_MM + 2 * WALL_MM


@dataclass(frozen=True)
class TrellisSpec:
    """Шпалера «Тoma-2» — лестница 0,6 × 2,0 м."""

    name: str = "Томат-2"
    width_mm: float = 600.0
    height_mm: float = 2000.0
    post_count: int = 2
    horizontal_count: int = 5  # низ + 3 перемычки + верх
    rung_heights_mm: Tuple[float, ...] = (100.0, 500.0, 1000.0, 1500.0, 1900.0)

    def profile_cut_list(self) -> List[Tuple[str, float, int]]:
        """Маркировка, длина мм, количество."""
        w = self.width_mm
        h = self.height_mm
        return [
            ("СТ-В", h, 2),  # стойки вертикальные
            ("ПР-Г", w, self.horizontal_count),  # перемычки горизонтальные
        ]

    def total_profile_mm(self) -> float:
        w, h = self.width_mm, self.height_mm
        return 2 * h + self.horizontal_count * w

    def connector_counts(self) -> Dict[str, int]:
        return {
            "corner_90": 4,
            "bracket_rung": max(0, (self.horizontal_count - 2) * 2),
            "foot_base": 2,
        }

    def bolt_count(self) -> int:
        n = sum(self.connector_counts().values())
        return n * 2  # по 2× M5 на узел


DEFAULT_SPEC = TrellisSpec()


def _box(extents: Tuple[float, float, float], center: Tuple[float, float, float]) -> trimesh.Trimesh:
    m = trimesh.creation.box(extents=extents)
    m.apply_translation(center)
    return m


def _socket_void(depth: float = SOCKET_DEPTH_MM) -> trimesh.Trimesh:
    return _box(
        (PROFILE_INNER_MM, PROFILE_INNER_MM, depth + 2.0),
        (0.0, 0.0, depth * 0.5),
    )


def _bool_diff(a: trimesh.Trimesh, b: trimesh.Trimesh) -> trimesh.Trimesh:
    for engine in ("manifold", None):
        try:
            kw = {"engine": engine} if engine else {}
            out = trimesh.boolean.difference([a, b], **kw)
            if out is not None and len(out.vertices) > 0:
                return out
        except Exception:
            continue
    return a


def _bool_union(parts: List[trimesh.Trimesh]) -> trimesh.Trimesh:
    if len(parts) == 1:
        return parts[0]
    for engine in ("manifold", None):
        try:
            kw = {"engine": engine} if engine else {}
            out = trimesh.boolean.union(parts, **kw)
            if out is not None and len(out.vertices) > 0:
                return out
        except Exception:
            continue
    return trimesh.util.concatenate(parts)


def _arm_along(axis: str, depth: float = SOCKET_DEPTH_MM) -> trimesh.Trimesh:
    """Гильза под профиль вдоль axis ('x'|'y'|'z')."""
    o = OUTER_MM
    if axis == "z":
        solid = _box((o, o, depth), (0.0, 0.0, depth * 0.5))
    elif axis == "x":
        solid = _box((depth, o, o), (depth * 0.5, 0.0, 0.0))
    else:
        solid = _box((o, depth, o), (0.0, depth * 0.5, 0.0))
    void = _socket_void(depth)
    if axis == "x":
        r = trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0])
        void.apply_transform(r)
        void.apply_translation([depth * 0.5 - SOCKET_DEPTH_MM * 0.5, 0, 0])
    elif axis == "y":
        r = trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0])
        void.apply_transform(r)
        void.apply_translation([0, depth * 0.5 - SOCKET_DEPTH_MM * 0.5, 0])
    return _bool_diff(solid, void)


def _add_bolt_hole(mesh: trimesh.Trimesh, axis: str = "y") -> trimesh.Trimesh:
    """Сквозное отверстие Ø5.5 под M5."""
    r_hole = 2.75
    length = OUTER_MM + 4.0
    cyl = trimesh.creation.cylinder(r_hole, length, sections=16)
    if axis == "y":
        cyl.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    elif axis == "x":
        cyl.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    z_pos = SOCKET_DEPTH_MM * 0.55
    cyl.apply_translation([0.0, 0.0, z_pos])
    return _bool_diff(mesh, cyl)


def build_corner_90() -> trimesh.Trimesh:
    """Угол 90°: два плеча вдоль +X и +Y (профиль вставляется снаружи)."""
    arm_x = _arm_along("x")
    arm_y = _arm_along("y")
    mesh = _bool_union([arm_x, arm_y])
    mesh = _add_bolt_hole(mesh, "y")
    return mesh


def build_bracket_rung() -> trimesh.Trimesh:
    """Кронштейн перемычки: вертикальная гильза (+Z) + горизонтальная (+X)."""
    arm_z = _arm_along("z")
    arm_x = _arm_along("x")
    arm_x.apply_translation([0.0, 0.0, SOCKET_DEPTH_MM * 0.5])
    mesh = _bool_union([arm_z, arm_x])
    mesh = _add_bolt_hole(mesh, "y")
    return mesh


def build_foot_base() -> trimesh.Trimesh:
    """Опора: гильза +Z + расширенное основание."""
    arm = _arm_along("z")
    pad = _box((OUTER_MM + 16, OUTER_MM + 16, 4.0), (0.0, 0.0, -2.0))
    mesh = _bool_union([arm, pad])
    cyl = trimesh.creation.cylinder(3.0, 80.0, sections=12)
    cyl.apply_translation([0.0, 0.0, -42.0])
    mesh = _bool_diff(mesh, cyl)
    mesh = _add_bolt_hole(mesh, "y")
    return mesh


def build_corner_post() -> trimesh.Trimesh:
    """Угол с вертикальной стойкой: +X, +Y, +Z (грядка, каркасы)."""
    arm_z = _arm_along("z")
    arm_x = _arm_along("x")
    arm_y = _arm_along("y")
    arm_x.apply_translation([0.0, 0.0, SOCKET_DEPTH_MM * 0.5])
    arm_y.apply_translation([0.0, 0.0, SOCKET_DEPTH_MM * 0.5])
    mesh = _bool_union([arm_z, arm_x, arm_y])
    return _add_bolt_hole(mesh, "y")


def build_hook() -> trimesh.Trimesh:
    """Крюк для лопаты/граблей на стойку."""
    plate = _box((6.0, 22.0, 35.0), (0.0, 0.0, 17.5))
    lip = _box((6.0, 10.0, 12.0), (0.0, 16.0, 32.0))
    mesh = _bool_union([plate, lip])
    cyl = trimesh.creation.cylinder(2.5, 30.0, sections=12)
    cyl.apply_translation([0.0, 0.0, 17.5])
    return _bool_diff(mesh, cyl)


CONNECTOR_BUILDERS = {
    "corner_90": build_corner_90,
    "bracket_rung": build_bracket_rung,
    "foot_base": build_foot_base,
    "corner_post": build_corner_post,
    "hook": build_hook,
}

CONNECTOR_ORDER = ("corner_90", "bracket_rung", "foot_base", "corner_post", "hook")

CONNECTOR_LABELS_RU = {
    "corner_90": "Угол 90° (угловой)",
    "bracket_rung": "Кронштейн перемычки",
    "foot_base": "Опора / ножка",
    "corner_post": "Угол со стойкой (3D)",
    "hook": "Крюк для инвентаря",
}


def build_all_connectors() -> Dict[str, trimesh.Trimesh]:
    return {name: fn() for name, fn in CONNECTOR_BUILDERS.items()}


def _orient_for_print(key: str, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Ориентация под FDM + нижняя грань на Z=0 (стол)."""
    m = mesh.copy()
    if key in ("corner_90", "corner_post"):
        m.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    elif key == "bracket_rung":
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    elif key == "hook":
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    # foot_base — подошва уже снизу
    m.apply_translation([0.0, 0.0, -float(m.bounds[0][2])])
    return m


def _collect_oriented_parts_from_counts(
    counts: Dict[str, int],
) -> List[Tuple[str, int, trimesh.Trimesh]]:
    meshes = build_all_connectors()
    parts: List[Tuple[str, int, trimesh.Trimesh]] = []
    idx = 0
    for key in CONNECTOR_ORDER:
        n = counts.get(key, 0)
        if n <= 0 or key not in meshes:
            continue
        proto = _orient_for_print(key, meshes[key])
        for _ in range(n):
            parts.append((key, idx, proto.copy()))
            idx += 1
    return parts


def _collect_oriented_parts(spec: TrellisSpec) -> List[Tuple[str, int, trimesh.Trimesh]]:
    return _collect_oriented_parts_from_counts(spec.connector_counts())


def _pack_parts_on_bed(
    parts: List[Tuple[str, int, trimesh.Trimesh]],
    *,
    spacing_mm: float = 10.0,
    bed_mm: float = 256.0,
) -> trimesh.Scene:
    scene = trimesh.Scene()
    x = spacing_mm
    y = spacing_mm
    row_depth = 0.0
    for key, idx, copy in parts:
        sx, sy, _ = copy.extents
        if y + sy > bed_mm - spacing_mm:
            y = spacing_mm
            x += row_depth + spacing_mm
            row_depth = 0.0
        bx, by, bz = copy.bounds[0]
        copy.apply_translation([x - bx, y - by, -bz])
        scene.add_geometry(copy, geom_name=f"{key}_{idx}")
        y += sy + spacing_mm
        row_depth = max(row_depth, sx)
    return scene


def layout_print_plate(
    spec: TrellisSpec = DEFAULT_SPEC,
    *,
    spacing_mm: float = 10.0,
    bed_mm: float = 256.0,
) -> trimesh.Scene:
    """Все 12 деталей на одном столе P2S."""
    return _pack_parts_on_bed(
        _collect_oriented_parts(spec),
        spacing_mm=spacing_mm,
        bed_mm=bed_mm,
    )


def layout_print_plates_split(
    spec: TrellisSpec = DEFAULT_SPEC,
    *,
    per_plate: int = 6,
) -> List[trimesh.Scene]:
    """Разбивка на несколько столов (по умолчанию 6 + 6 деталей)."""
    parts = _collect_oriented_parts(spec)
    plates: List[trimesh.Scene] = []
    for start in range(0, len(parts), per_plate):
        chunk = parts[start : start + per_plate]
        plates.append(_pack_parts_on_bed(chunk))
    return plates


def export_connectors_3mf(path: Path, spec: TrellisSpec = DEFAULT_SPEC) -> None:
    scene = layout_print_plate(spec)
    data = scene.export(file_type="3mf")
    path.write_bytes(data if isinstance(data, (bytes, bytearray)) else bytes(data))


def export_connectors_3mf_split(
    out_dir: Path,
    spec: TrellisSpec = DEFAULT_SPEC,
    *,
    per_plate: int = 6,
) -> List[Path]:
    """Два (или более) 3MF — удобнее для Bambu, без «висящих» групп."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    plates = layout_print_plates_split(spec, per_plate=per_plate)
    for i, scene in enumerate(plates, start=1):
        p = out_dir / f"connectors-plate-{i}-of-{len(plates)}.3mf"
        data = scene.export(file_type="3mf")
        p.write_bytes(data if isinstance(data, (bytes, bytearray)) else bytes(data))
        paths.append(p)
    return paths


def layout_print_plates_split_counts(
    counts: Dict[str, int],
    *,
    per_plate: int = 6,
) -> List[trimesh.Scene]:
    parts = _collect_oriented_parts_from_counts(counts)
    plates: List[trimesh.Scene] = []
    for start in range(0, len(parts), per_plate):
        plates.append(_pack_parts_on_bed(parts[start : start + per_plate]))
    return plates


def export_connectors_3mf_split_counts(
    out_dir: Path,
    counts: Dict[str, int],
    *,
    per_plate: int = 6,
    name_prefix: str = "connectors-plate",
) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    plates = layout_print_plates_split_counts(counts, per_plate=per_plate)
    for i, scene in enumerate(plates, start=1):
        p = out_dir / f"{name_prefix}-{i}-of-{len(plates)}.3mf"
        data = scene.export(file_type="3mf")
        p.write_bytes(data if isinstance(data, (bytes, bytearray)) else bytes(data))
        paths.append(p)
    return paths


def export_connector_stls_for_counts(
    out_dir: Path, counts: Dict[str, int], *, title: str = "набор"
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    meshes = build_all_connectors()
    for key in CONNECTOR_ORDER:
        if counts.get(key, 0) <= 0 or key not in meshes:
            continue
        oriented = _orient_for_print(key, meshes[key])
        (out_dir / f"{key}.stl").write_bytes(oriented.export(file_type="stl"))
    lines = [f"Количество деталей ({title}):", ""]
    for k in CONNECTOR_ORDER:
        n = counts.get(k, 0)
        if n:
            lines.append(f"  {CONNECTOR_LABELS_RU[k]}: {n} шт.")
    (out_dir / "print_quantities.txt").write_text("\n".join(lines), encoding="utf-8")


def export_connector_stls(out_dir: Path, spec: TrellisSpec = DEFAULT_SPEC) -> None:
    export_connector_stls_for_counts(out_dir, spec.connector_counts(), title=spec.name)


def build_kit_pdf(spec: TrellisSpec = DEFAULT_SPEC) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)

    font_r = "/System/Library/Fonts/Supplemental/Arial.ttf"
    font_b = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    try:
        pdf.add_font("Ar", "", font_r)
        pdf.add_font("ArB", "", font_b)
        bf, bb = "Ar", "ArB"
        uni = True
    except Exception:
        bf, bb = "Helvetica", "Helvetica"
        uni = False

    w = pdf.w - 30

    def txt(s: str, size: int = 11, bold: bool = False, ln: bool = True) -> None:
        pdf.set_font(bb if bold else bf, size=size)
        t = s.replace("\r", "")
        if uni:
            pdf.multi_cell(w, size * 0.42, t)
        else:
            pdf.multi_cell(w, size * 0.42, t.encode("latin-1", "replace").decode("latin-1"))
        if ln:
            pdf.ln(1)

    def page_title(title: str) -> None:
        pdf.add_page()
        txt(title, 16, bold=True)
        pdf.ln(2)

    # --- стр. 1: комплект ---
    page_title(f"Шпалера для дачи «{spec.name}» — комплект и чертёж")
    txt(
        "Профиль: обычная квадратная труба 20×20 мм (не T-slot). "
        "Коннекторы печатаются из PETG или ASA. Солнечногорск / Московская область.",
        9,
    )
    pdf.ln(2)
    txt("1. Состав комплекта", 13, bold=True)
    cuts = spec.profile_cut_list()
    total_m = spec.total_profile_mm() / 1000.0
    txt(f"• Алюминиевый (или стальной) профиль 20×20 — {total_m:.1f} п.м., нарезка:", 11)
    for mark, length, qty in cuts:
        txt(f"    — {mark}: {qty} × {length/10:.0f} см", 11)
    conn = spec.connector_counts()
    txt("• Пластиковые коннекторы (PETG/ASA):", 11)
    for k, n in conn.items():
        txt(f"    — {CONNECTOR_LABELS_RU[k]}: {n} шт.", 11)
    txt(f"• Болт M5×16 нержавейка + гайка M5 nylock — {spec.bolt_count()} компл.", 11)
    txt("• Шпагат садовый или леска для подвязки — 5–10 м (опционально).", 11)
    txt("• Инструмент: ключ на 8, отвёртка, уровень, маркер.", 11)
    pdf.ln(2)

    txt("2. Габариты готовой шпалеры", 13, bold=True)
    txt(
        f"Ширина между стойками: {spec.width_mm/10:.0f} см\n"
        f"Высота: {spec.height_mm/10:.0f} см\n"
        f"Глубина: минимальная (плоская лестница у грядки).",
        11,
    )

    # --- стр. 2: чертёж (отдельная страница, альбомная) ---
    pdf.add_page(orientation="L")
    pdf.set_margins(12, 12, 12)
    txt("Чертёж шпалеры «Томат-2» — вид спереди", 16, bold=True)
    pdf.ln(1)
    _draw_trellis_front(pdf, spec, uni=uni, bf=bf, bb=bb)
    pdf.ln(2)
    txt(
        "Схема: две вертикальные стойки (СТ-В) соединены 5 горизонтальными перемычками (ПР-Г). "
        "Красные узлы — угол 90° (4 шт.). Оранжевые — кронштейн перемычки (6 шт.). "
        "Коричневые — опора внизу (2 шт.). Все размеры в миллиметрах.",
        10,
    )

    # --- стр. 3: сборка ---
    page_title("Порядок сборки")
    steps = [
        (
            "Шаг 1. Разложите профиль по маркировке",
            "Проверьте длины: 2 стойки по 200 см, 5 перемычек по 60 см. "
            "Снимите заусенцы напильником.",
        ),
        (
            "Шаг 2. Нижняя рама",
            "На каждую стойку наденьте опору (foot_base) снизу. "
            "Соедините стойки нижней перемычкой (100 мм от земли) двумя углами 90°.",
        ),
        (
            "Шаг 3. Верхняя перемычка",
            "На высоте 190 см установите верхнюю перемычку — снова углы 90° на обоих концах.",
        ),
        (
            "Шаг 4. Средние перекладины",
            "На отметках 50 / 100 / 150 см с каждой стороны наденьте кронштейн перемычки "
            "на стойку, вставьте горизонтальную трубку 60 см, затяните болт M5.",
        ),
        (
            "Шаг 5. Фиксация",
            "В каждом коннекторе затяните болт M5 (не перетягивайте — профиль алюминиевый). "
            "Вбейте штырь через опору или прижмите низ стойки к земле.",
        ),
        (
            "Шаг 6. Подвязка растений",
            "Шпагат натягивайте зигзагом между перекладинами. "
            "Томаты — вертикально; огурцы — сетка из вертикалей и горизонталей.",
        ),
    ]
    for title, body in steps:
        txt(title, 12, bold=True)
        txt(body, 11)
        pdf.ln(1)

    txt("Время сборки: 40–60 мин. Вес каркаса без растений: ~3–4 кг.", 10)

    # --- стр. 4: печать ---
    page_title("Печать коннекторов (Bambu P2S)")
    txt("Материал: PETG (лето) или ASA (максимальная стойкость на солнце).", 11)
    txt("Не использовать PLA — размягчается на даче.", 11, bold=True)
    pdf.ln(1)
    txt("Настройки ориентира:", 12, bold=True)
    txt(
        "• Сопло 0,4 мм, слой 0,2 мм, стенки 4, верх/низ 5\n"
        "• Заполнение 40–50 %\n"
        "• Без поддержек (детали уже ориентированы в 3MF)\n"
        "• Печатайте connectors-plate-1-of-2.3mf, затем connectors-plate-2-of-2.3mf\n"
        "• В Bambu при вопросе «multi-part» — жмите NO\n"
        "• connectors-plate.3mf — все 12 деталей на одном столе (опционально)",
        11,
    )
    pdf.ln(1)
    txt("Количество на одну шпалеру:", 12, bold=True)
    for k, n in conn.items():
        txt(f"  {CONNECTOR_LABELS_RU[k]}: {n} шт.", 11)

    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")


def _draw_trellis_front(pdf, spec: TrellisSpec, *, uni: bool, bf: str, bb: str) -> None:
    """Чертёж спереди: стойки, перемычки, узлы, размеры, легенда."""
    # Область чертежа (альбомная A4 ≈ 297×210 мм)
    ox, oy = 55.0, 175.0  # левый нижний угол рамы (земля)
    draw_h = 130.0
    scale = draw_h / spec.height_mm
    W = spec.width_mm * scale

    def label(x: float, y: float, text: str, size: int = 9, bold: bool = False) -> None:
        pdf.set_font(bb if bold else bf, size=size)
        if uni:
            pdf.text(x, y, text)
        else:
            pdf.text(x, y, text.encode("latin-1", "replace").decode("latin-1"))

    # Земля
    pdf.set_draw_color(120, 90, 60)
    pdf.set_line_width(0.8)
    pdf.line(ox - 15, oy + 2, ox + W + 25, oy + 2)
    label(ox - 14, oy + 10, "земля", 8)

    # Стойки (СТ-В) — толстые синие линии
    pdf.set_draw_color(30, 80, 180)
    pdf.set_line_width(2.5)
    pdf.line(ox, oy, ox, oy - draw_h)
    pdf.line(ox + W, oy, ox + W, oy - draw_h)

    # Перемычки (ПР-Г) — зелёные
    pdf.set_draw_color(40, 140, 70)
    pdf.set_line_width(2.0)
    corner_heights = {spec.rung_heights_mm[0], spec.rung_heights_mm[-1]}
    for rh in spec.rung_heights_mm:
        y = oy - rh * scale
        pdf.line(ox, y, ox + W, y)
        # подпись высоты слева
        label(ox - 22, y + 2, f"{int(rh)}", 8, bold=True)
        # тип узла
        if rh in corner_heights:
            _draw_node(pdf, ox, y, "corner")
            _draw_node(pdf, ox + W, y, "corner")
        else:
            _draw_node(pdf, ox, y, "bracket")
            _draw_node(pdf, ox + W, y, "bracket")

    # Опоры внизу
    _draw_node(pdf, ox, oy, "foot")
    _draw_node(pdf, ox + W, oy, "foot")

    # Размерная линия ширины
    pdf.set_draw_color(60, 60, 60)
    pdf.set_line_width(0.35)
    dim_y = oy + 18
    pdf.line(ox, dim_y, ox + W, dim_y)
    for px in (ox, ox + W):
        pdf.line(px, dim_y - 2, px, dim_y + 2)
    label(ox + W / 2 - 12, dim_y + 8, f"{int(spec.width_mm)} mm", 10, bold=True)

    # Размерная линия высоты
    dim_x = ox + W + 18
    pdf.line(dim_x, oy, dim_x, oy - draw_h)
    pdf.line(dim_x - 2, oy, dim_x + 2, oy)
    pdf.line(dim_x - 2, oy - draw_h, dim_x + 2, oy - draw_h)
    label(dim_x + 4, oy - draw_h / 2, f"{int(spec.height_mm)} mm", 10, bold=True)

    # Подписи элементов на самом чертеже
    label(ox + 3, oy - draw_h / 2, "СТ-В", 9, bold=True)
    label(ox + W + 3, oy - draw_h / 2, "СТ-В", 9, bold=True)
    label(ox + W / 2 - 12, oy - spec.rung_heights_mm[2] * scale - 4, "ПР-Г 600", 8)

    # Легенда
    lx, ly = 12.0, 35.0
    label(lx, ly, "Условные обозначения:", 11, bold=True)
    items = [
        ("corner", "Угол 90° — 4 шт. (низ и верх)"),
        ("bracket", "Кронштейн перемычки — 6 шт."),
        ("foot", "Опора / ножка — 2 шт."),
    ]
    for i, (kind, text) in enumerate(items):
        yy = ly + 10 + i * 12
        _draw_node(pdf, lx + 4, yy, kind, size=5)
        label(lx + 14, yy + 2, text, 9)

    # Таблица высот перемычек
    tx = lx
    ty = ly + 52
    label(tx, ty, "Высота перемычек от земли:", 10, bold=True)
    for i, rh in enumerate(spec.rung_heights_mm):
        if rh == spec.rung_heights_mm[0]:
            role = "низ — угол 90°"
        elif rh == spec.rung_heights_mm[-1]:
            role = "верх — угол 90°"
        else:
            role = "середина — кронштейн"
        label(tx, ty + 8 + i * 7, f"  {int(rh)} мм — {role}", 8)


def _draw_node(pdf, x: float, y: float, kind: str, size: float = 4.0) -> None:
    h = size
    if kind == "corner":
        pdf.set_fill_color(220, 60, 50)
        pdf.set_draw_color(180, 40, 30)
    elif kind == "bracket":
        pdf.set_fill_color(240, 150, 30)
        pdf.set_draw_color(200, 120, 20)
    else:
        pdf.set_fill_color(130, 85, 45)
        pdf.set_draw_color(100, 65, 35)
    pdf.rect(x - h, y - h, h * 2, h * 2, style="FD")


def build_avito_draft(spec: TrellisSpec = DEFAULT_SPEC) -> str:
    total_m = spec.total_profile_mm() / 1000.0
    return f"""═══════════════════════════════════════════════
ОБЪЯВЛЕНИЕ 1 — ШПАЛЕРА (основное)
═══════════════════════════════════════════════

Заголовок:
Шпалера для томатов/огурцов 2 м — набор, доставка Солнечногорск

Цена: 5 900 – 6 900 ₽ (самовывоз Солнечногорск)
Доставка: Солнечногорск, Истра, Клин, Зеленоград — от 800 ₽

Описание:

Готовый набор шпалеры для дачи — соберёте за час без сварки и сверления профиля.

✔ Профиль 20×20 нарезан и промаркирован ({total_m:.1f} п.м.)
✔ Пластиковые коннекторы (PETG/ASA) — {sum(spec.connector_counts().values())} шт.
✔ Болты M5 нержавейка + инструкция с чертежом (PDF)
✔ Размер: {spec.width_mm/10:.0f}×{spec.height_mm/10:.0f} см, для грядки у забора или теплицы
✔ Подходит для томатов, огурцов, гороха, декоративных вьющихся

Как работает: каркас-«лестница» — стойки + 5 перекладин. Подвязываете шпагат или сетку — растения растут ровно, не ломают палки.

Самовывоз: Солнечногорск (Московская область).
Могу привезти и собрать на участке — спросите в сообщениях.

Не детская игровая конструкция. На зиму каркас лучше разобрать и убрать в сарай.

Пишите «шпалера» — пришлю фото комплектации и точную цену под ваш адрес.


═══════════════════════════════════════════════
ОБЪЯВЛЕНИЕ 2 — КОННЕКТОРЫ (если продаёте отдельно)
═══════════════════════════════════════════════

Заголовок:
Коннекторы для профиля 20×20 — шпалера, дача, PETG (набор)

Цена: 1 200 – 1 800 ₽ за комплект на 1 шпалеру

Набор печатных уголков и кронштейнов под обычный квадратный профиль 20×20 мм (не T-slot):
• 4 угла 90°
• 6 кронштейнов перемычки
• 2 опоры
+ болты M5, PDF-сборка.

Профиль в комплект не входит — только узлы. Или закажите полный набор с профилем.


═══════════════════════════════════════════════
СОВЕТЫ ПО ПУБЛИКАЦИИ
═══════════════════════════════════════════════

• Категория: «Для дома и дачи» → Сад и огород
• Фото: собранная шпалера на грядке, коробка с деталями, крупный план узла
• Гео: Солнечногорск + радиус 30 км
• Поднять объявление в апреле–июне; в описании слова: шпалера, томат, дача, теплица
"""


def build_kit_pack(out_dir: Path, spec: TrellisSpec = DEFAULT_SPEC) -> Path:
    """Собрать папку: PDF, 3MF (split + full), STL, Avito."""
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    safe = spec.name.replace(" ", "-").replace("Томат", "tomat")
    pdf_path = out_dir / f"shpalera-{safe}-instrukciya.pdf"
    pdf_path.write_bytes(build_kit_pdf(spec))

    split_paths = export_connectors_3mf_split(out_dir, spec)
    export_connectors_3mf(out_dir / "connectors-plate-all.3mf", spec)
    export_connector_stls(out_dir / "stl", spec)

    avito_path = out_dir / "avito-chernovik.txt"
    avito_path.write_text(build_avito_draft(spec), encoding="utf-8")

    split_names = ", ".join(p.name for p in split_paths)
    readme = out_dir / "README.txt"
    readme.write_text(
        f"Набор «{spec.name}» — шпалера 20×20\n"
        f"PDF: инструкция + чертёж (стр. 2, альбомная)\n"
        f"Печать (рекомендуется): {split_names}\n"
        f"  plate-1: 4 угла + 2 кронштейна | plate-2: 4 кронштейна + 2 опоры\n"
        f"connectors-plate-all.3mf — все 12 деталей на одном столе\n"
        f"  В Bambu при вопросе «multi-part» — жмите NO\n"
        f"stl/ — отдельные файлы (ориентированы на стол)\n"
        f"avito-chernovik.txt — текст объявления\n",
        encoding="utf-8",
    )
    return out_dir
