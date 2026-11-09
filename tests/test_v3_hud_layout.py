"""FrontUIView camera anchoring and the skinned pause-button hitbox."""

import unittest
from contextlib import ExitStack
from math import isclose
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sonolus.script.debug import simulation_context
from sonolus.script.quad import Rect

from sekai.lib import hud_geometry, layout, ui
from sekai.lib.options import Version


class V3HudTests(unittest.TestCase):
    def test_menu_matches_skinned_pause_center_for_every_aspect_and_scale(self):
        for aspect in (9 / 16, 4 / 3, 8 / 5, 16 / 9, 19.5 / 9, 21 / 9, 32 / 9):
            for life_scale in (0.5, 1, 1.5):
                for menu_scale in (0.5, 1, 2):
                    with (
                        self.subTest(aspect=aspect, life_scale=life_scale, menu_scale=menu_scale),
                        ExitStack() as stack,
                    ):
                        stack.enter_context(simulation_context())
                        runtime = Mock()
                        for name in (
                            "menu",
                            "primary_metric",
                            "secondary_metric",
                            "combo",
                            "judgment",
                            "progress",
                            "navigation",
                            "instruction",
                        ):
                            setattr(runtime, name + "_config", SimpleNamespace(scale=1, alpha=1))
                        runtime.menu_config.scale = menu_scale
                        runtime.secondary_metric_config.scale = life_scale
                        screen = Rect(l=-aspect, r=aspect, b=-1, t=1)
                        for module in (layout, ui):
                            for name, value in (
                                ("LevelConfig", SimpleNamespace(ui_version=Version.v3)),
                                ("aspect_ratio", lambda aspect=aspect: aspect),
                                ("screen", lambda screen=screen: +screen),
                                ("safe_area", lambda screen=screen: +screen),
                                ("runtime_ui", lambda runtime=runtime: runtime),
                            ):
                                stack.enter_context(patch.object(module, name, value))
                        stack.enter_context(
                            patch.object(
                                ui,
                                "Options",
                                SimpleNamespace(
                                    hide_ui=0,
                                    custom_life_bar=True,
                                    custom_score_bar=True,
                                    custom_combo=False,
                                    custom_judgment=False,
                                ),
                            )
                        )
                        stack.enter_context(
                            patch.object(
                                ui,
                                "ActiveSkin",
                                SimpleNamespace(
                                    life=SimpleNamespace(available=True), score=SimpleNamespace(available=True)
                                ),
                            )
                        )
                        stack.enter_context(patch.object(ui, "Layout", SimpleNamespace(field_w=2, field_h=2)))
                        stack.enter_context(patch.object(ui, "is_preview", return_value=False))
                        stack.enter_context(patch.object(ui, "is_tutorial", return_value=False))
                        layout.init_ui_margin()
                        ui.init_ui()
                        call = runtime.menu.update.call_args.kwargs
                        bar = layout.layout_life_bar()
                        # Pixel landmark measured in Life Bar Pause, independently
                        # of the runtime menu-center constants.
                        x = bar.bl.x + (bar.br.x - bar.bl.x) * (354 / 400)
                        y = bar.tl.y - (bar.tl.y - bar.bl.y) * (51 / 93)
                        assert isclose(call["anchor"].x, x, abs_tol=1e-12)
                        assert isclose(call["anchor"].y, y, abs_tol=1e-12)
                        assert call["pivot"].x == call["pivot"].y == 0.5
                        assert call["alpha"] == 0
                        assert isclose(
                            call["dimensions"].x, (96 / 108) * hud_geometry.hud_unit(aspect) * life_scale * menu_scale
                        )
                        unit = hud_geometry.hud_unit(aspect)
                        source_top = 1 - 0.1 * unit
                        source_left = -source_top * aspect
                        gauge = layout.layout_score_gauge()
                        assert isclose(gauge.bl.x, source_left + (3.7862 - 2.4542003) * unit)
                        assert isclose(gauge.br.x - gauge.bl.x, 4.923 * unit)
                        assert isclose((gauge.bl.y + gauge.tl.y) / 2, source_top - 0.52000026 * unit)
                        empty = layout.layout_life_gauge(0)
                        full = layout.layout_life_gauge(1000)
                        cap = layout.layout_life_gauge(1000, True)
                        assert isclose(empty.bl.x, full.bl.x)
                        assert isclose(full.br.x, cap.bl.x)
                        assert isclose(cap.br.x - full.bl.x, 2.45 * unit * life_scale)
                        score = layout.layout_score_bar()
                        half_height = 5 * max(1, (16 / 9) / aspect)
                        assert isclose(score.br.x - score.bl.x, (600 / 97.2) / half_height)
                        assert isclose(score.tl.y - score.bl.y, (128 / 97.2) / half_height)


if __name__ == "__main__":
    unittest.main()
