from sonolus.script.archetype import EntityRef, PreviewArchetype, callback, entity_info_at, imported
from sonolus.script.containers import sort_linked_entities
from sonolus.script.interval import lerp
from sonolus.script.printing import PrintColor, PrintFormat
from sonolus.script.quad import Quad
from sonolus.script.sprite import Sprite
from sonolus.script.timing import beat_to_time

from sekai.lib import archetype_names
from sekai.lib.baseevent import init_event_list
from sekai.lib.layer import LAYER_BEAT_LINE, get_z
from sekai.lib.layout import CameraInfo, get_camera_info, get_next_camera_event_time
from sekai.lib.level_config import EngineRevision, LevelConfig, init_level_config
from sekai.lib.particle import init_particles
from sekai.lib.skin import ActiveSkin, init_skin
from sekai.lib.ui import init_ui
from sekai.preview.dynamic_stage import PreviewCameraChange
from sekai.preview.events import PreviewSkill
from sekai.preview.layout import (
    PREVIEW_CAMERA_MARKER_ALPHA,
    PREVIEW_COLUMN_SECS,
    PREVIEW_DYNAMIC_STAGE_DIVIDER_W,
    PREVIEW_DYNAMIC_STAGE_TIME_INCREMENT,
    PreviewData,
    PreviewLayout,
    init_preview_layout,
    layout_preview_bar_line,
    layout_preview_camera_jump_connector,
    layout_preview_column_divider,
    layout_preview_lane_rotated_strip,
    print_at_col_top,
)
from sekai.preview.stage import draw_preview_cover, draw_preview_stage


class PreviewInitialization(PreviewArchetype):
    name = archetype_names.INITIALIZATION

    revision: EngineRevision = imported(name="revision", default=EngineRevision.LATEST)
    first_camera_ref: EntityRef[PreviewCameraChange] = imported(name="firstCamera")

    @callback(order=1)
    def preprocess(self):
        init_level_config(self.revision)
        init_ui()
        init_skin()
        init_particles()

        if not ActiveSkin.lane_background_preview.is_available:
            LevelConfig.dynamic_stages = False

        init_preview_layout()
        init_event_list(self.first_camera_ref)
        init_skill()

    def render(self):
        if not LevelConfig.dynamic_stages:
            draw_preview_stage()
        draw_preview_cover()
        print_preview_col_head_text()
        draw_beat_lines()
        if LevelConfig.dynamic_stages:
            draw_column_dividers()
            draw_camera_markers()


def print_preview_col_head_text():
    combo = 0
    for col in range(PreviewLayout.column_count):
        if col < len(PreviewData.note_counts_by_col):
            combo += PreviewData.note_counts_by_col[col]
            print_at_col_top(combo, col, fmt=PrintFormat.ENTITY_COUNT, color=PrintColor.RED, side="right")
        print_at_col_top((col + 1) * PREVIEW_COLUMN_SECS, col, fmt=PrintFormat.TIME, color=PrintColor.CYAN, side="left")


def draw_beat_lines():
    visible_secs = PreviewLayout.visible_secs
    beat = 0
    while beat_to_time(beat) <= visible_secs:
        for beat_offset, extend_scale in (
            (0, 0.3),
            (0.25, 0.1),
            (0.5, 0.2),
            (0.75, 0.1),
        ):
            t = beat_to_time(beat + beat_offset)
            if t > visible_secs:
                continue
            left_layout = +Quad
            right_layout = +Quad
            if LevelConfig.dynamic_stages:
                left_layout @= layout_preview_bar_line(t, extend="left_in", extend_scale=extend_scale)
                right_layout @= layout_preview_bar_line(t, extend="right_in", extend_scale=extend_scale)
            else:
                left_layout @= layout_preview_bar_line(t, extend="left_only", extend_scale=extend_scale)
                right_layout @= layout_preview_bar_line(t, extend="right_only", extend_scale=extend_scale)
            ActiveSkin.beat_line.draw(left_layout, z=get_z(LAYER_BEAT_LINE), a=0.5)
            ActiveSkin.beat_line.draw(right_layout, z=get_z(LAYER_BEAT_LINE), a=0.5)
        beat += 1


def draw_column_dividers():
    for col in range(1, PreviewLayout.column_count):
        ActiveSkin.preview_divider.draw(layout_preview_column_divider(col), z=get_z(LAYER_BEAT_LINE), a=0.5)


def draw_camera_markers():
    z_edge = get_z(LAYER_BEAT_LINE, etc=1)
    z_target = get_z(LAYER_BEAT_LINE, etc=2)
    for col in range(PreviewLayout.column_count):
        col_t_lo = col * PREVIEW_COLUMN_SECS
        col_t_hi = (col + 1) * PREVIEW_COLUMN_SECS

        t_a = col_t_lo
        camera_a = +CameraInfo
        camera_a_next = +CameraInfo
        camera_a @= get_camera_info(t_a)
        while t_a < col_t_hi:
            next_event = get_next_camera_event_time(t_a)
            t_b = min(t_a + PREVIEW_DYNAMIC_STAGE_TIME_INCREMENT, col_t_hi, next_event)
            at_event = t_b == next_event
            camera_b = get_camera_info(t_b, left_limit=at_event)

            draw_camera_line_slice(
                ActiveSkin.camera_line,
                camera_a.lane - camera_a.size,
                camera_b.lane - camera_b.size,
                col,
                t_a,
                t_b,
                z_edge,
            )
            draw_camera_line_slice(
                ActiveSkin.camera_line,
                camera_a.lane + camera_a.size,
                camera_b.lane + camera_b.size,
                col,
                t_a,
                t_b,
                z_edge,
            )
            draw_camera_line_slice(
                ActiveSkin.camera_target_line,
                camera_a.lane + camera_a.zoom_target_lane,
                camera_b.lane + camera_b.zoom_target_lane,
                col,
                t_a,
                t_b,
                z_target,
            )

            t_a = t_b
            if at_event:
                camera_a_next @= get_camera_info(t_a)
                draw_camera_jump_connectors(camera_b, camera_a_next, col, t_a, z_edge, z_target)
                camera_a @= camera_a_next
            else:
                camera_a @= camera_b


def draw_camera_line_slice(
    sprite: Sprite,
    lane_a: float,
    lane_b: float,
    col: int,
    t_a: float,
    t_b: float,
    z: float,
):
    bound = PreviewLayout.lane_bound
    de = lane_b - lane_a
    if de == 0:
        if abs(lane_a) > bound:
            return
        clip_t_a = t_a
        clip_t_b = t_b
        clip_lane_a = lane_a
        clip_lane_b = lane_b
    else:
        frac_pos = (bound - lane_a) / de
        frac_neg = (-bound - lane_a) / de
        frac_lo = max(0.0, min(frac_pos, frac_neg))
        frac_hi = min(1.0, max(frac_pos, frac_neg))
        if frac_lo >= frac_hi:
            return
        clip_t_a = lerp(t_a, t_b, frac_lo)
        clip_t_b = lerp(t_a, t_b, frac_hi)
        clip_lane_a = lerp(lane_a, lane_b, frac_lo)
        clip_lane_b = lerp(lane_a, lane_b, frac_hi)

    layout = layout_preview_lane_rotated_strip(
        clip_lane_a, clip_lane_b, clip_t_a, clip_t_b, PREVIEW_DYNAMIC_STAGE_DIVIDER_W, col
    )
    sprite.draw(layout, z=z, a=PREVIEW_CAMERA_MARKER_ALPHA)


def draw_camera_jump_connectors(
    camera_pre: CameraInfo,
    camera_post: CameraInfo,
    col: int,
    t: float,
    z_edge: float,
    z_target: float,
):
    left_pre = camera_pre.lane - camera_pre.size
    left_post = camera_post.lane - camera_post.size
    if left_pre != left_post:
        draw_camera_jump_connector(ActiveSkin.camera_line, left_pre, left_post, col, t, z_edge)

    right_pre = camera_pre.lane + camera_pre.size
    right_post = camera_post.lane + camera_post.size
    if right_pre != right_post:
        draw_camera_jump_connector(ActiveSkin.camera_line, right_pre, right_post, col, t, z_edge)

    target_pre = camera_pre.lane + camera_pre.zoom_target_lane
    target_post = camera_post.lane + camera_post.zoom_target_lane
    if target_pre != target_post:
        draw_camera_jump_connector(ActiveSkin.camera_target_line, target_pre, target_post, col, t, z_target)


def draw_camera_jump_connector(
    sprite: Sprite,
    lane_a: float,
    lane_b: float,
    col: int,
    t: float,
    z: float,
):
    bound = PreviewLayout.lane_bound
    lo = min(lane_a, lane_b)
    hi = max(lane_a, lane_b)
    if hi <= -bound or lo >= bound:
        return
    clip_lo = max(lo, -bound)
    clip_hi = min(hi, bound)
    if clip_hi <= clip_lo:
        return
    layout = layout_preview_camera_jump_connector(clip_lo, clip_hi, t, PREVIEW_DYNAMIC_STAGE_DIVIDER_W, col)
    sprite.draw(layout, z=z, a=PREVIEW_CAMERA_MARKER_ALPHA)


def init_skill():
    entity_count = 0
    while entity_info_at(entity_count).index == entity_count:
        entity_count += 1
    list_head, list_length = initial_list(entity_count)

    if list_length == 0:
        return

    sorted_list_head = sort_entities(list_head)

    setting_count(sorted_list_head.index)


def initial_list(entity_count):
    list_head = 0
    list_length = 0
    watch_note_id = PreviewSkill._compile_time_id()
    for i in range(entity_count):
        entity_index: int = entity_count - 1 - i
        info = entity_info_at(entity_index)
        is_watch_note = watch_note_id in PreviewSkill._get_mro_id_array(info.archetype_id)
        if is_watch_note:
            PreviewSkill.at(entity_index).preprocess()
            list_length += 1
            PreviewSkill.at(entity_index).next_ref.index = list_head
            list_head = entity_index
    return list_head, list_length


def sort_entities(index: int):
    head = PreviewSkill.at(index)
    return sort_linked_entities(
        head.ref(),
        get_value=lambda head: head.time,
        get_next_ref=lambda head: head.next_ref,
    )


def setting_count(head: int) -> None:
    ptr = head
    count = 0
    while ptr > 0:
        count += 1
        PreviewSkill.at(ptr).num += count

        ptr = PreviewSkill.at(ptr).next_ref.index
