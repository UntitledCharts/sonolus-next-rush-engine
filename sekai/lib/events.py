from sonolus.script.globals import level_memory
from sonolus.script.interval import lerp, unlerp_clamped
from sonolus.script.quad import Quad, Rect
from sonolus.script.vec import Vec2

from sekai.lib.layer import LAYER_JUDGMENT_SKILL, get_z
from sekai.lib.layout import (
    LANE_B,
    LANE_T,
    DynamicLayout,
    Layout,
    aspect_ratio,
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
    screen,
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


def draw_fever_side_cover(z: float, time: float):
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

    layout1 = layout_fever_cover(l, 0)
    layout2 = layout_fever_cover(0, r)
    a = unlerp_clamped(0, 0.25, time) * 0.75
    ActiveSkin.background.draw(layout1, z, a=a)
    ActiveSkin.background.draw(layout2, z, a=a)

    if screen().t < DynamicLayout.t:
        return
    layout_sky = layout_fever_cover_sky()
    ActiveSkin.background.draw(layout_sky, z, a=a)


def draw_fever_side_bar(z: float, z_t: float, time: float):
    if Options.hide_ui >= 3:
        return
    if Options.fever_effect == 2:
        return
    a = unlerp_clamped(0, 0.25, time)
    if LevelConfig.dynamic_stages:
        if not Fever.has_active:
            return

        l = Fever.min_l
        r = Fever.max_r

        a_left = a * Fever.alpha_l
        a_right = a * Fever.alpha_r

        thickness = 0.5

        layout1 = perspective_rect(l=l - thickness, r=l, t=LANE_T, b=get_perspective_y(-1))
        layout2 = perspective_rect(l=r, r=r + thickness, t=LANE_T, b=get_perspective_y(-1))

        fever_text_t = lerp(LANE_B, LANE_T, 0.78)
        super_fever_text_t = lerp(LANE_B, LANE_T, 0.90)

        zoom = DynamicLayout.w_scale / Layout.w_scale

        p1_h = 0.002 * zoom
        p2_h = 0.001 * zoom

        point1 = perspective_rect(l=l - 1, r=l, t=fever_text_t - p1_h, b=fever_text_t + p1_h)
        point2 = perspective_rect(l=l - 1, r=l, t=super_fever_text_t - p2_h, b=super_fever_text_t + p2_h)

        fever_l = (r - 0.6) * fever_text_t
        super_fever_l = (r - 0.7) * super_fever_text_t

        f_h = 0.07 * zoom
        sf_h = 0.053 * zoom

        fever_text_layout = transform_quad(Rect(l=fever_l, r=fever_l + 4.5, t=fever_text_t - f_h, b=fever_text_t + f_h))
        super_fever_text_layout = transform_quad(
            Rect(l=super_fever_l, r=super_fever_l + 2.94, t=super_fever_text_t - sf_h, b=super_fever_text_t + sf_h)
        )

        if a_left > 0:
            ActiveSkin.sekai_fever_gauge_background.draw(layout1, z, a=a_left)
            ActiveSkin.guide_neutral.draw(point1, z_t, a=a_left)
            ActiveSkin.guide_neutral.draw(point2, z_t, a=a_left)
        if a_right > 0:
            ActiveSkin.sekai_fever_gauge_background.draw(layout2, z, a=a_right)
            ActiveSkin.sekai_fever_text.draw(fever_text_layout, z_t, a=a_right)
            ActiveSkin.sekai_super_fever_text.draw(super_fever_text_layout, z_t, a=a_right)
    elif screen().t < DynamicLayout.t or not ActiveSkin.sekai_stage_fever_tablet.is_available:
        if ActiveSkin.sekai_stage_fever.is_available:
            layout = layout_sekai_stage()
            ActiveSkin.sekai_stage_fever.draw(layout, z, a=a)
    else:
        layout = layout_sekai_stage_t()
        ActiveSkin.sekai_stage_fever_tablet.draw(layout, z, a=a)


def draw_fever_gauge(z: float, percentage: float):
    if not ActiveSkin.sekai_fever_gauge.available:
        return
    if Options.hide_ui >= 3:
        return
    if Options.fever_effect == 2:
        return

    if LevelConfig.dynamic_stages:
        if not Fever.has_active:
            return

        l = Fever.min_l
        r = Fever.max_r

        a_left = 0.6 * Fever.alpha_l
        a_right = 0.6 * Fever.alpha_r

        thickness = 0.5

        layout1 = layout_dynamic_fever_side(l - thickness, l, percentage)
        layout2 = layout_dynamic_fever_side(r, r + thickness, percentage)

        if a_left > 0:
            ActiveSkin.sekai_fever_gauge.get_sprite(percentage).draw(layout1, z, a=a_left)
        if a_right > 0:
            ActiveSkin.sekai_fever_gauge.get_sprite(percentage).draw(layout2, z, a=a_right)
    else:
        t = lerp(LANE_B, LANE_T, percentage)
        layout1 = layout_fever_gauge_left(t)
        layout2 = layout_fever_gauge_right(t)
        ActiveSkin.sekai_fever_gauge.get_sprite(percentage).draw(layout1, z, a=0.6)
        ActiveSkin.sekai_fever_gauge.get_sprite(percentage).draw(layout2, z, a=0.6)


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
    if percentage < 0.9:
        layout_text = layout_fever_text()
        layout_lane1 = layout_lane_fever(l, 1)
        layout_lane2 = layout_lane_fever(r, 1)
        ActiveParticles.fever_start_text.spawn(layout_text, 1, False)
        if Options.fever_effect == 0:
            ActiveParticles.fever_start_lane.spawn(layout_lane1, 1, False)
            ActiveParticles.fever_start_lane.spawn(layout_lane2, 1, False)
    else:
        layout_text = layout_fever_text()
        layout_lane1 = layout_lane_fever(l, 1)
        layout_lane2 = layout_lane_fever(r, 1)
        mid = (get_perspective_y(1) + get_perspective_y(-1)) / 2
        layout_effect1 = perspective_rect(l=l - 0.5, r=l + 0.5, t=mid - 0.050075, b=mid + 0.050075)
        layout_effect2 = perspective_rect(l=r - 0.5, r=r + 0.5, t=mid - 0.050075, b=mid + 0.050075)
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
    layout_lane1 = layout_lane_fever(l, 0.5)
    layout_lane2 = layout_lane_fever(r, 0.5)
    ActiveParticles.fever_chance_text.spawn(layout_text, 1, False)
    if Options.fever_effect == 0:
        ActiveParticles.fever_chance_lane.spawn(layout_lane1, 1, False)
        ActiveParticles.fever_chance_lane.spawn(layout_lane2, 1, False)


def draw_skill_bar(z: float, z2: float, time: float, num: int, effect: SkillMode, level: int):
    if Options.hide_ui >= 3:
        return
    if not Options.skill_effect:
        return
    if not ActiveSkin.skill_bar_score.is_available:
        return

    enter_progress = unlerp_clamped(0, 0.25, time)
    exit_progress = unlerp_clamped(2.75, 3, time)

    anim = enter_progress - exit_progress

    layout = +Quad
    x_ratio = 0
    y_ratio = 0
    if LevelConfig.ui_version == Version.v3:
        x_ratio = 0.7 - 0.7 * (aspect_ratio() - 1.3333) ** 3

        raw_val = -0.405 * aspect_ratio() + 0.72
        y_ratio = max(raw_val, 0)

        x = -6.7 + x_ratio
        y = 0.433 - y_ratio
        start_center = Vec2(x=x - 0.2, y=y)
        target_center = Vec2(x=x, y=y)
        current_center = lerp(start_center, target_center, anim)
        h = 0.08
        w = h * 21
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
            ActiveSkin.skill_bar_score.draw(layout, z, anim)
        case SkillMode.HEAL:
            ActiveSkin.skill_bar_life.draw(layout, z, anim)
        case SkillMode.JUDGMENT:
            ActiveSkin.skill_bar_judgment.draw(layout, z, anim)

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
    ActiveSkin.skill_icon.get_sprite(num).draw(layout, z2, anim)

    if LevelConfig.ui_version == Version.v3:
        x = -5.58 + x_ratio
        y = 0.474 - y_ratio
        text_start_center = Vec2(x=x - 0.2, y=y)
        text_target_center = Vec2(x=x, y=y)
        text_changing_center = Vec2(x=x + 0.1, y=y)

        mid_progress = unlerp_clamped(1.5, 1.75, time)
        current_start_pos = +Vec2
        if time >= 1.5 and time < 2.75:
            current_start_pos @= text_changing_center
            final_anim = mid_progress
        else:
            current_start_pos @= text_start_center
            if time < 1.5:
                final_anim = enter_progress
            else:
                final_anim = mid_progress - exit_progress
        text_current_center = lerp(current_start_pos, text_target_center, final_anim)
        h = 0.027
        w = h * 14
        layout @= layout_skill_bar(text_current_center, w, h)
    else:
        x = 1.5
        y = 0.655
        text_current_center = Vec2(x=x, y=y)
        h = 0.032
        w = h * 14
        final_anim = anim
        layout @= layout_skill_bar(text_current_center, w, h)
    if time <= 1.5 or LevelConfig.ui_version == Version.v1:
        ActiveSkin.skill_level.get_sprite(level).draw(layout, z2, final_anim)
    else:
        ActiveSkin.skill_value.get_sprite(effect).draw(layout, z2, final_anim)


def draw_judgment_effect(time: float, l: float = -6, r: float = 6, stage_alpha: float = 1.0, y_offset: float = 0.0):
    enter_progress = unlerp_clamped(0, 0.25, time)
    exit_progress = unlerp_clamped(5.75, 6, time)

    anim = enter_progress - exit_progress
    layout = layout_skill_judgment_line(l, r, y_offset)
    z = get_z(LAYER_JUDGMENT_SKILL)
    ActiveSkin.skill_judgment_line.draw(layout, z=z, a=anim * stage_alpha)


def reset_fever_bounds():
    Fever.min_l = 1e8
    Fever.max_r = -1e8
    Fever.has_active = False
    Fever.y_offset = 0.0
    Fever.alpha_l = 0.0
    Fever.alpha_r = 0.0
