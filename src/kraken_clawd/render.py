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
