#!/usr/bin/env python3
"""Download free reference STL kits for bot quality improvement."""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Iterable, Tuple

ROOT = Path(__file__).resolve().parents[1]
REF_DIR = ROOT / "data" / "reference_models"

PrintablesKit = dict

CLERX_747SP: PrintablesKit = {
    "slug": "clerx_boeing_747sp",
    "print_id": 60733,
    "source_url": "https://www.printables.com/model/60733-boeing-747sp-1200",
    "license": "CC BY-NC-ND 4.0 (reference only, non-commercial)",
    "author": "CLERX",
    "use_for": ["mechanical_boeing_airliner", "assembly_preview", "part_naming"],
    "files": [
        ("637399_f506955b-e17e-460b-8ed2-17e84477b112", "engine-1.stl"),
        ("637403_5ee9e31c-5ccf-4b5c-bd5f-45f8ff6a2ed9", "engine-2.stl"),
        ("637400_4b2bf990-c76f-4554-b37f-aab00342d198", "engine-3.stl"),
        ("637402_2c1f20aa-5f6a-4b43-9320-aebe9dd041d6", "engine-4.stl"),
        ("637401_e06c40c5-2a84-47cc-8e78-4b3627cefac7", "fan-blades.stl"),
        ("637407_4af19705-5c10-4447-9d39-d25814b881d9", "fuselage-fwd.stl"),
        ("637404_faa5c272-d48f-462e-b297-e3dbb63eea7c", "fuselage-aft.stl"),
        ("637411_d2046b01-b0d5-4c63-bb17-df2d89282a26", "wing-left.stl"),
        ("637412_3df483cb-acbc-48ea-9482-1b5708b01d4a", "wing-right.stl"),
        ("637408_6a1b93b3-8208-43ff-8d2b-c206c14b612b", "vert-stab.stl"),
        ("637405_beed85a7-0aa3-4ff3-a1d9-ba64778ce3df", "horz-stab-left.stl"),
        ("637406_530005b6-4c1d-49bb-ab99-f5f5689df1c4", "horz-stab-right.stl"),
        ("637409_f8604643-1187-4ab1-b28c-8d9e26bd4efa", "pin.stl"),
        ("637410_b23ac5fd-8480-4f9b-94b3-303d3718d7b7", "stand.stl"),
    ],
}

# Useful for product-system archetypes (vehicle, box, basket) — manual incraft3d URLs.
INCRAFT3D_FREE_CATALOG = [
    {
        "slug": "incraft_jeep_willis",
        "url": "https://incraft3d.ru/catalog/3d-modeli/znamenityy-armeyskiy-dzhip-villis/",
        "use_for": ["vehicle_mechanical", "wheels"],
    },
    {
        "slug": "incraft_tool_box",
        "url": "https://incraft3d.ru/catalog/3d-modeli/yashchik-dlya-instrumentov/",
        "use_for": ["modular_storage_system"],
    },
    {
        "slug": "incraft_egg_basket",
        "url": "https://incraft3d.ru/catalog/3d-modeli/spiralnaya-korzina-dlya-yaits/",
        "use_for": ["perforated_basket"],
    },
    {
        "slug": "incraft_closing_box",
        "url": "https://incraft3d.ru/catalog/3d-modeli/zakryvayushchiysya-yashchik/",
        "use_for": ["hinged_container"],
    },
    {
        "slug": "incraft_star_destroyer",
        "url": "https://incraft3d.ru/catalog/3d-modeli/zvezdnnyy-razrushitel/",
        "use_for": ["vehicle_kit", "split_model"],
    },
]


def download_file(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest.write_bytes(data)


def download_printables_kit(kit: PrintablesKit) -> dict:
    out_dir = REF_DIR / kit["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"https://media.printables.com/media/prints/{kit['print_id']}/stls"
    results = []
    for file_id, name in kit["files"]:
        url = f"{base}/{file_id}/{name}"
        dest = out_dir / name
        if dest.is_file() and dest.stat().st_size > 1000:
            print(f"Skip existing {name}")
        else:
            print(f"Downloading {name} ...")
            download_file(url, dest)
        results.append({"file": name, "bytes": dest.stat().st_size, "url": url})
    manifest = {
        **{k: v for k, v in kit.items() if k != "files"},
        "part_count": len(results),
        "parts": results,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def write_incraft3d_manifest() -> dict:
    out_dir = REF_DIR / "incraft3d"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "note": (
            "Скачивание с incraft3d.ru требует авторизации в том же браузере, "
            "где вы вошли через Google. Откройте URL → «Скачать бесплатно» → "
            "оформите заказ 0 ₽ → скачайте ZIP в личном кабинете. "
            "Положите распакованные STL в подпапки slug/ ниже."
        ),
        "catalog": INCRAFT3D_FREE_CATALOG,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def discover_printables_files(print_id: int) -> Iterable[Tuple[str, str]]:
    """Scrape file id + name from Printables files page (no API key)."""
    url = f"https://www.printables.com/model/{print_id}/files"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    pat = re.compile(
        r"prints/" + str(print_id) + r"/stls/(\d+_[a-f0-9-]+)/[^\"]+/([a-z0-9._-]+\.stl)",
        re.I,
    )
    seen = set()
    for file_id, name in pat.findall(html):
        key = (file_id, name)
        if key not in seen:
            seen.add(key)
            yield file_id, name


if __name__ == "__main__":
    clerx = download_printables_kit(CLERX_747SP)
    incraft = write_incraft3d_manifest()
    print(
        json.dumps(
            {
                "ok": True,
                "clerx_parts": clerx["part_count"],
                "incraft3d_urls": len(incraft["catalog"]),
            },
            ensure_ascii=False,
        )
    )
