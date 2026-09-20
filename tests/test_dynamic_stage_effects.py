"""Regression coverage for masked effects and independent score/slide links."""

import unittest
from contextlib import ExitStack
from math import isclose
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.archetype import EntityRef
from sonolus.script.bucket import Judgment
from sonolus.script.vec import Vec2

from sekai.lib import initialization, layout
from sekai.lib import note as note_lib
from sekai.lib.ease import EaseType
from sekai.lib.stage import VisualMask, masked_note_extents_by_limits
from sekai.play import connector as play_connector
from sekai.play import initialization as play_initialization
from sekai.play import note as play_note
from sekai.watch import connector as watch_connector
from sekai.watch import initialization as watch_initialization
from sekai.watch import note as watch_note


class SlideScoreLinkTests(unittest.TestCase):
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
                for index, target, following, transform in ((1, 1, 2, raised), (2, 9, 0, raised), (3, 5, 0, flat)):
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
                for now in (1, 3, 5, 7, 2):
                    with patch.object(connectors, "time", return_value=now):
                        transform, alpha = manager.active_segment_transform_and_note_alpha(state)
                    point = transform.to_screen_transform().apply(Vec2(0, -0.5))
                    assert isclose(point.y, -0.2)
                    assert alpha == 1


class MaskedEffectTests(unittest.TestCase):
    def test_play_hit_effects_receive_the_visible_note_width(self):
        fake = SimpleNamespace(
            should_play_hit_effects=True,
            kind=note_lib.NoteKind.NORM_TAP,
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
        )
        fake.visual_extents = play_note.BaseNote.visual_extents.fget(fake)
        with (
            patch.object(play_note, "play_note_hit_effects") as effects,
            patch.object(play_note, "offset_adjusted_time", return_value=4),
        ):
            play_note.BaseNote.terminate(fake)
        assert effects.call_args.args[2:4] == (0, 1)

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
        fake = SimpleNamespace(
            stage_ref=SimpleNamespace(index=1, get=lambda: None),
            is_attached=False,
            rel_lane=0,
            size=6,
            kind=note_lib.NoteKind.NORM_TAP,
            direction=layout.FlickDirection.UP_OMNI,
            judgment=Judgment.PERFECT,
            index=1,
        )
        with (
            patch.object(watch_note, "get_stage_props", return_value=props),
            patch.object(watch_note, "resolve_judge_line_style", return_value=0),
            patch.object(watch_note, "camera_layout_transform_at_time"),
            patch.object(watch_note, "compute_stage_transform", return_value=layout.identity_stage_transform()),
            patch.object(watch_note, "schedule_note_slot_effects") as schedule,
        ):
            watch_note.WatchBaseNote.schedule_slot_effects_at(fake, 4)
        assert schedule.call_args.args[1:3] == (0, 1)

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
                transform=layout.IDENTITY_STAGE_SCREEN_TRANSFORM,
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
                transform=layout.IDENTITY_STAGE_SCREEN_TRANSFORM,
            )
            archetype.assert_not_called()

    def test_watch_schedules_particles_using_masked_extents(self):
        for attached in (False, True):
            for mask in (VisualMask(-1, 1, True, 1), VisualMask(10, 12, True, 1)):
                with self.subTest(attached=attached, mask=mask):
                    fake = SimpleNamespace(
                        is_scored=True,
                        kind=note_lib.NoteKind.NORM_TAP,
                        effect_kind=note_lib.NoteEffectKind.DEFAULT,
                        calc_time=4,
                        stage_ref=SimpleNamespace(index=0),
                        size=6,
                        is_attached=attached,
                        direction=layout.FlickDirection.UP_OMNI,
                        judgment=Judgment.PERFECT,
                        index=1,
                        visual_lane_at=lambda t: 0,
                        visual_mask_at=lambda t, mask=mask, **kwargs: mask,
                        y_offset_at=lambda t: 0,
                        _stage_lane_particles_at=lambda t: True,
                        stage_transform_at=lambda t: layout.identity_stage_transform(),
                    )
                    fake.visual_extents_at = lambda t, fake=fake: watch_note.WatchBaseNote.visual_extents_at(fake, t)
                    with (
                        patch.object(watch_note, "Options", SimpleNamespace(note_effect_enabled=True)),
                        patch.object(watch_note, "schedule_note_particles") as schedule,
                    ):
                        watch_note.WatchBaseNote.spawn_note_particles(fake)
                    expected = masked_note_extents_by_limits(0, 6, mask.left, mask.right, True)
                    assert schedule.call_args.args[2:4] == expected

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
