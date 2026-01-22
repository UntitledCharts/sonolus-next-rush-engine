from sonolus.script.interval import clamp, lerp, unlerp, unlerp_clamped

from sekai.lib.layer import LAYER_SIM_LINE, get_z
from sekai.lib.layout import DynamicLayout, approach, get_alpha, layout_sim_line
from sekai.lib.options import Options
from sekai.lib.skin import ActiveSkin


def draw_sim_line(
    left_lane: float,
    left_visual_progress: float,
    left_target_time: float,
    right_lane: float,
    right_visual_progress: float,
    right_target_time: float,
):
    if not Options.sim_line_enabled:
        return

    if left_visual_progress < DynamicLayout.progress_start and right_visual_progress < DynamicLayout.progress_start:
        return
    if left_visual_progress > DynamicLayout.progress_cutoff and right_visual_progress > DynamicLayout.progress_cutoff:
        return
    if (left_visual_progress < 1 < right_visual_progress) or (left_visual_progress > 1 > right_visual_progress):
        return

    adj_left_progress = clamp(left_visual_progress, DynamicLayout.progress_start, DynamicLayout.progress_cutoff)
    adj_right_progress = clamp(right_visual_progress, DynamicLayout.progress_start, DynamicLayout.progress_cutoff)
    if abs(left_visual_progress - right_visual_progress) > 1e-6:
        adj_left_frac = unlerp(left_visual_progress, right_visual_progress, adj_left_progress)
        adj_right_frac = unlerp(left_visual_progress, right_visual_progress, adj_right_progress)
        adj_left_lane = lerp(left_lane, right_lane, adj_left_frac)
        adj_right_lane = lerp(left_lane, right_lane, adj_right_frac)
    else:
        adj_left_lane = left_lane
        adj_right_lane = right_lane
    adj_left_travel = approach(adj_left_progress)
    adj_right_travel = approach(adj_right_progress)
    if abs(adj_left_lane - adj_right_lane) < 1e-6 and abs(adj_left_travel - adj_right_travel) < 1e-6:
        return
    layout = layout_sim_line(
        adj_left_lane,
        adj_left_travel,
        adj_right_lane,
        adj_right_travel,
    )
    progress_diff = abs(left_visual_progress - right_visual_progress)
    fade_alpha = unlerp_clamped(1, 0.5, progress_diff)
    z = get_z(
        LAYER_SIM_LINE,
        (left_target_time + right_target_time) / 2,
        (left_lane + right_lane) / 2,
    )
    a = (
        min(
            get_alpha(left_target_time),
            get_alpha(right_target_time),
        )
        * fade_alpha
    )
    ActiveSkin.sim_line.draw(layout, z=z, a=a)
