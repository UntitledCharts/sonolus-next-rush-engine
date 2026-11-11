from __future__ import annotations

from sonolus.script.archetype import PlayArchetype, callback
from sonolus.script.array import Array, Dim
from sonolus.script.containers import ArrayMap, ArraySet, VarArray
from sonolus.script.globals import level_memory
from sonolus.script.interval import clamp
from sonolus.script.runtime import Touch, screen, time, touches
from sonolus.script.values import alloc

from sekai.lib import archetype_names
from sekai.lib.buckets import SLIDE_END_LOCKOUT_DURATION
from sekai.lib.layout import DynamicLayout, Layout, segment_closeness_score, stage_aspect_ratio_locked
from sekai.lib.note import get_note_window, is_head
from sekai.lib.options import Options
from sekai.play import note
from sekai.play.input_index import INPUT_CANDIDATE_TOUCHES, InputCandidates, TapPriorityQuery, sort_input_notes

INPUT_SLOTS = INPUT_CANDIDATE_TOUCHES
INPUT_SCORE_TIME_SCALE = 0.05


def tap_center_score(touch, target) -> float:
    segment = target.hitbox.target
    axis = (segment.r - segment.l).normalize_or_zero()
    center = (segment.l + segment.r) / 2
    distance = (touch.position - center).dot(axis)
    return -distance * distance


def tap_has_high_accuracy(touch, target) -> bool:
    return touch.time - target.target_time in get_note_window(target.kind, False).great


def tap_input_is_eligible(touch, target) -> bool:
    return (
        target.captured_touch_id == 0
        and target.unadjusted_input_interval.start < touch.time < target.unadjusted_input_interval.end
        and target.hitbox.bounds.contains_point(touch.position)
    )


def select_tap_candidate(
    active, touch, owners: Array[int, Dim[256]] | None = None, touch_index: int = -1
) -> tuple[int, float]:
    left = 0
    right = len(active) - 1
    priority = TapPriorityQuery.new()
    while left <= right:
        first = active[left].get()
        if (
            (owners is not None and owners[left] != touch_index)
            or not tap_input_is_eligible(touch, first)
            or (first.is_trace_flick and priority.contains(active, touch, first.beat, has_priority_tap))
        ):
            left += 1
            continue
        current = active[right].get()
        if (
            (owners is not None and owners[right] != touch_index)
            or not tap_input_is_eligible(touch, current)
            or (current.is_trace_flick and priority.contains(active, touch, current.beat, has_priority_tap))
        ):
            right -= 1
            continue
        if left == right:
            break
        if first.target_time == current.target_time:
            if tap_center_score(touch, first) > tap_center_score(touch, current):
                right -= 1
            else:
                left += 1
        elif tap_has_high_accuracy(touch, current) and not tap_has_high_accuracy(touch, first):
            left += 1
        else:
            right -= 1
    result = -1
    score = 0.0
    if left <= right:
        result = left
        score = tap_center_score(touch, active[left].get())
    return result, score


@level_memory
class InputState:
    frame: int
    processed_touches: VarArray[Touch, Dim[32]]
    disallowed_empty_touches: ArraySet[int, Dim[32]]
    recent_note_input_times: ArrayMap[int, float, Dim[32]]
    last_started_touch_id: int
    last_started_touch_disallowed: bool
    previous_touch_disallowed: bool


def preprocess_touches():
    result = InputState.processed_touches
    result.clear()

    should_correct = Options.edge_touch_correction and stage_aspect_ratio_locked()
    field_bottom = screen().center.y - Layout.field_h / 2
    field_top = screen().center.y + Layout.field_h / 2

    for raw_touch in touches():
        if result.is_full():
            break

        touch = +raw_touch
        if should_correct:
            prev_position = raw_touch.prev_position
            touch.position.y = clamp(raw_touch.position.y, field_bottom, field_top)
            touch.start_position.y = clamp(raw_touch.start_position.y, field_bottom, field_top)
            touch.delta.y = touch.position.y - clamp(prev_position.y, field_bottom, field_top)
        result.append(touch)


def processed_touches() -> VarArray[Touch, Dim[32]]:
    return InputState.processed_touches


def disallow_empty(touch: Touch):
    InputState.disallowed_empty_touches.add(touch.id)
    if touch.id == InputState.last_started_touch_id or touch.started:
        InputState.last_started_touch_disallowed = True


def record_note_input(touch: Touch):
    InputState.recent_note_input_times[touch.id] = touch.time


def is_allowed_empty(touch: Touch) -> bool:
    return touch.id not in InputState.disallowed_empty_touches


def release_all_empty_disallows():
    InputState.disallowed_empty_touches.clear()
    InputState.last_started_touch_disallowed = False


def is_allowed_release(touch: Touch, target) -> bool:
    if touch.id not in InputState.recent_note_input_times:
        return True
    if touch.time - target.target_time in get_note_window(target.kind, False).perfect:
        return True
    return touch.time - InputState.recent_note_input_times[touch.id] > SLIDE_END_LOCKOUT_DURATION


class InputManager(PlayArchetype):
    name = archetype_names.INPUT_MANAGER

    @callback(order=-4)
    def update_sequential(self):
        InputState.frame += 1
        preprocess_touches()
        note.NoteMemory.active_tap_input_notes.clear()
        note.NoteMemory.active_release_input_notes.clear()

    @callback(order=-1)
    def touch(self):
        update_input_state()
        preassign_taps()
        preassign_releases()


def update_input_state():
    old_disallowed_empty_touches = +InputState.disallowed_empty_touches
    InputState.disallowed_empty_touches.clear()
    for touch in processed_touches():
        if touch.started:
            InputState.previous_touch_disallowed = InputState.last_started_touch_disallowed
            InputState.last_started_touch_id = touch.id
            InputState.last_started_touch_disallowed = False
    for existing_id in old_disallowed_empty_touches:
        for touch in processed_touches():
            if touch.id == existing_id:
                disallow_empty(touch)
                break

    old_recent_note_input_times = +InputState.recent_note_input_times
    InputState.recent_note_input_times.clear()
    for existing_id, input_time in old_recent_note_input_times.items():
        if any(touch.id == existing_id for touch in processed_touches()):
            InputState.recent_note_input_times[existing_id] = input_time


def is_last_started_touch_disallowed() -> bool:
    return InputState.last_started_touch_disallowed


def is_previous_touch_disallowed() -> bool:
    return InputState.previous_touch_disallowed


def _prepare_release_candidates(active, candidates: InputCandidates) -> bool:
    if len(active) < 32 or len(processed_touches()) < 4:
        return False
    count = 0
    for i in range(min(INPUT_SLOTS, len(processed_touches()))):
        touch = processed_touches()[i]
        count += touch.ended
    if count < 4:
        return False
    candidates.limit = count
    for i in range(INPUT_SLOTS):
        candidates.counts[i] = 0
    for note_i in range(len(active)):
        target = active[note_i].get()
        if target.captured_touch_id != 0:
            continue
        for i in range(min(INPUT_SLOTS, len(processed_touches()))):
            touch = processed_touches()[i]
            if not touch.ended:
                continue
            if not target.hitbox.bounds.contains_point(touch.position):
                continue
            if not target.unadjusted_input_interval.start < touch.time < target.unadjusted_input_interval.end:
                continue
            if not is_allowed_release(touch, target):
                continue
            score = (
                segment_closeness_score(touch.position, target.hitbox.target) / DynamicLayout.w_scale
                + (time() - target.target_time) / INPUT_SCORE_TIME_SCALE
            )
            if score != score:  # noqa: PLR0124 -- preserve the original path for NaN scores
                return False
            candidates.offer(i, note_i, score)
    for i in range(min(INPUT_SLOTS, len(processed_touches()))):
        candidates.finish(i)
    return True


def preassign_taps():
    active = note.NoteMemory.active_tap_input_notes
    if len(active) == 0 or not any(
        processed_touches()[i].started for i in range(min(INPUT_SLOTS, len(processed_touches())))
    ):
        return
    sort_input_notes(active)

    owners = alloc(Array[int, Dim[256]])
    touch_count = min(INPUT_SLOTS, len(processed_touches()))
    recent_inputs = alloc(Array[bool, Dim[INPUT_SLOTS]])
    for i in range(touch_count):
        recent_inputs[i] = False
    for note_i in range(len(active)):
        owners[note_i] = -1
        target = active[note_i].get()
        best_score = 0.0
        for i in range(touch_count):
            touch = processed_touches()[i]
            if not touch.started or not tap_input_is_eligible(touch, target):
                continue
            if not is_head(target.kind):
                recent_inputs[i] = True
            score = tap_center_score(touch, target)
            if owners[note_i] == -1 or score > best_score:
                owners[note_i] = i
                best_score = score

    preferred = alloc(Array[int, Dim[INPUT_SLOTS]])
    for i in range(touch_count):
        preferred[i] = -1
        touch = processed_touches()[i]
        if recent_inputs[i]:
            record_note_input(touch)
        if touch.started:
            preferred[i], _ = select_tap_candidate(active, touch, owners, i)
    for i in range(touch_count):
        note_i = preferred[i]
        if note_i < 0:
            continue
        target = active[note_i].get()
        touch = processed_touches()[i]
        disallow_empty(touch)
        target.captured_touch_id = touch.id
        target.captured_touch_time = min(touch.time, touch.start_time)


def has_priority_tap(touch: Touch, beat: float, query: TapPriorityQuery | None = None) -> bool:
    for ref in note.NoteMemory.active_tap_input_notes:
        target_note = ref.get()
        if query is not None and target_note.captured_touch_id == 0:
            if target_note.is_trace_flick:
                query.observed_traces += 1
            else:
                query.has_candidates = True
        if target_note.is_trace_flick or target_note.beat != beat or target_note.captured_touch_id != 0:
            continue
        if not target_note.unadjusted_input_interval.start < touch.time < target_note.unadjusted_input_interval.end:
            continue
        if target_note.hitbox.bounds.contains_point(touch.position):
            return True
    return False


def preassign_releases():
    active = note.NoteMemory.active_release_input_notes
    if len(active) == 0 or not any(
        processed_touches()[i].ended for i in range(min(INPUT_SLOTS, len(processed_touches())))
    ):
        return
    sort_input_notes(active)

    input_assigned = +Array[bool, Dim[INPUT_SLOTS]]
    for i in range(INPUT_SLOTS):
        if i >= len(processed_touches()) or not processed_touches()[i].ended:
            input_assigned[i] = True

    scores = +Array[float, Dim[INPUT_SLOTS]]
    preferred = +Array[int, Dim[INPUT_SLOTS]]
    candidates = alloc(InputCandidates)
    shortlisted = _prepare_release_candidates(active, candidates)

    for _ in range(INPUT_SLOTS):
        for i in range(INPUT_SLOTS):
            scores[i] = 0.0
            preferred[i] = -1

        for i in range(INPUT_SLOTS):
            if input_assigned[i]:
                continue
            if shortlisted:
                preferred[i] = candidates.best(i, active)
                if preferred[i] >= 0:
                    scores[i] = candidates.entries[i * INPUT_SLOTS].score
                continue
            touch = processed_touches()[i]
            for note_i in range(len(active)):
                target_note = active[note_i].get()
                if target_note.captured_touch_id != 0:
                    continue
                if not target_note.hitbox.bounds.contains_point(touch.position):
                    continue
                if (
                    not target_note.unadjusted_input_interval.start
                    < touch.time
                    < target_note.unadjusted_input_interval.end
                ):
                    continue
                if not is_allowed_release(touch, target_note):
                    continue
                score = (
                    segment_closeness_score(touch.position, target_note.hitbox.target) / DynamicLayout.w_scale
                    + (time() - target_note.target_time) / INPUT_SCORE_TIME_SCALE
                )
                if preferred[i] == -1 or score > scores[i]:
                    scores[i] = score
                    preferred[i] = note_i

        any_assigned = False
        for i in range(INPUT_SLOTS):
            note_i = preferred[i]
            if note_i < 0:
                continue
            is_best = True
            for j in range(INPUT_SLOTS):
                if j == i or preferred[j] != note_i:
                    continue
                if scores[j] > scores[i] or (scores[j] == scores[i] and j < i):
                    is_best = False
                    break
            if not is_best:
                continue
            target_note = active[note_i].get()
            touch = processed_touches()[i]
            disallow_empty(touch)
            target_note.captured_touch_id = touch.id
            target_note.captured_touch_time = touch.time
            input_assigned[i] = True
            any_assigned = True

        if not any_assigned:
            break
