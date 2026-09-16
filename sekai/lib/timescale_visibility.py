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
    _timescale_distance,
    _visibility_node_bounds,
    _VisibilityBounds,
    distance_to_target,
    locate_target,
    locate_time_from,
    timescale_change_archetype,
    timescale_group_archetype,
)
from sekai.lib.timescale_math import TimePosition, integrate_times, speed_at

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


def _can_use_visibility_indexes(
    sources: VarArray[VisibilitySource, Dim[4]], low: float, high: float, earliest: float, latest: float
) -> bool:
    if Options.disable_timescale or not -inf < earliest <= latest < inf:
        return False
    for source in sources:
        floor = source.preempt * (1 - high - source.offset_max)
        ceiling = source.preempt * (1 - low - source.offset_min)
        if source.preempt <= 0 or not -DISTANCE_LIMIT < floor <= ceiling < DISTANCE_LIMIT:
            return False
        if source.group > 0 and _require_group(source.group).has_scroll:
            return False
    return True


def _prefix_range_end(
    sources: VarArray[VisibilitySource, Dim[4]],
    targets: VarArray[TargetPosition, Dim[4]],
    low: float,
    high: float,
    anchor: float,
    latest: float,
) -> float:
    """Skip searching before the first marker only if all sources stay above or all stay below the visible range."""
    above = below = True
    end = latest
    for i in range(len(sources)):
        source, target = sources[i], targets[i]
        floor = source.preempt * (1 - high - source.offset_max)
        ceiling = source.preempt * (1 - low - source.offset_min)
        lower = upper = slack = 0.0
        if not source.clamp_after_hit or anchor < source.hit_time:
            boundary = latest
            magnitude = abs(target.coordinate.whole)
            if source.group > 0:
                first = timescale_group_archetype().at(source.group).first_ref.index
                if first > 0:
                    boundary = timescale_change_archetype().at(first).event_start
            upper = target.coordinate.difference(TimePosition.of(anchor))
            lower = upper - (boundary - anchor)
            magnitude = max(magnitude, abs(anchor), abs(boundary))
            magnitude = max(magnitude, abs(lower), abs(upper))
            if not -inf < lower <= upper < inf or not magnitude < inf:
                return anchor
            # Allow for rounding in coordinate bounds and distance evaluation.
            slack = 0.01 + source.preempt * 1e-4 + magnitude * 1e-6
            end = min(end, boundary)
            if anchor < source.hit_time:
                end = min(end, source.hit_time)
        above = above and lower > ceiling + slack
        below = below and upper < floor - slack
        if not above and not below:
            return anchor
    return max(anchor, end)


def _tree_range_clear(
    bounds: _VisibilityBounds,
    sources: VarArray[VisibilitySource, Dim[4]],
    targets: VarArray[TargetPosition, Dim[4]],
    low: float,
    high: float,
    anchor: float,
) -> bool:
    above = below = True
    for i in range(len(sources)):
        source, target = sources[i], targets[i]
        lower = upper = slack = 0.0
        if not source.clamp_after_hit or anchor < source.hit_time:
            lower = target.coordinate.difference(bounds.maximum)
            upper = target.coordinate.difference(bounds.minimum)
            magnitude = max(abs(target.coordinate.whole), bounds.magnitude, abs(lower), abs(upper))
            if not -inf < lower <= upper < inf or not magnitude < inf:
                return False
            slack = 0.01 + source.preempt * 1e-4 + magnitude * 1e-6
        ceiling = source.preempt * (1 - low - source.offset_min)
        floor = source.preempt * (1 - high - source.offset_max)
        above = above and lower > ceiling + slack
        below = below and upper < floor - slack
        if not above and not below:
            return False
    return True


def _tree_range_end(
    root: int,
    sources: VarArray[VisibilitySource, Dim[4]],
    targets: VarArray[TargetPosition, Dim[4]],
    low: float,
    high: float,
    anchor: float,
    latest: float,
) -> float:
    group = timescale_group_archetype().at(sources[0].group)
    ref = root
    end = latest
    for source in sources:
        if anchor < source.hit_time:
            end = min(end, source.hit_time)
    while ref != 0:
        bounds = _visibility_node_bounds(ref)
        if bounds.start >= end:
            return max(anchor, end)
        escape = 0
        if ref < 0:
            escape = timescale_change_archetype().at(-ref).leaf_escape
        else:
            escape = timescale_change_archetype().at(ref).tree_escape
        if bounds.end <= anchor or _tree_range_clear(bounds, sources, targets, low, high, anchor):
            ref = escape
        elif ref < 0:
            return max(anchor, bounds.start)
        else:
            ref = timescale_change_archetype().at(ref).tree_children[0]
    return max(anchor, min(end, timescale_change_archetype().at(group.last_ref).event_start))


class _OffscreenRange(Record):
    side: int
    end: float


def _offscreen_side(lower: float, upper: float, ceiling: float, floor: float) -> int:
    return 1 if lower > ceiling else -1 if upper < floor else 0


def _source_range_end(
    source: VisibilitySource,
    target: TargetPosition,
    ref: int,
    low: float,
    high: float,
    anchor: float,
    latest: float,
    side: int,
) -> _OffscreenRange:
    result = _OffscreenRange(side, anchor)
    end = min(latest, source.hit_time) if anchor < source.hit_time else latest
    ceiling = source.preempt * (1 - low - source.offset_min)
    floor = source.preempt * (1 - high - source.offset_max)
    root = timescale_group_archetype().at(source.group).tree_root if source.group > 0 else 0
    clamped = source.clamp_after_hit and anchor >= source.hit_time
    if clamped or ref <= 0 or root == 0 or timescale_change_archetype().at(ref).next_ref.index <= 0:
        distance = (
            0.0
            if clamped
            else max(-DISTANCE_LIMIT, min(DISTANCE_LIMIT, _timescale_distance(ref, anchor, target, source.hit_time)))
        )
        if not clamped:
            if ref > 0:
                marker = timescale_change_archetype().at(ref)
                if marker.next_ref.index > 0:
                    end = min(end, marker.event_end)
            elif source.group > 0:
                first = timescale_group_archetype().at(source.group).first_ref.index
                if first > 0:
                    end = min(end, timescale_change_archetype().at(first).event_start)
        piece = _prepare_distance_bounds(source, ref, anchor, distance, low, high)
        interval = _prepared_distance_bounds(source, piece, anchor, anchor, end)
        found = _offscreen_side(interval.start, interval.end, ceiling, floor)
        if found != 0 and side in (0, found):
            result @= _OffscreenRange(found, max(anchor, end))
        else:
            result @= _OffscreenRange(0, anchor)
        return result
    node_ref = root
    while node_ref != 0:
        bounds = _visibility_node_bounds(node_ref)
        if bounds.start >= end:
            result @= _OffscreenRange(side, max(anchor, end))
            return result
        if node_ref < 0:
            escape = timescale_change_archetype().at(-node_ref).leaf_escape
        else:
            escape = timescale_change_archetype().at(node_ref).tree_escape
        if bounds.end <= anchor:
            node_ref = escape
            continue
        lower = target.coordinate.difference(bounds.maximum)
        upper = target.coordinate.difference(bounds.minimum)
        magnitude = max(abs(target.coordinate.whole), bounds.magnitude, abs(lower), abs(upper))
        found = 0
        if -inf < lower <= upper < inf and magnitude < inf:
            slack = 0.01 + source.preempt * 1e-4 + magnitude * 1e-6
            found = _offscreen_side(lower - slack, upper + slack, ceiling, floor)
        if found != 0 and side in (0, found):
            side = found
            node_ref = escape
        elif node_ref < 0:
            result @= _OffscreenRange(side, max(anchor, bounds.start))
            return result
        else:
            node_ref = timescale_change_archetype().at(node_ref).tree_children[0]
    last = timescale_group_archetype().at(source.group).last_ref
    result @= _OffscreenRange(side, max(anchor, min(end, timescale_change_archetype().at(last).event_start)))
    return result


def _mixed_range_end(
    sources: VarArray[VisibilitySource, Dim[4]],
    targets: VarArray[TargetPosition, Dim[4]],
    refs: VarArray[int, Dim[4]],
    low: float,
    high: float,
    anchor: float,
    latest: float,
) -> float:
    side, end = 0, latest
    for i in range(len(sources)):
        # Require all sources to stay above the visible range or all to stay below it.
        # Sources on opposite sides can have visible geometry between them.
        result = _source_range_end(sources[i], targets[i], refs[i], low, high, anchor, end, side)
        if result.side == 0 or result.end <= anchor:
            return anchor
        side, end = result.side, result.end
    return end


def first_visible(
    sources: VarArray[VisibilitySource, Dim[4]],
    low: float,
    high: float,
    earliest: float,
    latest: float,
    *,
    use_index: bool = True,
) -> float:
    """Find an early spawn time by rejecting intervals that cannot be visible.

    Search earlier halves first as we subdivide the remaining intervals.
    Add a small margin so notes spawn before they might become visible.
    """
    if len(sources) == 0 or latest < earliest:
        return inf
    indexed = use_index and _can_use_visibility_indexes(sources, low, high, earliest, latest)
    tree_root = 0
    common_group = 0
    if indexed:
        common_group = sources[0].group
        for source in sources:
            if source.group != common_group:
                common_group = 0
        if common_group > 0:
            tree_root = timescale_group_archetype().at(common_group).tree_root
    targets = VarArray[TargetPosition, Dim[4]].new()
    refs = VarArray[int, Dim[4]].new()
    for source in sources:
        target = locate_target(source.group, source.hit_time)
        targets.append(target)
        refs.append(0 if indexed else target.event_ref)
    anchor = earliest
    while anchor <= latest:
        if indexed:
            for i in range(len(sources)):
                if common_group > 0 and i > 0:
                    refs[i] = refs[0]
                else:
                    refs[i] = locate_time_from(sources[i].group, anchor, refs[i], True)
            if common_group > 0 and refs[0] == 0:
                end = _prefix_range_end(sources, targets, low, high, anchor, latest)
            elif tree_root != 0:
                end = _tree_range_end(tree_root, sources, targets, low, high, anchor, latest)
            else:
                end = _mixed_range_end(sources, targets, refs, low, high, anchor, latest)
            if end > anchor:
                anchor = end
                continue
        pieces = VarArray[_DistanceBoundsPiece, Dim[4]].new()
        piece_end = latest
        for i in range(len(sources)):
            source = sources[i]
            ref = refs[i] if indexed else locate_time_from(source.group, anchor, refs[i])
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
    return first_visible(sources, bounds.start, bounds.end, MIN_START_TIME, latest)


def group_index(group: int | EntityRef) -> int:
    return group.index if isinstance(group, EntityRef) else group
