from __future__ import annotations

from typing import assert_never

from sonolus.script.archetype import EntityRef, WatchArchetype, callback, entity_data, entity_memory, imported
from sonolus.script.interval import Interval, lerp, remap_clamped, unlerp_clamped
from sonolus.script.particle import ParticleHandle
from sonolus.script.runtime import delta_time, is_replay, is_skip, time

from sekai.debug import DISABLE_NOTES
from sekai.lib import archetype_names
from sekai.lib.connector import (
    CONNECTOR_LENIENCY,
    CONNECTOR_SLOT_SPAWN_PERIOD,
    CONNECTOR_THROUGH_JUDGE_LINE_DESPAWN_DELAY,
    CONNECTOR_TRAIL_SPAWN_PERIOD,
    ActiveConnectorInfo,
    ConnectorKind,
    ConnectorVisualState,
    destroy_looped_particle,
    draw_connector,
    draw_connector_slot_glow_effect,
    schedule_connector_sfx,
    spawn_connector_slot_particles,
    spawn_linear_connector_trail_particle,
    update_circular_connector_particle,
    update_linear_connector_particle,
)
from sekai.lib.ease import EaseType, ease
from sekai.lib.layout import compute_hitbox, current_layout_transform
from sekai.lib.note import draw_hitbox_bounds_overlay, draw_slide_note_head, get_attach_params
from sekai.lib.options import Options
from sekai.lib.streams import Streams
from sekai.lib.timescale import group_hide_notes, update_timescale_group
from sekai.watch import note


class WatchConnector(WatchArchetype):
    name = archetype_names.CONNECTOR

    head_ref: EntityRef[note.WatchBaseNote] = imported(name="head")
    tail_ref: EntityRef[note.WatchBaseNote] = imported(name="tail")
    segment_head_ref: EntityRef[note.WatchBaseNote] = imported(name="segmentHead")
    segment_tail_ref: EntityRef[note.WatchBaseNote] = imported(name="segmentTail")
    active_head_ref: EntityRef[note.WatchBaseNote] = imported(name="activeHead")
    active_tail_ref: EntityRef[note.WatchBaseNote] = imported(name="activeTail")

    kind: ConnectorKind = entity_data()
    ease_type: EaseType = entity_data()
    start_time: float = entity_data()
    end_time: float = entity_data()
    visual_active_interval: Interval = entity_data()

    @callback(order=1)
    def preprocess(self):
        if DISABLE_NOTES:
            return
        head = self.head
        tail = self.tail
        self.kind = self.segment_head.segment_kind
        self.ease_type = head.connector_ease
        self.visual_active_interval.start = min(head.target_time, tail.target_time)
        self.visual_active_interval.end = max(head.target_time, tail.target_time)
        self.start_time = min(
            self.visual_active_interval.start,
            head.start_time,
            tail.start_time,
        )
        self.end_time = self.visual_active_interval.end
        if self.segment_head.segment_through_judge_line:
            self.end_time += CONNECTOR_THROUGH_JUDGE_LINE_DESPAWN_DELAY

        if self.head_ref.index == self.active_head_ref.index:
            # This is the first connector, so spawn the WatchSlideManager.
            WatchSlideManager.spawn(active_head_ref=self.active_head_ref, active_tail_ref=self.active_tail_ref)

        self.schedule_sfx()

    def spawn_time(self) -> float:
        if DISABLE_NOTES:
            return 1e8
        return self.start_time

    def despawn_time(self) -> float:
        return self.end_time

    @callback(order=-1)
    def update_sequential(self):
        update_timescale_group(self.head.timescale_group)
        update_timescale_group(self.tail.timescale_group)
        update_timescale_group(self.segment_head.timescale_group)

        if self.active_head_ref.index > 0 and time() in self.visual_active_interval:
            visual_lane, visual_size = self.get_attached_params(time())
            head = self.head
            tail = self.tail
            self.active_connector_info.visual_lane = visual_lane
            self.active_connector_info.visual_size = visual_size
            self.active_connector_info.visual_y_offset = remap_clamped(
                head.target_time,
                tail.target_time,
                head.visual_y_offset,
                tail.visual_y_offset,
                time(),
            )
            self.active_connector_info.connector_kind = self.kind
        if group_hide_notes(self.segment_head.timescale_group) and self.active_head_ref.index > 0:
            self.active_connector_info.connector_kind = ConnectorKind.NONE

    def update_parallel(self):
        if time() < self.visual_active_interval.end or self.segment_head.segment_through_judge_line:
            head = self.head
            tail = self.tail
            segment_head = self.segment_head
            segment_tail = self.segment_tail
            if self.active_head_ref.index > 0:
                if is_replay():
                    visual_state = Streams.connector_visual_states[self.index].get_previous_inclusive(time())
                elif time() < self.active_head.target_time:
                    visual_state = ConnectorVisualState.WAITING
                else:
                    visual_state = ConnectorVisualState.ACTIVE
            else:
                visual_state = ConnectorVisualState.WAITING
            if group_hide_notes(segment_head.timescale_group):
                return
            if self.active_tail_ref.index > 0 and time() >= self.active_tail.despawn_time():
                return
            if time() >= head.target_time and not segment_head.segment_through_judge_line:
                head_visual_progress = 1.0 - remap_clamped(
                    head.target_time, tail.target_time, head.visual_y_offset, tail.visual_y_offset, time()
                )
                head_target_time = time()
                if self.ease_type == EaseType.NONE:
                    head_lane = head.visual_lane
                    head_size = head.size
                    head_ease_frac = head.head_ease_frac
                else:
                    head_ease_frac = remap_clamped(
                        head.target_time, tail.target_time, head.head_ease_frac, tail.tail_ease_frac, time()
                    )
                    head_interp_frac = unlerp_clamped(
                        ease(self.ease_type, head.head_ease_frac),
                        ease(self.ease_type, tail.tail_ease_frac),
                        ease(self.ease_type, head_ease_frac),
                    )
                    head_lane = lerp(head.visual_lane, tail.visual_lane, head_interp_frac)
                    head_size = lerp(head.size, tail.size, head_interp_frac)
            else:
                head_lane = head.visual_lane
                head_size = head.size
                head_visual_progress = head.visual_progress
                head_target_time = head.target_time
                head_ease_frac = head.head_ease_frac
            draw_connector(
                kind=self.kind,
                visual_state=visual_state,
                ease_type=self.ease_type,
                head_lane=head_lane,
                head_size=head_size,
                head_visual_progress=head_visual_progress,
                head_target_time=head_target_time,
                head_ease_frac=head_ease_frac,
                tail_lane=tail.visual_lane,
                tail_size=tail.size,
                tail_visual_progress=tail.visual_progress,
                tail_target_time=tail.target_time,
                tail_ease_frac=tail.tail_ease_frac,
                segment_head_target_time=segment_head.target_time,
                segment_head_lane=segment_head.lane,
                segment_head_alpha=segment_head.segment_alpha,
                segment_tail_target_time=segment_tail.target_time,
                segment_tail_alpha=segment_tail.segment_alpha,
                layer=segment_head.segment_layer,
                bypass_tail_target_time_check=segment_head.segment_through_judge_line,
            )
        if Options.show_hitboxes and self.active_head_ref.index > 0 and time() in self.visual_active_interval:
            input_lane, input_size = self.get_attached_params(time())
            head = self.head
            tail = self.tail
            input_y_offset = remap_clamped(
                head.target_time,
                tail.target_time,
                head.y_offset_at(time()),
                tail.y_offset_at(time()),
                time(),
            )
            bounds = compute_hitbox(
                current_layout_transform(), input_lane, input_size, CONNECTOR_LENIENCY, input_y_offset
            ).bounds
            draw_hitbox_bounds_overlay(bounds, 0.6)

    def get_attached_params(self, target_time: float) -> tuple[float, float]:
        head = self.head_ref.get().effective_attach_head
        tail = self.tail_ref.get().effective_attach_tail
        return get_attach_params(
            ease_type=self.ease_type,
            head_lane=head._basic_visual_lane_at(target_time),
            head_size=head.size,
            head_target_time=head.target_time,
            tail_lane=tail._basic_visual_lane_at(target_time),
            tail_size=tail.size,
            tail_target_time=tail.target_time,
            target_time=target_time,
        )

    def schedule_sfx(self):
        if is_replay() and not Options.auto_sfx:
            if self.head_ref.index == self.active_head_ref.index:
                last_sfx_kind = ConnectorKind.NONE
                last_time = -1e8
                for next_time, next_sfx_kind in Streams.connector_effect_kinds[
                    self.active_head_ref.index
                ].iter_items_from(-2):
                    match last_sfx_kind:
                        case (
                            ConnectorKind.ACTIVE_NORMAL
                            | ConnectorKind.ACTIVE_CRITICAL
                            | ConnectorKind.ACTIVE_FAKE_NORMAL
                            | ConnectorKind.ACTIVE_FAKE_CRITICAL
                        ):
                            schedule_connector_sfx(
                                last_sfx_kind, self.segment_head.timescale_group, last_time, next_time
                            )
                        case (
                            ConnectorKind.NONE
                            | ConnectorKind.GUIDE_NEUTRAL
                            | ConnectorKind.GUIDE_RED
                            | ConnectorKind.GUIDE_GREEN
                            | ConnectorKind.GUIDE_BLUE
                            | ConnectorKind.GUIDE_YELLOW
                            | ConnectorKind.GUIDE_PURPLE
                            | ConnectorKind.GUIDE_CYAN
                            | ConnectorKind.GUIDE_BLACK
                        ):
                            pass
                        case _:
                            assert_never(last_sfx_kind)
                    last_sfx_kind = next_sfx_kind
                    last_time = next_time
        elif self.head_ref.index == self.segment_head_ref.index:
            match self.kind:
                case (
                    ConnectorKind.ACTIVE_NORMAL
                    | ConnectorKind.ACTIVE_CRITICAL
                    | ConnectorKind.ACTIVE_FAKE_NORMAL
                    | ConnectorKind.ACTIVE_FAKE_CRITICAL
                ):
                    schedule_connector_sfx(
                        self.kind,
                        self.segment_head.timescale_group,
                        self.segment_head.target_time,
                        self.segment_tail.target_time,
                    )
                case (
                    ConnectorKind.NONE
                    | ConnectorKind.GUIDE_NEUTRAL
                    | ConnectorKind.GUIDE_RED
                    | ConnectorKind.GUIDE_GREEN
                    | ConnectorKind.GUIDE_BLUE
                    | ConnectorKind.GUIDE_YELLOW
                    | ConnectorKind.GUIDE_PURPLE
                    | ConnectorKind.GUIDE_CYAN
                    | ConnectorKind.GUIDE_BLACK
                ):
                    pass
                case _:
                    assert_never(self.kind)

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

    @property
    def active_head(self):
        return self.active_head_ref.get()

    @property
    def active_tail(self):
        return self.active_tail_ref.get()

    @property
    def active_connector_info(self) -> ActiveConnectorInfo:
        return self.active_head_ref.get().active_connector_info


class WatchSlideManager(WatchArchetype):
    name = archetype_names.SLIDE_MANAGER

    active_head_ref: EntityRef[note.WatchBaseNote] = entity_memory()
    active_tail_ref: EntityRef[note.WatchBaseNote] = entity_memory()

    last_kind: ConnectorKind = entity_memory()
    circular_particle: ParticleHandle = entity_memory()
    linear_particle: ParticleHandle = entity_memory()
    next_trail_spawn_time: float = entity_memory()
    next_slot_spawn_time: float = entity_memory()

    def initialize(self):
        self.next_trail_spawn_time = -1e8
        self.next_slot_spawn_time = -1e8

    def spawn_time(self) -> float:
        return self.active_head.target_time

    def despawn_time(self) -> float:
        return self.active_tail.despawn_time()

    def update_parallel(self):
        if is_skip():
            destroy_looped_particle(self.circular_particle)
            destroy_looped_particle(self.linear_particle)
        if time() < self.active_head.target_time:
            return
        info = self.active_head.active_connector_info
        connector_kind = (
            Streams.connector_effect_kinds[self.active_head.index].get_previous_inclusive(time())
            if is_replay()
            else info.connector_kind
        )
        match connector_kind:
            case (
                ConnectorKind.ACTIVE_NORMAL
                | ConnectorKind.ACTIVE_CRITICAL
                | ConnectorKind.ACTIVE_FAKE_NORMAL
                | ConnectorKind.ACTIVE_FAKE_CRITICAL
            ):
                replace = connector_kind != self.last_kind
                self.last_kind = connector_kind
                update_circular_connector_particle(
                    self.circular_particle,
                    connector_kind,
                    info.visual_lane,
                    replace,
                    info.visual_y_offset,
                )
                update_linear_connector_particle(
                    self.linear_particle,
                    connector_kind,
                    info.visual_lane,
                    replace,
                    info.visual_y_offset,
                )
                trail_period = CONNECTOR_TRAIL_SPAWN_PERIOD / Options.effect_animation_speed
                if time() >= self.next_trail_spawn_time:
                    self.next_trail_spawn_time = max(
                        self.next_trail_spawn_time + trail_period,
                        time() + trail_period / 2,
                    )
                    spawn_linear_connector_trail_particle(connector_kind, info.visual_lane, info.visual_y_offset)
                slot_period = CONNECTOR_SLOT_SPAWN_PERIOD / Options.effect_animation_speed
                if time() >= self.next_slot_spawn_time:
                    self.next_slot_spawn_time = max(
                        self.next_slot_spawn_time + slot_period,
                        time() + slot_period / 2,
                    )
                    spawn_connector_slot_particles(
                        connector_kind, info.visual_lane, info.visual_size, info.visual_y_offset
                    )
                draw_connector_slot_glow_effect(
                    connector_kind,
                    self.active_head.target_time,
                    info.visual_lane,
                    info.visual_size,
                    info.visual_y_offset,
                )
            case _:
                destroy_looped_particle(self.circular_particle)
                destroy_looped_particle(self.linear_particle)

        if time() + delta_time() > self.active_tail.despawn_time():
            return
        match info.connector_kind:
            case (
                ConnectorKind.ACTIVE_NORMAL
                | ConnectorKind.ACTIVE_CRITICAL
                | ConnectorKind.ACTIVE_FAKE_NORMAL
                | ConnectorKind.ACTIVE_FAKE_CRITICAL
            ):
                draw_slide_note_head(
                    self.active_head.kind,
                    info.connector_kind,
                    info.visual_lane,
                    info.visual_size,
                    self.active_head.target_time,
                    1.0 - info.visual_y_offset,
                )
            case _:
                pass

    def terminate(self):
        destroy_looped_particle(self.circular_particle)
        destroy_looped_particle(self.linear_particle)

    @property
    def active_head(self) -> note.WatchBaseNote:
        return self.active_head_ref.get()

    @property
    def active_tail(self) -> note.WatchBaseNote:
        return self.active_tail_ref.get()


WATCH_CONNECTOR_ARCHETYPES = (
    WatchConnector,
    WatchSlideManager,
)
