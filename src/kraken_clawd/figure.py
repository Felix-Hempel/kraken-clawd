"""Claude-Code-Figur als Pixelraster, Palette und Hintergrund."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SIZE = 240
CENTER = (120, 128)
SCALE = 8
# Die CLI zeichnet die Figur aus Halbblock-Zeichen: ein Rasterpixel ist doppelt so hoch wie breit.
ASPECT = 2

BODY = (155, 107, 255)
SHADOW = (106, 63, 209)
HIGHLIGHT = (201, 176, 255)
EYE = (18, 10, 30)
ALERT = (208, 64, 138)
INK = (232, 221, 255)

# Abgeleitet aus dem Welcome-Mascot der CLI:  ▐▛███▜▌ / ▝▜█████▛▘ / ▘▘ ▝▝
# '#' Körper, 'o' Auge, '.' leer
GRID = (
    "...############...",
    "...##o######o##...",
    ".################.",
    "...############...",
    "....#.#....#.#....",
)
LEGS_STEP = ".....#.#..#.#....."


@dataclass(frozen=True)
class Pose:
    dx: int = 0
    dy: int = 0
    blink: bool = False
    arm_left: bool = False
    arm_right: bool = False
    step: bool = False
    lying: bool = False
    tint: tuple[int, int, int] | None = None


def grid_for(pose: Pose) -> list[str]:
    rows = [list(r) for r in GRID]
    if pose.blink:
        rows[1] = ["-" if c == "o" else c for c in rows[1]]
    if pose.arm_left:
        rows[2][1] = rows[2][2] = "."
        rows[1][2] = rows[0][1] = "#"
    if pose.arm_right:
        rows[2][15] = rows[2][16] = "."
        rows[1][15] = rows[0][16] = "#"
    if pose.step:
        rows[4] = list(LEGS_STEP)
    return ["".join(r) for r in rows]


def clawd_image(scale: int, pose: Pose = Pose()) -> Image.Image:
    px, py = scale, scale * ASPECT
    img = Image.new("RGBA", (len(GRID[0]) * px, len(GRID) * py), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    body = pose.tint or BODY
    lid = max(1, py // 4)
    for y, row in enumerate(grid_for(pose)):
        for x, c in enumerate(row):
            if c == ".":
                continue
            box = (x * px, y * py, (x + 1) * px - 1, (y + 1) * py - 1)
            if c == "o":
                d.rectangle(box, fill=EYE)
            else:
                d.rectangle(box, fill=body)
                if c == "-":
                    d.rectangle((box[0], box[3] - lid + 1, box[2], box[3]), fill=EYE)
    return img.rotate(180) if pose.lying else img


def paste_clawd(canvas: Image.Image, cx: float, cy: float, scale: int,
                pose: Pose = Pose()) -> tuple[int, int, int, int]:
    sprite = clawd_image(scale, pose)
    x0 = round(cx - sprite.width / 2 + pose.dx)
    y0 = round(cy - sprite.height / 2 + pose.dy)
    canvas.alpha_composite(sprite, (x0, y0))
    return x0, y0, x0 + sprite.width, y0 + sprite.height


@lru_cache(maxsize=1)
def background() -> Image.Image:
    """Dunkler Violett-Verlauf wie das Eclipse-Bild (kraken_gif.py)."""
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32) / SIZE
    bg = np.stack([6 + 30 * yy, 5 + 12 * yy, 18 + 40 * yy], -1)
    bg += np.exp(-(((xx - .5) ** 2 + (yy - .5) ** 2) / 0.08))[..., None] * np.array([40, 30, 70])
    return Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert("RGBA")


@lru_cache(maxsize=None)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)
