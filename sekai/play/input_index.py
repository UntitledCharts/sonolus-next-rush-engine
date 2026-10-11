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
    if len(active) < 32:
        active.sort(key=lambda ref: ref.get().target_time)
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
    last_beat: float
    last_result: bool
    has_candidates: bool
    observed_traces: int
    ready: bool
    beats: VarArray[float, Dim[256]]

    @staticmethod
    def new() -> TapPriorityQuery:
        result = alloc(TapPriorityQuery)
        result.queries = 0
        result.ready = False
        return result

    def contains(self, active, touch, beat: float, initial_query) -> bool:
        # Single queries and small windows retain the inexpensive existing scan.
        if len(active) < 16:
            return initial_query(touch, beat)
        if self.queries == -1 and len(self.beats) == 0:
            return False
        if self.queries != 0 and self.last_beat == beat:
            return self.last_result
        result = self._contains(active, touch, beat, initial_query)
        self.last_beat = beat
        self.last_result = result
        return result

    def _contains(self, active, touch, beat: float, initial_query) -> bool:
        if not self.ready:
            if self.queries == 0:
                self.queries = 1
                self.has_candidates = False
                self.observed_traces = 0
                # Observe candidate density during the existing scan, without another traversal.
                result = initial_query(touch, beat, self)
                if not self.has_candidates:
                    self.beats.clear()
                    self.queries = -1
                    self.ready = True
                return result
            if self.queries < 2 or (self.observed_traces < 16 and self.queries < 32):
                self.queries += 1
                return initial_query(touch, beat)
            self.beats.clear()
            ordered = True
            for ref in active:
                target = ref.get()
                if target.is_trace_flick or target.captured_touch_id != 0:
                    continue
                if touch.time not in target.unadjusted_input_interval:
                    continue
                if target.hitbox.bounds.contains_point(touch.position):
                    if len(self.beats) > 0 and target.beat < self.beats.get_unchecked(len(self.beats) - 1):
                        ordered = False
                    self.beats.append(target.beat)
            if not ordered and len(self.beats) >= 16 and self.observed_traces >= 32:
                self.beats.sort()
                ordered = True
            self.ready = True
            self.queries = -1 if ordered else 0

        # Cache eligibility once; only repeated queries justify sorting the cache.
        # The linear phase is bounded, retaining O(N log N) worst-case work.
        if self.queries >= 0:
            if len(self.beats) < 16 or self.queries < 32:
                self.queries += 1
                return any(candidate == beat for candidate in self.beats)
            self.beats.sort()
            self.queries = -1

        left = 0
        right = len(self.beats)
        while left < right:
            middle = (left + right) // 2
            if self.beats[middle] < beat:
                left = middle + 1
            else:
                right = middle
        return left < len(self.beats) and self.beats[left] == beat
