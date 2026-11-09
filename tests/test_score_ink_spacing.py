"""Score digits use equal visible gaps and a stable ink edge, including dim zero."""

import itertools
import unittest
from contextlib import ExitStack
from math import isclose
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.debug import simulation_context
from sonolus.script.quad import Rect
from sonolus.script.sprite import Sprite, SpriteGroup

from sekai.lib import custom_elements as ui
from sekai.lib import layout
from sekai.lib.options import Version
from sekai.lib.skin import UINumberSpriteSet

INK = [
    (4, 0, 36, 40),
    (8, 1, 29, 39),
    (6, 0, 35, 39),
    (5, 0, 35, 40),
    (4, 1, 36, 39),
    (5, 1, 36, 40),
    (4, 0, 36, 40),
    (6, 0, 35, 39),
    (4, 0, 36, 40),
    (4, 0, 36, 40),
]


class ScoreInkSpacingTests(unittest.TestCase):
    def test_ink_gaps_do_not_depend_on_digit_or_leading_zero(self):
        for aspect in (4 / 3, 16 / 9, 21 / 9):
            for scale in (0.75, 1, 1.5):
                with self.subTest(aspect=aspect, scale=scale), ExitStack() as stack:
                    stack.enter_context(simulation_context())
                    runtime = SimpleNamespace(primary_metric_config=SimpleNamespace(scale=scale))
                    for module in (ui, layout):
                        for name, value in [
                            ("LevelConfig", SimpleNamespace(ui_version=Version.v3)),
                            ("runtime_ui", lambda runtime=runtime: runtime),
                            ("aspect_ratio", lambda aspect=aspect: aspect),
                            ("screen", lambda aspect=aspect: Rect(l=-aspect, r=aspect, b=-1, t=1)),
                        ]:
                            stack.enter_context(patch.object(module, name, value))
                    stack.enter_context(
                        patch.object(layout, "safe_area", lambda aspect=aspect: Rect(l=-aspect, r=aspect, b=-1, t=1))
                    )
                    stack.enter_context(patch.object(ui, "Options", SimpleNamespace(hide_ui=0, custom_score_bar=True)))
                    stack.enter_context(
                        patch.object(
                            ui, "ActiveSkin", SimpleNamespace(ui_number=UINumberSpriteSet(SpriteGroup(100, 12)))
                        )
                    )
                    stack.enter_context(patch.object(Sprite, "is_available", property(lambda s: True)))
                    draws = []
                    stack.enter_context(
                        patch.object(
                            Sprite, "draw", lambda sprite, quad, z=0, a=1, draws=draws: draws.append((sprite.id, +quad))
                        )
                    )
                    layout.init_ui_margin()
                    last_right = None
                    for score in (0, 1, 1111, 88888888, 12345678, 10000001):
                        draws.clear()
                        ui.draw_score_bar_number(score, 0)
                        assert len(draws) == 8
                        visible = []
                        for sprite, quad in draws:
                            digit = sprite - 100
                            if digit == 10:
                                digit = 0
                            bounds = INK[digit]
                            width = quad.br.x - quad.bl.x
                            visible.append((quad.bl.x + width * bounds[0] / 40, quad.bl.x + width * bounds[2] / 40))
                        unit = min(1, aspect / (16 / 9)) / 5 * scale
                        for left, right in itertools.pairwise(visible):
                            assert isclose(right[0] - left[1], 3 / 108 * unit, abs_tol=1e-9)
                        if last_right is not None:
                            assert isclose(visible[-1][1], last_right, abs_tol=1e-9)
                        last_right = visible[-1][1]


if __name__ == "__main__":
    unittest.main()
