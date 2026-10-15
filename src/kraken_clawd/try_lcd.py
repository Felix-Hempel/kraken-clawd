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
