"""Regression coverage for RUSH features integrated with upstream elevation."""

import unittest
from math import isclose
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.quad import Rect

from sekai.lib import layer, layout
from sekai.lib.options import StageCoverNoteSpeedCompensation


class ElevationCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.options = SimpleNamespace(
            stage_cover_scroll_speed_compensation=StageCoverNoteSpeedCompensation.OFF,
            alternative_approach_curve=False,
        )
        for name, value in (
            ("Options", self.options),
            ("LevelConfig", SimpleNamespace(dynamic_stages=True)),
            ("Layout", SimpleNamespace(approach_start=0)),
        ):
            patcher = patch.object(layout, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(layout, "screen", return_value=Rect(l=-1, r=1, b=-1, t=1))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.camera = layout.LayoutTransform(
            t=0, w_scale=0.1, h_scale=-0.5, x_translate=0, rotate=0, stage_tilt=1, size_zoom=1
        )

    def test_hitbox_uses_static_stage_extents_during_dynamic_camera(self):
        layout.Layout.w_scale = 0.1
        layout.Layout.t = 0.4
        layout.Layout.h_scale = -0.6
        hitbox = layout.compute_hitbox(
            self.camera, 0, 1, 0.5, stage_transform=layout.IDENTITY_STAGE_SCREEN_TRANSFORM
        )
        assert isclose(hitbox.bounds.tl.y - hitbox.target.l.y, 0.15)
        assert isclose(hitbox.target.l.y - hitbox.bounds.bl.y, 0.8)

    def test_custom_layers_follow_elevation_order(self):
        with (
            patch.object(layer.runtime, "is_preview", return_value=False),
            patch.object(layer.runtime, "time", return_value=0),
        ):
            normal = layer.get_z(layer.LAYER_NOTE_ARROW)
            critical = layer.get_z(layer.LAYER_NOTE_ARROW_CRITICAL)
            raised = layer.get_z(layer.layers.note_body, elevation=1)
            assert normal.tuple < critical.tuple
            assert critical.tuple < raised.tuple
            assert layer.get_z(layer.LAYER_COVER).tuple < layer.get_z(layer.layers.note_body).tuple


if __name__ == "__main__":
    unittest.main()
