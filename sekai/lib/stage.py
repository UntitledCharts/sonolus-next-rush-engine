from __future__ import annotations

from enum import IntEnum
from math import ceil, cos, floor, pi
from typing import Protocol, assert_never, cast

from sonolus.script import runtime
from sonolus.script.archetype import EntityRef, get_archetype_by_name
from sonolus.script.interval import clamp, interp, lerp, unlerp_clamped
from sonolus.script.quad import Quad
from sonolus.script.record import Record
from sonolus.script.runtime import is_multiplayer, is_play, is_replay, is_watch, screen, time
from sonolus.script.vec import Vec2

from sekai.lib import archetype_names
from sekai.lib.baseevent import get_event_as, query_event_list
from sekai.lib.custom_elements import (
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
    LAYER_COVER_LINE,
    LAYER_JUDGMENT,
    LAYER_JUDGMENT_LINE,
    LAYER_STAGE,
    LAYER_STAGE_COVER,
    LAYER_STAGE_LANE,
    get_z,
    get_z_alt,
)
from sekai.lib.layout import (
    DynamicLayout,
    ScoreGaugeType,
    approach,
    current_stage_tilt,
    layout_background_cover,
    layout_custom_tag,
    layout_full_width_stage_cover,
    layout_hidden_cover,
    layout_lane,
    layout_lane_by_edges,
    layout_life_bar,
    layout_life_gauge,
    layout_score_bar,
    layout_score_gauge,
    layout_score_rank,
    layout_score_rank_text,
    layout_sekai_stage,
    layout_stage_cover,
    layout_stage_cover_and_line,
    perspective_rect,
    tilt_depth,
    tilt_widened_edge,
    tilt_width_factor,
    transformed_vec_at,
)
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import Options, SekaiVersion, StageCoverMode
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


class Transition[T](Record):
    start: T
    end: T
    progress: float


class StageProps(Record):
    lane: float
    width: float
    pivot_lane: float
    division: Transition[DivisionProps]
    judge_line_color: Transition[JudgeLineColor]
    left_border_style: Transition[StageBorderStyle]
    right_border_style: Transition[StageBorderStyle]
    order: int
    a: float
    lane_alpha: float
    judge_line_alpha: float
    y_offset: float

    def draw(self):
        draw_dynamic_stage(
            lane=self.lane,
            width=self.width,
            pivot_lane=self.pivot_lane,
            division=self.division,
            judge_line_color=self.judge_line_color,
            left_border_style=self.left_border_style,
            right_border_style=self.right_border_style,
            order=self.order,
            a=self.a,
            lane_alpha=self.lane_alpha,
            judge_line_alpha=self.judge_line_alpha,
            y_offset=self.y_offset,
        )


class StageMaskChangeLike(Protocol):
    time: float
    lane: float
    size: float
    ease: EaseType
    next_ref: EntityRef
    prev_ref: EntityRef

    @classmethod
    def at(cls, index: int) -> StageMaskChangeLike: ...

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
    def at(cls, index: int) -> StagePivotChangeLike: ...

    @property
    def index(self) -> int: ...


class StageStyleChangeLike(Protocol):
    time: float
    judge_line_color: JudgeLineColor
    left_border_style: StageBorderStyle
    right_border_style: StageBorderStyle
    alpha: float
    lane_alpha: float
    judge_line_alpha: float
    ease: EaseType
    next_ref: EntityRef
    prev_ref: EntityRef

    @classmethod
    def at(cls, index: int) -> StageStyleChangeLike: ...

    @property
    def index(self) -> int: ...


class DynamicStageLike(Protocol):
    from_start: bool
    until_end: bool
    first_mask_change_ref: EntityRef
    first_pivot_change_ref: EntityRef
    first_style_change_ref: EntityRef

    @property
    def index(self) -> int: ...


def _stage_mask_change_archetype() -> type[StageMaskChangeLike]:
    return cast(type[StageMaskChangeLike], get_archetype_by_name(archetype_names.STAGE_MASK_CHANGE))


def _stage_pivot_change_archetype() -> type[StagePivotChangeLike]:
    return cast(type[StagePivotChangeLike], get_archetype_by_name(archetype_names.STAGE_PIVOT_CHANGE))


def _stage_style_change_archetype() -> type[StageStyleChangeLike]:
    return cast(type[StageStyleChangeLike], get_archetype_by_name(archetype_names.STAGE_STYLE_CHANGE))


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
    return result


def get_stage_props(stage: DynamicStageLike, target_time: float | None = None, left_limit: bool = False) -> StageProps:
    t = target_time if target_time is not None else runtime.time()
    result = +StageProps
    result.order = stage.index

    first_mask_change_ref = stage.first_mask_change_ref
    first_pivot_change_ref = stage.first_pivot_change_ref
    first_style_change_ref = stage.first_style_change_ref

    # Query mask changes
    mask_a_ref, mask_b_ref = query_event_list(first_mask_change_ref, t, lambda e: e.time)
    if left_limit and mask_a_ref.index > 0:
        mask_curr = get_event_as(mask_a_ref, _stage_mask_change_archetype())
        if mask_curr.time == t:
            # Walk back through any same-time chain so b_ref ends up at the earliest at-t event.
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

    # Query pivot changes
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

    # Query style changes
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
        result.left_border_style.start = style_a.left_border_style
        result.left_border_style.end = style_a.left_border_style
        result.right_border_style.start = style_a.right_border_style
        result.right_border_style.end = style_a.right_border_style
        result.a = style_a.alpha
        result.lane_alpha = style_a.lane_alpha
        result.judge_line_alpha = style_a.judge_line_alpha
        if style_b_ref.index > 0:
            style_b = get_event_as(style_b_ref, _stage_style_change_archetype())
            t_a = style_a.time
            t_b = style_b.time
            if t_b > t_a:
                p = ease(style_a.ease, (t - t_a) / (t_b - t_a))
                result.judge_line_color.end = style_b.judge_line_color
                result.judge_line_color.progress = p
                result.left_border_style.end = style_b.left_border_style
                result.left_border_style.progress = p
                result.right_border_style.end = style_b.right_border_style
                result.right_border_style.progress = p
                result.a = lerp(style_a.alpha, style_b.alpha, p)
                result.lane_alpha = lerp(style_a.lane_alpha, style_b.lane_alpha, p)
                result.judge_line_alpha = lerp(style_a.judge_line_alpha, style_b.judge_line_alpha, p)
    elif style_b_ref.index > 0:
        style_b = get_event_as(style_b_ref, _stage_style_change_archetype())
        result.judge_line_color.start = style_b.judge_line_color
        result.judge_line_color.end = style_b.judge_line_color
        result.left_border_style.start = style_b.left_border_style
        result.left_border_style.end = style_b.left_border_style
        result.right_border_style.start = style_b.right_border_style
        result.right_border_style.end = style_b.right_border_style
        result.a = style_b.alpha
        result.lane_alpha = style_b.lane_alpha
        result.judge_line_alpha = style_b.judge_line_alpha

    return result


def draw_stage_and_accessories(
    z_stage_lane,
    z_stage_cover,
    z_stage,
    z_judgment_line,
    z_cover,
    z_cover_line,
    z_judgment,
    z_background_cover,
    z_layer_score,
    z_layer_score_glow,
    z_layer_score_bar,
    z_layer_score_bar_mask,
    z_layer_score_bar_rate,
    z_layer_background,
    ap,
    score,
    note_score,
    note_time,
    percentage,
    life=1000.0,
    last_time=1e8,
    dead_time=1e8,
):
    ui_alpha = 1.0
    if Options.ui_intro and time() < -1.0:
        ui_alpha = unlerp_clamped(-2.0, -1.0, time())
    if not LevelConfig.skip_default_stage:
        draw_basic_stage(z_stage_lane, z_stage_cover, z_stage, z_judgment_line, alpha=ui_alpha)
    draw_stage_cover(z_cover, z_cover_line, alpha=ui_alpha)
    draw_auto_play(z_judgment)
    draw_background_cover(z_background_cover)
    draw_dead(z_layer_background, life, dead_time)
    draw_score_number(
        ap=ap,
        score=percentage,
        z1=z_layer_score,
        z2=z_layer_score_glow,
        alpha=ui_alpha,
    )
    draw_life_bar(
        life,
        z_layer_score,
        z_layer_score_glow,
        z_layer_score_bar,
        z_layer_score_bar_mask,
        z_layer_score_bar_rate,
        last_time,
        alpha=ui_alpha,
    )
    draw_score_bar(
        score,
        note_score,
        note_time,
        z_layer_score,
        z_layer_score_glow,
        z_layer_score_bar,
        z_layer_score_bar_mask,
        z_layer_score_bar_rate,
        alpha=ui_alpha,
    )


def normalize_transition[T](value: Transition[T] | T) -> Transition[T]:
    if isinstance(value, Transition):
        return value
    return Transition(start=value, end=value, progress=0)


def draw_basic_stage(z_stage_lane, z_stage_cover, z_stage, z_judgment_line, alpha=1.0):
    if not Options.show_lane:
        return
    if (
        ActiveSkin.sekai_stage_lane.is_available
        and ActiveSkin.sekai_stage_cover.is_available
        and not LevelConfig.dynamic_stages
    ):
        draw_sekai_divided_stage(z_stage_lane, z_stage_cover, alpha)
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
            a=alpha,
        )


def draw_sekai_stage(z_stage, alpha):
    layout = layout_sekai_stage()
    ActiveSkin.sekai_stage.draw(layout, z=z_stage, a=alpha)


def draw_sekai_divided_stage(z_stage_lane, z_stage_cover, alpha):
    layout = layout_sekai_stage()
    ActiveSkin.sekai_stage_lane.draw(layout, z=z_stage_lane, a=alpha)
    ActiveSkin.sekai_stage_cover.draw(layout, z=z_stage_cover, a=Options.lane_alpha * alpha)


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
    a: float,
    lane_alpha: float = 1,
    judge_line_alpha: float = 1,
    y_offset: float = 0,
    alpha: float = 1,
):
    division = normalize_transition(division)
    judge_line_color = normalize_transition(judge_line_color)
    left_border_style = normalize_transition(left_border_style)
    right_border_style = normalize_transition(right_border_style)

    sprites_same = judge_line_color.start == judge_line_color.end
    sprites_a = get_judgment_sprites(judge_line_color.start)
    sprites_b = get_judgment_sprites(judge_line_color.end)
    p_sprites = judge_line_color.progress

    if not ActiveSkin.lane_background.is_available:
        draw_fallback_stage(
            lane,
            width,
            division.end.size,
            division.end.parity,
            pivot_lane,
            order,
            a,
            lane_alpha,
            judge_line_alpha,
            y_offset,
        )
        return

    travel = approach(1 - y_offset)
    nh = DynamicLayout.note_h
    l = lane - width
    r = lane + width
    z_bg0 = get_z_alt(LAYER_STAGE, order * 15)
    z_bg1_a = get_z_alt(LAYER_STAGE, order * 15 + 1)
    z_bg1_b = get_z_alt(LAYER_STAGE, order * 15 + 2)
    z_lane0 = get_z_alt(LAYER_STAGE, order * 15 + 3)
    z_lane1 = get_z_alt(LAYER_STAGE, order * 15 + 4)
    z_a0 = get_z_alt(LAYER_STAGE, order * 15 + 5)
    z_a1 = get_z_alt(LAYER_STAGE, order * 15 + 6)
    z_a2 = get_z_alt(LAYER_STAGE, order * 15 + 7)
    z_a3 = get_z_alt(LAYER_STAGE, order * 15 + 8)
    z_b0 = get_z_alt(LAYER_STAGE, order * 15 + 9)
    z_b1 = get_z_alt(LAYER_STAGE, order * 15 + 10)
    z_b2 = get_z_alt(LAYER_STAGE, order * 15 + 11)
    z_b3 = get_z_alt(LAYER_STAGE, order * 15 + 12)
    z_a4 = get_z_alt(LAYER_STAGE, order * 15 + 13)
    z_b4 = get_z_alt(LAYER_STAGE, order * 15 + 14)

    f = 5  # sizing factor for judge line border

    def draw_left_border(style: StageBorderStyle, z: float, a: float):
        match style:
            case StageBorderStyle.DEFAULT | StageBorderStyle.MEDIUM:
                scale = 0.5 if style == StageBorderStyle.MEDIUM else 1.0
                layout_b = layout_lane_by_edges(
                    l - 0.08 * scale, l
                )  # Artificially thicken the top so it renders better
                layout_t = layout_lane_by_edges(tilt_widened_edge(l - 0.08 * scale, l - 0.64 * scale), l)
                ActiveSkin.stage_border.draw(
                    Quad(bl=layout_b.bl, tl=layout_t.tl, tr=layout_t.tr, br=layout_b.br), z=z, a=a
                )
            case StageBorderStyle.LIGHT:
                layout_b = layout_lane_by_edges(l - 0.0125, l + 0.0125)
                layout_t = layout_lane_by_edges(
                    tilt_widened_edge(l - 0.0125, l - 0.1), tilt_widened_edge(l + 0.0125, l + 0.1)
                )
                ActiveSkin.lane_divider.draw(
                    Quad(bl=layout_b.bl, tl=layout_t.tl, tr=layout_t.tr, br=layout_b.br), z=z, a=a
                )
            case StageBorderStyle.DISABLED:
                pass
            case _:
                assert_never(style)

    def draw_right_border(style: StageBorderStyle, z: float, a: float):
        match style:
            case StageBorderStyle.DEFAULT | StageBorderStyle.MEDIUM:
                scale = 0.5 if style == StageBorderStyle.MEDIUM else 1.0
                layout_b = layout_lane_by_edges(r + 0.08 * scale, r)  # Flip horizontally
                layout_t = layout_lane_by_edges(tilt_widened_edge(r + 0.08 * scale, r + 0.64 * scale), r)
                ActiveSkin.stage_border.draw(
                    Quad(bl=layout_b.bl, tl=layout_t.tl, tr=layout_t.tr, br=layout_b.br), z=z, a=a
                )
            case StageBorderStyle.LIGHT:
                layout_b = layout_lane_by_edges(r - 0.0125, r + 0.0125)
                layout_t = layout_lane_by_edges(
                    tilt_widened_edge(r - 0.0125, r - 0.1), tilt_widened_edge(r + 0.0125, r + 0.1)
                )
                ActiveSkin.lane_divider.draw(
                    Quad(bl=layout_b.bl, tl=layout_t.tl, tr=layout_t.tr, br=layout_b.br), z=z, a=a
                )
            case StageBorderStyle.DISABLED:
                pass
            case _:
                assert_never(style)

    def draw_dividers(division_size: int, parity: DivisionParity, pivot: float, z: float, a: float):
        eps = 0.001
        parity_offset = division_size / 2 if parity == DivisionParity.ODD else 0
        shifted_pivot = pivot + parity_offset

        if division_size <= 0:
            return

        k_start = floor((l - shifted_pivot + eps) / division_size) + 1
        k_end = ceil((r - shifted_pivot - eps) / division_size) - 1

        for k in range(k_start, k_end + 1):
            pos = shifted_pivot + k * division_size
            div_layout_b = layout_lane_by_edges(pos - 0.0125, pos + 0.0125)
            div_layout_t = layout_lane_by_edges(
                tilt_widened_edge(pos - 0.0125, pos - 0.1), tilt_widened_edge(pos + 0.0125, pos + 0.1)
            )
            ActiveSkin.lane_divider.draw(
                Quad(bl=div_layout_b.bl, tl=div_layout_t.tl, tr=div_layout_t.tr, br=div_layout_b.br), z=z, a=a
            )

    thickness_scale = lerp(1.0, clamp(1 / travel, 1, 4) if travel > 0 else 4, current_stage_tilt())
    judgment_divider_size = 0.014 * thickness_scale * tilt_width_factor(travel) * DynamicLayout.w_scale
    judgment_divider_offset = Vec2(judgment_divider_size, 0).rotate(-DynamicLayout.rotate)
    divider_depth_b = tilt_depth(1 + nh - nh / f + 0.001, travel)
    divider_depth_t = tilt_depth(1 - nh + nh / f - 0.001, travel)

    def layout_judgment_divider(lane: float):
        b = transformed_vec_at(lane, divider_depth_b)
        t = transformed_vec_at(lane, divider_depth_t)
        return Quad(
            bl=b - judgment_divider_offset,
            tl=t - judgment_divider_offset,
            tr=t + judgment_divider_offset,
            br=b + judgment_divider_offset,
        )

    def draw_judgment_dividers(
        sprites: JudgmentSpriteSet, half_offset: bool, pivot: float, z_lo: float, z_hi: float, a: float
    ):
        eps = 0.001
        shifted_pivot = pivot + (0.5 if half_offset else 0)

        k_start = floor(l - shifted_pivot + eps) + 1
        k_end = ceil(r - shifted_pivot - eps) - 1

        for k in range(k_start, k_end + 1):
            pos = shifted_pivot + k
            div_layout = layout_judgment_divider(pos)
            edge_weight = abs(pos - lane) / width if width > 0 else 0
            sprites.judgment_center.draw(div_layout, z=z_lo, a=a)
            sprites.judgment_edge.draw(div_layout, z=z_hi, a=a * edge_weight)

    def draw_left_judgment_border(sprites: JudgmentSpriteSet, style: StageBorderStyle, z: float, a: float):
        match style:
            case StageBorderStyle.DEFAULT | StageBorderStyle.MEDIUM:
                if width <= 0:
                    return
                layout = perspective_rect(
                    l,
                    min(l + 1 / f / 2, lane),
                    1 - nh + nh / f,
                    1 + nh - nh / f,
                    travel,
                )
                sprites.judgment_edge_left.draw(layout, z=z, a=a)
            case StageBorderStyle.LIGHT:
                layout = layout_judgment_divider(l)
                sprites.judgment_edge.draw(layout, z=z, a=a)
            case StageBorderStyle.DISABLED:
                pass
            case _:
                assert_never(style)

    def draw_right_judgment_border(sprites: JudgmentSpriteSet, style: StageBorderStyle, z: float, a: float):
        match style:
            case StageBorderStyle.DEFAULT | StageBorderStyle.MEDIUM:
                if width <= 0:
                    return
                layout = perspective_rect(
                    r,
                    max(r - 1 / f / 2, lane),
                    1 - nh + nh / f,
                    1 + nh - nh / f,
                    travel,
                )
                sprites.judgment_edge_left.draw(layout, z=z, a=a)
            case StageBorderStyle.LIGHT:
                layout = layout_judgment_divider(r)
                sprites.judgment_edge.draw(layout, z=z, a=a)
            case StageBorderStyle.DISABLED:
                pass
            case _:
                assert_never(style)

    def draw_gradient(sprites: JudgmentSpriteSet, z: float, a: float):
        layout = perspective_rect(l, lane, 1 + nh, 1 + nh - nh / f, travel)
        sprites.judgment_gradient.draw(layout, z=z, a=a)
        layout = perspective_rect(r, lane, 1 + nh, 1 + nh - nh / f, travel)
        sprites.judgment_gradient.draw(layout, z=z, a=a)
        layout = perspective_rect(l, lane, 1 - nh, 1 - nh + nh / f, travel)
        sprites.judgment_gradient.draw(layout, z=z, a=a)
        layout = perspective_rect(r, lane, 1 - nh, 1 - nh + nh / f, travel)
        sprites.judgment_gradient.draw(layout, z=z, a=a)

    if lane_alpha > 0:
        la = a * lane_alpha
        ActiveSkin.lane_background.draw(layout_lane_by_edges(l, r), z=z_bg0, a=la)

        p_left = left_border_style.progress
        if left_border_style.start == left_border_style.end:
            draw_left_border(left_border_style.start, z_lane0, la)
        else:
            draw_left_border(left_border_style.start, z_lane0, la * (1 - p_left))
            draw_left_border(left_border_style.end, z_lane1, la * p_left)

        p_right = right_border_style.progress
        if right_border_style.start == right_border_style.end:
            draw_right_border(right_border_style.start, z_lane0, la)
        else:
            draw_right_border(right_border_style.start, z_lane0, la * (1 - p_right))
            draw_right_border(right_border_style.end, z_lane1, la * p_right)

        p_div = division.progress
        if division.start == division.end:
            draw_dividers(division.start.size, division.start.parity, pivot_lane, z_lane0, la)
        else:
            if 1 - p_div > 0:
                draw_dividers(division.start.size, division.start.parity, pivot_lane, z_lane0, la * (1 - p_div))
            if p_div > 0:
                draw_dividers(division.end.size, division.end.parity, pivot_lane, z_lane1, la * p_div)

    ja = a * judge_line_alpha
    bg_layout = perspective_rect(l, r, 1 - nh, 1 + nh, travel)
    if sprites_same:
        sprites_a.judgment_background.draw(bg_layout, z=z_bg1_a, a=ja)
    else:
        sprites_a.judgment_background.draw(bg_layout, z=z_bg1_a, a=ja * (1 - p_sprites))
        sprites_b.judgment_background.draw(bg_layout, z=z_bg1_b, a=ja * p_sprites)

    p_left = left_border_style.progress
    p_right = right_border_style.progress
    p_div = division.progress

    start_has_half_offset = division.start.parity == DivisionParity.ODD and division.start.size % 2 == 1
    end_has_half_offset = division.end.parity == DivisionParity.ODD and division.end.size % 2 == 1
    judgment_dividers_same = start_has_half_offset == end_has_half_offset

    if judgment_dividers_same and sprites_same:
        draw_judgment_dividers(sprites_a, start_has_half_offset, pivot_lane, z_a0, z_a1, ja)
    elif judgment_dividers_same:
        draw_judgment_dividers(sprites_a, start_has_half_offset, pivot_lane, z_a0, z_a1, ja * (1 - p_sprites))
        draw_judgment_dividers(sprites_b, start_has_half_offset, pivot_lane, z_b0, z_b1, ja * p_sprites)
    elif sprites_same:
        draw_judgment_dividers(sprites_a, start_has_half_offset, pivot_lane, z_a0, z_a1, ja * (1 - p_div))
        draw_judgment_dividers(sprites_a, end_has_half_offset, pivot_lane, z_a2, z_a3, ja * p_div)
    else:
        alpha_aa = (1 - p_sprites) * (1 - p_div)
        alpha_ab = (1 - p_sprites) * p_div
        alpha_ba = p_sprites * (1 - p_div)
        alpha_bb = p_sprites * p_div
        if alpha_aa > 0:
            draw_judgment_dividers(sprites_a, start_has_half_offset, pivot_lane, z_a0, z_a1, ja * alpha_aa)
        if alpha_ab > 0:
            draw_judgment_dividers(sprites_a, end_has_half_offset, pivot_lane, z_a2, z_a3, ja * alpha_ab)
        if alpha_ba > 0:
            draw_judgment_dividers(sprites_b, start_has_half_offset, pivot_lane, z_b0, z_b1, ja * alpha_ba)
        if alpha_bb > 0:
            draw_judgment_dividers(sprites_b, end_has_half_offset, pivot_lane, z_b2, z_b3, ja * alpha_bb)

    if sprites_same:
        draw_gradient(sprites_a, z_a4, ja)
    else:
        draw_gradient(sprites_a, z_a4, ja * (1 - p_sprites))
        draw_gradient(sprites_b, z_b4, ja * p_sprites)

    if sprites_same and left_border_style.start == left_border_style.end:
        draw_left_judgment_border(sprites_a, left_border_style.start, z_a0, ja)
    else:
        alpha_aa = (1 - p_sprites) * (1 - p_left)
        alpha_ab = (1 - p_sprites) * p_left
        alpha_ba = p_sprites * (1 - p_left)
        alpha_bb = p_sprites * p_left
        if alpha_aa > 0:
            draw_left_judgment_border(sprites_a, left_border_style.start, z_a0, ja * alpha_aa)
        if alpha_ab > 0:
            draw_left_judgment_border(sprites_a, left_border_style.end, z_a2, ja * alpha_ab)
        if alpha_ba > 0:
            draw_left_judgment_border(sprites_b, left_border_style.start, z_b0, ja * alpha_ba)
        if alpha_bb > 0:
            draw_left_judgment_border(sprites_b, left_border_style.end, z_b2, ja * alpha_bb)

    if sprites_same and right_border_style.start == right_border_style.end:
        draw_right_judgment_border(sprites_a, right_border_style.start, z_a0, ja)
    else:
        alpha_aa = (1 - p_sprites) * (1 - p_right)
        alpha_ab = (1 - p_sprites) * p_right
        alpha_ba = p_sprites * (1 - p_right)
        alpha_bb = p_sprites * p_right
        if alpha_aa > 0:
            draw_right_judgment_border(sprites_a, right_border_style.start, z_a0, ja * alpha_aa)
        if alpha_ab > 0:
            draw_right_judgment_border(sprites_a, right_border_style.end, z_a2, ja * alpha_ab)
        if alpha_ba > 0:
            draw_right_judgment_border(sprites_b, right_border_style.start, z_b0, ja * alpha_ba)
        if alpha_bb > 0:
            draw_right_judgment_border(sprites_b, right_border_style.end, z_b2, ja * alpha_bb)

    draw_per_stage_cover(l, r, a, lane_alpha, order, alpha)


def draw_fallback_stage(
    lane: float,
    width: float,
    division_size: int,
    parity: DivisionParity,
    pivot: float,
    z: int,
    a: float,
    lane_alpha: float = 1,
    judge_line_alpha: float = 1,
    y_offset: float = 0,
    alpha: float = 1,
):
    travel = approach(1 - y_offset)
    nh = DynamicLayout.note_h
    l = lane - width
    r = lane + width
    z_lo = get_z_alt(LAYER_STAGE, z * 3)
    z_mid = get_z_alt(LAYER_STAGE, z * 3 + 1)
    z_hi = get_z_alt(LAYER_STAGE, z * 3 + 2)
    la = a * lane_alpha
    ja = a * judge_line_alpha
    if la > 0:
        # Artificially thicken the top so it renders better
        layout_b = layout_lane_by_edges(l - 0.25, l)
        layout_t = layout_lane_by_edges(tilt_widened_edge(l - 0.25, l - 1), l)
        ActiveSkin.stage_left_border.draw(
            Quad(bl=layout_b.bl, tl=layout_t.tl, tr=layout_t.tr, br=layout_b.br), z=z_mid, a=la
        )
        layout_b = layout_lane_by_edges(r, r + 0.25)
        layout_t = layout_lane_by_edges(r, tilt_widened_edge(r + 0.25, r + 1))
        ActiveSkin.stage_right_border.draw(
            Quad(bl=layout_b.bl, tl=layout_t.tl, tr=layout_t.tr, br=layout_b.br), z=z_mid, a=la
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
                ActiveSkin.lane.draw(layout_lane_by_edges(prev, pos), a=la, z=z_lo)
                prev = pos
        ActiveSkin.lane.draw(layout_lane_by_edges(prev, r), a=la, z=z_lo)

    layout = perspective_rect(l, r, t=1 - nh, b=1 + nh, travel=travel)
    ActiveSkin.judgment_line.draw(layout, z=z_hi, a=ja)

    draw_per_stage_cover(l, r, a, lane_alpha, z, alpha)


def draw_per_stage_cover(l: float, r: float, a: float, lane_alpha: float, order: int, alpha: float):
    if not LevelConfig.dynamic_stages:
        return
    ca = a * lane_alpha
    if ca <= 0:
        return
    z_cover = get_z_alt(LAYER_COVER, order * 4)
    z_line = get_z_alt(LAYER_COVER, order * 4 + 1)
    z_hidden = get_z_alt(LAYER_COVER, order * 4 + 2)
    if Options.stage_cover > 0:
        match Options.stage_cover_mode:
            case StageCoverMode.STAGE:
                layout = layout_stage_cover(l, r)
                ActiveSkin.cover.draw(layout, z=z_cover, a=Options.stage_cover_alpha * ca * alpha)
            case StageCoverMode.STAGE_AND_LINE:
                cover_layout, line_layout = layout_stage_cover_and_line(l, r)
                ActiveSkin.cover.draw(cover_layout, z=z_cover, a=Options.stage_cover_alpha * ca * alpha)
                ActiveSkin.guide_neutral.draw(line_layout, z=z_line, a=0.75 * ca * alpha)
            case StageCoverMode.FULL_WIDTH:
                pass
            case _:
                assert_never(Options.stage_cover_mode)
    if Options.hidden > 0:
        layout = layout_hidden_cover(l, r)
        ActiveSkin.cover.draw(layout, z=z_hidden, a=ca)


def draw_stage_cover(z_cover, z_cover_line, alpha):
    if Options.stage_cover > 0:
        match Options.stage_cover_mode:
            case StageCoverMode.STAGE:
                if not LevelConfig.dynamic_stages:
                    layout = layout_stage_cover()
                    ActiveSkin.cover.draw(layout, z=z_cover, a=Options.stage_cover_alpha * alpha * alpha)
            case StageCoverMode.STAGE_AND_LINE:
                if not LevelConfig.dynamic_stages:
                    cover_layout, line_layout = layout_stage_cover_and_line()
                    ActiveSkin.cover.draw(cover_layout, z=z_cover, a=Options.stage_cover_alpha * alpha)
                    ActiveSkin.guide_neutral.draw(line_layout, z=z_cover_line, a=0.75 * alpha)
            case StageCoverMode.FULL_WIDTH:
                layout = layout_full_width_stage_cover()
                ActiveSkin.cover.draw(layout, z=z_cover, a=Options.stage_cover_alpha * alpha)
            case _:
                assert_never(Options.stage_cover_mode)
    if Options.hidden > 0 and not LevelConfig.dynamic_stages:
        layout = layout_hidden_cover()
        ActiveSkin.cover.draw(layout, z=z_cover, a=alpha)


def draw_background_cover(z_background_cover):
    if Options.background_alpha != 1:
        layout = layout_background_cover()
        ActiveSkin.background.draw(layout, z=z_background_cover, a=1 - Options.background_alpha)


def draw_dead(z_background, life, dead_time):
    if life == 0:
        if not ActiveSkin.dead_effect.is_available:
            layout = layout_background_cover()
            ActiveSkin.background.draw(layout, z=z_background, a=0.3)
        else:
            a = unlerp_clamped(0, 0.25, time() - dead_time)

            for i in range(2):
                for j in range(2):
                    l_val = screen().l if j == 0 else screen().r
                    if i == 0:
                        t_val = screen().t
                    else:
                        t_val = screen().b
                    layout = Quad(
                        bl=Vec2(l_val, 0),
                        br=Vec2(0, 0),
                        tl=Vec2(l_val, t_val),
                        tr=Vec2(0, t_val),
                    )
                    ActiveSkin.dead_effect.draw(quad=layout, z=z_background, a=a)


def draw_auto_play(z_judgment):
    if time() < 0:
        return
    if Options.custom_tag and is_watch() and not is_replay() and Options.hide_ui < 2:
        layout = layout_custom_tag()
        a = 0.8 * (cos(time() * pi) + 1) / 2
        ActiveSkin.auto_live.draw(layout, z=z_judgment, a=a)


def draw_life_bar(
    life,
    z_layer_score,
    z_layer_score_glow,
    z_layer_score_bar,
    z_layer_score_bar_mask,
    z_layer_score_bar_rate,
    last_time,
    alpha,
):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.ui_number.available:
        return
    if not Options.custom_life_bar:
        return
    if not ActiveSkin.life.bar.available:
        return
    draw_life_number(life, z_layer_score_bar_rate, alpha)
    bar_layout = layout_life_bar()
    if is_multiplayer():
        ActiveSkin.life.bar.get_sprite(LifeBarType.DISABLE, life).draw(bar_layout, z=z_layer_score_bar_mask, a=alpha)
    elif last_time < time() and is_play():
        ActiveSkin.life.bar.get_sprite(LifeBarType.SKIP, life).draw(bar_layout, z=z_layer_score_bar_mask, a=alpha)
    else:
        ActiveSkin.life.bar.get_sprite(LifeBarType.PAUSE, life).draw(bar_layout, z=z_layer_score_bar_mask, a=alpha)
    ActiveSkin.life.bar.get_sprite(LifeBarType.BACKGROUND, life).draw(bar_layout, z=z_layer_score, a=alpha)
    gauge_layout = layout_life_gauge(life)
    ActiveSkin.life.gauge.get_sprite(life).draw(gauge_layout, z_layer_score_glow, alpha)
    if life > 0:
        edge_layout = layout_life_gauge(life, True)
        ActiveSkin.life.gauge.get_sprite(life, True).draw(edge_layout, z_layer_score_bar, alpha)


def draw_score_bar(
    score,
    note_score,
    note_time,
    z_layer_score,
    z_layer_score_glow,
    z_layer_score_bar,
    z_layer_score_bar_mask,
    z_layer_score_bar_rate,
    alpha,
):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.ui_number.available:
        return
    if not Options.custom_score_bar:
        return
    if not ActiveSkin.score.available:
        return
    draw_score_bar_number(score, z_layer_score_bar_rate, alpha)
    draw_score_bar_raw_number(number=note_score, z=z_layer_score_bar_rate, time=time() - note_time, alpha=alpha)
    bar_layout = layout_score_bar()
    ActiveSkin.score.bar.draw(bar_layout, z=z_layer_score_bar, a=alpha)
    ActiveSkin.score.panel.draw(bar_layout, z=z_layer_score_bar_rate, a=alpha)
    rank = get_score_rank(score)
    if score > 0:
        gauge = get_gauge_progress(score)
        gauge_normal_layout = layout_score_gauge(score_type=ScoreGaugeType.NORMAL)
        ActiveSkin.score.gauge.normal.draw(gauge_normal_layout, z=z_layer_score, a=alpha)

        gauge_mask_layout = layout_score_gauge(gauge, ScoreGaugeType.MASK)
        ActiveSkin.score.gauge.mask.draw(gauge_mask_layout, z=z_layer_score_glow, a=alpha)
        if LevelConfig.ui_version == SekaiVersion.v3 or rank != ScoreRankType.D:
            score_rank_layout = layout_score_rank()
            ActiveSkin.score.rank.get_sprite(rank).draw(score_rank_layout, z=z_layer_score_bar_rate, a=alpha)
    else:
        gauge_cover_layout = layout_score_gauge(score_type=ScoreGaugeType.NORMAL)
        ActiveSkin.score.gauge.cover.draw(gauge_cover_layout, z=z_layer_score, a=alpha)
    if LevelConfig.ui_version == SekaiVersion.v3:
        score_rank_text_layout = layout_score_rank_text()
        ActiveSkin.score.rank_text.get_sprite(rank).draw(score_rank_text_layout, z=z_layer_score_bar_rate, a=alpha)


def get_gauge_progress(score):
    xp = (0, 4000, 400000, 620000, 840000, 1000000)
    fp = (
        0,
        0.447,
        0.6 if LevelConfig.ui_version == SekaiVersion.v3 else 0.577,
        0.755 if LevelConfig.ui_version == SekaiVersion.v3 else 0.72,
        0.9 if LevelConfig.ui_version == SekaiVersion.v3 else 0.87,
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
    elif score >= 4000:
        return ScoreRankType.C
    else:
        return ScoreRankType.D


def play_lane_hit_effects(lane: float, sfx: bool = True):
    if sfx or not Options.prevent_empty_lane_sfx:
        play_lane_sfx(lane)
    play_lane_particle(lane)


def play_lane_sfx(lane: float):
    if Options.sfx_enabled:
        Effects.stage.play(SFX_DISTANCE)


def schedule_lane_sfx(lane: float, target_time: float):
    if Options.sfx_enabled:
        Effects.stage.schedule(target_time, SFX_DISTANCE)


def play_lane_particle(lane: float):
    if Options.lane_effect_enabled:
        layout = layout_lane(lane, 0.5)
        ActiveParticles.lane.spawn(layout, duration=0.3 / Options.effect_animation_speed)


class StageZLayersProtocol(Protocol):
    z_layer_stage_lane: float
    z_layer_cover: float
    z_layer_cover_line: float
    z_layer_judgment: float
    z_layer_judgment_line: float
    z_layer_background_cover: float
    z_layer_stage: float
    z_layer_stage_cover: float
    z_layer_score: float
    z_layer_score_glow: float
    z_layer_score_bar: float
    z_layer_score_bar_mask: float
    z_layer_score_bar_rate: float
    z_layer_background: float


def init_stage_z_layers(stage_instance: StageZLayersProtocol):
    stage_instance.z_layer_stage_lane = get_z(LAYER_STAGE_LANE)
    stage_instance.z_layer_cover = get_z(LAYER_COVER)
    stage_instance.z_layer_cover_line = get_z(LAYER_COVER_LINE)
    stage_instance.z_layer_judgment = get_z(LAYER_JUDGMENT)
    stage_instance.z_layer_judgment_line = get_z(LAYER_JUDGMENT_LINE)
    stage_instance.z_layer_background_cover = get_z(LAYER_BACKGROUND_COVER)
    stage_instance.z_layer_stage = get_z(LAYER_STAGE)
    stage_instance.z_layer_stage_cover = get_z(LAYER_STAGE_COVER)
    stage_instance.z_layer_score = get_z(layer=LAYER_JUDGMENT)
    stage_instance.z_layer_score_glow = get_z(layer=LAYER_JUDGMENT, etc=1)
    stage_instance.z_layer_score_bar = get_z(layer=LAYER_JUDGMENT, etc=2)
    stage_instance.z_layer_score_bar_mask = get_z(layer=LAYER_JUDGMENT, etc=3)
    stage_instance.z_layer_score_bar_rate = get_z(layer=LAYER_JUDGMENT, etc=4)
    stage_instance.z_layer_background = get_z(layer=LAYER_BACKGROUND)
