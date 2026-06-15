"""
3D-видео полной сборки — pyrender + trimesh, плавный облёт камеры на каждом шаге.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from bot.services.dacha_shed_v3_stable import ShedV3StableSpec

from bot.services.dacha_shed_3d_geom import build_shed_meshes
from bot.services.dacha_shed_parts_ru import part_name
from bot.services.dacha_shed_steps24_video import VIDEO_H, VIDEO_W, _caption_bar

FPS = 12.0
RENDER_H = VIDEO_H - 96
_MESH_CACHE: dict = {}


@dataclass
class Assembly3DScene:
    step_label: str
    caption: str
    show_blocks: bool = False
    show_feet: bool = False
    show_frame: bool = False
    show_posts: bool = False
    show_braces: bool = False
    show_top: bool = False
    show_door: bool = False
    show_rafters: bool = False
    show_purlins: bool = False
    elev: float = 22.0
    azim_from: float = -125.0
    azim_to: float = -35.0
    orbit_frames: int = 60
    hold: int = 10


def _full_scenes() -> List[Assembly3DScene]:
    opora = part_name("foot_base")
    ugol_stoyka = part_name("corner_post")
    return [
        Assembly3DScene(
            "",
            f"Хозблок 3×3 «Стабл» — 3D-сборка. Одна стойка: через «{ugol_stoyka}» на обвязке → в «{opora}».",
            elev=28, azim_from=-140, azim_to=-50, orbit_frames=48,
        ),
        Assembly3DScene(
            "Шаг 1",
            "6 бетонных блоков: 4 угла + середина передней и задней стены.",
            show_blocks=True,
            elev=30, azim_from=-150, azim_to=-60, orbit_frames=56,
        ),
        Assembly3DScene(
            "Шаг 2",
            f"На блок — «{opora}» + анкер М8. Опора держит стойку, не обвязку.",
            show_blocks=True, show_feet=True,
            elev=26, azim_from=-130, azim_to=-40, orbit_frames=56,
        ),
        Assembly3DScene(
            "Шаг 3",
            f"Обвязка 3×3 м на ЗЕМЛЕ. В «{ugol_stoyka}» вставляются палки. В «{opora}» — нет!",
            show_blocks=True, show_feet=True, show_frame=True,
            elev=24, azim_from=-120, azim_to=-20, orbit_frames=64,
        ),
        Assembly3DScene(
            "Шаг 4",
            f"Стойка 200 см: одна палка с обвязки вверх и в гнездо «{opora}» на блоке.",
            show_blocks=True, show_feet=True, show_frame=True, show_posts=True,
            elev=20, azim_from=-110, azim_to=-30, orbit_frames=64,
        ),
        Assembly3DScene(
            "Шаг 5",
            "Раскосы крестом между стойками на каждой стене.",
            show_blocks=True, show_feet=True, show_frame=True, show_posts=True,
            show_braces=True,
            elev=22, azim_from=-100, azim_to=-20, orbit_frames=56,
        ),
        Assembly3DScene(
            "Шаг 6",
            "Верхняя обвязка: спереди 200 см, сзади 150 см.",
            show_blocks=True, show_feet=True, show_frame=True, show_posts=True,
            show_braces=True, show_top=True,
            elev=24, azim_from=-95, azim_to=-15, orbit_frames=64,
        ),
        Assembly3DScene(
            "Шаг 7",
            "Дверной проём 100×200 см на фасаде.",
            show_blocks=True, show_feet=True, show_frame=True, show_posts=True,
            show_braces=True, show_top=True, show_door=True,
            elev=18, azim_from=-95, azim_to=-5, orbit_frames=56,
        ),
        Assembly3DScene(
            "Шаг 8",
            "4 стропила по скату крыши.",
            show_blocks=True, show_feet=True, show_frame=True, show_posts=True,
            show_braces=True, show_top=True, show_door=True, show_rafters=True,
            elev=28, azim_from=-85, azim_to=-5, orbit_frames=64,
        ),
        Assembly3DScene(
            "Шаг 9",
            "Обрешётка на стенах и 2 прогона на крыше.",
            show_blocks=True, show_feet=True, show_frame=True, show_posts=True,
            show_braces=True, show_top=True, show_door=True, show_rafters=True,
            show_purlins=True,
            elev=26, azim_from=-75, azim_to=15, orbit_frames=64,
        ),
        Assembly3DScene(
            "Готово",
            "Каркас готов. Профлист — см. пошаговую инструкцию (PDF в папке).",
            show_blocks=True, show_feet=True, show_frame=True, show_posts=True,
            show_braces=True, show_top=True, show_door=True, show_rafters=True,
            show_purlins=True,
            elev=22, azim_from=-60, azim_to=30, orbit_frames=72, hold=16,
        ),
    ]


def _look_at(eye, target, up=(0.0, 0.0, 1.0)) -> np.ndarray:
    eye, target, up = map(lambda a: np.asarray(a, float), (eye, target, up))
    fwd = target - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    if np.linalg.norm(right) < 1e-8:
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    up_v = np.cross(right, fwd)
    m = np.eye(4)
    m[:3, 0] = right
    m[:3, 1] = up_v
    m[:3, 2] = -fwd
    m[:3, 3] = eye
    return m


def _camera_eye(
    spec: "ShedV3StableSpec",
    elev: float,
    azim: float,
    *,
    height_scale: float = 1.0,
) -> tuple:
    L = spec.length_mm / 1000.0
    D = spec.depth_mm / 1000.0
    fh = spec.front_height_mm / 1000.0
    cz = min(0.55 + height_scale * fh * 0.35, fh * 0.55)
    center = np.array([L * 0.5, D * 0.5, cz])
    dist = max(L, D) * 1.5 + 1.3 + height_scale * fh * 0.25
    er, ar = math.radians(elev), math.radians(azim)
    eye = center + dist * np.array([
        math.cos(er) * math.sin(ar),
        math.cos(er) * math.cos(ar),
        math.sin(er),
    ])
    return eye, center


def _scene_key(scene: Assembly3DScene) -> tuple:
    return (
        scene.show_blocks, scene.show_feet, scene.show_frame, scene.show_posts,
        scene.show_braces, scene.show_top, scene.show_door, scene.show_rafters,
        scene.show_purlins,
    )


def _get_meshes(spec: "ShedV3StableSpec", scene: Assembly3DScene):
    key = _scene_key(scene)
    if key not in _MESH_CACHE:
        _MESH_CACHE[key] = build_shed_meshes(
            spec,
            show_blocks=scene.show_blocks,
            show_feet=scene.show_feet,
            show_frame=scene.show_frame,
            show_posts=scene.show_posts,
            show_braces=scene.show_braces,
            show_top=scene.show_top,
            show_door=scene.show_door,
            show_rafters=scene.show_rafters,
            show_purlins=scene.show_purlins,
        )
    return _MESH_CACHE[key]


def _height_scale(scene: Assembly3DScene) -> float:
    if scene.show_rafters:
        return 1.0
    if scene.show_top:
        return 0.85
    if scene.show_posts:
        return 0.55
    if scene.show_frame:
        return 0.25
    return 0.1


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _hex_mat(rgba, metallic: float = 0.08, rough: float = 0.55):
    import pyrender

    return pyrender.MetallicRoughnessMaterial(
        baseColorFactor=list(rgba[:4]) if len(rgba) == 4 else [*rgba, 1.0],
        metallicFactor=metallic,
        roughnessFactor=rough,
    )


class _Renderer:
    def __init__(self, w: int = VIDEO_W, h: int = RENDER_H):
        import pyrender

        self._pr = pyrender
        self.w, self.h = w, h
        self._r = pyrender.OffscreenRenderer(w, h)

    def render(self, spec, scene: Assembly3DScene, *, elev: float, azim: float) -> np.ndarray:
        pr = self._pr
        hs = _height_scale(scene)
        eye, target = _camera_eye(spec, elev, azim, height_scale=hs)
        pose = _look_at(eye, target)

        sc = pr.Scene(bg_color=[0.97, 0.97, 0.97, 1.0], ambient_light=[0.45, 0.45, 0.45])
        sc.add(pr.PerspectiveCamera(yfov=math.radians(42.0), aspectRatio=self.w / self.h), pose=pose)
        sc.add(pr.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=4.5), pose=pose)
        fill = _look_at(eye + np.array([0.8, -1.2, 0.6]), target)
        sc.add(pr.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=1.8), pose=fill)

        for mesh in _get_meshes(spec, scene):
            col = mesh.metadata.get("color", (0.5, 0.5, 0.5))
            sc.add(pr.Mesh.from_trimesh(mesh, material=_hex_mat(col), smooth=False))

        color, _ = self._r.render(sc)
        return color

    def close(self):
        self._r.delete()


def build_3d_video(
    spec: "ShedV3StableSpec",
    path: Path,
    *,
    fps: float = FPS,
) -> Path:
    from PIL import Image

    _MESH_CACHE.clear()
    renderer = _Renderer()
    frames: List[Image.Image] = []
    try:
        for sc in _full_scenes():
            for i in range(sc.orbit_frames + sc.hold):
                if i < sc.orbit_frames:
                    t = _smoothstep(i / max(sc.orbit_frames - 1, 1))
                    az = sc.azim_from + (sc.azim_to - sc.azim_from) * t
                    el = sc.elev + 4.0 * math.sin(t * math.pi)
                else:
                    az, el = sc.azim_to, sc.elev
                rgb = renderer.render(spec, sc, elev=el, azim=az)
                frames.append(_caption_bar(Image.fromarray(rgb), sc.step_label, sc.caption))
    finally:
        renderer.close()

    path.parent.mkdir(parents=True, exist_ok=True)
    import imageio

    with imageio.get_writer(str(path), fps=fps, codec="libx264", macro_block_size=1) as w:
        for f in frames:
            w.append_data(np.array(f))
    return path
