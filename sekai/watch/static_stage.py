from sonolus.script.archetype import WatchArchetype, callback, entity_memory
from sonolus.script.runtime import is_replay, is_skip, time

from sekai.lib import archetype_names
from sekai.lib.layer import (
    LAYER_BACKGROUND,
    LAYER_BACKGROUND_COVER,
    LAYER_COVER,
    LAYER_COVER_LINE,
    LAYER_JUDGMENT,
    LAYER_JUDGMENT_LINE,
    LAYER_STAGE,
    LAYER_STAGE_COVER,
    LAYER_STAGE_LANE,
    get_z,
)
from sekai.lib.layout import refresh_layout
from sekai.lib.options import Options
from sekai.lib.stage import draw_stage_and_accessories, play_lane_particle
from sekai.lib.streams import Streams
from sekai.watch import custom_elements, initialization


class WatchStaticStage(WatchArchetype):
    name = archetype_names.STATIC_STAGE
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
    z_layer_background: float = entity_memory()

    def spawn_time(self) -> float:
        return -1e8

    def despawn_time(self) -> float:
        return 1e8

    @callback(order=-2)
    def update_sequential(self):
        refresh_layout()
        custom_elements.LifeManager.life = (
            Streams.life[self.index][time()] if is_replay() else custom_elements.LifeManager.life
        )
        if is_skip() and time() < custom_elements.ScoreIndicator.first:
            if Options.custom_score == 2:
                custom_elements.ScoreIndicator.score = 100
            else:
                custom_elements.ScoreIndicator.score = 0
            custom_elements.ScoreIndicator.ap = False

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
            self.z_layer_background,
            custom_elements.ScoreIndicator.ap,
            custom_elements.ScoreIndicator.score,
            custom_elements.LifeManager.life,
            initialization.LastNote.last_time,
        )


class WatchScheduledLaneEffect(WatchArchetype):
    name = archetype_names.SCHEDULED_LANE_EFFECT

    lane: float = entity_memory()
    target_time: float = entity_memory()

    def spawn_time(self) -> float:
        return self.target_time

    def despawn_time(self) -> float:
        return self.target_time + 1

    def initialize(self):
        if is_skip():
            return
        play_lane_particle(self.lane)
