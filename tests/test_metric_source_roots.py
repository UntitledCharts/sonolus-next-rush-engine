"""Compare actual glyph quads with source atlas alpha bounds and prefab roots."""

import json
import unittest
from contextlib import ExitStack
from math import isclose
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.debug import simulation_context
from sonolus.script.quad import Rect
from sonolus.script.sprite import Sprite, SpriteGroup

from sekai.lib import custom_elements as ui
from sekai.lib import layout
from sekai.lib.options import Version
from sekai.lib.skin import UINumberSpriteSet

FIXTURE = json.loads((Path(__file__).parent / "fixtures/v3_metric_glyphs.json").read_text())


class MetricSourceRootTests(unittest.TestCase):
    def test_combined_ink_matches_source_layers_at_original_digit_roots(self):
        for aspect in (4 / 3, 16 / 9, 21 / 9):
            for scale in (0.75, 1, 1.5):
                with self.subTest(aspect=aspect, scale=scale), ExitStack() as stack:
                    stack.enter_context(simulation_context())
                    runtime = SimpleNamespace(
                        primary_metric_config=SimpleNamespace(scale=scale),
                        secondary_metric_config=SimpleNamespace(scale=scale),
                    )
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
                    stack.enter_context(
                        patch.object(
                            ui, "Options", SimpleNamespace(hide_ui=0, custom_score_bar=True, custom_life_bar=True)
                        )
                    )
                    font = UINumberSpriteSet(SpriteGroup(100, 12))
                    stack.enter_context(
                        patch.object(
                            ui, "ActiveSkin", SimpleNamespace(ui_number=font, life=SimpleNamespace(number=font))
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
                    for mode, numbers in [
                        ("score", (0, 1, 1111, 88888888, 12345678, 10000001, 98765432)),
                        ("life", (0, 1, 1111, 8888, 1000, 2345, 6789)),
                    ]:
                        for number in numbers:
                            with self.subTest(mode=mode, number=number):
                                draws.clear()
                                if mode == "score":
                                    ui.draw_score_bar_number(number, 0)
                                    digits = str(number).zfill(8)
                                else:
                                    ui.draw_life_number(number, 0)
                                    digits = str(number)
                                assert len(draws) == len(digits)
                                self.check_source_bounds(draws, digits, mode, aspect, scale)

    def check_source_bounds(self, draws, digits, mode, aspect, scale):
        # Independent source camera/prefab values, not engine font coefficients.
        half_height = 5 * max(1, (16 / 9) / aspect)
        unit = scale / half_height
        anchor_y = (half_height - 0.1) / half_height
        anchor_x = anchor_y * aspect
        if mode == "score":
            root_x = -anchor_x + (3.7862 - 0.067200184 - 0.029999971) * unit
            root_y = anchor_y + (-0.42 - 0.2470001 - 0.26999998) * unit
            glyph_scale, advance = 0.94, 0.305
        else:
            root_x = anchor_x + (-0.61 - 0.666) * unit
            root_y = anchor_y + (-0.602 + 0.3584) * unit
            glyph_scale, advance = 0.63, 0.325 * 0.63
        for i, ((sprite, quad), char) in enumerate(zip(draws, digits, strict=True)):
            digit = 0 if sprite - 100 == 10 else sprite - 100
            assert digit == int(char)
            left, top, right, bottom = FIXTURE["skin_ink"][digit]
            width, height = quad.br.x - quad.bl.x, quad.tl.y - quad.bl.y
            actual = (
                quad.bl.x + width * left / 40,
                quad.tl.y - height * bottom / 40,
                quad.bl.x + width * right / 40,
                quad.tl.y - height * top / 40,
            )
            source = FIXTURE["source_union_world"][digit]
            x = root_x - (len(digits) - 1 - i) * advance * unit
            expected = (
                x + source[0] * glyph_scale * unit,
                root_y + source[1] * glyph_scale * unit,
                x + source[2] * glyph_scale * unit,
                root_y + source[3] * glyph_scale * unit,
            )
            for actual_edge, expected_edge in zip(actual, expected, strict=True):
                assert isclose(actual_edge, expected_edge, abs_tol=1e-9)


if __name__ == "__main__":
    unittest.main()
