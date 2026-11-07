"""Sekai cue-limit ownership, rather than the longest overlapping Sonolus handle."""

import unittest
from contextlib import ExitStack
from types import SimpleNamespace as Namespace
from unittest.mock import Mock, patch

from sonolus.script.array import Array, Dim
from sonolus.script.debug import simulation_context
from sonolus.script.effect import LoopedEffectHandle
from sonolus.script.interval import Interval
from sonolus.script.quad import Rect
from sonolus.script.vec import Vec2

from sekai.lib import connector as lib
from sekai.lib.ease import EaseType
from sekai.lib.note import NoteKind
from sekai.play import connector as play
from sekai.play import initialization as play_init
from sekai.watch import connector as watch
from sekai.watch import initialization as watch_init

K = lib.ConnectorKind


class Hold:
    tail_finished = play.SlideManager.tail_finished
    update_sequential = play.SlideManager.update_sequential
    touch = play.SlideManager.touch
    update_sfx_state = play.SlideManager.update_sfx_state
    activate_sfx_if_needed = play.SlideManager.activate_sfx_if_needed
    deactivate_sfx_if_needed = play.SlideManager.deactivate_sfx_if_needed

    def __init__(self, index, kind=K.ACTIVE_NORMAL):
        bounds = Rect(l=-1, r=1, b=-1, t=1).as_quad()
        self.active_head = Namespace(
            index=index,
            segment_kind=kind,
            target_time=1,
            kind=NoteKind.NORM_HEAD_TAP,
            is_scored=True,
            is_trace=False,
            captured_touch_id=1,
            timescale_group=0,
            connector_ease=EaseType.LINEAR,
            input_interval=Interval(1 - 5 / 60, 1 + 5 / 60),
            hitbox=Namespace(bounds=bounds),
            active_connector_info=Namespace(input_bounds=bounds, connector_kind=kind, is_active=True),
        )
        self.active_tail = Namespace(
            target_time=5, is_scored=True, is_despawned=False, pending_despawn=False, connector_ease=EaseType.LINEAR
        )
        self.effect_pool_slot = 1
        self.sfx_active = False
        self.head_ready = False
        self.head_touched = False
        self.head_began_frame = -1
        self.write_sfx_times = Mock()


class SekaiCueLimitTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(simulation_context())
        lib.init_connector_sfx_times()
        self.now = 2
        self.stack.enter_context(patch.object(lib, "offset_adjusted_time", side_effect=lambda: self.now))
        self.stack.enter_context(patch.object(play, "offset_adjusted_time", side_effect=lambda: self.now))
        self.stack.enter_context(patch.object(play, "time", side_effect=lambda: self.now))
        self.stack.enter_context(patch.object(play, "delta_time", return_value=0.01))
        self.stack.enter_context(patch.object(play, "Options", Namespace(auto_sfx=False)))
        self.stack.enter_context(patch.object(play, "group_hide_notes", return_value=False))
        self.touches = self.stack.enter_context(patch.object(play.input_manager, "processed_touches", return_value=[]))
        self.stack.enter_context(
            patch.object(
                play.note, "compute_slide_input_bounds", side_effect=lambda *args: Rect(l=-1, r=1, b=-1, t=1).as_quad()
            )
        )

    def step(self, hold, now, held):
        self.now = now
        play.input_manager.InputState.frame += 1
        self.touches.return_value = [Namespace(position=Vec2(0, 0))] if held else []
        hold.update_sequential()
        if held:
            hold.touch()

    def test_replaced_hold_release_cannot_stop_the_new_owner(self):
        a, b = Hold(1), Hold(2)
        a.activate_sfx_if_needed(K.ACTIVE_NORMAL, 1)
        b.activate_sfx_if_needed(K.ACTIVE_NORMAL, 2)
        a.deactivate_sfx_if_needed(2.5)
        channel = lib.connector_sfx_channel(K.ACTIVE_NORMAL)
        assert channel.active_head_index == 2
        assert lib.current_connector_sfx_is_active(K.ACTIVE_NORMAL)
        assert a.write_sfx_times.call_count == 1

    def test_latest_hold_release_does_not_resume_the_older_held_cue(self):
        a, b = Hold(1), Hold(2)
        a.activate_sfx_if_needed(K.ACTIVE_NORMAL, 1)
        b.activate_sfx_if_needed(K.ACTIVE_NORMAL, 2)
        b.deactivate_sfx_if_needed(3)
        a.activate_sfx_if_needed(K.ACTIVE_NORMAL, 4)
        assert not lib.current_connector_sfx_is_active(K.ACTIVE_NORMAL)
        a.deactivate_sfx_if_needed(4.1)
        a.activate_sfx_if_needed(K.ACTIVE_NORMAL, 4.2)
        self.now = 4.2
        assert lib.connector_sfx_channel(K.ACTIVE_NORMAL).active_head_index == 1
        assert lib.current_connector_sfx_is_active(K.ACTIVE_NORMAL)

    def test_normal_and_critical_have_separate_cue_limits(self):
        a, b = Hold(1), Hold(2, K.ACTIVE_CRITICAL)
        a.activate_sfx_if_needed(K.ACTIVE_NORMAL, 1)
        b.activate_sfx_if_needed(K.ACTIVE_CRITICAL, 2)
        a.deactivate_sfx_if_needed(2.1)
        assert not lib.current_connector_sfx_is_active(K.ACTIVE_NORMAL)
        assert lib.current_connector_sfx_is_active(K.ACTIVE_CRITICAL)

    def test_same_frame_replacement_changes_owner_and_restarts_only_that_cue(self):
        manager = Namespace(sfx=+Array[LoopedEffectHandle, Dim[2]], last_head=+Array[int, Dim[2]])
        with patch.object(play, "update_connector_sfx") as update, patch.object(play, "destroy_looped_sfx"):
            lib.activate_connector_sfx(K.ACTIVE_NORMAL, 2, 1, 5, 1)
            play.ConnectorSfxManager.update_parallel(manager)
            lib.activate_connector_sfx(K.ACTIVE_NORMAL, 2, 1, 5, 2)
            play.ConnectorSfxManager.update_parallel(manager)
        assert [call.args[2] for call in update.call_args_list] == [True, True]
        assert manager.last_head[0] == 2
        assert manager.last_head[1] == 0

    def test_early_tap_and_cached_trace_head_follow_input_began(self):
        tap = Hold(1)
        self.step(tap, 0.95, True)
        assert lib.connector_sfx_channel(K.ACTIVE_NORMAL).active_time == 0.95
        self.step(tap, 0.96, False)
        trace = Hold(2)
        trace.active_head.kind = NoteKind.NORM_HEAD_TRACE
        trace.active_head.is_trace = True
        trace.active_head.captured_touch_id = 0
        self.step(trace, 0.95, True)
        assert not trace.sfx_active
        self.step(trace, 1.01, False)
        assert trace.sfx_active
        self.step(trace, 1.02, False)
        assert not trace.sfx_active

    def test_release_uses_current_input_and_tail_waits_for_its_judgment(self):
        hold = Hold(1)
        hold.active_tail.target_time = 2
        self.step(hold, 2.05, True)
        assert hold.sfx_active
        self.step(hold, 2.06, False)
        assert hold.active_head.active_connector_info.is_active
        assert not hold.sfx_active
        self.step(hold, 2.07, True)
        assert hold.sfx_active
        hold.active_tail.pending_despawn = True
        self.step(hold, 2.08, True)
        assert not hold.sfx_active

    def test_parent_input_deadline_can_release_sound_before_tail_miss(self):
        for kind, late in ((NoteKind.NORM_HEAD_TAP, 0.13), (NoteKind.NORM_HEAD_TRACE, 0.09)):
            hold = Hold(1)
            hold.active_head.kind = kind
            hold.active_head.is_trace = kind == NoteKind.NORM_HEAD_TRACE
            hold.active_tail.target_time = 2
            self.step(hold, 2.05, True)
            assert hold.sfx_active
            self.step(hold, 2 + late, True)
            assert not hold.sfx_active
            assert not hold.active_tail.pending_despawn

    def test_auto_sfx_matches_latest_owner_and_does_not_restore_stolen_cues(self):
        for module, cls in ((play_init, play.Connector), (watch_init, watch.WatchConnector)):
            entities = {}
            for index, start, end, kind in (
                (1, 1, 5, K.ACTIVE_NORMAL),
                (2, 2, 3, K.ACTIVE_NORMAL),
                (3, 1.5, 4, K.ACTIVE_CRITICAL),
                (4, 3, 3, K.ACTIVE_NORMAL),
            ):
                entities[index] = Namespace(
                    index=index,
                    head_ref=Namespace(index=index),
                    active_head_ref=Namespace(index=index),
                    active_head=Namespace(target_time=start),
                    active_tail=Namespace(target_time=end),
                    segment_head=Namespace(segment_kind=kind, timescale_group=0),
                    sfx_act_next=Namespace(index=0),
                    sfx_deact_next=Namespace(index=0),
                    ref=lambda index=index: Namespace(index=index),
                )

            def sort_chain(ref, *, get_value, get_next_ref, entities=entities):
                indices = []
                while ref.index:
                    indices.append(ref.index)
                    ref = get_next_ref(entities[ref.index])
                indices.sort(key=lambda i: get_value(entities[i]))
                for pos, index in enumerate(indices):
                    get_next_ref(entities[index]).index = indices[pos + 1] if pos + 1 < len(indices) else 0
                return Namespace(index=indices[0])

            archetype = module.PlayArchetype if module is play_init else module.WatchArchetype
            with (
                patch.object(cls, "_compile_time_id", return_value=1),
                patch.object(cls, "at", side_effect=entities.__getitem__),
                patch.object(archetype, "_get_mro_id_array", side_effect=lambda i: [i]),
                patch.object(module, "entity_info_at", side_effect=lambda i: Namespace(archetype_id=int(i > 0))),
                patch.object(module, "sort_linked_entities", side_effect=sort_chain),
                patch.object(module, "schedule_connector_sfx") as schedule,
            ):
                module.schedule_auto_connector_sfx(5)
            assert [call.args for call in schedule.call_args_list] == [
                (K.ACTIVE_NORMAL, 0, 1, 2),
                (K.ACTIVE_NORMAL, 0, 2, 3),
                (K.ACTIVE_CRITICAL, 0, 1.5, 4),
            ]

    def test_kind_tracks_replay_the_audible_owner_intervals_and_keep_legacy_reader(self):
        on1 = lib.ConnectorSfxTimes(1, -1e8)
        on2 = lib.ConnectorSfxTimes(2, -1e8)
        off = lib.ConnectorSfxTimes(-1e8, 3)
        stream = Namespace(iter_items_from=lambda start: iter([(1, on1), (2, on2), (3, off)]))
        with patch.object(watch_init, "schedule_connector_sfx_between") as schedule:
            watch_init.schedule_replay_connector_sfx(stream, K.ACTIVE_NORMAL)
        assert [call.args for call in schedule.call_args_list] == [(K.ACTIVE_NORMAL, 1, 2), (K.ACTIVE_NORMAL, 2, 3)]
        legacy = Namespace(
            iter_items_from=lambda start: iter(
                [(1, lib.ConnectorSfxEvent(on1, K.ACTIVE_NORMAL)), (3, lib.ConnectorSfxEvent(off, K.NONE))]
            )
        )
        with (
            patch.object(watch_init, "Streams", Namespace(connector_sfx_events=legacy)),
            patch.object(watch_init, "schedule_connector_sfx_between") as schedule,
        ):
            watch_init.schedule_unified_replay_connector_sfx()
        assert [call.args for call in schedule.call_args_list] == [(K.ACTIVE_NORMAL, 1, 3)]


if __name__ == "__main__":
    unittest.main()
