"""Stable input ordering and per-touch priority queries without quadratic scans."""

from __future__ import annotations

from sonolus.script.array import Dim
from sonolus.script.containers import Pair, VarArray
from sonolus.script.record import Record
from sonolus.script.values import alloc


def sort_input_notes(active):
    if len(active) < 16:
        active.sort(key=lambda ref: ref.get().target_time)
        return
    previous = active.get_unchecked(0).get().target_time
    ordered = True
    for i in range(1, len(active)):
        current = active.get_unchecked(i).get().target_time
        if current < previous:
            ordered = False
            break
        previous = current
    if ordered:
        return

    # A keyless sort uses heap sort; the original position preserves tie order.
    order = alloc(VarArray[Pair[float, Pair[int, int]], Dim[256]])
    order.clear()
    for i in range(len(active)):
        ref = active.get_unchecked(i)
        order.append(Pair(ref.get().target_time, Pair(i, ref.index)))
    order.sort()
    for i in range(len(active)):
        active.get_unchecked(i).index = order.get_unchecked(i).second.second


class TapPriorityQuery(Record):
    queries: int
    beats: VarArray[float, Dim[256]]

    @staticmethod
    def new() -> TapPriorityQuery:
        result = alloc(TapPriorityQuery)
        result.queries = 0
        return result

    def contains(self, active, touch, beat: float, initial_query) -> bool:
        # Single queries and small windows retain the inexpensive existing scan.
        if len(active) < 16:
            return initial_query(touch, beat)
        if self.queries == 0:
            self.queries = 1
            return initial_query(touch, beat)
        if self.queries == 1:
            self.beats.clear()
            for ref in active:
                target = ref.get()
                if target.is_trace_flick or target.captured_touch_id != 0:
                    continue
                if touch.time not in target.unadjusted_input_interval:
                    continue
                if target.hitbox.bounds.contains_point(touch.position):
                    self.beats.append(target.beat)
            self.beats.sort()
            self.queries = 2

        left = 0
        right = len(self.beats)
        while left < right:
            middle = (left + right) // 2
            if self.beats[middle] < beat:
                left = middle + 1
            else:
                right = middle
        return left < len(self.beats) and self.beats[left] == beat
