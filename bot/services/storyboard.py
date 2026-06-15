"""Разбор HTML-раскадровок (storyboard) в список кадров для 3D-печати."""

import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

_FRAME_CLASS = re.compile(r"frame|slide|step|кадр|scene|panel|card", re.I)
_SKIP_TITLE = re.compile(
    r"раскадровк|storyboard|визуальное руководство|оглавлен|содержан|"
    r"гибридный генератор$",
    re.I,
)
_NON_PRINTABLE = re.compile(
    r"общий вид|целиком|схема сборки|итог|принцип|как работает|"
    r"раскадровк|storyboard|введение",
    re.I,
)
_DIM_MM = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:×|x|х)\s*(\d+(?:[.,]\d+)?)(?:\s*(?:×|x|х)\s*(\d+(?:[.,]\d+)?))?\s*мм",
    re.I,
)


class _StoryboardHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.headings: List[str] = []
        self._buf: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        cls = ""
        for k, v in attrs:
            if k == "class" and v:
                cls = v
        if tag in ("h1", "h2", "h3", "h4", "p", "li", "span", "div") and _FRAME_CLASS.search(cls):
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag in ("h1", "h2", "h3", "h4", "p", "li") and not self._skip:
            text = " ".join(self._buf).strip()
            self._buf = []
            if text and len(text) > 2:
                self.headings.append(text)

    def handle_data(self, data: str) -> None:
        if not self._skip:
            t = data.strip()
            if t:
                self._buf.append(t)


def _clean_title(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"^[🔭🎬⚙️🔧🧩📐🖨️\d\.\s]+", "", t).strip()
    return t[:120] or "Деталь"


def _parse_frames_from_plain_text(text: str) -> List[Dict[str, Any]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    frames: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if re.fullmatch(r"\d{1,2}", lines[i]):
            num = int(lines[i])
            title = _clean_title(lines[i + 1]) if i + 1 < len(lines) else f"Кадр {num}"
            desc = ""
            if i + 2 < len(lines) and not re.fullmatch(r"\d{1,2}", lines[i + 2]):
                if len(lines[i + 2]) < 120 and not _SKIP_TITLE.search(lines[i + 2]):
                    desc = lines[i + 2]
                    i += 1
            if not _SKIP_TITLE.search(title):
                frames.append(
                    {
                        "frame": num,
                        "title": title,
                        "description": desc,
                        "printable": not _NON_PRINTABLE.search(title + " " + desc),
                    }
                )
            i += 2
            continue
        i += 1
    return frames


def _parse_frames_from_headings(headings: List[str]) -> List[Dict[str, Any]]:
    frames: List[Dict[str, Any]] = []
    num = 0
    for h in headings:
        if _SKIP_TITLE.search(h):
            continue
        m = re.match(r"^(\d{1,2})[\.\)\s]+(.+)$", h)
        if m:
            num = int(m.group(1))
            title = _clean_title(m.group(2))
        else:
            num += 1
            title = _clean_title(h)
        if len(title) < 3:
            continue
        frames.append(
            {
                "frame": num,
                "title": title,
                "description": "",
                "printable": not _NON_PRINTABLE.search(title),
            }
        )
    return frames


def _parse_frames_from_raw_html(html: str) -> List[Dict[str, Any]]:
    frames: List[Dict[str, Any]] = []
    for m in re.finditer(
        r"<h[1-4][^>]*>\s*(?:<[^>]+>\s*)*(\d{1,2})?\s*([^<]{4,120})\s*</h[1-4]>",
        html,
        re.I | re.S,
    ):
        num = int(m.group(1)) if m.group(1) else len(frames) + 1
        title = _clean_title(m.group(2))
        if _SKIP_TITLE.search(title):
            continue
        frames.append(
            {
                "frame": num,
                "title": title,
                "description": "",
                "printable": not _NON_PRINTABLE.search(title),
            }
        )
    if frames:
        return frames

    blocks = re.split(
        r'<(?:section|div|article)[^>]*class="[^"]*(?:frame|slide|step|кадр)[^"]*"[^>]*>',
        html,
        flags=re.I,
    )
    for idx, block in enumerate(blocks[1:], start=1):
        titles = re.findall(r"<h[1-4][^>]*>([^<]{3,120})</h[1-4]>", block, re.I)
        paras = re.findall(r"<p[^>]*>([^<]{3,200})</p>", block, re.I)
        if not titles:
            continue
        title = _clean_title(titles[0])
        desc = _clean_title(paras[0]) if paras else ""
        if _SKIP_TITLE.search(title):
            continue
        frames.append(
            {
                "frame": idx,
                "title": title,
                "description": desc,
                "printable": not _NON_PRINTABLE.search(title + " " + desc),
            }
        )
    return frames


def extract_embedded_images(html: str, *, limit: int = 8) -> List[bytes]:
    """PNG/JPEG из data: URI в HTML (раскадровки со скриншотами)."""
    import base64

    out: List[bytes] = []
    for m in re.finditer(
        r'src=["\']data:image/(?:jpeg|jpg|png);base64,([^"\']+)["\']',
        html or "",
        re.I,
    ):
        try:
            raw = base64.b64decode(m.group(1), validate=False)
            if len(raw) > 500:
                out.append(raw)
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out


def parse_storyboard(html_or_text: str) -> List[Dict[str, Any]]:
    """Извлечь кадры раскадровки из HTML или текста."""
    raw = html_or_text or ""
    if not raw.strip():
        return []

    frames = _parse_frames_from_raw_html(raw)
    if len(frames) < 2:
        parser = _StoryboardHTMLParser()
        try:
            parser.feed(raw)
            frames = _parse_frames_from_headings(parser.headings)
        except Exception:
            pass

    if len(frames) < 2:
        plain = re.sub(r"<[^>]+>", "\n", raw)
        plain = re.sub(r"\n{3,}", "\n\n", plain)
        frames = _parse_frames_from_plain_text(plain)

    seen = set()
    out: List[Dict[str, Any]] = []
    for f in sorted(frames, key=lambda x: int(x.get("frame") or 0)):
        key = (f.get("title") or "").lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def is_storyboard_document(filename: str, content: str) -> bool:
    name = (filename or "").lower()
    blob = (content or "")[:8000].lower()
    return (
        "storyboard" in name
        or "раскадров" in name
        or ("гибридный" in blob and "генератор" in blob)
        or blob.count("кадр") >= 2
        or bool(re.search(r"frame|slide-\d|data-frame", blob, re.I))
    )


def _guess_template(title: str, desc: str) -> str:
    t = f"{title} {desc}".lower()
    if re.search(r"трубк|clip|клипс|хомут", t):
        return "tube_clip"
    if re.search(r"катуш|бобин|намотк|coil", t):
        return "bobbin"
    if re.search(r"сфер|шар|ball", t):
        return "sphere"
    if re.search(r"цилиндр|стакан|труб(а|ы)|колено", t):
        return "cylinder"
    if re.search(r"крышк|пластин|заглушк|площадк|пьезо|plate", t):
        return "plate"
    if re.search(r"корпус|короб|отсек|база|нижн|верхн|держател", t):
        return "hollow_box"
    return "hollow_box"


def _parse_dims(text: str) -> Dict[str, float]:
    m = _DIM_MM.search(text or "")
    if not m:
        return {}
    a = float(m.group(1).replace(",", "."))
    b = float(m.group(2).replace(",", "."))
    c = float(m.group(3).replace(",", ".")) if m.group(3) else None
    if c is not None:
        return {"width_mm": a, "depth_mm": b, "height_mm": c}
    return {"width_mm": a, "depth_mm": b, "height_mm": max(4.0, min(a, b) * 0.3)}


def frame_to_part(frame: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Кадр раскадровки → спецификация детали OpenSCAD."""
    title = str(frame.get("title") or f"Кадр {index}")
    desc = str(frame.get("description") or "")
    fid = re.sub(r"[^\w\-]+", "-", title.lower())[:36].strip("-") or f"frame-{index:02d}"
    template = _guess_template(title, desc)
    dims = _parse_dims(f"{title} {desc}")

    base = {
        "id": f"frame-{index:02d}-{fid}"[:40],
        "name": title,
        "template": template,
        "material": "PETG",
        "orientation": "дном на стол",
        "purpose": desc or title,
        "assembly_step": f"Кадр {frame.get('frame') or index}: {title}",
        "description": desc,
        "frame_number": frame.get("frame") or index,
        "tolerance_mm": 0.2,
    }

    scale = 0.85 + (index % 5) * 0.05
    if template == "tube_clip":
        base["params"] = {
            "width_mm": dims.get("width_mm", 24),
            "depth_mm": dims.get("depth_mm", 18),
            "height_mm": dims.get("height_mm", 12),
            "radius_mm": dims.get("radius_mm", 5.5),
        }
    elif template == "bobbin":
        base["params"] = {
            "radius_mm": dims.get("radius_mm", 14 * scale),
            "height_mm": dims.get("height_mm", 18),
            "wall_mm": 2,
        }
    elif template == "cylinder":
        base["params"] = {
            "radius_mm": dims.get("radius_mm", 16 * scale),
            "height_mm": dims.get("height_mm", 30 + index * 2),
        }
    elif template == "sphere":
        base["params"] = {"radius_mm": dims.get("radius_mm", 18 * scale)}
    elif template == "plate":
        base["params"] = {
            "width_mm": dims.get("width_mm", 48 + index * 2),
            "depth_mm": dims.get("depth_mm", 48),
            "height_mm": dims.get("height_mm", 6),
            "hole_mm": 40 if "пьезо" in title.lower() else 0,
        }
    else:
        base["params"] = {
            "width_mm": dims.get("width_mm", 60 + index * 8),
            "depth_mm": dims.get("depth_mm", 40 + index * 4),
            "height_mm": dims.get("height_mm", 20 + index * 3),
            "wall_mm": 2.4,
        }
    return base


def frames_to_project_specs(
    frames: List[Dict[str, Any]],
    *,
    project_name: str = "hybrid-generator",
) -> Dict[str, Any]:
    from bot.services.hybrid_generator import hybrid_generator_specs, is_hybrid_generator_storyboard

    if is_hybrid_generator_storyboard(frames):
        return hybrid_generator_specs(frames)

    printable = [f for f in frames if f.get("printable", True)]
    if not printable:
        printable = frames
    parts = [frame_to_part(f, idx) for idx, f in enumerate(printable, start=1)]
    return {
        "project_name": project_name,
        "mode": "storyboard",
        "source": "storyboard.html",
        "requirements": [
            "Печать по кадрам раскадровки в указанном порядке",
            "Каждый STL соответствует названию кадра из storyboard",
        ],
        "assumptions": [
            "Геометрия v0 по названиям кадров; уточните размеры в мм при необходимости",
            "Справочные кадры (общий вид) не включены в STL",
        ],
        "parts": parts,
        "storyboard_frames": frames,
    }


def build_print_order_txt(frames: List[Dict[str, Any]], parts: List[Dict[str, Any]]) -> str:
    lines = [
        "ПОРЯДОК ПЕЧАТИ (по раскадровке)",
        "==============================",
        "",
    ]
    part_by_frame = {p.get("frame_number"): p for p in parts}
    for frame in frames:
        num = frame.get("frame")
        title = frame.get("title") or "—"
        if not frame.get("printable", True):
            lines.append(f"Кадр {num}: {title}")
            lines.append("  → не печатается (справочный кадр / общий вид)")
            lines.append("")
            continue
        part = part_by_frame.get(num)
        if part:
            pid = part.get("id") or "part"
            lines.append(f"Кадр {num}: {title}")
            lines.append(f"  → stl/{pid}.stl")
            lines.append(f"  → scad/{pid}.scad")
            lines.append(f"  → {part.get('purpose') or part.get('description') or ''}")
        else:
            lines.append(f"Кадр {num}: {title}")
            lines.append("  → (деталь не сгенерирована)")
        lines.append("")
    lines.append("Печатайте файлы stl/ по номерам кадров сверху вниз.")
    return "\n".join(lines)
