"""Frame transforms preserve note elevation, attachments, and camera changes."""

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from sonolus.script.vec import Vec2

from sekai.lib import layout
from sekai.lib import stage as stage_lib
from sekai.play import note as play_note
from sekai.play.dynamic_stage import DynamicStage
from sekai.watch import note as watch_note
from sekai.watch.dynamic_stage import WatchDynamicStage


def uncached_transform(note):
    if note.stage_ref.index > 0:
        return note.stage_ref.get().props.stage_transform(note.elevation)
    if note.elevation != 0:
        return layout.compute_stage_transform(
            stage_lib.current_layout_transform(), 0, 0, 0, 0, elevation=note.elevation
        )
    return layout.identity_stage_transform()


def assert_transform_equal(actual, expected):
    # Compare the blendable components as well as their composed screen mapping.
    for name in ("sr", "px", "py", "tx", "ty"):
        assert getattr(actual, name) == getattr(expected, name)
    for name in ("a00", "a01", "a02", "a10", "a11", "a12", "elevation"):
        assert getattr(actual.projection, name) == getattr(expected.projection, name)
    for point in (Vec2(-2, 0), Vec2(0, 1), Vec2(3, -0.5)):
        assert actual.to_screen_transform().apply(point) == expected.to_screen_transform().apply(point)


class StageTransformCacheTests(unittest.TestCase):
    def test_static_note_without_elevation_never_reads_a_stage_cache(self):
        for notes in (play_note.BaseNote, watch_note.WatchBaseNote):
            read_stage = Mock(side_effect=AssertionError("static note read a stage"))
            note: Any = SimpleNamespace(stage_ref=SimpleNamespace(index=0, get=read_stage), elevation=0)
            assert not notes._basic_has_stage_transform(note)
            assert_transform_equal(notes._basic_visual_stage_transform(note), layout.identity_stage_transform())
            read_stage.assert_not_called()

    def test_stage_without_transform_does_not_compute_a_frame_cache(self):
        for stages in (DynamicStage, WatchDynamicStage):
            stage: Any = SimpleNamespace(
                props=+stage_lib.StageProps,
                visual_transform=+layout.StageTransform,
                end_time=100,
                fever_boundary=lambda: None,
            )
            module = __import__(stages.__module__, fromlist=["get_stage_props"])
            with (
                patch.object(module, "get_stage_props", return_value=+stage_lib.StageProps),
                patch.object(module, "time", return_value=1, create=True),
                patch.object(stage_lib.StageProps, "stage_transform", side_effect=AssertionError("unneeded transform")),
            ):
                stages.update_sequential(stage)

    def test_both_modes_reuse_one_stage_transform_and_keep_elevation_and_attachment_blends(self):
        with (
            patch.object(layout, "Layout", SimpleNamespace(field_h=2, approach_start=-0.2)),
            patch.object(layout, "Options", SimpleNamespace(alternative_approach_curve=False)) as options,
        ):
            for notes, stages in ((play_note.BaseNote, DynamicStage), (watch_note.WatchBaseNote, WatchDynamicStage)):
                for options.alternative_approach_curve in (False, True):
                    for tilt in (0, 0.02, 0.05, 0.4, 1, 0.4):
                        for rotation in (-0.5, 0, 0.7):
                            camera = layout.LayoutTransform(
                                t=0.5, w_scale=0.15, h_scale=-1, x_translate=0.2,
                                rotate=rotation, stage_tilt=tilt, size_zoom=1.2,
                            )
                            with patch.object(stage_lib, "current_layout_transform", return_value=camera):
                                endpoints = []
                                for index, elevation in enumerate((0, -2, 3)):
                                    props = +stage_lib.StageProps
                                    props.lane = index - 1
                                    props.rotate = rotation * index
                                    props.x_lane_translate = 0.2 + index * 0.5
                                    props.y_lane_translate = -index * 0.2
                                    props.center_weight = index * 0.5
                                    props.elevation = elevation
                                    stage: Any = SimpleNamespace(
                                        props=+stage_lib.StageProps,
                                        visual_transform=+layout.StageTransform,
                                        end_time=100,
                                        fever_boundary=lambda: None,
                                    )
                                    module = __import__(stages.__module__, fromlist=["get_stage_props"])
                                    with (
                                        patch.object(module, "get_stage_props", return_value=props),
                                        patch.object(module, "time", return_value=1, create=True),
                                        patch.object(stage_lib.StageProps, "stage_transform", autospec=True,
                                                     side_effect=stage_lib.StageProps.stage_transform) as compute,
                                    ):
                                        stages.update_sequential(stage)
                                        assert compute.call_count == 1
                                        head: Any = SimpleNamespace(
                                            stage_ref=SimpleNamespace(index=index + 1, get=lambda stage=stage: stage),
                                            elevation=0,
                                        )
                                        expected = uncached_transform(head)
                                        compute.reset_mock()
                                        # Reusing a stage across many notes must perform no additional transforms.
                                        for _ in range(20):
                                            assert_transform_equal(notes._basic_visual_stage_transform(head), expected)
                                        assert compute.call_count == 0
                                    for head.elevation in (-1, 0, 2):
                                        assert_transform_equal(notes._basic_visual_stage_transform(head), uncached_transform(head))
                                    head.elevation = 0
                                    endpoints.append(head)
                                    if index == 2:
                                        endpoints.append(SimpleNamespace(stage_ref=head.stage_ref, elevation=2))
                                zero_props = +stage_lib.StageProps
                                zero_props.lane = 3
                                zero_stage = SimpleNamespace(props=zero_props, visual_transform=+layout.StageTransform)
                                endpoints.append(SimpleNamespace(
                                    stage_ref=SimpleNamespace(index=4, get=lambda zero_stage=zero_stage: zero_stage), elevation=0
                                ))
                                for head in endpoints:
                                    for tail in endpoints:
                                        head._basic_visual_stage_transform = lambda head=head, notes=notes: notes._basic_visual_stage_transform(head)
                                        tail._basic_visual_stage_transform = lambda tail=tail, notes=notes: notes._basic_visual_stage_transform(tail)
                                        for frac in (-0.25, 0, 0.5, 1, 1.25):
                                            attached: Any = SimpleNamespace(
                                                is_attached=True,
                                                attach_head_ref=SimpleNamespace(get=lambda head=head: head),
                                                attach_tail_ref=SimpleNamespace(get=lambda tail=tail: tail),
                                                attach_eased_frac=frac,
                                            )
                                            assert_transform_equal(
                                                notes.visual_stage_transform(attached),
                                                layout.blend_stage_transform(uncached_transform(head), uncached_transform(tail), frac),
                                            )


if __name__ == "__main__":
    unittest.main()
