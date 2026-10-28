"""Gauge fills retain their texture projection and cover exactly the empty area."""

import unittest
from contextlib import ExitStack
from math import isclose
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.debug import simulation_context
from sonolus.script.quad import Rect
from sonolus.script.sprite import Sprite, SpriteGroup

from sekai.lib import layout, stage
from sekai.lib.options import Version
from sekai.lib.skin import (
    BaseSkin,
    LifeBarSpriteSet,
    LifeGaugeSpriteSet,
    LifeSpriteSet,
    ScoreGaugeSpriteSet,
    ScoreRankSpriteSet,
    ScoreSpriteSet,
    UINumberSpriteSet,
)


def side_at(draw, side, t):
    quad, cp_left, cp_right = draw[1:4]
    cp = cp_left if side == "left" else cp_right
    a = quad.tl if side == "left" else quad.tr
    b = quad.bl if side == "left" else quad.br
    u, v = (cp.x + 1) / 2, (cp.y + 1) / 2
    lower = quad.bl.x + (quad.br.x - quad.bl.x) * u
    upper = quad.tl.x + (quad.tr.x - quad.tl.x) * u
    x = lower + (upper - lower) * v
    return (1 - t) ** 2 * a.x + 2 * (1 - t) * t * x + t**2 * b.x


class CurvedGaugeTests(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        stack.enter_context(simulation_context())
        self.aspect = 16 / 9
        self.scale = 1
        self.version = SimpleNamespace(ui_version=Version.v3)
        self.now = 1
        self.multiplayer = False
        self.play = True
        self.draws = []
        self.curved = []
        self.skin = SimpleNamespace(
            ui_number=UINumberSpriteSet(SpriteGroup(100, 18)),
            life=LifeSpriteSet(
                LifeBarSpriteSet(*(Sprite(i) for i in range(1, 6)), Sprite(8), Sprite(9)),
                LifeGaugeSpriteSet(Sprite(6), Sprite(7)),
                UINumberSpriteSet(SpriteGroup(100, 18)),
            ),
            score=ScoreSpriteSet(
                Sprite(20),
                Sprite(21),
                ScoreGaugeSpriteSet(Sprite(22), Sprite(23), Sprite(24)),
                ScoreRankSpriteSet(*(Sprite(i) for i in range(30, 35))),
                ScoreRankSpriteSet(*(Sprite(i) for i in range(40, 45))),
            ),
        )
        self.options = SimpleNamespace(hide_ui=0, custom_life_bar=True, custom_score_bar=True)
        stack.enter_context(patch.object(stage, "ActiveSkin", self.skin))
        stack.enter_context(patch.object(stage, "Options", self.options))
        stack.enter_context(patch.object(stage, "is_multiplayer", lambda: self.multiplayer))
        stack.enter_context(patch.object(stage, "is_play", lambda: self.play))
        stack.enter_context(patch.object(stage, "time", lambda: self.now))
        for name in ("draw_life_number", "draw_score_bar_number", "draw_score_bar_raw_number"):
            stack.enter_context(patch.object(stage, name))
        for mod in (stage, layout):
            stack.enter_context(patch.object(mod, "LevelConfig", self.version))
        stack.enter_context(patch.object(layout, "aspect_ratio", lambda: self.aspect))
        stack.enter_context(patch.object(layout, "screen", lambda: Rect(l=-self.aspect, r=self.aspect, b=-1, t=1)))
        stack.enter_context(patch.object(layout, "safe_area", lambda: Rect(l=-self.aspect, r=self.aspect, b=-1, t=1)))
        stack.enter_context(
            patch.object(
                layout,
                "runtime_ui",
                lambda: SimpleNamespace(
                    primary_metric_config=SimpleNamespace(scale=self.scale),
                    secondary_metric_config=SimpleNamespace(scale=self.scale),
                ),
            )
        )
        stack.enter_context(patch.object(Sprite, "is_available", property(lambda _: True)))
        stack.enter_context(patch.object(Sprite, "draw", lambda s, q, z=0, a=1: self.draws.append((s.id, +q, z, a))))
        stack.enter_context(
            patch.object(
                Sprite,
                "draw_curved_lr",
                lambda s, q, cp1, cp2, n, z=0, a=1: self.curved.append(
                    (s.id, q.as_quad() if isinstance(q, Rect) else +q, +cp1, +cp2, n, z, a)
                ),
            )
        )

    def ui(self):
        layout.init_ui_margin()
        return SimpleNamespace(
            life_bar=layout.layout_life_bar(),
            score_bar=layout.layout_score_bar(),
            score_gauge=layout.layout_score_gauge(),
            score_rank=Rect(l=0, r=1, b=0, t=1).as_quad(),
            score_rank_text=Rect(l=0, r=1, b=0, t=1).as_quad(),
        )

    def draw(self, progress, bounds=None, alpha=1):
        self.curved.clear()
        bounds = bounds if bounds is not None else Rect(l=-1.5, r=-0.5, b=0.6, t=0.65).as_quad()
        stage.draw_curved_gauge(Sprite(22), Sprite(23), Sprite(24), bounds, progress, alpha)
        return bounds

    def test_zero_full_and_out_of_range_values(self):
        for value, ids in ((-10, [23]), (0, [23]), (0.5, [23, 22, 24, 24]), (1, [23, 22]), (10, [23, 22])):
            with self.subTest(value=value):
                self.draw(value)
                assert [d[0] for d in self.curved] == ids
                assert [d[5][2] for d in self.curved] == [0, 1, 2, 2][: len(ids)]

    def test_gradient_projection_is_identical_at_every_positive_value(self):
        self.draw(1)
        full = self.curved[1]
        for value in (1e-8, 0.001, 0.01, 0.025, 0.05, 0.1, 0.45, 0.6, 0.75, 0.9, 1 - 1e-8):
            self.draw(value)
            assert self.curved[1] == full

    def test_rounded_artwork_keeps_its_original_quad_without_a_second_curve(self):
        for value in (0, 0.5, 1):
            bounds = self.draw(value)
            for draw in self.curved[: 2 if value > 0 else 1]:
                assert draw[1] == bounds
                assert (draw[2].x, draw[2].y, draw[3].x, draw[3].y) == (-1, 0, 1, 0)
                assert draw[4] == 2
            if 0 < value < 1:
                assert self.curved[-1][0] == 24

    def test_empty_cover_stays_inside_the_full_gauge_and_reaches_the_exact_value(self):
        for width, height in ((1, 0.05), (0.5, 0.033), (0.001, 0.01), (5, 0.002)):
            bounds = Rect(l=-2, r=-2 + width, b=0.6, t=0.6 + height).as_quad()
            for value in (1e-8, 0.001, 0.01, 0.1, 0.45, 0.6, 0.75, 0.9, 1 - 1e-8):
                with self.subTest(width=width, height=height, value=value):
                    self.draw(value, bounds)
                    _, fill, upper, lower = self.curved
                    assert isclose(side_at(fill, "left", 0.5), bounds.bl.x, abs_tol=1e-10)
                    assert isclose(side_at(fill, "right", 0.5), bounds.br.x, abs_tol=1e-10)
                    end = bounds.bl.x + width * value
                    assert isclose(upper[1].bl.x, end, abs_tol=1e-10)
                    assert upper[1].bl == lower[1].tl
                    assert isclose(side_at(upper, "left", 1), end, abs_tol=1e-10)
                    assert isclose(side_at(lower, "left", 0), end, abs_tol=1e-10)
                    for cover in (upper, lower):
                        for i in range(65):
                            t = i / 64
                            l = side_at(cover, "left", t)
                            r = side_at(cover, "right", t)
                            assert bounds.bl.x - 1e-10 <= l <= r + 1e-10
                            assert isclose(r, bounds.br.x, abs_tol=1e-10)
                    # Control points meet the top/bottom horizontally and the tip vertically.
                    for cover, q in ((upper, 1), (lower, -1)):
                        assert cover[2].y == q
                        quad, cp = cover[1:3]
                        row_left = quad.tl.x if q == 1 else quad.bl.x
                        cp_x = row_left + (bounds.br.x - row_left) * (cp.x + 1) / 2
                        assert isclose(cp_x, end, abs_tol=1e-10)

    def test_degenerate_gauges_never_divide_by_zero(self):
        for bounds in (Rect(l=0, r=0, b=0, t=1), Rect(l=0, r=1, b=0, t=0), Rect(l=1, r=0, b=0, t=1)):
            self.draw(0.5, bounds.as_quad())
            assert not self.curved

    def test_background_is_present_for_all_life_states_and_play_modes(self):
        for version in (Version.v1, Version.v3):
            self.version.ui_version = version
            for self.aspect in (4 / 3, 8 / 5, 16 / 9, 21 / 9):
                for self.scale in (0.5, 1, 1.5):
                    for life in (-1, 0, 1, 200, 201, 999, 1000, 2000):
                        self.curved.clear()
                        stage.draw_life_bar(life, 100, self.ui(), 1)
                        assert self.curved[0][0] == (4 if life > 200 else 5)
                        assert [d[0] for d in self.curved if d[0] in (6, 7)] == (
                            [] if life <= 0 else [6 if life > 200 else 7]
                        )
        for self.multiplayer, self.play, last_time, expected in (
            (True, True, 100, 3),
            (False, True, 0, 2),
            (False, False, 0, 1),
        ):
            self.draws.clear()
            stage.draw_life_bar(500, last_time, self.ui(), 1)
            assert self.draws[0][0] == expected

    def test_score_thresholds_keep_the_same_gauge_texture(self):
        ui = self.ui()
        full = None
        for score in (0, 1, 19999, 20000, 399999, 400000, 619999, 620000, 839999, 840000, 1000000, 2000000):
            self.curved.clear()
            stage.draw_score_bar(score, 0, 1, ui, 1)
            assert self.curved[0][0] == 23
            if score > 0:
                if full is None:
                    full = self.curved[1]
                assert self.curved[1] == full
        assert [stage.get_gauge_progress(s) for s in (0, 20000, 400000, 620000, 840000, 1000000)] == [
            0,
            0.45,
            0.6,
            0.75,
            0.9,
            1,
        ]

    def test_housing_is_above_both_the_fill_and_cover(self):
        stage.draw_score_bar(400000, 0, 1, self.ui(), 1)
        assert next(d for d in self.draws if d[0] == 20)[2] > self.curved[-1][5]

    def test_intro_fade_has_no_cover_at_the_initial_zero_score_and_full_life(self):
        for alpha in (0, 0.25, 0.5, 0.75, 1):
            self.curved.clear()
            stage.draw_score_bar(0, 0, 1, self.ui(), alpha)
            assert [d[0] for d in self.curved] == [23]
            assert all(d[6] == alpha for d in self.curved)
            self.curved.clear()
            stage.draw_life_bar(1000, 100, self.ui(), alpha)
            assert [d[0] for d in self.curved] == [4, 6]
            assert all(d[6] == alpha for d in self.curved)

    def test_hidden_ui_draws_no_gauges(self):
        self.options.hide_ui = 2
        stage.draw_score_bar(1000000, 0, 1, self.ui(), 1)
        stage.draw_life_bar(1000, 100, self.ui(), 1)
        assert not self.curved

    def test_skin_contract_removes_masks_and_separate_edges(self):
        names = set(BaseSkin._sprites_)
        assert "Score Bar Background" in names
        assert not names.intersection(
            {"Score Bar Mask", "Score Bar Cover", "Life Bar Gauge Normal Edge", "Life Bar Gauge Danger Edge"}
        )


if __name__ == "__main__":
    unittest.main()
