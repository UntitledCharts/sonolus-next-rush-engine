from sonolus.script.archetype import PlayArchetype, entity_memory
from sonolus.script.runtime import time
from sonolus.script.sprite import Sprite

from sekai.lib import archetype_names
from sekai.lib.layout import AffineTransform2d
from sekai.lib.options import Options
from sekai.lib.slot_effect import (
    SLOT_EFFECT_DURATION,
    SLOT_GLOW_EFFECT_DURATION,
    draw_slot_effects_in_range,
    draw_slot_glow_effects_in_range,
    is_slot_generation_visible,
    next_slot_generation,
)


class SlotGlowEffect(PlayArchetype):
    name = archetype_names.SLOT_GLOW_EFFECT

    sprite: Sprite = entity_memory()
    start_time: float = entity_memory()
    left: int = entity_memory()
    right: int = entity_memory()
    y_offset: float = entity_memory()
    transform: AffineTransform2d = entity_memory()
    end_time: float = entity_memory()
    group_id: float = entity_memory()
    generation: float = entity_memory()
    generation_set: bool = entity_memory()

    def initialize(self):
        self.end_time = self.start_time + SLOT_GLOW_EFFECT_DURATION / Options.effect_animation_speed

    def update_sequential(self):
        if self.despawn or self.generation_set:
            return
        self.generation = next_slot_generation(self.sprite, self.group_id)
        self.generation_set = True

    def update_parallel(self):
        if time() > self.end_time or not is_slot_generation_visible(self.sprite, self.generation):
            self.despawn = True
            return
        draw_slot_glow_effects_in_range(
            self.sprite,
            self.start_time,
            self.end_time,
            self.left,
            self.right,
            y_offset=self.y_offset,
            transform=self.transform,
        )


class SlotEffect(PlayArchetype):
    name = archetype_names.SLOT_EFFECT

    sprite: Sprite = entity_memory()
    start_time: float = entity_memory()
    left: int = entity_memory()
    right: int = entity_memory()
    shift: float = entity_memory()
    y_offset: float = entity_memory()
    transform: AffineTransform2d = entity_memory()
    end_time: float = entity_memory()
    group_id: float = entity_memory()
    generation: float = entity_memory()
    generation_set: bool = entity_memory()

    def initialize(self):
        self.end_time = self.start_time + SLOT_EFFECT_DURATION / Options.effect_animation_speed

    def update_sequential(self):
        if self.despawn or self.generation_set:
            return
        self.generation = next_slot_generation(self.sprite, self.group_id)
        self.generation_set = True

    def update_parallel(self):
        if time() > self.end_time or not is_slot_generation_visible(self.sprite, self.generation):
            self.despawn = True
            return
        draw_slot_effects_in_range(
            self.sprite,
            self.start_time,
            self.end_time,
            self.left,
            self.right,
            self.shift,
            y_offset=self.y_offset,
            transform=self.transform,
        )


SLOT_EFFECT_ARCHETYPES = (
    SlotGlowEffect,
    SlotEffect,
)
