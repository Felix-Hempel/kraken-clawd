"""View → fertiges 240×240-Frame inkl. Mini-Clawds, Subagent-Klone und Extras."""
from __future__ import annotations

import math
import time

from PIL import Image, ImageDraw

from .animations import frame_at
from .figure import ALERT, INK, Pose, background, font, paste_clawd
from .state import SessionView, View

MINI_SCALE = 2
MAX_MINIS = 4
MAX_CLONES = 3
MINI_Y = 200
MINI_GAP = 36
ARC_R = 95


def nightcap_active(now: float) -> bool:
    lt = time.localtime(now)
    return lt.tm_hour == 0 and lt.tm_min == 0 and lt.tm_sec < 10


def _mini_pose(state: str, now: float, k: int) -> Pose:
    beat = int(now * 4 + k) % 2 == 0
    if state == "waiting":
        return Pose(dy=-3 if beat else 0, arm_left=beat, arm_right=not beat)
    if state in ("idle", "done", "celebrate"):
        return Pose()
    return Pose(step=beat)


class Renderer:
    def frame(self, view: View, now: float) -> Image.Image:
        canvas = background().copy()
        if view.sleeping or view.main is None:
            canvas.alpha_composite(frame_at("sleep", now))
            return canvas.convert("RGB")
        canvas.alpha_composite(frame_at(view.main.state, now - view.main.since))
        d = ImageDraw.Draw(canvas)
        self._clones(canvas, d, view.main.subagents, now)
        self._minis(canvas, d, view.others, now)
        if nightcap_active(now):
            self._nightcap(d)
        return canvas.convert("RGB")

    def _clones(self, canvas: Image.Image, d: ImageDraw.ImageDraw, n: int, now: float) -> None:
        if n <= 0:
            return
        if n > MAX_CLONES:
            paste_clawd(canvas, 100, 40, MINI_SCALE, Pose(step=int(now * 4) % 2 == 0))
            d.text((122, 28), f"x{n}", font=font(22), fill=INK)
            return
        for k in range(n):
            ang = math.pi + math.pi * (k + 1) / (n + 1)
            x = 120 + ARC_R * math.cos(ang)
            y = 120 + ARC_R * math.sin(ang) + 2 * math.sin(now * 6 + k)
            paste_clawd(canvas, x, y, MINI_SCALE, Pose(step=int(now * 6 + k) % 2 == 0))

    def _minis(self, canvas: Image.Image, d: ImageDraw.ImageDraw,
               others: tuple[SessionView, ...], now: float) -> None:
        if not others:
            return
        shown = others if len(others) <= MAX_MINIS else others[:MAX_MINIS - 1]
        slots = len(shown) + (len(others) > MAX_MINIS)
        x0 = 120 - (slots - 1) * MINI_GAP / 2
        for k, s in enumerate(shown):
            paste_clawd(canvas, x0 + k * MINI_GAP, MINI_Y, MINI_SCALE, _mini_pose(s.state, now, k))
        if len(others) > MAX_MINIS:
            x = x0 + len(shown) * MINI_GAP
            d.text((x - 14, MINI_Y - 10), f"+{len(others) - len(shown)}", font=font(18), fill=INK)

    @staticmethod
    def _nightcap(d: ImageDraw.ImageDraw) -> None:
        d.polygon(((140, 90), (186, 90), (180, 50)), fill=INK)
        d.ellipse((172, 40, 188, 56), fill=ALERT)
