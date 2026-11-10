"""Source counterexamples for overlap, release history, and physical flick motion."""

import unittest
from contextlib import ExitStack
from math import isclose
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.debug import simulation_context
from sonolus.script.quad import Rect
from sonolus.script.vec import Vec2
from test_input_index import make_notes
from test_tick_judgment import TickHarness

from sekai.lib import layout
from sekai.lib.input_calibration import flick_distance, has_flick_motion
from sekai.lib.note import NoteKind
from sekai.play import input_manager as manager
from sekai.play import note as play


def spec(x, *, target=1, kind=NoteKind.NORM_TAP):
    return {
        "beat": target,
        "target_time": target,
        "trace": False,
        "captured": 0,
        "x": x,
        "width": 1.25,
        "kind": kind,
        "interval": (target - 0.125, target + 8.5 / 60),
    }


def touch(touch_id, x, *, time=1, ended=False):
    return SimpleNamespace(id=touch_id, started=not ended, ended=ended, time=time, start_time=time, position=Vec2(x, 0))


class InputParityTests(unittest.TestCase):
    def test_overlapping_chord_keeps_source_ownership_before_selection(self):
        # OpenSekai LiveLogic: both notes belong to finger 1 before it picks A.
        with simulation_context():
            active, registry = make_notes([spec(0), spec(1)])
            with (
                patch.object(
                    manager, "note", SimpleNamespace(NoteMemory=SimpleNamespace(active_tap_input_notes=active))
                ),
                patch.object(manager, "processed_touches", return_value=[touch(1, 0.4), touch(2, 1.8)]),
            ):
                manager.preassign_taps()
            assert registry[1].captured_touch_id == 1
            assert registry[2].captured_touch_id == 0
            # The source records eligible beginnings even if candidate pruning loses their note.
            assert manager.InputState.recent_note_input_times[2] == 1

    def test_distinct_chord_inputs_and_equal_distance_ties(self):
        with simulation_context():
            for positions, expected in [((0, 1), (1, 2)), ((0.5, 0.5), (0, 1))]:
                active, registry = make_notes([spec(0), spec(1)])
                with (
                    patch.object(
                        manager, "note", SimpleNamespace(NoteMemory=SimpleNamespace(active_tap_input_notes=active))
                    ),
                    patch.object(
                        manager, "processed_touches", return_value=[touch(i + 1, x) for i, x in enumerate(positions)]
                    ),
                ):
                    manager.preassign_taps()
                assert tuple(n.captured_touch_id for n in registry.values()) == expected

    def test_recent_tap_allows_perfect_release_even_with_another_finger_holding(self):
        with simulation_context():
            # Actual input was 0.91, not the earlier note's scheduled 0.90.
            pressed = touch(1, 0, time=0.91)
            manager.record_note_input(pressed)
            assert manager.InputState.recent_note_input_times[1] == 0.91
            for ongoing in (False, True):
                active, registry = make_notes([spec(0, kind=NoteKind.NORM_TAIL_RELEASE)])
                head = SimpleNamespace(active_connector_info=SimpleNamespace(input_bounds=Rect(-1, 1, 1, -1).as_quad()))
                registry[1].active_head_ref = SimpleNamespace(index=1, get=lambda head=head: head)
                inputs = [touch(1, 0, ended=True)]
                if ongoing:
                    held = touch(2, 0)
                    held.started = False
                    inputs.append(held)
                with (
                    patch.object(
                        manager, "note", SimpleNamespace(NoteMemory=SimpleNamespace(active_release_input_notes=active))
                    ),
                    patch.object(manager, "processed_touches", return_value=inputs),
                    patch.object(manager, "time", return_value=1),
                    patch.object(manager, "DynamicLayout", SimpleNamespace(w_scale=1)),
                ):
                    manager.preassign_releases()
                assert registry[1].captured_touch_id == 1

    def test_nonperfect_release_checks_actual_event_time_and_strict_sixth_second(self):
        with simulation_context():
            target = SimpleNamespace(kind=NoteKind.NORM_TAIL_RELEASE, target_time=-0.1)
            released = touch(1, 0, time=0, ended=True)  # +100 ms: GREAT, not PERFECT.
            for elapsed, expected in [(0.1, False), (1 / 6, False), (1 / 6 + 1e-8, True)]:
                manager.record_note_input(touch(1, 0, time=-elapsed))
                assert manager.is_allowed_release(released, target) == expected
            assert manager.is_allowed_release(touch(2, 0, time=0, ended=True), target)
            target.target_time = 0
            assert manager.is_allowed_release(released, target)

    def test_history_is_cleared_when_touch_disappears(self):
        with simulation_context():
            manager.record_note_input(touch(1, 0, time=0.9))
            with patch.object(manager, "processed_touches", return_value=[]):
                manager.update_input_state()
            assert 1 not in manager.InputState.recent_note_input_times


class FlickCalibrationTests(unittest.TestCase):
    def test_calibration_matches_source_dpi_formula_at_multiple_frame_rates(self):
        # Original SUS/Converter + LiveUtility + FlickNote.UpdateDelta formulas.
        for dpi, pixels in [(160, 720), (400, 1080), (500, 1440)]:
            cm = pixels / dpi * 2.54
            distance = flick_distance(2, cm)
            source_distance = dpi / 2.54 * 0.083333
            assert isclose(distance * pixels / 2, source_distance, abs_tol=1e-12)
            for fps in (30, 60, 90, 120, 144, 240):
                dt = 1 / fps
                for multiplier in (0.8, 1.2):
                    pixels_moved = source_distance * (dt / 0.016667) * multiplier
                    delta = Vec2(pixels_moved * 2 / pixels, 0)
                    assert has_flick_motion(delta, dt, distance) == (multiplier > 1)

    def test_strict_boundary_stationary_and_zero_duration_follow_source(self):
        for dt in (0.016667, 0, -1):
            assert not has_flick_motion(Vec2(0.02, 0), dt, 0.02)
            assert has_flick_motion(Vec2(0.02001, 0), dt, 0.02)
            assert not has_flick_motion(Vec2(0, 0), dt, 0.02)

    def test_portrait_landscape_and_stage_options_do_not_change_physical_calibration(self):
        for width, height in ((2, 32 / 9), (32 / 9, 2), (2, 14 / 3), (14 / 3, 2)):
            assert isclose(flick_distance(min(width, height), 7), 2 / 7 * 0.083333)
        # Different physical sizes need different screen-space thresholds.
        assert isclose(flick_distance(2, 14), flick_distance(2, 7) / 2)

    def test_note_uses_raw_frame_motion_instead_of_reported_speed_or_angle(self):
        with ExitStack() as stack:
            stack.enter_context(simulation_context())
            stack.enter_context(patch.object(play, "Layout", SimpleNamespace(flick_distance=0.02)))
            stack.enter_context(patch.object(play, "delta_time", return_value=0.016667))
            stack.enter_context(patch.object(play, "DynamicLayout", SimpleNamespace(rotate=0)))
            note = TickHarness(kind=NoteKind.NORM_FLICK, connected=False)
            note.direction = layout.FlickDirection.UP_RIGHT
            note.visual_stage_rotate = 0
            t = SimpleNamespace(id=1, time=1, speed=999, angle=0, delta=Vec2(0, 0))
            index = note.register_flick_touch(t)
            assert not note.record_flick_motion(t, index)
            t.speed = 0
            t.angle = 0
            t.delta = Vec2(-0.03, -0.03)
            assert note.record_flick_motion(t, index)
            assert note.flick_touch_states == 1  # Raw motion is down-left: wrong direction.


if __name__ == "__main__":
    unittest.main()
