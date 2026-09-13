from math import inf
from typing import Any

from sonolus.script.array import Dim
from sonolus.script.containers import VarArray
from sonolus.script.interval import Interval, lerp

from sekai.lib.ease import safe_unlerp_clamped
from sekai.lib.options import Options
from sekai.lib.stage import stage_note_visibility_start
from sekai.lib.timescale import (
    MIN_START_TIME,
    TrajectoryCache,
    evaluate_trajectory,
    group_preempt_time,
    group_visibility_end,
    group_visibility_start,
    prepare_trajectory,
    register_group_window,
)
from sekai.lib.timescale_visibility import VisibilitySource, first_visible, get_sources_visual_spawn_time


def register_note_group_window(note: Any, start: float, end: float) -> None:
    register_group_window(note.timescale_group, start, end)
    if note.is_attached:
        # Keep anchor groups active for attached notes, even if the anchors never spawn.
        register_group_window(note.attach_head_ref.get().timescale_group, start, end)
        register_group_window(note.attach_tail_ref.get().timescale_group, start, end)


def prepare_note_trajectories(note: Any, first: TrajectoryCache, second: TrajectoryCache, now: float) -> None:
    if note.is_attached:
        head = note.attach_head_ref.get()
        tail = note.attach_tail_ref.get()
        if now < head.target_time:
            prepare_trajectory(head.timescale_group, head.target_time, head.target_position, first, now)
        prepare_trajectory(tail.timescale_group, tail.target_time, tail.target_position, second, now)
    else:
        prepare_trajectory(note.timescale_group, note.target_time, note.target_position, first, now)


def _basic_progress(note: Any, cache: TrajectoryCache, now: float) -> float:
    distance = evaluate_trajectory(note.timescale_group, note.target_time, note.target_position, cache, now)
    return 1.0 - distance / group_preempt_time(note.timescale_group)


def note_progress(note: Any, first: TrajectoryCache, second: TrajectoryCache, now: float) -> float:
    if not note.is_attached:
        return _basic_progress(note, first, now)
    head = note.attach_head_ref.get()
    tail = note.attach_tail_ref.get()
    head_progress = _basic_progress(head, first, now) if now < head.target_time else 1.0
    tail_progress = _basic_progress(tail, second, now)
    head_frac = 0.0 if now < head.target_time else safe_unlerp_clamped(head.target_time, tail.target_time, now)
    target_frac = safe_unlerp_clamped(head.target_time, tail.target_time, note.target_time)
    return lerp(head_progress, tail_progress, safe_unlerp_clamped(head_frac, 1.0, target_frac))


def note_visual_progress(note: Any, first: TrajectoryCache, second: TrajectoryCache, now: float) -> float:
    return note_progress(note, first, second, now) - note.visual_y_offset


def basic_note_offset_bounds(note: Any) -> Interval:
    result = Interval(0, 0)
    if note.stage_ref.index > 0:
        result @= note.stage_ref.get().y_offset_bounds
    return result


def note_offset_bounds(note: Any) -> Interval:
    result = +Interval
    if note.is_attached:
        head = basic_note_offset_bounds(note.attach_head_ref.get())
        tail = basic_note_offset_bounds(note.attach_tail_ref.get())
        result @= Interval(min(head.start, tail.start), max(head.end, tail.end))
    else:
        result @= basic_note_offset_bounds(note)
    return result


def _basic_note_stage_visibility_end(note: Any) -> float:
    return note.stage_ref.get().note_visibility_end if note.stage_ref.index > 0 else inf


def note_stage_visibility_end(note: Any) -> float:
    """Return a time after which the note's stages keep it invisible."""
    if not note.is_attached:
        return _basic_note_stage_visibility_end(note)
    head = note.attach_head_ref.get()
    tail = note.attach_tail_ref.get()
    fraction = safe_unlerp_clamped(head.target_time, tail.target_time, note.target_time)
    if fraction <= 0:
        return _basic_note_stage_visibility_end(head)
    if fraction >= 1:
        return _basic_note_stage_visibility_end(tail)
    return max(_basic_note_stage_visibility_end(head), _basic_note_stage_visibility_end(tail))


def note_visibility_end(note: Any) -> float:
    """Return when timescale hiding or stage alpha keeps the note invisible for the rest of the level."""
    return min(group_visibility_end(note.timescale_group), note_stage_visibility_end(note))


def _basic_note_stage_visibility_start(note: Any, start: float) -> float:
    return stage_note_visibility_start(note.stage_ref.get(), start) if note.stage_ref.index > 0 else start


def note_stage_visibility_start(note: Any, start: float) -> float:
    """Return a later start if the note's stages keep it invisible after start."""
    if not note.is_attached:
        return _basic_note_stage_visibility_start(note, start)
    head = note.attach_head_ref.get()
    tail = note.attach_tail_ref.get()
    fraction = safe_unlerp_clamped(head.target_time, tail.target_time, note.target_time)
    if fraction <= 0:
        return _basic_note_stage_visibility_start(head, start)
    if fraction >= 1:
        return _basic_note_stage_visibility_start(tail, start)
    return min(_basic_note_stage_visibility_start(head, start), _basic_note_stage_visibility_start(tail, start))


def note_visibility_start(note: Any, start: float) -> float:
    """Return a spawn time after skipping known periods of invisibility."""
    if start == inf:
        return start
    return max(group_visibility_start(note.timescale_group, start), note_stage_visibility_start(note, start))


def extend_note_chain_stage_windows(head: Any, start: float, end: float) -> None:
    """Keep the stages of each note pair updating while the slide manager uses them."""
    if start >= end:
        return
    ref = +head.ref()
    while ref.index > 0:
        current = ref.get()
        segment_start = max(start, current.target_time)
        next_ref = +current.next_ref
        if next_ref.index <= 0:
            if segment_start < end:
                current.extend_stage_windows(segment_start - 1.0, end + 1.0)
            return
        following = next_ref.get()
        segment_end = min(end, following.target_time)
        if segment_start < segment_end:
            current.extend_stage_windows(segment_start - 1.0, segment_end + 1.0)
            following.extend_stage_windows(segment_start - 1.0, segment_end + 1.0)
        if following.target_time >= end:
            return
        ref.index = next_ref.index


def _append_visibility_source(
    note: Any, sources: VarArray[VisibilitySource, Dim[4]], offsets: Interval, clamp_after_hit: bool
) -> None:
    sources.append(
        VisibilitySource(
            note.timescale_group.index,
            note.target_time,
            group_preempt_time(note.timescale_group),
            offsets.start,
            offsets.end,
            clamp_after_hit,
        )
    )


def append_note_visibility_sources(note: Any, sources: VarArray[VisibilitySource, Dim[4]]) -> None:
    offsets = note_offset_bounds(note)
    if note.is_attached:
        # Give both sources the full offset range: after the head's hit time,
        # progress and y offset can use different interpolation fractions.
        _append_visibility_source(note.attach_head_ref.get(), sources, offsets, True)
        _append_visibility_source(note.attach_tail_ref.get(), sources, offsets, False)
    else:
        _append_visibility_source(note, sources, offsets, False)


def note_visual_spawn_time(note: Any, latest: float) -> float:
    if latest < MIN_START_TIME:
        return inf
    sources = +VarArray[VisibilitySource, Dim[4]]
    append_note_visibility_sources(note, sources)
    return get_sources_visual_spawn_time(sources, latest)


def segment_visual_spawn_time(head: Any, tail: Any, latest: float) -> float:
    if latest < MIN_START_TIME:
        return inf
    sources = +VarArray[VisibilitySource, Dim[4]]
    append_note_visibility_sources(head, sources)
    append_note_visibility_sources(tail, sources)
    return get_sources_visual_spawn_time(sources, latest)


def legacy_connector_spawn_time(head: Any) -> float:
    sources = +VarArray[VisibilitySource, Dim[4]]
    duration = lerp(0.35, 4, safe_unlerp_clamped(12, 1, Options.note_speed) ** 1.31)
    sources.append(VisibilitySource(head.timescale_group.index, head.target_time, duration, 0, 0, False))
    return first_visible(sources, 0.0, 1.0, MIN_START_TIME, head.target_time)
