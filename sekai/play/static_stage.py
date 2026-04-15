from sonolus.script.archetype import PlayArchetype, callback, entity_memory
from sonolus.script.array import Dim
from sonolus.script.containers import VarArray
from sonolus.script.globals import level_memory
from sonolus.script.interval import clamp
from sonolus.script.runtime import offset_adjusted_time, time, touches

from sekai.lib import archetype_names
from sekai.lib.custom_elements import LifeManager, ScoreIndicator
from sekai.lib.events import reset_fever_bounds
from sekai.lib.initialization import LastNote
from sekai.lib.layout import layout_lane_area, refresh_layout, touch_to_lane
from sekai.lib.level_config import LevelConfig
from sekai.lib.stage import draw_stage_and_accessories, init_stage_z_layers, play_lane_hit_effects
from sekai.lib.streams import Streams
from sekai.play import custom_elements, input_manager
from sekai.play.common import PlayLevelMemory


@level_memory
class StageMemory:
    empty_lanes: VarArray[float, Dim[16]]


class StaticStage(PlayArchetype):
    name = archetype_names.STATIC_STAGE
    dead_time: float = entity_memory()
    z_layer_stage_lane: float = entity_memory()
    z_layer_judgment: float = entity_memory()
    z_layer_cover: float = entity_memory()
    z_layer_cover_line: float = entity_memory()
    z_layer_judgment_line: float = entity_memory()
    z_layer_background_cover: float = entity_memory()
    z_layer_stage: float = entity_memory()
    z_layer_stage_cover: float = entity_memory()
    z_layer_score: float = entity_memory()
    z_layer_score_glow: float = entity_memory()
    z_layer_score_bar: float = entity_memory()
    z_layer_score_bar_mask: float = entity_memory()
    z_layer_score_bar_rate: float = entity_memory()
    z_layer_background: float = entity_memory()

    def spawn_order(self) -> float:
        return -1e8

    def should_spawn(self) -> bool:
        return True

    def initialize(self):
        init_stage_z_layers(self)
        self.dead_time = -2

    @callback(order=-2)
    def update_sequential(self):
        refresh_layout()
        reset_fever_bounds()
        Streams.life[self.index][offset_adjusted_time()] = LifeManager.life

    @callback(order=3)
    def touch(self):
        empty_lanes = StageMemory.empty_lanes
        if LevelConfig.dynamic_stages:
            if len(empty_lanes) > 0:
                Streams.empty_input_lanes[offset_adjusted_time()] = empty_lanes
                empty_lanes.clear()
            return
        empty_lanes.clear()
        total_hitbox = layout_lane_area(-7, 7)
        for touch in touches():
            if not total_hitbox.contains_point(touch.position):
                continue
            if not input_manager.is_allowed_empty(touch):
                continue
            lane = touch_to_lane(touch.position)
            rounded_lane = clamp(round(lane - 0.5) + 0.5, -5.5, 5.5)
            if touch.started:
                play_lane_hit_effects(rounded_lane, sfx=time() > PlayLevelMemory.last_note_sfx_time + 0.6)
                if not empty_lanes.is_full():
                    empty_lanes.append(rounded_lane)
            else:
                prev_lane = touch_to_lane(touch.prev_position)
                prev_rounded_lane = clamp(round(prev_lane - 0.5) + 0.5, -5.5, 5.5)
                if rounded_lane != prev_rounded_lane:
                    play_lane_hit_effects(rounded_lane, sfx=time() > PlayLevelMemory.last_note_sfx_time + 0.6)
                    if not empty_lanes.is_full():
                        empty_lanes.append(rounded_lane)
        if len(empty_lanes) > 0:
            Streams.empty_input_lanes[offset_adjusted_time()] = empty_lanes

    def update_parallel(self):
        draw_stage_and_accessories(
            self.z_layer_stage_lane,
            self.z_layer_stage_cover,
            self.z_layer_stage,
            self.z_layer_judgment_line,
            self.z_layer_cover,
            self.z_layer_cover_line,
            self.z_layer_judgment,
            self.z_layer_background_cover,
            self.z_layer_score,
            self.z_layer_score_glow,
            self.z_layer_score_bar,
            self.z_layer_score_bar_mask,
            self.z_layer_score_bar_rate,
            self.z_layer_background,
            custom_elements.ComboJudgeMemory.ap,
            ScoreIndicator.score,
            ScoreIndicator.note_score,
            ScoreIndicator.note_time,
            ScoreIndicator.percentage,
            LifeManager.life,
            LastNote.last_time,
            self.dead_time,
        )
        if LifeManager.life == 0 and self.dead_time != -2:
            self.dead_time = time()
