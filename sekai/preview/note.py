from __future__ import annotations

from typing import cast

from sonolus.script.archetype import EntityRef, PreviewArchetype, StandardImport, entity_data, imported
from sonolus.script.interval import lerp, unlerp_clamped
from sonolus.script.sprite import Sprite
from sonolus.script.timing import beat_to_time

from sekai.lib.connector import ConnectorKind, ConnectorLayer
from sekai.lib.ease import EaseType, ease
from sekai.lib.layer import (
    LAYER_NOTE_TICK,
    get_z,
)
from sekai.lib.layout import FlickDirection
from sekai.lib.note import (
    NoteKind,
    get_attach_params,
    get_flick_layer,
    get_note_body_layer,
    get_note_sprite_set,
    map_note_kind,
    mirror_flick_direction,
)
from sekai.lib.options import Options
from sekai.lib.skin import ArrowRenderType, ArrowSpriteSet, BodyRenderType, BodySpriteSet
from sekai.lib.stage import get_stage_props
from sekai.play.note import derive_note_archetypes
from sekai.preview.dynamic_stage import PreviewDynamicStage
from sekai.preview.layout import (
    PreviewData,
    get_adjusted_time,
    layout_preview_flick_arrow,
    layout_preview_flick_arrow_fallback,
    layout_preview_regular_note_body,
    layout_preview_regular_note_body_fallback,
    layout_preview_slim_note_body,
    layout_preview_slim_note_body_fallback,
    layout_preview_tick,
    time_to_preview_col,
    time_to_preview_y,
)


class PreviewBaseNote(PreviewArchetype):
    beat: StandardImport.BEAT
    stage_ref: EntityRef[PreviewDynamicStage] = imported(name="stage")
    lane: float = imported()
    size: float = imported()
    direction: FlickDirection = imported()
    active_head_ref: EntityRef[PreviewBaseNote] = imported(name="activeHead")
    is_attached: bool = imported(name="isAttached")
    connector_ease: EaseType = imported(name="connectorEase")
    segment_kind: ConnectorKind = imported(name="segmentKind")
    segment_alpha: float = imported(name="segmentAlpha")
    segment_layer: ConnectorLayer = imported(name="segmentLayer")
    segment_through_judge_line: bool = imported(name="segmentThroughJudgeLine")
    attach_head_ref: EntityRef[PreviewBaseNote] = imported(name="attachHead")
    attach_tail_ref: EntityRef[PreviewBaseNote] = imported(name="attachTail")
    next_ref: EntityRef[PreviewBaseNote] = imported(name="next")
    prev_ref: EntityRef[PreviewBaseNote] = imported(name="prev")

    kind: NoteKind = entity_data()
    data_init_done: bool = entity_data()
    rel_lane: float = entity_data()
    target_time: float = entity_data()

    def init_data(self):
        if self.data_init_done:
            return

        self.kind = map_note_kind(cast(NoteKind, self.key))

        self.data_init_done = True

        if Options.mirror:
            self.lane *= -1
            self.direction = mirror_flick_direction(self.direction)

        self.target_time = beat_to_time(self.beat)

        if self.stage_ref.index > 0:
            self.rel_lane = self.lane
            self.lane += get_stage_props(self.stage_ref.get(), self.target_time).pivot_lane

        if self.next_ref.index > 0:
            self.next_ref.get().prev_ref = self.ref()

    def preprocess(self):
        self.init_data()

        if self.is_attached:
            attach_head = self.attach_head_ref.get()
            attach_tail = self.attach_tail_ref.get()
            attach_head.init_data()
            attach_tail.init_data()
            self.connector_ease = attach_head.connector_ease
            lane, size = get_attach_params(
                ease_type=attach_head.connector_ease,
                head_lane=attach_head._basic_visual_lane_at(self.target_time),
                head_size=attach_head.size,
                head_target_time=attach_head.target_time,
                tail_lane=attach_tail._basic_visual_lane_at(self.target_time),
                tail_size=attach_tail.size,
                tail_target_time=attach_tail.target_time,
                target_time=self.target_time,
            )
            self.lane = lane
            self.size = size

        PreviewData.max_time = max(PreviewData.max_time, self.target_time)

        if self.is_scored:
            col = max(time_to_preview_col(self.target_time), 0)
            if col < len(PreviewData.note_counts_by_col):
                PreviewData.note_counts_by_col[col] += 1

    def render(self):
        if abs(self.lane) > 12:
            return
        if not self.is_scored:
            return
        draw_note(self.kind, self.lane, self.size, self.direction, self.target_time)

    @property
    def head_ease_frac(self) -> float:
        if self.is_attached:
            return unlerp_clamped(
                self.attach_head_ref.get().target_time, self.attach_tail_ref.get().target_time, self.target_time
            )
        else:
            return 0.0

    @property
    def tail_ease_frac(self) -> float:
        if self.is_attached:
            return unlerp_clamped(
                self.attach_head_ref.get().target_time, self.attach_tail_ref.get().target_time, self.target_time
            )
        else:
            return 1.0

    def _basic_visual_lane_at(self, t: float) -> float:
        if self.stage_ref.index <= 0:
            return self.lane
        return get_stage_props(self.stage_ref.get(), t).pivot_lane + self.rel_lane

    def visual_lane_at(self, t: float) -> float:
        if self.is_attached:
            head = self.attach_head_ref.get()
            tail = self.attach_tail_ref.get()
            note_ease_frac = unlerp_clamped(head.target_time, tail.target_time, self.target_time)
            head_lane = head._basic_visual_lane_at(t)
            tail_lane = tail._basic_visual_lane_at(t)
            return lerp(head_lane, tail_lane, ease(self.connector_ease, note_ease_frac))
        return self._basic_visual_lane_at(t)


def draw_note(kind: NoteKind, lane: float, size: float, direction: FlickDirection, target_time: float):
    col = time_to_preview_col(target_time)
    y = time_to_preview_y(target_time, col)
    sprite_set = get_note_sprite_set(kind, direction)
    draw_note_body(sprite_set.body, kind, lane, size, target_time, col, y)
    draw_note_arrow(sprite_set.arrow, kind, lane, size, target_time, direction, col, y)
    draw_note_tick(sprite_set.tick, lane, target_time, col, y)


def draw_note_body(
    sprites: BodySpriteSet, kind: NoteKind, lane: float, size: float, target_time: float, col: int, y: float
):
    layer = get_note_body_layer(kind)
    z = get_z(layer, time=get_adjusted_time(target_time, col), lane=lane)
    match sprites.render_type:
        case BodyRenderType.NORMAL:
            left_layout, middle_layout, right_layout = layout_preview_regular_note_body(lane, size, col, y)
            sprites.left.draw(left_layout, z=z)
            sprites.middle.draw(middle_layout, z=z)
            sprites.right.draw(right_layout, z=z)
        case BodyRenderType.SLIM:
            left_layout, middle_layout, right_layout = layout_preview_slim_note_body(lane, size, col, y)
            sprites.left.draw(left_layout, z=z)
            sprites.middle.draw(middle_layout, z=z)
            sprites.right.draw(right_layout, z=z)
        case BodyRenderType.NORMAL_FALLBACK:
            layout = layout_preview_regular_note_body_fallback(lane, size, col, y)
            sprites.middle.draw(layout, z=z)
        case BodyRenderType.SLIM_FALLBACK:
            layout = layout_preview_slim_note_body_fallback(lane, size, col, y)
            sprites.middle.draw(layout, z=z)


def draw_note_arrow(
    sprites: ArrowSpriteSet,
    kind: NoteKind,
    lane: float,
    size: float,
    target_time: float,
    direction: FlickDirection,
    col: int,
    y: float,
):
    z = get_z(
        get_flick_layer(kind),
        time=get_adjusted_time(target_time, col),
        lane=lane,
        etc=direction,
    )
    match sprites.render_type:
        case ArrowRenderType.NORMAL:
            layout = layout_preview_flick_arrow(lane, size, direction, col, y)
            sprites.get_sprite(size, direction).draw(layout, z=z)
        case ArrowRenderType.FALLBACK:
            layout = layout_preview_flick_arrow_fallback(lane, size, direction, col, y)
            sprites.get_sprite(size, direction).draw(layout, z=z)


def draw_note_tick(sprite: Sprite, lane: float, target_time: float, col: int, y: float):
    z = get_z(LAYER_NOTE_TICK, time=get_adjusted_time(target_time, col), lane=lane)
    layout = layout_preview_tick(lane, col, y)
    sprite.draw(layout, z=z)


PREVIEW_NOTE_ARCHETYPES = derive_note_archetypes(PreviewBaseNote)
