from __future__ import annotations

from math import ceil, floor, pi

from sonolus.script.archetype import (
    EntityRef,
    PlayArchetype,
    StandardImport,
    callback,
    entity_data,
    entity_memory,
    imported,
    shared_memory,
)
from sonolus.script.interval import Interval, clamp
from sonolus.script.runtime import time
from sonolus.script.timing import beat_to_bpm, beat_to_time

from sekai.lib import archetype_names
from sekai.lib.baseevent import BaseEvent, init_event_list
from sekai.lib.ease import EaseType
from sekai.lib.events import Fever, draw_judgment_effect
from sekai.lib.layout import (
    IDENTITY_STAGE_SCREEN_TRANSFORM,
    DynamicLayout,
    JudgmentLaneInput,
    StageRotationCenter,
    StageScreenTransform,
    StageTransform,
    StageTransformAnchor,
    ZoomVerticalAlign,
    preempt_time,
)
from sekai.lib.level_config import LevelConfig
from sekai.lib.note_style import NoteStyle
from sekai.lib.options import Options
from sekai.lib.stage import (
    DivisionParity,
    JudgeLineColor,
    JudgeLineStyle,
    StageBorderStyle,
    StageEventCursors,
    StageProps,
    StageSamplingPlan,
    StageSharedProps,
    get_draw_end_time,
    get_draw_start_time,
    get_end_time,
    get_stage_props,
    get_start_time,
    initialize_stage_note_visibility,
    stage_y_offset_bounds,
    update_prepared_stage_props,
)
from sekai.play import input_manager
from sekai.play.events import SkillActive
from sekai.play.static_stage import EmptyInputCandidate, StageMemory


class CameraChange(PlayArchetype, BaseEvent):
    name = archetype_names.CAMERA_CHANGE

    beat: StandardImport.BEAT
    lane: float = imported()
    size: float = imported()
    zoom: float = imported(default=1)
    zoom_target_lane: float = imported(name="zoomTargetLane")
    zoom_target_y: float = imported(name="zoomTargetY")
    zoom_vertical_align: ZoomVerticalAlign = imported(name="zoomVerticalAlign")
    rotate: float = imported()
    stage_tilt: float = imported(name="stageTilt", default=1)
    ease: EaseType = imported()
    next_ref: EntityRef[CameraChange] = imported(name="next")

    time: float = entity_data()

    @callback(order=-4)
    def preprocess(self):
        LevelConfig.dynamic_stages = True
        self.time = beat_to_time(self.beat)
        self.zoom = max(self.zoom, 0.01)
        self.rotate = self.rotate * pi / 180
        self.stage_tilt = clamp(self.stage_tilt, 0, 1)
        if Options.mirror:
            self.lane *= -1
            self.zoom_target_lane *= -1
            self.rotate *= -1

    def spawn_order(self) -> float:
        return 1e8

    def should_spawn(self) -> bool:
        return False


class StageTransformChange(PlayArchetype, BaseEvent):
    name = archetype_names.STAGE_TRANSFORM_CHANGE

    stage_ref: EntityRef[DynamicStage] = imported(name="stage")
    beat: StandardImport.BEAT
    rotate: float = imported()
    x_lane_translate: float = imported(name="xLaneTranslate")
    y_lane_translate: float = imported(name="yLaneTranslate")
    elevation: float = imported()
    anchor: StageTransformAnchor = imported(name="anchor")
    rotation_center: StageRotationCenter = imported(name="rotationCenter")
    rotation_center_x_offset: float = imported(name="rotationCenterXOffset")
    rotation_center_y_offset: float = imported(name="rotationCenterYOffset")
    ease: EaseType = imported()
    next_ref: EntityRef[StageTransformChange] = imported(name="next")

    time: float = entity_data()

    @callback(order=-4)
    def preprocess(self):
        LevelConfig.dynamic_stages = True
        LevelConfig.has_stage_transforms = True
        self.time = beat_to_time(self.beat)
        self.rotate = self.rotate * pi / 180
        if Options.mirror:
            self.rotate *= -1
            self.x_lane_translate *= -1
            self.rotation_center_x_offset *= -1

    def spawn_order(self) -> float:
        return 1e8

    def should_spawn(self) -> bool:
        return False


class DynamicStage(PlayArchetype):
    name = archetype_names.STAGE

    from_start: bool = imported(name="fromStart")
    until_end: bool = imported(name="untilEnd")
    first_mask_change_ref: EntityRef[StageMaskChange] = imported(name="firstMaskChange")
    first_pivot_change_ref: EntityRef[StagePivotChange] = imported(name="firstPivotChange")
    first_style_change_ref: EntityRef[StageStyleChange] = imported(name="firstStyleChange")
    first_transform_change_ref: EntityRef[StageTransformChange] = imported(name="firstTransformChange")

    start_time: float = entity_data()
    end_time: float = entity_data()
    draw_start_time: float = entity_data()
    draw_end_time: float = entity_data()
    y_offset_bounds: Interval = entity_data()
    note_visibility_end: float = entity_data()
    sampling_plan: StageSamplingPlan = entity_data()

    use_event_cursors: bool = entity_data()
    event_cursors: StageEventCursors = entity_memory()
    visual_transform: StageTransform = shared_memory()
    visual_screen_transform: StageScreenTransform = shared_memory()
    transform_revision: int = entity_memory()
    draw_props: StageProps = entity_memory()
    props: StageSharedProps = shared_memory()

    @callback(order=-2)
    def preprocess(self):
        LevelConfig.dynamic_stages = True
        LevelConfig.skip_default_stage = True
        init_event_list(self.first_mask_change_ref)
        init_event_list(self.first_pivot_change_ref)
        init_event_list(self.first_style_change_ref)
        init_event_list(self.first_transform_change_ref)
        pivot_ref = +self.first_pivot_change_ref
        while pivot_ref.index > 0:
            pivot = pivot_ref.get()
            pivot.y_offset = pivot.abs_y_offset + pivot.y_beat_offset * 60 / beat_to_bpm(pivot.beat) / preempt_time()
            pivot_ref.index = pivot.next_ref.index
        self.y_offset_bounds = stage_y_offset_bounds(self)
        self.note_visibility_end = initialize_stage_note_visibility(self)
        self.start_time = get_start_time(self)
        self.end_time = get_end_time(self)
        self.draw_start_time = get_draw_start_time(self)
        self.draw_end_time = get_draw_end_time(self)
        self.use_event_cursors = (
            (self.first_mask_change_ref.index > 0 and self.first_mask_change_ref.get().skip_levels >= 3)
            or (self.first_pivot_change_ref.index > 0 and self.first_pivot_change_ref.get().skip_levels >= 3)
            or (self.first_style_change_ref.index > 0 and self.first_style_change_ref.get().skip_levels >= 3)
            or (self.first_transform_change_ref.index > 0 and self.first_transform_change_ref.get().skip_levels >= 3)
        )
        self.sampling_plan @= StageSamplingPlan.prepare(self)
        # A singleton event applies before its time, so constant tracks are correct at 0.
        # Animated tracks are resampled before consumers run each frame.
        self.draw_props @= get_stage_props(self, target_time=0.0, right_limit=True)
        self.props @= self.draw_props.shared()

    def spawn_order(self) -> float:
        return self.start_time

    def should_spawn(self) -> bool:
        return time() >= self.start_time

    @callback(order=-2)
    def update_sequential(self):
        sampling = not self.sampling_plan.is_static
        if sampling:
            if self.use_event_cursors:
                update_prepared_stage_props(self.draw_props, self, self.sampling_plan, time(), self.event_cursors)
            else:
                update_prepared_stage_props(self.draw_props, self, self.sampling_plan, time())
        if self.draw_props.has_transform():
            revision = DynamicLayout.revision + 1
            if self.transform_revision != revision or (sampling and self.draw_props.transform_changed(self.props)):
                self.visual_transform @= self.draw_props.stage_transform()
                self.visual_screen_transform @= self.visual_transform.to_screen_transform()
                self.transform_revision = revision
        if sampling:
            self.props @= self.draw_props.shared()
        if time() >= self.end_time:
            self.despawn = True
            return
        self.fever_boundary()

    def fever_boundary(self):
        if self.draw_props.lane_alpha > 0:
            l = self.draw_props.lane - self.draw_props.width
            r = self.draw_props.lane + self.draw_props.width
            transform = self.screen_transform()

            if l < Fever.min_l:
                Fever.min_l = l
                Fever.alpha_l = self.draw_props.lane_alpha
                Fever.left_transform = transform
            elif l == Fever.min_l and self.draw_props.lane_alpha > Fever.alpha_l:
                Fever.alpha_l = self.draw_props.lane_alpha
                Fever.left_transform = transform

            if r > Fever.max_r:
                Fever.max_r = r
                Fever.alpha_r = self.draw_props.lane_alpha
                Fever.right_transform = transform
            elif r == Fever.max_r and self.draw_props.lane_alpha > Fever.alpha_r:
                Fever.alpha_r = self.draw_props.lane_alpha
                Fever.right_transform = transform

            Fever.has_active = True
            Fever.y_offset = self.draw_props.y_offset

    @callback(order=3)
    def touch(self):
        t = time()
        if t < self.draw_start_time or t > self.draw_end_time:
            return
        p = self.draw_props
        if p.lane_alpha * (1 - p.full_width) < 1:
            return
        half_offset = p.division.start.parity == DivisionParity.ODD and p.division.start.size % 2 == 1
        lo = p.lane - p.width + 0.5
        hi = p.lane + p.width - 0.5
        if half_offset:
            leftmost = p.pivot_lane + ceil(lo - p.pivot_lane)
            rightmost = p.pivot_lane + floor(hi - p.pivot_lane)
        else:
            leftmost = p.pivot_lane + 0.5 + ceil(lo - p.pivot_lane - 0.5)
            rightmost = p.pivot_lane + 0.5 + floor(hi - p.pivot_lane - 0.5)
        if leftmost > rightmost:
            return
        bounds = JudgmentLaneInput.at(leftmost, rightmost, p.y_offset, self.screen_transform())
        frame = input_manager.InputState.frame
        for i, touch in enumerate(input_manager.processed_touches()):
            if not input_manager.is_allowed_empty(touch):
                continue
            lane_index, distance = bounds.lane_at(touch.position)
            if lane_index < 0:
                continue
            candidate = StageMemory.empty_input_candidates[i]
            if candidate.frame != frame or distance < candidate.distance_squared:
                candidate @= EmptyInputCandidate(
                    frame=frame,
                    stage_index=self.index,
                    lane_index=lane_index,
                    lane=leftmost + lane_index,
                    distance_squared=distance,
                )

    def screen_transform(self) -> StageScreenTransform:
        result = +IDENTITY_STAGE_SCREEN_TRANSFORM
        if self.props.has_transform():
            result @= self.visual_screen_transform
        return result

    def update_parallel(self):
        t = time()
        if t < self.draw_start_time or t > self.draw_end_time:
            return
        if self.draw_props.should_draw():
            self.draw_props.draw(self.index, self.screen_transform())
        if SkillActive.judgment:
            elapsed = t - SkillActive.start_time
            if elapsed < SkillActive.duration:
                l = self.draw_props.lane - self.draw_props.width
                r = self.draw_props.lane + self.draw_props.width
                draw_judgment_effect(
                    elapsed,
                    l,
                    r,
                    self.draw_props.judge_line_alpha,
                    self.draw_props.y_offset,
                    duration=SkillActive.duration,
                    transform=self.screen_transform(),
                )


class StageMaskChange(PlayArchetype, BaseEvent):
    name = archetype_names.STAGE_MASK_CHANGE

    stage_ref: EntityRef[DynamicStage] = imported(name="stage")
    beat: StandardImport.BEAT
    lane: float = imported()
    size: float = imported()
    mask_notes: bool = imported(name="maskNotes", default=False)
    ease: EaseType = imported()
    next_ref: EntityRef[StageMaskChange] = imported(name="next")

    time: float = entity_data()

    @callback(order=-4)
    def preprocess(self):
        LevelConfig.dynamic_stages = True
        self.time = beat_to_time(self.beat)
        if Options.mirror:
            self.lane *= -1

    def spawn_order(self) -> float:
        return 1e8

    def should_spawn(self) -> bool:
        return False


class StagePivotChange(PlayArchetype, BaseEvent):
    name = archetype_names.STAGE_PIVOT_CHANGE

    stage_ref: EntityRef[DynamicStage] = imported(name="stage")
    beat: StandardImport.BEAT
    lane: float = imported()
    division_size: float = imported(name="divisionSize")
    division_parity: DivisionParity = imported(name="divisionParity")
    abs_y_offset: float = imported(name="yOffset")
    y_beat_offset: float = imported(name="yBeatOffset")
    ease: EaseType = imported()
    next_ref: EntityRef[StagePivotChange] = imported(name="next")

    y_offset: float = entity_data()
    time: float = entity_data()

    @callback(order=-4)
    def preprocess(self):
        LevelConfig.dynamic_stages = True
        self.time = beat_to_time(self.beat)
        if Options.mirror:
            self.lane *= -1

    def spawn_order(self) -> float:
        return 1e8

    def should_spawn(self) -> bool:
        return False


class StageStyleChange(PlayArchetype, BaseEvent):
    name = archetype_names.STAGE_STYLE_CHANGE

    stage_ref: EntityRef[DynamicStage] = imported(name="stage")
    beat: StandardImport.BEAT
    lane_color: NoteStyle = imported(name="laneColor", default=NoteStyle.DEFAULT)
    judge_line_color: JudgeLineColor = imported(name="judgeLineColor")
    judge_line_style: JudgeLineStyle = imported(name="judgeLineStyle")
    left_border_style: StageBorderStyle = imported(name="leftBorderStyle")
    right_border_style: StageBorderStyle = imported(name="rightBorderStyle")
    full_width: bool = imported(name="fullWidth")
    alpha: float = imported(default=1)  # Deprecated
    lane_alpha: float = imported(name="laneAlpha")
    judge_line_alpha: float = imported(name="judgeLineAlpha")
    division_line_alpha: float = imported(name="divisionLineAlpha", default=1)
    note_alpha: float = imported(name="noteAlpha", default=1)
    ease: EaseType = imported()
    next_ref: EntityRef[StageStyleChange] = imported(name="next")

    time: float = entity_data()
    note_visibility_start: float = entity_data()
    previous_note_visibility_end: float = entity_data()

    @callback(order=-4)
    def preprocess(self):
        LevelConfig.dynamic_stages = True
        self.time = beat_to_time(self.beat)
        self.lane_alpha *= self.alpha
        self.judge_line_alpha *= self.alpha
        if Options.mirror:
            self.left_border_style, self.right_border_style = self.right_border_style, self.left_border_style

    def spawn_order(self) -> float:
        return 1e8

    def should_spawn(self) -> bool:
        return False
