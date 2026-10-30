"""Stable input ordering and per-touch priority queries without quadratic scans."""

from __future__ import annotations

from sonolus.script.array import Array, Dim
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


INPUT_CANDIDATE_TOUCHES = 16


class InputCandidate(Record):
    score: float
    note_index: int

    def worse_than(self, other: InputCandidate) -> bool:
        return self.score < other.score or (self.score == other.score and self.note_index > other.note_index)


class InputCandidates(Record):
    """Keep only T candidates per touch: at most T-1 can be taken by other touches."""

    entries: Array[InputCandidate, Dim[256]]
    counts: Array[int, Dim[16]]
    limit: int

    def _sift(self, base: int, count: int, hole: int, value: InputCandidate, minimum: bool):
        child = hole * 2 + 1
        while child < count:
            if child + 1 < count:
                left = self.entries[base + child]
                right = self.entries[base + child + 1]
                if right.worse_than(left) if minimum else left.worse_than(right):
                    child += 1
            candidate = self.entries[base + child]
            if not (candidate.worse_than(value) if minimum else value.worse_than(candidate)):
                break
            self.entries[base + hole] = candidate
            hole = child
            child = hole * 2 + 1
        self.entries[base + hole] = value

    def offer(self, touch_index: int, note_index: int, score: float):
        base = touch_index * INPUT_CANDIDATE_TOUCHES
        count = self.counts[touch_index]
        value = InputCandidate(score, note_index)
        if count < self.limit:
            hole = count
            while hole > 0:
                parent = (hole - 1) // 2
                candidate = self.entries[base + parent]
                if not value.worse_than(candidate):
                    break
                self.entries[base + hole] = candidate
                hole = parent
            self.entries[base + hole] = value
            self.counts[touch_index] = count + 1
        elif self.entries[base].worse_than(value):
            self._sift(base, count, 0, value, True)

    def finish(self, touch_index: int):
        # Selection uses a min heap; allocation consumes a max heap. Heapify the
        # retained T entries in O(T), without sorting all N notes for each touch.
        base = touch_index * INPUT_CANDIDATE_TOUCHES
        count = self.counts[touch_index]
        for hole in range(count // 2 - 1, -1, -1):
            value = +self.entries[base + hole]
            self._sift(base, count, hole, value, False)

    def best(self, touch_index: int, active) -> int:
        base = touch_index * INPUT_CANDIDATE_TOUCHES
        count = self.counts[touch_index]
        while count > 0:
            note_index = self.entries[base].note_index
            if active[note_index].get().captured_touch_id == 0:
                return note_index
            count -= 1
            self.counts[touch_index] = count
            if count > 0:
                value = +self.entries[base + count]
                self._sift(base, count, 0, value, False)
        return -1
