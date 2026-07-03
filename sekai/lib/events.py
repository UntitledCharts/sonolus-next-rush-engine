from math import floor

from sonolus.script.globals import level_memory
from sonolus.script.interval import lerp, unlerp_clamped
from sonolus.script.quad import Quad, Rect
from sonolus.script.record import Record
from sonolus.script.sprite import Sprite
from sonolus.script.vec import Vec2

from sekai.lib.layer import (
    LAYER_BACKGROUND_SIDE,
    LAYER_GAUGE,
    LAYER_JUDGMENT_SKILL,
    LAYER_SKILL_BAR,
    LAYER_SKILL_ETC,
    LAYER_STAGE,
    get_z_alt,
)
from sekai.lib.layout import (
    IDENTITY_AFFINE_TRANSFORM,
    LANE_B,
    LANE_T,
    TARGET_ASPECT_RATIO,
    AffineTransform2d,
    DynamicLayout,
    Layout,
    aspect_ratio,
    get_note_spawn_depth,
    get_perspective_y,
    layout_dynamic_fever_side,
    layout_fever_border,
    layout_fever_cover,
    layout_fever_cover_sky,
    layout_fever_gauge_left,
    layout_fever_gauge_right,
    layout_fever_text,
    layout_lane_fever,
    layout_sekai_stage,
    layout_sekai_stage_t,
    layout_skill_bar,
    layout_skill_judgment_line,
    perspective_rect,
    safe_area,
    screen,
    tilt_depth,
    tilt_width_factor,
    transform_quad,
)
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import Options, SkillMode, Version
from sekai.lib.particle import ActiveParticles
from sekai.lib.skin import ActiveSkin


@level_memory
class Fever:
    fever_chance_time: float
    fever_start_time: float
    fever_chance_current_combo: int
    fever_chance_cant_super_fever: bool
    fever_last_count: int
    fever_first_count: int
    min_l: float
    max_r: float
    has_active: bool
    y_offset: float
    alpha_l: float
    alpha_r: float
    left_transform: AffineTransform2d
    right_transform: AffineTransform2d


def draw_fever_side_cover(draw_time: float):
    if not ActiveSkin.background.is_available:
        return
    if Options.hide_ui >= 3:
        return
    if Options.fever_effect == 2:
        return
    if LevelConfig.dynamic_stages:
        l = 0
        r = 0
        if Fever.has_active:
            l = Fever.min_l - 0.5
            r = Fever.max_r + 0.5
    else:
        l = -6.5
        r = 6.5

    layout1 = +Quad
    layout2 = +Quad
    if LevelConfig.dynamic_stages:
        layout1 @= Fever.left_transform.transform_quad(layout_fever_cover(l, 0))
        layout2 @= Fever.right_transform.transform_quad(layout_fever_cover(0, r))
    else:
        layout1 @= layout_fever_cover(l, 0)
        layout2 @= layout_fever_cover(0, r)
    a = unlerp_clamped(0, 0.25, draw_time) * 0.75
    ActiveSkin.background.draw(layout1, LAYER_BACKGROUND_SIDE, a=a)
    ActiveSkin.background.draw(layout2, LAYER_BACKGROUND_SIDE, a=a)

    if screen().t < DynamicLayout.t:
        return
    layout_sky = layout_fever_cover_sky()
    ActiveSkin.background.draw(layout_sky, LAYER_BACKGROUND_SIDE, a=a)


def draw_fever_side_bar(draw_time: float):
    if Options.hide_ui >= 3:
        return
    if Options.fever_effect == 2:
        return
    a = unlerp_clamped(0, 0.25, draw_time)
    use_dynamic_draw = LevelConfig.dynamic_stages or (
        not ActiveSkin.sekai_stage_fever.is_available and ActiveSkin.sekai_fever_gauge_background.is_available
    )
    if use_dynamic_draw:
        l = -6.0
        r = 6.0
        a_left = a
        a_right = a
        if LevelConfig.dynamic_stages:
            if not Fever.has_active:
                return

            l = Fever.min_l
            r = Fever.max_r

            a_left = a * Fever.alpha_l
            a_right = a * Fever.alpha_r

        thickness = 0.5

        is_tablet = screen().t >= DynamicLayout.t

        side_sprite = +Sprite
        if is_tablet:
            side_sprite @= ActiveSkin.sekai_fever_gauge_background_tablet
        else:
            side_sprite @= ActiveSkin.sekai_fever_gauge_background

        t_top = get_note_spawn_depth()
        if is_tablet:
            t_top = -0.05

        layout1 = +Quad
        layout2 = +Quad

        fever_text_t = lerp(LANE_B, LANE_T, 0.78)
        super_fever_text_t = lerp(LANE_B, LANE_T, 0.90)

        zoom = DynamicLayout.w_scale / Layout.w_scale

        p1_h = 0.002 * zoom
        p2_h = 0.001 * zoom

        point1 = +Quad
        point2 = +Quad

        fever_depth = tilt_depth(fever_text_t, 1.0)
        super_fever_depth = tilt_depth(super_fever_text_t, 1.0)
        fever_l = r * tilt_width_factor(fever_depth) - 0.6 * fever_depth
        super_fever_l = r * tilt_width_factor(super_fever_depth) - 0.7 * super_fever_depth

        f_h = 0.07 * zoom
        sf_h = 0.053 * zoom

        fever_text_layout = +Quad
        super_fever_text_layout = +Quad

        if LevelConfig.dynamic_stages:
            layout1 @= Fever.left_transform.transform_quad(
                perspective_rect(l=l - thickness, r=l, t=t_top, b=get_perspective_y(-1))
            )
            layout2 @= Fever.right_transform.transform_quad(
                perspective_rect(l=r, r=r + thickness, t=t_top, b=get_perspective_y(-1))
            )
            point1 @= Fever.left_transform.transform_quad(
                perspective_rect(l=l - 1, r=l, t=fever_text_t - p1_h, b=fever_text_t + p1_h)
            )
            point2 @= Fever.left_transform.transform_quad(
                perspective_rect(l=l - 1, r=l, t=super_fever_text_t - p2_h, b=super_fever_text_t + p2_h)
            )
            fever_text_layout @= Fever.right_transform.transform_quad(
                transform_quad(Rect(l=fever_l, r=fever_l + 4.5, t=fever_depth - f_h, b=fever_depth + f_h))
            )
            super_fever_text_layout @= Fever.right_transform.transform_quad(
                transform_quad(
                    Rect(
                        l=super_fever_l,
                        r=super_fever_l + 2.94,
                        t=super_fever_depth - sf_h,
                        b=super_fever_depth + sf_h,
                    )
                )
            )
        else:
            layout1 @= perspective_rect(l=l - thickness, r=l, t=t_top, b=get_perspective_y(-1))
            layout2 @= perspective_rect(l=r, r=r + thickness, t=t_top, b=get_perspective_y(-1))
            point1 @= perspective_rect(l=l - 1, r=l, t=fever_text_t - p1_h, b=fever_text_t + p1_h)
            point2 @= perspective_rect(l=l - 1, r=l, t=super_fever_text_t - p2_h, b=super_fever_text_t + p2_h)
            fever_text_layout @= transform_quad(
                Rect(l=fever_l, r=fever_l + 4.5, t=fever_depth - f_h, b=fever_depth + f_h)
            )
            super_fever_text_layout @= transform_quad(
                Rect(l=super_fever_l, r=super_fever_l + 2.94, t=super_fever_depth - sf_h, b=super_fever_depth + sf_h)
            )

        if a_left > 0:
            side_sprite.draw(layout1, get_z_alt(LAYER_STAGE), a=a_left)
            ActiveSkin.guide_neutral.draw(point1, get_z_alt(LAYER_STAGE, 1), a=a_left)
            ActiveSkin.guide_neutral.draw(point2, get_z_alt(LAYER_STAGE, 1), a=a_left)
        if a_right > 0:
            side_sprite.draw(layout2, get_z_alt(LAYER_STAGE), a=a_right)
            ActiveSkin.sekai_fever_text.draw(fever_text_layout, get_z_alt(LAYER_STAGE, 1), a=a_right)
            if screen().t < DynamicLayout.t:
                ActiveSkin.sekai_super_fever_text.draw(super_fever_text_layout, get_z_alt(LAYER_STAGE, 1), a=a_right)
            else:
                ActiveSkin.sekai_super_fever_text_tablet.draw(
                    super_fever_text_layout, get_z_alt(LAYER_STAGE, 1), a=a_right
                )
    elif screen().t < DynamicLayout.t or not ActiveSkin.sekai_stage_fever_tablet.is_available:
        if ActiveSkin.sekai_stage_fever.is_available:
            layout = layout_sekai_stage()
            ActiveSkin.sekai_stage_fever.draw(layout, get_z_alt(LAYER_STAGE), a=a)
    else:
        layout = layout_sekai_stage_t()
        ActiveSkin.sekai_stage_fever_tablet.draw(layout, get_z_alt(LAYER_STAGE), a=a)


def draw_fever_gauge(percentage: float):
    if not ActiveSkin.sekai_fever_gauge.available:
        return
    if Options.hide_ui >= 3:
        return
    if Options.fever_effect == 2:
        return

    layout1 = +Quad
    layout2 = +Quad
    a_left = 0.6
    a_right = 0.6
    if LevelConfig.dynamic_stages:
        if not Fever.has_active:
            return

        l = Fever.min_l
        r = Fever.max_r

        a_left = 0.6 * Fever.alpha_l
        a_right = 0.6 * Fever.alpha_r

        thickness = 0.5

        layout1 @= Fever.left_transform.transform_quad(layout_dynamic_fever_side(l - thickness, l, percentage))
        layout2 @= Fever.right_transform.transform_quad(layout_dynamic_fever_side(r, r + thickness, percentage))
    else:
        t = lerp(LANE_B, LANE_T, percentage)
        layout1 @= layout_fever_gauge_left(t)
        layout2 @= layout_fever_gauge_right(t)

    if a_left > 0:
        ActiveSkin.sekai_fever_gauge.get_sprite(percentage).draw(layout1, get_z_alt(LAYER_GAUGE), a=a_left)
    if a_right > 0:
        ActiveSkin.sekai_fever_gauge.get_sprite(percentage).draw(layout2, get_z_alt(LAYER_GAUGE), a=a_right)


def spawn_fever_start_particle(percentage: float):
    if Options.hide_ui >= 3:
        return
    if Options.fever_effect == 2:
        return
    if percentage < 0.78:
        return
    if LevelConfig.dynamic_stages:
        l = 0
        r = 0
        if Fever.has_active:
            l = Fever.min_l
            r = Fever.max_r
    else:
        l = -6
        r = 6
    layout_text = layout_fever_text()
    layout_lane1 = +Quad
    layout_lane2 = +Quad
    if LevelConfig.dynamic_stages:
        layout_lane1 @= Fever.left_transform.transform_quad(layout_lane_fever(l, 1))
        layout_lane2 @= Fever.right_transform.transform_quad(layout_lane_fever(r, 1))
    else:
        layout_lane1 @= layout_lane_fever(l, 1)
        layout_lane2 @= layout_lane_fever(r, 1)
    if percentage < 0.9:
        ActiveParticles.fever_start_text.spawn(layout_text, 1, False)
        if Options.fever_effect == 0:
            ActiveParticles.fever_start_lane.spawn(layout_lane1, 1, False)
            ActiveParticles.fever_start_lane.spawn(layout_lane2, 1, False)
    else:
        mid = (get_perspective_y(1) + get_perspective_y(-1)) / 2
        layout_effect1 = +Quad
        layout_effect2 = +Quad
        if LevelConfig.dynamic_stages:
            layout_effect1 @= Fever.left_transform.transform_quad(
                perspective_rect(l=l - 0.5, r=l + 0.5, t=mid - 0.050075, b=mid + 0.050075)
            )
            layout_effect2 @= Fever.right_transform.transform_quad(
                perspective_rect(l=r - 0.5, r=r + 0.5, t=mid - 0.050075, b=mid + 0.050075)
            )
        else:
            layout_effect1 @= perspective_rect(l=l - 0.5, r=l + 0.5, t=mid - 0.050075, b=mid + 0.050075)
            layout_effect2 @= perspective_rect(l=r - 0.5, r=r + 0.5, t=mid - 0.050075, b=mid + 0.050075)
        ActiveParticles.super_fever_start_text.spawn(layout_text, 1, False)
        if Options.fever_effect == 0:
            ActiveParticles.super_fever_start_lane.spawn(layout_lane1, 1, False)
            ActiveParticles.super_fever_start_lane.spawn(layout_lane2, 1, False)
            ActiveParticles.super_fever_start_effect.spawn(layout_effect1, 1, False)
            ActiveParticles.super_fever_start_effect.spawn(layout_effect2, 1, False)
    layout_border = layout_fever_border()
    ActiveParticles.fever_border.spawn(layout_border, 1, False)


def spawn_fever_chance_particle():
    if Options.hide_ui >= 3:
        return
    if Options.fever_effect == 2:
        return
    if LevelConfig.dynamic_stages:
        l = 0
        r = 0
        if Fever.has_active:
            l = Fever.min_l - 0.5
            r = Fever.max_r + 0.5
    else:
        l = -6.5
        r = 6.5
    layout_text = layout_fever_text()
    layout_lane1 = +Quad
    layout_lane2 = +Quad
    if LevelConfig.dynamic_stages:
        layout_lane1 @= Fever.left_transform.transform_quad(layout_lane_fever(l, 0.5))
        layout_lane2 @= Fever.right_transform.transform_quad(layout_lane_fever(r, 0.5))
    else:
        layout_lane1 @= layout_lane_fever(l, 0.5)
        layout_lane2 @= layout_lane_fever(r, 0.5)
    ActiveParticles.fever_chance_text.spawn(layout_text, 1, False)
    if Options.fever_effect == 0:
        ActiveParticles.fever_chance_lane.spawn(layout_lane1, 1, False)
        ActiveParticles.fever_chance_lane.spawn(layout_lane2, 1, False)


# Glyph indices into the shared UI Number sprite group (0-9 digits, 10 alt-color 0, 11 +).
SKILL_GLYPH_MINUS = 12
SKILL_GLYPH_L = 13
SKILL_GLYPH_V = 14
SKILL_GLYPH_DOT = 15
SKILL_GLYPH_PERCENT = 16
SKILL_GLYPH_SECOND = 17

SKILL_GLYPH_WIDTH_FACTOR = 6.25
SKILL_GLYPH_HEIGHT_FACTOR = 1
SKILL_GLYPH_GAP_FACTOR = -4
SKILL_DOT_GAP_FACTOR = -6
SKILL_PERCENT_GAP_FACTOR = -2


def skill_glyph_gap_factor(glyph: int) -> float:
    result = SKILL_GLYPH_GAP_FACTOR
    if glyph == SKILL_GLYPH_DOT:
        result = SKILL_DOT_GAP_FACTOR
    elif glyph == SKILL_GLYPH_PERCENT:
        result = SKILL_PERCENT_GAP_FACTOR
    return result


def skill_gap_factor(left_glyph: int, right_glyph: int) -> float:
    result = skill_glyph_gap_factor(left_glyph)
    right = skill_glyph_gap_factor(right_glyph)
    if right != SKILL_GLYPH_GAP_FACTOR:
        result = right
    return result


SKILL_BAR_BASE_X = -6.7
SKILL_BAR_H = 0.08
SKILL_BAR_HALF_W = SKILL_BAR_H * 21
SKILL_NOTCH_PUSH = 1.35777
SKILL_EDGE_MARGIN = 0.3
SKILL_REF_TOP_EDGE = 0.05529
SKILL_REF_Y_RATIO = 0.0


class SkillNumberSpec(Record):
    has_prefix: bool
    has_minus: bool
    int_val: int
    int_digits: int
    has_mid: bool
    dec_digit: int
    has_suffix: bool
    suffix_glyph: int

    @property
    def count(self) -> int:
        prefix_count = 3 if self.has_prefix else 0
        minus_count = 1 if self.has_minus else 0
        mid_count = 2 if self.has_mid else 0
        suffix_count = 1 if self.has_suffix else 0
        return prefix_count + minus_count + self.int_digits + mid_count + suffix_count

    def glyph_at(self, i: int) -> int:
        prefix_count = 3 if self.has_prefix else 0
        minus_count = 1 if self.has_minus else 0
        int_start = prefix_count + minus_count
        result = self.suffix_glyph
        if self.has_prefix and i == 0:
            result = SKILL_GLYPH_L
        elif self.has_prefix and i == 1:
            result = SKILL_GLYPH_V
        elif self.has_prefix and i == 2:
            result = SKILL_GLYPH_DOT
        elif self.has_minus and i == prefix_count:
            result = SKILL_GLYPH_MINUS
        elif i < int_start + self.int_digits:
            result = floor(self.int_val / 10 ** (self.int_digits - 1 - (i - int_start))) % 10
        elif self.has_mid and i == int_start + self.int_digits:
            result = SKILL_GLYPH_DOT
        elif self.has_mid and i == int_start + self.int_digits + 1:
            result = self.dec_digit
        return result


def draw_skill_bar(
    draw_time: float, num: int, effect: SkillMode, level: int, value: int, scale: float, duration: float
):
    if Options.hide_ui >= 3:
        return
    if not Options.skill_effect:
        return
    if not ActiveSkin.skill_bar_score.is_available:
        return

    enter_progress = unlerp_clamped(0, 0.25, draw_time)
    exit_progress = unlerp_clamped(2.75, 3, draw_time)

    anim = enter_progress - exit_progress

    layout = +Quad
    x_ratio = 0
    y_ratio = 0
    if LevelConfig.ui_version == Version.v3:
        scale_ratio = min(1, aspect_ratio() / TARGET_ASPECT_RATIO)
        has_side_notch = screen().l != safe_area().l or screen().r != safe_area().r
        edge_offset = SKILL_NOTCH_PUSH * scale_ratio if has_side_notch else -SKILL_EDGE_MARGIN
        bar_center_x = screen().l / Layout.fixed_w_scale + SKILL_BAR_HALF_W + edge_offset
        x_ratio = bar_center_x - SKILL_BAR_BASE_X
        y_ratio = SKILL_REF_TOP_EDGE - (screen().t - Layout.t) / Layout.fixed_h_scale + SKILL_REF_Y_RATIO

        x = SKILL_BAR_BASE_X + x_ratio
        y = 0.433 - y_ratio
        start_center = Vec2(x=x - 0.2, y=y)
        target_center = Vec2(x=x, y=y)
        current_center = lerp(start_center, target_center, anim)
        h = SKILL_BAR_H
        w = SKILL_BAR_HALF_W
        layout @= layout_skill_bar(current_center, w, h)
    else:
        x = 0
        y = 0.633
        current_center = Vec2(x=x, y=y)
        h = 0.1
        w = h * 21
        layout @= layout_skill_bar(current_center, w, h)
    match effect:
        case SkillMode.SCORE:
            ActiveSkin.skill_bar_score.draw(layout, LAYER_SKILL_BAR, anim)
        case SkillMode.HEAL:
            ActiveSkin.skill_bar_life.draw(layout, LAYER_SKILL_BAR, anim)
        case SkillMode.JUDGMENT:
            ActiveSkin.skill_bar_judgment.draw(layout, LAYER_SKILL_BAR, anim)

    if LevelConfig.ui_version == Version.v3:
        x = -7.5 + x_ratio
        y = 0.45 - y_ratio
        icon_start_center = Vec2(x=x - 0.2, y=y)
        icon_target_center = Vec2(x=x, y=y)
        icon_current_center = lerp(icon_start_center, icon_target_center, anim)
        h = 0.045
        w = h * 7
        layout @= layout_skill_bar(icon_current_center, w, h)
    else:
        x = -1.5
        y = 0.633
        icon_current_center = Vec2(x=x, y=y)
        h = 0.045
        w = h * 7
        layout @= layout_skill_bar(icon_current_center, w, h)
    ActiveSkin.skill_icon.get_sprite(num).draw(layout, LAYER_SKILL_ETC, anim)

    if not ActiveSkin.skill_number.available:
        return

    text_current_center = +Vec2

    if LevelConfig.ui_version == Version.v3:
        x = -5.53 + x_ratio
        y = 0.474 - y_ratio
        text_start_center = Vec2(x=x - 0.2, y=y)
        text_target_center = Vec2(x=x, y=y)
        text_changing_center = Vec2(x=x + 0.1, y=y)

        mid_progress = unlerp_clamped(1.5, 1.75, draw_time)
        current_start_pos = +Vec2
        if draw_time >= 1.5 and draw_time < 2.75:
            current_start_pos @= text_changing_center
            final_anim = mid_progress
        else:
            current_start_pos @= text_start_center
            if draw_time < 1.5:
                final_anim = enter_progress
            else:
                final_anim = mid_progress - exit_progress
        text_current_center @= lerp(current_start_pos, text_target_center, final_anim)
        h = 0.024
        w = h * 14
    else:
        x = 1.5
        y = 0.655
        text_current_center @= Vec2(x=x, y=y)
        h = 0.028
        w = h * 14
        final_anim = anim

    spec = +SkillNumberSpec
    spec.has_prefix = draw_time <= 1.5 or LevelConfig.ui_version == Version.v1
    spec.has_minus = False
    spec.int_val = 0
    spec.has_mid = False
    spec.dec_digit = 0
    spec.has_suffix = False
    spec.suffix_glyph = 0
    if spec.has_prefix:
        if level < 0:
            spec.has_minus = True
            spec.int_val = -level
        else:
            spec.int_val = level
    else:
        match effect:
            case SkillMode.SCORE:
                scaled = floor(scale * 1000 + 0.5)
                spec.int_val = scaled // 10
                if scaled % 10 > 0:
                    spec.has_mid = True
                    spec.dec_digit = scaled % 10
                spec.has_suffix = True
                spec.suffix_glyph = SKILL_GLYPH_PERCENT
            case SkillMode.HEAL:
                if value < 0:
                    spec.has_minus = True
                    spec.int_val = -value
                else:
                    spec.int_val = value
            case SkillMode.JUDGMENT:
                scaled = floor(duration * 10 + 0.5)
                spec.int_val = scaled // 10
                if scaled % 10 > 0:
                    spec.has_mid = True
                    spec.dec_digit = scaled % 10
                spec.has_suffix = True
                spec.suffix_glyph = SKILL_GLYPH_SECOND

    spec.int_digits = 1
    temp_n = spec.int_val // 10
    while temp_n > 0:
        temp_n //= 10
        spec.int_digits += 1

    count = spec.count

    glyph_half_w = h * SKILL_GLYPH_WIDTH_FACTOR
    glyph_half_h = h * SKILL_GLYPH_HEIGHT_FACTOR

    total_width = count * 2 * glyph_half_w
    for i in range(count - 1):
        total_width += h * skill_gap_factor(spec.glyph_at(i), spec.glyph_at(i + 1))

    if LevelConfig.ui_version == Version.v3:
        cursor_x = text_current_center.x + w - total_width
    else:
        cursor_x = text_current_center.x - w

    for i in range(count):
        glyph = spec.glyph_at(i)
        layout @= layout_skill_bar(Vec2(x=cursor_x + glyph_half_w, y=text_current_center.y), glyph_half_w, glyph_half_h)
        ActiveSkin.skill_number.get_sprite(glyph).draw(layout, LAYER_SKILL_ETC, final_anim)
        cursor_x += 2 * glyph_half_w
        if i < count - 1:
            cursor_x += h * skill_gap_factor(glyph, spec.glyph_at(i + 1))


def draw_judgment_effect(
    draw_time: float,
    l: float = -6,
    r: float = 6,
    stage_alpha: float = 1.0,
    y_offset: float = 0.0,
    *,
    duration: float = 6.0,
    transform: AffineTransform2d = IDENTITY_AFFINE_TRANSFORM,
):
    enter_progress = unlerp_clamped(0, 0.25, draw_time)
    exit_progress = unlerp_clamped(duration - 0.25, duration, draw_time)

    anim = enter_progress - exit_progress
    layout = transform.transform_quad(layout_skill_judgment_line(l, r, y_offset))
    z = get_z_alt(LAYER_JUDGMENT_SKILL)
    ActiveSkin.skill_judgment_line.draw(layout, z=z, a=anim * stage_alpha)


def reset_fever_bounds():
    Fever.min_l = 1e8
    Fever.max_r = -1e8
    Fever.has_active = False
    Fever.y_offset = 0.0
    Fever.alpha_l = 0.0
    Fever.alpha_r = 0.0
    Fever.left_transform = IDENTITY_AFFINE_TRANSFORM
    Fever.right_transform = IDENTITY_AFFINE_TRANSFORM
