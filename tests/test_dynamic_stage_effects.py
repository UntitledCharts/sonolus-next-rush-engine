"""Regression coverage for masked effects and independent score/slide links."""

import unittest
from contextlib import ExitStack
from math import isclose
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from sonolus.script.archetype import EntityRef
from sonolus.script.bucket import Judgment
from sonolus.script.debug import simulation_context
from sonolus.script.particle import Particle
from sonolus.script.vec import Vec2

from sekai.lib import initialization, layout, particle_manager
from sekai.lib import note as note_lib
from sekai.lib.ease import EaseType
from sekai.lib.level_config import EngineRevision
from sekai.lib.note_style import NoteStyle
from sekai.lib.stage import VisualMask, masked_note_extents_by_limits
from sekai.play import connector as play_connector
from sekai.play import dynamic_stage as play_stage
from sekai.play import initialization as play_initialization
from sekai.play import note as play_note
from sekai.play import slot_effect as play_slot
from sekai.watch import connector as watch_connector
from sekai.watch import dynamic_stage as watch_stage
from sekai.watch import initialization as watch_initialization
from sekai.watch import note as watch_note
from sekai.watch import slot_effect as watch_slot


class SlideScoreLinkTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(layout, "LevelConfig", SimpleNamespace(revision=EngineRevision.LATEST))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_score_sort_preserves_elevated_slide_in_both_modes(self):
        camera = layout.LayoutTransform(
            t=0, w_scale=0.1, h_scale=-0.5, x_translate=0, rotate=0, stage_tilt=1, size_zoom=1
        )
        raised = layout.identity_stage_transform()
        raised.projection = layout.elevation_projection(camera, 3)
        flat = layout.identity_stage_transform()
        for init, notes, connectors, manager in (
            (play_initialization, play_note.BaseNote, play_connector, play_connector.SlideManager),
            (watch_initialization, watch_note.WatchBaseNote, watch_connector, watch_connector.WatchSlideManager),
        ):
            with self.subTest(mode=init.__name__), ExitStack() as stack:
                ref = EntityRef[notes]
                entities = {}
                # The ordinary tap occurs during a slide, on an unelevated stage.
                for index, target, following, transform in ((1, 1, 2, raised), (2, 9, 0, flat), (3, 5, 0, flat)):
                    entities[index] = SimpleNamespace(
                        index=index,
                        target_time=target,
                        calc_time=target,
                        next_ref=ref(following),
                        prev_ref=ref(1 if index == 2 else 0),
                        score_next_ref=ref(0),
                        init_data=lambda: None,
                        is_scored=True,
                        connector_ease=EaseType.LINEAR,
                        head_ease_frac=0,
                        tail_ease_frac=1,
                        visual_note_alpha=1,
                        visual_stage_transform=lambda transform=transform: +transform,
                        ref=lambda index=index, ref=ref: ref(index),
                    )
                stack.enter_context(
                    patch.object(notes, "at", side_effect=lambda i, entities=entities, **kwargs: entities[i])
                )
                stack.enter_context(patch.object(notes, "_compile_time_id", return_value=1))
                stack.enter_context(patch.object(init.Skill, "_compile_time_id", return_value=2))
                archetype = init.PlayArchetype if init is play_initialization else init.WatchArchetype
                stack.enter_context(patch.object(archetype, "_get_mro_id_array", side_effect=lambda n: [n]))
                stack.enter_context(
                    patch.object(
                        init, "entity_info_at", side_effect=lambda i: SimpleNamespace(archetype_id=1 if i else 0)
                    )
                )
                head, count, _, _ = init.initial_list(4)
                assert count == 3
                sorted_head = initialization.sort_entities_by_time(head, notes, get_next_ref=lambda n: n.score_next_ref)
                assert sorted_head.index == 1
                assert entities[1].score_next_ref.index == 3
                assert entities[3].score_next_ref.index == 2
                assert entities[2].score_next_ref.index == 0
                assert entities[1].next_ref.index == 2
                assert entities[2].prev_ref.index == 1
                state = SimpleNamespace(active_head_ref=ref(1), segment_head_ref=ref(1), segment_cursor_time=-1e8)
                if init is watch_initialization:
                    stack.enter_context(patch.object(connectors, "is_skip", return_value=False))
                # Include a rewind so the cursor reset also uses the original slide chain.
                for now in (1, 3, 5, 7, 9, 2):
                    with patch.object(connectors, "time", return_value=now):
                        transform, alpha = manager.active_segment_transform_and_note_alpha(state)
                    point = transform.to_screen_transform().apply(Vec2(0, -0.5))
                    expected_elevation = 3 * (9 - now) / 8
                    assert isclose(point.y, -0.5 + 0.1 * expected_elevation)
                    assert isclose(transform.projection.elevation, expected_elevation)
                    assert alpha == 1


class MaskedEffectTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(layout, "LevelConfig", SimpleNamespace(revision=EngineRevision.LATEST))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unrelated_particle_groups_do_not_share_a_recycling_chunk(self):
        with simulation_context():
            storage = dict.fromkeys((1, 7), +particle_manager.ParticleStorage)
            with (
                patch.object(particle_manager, "particle_storage", side_effect=storage.__getitem__),
            ):
                first = particle_manager.begin_particle_chunk(Particle(4), 1, particle_manager.ParticleManageKind.MULTI)
                second = particle_manager.begin_particle_chunk(
                    Particle(4), 7, particle_manager.ParticleManageKind.MULTI
                )
        assert first != second

    def test_play_hit_effects_receive_the_visible_note_width(self):
        fake = SimpleNamespace(
            should_play_hit_effects=True,
            kind=note_lib.NoteKind.NORM_TAP,
            style=NoteStyle.BLUE,
            effect_kind=note_lib.NoteEffectKind.DEFAULT,
            is_scored=False,
            visual_lane=0,
            size=6,
            visual_mask=VisualMask(-1, 1, True, 1),
            direction=layout.FlickDirection.UP_OMNI,
            result=SimpleNamespace(judgment=Judgment.PERFECT),
            visual_y_offset=0,
            visual_pivot_lane=0,
            visual_half_offset=False,
            index=1,
            visual_single_line=False,
            visual_lane_particles=True,
            visual_stage_transform=layout.identity_stage_transform,
            stage_params=lambda: +layout.NoteStageParams,
        )
        fake.visual_extents = play_note.BaseNote.visual_extents.fget(fake)
        with (
            patch.object(play_note, "play_note_hit_effects") as effects,
            patch.object(play_note, "offset_adjusted_time", return_value=4),
        ):
            play_note.BaseNote.terminate(fake)
        assert effects.call_args.args[2:4] == (0, 1)
        assert effects.call_args.kwargs["style"] == NoteStyle.BLUE

    def test_watch_slots_and_glow_use_masked_width(self):
        division = SimpleNamespace(start=SimpleNamespace(parity=0, size=1))
        props = SimpleNamespace(
            pivot_lane=0,
            y_offset=0,
            division=division,
            judge_line_style=None,
            rotate=0,
            x_lane_translate=0,
            y_lane_translate=0,
            lane=0,
            center_weight=0,
            elevation=3,
            width=1,
            mask_notes=True,
        )
        props.transform_params = lambda offset: layout.StageTransformParams(
            stage_rotate=props.rotate,
            x_lane_translate=props.x_lane_translate,
            y_lane_translate=props.y_lane_translate,
            mask_lane=props.lane,
            center_weight=props.center_weight,
            elevation=props.elevation + offset,
        )
        fake = SimpleNamespace(
            stage_ref=SimpleNamespace(index=1, get=lambda: None),
            is_attached=False,
            rel_lane=0,
            size=6,
            elevation=-1,
            kind=note_lib.NoteKind.NORM_TAP,
            style=NoteStyle.BLUE,
            direction=layout.FlickDirection.UP_OMNI,
            judgment=Judgment.PERFECT,
            index=1,
        )
        with (
            patch.object(watch_note, "get_stage_props", return_value=props),
            patch.object(watch_note, "resolve_judge_line_style", return_value=0),
            patch.object(layout, "Layout", SimpleNamespace(field_h=1, approach_start=0)),
            patch.object(layout, "Options", SimpleNamespace(alternative_approach_curve=False)),
            patch.object(
                watch_note,
                "camera_layout_transform_at_time",
                return_value=layout.LayoutTransform(
                    t=0, w_scale=0.1, h_scale=-0.5, x_translate=0, rotate=0, stage_tilt=1, size_zoom=1
                ),
            ),
            patch.object(watch_note, "schedule_note_slot_effects") as schedule,
        ):
            watch_note.WatchBaseNote.schedule_slot_effects_at(fake, 4)
        assert schedule.call_args.args[1:3] == (0, 1)
        stage = schedule.call_args.kwargs["stage"]
        camera = layout.LayoutTransform(
            t=0, w_scale=0.1, h_scale=-0.5, x_translate=0, rotate=0, stage_tilt=1, size_zoom=1
        )
        with (
            patch.object(layout, "Layout", SimpleNamespace(field_h=1, approach_start=0)),
            patch.object(layout, "Options", SimpleNamespace(alternative_approach_curve=False)),
        ):
            transform = stage.screen_transform(camera)
        assert isclose(transform.elevation, 2)
        assert isclose(transform.apply(Vec2(0, -0.5)).y, -0.3)

    def test_slot_and_glow_emissions_are_limited_to_visible_lanes(self):
        sprite = SimpleNamespace(is_available=True)
        sprites = SimpleNamespace(slot=sprite, slot_glow=SimpleNamespace(get_sprite=lambda judgment: sprite))
        with (
            patch.object(note_lib, "is_tutorial", return_value=False),
            patch.object(note_lib, "Options", SimpleNamespace(slot_effect_enabled=True)),
            patch.object(note_lib, "get_note_sprite_set", return_value=sprites),
            patch.object(note_lib, "get_archetype_by_name") as archetype,
        ):
            note_lib.schedule_note_slot_effects(
                note_lib.NoteKind.NORM_TAP,
                0,
                1,
                4,
                layout.FlickDirection.UP_OMNI,
                stage=+layout.NoteStageParams,
            )
            calls = archetype.return_value.spawn.call_args_list
            assert len(calls) == 2
            assert all(call.kwargs["left"] == -1 and call.kwargs["right"] == 1 for call in calls)
            archetype.reset_mock()
            note_lib.schedule_note_slot_effects(
                note_lib.NoteKind.NORM_TAP,
                0.25,
                0,
                4,
                layout.FlickDirection.UP_OMNI,
                stage=+layout.NoteStageParams,
            )
            archetype.assert_not_called()

    def test_bundled_slots_follow_camera_changes_in_both_modes(self):
        for module, cls, draw in (
            (play_slot, play_slot.SlotEffect, "draw_slot_effects_in_range"),
            (play_slot, play_slot.SlotGlowEffect, "draw_slot_glow_effects_in_range"),
            (watch_slot, watch_slot.WatchSlotEffect, "draw_slot_effects_in_range"),
            (watch_slot, watch_slot.WatchSlotGlowEffect, "draw_slot_glow_effects_in_range"),
        ):
            for elevation in (0, 2):
                with self.subTest(effect=cls.__name__, elevation=elevation):
                    stage = +layout.NoteStageParams
                    stage.head.elevation = elevation
                    fake = SimpleNamespace(
                        sprite=SimpleNamespace(id=1),
                        start_time=0,
                        end_time=1,
                        left=-1,
                        right=1,
                        shift=0,
                        bounds=None,
                        y_offset=0,
                        stage=stage,
                        projection=+layout.NoteStageProjection,
                        generation=1,
                    )
                    with (
                        patch.object(module, "time", return_value=0.1, create=True),
                        patch.object(module, "is_slot_generation_visible", return_value=True),
                        patch.object(module, draw) as render,
                        patch.object(layout, "Layout", SimpleNamespace(field_h=1, approach_start=0)),
                        patch.object(layout, "Options", SimpleNamespace(alternative_approach_curve=False)),
                    ):
                        for width in (0.1, 0.2):
                            camera = layout.LayoutTransform(
                                t=0,
                                w_scale=width,
                                h_scale=-0.5,
                                x_translate=0,
                                rotate=0,
                                stage_tilt=1,
                                size_zoom=1,
                            )
                            with patch.object(layout, "current_layout_transform", return_value=camera):
                                cls.update_parallel(fake)
                            transform = render.call_args.kwargs["transform"]
                            assert isclose(transform.apply(Vec2(0, -0.5)).y, -0.5 + elevation * width)
                            assert render.call_args.args[3:5] == (-1, 1)
                        assert render.call_count == 2
                        if elevation == 0:
                            assert fake.projection.camera.w_scale == 0

    def test_fever_boundaries_use_full_draw_properties_after_shared_props_split(self):
        from sekai.lib.stage import StageProps, StageSharedProps

        for module, cls in ((play_stage, play_stage.DynamicStage), (watch_stage, watch_stage.WatchDynamicStage)):
            with self.subTest(mode=module.__name__):
                props = +StageProps
                props.lane = 2
                props.width = 1
                props.lane_alpha = 0.8
                fake = SimpleNamespace(draw_props=props, props=+StageSharedProps)
                fever = SimpleNamespace(min_l=1e8, max_r=-1e8)
                with patch.object(module, "Fever", fever):
                    cls.fever_boundary(fake)
                assert (fever.min_l, fever.max_r) == (1, 3)
                assert fever.alpha_l == fever.alpha_r == 0.8
                assert fever.has_active

    def test_watch_hit_effects_use_current_masked_extents(self):
        for mask in (VisualMask(-1, 1, True, 1), VisualMask(10, 12, True, 1)):
            with self.subTest(mask=mask):
                fake: Any = SimpleNamespace(
                    kind=note_lib.NoteKind.NORM_TAP,
                    style=NoteStyle.BLUE,
                    effect_kind=note_lib.NoteEffectKind.DEFAULT,
                    direction=layout.FlickDirection.UP_OMNI,
                    judgment=Judgment.PERFECT,
                    index=7,
                    visual_lane_at=lambda t, right_limit: 0,
                    size=6,
                    visual_mask_at=lambda t, right_limit, mask=mask: mask,
                    visual_y_offset=0,
                    visual_pivot_lane=0,
                    visual_half_offset=False,
                    _stage_lane_particles_at=lambda t, *, right_limit: right_limit,
                    visual_stage_transform=layout.identity_stage_transform,
                )
                fake.visual_extents_at = (
                    lambda t, right_limit=False, fake=fake: watch_note.WatchBaseNote.visual_extents_at(
                        fake, t, right_limit
                    )
                )
                with (
                    patch.object(watch_note, "time", return_value=4),
                    patch.object(watch_note, "handle_note_particles") as emit,
                ):
                    fake.visual_extents = cast(Any, watch_note.WatchBaseNote.visual_extents.fget)(fake)
                    watch_note.WatchBaseNote.play_hit_effects(fake)
                expected = masked_note_extents_by_limits(0, 6, mask.left, mask.right, True)
                assert emit.call_args.args[2:4] == expected
                assert emit.call_args.kwargs["style"] == NoteStyle.BLUE
                assert emit.call_args.kwargs["group_id"] == 7
                assert emit.call_args.kwargs["lane_particles"] is True

    def test_watch_hit_emitter_runs_once_and_suppresses_skipped_effects(self):
        for skipped in (False, True):
            with self.subTest(skipped=skipped):
                note = SimpleNamespace(play_hit_effects=lambda *args: None)
                fake: Any = SimpleNamespace(
                    played=True,
                    component=0,
                    page_index=0,
                    page=SimpleNamespace(entries=[]),
                    note_ref=SimpleNamespace(get=lambda note=note: note),
                )
                watch_note.WatchHitEffect.initialize(fake)
                with (
                    patch.object(watch_note, "is_skip", return_value=skipped),
                    patch.object(note, "play_hit_effects") as effects,
                ):
                    watch_note.WatchHitEffect.update_sequential(fake)
                    watch_note.WatchHitEffect.update_sequential(fake)
                assert effects.call_count == int(not skipped)

    def test_fully_masked_notes_emit_no_particles(self):
        for lane in (0, 0.25, -1.75):
            with self.subTest(lane=lane), patch.object(note_lib, "get_note_particles") as particles:
                note_lib.handle_note_particles(
                    note_lib.NoteKind.NORM_TAP,
                    note_lib.NoteEffectKind.DEFAULT,
                    lane,
                    0,
                    layout.FlickDirection.UP_OMNI,
                    Judgment.PERFECT,
                )
                particles.assert_not_called()

    def test_lane_emitter_does_not_round_empty_fractional_mask_up_to_a_lane(self):
        with patch.object(note_lib, "emit_particle") as emit:
            note_lib._emit_lane_particles(
                None,
                0.25,
                0,
                0,
                1,
                0,
                False,
                layout.IDENTITY_STAGE_SCREEN_TRANSFORM,
                extend_down=True,
                compensate_overshoot=True,
            )
            emit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
