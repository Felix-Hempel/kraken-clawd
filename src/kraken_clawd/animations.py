"""Animationen: pro Zustand eine Frame-Folge (Figur + Requisiten) auf transparentem Layer."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from PIL import Image, ImageDraw

from .figure import ALERT, CENTER, HIGHLIGHT, INK, SCALE, SHADOW, SIZE, Pose, font, paste_clawd

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


JUMP = (0, -6, -12, -16, -12, -6, 0, 0)


def _mix(a: tuple, b: tuple, t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _star(d: ImageDraw.ImageDraw, x: int, y: int, r: int, color) -> None:
    d.line((x - r, y, x + r, y), fill=color, width=3)
    d.line((x, y - r, x, y + r), fill=color, width=3)


def _thinking(c, i):
    paste_clawd(c, CX, CY, SCALE, Pose(dy=_breath(i, 6, 2)))
    d = ImageDraw.Draw(c)
    active = (i // 2) % 3
    for k in range(3):
        r = 7 if k == active else 4
        x, y = 100 + 20 * k, CY - 62
        d.ellipse((x - r, y - r, x + r, y + r), fill=INK if k == active else HIGHLIGHT)


def _typing(c, i):
    paste_clawd(c, CX, CY - 6, SCALE, Pose(arm_left=i % 2 == 0, arm_right=i % 2 == 1, dy=-(i % 2)))
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((64, CY + 40, 176, CY + 60), 4, fill=SHADOW)
    for k in range(8):
        x, down = 70 + k * 13, 2 if k == (i * 3) % 8 else 0
        d.rectangle((x, CY + 44 + down, x + 9, CY + 52 + down), fill=INK if down else HIGHLIGHT)


def _reading(c, i):
    paste_clawd(c, CX, CY, SCALE, Pose(arm_right=True))
    d = ImageDraw.Draw(c)
    x, y = CX + round(40 * math.sin(2 * math.pi * i / 8)), CY - 8
    d.line((x + 14, y + 14, x + 30, y + 30), fill=SHADOW, width=7)
    d.ellipse((x - 20, y - 20, x + 20, y + 20), outline=INK, width=5)


def _bash(c, i):
    up = i < 2
    paste_clawd(c, CX - 16, CY, SCALE, Pose(arm_right=up, dy=0 if up else 2))
    d = ImageDraw.Draw(c)
    hx, hy = CX + 52, CY + 4
    ang = math.radians(-60 if up else 20)
    tx, ty = hx + 36 * math.cos(ang), hy + 36 * math.sin(ang)
    d.line((hx, hy, tx, ty), fill=HIGHLIGHT, width=6)
    nx, ny = -math.sin(ang) * 12, math.cos(ang) * 12
    d.line((tx - nx, ty - ny, tx + nx, ty + ny), fill=INK, width=14)
    if i == 2:
        for a in range(0, 360, 60):
            r = math.radians(a)
            d.line((tx + 10 * math.cos(r), ty + 10 * math.sin(r),
                    tx + 20 * math.cos(r), ty + 20 * math.sin(r)), fill=ALERT, width=3)


def _conducting(c, i):
    sway = math.sin(2 * math.pi * i / 8)
    paste_clawd(c, CX, CY, SCALE, Pose(arm_left=sway < 0, arm_right=sway >= 0, dy=_breath(i, 8, 2)))
    d = ImageDraw.Draw(c)
    hx, hy = CX + 60, CY - 36
    ang = math.radians(-90 + 45 * sway)
    d.line((hx, hy, hx + 40 * math.cos(ang), hy + 40 * math.sin(ang)), fill=INK, width=4)


def _working(c, i):
    paste_clawd(c, CX, CY, SCALE, Pose(step=i % 2 == 1, dy=-2 if i % 2 else 0))


def _waiting(c, i):
    j = JUMP[i]
    paste_clawd(c, CX, CY + 4, SCALE, Pose(dy=j, arm_left=i in (2, 3, 4), arm_right=i in (1, 3, 5)))
    d = ImageDraw.Draw(c)
    d.ellipse((8, 8, 231, 231), outline=_mix(SHADOW, ALERT, abs(math.sin(math.pi * i / 8))), width=6)
    d.rounded_rectangle((115, 30 + j, 125, 56 + j), 3, fill=INK)
    d.ellipse((115, 60 + j, 125, 70 + j), fill=INK)


def _done(c, i):
    paste_clawd(c, CX, CY, SCALE, Pose(dy=JUMP[i], arm_left=True, arm_right=True))
    d = ImageDraw.Draw(c)
    for k, (x, y) in enumerate(((60, 70), (180, 70), (40, 140), (200, 140))):
        if (i + k) % 2 == 0:
            _star(d, x, y, 8, INK)


def _celebrate(c, i):
    paste_clawd(c, CX, CY, SCALE, Pose(dy=JUMP[i % 8], arm_left=True, arm_right=True))
    d = ImageDraw.Draw(c)
    for k in range(24):
        rng = random.Random(k)
        x = rng.uniform(40, 200)
        y = 30 + (rng.uniform(0, 180) + i * rng.uniform(8, 16)) % 180
        color = rng.choice((HIGHLIGHT, INK, ALERT, SHADOW))
        if math.hypot(x + 2 - 120, y + 3 - 120) > 110:
            continue
        d.rectangle((x, y, x + 4, y + 6), fill=color)


def _error(c, i):
    paste_clawd(c, CX, CY, SCALE, Pose(dx=(-4, 4)[i % 2], tint=ALERT if i % 2 == 0 else None,
                                       arm_left=True, arm_right=True))


def _limit(c, i):
    paste_clawd(c, CX, CY + 20, SCALE, Pose(lying=True, blink=True))
    d = ImageDraw.Draw(c)
    d.rectangle((90, 46, 146, 72), outline=INK, width=3)
    d.rectangle((146, 54, 152, 64), fill=INK)
    if i % 2 == 0:
        d.rectangle((95, 51, 103, 67), fill=ALERT)


def _sleep(c, i):
    paste_clawd(c, CX, CY + 8, SCALE, Pose(blink=True, dy=_breath(i, 12, 2)))
    d = ImageDraw.Draw(c)
    for k, size in enumerate((18, 24, 30)):
        phase = (i + k * 4) % 12
        d.text((140 + k * 14 + phase, 100 - k * 16 - phase * 2), "z", font=font(size),
               fill=INK if phase < 8 else SHADOW)


ANIMATIONS: dict[str, Anim] = {
    "idle": Anim(12, 6, _idle),
    "thinking": Anim(6, 6, _thinking),
    "typing": Anim(4, 10, _typing),
    "reading": Anim(8, 6, _reading),
    "bash": Anim(4, 8, _bash),
    "conducting": Anim(8, 6, _conducting),
    "working": Anim(4, 8, _working),
    "waiting": Anim(8, 6, _waiting),
    "done": Anim(8, 8, _done),
    "celebrate": Anim(12, 10, _celebrate),
    "error": Anim(6, 10, _error),
    "limit": Anim(4, 2, _limit),
    "sleep": Anim(12, 3, _sleep),
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
