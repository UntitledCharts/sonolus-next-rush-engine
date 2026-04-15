from __future__ import annotations

from enum import IntEnum
from math import atan, ceil, cos, floor, log, pi, sin
from typing import Protocol, assert_never, cast

from sonolus.script.archetype import EntityRef, get_archetype_by_name
from sonolus.script.debug import static_error
from sonolus.script.globals import level_data, level_memory
from sonolus.script.interval import clamp, lerp, remap, unlerp
from sonolus.script.num import Num
from sonolus.script.quad import Quad, QuadLike, Rect
from sonolus.script.record import Record
from sonolus.script.runtime import (
    aspect_ratio,
    background,
    is_play,
    is_watch,
    runtime_ui,
    safe_area,
    screen,
    set_background,
    time,
)
from sonolus.script.values import swap
from sonolus.script.vec import Vec2

from sekai.lib import archetype_names
from sekai.lib.baseevent import get_event_as, query_event_list
from sekai.lib.ease import EaseType, ease
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import HitboxRange, Options, StageCoverNoteSpeedCompensation, Version
from sekai.lib.timescale import CompositeTime

LANE_T = 47 / 850
LANE_B = 1176 / 850

NOTE_H = 75 / 850 / 2
NOTE_EDGE_W = 0.25
NOTE_SLIM_EDGE_W = 0.125

TARGET_ASPECT_RATIO = 16 / 9

FIELD_T_FACTOR = 0.5 + 1.15875 * (47 / 1176)
FIELD_B_FACTOR = 0.5 - 1.15875 * (803 / 1176)
FIELD_W_FACTOR = (1.15875 * (1420 / 1176)) / TARGET_ASPECT_RATIO / 12

# Value between 0 and 1 where smaller values mean a 'harsher' approach with more acceleration.
APPROACH_SCALE = 1.06**-45

# Value above 1 where we cut off drawing sprites. Doesn't really matter as long as it's high enough,
# such that something like a flick arrow below the judge line isn't obviously suddenly cut off.
DEFAULT_APPROACH_CUTOFF = 5

# Stage width at 0 tilt
STAGE_WIDTH_MID = (APPROACH_SCALE + 1) / 2

# As tilt decreases, the perspective vanishing point (where the width factor reaches 0) recedes
# upward and the stage top is extended toward it. This floors the effective tilt used for that
# extent so it stays finite (instead of diverging) as tilt approaches 0.
STAGE_TILT_VANISH_MIN = 0.2


class FlickDirection(IntEnum):
    UP_OMNI = 0
    UP_LEFT = 1
    UP_RIGHT = 2
    DOWN_OMNI = 3
    DOWN_LEFT = 4
    DOWN_RIGHT = 5


class ZoomVerticalAlign(IntEnum):
    DEFAULT = 0
    CENTER = 1


class AccuracyType(IntEnum):
    NONE = 0
    Fast = 1
    Late = 2
    Flick = 3


class JudgmentType(IntEnum):
    PERFECT = 1
    GREAT = 2
    GOOD = 3
    BAD = 4
    AUTO = -1
    MISS = 0


class ComboType(IntEnum):
    NORMAL = 0
    AP = 1
    GLOW = 2


@level_data
class UIMargin:
    life_bar_x: float
    life_bar_y: float
    score_bar_x: float
    score_bar_y: float
    ui_x: float


@level_data
class Layout:
    field_w: float
    field_h: float
    approach_start: float
    cover_depth: float
    cutoff_depth: float
    flick_speed_threshold: float
    initial_background: Quad
    t: float
    w_scale: float
    h_scale: float
    fixed_w_scale: float
    fixed_h_scale: float


@level_memory
class DynamicLayout:
    t: float
    w_scale: float
    h_scale: float
    x_translate: float
    rotate: float
    stage_tilt: float
    size_zoom: float
    note_h: float
    scaled_note_h: float
    progress_start: float
    progress_cutoff: float
    width_offset: float
    lane_t: float
    lane_b: float
    stage_lane_t: float
    stage_lane_b: float


class CameraInfo(Record):
    lane: float
    size: float
    zoom: float
    zoom_target_lane: float  # lane-space, for the preview timeline marker only
    zoom_target: Vec2  # screen-space zoom target
    zoom_anchor: Vec2  # screen-space anchor (encodes the vertical align)
    rotate: float
    stage_tilt: float


def init_layout():
    if Options.lock_stage_aspect_ratio:
        if aspect_ratio() > TARGET_ASPECT_RATIO:
            field_w = screen().h * TARGET_ASPECT_RATIO
            field_h = screen().h
        else:
            field_w = screen().w
            field_h = screen().w / TARGET_ASPECT_RATIO
    else:
        field_w = screen().w
        field_h = screen().h

    Layout.field_w = field_w
    Layout.field_h = field_h

    Layout.initial_background = background()

    t = Layout.field_h * (0.5 + 1.15875 * (47 / 1176))
    b = Layout.field_h * (0.5 - 1.15875 * (803 / 1176))
    w = Layout.field_w * ((1.15875 * (1420 / 1176)) / TARGET_ASPECT_RATIO / 12)

    Layout.t = t
    Layout.w_scale = w
    Layout.h_scale = b - t

    if aspect_ratio() > TARGET_ASPECT_RATIO:
        field_w = screen().h * TARGET_ASPECT_RATIO
        field_h = screen().h
    else:
        field_w = screen().w
        field_h = screen().w / TARGET_ASPECT_RATIO
    ref_t = field_h * (0.5 + 1.15875 * (47 / 1176))
    ref_b = field_h * (0.5 - 1.15875 * (803 / 1176))
    ref_w = field_w * ((1.15875 * (1420 / 1176)) / TARGET_ASPECT_RATIO / 12)
    Layout.fixed_w_scale = ref_w
    Layout.fixed_h_scale = ref_b - ref_t

    Layout.approach_start = 0.0

    # Fixed approach-curve depths for the cover/spawn and far cutoff boundaries. These are
    # tilt-independent (they pin screen positions); refresh_layout() converts them to the
    # equivalent progress bounds under the current tilt each frame.
    if Options.stage_cover:
        Layout.cover_depth = lerp(APPROACH_SCALE, 1.0, Options.stage_cover)
    else:
        Layout.cover_depth = APPROACH_SCALE
    if Options.hidden:
        Layout.cutoff_depth = lerp(1.0, APPROACH_SCALE, Options.hidden)
    else:
        Layout.cutoff_depth = DEFAULT_APPROACH_CUTOFF

    if Options.stage_cover and Options.stage_cover_scroll_speed_compensation != StageCoverNoteSpeedCompensation.OFF:
        target_travel = lerp(APPROACH_SCALE, 1.0, Options.stage_cover)
        candidate = inverse_approach_untilted(target_travel)
        Layout.approach_start = clamp(candidate, 0, 0.99)

    refresh_layout()

    Layout.flick_speed_threshold = 2 * DynamicLayout.w_scale


class CameraChangeLike(Protocol):
    time: float
    lane: float
    size: float
    zoom: float
    zoom_target_lane: float
    zoom_target_y: float
    zoom_vertical_align: ZoomVerticalAlign
    rotate: float
    stage_tilt: float
    ease: EaseType
    next_ref: EntityRef
    prev_ref: EntityRef

    @classmethod
    def at(cls, index: int) -> CameraChangeLike: ...

    @property
    def index(self) -> int: ...


class InitializationLike(Protocol):
    first_camera_ref: EntityRef

    @classmethod
    def at(cls, index: int) -> InitializationLike: ...


def _camera_change_archetype() -> type[CameraChangeLike]:
    return cast(type[CameraChangeLike], get_archetype_by_name(archetype_names.CAMERA_CHANGE))


def _initialization_archetype() -> type[InitializationLike]:
    return cast(type[InitializationLike], get_archetype_by_name(archetype_names.INITIALIZATION))


def get_camera_info(target_time: float | None = None, left_limit: bool = False) -> CameraInfo:
    result = +CameraInfo
    first_camera_ref = _initialization_archetype().at(0).first_camera_ref
    if first_camera_ref.index <= 0:
        result @= CameraInfo(
            lane=0.0,
            size=6.0,
            zoom=1.0,
            zoom_target_lane=0.0,
            zoom_target=Vec2(0.0, 0.0),
            zoom_anchor=Vec2(0.0, 0.0),
            rotate=0.0,
            stage_tilt=1.0,
        )
        return result
    t = time() if target_time is None else target_time
    camera_a_ref, camera_b_ref = query_event_list(first_camera_ref, t, lambda e: e.time)
    camera_archetype = _camera_change_archetype()
    if left_limit and camera_a_ref.index > 0:
        camera_curr = get_event_as(camera_a_ref, camera_archetype)
        if camera_curr.time == t:
            camera_probe_ref = +camera_curr.prev_ref
            while camera_probe_ref.index > 0:
                if get_event_as(camera_probe_ref, camera_archetype).time != t:
                    break
                camera_a_ref.index = camera_probe_ref.index
                camera_probe_ref.index = get_event_as(camera_probe_ref, camera_archetype).prev_ref.index
            camera_b_ref.index = camera_a_ref.index
            camera_a_ref.index = camera_probe_ref.index
    if camera_a_ref.index > 0:
        camera_a = get_event_as(camera_a_ref, camera_archetype)
        if camera_b_ref.index > 0:
            camera_b = get_event_as(camera_b_ref, camera_archetype)
            if camera_b.time > camera_a.time:
                p = ease(camera_a.ease, unlerp(camera_a.time, camera_b.time, t))
                ta = camera_zoom_target_at(
                    camera_a.lane, camera_a.size, camera_a.zoom_target_lane, camera_a.zoom_target_y, camera_a.stage_tilt
                )
                tb = camera_zoom_target_at(
                    camera_b.lane, camera_b.size, camera_b.zoom_target_lane, camera_b.zoom_target_y, camera_b.stage_tilt
                )
                aa = camera_zoom_anchor(camera_a.zoom_vertical_align)
                ab = camera_zoom_anchor(camera_b.zoom_vertical_align)
                result @= CameraInfo(
                    lane=lerp(camera_a.lane, camera_b.lane, p),
                    size=lerp(camera_a.size, camera_b.size, p),
                    zoom=lerp(camera_a.zoom, camera_b.zoom, p),
                    zoom_target_lane=lerp(camera_a.zoom_target_lane, camera_b.zoom_target_lane, p),
                    zoom_target=Vec2(lerp(ta.x, tb.x, p), lerp(ta.y, tb.y, p)),
                    zoom_anchor=Vec2(lerp(aa.x, ab.x, p), lerp(aa.y, ab.y, p)),
                    rotate=lerp(camera_a.rotate, camera_b.rotate, p),
                    stage_tilt=lerp(camera_a.stage_tilt, camera_b.stage_tilt, p),
                )
                return result
        result @= CameraInfo(
            lane=camera_a.lane,
            size=camera_a.size,
            zoom=camera_a.zoom,
            zoom_target_lane=camera_a.zoom_target_lane,
            zoom_target=camera_zoom_target_at(
                camera_a.lane, camera_a.size, camera_a.zoom_target_lane, camera_a.zoom_target_y, camera_a.stage_tilt
            ),
            zoom_anchor=camera_zoom_anchor(camera_a.zoom_vertical_align),
            rotate=camera_a.rotate,
            stage_tilt=camera_a.stage_tilt,
        )
        return result
    if camera_b_ref.index > 0:
        camera_b = get_event_as(camera_b_ref, camera_archetype)
        result @= CameraInfo(
            lane=camera_b.lane,
            size=camera_b.size,
            zoom=camera_b.zoom,
            zoom_target_lane=camera_b.zoom_target_lane,
            zoom_target=camera_zoom_target_at(
                camera_b.lane, camera_b.size, camera_b.zoom_target_lane, camera_b.zoom_target_y, camera_b.stage_tilt
            ),
            zoom_anchor=camera_zoom_anchor(camera_b.zoom_vertical_align),
            rotate=camera_b.rotate,
            stage_tilt=camera_b.stage_tilt,
        )
        return result
    result @= CameraInfo(
        lane=0.0,
        size=6.0,
        zoom=1.0,
        zoom_target_lane=0.0,
        zoom_target=Vec2(0.0, 0.0),
        zoom_anchor=Vec2(0.0, 0.0),
        rotate=0.0,
        stage_tilt=1.0,
    )
    return result


def get_next_camera_event_time(t: float) -> float:
    result = 1e8
    first_camera_ref = _initialization_archetype().at(0).first_camera_ref
    if first_camera_ref.index > 0:
        _, b_ref = query_event_list(first_camera_ref, t, lambda e: e.time)
        if b_ref.index > 0:
            result = min(result, get_event_as(b_ref, _camera_change_archetype()).time)
    return result


def refresh_layout():
    camera = +CameraInfo
    if is_play() or is_watch():
        camera @= get_camera_info()
    else:
        camera @= CameraInfo(
            lane=0.0,
            size=6.0,
            zoom=1.0,
            zoom_target_lane=0.0,
            zoom_target=Vec2(0.0, 0.0),
            zoom_anchor=Vec2(0.0, 0.0),
            rotate=0.0,
            stage_tilt=1.0,
        )

    base = base_layout_transform(camera)
    DynamicLayout.t = base.t
    DynamicLayout.w_scale = base.w_scale
    DynamicLayout.h_scale = base.h_scale
    DynamicLayout.x_translate = base.x_translate
    DynamicLayout.rotate = base.rotate
    DynamicLayout.stage_tilt = base.stage_tilt
    DynamicLayout.size_zoom = base.size_zoom
    tilt = current_stage_tilt()

    DynamicLayout.width_offset = (1 - tilt) * STAGE_WIDTH_MID
    vanish_tilt = max(tilt, STAGE_TILT_VANISH_MIN)
    vanish_ext = (1 - vanish_tilt) * STAGE_WIDTH_MID / vanish_tilt
    DynamicLayout.lane_t = LANE_T - vanish_ext
    DynamicLayout.lane_b = LANE_B + vanish_ext
    if LevelConfig.dynamic_stages:
        DynamicLayout.stage_lane_t = LANE_T - vanish_ext * 0.9
        DynamicLayout.stage_lane_b = LANE_B + vanish_ext + 3
    else:
        DynamicLayout.stage_lane_t = LANE_T - vanish_ext
        DynamicLayout.stage_lane_b = LANE_B + vanish_ext

    base_note_h = NOTE_H * (0.6 * base.size_zoom + 0.4)
    flat_note_h = STAGE_WIDTH_MID * DynamicLayout.w_scale / (2 * abs(DynamicLayout.h_scale))
    DynamicLayout.note_h = lerp(flat_note_h, base_note_h, tilt)

    if is_play() or is_watch():
        apply_camera_zoom(base, camera.zoom, camera.zoom_target, camera.zoom_anchor, camera.rotate)

    DynamicLayout.scaled_note_h = DynamicLayout.note_h * DynamicLayout.h_scale

    if Options.stage_cover:
        DynamicLayout.progress_start = inverse_approach_tilt(Layout.cover_depth)
    else:
        DynamicLayout.progress_start = inverse_approach_tilt(Layout.cover_depth - vanish_ext)
    DynamicLayout.progress_cutoff = inverse_approach_tilt(Layout.cutoff_depth)


def camera_zoom_target_at(lane: float, size: float, target_lane: float, target_y: float, tilt: float) -> Vec2:
    size_zoom = 6.0 / size
    w = Layout.field_w * FIELD_W_FACTOR * size_zoom
    t_top = Layout.field_h * FIELD_T_FACTOR
    b = Layout.field_h * FIELD_B_FACTOR
    travel = approach_at_tilt(1 - target_y, tilt)
    target_total_lane = lane + target_lane
    return Vec2(target_total_lane * width_factor_at_tilt(travel, tilt) * w - lane * w, travel * (b - t_top) + t_top)


def camera_zoom_anchor(align: ZoomVerticalAlign) -> Vec2:
    if align == ZoomVerticalAlign.CENTER:
        anchor_y = 0.0
    else:
        anchor_y = Layout.field_h * FIELD_B_FACTOR
    return Vec2(0.0, anchor_y)


def apply_camera_zoom(transform: LayoutTransform, zoom: float, target: Vec2, anchor: Vec2, rotate: float = 0.0):
    zoomed = zoomed_layout_transform(transform, zoom, target, anchor, rotate)
    DynamicLayout.t = zoomed.t
    DynamicLayout.w_scale = zoomed.w_scale
    DynamicLayout.h_scale = zoomed.h_scale
    DynamicLayout.x_translate = zoomed.x_translate
    DynamicLayout.rotate = zoomed.rotate
    bg = Layout.initial_background
    rot = -rotate
    set_background(
        Quad(
            bl=Vec2(zoom * (bg.bl.x - target.x) + anchor.x, zoom * (bg.bl.y - target.y) + anchor.y).rotate(rot),
            br=Vec2(zoom * (bg.br.x - target.x) + anchor.x, zoom * (bg.br.y - target.y) + anchor.y).rotate(rot),
            tl=Vec2(zoom * (bg.tl.x - target.x) + anchor.x, zoom * (bg.tl.y - target.y) + anchor.y).rotate(rot),
            tr=Vec2(zoom * (bg.tr.x - target.x) + anchor.x, zoom * (bg.tr.y - target.y) + anchor.y).rotate(rot),
        )
    )


def current_stage_tilt() -> float:
    if is_play() or is_watch():
        return DynamicLayout.stage_tilt
    return 1.0


def approach_curve_base(x: float) -> float:
    if Options.alternative_approach_curve:
        d_0 = 1 / APPROACH_SCALE
        d_1 = 2.5
        v_1 = (d_0 - d_1) / d_1**2
        d = 1 / lerp(d_0, d_1, x) if x < 1 else 1 / d_1 + v_1 * (x - 1)
        return remap(1 / d_0, 1 / d_1, APPROACH_SCALE, 1, d)
    return APPROACH_SCALE ** (1 - x)


def approach_at_tilt(progress: float, tilt: float) -> float:
    x = lerp(Layout.approach_start, 1.0, progress)
    base = approach_curve_base(x)
    if tilt >= 1.0:
        return base
    linear = lerp(APPROACH_SCALE, 1.0, x)
    raw = lerp(linear, base, tilt)
    natural_spawn = lerp(lerp(APPROACH_SCALE, 1.0, Layout.approach_start), Layout.cover_depth, tilt)
    return remap(natural_spawn, 1.0, min(natural_spawn, Layout.cover_depth), 1.0, raw)


def approach(progress: float) -> float:
    return approach_at_tilt(progress, current_stage_tilt())


def inverse_approach_untilted(approach_value: float) -> float:
    if Options.alternative_approach_curve:
        d_0 = 1 / APPROACH_SCALE
        d_1 = 2.5
        v_1 = (d_0 - d_1) / d_1**2
        d = remap(APPROACH_SCALE, 1, 1 / d_0, 1 / d_1, approach_value)
        if d <= 1 / d_1:
            raw = (1 / d - d_0) / (d_1 - d_0)
        else:
            raw = 1 + (d - 1 / d_1) / v_1
    else:
        raw = 1 - log(approach_value) / log(APPROACH_SCALE)
    return unlerp(Layout.approach_start, 1.0, raw)


def inverse_approach_tilt(approach_value: float) -> float:
    tilt = current_stage_tilt()
    if tilt >= 1.0:
        return inverse_approach_untilted(approach_value)
    lo = -4.0
    hi = 4.0
    for _ in range(20):
        mid = (lo + hi) / 2
        too_low = approach_at_tilt(mid, tilt) < approach_value
        lo = mid if too_low else lo
        hi = hi if too_low else mid
    return (lo + hi) / 2


def progress_to(
    to_time: float | CompositeTime,
    now: float | CompositeTime,
    force_speed: float = 0,
) -> float:
    p = preempt_time(force_speed)
    match (to_time, now):
        case (CompositeTime(), CompositeTime()):
            return ((now.base - to_time.base) + now.delta - to_time.delta + p) / p
        case (Num(), Num()):
            return unlerp(to_time - p, to_time, now)
        case _:
            static_error("Unexpected types for progress_to")


def preempt_time(force_speed: float = 0) -> float:
    if force_speed > 0:
        return lerp(0.35, 4, unlerp(12, 1, force_speed) ** 1.31)
    raw = lerp(0.35, 4, unlerp(12, 1, Options.note_speed) ** 1.31)
    if Options.stage_cover_scroll_speed_compensation == StageCoverNoteSpeedCompensation.FIXED_ONLY:
        return raw * (1 - Layout.approach_start)
    return raw


def get_alpha(target_time: float, now: float | None = None) -> float:
    return 1.0


def width_factor_at_tilt(depth: float, tilt: float) -> float:
    return tilt * depth + (1 - tilt) * STAGE_WIDTH_MID


def tilt_width_factor(depth: float) -> float:
    return current_stage_tilt() * depth + DynamicLayout.width_offset


def tilt_depth(line_y: float, travel: float) -> float:
    return travel + (line_y - 1.0) * lerp(1.0, travel, current_stage_tilt())


def tilt_widened_edge(bottom_edge: float, top_edge: float) -> float:
    return lerp(bottom_edge, top_edge, current_stage_tilt())


def transform_vec(v: Vec2) -> Vec2:
    return Vec2(
        v.x * DynamicLayout.w_scale + DynamicLayout.x_translate,
        v.y * DynamicLayout.h_scale + DynamicLayout.t,
    ).rotate(-DynamicLayout.rotate)


def transform_static_vec(v: Vec2) -> Vec2:
    return Vec2(
        v.x * Layout.w_scale,
        v.y * Layout.h_scale + Layout.t,
    )


def transform_fixed_vec(v: Vec2) -> Vec2:
    return Vec2(
        v.x * Layout.fixed_w_scale,
        v.y * Layout.fixed_h_scale + Layout.t,
    )


def transform_quad(q: QuadLike) -> Quad:
    return Quad(
        bl=transform_vec(q.bl),
        br=transform_vec(q.br),
        tl=transform_vec(q.tl),
        tr=transform_vec(q.tr),
    )


def transform_static_quad(q: QuadLike) -> Quad:
    return Quad(
        bl=transform_static_vec(q.bl),
        br=transform_static_vec(q.br),
        tl=transform_static_vec(q.tl),
        tr=transform_static_vec(q.tr),
    )


def transform_fixed_quad(q: QuadLike) -> Quad:
    return Quad(
        bl=transform_fixed_vec(q.bl),
        br=transform_fixed_vec(q.br),
        tl=transform_fixed_vec(q.tl),
        tr=transform_fixed_vec(q.tr),
    )


def transformed_vec_at(lane: float, travel: float = 1.0) -> Vec2:
    return transform_vec(Vec2(lane * tilt_width_factor(travel), travel))


def pre_rotation_vec_at(lane: float, travel: float = 1.0) -> Vec2:
    return Vec2(
        lane * tilt_width_factor(travel) * DynamicLayout.w_scale + DynamicLayout.x_translate,
        travel * DynamicLayout.h_scale + DynamicLayout.t,
    )


def touch_to_lane(pos: Vec2) -> float:
    unrotated = pos.rotate(DynamicLayout.rotate)
    y_raw = (unrotated.y - DynamicLayout.t) / DynamicLayout.h_scale
    x_raw = (unrotated.x - DynamicLayout.x_translate) / DynamicLayout.w_scale
    width = tilt_width_factor(y_raw)
    if -1e-6 < width < 1e-6:
        width = 1e-6 if width >= 0 else -1e-6
    return x_raw / width


def perspective_vec(x: float, y: float, travel: float = 1.0) -> Vec2:
    return transform_vec(Vec2(x * tilt_width_factor(y * travel), y * travel))


def perspective_rect(l, r, t, b, travel=1.0, p=1.0):
    depth_b = tilt_depth(b, travel)
    depth_t = tilt_depth(t, travel)
    w_ref = tilt_width_factor(travel)
    wb = lerp(w_ref, tilt_width_factor(depth_b), p)
    wt = lerp(w_ref, tilt_width_factor(depth_t), p)
    return transform_quad(
        Quad(
            bl=Vec2(l * wb, depth_b),
            br=Vec2(r * wb, depth_b),
            tl=Vec2(l * wt, depth_t),
            tr=Vec2(r * wt, depth_t),
        )
    )


def perspective_static_rect(l: float, r: float, t: float, b: float, travel: float = 1.0) -> Quad:
    return transform_static_quad(
        Quad(
            bl=Vec2(l * b * travel, b * travel),
            br=Vec2(r * b * travel, b * travel),
            tl=Vec2(l * t * travel, t * travel),
            tr=Vec2(r * t * travel, t * travel),
        )
    )


def get_perspective_y(target_y: float, travel: float = 1.0) -> float:
    if DynamicLayout.h_scale == 0 or travel == 0:
        return 0.0

    rot = DynamicLayout.rotate
    edge_reach = screen().r * abs(sin(rot))
    pre_y = target_y * cos(rot) + (edge_reach if target_y >= 0 else -edge_reach)
    return (pre_y - DynamicLayout.t) / (DynamicLayout.h_scale * travel)


def layout_sekai_stage() -> Quad:
    w = (2048 / 1420) * 12 / 2
    h = 1176 / 850
    rect = Rect(l=-w, r=w, t=LANE_T, b=LANE_T + h)
    return transform_quad(rect)


def layout_sekai_stage_t() -> Quad:
    scale_factor = 2048 / 1440
    w = (2048 / 1420) * 12 / 2

    h = 1080 * scale_factor / 850

    original_h_pixel = 1176
    new_h_pixel = 1080 * scale_factor

    new_lane_t = (47 - (new_h_pixel - original_h_pixel) / 2) / 850
    rect = Rect(l=-w, r=w, t=new_lane_t, b=new_lane_t + h)
    return transform_quad(rect)


def layout_stage_lane_by_edges(l: float, r: float, y_offset: float = 0.0) -> Quad:
    return perspective_rect(
        l=l, r=r, t=DynamicLayout.stage_lane_t, b=DynamicLayout.stage_lane_b, travel=approach(1 - y_offset)
    )


def layout_particle_lane(lane: float, size: float, y_offset: float = 0.0) -> Quad:
    return perspective_rect(
        l=lane - (size + 0.01),
        r=lane + (size + 0.01),
        t=DynamicLayout.lane_t,
        b=DynamicLayout.lane_b,
        travel=approach(1 - y_offset),
    )


def layout_lane_fever(lane: float, size: float, y_offset: float = 0.0) -> Quad:
    return layout_lane_by_edges_fever(lane - size, lane + size, y_offset=y_offset)


def layout_lane_by_edges_fever(l: float, r: float, y_offset: float = 0.0) -> Quad:
    return perspective_rect(l=l, r=r, t=get_perspective_y(1), b=get_perspective_y(-1), travel=approach(1 - y_offset))


def layout_stage_cover(l: float = -6, r: float = 6) -> Quad:
    b = lerp(APPROACH_SCALE, 1.0, Options.stage_cover)
    return perspective_rect(
        l=l,
        r=r,
        t=max(DynamicLayout.lane_t, get_perspective_y(1)),
        b=b,
    )


def layout_stage_cover_and_line(l: float = -6, r: float = 6) -> tuple[Quad, Quad]:
    b = lerp(APPROACH_SCALE, 1.0, Options.stage_cover)
    cover_b = b + 0.002
    return perspective_rect(
        l=l,
        r=r,
        t=max(DynamicLayout.lane_t, get_perspective_y(1)),
        b=cover_b,
    ), perspective_rect(
        l=l,
        r=r,
        t=cover_b,
        b=b,
    )


def layout_full_width_stage_cover() -> Quad:
    pre_b = lerp(APPROACH_SCALE, 1.0, Options.stage_cover) * DynamicLayout.h_scale + DynamicLayout.t
    big = 20.0
    rot = -DynamicLayout.rotate
    return Quad(
        bl=Vec2(-big, pre_b).rotate(rot),
        br=Vec2(big, pre_b).rotate(rot),
        tl=Vec2(-big, big).rotate(rot),
        tr=Vec2(big, big).rotate(rot),
    )


def layout_hidden_cover(l: float = -6, r: float = 6) -> Quad:
    b = 1 - DynamicLayout.note_h
    t = min(b, max(lerp(1.0, APPROACH_SCALE, Options.hidden), lerp(APPROACH_SCALE, 1.0, Options.stage_cover)))
    return perspective_rect(
        l=l,
        r=r,
        t=t,
        b=b,
    )


def layout_custom_tag() -> Quad:
    h = -0.0264 / aspect_ratio() ** 2 + 0.0733
    w = h * 4.465
    x = (8.711111 * aspect_ratio() / 2.045 / 5) + (0.5936 / aspect_ratio() ** 2 - 0.4339)
    y = (-4.9 / 5) + (-0.0885 / aspect_ratio() ** 2 + 0.1498)
    return Quad(
        bl=Vec2(x - w, y - h),
        br=Vec2(x + w, y - h),
        tl=Vec2(x - w, y + h),
        tr=Vec2(x + w, y + h),
    )


def init_ui_margin():
    has_side_notch = (screen().l != safe_area().l) or (screen().r != safe_area().r)

    match LevelConfig.ui_version:
        case Version.v3:
            UIMargin.life_bar_x = 0.28 if has_side_notch else 0.05
            UIMargin.score_bar_x = 0.3 if has_side_notch else 0.1
            UIMargin.life_bar_y = 0.887
            UIMargin.score_bar_y = 0.865
            UIMargin.ui_x = 0.23 if has_side_notch else 0.0
        case Version.v1:
            UIMargin.life_bar_x = 0.28 if has_side_notch else 0.0
            UIMargin.score_bar_x = 0.3 if has_side_notch else 0.05
            UIMargin.life_bar_y = 0.84
            UIMargin.score_bar_y = 0.83
            UIMargin.ui_x = 0.28 if has_side_notch else 0.0


def layout_life_bar() -> Quad:
    ui = runtime_ui()

    scale_ratio = min(1, aspect_ratio() / (16 / 9))

    h = 0
    w = 0
    base_h_unscaled = 0
    match LevelConfig.ui_version:
        case Version.v3:
            base_h_unscaled = 0.196 * ui.secondary_metric_config.scale
            h = base_h_unscaled * scale_ratio
            w = h * 4.22
        case Version.v1:
            base_h_unscaled = 0.23 * ui.secondary_metric_config.scale
            h = base_h_unscaled * scale_ratio
            w = h * 4.22

    y_shift = (base_h_unscaled - h) / 2

    screen_center = Vec2(x=screen().r - UIMargin.life_bar_x * scale_ratio - (w / 2), y=UIMargin.life_bar_y + y_shift)
    return Quad(
        bl=Vec2(screen_center.x - w / 2, screen_center.y - h / 2),
        br=Vec2(screen_center.x + w / 2, screen_center.y - h / 2),
        tl=Vec2(screen_center.x - w / 2, screen_center.y + h / 2),
        tr=Vec2(screen_center.x + w / 2, screen_center.y + h / 2),
    )


def layout_life_gauge(life, edge=False) -> Quad:
    ui = runtime_ui()

    scale_ratio = min(1, aspect_ratio() / (16 / 9))

    bar_h_unscaled = (
        0.196 * ui.secondary_metric_config.scale
        if LevelConfig.ui_version == Version.v3
        else 0.23 * ui.secondary_metric_config.scale
    )
    bar_h_current = bar_h_unscaled * scale_ratio
    y_shift = (bar_h_unscaled - bar_h_current) / 2

    y_offset = 0
    margin_offset = 0
    h = 0
    w = 0
    match LevelConfig.ui_version:
        case Version.v3:
            margin_offset = 0.118
            y_offset = -0.007
            h = 0.033 * ui.secondary_metric_config.scale * scale_ratio
            w = h * 15.3
        case Version.v1:
            margin_offset = 0.02
            y_offset = 0.01
            h = 0.023 * ui.secondary_metric_config.scale * scale_ratio
            w = h * 23

    bar_base_w = 0.827
    final_scale = ui.secondary_metric_config.scale * scale_ratio
    current_bar_w = bar_base_w * final_scale

    bar_center_x = screen().r - UIMargin.life_bar_x * scale_ratio - (current_bar_w / 2)
    number_center_x = bar_center_x + (margin_offset * final_scale)

    center_y = UIMargin.life_bar_y + (y_offset * final_scale) + y_shift

    screen_center = Vec2(x=number_center_x - (current_bar_w / 2), y=center_y)

    life = clamp((life / 1000), 0, 1)
    if not edge:
        return Quad(
            bl=Vec2(screen_center.x, screen_center.y - h / 2),
            br=Vec2(screen_center.x + w * life, screen_center.y - h / 2),
            tl=Vec2(screen_center.x, screen_center.y + h / 2),
            tr=Vec2(screen_center.x + w * life, screen_center.y + h / 2),
        )
    else:
        active_ratio = 0.9625 if LevelConfig.ui_version == Version.v3 else 0.915

        travel_distance = w * active_ratio

        shift_amount = travel_distance * (1 - life)

        base_x = screen_center.x

        return Quad(
            bl=Vec2(base_x - shift_amount, screen_center.y - h / 2),
            br=Vec2(base_x + w - shift_amount, screen_center.y - h / 2),
            tl=Vec2(base_x - shift_amount, screen_center.y + h / 2),
            tr=Vec2(base_x + w - shift_amount, screen_center.y + h / 2),
        )


def layout_score_bar() -> Quad:
    ui = runtime_ui()

    scale_ratio = min(1, aspect_ratio() / (16 / 9))

    base_h_unscaled = 0
    h = 0
    w = 0
    match LevelConfig.ui_version:
        case Version.v3:
            base_h_unscaled = 0.27 * ui.primary_metric_config.scale
            h = base_h_unscaled * scale_ratio
            w = h * 4.6
        case Version.v1:
            base_h_unscaled = 0.32 * ui.primary_metric_config.scale
            h = base_h_unscaled * scale_ratio
            w = h * 4.6

    y_shift = (base_h_unscaled - h) / 2

    screen_center = Vec2(x=screen().l + UIMargin.score_bar_x * scale_ratio + (w / 2), y=UIMargin.score_bar_y + y_shift)
    return Quad(
        bl=Vec2(screen_center.x - w / 2, screen_center.y - h / 2),
        br=Vec2(screen_center.x + w / 2, screen_center.y - h / 2),
        tl=Vec2(screen_center.x - w / 2, screen_center.y + h / 2),
        tr=Vec2(screen_center.x + w / 2, screen_center.y + h / 2),
    )


class ScoreGaugeType(IntEnum):
    NORMAL = 0
    MASK = 1


def layout_score_gauge(gauge=0.0, score_type: ScoreGaugeType = ScoreGaugeType.NORMAL) -> Quad:
    ui = runtime_ui()

    scale_ratio = min(1, aspect_ratio() / (16 / 9))

    bar_h_unscaled = (
        0.27 * ui.primary_metric_config.scale
        if LevelConfig.ui_version == Version.v3
        else 0.32 * ui.primary_metric_config.scale
    )
    bar_h_current = bar_h_unscaled * scale_ratio
    y_shift = (bar_h_unscaled - bar_h_current) / 2

    # c = 0-0.44 b = 0.44-0.6 a= 0.6-0.75 s=0.75-0.9

    margin_offset = 0
    y_offset = 0
    h = 0
    w = 0
    match LevelConfig.ui_version:
        case Version.v3:
            margin_offset = 0.04
            y_offset = 0.008
            h = max(
                (0.049 * ui.primary_metric_config.scale * scale_ratio),
                1e-3,
            )
            w = max(
                (h * 20 * ((1 - gauge) if score_type == ScoreGaugeType.MASK else 1)),
                1e-3,
            )
        case Version.v1:
            margin_offset = -0.155
            y_offset = 0.021
            h = max(
                (0.062 * ui.primary_metric_config.scale * scale_ratio),
                1e-3,
            )
            w = max(
                (h * 18.8 * ((1 - gauge) if score_type == ScoreGaugeType.MASK else 1)),
                1e-3,
            )

    bar_base_w = 0.27 * 4.6
    final_scale = ui.primary_metric_config.scale * scale_ratio
    current_bar_w = bar_base_w * final_scale
    bar_center_x = screen().l + UIMargin.score_bar_x * scale_ratio + (current_bar_w / 2)
    number_center_x = bar_center_x - (margin_offset * final_scale)

    center_y = UIMargin.score_bar_y + (y_offset * final_scale) + y_shift

    screen_center = Vec2(x=number_center_x + (current_bar_w / 2), y=center_y)

    return Quad(
        bl=Vec2(screen_center.x - w, screen_center.y - h / 2),
        br=Vec2(screen_center.x, screen_center.y - h / 2),
        tl=Vec2(screen_center.x - w, screen_center.y + h / 2),
        tr=Vec2(screen_center.x, screen_center.y + h / 2),
    )


def layout_score_rank() -> Quad:
    ui = runtime_ui()

    scale_ratio = min(1, aspect_ratio() / (16 / 9))

    bar_h_unscaled = (
        0.27 * ui.primary_metric_config.scale
        if LevelConfig.ui_version == Version.v3
        else 0.32 * ui.primary_metric_config.scale
    )
    bar_h_current = bar_h_unscaled * scale_ratio
    y_shift = (bar_h_unscaled - bar_h_current) / 2

    y_offset = 0.015
    margin_offset = 1.138
    h = 0
    w = 0
    match LevelConfig.ui_version:
        case Version.v3:
            margin_offset = 1.138
            y_offset = 0.015
            h = 0.29 * ui.primary_metric_config.scale * scale_ratio
            w = h * 0.772
        case Version.v1:
            margin_offset = 1.102
            y_offset = 0.002
            h = 0.17 * ui.primary_metric_config.scale * scale_ratio
            w = h * 0.882

    bar_base_w = 0.27 * 4.6
    final_scale = ui.primary_metric_config.scale * scale_ratio
    current_bar_w = bar_base_w * final_scale

    bar_center_x = screen().l + UIMargin.score_bar_x * scale_ratio + (current_bar_w / 2)
    number_center_x = bar_center_x - (margin_offset * final_scale)

    center_y = UIMargin.score_bar_y + (y_offset * final_scale) + y_shift

    screen_center = Vec2(x=number_center_x + (current_bar_w / 2), y=center_y)

    return Quad(
        bl=Vec2(screen_center.x - w / 2, screen_center.y - h / 2),
        br=Vec2(screen_center.x + w / 2, screen_center.y - h / 2),
        tl=Vec2(screen_center.x - w / 2, screen_center.y + h / 2),
        tr=Vec2(screen_center.x + w / 2, screen_center.y + h / 2),
    )


def layout_score_rank_text() -> Quad:
    ui = runtime_ui()

    scale_ratio = min(1, aspect_ratio() / (16 / 9))

    bar_h_unscaled = (
        0.27 * ui.primary_metric_config.scale
        if LevelConfig.ui_version == Version.v3
        else 0.32 * ui.primary_metric_config.scale
    )
    bar_h_current = bar_h_unscaled * scale_ratio
    y_shift = (bar_h_unscaled - bar_h_current) / 2

    h = 0.02 * ui.primary_metric_config.scale * scale_ratio
    w = h * 7.5

    margin_offset = 1.138
    bar_base_w = 0.27 * 4.6
    final_scale = ui.primary_metric_config.scale * scale_ratio
    current_bar_w = bar_base_w * final_scale

    bar_center_x = screen().l + UIMargin.score_bar_x * scale_ratio + (current_bar_w / 2)
    number_center_x = bar_center_x - (margin_offset * final_scale)

    y_offset = -0.1
    center_y = UIMargin.score_bar_y + (y_offset * final_scale) + y_shift

    screen_center = Vec2(x=number_center_x + (current_bar_w / 2), y=center_y)

    return Quad(
        bl=Vec2(screen_center.x - w / 2, screen_center.y - h / 2),
        br=Vec2(screen_center.x + w / 2, screen_center.y - h / 2),
        tl=Vec2(screen_center.x - w / 2, screen_center.y + h / 2),
        tr=Vec2(screen_center.x + w / 2, screen_center.y + h / 2),
    )


def layout_background_cover() -> Quad:
    return Quad(
        bl=screen().bl,
        br=screen().br,
        tl=screen().tl,
        tr=screen().tr,
    )


def layout_fallback_judge_line() -> Quad:
    nh = DynamicLayout.note_h
    return perspective_rect(l=-6, r=6, t=1 - nh, b=1 + nh)


def layout_note_body_by_edges(l: float, r: float, h: float, travel: float):
    return perspective_rect(l=l, r=r, t=1 - h, b=1 + h, travel=travel, p=Options.note_perspective)


def layout_note_body_slices_by_edges(
    l: float, r: float, h: float, edge_w: float, travel: float
) -> tuple[Quad, Quad, Quad]:
    m = (l + r) / 2
    if r < l:
        # Make the note 0 width; shouldn't normally happen, but in case, we want to handle it gracefully
        l = r = m
    ml = min(l + edge_w, m)
    mr = max(r - edge_w, m)
    return (
        layout_note_body_by_edges(l=l, r=ml, h=h, travel=travel),
        layout_note_body_by_edges(l=ml, r=mr, h=h, travel=travel),
        layout_note_body_by_edges(l=mr, r=r, h=h, travel=travel),
    )


def layout_regular_note_body(lane: float, size: float, travel: float) -> tuple[Quad, Quad, Quad]:
    return layout_note_body_slices_by_edges(
        l=lane - size + Options.note_margin,
        r=lane + size - Options.note_margin,
        h=DynamicLayout.note_h,
        edge_w=NOTE_EDGE_W,
        travel=travel,
    )


def layout_regular_note_body_fallback(lane: float, size: float, travel: float) -> Quad:
    return layout_note_body_by_edges(
        l=lane - size + Options.note_margin,
        r=lane + size - Options.note_margin,
        h=DynamicLayout.note_h,
        travel=travel,
    )


def layout_slim_note_body(lane: float, size: float, travel: float) -> tuple[Quad, Quad, Quad]:
    return layout_note_body_slices_by_edges(
        l=lane - size + Options.note_margin,
        r=lane + size - Options.note_margin,
        h=DynamicLayout.note_h,  # Height is handled by the sprite rather than being changed here
        edge_w=NOTE_SLIM_EDGE_W,
        travel=travel,
    )


def layout_slim_note_body_fallback(lane: float, size: float, travel: float) -> Quad:
    return layout_note_body_by_edges(
        l=lane - size + Options.note_margin,
        r=lane + size - Options.note_margin,
        h=DynamicLayout.note_h / 2,  # For fallback, we need to halve the height manually engine-side
        travel=travel,
    )


def layout_tick(lane: float, travel: float) -> Quad:
    center = transformed_vec_at(lane, travel)
    h = -DynamicLayout.scaled_note_h * tilt_width_factor(travel)
    rot = -DynamicLayout.rotate
    dx = Vec2(h, 0).rotate(rot)
    dy = Vec2(0, h).rotate(rot)
    return Quad(
        bl=center - dx - dy,
        tl=center - dx + dy,
        tr=center + dx + dy,
        br=center + dx - dy,
    )


def layout_flick_arrow(
    lane: float, size: float, direction: FlickDirection, travel: float, animation_progress: float
) -> Quad:
    match direction:
        case FlickDirection.UP_OMNI:
            is_down = False
            reverse = False
            animation_top_x_offset = 0
        case FlickDirection.DOWN_OMNI:
            is_down = True
            reverse = False
            animation_top_x_offset = 0
        case FlickDirection.UP_LEFT:
            is_down = False
            reverse = False
            animation_top_x_offset = -1
        case FlickDirection.UP_RIGHT:
            is_down = False
            reverse = True
            animation_top_x_offset = 1
        case FlickDirection.DOWN_LEFT:
            is_down = True
            reverse = False
            animation_top_x_offset = 1
        case FlickDirection.DOWN_RIGHT:
            is_down = True
            reverse = True
            animation_top_x_offset = -1
        case _:
            assert_never(direction)
    w = clamp(size, 0, 3) / 2
    base_bl = transformed_vec_at(lane - w, travel)
    base_br = transformed_vec_at(lane + w, travel)
    up = (base_br - base_bl).rotate(pi / 2)
    base_tl = base_bl + up
    base_tr = base_br + up
    offset_scale = animation_progress if not is_down else 1 - animation_progress
    offset = (
        Vec2(animation_top_x_offset * DynamicLayout.w_scale, 2 * DynamicLayout.w_scale).rotate(-DynamicLayout.rotate)
        * offset_scale
        * tilt_width_factor(travel)
    )
    result = Quad(
        bl=base_bl,
        br=base_br,
        tl=base_tl,
        tr=base_tr,
    ).translate(offset)
    if reverse:
        swap(result.bl, result.br)
        swap(result.tl, result.tr)
    return result


def layout_flick_arrow_fallback(
    lane: float, size: float, direction: FlickDirection, travel: float, animation_progress: float
) -> Quad:
    match direction:
        case FlickDirection.UP_OMNI:
            rotation = 0
            animation_top_x_offset = 0
            is_down = False
        case FlickDirection.DOWN_OMNI:
            rotation = pi
            animation_top_x_offset = 0
            is_down = True
        case FlickDirection.UP_LEFT:
            rotation = pi / 6
            animation_top_x_offset = -1
            is_down = False
        case FlickDirection.UP_RIGHT:
            rotation = -pi / 6
            animation_top_x_offset = 1
            is_down = False
        case FlickDirection.DOWN_LEFT:
            rotation = pi * 5 / 6
            animation_top_x_offset = 1
            is_down = True
            lane -= 0.25  # Note: backwards from the regular skin due to how the sprites are designed
        case FlickDirection.DOWN_RIGHT:
            rotation = -pi * 5 / 6
            animation_top_x_offset = -1
            is_down = True
            lane += 0.25
        case _:
            assert_never(direction)

    w = clamp(size / 2, 1, 2)
    offset_scale = animation_progress if not is_down else 1 - animation_progress
    width = tilt_width_factor(travel)
    offset = Vec2(animation_top_x_offset * DynamicLayout.w_scale, 2 * DynamicLayout.w_scale) * offset_scale * width
    return (
        Rect(l=-1, r=1, t=1, b=-1)
        .as_quad()
        .rotate(rotation)
        .scale(Vec2(w, w) * DynamicLayout.w_scale * width)
        .translate(offset)
        .rotate(-DynamicLayout.rotate)
        .translate(transformed_vec_at(lane, travel))
    )


def layout_slot_effect(lane: float, y_offset: float = 0.0) -> Quad:
    travel = approach(1 - y_offset)
    nh = DynamicLayout.note_h
    return perspective_rect(
        l=lane - 0.485,
        r=lane + 0.485,
        b=1 + nh,
        t=1 - nh,
        travel=travel,
    )


def layout_slot_glow_effect(lane: float, size: float, height: float, y_offset: float = 0.0) -> Quad:
    s = 1 + 0.25 * Options.slot_effect_size
    travel = approach(1 - y_offset)
    h = 4.75 * DynamicLayout.w_scale * Options.slot_effect_size * tilt_width_factor(travel)
    up = Vec2(0, h).rotate(-DynamicLayout.rotate)
    l_min = transformed_vec_at(lane - size, travel)
    r_min = transformed_vec_at(lane + size, travel)
    l_max = transformed_vec_at((lane - size) * s, travel) + up
    r_max = transformed_vec_at((lane + size) * s, travel) + up
    return Quad(
        bl=l_min,
        br=r_min,
        tl=lerp(l_min, l_max, height),
        tr=lerp(r_min, r_max, height),
    )


def layout_linear_effect(lane: float, shear: float, y_offset: float = 0.0) -> Quad:
    w = Options.note_effect_size
    travel = approach(1 - y_offset)
    bl = transformed_vec_at(lane - w, travel)
    br = transformed_vec_at(lane + w, travel)
    up = (br - bl).rotate(pi / 2) + (shear + 0.125 * lane) * (br - bl) / 2
    return Quad(
        bl=bl,
        br=br,
        tl=bl + up,
        tr=br + up,
    )


def layout_rotated_linear_effect(lane: float, shear: float, y_offset: float = 0.0) -> Quad:
    w = Options.note_effect_size
    travel = approach(1 - y_offset)
    bl = transformed_vec_at(lane - w, travel)
    br = transformed_vec_at(lane + w, travel)
    up = (br - bl).orthogonal()
    return Quad(
        bl=bl,
        br=br,
        tl=bl + up,
        tr=br + up,
    ).rotate_about(atan(-(shear + 0.125 * lane) / 2), pivot=(bl + br) / 2)


def layout_rotated2_linear_effect(lane: float, degree: float, y_offset: float = 0.0) -> Quad:
    w = Options.note_effect_size
    travel = approach(1 - y_offset)
    p = 1 + 0.12 * w
    bl = transformed_vec_at(lane - w, travel)
    br = transformed_vec_at(lane + w, travel)
    tl = transformed_vec_at(lane * p - w, travel)
    tr = transformed_vec_at(lane * p + w, travel)
    up = (tr - tl).orthogonal()
    radian = degree * pi / 180
    return Quad(
        bl=bl,
        br=br,
        tl=tl + up,
        tr=tr + up,
    ).rotate_about(radian, pivot=(bl + br) / 2)


def layout_circular_effect(lane: float, w: float, h: float, y_offset: float = 0.0) -> Quad:
    travel = approach(1 - y_offset)
    width = tilt_width_factor(travel)
    w *= Options.note_effect_size * width
    h *= Options.note_effect_size * DynamicLayout.w_scale / DynamicLayout.h_scale
    t = travel + h * width
    b = travel - h * width
    wb = tilt_width_factor(b)
    wt = tilt_width_factor(t)
    return transform_quad(
        Quad(
            bl=Vec2(lane * wb - w, b),
            br=Vec2(lane * wb + w, b),
            tl=Vec2(lane * wt - w, t),
            tr=Vec2(lane * wt + w, t),
        )
    )


def layout_tick_effect(lane: float, y_offset: float = 0.0) -> Quad:
    travel = approach(1 - y_offset)
    w = 4 * DynamicLayout.w_scale * Options.note_effect_size * tilt_width_factor(travel)
    center = transformed_vec_at(lane, travel)
    rot = -DynamicLayout.rotate
    dx = Vec2(w, 0).rotate(rot)
    dy = Vec2(0, w).rotate(rot)
    return Quad(
        bl=center - dx - dy,
        tl=center - dx + dy,
        tr=center + dx + dy,
        br=center + dx - dy,
    )


def layout_slide_connector_segment(
    start_lane: float,
    start_size: float,
    start_travel: float,
    end_lane: float,
    end_size: float,
    end_travel: float,
) -> Quad:
    if start_travel < end_travel:
        start_lane, end_lane = end_lane, start_lane
        start_size, end_size = end_size, start_size
        start_travel, end_travel = end_travel, start_travel
    return Quad(
        bl=perspective_vec(start_lane - start_size, 1, start_travel),
        br=perspective_vec(start_lane + start_size, 1, start_travel),
        tl=perspective_vec(end_lane - end_size, 1, end_travel),
        tr=perspective_vec(end_lane + end_size, 1, end_travel),
    )


def layout_sim_line(
    left_lane: float,
    left_travel: float,
    right_lane: float,
    right_travel: float,
) -> Quad:
    if left_lane > right_lane:
        left_lane, right_lane = right_lane, left_lane
        left_travel, right_travel = right_travel, left_travel
    ml = perspective_vec(left_lane, 1, left_travel)
    mr = perspective_vec(right_lane, 1, right_travel)
    ort = (mr - ml).orthogonal().normalize_or_zero()
    left_h = DynamicLayout.scaled_note_h * tilt_width_factor(left_travel)
    right_h = DynamicLayout.scaled_note_h * tilt_width_factor(right_travel)
    return Quad(
        bl=ml + ort * left_h,
        br=mr + ort * right_h,
        tl=ml - ort * left_h,
        tr=mr - ort * right_h,
    )


def layout_combo_label(
    center: Vec2,
    w: float,
    h: float,
) -> Quad:
    return transform_static_quad(
        Quad(
            bl=Vec2(center.x - w, center.y + h),
            br=Vec2(center.x + w, center.y + h),
            tl=Vec2(center.x - w, center.y - h),
            tr=Vec2(center.x + w, center.y - h),
        )
    )


def layout_skill_bar(
    center: Vec2,
    w: float,
    h: float,
) -> Quad:
    layout = +Quad
    if LevelConfig.ui_version == Version.v1:
        h, w = transform_fixed_size(h, w)
        layout @= transform_quad(
            Quad(
                bl=Vec2(center.x - w, center.y + h),
                br=Vec2(center.x + w, center.y + h),
                tl=Vec2(center.x - w, center.y - h),
                tr=Vec2(center.x + w, center.y - h),
            )
        )
    else:
        layout @= transform_fixed_quad(
            Quad(
                bl=Vec2(center.x - w, center.y + h),
                br=Vec2(center.x + w, center.y + h),
                tl=Vec2(center.x - w, center.y - h),
                tr=Vec2(center.x + w, center.y - h),
            )
        )
    return layout


def layout_skill_judgment_line(l: float = -6, r: float = 6, y_offset: float = 0.0) -> Quad:
    b = 1 + DynamicLayout.note_h
    t = 1 - DynamicLayout.note_h
    travel = approach(1 - y_offset)
    return perspective_rect(l=l, r=r, t=t, b=b, travel=travel)


def layout_fever_cover(l, r) -> Quad:
    p = perspective_rect(l=l, r=r, t=0, b=get_perspective_y(-1))
    big = 40.0
    horiz = Vec2(big, 0).rotate(-DynamicLayout.rotate)
    quad = +Quad
    if r == 0:
        quad @= Quad(
            bl=p.bl - horiz,
            br=p.bl,
            tl=p.tl - horiz,
            tr=p.tl,
        )
    else:
        quad @= Quad(
            bl=p.br,
            br=p.br + horiz,
            tl=p.tr,
            tr=p.tr + horiz,
        )
    return quad


def layout_fever_cover_sky() -> Quad:
    big = 40.0
    rot = -DynamicLayout.rotate
    return Quad(
        bl=Vec2(-big, DynamicLayout.t).rotate(rot),
        br=Vec2(big, DynamicLayout.t).rotate(rot),
        tl=Vec2(-big, big).rotate(rot),
        tr=Vec2(big, big).rotate(rot),
    )


def layout_fever_gauge_left(t) -> Quad:
    return perspective_rect(l=-6.5, r=-6, t=t, b=get_perspective_y(-1))


def layout_fever_gauge_right(t) -> Quad:
    return perspective_rect(l=6, r=6.5, t=t, b=get_perspective_y(-1))


def layout_dynamic_fever_side(l: float, r: float, percentage: float, travel: float = 1.0) -> Quad:
    t_val = lerp(LANE_B, LANE_T, percentage)

    b_val = get_perspective_y(-1)

    return perspective_rect(l=l, r=r, t=t_val, b=b_val, travel=travel)


def layout_fever_text() -> Quad:
    center = 0.65
    rect = Rect(t=center - 0.2, b=center + 0.2, l=-1.5, r=1.5)
    return transform_static_quad(rect)


def layout_fever_border() -> Rect:
    return Rect(t=1, b=-1, l=screen().l, r=screen().r)


def transform_fixed_size(h, w):
    target_width = w * Layout.fixed_w_scale
    target_height = h * Layout.fixed_h_scale

    width = target_width / Layout.w_scale
    height = target_height / Layout.h_scale

    return height, width


class HitboxTarget(Record):
    l: Vec2
    r: Vec2


class Hitbox(Record):
    target: HitboxTarget
    bounds: Quad


def interpolate_hitbox_edge_x(base_x: float, base_y: float, target_x: float, target_y: float, y: float) -> float:
    if base_y == target_y:
        return target_x
    return lerp(base_x, target_x, clamp((y - base_y) / (target_y - base_y), 0.0, 1.0))


class LayoutTransform(Record):
    t: float
    w_scale: float
    h_scale: float
    x_translate: float
    rotate: float
    stage_tilt: float
    size_zoom: float


def current_layout_transform() -> LayoutTransform:
    return LayoutTransform(
        t=DynamicLayout.t,
        w_scale=DynamicLayout.w_scale,
        h_scale=DynamicLayout.h_scale,
        x_translate=DynamicLayout.x_translate,
        rotate=DynamicLayout.rotate,
        stage_tilt=DynamicLayout.stage_tilt,
        size_zoom=DynamicLayout.size_zoom,
    )


def base_layout_transform(camera: CameraInfo) -> LayoutTransform:
    size_zoom = 6.0 / camera.size
    t = Layout.field_h * FIELD_T_FACTOR
    w = Layout.field_w * FIELD_W_FACTOR * size_zoom
    return LayoutTransform(
        t=t,
        w_scale=w,
        h_scale=Layout.field_h * FIELD_B_FACTOR - t,
        x_translate=-camera.lane * w,
        rotate=0.0,
        stage_tilt=clamp(camera.stage_tilt, 0.0, 1.0),
        size_zoom=size_zoom,
    )


def zoomed_layout_transform(
    transform: LayoutTransform, zoom: float, target: Vec2, anchor: Vec2, rotate: float
) -> LayoutTransform:
    return LayoutTransform(
        t=zoom * (transform.t - target.y) + anchor.y,
        w_scale=zoom * transform.w_scale,
        h_scale=zoom * transform.h_scale,
        x_translate=zoom * (transform.x_translate - target.x) + anchor.x,
        rotate=rotate,
        stage_tilt=transform.stage_tilt,
        size_zoom=transform.size_zoom,
    )


def layout_transform_at_camera(camera: CameraInfo) -> LayoutTransform:
    return zoomed_layout_transform(
        base_layout_transform(camera),
        camera.zoom,
        camera.zoom_target,
        camera.zoom_anchor,
        camera.rotate,
    )


def compute_hitbox(
    transform: LayoutTransform, lane: float, size: float, leniency: float, y_offset: float = 0.0
) -> Hitbox:
    tilt = transform.stage_tilt
    travel = approach_at_tilt(1 - y_offset, tilt)
    width_factor = width_factor_at_tilt(travel, tilt)
    l_x = (lane - size) * width_factor * transform.w_scale + transform.x_translate
    r_x = (lane + size) * width_factor * transform.w_scale + transform.x_translate
    note_y = travel * transform.h_scale + transform.t
    # We intentionally don't adjust for tilt to give the same screen-space leniency at low tilt
    lane_w = transform.w_scale
    vertical_half_lanes = 3.0
    if (
        Options.stage_cover_scroll_speed_compensation != StageCoverNoteSpeedCompensation.OFF
        and LevelConfig.dynamic_stages
    ):
        cover_travel = lerp(APPROACH_SCALE, 1.0, Options.stage_cover)
        vertical_half_lanes *= clamp((1 - cover_travel) / (1 - APPROACH_SCALE), 0, 1)
    vertical_extent = vertical_half_lanes * lane_w
    rot = -transform.rotate
    t_y = note_y + vertical_extent
    bl_x_final, br_x_final = l_x - leniency * lane_w, r_x + leniency * lane_w
    tl_x_final, tr_x_final = bl_x_final, br_x_final
    b_y = note_y - vertical_extent

    full_bottom = screen().b * cos(transform.rotate) - screen().r * abs(sin(transform.rotate))

    if Options.hitbox_range == HitboxRange.FULL_VERTICAL:
        b_y = full_bottom

    elif Options.hitbox_range == HitboxRange.FULL_ADAPTIVE:
        b_y = full_bottom

        base_travel = approach_at_tilt(1.0, tilt)
        base_width = width_factor_at_tilt(base_travel, tilt)
        base_l_x = (lane - size) * base_width * transform.w_scale + transform.x_translate
        base_r_x = (lane + size) * base_width * transform.w_scale + transform.x_translate
        base_y = base_travel * transform.h_scale + transform.t

        bl_x_final = interpolate_hitbox_edge_x(base_l_x, base_y, l_x, note_y, b_y) - (leniency * lane_w)
        br_x_final = interpolate_hitbox_edge_x(base_r_x, base_y, r_x, note_y, b_y) + (leniency * lane_w)

    return Hitbox(
        target=HitboxTarget(
            l=Vec2(l_x, note_y).rotate(rot),
            r=Vec2(r_x, note_y).rotate(rot),
        ),
        bounds=Quad(
            bl=Vec2(bl_x_final, b_y).rotate(rot),
            br=Vec2(br_x_final, b_y).rotate(rot),
            tl=Vec2(tl_x_final, t_y).rotate(rot),
            tr=Vec2(tr_x_final, t_y).rotate(rot),
        ),
    )


def compute_hitbox_at_time(
    lane: float,
    size: float,
    leniency: float,
    target_time: float,
    y_offset: float = 0.0,
    left_limit: bool = False,
) -> Hitbox:
    return compute_hitbox(
        layout_transform_at_camera(get_camera_info(target_time, left_limit=left_limit)),
        lane,
        size,
        leniency,
        y_offset,
    )


def segment_closeness_score(p: Vec2, seg: HitboxTarget) -> float:
    d = seg.r - seg.l
    t = clamp((p - seg.l).dot(d) / d.dot(d), 0.0, 1.0)
    return -(p - (seg.l + d * t)).magnitude


def layout_lane_area(l: float, r: float) -> Quad:
    return perspective_rect(l, r, LANE_T, LANE_B)


def iter_slot_lanes(lane: float, size: float, pivot_lane: float = 0.0, half_offset: bool = False):
    e = 1e-6
    offset = 0.0 if half_offset else 0.5
    shift = pivot_lane + offset - 0.5
    shifted_lane = lane - shift
    for i in range(floor(shifted_lane - size + e), ceil(shifted_lane + size - e)):
        yield i + 0.5 + shift
