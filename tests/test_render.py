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
