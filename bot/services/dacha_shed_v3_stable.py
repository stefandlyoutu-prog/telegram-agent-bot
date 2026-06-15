"""
Сарай v3 Stable — 3×3 м, без резки, упор на устойчивость.
Квадратный план, 6 стоек, 8 раскосов, меньше палок чем v2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from bot.services.dacha_shed_v2_nocut import (
    BeamAssembly,
    IkeaStep,
    ShedNoCutSpec,
    build_shed_nocut_archive,
    ikea_steps,
)
from bot.services.dacha_shed_parts_ru import step_part


@dataclass(frozen=True)
class ShedV3StableSpec:
    """
    Хозблок 3×3 м «Stable».
    — Квадрат 150+150 см на сторону (4 стороны × стык)
    — 6 стоек по 200 см (углы + центр перед/зад)
    — 8 раскосов brace_45 (по 2 на каждую стену)
    — Односкат: фасад 200 см → зад 150 см
    — 4 стропила 150+150 см
    """

    name: str = "Хозблок 3×3 Stable"
    length_mm: int = 3000
    depth_mm: int = 3000
    front_height_mm: int = 2000
    back_height_mm: int = 1500
    door_width_mm: int = 1000
    door_height_mm: int = 2000
    door_offset_left_mm: int = 500
    post_count: int = 6
    brace_count: int = 8
    rafter_count_n: int = 4

    @property
    def rise_mm(self) -> float:
        return float(self.front_height_mm - self.back_height_mm)

    @property
    def pitch_deg(self) -> float:
        return math.degrees(math.atan(self.rise_mm / self.depth_mm))

    @property
    def rafter_slope_mm(self) -> float:
        return math.hypot(self.depth_mm, self.rise_mm)

    def span_side(self) -> Tuple[int, ...]:
        return (1500, 1500)

    def span_rafter(self) -> Tuple[int, ...]:
        return (1500, 1500)

    def beam_list(self) -> List[BeamAssembly]:
        s = self.span_side()
        sr = self.span_rafter()
        n_side = 4  # периметр низ + верх
        return [
            BeamAssembly("НИЗ периметр (4 стороны)", s, 4),
            BeamAssembly("СТ углы", (2000,), 4),
            BeamAssembly("СТ центр перед+зад", (2000,), 2, "усиление + косяк двери"),
            BeamAssembly("ВЕРХ периметр", s, 4),
            BeamAssembly("СТР стропило", sr, self.rafter_count_n, "концы в rafter_seat ~10 см"),
            BeamAssembly("GIRT (1 ряд по стенам)", s, 4, "середина стены ~100 см"),
            BeamAssembly("ПРОГ крыши", s, 2),
            BeamAssembly("РИГ-Д двойной", (1000,), 2),
            BeamAssembly("РАСКОС brace_45", (1500,), self.brace_count, "палка 150 см + brace_45"),
        ]

    def front_post_x(self) -> Tuple[int, ...]:
        return (0, 1500, self.length_mm)

    def back_post_x(self) -> Tuple[int, ...]:
        return (0, 1500, self.length_mm)

    def front_post_x_mm(self) -> Tuple[float, ...]:
        return tuple(float(x) for x in self.front_post_x())

    def back_post_x_mm(self) -> Tuple[float, ...]:
        return tuple(float(x) for x in self.back_post_x())

    def window_width_mm(self) -> float:
        return 0.0

    def window_sill_mm(self) -> float:
        return 0.0

    def stick_counts(self) -> Dict[int, int]:
        c = {1000: 0, 1500: 0, 2000: 0}
        for b in self.beam_list():
            for seg in b.segments_mm:
                c[seg] += b.qty
        return c

    def inline_splice_count(self) -> int:
        return sum(b.splices for b in self.beam_list())

    def connector_counts(self) -> Dict[str, int]:
        return {
            "foot_base": self.post_count,
            "corner_90": 8,
            "corner_post": 4,
            "tee_90": 4,
            "rafter_seat": self.rafter_count_n * 2,
            "girt_bracket": 8,
            "brace_45": self.brace_count,
            "door_frame": 4,
            "lintel_splice": 1,
            "inline_splice": self.inline_splice_count(),
        }

    def to_legacy_spec(self) -> ShedNoCutSpec:
        return ShedNoCutSpec(
            name=self.name,
            length_mm=float(self.length_mm),
            depth_mm=float(self.depth_mm),
            front_height_mm=float(self.front_height_mm),
            back_height_mm=self.back_height_mm,
            door_width_mm=float(self.door_width_mm),
            door_height_mm=float(self.door_height_mm),
            door_offset_left_mm=float(self.door_offset_left_mm),
            rafter_count_n=self.rafter_count_n,
            girt_rows=1,
        )

    def load_summary(self) -> Dict[str, float]:
        spec = ShedNoCutSpec(
            length_mm=float(self.length_mm),
            depth_mm=float(self.depth_mm),
            front_height_mm=float(self.front_height_mm),
            back_height_mm=self.back_height_mm,
        )
        loads = spec.load_summary()
        loads["back_height_mm"] = self.back_height_mm
        loads["pitch_deg"] = round(self.pitch_deg, 1)
        loads["post_load_kn"] = round(loads["roof_load_kn"] / self.post_count, 2)
        return loads

    def stability_text(self) -> str:
        loads = self.load_summary()
        return (
            "Почему v3 Stable устойчивее v2 (4×3)\n"
            "=" * 40 + "\n\n"
            "1. КВАДРАТ 3×3 м\n"
            "   — одинаковые диагонали, нет «длинной» стены 4 м\n"
            "   — меньше прогиб обвязки\n\n"
            "2. ШЕСТЬ СТОЕК (не четыре)\n"
            "   — 4 угла + 2 по центру перед/зад\n"
            "   — нагрузка на стойку ~"
            f"{loads['post_load_kn']*100:.0f} kg (ниже чем на 4 стойки)\n\n"
            "3. ВОСЕМЬ РАСКОСОВ brace_45\n"
            "   — по 2 на каждую стену (крестовая жёсткость)\n"
            "   — ставить ДО профлиста\n\n"
            "4. СТОЙКИ 200 см (одна палка)\n"
            "   — без стыков в стойках = максимальная жёсткость на сжатие\n\n"
            "5. СТРОПИЛА 150+150 см\n"
            "   — короткий пролёт по скату ~"
            f"{self.rafter_slope_mm/10:.0f} см\n"
            "   — уклон "
            f"{self.pitch_deg:.1f}° (сток на зад)\n\n"
            "6. ФУНДАМЕНТ\n"
            "   — 6 блоков 40×40, foot_base + анкер M8\n"
            "   — диагонали нижней рамы проверить до стоек\n\n"
            "7. ДВОЙНОЙ РИГЕЛЬ над дверью (2×100 см)\n"
            "   — lintel_splice, петли только в профиль\n"
        )


DEFAULT_SHED_V3 = ShedV3StableSpec()


def ikea_steps_v3(spec: ShedV3StableSpec = DEFAULT_SHED_V3) -> List[IkeaStep]:
    cc = spec.connector_counts()
    return [
        IkeaStep(
            1,
            "Разложите детали",
            "Это хозблок 3×3 метра. Резать палки не нужно — только вставлять и закручивать.\n\n"
            "Сначала найдите на первой странице инструкции «Словарь деталей».\n"
            "Разложите все палки и пластиковые уголки на чистой земле.\n"
            "Сложите палки в три кучки: длинные 200 см, средние 150 см, короткие 100 см.\n"
            "Попросите взрослого проверить: все ли детали на месте.",
            (
                step_part("profil_200", spec.stick_counts()[2000]),
                step_part("profil_150", spec.stick_counts()[1500]),
                step_part("profil_100", spec.stick_counts()[1000]),
                step_part("inline_splice", cc["inline_splice"]),
                step_part("brace_45", cc["brace_45"]),
            ),
            connect="Палки пока ни с чем не соединяем — только раскладываем и считаем.",
        ),
        IkeaStep(
            2,
            "6 опор на блоки",
            "Нужно поставить 6 бетонных блоков в форме квадрата 3×3 м.\n\n"
            "Где стоят блоки:\n"
            "• 4 блока — в углах квадрата\n"
            "• 2 блока — ровно посередине передней и задней стороны\n\n"
            "На каждый блок кладём пластиковую «Опору на блок».\n"
            "Взрослый вкручивает анкер M8 сквозь опору в блок.",
            (
                step_part("blok", spec.post_count),
                step_part("foot_base", cc["foot_base"]),
                step_part("bolt_m8", spec.post_count),
            ),
            connect=(
                "1. Поставьте блок на ровное место.\n"
                "2. Положите сверху «Опору на блок» — плоская сторона на блок.\n"
                "3. В отверстие опоры вставьте анкер M8 (делает взрослый).\n"
                "4. В верхнее гнездо опоры потом встанет палка 200 см."
            ),
        ),
        IkeaStep(
            3,
            "Нижний периметр",
            "Собираем «квадрат на полу» — это нижняя рама домика.\n\n"
            "Каждая из 4 сторон = две палки 150 см + один соединитель «в линию».\n"
            "Получается 4 длинные стороны по 300 см (3 метра).",
            (
                step_part("profil_150", 8),
                step_part("inline_splice", 4),
                step_part("corner_90", 4),
                step_part("bolt_m5", 16),
            ),
            connect=(
                "1. Возьмите 2 палки по 150 см.\n"
                "2. Вставьте концы в «Соединитель в линию» — получится одна длинная палка 300 см.\n"
                "3. Сделайте так 4 длинные палки (4 стороны квадрата).\n"
                "4. На каждый УГОЛ поставьте «Уголок 90°».\n"
                "5. Вставьте концы палок в уголки. Закрутите болты M5.\n"
                "6. Положите раму на 6 опор (пока без стоек).\n"
                "7. Взрослый проверит: диагонали квадрата должны быть одинаковые!"
            ),
        ),
        IkeaStep(
            4,
            "6 стоек",
            "Ставим 6 вертикальных палок по 200 см.\n\n"
            "Где стоят стойки:\n"
            "• 4 стойки — в углах (на уголках для стойки)\n"
            "• 1 стойка — середина передней стены (это правый косяк двери)\n"
            "• 1 стойка — середина задней стены",
            (
                step_part("profil_200", spec.post_count),
                step_part("corner_post", cc["corner_post"]),
                step_part("tee_90", 2),
                step_part("bolt_m5", 24),
            ),
            connect=(
                "УГЛЫ (4 штуки):\n"
                "1. На угол нижней рамы наденьте «Уголок для стойки».\n"
                "2. Нижний конец палки 200 см вставьте в опору на блок.\n"
                "3. Верхний конец палки вставьте в уголок. Закрутите болты M5.\n\n"
                "СЕРЕДИНА перед/зад (2 штуки):\n"
                "1. На нижнюю раму поставьте «Т-образный уголок».\n"
                "2. Вставьте палку 200 см снизу в опору, сверху в Т-уголок.\n"
                "3. Передняя средняя стойка — там, где будет дверь справа от неё."
            ),
        ),
        IkeaStep(
            5,
            "8 раскосов — важно!",
            "Раскосы не дают домику качаться на ветру.\n"
            "На КАЖДУЮ из 4 стен нужно 2 раскоса — всего 8 штук.\n"
            "Без раскосов собирать дальше нельзя!",
            (
                step_part("brace_45", cc["brace_45"]),
                step_part("profil_150", cc["brace_45"]),
                step_part("bolt_m5", cc["brace_45"] * 2),
            ),
            connect=(
                "1. Возьмите палку 150 см — это наклонная «лесенка».\n"
                "2. «Крепление для раскоса» — одно гнездо на стойку, второе на палку.\n"
                "3. Прикрутите один раскос от низа одной стойки к верху другой.\n"
                "4. Второй раскос — крестом (как буква X на стене).\n"
                "5. Повторите на всех 4 стенах."
            ),
        ),
        IkeaStep(
            6,
            "Верхний периметр",
            "Сверху делаем такой же квадрат, как внизу.\n"
            "Передняя сторона выше (200 см), задняя ниже (150 см) — крыша будет наклонная.",
            (
                step_part("profil_150", 8),
                step_part("inline_splice", 4),
                step_part("corner_90", 4),
                step_part("tee_90", 2),
                step_part("bolt_m5", 20),
            ),
            connect=(
                "1. Соберите 4 длинные стороны: 150+150 см + соединитель «в линию».\n"
                "2. В углах — «Уголок 90°» (как на нижней раме).\n"
                "3. На средних стойках перед/зад — «Т-образный уголок».\n"
                "4. Поднимите верхнюю раму и вставьте концы в уголки на стойках.\n"
                "5. Закрутите все болты M5."
            ),
        ),
        IkeaStep(
            7,
            "Дверь 100×200 см",
            "Делаем проём для двери на передней стене.\n"
            "Дверь слева направо: 50 см стена — 100 см проём — 150 см стена.\n"
            "Над проёмом — две короткие палки 100 см.",
            (
                step_part("door_frame", cc["door_frame"]),
                step_part("profil_100", 2),
                step_part("lintel_splice", cc["lintel_splice"]),
                step_part("bolt_m5", 8),
            ),
            connect=(
                "1. «Уголок двери» — на стойках у проёма (4 штуки).\n"
                "2. Две палки 100 см вставьте в «Соединитель над дверью» — "
                "получится длинная перекладина над дверью.\n"
                "3. Перекладину закрепите в уголки двери болтами M5.\n"
                "4. Петли для двери вешают только на металлический профиль."
            ),
        ),
        IkeaStep(
            8,
            "4 стропила",
            "Стропила — наклонные палки крыши. Их 4 штуки.\n"
            "Каждое стропило = 150 + 150 см + соединитель «в линию».\n"
            "Шаг между стропилами — примерно 100 см.",
            (
                step_part("profil_150", spec.rafter_count_n * 2),
                step_part("inline_splice", spec.rafter_count_n),
                step_part("rafter_seat", cc["rafter_seat"]),
                step_part("bolt_m5", spec.rafter_count_n * 4),
            ),
            connect=(
                "1. Соберите 4 длинные палки (150+150+стык).\n"
                "2. На передней и задней верхней раме закрепите «Держатель стропила».\n"
                "3. Положите стропило: передний конец выше, задний ниже (вода стекает назад).\n"
                "4. Вставьте концы в держатели. Закрутите болты M5."
            ),
        ),
        IkeaStep(
            9,
            "Обрешётка",
            "Горизонтальные палки для крепления листа на стенах и крыше.\n"
            "1 ряд посередине каждой стены + 2 прогона на крыше.",
            (
                step_part("girt_bracket", cc["girt_bracket"]),
                step_part("profil_150", 12),
                step_part("inline_splice", 6),
                step_part("bolt_m5", 24),
            ),
            connect=(
                "1. «Кронштейн для полки на стене» — на стойку, на высоте ~100 см от пола.\n"
                "2. В кронштейн вставьте палку 150 см (на стенах — 150+150+стык = 300 см).\n"
                "3. На крыше — 2 прогона поперёк: тоже 150+150+стык.\n"
                "4. Закрутите болты M5."
            ),
        ),
        IkeaStep(
            10,
            "Профлист",
            "Последний шаг — накрыть каркас металлическим листом.\n"
            "Сначала стены, потом крыша (снизу вверх по скату).",
            (
                step_part("proflist", 1),
                step_part("samorez", 180),
            ),
            connect=(
                "1. Лист режет и держит взрослый.\n"
                "2. Прикрутите лист к горизонтальным палкам саморезами 5,5×25 мм.\n"
                "3. Шаг саморезов — не больше 30 см по краю листа.\n"
                "4. Крышу крепите от передней стены к задней — вода стекает назад."
            ),
        ),
    ]


def build_shed_v3_archive(out_dir: Path, spec: ShedV3StableSpec = DEFAULT_SHED_V3) -> Path:
    import zipfile

    from bot.services.dacha_shed_blueprints import build_ikea_pdf_with_schemes, build_schemes_pdf
    from bot.services.dacha_shed_pack_layout import ShedPackDirs, write_pack_readme, write_pechat_txt
    from bot.services.dacha_shed_v2_nocut import (
        build_shed_nocut_text_pdf,
        export_shed_v2_connectors,
    )
    from bot.services.dacha_shed_kit import render_shed_scheme_png

    dirs = ShedPackDirs.create(out_dir)
    write_pack_readme(dirs, kit_name=spec.name)
    write_pechat_txt(dirs)

    schemes_dir = dirs.instrukcii / "schemes-png"
    ikea_dir = dirs.instrukcii / "ikea-steps-png"
    novice_dir = dirs.instrukcii / "poshagovaya-png"
    from bot.services.dacha_shed_instr_novice import ikea_steps_v3_novice
    from bot.services.dacha_shed_assembly_check import format_assembly_report

    steps_legacy = ikea_steps_v3(spec)
    steps = ikea_steps_v3_novice(spec)

    (dirs.tehnika / "sborka-proverka.txt").write_text(
        format_assembly_report(spec, steps), encoding="utf-8"
    )

    (dirs.instrukcii / "instrukciya.pdf").write_bytes(build_shed_nocut_text_pdf(spec))  # type: ignore[arg-type]
    (dirs.instrukcii / "shemy-tehnicheskie.pdf").write_bytes(build_schemes_pdf(spec, schemes_dir))
    (dirs.instrukcii / "instrukciya-IKEA.pdf").write_bytes(
        build_ikea_pdf_with_schemes(spec, steps_legacy, ikea_dir)
    )
    (dirs.instrukcii / "instrukciya-poshagovaya.pdf").write_bytes(
        build_ikea_pdf_with_schemes(spec, steps, novice_dir)
    )

    from bot.services.dacha_shed_assembly_anim import build_assembly_gif

    render_shed_scheme_png(spec.to_legacy_spec(), dirs.instrukcii / "schema-plan-razrez.png")
    build_assembly_gif(spec, dirs.instrukcii / "sborka-animaciya.gif")

    from bot.services.dacha_shed_ikea_video import build_ikea_assembly_video

    build_ikea_assembly_video(
        spec,
        dirs.instrukcii / "sborka-video.mp4",
        frames_per_step=8,
        hold_frames=5,
        fps=10.0,
    )

    from bot.services.dacha_shed_3d_video import build_3d_video
    from bot.services.dacha_shed_interior_video import build_interior_video
    from bot.services.dacha_shed_steps24_video import build_steps24_video

    build_interior_video(spec, dirs.instrukcii / "sborka-iznutri.mp4", fps=10.0)
    build_steps24_video(spec, dirs.instrukcii / "sborka-shagi-2-4.mp4")
    build_3d_video(spec, dirs.instrukcii / "sborka-3d.mp4")

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
    (dirs.tehnika / "ustoychivost.txt").write_text(spec.stability_text(), encoding="utf-8")

    loads = spec.load_summary()
    (dirs.tehnika / "nagruzki.txt").write_text(
        f"Уклон: {loads['pitch_deg']} deg\n"
        f"Крыша: {loads['roof_area_m2']} m2\n"
        f"На стойку: ~{loads['post_load_kn']*100:.0f} kg\n",
        encoding="utf-8",
    )
    (dirs.prodazha / "avito.txt").write_text(
        f"Хозблок 3×3 м Stable — каркас под профлист.\n"
        f"Без резки: палки 1/1,5/2 м. PDF-схемы как на чертеже + IKEA.\n"
        f"200×{sc[2000]}, 150×{sc[1500]}, 100×{sc[1000]}. 8 раскосов.\n"
        f"Solnechnogorsk, доставка МО.",
        encoding="utf-8",
    )

    export_shed_v2_connectors(
        out_dir,
        spec,  # type: ignore[arg-type]
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
