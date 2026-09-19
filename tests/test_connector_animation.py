"""Connector geometry must not change the shared slide's visual state or animation."""

import unittest
from math import isclose
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sonolus.script.quad import Rect

from sekai.lib import connector
from sekai.lib.connector import ConnectorKind, ConnectorRenderCache, ConnectorVisualState
from sekai.lib.layer import ZIndexes


class ConnectorAnimationTests(unittest.TestCase):
    def setUp(self):
        self.options = SimpleNamespace(connector_animation=True)
        self.clock = SimpleNamespace(time=3.37)
        self.layout = Rect(l=-1, r=1, b=-1, t=1).as_quad()
        for name, kwargs in (
            ("Options", {"new": self.options}),
            ("time", {"side_effect": lambda: self.clock.time}),
            ("layout_slide_connector_segment", {"return_value": self.layout}),
            ("screen", {"return_value": self.layout}),
            ("get_alpha", {"return_value": 1.0}),
            ("get_connector_alpha_option", {"return_value": 1.0}),
        ):
            patcher = patch.object(connector, name, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def render(self, path, state, animation_start_time=3.13, active_available=True):
        draws = []
        normal = SimpleNamespace(draw=Mock(side_effect=lambda *_, **kw: draws.append(("normal", kw["a"]))))
        active = SimpleNamespace(
            is_available=active_available,
            draw=Mock(side_effect=lambda *_, **kw: draws.append(("active", kw["a"]))),
        )
        common = {
            "visual_state": state,
            "normal_sprite": normal,
            "active_sprite": active,
            "z_normal": +ZIndexes,
            "z_active": +ZIndexes,
            "animation_start_time": animation_start_time,
        }
        if path == "quad":
            connector.draw_connector_quad(layout=self.layout, base_a=0.8, **common)
        elif path == "segmented":
            connector.draw_connector_default_segment(
                base_a=0.8,
                start_lane=0,
                start_size=1,
                start_travel=0.2,
                start_interp_frac=0,
                end_lane=1,
                end_size=1,
                end_travel=0.8,
                end_interp_frac=1,
                has_transform=False,
                head_transform=None,
                tail_transform=None,
                render_cache=+ConnectorRenderCache,
                **common,
            )
        else:
            connector.draw_connector_full_screen(
                kind=ConnectorKind.ACTIVE_NORMAL,
                head_target_time=3,
                head_alpha=0.8,
                tail_target_time=4,
                tail_alpha=0.8,
                **common,
            )
        return draws

    def test_all_paths_share_animation_phase(self):
        for current_time in (3.13, 3.19, 3.37, 3.54, 3.63):
            with self.subTest(time=current_time):
                self.clock.time = current_time
                expected = self.render("quad", ConnectorVisualState.ACTIVE)
                assert expected == self.render("segmented", ConnectorVisualState.ACTIVE)
                assert expected == self.render("full_screen", ConnectorVisualState.ACTIVE)
        # Moving the shared head and playback clock together preserves the phase.
        self.clock.time = 3.37
        expected = self.render("segmented", ConnectorVisualState.ACTIVE)
        self.clock.time += 2
        actual = self.render("quad", ConnectorVisualState.ACTIVE, animation_start_time=5.13)
        for (_, expected_alpha), (_, actual_alpha) in zip(expected, actual, strict=True):
            assert isclose(expected_alpha, actual_alpha)

    def test_animation_disabled_uses_normal_sprite_on_every_path(self):
        self.options.connector_animation = False
        for path in ("quad", "segmented", "full_screen"):
            with self.subTest(path=path):
                assert self.render(path, ConnectorVisualState.ACTIVE) == [("normal", 0.8)]

    def test_waiting_inactive_and_missing_active_sprite_are_consistent(self):
        for path in ("quad", "segmented", "full_screen"):
            with self.subTest(path=path):
                assert self.render(path, ConnectorVisualState.WAITING) == [("normal", 0.8)]
                assert self.render(path, ConnectorVisualState.INACTIVE) == [("normal", 0.4)]
                assert self.render(path, ConnectorVisualState.ACTIVE, active_available=False) == [("normal", 0.8)]
