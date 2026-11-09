"""Cached custom UI keeps digit ordering, animation geometry, and replay snapshots."""

import unittest
from contextlib import ExitStack
from math import isclose
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from sonolus.script.array import Array, Dim
from sonolus.script.bucket import Judgment
from sonolus.script.debug import simulation_context
from sonolus.script.quad import Quad
from sonolus.script.sprite import Sprite, SpriteGroup

from sekai.lib import custom_elements as ui
from sekai.lib import layout
from sekai.lib.buckets import TAP_NORMAL_WINDOW
from sekai.lib.skin import AccuracySpriteSet, ComboNumberSpriteSet, JudgmentUiSpriteSet
from sekai.watch import note as watch_note


class CustomUiCacheTests(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        stack.enter_context(simulation_context())
        self.options = SimpleNamespace(
            hide_ui=0,
            custom_combo=True,
            ap_effect=True,
            auto_judgment=False,
            custom_judgment=True,
            custom_accuracy=True,
        )
        self.skin = SimpleNamespace(
            combo_number=ComboNumberSpriteSet(SpriteGroup(100, 20), SpriteGroup(200, 20), SpriteGroup(300, 20), False),
            judgment=JudgmentUiSpriteSet(*(Sprite(i) for i in range(800, 806))),
            accuracy_warning=AccuracySpriteSet(Sprite(900), Sprite(901), Sprite(902)),
        )
        self.visibility = SimpleNamespace(
            combo_config=SimpleNamespace(scale=1, alpha=0.8),
            judgment_config=SimpleNamespace(scale=1, alpha=0.7),
        )
        self.now = 0.3
        stack.enter_context(patch.object(layout, "aspect_ratio", return_value=16 / 9))
        self.draws = []
        for name, value in (
            ("Options", self.options),
            ("ActiveSkin", self.skin),
            ("runtime_ui", lambda: self.visibility),
            ("time", lambda: self.now),
            ("is_watch", lambda: False),
            ("layout_dead_effect_quads", lambda: +Array[Quad, Dim[4]]),
        ):
            stack.enter_context(patch.object(ui, name, value))
        stack.enter_context(
            patch.object(
                layout,
                "Layout",
                SimpleNamespace(
                    w_scale=0.13,
                    h_scale=-0.7,
                    t=0.25,
                    fixed_w_scale=0.11,
                    fixed_h_scale=-0.5,
                ),
            )
        )
        stack.enter_context(patch.object(Sprite, "is_available", property(lambda sprite: True)))
        stack.enter_context(
            patch.object(Sprite, "draw", lambda sprite, quad, z=0, a=1: self.record_draw(sprite, quad, z, a))
        )
        ui.init_fixed_ui_layout()

    def record_draw(self, sprite, quad, z=0, a=1):
        self.draws.append((sprite.id, +quad, z, a))

    def test_digit_order_and_cache_replacement(self):
        cache = +ui.ComboNumberCache
        for combo in (9, 10, 999, 1000, 901, 0, 9007199254740991, 1):
            with self.subTest(combo=combo):
                cache.set_combo(combo)
                self.draws.clear()
                ui.draw_combo_number(0, True, cache)
                expected = [] if combo == 0 else [100 + int(digit) for digit in str(combo)]
                assert [draw[0] for draw in self.draws[1::2]] == expected

    def test_combo_geometry_preserves_fallback_and_pop_animation(self):
        for fallback in (False, True):
            self.skin.combo_number.is_fallback = fallback
            ui.init_fixed_ui_layout()
            cache = +ui.ComboNumberCache
            cache.set_combo(123)
            for self.now in (0, 0.056, 0.112, 0.152, 0.192, 0.3):
                with self.subTest(fallback=fallback, time=self.now):
                    self.draws.clear()
                    with patch.object(
                        ui, "transform_fixed_size", side_effect=AssertionError("recomputed"), create=True
                    ):
                        ui.draw_combo_number(0, True, cache)
                    first, last = self.draws[1][1], self.draws[-1][1]
                    scale = 0.6 + 0.4 * min(1, self.now / 0.112)
                    if fallback:
                        width = (150 / 108) * 0.2 * 0.67
                        gap = 0.95 * 0.2 - width
                        assert isclose(last.tr.x - first.tl.x, scale * (3 * width + 2 * gap))
                        assert isclose((first.tl.x + last.tr.x) / 2, 6.217 * 0.2)
                    else:
                        # Compare visible ink, not padded 150x150 rectangles.
                        # These landmarks are from OpenSekai's trimmed glyphs 1/3.
                        ink_left = first.tl.x + (first.tr.x - first.tl.x) * (50 / 150)
                        ink_right = last.tl.x + (last.tr.x - last.tl.x) * (111 / 150)
                        source_left = (5 - 0.5899191 * 77.84776) / 108
                        source_right = (107 - 0.51788145 * 111.84775) / 108
                        assert isclose(ink_left, (6.217 + scale * (-0.95 + source_left)) / 5, abs_tol=2e-8)
                        assert isclose(ink_right, (6.217 + scale * (0.95 + source_right)) / 5, abs_tol=2e-8)
                        assert isclose((first.tl.y - first.bl.y) * (97 / 150), scale * (132 / 108) / 5, abs_tol=2e-8)

    def test_judgment_uses_judgment_scale_and_ignores_stage_projection(self):
        self.options.custom_accuracy = True
        self.now = 0.2
        for combo_scale, judgment_scale in ((0.5, 1), (2, 1), (1, 1.5)):
            self.visibility.combo_config.scale = combo_scale
            self.visibility.judgment_config.scale = judgment_scale
            ui.init_fixed_ui_layout()
            self.draws.clear()
            ui.draw_judgment_text(0, Sprite(800))
            quad = self.draws[-1][1]
            assert isclose((quad.bl.y + quad.tl.y) / 2, -1.17 / 5)
            assert isclose(quad.tr.x - quad.tl.x, (310 / 108) * judgment_scale / 5)
            assert isclose(quad.tl.y - quad.bl.y, (80 / 108) * judgment_scale / 5)

    def test_ap_sprites_and_ui_visibility_remain_dynamic(self):
        cache = +ui.ComboNumberCache
        cache.set_combo(12)
        ui.draw_combo_number(0, False, cache)
        assert [draw[0] for draw in self.draws] == [301, 201, 201, 302, 202, 202]
        self.draws.clear()
        self.options.hide_ui = 2
        ui.draw_combo_number(0, False, cache)
        assert not self.draws
        self.options.hide_ui = 0
        self.visibility.combo_config.alpha = 0.4
        ui.draw_combo_number(0, True, cache)
        assert isclose(self.draws[-1][3], 0.4)

    def test_watch_reinitialization_refreshes_combo_and_judgment(self):
        from sekai.watch import custom_elements as watch_ui

        recorded = SimpleNamespace(
            calc_time=2,
            ap=False,
            combo=99,
            judgment=Judgment.PERFECT,
            judgment_window=TAP_NORMAL_WINDOW,
            accuracy=0,
        )
        fake: Any = SimpleNamespace(note_index=1, combo_cache=+ui.ComboNumberCache)
        with (
            patch.object(watch_note.WatchBaseNote, "at", return_value=recorded),
            patch.object(watch_ui, "ActiveSkin", self.skin),
        ):
            watch_ui.ComboJudge.initialize(fake)
            assert fake.combo == 99
            assert len(fake.combo_cache.digits) == 2
            assert fake.judgment_sprite == self.skin.judgment.perfect
            recorded.combo = 100
            recorded.ap = True
            recorded.judgment = Judgment.GOOD
            recorded.calc_time = 3
            watch_ui.ComboJudge.initialize(fake)
            assert fake.combo == 100
            assert fake.ap
            assert fake.draw_time == 3
            assert len(fake.combo_cache.digits) == 3
            assert fake.judgment_sprite == self.skin.judgment.good

    def test_play_spawn_caches_bad_and_wrong_way_sprites(self):
        from sekai.play import custom_elements as play_ui

        self.options.custom_damage = True
        with (
            patch.object(play_ui, "Options", self.options),
            patch.object(play_ui, "ActiveSkin", self.skin),
            patch.object(play_ui.ComboJudge, "spawn") as combo,
            patch.object(play_ui.JudgmentAccuracy, "spawn") as accuracy,
            patch.object(play_ui.DamageFlash, "spawn"),
        ):
            play_ui.spawn_custom(Judgment.MISS, 7 / 60, TAP_NORMAL_WINDOW, True, 2, 1, True)
        assert combo.call_args.kwargs["judgment_sprite"] == self.skin.judgment.bad
        assert accuracy.call_args.kwargs["accuracy_sprite"] == self.skin.accuracy_warning.flick

    def test_watch_accuracy_cache_refreshes_after_rewind(self):
        from sekai.watch import custom_elements as watch_ui

        recorded = SimpleNamespace(
            judgment=Judgment.GREAT,
            judgment_window=TAP_NORMAL_WINDOW,
            accuracy=-0.06,
            wrong_way_check=False,
        )
        fake: Any = SimpleNamespace(note_index=1)
        with (
            patch.object(watch_note.WatchBaseNote, "at", return_value=recorded),
            patch.object(watch_ui, "ActiveSkin", self.skin),
        ):
            watch_ui.JudgmentAccuracy.initialize(fake)
            assert fake.accuracy_sprite == self.skin.accuracy_warning.fast
            recorded.accuracy = 0.06
            watch_ui.JudgmentAccuracy.initialize(fake)
            assert fake.accuracy_sprite == self.skin.accuracy_warning.late


if __name__ == "__main__":
    unittest.main()
