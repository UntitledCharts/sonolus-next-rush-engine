from __future__ import annotations

from math import ceil, floor, pi

from sonolus.script.archetype import (
    EntityRef,
    PlayArchetype,
    StandardImport,
    callback,
    entity_data,
    imported,
    shared_memory,
)
from sonolus.script.interval import clamp
from sonolus.script.runtime import time, touches
from sonolus.script.timing import beat_to_bpm, beat_to_time

from sekai.lib import archetype_names
from sekai.lib.baseevent import BaseEvent, init_event_list
from sekai.lib.ease import EaseType
from sekai.lib.events import Fever, draw_judgment_effect
from sekai.lib.layout import ZoomVerticalAlign, layout_lane_area, preempt_time, touch_to_lane
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
    play_lane_hit_effects,
)
from sekai.play import input_manager
from sekai.play.common import PlayLevelMemory
from sekai.play.events import SkillActive
from sekai.play.static_stage import StageMemory


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

    start_time: float = entity_data()
    end_time: float = entity_data()
    draw_start_time: float = entity_data()
    draw_end_time: float = entity_data()

    props: StageProps = shared_memory()

    @callback(order=-2)
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

    def spawn_order(self) -> float:
        return self.start_time

    def should_spawn(self) -> bool:
        return time() >= self.start_time

    @callback(order=-1)
    def update_sequential(self):
        self.props @= get_stage_props(self)
        if time() >= self.end_time:
            self.despawn = True
            return
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

    @callback(order=2)
    def touch(self):
        t = time()
        if t < self.draw_start_time or t > self.draw_end_time:
            return
        p = self.props
        if p.a < 1 or p.lane_alpha < 1:
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
        total_hitbox = layout_lane_area(leftmost - 0.5, rightmost + 0.5)
        empty_lanes = StageMemory.empty_lanes
        for touch in touches():
            if not total_hitbox.contains_point(touch.position):
                continue
            if not input_manager.is_allowed_empty(touch):
                continue
            lane = touch_to_lane(touch.position)
            rel = lane - p.pivot_lane
            if half_offset:
                rounded_lane = clamp(p.pivot_lane + round(rel), lo, hi)
            else:
                rounded_lane = clamp(p.pivot_lane + round(rel - 0.5) + 0.5, lo, hi)
            if touch.started:
                play_lane_hit_effects(rounded_lane, sfx=time() > PlayLevelMemory.last_note_sfx_time + 0.6)
                if not empty_lanes.is_full():
                    empty_lanes.append(rounded_lane)
            else:
                prev_lane = touch_to_lane(touch.prev_position)
                prev_rel = prev_lane - p.pivot_lane
                if half_offset:
                    prev_rounded_lane = clamp(p.pivot_lane + round(prev_rel), lo, hi)
                else:
                    prev_rounded_lane = clamp(p.pivot_lane + round(prev_rel - 0.5) + 0.5, lo, hi)
                if rounded_lane != prev_rounded_lane:
                    play_lane_hit_effects(rounded_lane, sfx=time() > PlayLevelMemory.last_note_sfx_time + 0.6)
                    if not empty_lanes.is_full():
                        empty_lanes.append(rounded_lane)

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


class StageMaskChange(PlayArchetype, BaseEvent):
    name = archetype_names.STAGE_MASK_CHANGE

    stage_ref: EntityRef[DynamicStage] = imported(name="stage")
    beat: StandardImport.BEAT
    lane: float = imported()
    size: float = imported()
    ease: EaseType = imported()
    next_ref: EntityRef[StageMaskChange] = imported(name="next")

    time: float = entity_data()

    @callback(order=-3)
    def preprocess(self):
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

    @callback(order=-3)
    def preprocess(self):
        self.time = beat_to_time(self.beat)
        self.y_offset = self.abs_y_offset + self.y_beat_offset * 60 / beat_to_bpm(self.beat) / preempt_time()
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
    judge_line_color: JudgeLineColor = imported(name="judgeLineColor")
    left_border_style: StageBorderStyle = imported(name="leftBorderStyle")
    right_border_style: StageBorderStyle = imported(name="rightBorderStyle")
    alpha: float = imported()
    lane_alpha: float = imported(name="laneAlpha")
    judge_line_alpha: float = imported(name="judgeLineAlpha")
    ease: EaseType = imported()
    next_ref: EntityRef[StageStyleChange] = imported(name="next")

    time: float = entity_data()

    @callback(order=-3)
    def preprocess(self):
        self.time = beat_to_time(self.beat)
        if Options.mirror:
            self.left_border_style, self.right_border_style = self.right_border_style, self.left_border_style

    def spawn_order(self) -> float:
        return 1e8

    def should_spawn(self) -> bool:
        return False
