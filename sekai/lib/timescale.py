from __future__ import annotations

from collections.abc import Iterator
from enum import IntEnum
from math import inf, trunc
from typing import Protocol, Self, cast

from sonolus.script import runtime
from sonolus.script.archetype import EntityRef, entity_info_at, get_archetype_by_name
from sonolus.script.debug import error
from sonolus.script.record import Record
from sonolus.script.timing import beat_to_bpm, beat_to_time

from sekai.lib import archetype_names
from sekai.lib.ease import EaseType
from sekai.lib.layout import Layout, preempt_time
from sekai.lib.options import Options
from sekai.lib.timescale_math import TimePosition, integrate_times, speed_at

MIN_START_TIME = -2.0
DISTANCE_LIMIT = 1e20
# Multiples of 64 stay exact in f32 up to magnitude 2**30.
SCROLL_SKIP_BLOCK = 64


class TransitionStyle(IntEnum):
    TIMESCALE = 0
    SCROLL = 1


class TimelineError(IntEnum):
    NONE = 0
    REFERENCE = 1
    OWNERSHIP = 2
    CYCLE = 3
    ORDER = 4
    VALUE = 5


class TargetPosition(Record):
    event_ref: int
    coordinate: TimePosition


class RunSummary(Record):
    """Note-distance changes across a sequence of runs.

    Distances at the two boundaries satisfy
    D(left, hit) = forward + ratio * D(right, hit).
    The separate backward term, -D(right, left), avoids division by the combined
    ratio, which can become very large or small.
    """

    ratio: float
    forward: float
    backward: float

    def then(self, other: Self) -> Self:
        return type(self)(
            self.ratio * other.ratio,
            self.forward + self.ratio * other.forward,
            other.backward + self.backward / other.ratio,
        )


class TrajectoryCache(Record):
    """A target's distance from a fixed boundary of the current run.

    Each consumer refreshes its cache when the run changes. Later targets use
    the run's end, and earlier targets use its start.
    """

    run_ref: int  # 0: uninitialized; -1: before the first marker.
    boundary_distance: float
    target_side: int  # -1: earlier run; 0: same run; 1: later run.


class TimescaleChangeLike(Protocol):
    id: int
    beat: float
    timescale: float
    timescale_skip: float
    timescale_group: EntityRef
    timescale_ease: EaseType
    transition_style: TransitionStyle
    hide_notes: bool
    next_ref: EntityRef
    event_start: float
    event_end: float
    converted_skip: float
    position: TimePosition
    scroll_skip: TimePosition
    scroll_skip_base: float
    ordinal: int
    prev_ref: int
    run_first: int
    run_end: int
    prev_run: int
    validation_owner: int
    jump_end: int
    jump_width: int
    jump: RunSummary
    note_visibility_start: float

    @classmethod
    def at(cls, index: int) -> Self: ...

    @property
    def index(self) -> int: ...


class TimescaleGroupLike(Protocol):
    first_ref: EntityRef
    force_note_speed: float
    valid: bool
    has_scroll: bool
    monotone_targets: bool
    identity: bool
    error_code: TimelineError
    used: bool
    effective_preempt: float
    needed_start: float
    needed_end: float
    note_visibility_end: float
    lookup_ref: int
    current_event: int
    current_run: int
    current_speed: float
    current_constant: bool
    coordinate: TimePosition
    time_valid: bool
    last_updated: float
    future_gain: float
    future_offset: float
    past_gain: float
    past_offset: float
    hide_notes: bool
    event_start: float
    event_end: float
    v0: float
    v1: float
    ease: EaseType
    style: TransitionStyle
    last_spawn_target: float
    last_spawn_ceiling: float
    last_spawn_time: float
    spawn_cursor_valid: bool

    @classmethod
    def at(cls, index: int) -> Self: ...

    @property
    def index(self) -> int: ...


def timescale_change_archetype() -> type[TimescaleChangeLike]:
    return cast(type[TimescaleChangeLike], get_archetype_by_name(archetype_names.TIMESCALE_CHANGE))


def timescale_group_archetype() -> type[TimescaleGroupLike]:
    return cast(type[TimescaleGroupLike], get_archetype_by_name(archetype_names.TIMESCALE_GROUP))


def _group_index(group: int | EntityRef) -> int:
    return group.index if isinstance(group, EntityRef) else group


def _marker(index: int) -> TimescaleChangeLike:
    return timescale_change_archetype().at(index)


def _require_group(index: int) -> TimescaleGroupLike:
    group = timescale_group_archetype().at(index)
    if runtime.is_preprocessing() and not group.valid:
        error("Invalid timescale group; inspect its validation error code")
    assert group.valid, "Invalid timescale group"
    return group


def _valid_marker_ref(index: int) -> bool:
    return 0 < index < inf and index % 1 == 0 and entity_info_at(index).archetype_id == timescale_change_archetype().id


def _fail(group: TimescaleGroupLike, code: TimelineError) -> None:
    group.valid, group.error_code = False, code


def iter_timescale_changes(index: int) -> Iterator[TimescaleChangeLike]:
    while index > 0:
        marker = _marker(index)
        yield marker
        index = marker.next_ref.index


def _integral(ref: int, left: float, right: float) -> float:
    if ref == 0:
        return right - left
    marker = _marker(ref)
    if marker.next_ref.index == 0:
        return marker.timescale * (right - left)
    return integrate_times(
        marker.timescale,
        _marker(marker.next_ref.index).timescale,
        marker.timescale_ease,
        marker.event_start,
        marker.event_end,
        left,
        right,
    )


def event_speed(ref: int, now: float) -> float:
    if ref == 0:
        return 1.0
    marker = _marker(ref)
    if marker.next_ref.index == 0:
        return marker.timescale
    return speed_at(
        marker.timescale,
        _marker(marker.next_ref.index).timescale,
        marker.timescale_ease,
        marker.event_start,
        marker.event_end,
        now,
    )


def _coordinate(ref: int, now: float) -> TimePosition:
    result = TimePosition.of(now)
    if ref > 0:
        marker = _marker(ref)
        # Integrate from the nearer endpoint to reduce rounding near a note hit.
        if marker.next_ref.index > 0 and now - marker.event_start > marker.event_end - now:
            following = _marker(marker.next_ref.index)
            result @= following.position.add(-following.converted_skip).add(-_integral(ref, now, marker.event_end))
        else:
            result @= marker.position.add(_integral(ref, marker.event_start, now))
    return result


def initialize_timescale_group(group: TimescaleGroupLike) -> None:
    group.valid, group.has_scroll, group.error_code = False, False, TimelineError.NONE
    group.monotone_targets = True
    group.identity = True
    group.used, group.time_valid, group.spawn_cursor_valid = False, False, False
    group.needed_start, group.needed_end = inf, -inf
    group.note_visibility_end = -inf
    group.lookup_ref, group.current_event, group.current_run = 0, 0, 0
    group.effective_preempt = preempt_time(group.force_note_speed)
    ref, previous, previous_time, ordinal = group.first_ref.index, 0, -inf, 0
    hidden = False
    while ref != 0:
        if not _valid_marker_ref(ref):
            _fail(group, TimelineError.REFERENCE)
            return
        marker = _marker(ref)
        if marker.validation_owner != 0:
            code = TimelineError.CYCLE if marker.validation_owner == group.index else TimelineError.OWNERSHIP
            _fail(group, code)
            if code == TimelineError.OWNERSHIP:
                _fail(timescale_group_archetype().at(marker.validation_owner), code)
            return
        if marker.timescale_group.index not in (0, group.index):
            _fail(group, TimelineError.OWNERSHIP)
            return
        marker.validation_owner = group.index
        if not (
            abs(marker.beat) < inf
            and abs(marker.timescale) < inf
            and abs(marker.timescale_skip) < inf
            and 0 <= marker.timescale_ease <= 5
            and marker.timescale_ease % 1 == 0
            and 0 <= marker.transition_style <= 1
            and marker.transition_style % 1 == 0
        ):
            _fail(group, TimelineError.VALUE)
            return
        converted = beat_to_time(marker.beat)
        if not abs(converted) < inf or converted < previous_time:
            _fail(group, TimelineError.ORDER if converted < previous_time else TimelineError.VALUE)
            return
        # Only count visible intervals between distinct marker times.
        if not hidden and converted > previous_time:
            group.note_visibility_end = converted
        hidden = marker.hide_notes
        marker.converted_skip = 0
        if marker.timescale_skip != 0:
            bpm = beat_to_bpm(marker.beat)
            if not 0 < bpm < inf:
                _fail(group, TimelineError.VALUE)
                return
            marker.converted_skip = marker.timescale_skip * (60 / bpm)
        ordinal += 1
        group.monotone_targets = group.monotone_targets and marker.timescale >= 0 and marker.converted_skip >= 0
        group.identity = group.identity and marker.timescale == 1 and marker.converted_skip == 0
        marker.ordinal, marker.prev_ref = ordinal, previous
        marker.event_start, marker.event_end = converted, converted
        if previous > 0:
            _marker(previous).event_end = converted
        if marker.transition_style == TransitionStyle.SCROLL:
            group.has_scroll = True
        previous, previous_time, ref = ref, converted, marker.next_ref.index
    if not hidden:
        group.note_visibility_end = inf
    elif group.note_visibility_end <= MIN_START_TIME:
        group.note_visibility_end = -inf
    visibility_start, visibility_ref = inf, previous
    while visibility_ref > 0:
        marker = _marker(visibility_ref)
        # Changes overridden at the same time do not create a visible interval.
        if not marker.hide_notes and (marker.next_ref.index <= 0 or marker.event_end > marker.event_start):
            visibility_start = marker.event_start
        marker.note_visibility_start = visibility_start
        visibility_ref = marker.prev_ref
    run, previous_run, run_count = 0, -1, 0
    for marker in iter_timescale_changes(group.first_ref.index):
        marker.scroll_skip = TimePosition.of(0)
        marker.scroll_skip_base = 0
        if marker.prev_ref > 0:
            marker.scroll_skip = _marker(marker.prev_ref).scroll_skip
            marker.scroll_skip_base = _marker(marker.prev_ref).scroll_skip_base
        # Divide skips by destination speed. Near-zero speeds can make these values
        # large, so store whole blocks separately to preserve small later skips.
        skip = marker.converted_skip / _scroll_speed(marker.timescale)
        whole = trunc(skip / SCROLL_SKIP_BLOCK) * SCROLL_SKIP_BLOCK
        prefix = marker.scroll_skip.add(skip - whole)
        carry = trunc(prefix.whole / SCROLL_SKIP_BLOCK) * SCROLL_SKIP_BLOCK
        marker.scroll_skip_base += whole + carry
        marker.scroll_skip = TimePosition(prefix.whole - carry, prefix.fraction)
        if marker.prev_ref == 0:
            marker.position = TimePosition.of(marker.event_start).add(marker.converted_skip)
        else:
            prior = _marker(marker.prev_ref)
            marker.position = prior.position.add(_integral(prior.index, prior.event_start, prior.event_end)).add(
                marker.converted_skip
            )
        if run == 0 or marker.transition_style != _marker(run).transition_style:
            if run > 0:
                _marker(run).run_end = marker.index
                previous_run = run
            run = marker.index
            run_count += 1
            marker.run_end = 0
        marker.run_first, marker.prev_run = run, previous_run
    if group.has_scroll:
        _initialize_run_index(run, run_count)
    group.valid = True


def _locate(group: TimescaleGroupLike, now: float, ref: int) -> int:
    while ref > 0 and now < _marker(ref).event_start:
        ref = _marker(ref).prev_ref
    following = group.first_ref.index if ref == 0 else _marker(ref).next_ref.index
    while following > 0 and _marker(following).event_start <= now:
        ref = following
        following = _marker(ref).next_ref.index
    return ref


def locate_time(group: int | EntityRef, now: float) -> int:
    index = _group_index(group)
    if index <= 0 or Options.disable_timescale:
        return 0
    entity = _require_group(index)
    entity.lookup_ref = _locate(entity, now, entity.lookup_ref)
    return entity.lookup_ref


def locate_target(group: int | EntityRef, hit_time: float) -> TargetPosition:
    ref = locate_time(group, hit_time)
    return TargetPosition(ref, _coordinate(ref, hit_time))


def locate_time_from(group: int | EntityRef, now: float, ref: int) -> int:
    # Leave the shared lookup cursor unchanged.
    index = _group_index(group)
    if index <= 0 or Options.disable_timescale:
        return 0
    return _locate(_require_group(index), now, ref)


def _run(ref: int) -> int:
    return -1 if ref == 0 else _marker(ref).run_first


def _scroll_speed(value: float) -> float:
    return min(value, -1e-4) if value < 0 else max(value, 1e-4)


def _scroll_width(ref: int, now: float, end_ref: int, end: float) -> float:
    left, right = TimePosition.of(0), TimePosition.of(0)
    left_base, right_base = 0.0, 0.0
    if ref > 0:
        left @= _marker(ref).scroll_skip
        left_base = _marker(ref).scroll_skip_base
    if end_ref > 0:
        right @= _marker(end_ref).scroll_skip
        right_base = _marker(end_ref).scroll_skip_base
    # Subtract the whole parts first to preserve small fractional differences.
    # Across a block boundary, 64.001 - 63.999 becomes (64 - 63) + (.001 - .999).
    difference = ((right_base - left_base) + (right.whole - left.whole)) + (right.fraction - left.fraction)
    return end - now + difference


def _timescale_distance(ref: int, now: float, target: TargetPosition, hit: float) -> float:
    if ref == target.event_ref:
        return _integral(ref, now, hit)
    return target.coordinate.difference(_coordinate(ref, now))


def _distance_from(
    group: TimescaleGroupLike,
    ref: int,
    now: float,
    target: TargetPosition,
    hit: float,
    distance_limit: float = DISTANCE_LIMIT,
) -> float:
    if group.has_scroll and _run(ref) != _run(target.event_ref):
        return _mixed_run_distance(group, ref, now, target, hit, distance_limit)
    if ref > 0 and _marker(ref).transition_style == TransitionStyle.SCROLL:
        value = _scroll_speed(event_speed(ref, now)) * _scroll_width(ref, now, target.event_ref, hit)
    else:
        value = _timescale_distance(ref, now, target, hit)
    return max(-distance_limit, min(distance_limit, value))


def _piece_summary(ref: int, start: float, end_ref: int, end: float) -> RunSummary:
    result = RunSummary(1, 0, 0)
    if ref > 0 and _marker(ref).transition_style == TransitionStyle.SCROLL:
        left_speed = _scroll_speed(event_speed(ref, start))
        right_speed = _scroll_speed(event_speed(end_ref, end))
        width = _scroll_width(ref, start, end_ref, end)
        result.ratio = left_speed / right_speed
        result.forward, result.backward = left_speed * width, right_speed * width
    else:
        distance = _coordinate(end_ref, end).difference(_coordinate(ref, start))
        result.forward, result.backward = distance, distance
    return result


def _initialize_run_index(run: int, ordinal: int) -> None:
    # Use Fenwick block sizes: 1, 2, 1, 4, 1, 2, 1, 8, ...
    # The width is the lowest set bit of the run's number.
    # Each run stores one forward summary: run 2 covers 2-3, run 4 covers 4-7.
    # A query crosses runs 1-7 with three summaries: [1], [2-3], [4-7].
    # Build right to left so larger blocks can reuse smaller summaries.
    while run > 0:
        marker = _marker(run)
        width, divisor = 1, ordinal
        while divisor % 2 == 0:
            width *= 2
            divisor //= 2
        marker.jump_end, marker.jump_width = marker.run_end, 0
        marker.jump = RunSummary(1, 0, 0)
        if marker.run_end > 0:
            endpoint = _marker(marker.run_end)
            marker.jump = _piece_summary(run, marker.event_start, endpoint.index, endpoint.event_start)
            marker.jump_width = 1
            cursor = marker.run_end
            while marker.jump_width < width and _marker(cursor).jump_end > 0:
                following = _marker(cursor)
                assert marker.jump_width + following.jump_width <= width
                marker.jump = marker.jump.then(following.jump)
                marker.jump_width += following.jump_width
                marker.jump_end = following.jump_end
                cursor = following.jump_end
        run, ordinal = marker.prev_run, ordinal - 1


def _mixed_run_distance(
    group: TimescaleGroupLike,
    ref: int,
    now: float,
    target: TargetPosition,
    hit: float,
    distance_limit: float,
) -> float:
    reverse = now > hit or (
        now == hit
        and (0 if ref == 0 else _marker(ref).ordinal)
        > (0 if target.event_ref == 0 else _marker(target.event_ref).ordinal)
    )
    left_ref, left, right_ref, right = ref, now, target.event_ref, hit
    if reverse:
        left_ref, left, right_ref, right = right_ref, right, left_ref, left
    target_run = _run(right_ref)
    total = RunSummary(1, 0, 0)
    while _run(left_ref) != target_run:
        current_run = _run(left_ref)
        boundary = group.first_ref.index if current_run < 0 else _marker(current_run).run_end
        assert boundary > 0
        part = RunSummary(1, 0, 0)
        indexed = False
        if left_ref == current_run and left == _marker(left_ref).event_start:
            marker = _marker(left_ref)
            if marker.jump_end > 0 and _marker(marker.jump_end).ordinal <= _marker(target_run).ordinal:
                part @= marker.jump
                boundary, indexed = marker.jump_end, True
        if not indexed:
            # Cross the rest of this run when no stored block fits.
            part @= _piece_summary(left_ref, left, boundary, _marker(boundary).event_start)
        total @= total.then(part)
        left_ref, left = boundary, _marker(boundary).event_start
    total @= total.then(_piece_summary(left_ref, left, right_ref, right))
    value = -total.backward if reverse else total.forward
    return max(-distance_limit, min(distance_limit, value))


def distance_between(group: int | EntityRef, now: float, hit: float, distance_limit: float = DISTANCE_LIMIT) -> float:
    index = _group_index(group)
    if index <= 0 or Options.disable_timescale:
        return max(-distance_limit, min(distance_limit, hit - now))
    entity = _require_group(index)
    ref = locate_time(index, now)
    return _distance_from(entity, ref, now, locate_target(index, hit), hit, distance_limit)


def distance_to_target(
    group: int | EntityRef,
    ref: int,
    now: float,
    target: TargetPosition,
    hit: float,
    distance_limit: float = DISTANCE_LIMIT,
) -> float:
    index = _group_index(group)
    if index <= 0 or Options.disable_timescale:
        return max(-distance_limit, min(distance_limit, hit - now))
    return _distance_from(_require_group(index), ref, now, target, hit, distance_limit)


def prepared_time_matches(stored: float, now: float) -> bool:
    # Allow f32 timestamp rounding in assertions. prepare_group still requires an exact match.
    return abs(stored - now) <= 2.0**-23 * max(abs(stored), abs(now)) + 2.0**-149


def prepare_group(group: int | EntityRef, now: float) -> None:
    index = _group_index(group)
    if index <= 0 or Options.disable_timescale:
        return
    entity = _require_group(index)
    if entity.time_valid and entity.last_updated == now:
        return
    ref = _locate(entity, now, entity.current_event)
    entity.current_event, entity.current_run = ref, _run(ref)
    entity.last_updated, entity.time_valid = now, True
    entity.coordinate, entity.current_speed = _coordinate(ref, now), event_speed(ref, now)
    entity.event_start, entity.event_end = -inf, inf
    entity.v0, entity.v1, entity.ease, entity.style = 1, 1, EaseType.NONE, TransitionStyle.TIMESCALE
    entity.hide_notes = False
    future = entity.first_ref.index
    if ref > 0:
        marker = _marker(ref)
        entity.event_start, entity.v0, entity.v1 = marker.event_start, marker.timescale, marker.timescale
        entity.ease, entity.style, entity.hide_notes = marker.timescale_ease, marker.transition_style, marker.hide_notes
        if marker.next_ref.index > 0:
            entity.event_end, entity.v1 = marker.event_end, _marker(marker.next_ref.index).timescale
        else:
            entity.ease = EaseType.NONE
        future = _marker(entity.current_run).run_end
    elif future > 0:
        entity.event_end = _marker(future).event_start
    if entity.style == TransitionStyle.SCROLL:
        entity.current_speed = _scroll_speed(entity.current_speed)
    entity.current_constant = entity.ease == EaseType.NONE or entity.v0 == entity.v1
    # Compute note distance from a cached distance at either run boundary:
    # D(now, hit) = offset + gain * D(boundary, hit).
    # Only gain and offset need to change while we stay in the same run.
    entity.future_gain, entity.past_gain, entity.future_offset, entity.past_offset = 1, 1, 0, 0
    for side in range(2):
        anchor = future if side == 0 else entity.current_run
        if anchor > 0:
            endpoint = _marker(anchor)
            gain, offset = 1.0, endpoint.position.difference(entity.coordinate)
            if entity.style == TransitionStyle.SCROLL:
                gain = entity.current_speed / _scroll_speed(endpoint.timescale)
                offset = entity.current_speed * _scroll_width(ref, now, anchor, endpoint.event_start)
            if side == 0:
                entity.future_gain, entity.future_offset = gain, offset
            else:
                entity.past_gain, entity.past_offset = gain, offset


def prepare_trajectory(
    group: int | EntityRef, hit: float, target: TargetPosition, cache: TrajectoryCache, now: float
) -> None:
    index = _group_index(group)
    if index <= 0 or Options.disable_timescale:
        return
    entity = _require_group(index)
    assert entity.time_valid
    assert prepared_time_matches(entity.last_updated, now)
    if cache.run_ref == entity.current_run:
        return
    cache.run_ref, cache.boundary_distance, cache.target_side = entity.current_run, 0, 0
    target_run = _run(target.event_ref)
    if target_run != entity.current_run:
        past = target_run < 0 or (
            entity.current_run > 0 and _marker(target_run).ordinal < _marker(entity.current_run).ordinal
        )
        # The side is constant within a run, just like the boundary distance.
        cache.target_side = -1 if past else 1
        anchor = (
            entity.current_run
            if past
            else (entity.first_ref.index if entity.current_run < 0 else _marker(entity.current_run).run_end)
        )
        cache.boundary_distance = _distance_from(entity, anchor, _marker(anchor).event_start, target, hit)


def evaluate_trajectory(
    group: int | EntityRef, hit: float, target: TargetPosition, cache: TrajectoryCache, now: float
) -> float:
    index = _group_index(group)
    if index <= 0 or Options.disable_timescale:
        return hit - now
    entity = _require_group(index)
    assert cache.run_ref == entity.current_run
    if cache.target_side == 0:
        # No skips occur between two times in the same event, so scroll distance
        # is the current speed multiplied by the time remaining until the hit.
        if target.event_ref == entity.current_event:
            if entity.style == TransitionStyle.SCROLL or entity.current_constant:
                return entity.current_speed * (hit - now)
            return integrate_times(entity.v0, entity.v1, entity.ease, entity.event_start, entity.event_end, now, hit)
        if entity.style == TransitionStyle.SCROLL:
            return entity.current_speed * _scroll_width(entity.current_event, now, target.event_ref, hit)
        return target.coordinate.difference(entity.coordinate)
    if cache.target_side < 0:
        return entity.past_gain * cache.boundary_distance + entity.past_offset
    return entity.future_gain * cache.boundary_distance + entity.future_offset


def register_group_window(group: int | EntityRef, start: float, end: float) -> None:
    index = _group_index(group)
    if index <= 0 or Options.disable_timescale or not (-inf < start <= end < inf):
        return
    assert runtime.is_preprocessing(), "Group lifetimes must be registered during preprocessing"
    entity = _require_group(index)
    entity.needed_start, entity.needed_end, entity.used = (
        min(entity.needed_start, start),
        max(entity.needed_end, end),
        True,
    )


def group_hide_notes(group: int | EntityRef) -> bool:
    index = _group_index(group)
    return index > 0 and not Options.disable_timescale and _require_group(index).hide_notes


def group_visibility_end(group: int | EntityRef) -> float:
    """Return the cached cutoff for permanent timescale hiding, or inf if none exists."""
    index = _group_index(group)
    if index <= 0 or Options.disable_timescale:
        return inf
    return _require_group(index).note_visibility_end


def group_visibility_start(group: int | EntityRef, start: float) -> float:
    """Return the first time at or after start when timescale hiding permits notes, or inf."""
    index = _group_index(group)
    if start == inf or index <= 0 or Options.disable_timescale:
        return start
    entity = _require_group(index)
    if start >= MIN_START_TIME and start >= entity.note_visibility_end:
        return inf
    ref = locate_time(index, start)
    return max(start, _marker(ref).note_visibility_start) if ref > 0 else start


def group_force_note_speed(group: int | EntityRef) -> float:
    index = _group_index(group)
    return timescale_group_archetype().at(index).force_note_speed if index > 0 else 0.0


def group_preempt_time(group: int | EntityRef) -> float:
    index = _group_index(group)
    return timescale_group_archetype().at(index).effective_preempt if index > 0 else Layout.default_preempt


def iter_timescale_changes_in_group_from_time(group: int | EntityRef, now: float) -> Iterator[TimescaleChangeLike]:
    index = _group_index(group)
    if index > 0 and not Options.disable_timescale:
        entity = _require_group(index)
        ref = locate_time(index, now)
        yield from iter_timescale_changes(entity.first_ref.index if ref == 0 else ref)
