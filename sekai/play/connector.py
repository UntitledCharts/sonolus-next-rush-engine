from __future__ import annotations

from math import inf
from typing import assert_never, cast

from sonolus.script.archetype import EntityRef, PlayArchetype, callback, entity_data, entity_memory, imported
from sonolus.script.array import Array, Dim
from sonolus.script.effect import LoopedEffectHandle
from sonolus.script.interval import Interval, lerp
from sonolus.script.particle import ParticleHandle
from sonolus.script.runtime import delta_time, input_offset, offset_adjusted_time, time
from sonolus.script.timing import beat_to_time
from sonolus.script.values import alloc

from sekai.debug import DISABLE_NOTES
from sekai.lib import archetype_names
from sekai.lib.connector import (
    CONNECTOR_PARTICLE_ACTIVE_DELAY,
    CONNECTOR_SLOT_SPAWN_PERIOD,
    CONNECTOR_THROUGH_JUDGE_LINE_DESPAWN_DELAY,
    CONNECTOR_TRAIL_SPAWN_PERIOD,
    ActiveConnectorInfo,
    ActiveConnectorKind,
    ConnectorKind,
    ConnectorRenderInfo,
    ConnectorSfxTimes,
    ConnectorVisualState,
    DamageConnectorKind,
    SlideConnectorKind,
    activate_connector_sfx,
    connector_sfx_channel,
    current_connector_sfx_is_active,
    deactivate_connector_sfx,
    destroy_looped_particle,
    destroy_looped_sfx,
    draw_connector,
    draw_connector_slot_glow_effect,
    get_connector_alpha_frac,
    get_connector_base_kind,
    get_connector_fractions,
    get_connector_input_leniency,
    get_connector_interp_frac,
    get_connector_render_info,
    get_connector_sfx_kind,
    inactive_connector_sfx_times,
    is_fake_active_connector,
    is_sfx_connector,
    should_show_connector_hitbox,
    spawn_connector_slot_particles,
    spawn_linear_connector_trail_particle,
    update_circular_connector_particle,
    update_connector_sfx,
    update_linear_connector_particle,
)
from sekai.lib.ease import EaseType, is_in_step_ease, safe_unlerp_clamped
from sekai.lib.initialization import schedule_connector_sfx_after_notes
from sekai.lib.layout import (
    ElevationTransformPreparation,
    StageTransform,
    blend_stage_transform,
    current_layout_transform,
)
from sekai.lib.note import NoteKind, draw_connector_hitbox_overlay, draw_slide_note_head, get_note_window, has_tap_input
from sekai.lib.options import Options
from sekai.lib.particle_manager import release_hold_particles, reserve_hold_particles
from sekai.lib.stage import VisualMask, masked_note_extents_by_limits
from sekai.lib.streams import Streams
from sekai.lib.timescale import (
    MIN_START_TIME,
    TrajectoryCache,
    group_hide_notes,
    register_group_window,
)
from sekai.lib.timescale_consumer import (
    connector_visibility_end,
    connector_visibility_start,
    extend_note_chain_stage_windows,
    legacy_connector_spawn_time,
    note_visual_progress,
    prepare_note_trajectories,
    register_note_group_window,
)
from sekai.play import input_manager, note

START_LENIENCY_BEATS = 0.5


class Connector(PlayArchetype):
    name = archetype_names.CONNECTOR

    head_ref: EntityRef[note.BaseNote] = imported(name="head")
    tail_ref: EntityRef[note.BaseNote] = imported(name="tail")
    segment_head_ref: EntityRef[note.BaseNote] = imported(name="segmentHead")
    segment_tail_ref: EntityRef[note.BaseNote] = imported(name="segmentTail")
    active_head_ref: EntityRef[note.BaseNote] = imported(name="activeHead")
    active_tail_ref: EntityRef[note.BaseNote] = imported(name="activeTail")
    legacy_hidden_pop: bool = imported(name="legacyHiddenPop")

    kind: ConnectorKind = entity_data()
    ease_type: EaseType = entity_data()
    shared_stage_transform: bool = entity_data()
    start_time: float = entity_data()
    scheduled_spawn_time: float = entity_data()
    end_time: float = entity_data()
    visual_active_interval: Interval = entity_data()

    head_trajectory_first: TrajectoryCache = entity_memory()
    head_trajectory_second: TrajectoryCache = entity_memory()
    tail_trajectory_first: TrajectoryCache = entity_memory()
    tail_trajectory_second: TrajectoryCache = entity_memory()
    input_active_interval: Interval = entity_data()
    ease_over_elevation: bool = entity_data()
    time_attachment_slice: bool = entity_data()
    render_info: ConnectorRenderInfo = entity_data()

    last_visual_state: ConnectorVisualState = entity_memory()
    delay: bool = entity_memory()
    can_consume_empty: bool = entity_memory()
    # Temporary linked-list pointers used only during preprocess to sort connectors by their
    # activation / deactivation times for the auto-SFX sweep (see schedule_auto_connector_sfx_events).
    # entity_data (not entity_memory) so they can be written cross-entity during the global auto-SFX sweep.
    sfx_act_next: EntityRef[Connector] = entity_data()
    sfx_deact_next: EntityRef[Connector] = entity_data()

    @callback(order=1)
    def preprocess(self):
        schedule_connector_sfx_after_notes()
        self.start_time = inf
        self.scheduled_spawn_time = inf
        if DISABLE_NOTES:
            return
        head = self.head
        tail = self.tail
        if not head.preprocess_done or not tail.preprocess_done:
            return
        if not self.segment_head.preprocess_done or not self.segment_tail.preprocess_done:
            return
        if self.active_head_ref.index > 0 and not self.active_head.preprocess_done:
            return
        if self.active_tail_ref.index > 0 and not self.active_tail.preprocess_done:
            return
        self.ease_over_elevation = head.beat == tail.beat
        self.time_attachment_slice = self.ease_over_elevation and (head.has_time_attachment or tail.has_time_attachment)
        self.shared_stage_transform = (
            not head.is_attached
            and not tail.is_attached
            and head.stage_ref.index == tail.stage_ref.index
            and head.elevation == tail.elevation
        )
        self.kind = self.segment_head.segment_kind
        self.render_info = get_connector_render_info(
            self.kind, self.segment_head.segment_layer, self.segment_head.target_time, self.segment_head.lane
        )
        self.ease_type = head.connector_ease
        self.visual_active_interval.start = min(head.target_time, tail.target_time)
        self.visual_active_interval.end = max(head.target_time, tail.target_time)
        if self.legacy_hidden_pop:
            self.visual_active_interval.start = legacy_connector_spawn_time(self.segment_head)
            self.visual_active_interval.end = tail.target_time
        self.input_active_interval = self.visual_active_interval + input_offset()
        self.end_time = max(self.visual_active_interval.end, self.input_active_interval.end)
        if self.segment_head.segment_through_judge_line:
            self.end_time += CONNECTOR_THROUGH_JUDGE_LINE_DESPAWN_DELAY
        self.last_visual_state = ConnectorVisualState.WAITING
        self.can_consume_empty = True
        if self.active_head_ref.index > 0:
            head.tick_head_ref = self.active_head_ref
        if self.active_tail_ref.index > 0:
            head.tick_tail_ref = self.active_tail_ref

        start_time = min(
            self.visual_active_interval.start,
            self.input_active_interval.start,
            head.spawn_eligibility_time,
            tail.spawn_eligibility_time,
        )
        if self.active_head_ref.index <= 0:
            self.end_time = connector_visibility_end(
                head, tail, self.segment_head.timescale_group, self.end_time, start_time
            )
            if not self.legacy_hidden_pop:
                start_time = connector_visibility_start(
                    head, tail, self.segment_head.timescale_group, start_time, self.end_time
                )
            if start_time >= self.end_time or self.end_time <= MIN_START_TIME:
                return
        if self.legacy_hidden_pop:
            start_time = self.visual_active_interval.start
            if start_time >= self.end_time:
                return

        spawn_time = start_time
        if self.active_head_ref.index > 0:
            spawn_time = min(spawn_time, self.active_head.target_time + min(0, input_offset()))

        head.extend_stage_windows(spawn_time - 1.0, self.end_time + 1.0)
        tail.extend_stage_windows(spawn_time - 1.0, self.end_time + 1.0)
        if self.head_ref.index == self.active_head_ref.index:
            extend_note_chain_stage_windows(
                self.active_head, self.active_head.target_time, self.active_tail.target_time
            )

        register_note_group_window(head, spawn_time, self.end_time)
        register_note_group_window(tail, spawn_time, self.end_time)
        register_group_window(self.segment_head.timescale_group, spawn_time, self.end_time)
        self.start_time = start_time
        self.scheduled_spawn_time = spawn_time

    def initialize(self):
        if self.head_ref.index == self.active_head_ref.index:
            SlideManager.spawn(active_head_ref=self.active_head_ref, active_tail_ref=self.active_tail_ref)
        Streams.connector_visual_states[self.index][-2] = ConnectorVisualState.WAITING

    def spawn_order(self) -> float:
        if DISABLE_NOTES:
            return 1e8
        return self.scheduled_spawn_time

    def should_spawn(self) -> bool:
        if DISABLE_NOTES:
            return False
        return time() >= self.scheduled_spawn_time

    @callback(order=-1)
    def update_sequential(self):
        current_time = time()
        if time() < self.start_time:
            return
        if time() >= self.end_time:
            self.despawn = True
            return

        if self.active_head_ref.index > 0:
            tail_processed = self.active_tail_ref.index > 0 and self.active_tail.is_despawned
            if not tail_processed and current_time in self.input_active_interval:
                self.active_connector_info.input_bounds @= note.compute_slide_input_bounds(
                    self.ease_type,
                    self.head,
                    self.tail,
                    offset_adjusted_time(),
                    get_connector_input_leniency(self.kind, base_kind=self.render_info.base_kind),
                )
                bounds = self.active_connector_info.input_bounds
                if is_fake_active_connector(self.kind, base_kind=self.render_info.base_kind):
                    if not self.active_connector_info.is_active:
                        self.active_connector_info.active_start_time = current_time
                    self.active_connector_info.is_active = True
                    self.delay = False
                else:
                    for touch in input_manager.processed_touches():
                        if not touch.ended and bounds.contains_point(touch.position):
                            if not self.active_connector_info.is_active:
                                self.active_connector_info.active_start_time = current_time
                            self.active_connector_info.is_active = True
                            self.delay = False
                            break
                    else:
                        if self.delay:
                            self.active_connector_info.is_active = False
                            self.can_consume_empty = True
                        else:
                            self.delay = True
            if time() in self.visual_active_interval:
                self.active_connector_info.visual_connector_index = self.index + 1
                self.active_connector_info.visual_update_time = time()
                self.active_connector_info.connector_kind = self.kind
            if self.active_connector_info.visual_connector_index == self.index + 1 and group_hide_notes(
                self.segment_head.timescale_group
            ):
                self.active_connector_info.connector_kind = ConnectorKind.NONE

    @callback(order=1)
    def touch(self):
        if self.despawn:
            return
        current_time = time()
        if self.active_head_ref.index > 0 and current_time in self.input_active_interval:
            bounds = self.active_connector_info.input_bounds
            for touch in input_manager.processed_touches():
                if (
                    not touch.ended
                    and bounds.contains_point(touch.position)
                    and input_manager.is_allowed_empty(touch)
                    and (
                        self.can_consume_empty
                        or input_manager.is_last_started_touch_disallowed()
                        or (touch.started and input_manager.is_previous_touch_disallowed())
                    )
                ):
                    input_manager.disallow_empty(touch)
                    self.can_consume_empty = False

    def update_parallel(self):
        if time() < self.start_time and self.active_head_ref.index <= 0:
            return
        if self.despawn:
            return
        current_time = time()
        adj_time = offset_adjusted_time()
        if current_time >= self.start_time:
            self.draw_hitbox()
        if current_time < self.visual_active_interval.end or self.segment_head.segment_through_judge_line:
            head = self.head
            tail = self.tail
            segment_head = self.segment_head
            segment_tail = self.segment_tail
            if self.active_head_ref.index > 0:
                active_head = self.active_head
                if self.render_info.base_kind == ConnectorKind.DAMAGE:
                    # Damage connectors do not get the initial grace period for staying active.
                    if self.active_connector_info.is_active:
                        visual_state = ConnectorVisualState.ACTIVE
                    else:
                        visual_state = ConnectorVisualState.WAITING
                elif current_time < active_head.target_time:
                    visual_state = ConnectorVisualState.WAITING
                elif (
                    adj_time < beat_to_time(active_head.beat + START_LENIENCY_BEATS)
                    or self.active_connector_info.is_active
                ):
                    visual_state = ConnectorVisualState.ACTIVE
                    self.can_consume_empty = False
                else:
                    visual_state = ConnectorVisualState.INACTIVE
            else:
                visual_state = ConnectorVisualState.WAITING
            if visual_state != self.last_visual_state:
                self.last_visual_state = visual_state
                Streams.connector_visual_states[self.index][adj_time] = visual_state
            if current_time < self.start_time:
                return
            if group_hide_notes(segment_head.timescale_group):
                return
            if self.active_tail_ref.index > 0:
                active_tail = self.active_tail
                # A hidden fake tail can despawn while its connector is still visible.
                if (active_tail.is_scored and active_tail.is_despawned) or (
                    not active_tail.is_scored
                    and active_tail.kind != NoteKind.ANCHOR
                    and time() >= active_tail.target_time
                ):
                    return
            self.draw_fake_damage_head()
            if self.render_info.alpha <= 0:
                return
            head_note_alpha = head.visual_note_alpha
            tail_note_alpha = tail.visual_note_alpha
            if head_note_alpha <= 0 and tail_note_alpha <= 0:
                return
            prepare_note_trajectories(tail, self.tail_trajectory_first, self.tail_trajectory_second, time())
            head_transform = +StageTransform
            tail_transform = +StageTransform
            tail_transform @= tail.visual_stage_transform()
            shared_stage_transform = self.shared_stage_transform
            if shared_stage_transform:
                head_transform @= tail_transform
            else:
                head_transform @= head.visual_stage_transform()
            head_mask = +VisualMask
            head_mask @= head.visual_mask
            tail_mask = tail.visual_mask
            head_alpha_frac = -1.0
            tail_alpha_frac = -1.0
            if segment_head.beat == segment_tail.beat:
                head_alpha_frac = get_connector_alpha_frac(head, segment_head, segment_tail)
                tail_alpha_frac = get_connector_alpha_frac(tail, segment_head, segment_tail)
            if current_time >= head.target_time and not segment_head.segment_through_judge_line:
                head_frac = safe_unlerp_clamped(head.target_time, tail.target_time, current_time)
                head_visual_progress = 1.0 - lerp(head.visual_y_offset, tail.visual_y_offset, head_frac)
                head_target_time = time()
                head_note_alpha = lerp(head_note_alpha, tail_note_alpha, head_frac)
                if head_alpha_frac >= 0:
                    head_alpha_frac = lerp(head_alpha_frac, tail_alpha_frac, head_frac)
                if is_in_step_ease(self.ease_type) or head_frac <= 0:
                    head_lane = head.visual_lane
                    head_size = head.size
                    head_ease_frac = head.head_ease_frac
                else:
                    head_ease_frac = lerp(head.head_ease_frac, tail.tail_ease_frac, head_frac)
                    head_interp_frac = get_connector_interp_frac(
                        self.ease_type,
                        head.head_ease_frac,
                        tail.tail_ease_frac,
                        head_ease_frac,
                        head_frac,
                    )
                    head_lane = lerp(head.visual_lane, tail.visual_lane, head_interp_frac)
                    head_size = lerp(head.size, tail.size, head_interp_frac)
                    if head_mask.enabled and tail_mask.enabled:
                        head_mask.left = lerp(head_mask.left, tail_mask.left, head_interp_frac)
                        head_mask.right = lerp(head_mask.right, tail_mask.right, head_interp_frac)
                    # The head has passed the judge line. Blend distinct endpoint transforms at its current position.
                    if not shared_stage_transform:
                        head_transform @= blend_stage_transform(head_transform, tail_transform, head_interp_frac)
            else:
                prepare_note_trajectories(head, self.head_trajectory_first, self.head_trajectory_second, time())
                head_lane = head.visual_lane
                head_size = head.size
                head_visual_progress = note_visual_progress(
                    head, self.head_trajectory_first, self.head_trajectory_second, time()
                )
                head_target_time = head.target_time
                head_ease_frac = head.head_ease_frac

            tail_ease_frac = tail.tail_ease_frac
            if self.time_attachment_slice:
                # Same-beat slices of time attachments use their own elevation span.
                head_ease_frac = 0.0
                tail_ease_frac = 1.0

            elevation_preparation = alloc(ElevationTransformPreparation)
            elevation_preparation.ready = False

            def elevation_transform(interp_frac: float, elevation_frac: float) -> StageTransform:
                if not elevation_preparation.ready:
                    camera = current_layout_transform()
                    elevation_preparation.projection.prepare(camera)
                    head.prepare_elevation_transform(
                        camera, elevation_preparation.projection, elevation_preparation.head
                    )
                    tail.prepare_elevation_transform(
                        camera, elevation_preparation.projection, elevation_preparation.tail
                    )
                    elevation_preparation.ready = True
                return elevation_preparation.at(interp_frac, elevation_frac)

            draw_connector(
                kind=self.kind,
                render_info=self.render_info,
                animation_start_time=(
                    self.active_head.target_time
                    if self.active_head_ref.index > 0
                    else segment_head.active_head_ref.get().target_time
                    if segment_head.active_head_ref.index > 0
                    else segment_head.target_time
                ),
                visual_state=visual_state,
                ease_type=self.ease_type,
                head_lane=head_lane,
                head_size=head_size,
                head_visual_progress=head_visual_progress,
                head_target_time=head_target_time,
                head_ease_frac=head_ease_frac,
                tail_lane=tail.visual_lane,
                tail_size=tail.size,
                tail_visual_progress=note_visual_progress(
                    tail, self.tail_trajectory_first, self.tail_trajectory_second, time()
                ),
                tail_target_time=tail.target_time,
                tail_ease_frac=tail_ease_frac,
                segment_head_target_time=segment_head.target_time,
                segment_head_lane=segment_head.lane,
                segment_head_alpha=segment_head.segment_alpha,
                segment_tail_target_time=segment_tail.target_time,
                segment_tail_alpha=segment_tail.segment_alpha,
                layer=segment_head.segment_layer,
                presentation=segment_head.segment_presentation,
                bypass_tail_target_time_check=segment_head.segment_through_judge_line,
                head_transform=head_transform,
                tail_transform=tail_transform,
                shared_transform=shared_stage_transform,
                head_note_alpha=head_note_alpha,
                tail_note_alpha=tail_note_alpha,
                head_mask=head_mask,
                tail_mask=tail_mask,
                ease_over_elevation=self.ease_over_elevation,
                elevation_transform=elevation_transform,
                head_alpha_frac=head_alpha_frac,
                tail_alpha_frac=tail_alpha_frac,
            )

    def draw_fake_damage_head(self):
        if (
            self.render_info.base_kind != ConnectorKind.FAKE_DAMAGE
            or self.active_head_ref.index > 0
            or Options.disable_fake_notes
            or not self.visual_active_interval.start <= time() < self.visual_active_interval.end
        ):
            return
        lane, size = self.current_visual_head_extents()
        if size <= 0:
            return
        head = self.head
        tail = self.tail
        frac, transform_frac = get_connector_fractions(
            self.ease_type,
            head.target_time,
            head.head_ease_frac,
            tail.target_time,
            tail.tail_ease_frac,
            time(),
        )
        transform = blend_stage_transform(head.visual_stage_transform(), tail.visual_stage_transform(), transform_frac)
        draw_slide_note_head(
            self.segment_head.kind,
            cast(DamageConnectorKind, self.kind),
            lane,
            size,
            self.segment_head.target_time,
            1.0 - lerp(head.visual_y_offset, tail.visual_y_offset, frac),
            transform=transform.to_screen_transform(),
            note_alpha=lerp(head.visual_note_alpha, tail.visual_note_alpha, frac),
            style=self.segment_head.style,
        )

    def draw_hitbox(self):
        if not Options.allow_debug_options_in_play_mode or not Options.show_hitboxes:
            return
        if self.active_head_ref.index <= 0 or not should_show_connector_hitbox(
            self.kind, base_kind=self.render_info.base_kind
        ):
            return
        if time() in self.input_active_interval:
            draw_connector_hitbox_overlay(self.active_connector_info.input_bounds, 0.6)

    def current_visual_head_extents(self) -> tuple[float, float]:
        head = self.head
        tail = self.tail
        result_lane = head.visual_lane
        result_size = head.size
        head_mask = head.visual_mask
        tail_mask = tail.visual_mask
        mask_left = head_mask.left
        mask_right = head_mask.right
        if not is_in_step_ease(self.ease_type):
            _, interp_frac = get_connector_fractions(
                self.ease_type,
                head.target_time,
                head.head_ease_frac,
                tail.target_time,
                tail.tail_ease_frac,
                time(),
            )
            result_lane = lerp(head.visual_lane, tail.visual_lane, interp_frac)
            result_size = lerp(head.size, tail.size, interp_frac)
            mask_left = lerp(head_mask.left, tail_mask.left, interp_frac)
            mask_right = lerp(head_mask.right, tail_mask.right, interp_frac)
        return masked_note_extents_by_limits(
            result_lane,
            result_size,
            mask_left,
            mask_right,
            head_mask.enabled and tail_mask.enabled,
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

    @property
    def active_head(self):
        return self.active_head_ref.get()

    @property
    def active_tail(self):
        return self.active_tail_ref.get()

    @property
    def active_connector_info(self) -> ActiveConnectorInfo:
        return self.active_head_ref.get().active_connector_info


class SlideManager(PlayArchetype):
    name = archetype_names.SLIDE_MANAGER

    active_head_ref: EntityRef[note.BaseNote] = entity_memory()
    active_tail_ref: EntityRef[note.BaseNote] = entity_memory()

    visual_lane: float = entity_memory()
    visual_size: float = entity_memory()
    visual_y_offset: float = entity_memory()
    segment_head_ref: EntityRef[note.BaseNote] = entity_memory()
    segment_cursor_time: float = entity_memory()

    last_kind: ConnectorKind = entity_memory()
    circular_particle: ParticleHandle = entity_memory()
    linear_particle: ParticleHandle = entity_memory()
    next_trail_spawn_time: float = entity_memory()
    next_slot_spawn_time: float = entity_memory()
    last_effect_kind: ConnectorKind = entity_memory()
    sfx_active: bool = entity_memory()
    head_ready: bool = entity_memory()
    head_touched: bool = entity_memory()
    head_began_frame: int = entity_memory()

    effect_pool_slot: int = entity_memory()
    cleanup_time: float = entity_memory()

    def initialize(self):
        self.effect_pool_slot = -1
        self.cleanup_time = self.active_tail.target_time
        self.segment_head_ref @= self.active_head_ref
        self.segment_cursor_time = -1e8
        self.next_trail_spawn_time = -1e8
        self.next_slot_spawn_time = -1e8
        Streams.connector_effect_kinds[self.active_head.index][-2] = ConnectorKind.NONE
        self.last_effect_kind = ConnectorKind.NONE
        self.sfx_active = False
        self.head_began_frame = -1

    @property
    def tail_finished(self) -> bool:
        tail = self.active_tail
        return (
            tail.is_despawned
            or tail.pending_despawn
            or (not tail.is_scored and offset_adjusted_time() >= tail.target_time)
            or (tail.is_scored and offset_adjusted_time() - delta_time() > tail.target_time + note.JUDGMENT_LAST_TIME)
        )

    @callback(order=2)
    def update_sequential(self):
        if self.effect_pool_slot < 0:
            self.effect_pool_slot = reserve_hold_particles(
                self.active_head.index,
                get_connector_sfx_kind(self.active_head.segment_kind) == ConnectorKind.ACTIVE_CRITICAL,
                self.cleanup_time + note.JUDGMENT_LAST_TIME + delta_time(),
            )
        if self.tail_finished or (Options.auto_sfx and time() >= self.cleanup_time):
            release_hold_particles(self.effect_pool_slot, self.active_head.index)
            self.effect_pool_slot = 0
        if Options.auto_sfx:
            return
        head = self.active_head
        t = offset_adjusted_time()
        if not self.head_ready:
            if t >= head.target_time and (self.head_touched or not head.is_scored):
                self.head_ready = True
                self.head_began_frame = input_manager.InputState.frame
            elif (
                has_tap_input(head.kind) and head.captured_touch_id > 0
            ) or t - delta_time() > head.target_time + 0.125:
                self.head_ready = True
        # With touches, wait until note judgments finish. Without touches, handle Release here.
        if len(input_manager.processed_touches()) == 0:
            self.update_sfx_state()

    @callback(order=2)
    def touch(self):
        self.update_sfx_state()

    def update_sfx_state(self):
        if self.tail_finished:
            release_hold_particles(self.effect_pool_slot, self.active_head.index)
            self.effect_pool_slot = 0
        if Options.auto_sfx:
            return
        head = self.active_head
        tail = self.active_tail
        t = offset_adjusted_time()
        kind = head.segment_kind
        if (
            self.effect_pool_slot == 0
            or self.tail_finished
            or tail.target_time <= head.target_time
            or not is_sfx_connector(kind)
        ):
            self.deactivate_sfx_if_needed(t)
            return
        if not self.head_ready:
            if has_tap_input(head.kind) and head.captured_touch_id > 0:
                self.head_ready = True
            elif (
                head.is_trace
                and head.input_interval.start < time() < head.input_interval.end
                and any(
                    head.hitbox.bounds.contains_point(touch.position) for touch in input_manager.processed_touches()
                )
            ):
                self.head_touched = True
            if not self.head_ready:
                return
        info = head.active_connector_info
        bounds = +info.input_bounds
        if t < head.target_time:
            bounds @= note.compute_slide_input_bounds(
                head.connector_ease, head, head, t, get_connector_input_leniency(kind)
            )
        elif t >= tail.target_time:
            bounds @= note.compute_slide_input_bounds(
                tail.connector_ease, tail, tail, t, get_connector_input_leniency(kind)
            )
        held = self.head_began_frame == input_manager.InputState.frame or is_fake_active_connector(kind)
        held = held or any(bounds.contains_point(touch.position) for touch in input_manager.processed_touches())
        if t >= tail.target_time:
            after = get_note_window(head.kind, False).bad.end if head.is_scored else 5 / 60
            if t - tail.target_time >= after:
                held = False
        if group_hide_notes(head.timescale_group):
            held = False
        if held:
            self.activate_sfx_if_needed(kind, t)
        else:
            self.deactivate_sfx_if_needed(t)

    def update_parallel(self):
        current_time = time()
        adj_time = offset_adjusted_time()

        connector_effect_kind_stream = Streams.connector_effect_kinds[self.active_head.index]
        if time() >= self.cleanup_time or (self.active_tail.is_scored and self.active_tail.is_despawned):
            destroy_looped_particle(self.circular_particle)
            destroy_looped_particle(self.linear_particle)
            connector_effect_kind_stream[adj_time] = ConnectorKind.NONE
            self.last_effect_kind = ConnectorKind.NONE
            if Options.auto_sfx or self.tail_finished:
                self.despawn = True
            return
        info = self.active_head.active_connector_info
        if info.visual_connector_index > 0 and info.visual_update_time == time():
            connector = EntityRef[Connector](index=info.visual_connector_index - 1).get()
            visual_lane, visual_size = connector.current_visual_head_extents()
            self.visual_lane = visual_lane
            self.visual_size = visual_size
            self.visual_y_offset = lerp(
                connector.head.visual_y_offset,
                connector.tail.visual_y_offset,
                safe_unlerp_clamped(connector.head.target_time, connector.tail.target_time, time()),
            )
        if time() < self.active_head.target_time:
            return
        segment_transform, segment_note_alpha = self.active_segment_transform_and_note_alpha()
        head_transform = segment_transform.to_screen_transform()
        match get_connector_base_kind(info.connector_kind):
            case (
                ConnectorKind.ACTIVE_NORMAL
                | ConnectorKind.ACTIVE_CRITICAL
                | ConnectorKind.FAKE_ACTIVE_NORMAL
                | ConnectorKind.FAKE_ACTIVE_CRITICAL
            ) if info.is_active and self.effect_pool_slot > 0:
                if current_time < info.active_start_time + CONNECTOR_PARTICLE_ACTIVE_DELAY:
                    destroy_looped_particle(self.circular_particle)
                    destroy_looped_particle(self.linear_particle)
                    if self.last_effect_kind != ConnectorKind.NONE:
                        connector_effect_kind_stream[adj_time] = ConnectorKind.NONE
                        self.last_effect_kind = ConnectorKind.NONE
                else:
                    replace = info.connector_kind != self.last_kind
                    self.last_kind = info.connector_kind
                    if self.visual_size <= 0:
                        destroy_looped_particle(self.circular_particle)
                        destroy_looped_particle(self.linear_particle)
                    else:
                        update_circular_connector_particle(
                            self.circular_particle,
                            cast(ActiveConnectorKind, info.connector_kind),
                            self.visual_lane,
                            replace,
                            self.visual_y_offset,
                            transform=head_transform,
                        )
                        update_linear_connector_particle(
                            self.linear_particle,
                            cast(ActiveConnectorKind, info.connector_kind),
                            self.visual_lane,
                            replace,
                            self.visual_y_offset,
                            transform=head_transform,
                        )
                    if self.last_effect_kind != info.connector_kind:
                        connector_effect_kind_stream[adj_time] = info.connector_kind
                        self.last_effect_kind = info.connector_kind
                    trail_period = CONNECTOR_TRAIL_SPAWN_PERIOD / Options.effect_animation_speed
                    if self.visual_size > 0 and current_time >= self.next_trail_spawn_time:
                        self.next_trail_spawn_time = max(
                            self.next_trail_spawn_time + trail_period,
                            current_time + trail_period / 2,
                        )
                        spawn_linear_connector_trail_particle(
                            cast(ActiveConnectorKind, info.connector_kind),
                            self.visual_lane,
                            self.visual_y_offset,
                            transform=head_transform,
                        )
                    if self.visual_size > 0:
                        slot_period = CONNECTOR_SLOT_SPAWN_PERIOD / Options.effect_animation_speed
                        if current_time >= self.next_slot_spawn_time:
                            self.next_slot_spawn_time = max(
                                self.next_slot_spawn_time + slot_period,
                                current_time + slot_period / 2,
                            )
                            spawn_connector_slot_particles(
                                cast(ActiveConnectorKind, info.connector_kind),
                                self.visual_lane,
                                self.visual_size,
                                self.visual_y_offset,
                                transform=head_transform,
                            )
                        draw_connector_slot_glow_effect(
                            cast(ActiveConnectorKind, info.connector_kind),
                            info.active_start_time,
                            self.visual_lane,
                            self.visual_size,
                            self.visual_y_offset,
                            transform=head_transform,
                        )
            case _:
                destroy_looped_particle(self.circular_particle)
                destroy_looped_particle(self.linear_particle)
                if self.last_effect_kind != ConnectorKind.NONE:
                    connector_effect_kind_stream[adj_time] = ConnectorKind.NONE
                    self.last_effect_kind = ConnectorKind.NONE
        match get_connector_base_kind(info.connector_kind):
            case (
                ConnectorKind.ACTIVE_NORMAL
                | ConnectorKind.ACTIVE_CRITICAL
                | ConnectorKind.FAKE_ACTIVE_NORMAL
                | ConnectorKind.FAKE_ACTIVE_CRITICAL
                | ConnectorKind.DAMAGE
                | ConnectorKind.FAKE_DAMAGE
            ) if self.visual_size > 0:
                draw_slide_note_head(
                    self.active_head.kind,
                    cast(SlideConnectorKind, info.connector_kind),
                    self.visual_lane,
                    self.visual_size,
                    self.active_head.target_time,
                    1.0 - self.visual_y_offset,
                    transform=head_transform,
                    note_alpha=segment_note_alpha,
                    style=self.active_head.style,
                )
            case _:
                pass

    def activate_sfx_if_needed(self, kind: ConnectorKind, event_time: float):
        if self.sfx_active:
            return
        match get_connector_base_kind(kind):
            case (
                ConnectorKind.ACTIVE_NORMAL
                | ConnectorKind.ACTIVE_CRITICAL
                | ConnectorKind.FAKE_ACTIVE_NORMAL
                | ConnectorKind.FAKE_ACTIVE_CRITICAL
            ):
                times = activate_connector_sfx(
                    cast(ActiveConnectorKind, kind),
                    event_time,
                    self.active_head.target_time,
                    self.active_tail.target_time,
                    self.active_head.index,
                )
                self.write_sfx_times(times.active_time, times)
                self.sfx_active = True
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
                | ConnectorKind.DAMAGE
                | ConnectorKind.FAKE_DAMAGE
            ):
                pass
            case _:
                assert_never(kind)

    def deactivate_sfx_if_needed(self, event_time: float):
        if not self.sfx_active:
            return
        kind = get_connector_sfx_kind(self.active_head.segment_kind)
        owns_sound = connector_sfx_channel(kind).active_head_index == self.active_head.index
        times = deactivate_connector_sfx(
            event_time, self.active_head.target_time, self.active_tail.target_time, kind, self.active_head.index
        )
        if owns_sound:
            self.write_sfx_times(event_time, times)
        self.sfx_active = False

    def write_sfx_times(self, event_time: float, times: ConnectorSfxTimes):
        if get_connector_sfx_kind(self.active_head.segment_kind) == ConnectorKind.ACTIVE_CRITICAL:
            Streams.connector_critical_sfx_times[0][event_time] = times
        else:
            Streams.connector_normal_sfx_times[0][event_time] = times

    def active_segment_transform_and_note_alpha(self) -> tuple[StageTransform, float]:
        result = +StageTransform
        # The cached segment is valid only while playback moves forward.
        if time() < self.segment_cursor_time:
            self.segment_head_ref @= self.active_head_ref
        head_ref = +self.segment_head_ref
        next_ref = +head_ref.get().next_ref
        while next_ref.index > 0 and time() >= next_ref.get().target_time:
            head_ref.index = next_ref.index
            next_ref.index = head_ref.get().next_ref.index
        self.segment_head_ref @= head_ref
        self.segment_cursor_time = time()
        seg_head = head_ref.get()
        note_alpha = seg_head.visual_note_alpha
        if next_ref.index > 0:
            seg_tail = next_ref.get()
            frac, transform_frac = get_connector_fractions(
                seg_head.connector_ease,
                seg_head.target_time,
                seg_head.head_ease_frac,
                seg_tail.target_time,
                seg_tail.tail_ease_frac,
                time(),
            )
            result @= blend_stage_transform(
                seg_head.visual_stage_transform(),
                seg_tail.visual_stage_transform(),
                transform_frac,
            )
            note_alpha = lerp(seg_head.visual_note_alpha, seg_tail.visual_note_alpha, frac)
        else:
            result @= seg_head.visual_stage_transform()
        return result, note_alpha

    @property
    def active_head(self) -> note.BaseNote:
        return self.active_head_ref.get()

    @property
    def active_tail(self) -> note.BaseNote:
        return self.active_tail_ref.get()


class ConnectorSfxManager(PlayArchetype):
    name = archetype_names.CONNECTOR_SFX_MANAGER

    sfx: Array[LoopedEffectHandle, Dim[2]] = entity_memory()
    last_head: Array[int, Dim[2]] = entity_memory()

    def initialize(self):
        Streams.unified_connector_sfx = False
        Streams.connector_normal_sfx_times[0][-2] = inactive_connector_sfx_times()
        Streams.connector_critical_sfx_times[0][-2] = inactive_connector_sfx_times()

    def update_parallel(self):
        for i in range(2):
            kind = ConnectorKind.ACTIVE_NORMAL if i == 0 else ConnectorKind.ACTIVE_CRITICAL
            channel = connector_sfx_channel(kind)
            if current_connector_sfx_is_active(kind):
                update_connector_sfx(
                    self.sfx[i], cast(ActiveConnectorKind, kind), channel.active_head_index != self.last_head[i]
                )
                self.last_head[i] = channel.active_head_index
            else:
                destroy_looped_sfx(self.sfx[i])
                self.last_head[i] = 0


CONNECTOR_ARCHETYPES = (
    Connector,
    SlideManager,
    ConnectorSfxManager,
)
