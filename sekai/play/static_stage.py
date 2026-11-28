from sonolus.script.archetype import PlayArchetype, callback, entity_memory, get_archetype_by_name
from sonolus.script.array import Array, Dim
from sonolus.script.containers import VarArray
from sonolus.script.globals import level_memory
from sonolus.script.record import Record
from sonolus.script.runtime import offset_adjusted_time, time

from sekai.lib import archetype_names
from sekai.lib.custom_elements import LifeManager, ScoreIndicator
from sekai.lib.events import reset_fever_bounds
from sekai.lib.initialization import LastNote
from sekai.lib.layout import (
    IDENTITY_STAGE_SCREEN_TRANSFORM,
    JudgmentLaneInput,
    StaticStageData,
    refresh_layout,
)
from sekai.lib.level_config import LevelConfig
from sekai.lib.stage import draw_stage_and_accessories, play_lane_hit_effects
from sekai.lib.streams import Streams
from sekai.play import custom_elements, input_manager
from sekai.play.common import PlayLevelMemory


class EmptyInputCandidate(Record):
    frame: int
    stage_index: int
    lane_index: int
    lane: float
    distance_squared: float


@level_memory
class StageMemory:
    empty_lanes: VarArray[float, Dim[16]]
    empty_lane_stages: VarArray[int, Dim[16]]
    empty_input_candidates: Array[EmptyInputCandidate, Dim[32]]


class StaticStage(PlayArchetype):
    name = archetype_names.STATIC_STAGE
    dead_time: float = entity_memory()

    def spawn_order(self) -> float:
        return -1e8

    def should_spawn(self) -> bool:
        return True

    def initialize(self):
        self.dead_time = -2

    @callback(order=-3)
    def update_sequential(self):
        refresh_layout()
        reset_fever_bounds()

    @callback(order=4)
    def touch(self):
        empty_lanes = StageMemory.empty_lanes
        empty_stages = StageMemory.empty_lane_stages
        empty_lanes.clear()
        empty_stages.clear()
        frame = input_manager.InputState.frame
        sfx = time() > PlayLevelMemory.last_note_sfx_time + 0.6
        if LevelConfig.dynamic_stages:
            for i, touch in enumerate(input_manager.processed_touches()):
                candidate = StageMemory.empty_input_candidates[i]
                if candidate.frame != frame or candidate.stage_index <= 0:
                    continue
                if input_manager.register_empty_input(touch, candidate.lane_index, candidate.stage_index):
                    stage = get_archetype_by_name(archetype_names.STAGE).at(candidate.stage_index)
                    play_lane_hit_effects(
                        candidate.lane, sfx=sfx, transform=stage.screen_transform(), y_offset=stage.props.y_offset
                    )
                    if not empty_lanes.is_full():
                        empty_lanes.append(candidate.lane)
                        empty_stages.append(candidate.stage_index)
        else:
            bounds = JudgmentLaneInput.at(-5.5, 5.5, 0, IDENTITY_STAGE_SCREEN_TRANSFORM)
            for touch in input_manager.processed_touches():
                if not input_manager.is_allowed_empty(touch):
                    continue
                lane_index, _ = bounds.lane_at(touch.position)
                if lane_index >= 0 and input_manager.register_empty_input(touch, lane_index):
                    lane = lane_index - 5.5
                    play_lane_hit_effects(lane, sfx=sfx, transform=IDENTITY_STAGE_SCREEN_TRANSFORM)
                    if not empty_lanes.is_full():
                        empty_lanes.append(lane)
        if len(empty_lanes) > 0:
            Streams.empty_input_lanes[offset_adjusted_time()] = empty_lanes
            if LevelConfig.dynamic_stages:
                Streams.empty_input_stages[offset_adjusted_time()] = empty_stages

    def update_parallel(self):
        draw_stage_and_accessories(
            custom_elements.ComboJudgeMemory.ap,
            ScoreIndicator.score,
            ScoreIndicator.note_score,
            ScoreIndicator.note_time,
            ScoreIndicator.percentage,
            StaticStageData.background_cover,
            StaticStageData.dead_effect_quads,
            StaticStageData.ui_layout,
            LifeManager.life,
            LastNote.last_time,
            self.dead_time,
            StaticStageData.layout_stage,
        )
        if LifeManager.life == 0 and self.dead_time != -2:
            self.dead_time = time()
