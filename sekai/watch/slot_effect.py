from sonolus.script.archetype import WatchArchetype, entity_memory
from sonolus.script.interval import Interval
from sonolus.script.runtime import is_skip
from sonolus.script.sprite import Sprite

from sekai.lib import archetype_names
from sekai.lib.layout import IDENTITY_STAGE_SCREEN_TRANSFORM, NoteStageParams, NoteStageProjection
from sekai.lib.options import Options
from sekai.lib.slot_animation import slot_effect_duration, slot_glow_duration
from sekai.lib.slot_effect import (
    clear_slot_effects,
    draw_slot_effects_in_range,
    draw_slot_glow_effects_in_range,
    is_slot_generation_visible,
    next_slot_generation,
)


class WatchSlotGlowEffect(WatchArchetype):
    name = archetype_names.SLOT_GLOW_EFFECT

    sprite: Sprite = entity_memory()
    start_time: float = entity_memory()
    left: int = entity_memory()
    right: int = entity_memory()
    shift: float = entity_memory()
    bounds: Interval = entity_memory()
    y_offset: float = entity_memory()
    stage: NoteStageParams = entity_memory()
    projection: NoteStageProjection = entity_memory()
    end_time: float = entity_memory()
    group_id: float = entity_memory()
    pool_id: int = entity_memory()
    generation: float = entity_memory()

    def initialize(self):
        self.generation = -1
        self.end_time = self.start_time + slot_glow_duration(self.pool_id) / Options.effect_animation_speed

    def spawn_time(self) -> float:
        return self.start_time

    def despawn_time(self) -> float:
        return self.start_time + slot_glow_duration(self.pool_id) / Options.effect_animation_speed

    def update_sequential(self):
        if is_skip():
            clear_slot_effects()
            self.generation = -1
            return
        if self.generation >= 0:
            return
        self.generation = next_slot_generation(self.sprite, self.group_id, self.right - self.left, self.pool_id)

    def update_parallel(self):
        if not is_slot_generation_visible(self.sprite, self.generation + self.right - self.left - 1, self.pool_id):
            return
        if self.stage.has_transform():
            self.projection.update(self.stage)
            draw_slot_glow_effects_in_range(
                self.sprite,
                self.start_time,
                self.end_time,
                self.left,
                self.right,
                shift=self.shift,
                bounds=self.bounds,
                generation=self.generation,
                pool_id=self.pool_id,
                y_offset=self.y_offset,
                transform=self.projection.transform,
            )
        else:
            draw_slot_glow_effects_in_range(
                self.sprite,
                self.start_time,
                self.end_time,
                self.left,
                self.right,
                shift=self.shift,
                bounds=self.bounds,
                generation=self.generation,
                pool_id=self.pool_id,
                y_offset=self.y_offset,
                transform=IDENTITY_STAGE_SCREEN_TRANSFORM,
            )

    def terminate(self):
        self.generation = -1


class WatchSlotEffect(WatchArchetype):
    name = archetype_names.SLOT_EFFECT

    sprite: Sprite = entity_memory()
    start_time: float = entity_memory()
    left: int = entity_memory()
    right: int = entity_memory()
    shift: float = entity_memory()
    bounds: Interval = entity_memory()
    y_offset: float = entity_memory()
    stage: NoteStageParams = entity_memory()
    projection: NoteStageProjection = entity_memory()
    end_time: float = entity_memory()
    group_id: float = entity_memory()
    pool_id: int = entity_memory()
    generation: float = entity_memory()

    def initialize(self):
        self.generation = -1
        self.end_time = self.start_time + slot_effect_duration(self.pool_id) / Options.effect_animation_speed

    def spawn_time(self) -> float:
        return self.start_time

    def despawn_time(self) -> float:
        return self.start_time + slot_effect_duration(self.pool_id) / Options.effect_animation_speed

    def update_sequential(self):
        if is_skip():
            clear_slot_effects()
            self.generation = -1
            return
        if self.generation >= 0:
            return
        self.generation = next_slot_generation(self.sprite, self.group_id, self.right - self.left, self.pool_id)

    def update_parallel(self):
        if not is_slot_generation_visible(self.sprite, self.generation + self.right - self.left - 1, self.pool_id):
            return
        if self.stage.has_transform():
            self.projection.update(self.stage)
            draw_slot_effects_in_range(
                self.sprite,
                self.start_time,
                self.end_time,
                self.left,
                self.right,
                self.shift,
                bounds=self.bounds,
                generation=self.generation,
                pool_id=self.pool_id,
                y_offset=self.y_offset,
                transform=self.projection.transform,
            )
        else:
            draw_slot_effects_in_range(
                self.sprite,
                self.start_time,
                self.end_time,
                self.left,
                self.right,
                self.shift,
                bounds=self.bounds,
                generation=self.generation,
                pool_id=self.pool_id,
                y_offset=self.y_offset,
                transform=IDENTITY_STAGE_SCREEN_TRANSFORM,
            )

    def terminate(self):
        self.generation = -1


WATCH_SLOT_EFFECT_ARCHETYPES = (
    WatchSlotGlowEffect,
    WatchSlotEffect,
)
