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
