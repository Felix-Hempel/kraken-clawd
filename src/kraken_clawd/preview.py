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
