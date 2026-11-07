"""Connected ticks follow Sekai; independent ticks keep the extended timing window."""

import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sonolus.script.archetype import EntityRef
from sonolus.script.array import Dim
from sonolus.script.bucket import Judgment
from sonolus.script.containers import VarArray
from sonolus.script.debug import simulation_context
from sonolus.script.quad import Rect
from sonolus.script.vec import Vec2

from sekai.lib.connector import ConnectorKind
from sekai.lib.ease import EaseType
from sekai.lib.note import NoteKind
from sekai.play import note as play


class TickHarness:
    is_connector_tick = play.BaseNote.is_connector_tick
    judgment_window = play.BaseNote.judgment_window
    is_tail = play.BaseNote.is_tail
    is_trace = play.BaseNote.is_trace
    is_trace_flick = play.BaseNote.is_trace_flick
    is_slide_end_flick = play.BaseNote.is_slide_end_flick
    is_friction_flick = play.BaseNote.is_friction_flick
    uses_frame_miss = play.BaseNote.uses_frame_miss
    prepare_input_intervals = play.BaseNote.prepare_input_intervals
    update_sequential = play.BaseNote.update_sequential
    touch = play.BaseNote.touch
    update_parallel = play.BaseNote.update_parallel
    handle_tick_input = play.BaseNote.handle_tick_input
    update_connector_tick_parallel = play.BaseNote.update_connector_tick_parallel
    tick_trigger = play.BaseNote.tick_trigger
    should_do_delayed_trigger = play.BaseNote.should_do_delayed_trigger
    handle_late_miss = play.BaseNote.handle_late_miss
    complete = play.BaseNote.complete
    complete_parallel = play.BaseNote.complete_parallel
    fail_late = play.BaseNote.fail_late
    judge = play.BaseNote.judge
    post_judge = play.BaseNote.post_judge
    handle_trace_input = play.BaseNote.handle_trace_input
    handle_flick_input = play.BaseNote.handle_flick_input
    handle_trace_flick_input = play.BaseNote.handle_trace_flick_input
    flick_touch_index = play.BaseNote.flick_touch_index
    register_flick_touch = play.BaseNote.register_flick_touch
    record_flick_motion = play.BaseNote.record_flick_motion
    finish_flick = play.BaseNote.finish_flick
    judge_wrong_way = play.BaseNote.judge_wrong_way
    check_direction_matches = play.BaseNote.check_direction_matches
    check_touch_is_eligible_for_trace = play.BaseNote.check_touch_is_eligible_for_trace

    def __init__(self, *, kind=NoteKind.NORM_TICK, connected=True, attached=False):
        self.kind = kind
        self.target_time = 1
        self.active_head_ref = EntityRef[play.BaseNote](index=int(connected))
        self.tick_head_ref = EntityRef[play.BaseNote](index=int(connected))
        self.tick_tail_ref = EntityRef[play.BaseNote](index=2 if connected else 0)
        self.is_attached = attached
        self.attach_head_ref = EntityRef[play.BaseNote](index=3 if attached else 0)
        self.is_scored = True
        self.despawn = False
        self.pending_despawn = False
        self.pending_post_judge = False
        self.managing_despawn = False
        self.tick_pending = False
        self.late_miss_pending = False
        self.flick_touch_ids = +VarArray[int, Dim[8]]
        self.flick_touch_states = 0
        self.last_flick_input_frame = 0
        self.best_touch_id = -1
        self.slide_end_input = False
        self.should_play_hit_effects = False
        self.best_touch_time = play.DEFAULT_BEST_TOUCH_TIME
        self.best_touch_matches_direction = False
        self.captured_touch_id = 0
        self.visual_start_time = float("inf")
        self.draw_hitbox = Mock()
        self.result = SimpleNamespace(judgment=None, bucket=SimpleNamespace(id=0), accuracy=None, bucket_value=None)
        self.hitbox = SimpleNamespace(bounds=Rect(l=-1, r=1, t=1, b=-1).as_quad())
        self.bounds = self.hitbox.bounds
        self.connector_tick_input_bounds = lambda: self.bounds
        self.prepare_input_intervals()


class TickJudgmentTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(simulation_context())
        self.clock = self.stack.enter_context(patch.object(play, "time", return_value=0))
        self.adjusted = self.stack.enter_context(patch.object(play, "offset_adjusted_time", return_value=0))
        self.delta = self.stack.enter_context(patch.object(play, "delta_time", return_value=1 / 60))
        self.offset = self.stack.enter_context(patch.object(play, "input_offset", return_value=0))
        self.stack.enter_context(patch.object(play, "PlayLevelMemory", SimpleNamespace(last_note_sfx_time=0)))
        self.stack.enter_context(patch.object(play, "SkillActive", SimpleNamespace(judgment=False)))
        self.touches = self.stack.enter_context(patch.object(play.input_manager, "processed_touches", return_value=[]))
        self.disallow = self.stack.enter_context(patch.object(play.input_manager, "disallow_empty"))
        self.head = SimpleNamespace(
            kind=NoteKind.NORM_HEAD_TAP,
            is_scored=True,
            captured_touch_id=1,
            is_despawned=False,
            active_connector_info=SimpleNamespace(is_active=False, connector_kind=ConnectorKind.ACTIVE_NORMAL),
        )
        self.tail = SimpleNamespace(is_despawned=False, pending_despawn=False, slide_end_input=False)
        self.anchor = SimpleNamespace(
            tick_head_ref=EntityRef[play.BaseNote](index=1), tick_tail_ref=EntityRef[play.BaseNote](index=2)
        )
        self.registry = {1: self.head, 2: self.tail, 3: self.anchor}
        self.stack.enter_context(
            patch.object(play.BaseNote, "at", side_effect=lambda index, **kw: self.registry[index])
        )

    def frame(self, note, now, *, positions=(), ended=False):
        play.input_manager.InputState.frame += 1
        self.clock.return_value = now + self.offset.return_value
        self.adjusted.return_value = now
        self.touches.return_value = [
            SimpleNamespace(id=i + 1, position=Vec2(x, 0), ended=ended, started=False) for i, x in enumerate(positions)
        ]
        note.update_sequential()
        if positions:
            note.touch()
        note.update_parallel()
        return note.result.judgment

    def test_connected_tick_accepts_first_reached_frame_even_after_zero_window(self):
        for kind in (NoteKind.NORM_TICK, NoteKind.CRIT_TICK, NoteKind.HIDE_TICK):
            for attached in (False, True):
                for offset in (-0.05, 0, 0.05):
                    with self.subTest(kind=kind, attached=attached, offset=offset):
                        self.offset.return_value = offset
                        note = TickHarness(kind=kind, attached=attached)
                        assert self.frame(note, 0.99) is None
                        assert self.frame(note, 1.01, positions=[0]) == Judgment.PERFECT
                        assert note.result.accuracy == 0

    def test_connected_tick_does_not_remember_early_input_or_accept_next_frame(self):
        note = TickHarness()
        assert self.frame(note, 0.99, positions=[0]) is None
        assert note.best_touch_time == play.DEFAULT_BEST_TOUCH_TIME
        assert self.frame(note, 1.01) is None
        assert self.frame(note, 1.02, positions=[0]) == Judgment.MISS

    def test_large_frame_jump_still_has_exactly_one_input_pass(self):
        note = TickHarness()
        assert self.frame(note, 0.7) is None
        assert self.frame(note, 1.2) is None
        assert self.frame(note, 1.21, positions=[0]) == Judgment.MISS
        note = TickHarness()
        assert self.frame(note, 1.2, positions=[0]) == Judgment.PERFECT

    def test_exact_target_is_an_input_frame(self):
        note = TickHarness()
        assert self.frame(note, 1, positions=[0]) == Judgment.PERFECT
        note = TickHarness()
        assert self.frame(note, 1) is None
        assert self.frame(note, 1.01, positions=[0]) == Judgment.MISS

    def test_current_slide_bounds_replace_fixed_tick_hitbox(self):
        note = TickHarness()
        note.bounds = Rect(l=2, r=3, t=1, b=-1).as_quad()
        assert self.frame(note, 1.01, positions=[2.5]) == Judgment.PERFECT
        note = TickHarness()
        note.bounds = Rect(l=2, r=3, t=1, b=-1).as_quad()
        assert self.frame(note, 1.01, positions=[0]) is None
        assert self.frame(note, 1.02) == Judgment.MISS

    def test_connector_effect_grace_does_not_judge_a_tick(self):
        self.head.active_connector_info.is_active = True
        note = TickHarness()
        assert self.frame(note, 1.01) is None
        assert self.frame(note, 1.02) == Judgment.MISS

    def test_tap_hold_needs_its_initial_tap_until_the_head_misses(self):
        self.head.captured_touch_id = 0
        note = TickHarness()
        assert self.frame(note, 1.01, positions=[0]) is None
        assert self.frame(note, 1.02) == Judgment.MISS
        self.head.is_despawned = True
        note = TickHarness()
        assert self.frame(note, 1.01, positions=[0]) == Judgment.PERFECT

    def test_trace_hold_can_receive_held_input_without_a_tap(self):
        self.head.captured_touch_id = 0
        self.head.kind = NoteKind.NORM_HEAD_TRACE
        note = TickHarness()
        assert self.frame(note, 1.01, positions=[0]) == Judgment.PERFECT

    def test_release_frame_input_is_still_available(self):
        note = TickHarness()
        assert self.frame(note, 1.01, positions=[0], ended=True) == Judgment.PERFECT

    def test_visible_tick_termination_and_hidden_combo_termination_differ(self):
        for attached in (False, True):
            for pending in (False, True):
                for accepted_end in (False, True):
                    for kind in (NoteKind.NORM_TICK, NoteKind.CRIT_TICK, NoteKind.HIDE_TICK):
                        with self.subTest(attached=attached, pending=pending, end=accepted_end, kind=kind):
                            self.tail.is_despawned = not pending
                            self.tail.pending_despawn = pending
                            self.tail.slide_end_input = accepted_end
                            note = TickHarness(kind=kind, attached=attached)
                            expected = (
                                Judgment.MISS if kind == NoteKind.HIDE_TICK and not accepted_end else Judgment.PERFECT
                            )
                            assert self.frame(note, 0.99) == expected

    def test_tail_flick_in_progress_only_automatically_judges_hidden_combo_when_due(self):
        self.tail.slide_end_input = True
        hidden = TickHarness(kind=NoteKind.HIDE_TICK)
        assert self.frame(hidden, 0.99) is None
        assert self.frame(hidden, 1.01) == Judgment.PERFECT
        visible = TickHarness()
        assert self.frame(visible, 1.01) is None
        assert self.frame(visible, 1.02) == Judgment.MISS

    def test_fake_active_connector_keeps_automatic_ticks(self):
        self.head.active_connector_info.is_active = True
        self.head.active_connector_info.connector_kind = ConnectorKind.FAKE_ACTIVE_NORMAL
        note = TickHarness()
        assert self.frame(note, 0.99) is None
        assert self.frame(note, 1.01) == Judgment.PERFECT

    def test_tail_bad_input_is_distinguished_from_an_unplayed_miss(self):
        # Sekai's child.Result > Pass includes BAD, even though Sonolus reports BAD as MISS.
        end = TickHarness(kind=NoteKind.NORM_TAIL_TAP)
        end.judge(1.12)
        assert end.result.judgment == Judgment.MISS
        assert end.pending_despawn
        assert end.slide_end_input
        missed = TickHarness(kind=NoteKind.NORM_TAIL_TAP)
        assert self.frame(missed, 1.2) is None
        assert self.frame(missed, 1.22) == Judgment.MISS
        assert not missed.slide_end_input

    def test_tail_flick_input_state_does_not_require_flick_movement(self):
        self.clock.return_value = 0.99
        self.touches.return_value = [SimpleNamespace(id=1)]
        end = SimpleNamespace(
            flick_touch_index=lambda touch: 0,
            record_flick_motion=lambda touch, index: False,
            is_slide_end_flick=True,
            slide_end_input=False,
            target_time=1,
        )
        self.touches.return_value[0].time = 0.99
        play.BaseNote.handle_trace_flick_input(end)
        assert end.slide_end_input

    def test_expired_tail_flick_input_is_not_a_successful_termination(self):
        end = TickHarness(kind=NoteKind.NORM_TAIL_FLICK)
        end.slide_end_input = True
        assert self.frame(end, 1.15) is None
        assert self.frame(end, 1.2) == Judgment.MISS
        assert not end.slide_end_input

    def test_independent_ticks_keep_window_early_memory_and_late_input(self):
        for kind in (NoteKind.NORM_TICK, NoteKind.CRIT_TICK, NoteKind.HIDE_TICK):
            with self.subTest(kind=kind):
                note = TickHarness(kind=kind, connected=False)
                assert not note.is_connector_tick
                assert abs(note.input_interval.start - (1 - 5 / 60)) < 1e-12
                assert abs(note.input_interval.end - (1 + 5 / 60)) < 1e-12
                assert self.frame(note, 0.95, positions=[0]) is None
                assert note.best_touch_time == 1
                assert self.frame(note, 1.01) is None
                assert self.frame(note, 1.03) == Judgment.PERFECT
                note = TickHarness(kind=kind, connected=False)
                assert self.frame(note, 1.05, positions=[0]) == Judgment.PERFECT
                note = TickHarness(kind=kind, connected=False)
                assert self.frame(note, 1.09) == Judgment.MISS

    def test_nonzero_window_with_connector_metadata_keeps_legacy_branch(self):
        note = TickHarness(connected=False)
        note.tick_head_ref = EntityRef[play.BaseNote](index=1)
        assert not note.is_connector_tick
        assert self.frame(note, 0.95, positions=[0]) is None
        assert self.frame(note, 1.01) is None
        assert self.frame(note, 1.03) == Judgment.PERFECT

    def test_tick_geometry_walks_only_crossed_segments_and_skips_attachments(self):
        def ref(index):
            return EntityRef[play.BaseNote](index=index)

        def node(index, target, next_index, *, attached=False):
            result = SimpleNamespace(
                target_time=target,
                is_attached=attached,
                is_scored=False,
                is_connector_tick=False,
                kind=NoteKind.ANCHOR,
                next_ref=ref(next_index),
                prev_ref=ref(index - 1 if index > 4 else 0),
                connector_ease=EaseType.LINEAR,
            )
            self.registry[index] = result
            return result

        current = node(4, 1, 5)
        node(5, 1.05, 6, attached=True)
        crossed = node(6, 1.1, 7)
        following = node(7, 2, 0)
        tick = SimpleNamespace(is_attached=False, ref=lambda: ref(4), next_ref=ref(5), kind=NoteKind.NORM_TICK)
        attached_tick = SimpleNamespace(
            is_attached=True, attach_head_ref=ref(4), attach_tail_ref=ref(6), kind=NoteKind.HIDE_TICK
        )
        with patch.object(
            play, "compute_slide_input_bounds", return_value=Rect(l=-1, r=1, t=1, b=-1).as_quad()
        ) as compute:
            for subject in (tick, attached_tick):
                self.adjusted.return_value = 1.02
                play.BaseNote.connector_tick_input_bounds(subject)
                assert compute.call_args.args[1:3] == (current, crossed)
                self.adjusted.return_value = 1.2
                play.BaseNote.connector_tick_input_bounds(subject)
                assert compute.call_args.args[1:3] == (crossed, following)
                self.adjusted.return_value = 2.1
                play.BaseNote.connector_tick_input_bounds(subject)
                assert compute.call_args.args[1:3] == (following, following)

    def test_parent_lane_stops_at_first_visible_tick_reached_this_frame(self):
        def ref(index):
            return EntityRef[play.BaseNote](index=index)

        for index, target in ((4, 0.5), (5, 1), (6, 1.1), (7, 2)):
            self.registry[index] = SimpleNamespace(
                target_time=target,
                is_attached=False,
                is_scored=True,
                is_connector_tick=index in (5, 6),
                kind=NoteKind.NORM_TICK if index in (5, 6) else NoteKind.ANCHOR,
                next_ref=ref(index + 1 if index < 7 else 0),
                prev_ref=ref(index - 1 if index > 4 else 0),
                connector_ease=EaseType.LINEAR,
            )
        visible = SimpleNamespace(is_attached=False, ref=lambda: ref(6), next_ref=ref(7), kind=NoteKind.NORM_TICK)
        hidden = SimpleNamespace(
            is_attached=True, attach_head_ref=ref(6), attach_tail_ref=ref(7), kind=NoteKind.HIDE_TICK
        )
        self.adjusted.return_value = 1.11
        with patch.object(
            play, "compute_slide_input_bounds", return_value=Rect(l=-1, r=1, t=1, b=-1).as_quad()
        ) as compute:
            for subject in (visible, hidden):
                for delta, expected in ((0.02, 6), (0.2, 5)):
                    self.delta.return_value = delta
                    play.BaseNote.connector_tick_input_bounds(subject)
                    point = self.registry[expected]
                    assert compute.call_args.args[1:3] == (point, point)
            hidden.attach_head_ref = ref(4)
            hidden.attach_tail_ref = ref(5)
            play.BaseNote.connector_tick_input_bounds(hidden)
            point = self.registry[5]
            assert compute.call_args.args[1:3] == (point, point)
            self.registry[5].kind = NoteKind.HIDE_TICK
            play.BaseNote.connector_tick_input_bounds(hidden)
            point = self.registry[6]
            assert compute.call_args.args[1:3] == (point, point)


if __name__ == "__main__":
    unittest.main()
