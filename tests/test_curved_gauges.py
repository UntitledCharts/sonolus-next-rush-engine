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
                LifeBarSpriteSet(*(Sprite(i) for i in range(1, 6))),
                LifeGaugeSpriteSet(Sprite(6), Sprite(7)),
                UINumberSpriteSet(SpriteGroup(100, 18)),
            ),
            score=ScoreSpriteSet(
                Sprite(20),
                Sprite(21),
                ScoreGaugeSpriteSet(Sprite(22), Sprite(23)),
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
        stage.draw_curved_gauge(Sprite(22), Sprite(23), bounds, progress, alpha)
        return bounds

    def test_zero_full_and_out_of_range_values(self):
        for value, ids in ((-10, [23]), (0, [23]), (0.5, [23, 22]), (1, [23, 22]), (10, [23, 22])):
            with self.subTest(value=value):
                self.draw(value)
                assert [d[0] for d in self.curved] == ids
                assert [d[5][2] for d in self.curved] == [0, 1][: len(ids)]

    def test_gradient_projection_stays_fixed_while_only_the_control_point_moves(self):
        for value in (0.001, 0.01, 0.1, 0.45, 0.6, 0.75, 0.9, 1):
            bounds = self.draw(value)
            bg, fill = self.curved
            assert bg[1] == fill[1] == bounds
            assert (fill[2].x, fill[2].y, fill[3].y) == (-1, 0, 0)
            assert isclose(fill[3].x, 4 * value - 3)
            assert isclose(side_at(fill, "right", 0.5), bounds.bl.x + (bounds.br.x - bounds.bl.x) * value)
            assert bg[5] < fill[5]

    def test_background_is_always_full_and_has_no_second_curve(self):
        for value in (0, 0.5, 1):
            bounds = self.draw(value)
            background = self.curved[0]
            assert background[1] == bounds
            assert (background[2].x, background[2].y, background[3].x, background[3].y) == (-1, 0, 1, 0)
            assert background[4] == 2

    def test_foreground_curve_stays_inside_the_full_gauge(self):
        for width, height in ((1, 0.05), (0.5, 0.033), (0.001, 0.01), (5, 0.002)):
            bounds = Rect(l=-2, r=-2 + width, b=0.6, t=0.6 + height).as_quad()
            for value in (1e-8, 0.001, 0.1, 0.45, 0.6, 0.9, 1 - 1e-8):
                self.draw(value, bounds)
                fill = self.curved[1]
                for i in range(65):
                    t = i / 64
                    l, r = side_at(fill, "left", t), side_at(fill, "right", t)
                    assert bounds.bl.x - 1e-10 <= l <= r + 1e-10 <= bounds.br.x + 1e-10
                    assert isclose(r, side_at(fill, "right", 1 - t), abs_tol=1e-10)

    def test_background_and_gauge_use_separate_pixel_aligned_bounds(self):
        for version in (Version.v1, Version.v3):
            self.version.ui_version = version
            for life in (0, 200, 201, 1000):
                self.curved.clear()
                ui = self.ui()
                stage.draw_life_bar(life, 100, ui, 1)
                assert self.curved[0][1] == layout.layout_life_background(ui.life_bar, life)
                if life > 0:
                    assert self.curved[1][1] == layout.layout_life_gauge()
                assert len(self.curved) == (2 if life > 0 else 1)

    def test_pixel_window_alignment_is_independent_of_screen_aspect_and_ui_scale(self):
        def normalized(bar, region):
            w, h = bar.br.x - bar.bl.x, bar.tl.y - bar.bl.y
            return (
                (region.bl.x - bar.bl.x) / w,
                (bar.tl.y - region.tl.y) / h,
                (region.br.x - bar.bl.x) / w,
                (bar.tl.y - region.bl.y) / h,
            )

        for version, life, score in (
            (Version.v1, (118 / 600, 58 / 140, 408 / 600, 72 / 140), (126 / 800, 58 / 170, 756 / 800, 88 / 170)),
            (
                Version.v3,
                (177 / 1200, 129 / 280, 896 / 1200, 171 / 280),
                (218 / 1200, 99 / 255, 1153 / 1200, 141 / 255),
            ),
        ):
            self.version.ui_version = version
            for self.aspect in (4 / 3, 8 / 5, 16 / 9, 21 / 9):
                for self.scale in (0.5, 1, 1.5):
                    ui = self.ui()
                    for actual, expected in (
                        (normalized(ui.life_bar, layout.layout_life_gauge()), life),
                        (normalized(ui.score_bar, ui.score_gauge), score),
                    ):
                        assert all(isclose(a, b, abs_tol=1e-10) for a, b in zip(actual, expected, strict=True))

    def test_degenerate_gauges_never_divide_by_zero(self):
        for bounds in (Rect(l=0, r=0, b=0, t=1), Rect(l=0, r=1, b=0, t=0), Rect(l=1, r=0, b=0, t=1)):
            self.draw(0.5, bounds.as_quad())
            assert not self.curved

    def test_background_is_behind_positive_life_for_all_states_and_play_modes(self):
        for version in (Version.v1, Version.v3):
            self.version.ui_version = version
            for self.aspect in (4 / 3, 8 / 5, 16 / 9, 21 / 9):
                for self.scale in (0.5, 1, 1.5):
                    for life in (-1, 0, 1, 200, 201, 999, 1000, 2000):
                        self.curved.clear()
                        stage.draw_life_bar(life, 100, self.ui(), 1)
                        assert [d[0] for d in self.curved if d[0] in (4, 5)] == ([4 if life > 200 else 5])
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
                    full = self.curved[1][1]
                assert self.curved[1][1] == full
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

    def test_intro_fade_keeps_background_then_positive_gauge_order(self):
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

    def test_skin_contract_adds_no_masks_fill_sprites_or_separate_edges(self):
        names = set(BaseSkin._sprites_)
        assert "Score Bar Background" in names
        assert not names.intersection(
            {
                "Life Bar Normal Background Fill",
                "Life Bar Danger Background Fill",
                "Score Bar Background Fill",
            }
        )
        assert not names.intersection(
            {
                "Score Bar Mask",
                "Life Bar Normal Mask",
                "Life Bar Danger Mask",
                "Score Bar Cover",
                "Life Bar Gauge Normal Edge",
                "Life Bar Gauge Danger Edge",
            }
        )


if __name__ == "__main__":
    unittest.main()
