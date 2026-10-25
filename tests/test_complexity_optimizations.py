"""Compare structural indexes with the original maps and searches."""

import bisect
import random
import unittest
from math import inf
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

from sonolus.script.array import Array, Dim
from sonolus.script.debug import simulation_context
from sonolus.script.sprite import Sprite

from sekai.lib import skin
from sekai.lib import slot_effect as slots
from sekai.lib import timescale as ts
from sekai.lib import timescale_visibility as visibility
from sekai.lib.baseevent import query_event_list, query_event_list_from
from sekai.lib.ease import EaseType
from sekai.lib.timescale_math import TimePosition


class SlotGenerationIndexTests(unittest.TestCase):
    def test_all_note_slot_bindings_have_dense_indices(self):
        supported = set(slots._SLOT_SPRITE_IDS)
        for name in dir(skin.BaseSkin):
            if name.startswith("slot_") and "slider_hold" not in name:
                sprite = getattr(skin.BaseSkin, name)
                if isinstance(sprite, Sprite):
                    assert sprite.id in supported
        for row in skin._STYLE_NOTES:
            for note in row:
                for sprite in (note.slot, note.slot_glow.perfect, note.slot_glow.great, note.slot_glow.good):
                    if sprite.id >= 0:
                        assert sprite.id in supported
        assert len(supported) == slots.SLOT_KIND_COUNT
        assert 3 * slots.SLOT_KIND_COUNT + 1 < 769

    def test_generations_match_the_original_map_including_clears_and_group_zero(self):
        rng = random.Random(215)
        with simulation_context():
            slots.clear_slot_effects()
            reference = {}
            history = []
            for step in range(2000):
                if step % 53 == 0:
                    slots.clear_slot_effects()
                    reference.clear()
                sprite = Sprite(rng.choice(slots._SLOT_SPRITE_IDS))
                group = rng.choice((0, 0, 1, 2, 3, 100000))
                previous = reference.get(sprite.id)
                generation = 0 if previous is None else previous[0] + (previous[1] != group)
                reference[sprite.id] = (generation, group)
                assert slots.next_slot_generation(sprite, group) == generation
                history.append((sprite, generation))
                for old_sprite, old_generation in rng.sample(history, min(8, len(history))):
                    entry = reference.get(old_sprite.id)
                    expected = entry is None or entry[0] - old_generation < 6
                    assert slots.is_slot_generation_visible(old_sprite, old_generation) == expected

    def test_only_the_seventh_distinct_bundle_retires_the_first(self):
        with simulation_context():
            slots.clear_slot_effects()
            for sprite_id in slots._SLOT_SPRITE_IDS:
                sprite = Sprite(sprite_id)
                first = slots.next_slot_generation(sprite, 0)
                assert slots.next_slot_generation(sprite, 0) == first
                for group in range(1, 6):
                    slots.next_slot_generation(sprite, group)
                    assert slots.is_slot_generation_visible(sprite, first)
                slots.next_slot_generation(sprite, 6)
                assert not slots.is_slot_generation_visible(sprite, first)


class EventRef:
    nodes: ClassVar[dict[int, SimpleNamespace]] = {}
    reads: ClassVar[int] = 0

    def __init__(self, index=0):
        self.index = index

    def get(self):
        EventRef.reads += 1
        return self.nodes[self.index]

    def with_archetype(self, archetype):
        return self

    def __pos__(self):
        return EventRef(self.index)


def make_events(times):
    count = len(times)
    EventRef.nodes = {
        i: SimpleNamespace(
            time=t,
            next_ref=EventRef(i + 1 if i < count else 0),
            skip_levels=min(15, (count - 1).bit_length()),
            skip_refs=[
                EventRef(i + (1 << j) if (i - 1) % (1 << j) == 0 and i + (1 << j) <= count else 0) for j in range(15)
            ],
        )
        for i, t in enumerate(times, 1)
    }
    return EventRef(1 if count else 0)


class StageEventCursorTests(unittest.TestCase):
    def test_cursor_matches_indexed_lookup_at_ties_steps_jumps_and_rewinds(self):
        rng = random.Random(530)
        for count in (0, 1, 4, 64, 1024):
            times = [i // 3 - 4 for i in range(count)]
            first = make_events(times)
            keys = [-10, -4, -4, -3.999, 0, 1, 10000, -5, 0]
            keys += sorted(rng.uniform(-8, count / 3 + 8) for _ in range(300))
            keys += [rng.uniform(-8, count / 3 + 8) for _ in range(100)]
            for strict in (False, True):
                cursor = 0
                for key in keys:
                    expected_a, expected_b = query_event_list(first, key, lambda event: event.time, strict)
                    a, b = query_event_list_from(first, key, lambda event: event.time, cursor, strict)
                    assert (a.index, b.index) == (expected_a.index, expected_b.index)
                    cursor = a.index

    def test_quiet_frames_do_not_repeat_the_skip_search(self):
        first = make_events(list(range(1024)))
        cursor = query_event_list(first, 512.1, lambda event: event.time)[0].index
        EventRef.reads = 0
        for i in range(1000):
            a, b = query_event_list_from(first, 512.1 + i / 10000, lambda event: event.time, cursor)
            assert (a.index, b.index) == (513, 514)
            cursor = a.index
        assert EventRef.reads <= 4000


class TimescaleTimeIndexTests(unittest.TestCase):
    def test_both_indexes_locate_all_duplicate_boundaries_and_arbitrary_seeks(self):
        rng = random.Random(641)
        with simulation_context():
            for count in (0, 1, 2, 4, 5, 17, 64, 257):
                times = [i // 3 - 5 for i in range(count)]
                for scroll in (False, True):
                    nodes = {}
                    for i, t in enumerate(times, 1):
                        nodes[i] = SimpleNamespace(
                            event_start=t,
                            event_end=times[i] if i < count else inf,
                            next_ref=SimpleNamespace(index=i + 1 if i < count else 0),
                            prev_ref=i - 1,
                            timescale=1 if i % 2 else -1,
                            timescale_ease=EaseType.NONE,
                            position=TimePosition.of(t),
                            tree_children=+Array[int, Dim[4]],
                            tree_start=0,
                            tree_end=0,
                            tree_min=+TimePosition,
                            tree_max=+TimePosition,
                            tree_magnitude=0,
                            tree_escape=0,
                            leaf_min=+TimePosition,
                            leaf_max=+TimePosition,
                            leaf_magnitude=0,
                            leaf_escape=0,
                        )
                    group = SimpleNamespace(
                        first_ref=SimpleNamespace(index=1 if count else 0),
                        last_ref=count,
                        tree_root=0,
                        has_scroll=scroll,
                    )
                    with patch.object(ts, "_marker", side_effect=lambda i, nodes=nodes: nodes[int(i)]):
                        ts._prepare_event_index(group, time_only=scroll)
                        queries = [-10, -5, -4, 0, 10000, *times]
                        queries += [rng.uniform(-8, count / 3 + 8) for _ in range(100)]
                        cursor = 0
                        for now in queries:
                            cursor = ts._locate(group, now, cursor, True)
                            assert cursor == bisect.bisect_right(times, now), (count, scroll, now)

    def test_scroll_time_tree_never_enables_coordinate_pruning(self):
        sources = [SimpleNamespace(group=1, preempt=1, offset_min=0, offset_max=0)]
        with (
            patch.object(visibility, "Options", SimpleNamespace(disable_timescale=False)),
            patch.object(visibility, "_require_group", return_value=SimpleNamespace(has_scroll=True, tree_root=1)),
        ):
            assert not visibility._can_use_visibility_indexes(sources, 0, 1, -10, 10)


if __name__ == "__main__":
    unittest.main()
