"""Slides share hold/release state while retaining their sound selection."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sonolus.script.debug import simulation_context

from sekai.lib import connector as lib
from sekai.play import connector as play
from sekai.play import initialization as play_init
from sekai.watch import connector as watch
from sekai.watch import initialization as watch_init

K = lib.ConnectorKind


class SharedSlideSfxTests(unittest.TestCase):
    def test_cross_kind_release_updates_the_same_state(self):
        with simulation_context():
            lib.init_connector_sfx_times()
            lib.activate_connector_sfx(K.ACTIVE_NORMAL_BLUE, 1, 1, 4, 10)
            lib.activate_connector_sfx(K.FAKE_ACTIVE_CRITICAL_RED, 2, 2, 5, 20)
            assert lib.ConnectorSfxState.kind == K.ACTIVE_CRITICAL
            times = lib.deactivate_connector_sfx(4, 1, 4)
            assert not lib.connector_sfx_is_active(times)
            assert times.active_time == 2
            assert times.inactive_time == 4

    def test_activation_wins_over_release_at_same_time_in_either_order(self):
        for release_first in (False, True):
            with self.subTest(release_first=release_first), simulation_context():
                lib.init_connector_sfx_times()
                lib.activate_connector_sfx(K.ACTIVE_NORMAL, 1, 1, 4, 10)
                if release_first:
                    lib.deactivate_connector_sfx(4, 1, 4)
                lib.activate_connector_sfx(K.ACTIVE_CRITICAL, 4, 4, 6, 20)
                if not release_first:
                    lib.deactivate_connector_sfx(4, 1, 4)
                with patch.object(lib, "offset_adjusted_time", return_value=4):
                    assert lib.current_connector_sfx_is_active()
                assert lib.ConnectorSfxState.kind == K.ACTIVE_CRITICAL

    def test_sound_change_does_not_reactivate_a_slide(self):
        fake = SimpleNamespace(
            sfx_active=True,
            active_head=SimpleNamespace(
                index=10,
                target_time=1,
                active_connector_info=SimpleNamespace(connector_kind=K.ACTIVE_CRITICAL_RED, is_active=True),
            ),
            active_tail=SimpleNamespace(target_time=5, is_despawned=False),
            write_sfx_times=Mock(),
            activate_sfx_if_needed=Mock(),
            deactivate_sfx_if_needed=Mock(),
        )
        with (
            simulation_context(),
            patch.object(play, "Options", SimpleNamespace(auto_sfx=False)),
            patch.object(play, "time", return_value=3),
            patch.object(play, "offset_adjusted_time", return_value=3),
        ):
            lib.init_connector_sfx_times()
            lib.activate_connector_sfx(K.ACTIVE_NORMAL, 1, 1, 5, 10)
            play.SlideManager.update_sequential(fake)
            assert lib.ConnectorSfxState.active_time == 1
            assert lib.ConnectorSfxState.kind == K.ACTIVE_CRITICAL
            fake.activate_sfx_if_needed.assert_not_called()
            fake.deactivate_sfx_if_needed.assert_not_called()
            fake.write_sfx_times.assert_called_once()

    def test_auto_sfx_uses_one_event_order_for_both_kinds(self):
        for module, cls in ((play_init, play.Connector), (watch_init, watch.WatchConnector)):
            with self.subTest(mode=module.__name__):
                entities = {}
                # A normal release silences the shared state even with a critical slide held.
                # A zero-duration slide at 3 must not reactivate it or change the sound.
                for index, start, end, kind in (
                    (1, 1, 4, K.ACTIVE_NORMAL_BLUE),
                    (2, 2, 5, K.ACTIVE_CRITICAL_RED),
                    (3, 3, 3, K.ACTIVE_NORMAL),
                ):
                    entities[index] = SimpleNamespace(
                        index=index,
                        active_head_ref=SimpleNamespace(index=index),
                        active_head=SimpleNamespace(target_time=start),
                        active_tail=SimpleNamespace(target_time=end),
                        segment_head=SimpleNamespace(segment_kind=kind, timescale_group=0),
                        sfx_act_next=SimpleNamespace(index=0),
                        sfx_deact_next=SimpleNamespace(index=0),
                        ref=lambda index=index: SimpleNamespace(index=index),
                    )

                def sort_chain(ref, *, get_value, get_next_ref, entities=entities):
                    indices = []
                    while ref.index:
                        indices.append(ref.index)
                        ref = get_next_ref(entities[ref.index])
                    indices.sort(key=lambda i: get_value(entities[i]))
                    for pos, index in enumerate(indices):
                        get_next_ref(entities[index]).index = indices[pos + 1] if pos + 1 < len(indices) else 0
                    return SimpleNamespace(index=indices[0])

                archetype = module.PlayArchetype if module is play_init else module.WatchArchetype
                with (
                    patch.object(cls, "_compile_time_id", return_value=1),
                    patch.object(cls, "at", side_effect=lambda i, entities=entities: entities[i]),
                    patch.object(
                        module, "entity_info_at", side_effect=lambda i: SimpleNamespace(archetype_id=int(i > 0))
                    ),
                    patch.object(archetype, "_get_mro_id_array", side_effect=lambda i: [i]),
                    patch.object(module, "sort_linked_entities", side_effect=sort_chain),
                    patch.object(module, "schedule_connector_sfx") as schedule,
                ):
                    module.schedule_auto_connector_sfx(4)
                assert [call.args for call in schedule.call_args_list] == [
                    (K.ACTIVE_NORMAL_BLUE, 0, 1, 2),
                    (K.ACTIVE_CRITICAL_RED, 0, 2, 4),
                ]

    def test_replay_preserves_sound_changes_and_shared_release(self):
        events = [
            (-2, lib.ConnectorSfxEvent(lib.inactive_connector_sfx_times(), K.NONE)),
            (1, lib.ConnectorSfxEvent(lib.ConnectorSfxTimes(1, 1), K.ACTIVE_NORMAL)),
            (2, lib.ConnectorSfxEvent(lib.ConnectorSfxTimes(2, 1), K.ACTIVE_CRITICAL)),
            (4, lib.ConnectorSfxEvent(lib.ConnectorSfxTimes(2, 4), K.ACTIVE_CRITICAL)),
        ]
        stream = SimpleNamespace(iter_items_from=lambda start: iter(events))
        with (
            patch.object(watch_init, "Streams", SimpleNamespace(connector_sfx_events=stream)),
            patch.object(watch_init, "schedule_connector_sfx_between") as schedule,
        ):
            watch_init.schedule_unified_replay_connector_sfx()
        assert [call.args for call in schedule.call_args_list] == [
            (K.ACTIVE_NORMAL, 1, 2),
            (K.ACTIVE_CRITICAL, 2, 4),
        ]


if __name__ == "__main__":
    unittest.main()
