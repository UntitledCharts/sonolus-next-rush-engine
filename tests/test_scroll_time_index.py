import bisect
import random
import unittest
from math import inf
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.array import Array, Dim
from sonolus.script.debug import simulation_context

from sekai.lib import timescale as ts
from sekai.lib import timescale_visibility as visibility
from sekai.lib.ease import EaseType
from sekai.lib.timescale_math import TimePosition


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
