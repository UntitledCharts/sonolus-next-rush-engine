"""Skill notifications stay on screen alongside the score and life bars."""

import unittest
from contextlib import ExitStack
from math import isclose
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.debug import simulation_context
from sonolus.script.quad import Rect
from sonolus.script.sprite import Sprite, SpriteGroup

from sekai.lib import events, layout
from sekai.lib.options import SkillMode, Version
from sekai.lib.skin import SkillIconSpriteSet, UINumberSpriteSet


class SkillUiLayoutTests(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        stack.enter_context(simulation_context())
        self.aspect = 8 / 5
        self.notch_left = 0.0
        self.notch_right = 0.0
        self.config = SimpleNamespace(ui_version=Version.v3)
        self.fixed_layout = SimpleNamespace(fixed_w_scale=0.2, fixed_h_scale=-1.5, t=0.9)
        self.draws = []
        skin = SimpleNamespace(
            skill_bar_score=Sprite(100),
            skill_bar_life=Sprite(101),
            skill_bar_judgment=Sprite(102),
            skill_icon=SkillIconSpriteSet(SpriteGroup(200, 5)),
            skill_number=UINumberSpriteSet(SpriteGroup(300, 18)),
        )
        for module in (events, layout):
            for name, value in (
                ("LevelConfig", self.config),
                ("Layout", self.fixed_layout),
                ("aspect_ratio", lambda: self.aspect),
                ("screen", lambda: Rect(l=-self.aspect, r=self.aspect, b=-1, t=1)),
            ):
                stack.enter_context(patch.object(module, name, value))
        stack.enter_context(
            patch.object(
                layout,
                "safe_area",
                lambda: Rect(l=-self.aspect + self.notch_left, r=self.aspect - self.notch_right, b=-1, t=1),
            )
        )
        stack.enter_context(patch.object(events, "Options", SimpleNamespace(hide_ui=0, skill_effect=True)))
        stack.enter_context(patch.object(events, "ActiveSkin", skin))
        stack.enter_context(
            patch.object(
                layout, "runtime_ui", return_value=SimpleNamespace(primary_metric_config=SimpleNamespace(scale=1))
            )
        )
        stack.enter_context(patch.object(Sprite, "is_available", property(lambda sprite: True)))
        stack.enter_context(
            patch.object(Sprite, "draw", lambda sprite, quad, z=0, a=1: self.draws.append((sprite.id, +quad, a)))
        )

    def configure(self, aspect, notch_left, notch_right):
        self.aspect = aspect
        self.notch_left = notch_left
        self.notch_right = notch_right
        scale = min(1, aspect / (16 / 9))
        self.fixed_layout.fixed_w_scale = 0.2 * scale
        self.fixed_layout.fixed_h_scale = -1.5 * scale
        layout.init_ui_margin()

    def draw_skill(self, draw_time, effect):
        self.draws.clear()
        events.draw_skill_bar(draw_time, 2, effect, 5, 300, 1.25, 5.5)

    def test_skill_group_stays_on_screen_during_animation(self):
        for aspect in (8 / 5, 4 / 3, 16 / 9, 21 / 9):
            for notch_left, notch_right in ((0, 0), (0.1, 0), (0, 0.1)):
                self.configure(aspect, notch_left, notch_right)
                for effect in (SkillMode.SCORE, SkillMode.HEAL, SkillMode.JUDGMENT):
                    for draw_time in (0, 0.125, 0.25, 1, 1.5, 1.625, 2, 2.75, 2.875, 3):
                        with self.subTest(
                            aspect=aspect, notch=(notch_left, notch_right), effect=effect, time=draw_time
                        ):
                            self.draw_skill(draw_time, effect)
                            assert len(self.draws) > 2
                            for _, quad, _ in self.draws:
                                for point in (quad.bl, quad.br, quad.tl, quad.tr):
                                    assert -aspect <= point.x <= aspect
                                    assert -1 <= point.y <= 1

    def test_settled_skill_bar_aligns_with_score_bar(self):
        for aspect in (8 / 5, 4 / 3, 16 / 9, 21 / 9):
            for notch_left, notch_right in ((0, 0), (0.1, 0), (0, 0.1)):
                with self.subTest(aspect=aspect, notch=(notch_left, notch_right)):
                    self.configure(aspect, notch_left, notch_right)
                    self.draw_skill(1, SkillMode.SCORE)
                    assert isclose(self.draws[0][1].tl.x, layout.layout_score_bar().tl.x)


if __name__ == "__main__":
    unittest.main()
