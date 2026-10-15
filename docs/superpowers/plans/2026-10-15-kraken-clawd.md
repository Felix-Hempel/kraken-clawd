# kraken-clawd Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Claude-Code-Figur läuft animiert und in Lila auf dem LCD der NZXT Kraken 2023 und reagiert live auf alle lokalen Claude-Code-Sessions.

**Architecture:** Ein Python-Daemon (systemd-User-Service) nimmt Claude-Code-Hooks per HTTP auf `127.0.0.1:7377` entgegen, verdichtet sie in einem reinen Zustandsmodell zu einer `View` und rendert daraus mit 15 fps 240×240-Frames (PIL), die über liquidctl direkt als RGB565 an die Kraken gehen.

**Tech Stack:** Python 3.13, uv, liquidctl 1.16.0 (exakt), Pillow, numpy, pytest; node für den Hook-Installer; systemd --user.

**Spec:** `docs/superpowers/specs/2026-10-15-kraken-clawd-design.md`

## Global Constraints

- Repo: `~/Documents/IT/kraken-clawd`, privates Projekt → Commits direkt auf `main`, Conventional Commits, Footer `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- `liquidctl==1.16.0` exakt gepinnt (private Methode `_send_2023_data_fw2` wird genutzt).
- LCD 240×240, rund: alle Inhalte innerhalb Radius 120 um (120,120).
- HTTP-Server bindet nur `127.0.0.1`, Port `7377`, antwortet auf `/hook` immer `200` mit Body `{}`.
- Palette: Körper `#9B6BFF`, Schatten `#6A3FD1`, Highlight `#C9B0FF`, Augen `#120A1E`, Fehler-Akzent `#D0408A`, Tinte `#E8DDFF`.
- Zeiten: error 1,5 s; done 2 s; celebrate 4 s, ab 30 min Arbeitsphase; sleep nach 30 min ohne Hook; Dimmen (20 %) nach 40 min; Mini-Clawd ausgeblendet ab 10 min idle; Session-TTL 2 h.
- Präzisierungen gegenüber Spec (bewusst): Figur-Raster 18×5 mit Pixel-Seitenverhältnis 1:2 (abgeleitet aus den Halbblock-Zeichen der CLI); `limit` = Figur liegt auf dem Rücken (180° gedreht); eine Session im Zustand `waiting` verhindert `sleep`; gecacht werden die Animations-Layer als RGBA-Bilder, die RGB565-Konvertierung passiert pro Frame (numpy, < 1 ms).
- Kein Code mit `TODO`/`FIXME`/`HACK`.

## Review Focus

1. Hooks aus Subagents (Payload enthält `agent_id`) dürfen den Zustand der Haupt-Session nicht überschreiben – außer `waiting`. → Test in Task 3.
2. Hooks einer `session_id` ohne vorheriges `SessionStart` (Daemon wurde während laufender Sessions gestartet) legen die Session implizit an. → Test in Task 3.
3. `SubagentStop` ohne `SubagentStart` oder doppelt → Zähler nie negativ, `Stop` setzt ihn zurück. → Test in Task 3.
4. Kraken verschwindet zur Laufzeit (Suspend/Resume, USB-Reset) → kein Absturz, Reconnect mit Backoff 1 s → 30 s. → Test in Task 2.
5. Eine Session wartet > 30 min auf eine Freigabe → Clawd schläft nicht ein, `waiting` bleibt sichtbar. → Test in Task 3.

---

## Dateistruktur

```
kraken-clawd/
├─ pyproject.toml, .gitignore, README.md
├─ src/kraken_clawd/
│  ├─ __init__.py
│  ├─ __main__.py      Daemon-Einstieg (Server + Display + Loop)
│  ├─ figure.py        Palette, Pixelraster, Pose, clawd_image/paste_clawd, background, font
│  ├─ animations.py    Anim + ANIMATIONS (Zustand → Frame-Folge), frame_at
│  ├─ render.py        Renderer: View → 240×240-Frame inkl. Overlays
│  ├─ state.py         Store: Hook-Events → View (reine Logik)
│  ├─ server.py        HookServer (http.server, Thread)
│  ├─ lcd.py           to_rgb565, Display (Fast-Path, Fallback, Reconnect)
│  ├─ loop.py          run(): Render-Schleife
│  ├─ preview.py       schreibt preview/*.gif
│  └─ try_lcd.py       manuelles Abspielen einer Animation auf der Kraken
├─ tests/ test_figure.py, test_animations.py, test_lcd.py, test_state.py,
│         test_server.py, test_render.py, test_loop.py
├─ demo.sh             curl-Sequenz durch alle Zustände
├─ install-hooks.mjs   trägt HTTP-Hooks in ~/.claude/settings.json ein / aus
└─ systemd/kraken-clawd.service
```

---

### Task 1: Projektgerüst, Figur und Idle-Animation mit Preview

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/kraken_clawd/__init__.py`, `src/kraken_clawd/figure.py`, `src/kraken_clawd/animations.py`, `src/kraken_clawd/preview.py`
- Test: `tests/test_figure.py`, `tests/test_animations.py`

**Interfaces:**
- Produces:
  - `figure.SIZE = 240`, `figure.CENTER = (120, 128)`, `figure.SCALE = 8`, Farbkonstanten `BODY, SHADOW, HIGHLIGHT, EYE, ALERT, INK` (RGB-Tupel)
  - `figure.Pose` (frozen dataclass: `dx:int=0, dy:int=0, blink:bool=False, arm_left:bool=False, arm_right:bool=False, step:bool=False, lying:bool=False, tint:tuple|None=None`)
  - `figure.grid_for(pose: Pose) -> list[str]`
  - `figure.clawd_image(scale: int, pose: Pose = Pose()) -> Image.Image` (RGBA)
  - `figure.paste_clawd(canvas: Image.Image, cx: float, cy: float, scale: int, pose: Pose = Pose()) -> tuple[int,int,int,int]` (Bounding-Box)
  - `figure.background() -> Image.Image` (RGBA 240×240, gecacht – immer `.copy()` verwenden)
  - `figure.font(size: int) -> ImageFont`
  - `animations.Anim(frames: int, fps: float, draw: Callable[[Image.Image, int], None])`
  - `animations.ANIMATIONS: dict[str, Anim]` (in Task 1 nur `"idle"`)
  - `animations.layer(name: str, i: int) -> Image.Image` (RGBA, transparent, gecacht)
  - `animations.frame_at(name: str, t: float) -> Image.Image` (unbekannter Name → `"idle"`)

- [ ] **Step 1: Projektgerüst anlegen**

`pyproject.toml`:
```toml
[project]
name = "kraken-clawd"
version = "0.1.0"
description = "Claude-Code-Figur in Lila auf dem NZXT-Kraken-LCD"
requires-python = ">=3.13"
dependencies = ["liquidctl==1.16.0", "pillow>=11", "numpy>=2"]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/kraken_clawd"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:
```
.venv/
__pycache__/
preview/
*.pyc
```

`src/kraken_clawd/__init__.py`:
```python
"""Claude-Code-Figur auf dem Kraken-LCD."""
```

Run: `cd ~/Documents/IT/kraken-clawd && uv sync`
Expected: `.venv` angelegt, liquidctl 1.16.0, pillow, numpy, pytest installiert.

- [ ] **Step 2: Failing Tests für die Figur schreiben**

`tests/test_figure.py`:
```python
from kraken_clawd.figure import (
    ASPECT, BODY, EYE, GRID, SIZE, Pose, background, clawd_image, grid_for, paste_clawd,
)
from PIL import Image


def test_grid_is_rectangular_and_mirror_symmetric():
    assert len({len(r) for r in GRID}) == 1
    for row in GRID:
        assert row == row[::-1]


def test_clawd_image_size_follows_grid_and_aspect():
    img = clawd_image(8)
    assert img.size == (len(GRID[0]) * 8, len(GRID) * 8 * ASPECT)
    assert img.mode == "RGBA"


def test_clawd_uses_only_palette_colors():
    colors = {c[:3] for _, c in clawd_image(4).getcolors(10_000) if c[3] == 255}
    assert colors == {BODY, EYE}


def test_blink_closes_eyes():
    open_eyes = sum(r.count("o") for r in grid_for(Pose()))
    closed = grid_for(Pose(blink=True))
    assert open_eyes == 2
    assert sum(r.count("o") for r in closed) == 0
    assert sum(r.count("-") for r in closed) == 2


def test_raised_arms_move_pixels_up():
    g = grid_for(Pose(arm_left=True, arm_right=True))
    assert g[0][1] == "#" and g[0][16] == "#"
    assert g[2][1] == "." and g[2][16] == "."


def test_lying_turns_figure_upside_down():
    normal = clawd_image(4)
    lying = clawd_image(4, Pose(lying=True))
    assert lying.size == normal.size
    assert lying.tobytes() == normal.rotate(180).tobytes()


def test_tint_replaces_body_color():
    colors = {c[:3] for _, c in clawd_image(4, Pose(tint=(1, 2, 3))).getcolors(10_000) if c[3] == 255}
    assert (1, 2, 3) in colors and BODY not in colors


def test_paste_returns_bbox_inside_canvas():
    canvas = Image.new("RGBA", (SIZE, SIZE))
    x0, y0, x1, y1 = paste_clawd(canvas, 120, 128, 8)
    assert 0 <= x0 < x1 <= SIZE and 0 <= y0 < y1 <= SIZE


def test_background_is_cached_rgba():
    assert background() is background()
    assert background().size == (SIZE, SIZE) and background().mode == "RGBA"
```

- [ ] **Step 3: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_figure.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'kraken_clawd.figure'`

- [ ] **Step 4: `figure.py` implementieren**

`src/kraken_clawd/figure.py`:
```python
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
```

- [ ] **Step 5: Figur-Tests grün**

Run: `uv run pytest tests/test_figure.py -v`
Expected: 9 passed

- [ ] **Step 6: Failing Tests für Animationen schreiben**

`tests/test_animations.py`:
```python
from kraken_clawd.animations import ANIMATIONS, frame_at, layer
from kraken_clawd.figure import SIZE


def test_every_animation_draws_visible_frames():
    for name, anim in ANIMATIONS.items():
        assert anim.frames >= 1 and anim.fps > 0, name
        for i in range(anim.frames):
            img = layer(name, i)
            assert img.size == (SIZE, SIZE) and img.mode == "RGBA", name
            assert img.getbbox() is not None, f"{name}[{i}] leer"


def test_layers_are_cached():
    assert layer("idle", 0) is layer("idle", 0)


def test_frame_at_loops_with_fps():
    anim = ANIMATIONS["idle"]
    assert frame_at("idle", 0) is layer("idle", 0)
    assert frame_at("idle", anim.frames / anim.fps) is layer("idle", 0)
    assert frame_at("idle", 1 / anim.fps) is layer("idle", 1)


def test_unknown_animation_falls_back_to_idle():
    assert frame_at("gibt-es-nicht", 0) is layer("idle", 0)


def test_idle_moves():
    frames = {layer("idle", i).tobytes() for i in range(ANIMATIONS["idle"].frames)}
    assert len(frames) > 1
```

- [ ] **Step 7: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_animations.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'kraken_clawd.animations'`

- [ ] **Step 8: `animations.py` mit Idle implementieren**

`src/kraken_clawd/animations.py`:
```python
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
```

- [ ] **Step 9: Animations-Tests grün**

Run: `uv run pytest -v`
Expected: alle Tests passed

- [ ] **Step 10: Preview-Skript**

`src/kraken_clawd/preview.py`:
```python
"""Schreibt jede Animation als GIF nach preview/ (Sichtprüfung ohne LCD)."""
from __future__ import annotations

import sys
from pathlib import Path

from .animations import ANIMATIONS, layer
from .figure import background


def write(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, anim in ANIMATIONS.items():
        frames = []
        for i in range(anim.frames):
            f = background().copy()
            f.alpha_composite(layer(name, i))
            frames.append(f.convert("RGB"))
        path = out / f"{name}.gif"
        frames[0].save(path, save_all=True, append_images=frames[1:],
                       duration=round(1000 / anim.fps), loop=0)
        written.append(path)
    return written


if __name__ == "__main__":
    for p in write(Path(sys.argv[1] if len(sys.argv) > 1 else "preview")):
        print(p)
```

Run: `uv run python -m kraken_clawd.preview && xdg-open preview/idle.gif`
Expected: `preview/idle.gif` zeigt die lila Figur, die atmet und einmal blinzelt.

- [ ] **Step 11: CHECKPOINT – Figur mit Felix abgleichen**

`preview/idle.gif` (und ggf. ein 4×-skaliertes PNG) Felix zeigen und mit dem Stream-Deck-Icon/CLI-Welcome-Mascot vergleichen lassen. Änderungen am Raster nur in `GRID`/`LEGS_STEP`/`grid_for` vornehmen; die Tests (Symmetrie, Palette, Augen) müssen weiter grün sein. Erst nach Felix' Okay weiter.

- [ ] **Step 12: Commit**

```bash
git add pyproject.toml uv.lock .gitignore src tests
git commit -m "feat(figure): Clawd-Pixelraster in Lila, Idle-Animation und GIF-Preview

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: LCD-Ausgabe und Live-Prototyp

**Files:**
- Create: `src/kraken_clawd/lcd.py`, `src/kraken_clawd/try_lcd.py`
- Test: `tests/test_lcd.py`

**Interfaces:**
- Consumes: `animations.frame_at`, `figure.background` (Task 1)
- Produces:
  - `lcd.to_rgb565(img: Image.Image, rotation: int = 0) -> bytes` (big-endian, 2 Byte/Pixel)
  - `lcd.Display(finder=find_liquidctl_devices, clock=time.monotonic, tmp: Path = …)` mit `show(img: Image.Image) -> None`, `brightness(pct: int) -> None`, `close() -> None`. Keine Methode wirft bei Gerätefehlern.

- [ ] **Step 1: Failing Tests schreiben**

`tests/test_lcd.py`:
```python
from types import SimpleNamespace

from liquidctl.driver.kraken3 import KrakenZ3
from PIL import Image

from kraken_clawd.lcd import Display, to_rgb565


class FakeDev:
    description = "NZXT Kraken 2023"

    def __init__(self, fast_error=None):
        self.calls = []
        self._fw = (2, 0, 0)
        self.orientation = 0
        self.broken = False
        self.fast_error = fast_error

    def connect(self):
        self.calls.append("connect")

    def initialize(self):
        self.calls.append("init")

    def disconnect(self):
        self.calls.append("disconnect")

    def set_screen(self, channel, mode, value):
        if self.broken:
            raise OSError("usb weg")
        self.calls.append(("screen", mode, value))

    def _send_2023_data_fw2(self, data, info):
        if self.broken:
            raise OSError("usb weg")
        if self.fast_error:
            raise self.fast_error
        self.calls.append(("fast", len(data), info))


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def img(color=(155, 107, 255)):
    return Image.new("RGB", (240, 240), color)


def test_rgb565_matches_liquidctl(tmp_path):
    src = Image.effect_noise((240, 240), 80).convert("RGB")
    path = tmp_path / "n.png"
    src.save(path)
    fake_self = SimpleNamespace(lcd_resolution=(240, 240))
    expected = bytes(KrakenZ3._prepare_static_file_rgb16(fake_self, str(path), 1))
    assert to_rgb565(src, 1) == expected


def test_first_frame_public_then_fast_path(tmp_path):
    dev = FakeDev()
    d = Display(finder=lambda: [dev], clock=Clock(), tmp=tmp_path / "f.png")
    d.show(img())
    d.show(img())
    assert dev.calls[:2] == ["connect", "init"]
    assert dev.calls[2][:2] == ("screen", "static")
    assert dev.calls[3][0] == "fast" and dev.calls[3][1] == 240 * 240 * 2
    assert dev.calls[3][2] == [0x06, 0, 0, 0] + list((240 * 240 * 2).to_bytes(4, "little"))


def test_falls_back_when_private_api_changed(tmp_path):
    dev = FakeDev(fast_error=TypeError("signatur geändert"))
    d = Display(finder=lambda: [dev], clock=Clock(), tmp=tmp_path / "f.png")
    for _ in range(3):
        d.show(img())
    screens = [c for c in dev.calls if isinstance(c, tuple) and c[0] == "screen"]
    assert len(screens) == 3
    assert "disconnect" not in dev.calls


def test_usb_error_reconnects_with_backoff(tmp_path):
    dev, clock, finds = FakeDev(), Clock(), []
    d = Display(finder=lambda: finds.append(1) or [dev], clock=clock, tmp=tmp_path / "f.png")
    d.show(img())
    d.show(img())
    dev.broken = True
    d.show(img())                       # Fehler -> getrennt, nächster Versuch in 1 s
    assert "disconnect" in dev.calls
    dev.broken = False
    d.show(img())
    assert len(finds) == 1              # noch im Backoff
    clock.t = 1.1
    d.show(img())
    assert len(finds) == 2


def test_missing_device_never_raises(tmp_path):
    clock = Clock()
    d = Display(finder=lambda: [], clock=clock, tmp=tmp_path / "f.png")
    d.show(img())
    d.brightness(50)
    clock.t = 100
    d.show(img())
    d.close()


def test_brightness_only_sent_on_change(tmp_path):
    dev = FakeDev()
    d = Display(finder=lambda: [dev], clock=Clock(), tmp=tmp_path / "f.png")
    for pct in (100, 100, 20, 20):
        d.brightness(pct)
    assert [c for c in dev.calls if isinstance(c, tuple) and c[1] == "brightness"] == [
        ("screen", "brightness", 100), ("screen", "brightness", 20)]
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_lcd.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'kraken_clawd.lcd'`

- [ ] **Step 3: `lcd.py` implementieren**

`src/kraken_clawd/lcd.py`:
```python
"""Ausgabe auf das Kraken-2023-LCD (Firmware 2.x): Fast-Path über liquidctl-Interna, Fallback set_screen."""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Callable

import numpy as np
from liquidctl import find_liquidctl_devices
from PIL import Image

log = logging.getLogger(__name__)
MAX_DELAY = 30.0


def to_rgb565(img: Image.Image, rotation: int = 0) -> bytes:
    """Wie liquidctl _prepare_static_file_rgb16, aber vektorisiert. rotation in 90°-Schritten."""
    a = np.asarray(img.convert("RGB").rotate(rotation * -90), dtype=np.uint16)
    v = ((a[..., 0] >> 3) << 11) | ((a[..., 1] >> 2) << 5) | (a[..., 2] >> 3)
    return v.astype(">u2").tobytes()


class Display:
    def __init__(self, finder: Callable = find_liquidctl_devices,
                 clock: Callable[[], float] = time.monotonic,
                 tmp: Path = Path(tempfile.gettempdir()) / "kraken-clawd-frame.png"):
        self._finder, self._clock, self._tmp = finder, clock, tmp
        self._dev = None
        self._fast = False
        self._first = True
        self._brightness: int | None = None
        self._retry_at = 0.0
        self._delay = 1.0

    def _connect(self) -> None:
        dev = next((d for d in self._finder() if "Kraken" in d.description), None)
        if dev is None:
            raise LookupError("keine Kraken gefunden")
        dev.connect()
        try:
            dev.initialize()
        except Exception:
            dev.disconnect()
            raise
        self._dev = dev
        self._fast = hasattr(dev, "_send_2023_data_fw2") and getattr(dev, "_fw", (0,))[0] == 2
        self._first = True
        self._brightness = None
        log.info("Kraken verbunden (Fast-Path: %s)", self._fast)

    def _ensure(self) -> bool:
        if self._dev is not None:
            return True
        if self._clock() < self._retry_at:
            return False
        try:
            self._connect()
        except Exception as e:
            log.warning("Kraken nicht verfügbar (%s), neuer Versuch in %.0f s", e, self._delay)
            self._backoff()
            return False
        self._delay = 1.0
        return True

    def _backoff(self) -> None:
        self._retry_at = self._clock() + self._delay
        self._delay = min(self._delay * 2, MAX_DELAY)

    def _fail(self, e: Exception) -> None:
        log.warning("LCD-Fehler: %s", e)
        try:
            self._dev.disconnect()
        except Exception:
            pass
        self._dev = None
        self._backoff()

    def _show_public(self, img: Image.Image) -> None:
        img.convert("RGB").save(self._tmp)
        self._dev.set_screen("lcd", "static", str(self._tmp))

    def _show_fast(self, img: Image.Image) -> None:
        data = to_rgb565(img, getattr(self._dev, "orientation", 0))
        self._dev._send_2023_data_fw2(data, [0x06, 0, 0, 0] + list(len(data).to_bytes(4, "little")))

    def show(self, img: Image.Image) -> None:
        if not self._ensure():
            return
        try:
            if self._first or not self._fast:
                # set_screen sendet nach initialize doppelt und liest die Orientierung aus
                self._show_public(img)
                self._first = False
                return
            try:
                self._show_fast(img)
            except (AttributeError, TypeError, ValueError) as e:
                log.warning("Fast-Path nicht nutzbar (%s), Fallback set_screen", e)
                self._fast = False
                self._show_public(img)
        except Exception as e:
            self._fail(e)

    def brightness(self, pct: int) -> None:
        if pct == self._brightness or not self._ensure():
            return
        try:
            self._dev.set_screen("lcd", "brightness", pct)
            self._brightness = pct
        except Exception as e:
            self._fail(e)

    def close(self) -> None:
        if self._dev is not None:
            try:
                self._dev.disconnect()
            except Exception:
                pass
            self._dev = None
```

- [ ] **Step 4: Tests grün**

Run: `uv run pytest tests/test_lcd.py -v`
Expected: 6 passed

- [ ] **Step 5: Manuelles Abspiel-Skript**

`src/kraken_clawd/try_lcd.py`:
```python
"""Spielt eine Animation N Sekunden auf der Kraken ab, danach Eclipse-Bild zurück.

uv run python -m kraken_clawd.try_lcd idle 20
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

from .animations import frame_at
from .figure import background
from .lcd import Display

KRAKEN_SH = Path.home() / ".config/rgb-aurora/kraken.sh"


def main(name: str, seconds: float, fps: float = 15) -> None:
    logging.basicConfig(level=logging.INFO)
    d = Display()
    start = time.monotonic()
    shown = 0
    try:
        while (t := time.monotonic() - start) < seconds:
            f = background().copy()
            f.alpha_composite(frame_at(name, t))
            d.show(f)
            shown += 1
            time.sleep(max(0.0, (shown / fps) - (time.monotonic() - start)))
    finally:
        d.close()
        print(f"{shown} Frames in {time.monotonic() - start:.1f} s")
        if KRAKEN_SH.exists():
            subprocess.run([str(KRAKEN_SH)], check=False)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "idle", float(sys.argv[2]) if len(sys.argv) > 2 else 20)
```

- [ ] **Step 6: CHECKPOINT – Sichtprüfung am echten LCD**

Run: `uv run python -m kraken_clawd.try_lcd idle 20`
Expected: Ausgabe ca. `300 Frames in 20.0 s`; danach steht wieder das Eclipse-Bild. Felix schaut während der 20 s aufs LCD: Figur zentriert und aufrecht, kein Flackern oder Tearing, Lila wirkt passend. Bei falscher Ausrichtung prüfen, welchen Wert `dev.orientation` hat; bei Tearing fps in `try_lcd.main(..., fps=10)` testen und das Ergebnis notieren (bestimmt `FPS` in Task 5). Farb-Feintuning nur in den Konstanten von `figure.py`.

- [ ] **Step 7: Commit**

```bash
git add src/kraken_clawd/lcd.py src/kraken_clawd/try_lcd.py tests/test_lcd.py
git commit -m "feat(lcd): RGB565-Fast-Path, Fallback und Reconnect für das Kraken-LCD

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Zustandsmodell (TDD)

**Files:**
- Create: `src/kraken_clawd/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces:
  - `state.Store(created: float)` mit `apply(event: dict, now: float) -> None` und `view(now: float) -> View`
  - `state.View` (frozen: `main: SessionView | None`, `others: tuple[SessionView, ...]`, `sleeping: bool`, `dimmed: bool`)
  - `state.SessionView` (frozen: `state: str`, `subagents: int`, `since: float`)
  - Zustandsnamen: `idle, thinking, typing, reading, bash, conducting, working, waiting, done, celebrate, error, limit` (identisch mit Animationsnamen; `sleep` ist kein Session-Zustand, sondern `View.sleeping`)

- [ ] **Step 1: Failing Tests schreiben**

`tests/test_state.py`:
```python
import pytest

from kraken_clawd.state import Store


def ev(name, sid="a", **kw):
    return {"hook_event_name": name, "session_id": sid, **kw}


@pytest.fixture
def store():
    return Store(created=0.0)


def main_state(store, now):
    v = store.view(now)
    return v.main.state if v.main else None


@pytest.mark.parametrize("tool,expected", [
    ("Edit", "typing"), ("Write", "typing"), ("MultiEdit", "typing"), ("NotebookEdit", "typing"),
    ("Read", "reading"), ("Grep", "reading"), ("Glob", "reading"),
    ("WebFetch", "reading"), ("WebSearch", "reading"),
    ("Bash", "bash"), ("Agent", "conducting"), ("Task", "conducting"),
    ("mcp__server__server_run", "working"),
])
def test_pre_tool_use_maps_tool(store, tool, expected):
    store.apply(ev("PreToolUse", tool_name=tool), 1)
    assert main_state(store, 1) == expected


def test_prompt_and_post_tool_mean_thinking(store):
    store.apply(ev("UserPromptSubmit"), 1)
    assert main_state(store, 1) == "thinking"
    store.apply(ev("PreToolUse", tool_name="Bash"), 2)
    store.apply(ev("PostToolUse", tool_name="Bash"), 3)
    assert main_state(store, 3) == "thinking"


@pytest.mark.parametrize("payload", [
    ev("PermissionRequest", tool_name="Bash"),
    ev("Notification", notification_type="permission_prompt"),
    ev("Notification", notification_type="elicitation_dialog"),
    ev("Notification", notification_type="agent_needs_input"),
])
def test_waiting_triggers(store, payload):
    store.apply(payload, 1)
    assert main_state(store, 1) == "waiting"


def test_idle_prompt_notification_means_idle(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("Notification", notification_type="idle_prompt"), 2)
    assert main_state(store, 2) == "idle"


def test_unknown_notification_type_is_ignored(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("Notification", notification_type="sonstwas"), 2)
    assert main_state(store, 2) == "thinking"


def test_stop_shows_done_then_idle(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("Stop", stop_hook_active=False), 10)
    assert main_state(store, 11) == "done"
    assert main_state(store, 12.1) == "idle"


def test_stop_with_active_stop_hook_is_ignored(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("Stop", stop_hook_active=True), 2)
    assert main_state(store, 2) == "thinking"


def test_long_work_celebrates(store):
    store.apply(ev("UserPromptSubmit"), 0)
    store.apply(ev("PostToolUse"), 1700)
    store.apply(ev("Stop"), 1801)
    assert main_state(store, 1802) == "celebrate"
    assert main_state(store, 1805.1) == "idle"


def test_work_timer_resets_after_done(store):
    store.apply(ev("UserPromptSubmit"), 0)
    store.apply(ev("Stop"), 1801)
    store.apply(ev("UserPromptSubmit"), 1810)
    store.apply(ev("Stop"), 1820)
    assert main_state(store, 1821) == "done"


def test_error_returns_to_previous_state(store):
    store.apply(ev("PreToolUse", tool_name="Edit"), 1)
    store.apply(ev("PostToolUseFailure", tool_name="Edit"), 2)
    assert main_state(store, 2.5) == "error"
    assert main_state(store, 3.6) == "typing"


def test_rate_limit_is_sticky_until_next_prompt(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("StopFailure", error="rate_limit", error_details="429"), 2)
    assert main_state(store, 3) == "limit"
    store.apply(ev("Notification", notification_type="idle_prompt"), 4)
    store.apply(ev("PreToolUse", tool_name="Bash"), 5)
    assert main_state(store, 5) == "limit"
    store.apply(ev("UserPromptSubmit"), 6)
    assert main_state(store, 6) == "thinking"


def test_other_stop_failure_is_error(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("StopFailure", error="server_error"), 2)
    assert main_state(store, 2) == "error"


def test_waiting_session_wins_priority(store):
    store.apply(ev("PreToolUse", "a", tool_name="Edit"), 5)
    store.apply(ev("PermissionRequest", "b", tool_name="Bash"), 1)
    v = store.view(5)
    assert v.main.state == "waiting"
    assert [o.state for o in v.others] == ["typing"]


def test_limit_beats_waiting(store):
    store.apply(ev("PermissionRequest", "a"), 1)
    store.apply(ev("StopFailure", "b", error="rate_limit"), 2)
    assert main_state(store, 2) == "limit"


def test_tie_goes_to_latest_hook(store):
    store.apply(ev("PreToolUse", "a", tool_name="Edit"), 1)
    store.apply(ev("PreToolUse", "b", tool_name="Read"), 2)
    assert main_state(store, 2) == "reading"


def test_subagent_counter(store):
    store.apply(ev("PreToolUse", tool_name="Agent"), 1)
    store.apply(ev("SubagentStart", agent_id="x"), 2)
    store.apply(ev("SubagentStart", agent_id="y"), 2)
    assert store.view(2).main.subagents == 2
    store.apply(ev("SubagentStop", agent_id="x"), 3)
    store.apply(ev("SubagentStop", agent_id="x"), 3)
    store.apply(ev("SubagentStop", agent_id="nie-gestartet"), 3)
    assert store.view(3).main.subagents == 1


def test_stop_resets_subagents(store):
    store.apply(ev("SubagentStart", agent_id="x"), 1)
    store.apply(ev("Stop"), 2)
    assert store.view(2).main.subagents == 0


def test_subagent_hooks_do_not_override_main_state(store):
    store.apply(ev("PreToolUse", tool_name="Agent"), 1)
    store.apply(ev("PreToolUse", tool_name="Read", agent_id="x"), 2)
    store.apply(ev("PostToolUseFailure", tool_name="Read", agent_id="x"), 3)
    assert main_state(store, 3) == "conducting"
    store.apply(ev("PermissionRequest", tool_name="Bash", agent_id="x"), 4)
    assert main_state(store, 4) == "waiting"


def test_unknown_session_is_created_implicitly(store):
    store.apply(ev("PreToolUse", "neu", tool_name="Bash"), 1)
    assert main_state(store, 1) == "bash"


def test_sleep_after_30_min_and_dim_after_40(store):
    store.apply(ev("Stop"), 0)
    assert not store.view(1799).sleeping
    v = store.view(1801)
    assert v.sleeping and not v.dimmed and v.main is None
    assert store.view(2401).dimmed


def test_no_sessions_means_sleeping(store):
    v = store.view(1)
    assert v.sleeping and v.main is None and not v.dimmed
    assert store.view(2401).dimmed


def test_hook_wakes_up(store):
    store.view(5000)
    store.apply(ev("UserPromptSubmit"), 5000)
    v = store.view(5000)
    assert not v.sleeping and not v.dimmed and v.main.state == "thinking"


def test_waiting_session_never_sleeps(store):
    store.apply(ev("PermissionRequest"), 0)
    v = store.view(3600)
    assert not v.sleeping and v.main.state == "waiting"


def test_session_end_removes_session(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("SessionEnd"), 2)
    assert store.view(2).main is None


def test_session_ttl_two_hours(store):
    store.apply(ev("PermissionRequest", "alt"), 0)
    store.apply(ev("UserPromptSubmit", "neu"), 7000)
    v = store.view(7201)
    assert v.main.state == "thinking" and v.others == ()


def test_others_hide_sessions_idle_for_10_min(store):
    store.apply(ev("SessionStart", "a"), 0)
    store.apply(ev("UserPromptSubmit", "b"), 601)
    assert store.view(601).others == ()


def test_invalid_events_are_ignored(store):
    for bad in ({}, {"session_id": 1, "hook_event_name": "Stop"}, {"session_id": "a"},
                {"hook_event_name": "Stop"}, ev("Erfunden")):
        store.apply(bad, 1)
    assert store.view(1).main is None or store.view(1).main.state == "idle"


def test_state_since_kept_while_state_unchanged(store):
    store.apply(ev("PreToolUse", tool_name="Edit"), 1)
    store.apply(ev("PreToolUse", tool_name="Write"), 5)
    assert store.view(5).main.since == 1
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'kraken_clawd.state'`

- [ ] **Step 3: `state.py` implementieren**

`src/kraken_clawd/state.py`:
```python
"""Zustandsmodell: Claude-Code-Hook-Events pro Session → ein Anzeige-Modell (View)."""
from __future__ import annotations

from dataclasses import dataclass, field

TOOL_STATES = {
    "Edit": "typing", "Write": "typing", "MultiEdit": "typing", "NotebookEdit": "typing",
    "Read": "reading", "Grep": "reading", "Glob": "reading", "WebFetch": "reading", "WebSearch": "reading",
    "Bash": "bash", "Agent": "conducting", "Task": "conducting",
}
WAIT_TYPES = {"permission_prompt", "elicitation_dialog", "agent_needs_input"}
WORKING = ("thinking", "typing", "reading", "bash", "conducting", "working")
PRIORITY = {"limit": 0, "waiting": 1, "error": 2, **{s: 3 for s in WORKING},
            "celebrate": 4, "done": 4, "idle": 5}

ERROR_SECONDS = 1.5
DONE_SECONDS = 2.0
CELEBRATE_SECONDS = 4.0
CELEBRATE_AFTER = 30 * 60
SLEEP_AFTER = 30 * 60
DIM_AFTER = 40 * 60
OTHERS_IDLE_HIDE = 10 * 60
SESSION_TTL = 2 * 3600


@dataclass(frozen=True)
class SessionView:
    state: str
    subagents: int
    since: float


@dataclass(frozen=True)
class View:
    main: SessionView | None
    others: tuple[SessionView, ...]
    sleeping: bool
    dimmed: bool


@dataclass
class _Session:
    state: str
    since: float
    last: float
    prev: str = "idle"
    work_start: float | None = None
    subagents: set[str] = field(default_factory=set)

    def view(self) -> SessionView:
        return SessionView(self.state, len(self.subagents), self.since)


def _map(name: str, ev: dict) -> str | None:
    match name:
        case "SessionStart":
            return "idle"
        case "UserPromptSubmit" | "PostToolUse":
            return "thinking"
        case "PreToolUse":
            return TOOL_STATES.get(ev.get("tool_name"), "working")
        case "PostToolUseFailure":
            return "error"
        case "PermissionRequest":
            return "waiting"
        case "Notification":
            t = ev.get("notification_type")
            return "waiting" if t in WAIT_TYPES else "idle" if t == "idle_prompt" else None
        case "Stop":
            return None if ev.get("stop_hook_active") else "done"
        case "StopFailure":
            return "limit" if ev.get("error") == "rate_limit" else "error"
    return None


class Store:
    def __init__(self, created: float):
        self._sessions: dict[str, _Session] = {}
        self._quiet_since = created

    def apply(self, ev: dict, now: float) -> None:
        sid, name = ev.get("session_id"), ev.get("hook_event_name")
        if not isinstance(sid, str) or not isinstance(name, str):
            return
        self._quiet_since = now
        if name == "SessionEnd":
            self._sessions.pop(sid, None)
            return
        s = self._sessions.get(sid)
        if s is None:
            s = self._sessions[sid] = _Session(state="idle", since=now, last=now)
        s.last = now
        self._settle(s, now)

        agent = ev.get("agent_id")
        if name == "SubagentStart":
            if agent:
                s.subagents.add(str(agent))
            return
        if name == "SubagentStop":
            s.subagents.discard(str(agent))
            return

        new = _map(name, ev)
        if new is None or (agent and new != "waiting"):
            return
        if s.state == "limit" and name != "UserPromptSubmit":
            return
        if name == "UserPromptSubmit" and s.work_start is None:
            s.work_start = now
        if new == "error" and s.state != "error":
            s.prev = s.state
        if new == "done":
            if s.work_start is not None and now - s.work_start > CELEBRATE_AFTER:
                new = "celebrate"
            s.work_start = None
            s.subagents.clear()
        self._set(s, new, now)

    @staticmethod
    def _set(s: _Session, state: str, now: float) -> None:
        if s.state != state:
            s.state, s.since = state, now

    def _settle(self, s: _Session, now: float) -> None:
        age = now - s.since
        if s.state == "error" and age >= ERROR_SECONDS:
            self._set(s, s.prev, now)
        elif s.state == "done" and age >= DONE_SECONDS:
            self._set(s, "idle", now)
        elif s.state == "celebrate" and age >= CELEBRATE_SECONDS:
            self._set(s, "idle", now)

    def view(self, now: float) -> View:
        for sid, s in list(self._sessions.items()):
            if now - s.last > SESSION_TTL:
                del self._sessions[sid]
            else:
                self._settle(s, now)
        sessions = list(self._sessions.values())
        sleeping = not any(s.state == "waiting" or now - s.last < SLEEP_AFTER for s in sessions)
        dimmed = sleeping and now - self._quiet_since >= DIM_AFTER
        if sleeping:
            return View(None, (), True, dimmed)
        ranked = sorted(sessions, key=lambda s: (PRIORITY[s.state], -s.last))
        others = tuple(s.view() for s in ranked[1:]
                       if not (s.state == "idle" and now - s.since > OTHERS_IDLE_HIDE))
        return View(ranked[0].view(), others, False, False)
```

- [ ] **Step 4: Tests grün**

Run: `uv run pytest tests/test_state.py -v`
Expected: alle passed. (`ev("Erfunden")` legt bewusst eine Session im Zustand `idle` an – unbekannte Events halten die Session am Leben, ändern aber nichts.)

- [ ] **Step 5: Commit**

```bash
git add src/kraken_clawd/state.py tests/test_state.py
git commit -m "feat(state): Hook-Events pro Session zu Anzeige-Modell mit Prioritäten

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: HTTP-Server für Hooks

**Files:**
- Create: `src/kraken_clawd/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `state.Store.apply(event, now)` (Task 3) – im Test durch Fake ersetzt
- Produces: `server.HookServer(store, lock: threading.Lock, host="127.0.0.1", port=7377, clock=time.time)` mit Attribut `port: int` und Methoden `start() -> None`, `stop() -> None`. Konstruktor wirft `OSError`, wenn der Port belegt ist.

- [ ] **Step 1: Failing Tests schreiben**

`tests/test_server.py`:
```python
import json
import threading
import urllib.request

import pytest

from kraken_clawd.server import HookServer


class FakeStore:
    def __init__(self):
        self.events = []

    def apply(self, ev, now):
        if ev.get("boom"):
            raise RuntimeError("kaputt")
        self.events.append((ev, now))


@pytest.fixture
def srv():
    store = FakeStore()
    s = HookServer(store, threading.Lock(), port=0, clock=lambda: 42.0)
    s.start()
    yield s, store
    s.stop()


def post(port, body: bytes, path="/hook"):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=2) as r:
        return r.status, r.read()


def test_hook_is_applied(srv):
    s, store = srv
    status, body = post(s.port, json.dumps({"session_id": "a", "hook_event_name": "Stop"}).encode())
    assert (status, body) == (200, b"{}")
    assert store.events == [({"session_id": "a", "hook_event_name": "Stop"}, 42.0)]


@pytest.mark.parametrize("body", [b"kein json", b"[1,2]", b"\xff\xfe", b""])
def test_invalid_bodies_answer_200(srv, body):
    s, store = srv
    assert post(s.port, body)[0] == 200
    assert store.events == []


def test_store_exception_still_answers_200(srv):
    s, _ = srv
    assert post(s.port, b'{"boom": true}')[0] == 200
    assert post(s.port, b'{"session_id": "a", "hook_event_name": "Stop"}')[0] == 200


def test_other_paths_404(srv):
    s, _ = srv
    with pytest.raises(urllib.error.HTTPError) as e:
        post(s.port, b"{}", path="/x")
    assert e.value.code == 404


def test_binds_localhost_only(srv):
    s, _ = srv
    assert s._httpd.server_address[0] == "127.0.0.1"


def test_port_in_use_raises(srv):
    s, store = srv
    with pytest.raises(OSError):
        HookServer(store, threading.Lock(), port=s.port)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'kraken_clawd.server'`

- [ ] **Step 3: `server.py` implementieren**

`src/kraken_clawd/server.py`:
```python
"""Mini-HTTP-Server: nimmt Claude-Code-Hooks (type "http") an und reicht sie an den Store."""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

log = logging.getLogger(__name__)
MAX_BODY = 1 << 20


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_port = False   # zweiter Daemon auf demselben Port muss scheitern


class HookServer:
    def __init__(self, store, lock: threading.Lock, host: str = "127.0.0.1", port: int = 7377,
                 clock: Callable[[], float] = time.time):
        self._httpd = _Server((host, port), _handler(store, lock, clock))
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="hooks", daemon=True)

    def start(self) -> None:
        self._thread.start()
        log.info("Hooks auf http://127.0.0.1:%d/hook", self.port)

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def _handler(store, lock: threading.Lock, clock: Callable[[], float]):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/hook":
                self.send_response(404)
                self.end_headers()
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if 0 < length <= MAX_BODY:
                self._apply(self.rfile.read(length))
            else:
                self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def _apply(self, raw: bytes) -> None:
            try:
                ev = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                log.debug("ungültiges Hook-JSON ignoriert")
                return
            if not isinstance(ev, dict):
                return
            try:
                with lock:
                    store.apply(ev, clock())
            except Exception:
                log.exception("Hook-Verarbeitung fehlgeschlagen: %s", ev.get("hook_event_name"))

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

    return Handler
```

- [ ] **Step 4: Tests grün**

Run: `uv run pytest tests/test_server.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/kraken_clawd/server.py tests/test_server.py
git commit -m "feat(server): lokaler HTTP-Endpunkt für Claude-Code-Hooks

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Renderer, Render-Schleife, Daemon-Einstieg und demo.sh

**Files:**
- Create: `src/kraken_clawd/render.py`, `src/kraken_clawd/loop.py`, `src/kraken_clawd/__main__.py`, `demo.sh`
- Test: `tests/test_render.py`, `tests/test_loop.py`

**Interfaces:**
- Consumes: `animations.frame_at`, `figure.background` (Task 1), `lcd.Display` (Task 2), `state.Store/View/SessionView` (Task 3), `server.HookServer` (Task 4)
- Produces:
  - `render.Renderer()` mit `frame(view: View, now: float) -> Image.Image` (RGB 240×240) – in Task 7 um Overlays erweitert
  - `loop.FPS = 15`, `loop.FULL = 100`, `loop.DIM = 20`
  - `loop.run(display, store, lock, stop: threading.Event, renderer=None, clock=time.time, fps=FPS) -> None`

- [ ] **Step 1: Failing Tests schreiben**

`tests/test_render.py`:
```python
from kraken_clawd.animations import frame_at
from kraken_clawd.figure import background
from kraken_clawd.render import Renderer
from kraken_clawd.state import SessionView, View


def expected(name, t):
    f = background().copy()
    f.alpha_composite(frame_at(name, t))
    return f.convert("RGB")


def test_sleeping_view_renders_sleep_animation():
    img = Renderer().frame(View(None, (), True, False), 100.0)
    assert img.mode == "RGB" and img.size == (240, 240)
    assert img.tobytes() == expected("sleep", 100.0).tobytes()


def test_main_state_animation_runs_from_state_start():
    view = View(SessionView("idle", 0, 50.0), (), False, False)
    assert Renderer().frame(view, 51.0).tobytes() == expected("idle", 1.0).tobytes()
```

`tests/test_loop.py`:
```python
import threading

from kraken_clawd.loop import DIM, FULL, run
from kraken_clawd.state import Store


class FakeDisplay:
    def __init__(self, stop, frames):
        self.stop, self.frames = stop, frames
        self.shown, self.levels = 0, []

    def show(self, img):
        assert img.size == (240, 240)
        self.shown += 1
        if self.shown >= self.frames:
            self.stop.set()

    def brightness(self, pct):
        self.levels.append(pct)


def test_run_renders_until_stopped():
    stop = threading.Event()
    d = FakeDisplay(stop, 3)
    run(d, Store(created=0.0), threading.Lock(), stop, clock=lambda: 1.0, fps=1000)
    assert d.shown == 3 and set(d.levels) == {FULL}


def test_run_dims_when_view_dimmed():
    stop = threading.Event()
    d = FakeDisplay(stop, 1)
    run(d, Store(created=0.0), threading.Lock(), stop, clock=lambda: 5000.0, fps=1000)
    assert d.levels == [DIM]
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_render.py tests/test_loop.py -v`
Expected: FAIL mit `ModuleNotFoundError` für `kraken_clawd.render` bzw. `kraken_clawd.loop`

- [ ] **Step 3: `render.py` und `loop.py` implementieren**

`src/kraken_clawd/render.py`:
```python
"""View → fertiges 240×240-Frame."""
from __future__ import annotations

from PIL import Image

from .animations import frame_at
from .figure import background
from .state import View


class Renderer:
    def frame(self, view: View, now: float) -> Image.Image:
        canvas = background().copy()
        if view.sleeping or view.main is None:
            canvas.alpha_composite(frame_at("sleep", now))
        else:
            canvas.alpha_composite(frame_at(view.main.state, now - view.main.since))
        return canvas.convert("RGB")
```

`src/kraken_clawd/loop.py`:
```python
"""Render-Schleife: Store-View → Frame → LCD mit fester Bildrate."""
from __future__ import annotations

import threading
import time
from typing import Callable

from .render import Renderer

FPS = 15
FULL = 100
DIM = 20


def run(display, store, lock: threading.Lock, stop: threading.Event, renderer: Renderer | None = None,
        clock: Callable[[], float] = time.time, fps: float = FPS) -> None:
    renderer = renderer or Renderer()
    period = 1 / fps
    while not stop.is_set():
        tick = time.monotonic()
        now = clock()
        with lock:
            view = store.view(now)
        display.brightness(DIM if view.dimmed else FULL)
        display.show(renderer.frame(view, now))
        stop.wait(max(0.0, period - (time.monotonic() - tick)))
```

`src/kraken_clawd/__main__.py`:
```python
"""Daemon: Hook-Server + Render-Schleife auf dem Kraken-LCD."""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time

from .lcd import Display
from .loop import run
from .server import HookServer
from .state import Store

log = logging.getLogger("kraken_clawd")


def main() -> int:
    logging.basicConfig(level=os.environ.get("CLAWD_LOG", "INFO"),
                        format="%(levelname)s %(name)s: %(message)s")
    store, lock, stop = Store(created=time.time()), threading.Lock(), threading.Event()
    try:
        server = HookServer(store, lock, port=int(os.environ.get("CLAWD_PORT", "7377")))
    except OSError as e:
        log.error("Hook-Port nicht verfügbar: %s", e)
        return 1
    server.start()
    display = Display()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        run(display, store, lock, stop)
    finally:
        server.stop()
        display.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Tests grün**

Run: `uv run pytest -v`
Expected: alle passed (`sleep` existiert noch nicht → `frame_at` fällt auf `idle` zurück, beide Seiten des Render-Tests nutzen dieselbe Funktion)

- [ ] **Step 5: `demo.sh` schreiben**

`demo.sh`:
```bash
#!/usr/bin/env bash
# Spielt alle Zustände gegen den laufenden Daemon durch.
set -euo pipefail
URL="${CLAWD_URL:-http://127.0.0.1:7377/hook}"
SID="demo-$$"
hook() { curl -fsS -o /dev/null -X POST "$URL" -H 'Content-Type: application/json' -d "$1"; }
ev() { hook "{\"session_id\":\"$SID\",\"hook_event_name\":\"$1\"${2:+,$2}}"; echo "→ $1 ${2:-}"; sleep "${3:-3}"; }

ev SessionStart
ev UserPromptSubmit
ev PreToolUse '"tool_name":"Read"'
ev PreToolUse '"tool_name":"Edit"'
ev PreToolUse '"tool_name":"Bash"'
ev PreToolUse '"tool_name":"mcp__server__server_run"'
ev PostToolUseFailure '"tool_name":"Bash"' 2
ev PreToolUse '"tool_name":"Agent"' 1
for a in s1 s2 s3 s4; do ev SubagentStart "\"agent_id\":\"$a\"" 1; done
sleep 3
for a in s1 s2 s3 s4; do ev SubagentStop "\"agent_id\":\"$a\"" 0.5; done
hook "{\"session_id\":\"$SID-b\",\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Edit\"}"
hook "{\"session_id\":\"$SID-c\",\"hook_event_name\":\"UserPromptSubmit\"}"
echo "→ zwei weitere Sessions (Mini-Clawds)"
ev PermissionRequest '"tool_name":"Bash"' 4
ev PostToolUse '"tool_name":"Bash"' 1
ev Stop '"stop_hook_active":false' 3
ev UserPromptSubmit '' 1
ev StopFailure '"error":"rate_limit","error_details":"429 Too Many Requests"' 5
ev UserPromptSubmit '' 1
for s in "$SID" "$SID-b" "$SID-c"; do hook "{\"session_id\":\"$s\",\"hook_event_name\":\"SessionEnd\"}"; done
echo "→ alle Sessions beendet: Clawd schläft"
```

Run: `chmod +x demo.sh`

- [ ] **Step 6: Daemon manuell starten und Demo laufen lassen**

Run (Terminal 1): `uv run python -m kraken_clawd`
Run (Terminal 2): `./demo.sh`
Expected: Daemon loggt `Kraken verbunden (Fast-Path: True)` und `Hooks auf http://127.0.0.1:7377/hook`; `demo.sh` läuft ohne curl-Fehler durch; auf dem LCD läuft Idle (alle anderen Zustände fallen bis Task 6 auf Idle zurück). Daemon mit Ctrl+C beenden, danach `~/.config/rgb-aurora/kraken.sh`.

- [ ] **Step 7: Commit**

```bash
git add src/kraken_clawd/render.py src/kraken_clawd/loop.py src/kraken_clawd/__main__.py demo.sh tests/test_render.py tests/test_loop.py
git commit -m "feat(daemon): Render-Schleife, Daemon-Einstieg und Demo-Skript

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Alle Zustands-Animationen

**Files:**
- Modify: `src/kraken_clawd/animations.py` (Requisiten-Funktionen + Einträge in `ANIMATIONS`)
- Test: `tests/test_animations.py` (ergänzen)

**Interfaces:**
- Consumes: `figure.*` (Task 1)
- Produces: `ANIMATIONS` enthält genau die Schlüssel `idle, thinking, typing, reading, bash, conducting, working, waiting, done, celebrate, error, limit, sleep`

- [ ] **Step 1: Failing Tests ergänzen**

An `tests/test_animations.py` anhängen:
```python
import numpy as np

STATES = {"idle", "thinking", "typing", "reading", "bash", "conducting", "working",
          "waiting", "done", "celebrate", "error", "limit", "sleep"}
_yy, _xx = np.mgrid[0:240, 0:240]
OUTSIDE = np.hypot(_xx - 119.5, _yy - 119.5) > 121


def test_all_states_have_animations():
    assert set(ANIMATIONS) == STATES


def test_every_animation_moves():
    for name, anim in ANIMATIONS.items():
        frames = {layer(name, i).tobytes() for i in range(anim.frames)}
        assert len(frames) > 1, name


def test_content_stays_inside_round_lcd():
    for name, anim in ANIMATIONS.items():
        for i in range(anim.frames):
            alpha = np.asarray(layer(name, i).getchannel("A"))
            assert not (alpha[OUTSIDE] > 0).any(), f"{name}[{i}] ragt über den runden Rand"


def test_error_uses_alert_tint():
    from kraken_clawd.figure import ALERT
    colors = {c[:3] for _, c in layer("error", 0).getcolors(100_000) if c[3] == 255}
    assert ALERT in colors
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_animations.py -v`
Expected: FAIL in `test_all_states_have_animations` (nur `idle` vorhanden) und `test_error_uses_alert_tint` (KeyError)

- [ ] **Step 3: Animationen implementieren**

In `src/kraken_clawd/animations.py` den Import erweitern:
```python
import random

from PIL import Image, ImageDraw

from .figure import ALERT, CENTER, HIGHLIGHT, INK, SCALE, SHADOW, SIZE, Pose, font, paste_clawd
```

Nach `_idle` einfügen:
```python
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
```

`ANIMATIONS` ersetzen durch:
```python
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
```

- [ ] **Step 4: Tests grün**

Run: `uv run pytest -v`
Expected: alle passed. Schlägt `test_content_stays_inside_round_lcd` für eine Animation fehl, deren Requisiten-Koordinaten in Richtung Mitte verschieben (nicht den Test lockern).

- [ ] **Step 5: Preview prüfen**

Run: `uv run python -m kraken_clawd.preview && xdg-open preview/`
Expected: 13 GIFs. Jedes ansehen und notieren, ob es passt: Requisiten lesbar (Lupe, Hammer, Taktstock, Tastatur), keine abgeschnittenen Teile, `limit` liegt auf dem Rücken mit blinkender leerer Batterie, `sleep` mit aufsteigenden z. Nicht passende Animationen in `animations.py` nachbessern und Preview neu erzeugen.

- [ ] **Step 6: Live mit demo.sh**

Run: Daemon (`uv run python -m kraken_clawd`) + `./demo.sh`
Expected: Jeder Zustand aus `demo.sh` erscheint < 1 s nach der Ausgabezeile auf dem LCD. Danach Daemon beenden und `~/.config/rgb-aurora/kraken.sh`.

- [ ] **Step 7: Commit**

```bash
git add src/kraken_clawd/animations.py tests/test_animations.py
git commit -m "feat(animations): Animationen für alle Zustände (tippen, Lupe, Hammer, Limit, Schlaf …)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Mini-Clawds, Subagent-Klone, Badges und Extras

**Files:**
- Modify: `src/kraken_clawd/render.py`
- Test: `tests/test_render.py` (ergänzen)

**Interfaces:**
- Consumes: `figure.paste_clawd/Pose/font/INK/ALERT` (Task 1), `state.View/SessionView` (Task 3)
- Produces: `render.nightcap_active(now: float) -> bool`; `Renderer.frame` zeichnet Overlays. Geometrie-Konstanten `MINI_SCALE = 2`, `MAX_MINIS = 4`, `MAX_CLONES = 3`.

- [ ] **Step 1: Failing Tests ergänzen**

An `tests/test_render.py` anhängen:
```python
import time

from kraken_clawd.render import nightcap_active


def sv(state="typing", subagents=0, since=0.0):
    return SessionView(state, subagents, since)


def region(img, box):
    return img.crop(box).tobytes()


BOTTOM = (40, 185, 200, 222)
TOP = (20, 10, 220, 60)


def test_other_sessions_draw_minis_at_bottom():
    r = Renderer()
    alone = r.frame(View(sv(), (), False, False), 10.0)
    with_others = r.frame(View(sv(), (sv("waiting"), sv("idle")), False, False), 10.0)
    assert region(alone, BOTTOM) != region(with_others, BOTTOM)


def test_more_than_four_others_show_plus_n():
    r = Renderer()
    four = r.frame(View(sv(), tuple(sv() for _ in range(4)), False, False), 10.0)
    six = r.frame(View(sv(), tuple(sv() for _ in range(6)), False, False), 10.0)
    assert region(four, BOTTOM) != region(six, BOTTOM)


def test_subagents_draw_clones_on_top_arc():
    r = Renderer()
    none = r.frame(View(sv("conducting", 0), (), False, False), 10.0)
    two = r.frame(View(sv("conducting", 2), (), False, False), 10.0)
    many = r.frame(View(sv("conducting", 7), (), False, False), 10.0)
    assert region(none, TOP) != region(two, TOP)
    assert region(two, TOP) != region(many, TOP)


def test_sleeping_hides_overlays():
    r = Renderer()
    a = r.frame(View(None, (), True, False), 10.0)
    b = r.frame(View(None, (sv(),), True, False), 10.0)
    assert a.tobytes() == b.tobytes()


def local(h, m, s):
    return time.mktime((2026, 10, 16, h, m, s, 0, 0, -1))


def test_nightcap_only_first_ten_seconds_after_midnight():
    assert nightcap_active(local(0, 0, 0))
    assert nightcap_active(local(0, 0, 9))
    assert not nightcap_active(local(0, 0, 10))
    assert not nightcap_active(local(23, 59, 59))
    assert not nightcap_active(local(12, 0, 5))


def test_nightcap_is_drawn():
    r = Renderer()
    view = View(sv("idle"), (), False, False)
    assert r.frame(view, local(0, 0, 5)).tobytes() != r.frame(view, local(0, 1, 5)).tobytes()
```

Hinweis: `test_nightcap_is_drawn` vergleicht 00:00:05 mit 00:01:05 – beide Zeitpunkte liegen bei `since=0` im selben Idle-Frame (60 s Abstand, Loop 2 s), der Unterschied kommt also nur von der Mütze.

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL mit `ImportError: cannot import name 'nightcap_active'`

- [ ] **Step 3: Overlays implementieren**

`src/kraken_clawd/render.py` vollständig ersetzen:
```python
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
            d.text((122, 28), f"×{n}", font=font(22), fill=INK)
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
```

- [ ] **Step 4: Tests grün**

Run: `uv run pytest -v`
Expected: alle passed

- [ ] **Step 5: Live mit demo.sh**

Run: Daemon + `./demo.sh`
Expected: Bei den 4 Subagents erscheint erst 1–3 kreisende Klone oben, beim vierten das Badge `×4`; danach zwei Mini-Clawds unten (einer tippt, einer denkt), bei `PermissionRequest` springt die wartende Session nach vorne. Kein Overlay ragt über den runden Rand. Danach Daemon beenden und `kraken.sh`.

- [ ] **Step 6: Commit**

```bash
git add src/kraken_clawd/render.py tests/test_render.py
git commit -m "feat(render): Mini-Clawds für weitere Sessions, Subagent-Klone, Badges und Mitternachtsmütze

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Hook-Installation, systemd-Service und Eclipse-Fallback

**Files:**
- Create: `install-hooks.mjs`, `systemd/kraken-clawd.service`, `README.md`
- Modify: `~/.claude/settings.json` (über `install-hooks.mjs`), `~/.config/systemd/user/kraken-clawd.service` (Symlink)

**Interfaces:**
- Consumes: Daemon `python -m kraken_clawd` (Task 5), `~/.config/rgb-aurora/kraken.sh` (bestehend)
- Produces: `node install-hooks.mjs [--remove] [--settings <pfad>]` – idempotent, Backup `settings.json.bak-kraken-clawd`

- [ ] **Step 1: Installer schreiben**

`install-hooks.mjs`:
```js
#!/usr/bin/env node
// Trägt die kraken-clawd-HTTP-Hooks in ~/.claude/settings.json ein (idempotent) oder entfernt sie (--remove).
import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const URL = "http://127.0.0.1:7377/hook";
const EVENTS = [
  "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
  "PostToolUseFailure", "PermissionRequest", "Notification", "Stop", "StopFailure",
  "SubagentStart", "SubagentStop",
];

const args = process.argv.slice(2);
const remove = args.includes("--remove");
const i = args.indexOf("--settings");
const path = i >= 0 ? args[i + 1] : join(homedir(), ".claude", "settings.json");

const settings = existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : {};
if (existsSync(path)) copyFileSync(path, `${path}.bak-kraken-clawd`);
settings.hooks ??= {};

const ours = (group) => (group.hooks ?? []).some((h) => h.type === "http" && h.url === URL);

for (const ev of EVENTS) {
  const groups = (settings.hooks[ev] ?? []).filter((g) => !ours(g));
  if (!remove) groups.push({ hooks: [{ type: "http", url: URL, timeout: 1 }] });
  if (groups.length) settings.hooks[ev] = groups;
  else delete settings.hooks[ev];
}
if (!Object.keys(settings.hooks).length) delete settings.hooks;

writeFileSync(path, JSON.stringify(settings, null, 2) + "\n");
console.log(`${remove ? "entfernt" : "eingetragen"}: ${EVENTS.length} Events in ${path}`);
```

- [ ] **Step 2: Installer an einer Kopie testen**

Run:
```bash
cp ~/.claude/settings.json /tmp/settings-test.json
node install-hooks.mjs --settings /tmp/settings-test.json
node install-hooks.mjs --settings /tmp/settings-test.json
node -e 'const s=require("/tmp/settings-test.json");console.log(s.hooks.PreToolUse.length, s.hooks.Stop.length)'
node install-hooks.mjs --remove --settings /tmp/settings-test.json
diff <(node -e 'console.log(JSON.stringify(require("/tmp/settings-test.json").hooks))') <(node -e 'console.log(JSON.stringify(require(process.env.HOME+"/.claude/settings.json").hooks))') && echo IDENTISCH
```
Expected: zweimal `eingetragen`, dann `2 1` (bestehender PreToolUse-Hook + unserer, kein Duplikat), dann `entfernt`, dann `IDENTISCH`.

- [ ] **Step 3: systemd-Unit**

Vorher prüfen, ob `kraken.sh` noch anderweitig beim Login läuft (würde mit dem Daemon um das LCD konkurrieren):
Run: `grep -rl kraken.sh ~/.config/systemd/user ~/.config/autostart 2>/dev/null`
Expected: keine Treffer. Bei Treffern: dort nur `ExecStart`-Aufruf entfernen bzw. Autostart-Eintrag deaktivieren und das im Commit erwähnen.

`systemd/kraken-clawd.service`:
```ini
[Unit]
Description=Claude-Code-Figur auf dem Kraken-LCD
After=default.target

[Service]
ExecStart=%h/Documents/IT/kraken-clawd/.venv/bin/python -m kraken_clawd
ExecStopPost=%h/.config/rgb-aurora/kraken.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Run:
```bash
ln -sf ~/Documents/IT/kraken-clawd/systemd/kraken-clawd.service ~/.config/systemd/user/kraken-clawd.service
systemctl --user daemon-reload
systemctl --user enable --now kraken-clawd
sleep 3; systemctl --user status kraken-clawd --no-pager | head -12
```
Expected: `active (running)`, Journal zeigt `Kraken verbunden (Fast-Path: True)`; LCD zeigt schlafenden Clawd.

- [ ] **Step 4: Hooks live eintragen und End-to-End prüfen**

Run:
```bash
node install-hooks.mjs
claude -p "Lies die Datei README.md nicht, antworte nur mit OK" >/dev/null
journalctl --user -u kraken-clawd --since "-2 min" --no-pager | tail -5
```
Expected: `eingetragen: 12 Events`; während `claude -p` läuft, wacht Clawd auf (denkt) und geht danach auf done → idle. Falls nichts reagiert: `CLAWD_LOG=DEBUG` in der Unit setzen (`Environment=CLAWD_LOG=DEBUG`), Daemon neu starten und prüfen, ob POSTs ankommen.

- [ ] **Step 5: Fehlerfälle prüfen**

Run:
```bash
systemctl --user stop kraken-clawd   # LCD zeigt wieder Eclipse
claude -p "antworte nur mit OK"      # muss normal funktionieren, ohne Hook-Fehler
systemctl --user start kraken-clawd
```
Expected: Eclipse-Bild nach Stop, `claude -p` antwortet `OK` ohne Verzögerung, nach Start wieder Clawd.

- [ ] **Step 6: README**

`README.md`:
```markdown
# kraken-clawd

Die Claude-Code-Figur in Lila auf dem LCD der NZXT Kraken 2023. Reagiert über Claude-Code-Hooks auf alle lokalen Sessions.

- Spec: `docs/superpowers/specs/2026-10-15-kraken-clawd-design.md`
- Daemon: `systemctl --user {status,restart,stop} kraken-clawd` (Stop → Eclipse-Bild über `~/.config/rgb-aurora/kraken.sh`)
- Hooks: `node install-hooks.mjs` / `node install-hooks.mjs --remove` (Backup: `~/.claude/settings.json.bak-kraken-clawd`)
- Vorschau ohne LCD: `uv run python -m kraken_clawd.preview`
- Eine Animation am LCD testen: `uv run python -m kraken_clawd.try_lcd <name> <sekunden>` (Daemon vorher stoppen)
- Alle Zustände durchspielen: `./demo.sh`
- Tests: `uv run pytest`
- `liquidctl` ist auf 1.16.0 gepinnt (private Methode `_send_2023_data_fw2`); beim Update Fast-Path prüfen.
```

- [ ] **Step 7: Abschluss-Verifikation**

Run: `uv run pytest -v && git status --short`
Expected: alle Tests passed; nur `install-hooks.mjs`, `systemd/`, `README.md` als neu.

- [ ] **Step 8: Commit**

```bash
git add install-hooks.mjs systemd/kraken-clawd.service README.md
git commit -m "feat(setup): Hook-Installer, systemd-Service mit Eclipse-Fallback und README

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 9: Memory aktualisieren**

In `~/.claude/projects/-home-felix/memory/project_desktop-aurora.md` ergänzen: „Kraken-LCD zeigt seit <Datum> per Daemon `kraken-clawd` (`~/Documents/IT/kraken-clawd`, systemd --user) die Claude-Figur; Stop → Eclipse über kraken.sh. Firmware 2.x kann zwar keine GIFs, aber Einzelbild-Streaming mit ~37 fps über liquidctl-Interna.“
