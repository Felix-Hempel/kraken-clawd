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
