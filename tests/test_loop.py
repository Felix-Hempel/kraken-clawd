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
