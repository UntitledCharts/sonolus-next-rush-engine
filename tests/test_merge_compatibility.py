"""Regression coverage for RUSH features integrated with upstream elevation."""

import unittest
from math import isclose
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from sonolus.script.quad import Rect
from sonolus.script.vec import Vec2

from sekai.level_utils import LevelNote, build_level
from sekai.lib import layer, layout
from sekai.lib.ease import EaseType
from sekai.lib.note import NoteKind
from sekai.lib.options import StageCoverNoteSpeedCompensation
from sekai.play import note as play_note
from sekai.watch import note as watch_note


class ElevationCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.options = SimpleNamespace(
            stage_cover_scroll_speed_compensation=StageCoverNoteSpeedCompensation.OFF,
            alternative_approach_curve=False,
        )
        for name, value in (
            ("Options", self.options),
            ("LevelConfig", SimpleNamespace(dynamic_stages=True)),
            ("Layout", SimpleNamespace(approach_start=0, field_h=1)),
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

    def test_level_builder_preserves_per_note_elevation(self):
        level = build_level(
            name="elevation-regression",
            title="Elevation Regression",
            bgm=b"",
            entities=[LevelNote(beat=1, lane=0, size=1, kind=NoteKind.NORM_TAP, elevation=1.5)],
        )
        notes = [entity for entity in level.data.entities if isinstance(entity, play_note.BaseNote)]
        assert len(notes) == 1
        assert notes[0].elevation == 1.5

    def test_attached_note_geometry_uses_preprocessed_fraction(self):
        for module, cls in ((play_note, play_note.BaseNote), (watch_note, watch_note.WatchBaseNote)):
            with self.subTest(mode=module.__name__):
                head = SimpleNamespace(
                    _basic_stage_transform_at=lambda t, **kwargs: layout.identity_stage_transform(),
                )
                tail = SimpleNamespace(
                    _basic_stage_transform_at=lambda t, **kwargs: layout.compute_stage_transform(
                        self.camera, 0, 0, 0, 0, elevation=2
                    ),
                )
                fake: Any = SimpleNamespace(
                    is_attached=True,
                    connector_ease=EaseType.IN_QUAD,
                    attach_head_ref=SimpleNamespace(get=lambda head=head: head),
                    attach_tail_ref=SimpleNamespace(get=lambda tail=tail: tail),
                    attach_eased_frac=0.25,
                )
                with patch.object(module, "get_attach_eased_frac", side_effect=AssertionError("recomputed")):
                    for t in (0, 2, 4):
                        transform = cls.stage_transform_at(fake, t)
                        assert isclose(transform.projection.elevation, 0.5)

    def test_elevated_note_input_and_visual_geometry_agree(self):
        for module, cls in ((play_note, play_note.BaseNote), (watch_note, watch_note.WatchBaseNote)):
            with self.subTest(mode=module.__name__):
                fake: Any = SimpleNamespace(stage_ref=SimpleNamespace(index=0), lane=0, elevation=2)
                fake._basic_stage_transform_at = lambda t, cls=cls, fake=fake: cls._basic_stage_transform_at(fake, t)
                with (
                    patch.object(module, "camera_layout_transform_at_time", return_value=self.camera),
                    patch.object(module, "current_layout_transform", return_value=self.camera),
                ):
                    geometry = cls._basic_input_geometry(fake, cast(Any, SimpleNamespace(time=1)))
                    visual = cls._basic_visual_stage_transform(fake)
                for transform in (geometry.transform, visual):
                    target = transform.to_screen_transform().apply(Vec2(0, -0.5))
                    assert isclose(target.y, -0.3)
                    assert isclose(transform.projection.elevation, 2)

    def test_hitbox_uses_static_stage_extents_during_dynamic_camera(self):
        layout.Layout.w_scale = 0.1
        layout.Layout.t = 0.4
        layout.Layout.h_scale = -0.6
        hitbox = layout.compute_hitbox(self.camera, 0, 1, 0.5, stage_transform=layout.IDENTITY_STAGE_SCREEN_TRANSFORM)
        assert isclose(hitbox.bounds.tl.y - hitbox.target.l.y, 0.3)
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
