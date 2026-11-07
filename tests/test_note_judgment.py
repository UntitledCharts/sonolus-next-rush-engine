"""Sekai timing, registered flick inputs, and note selection regressions."""

import unittest
from math import radians
from types import SimpleNamespace
from unittest.mock import patch

import test_tick_judgment as tick_fixture
from sonolus.script.bucket import Judgment
from sonolus.script.interval import Interval
from sonolus.script.quad import Rect
from sonolus.script.vec import Vec2
from test_input_index import make_notes

from sekai.lib import layout
from sekai.lib.layout import FlickDirection
from sekai.lib.note import NoteKind, get_leniency, hitbox_height_limit
from sekai.play import note as play

TickHarness = tick_fixture.TickHarness


class NoteJudgmentTests(unittest.TestCase):
    setUp = tick_fixture.TickJudgmentTests.setUp

    def make_note(self, kind):
        note = TickHarness(kind=kind, connected=False)
        note.captured_touch_id = 1
        note.direction = FlickDirection.UP_OMNI
        note.visual_stage_rotate = 0
        return note

    def touch(self, now, *, touch_id=1, started=False, ended=False, speed=0, angle=0, x=0):
        return SimpleNamespace(
            id=touch_id,
            started=started,
            ended=ended,
            speed=speed,
            angle=radians(angle),
            time=now,
            start_time=now if started else 0.95,
            position=Vec2(x, 0),
            prev_position=Vec2(x, 0),
        )

    def step(self, note, now, touches=()):
        self.clock.return_value = now
        self.adjusted.return_value = now
        play.input_manager.InputState.frame += 1
        self.touches.return_value = touches
        with (
            patch.object(play, "Layout", SimpleNamespace(flick_speed_threshold=1)),
            patch.object(play, "DynamicLayout", SimpleNamespace(rotate=0)),
        ):
            note.update_sequential()
            if touches:
                note.touch()
            note.update_parallel()
        return note.result.judgment

    def test_tail_trace_flick_has_end_input_window_and_trace_grade_window(self):
        for kind in (NoteKind.NORM_TAIL_TRACE_FLICK, NoteKind.CRIT_TAIL_TRACE_FLICK):
            note = self.make_note(kind)
            assert abs(note.input_interval.start - (1 - 7.5 / 60)) < 1e-12
            assert abs(note.input_interval.end - (1 + 8.5 / 60)) < 1e-12
            assert abs(note.judgment_window.perfect.start + 6.5 / 60) < 1e-12
            assert self.step(note, 1 - 7 / 60, [self.touch(1 - 7 / 60, speed=2)]) is None
            assert self.step(note, 1.01) == Judgment.PERFECT

    def test_unregistered_finger_cannot_finish_a_normal_flick(self):
        note = self.make_note(NoteKind.NORM_FLICK)
        assert self.step(note, 0.95, [self.touch(0.95, started=True, speed=2)]) is None
        assert self.step(note, 1, [self.touch(1, touch_id=2, speed=2)]) is None
        assert self.step(note, 1.01, [self.touch(1.01, speed=2, x=2)]) == Judgment.PERFECT

    def test_second_finger_can_register_with_a_begin_inside_the_flick(self):
        note = self.make_note(NoteKind.NORM_FLICK)
        self.step(note, 0.95, [self.touch(0.95, started=True)])
        self.step(note, 0.98, [self.touch(0.98, touch_id=2, started=True)])
        assert self.step(note, 1, [self.touch(1, touch_id=2, speed=2)]) == Judgment.PERFECT

    def test_flick_registration_is_bounded_and_motion_states_do_not_collide(self):
        note = self.make_note(NoteKind.NORM_FLICK)
        for i in range(9):
            assert note.register_flick_touch(self.touch(0.95, touch_id=100 + i)) == (i if i < 8 else -1)
        with patch.object(play, "Layout", SimpleNamespace(flick_speed_threshold=1)):
            for i in range(8):
                note.record_flick_motion(self.touch(1, touch_id=100 + i, speed=2), i)
        assert len(note.flick_touch_ids) == 8
        assert note.flick_touch_states == sum(2 * 4**i for i in range(8))

    def test_diagonal_flicks_use_a_forty_five_degree_center(self):
        for angle, expected in ((-50, Judgment.GREAT), (130, Judgment.PERFECT)):
            note = self.make_note(NoteKind.NORM_FLICK)
            note.direction = FlickDirection.UP_RIGHT
            self.step(note, 0.95, [self.touch(0.95, started=True)])
            assert self.step(note, 1, [self.touch(1, speed=2, angle=angle)]) == expected

    def test_tail_flick_held_without_new_motion_times_out_as_miss(self):
        note = self.make_note(NoteKind.NORM_TAIL_FLICK)
        self.step(note, 0.95, [self.touch(0.95, speed=2)])
        for now in (0.99, 1.01, 1.13):
            assert self.step(note, now, [self.touch(now)]) is None
        assert self.step(note, 1.15, [self.touch(1.15)]) is None
        assert self.step(note, 1.17) == Judgment.MISS

    def test_tail_flick_release_waits_one_absent_frame_and_uses_resolution_time(self):
        note = self.make_note(NoteKind.NORM_TAIL_FLICK)
        self.step(note, 0.95, [self.touch(0.95, speed=2)])
        assert self.step(note, 1) is None
        assert self.step(note, 1.03) == Judgment.PERFECT
        assert abs(note.result.accuracy - 0.03) < 1e-12

    def test_trace_flick_uses_each_fingers_latest_motion(self):
        note = self.make_note(NoteKind.NORM_TRACE_FLICK)
        note.direction = FlickDirection.UP_RIGHT
        self.step(note, 0.9, [self.touch(0.9, speed=2, angle=45)])
        self.step(note, 0.93, [self.touch(0.93, speed=2, angle=-90)])
        assert self.step(note, 1) == Judgment.GREAT
        note = self.make_note(NoteKind.NORM_TRACE_FLICK)
        note.direction = FlickDirection.UP_RIGHT
        self.step(note, 0.9, [self.touch(0.9, speed=2, angle=-90)])
        self.step(note, 0.94, [self.touch(0.94, touch_id=2, speed=2, angle=45)])
        assert self.step(note, 1) == Judgment.PERFECT

    def test_trace_input_excludes_outer_boundaries(self):
        for boundary in (1 - 5 / 60, 1 + 5 / 60):
            note = self.make_note(NoteKind.NORM_TRACE)
            assert self.step(note, boundary, [self.touch(boundary)]) is None
            assert note.best_touch_time == play.DEFAULT_BEST_TOUCH_TIME

    def test_miss_waits_for_last_state_instead_of_the_local_input_deadline(self):
        note = self.make_note(NoteKind.NORM_TAP)
        assert self.step(note, 1.13) is None
        assert not note.late_miss_pending
        assert self.step(note, 1.15) is None
        assert note.late_miss_pending
        assert self.step(note, 1.17) == Judgment.MISS
        head = self.make_note(NoteKind.NORM_HEAD_TAP)
        assert self.step(head, 1.13) is None
        assert head.late_miss_pending
        assert self.step(head, 1.15) == Judgment.MISS

    def test_later_perfect_tap_wins_over_an_earlier_good(self):
        specs = [
            {
                "beat": i,
                "target_time": t,
                "trace": False,
                "captured": 0,
                "x": 0,
                "width": 1,
                "kind": NoteKind.NORM_TAP,
                "interval": (t - 0.125, t + 0.125),
            }
            for i, t in enumerate((1, 1.1))
        ]
        active, _ = make_notes(specs)
        chosen, _ = play.input_manager.select_tap_candidate(active, self.touch(1.1, started=True))
        assert active[chosen].get().target_time == 1.1

    def test_mixed_same_time_grades_keep_sekai_pruning_order(self):
        specs = [
            {
                "beat": i,
                "target_time": t,
                "trace": False,
                "captured": 0,
                "x": x,
                "width": 1,
                "kind": kind,
                "interval": (t - 0.125, t + 0.125),
            }
            for i, (t, x, kind) in enumerate(
                ((1, 0, NoteKind.NORM_TAP), (1, 0.2, NoteKind.CRIT_TAP), (1.1, 0.2, NoteKind.NORM_TAP))
            )
        ]
        active, _ = make_notes(specs)
        touch = self.touch(1.08, started=True, x=0.2)
        chosen, _ = play.input_manager.select_tap_candidate(active, touch)
        assert active[chosen].get().target_time == 1
        assert active[chosen].get().kind == NoteKind.CRIT_TAP

    def test_hitbox_uses_sekai_top_and_screen_bottom(self):
        transform = layout.LayoutTransform(
            t=0, w_scale=0.1, h_scale=-0.5, x_translate=0, rotate=0, stage_tilt=1, size_zoom=1
        )
        with (
            patch.object(layout, "Layout", SimpleNamespace(w_scale=0.1, t=0, h_scale=-0.5, approach_start=0)),
            patch.object(layout, "approach_curve_base", side_effect=lambda x: x),
            patch.object(layout, "screen", return_value=Rect(l=-1, r=1, b=-1, t=1)),
        ):
            hitbox = layout.compute_hitbox(
                transform,
                lane=0,
                size=0.5,
                leniency=1,
                stage_transform=layout.IDENTITY_STAGE_SCREEN_TRANSFORM,
            )
        assert abs(hitbox.bounds.bl.x + 0.15) < 1e-12
        assert abs(hitbox.bounds.br.x - 0.15) < 1e-12
        assert abs(hitbox.bounds.tl.y - (-0.5 + 0.1 * 3.5 / 1.19)) < 1e-12
        assert hitbox.bounds.bl.y == -1

    def test_sekai_hitbox_widths_edges_and_left_flick_height(self):
        transform = layout.LayoutTransform(
            t=0, w_scale=0.1, h_scale=-0.5, x_translate=0, rotate=0, stage_tilt=1, size_zoom=1
        )
        with (
            patch.object(layout, "Layout", SimpleNamespace(w_scale=0.1, t=0, h_scale=-0.5, approach_start=0)),
            patch.object(layout, "approach_curve_base", side_effect=lambda x: x),
            patch.object(layout, "screen", return_value=Rect(l=-1, r=1, b=-1, t=1)),
        ):

            def bounds(kind, lane=0, direction=FlickDirection.UP_OMNI):
                return layout.compute_hitbox(
                    transform,
                    lane,
                    0.5,
                    get_leniency(kind),
                    stage_transform=layout.IDENTITY_STAGE_SCREEN_TRANSFORM,
                    height_limit=hitbox_height_limit(kind, direction),
                ).bounds

            for kind in (NoteKind.NORM_TAP, NoteKind.CRIT_TAP, NoteKind.NORM_TRACE, NoteKind.NORM_TAIL_RELEASE):
                result = bounds(kind)
                assert abs(result.bl.x + 0.125) < 1e-12
                assert abs(result.br.x - 0.125) < 1e-12
            for kind in (NoteKind.NORM_FLICK, NoteKind.NORM_HEAD_TAP, NoteKind.NORM_TICK):
                assert abs(bounds(kind).bl.x + 0.15) < 1e-12
            outer = 0.1 * (5.5 + 1.8 / 1.19)
            assert abs(bounds(NoteKind.NORM_TAP, lane=-4.5).bl.x + outer) < 1e-12
            assert abs(bounds(NoteKind.NORM_TAP, lane=4.5).br.x - outer) < 1e-12
            assert bounds(NoteKind.NORM_FLICK, direction=FlickDirection.UP_LEFT).contains_point(Vec2(0, 0.9))
            assert not bounds(NoteKind.NORM_FLICK, direction=FlickDirection.UP_RIGHT).contains_point(Vec2(0, 0.9))
            assert abs(bounds(NoteKind.NORM_TAP, lane=7).bl.x - 0.575) < 1e-12

    def test_dynamic_stage_uses_its_own_lane_range_with_the_same_hitbox_path(self):
        transform = layout.LayoutTransform(
            t=0, w_scale=0.1, h_scale=-0.5, x_translate=0, rotate=0, stage_tilt=1, size_zoom=1
        )
        stage = layout.StageScreenTransform(a00=2, a01=0, a02=0.2, a10=0, a11=0.5, a12=0.1, elevation=1)
        with (
            patch.object(layout, "Layout", SimpleNamespace(w_scale=0.1, t=0, h_scale=-0.5, approach_start=0)),
            patch.object(layout, "approach_curve_base", side_effect=lambda x: x),
            patch.object(layout, "screen", return_value=Rect(l=-1, r=1, b=-1, t=1)),
        ):
            for direction in (FlickDirection.UP_LEFT, FlickDirection.UP_RIGHT):
                result = layout.compute_hitbox(
                    transform,
                    lane=2,
                    size=0.5,
                    leniency=0.75,
                    stage_transform=stage,
                    stage_bounds=Interval(1, 5),
                    height_limit=hitbox_height_limit(NoteKind.NORM_FLICK, direction),
                )
                assert abs(result.bounds.bl.x - (0.5 - 0.1 * 1.8 / 1.19)) < 1e-12
                assert result.bounds.contains_point(Vec2(0.6, 0.9)) == (direction == FlickDirection.UP_LEFT)


if __name__ == "__main__":
    unittest.main()
