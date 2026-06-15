"""Структура папок в ZIP-комплекте сарая."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ShedPackDirs:
    root: Path
    instrukcii: Path
    pechat: Path
    pechat_stl: Path
    pechat_3mf: Path
    tehnika: Path
    prodazha: Path

    @classmethod
    def create(cls, root: Path, *, clean: bool = True) -> "ShedPackDirs":
        if clean and root.exists():
            for p in root.iterdir():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
        root.mkdir(parents=True, exist_ok=True)
        d = cls(
            root=root,
            instrukcii=root / "instrukcii",
            pechat=root / "dlya-pechati",
            pechat_stl=root / "dlya-pechati" / "stl",
            pechat_3mf=root / "dlya-pechati" / "3mf",
            tehnika=root / "tehnika",
            prodazha=root / "prodazha",
        )
        for p in (d.instrukcii, d.pechat_stl, d.pechat_3mf, d.tehnika, d.prodazha):
            p.mkdir(parents=True, exist_ok=True)
        return d


def write_pack_readme(d: ShedPackDirs, *, kit_name: str) -> None:
    (d.root / "README.txt").write_text(
        f"{kit_name} — комплект файлов (v5)\n"
        + "=" * 48
        + "\n\n"
        "instrukcii/\n"
        "  instrukciya-poshagovaya.pdf — главная пошаговая сборка (начните отсюда)\n"
        "  sborka-3d.mp4              — 3D-сборка всех шагов с плавным облётом камеры\n"
        "  sborka-animaciya.gif       — анимация: как детали соединяются\n"
        "  sborka-video.mp4           — видео-сборка (IKEA/Letta): детали по одной\n"
        "  sborka-shagi-2-4.mp4       — коротко: шаги 2–4 (блок, опора, рама, стойки)\n"
        "  sborka-iznutri.mp4         — подробно изнутри + крупные планы стыков\n"
        "  instrukciya-IKEA.pdf        — предыдущая версия инструкции\n"
        "  instrukciya.pdf             — текстовая спецификация\n"
        "  shemy-tehnicheskie.pdf — чертежи и этапы\n"
        "  schema-plan-razrez.png — план и разрез\n"
        "  ikea-steps-png/        — картинки шагов IKEA\n"
        "  schemes-png/           — исходники чертежей\n\n"
        "dlya-pechati/\n"
        "  3mf/                   — столы для Bambu (печатать по порядку 1…N)\n"
        "  stl/                   — отдельные детали (если нужна одна штука)\n"
        "  print_quantities.txt   — сколько штук каждого коннектора\n"
        "  PECHAT.txt             — настройки принтера\n\n"
        "tehnika/\n"
        "  profil-bez-rezki.txt   — палки и сборные балки\n"
        "  nagruzki.txt           — нагрузки на крышу и стойки\n"
        "  ustoychivost.txt       — почему каркас устойчивый\n"
        "  sborka-proverka.txt    — проверка логики сборки по шагам\n\n"
        "prodazha/\n"
        "  avito.txt              — текст объявления\n",
        encoding="utf-8",
    )


def write_pechat_txt(d: ShedPackDirs) -> None:
    (d.pechat / "PECHAT.txt").write_text(
        "Печать коннекторов — Bambu P2S / X1\n"
        + "=" * 40
        + "\n\n"
        "1. Откройте файлы из папки 3mf/ по порядку:\n"
        "   connectors-plate-1-of-N.3mf, затем 2-of-N и т.д.\n\n"
        "2. Материал: PETG или PETG-CF (не PLA — на солнце размягчается).\n\n"
        "3. Настройки:\n"
        "   • высота слоя 0,2 мм\n"
        "   • стенки 4–5 линий\n"
        "   • заполнение 50 % (foot_base, door_frame, rafter_seat — 60 %)\n"
        "   • поддержки не нужны\n\n"
        "4. После печати проверьте, что болт M5 проходит в отверстие.\n\n"
        "5. Количество деталей — в print_quantities.txt\n",
        encoding="utf-8",
    )
