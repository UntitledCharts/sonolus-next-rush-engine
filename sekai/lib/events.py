from sonolus.script.interval import lerp, unlerp_clamped
from sonolus.script.vec import Vec2

from sekai.lib.layout import (
    LANE_B,
    LANE_T,
    Layout,
    aspect_ratio,
    get_perspective_y,
    layout_fever_border,
    layout_fever_cover_left,
    layout_fever_cover_right,
    layout_fever_cover_sky,
    layout_fever_gauge_left,
    layout_fever_gauge_right,
    layout_fever_text,
    layout_lane_fever,
    layout_sekai_stage,
    layout_sekai_stage_t,
    layout_skill_bar,
    perspective_rect,
    screen,
)
from sekai.lib.options import Options
from sekai.lib.particle import ActiveParticles
from sekai.lib.skin import ActiveSkin, SkillEffects


def draw_fever_side_cover(z: float, time: float):
    if not ActiveSkin.background.is_available:
        return
    if Options.hide_ui >= 3:
        return
    if Options.fever_effect == 2:
        return
    layout1 = layout_fever_cover_left()
    layout2 = layout_fever_cover_right()
    a = unlerp_clamped(0, 0.25, time) * 0.75
    ActiveSkin.background.draw(layout1, z, a=a)
    ActiveSkin.background.draw(layout2, z, a=a)

    if screen().t < Layout.t:
        return
    layout_sky = layout_fever_cover_sky()
    ActiveSkin.background.draw(layout_sky, z, a=a)


def draw_fever_side_bar(z: float, time: float):
    if not ActiveSkin.sekai_stage_fever.is_available:
        return
    if Options.hide_ui >= 3:
        return
    if Options.fever_effect == 2:
        return
    a = unlerp_clamped(0, 0.25, time)
    if screen().t < Layout.t or not ActiveSkin.sekai_stage_fever_tablet.is_available:
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
    if percentage < 0.9:
        layout_text = layout_fever_text()
        layout_lane1 = layout_lane_fever(-6, 1)
        layout_lane2 = layout_lane_fever(6, 1)
        ActiveParticles.fever_start_text.spawn(layout_text, 1, False)
        if Options.fever_effect == 0:
            ActiveParticles.fever_start_lane.spawn(layout_lane1, 1, False)
            ActiveParticles.fever_start_lane.spawn(layout_lane2, 1, False)
    else:
        layout_text = layout_fever_text()
        layout_lane1 = layout_lane_fever(-6, 1)
        layout_lane2 = layout_lane_fever(6, 1)
        mid = (get_perspective_y(1) + get_perspective_y(-1)) / 2
        layout_effect1 = perspective_rect(l=-6 - 0.5, r=-6 + 0.5, t=mid - 0.050075, b=mid + 0.050075)
        layout_effect2 = perspective_rect(l=6 - 0.5, r=6 + 0.5, t=mid - 0.050075, b=mid + 0.050075)
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
    layout_text = layout_fever_text()
    layout_lane1 = layout_lane_fever(-6, 0.5)
    layout_lane2 = layout_lane_fever(6, 0.5)
    ActiveParticles.fever_chance_text.spawn(layout_text, 1, False)
    if Options.fever_effect == 0:
        ActiveParticles.fever_chance_lane.spawn(layout_lane1, 1, False)
        ActiveParticles.fever_chance_lane.spawn(layout_lane2, 1, False)


def draw_skill_bar(z: float, z2: float, time: float, num: int, effect: SkillEffects, level: int):
    if Options.hide_ui >= 3:
        return
    if not Options.skill_effect:
        return
    if not ActiveSkin.skill_bar.is_available:
        return

    enter_progress = unlerp_clamped(0, 0.25, time)
    exit_progress = unlerp_clamped(2.75, 3, time)

    anim = enter_progress - exit_progress

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
    layout = layout_skill_bar(current_center, w, h)
    ActiveSkin.skill_bar.draw(layout, z, anim)

    x = -7.5 + x_ratio
    y = 0.45 - y_ratio
    icon_start_center = Vec2(x=x - 0.2, y=y)
    icon_target_center = Vec2(x=x, y=y)
    icon_current_center = lerp(icon_start_center, icon_target_center, anim)
    h = 0.045
    w = h * 7
    layout = layout_skill_bar(icon_current_center, w, h)
    ActiveSkin.skill_icon.get_sprite(num).draw(layout, z2, anim)

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
    layout = layout_skill_bar(text_current_center, w, h)
    if time <= 1.5:
        ActiveSkin.skill_level.get_sprite(level).draw(layout, z2, final_anim)
    else:
        ActiveSkin.skill_value.get_sprite(level, effect).draw(layout, z2, final_anim)
