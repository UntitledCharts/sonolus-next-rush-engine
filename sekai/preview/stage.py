from math import ceil, floor
from typing import assert_never

from sonolus.script.interval import lerp
from sonolus.script.sprite import ZIndex
from sonolus.script.values import swap

from sekai.lib.layer import LAYER_PREVIEW_COVER, LAYER_STAGE, get_z_alt
from sekai.lib.skin import ActiveSkin
from sekai.lib.stage import (
    DivisionParity,
    DivisionProps,
    DynamicStageLike,
    StageBorderStyle,
    StageProps,
    get_next_event_time,
    get_stage_props,
)
from sekai.preview.layout import (
    PREVIEW_COLUMN_SECS,
    PREVIEW_DYNAMIC_STAGE_BORDER_DEFAULT_W,
    PREVIEW_DYNAMIC_STAGE_BORDER_LIGHT_W,
    PREVIEW_DYNAMIC_STAGE_BORDER_MEDIUM_W,
    PREVIEW_DYNAMIC_STAGE_BSEARCH_ITERS,
    PREVIEW_DYNAMIC_STAGE_DIVIDER_W,
    PREVIEW_DYNAMIC_STAGE_EPS,
    PREVIEW_DYNAMIC_STAGE_TIME_INCREMENT,
    PreviewLayout,
    layout_preview_bottom_cover,
    layout_preview_lane,
    layout_preview_lane_by_edges,
    layout_preview_lane_rotated_strip,
    layout_preview_lane_strip,
    layout_preview_top_cover,
    time_to_preview_col,
)


def draw_preview_stage():
    for col in range(PreviewLayout.column_count):
        left_border_layout = layout_preview_lane_by_edges(-6.5, -6, col)
        right_border_layout = layout_preview_lane_by_edges(6, 6.5, col)
        ActiveSkin.stage_left_border.draw(left_border_layout, z=get_z_alt(LAYER_STAGE))
        ActiveSkin.stage_right_border.draw(right_border_layout, z=get_z_alt(LAYER_STAGE))
        for lane in (-5, -3, -1, 1, 3, 5):
            layout = layout_preview_lane(lane, 1, col)
            ActiveSkin.lane.draw(layout, z=get_z_alt(LAYER_STAGE))


def draw_preview_cover():
    bottom_layout = layout_preview_bottom_cover()
    top_layout = layout_preview_top_cover()
    z = get_z_alt(LAYER_PREVIEW_COVER)
    ActiveSkin.cover.draw(
        bottom_layout,
        z=z,
    )
    ActiveSkin.cover.draw(
        top_layout,
        z=z,
    )


def draw_preview_dynamic_stage(stage: DynamicStageLike, start_time: float, end_time: float):
    """Draw a dynamic stage in preview by walking time in fixed increments.

    Each column shows a slice of the song along the y-axis. Within each column we
    step from `col_lo` to `col_hi` in increments of PREVIEW_DYNAMIC_STAGE_TIME_INCREMENT,
    and for every (t_a, t_b) sub-slice we sample stage props at both ends and draw a
    slanted quad whose left/right edges follow the mask between t_a and t_b. Style and
    division transitions are cross-faded by drawing both sides at progress-weighted
    alpha. See draw_dynamic_stage_division_set for the per-divider logic.
    """
    if end_time <= start_time:
        return

    z_bg = get_z_alt(LAYER_STAGE)
    z_left_a = get_z_alt(LAYER_STAGE, 1)
    z_left_b = get_z_alt(LAYER_STAGE, 2)
    z_right_a = get_z_alt(LAYER_STAGE, 3)
    z_right_b = get_z_alt(LAYER_STAGE, 4)
    z_div_a = get_z_alt(LAYER_STAGE, 5)
    z_div_b = get_z_alt(LAYER_STAGE, 6)

    start_col = max(0, time_to_preview_col(start_time))
    end_col = min(PreviewLayout.column_count - 1, time_to_preview_col(end_time))

    for col in range(start_col, end_col + 1):
        col_t_lo = max(start_time, col * PREVIEW_COLUMN_SECS)
        col_t_hi = min(end_time, (col + 1) * PREVIEW_COLUMN_SECS)
        if col_t_hi <= col_t_lo:
            continue

        t_a = col_t_lo
        props_a = +StageProps
        props_a @= get_stage_props(stage, t_a)
        while t_a < col_t_hi:
            next_event = get_next_event_time(stage, t_a)
            t_b = min(t_a + PREVIEW_DYNAMIC_STAGE_TIME_INCREMENT, col_t_hi, next_event)
            at_event = t_b == next_event
            props_b = get_stage_props(stage, t_b, left_limit=at_event)

            draw_dynamic_stage_lane_bg_slice(props_a, props_b, col, t_a, t_b, z_bg)
            draw_dynamic_stage_border_slice(True, props_a, props_b, col, t_a, t_b, z_left_a, z_left_b)
            draw_dynamic_stage_border_slice(False, props_a, props_b, col, t_a, t_b, z_right_a, z_right_b)
            draw_dynamic_stage_dividers_slice(stage, props_a, props_b, col, t_a, t_b, z_div_a, z_div_b)

            t_a = t_b
            if at_event:
                props_a @= get_stage_props(stage, t_a)
            else:
                props_a @= props_b


def slice_lane_alpha(props_a: StageProps, props_b: StageProps) -> float:
    """Mask alpha (a * lane_alpha) averaged across the slice endpoints."""
    return (props_a.a * props_a.lane_alpha + props_b.a * props_b.lane_alpha) / 2


def draw_dynamic_stage_lane_bg_slice(
    props_a: StageProps, props_b: StageProps, col: int, t_a: float, t_b: float, z: ZIndex
):
    alpha = slice_lane_alpha(props_a, props_b)
    if alpha <= 0:
        return

    bound = PreviewLayout.lane_bound
    mask_l_a = max(props_a.lane - props_a.width, -bound)
    mask_r_a = min(props_a.lane + props_a.width, bound)
    mask_l_b = max(props_b.lane - props_b.width, -bound)
    mask_r_b = min(props_b.lane + props_b.width, bound)
    if mask_l_a >= mask_r_a and mask_l_b >= mask_r_b:
        return

    layout = layout_preview_lane_strip(mask_l_a, mask_r_a, t_a, mask_l_b, mask_r_b, t_b, col)
    ActiveSkin.lane_background_preview.draw(layout, z=z, a=alpha)


def draw_dynamic_stage_border_slice(
    is_left: bool,
    props_a: StageProps,
    props_b: StageProps,
    col: int,
    t_a: float,
    t_b: float,
    z_a: ZIndex,
    z_b: ZIndex,
):
    alpha = slice_lane_alpha(props_a, props_b)
    if alpha <= 0:
        return

    if is_left:
        edge_a = props_a.lane - props_a.width
        edge_b = props_b.lane - props_b.width
        style_a = props_a.left_border_style
        style_b = props_b.left_border_style
    else:
        edge_a = props_a.lane + props_a.width
        edge_b = props_b.lane + props_b.width
        style_a = props_a.right_border_style
        style_b = props_b.right_border_style

    bound = PreviewLayout.lane_bound
    de = edge_b - edge_a
    if de == 0:
        if abs(edge_a) > bound:
            return
        clip_t_a = t_a
        clip_t_b = t_b
        clip_edge_a = edge_a
        clip_edge_b = edge_b
    else:
        frac_pos = (bound - edge_a) / de
        frac_neg = (-bound - edge_a) / de
        frac_lo = max(0.0, min(frac_pos, frac_neg))
        frac_hi = min(1.0, max(frac_pos, frac_neg))
        if frac_lo >= frac_hi:
            return
        clip_t_a = lerp(t_a, t_b, frac_lo)
        clip_t_b = lerp(t_a, t_b, frac_hi)
        clip_edge_a = lerp(edge_a, edge_b, frac_lo)
        clip_edge_b = lerp(edge_a, edge_b, frac_hi)

    if style_b.start == style_b.end:
        draw_border_strip_for_style(
            is_left, style_b.start, clip_edge_a, clip_edge_b, col, clip_t_a, clip_t_b, alpha, z_a
        )
    else:
        if style_a.start == style_b.start and style_a.end == style_b.end:
            progress = (style_a.progress + style_b.progress) / 2
        else:
            # Just go with b
            progress = style_b.progress
        if 1 - progress > 0:
            draw_border_strip_for_style(
                is_left, style_b.start, clip_edge_a, clip_edge_b, col, clip_t_a, clip_t_b, alpha * (1 - progress), z_a
            )
        if progress > 0:
            draw_border_strip_for_style(
                is_left, style_b.end, clip_edge_a, clip_edge_b, col, clip_t_a, clip_t_b, alpha * progress, z_b
            )


def draw_border_strip_for_style(
    is_left: bool,
    style: StageBorderStyle,
    edge_a: float,
    edge_b: float,
    col: int,
    t_a: float,
    t_b: float,
    alpha: float,
    z: ZIndex,
):
    if alpha <= 0:
        return
    match style:
        case StageBorderStyle.DEFAULT:
            draw_solid_border_strip(
                is_left, PREVIEW_DYNAMIC_STAGE_BORDER_DEFAULT_W, edge_a, edge_b, col, t_a, t_b, alpha, z
            )
        case StageBorderStyle.MEDIUM:
            draw_solid_border_strip(
                is_left, PREVIEW_DYNAMIC_STAGE_BORDER_MEDIUM_W, edge_a, edge_b, col, t_a, t_b, alpha, z
            )
        case StageBorderStyle.LIGHT:
            draw_light_border_strip(PREVIEW_DYNAMIC_STAGE_BORDER_LIGHT_W, edge_a, edge_b, col, t_a, t_b, alpha, z)
        case StageBorderStyle.DISABLED:
            return
        case _:
            assert_never(style)


def draw_solid_border_strip(
    is_left: bool,
    width: float,
    edge_a: float,
    edge_b: float,
    col: int,
    t_a: float,
    t_b: float,
    alpha: float,
    z: ZIndex,
):
    sign = -1 if is_left else 1
    center_a = edge_a + sign * width / 2
    center_b = edge_b + sign * width / 2
    layout = layout_preview_lane_rotated_strip(center_a, center_b, t_a, t_b, width, col)
    if not is_left:
        swap(layout.bl, layout.br)
        swap(layout.tl, layout.tr)
    ActiveSkin.stage_border_preview.draw(layout, z=z, a=alpha)


def draw_light_border_strip(
    width: float, edge_a: float, edge_b: float, col: int, t_a: float, t_b: float, alpha: float, z: ZIndex
):
    layout = layout_preview_lane_rotated_strip(edge_a, edge_b, t_a, t_b, width, col)
    ActiveSkin.lane_divider_preview.draw(layout, z=z, a=alpha)


def draw_dynamic_stage_dividers_slice(
    stage: DynamicStageLike,
    props_a: StageProps,
    props_b: StageProps,
    col: int,
    t_a: float,
    t_b: float,
    z_a: ZIndex,
    z_b: ZIndex,
):
    alpha = slice_lane_alpha(props_a, props_b)
    if alpha <= 0:
        return

    # During a division/parity transition, division.start and division.end describe two
    # different divider sets that need to cross-fade by `progress`. Outside a transition,
    # start == end and we draw one set at full alpha.
    division_a = props_a.division
    division_b = props_b.division
    if division_b.start == division_b.end:
        draw_dynamic_stage_division_set(stage, props_a, props_b, col, t_a, t_b, division_b.start, alpha, z_a)
    else:
        if division_a.start == division_b.start and division_a.end == division_b.end:
            progress = (division_a.progress + division_b.progress) / 2
        else:
            progress = division_b.progress
        if 1 - progress > 0:
            draw_dynamic_stage_division_set(
                stage, props_a, props_b, col, t_a, t_b, division_b.start, alpha * (1 - progress), z_a
            )
        if progress > 0:
            draw_dynamic_stage_division_set(
                stage, props_a, props_b, col, t_a, t_b, division_b.end, alpha * progress, z_b
            )


def draw_dynamic_stage_division_set(
    stage: DynamicStageLike,
    props_a: StageProps,
    props_b: StageProps,
    col: int,
    t_a: float,
    t_b: float,
    div_props: DivisionProps,
    alpha: float,
    z: ZIndex,
):
    """Draw the dividers for one division set across a slice.

    Each divider sits at `pivot(t) + parity_offset + k*size` for an integer index `k`.
    Pivot moves continuously between events, so the divider's x-position varies over
    the slice. We sample at t_a and t_b and emit one slanted strip per `k`:

      * both endpoints inside the (clipped) mask -> draw the full strip.
      * only t_b inside -> divider entered the mask mid-slice; bsearch backwards to
        find the entry time and clip the strip to it.
      * only t_a inside -> divider is leaving; bsearch forwards for the exit time.
      * neither inside -> skip.

    The mask used for in/out tests is `[max(l, -bound), min(r, bound)]`, so dividers
    are clipped to the column boundary the same way they are clipped to the mask
    edges.
    """
    if alpha <= 0:
        return
    size = div_props.size
    if size <= 0:
        return
    parity = div_props.parity
    parity_offset = size / 2 if parity == DivisionParity.ODD else 0

    eps = PREVIEW_DYNAMIC_STAGE_EPS
    divider_w = PREVIEW_DYNAMIC_STAGE_DIVIDER_W
    bound = PreviewLayout.lane_bound

    mask_l_a = max(props_a.lane - props_a.width, -bound)
    mask_r_a = min(props_a.lane + props_a.width, bound)
    mask_l_b = max(props_b.lane - props_b.width, -bound)
    mask_r_b = min(props_b.lane + props_b.width, bound)

    shifted_pivot_a = props_a.pivot_lane + parity_offset
    shifted_pivot_b = props_b.pivot_lane + parity_offset

    # k range: union of indices that could be visible at either endpoint.
    k_lo = min(floor((mask_l_a - shifted_pivot_a + eps) / size), floor((mask_l_b - shifted_pivot_b + eps) / size)) + 1
    k_hi = max(ceil((mask_r_a - shifted_pivot_a - eps) / size), ceil((mask_r_b - shifted_pivot_b - eps) / size)) - 1

    for k in range(k_lo, k_hi + 1):
        pos_a = shifted_pivot_a + k * size
        pos_b = shifted_pivot_b + k * size
        in_mask_a = mask_l_a + eps < pos_a < mask_r_a - eps
        in_mask_b = mask_l_b + eps < pos_b < mask_r_b - eps

        if in_mask_a and in_mask_b:
            draw_divider_strip(pos_a, pos_b, t_a, t_b, divider_w, col, alpha, z)
        elif in_mask_b:
            t_entry = bsearch_divider_mask_edge(stage, k, size, parity_offset, t_a, t_b, target_in_mask=True)
            if t_entry < t_b:
                pos_entry = get_stage_props(stage, t_entry).pivot_lane + parity_offset + k * size
                draw_divider_strip(pos_entry, pos_b, t_entry, t_b, divider_w, col, alpha, z)
        elif in_mask_a:
            t_exit = bsearch_divider_mask_edge(stage, k, size, parity_offset, t_a, t_b, target_in_mask=False)
            if t_exit > t_a:
                pos_exit = get_stage_props(stage, t_exit).pivot_lane + parity_offset + k * size
                draw_divider_strip(pos_a, pos_exit, t_a, t_exit, divider_w, col, alpha, z)


def draw_divider_strip(
    pos_a: float, pos_b: float, t_a: float, t_b: float, width: float, col: int, alpha: float, z: ZIndex
):
    layout = layout_preview_lane_rotated_strip(pos_a, pos_b, t_a, t_b, width, col)
    ActiveSkin.lane_divider_preview.draw(layout, z=z, a=alpha)


def bsearch_divider_mask_edge(
    stage: DynamicStageLike,
    k: int,
    size: float,
    parity_offset: float,
    t_lo: float,
    t_hi: float,
    target_in_mask: bool,
) -> float:
    """Bisect [t_lo, t_hi] for the time at which divider `k` crosses the mask edge.

    Caller knows divider `k` is in-mask at one endpoint and out-of-mask at the other.
    `target_in_mask` says which endpoint is in-mask: True -> t_hi is in (we're looking
    for the entry time on its side), False -> t_lo is in (we're looking for the exit
    time). On exit we return the time on the in-mask side of the converged interval.
    """
    eps = PREVIEW_DYNAMIC_STAGE_EPS
    bound = PreviewLayout.lane_bound
    bisect_lo = t_lo
    bisect_hi = t_hi
    for _ in range(PREVIEW_DYNAMIC_STAGE_BSEARCH_ITERS):
        t_mid = (bisect_lo + bisect_hi) / 2
        props = get_stage_props(stage, t_mid)
        divider_pos = props.pivot_lane + parity_offset + k * size
        mask_l = max(props.lane - props.width, -bound)
        mask_r = min(props.lane + props.width, bound)
        in_mask = mask_l + eps < divider_pos < mask_r - eps
        if in_mask == target_in_mask:
            bisect_hi = t_mid
        else:
            bisect_lo = t_mid
    return bisect_hi if target_in_mask else bisect_lo
