from __future__ import annotations

from sonolus.script.archetype import PlayArchetype, callback
from sonolus.script.array import Array, Dim
from sonolus.script.containers import ArrayMap, ArraySet
from sonolus.script.globals import level_memory
from sonolus.script.runtime import Touch, time, touches

from sekai.lib import archetype_names
from sekai.lib.buckets import SLIDE_END_LOCKOUT_DURATION
from sekai.lib.layout import DynamicLayout, segment_closeness_score
from sekai.lib.note import is_head
from sekai.play import note

INPUT_SLOTS = 16
INPUT_SCORE_TIME_SCALE = 0.05


@level_memory
class InputState:
    disallowed_empty_touches: ArraySet[int, Dim[32]]
    disallowed_release_touches: ArrayMap[int, float, Dim[32]]


def disallow_empty(touch: Touch):
    InputState.disallowed_empty_touches.add(touch.id)


def disallow_release(touch: Touch, until_time: float):
    if touch.id in InputState.disallowed_release_touches:
        until_time = max(InputState.disallowed_release_touches[touch.id], until_time)
    InputState.disallowed_release_touches[touch.id] = until_time


def is_allowed_empty(touch: Touch) -> bool:
    return touch.id not in InputState.disallowed_empty_touches


def is_allowed_release(touch: Touch, target_time: float) -> bool:
    if touch.id not in InputState.disallowed_release_touches:
        return True
    return InputState.disallowed_release_touches[touch.id] <= target_time


class InputManager(PlayArchetype):
    name = archetype_names.INPUT_MANAGER

    @callback(order=-1)
    def update_sequential(self):
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

    old_disallowed_release_touches = +InputState.disallowed_release_touches
    InputState.disallowed_release_touches.clear()

    for touch in touches():
        if touch.id in old_disallowed_empty_touches:
            disallow_empty(touch)

        if touch.id in old_disallowed_release_touches:
            InputState.disallowed_release_touches[touch.id] = old_disallowed_release_touches[touch.id]


def preassign_taps():
    active = note.NoteMemory.active_tap_input_notes
    active.sort(key=lambda ref: ref.get().target_time)

    input_assigned = +Array[bool, Dim[INPUT_SLOTS]]
    for i in range(INPUT_SLOTS):
        if i >= len(touches()) or not touches()[i].started:
            input_assigned[i] = True

    scores = +Array[float, Dim[INPUT_SLOTS]]
    preferred = +Array[int, Dim[INPUT_SLOTS]]

    for _ in range(INPUT_SLOTS):
        for i in range(INPUT_SLOTS):
            scores[i] = 0.0
            preferred[i] = -1

        for i in range(INPUT_SLOTS):
            if input_assigned[i]:
                continue
            touch = touches()[i]
            for note_i in range(len(active)):
                target_note = active[note_i].get()
                if target_note.captured_touch_id != 0:
                    continue
                if not target_note.hitbox.bounds.contains_point(touch.position):
                    continue
                if touch.time not in target_note.unadjusted_input_interval:
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
            touch = touches()[i]
            disallow_empty(touch)
            if not is_head(target_note.kind):
                disallow_release(touch, target_note.target_time + SLIDE_END_LOCKOUT_DURATION)
            target_note.captured_touch_id = touch.id
            target_note.captured_touch_time = min(touch.time, touch.start_time)
            input_assigned[i] = True
            any_assigned = True

        if not any_assigned:
            break


def preassign_releases():
    active = note.NoteMemory.active_release_input_notes
    active.sort(key=lambda ref: ref.get().target_time)

    input_assigned = +Array[bool, Dim[INPUT_SLOTS]]
    for i in range(INPUT_SLOTS):
        if i >= len(touches()) or not touches()[i].ended:
            input_assigned[i] = True

    scores = +Array[float, Dim[INPUT_SLOTS]]
    preferred = +Array[int, Dim[INPUT_SLOTS]]

    for _ in range(INPUT_SLOTS):
        for i in range(INPUT_SLOTS):
            scores[i] = 0.0
            preferred[i] = -1

        for i in range(INPUT_SLOTS):
            if input_assigned[i]:
                continue
            touch = touches()[i]
            for note_i in range(len(active)):
                target_note = active[note_i].get()
                if target_note.captured_touch_id != 0:
                    continue
                if not target_note.hitbox.bounds.contains_point(touch.position):
                    continue
                if touch.time not in target_note.unadjusted_input_interval:
                    continue
                ignore_lockout = False
                if target_note.active_head_ref.index > 0:
                    head_bounds = target_note.active_head_ref.get().active_connector_info.input_bounds
                    ongoing = False
                    for t in touches():
                        if not t.ended and head_bounds.contains_point(t.position):
                            ongoing = True
                            break
                    ignore_lockout = not ongoing
                if not ignore_lockout and not is_allowed_release(touch, target_note.target_time):
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
            touch = touches()[i]
            disallow_empty(touch)
            target_note.captured_touch_id = touch.id
            target_note.captured_touch_time = touch.time
            input_assigned[i] = True
            any_assigned = True

        if not any_assigned:
            break
