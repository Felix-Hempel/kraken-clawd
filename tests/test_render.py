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
