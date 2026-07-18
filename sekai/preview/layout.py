from collections.abc import Iterator
from math import floor, pi
from typing import Literal, assert_never

from sonolus.script.array import Array, Dim
from sonolus.script.containers import VarArray
from sonolus.script.globals import level_data
from sonolus.script.interval import clamp, lerp, remap_clamped
from sonolus.script.printing import PrintColor, PrintFormat, print_number
from sonolus.script.quad import Quad, Rect
from sonolus.script.runtime import HorizontalAlign, ScrollDirection, canvas, screen
from sonolus.script.vec import Vec2

from sekai.lib.layout import NOTE_EDGE_W, NOTE_SLIM_EDGE_W, FlickDirection, preempt_time
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import Options, PreviewDisplayMode

PREVIEW_COLUMN_SECS = 2
PREVIEW_MIN_COLUMN_SECS = 0.25

PREVIEW_MARGIN_Y = 0.125
PREVIEW_MARGIN_X = 0.26
PREVIEW_EXTEND_MARGIN_X = 0.02
PREVIEW_TEXT_MARGIN_X = 0
PREVIEW_TEXT_MARGIN_Y = -0.002

PREVIEW_LANE_W = 0.05
PREVIEW_STAGE_BORDER_W = 0.25 * PREVIEW_LANE_W
PREVIEW_NOTE_H = PREVIEW_LANE_W / 3
PREVIEW_BAR_LINE_H = PREVIEW_LANE_W / 20
PREVIEW_BAR_LINE_ALPHA = 0.8

PREVIEW_CLASSIC_BASE_LANE_COUNT = 12
PREVIEW_DYNAMIC_STAGE_BASE_LANE_COUNT = 20
PREVIEW_CLASSIC_COLUMN_WIDTH = 2 * (PREVIEW_MARGIN_X + PREVIEW_LANE_W * PREVIEW_CLASSIC_BASE_LANE_COUNT / 2)
PREVIEW_DYNAMIC_STAGE_COLUMN_WIDTH = 2 * (PREVIEW_MARGIN_X + PREVIEW_LANE_W * PREVIEW_DYNAMIC_STAGE_BASE_LANE_COUNT / 2)
PREVIEW_CLASSIC_LANE_BOUND = (
    PREVIEW_CLASSIC_BASE_LANE_COUNT / 2 + (PREVIEW_MARGIN_X - PREVIEW_EXTEND_MARGIN_X) / PREVIEW_LANE_W
)
PREVIEW_DYNAMIC_STAGE_LANE_BOUND = (
    PREVIEW_DYNAMIC_STAGE_BASE_LANE_COUNT / 2 + (PREVIEW_MARGIN_X - PREVIEW_EXTEND_MARGIN_X) / PREVIEW_LANE_W
)

PREVIEW_CAMERA_MARKER_ALPHA = 0.6

PREVIEW_COVER_ALPHA = 1.0

PREVIEW_Y_MIN = -1 + PREVIEW_MARGIN_Y
PREVIEW_Y_MAX = 1 - PREVIEW_MARGIN_Y

PREVIEW_BAR_EXTEND_W = 4.5 * PREVIEW_LANE_W
PREVIEW_DYNAMIC_BAR_EXTEND_W = 4 * PREVIEW_LANE_W

PREVIEW_TEXT_H = 0.11
PREVIEW_TEXT_W = 3.5 * PREVIEW_LANE_W - 2 * PREVIEW_TEXT_MARGIN_X

PREVIEW_DYNAMIC_STAGE_TIME_INCREMENT = 1 / 60
PREVIEW_DYNAMIC_STAGE_BSEARCH_ITERS = 6
PREVIEW_DYNAMIC_STAGE_BORDER_DEFAULT_W = 0.15
PREVIEW_DYNAMIC_STAGE_BORDER_MEDIUM_W = 0.075
PREVIEW_DYNAMIC_STAGE_BORDER_LIGHT_W = 0.075
PREVIEW_DYNAMIC_STAGE_DIVIDER_W = 0.075
PREVIEW_DYNAMIC_STAGE_EPS = 0.001


@level_data
class PreviewData:
    max_time: float
    max_col: int
    note_counts_by_col: Array[int, Dim[1000]]
    min_timescale_group: int


@level_data
class PreviewLayout:
    column_count: int
    column_width: float
    visible_secs: float
    lane_bound: float


def preview_column_secs() -> float:
    if Options.preview_display_mode == PreviewDisplayMode.EDITOR:
        return PREVIEW_COLUMN_SECS
    return max(preempt_time(), PREVIEW_MIN_COLUMN_SECS)


def init_preview_layout():
    PreviewLayout.column_count = max(PreviewData.max_col, time_to_preview_col(PreviewData.max_time)) + 1
    PreviewLayout.column_width = (
        PREVIEW_DYNAMIC_STAGE_COLUMN_WIDTH if LevelConfig.dynamic_stages else PREVIEW_CLASSIC_COLUMN_WIDTH
    )
    PreviewLayout.visible_secs = PreviewLayout.column_count * preview_column_secs()
    PreviewLayout.lane_bound = (
        PREVIEW_DYNAMIC_STAGE_LANE_BOUND if LevelConfig.dynamic_stages else PREVIEW_CLASSIC_LANE_BOUND
    )

    canvas().update(
        scroll_direction=ScrollDirection.LEFT_TO_RIGHT,
        size=PreviewLayout.column_width * PreviewLayout.column_count,
    )


def time_to_preview_col(time: float, group: int = 0) -> int:
    return floor(time / preview_column_secs())


def time_to_preview_y_axis(time: float, col: int, group: int = 0) -> float:
    return time - col * preview_column_secs()


def preview_y_axis_to_y(axis: float) -> float:
    return lerp(PREVIEW_Y_MIN, PREVIEW_Y_MAX, axis / preview_column_secs())


def preview_axis_to_col(axis: float) -> int:
    return floor(axis / preview_column_secs())


def preview_axis_to_y(axis: float, col: int) -> float:
    return preview_y_axis_to_y(axis - col * preview_column_secs())


def time_to_preview_y(time: float, col: int, group: int = 0) -> float:
    if col is None:
        col = time_to_preview_col(time, group)
    return preview_y_axis_to_y(time_to_preview_y_axis(time, col, group))


def lane_to_preview_x(lane: float, col: int) -> float:
    return (col + 0.5) * PreviewLayout.column_width + lane * PREVIEW_LANE_W - screen().w / 2


def get_adjusted_time(time: float, col: int) -> float:
    # Times are kept relative to the column so the z time component stays consistent across columns
    return time - col * preview_column_secs()


def layout_preview_lane_by_edges(l: float, r: float, col: int) -> Rect:
    return Rect(
        l=lane_to_preview_x(l, col),
        r=lane_to_preview_x(r, col),
        b=-1,
        t=1,
    )


def layout_preview_lane(lane: float, size: float, col: int) -> Rect:
    return layout_preview_lane_by_edges(lane - size, lane + size, col)


def layout_preview_lane_strip(l_a: float, r_a: float, t_a: float, l_b: float, r_b: float, t_b: float, col: int) -> Quad:
    y_a = time_to_preview_y(t_a, col)
    y_b = time_to_preview_y(t_b, col)
    return Quad(
        bl=Vec2(lane_to_preview_x(l_a, col), y_a),
        br=Vec2(lane_to_preview_x(r_a, col), y_a),
        tr=Vec2(lane_to_preview_x(r_b, col), y_b),
        tl=Vec2(lane_to_preview_x(l_b, col), y_b),
    )


def layout_preview_lane_rotated_strip(
    pos_a: float, pos_b: float, t_a: float, t_b: float, width: float, col: int
) -> Quad:
    center_a = Vec2(lane_to_preview_x(pos_a, col), time_to_preview_y(t_a, col))
    center_b = Vec2(lane_to_preview_x(pos_b, col), time_to_preview_y(t_b, col))
    offset = (center_b - center_a).orthogonal().normalize_or_zero() * (width / 2 * PREVIEW_LANE_W)
    return Quad(
        bl=center_a + offset,
        br=center_a - offset,
        tr=center_b - offset,
        tl=center_b + offset,
    )


def layout_preview_bottom_cover() -> Rect:
    return Rect(
        l=screen().l,
        r=PreviewLayout.column_width * PreviewLayout.column_count + 1,
        b=screen().b,
        t=PREVIEW_Y_MIN,
    )


def layout_preview_top_cover() -> Rect:
    return Rect(
        l=screen().l,
        r=PreviewLayout.column_width * PreviewLayout.column_count + 1,
        b=PREVIEW_Y_MAX,
        t=screen().t,
    )


def layout_preview_note_body_by_edges(l: float, r: float, h: float, col: int, y: float) -> Rect:
    return Rect(
        l=lane_to_preview_x(l, col),
        r=lane_to_preview_x(r, col),
        b=y - h,
        t=y + h,
    )


def layout_preview_note_body_slices_by_edges(
    l: float, r: float, h: float, edge_w: float, col: int, y: float
) -> tuple[Rect, Rect, Rect]:
    m = (l + r) / 2
    if r < l:
        # Make the note 0 width; shouldn't normally happen, but in case, we want to handle it gracefully
        l = r = m
    ml = min(l + edge_w, m)
    mr = max(r - edge_w, m)
    return (
        layout_preview_note_body_by_edges(l=l, r=ml, h=h, col=col, y=y),
        layout_preview_note_body_by_edges(l=ml, r=mr, h=h, col=col, y=y),
        layout_preview_note_body_by_edges(l=mr, r=r, h=h, col=col, y=y),
    )


def layout_preview_regular_note_body(lane: float, size: float, col: int, y: float) -> tuple[Rect, Rect, Rect]:
    return layout_preview_note_body_slices_by_edges(
        l=lane - size + Options.note_margin,
        r=lane + size - Options.note_margin,
        h=PREVIEW_NOTE_H,
        edge_w=NOTE_EDGE_W,
        col=col,
        y=y,
    )


def layout_preview_regular_note_body_fallback(lane: float, size: float, col: int, y: float) -> Rect:
    return layout_preview_note_body_by_edges(
        l=lane - size + Options.note_margin,
        r=lane + size - Options.note_margin,
        h=PREVIEW_NOTE_H,
        col=col,
        y=y,
    )


def layout_preview_slim_note_body(lane: float, size: float, col: int, y: float) -> tuple[Rect, Rect, Rect]:
    return layout_preview_note_body_slices_by_edges(
        l=lane - size + Options.note_margin,
        r=lane + size - Options.note_margin,
        h=PREVIEW_NOTE_H,  # Height is handled by the sprite rather than being changed here
        edge_w=NOTE_SLIM_EDGE_W,
        col=col,
        y=y,
    )


def layout_preview_slim_note_body_fallback(lane: float, size: float, col: int, y: float) -> Rect:
    return layout_preview_note_body_by_edges(
        l=lane - size + Options.note_margin,
        r=lane + size - Options.note_margin,
        h=PREVIEW_NOTE_H / 2,  # For fallback, we need to halve the height manually engine-side
        col=col,
        y=y,
    )


def layout_preview_tick(lane: float, col: int, y: float) -> Rect:
    center = Vec2(lane_to_preview_x(lane, col), y)
    return Rect.from_center(center, Vec2(PREVIEW_NOTE_H, PREVIEW_NOTE_H) * 2)


def layout_preview_camera_jump_connector(lane_lo: float, lane_hi: float, time: float, width: float, col: int) -> Quad:
    half_h = width / 2 * PREVIEW_LANE_W
    y = time_to_preview_y(time, col)
    x_lo = lane_to_preview_x(lane_lo, col)
    x_hi = lane_to_preview_x(lane_hi, col)
    return Quad(
        bl=Vec2(x_lo, y - half_h),
        br=Vec2(x_hi, y - half_h),
        tr=Vec2(x_hi, y + half_h),
        tl=Vec2(x_lo, y + half_h),
    )


def layout_preview_flick_arrow(lane: float, size: float, direction: FlickDirection, col: int, y: float) -> Rect:
    match direction:
        case FlickDirection.UP_OMNI:
            reverse = False
        case FlickDirection.DOWN_OMNI:
            reverse = False
        case FlickDirection.UP_LEFT:
            reverse = False
        case FlickDirection.UP_RIGHT:
            reverse = True
        case FlickDirection.DOWN_LEFT:
            reverse = False
        case FlickDirection.DOWN_RIGHT:
            reverse = True
        case _:
            assert_never(direction)
    w = clamp(size, 0, 3) / 2
    result = Rect(
        l=lane_to_preview_x(lane - w, col),
        r=lane_to_preview_x(lane + w, col),
        b=y,
        t=y + 2 * w * PREVIEW_LANE_W,
    )
    if reverse:
        result.l, result.r = result.r, result.l
    return result


def layout_preview_flick_arrow_fallback(
    lane: float, size: float, direction: FlickDirection, col: int, y: float
) -> Quad:
    match direction:
        case FlickDirection.UP_OMNI:
            rotation = 0
        case FlickDirection.DOWN_OMNI:
            rotation = pi
        case FlickDirection.UP_LEFT:
            rotation = pi / 6
        case FlickDirection.UP_RIGHT:
            rotation = -pi / 6
        case FlickDirection.DOWN_LEFT:
            rotation = pi * 5 / 6
            lane -= 0.25  # Note: backwards from the regular skin due to how the sprites are designed
        case FlickDirection.DOWN_RIGHT:
            rotation = -pi * 5 / 6
            lane += 0.25
        case _:
            assert_never(direction)

    w = clamp(size / 2, 1, 2)
    return (
        Rect(l=-1, r=1, t=1, b=-1)
        .as_quad()
        .rotate(rotation)
        .scale(Vec2(w, w) * PREVIEW_LANE_W)
        .translate(Vec2(lane_to_preview_x(lane, col), y + PREVIEW_NOTE_H / 2))
    )


def layout_preview_slide_connector_segment(
    start_lane: float,
    start_size: float,
    start_y: float,
    end_lane: float,
    end_size: float,
    end_y: float,
    col: int,
) -> Iterator[Quad]:
    x_min = lane_to_preview_x(-PreviewLayout.lane_bound, col)
    x_max = lane_to_preview_x(PreviewLayout.lane_bound, col)
    bl = Vec2(lane_to_preview_x(start_lane - start_size, col), start_y)
    br = Vec2(lane_to_preview_x(start_lane + start_size, col), start_y)
    tl = Vec2(lane_to_preview_x(end_lane - end_size, col), end_y)
    tr = Vec2(lane_to_preview_x(end_lane + end_size, col), end_y)
    endpoints = VarArray[float, Dim[5]].new()
    endpoints.append(end_y)
    l_x_min = min(bl.x, tl.x)
    l_x_max = max(bl.x, tl.x)
    r_x_min = min(br.x, tr.x)
    r_x_max = max(br.x, tr.x)
    if l_x_min < x_min < l_x_max:
        endpoints.append(remap_clamped(l_x_min, l_x_max, bl.y, tl.y, x_min))
    if l_x_min < x_max < l_x_max:
        endpoints.append(remap_clamped(l_x_min, l_x_max, bl.y, tl.y, x_max))
    if r_x_min < x_min < r_x_max:
        endpoints.append(remap_clamped(r_x_min, r_x_max, br.y, tr.y, x_min))
    if r_x_min < x_max < r_x_max:
        endpoints.append(remap_clamped(r_x_min, r_x_max, br.y, tr.y, x_max))
    prev_y = start_y
    prev_l_x = clamp(bl.x, x_min, x_max)
    prev_r_x = clamp(br.x, x_min, x_max)
    endpoints.sort()
    for next_y in endpoints:
        next_l_x = clamp(remap_clamped(start_y, end_y, bl.x, tl.x, next_y), x_min, x_max)
        next_r_x = clamp(remap_clamped(start_y, end_y, br.x, tr.x, next_y), x_min, x_max)
        yield Quad(
            bl=Vec2(prev_l_x, prev_y),
            br=Vec2(prev_r_x, prev_y),
            tr=Vec2(next_r_x, next_y),
            tl=Vec2(next_l_x, next_y),
        )
        prev_y = next_y
        prev_l_x = next_l_x
        prev_r_x = next_r_x


def layout_preview_sim_line(
    left_lane: float,
    right_lane: float,
    col: int,
    y: float,
) -> Quad:
    if left_lane > right_lane:
        left_lane, right_lane = right_lane, left_lane
    return Rect(
        l=lane_to_preview_x(left_lane, col),
        r=lane_to_preview_x(right_lane, col),
        b=y - PREVIEW_NOTE_H,
        t=y + PREVIEW_NOTE_H,
    ).as_quad()


def layout_preview_bar_line(
    time: float,
    extend: Literal[
        "left",
        "right",
        "both",
        "none",
        "left_only",
        "right_only",
        "left_in",
        "right_in",
        "left_dynamic",
        "right_dynamic",
    ],
    extend_scale: float = 1.0,
) -> Quad:
    col = time_to_preview_col(time)
    left_lane = -6
    right_lane = 6
    left_x = lane_to_preview_x(left_lane, col)
    right_x = lane_to_preview_x(right_lane, col)
    column_center_x = lane_to_preview_x(0, col)
    column_left_x = column_center_x - PreviewLayout.column_width / 2
    column_right_x = column_center_x + PreviewLayout.column_width / 2
    match extend:
        case "left":
            left_x -= PREVIEW_BAR_EXTEND_W * extend_scale
        case "right":
            right_x += PREVIEW_BAR_EXTEND_W * extend_scale
        case "both":
            left_x -= PREVIEW_BAR_EXTEND_W * extend_scale
            right_x += PREVIEW_BAR_EXTEND_W * extend_scale
        case "left_only":
            right_x = left_x - PREVIEW_LANE_W * 0.5
            left_x = right_x - PREVIEW_BAR_EXTEND_W * extend_scale
        case "right_only":
            left_x = right_x + PREVIEW_LANE_W * 0.5
            right_x = left_x + PREVIEW_BAR_EXTEND_W * extend_scale
        case "left_in":
            left_x = column_left_x + PREVIEW_LANE_W * 0.5
            right_x = left_x + PREVIEW_BAR_EXTEND_W * extend_scale
        case "right_in":
            right_x = column_right_x - PREVIEW_LANE_W * 0.5
            left_x = right_x - PREVIEW_BAR_EXTEND_W * extend_scale
        case "left_dynamic":
            left_x = column_left_x + PREVIEW_LANE_W * 0.5
            right_x = left_x + PREVIEW_DYNAMIC_BAR_EXTEND_W
        case "right_dynamic":
            right_x = column_right_x - PREVIEW_LANE_W * 0.5
            left_x = right_x - PREVIEW_DYNAMIC_BAR_EXTEND_W
        case _:
            pass
    y = time_to_preview_y(time, col)
    return Quad(
        bl=Vec2(left_x, y - PREVIEW_BAR_LINE_H),
        br=Vec2(right_x, y - PREVIEW_BAR_LINE_H),
        tr=Vec2(right_x, y + PREVIEW_BAR_LINE_H),
        tl=Vec2(left_x, y + PREVIEW_BAR_LINE_H),
    )


def layout_preview_column_divider(col: int) -> Rect:
    x = lane_to_preview_x(0, col) - PreviewLayout.column_width / 2
    return Rect(
        l=x - PREVIEW_BAR_LINE_H,
        r=x + PREVIEW_BAR_LINE_H,
        b=PREVIEW_Y_MIN,
        t=PREVIEW_Y_MAX,
    )


def print_at_time(
    value: float,
    time: float,
    *,
    fmt: PrintFormat,
    decimal_places: int = -1,
    color: PrintColor,
    side: Literal["left", "right"],
    dynamic: bool = False,
):
    col = time_to_preview_col(time)
    y = time_to_preview_y(time, col)
    if dynamic:
        # Anchored at the inner end of the line that hugs the column edge,
        # with text aligned toward the column edge so it grows away from the stage.
        column_center_x = lane_to_preview_x(0, col)
        column_left_x = column_center_x - PreviewLayout.column_width / 2
        column_right_x = column_center_x + PreviewLayout.column_width / 2
        if side == "left":
            anchor_x = column_left_x + PREVIEW_LANE_W * 0.5 + PREVIEW_DYNAMIC_BAR_EXTEND_W - PREVIEW_TEXT_MARGIN_X
            pivot_x = 1.0
            align = HorizontalAlign.RIGHT
        else:
            anchor_x = column_right_x - PREVIEW_LANE_W * 0.5 - PREVIEW_DYNAMIC_BAR_EXTEND_W + PREVIEW_TEXT_MARGIN_X
            pivot_x = 0.0
            align = HorizontalAlign.LEFT
    else:
        anchor_x = lane_to_preview_x(-6 if side == "left" else 6, col) + (
            PREVIEW_TEXT_MARGIN_X - PREVIEW_BAR_EXTEND_W
            if side == "left"
            else PREVIEW_BAR_EXTEND_W - PREVIEW_TEXT_MARGIN_X
        )
        pivot_x = 0.0 if side == "left" else 1.0
        align = HorizontalAlign.LEFT if side == "left" else HorizontalAlign.RIGHT
    print_number(
        value=value,
        fmt=fmt,
        decimal_places=decimal_places,
        anchor=Vec2(anchor_x, y + PREVIEW_TEXT_MARGIN_Y),
        pivot=Vec2(pivot_x, 0),
        dimensions=Vec2(PREVIEW_TEXT_W, PREVIEW_TEXT_H),
        color=color,
        horizontal_align=align,
        background=False,
    )


def print_at_col_top(
    value: float,
    col: int,
    *,
    fmt: PrintFormat,
    decimal_places: int = -1,
    color: PrintColor,
    side: Literal["left", "right"],
):
    print_number(
        value=value,
        fmt=fmt,
        decimal_places=decimal_places,
        anchor=Vec2(
            lane_to_preview_x(
                -6 if side == "left" else 6,
                col,
            )
            + (-PREVIEW_TEXT_MARGIN_X if side == "left" else PREVIEW_TEXT_MARGIN_X),
            PREVIEW_Y_MAX + PREVIEW_TEXT_MARGIN_Y + 0.008,
        ),
        pivot=Vec2(0.5, 0),
        dimensions=Vec2(PREVIEW_TEXT_W, PREVIEW_TEXT_H),
        color=color,
        horizontal_align=HorizontalAlign.CENTER,
        background=False,
    )
