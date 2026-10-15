"""Animationen: pro Zustand eine Frame-Folge (Figur + Requisiten) auf transparentem Layer."""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from PIL import Image

from .figure import CENTER, SCALE, SIZE, Pose, paste_clawd

CX, CY = CENTER


@dataclass(frozen=True)
class Anim:
    frames: int
    fps: float
    draw: Callable[[Image.Image, int], None]


def _breath(i: int, n: int, amp: int = 3) -> int:
    return round(amp * math.sin(2 * math.pi * i / n))


def _idle(c: Image.Image, i: int) -> None:
    paste_clawd(c, CX, CY, SCALE, Pose(dy=_breath(i, 12), blink=i == 11))


ANIMATIONS: dict[str, Anim] = {
    "idle": Anim(12, 6, _idle),
}


@lru_cache(maxsize=None)
def layer(name: str, i: int) -> Image.Image:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ANIMATIONS[name].draw(canvas, i)
    return canvas


def frame_at(name: str, t: float) -> Image.Image:
    if name not in ANIMATIONS:
        name = "idle"
    anim = ANIMATIONS[name]
    return layer(name, int(t * anim.fps + 1e-9) % anim.frames)
