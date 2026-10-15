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
