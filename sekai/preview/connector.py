from math import ceil
from typing import assert_never

from sonolus.script.archetype import EntityRef, PreviewArchetype, callback, entity_data, imported
from sonolus.script.interval import clamp, lerp, remap_clamped, unlerp_clamped
from sonolus.script.sprite import Sprite

from sekai.lib import archetype_names
from sekai.lib.connector import (
    ConnectorKind,
    ConnectorLayer,
    get_active_connector_sprites,
    get_connector_alpha_option,
    get_connector_quality_option,
    get_connector_z,
    get_damage_connector_sprite,
    get_guide_connector_sprite,
)
from sekai.lib.ease import EaseType, ease
from sekai.lib.layout import get_alpha
from sekai.lib.level_config import LevelConfig
from sekai.preview import note
from sekai.preview.layout import (
    get_adjusted_time,
    layout_preview_slide_connector_segment,
    preview_axis_to_y,
    preview_column_secs,
    time_to_preview_col,
)


class PreviewConnector(PreviewArchetype):
    name = archetype_names.CONNECTOR

    head_ref: EntityRef[note.PreviewBaseNote] = imported(name="head")
    tail_ref: EntityRef[note.PreviewBaseNote] = imported(name="tail")
    segment_head_ref: EntityRef[note.PreviewBaseNote] = imported(name="segmentHead")
    segment_tail_ref: EntityRef[note.PreviewBaseNote] = imported(name="segmentTail")

    kind: ConnectorKind = entity_data()
    ease_type: EaseType = entity_data()

    @callback(order=1)  # After note preprocessing is done
    def preprocess(self):
        head = self.head
        self.kind = self.segment_head.segment_kind
        self.ease_type = head.connector_ease

    def render(self):
        head = self.head
        tail = self.tail
        draw_connector(
            kind=self.kind,
            ease_type=self.ease_type,
            head_ref=self.head_ref,
            head_size=head.size,
            head_target_time=head.target_time,
            head_preview_axis=head.preview_axis,
            head_ease_frac=head.head_ease_frac,
            tail_ref=self.tail_ref,
            tail_size=tail.size,
            tail_target_time=tail.target_time,
            tail_preview_axis=tail.preview_axis,
            tail_ease_frac=tail.tail_ease_frac,
            segment_head_target_time=self.segment_head.target_time,
            segment_head_lane=self.segment_head.lane,
            segment_head_alpha=self.segment_head.segment_alpha,
            segment_tail_target_time=self.segment_tail.target_time,
            segment_tail_alpha=self.segment_tail.segment_alpha,
            layer=self.segment_head.segment_layer,
        )

    @property
    def head(self):
        return self.head_ref.get()

    @property
    def tail(self):
        return self.tail_ref.get()

    @property
    def segment_head(self):
        return self.segment_head_ref.get()

    @property
    def segment_tail(self):
        return self.segment_tail_ref.get()


def draw_connector(
    kind: ConnectorKind,
    ease_type: EaseType,
    head_ref: EntityRef[note.PreviewBaseNote],
    head_size: float,
    head_target_time: float,
    head_preview_axis: float,
    head_ease_frac: float,
    tail_ref: EntityRef[note.PreviewBaseNote],
    tail_size: float,
    tail_target_time: float,
    tail_preview_axis: float,
    tail_ease_frac: float,
    segment_head_target_time: float,
    segment_head_lane: float,
    segment_head_alpha: float,
    segment_tail_target_time: float,
    segment_tail_alpha: float,
    layer: ConnectorLayer,
):
    if head_target_time == tail_target_time:
        return

    if ease_type == EaseType.NONE:
        tail_size = head_size

    normal_sprite = Sprite(-1)
    match kind:
        case (
            ConnectorKind.ACTIVE_NORMAL
            | ConnectorKind.ACTIVE_CRITICAL
            | ConnectorKind.ACTIVE_FAKE_NORMAL
            | ConnectorKind.ACTIVE_FAKE_CRITICAL
        ):
            sprites = get_active_connector_sprites(kind)
            normal_sprite @= sprites.connection.normal
        case (
            ConnectorKind.GUIDE_NEUTRAL
            | ConnectorKind.GUIDE_RED
            | ConnectorKind.GUIDE_GREEN
            | ConnectorKind.GUIDE_BLUE
            | ConnectorKind.GUIDE_YELLOW
            | ConnectorKind.GUIDE_PURPLE
            | ConnectorKind.GUIDE_CYAN
            | ConnectorKind.GUIDE_BLACK
        ):
            normal_sprite @= get_guide_connector_sprite(kind)
        case ConnectorKind.DAMAGE | ConnectorKind.FAKE_DAMAGE:
            normal_sprite @= get_damage_connector_sprite()
        case ConnectorKind.NONE:
            return
        case _:
            assert_never(kind)

    match kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_CRITICAL:
            segment_head_alpha = 1.0
            segment_tail_alpha = 1.0
        case ConnectorKind.ACTIVE_FAKE_NORMAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
            segment_head_alpha = 1.0
            segment_tail_alpha = 1.0
        case (
            ConnectorKind.GUIDE_NEUTRAL
            | ConnectorKind.GUIDE_RED
            | ConnectorKind.GUIDE_GREEN
            | ConnectorKind.GUIDE_BLUE
            | ConnectorKind.GUIDE_YELLOW
            | ConnectorKind.GUIDE_PURPLE
            | ConnectorKind.GUIDE_CYAN
            | ConnectorKind.GUIDE_BLACK
            | ConnectorKind.DAMAGE
            | ConnectorKind.FAKE_DAMAGE
        ):
            pass
        case _:
            assert_never(kind)

    head_alpha = remap_clamped(
        segment_head_target_time, segment_tail_target_time, segment_head_alpha, segment_tail_alpha, head_target_time
    )
    tail_alpha = remap_clamped(
        segment_head_target_time, segment_tail_target_time, segment_head_alpha, segment_tail_alpha, tail_target_time
    )

    match ease_type:
        case EaseType.NONE | EaseType.LINEAR if head_alpha == tail_alpha and not LevelConfig.dynamic_stages:
            quality_dist_scale = 0
        case _:
            quality_dist_scale = 100 * abs(tail_target_time - head_target_time) / preview_column_secs()
    quality_alpha_scale = 30 * abs(head_alpha - tail_alpha)
    segment_count = max(1, ceil(get_connector_quality_option(kind) * max(quality_dist_scale, quality_alpha_scale)))

    eased_head_ease_frac = ease(ease_type, head_ease_frac)
    eased_tail_ease_frac = ease(ease_type, tail_ease_frac)

    head = head_ref.get()
    tail = tail_ref.get()

    last_lane = head.visual_lane_at(head_target_time)
    last_size = head_size
    last_alpha = head_alpha
    last_target_time = head_target_time
    last_axis = head_preview_axis
    last_col = time_to_preview_col(last_target_time)

    for i in range(1, segment_count + 1):
        next_frac = i / segment_count
        next_ease_frac = lerp(head_ease_frac, tail_ease_frac, next_frac)
        next_interp_frac = unlerp_clamped(eased_head_ease_frac, eased_tail_ease_frac, ease(ease_type, next_ease_frac))
        next_target_time = lerp(head_target_time, tail_target_time, next_frac)
        head_lane_at_t = head.visual_lane_at(next_target_time)
        if ease_type == EaseType.NONE:
            tail_lane_at_t = head_lane_at_t
        else:
            tail_lane_at_t = tail.visual_lane_at(next_target_time)
        next_lane = lerp(head_lane_at_t, tail_lane_at_t, next_interp_frac)
        next_size = max(1e-3, lerp(head_size, tail_size, next_interp_frac))
        next_alpha = lerp(head_alpha, tail_alpha, next_frac)
        next_axis = lerp(head_preview_axis, tail_preview_axis, next_frac)
        next_col = time_to_preview_col(next_target_time)

        a = clamp(
            get_alpha((last_target_time + next_target_time) / 2)
            * (last_alpha + next_alpha)
            / 2
            * get_connector_alpha_option(kind),
            0,
            1,
        )

        for col in range(last_col, next_col + 1):
            z = get_connector_z(
                kind,
                get_adjusted_time(segment_head_target_time, col),
                segment_head_lane,
                active=False,
                layer=layer,
            )
            start_y = preview_axis_to_y(last_axis, col)
            end_y = preview_axis_to_y(next_axis, col)
            for layout in layout_preview_slide_connector_segment(
                start_lane=last_lane,
                start_size=last_size,
                start_y=start_y,
                end_lane=next_lane,
                end_size=next_size,
                end_y=end_y,
                col=col,
            ):
                normal_sprite.draw(layout, z=z.tuple, a=a)

        last_lane = next_lane
        last_size = next_size
        last_alpha = next_alpha
        last_target_time = next_target_time
        last_axis = next_axis
        last_col = next_col
