from math import inf

from sonolus.script.archetype import EntityRef
from sonolus.script.array import Dim
from sonolus.script.containers import VarArray
from sonolus.script.interval import Interval
from sonolus.script.record import Record

from sekai.lib.ease import EaseType
from sekai.lib.layout import conservative_progress_bounds
from sekai.lib.options import Options
from sekai.lib.timescale import (
    DISTANCE_LIMIT,
    MIN_START_TIME,
    TargetPosition,
    _require_group,
    _scroll_speed,
    distance_to_target,
    locate_target,
    locate_time_from,
    timescale_change_archetype,
    timescale_group_archetype,
)
from sekai.lib.timescale_math import integrate_times, speed_at

SPAWN_STEP = 1 / 120
SPAWN_PADDING = 0.01
COARSE_SPAWN_STEP = 0.2


class VisibilitySource(Record):
    group: int
    hit_time: float
    preempt: float
    offset_min: float
    offset_max: float
    clamp_after_hit: bool


class _DistanceBoundsPiece(Record):
    distance: float
    v0: float
    v1: float
    start: float
    end: float
    easing: EaseType
    scroll: bool
    peak_speed: float
    span: float
    width: float
    ceiling: float
    floor: float


def _prepare_distance_bounds(
    source: VisibilitySource, ref: int, anchor: float, distance: float, low: float, high: float
) -> _DistanceBoundsPiece:
    # All subdivisions of an event piece share these parameters.
    v0 = v1 = 1.0
    start, end = anchor, anchor + 1
    easing = EaseType.NONE
    scroll = False
    if ref > 0 and not (source.clamp_after_hit and anchor >= source.hit_time) and -inf < distance < inf:
        event = timescale_change_archetype().at(ref)
        v0 = v1 = event.timescale
        start, end = event.event_start, event.event_start + 1
        scroll = event.transition_style == 1
        if event.next_ref.index > 0:
            v1 = timescale_change_archetype().at(event.next_ref.index).timescale
            end, easing = event.event_end, event.timescale_ease
    peak_speed = abs(v0) if easing == EaseType.NONE else max(abs(v0), abs(v1))
    span = max(end - start, abs(anchor - start))
    width = 0.0
    if scroll:
        width = distance / _scroll_speed(speed_at(v0, v1, easing, start, end, anchor))
    return _DistanceBoundsPiece(
        distance,
        v0,
        v1,
        start,
        end,
        easing,
        scroll,
        peak_speed,
        span,
        width,
        source.preempt * (1 - low - source.offset_min),
        source.preempt * (1 - high - source.offset_max),
    )


def _prepared_distance_bounds(
    source: VisibilitySource, piece: _DistanceBoundsPiece, anchor: float, a: float, b: float
) -> Interval:
    result = Interval(-inf, inf)
    if source.clamp_after_hit and anchor >= source.hit_time:
        result @= Interval(0.0, 0.0)
        return result
    distance = piece.distance
    if not -inf < distance < inf:
        return result
    va = vb = piece.v0
    if piece.easing != EaseType.NONE:
        va = speed_at(piece.v0, piece.v1, piece.easing, piece.start, piece.end, a)
        vb = speed_at(piece.v0, piece.v1, piece.easing, piece.start, piece.end, b)
    # Allow for rounding in large intermediate values, even when the result is small.
    magnitude = max(abs(distance), piece.peak_speed * max(piece.span, abs(b - anchor)))
    if piece.scroll:
        # Bound speed and width separately, then find the smallest and largest
        # of the four endpoint products. This also covers sign changes.
        va, vb = _scroll_speed(va), _scroll_speed(vb)
        width = piece.width
        magnitude = max(magnitude, (abs(width) + abs(b - anchor)) * max(piece.peak_speed, 1e-4))
        q = width - (a - anchor)
        r = q - (b - a)
        lower = min(va * q, va * r, vb * q, vb * r)
        upper = max(va * q, va * r, vb * q, vb * r)
    else:
        integral = 0.0
        if piece.easing == EaseType.NONE:
            if piece.start != piece.end and anchor != a:
                integral = (a - anchor) * piece.v0
        else:
            integral = integrate_times(piece.v0, piece.v1, piece.easing, piece.start, piece.end, anchor, a)
        value = distance - integral
        lower = value + min(0.0, -max(va, vb) * (b - a))
        upper = value + max(0.0, -min(va, vb) * (b - a))
    if not -inf < lower <= upper < inf:
        return result
    # When timescale speed stays at zero, only rounding needs extra margin.
    # Scroll still moves at zero because _scroll_speed enforces a minimum speed.
    stopped = not piece.scroll and piece.v0 == 0 and (piece.easing == EaseType.NONE or piece.v1 == 0)
    slack = (0.0 if stopped else 0.01) + source.preempt * 1e-4 + max(magnitude, abs(lower), abs(upper)) * 1e-6
    # If the distance was capped, we do not know how far it extends beyond the cap.
    result @= Interval(
        -inf if distance <= -DISTANCE_LIMIT else lower - slack, inf if distance >= DISTANCE_LIMIT else upper + slack
    )
    return result


def _distance_bounds(
    source: VisibilitySource, ref: int, anchor: float, distance: float, a: float, b: float
) -> Interval:
    return _prepared_distance_bounds(
        source, _prepare_distance_bounds(source, ref, anchor, distance, 0, 0), anchor, a, b
    )


def _constant_piece_spawn_time(
    sources: VarArray[VisibilitySource, Dim[4]],
    pieces: VarArray[_DistanceBoundsPiece, Dim[4]],
    anchor: float,
    end: float,
) -> float:
    """Solve a linear visibility hull, or return -inf to request subdivision."""
    if not -inf < anchor <= end < inf:
        return -inf
    above = below = True
    from_above = from_below = inf
    for i in range(len(sources)):
        source, piece = sources[i], pieces[i]
        if (
            source.preempt <= 0
            or not -inf < piece.floor <= piece.ceiling < inf
            or not -DISTANCE_LIMIT < piece.distance < DISTANCE_LIMIT
            or (piece.easing != EaseType.NONE and piece.v0 != piece.v1)
            or piece.start == piece.end
        ):
            return -inf
        speed = _scroll_speed(piece.v0) if piece.scroll else piece.v0
        if source.clamp_after_hit and anchor >= source.hit_time:
            speed = 0.0
        distance = piece.distance
        last_distance = distance - speed * (end - anchor)
        magnitude = max(abs(distance), abs(last_distance), piece.peak_speed * max(piece.span, end - anchor))
        if piece.scroll:
            magnitude = max(magnitude, (abs(piece.width) + end - anchor) * max(piece.peak_speed, 1e-4))
        if not magnitude < inf:
            return -inf
        # Both endpoints contribute to the rounding margin for the whole piece.
        slack = (0.0 if speed == 0 else 0.01) + source.preempt * 1e-4 + magnitude * 1e-6
        if source.clamp_after_hit and anchor >= source.hit_time:
            slack = 0.0
        ceiling, floor = piece.ceiling + slack, piece.floor - slack
        above = above and distance > ceiling
        below = below and distance < floor
        if speed > 0:
            from_above = min(from_above, anchor + (distance - ceiling) / speed)
        elif speed < 0:
            from_below = min(from_below, anchor + (distance - floor) / speed)
    result = anchor
    if above:
        result = max(anchor, from_above)
    elif below:
        result = max(anchor, from_below)
    # Once any source leaves the common offscreen side, the segment hull can
    # intersect the visible range, even if its other endpoints remain offscreen.
    return result if result <= end else inf


def _identity_spawn_time(
    sources: VarArray[VisibilitySource, Dim[4]], low: float, high: float, earliest: float, latest: float
) -> float:
    """Solve identity trajectories without marker lookups; -inf requests fallback."""
    if len(sources) == 0 or latest < earliest:
        return inf
    if not -inf < earliest <= latest < inf or not -inf < low <= high < inf:
        return -inf
    above = below = True
    crossing = inf
    for source in sources:
        if source.group > 0 and not Options.disable_timescale and not _require_group(source.group).identity:
            return -inf
        ceiling = source.preempt * (1 - low - source.offset_min)
        floor = source.preempt * (1 - high - source.offset_max)
        distance = source.hit_time - earliest
        if source.preempt <= 0 or not -inf < floor <= ceiling < inf or not -DISTANCE_LIMIT < distance < DISTANCE_LIMIT:
            return -inf
        if source.clamp_after_hit and ceiling < 0:
            return -inf
        if source.clamp_after_hit:
            distance = max(0.0, distance)
        # Unit-speed groups still incur rounding when composing timeline coordinates.
        magnitude = max(abs(source.hit_time), abs(earliest), abs(latest), abs(distance), abs(ceiling), abs(floor))
        slack = 0.01 + source.preempt * 1e-4 + magnitude * 1e-6
        if source.clamp_after_hit and earliest >= source.hit_time:
            slack = 0.0
        ceiling += slack
        floor -= slack
        above = above and distance > ceiling
        below = below and distance < floor
        if not source.clamp_after_hit or ceiling >= 0:
            crossing = min(crossing, source.hit_time - ceiling)
    if below:
        return inf
    result = max(earliest, crossing) if above else earliest
    return max(earliest, result - SPAWN_PADDING - SPAWN_STEP) if result <= latest else inf


def first_visible(
    sources: VarArray[VisibilitySource, Dim[4]], low: float, high: float, earliest: float, latest: float
) -> float:
    """Find an early spawn time by rejecting intervals that cannot be visible.

    Search earlier halves first as we subdivide the remaining intervals.
    Add a small margin so notes spawn before they might become visible.
    """
    if len(sources) == 0 or latest < earliest:
        return inf
    targets = VarArray[TargetPosition, Dim[4]].new()
    refs = VarArray[int, Dim[4]].new()
    for source in sources:
        target = locate_target(source.group, source.hit_time)
        targets.append(target)
        refs.append(target.event_ref)
    anchor = earliest
    while anchor <= latest:
        pieces = VarArray[_DistanceBoundsPiece, Dim[4]].new()
        piece_end = latest
        for i in range(len(sources)):
            source = sources[i]
            ref = locate_time_from(source.group, anchor, refs[i])
            refs[i] = ref
            clamped = source.clamp_after_hit and anchor >= source.hit_time
            distance = 0.0 if clamped else distance_to_target(source.group, ref, anchor, targets[i], source.hit_time)
            pieces.append(_prepare_distance_bounds(source, ref, anchor, distance, low, high))
            if anchor < source.hit_time:
                piece_end = min(piece_end, source.hit_time)
            if not clamped:
                if ref > 0:
                    event = timescale_change_archetype().at(ref)
                    if event.next_ref.index > 0:
                        piece_end = min(piece_end, event.event_end)
                elif source.group > 0 and not Options.disable_timescale:
                    first = timescale_group_archetype().at(source.group).first_ref.index
                    if first > 0:
                        piece_end = min(piece_end, timescale_change_archetype().at(first).event_start)
        linear = _constant_piece_spawn_time(sources, pieces, anchor, piece_end)
        if linear > -inf:
            if linear < inf:
                return max(earliest, linear - SPAWN_PADDING - (SPAWN_STEP if linear > anchor else 0.0))
        else:
            coarse_checks = 0
            left, right = anchor, piece_end
            while True:
                # Reject when all sources stay on the same side of the visible range.
                above = below = True
                for i in range(len(sources)):
                    source = sources[i]
                    piece = pieces[i]
                    bounds = _prepared_distance_bounds(source, piece, anchor, left, right)
                    above = above and bounds.start > piece.ceiling
                    below = below and bounds.end < piece.floor
                    if not above and not below:
                        break
                if above or below:
                    if right == piece_end:
                        break
                    left, right = right, piece_end
                else:
                    if SPAWN_STEP < right - left <= COARSE_SPAWN_STEP and coarse_checks < 2:
                        coarse_checks += 1
                        # A visible right endpoint bounds the advance over fine
                        # search to this interval's width. The endpoint hull must
                        # intersect the visible range even with rounding margins.
                        # Limit checks per piece to avoid repeated work on near misses.
                        witness_above = witness_below = False
                        for i in range(len(sources)):
                            piece = pieces[i]
                            witness = _prepared_distance_bounds(sources[i], piece, anchor, right, right)
                            witness_above = witness_above or witness.end <= piece.ceiling
                            witness_below = witness_below or witness.start >= piece.floor
                            if witness_above and witness_below:
                                break
                        if witness_above and witness_below:
                            return max(earliest, left - SPAWN_PADDING)
                    middle = left + (right - left) * 0.5
                    if right - left <= SPAWN_STEP or middle <= left or middle >= right:
                        return max(earliest, left - SPAWN_PADDING)
                    # Search the earlier half first to find the earliest possible visibility.
                    right = middle
        if anchor == latest:
            break
        # Apply all markers at this boundary before searching the next interval.
        anchor = piece_end
    return inf


def get_sources_visual_spawn_time(sources: VarArray[VisibilitySource, Dim[4]], latest: float) -> float:
    bounds = conservative_progress_bounds()
    identity = _identity_spawn_time(sources, bounds.start, bounds.end, MIN_START_TIME, latest)
    if identity > -inf:
        return identity
    if len(sources) > 1:
        first = sources[0]
        if first.group > 0 and not Options.disable_timescale:
            group = timescale_group_archetype().at(first.group)
            proxy = VisibilitySource(
                first.group, first.hit_time, first.preempt, first.offset_min, first.offset_max, False
            )
            reusable = group.monotone_targets and first.preempt > 0
            for source in sources:
                floor = source.preempt * (1 - bounds.end - source.offset_max)
                ceiling = source.preempt * (1 - bounds.start - source.offset_min)
                reusable = (
                    reusable
                    and source.group == proxy.group
                    and source.preempt == proxy.preempt
                    and floor <= 0 <= ceiling
                )
                proxy.hit_time = min(proxy.hit_time, source.hit_time)
                proxy.offset_min = min(proxy.offset_min, source.offset_min)
                proxy.offset_max = max(proxy.offset_max, source.offset_max)
            if reusable and proxy.hit_time >= MIN_START_TIME:
                # Before the earliest hit, no source is clamped or closer than the proxy.
                # The proxy also has the widest visible distance range. All sources are
                # therefore out of view until the proxy could be visible. The proxy is
                # within its range at its hit time because the range includes zero, so
                # its spawn time is a safe starting point for the segment search.
                proxies = VarArray[VisibilitySource, Dim[4]].new()
                proxies.append(proxy)
                earliest = _search_with_spawn_cursor(proxies, bounds, latest)
                # Only the proxy search updates the cursor. Using the segment's later
                # spawn time could skip visible intervals in future searches.
                return first_visible(sources, bounds.start, bounds.end, earliest, latest)
    return _search_with_spawn_cursor(sources, bounds, latest)


def _search_with_spawn_cursor(sources: VarArray[VisibilitySource, Dim[4]], bounds: Interval, latest: float) -> float:
    """Find a spawn time, using the group's previous result when it is safe to reuse."""
    earliest = MIN_START_TIME
    cache_group = 0
    ceiling = 0.0
    if len(sources) == 1:
        source = sources[0]
        if source.group > 0 and not source.clamp_after_hit and not Options.disable_timescale:
            group = timescale_group_archetype().at(source.group)
            floor = source.preempt * (1 - bounds.end - source.offset_max)
            ceiling = source.preempt * (1 - bounds.start - source.offset_min)
            # Before the hit, monotone target distances and a nonincreasing ceiling
            # make cached spawn times safe to reuse. Hits before the search start
            # are excluded because their first visible interval may occur after the hit.
            if group.monotone_targets and source.hit_time >= MIN_START_TIME and floor <= 0 <= ceiling:
                cache_group = source.group
                if (
                    group.spawn_cursor_valid
                    and source.hit_time >= group.last_spawn_target
                    and ceiling <= group.last_spawn_ceiling
                    and group.last_spawn_time <= latest
                ):
                    earliest = max(earliest, group.last_spawn_time)
    result = first_visible(sources, bounds.start, bounds.end, earliest, latest)
    if cache_group > 0 and result < inf:
        group = timescale_group_archetype().at(cache_group)
        group.last_spawn_target = sources[0].hit_time
        group.last_spawn_ceiling = ceiling
        group.last_spawn_time = result
        group.spawn_cursor_valid = True
    return result


def group_index(group: int | EntityRef) -> int:
    return group.index if isinstance(group, EntityRef) else group
