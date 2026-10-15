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
