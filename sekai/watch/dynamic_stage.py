from __future__ import annotations

from math import pi

from sonolus.script.archetype import (
    EntityRef,
    StandardImport,
    WatchArchetype,
    callback,
    entity_data,
    imported,
    shared_memory,
)
from sonolus.script.interval import clamp
from sonolus.script.runtime import time
from sonolus.script.timing import beat_to_bpm, beat_to_time

from sekai.lib import archetype_names
from sekai.lib.baseevent import BaseEvent, init_event_list
from sekai.lib.ease import EaseType
from sekai.lib.events import Fever, draw_judgment_effect
from sekai.lib.layout import ZoomVerticalAlign, preempt_time
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import Options
from sekai.lib.stage import (
    DivisionParity,
    JudgeLineColor,
    StageBorderStyle,
    StageProps,
    get_draw_end_time,
    get_draw_start_time,
    get_end_time,
    get_stage_props,
    get_start_time,
)
from sekai.watch.events import SkillActive


class WatchCameraChange(WatchArchetype, BaseEvent):
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
    next_ref: EntityRef[WatchCameraChange] = imported(name="next")

    time: float = entity_data()

    @callback(order=-2)
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


class WatchDynamicStage(WatchArchetype):
    name = archetype_names.STAGE

    from_start: bool = imported(name="fromStart")
    until_end: bool = imported(name="untilEnd")
    first_mask_change_ref: EntityRef[WatchStageMaskChange] = imported(name="firstMaskChange")
    first_pivot_change_ref: EntityRef[WatchStagePivotChange] = imported(name="firstPivotChange")
    first_style_change_ref: EntityRef[WatchStageStyleChange] = imported(name="firstStyleChange")

    start_time: float = entity_data()
    end_time: float = entity_data()
    draw_start_time: float = entity_data()
    draw_end_time: float = entity_data()

    props: StageProps = shared_memory()

    @callback(order=-1)
    def preprocess(self):
        LevelConfig.dynamic_stages = True
        LevelConfig.skip_default_stage = True
        init_event_list(self.first_mask_change_ref)
        init_event_list(self.first_pivot_change_ref)
        init_event_list(self.first_style_change_ref)
        self.start_time = get_start_time(self)
        self.end_time = get_end_time(self)
        self.draw_start_time = get_draw_start_time(self)
        self.draw_end_time = get_draw_end_time(self)

    def spawn_time(self) -> float:
        return self.start_time

    def despawn_time(self) -> float:
        return self.end_time

    @callback(order=-1)
    def update_sequential(self):
        self.props @= get_stage_props(self)
        self.fever_boundary()

    def fever_boundary(self):
        if self.props.a > 0:
            l = self.props.lane - self.props.width
            r = self.props.lane + self.props.width

            if l < Fever.min_l:
                Fever.min_l = l
                Fever.alpha_l = self.props.a
            elif l == Fever.min_l and self.props.a > Fever.alpha_l:
                Fever.alpha_l = self.props.a

            if r > Fever.max_r:
                Fever.max_r = r
                Fever.alpha_r = self.props.a
            elif r == Fever.max_r and self.props.a > Fever.alpha_r:
                Fever.alpha_r = self.props.a

            Fever.has_active = True
            Fever.y_offset = self.props.y_offset

    def update_parallel(self):
        t = time()
        if t < self.draw_start_time or t > self.draw_end_time:
            return
        self.props.draw()

        if SkillActive.judgment:
            elapsed = t - SkillActive.start_time
            if elapsed < 6:
                l = self.props.lane - self.props.width
                r = self.props.lane + self.props.width
                draw_judgment_effect(elapsed, l, r, self.props.a, self.props.y_offset)


class WatchStageMaskChange(WatchArchetype, BaseEvent):
    name = archetype_names.STAGE_MASK_CHANGE

    stage_ref: EntityRef[WatchDynamicStage] = imported(name="stage")
    beat: StandardImport.BEAT
    lane: float = imported()
    size: float = imported()
    ease: EaseType = imported()
    next_ref: EntityRef[WatchStageMaskChange] = imported(name="next")

    time: float = entity_data()

    @callback(order=-2)
    def preprocess(self):
        self.time = beat_to_time(self.beat)
        if Options.mirror:
            self.lane *= -1


class WatchStagePivotChange(WatchArchetype, BaseEvent):
    name = archetype_names.STAGE_PIVOT_CHANGE

    stage_ref: EntityRef[WatchDynamicStage] = imported(name="stage")
    beat: StandardImport.BEAT
    lane: float = imported()
    division_size: float = imported(name="divisionSize")
    division_parity: DivisionParity = imported(name="divisionParity")
    abs_y_offset: float = imported(name="yOffset")
    y_beat_offset: float = imported(name="yBeatOffset")
    ease: EaseType = imported()
    next_ref: EntityRef[WatchStagePivotChange] = imported(name="next")

    y_offset: float = entity_data()
    time: float = entity_data()

    @callback(order=-2)
    def preprocess(self):
        self.time = beat_to_time(self.beat)
        self.y_offset = self.abs_y_offset + self.y_beat_offset * 60 / beat_to_bpm(self.beat) / preempt_time()
        if Options.mirror:
            self.lane *= -1


class WatchStageStyleChange(WatchArchetype, BaseEvent):
    name = archetype_names.STAGE_STYLE_CHANGE

    stage_ref: EntityRef[WatchDynamicStage] = imported(name="stage")
    beat: StandardImport.BEAT
    judge_line_color: JudgeLineColor = imported(name="judgeLineColor")
    left_border_style: StageBorderStyle = imported(name="leftBorderStyle")
    right_border_style: StageBorderStyle = imported(name="rightBorderStyle")
    alpha: float = imported()
    lane_alpha: float = imported(name="laneAlpha")
    judge_line_alpha: float = imported(name="judgeLineAlpha")
    ease: EaseType = imported()
    next_ref: EntityRef[WatchStageStyleChange] = imported(name="next")

    time: float = entity_data()

    @callback(order=-2)
    def preprocess(self):
        self.time = beat_to_time(self.beat)
        if Options.mirror:
            self.left_border_style, self.right_border_style = self.right_border_style, self.left_border_style
