"""Render reference-kit mood boards for Meshy image-to-3D."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bot.services.reference_geometry import build_geometry_profile

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "data" / "reference_models"

ROLE_COLORS: Dict[str, Tuple[int, int, int]] = {
    "fuselage": (90, 140, 220),
    "wing": (70, 180, 120),
    "vert_stab": (180, 120, 200),
    "horz_stab": (160, 160, 90),
    "engine": (200, 100, 80),
    "rotor": (120, 120, 120),
    "landing_gear": (80, 80, 80),
    "wheel": (40, 40, 40),
    "gear": (220, 160, 60),
    "link": (100, 180, 180),
    "gripper": (180, 80, 80),
    "container": (140, 110, 70),
    "base": (160, 160, 160),
    "generic": (130, 130, 130),
}


def _layout_boxes(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    parts = profile.get("parts") or []
    if not parts:
        return []
    env = profile.get("envelope_mm") or {"x": 1, "y": 1, "z": 1}
    ex = max(float(env.get("x") or 1), 1e-3)
    ey = max(float(env.get("y") or 1), 1e-3)
    ez = max(float(env.get("z") or 1), 1e-3)
    laid: List[Dict[str, Any]] = []
    x_cursor = 20
    row_y = 40
    row_h = 0
    last_role = ""
    for p in parts[:20]:
        bb = p.get("bbox_mm") or {"x": 10, "y": 10, "z": 10}
        w = max(28, int(180 * float(bb.get("x", 10)) / ex))
        h = max(22, int(120 * float(bb.get("y", 10)) / ey))
        role = p.get("role") or "generic"
        if last_role and role != last_role:
            x_cursor += 14
        if x_cursor + w > 960:
            x_cursor = 20
            row_y += row_h + 36
            row_h = 0
        laid.append(
            {
                **p,
                "rect": (x_cursor, row_y, w, h),
                "color": ROLE_COLORS.get(role, ROLE_COLORS["generic"]),
            }
        )
        x_cursor += w + 10
        row_h = max(row_h, h)
        last_role = role
    return laid


def render_mood_board_png(slug: str, *, width: int = 1024, height: int = 768) -> Optional[bytes]:
    """2D exploded blueprint diagram — Meshy image-to-3D input."""
    profile = build_geometry_profile(slug)
    if not profile or profile.get("part_count", 0) < 3:
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("Pillow not available for mood board")
        return None

    boxes = _layout_boxes(profile)
    if not boxes:
        return None

    img = Image.new("RGB", (width, height), (248, 248, 252))
    draw = ImageDraw.Draw(img)
    title = f"Reference kit: {slug} ({profile.get('part_count')} parts)"
    draw.text((24, 12), title, fill=(30, 30, 40))
    draw.text(
        (24, 32),
        f"category={profile.get('category')} — exploded print layout (not exact mesh)",
        fill=(80, 80, 90),
    )

    for item in boxes:
        x, y, w, h = item["rect"]
        color = item["color"]
        draw.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=color, outline=(30, 30, 30), width=2)
        label = (item.get("name") or item.get("id") or "")[:22]
        draw.text((x + 4, y + 4), label, fill=(255, 255, 255))
        role = item.get("role") or ""
        draw.text((x + 4, y + h - 16), role, fill=(240, 240, 240))

    draw.text(
        (24, height - 28),
        "Use this layout: separate printable parts, realistic proportions, high detail sculpt",
        fill=(60, 60, 70),
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_mood_board_to_kit(slug: str) -> Optional[Path]:
    data = render_mood_board_png(slug)
    if not data:
        return None
    out = REF / slug / "reference_mood_board.png"
    out.write_bytes(data)
    return out
