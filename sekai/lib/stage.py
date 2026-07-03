from __future__ import annotations

from enum import IntEnum
from math import ceil, cos, floor, inf, pi
from typing import Protocol, Self, assert_never, cast

from sonolus.script import runtime
from sonolus.script.archetype import EntityRef, get_archetype_by_name
from sonolus.script.array import Array, Dim
from sonolus.script.containers import VarArray
from sonolus.script.interval import Interval, clamp, interp, lerp, unlerp_clamped
from sonolus.script.quad import Quad, QuadLike, Rect
from sonolus.script.record import Record
from sonolus.script.runtime import is_multiplayer, is_play, is_replay, is_watch, time
from sonolus.script.sprite import Sprite
from sonolus.script.values import alloc
from sonolus.script.vec import Vec2

from sekai.lib import archetype_names
from sekai.lib.baseevent import get_event_as, query_event_list
from sekai.lib.custom_elements import (
    SkillHide,
    draw_life_number,
    draw_score_bar_number,
    draw_score_bar_raw_number,
    draw_score_number,
)
from sekai.lib.ease import EaseType, ease
from sekai.lib.effect import SFX_DISTANCE, Effects
from sekai.lib.layer import (
    LAYER_BACKGROUND,
    LAYER_BACKGROUND_COVER,
    LAYER_COVER,
    LAYER_JUDGMENT,
    LAYER_STAGE_LANE,
    ZIndexes,
    get_z,
    get_z_alt,
    layers,
)
from sekai.lib.layout import (
    IDENTITY_STAGE_SCREEN_TRANSFORM,
    TEST_ASPECT_SCALE,
    DynamicLayout,
    Layout,
    LayoutTransform,
    ScoreGaugeType,
    StageScreenTransform,
    StageTransform,
    StageTransformAnchor,
    StaticUiLayout,
    approach,
    camera_layout_transform_at_time,
    compute_stage_transform,
    current_layout_transform,
    current_stage_tilt,
    hidden_amount,
    identity_stage_transform,
    layout_full_width_stage_cover,
    layout_hidden_cover,
    layout_life_gauge,
    layout_particle_lane,
    layout_score_gauge,
    layout_sekai_stage,
    layout_stage_cover,
    layout_stage_cover_and_line,
    layout_stage_lane_by_edges,
    perspective_rect,
    stage_aspect_ratio_locked,
    stage_cover_amount,
    test_aspect_active,
    tilt_depth,
    tilt_widened_edge,
    tilt_width_factor,
    transformed_vec_at,
)
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import Options, StageCoverMode, Version
from sekai.lib.particle import ActiveParticles
from sekai.lib.skin import (
    ActiveSkin,
    JudgmentSpriteSet,
    LifeBarType,
    ScoreRankType,
)


class JudgeLineColor(IntEnum):
    NEUTRAL = 0
    RED = 1
    GREEN = 2
    BLUE = 3
    YELLOW = 4
    PURPLE = 5
    CYAN = 6
    BLACK = 7


class DivisionParity(IntEnum):
    EVEN = 0
    ODD = 1


class DivisionProps(Record):
    size: int
    parity: DivisionParity


class StageBorderStyle(IntEnum):
    DEFAULT = 0
    LIGHT = 1
    DISABLED = 2
    MEDIUM = 3


class JudgeLineStyle(IntEnum):
    DEFAULT = 0
    SINGLE_LINE = 1


FULL_WIDTH_HALF_EXTENT = 48.0
JUDGE_LINE_BORDER_FACTOR = 5.0


def full_width_factor(full_width: bool) -> float:
    return 1.0 if full_width else 0.0


class Transition[T](Record):
    start: T
    end: T
    progress: float


def border_style_width(style: StageBorderStyle, default: float, medium: float, light: float) -> float:
    match style:
        case StageBorderStyle.DEFAULT:
            return default
        case StageBorderStyle.MEDIUM:
            return medium
        case StageBorderStyle.LIGHT:
            return light
        case StageBorderStyle.DISABLED:
            return 0.0
        case _:
            assert_never(style)


def border_width(style: Transition[StageBorderStyle], default: float, medium: float, light: float) -> float:
    return lerp(
        border_style_width(style.start, default, medium, light),
        border_style_width(style.end, default, medium, light),
        style.progress,
    )


def border_sprite_transition(style: Transition[StageBorderStyle]) -> Transition[StageBorderStyle]:
    result = +style
    if result.start == StageBorderStyle.MEDIUM:
        result.start = StageBorderStyle.DEFAULT
    if result.end == StageBorderStyle.MEDIUM:
        result.end = StageBorderStyle.DEFAULT
    if result.start == StageBorderStyle.DISABLED:
        result.start = result.end
    if result.end == StageBorderStyle.DISABLED:
        result.end = result.start
    if result.start == result.end:
        result.progress = 0.0
    return result


def blend_border_layout(start: QuadLike, end: QuadLike, progress: float) -> Quad:
    return Quad(
        bl=start.bl + (end.bl - start.bl) * progress,
        br=start.br + (end.br - start.br) * progress,
        tl=start.tl + (end.tl - start.tl) * progress,
        tr=start.tr + (end.tr - start.tr) * progress,
    )


def border_blend_alpha(alpha: float, progress: float) -> float:
    remaining = 1 - alpha * progress
    return alpha * (1 - progress) / remaining if remaining > 0 else 0.0


def judge_line_style_weight(style: Transition[JudgeLineStyle], target: JudgeLineStyle) -> float:
    weight = 0.0
    if style.start == target:
        weight += 1 - style.progress
    if style.end == target:
        weight += style.progress
    return weight


def resolve_judge_line_style(style: Transition[JudgeLineStyle]) -> JudgeLineStyle:
    """Choose the more visible judge line style for effects that cannot blend styles."""
    if style.progress < 0.5:
        return style.start
    return style.end


class StageProps(Record):
    lane: float
    width: float
    pivot_lane: float
    division: Transition[DivisionProps]
    judge_line_color: Transition[JudgeLineColor]
    left_border_style: Transition[StageBorderStyle]
    right_border_style: Transition[StageBorderStyle]
    lane_alpha: float
    judge_line_alpha: float
    y_offset: float
    judge_line_style: Transition[JudgeLineStyle]
    full_width: float
    division_line_alpha: float
    note_alpha: float
    mask_notes: bool
    rotate: float
    x_lane_translate: float
    y_lane_translate: float
    center_weight: float
    elevation: float

    def stage_transform(self) -> StageTransform:
        return compute_stage_transform(
            current_layout_transform(),
            self.rotate,
            self.x_lane_translate,
            self.y_lane_translate,
            self.lane,
            self.center_weight,
            self.elevation,
        )

    def has_transform(self) -> bool:
        return (
            self.rotate != 0.0
            or self.x_lane_translate != 0.0
            or self.y_lane_translate != 0.0
            or self.center_weight != 0.0
            or self.elevation != 0.0
        )

    def draw(self, order: int):
        ui_alpha = 1.0
        if Options.ui_intro and time() < -1.0:
            ui_alpha = unlerp_clamped(-2.0, -1.0, time())
        transform = +StageTransform
        if self.has_transform():
            transform @= self.stage_transform()
        else:
            transform @= identity_stage_transform()
        draw_dynamic_stage(
            lane=self.lane,
            width=self.width,
            pivot_lane=self.pivot_lane,
            division=self.division,
            judge_line_color=self.judge_line_color,
            judge_line_style=self.judge_line_style,
            left_border_style=self.left_border_style,
            right_border_style=self.right_border_style,
            order=order,
            lane_alpha=self.lane_alpha,
            judge_line_alpha=self.judge_line_alpha,
            y_offset=self.y_offset,
            alpha=ui_alpha,
            full_width=self.full_width,
            division_line_alpha=self.division_line_alpha,
            transform=transform.to_screen_transform(),
        )


class VisualMask(Record):
    left: float
    right: float
    enabled: bool
    stage_index: int


class InputGeometry(Record):
    lane: float
    mask: VisualMask
    y_offset: float
    transform: StageTransform


class StageInputGeometry(Record):
    stage_index: int
    geometry: InputGeometry


class InputGeometryContext(Record):
    time: float
    layout: LayoutTransform
    # An endpoint note attached to a segment uses that segment's head and tail stages.
    # The connector's two endpoints therefore need at most four cache entries.
    stages: VarArray[StageInputGeometry, Dim[4]]

    @staticmethod
    def at(t: float) -> InputGeometryContext:
        result = alloc(InputGeometryContext)
        result.time = t
        result.layout @= camera_layout_transform_at_time(t, left_limit=True)
        result.stages.clear()
        return result

    def stage_geometry(self, stage: DynamicStageLike) -> InputGeometry:
        result = +InputGeometry
        for cached in self.stages:
            if cached.stage_index == stage.index:
                result @= cached.geometry
                return result

        props = get_stage_input_props(stage, self.time)
        # Lane includes events at the input timestamp; mask, offset, and transform use the left limit.
        result.lane = get_stage_pivot_lane(stage, self.time)
        result.mask.left = props.lane - props.width
        result.mask.right = props.lane + props.width
        result.mask.enabled = props.mask_notes
        if props.mask_notes:
            result.mask.stage_index = stage.index
        result.y_offset = props.y_offset
        result.transform @= compute_stage_transform(
            self.layout,
            props.rotate,
            props.x_lane_translate,
            props.y_lane_translate,
            props.lane,
            props.center_weight,
            props.elevation,
        )
        self.stages.append(StageInputGeometry(stage_index=stage.index, geometry=result))
        return result


def interpolate_visual_masks(head: VisualMask, tail: VisualMask, frac: float) -> VisualMask:
    """Return the connector mask at an interpolated point between two notes."""
    result = +VisualMask
    if not head.enabled or not tail.enabled:
        return result
    result.left = lerp(head.left, tail.left, frac)
    result.right = lerp(head.right, tail.right, frac)
    result.enabled = True
    if head.stage_index > 0 and head.stage_index == tail.stage_index:
        result.stage_index = head.stage_index
    return result


class StageMaskChangeLike(Protocol):
    time: float
    lane: float
    size: float
    mask_notes: bool
    ease: EaseType
    next_ref: EntityRef
    prev_ref: EntityRef

    @classmethod
    def at(cls, index: int) -> Self: ...

    @property
    def index(self) -> int: ...


class StagePivotChangeLike(Protocol):
    time: float
    lane: float
    division_size: float
    division_parity: DivisionParity
    y_offset: float
    ease: EaseType
    next_ref: EntityRef
    prev_ref: EntityRef

    @classmethod
    def at(cls, index: int) -> Self: ...

    @property
    def index(self) -> int: ...


class StageStyleChangeLike(Protocol):
    time: float
    judge_line_color: JudgeLineColor
    judge_line_style: JudgeLineStyle
    left_border_style: StageBorderStyle
    right_border_style: StageBorderStyle
    full_width: bool
    lane_alpha: float
    judge_line_alpha: float
    division_line_alpha: float
    note_alpha: float
    ease: EaseType
    next_ref: EntityRef
    prev_ref: EntityRef
    note_visibility_start: float
    previous_note_visibility_end: float

    @classmethod
    def at(cls, index: int) -> Self: ...

    @property
    def index(self) -> int: ...


class StageTransformChangeLike(Protocol):
    time: float
    rotate: float
    x_lane_translate: float
    y_lane_translate: float
    anchor: StageTransformAnchor
    elevation: float
    ease: EaseType
    next_ref: EntityRef
    prev_ref: EntityRef

    @classmethod
    def at(cls, index: int) -> Self: ...

    @property
    def index(self) -> int: ...


class DynamicStageLike(Protocol):
    from_start: bool
    until_end: bool
    first_mask_change_ref: EntityRef
    first_pivot_change_ref: EntityRef
    first_style_change_ref: EntityRef
    first_transform_change_ref: EntityRef

    @property
    def index(self) -> int: ...


def _stage_mask_change_archetype() -> type[StageMaskChangeLike]:
    return cast(type[StageMaskChangeLike], get_archetype_by_name(archetype_names.STAGE_MASK_CHANGE))


def _stage_pivot_change_archetype() -> type[StagePivotChangeLike]:
    return cast(type[StagePivotChangeLike], get_archetype_by_name(archetype_names.STAGE_PIVOT_CHANGE))


def _stage_style_change_archetype() -> type[StageStyleChangeLike]:
    return cast(type[StageStyleChangeLike], get_archetype_by_name(archetype_names.STAGE_STYLE_CHANGE))


def _stage_transform_change_archetype() -> type[StageTransformChangeLike]:
    return cast(type[StageTransformChangeLike], get_archetype_by_name(archetype_names.STAGE_TRANSFORM_CHANGE))


def stage_y_offset_bounds(stage: DynamicStageLike) -> Interval:
    """Scan the stage's pivot offsets and return their full y offset range.

    Call after converting beat offsets into pivot.y_offset values. Easing keeps
    each offset between the two event values, so checking those values is enough.
    """
    ref = +stage.first_pivot_change_ref
    result = Interval(0.0, 0.0)
    if ref.index > 0:
        first = get_event_as(ref, _stage_pivot_change_archetype())
        result.start = first.y_offset
        result.end = first.y_offset
    while ref.index > 0:
        pivot = get_event_as(ref, _stage_pivot_change_archetype())
        result.start = min(result.start, pivot.y_offset)
        result.end = max(result.end, pivot.y_offset)
        ref.index = pivot.next_ref.index
    return result


def _stage_style_interval_visible(style: StageStyleChangeLike) -> bool:
    if style.next_ref.index <= 0:
        return style.note_alpha > 0
    following = get_event_as(style.next_ref, _stage_style_change_archetype())
    return following.time > style.time and (
        style.note_alpha > 0 or (style.ease != EaseType.NONE and following.note_alpha > 0)
    )


def initialize_stage_note_visibility(stage: DynamicStageLike) -> float:
    """Cache neighboring visibility boundaries and return the permanent cutoff.

    The first style also applies before its event time. Events at the same time
    can still set the ending alpha of the previous fade.

    Call after style times and the event list's previous links are initialized.
    """
    ref = +stage.first_style_change_ref
    if ref.index <= 0:
        return inf
    first = get_event_as(ref, _stage_style_change_archetype())
    result = first.time if first.note_alpha > 0 else -inf
    last_ref = +ref
    while ref.index > 0:
        style = get_event_as(ref, _stage_style_change_archetype())
        style.previous_note_visibility_end = result
        if _stage_style_interval_visible(style):
            if style.next_ref.index <= 0:
                result = inf
            else:
                result = get_event_as(style.next_ref, _stage_style_change_archetype()).time
        last_ref.index = ref.index
        ref.index = style.next_ref.index
    visibility_start = inf
    while last_ref.index > 0:
        style = get_event_as(last_ref, _stage_style_change_archetype())
        if _stage_style_interval_visible(style):
            visibility_start = style.time
        style.note_visibility_start = visibility_start
        last_ref.index = style.prev_ref.index
    return result


def stage_note_visibility_end_before(stage: DynamicStageLike, end: float, earliest: float = -inf) -> float:
    """Return the last potentially visible interval's end within [earliest, end), or earliest."""
    if end <= earliest:
        return earliest
    if stage.first_style_change_ref.index <= 0:
        return end
    ref, following_ref = query_event_list(stage.first_style_change_ref, end, lambda event: event.time)
    if ref.index > 0:
        style = get_event_as(ref, _stage_style_change_archetype())
        if end > style.time and style.note_visibility_start == style.time:
            return end
        return max(earliest, style.previous_note_visibility_end)
    first = get_event_as(following_ref, _stage_style_change_archetype())
    return end if first.note_alpha > 0 else earliest


def stage_note_visibility_start(stage: DynamicStageLike, start: float, latest: float = inf) -> float:
    """Return the next time at or after start when stage notes could be visible.

    Return latest if no potentially visible interval begins before it. If either
    end of a fade has positive alpha, treat the whole fade as potentially visible.
    """
    if start >= latest:
        return latest
    if stage.first_style_change_ref.index <= 0:
        return start
    ref, following_ref = query_event_list(stage.first_style_change_ref, start, lambda event: event.time)
    if ref.index <= 0:
        first = get_event_as(following_ref, _stage_style_change_archetype())
        if first.note_alpha > 0:
            return start
        ref.index = following_ref.index
    style = get_event_as(ref, _stage_style_change_archetype())
    return min(latest, max(start, style.note_visibility_start))


def center_anchor_weight(anchor: StageTransformAnchor) -> float:
    return 1.0 if anchor == StageTransformAnchor.CENTER else 0.0


def get_start_time(stage: DynamicStageLike) -> float:
    if stage.from_start:
        return -1e8
    result = 1e8
    if stage.first_mask_change_ref.index > 0:
        result = min(result, get_event_as(stage.first_mask_change_ref, _stage_mask_change_archetype()).time)
    if stage.first_pivot_change_ref.index > 0:
        result = min(result, get_event_as(stage.first_pivot_change_ref, _stage_pivot_change_archetype()).time)
    if stage.first_style_change_ref.index > 0:
        result = min(result, get_event_as(stage.first_style_change_ref, _stage_style_change_archetype()).time)
    if stage.first_transform_change_ref.index > 0:
        result = min(result, get_event_as(stage.first_transform_change_ref, _stage_transform_change_archetype()).time)
    return result


def get_end_time(stage: DynamicStageLike) -> float:
    if stage.until_end:
        return 1e8
    result = -1e8
    if stage.first_mask_change_ref.index > 0:
        last_ref, _ = query_event_list(stage.first_mask_change_ref, 1e8, lambda e: e.time)
        result = max(result, get_event_as(last_ref, _stage_mask_change_archetype()).time)
    if stage.first_pivot_change_ref.index > 0:
        last_ref, _ = query_event_list(stage.first_pivot_change_ref, 1e8, lambda e: e.time)
        result = max(result, get_event_as(last_ref, _stage_pivot_change_archetype()).time)
    if stage.first_style_change_ref.index > 0:
        last_ref, _ = query_event_list(stage.first_style_change_ref, 1e8, lambda e: e.time)
        result = max(result, get_event_as(last_ref, _stage_style_change_archetype()).time)
    if stage.first_transform_change_ref.index > 0:
        last_ref, _ = query_event_list(stage.first_transform_change_ref, 1e8, lambda e: e.time)
        result = max(result, get_event_as(last_ref, _stage_transform_change_archetype()).time)
    return result


def get_draw_start_time(stage: DynamicStageLike) -> float:
    if stage.from_start:
        return -1e8
    if stage.first_mask_change_ref.index > 0:
        return get_event_as(stage.first_mask_change_ref, _stage_mask_change_archetype()).time
    return 1e8


def get_draw_end_time(stage: DynamicStageLike) -> float:
    if stage.until_end:
        return 1e8
    if stage.first_mask_change_ref.index > 0:
        last_ref, _ = query_event_list(stage.first_mask_change_ref, 1e8, lambda e: e.time)
        return get_event_as(last_ref, _stage_mask_change_archetype()).time
    return -1e8


def get_next_event_time(stage: DynamicStageLike, t: float) -> float:
    result = 1e8
    if stage.first_mask_change_ref.index > 0:
        _, b_ref = query_event_list(stage.first_mask_change_ref, t, lambda e: e.time)
        if b_ref.index > 0:
            result = min(result, get_event_as(b_ref, _stage_mask_change_archetype()).time)
    if stage.first_pivot_change_ref.index > 0:
        _, b_ref = query_event_list(stage.first_pivot_change_ref, t, lambda e: e.time)
        if b_ref.index > 0:
            result = min(result, get_event_as(b_ref, _stage_pivot_change_archetype()).time)
    if stage.first_style_change_ref.index > 0:
        _, b_ref = query_event_list(stage.first_style_change_ref, t, lambda e: e.time)
        if b_ref.index > 0:
            result = min(result, get_event_as(b_ref, _stage_style_change_archetype()).time)
    if stage.first_transform_change_ref.index > 0:
        _, b_ref = query_event_list(stage.first_transform_change_ref, t, lambda e: e.time)
        if b_ref.index > 0:
            result = min(result, get_event_as(b_ref, _stage_transform_change_archetype()).time)
    return result


def get_stage_props(stage: DynamicStageLike, target_time: float | None = None, left_limit: bool = False) -> StageProps:
    t = target_time if target_time is not None else runtime.time()
    result = +StageProps
    result.note_alpha = 1.0
    result.mask_notes = False

    first_mask_change_ref = stage.first_mask_change_ref
    first_pivot_change_ref = stage.first_pivot_change_ref
    first_style_change_ref = stage.first_style_change_ref
    first_transform_change_ref = stage.first_transform_change_ref

    update_stage_mask_props(result, first_mask_change_ref, t, left_limit)

    update_stage_pivot_props(result, first_pivot_change_ref, t, left_limit)

    update_stage_style_props(result, first_style_change_ref, t, left_limit)

    update_stage_transform_props(result, first_transform_change_ref, t, left_limit)

    return result


def update_stage_mask_props(result: StageProps, first_mask_change_ref: EntityRef, t: float, left_limit: bool):
    mask_a_ref, mask_b_ref = query_event_list(first_mask_change_ref, t, lambda e: e.time)
    if left_limit and mask_a_ref.index > 0:
        mask_curr = get_event_as(mask_a_ref, _stage_mask_change_archetype())
        if mask_curr.time == t:
            # Find the first event at t so interpolation uses the value just before t.
            mask_probe_ref = +mask_curr.prev_ref
            while mask_probe_ref.index > 0:
                if get_event_as(mask_probe_ref, _stage_mask_change_archetype()).time != t:
                    break
                mask_a_ref.index = mask_probe_ref.index
                mask_probe_ref.index = get_event_as(mask_probe_ref, _stage_mask_change_archetype()).prev_ref.index
            mask_b_ref.index = mask_a_ref.index
            mask_a_ref.index = mask_probe_ref.index
    if mask_a_ref.index > 0:
        mask_a = get_event_as(mask_a_ref, _stage_mask_change_archetype())
        result.lane = mask_a.lane
        result.width = mask_a.size
        result.mask_notes = mask_a.mask_notes
        if mask_b_ref.index > 0:
            mask_b = get_event_as(mask_b_ref, _stage_mask_change_archetype())
            t_a = mask_a.time
            t_b = mask_b.time
            if t_b > t_a:
                p = ease(mask_a.ease, (t - t_a) / (t_b - t_a))
                result.lane = lerp(mask_a.lane, mask_b.lane, p)
                result.width = lerp(mask_a.size, mask_b.size, p)
    elif mask_b_ref.index > 0:
        mask_b = get_event_as(mask_b_ref, _stage_mask_change_archetype())
        result.lane = mask_b.lane
        result.width = mask_b.size
        result.mask_notes = mask_b.mask_notes


def update_stage_style_props(result: StageProps, first_style_change_ref: EntityRef, t: float, left_limit: bool):
    style_a_ref, style_b_ref = query_event_list(first_style_change_ref, t, lambda e: e.time)
    if left_limit and style_a_ref.index > 0:
        style_curr = get_event_as(style_a_ref, _stage_style_change_archetype())
        if style_curr.time == t:
            style_probe_ref = +style_curr.prev_ref
            while style_probe_ref.index > 0:
                if get_event_as(style_probe_ref, _stage_style_change_archetype()).time != t:
                    break
                style_a_ref.index = style_probe_ref.index
                style_probe_ref.index = get_event_as(style_probe_ref, _stage_style_change_archetype()).prev_ref.index
            style_b_ref.index = style_a_ref.index
            style_a_ref.index = style_probe_ref.index
    if style_a_ref.index > 0:
        style_a = get_event_as(style_a_ref, _stage_style_change_archetype())
        result.judge_line_color.start = style_a.judge_line_color
        result.judge_line_color.end = style_a.judge_line_color
        result.judge_line_style.start = style_a.judge_line_style
        result.judge_line_style.end = style_a.judge_line_style
        result.left_border_style.start = style_a.left_border_style
        result.left_border_style.end = style_a.left_border_style
        result.right_border_style.start = style_a.right_border_style
        result.right_border_style.end = style_a.right_border_style
        result.lane_alpha = style_a.lane_alpha
        result.judge_line_alpha = style_a.judge_line_alpha
        result.full_width = full_width_factor(style_a.full_width)
        result.division_line_alpha = style_a.division_line_alpha
        result.note_alpha = style_a.note_alpha
        if style_b_ref.index > 0:
            style_b = get_event_as(style_b_ref, _stage_style_change_archetype())
            t_a = style_a.time
            t_b = style_b.time
            if t_b > t_a:
                p = ease(style_a.ease, (t - t_a) / (t_b - t_a))
                result.judge_line_color.end = style_b.judge_line_color
                result.judge_line_color.progress = p
                result.judge_line_style.end = style_b.judge_line_style
                result.judge_line_style.progress = p
                result.left_border_style.end = style_b.left_border_style
                result.left_border_style.progress = p
                result.right_border_style.end = style_b.right_border_style
                result.right_border_style.progress = p
                result.lane_alpha = lerp(style_a.lane_alpha, style_b.lane_alpha, p)
                result.judge_line_alpha = lerp(style_a.judge_line_alpha, style_b.judge_line_alpha, p)
                result.full_width = lerp(
                    full_width_factor(style_a.full_width), full_width_factor(style_b.full_width), p
                )
                result.division_line_alpha = lerp(style_a.division_line_alpha, style_b.division_line_alpha, p)
                result.note_alpha = lerp(style_a.note_alpha, style_b.note_alpha, p)
    elif style_b_ref.index > 0:
        style_b = get_event_as(style_b_ref, _stage_style_change_archetype())
        result.judge_line_color.start = style_b.judge_line_color
        result.judge_line_color.end = style_b.judge_line_color
        result.judge_line_style.start = style_b.judge_line_style
        result.judge_line_style.end = style_b.judge_line_style
        result.left_border_style.start = style_b.left_border_style
        result.left_border_style.end = style_b.left_border_style
        result.right_border_style.start = style_b.right_border_style
        result.right_border_style.end = style_b.right_border_style
        result.lane_alpha = style_b.lane_alpha
        result.judge_line_alpha = style_b.judge_line_alpha
        result.full_width = full_width_factor(style_b.full_width)
        result.division_line_alpha = style_b.division_line_alpha
        result.note_alpha = style_b.note_alpha


def update_stage_transform_props(result: StageProps, first_transform_change_ref: EntityRef, t: float, left_limit: bool):
    transform_a_ref, transform_b_ref = query_event_list(first_transform_change_ref, t, lambda e: e.time)
    if left_limit and transform_a_ref.index > 0:
        transform_curr = get_event_as(transform_a_ref, _stage_transform_change_archetype())
        if transform_curr.time == t:
            transform_probe_ref = +transform_curr.prev_ref
            while transform_probe_ref.index > 0:
                if get_event_as(transform_probe_ref, _stage_transform_change_archetype()).time != t:
                    break
                transform_a_ref.index = transform_probe_ref.index
                transform_probe_ref.index = get_event_as(
                    transform_probe_ref, _stage_transform_change_archetype()
                ).prev_ref.index
            transform_b_ref.index = transform_a_ref.index
            transform_a_ref.index = transform_probe_ref.index
    if transform_a_ref.index > 0:
        transform_a = get_event_as(transform_a_ref, _stage_transform_change_archetype())
        result.rotate = transform_a.rotate
        result.x_lane_translate = transform_a.x_lane_translate
        result.y_lane_translate = transform_a.y_lane_translate
        result.elevation = transform_a.elevation
        result.center_weight = center_anchor_weight(transform_a.anchor)
        if transform_b_ref.index > 0:
            transform_b = get_event_as(transform_b_ref, _stage_transform_change_archetype())
            t_a = transform_a.time
            t_b = transform_b.time
            if t_b > t_a:
                p = ease(transform_a.ease, (t - t_a) / (t_b - t_a))
                result.rotate = lerp(transform_a.rotate, transform_b.rotate, p)
                result.x_lane_translate = lerp(transform_a.x_lane_translate, transform_b.x_lane_translate, p)
                result.y_lane_translate = lerp(transform_a.y_lane_translate, transform_b.y_lane_translate, p)
                result.elevation = lerp(transform_a.elevation, transform_b.elevation, p)
                result.center_weight = lerp(
                    center_anchor_weight(transform_a.anchor), center_anchor_weight(transform_b.anchor), p
                )
    elif transform_b_ref.index > 0:
        transform_b = get_event_as(transform_b_ref, _stage_transform_change_archetype())
        result.rotate = transform_b.rotate
        result.x_lane_translate = transform_b.x_lane_translate
        result.y_lane_translate = transform_b.y_lane_translate
        result.elevation = transform_b.elevation
        result.center_weight = center_anchor_weight(transform_b.anchor)


def get_stage_input_props(stage: DynamicStageLike, t: float) -> StageProps:
    result = +StageProps
    update_stage_mask_props(result, stage.first_mask_change_ref, t, True)
    update_stage_pivot_props(result, stage.first_pivot_change_ref, t, True)
    update_stage_transform_props(result, stage.first_transform_change_ref, t, True)
    return result


def update_stage_pivot_props(result: StageProps, first_pivot_change_ref: EntityRef, t: float, left_limit: bool):
    pivot_a_ref, pivot_b_ref = query_event_list(first_pivot_change_ref, t, lambda e: e.time)
    if left_limit and pivot_a_ref.index > 0:
        pivot_curr = get_event_as(pivot_a_ref, _stage_pivot_change_archetype())
        if pivot_curr.time == t:
            pivot_probe_ref = +pivot_curr.prev_ref
            while pivot_probe_ref.index > 0:
                if get_event_as(pivot_probe_ref, _stage_pivot_change_archetype()).time != t:
                    break
                pivot_a_ref.index = pivot_probe_ref.index
                pivot_probe_ref.index = get_event_as(pivot_probe_ref, _stage_pivot_change_archetype()).prev_ref.index
            pivot_b_ref.index = pivot_a_ref.index
            pivot_a_ref.index = pivot_probe_ref.index
    if pivot_a_ref.index > 0:
        pivot_a = get_event_as(pivot_a_ref, _stage_pivot_change_archetype())
        result.pivot_lane = pivot_a.lane
        result.division.start.size = int(pivot_a.division_size)
        result.division.start.parity = pivot_a.division_parity
        result.division.end @= result.division.start
        result.y_offset = pivot_a.y_offset
        if pivot_b_ref.index > 0:
            pivot_b = get_event_as(pivot_b_ref, _stage_pivot_change_archetype())
            t_a = pivot_a.time
            t_b = pivot_b.time
            if t_b > t_a:
                p = ease(pivot_a.ease, (t - t_a) / (t_b - t_a))
                result.pivot_lane = lerp(pivot_a.lane, pivot_b.lane, p)
                result.division.end.size = int(pivot_b.division_size)
                result.division.end.parity = pivot_b.division_parity
                result.division.progress = p
                result.y_offset = lerp(pivot_a.y_offset, pivot_b.y_offset, p)
    elif pivot_b_ref.index > 0:
        pivot_b = get_event_as(pivot_b_ref, _stage_pivot_change_archetype())
        result.pivot_lane = pivot_b.lane
        result.division.start.size = int(pivot_b.division_size)
        result.division.start.parity = pivot_b.division_parity
        result.division.end @= result.division.start
        result.y_offset = pivot_b.y_offset


def get_stage_pivot_lane(stage: DynamicStageLike, t: float) -> float:
    props = +StageProps
    update_stage_pivot_props(props, stage.first_pivot_change_ref, t, False)
    return props.pivot_lane


def get_stage_y_offset(stage: DynamicStageLike, t: float, left_limit: bool = False) -> float:
    props = +StageProps
    update_stage_pivot_props(props, stage.first_pivot_change_ref, t, left_limit)
    return props.y_offset


def masked_note_extents(lane: float, size: float, props: StageProps, x_translate: float = 0.0) -> tuple[float, float]:
    """Return the masked visual lane and half-width."""
    return masked_note_extents_by_limits(
        lane,
        size,
        props.lane - props.width + x_translate,
        props.lane + props.width + x_translate,
        props.mask_notes,
    )


def masked_note_extents_by_limits(
    lane: float, size: float, mask_left: float, mask_right: float, mask_notes: bool
) -> tuple[float, float]:
    result_lane = lane
    result_size = size
    if mask_notes:
        left = clamp(lane - size, mask_left, mask_right)
        right = clamp(lane + size, mask_left, mask_right)
        result_lane = (left + right) / 2
        result_size = (right - left) / 2
    return result_lane, result_size


TEST_ASPECT_BOX_EDGE = 0.004


def draw_aspect_box(sprite: Sprite, ratio: float, sub: int):
    if not stage_aspect_ratio_locked():
        return
    hf = TEST_ASPECT_SCALE * Layout.field_h / 2
    wf = TEST_ASPECT_SCALE * Layout.field_w / 2
    if ratio < wf / hf:
        hw = wf
        hh = wf / ratio
    else:
        hw = ratio * hf
        hh = hf
    e = TEST_ASPECT_BOX_EDGE
    top = Rect(l=-hw - e, r=hw + e, t=hh + e, b=hh - e)
    bottom = Rect(l=-hw - e, r=hw + e, t=-hh + e, b=-hh - e)
    left = Rect(l=-hw - e, r=-hw + e, t=hh, b=-hh)
    right = Rect(l=hw - e, r=hw + e, t=hh, b=-hh)
    sprite.draw(top.as_quad(), z=get_z_alt(layers.overlay, 1000 + 4 * sub).tuple, a=1.0)
    sprite.draw(bottom.as_quad(), z=get_z_alt(layers.overlay, 1000 + 4 * sub + 1).tuple, a=1.0)
    sprite.draw(left.as_quad(), z=get_z_alt(layers.overlay, 1000 + 4 * sub + 2).tuple, a=1.0)
    sprite.draw(right.as_quad(), z=get_z_alt(layers.overlay, 1000 + 4 * sub + 3).tuple, a=1.0)


def draw_test_aspect_overlay():
    if not test_aspect_active():
        return
    draw_aspect_box(ActiveSkin.guide_red, 21 / 9, 0)
    draw_aspect_box(ActiveSkin.guide_blue, 4 / 3, 1)
    draw_aspect_box(ActiveSkin.guide_green, 16 / 9, 2)


def draw_stage_and_accessories(
    ap: bool,
    score: float,
    note_score: float,
    note_time: float,
    percentage: float,
    background_cover: Quad,
    dead_effect_quads: Array[Quad, Dim[4]],
    ui_layout: StaticUiLayout,
    life: float = 1000.0,
    last_time: float = 1e8,
    dead_time: float = 1e8,
    layout_stage: Quad = Quad.zero(),  # noqa: B008
):
    ui_alpha = 1.0
    if Options.ui_intro and time() < -1.0:
        ui_alpha = unlerp_clamped(-2.0, -1.0, time())
    if not LevelConfig.skip_default_stage:
        draw_basic_stage(ui_alpha, layout_stage)
    draw_stage_cover(ui_alpha)
    draw_test_aspect_overlay()
    draw_auto_play(ui_layout)
    draw_background_cover(background_cover)
    draw_dead(life, dead_time, background_cover, dead_effect_quads)
    draw_score_number(
        ap=ap,
        score=percentage,
        alpha=ui_alpha,
    )
    draw_life_bar(
        life,
        last_time,
        ui_layout,
        alpha=ui_alpha,
    )
    draw_score_bar(
        score,
        note_score,
        note_time,
        ui_layout,
        alpha=ui_alpha,
    )


def normalize_transition[T](value: Transition[T] | T) -> Transition[T]:
    if isinstance(value, Transition):
        return value
    return Transition(start=value, end=value, progress=0)


def draw_basic_stage(alpha=1.0, layout=Quad.zero()):  # noqa: B008
    if not Options.show_lane:
        return
    if (
        ActiveSkin.sekai_stage_lane.is_available
        and ActiveSkin.sekai_stage_cover.is_available
        and not LevelConfig.dynamic_stages
    ):
        draw_sekai_divided_stage(LAYER_STAGE_LANE, LAYER_COVER, alpha, layout)
    else:
        draw_dynamic_stage(
            lane=0,
            width=6,
            pivot_lane=0,
            division=DivisionProps(size=2, parity=DivisionParity.EVEN),
            judge_line_color=JudgeLineColor.PURPLE,
            left_border_style=StageBorderStyle.DEFAULT,
            right_border_style=StageBorderStyle.DEFAULT,
            order=0,
            lane_alpha=alpha,
            judge_line_alpha=alpha,
            transform=IDENTITY_STAGE_SCREEN_TRANSFORM,
        )


def draw_sekai_stage(z_stage, alpha):
    layout = layout_sekai_stage()
    ActiveSkin.sekai_stage.draw(layout, z=z_stage, a=alpha)


def draw_sekai_divided_stage(z_stage_lane, z_stage_cover, alpha, layout):
    resolved = +Quad
    if layout == Quad.zero():
        resolved @= layout_sekai_stage()
    else:
        resolved @= layout
    ActiveSkin.sekai_stage_lane.draw(resolved, z=get_z(z_stage_lane).tuple, a=alpha)
    if Options.lane_alpha > 0:
        ActiveSkin.sekai_stage_cover.draw(resolved, z=get_z(z_stage_cover).tuple, a=Options.lane_alpha * alpha)


def get_judgment_sprites(judge_line_color: JudgeLineColor) -> JudgmentSpriteSet:
    result = +JudgmentSpriteSet
    match judge_line_color:
        case JudgeLineColor.NEUTRAL:
            result @= ActiveSkin.judgment_neutral
        case JudgeLineColor.RED:
            result @= ActiveSkin.judgment_red
        case JudgeLineColor.GREEN:
            result @= ActiveSkin.judgment_green
        case JudgeLineColor.BLUE:
            result @= ActiveSkin.judgment_blue
        case JudgeLineColor.YELLOW:
            result @= ActiveSkin.judgment_yellow
        case JudgeLineColor.PURPLE:
            result @= ActiveSkin.judgment_purple
        case JudgeLineColor.CYAN:
            result @= ActiveSkin.judgment_cyan
        case JudgeLineColor.BLACK:
            result @= ActiveSkin.judgment_black
        case _:
            assert_never(judge_line_color)
    return result


def draw_dynamic_stage(
    lane: float,
    width: float,
    pivot_lane: float,
    division: Transition[DivisionProps] | DivisionProps,
    judge_line_color: Transition[JudgeLineColor] | JudgeLineColor,
    left_border_style: Transition[StageBorderStyle] | StageBorderStyle,
    right_border_style: Transition[StageBorderStyle] | StageBorderStyle,
    order: int,
    lane_alpha: float = 1,
    judge_line_alpha: float = 1,
    y_offset: float = 0,
    alpha: float = 1,
    judge_line_style: Transition[JudgeLineStyle] | JudgeLineStyle = JudgeLineStyle.DEFAULT,
    full_width: float = 0,
    division_line_alpha: float = 1,
    *,
    transform: StageScreenTransform,
):
    division = normalize_transition(division)
    judge_line_color = normalize_transition(judge_line_color)
    judge_line_style = normalize_transition(judge_line_style)
    left_border_style = normalize_transition(left_border_style)
    right_border_style = normalize_transition(right_border_style)

    def place(q: QuadLike) -> QuadLike:
        return transform.transform_quad(q)

    sprites_same = judge_line_color.start == judge_line_color.end
    sprites_a = get_judgment_sprites(judge_line_color.start)
    sprites_b = get_judgment_sprites(judge_line_color.end)
    p_sprites = 0.0 if sprites_same else judge_line_color.progress

    w_default = judge_line_style_weight(judge_line_style, JudgeLineStyle.DEFAULT)
    w_single_line = judge_line_style_weight(judge_line_style, JudgeLineStyle.SINGLE_LINE)
    fw = clamp(full_width, 0, 1)

    if not ActiveSkin.lane_background.is_available:
        draw_fallback_stage(
            lane,
            width,
            division.end.size,
            division.end.parity,
            pivot_lane,
            order,
            lane_alpha,
            judge_line_alpha,
            y_offset,
            alpha,
            judge_line_style,
            fw,
            left_border_style=left_border_style,
            right_border_style=right_border_style,
            transform=transform,
        )
        return

    travel = approach(1 - y_offset)
    nh = DynamicLayout.note_h
    l = lane - width
    r = lane + width
    half_jl = lerp(width, FULL_WIDTH_HALF_EXTENT, fw)
    l_jl = lane - half_jl
    r_jl = lane + half_jl
    z_bg0 = get_z_alt(layers.stage, order * 17, elevation=transform.elevation)
    z_bg1_a = get_z_alt(layers.stage, order * 17 + 1, elevation=transform.elevation)
    z_bg1_b = get_z_alt(layers.stage, order * 17 + 2, elevation=transform.elevation)
    z_lane0 = get_z_alt(layers.stage, order * 17 + 3, elevation=transform.elevation)
    z_lane1 = get_z_alt(layers.stage, order * 17 + 4, elevation=transform.elevation)
    z_a0 = get_z_alt(layers.stage, order * 17 + 5, elevation=transform.elevation)
    z_a1 = get_z_alt(layers.stage, order * 17 + 6, elevation=transform.elevation)
    z_a2 = get_z_alt(layers.stage, order * 17 + 7, elevation=transform.elevation)
    z_a3 = get_z_alt(layers.stage, order * 17 + 8, elevation=transform.elevation)
    z_b0 = get_z_alt(layers.stage, order * 17 + 9, elevation=transform.elevation)
    z_b1 = get_z_alt(layers.stage, order * 17 + 10, elevation=transform.elevation)
    z_b2 = get_z_alt(layers.stage, order * 17 + 11, elevation=transform.elevation)
    z_b3 = get_z_alt(layers.stage, order * 17 + 12, elevation=transform.elevation)
    z_a4 = get_z_alt(layers.stage, order * 17 + 13, elevation=transform.elevation)
    z_b4 = get_z_alt(layers.stage, order * 17 + 14, elevation=transform.elevation)
    z_single_a = get_z_alt(layers.stage, order * 17 + 15, elevation=transform.elevation)
    z_single_b = get_z_alt(layers.stage, order * 17 + 16, elevation=transform.elevation)

    f = 5  # sizing factor for judge line border

    def layout_lane_border(style: StageBorderStyle, edge: float, is_left: bool) -> Quad:
        border_w = border_style_width(style, 0.08, 0.04, 0.025)
        if style == StageBorderStyle.LIGHT:
            left = edge - border_w / 2
            right = edge + border_w / 2
        elif is_left:
            left = edge - border_w
            right = edge
        else:
            left = edge
            right = edge + border_w
        bottom = layout_stage_lane_by_edges(left, right)
        top = layout_stage_lane_by_edges(
            tilt_widened_edge(left, edge + 8 * (left - edge)),
            tilt_widened_edge(right, edge + 8 * (right - edge)),
        )
        return Quad(bl=bottom.bl, br=bottom.br, tl=top.tl, tr=top.tr)

    left_border_layout = blend_border_layout(
        layout_lane_border(left_border_style.start, l, True),
        layout_lane_border(left_border_style.end, l, True),
        left_border_style.progress,
    )
    right_border_layout = blend_border_layout(
        layout_lane_border(right_border_style.start, r, False),
        layout_lane_border(right_border_style.end, r, False),
        right_border_style.progress,
    )

    def draw_border(style: StageBorderStyle, is_left: bool, q: Quad, z: ZIndexes, a: float):
        if a <= 0 or (q.bl == q.br and q.tl == q.tr):
            return
        match style:
            case StageBorderStyle.DEFAULT | StageBorderStyle.MEDIUM:
                if not is_left:
                    q = Quad(bl=q.br, br=q.bl, tl=q.tr, tr=q.tl)
                ActiveSkin.stage_border.draw(place(q), z=z.tuple, a=a)
            case StageBorderStyle.LIGHT:
                ActiveSkin.lane_divider.draw(place(q), z=z.tuple, a=a)
            case StageBorderStyle.DISABLED:
                pass
            case _:
                assert_never(style)

    def draw_dividers(division_size: int, parity: DivisionParity, pivot: float, z: ZIndexes, a: float):
        eps = 0.001
        parity_offset = division_size / 2 if parity == DivisionParity.ODD else 0
        shifted_pivot = pivot + parity_offset

        if division_size <= 0:
            return

        k_start = floor((l - shifted_pivot + eps) / division_size) + 1
        k_end = ceil((r - shifted_pivot - eps) / division_size) - 1

        for k in range(k_start, k_end + 1):
            pos = shifted_pivot + k * division_size
            div_layout_b = layout_stage_lane_by_edges(pos - 0.0125, pos + 0.0125)
            div_layout_t = layout_stage_lane_by_edges(
                tilt_widened_edge(pos - 0.0125, pos - 0.1), tilt_widened_edge(pos + 0.0125, pos + 0.1)
            )
            ActiveSkin.lane_divider.draw(
                place(Quad(bl=div_layout_b.bl, tl=div_layout_t.tl, tr=div_layout_t.tr, br=div_layout_b.br)),
                z=z.tuple,
                a=a,
            )

    thickness_scale = lerp(1.0, clamp(1 / travel, 1, 4) if travel > 0 else 4, current_stage_tilt())
    judgment_divider_size = 0.014 * thickness_scale * tilt_width_factor(travel) * DynamicLayout.w_scale
    divider_depth_b = tilt_depth(1 + nh - nh / f + 0.001, travel)
    divider_depth_t = tilt_depth(1 - nh + nh / f - 0.001, travel)

    def layout_judgment_divider(lane: float, half_width: float):
        offset = Vec2(half_width, 0).rotate(-DynamicLayout.rotate)
        b = transformed_vec_at(lane, divider_depth_b)
        t = transformed_vec_at(lane, divider_depth_t)
        return Quad(
            bl=b - offset,
            tl=t - offset,
            tr=t + offset,
            br=b + offset,
        )

    def draw_judgment_dividers(
        sprites: JudgmentSpriteSet, half_offset: bool, pivot: float, z_lo: ZIndexes, z_hi: ZIndexes, a: float
    ):
        eps = 0.001
        shifted_pivot = pivot + (0.5 if half_offset else 0)

        k_start = floor(l - shifted_pivot + eps) + 1
        k_end = ceil(r - shifted_pivot - eps) - 1

        for k in range(k_start, k_end + 1):
            pos = shifted_pivot + k
            div_layout = place(layout_judgment_divider(pos, judgment_divider_size))
            edge_weight = abs(pos - lane) / width if width > 0 else 0
            sprites.judgment_center.draw(div_layout, z=z_lo.tuple, a=a)
            sprites.judgment_edge.draw(div_layout, z=z_hi.tuple, a=a * edge_weight)

    def layout_judgment_border(style: StageBorderStyle, edge: float, is_left: bool) -> Quad:
        result = +Quad
        if style == StageBorderStyle.LIGHT:
            result @= layout_judgment_divider(edge, judgment_divider_size)
        else:
            border_w = max(0.0, min(1 / f / 2, width)) if style != StageBorderStyle.DISABLED else 0.0
            result @= perspective_rect(
                edge if is_left else edge - border_w,
                edge + border_w if is_left else edge,
                1 - nh + nh / f,
                1 + nh - nh / f,
                travel,
            )
        return result

    left_judgment_layout = blend_border_layout(
        layout_judgment_border(left_border_style.start, l, True),
        layout_judgment_border(left_border_style.end, l, True),
        left_border_style.progress,
    )
    right_judgment_layout = blend_border_layout(
        layout_judgment_border(right_border_style.start, r, False),
        layout_judgment_border(right_border_style.end, r, False),
        right_border_style.progress,
    )
    left_border_style = border_sprite_transition(left_border_style)
    right_border_style = border_sprite_transition(right_border_style)

    def draw_judgment_border(
        sprites: JudgmentSpriteSet, style: StageBorderStyle, is_left: bool, q: Quad, z: ZIndexes, a: float
    ):
        if a <= 0 or (q.bl == q.br and q.tl == q.tr):
            return
        match style:
            case StageBorderStyle.DEFAULT | StageBorderStyle.MEDIUM:
                if not is_left:
                    q = Quad(bl=q.br, br=q.bl, tl=q.tr, tr=q.tl)
                sprites.judgment_edge_left.draw(place(q), z=z.tuple, a=a)
            case StageBorderStyle.LIGHT:
                sprites.judgment_edge.draw(place(q), z=z.tuple, a=a)
            case StageBorderStyle.DISABLED:
                pass
            case _:
                assert_never(style)

    def draw_gradient(sprites: JudgmentSpriteSet, z: ZIndexes, a: float):
        bottom_l = place(perspective_rect(l_jl, lane, 1 + nh, 1 + nh - nh / f, travel))
        bottom_r = place(perspective_rect(r_jl, lane, 1 + nh, 1 + nh - nh / f, travel))
        top_l = place(perspective_rect(l_jl, lane, 1 - nh, 1 - nh + nh / f, travel))
        top_r = place(perspective_rect(r_jl, lane, 1 - nh, 1 - nh + nh / f, travel))
        grad_a = a * (1 - fw)
        edge_a = a * fw
        if grad_a > 0:
            sprites.judgment_gradient.draw(bottom_l, z=z.tuple, a=grad_a)
            sprites.judgment_gradient.draw(bottom_r, z=z.tuple, a=grad_a)
            sprites.judgment_gradient.draw(top_l, z=z.tuple, a=grad_a)
            sprites.judgment_gradient.draw(top_r, z=z.tuple, a=grad_a)
        if edge_a > 0:
            sprites.judgment_edge.draw(bottom_l, z=z.tuple, a=edge_a)
            sprites.judgment_edge.draw(bottom_r, z=z.tuple, a=edge_a)
            sprites.judgment_edge.draw(top_l, z=z.tuple, a=edge_a)
            sprites.judgment_edge.draw(top_r, z=z.tuple, a=edge_a)

    def draw_single_line(sprites: JudgmentSpriteSet, z: ZIndexes, a: float):
        half_thick = nh / f / 2
        layout = place(perspective_rect(l_jl, r_jl, 1 - half_thick, 1 + half_thick, travel))
        sprites.judgment_single_line.draw(layout, z=z.tuple, a=a)

    la = lane_alpha * (1 - fw)
    if la > 0:
        ActiveSkin.lane_background.draw(place(layout_stage_lane_by_edges(l, r)), z=z_bg0.tuple, a=la)

        p_left = left_border_style.progress
        if left_border_style.start == left_border_style.end:
            draw_border(left_border_style.start, True, left_border_layout, z_lane0, la)
        else:
            draw_border(left_border_style.start, True, left_border_layout, z_lane0, border_blend_alpha(la, p_left))
            draw_border(left_border_style.end, True, left_border_layout, z_lane1, la * p_left)

        p_right = right_border_style.progress
        if right_border_style.start == right_border_style.end:
            draw_border(right_border_style.start, False, right_border_layout, z_lane0, la)
        else:
            draw_border(right_border_style.start, False, right_border_layout, z_lane0, border_blend_alpha(la, p_right))
            draw_border(right_border_style.end, False, right_border_layout, z_lane1, la * p_right)

        la_div = la * division_line_alpha
        if la_div > 0:
            p_div = division.progress
            if division.start == division.end:
                draw_dividers(division.start.size, division.start.parity, pivot_lane, z_lane0, la_div)
            else:
                if 1 - p_div > 0:
                    draw_dividers(division.start.size, division.start.parity, pivot_lane, z_lane0, la_div * (1 - p_div))
                if p_div > 0:
                    draw_dividers(division.end.size, division.end.parity, pivot_lane, z_lane1, la_div * p_div)

    ja = judge_line_alpha
    ja_bar = ja * w_default
    ja_dec = ja_bar * (1 - fw)
    ja_single = ja * w_single_line

    if ja_bar > 0:
        bg_layout = place(perspective_rect(l_jl, r_jl, 1 - nh, 1 + nh, travel))
        if sprites_same:
            sprites_a.judgment_background.draw(bg_layout, z=z_bg1_a.tuple, a=ja_bar)
        else:
            sprites_a.judgment_background.draw(bg_layout, z=z_bg1_a.tuple, a=ja_bar * (1 - p_sprites))
            sprites_b.judgment_background.draw(bg_layout, z=z_bg1_b.tuple, a=ja_bar * p_sprites)

    p_left = left_border_style.progress
    p_right = right_border_style.progress
    p_div = division.progress

    start_has_half_offset = division.start.parity == DivisionParity.ODD and division.start.size % 2 == 1
    end_has_half_offset = division.end.parity == DivisionParity.ODD and division.end.size % 2 == 1
    judgment_dividers_same = start_has_half_offset == end_has_half_offset

    if ja_dec > 0:
        if judgment_dividers_same and sprites_same:
            draw_judgment_dividers(sprites_a, start_has_half_offset, pivot_lane, z_a0, z_a1, ja_dec)
        elif judgment_dividers_same:
            draw_judgment_dividers(sprites_a, start_has_half_offset, pivot_lane, z_a0, z_a1, ja_dec * (1 - p_sprites))
            draw_judgment_dividers(sprites_b, start_has_half_offset, pivot_lane, z_b0, z_b1, ja_dec * p_sprites)
        elif sprites_same:
            draw_judgment_dividers(sprites_a, start_has_half_offset, pivot_lane, z_a0, z_a1, ja_dec * (1 - p_div))
            draw_judgment_dividers(sprites_a, end_has_half_offset, pivot_lane, z_a2, z_a3, ja_dec * p_div)
        else:
            alpha_aa = (1 - p_sprites) * (1 - p_div)
            alpha_ab = (1 - p_sprites) * p_div
            alpha_ba = p_sprites * (1 - p_div)
            alpha_bb = p_sprites * p_div
            if alpha_aa > 0:
                draw_judgment_dividers(sprites_a, start_has_half_offset, pivot_lane, z_a0, z_a1, ja_dec * alpha_aa)
            if alpha_ab > 0:
                draw_judgment_dividers(sprites_a, end_has_half_offset, pivot_lane, z_a2, z_a3, ja_dec * alpha_ab)
            if alpha_ba > 0:
                draw_judgment_dividers(sprites_b, start_has_half_offset, pivot_lane, z_b0, z_b1, ja_dec * alpha_ba)
            if alpha_bb > 0:
                draw_judgment_dividers(sprites_b, end_has_half_offset, pivot_lane, z_b2, z_b3, ja_dec * alpha_bb)

    if ja_bar > 0:
        if sprites_same:
            draw_gradient(sprites_a, z_a4, ja_bar)
        else:
            draw_gradient(sprites_a, z_a4, ja_bar * (1 - p_sprites))
            draw_gradient(sprites_b, z_b4, ja_bar * p_sprites)

    if ja_dec > 0:
        if sprites_same and left_border_style.start == left_border_style.end:
            draw_judgment_border(sprites_a, left_border_style.start, True, left_judgment_layout, z_a0, ja_dec)
        else:
            alpha_aa = border_blend_alpha(ja_dec * (1 - p_sprites), p_left)
            alpha_ab = ja_dec * (1 - p_sprites) * p_left
            alpha_ba = border_blend_alpha(ja_dec * p_sprites, p_left)
            alpha_bb = ja_dec * p_sprites * p_left
            if alpha_aa > 0:
                draw_judgment_border(sprites_a, left_border_style.start, True, left_judgment_layout, z_a0, alpha_aa)
            if alpha_ab > 0:
                draw_judgment_border(sprites_a, left_border_style.end, True, left_judgment_layout, z_a2, alpha_ab)
            if alpha_ba > 0:
                draw_judgment_border(sprites_b, left_border_style.start, True, left_judgment_layout, z_b0, alpha_ba)
            if alpha_bb > 0:
                draw_judgment_border(sprites_b, left_border_style.end, True, left_judgment_layout, z_b2, alpha_bb)

        if sprites_same and right_border_style.start == right_border_style.end:
            draw_judgment_border(sprites_a, right_border_style.start, False, right_judgment_layout, z_a0, ja_dec)
        else:
            alpha_aa = border_blend_alpha(ja_dec * (1 - p_sprites), p_right)
            alpha_ab = ja_dec * (1 - p_sprites) * p_right
            alpha_ba = border_blend_alpha(ja_dec * p_sprites, p_right)
            alpha_bb = ja_dec * p_sprites * p_right
            if alpha_aa > 0:
                draw_judgment_border(sprites_a, right_border_style.start, False, right_judgment_layout, z_a0, alpha_aa)
            if alpha_ab > 0:
                draw_judgment_border(sprites_a, right_border_style.end, False, right_judgment_layout, z_a2, alpha_ab)
            if alpha_ba > 0:
                draw_judgment_border(sprites_b, right_border_style.start, False, right_judgment_layout, z_b0, alpha_ba)
            if alpha_bb > 0:
                draw_judgment_border(sprites_b, right_border_style.end, False, right_judgment_layout, z_b2, alpha_bb)

    if ja_single > 0:
        if sprites_same:
            draw_single_line(sprites_a, z_single_a, ja_single)
        else:
            draw_single_line(sprites_a, z_single_a, ja_single * (1 - p_sprites))
            draw_single_line(sprites_b, z_single_b, ja_single * p_sprites)

    draw_per_stage_cover(l, r, lane_alpha, alpha, order, transform)


def draw_fallback_stage(
    lane: float,
    width: float,
    division_size: int,
    parity: DivisionParity,
    pivot: float,
    order: int,
    lane_alpha: float = 1,
    judge_line_alpha: float = 1,
    y_offset: float = 0,
    alpha: float = 1,
    judge_line_style: Transition[JudgeLineStyle] | JudgeLineStyle = JudgeLineStyle.DEFAULT,
    full_width: float = 0,
    *,
    left_border_style: Transition[StageBorderStyle] | StageBorderStyle = StageBorderStyle.DEFAULT,
    right_border_style: Transition[StageBorderStyle] | StageBorderStyle = StageBorderStyle.DEFAULT,
    transform: StageScreenTransform,
):
    def place(q: QuadLike) -> QuadLike:
        return transform.transform_quad(q)

    judge_line_style = normalize_transition(judge_line_style)
    w_default = judge_line_style_weight(judge_line_style, JudgeLineStyle.DEFAULT)
    w_single_line = judge_line_style_weight(judge_line_style, JudgeLineStyle.SINGLE_LINE)
    travel = approach(1 - y_offset)
    nh = DynamicLayout.note_h
    l = lane - width
    r = lane + width
    fw = clamp(full_width, 0, 1)
    half_jl = lerp(width, FULL_WIDTH_HALF_EXTENT, fw)
    l_jl = lane - half_jl
    r_jl = lane + half_jl
    z_lo = get_z_alt(layers.stage, order * 4, elevation=transform.elevation)
    z_mid = get_z_alt(layers.stage, order * 4 + 1, elevation=transform.elevation)
    z_hi = get_z_alt(layers.stage, order * 4 + 2, elevation=transform.elevation)
    z_single = get_z_alt(layers.stage, order * 4 + 3, elevation=transform.elevation)
    la = lane_alpha * (1 - fw)
    ja = judge_line_alpha
    left_width = border_width(normalize_transition(left_border_style), 0.25, 0.125, 0.025)
    right_width = border_width(normalize_transition(right_border_style), 0.25, 0.125, 0.025)
    if la > 0:
        if left_width > 0:
            layout_b = layout_stage_lane_by_edges(l - left_width, l)
            layout_t = layout_stage_lane_by_edges(tilt_widened_edge(l - left_width, l - 4 * left_width), l)
            ActiveSkin.stage_left_border.draw(
                place(Quad(bl=layout_b.bl, tl=layout_t.tl, tr=layout_t.tr, br=layout_b.br)), z=z_mid.tuple, a=la
            )
        if right_width > 0:
            layout_b = layout_stage_lane_by_edges(r, r + right_width)
            layout_t = layout_stage_lane_by_edges(r, tilt_widened_edge(r + right_width, r + 4 * right_width))
            ActiveSkin.stage_right_border.draw(
                place(Quad(bl=layout_b.bl, tl=layout_t.tl, tr=layout_t.tr, br=layout_b.br)), z=z_mid.tuple, a=la
            )

        eps = 0.001
        parity_offset = division_size / 2 if parity == DivisionParity.ODD else 0
        shifted_pivot = pivot + parity_offset
        prev = l
        if division_size > 0:
            k_start = floor((l - shifted_pivot + eps) / division_size) + 1
            k_end = ceil((r - shifted_pivot - eps) / division_size) - 1
            for k in range(k_start, k_end + 1):
                pos = shifted_pivot + k * division_size
                ActiveSkin.lane.draw(place(layout_stage_lane_by_edges(prev, pos)), a=la, z=z_lo.tuple)
                prev = pos
        ActiveSkin.lane.draw(place(layout_stage_lane_by_edges(prev, r)), a=la, z=z_lo.tuple)

    if ja * w_default > 0:
        layout = place(perspective_rect(l_jl, r_jl, t=1 - nh, b=1 + nh, travel=travel))
        ActiveSkin.judgment_line.draw(layout, z=z_hi.tuple, a=ja * w_default)
    if ja * w_single_line > 0:
        half_thick = nh / JUDGE_LINE_BORDER_FACTOR / 2
        layout = place(perspective_rect(l_jl, r_jl, t=1 - half_thick, b=1 + half_thick, travel=travel))
        ActiveSkin.judgment_line.draw(layout, z=z_single.tuple, a=ja * w_single_line)

    draw_per_stage_cover(l, r, lane_alpha, alpha, order, transform)


def draw_per_stage_cover(
    l: float,
    r: float,
    lane_alpha: float,
    alpha: float,
    order: int,
    transform: StageScreenTransform,
):
    if not LevelConfig.dynamic_stages:
        return
    ca = lane_alpha
    if ca <= 0:
        return

    def place(q: QuadLike) -> QuadLike:
        return transform.transform_quad(q)

    z_cover = get_z_alt(layers.cover, order * 4, elevation=transform.elevation)
    z_line = get_z_alt(layers.cover, order * 4 + 1, elevation=transform.elevation)
    z_hidden = get_z_alt(layers.cover, order * 4 + 2, elevation=transform.elevation)
    if stage_cover_amount() > 0:
        match Options.stage_cover_mode:
            case StageCoverMode.STAGE:
                layout = layout_stage_cover(l, r)
                ActiveSkin.cover.draw(place(layout), z=z_cover.tuple, a=Options.stage_cover_alpha * ca * alpha)
            case StageCoverMode.STAGE_AND_LINE:
                cover_layout, line_layout = layout_stage_cover_and_line(l, r)
                ActiveSkin.cover.draw(place(cover_layout), z=z_cover.tuple, a=Options.stage_cover_alpha * ca * alpha)
                ActiveSkin.guide_neutral.draw(place(line_layout), z=z_line.tuple, a=0.75 * ca * alpha)
            case StageCoverMode.FULL_WIDTH:
                pass
            case _:
                assert_never(Options.stage_cover_mode)
    if hidden_amount() > 0:
        layout = layout_hidden_cover(l, r)
        ActiveSkin.cover.draw(place(layout), z=z_hidden.tuple, a=ca * alpha)


def draw_stage_cover(alpha):
    if stage_cover_amount() > 0:
        match Options.stage_cover_mode:
            case StageCoverMode.STAGE:
                if not LevelConfig.dynamic_stages:
                    layout = layout_stage_cover()
                    ActiveSkin.cover.draw(layout, z=get_z(LAYER_COVER).tuple, a=Options.stage_cover_alpha * alpha)
            case StageCoverMode.STAGE_AND_LINE:
                if not LevelConfig.dynamic_stages:
                    cover_layout, line_layout = layout_stage_cover_and_line()
                    ActiveSkin.cover.draw(cover_layout, z=get_z(LAYER_COVER).tuple, a=Options.stage_cover_alpha * alpha)
                    ActiveSkin.guide_neutral.draw(line_layout, z=get_z(LAYER_COVER, etc=1).tuple, a=0.75 * alpha)
            case StageCoverMode.FULL_WIDTH:
                layout = layout_full_width_stage_cover()
                ActiveSkin.cover.draw(layout, z=get_z(LAYER_COVER).tuple, a=Options.stage_cover_alpha * alpha)
            case _:
                assert_never(Options.stage_cover_mode)
    if hidden_amount() > 0 and not LevelConfig.dynamic_stages:
        layout = layout_hidden_cover()
        ActiveSkin.cover.draw(layout, z=get_z(LAYER_COVER).tuple, a=alpha)


def draw_background_cover(background_cover):
    if Options.background_alpha != 1:
        ActiveSkin.background.draw(
            background_cover, z=get_z_alt(LAYER_BACKGROUND_COVER).tuple, a=1 - Options.background_alpha
        )


def draw_dead(life, dead_time, background_cover, dead_effect_quads):
    if life == 0:
        if not ActiveSkin.dead_effect.is_available:
            ActiveSkin.background.draw(background_cover, z=get_z_alt(LAYER_BACKGROUND).tuple, a=0.3)
        else:
            a = unlerp_clamped(0, 0.25, time() - dead_time)

            for k in range(len(dead_effect_quads)):
                ActiveSkin.dead_effect.draw(quad=dead_effect_quads[k], z=get_z_alt(LAYER_BACKGROUND).tuple, a=a)


def draw_auto_play(ui_layout):
    if time() < 0:
        return
    if Options.custom_tag and is_watch() and not is_replay() and Options.hide_ui < 2:
        layout = ui_layout.custom_tag
        a = 0.8 * (cos(time() * pi) + 1) / 2
        ActiveSkin.auto_live.draw(layout, z=get_z_alt(LAYER_JUDGMENT).tuple, a=a)


def draw_life_bar(
    life,
    last_time,
    ui_layout,
    alpha,
):
    if Options.hide_ui >= 2:
        return
    alpha = alpha * (1.0 - SkillHide.secondary_hidden)
    if alpha <= 0:
        return
    if not ActiveSkin.ui_number.available:
        return
    if not Options.custom_life_bar:
        return
    if not ActiveSkin.life.bar.available:
        return
    draw_life_number(life, get_z_alt(LAYER_JUDGMENT, 4).tuple, alpha)
    bar_layout = ui_layout.life_bar
    if is_multiplayer():
        ActiveSkin.life.bar.get_sprite(LifeBarType.DISABLE, life).draw(
            bar_layout, z=get_z_alt(LAYER_JUDGMENT, 3).tuple, a=alpha
        )
    elif last_time < time() and is_play():
        ActiveSkin.life.bar.get_sprite(LifeBarType.SKIP, life).draw(
            bar_layout, z=get_z_alt(LAYER_JUDGMENT, 3).tuple, a=alpha
        )
    else:
        ActiveSkin.life.bar.get_sprite(LifeBarType.PAUSE, life).draw(
            bar_layout, z=get_z_alt(LAYER_JUDGMENT, 3).tuple, a=alpha
        )
    ActiveSkin.life.bar.get_sprite(LifeBarType.BACKGROUND, life).draw(bar_layout, z=LAYER_JUDGMENT, a=alpha)
    gauge_layout = layout_life_gauge(life)
    ActiveSkin.life.gauge.get_sprite(life).draw(gauge_layout, get_z_alt(LAYER_JUDGMENT, 1).tuple, alpha)
    if life > 0:
        edge_layout = layout_life_gauge(life, True)
        ActiveSkin.life.gauge.get_sprite(life, True).draw(edge_layout, get_z_alt(LAYER_JUDGMENT, 2).tuple, alpha)


def draw_score_bar(
    score,
    note_score,
    note_time,
    ui_layout,
    alpha,
):
    if Options.hide_ui >= 2:
        return
    alpha = alpha * (1.0 - SkillHide.primary_hidden)
    if alpha <= 0:
        return
    if not ActiveSkin.ui_number.available:
        return
    if not Options.custom_score_bar:
        return
    if not ActiveSkin.score.available:
        return
    draw_score_bar_number(score, get_z_alt(LAYER_JUDGMENT, 4).tuple, alpha)
    draw_score_bar_raw_number(
        number=note_score, z=get_z_alt(LAYER_JUDGMENT, 4).tuple, time=time() - note_time, alpha=alpha
    )
    bar_layout = ui_layout.score_bar
    ActiveSkin.score.bar.draw(bar_layout, z=get_z_alt(LAYER_JUDGMENT, 2).tuple, a=alpha)
    ActiveSkin.score.panel.draw(bar_layout, z=get_z_alt(LAYER_JUDGMENT, 4).tuple, a=alpha)
    rank = get_score_rank(score)
    if score > 0:
        gauge = get_gauge_progress(score)
        ActiveSkin.score.gauge.normal.draw(ui_layout.score_gauge, z=get_z_alt(LAYER_JUDGMENT).tuple, a=alpha)

        gauge_mask_layout = layout_score_gauge(gauge, ScoreGaugeType.MASK)
        ActiveSkin.score.gauge.mask.draw(gauge_mask_layout, z=get_z_alt(LAYER_JUDGMENT, 1).tuple, a=alpha)
    else:
        ActiveSkin.score.gauge.cover.draw(ui_layout.score_gauge, z=get_z_alt(LAYER_JUDGMENT).tuple, a=alpha)
    if LevelConfig.ui_version == Version.v3 or rank != ScoreRankType.D:
        ActiveSkin.score.rank.get_sprite(rank).draw(ui_layout.score_rank, z=get_z_alt(LAYER_JUDGMENT, 4).tuple, a=alpha)
    if LevelConfig.ui_version == Version.v3:
        ActiveSkin.score.rank_text.get_sprite(rank).draw(
            ui_layout.score_rank_text, z=get_z_alt(LAYER_JUDGMENT, 4).tuple, a=alpha
        )


def get_gauge_progress(score):
    xp = (0, 20000, 400000, 620000, 840000, 1000000)
    fp = (
        0,
        0.45,
        0.6,
        0.75,
        0.9,
        1.0,
    )

    return interp(xp, fp, score)


def get_score_rank(score):
    if score >= 840000:
        return ScoreRankType.S
    elif score >= 620000:
        return ScoreRankType.A
    elif score >= 400000:
        return ScoreRankType.B
    elif score >= 20000:
        return ScoreRankType.C
    else:
        return ScoreRankType.D


def play_lane_hit_effects(lane: float, sfx: bool = True, *, transform: StageScreenTransform):
    if sfx or not Options.prevent_empty_lane_sfx:
        play_lane_sfx(lane)
    play_lane_particle(lane, transform)


def play_lane_sfx(lane: float):
    if Options.sfx_enabled:
        Effects.stage.play(SFX_DISTANCE)


def schedule_lane_sfx(lane: float, target_time: float):
    if Options.sfx_enabled:
        Effects.stage.schedule(target_time, SFX_DISTANCE)


def play_lane_particle(lane: float, transform: StageScreenTransform):
    if Options.lane_effect_enabled:
        layout = transform.transform_quad(layout_particle_lane(lane, 0.5, compensate_overshoot=False))
        ActiveParticles.lane.spawn(layout, duration=0.3 / Options.effect_animation_speed)
