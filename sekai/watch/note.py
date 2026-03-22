from __future__ import annotations

from typing import cast

from sonolus.script.archetype import (
    EntityRef,
    StandardImport,
    WatchArchetype,
    entity_data,
    imported,
    shared_memory,
)
from sonolus.script.bucket import Judgment, JudgmentWindow
from sonolus.script.interval import Interval, lerp, remap_clamped, unlerp_clamped
from sonolus.script.runtime import is_replay, is_skip, time
from sonolus.script.timing import beat_to_time

from sekai.debug import DISABLE_NOTES
from sekai.lib.buckets import get_judgment_interval
from sekai.lib.connector import ActiveConnectorInfo, ConnectorKind, ConnectorLayer
from sekai.lib.ease import EaseType, ease
from sekai.lib.layout import FlickDirection, Hitbox, compute_hitbox_at_time, progress_to
from sekai.lib.note import (
    NoteEffectKind,
    NoteKind,
    draw_hitbox_overlay,
    draw_note,
    get_attach_params,
    get_leniency,
    get_note_bucket,
    get_note_effect_kind,
    get_note_particles,
    get_note_window,
    get_visual_spawn_time,
    has_release_input,
    has_tap_input,
    is_head,
    map_note_kind,
    mirror_flick_direction,
    play_note_hit_effects,
    schedule_note_auto_sfx,
    schedule_note_sfx,
    schedule_note_slot_effects,
)
from sekai.lib.options import Options
from sekai.lib.particle import BaseParticles
from sekai.lib.stage import DivisionParity, get_stage_props
from sekai.lib.timescale import (
    CompositeTime,
    group_force_note_speed,
    group_hide_notes,
    group_scaled_time,
    group_time_to_scaled_time,
    update_timescale_group,
)
from sekai.play.note import HITBOX_DRAW_MIN_EARLY_WINDOW, derive_note_archetypes
from sekai.watch.custom_elements import spawn_custom
from sekai.watch.dynamic_stage import WatchDynamicStage
from sekai.watch.particle_manager import ParticleManager

MIN_START_TIME = 0.0167  # Executes the terminate process with a guaranteed minimum duration.


class WatchBaseNote(WatchArchetype):
    beat: StandardImport.BEAT
    timescale_group: StandardImport.TIMESCALE_GROUP
    stage_ref: EntityRef[WatchDynamicStage] = imported(name="stage")
    lane: float = imported()
    size: float = imported()
    direction: FlickDirection = imported()
    active_head_ref: EntityRef[WatchBaseNote] = imported(name="activeHead")
    is_attached: bool = imported(name="isAttached")
    connector_ease: EaseType = imported(name="connectorEase")
    segment_kind: ConnectorKind = imported(name="segmentKind")
    segment_alpha: float = imported(name="segmentAlpha")
    segment_layer: ConnectorLayer = imported(name="segmentLayer")
    segment_through_judge_line: bool = imported(name="segmentThroughJudgeLine")
    attach_head_ref: EntityRef[WatchBaseNote] = imported(name="attachHead")
    attach_tail_ref: EntityRef[WatchBaseNote] = imported(name="attachTail")
    next_ref: EntityRef[WatchBaseNote] = imported(name="next")
    prev_ref: EntityRef[WatchBaseNote] = imported(name="prev")
    effect_kind: NoteEffectKind = imported(name="effectKind")

    kind: NoteKind = entity_data()
    data_init_done: bool = entity_data()
    rel_lane: float = entity_data()
    target_time: float = entity_data()
    visual_start_time: float = entity_data()
    start_time: float = entity_data()
    target_scaled_time: CompositeTime = entity_data()
    target_y_offset: float = entity_data()
    not_render: float = entity_data()

    active_connector_info: ActiveConnectorInfo = shared_memory()

    hitbox: Hitbox = shared_memory()

    next_ref_accuracy: EntityRef[WatchBaseNote] = shared_memory()
    next_ref_damage_flash: EntityRef[WatchBaseNote] = shared_memory()
    judgment_window: JudgmentWindow = shared_memory()
    judgment_window_bad: Interval = shared_memory()
    combo: int = shared_memory()
    count: int = shared_memory()
    ap: bool = shared_memory()
    score: float = shared_memory()
    percentage: float = shared_memory()
    note_raw_score: float = shared_memory()

    end_time: float = imported()
    played_hit_effects: bool = imported()
    wrong_way_check: bool = imported()

    judgment: StandardImport.JUDGMENT = imported()
    accuracy: StandardImport.ACCURACY = imported()

    def init_data(self):
        if self.data_init_done:
            return

        self.kind = map_note_kind(cast(NoteKind, self.key))
        self.effect_kind = get_note_effect_kind(self.kind, self.effect_kind)

        self.data_init_done = True

        if Options.mirror:
            self.lane *= -1
            self.direction = mirror_flick_direction(self.direction)

        self.target_time = beat_to_time(self.beat)
        self.judgment_window = get_note_window(self.kind)
        self.judgment_window_bad = get_judgment_interval(
            bad_window=get_note_window_bad(self.kind), good_window=self.judgment_window.good
        )

        if not self.is_attached:
            self.target_scaled_time = group_time_to_scaled_time(self.timescale_group, self.target_time)
            self.visual_start_time = get_visual_spawn_time(self.timescale_group, self.target_scaled_time)
            self.start_time = self.get_min_start_time()

        if self.stage_ref.index > 0:
            stage_props = get_stage_props(self.stage_ref.get(), self.target_time)
            self.rel_lane = self.lane
            self.lane += stage_props.pivot_lane
            self.target_y_offset = self._basic_y_offset_at(self.target_time, left_limit=True)

        if self.next_ref.index > 0:
            self.next_ref.get().prev_ref = self.ref()

    def preprocess(self):
        if DISABLE_NOTES:
            self.result.target_time = 1e8
            return
        self.init_data()

        self.result.bucket = get_note_bucket(self.kind)

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
            self.visual_start_time = min(attach_head.visual_start_time, attach_tail.visual_start_time)
            self.start_time = self.visual_start_time
            self.target_y_offset = remap_clamped(
                attach_head.target_time,
                attach_tail.target_time,
                attach_head._basic_y_offset_at(self.target_time, left_limit=True),
                attach_tail._basic_y_offset_at(self.target_time, left_limit=True),
                self.target_time,
            )

        if self.is_scored:
            self.hitbox @= compute_hitbox_at_time(
                self.lane,
                self.size,
                get_leniency(self.kind),
                self.target_time,
                self.target_y_offset,
                left_limit=True,
            )

        if is_replay():
            if self.played_hit_effects:
                if Options.auto_sfx:
                    schedule_note_auto_sfx(self.effect_kind, self.target_time)
                else:
                    schedule_note_sfx(self.effect_kind, self.judgment, self.end_time)
                schedule_note_slot_effects(
                    self.kind,
                    self.visual_lane_at(self.end_time),
                    self.size,
                    self.end_time,
                    self.direction,
                    self.judgment,
                    y_offset=self._basic_y_offset_at(self.end_time),
                    pivot_lane=self._stage_pivot_lane_at(self.end_time),
                    half_offset=self._stage_half_offset_at(self.end_time),
                )
            self.result.bucket_value = self.accuracy * 1000
        else:
            self.judgment = Judgment.PERFECT
            if self.is_scored:
                schedule_note_sfx(self.effect_kind, Judgment.PERFECT, self.target_time)
                schedule_note_slot_effects(
                    self.kind,
                    self.visual_lane_at(self.target_time),
                    self.size,
                    self.target_time,
                    self.direction,
                    y_offset=self._basic_y_offset_at(self.target_time),
                    pivot_lane=self._stage_pivot_lane_at(self.target_time),
                    half_offset=self._stage_half_offset_at(self.target_time),
                )

        self.result.target_time = self.target_time

        if self.stage_ref.index > 0:
            stage = self.stage_ref.get()
            stage.start_time = min(stage.start_time, self.start_time - 1.0)
            stage.end_time = max(stage.end_time, self.target_time + 1.0)

        if self.is_scored:
            spawn_custom(
                self.next_ref,
                self.next_ref_accuracy,
                self.next_ref_damage_flash,
                self.index,
                self.judgment,
                self.played_hit_effects,
            )

        if self.played_hit_effects or not is_replay():
            self.spawn_critical_lane()

    def get_min_start_time(self):
        if self.calc_time - self.visual_start_time > MIN_START_TIME:
            return self.visual_start_time
        else:
            self.not_render = True
            return self.calc_time - MIN_START_TIME

    def spawn_critical_lane(self):
        if Options.lane_effect_enabled:
            particles = get_note_particles(self.kind, self.direction)
            if particles.lane.id == BaseParticles.critical_flick_note_lane_linear.id:
                ParticleManager.spawn(lane=self.lane, size=self.size, target_time=self.calc_time, particles=particles)

    def spawn_time(self) -> float:
        if DISABLE_NOTES or self.kind == NoteKind.ANCHOR:
            return 1e8
        return self.start_time

    def despawn_time(self) -> float:
        return self.calc_time

    @property
    def calc_time(self) -> float:
        if is_replay() and self.is_scored:
            if self.end_time == 0 and self.accuracy == 0 and self.judgment == Judgment.MISS:
                # This is a note that's part of a partial replay that ended before this note was hit
                return self.target_time + self.accuracy
            return self.end_time
        else:
            return self.target_time

    def update_sequential(self):
        update_timescale_group(self.timescale_group)

    def update_parallel(self):
        if time() < self.visual_start_time:
            return
        if is_head(self.kind) and time() > self.target_time:
            return
        if group_hide_notes(self.timescale_group):
            return
        if Options.disable_fake_notes and not self.is_scored:
            return
        if self.not_render:
            return
        draw_note(
            self.kind,
            self.visual_lane,
            self.size,
            self.visual_progress,
            self.direction,
            self.target_time,
        )
        if Options.show_hitboxes and self.is_scored:
            input_interval = get_note_window(self.kind).bad + self.target_time
            draw_start = min(input_interval.start, self.target_time - HITBOX_DRAW_MIN_EARLY_WINDOW)
            if draw_start <= time() <= input_interval.end:
                draw_hitbox_overlay(
                    self.hitbox,
                    has_tap_input(self.kind) or has_release_input(self.kind),
                    unlerp_clamped(draw_start, self.target_time, time()),
                )

    def terminate(self):
        if is_skip():
            return
        if time() < self.despawn_time():
            return
        if (not is_replay() or self.played_hit_effects) and self.is_scored:
            play_note_hit_effects(
                self.kind,
                self.effect_kind,
                self.visual_lane,
                self.size,
                self.direction,
                self.judgment,
                y_offset=self.visual_y_offset,
                pivot_lane=self.visual_pivot_lane,
                half_offset=self.visual_half_offset,
            )

    def _basic_visual_lane_at(self, t: float) -> float:
        if self.stage_ref.index <= 0:
            return self.lane
        return get_stage_props(self.stage_ref.get(), t).pivot_lane + self.rel_lane

    def visual_lane_at(self, t: float) -> float:
        if self.is_attached:
            head = self.attach_head_ref.get()
            tail = self.attach_tail_ref.get()
            note_ease_frac = unlerp_clamped(head.target_time, tail.target_time, self.target_time)
            current_tail_lane = tail._basic_visual_lane_at(t)
            if t >= head.target_time:
                now_ease_frac = unlerp_clamped(head.target_time, tail.target_time, t)
                eased_now_ease_frac = ease(self.connector_ease, now_ease_frac)
                eased_note_ease_frac = ease(self.connector_ease, note_ease_frac)
                current_head_lane = lerp(
                    head._basic_visual_lane_at(t), tail._basic_visual_lane_at(t), eased_now_ease_frac
                )
                note_interp_frac = unlerp_clamped(eased_now_ease_frac, 1.0, eased_note_ease_frac)
                return lerp(current_head_lane, current_tail_lane, note_interp_frac)
            else:
                current_head_lane = head._basic_visual_lane_at(t)
                return lerp(current_head_lane, current_tail_lane, ease(self.connector_ease, note_ease_frac))
        return self._basic_visual_lane_at(t)

    def _basic_y_offset_at(self, t: float, left_limit: bool = False) -> float:
        if self.stage_ref.index <= 0:
            return 0.0
        return get_stage_props(self.stage_ref.get(), t, left_limit=left_limit).y_offset

    def y_offset_at(self, t: float) -> float:
        if self.is_attached:
            head = self.attach_head_ref.get()
            tail = self.attach_tail_ref.get()
            return remap_clamped(
                head.target_time,
                tail.target_time,
                head._basic_y_offset_at(t),
                tail._basic_y_offset_at(t),
                self.target_time,
            )
        return self._basic_y_offset_at(t)

    def _stage_pivot_lane_at(self, t: float) -> float:
        if self.stage_ref.index <= 0:
            return 0.0
        return get_stage_props(self.stage_ref.get(), t).pivot_lane

    def _stage_half_offset_at(self, t: float) -> bool:
        if self.stage_ref.index <= 0:
            return False
        division = get_stage_props(self.stage_ref.get(), t).division.start
        return division.parity == DivisionParity.ODD and division.size % 2 == 1

    @property
    def visual_lane(self) -> float:
        return self.visual_lane_at(time())

    @property
    def _basic_visual_y_offset(self) -> float:
        if self.stage_ref.index > 0:
            return self.stage_ref.get().props.y_offset
        else:
            return 0.0

    @property
    def visual_y_offset(self) -> float:
        if self.is_attached:
            head = self.attach_head_ref.get()
            tail = self.attach_tail_ref.get()
            return remap_clamped(
                head.target_time,
                tail.target_time,
                head._basic_visual_y_offset,
                tail._basic_visual_y_offset,
                self.target_time,
            )
        return self._basic_visual_y_offset

    @property
    def visual_pivot_lane(self) -> float:
        if self.stage_ref.index > 0:
            return self.stage_ref.get().props.pivot_lane
        else:
            return 0.0

    @property
    def visual_half_offset(self) -> bool:
        if self.stage_ref.index > 0:
            division = self.stage_ref.get().props.division.start
            return division.parity == DivisionParity.ODD and division.size % 2 == 1
        else:
            return False

    @property
    def progress(self) -> float:
        if self.is_attached:
            current_time = time()
            attach_head = self.attach_head_ref.get()
            attach_tail = self.attach_tail_ref.get()
            head_progress = (
                progress_to(
                    attach_head.target_scaled_time,
                    group_scaled_time(attach_head.timescale_group),
                    group_force_note_speed(attach_head.timescale_group),
                )
                if current_time < attach_head.target_time
                else 1.0
            )
            tail_progress = progress_to(
                attach_tail.target_scaled_time,
                group_scaled_time(attach_tail.timescale_group),
                group_force_note_speed(attach_tail.timescale_group),
            )
            head_frac = (
                0.0
                if current_time < attach_head.target_time
                else unlerp_clamped(attach_head.target_time, attach_tail.target_time, current_time)
            )
            tail_frac = 1.0
            frac = self.attach_frac
            return remap_clamped(head_frac, tail_frac, head_progress, tail_progress, frac)
        else:
            return progress_to(
                self.target_scaled_time,
                group_scaled_time(self.timescale_group),
                group_force_note_speed(self.timescale_group),
            )

    @property
    def visual_progress(self) -> float:
        return self.progress - self.visual_y_offset

    @property
    def head_ease_frac(self) -> float:
        if self.is_attached:
            return self.attach_frac
        else:
            return 0.0

    @property
    def tail_ease_frac(self) -> float:
        if self.is_attached:
            return self.attach_frac
        else:
            return 1.0

    @property
    def effective_attach_head(self) -> WatchBaseNote:
        ref = +EntityRef[WatchBaseNote]
        if self.is_attached:
            ref @= self.attach_head_ref
        else:
            ref @= self.ref()
        return ref.get()

    @property
    def effective_attach_tail(self) -> WatchBaseNote:
        ref = +EntityRef[WatchBaseNote]
        if self.is_attached:
            ref @= self.attach_tail_ref
        else:
            ref @= self.ref()
        return ref.get()


WATCH_NOTE_ARCHETYPES = derive_note_archetypes(WatchBaseNote)
