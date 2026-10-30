import random
import unittest
from types import SimpleNamespace
from typing import ClassVar

from sekai.lib.baseevent import query_event_list, query_event_list_from


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
