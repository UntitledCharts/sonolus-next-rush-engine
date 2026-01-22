from sonolus.script.archetype import PlayArchetype, entity_memory
from sonolus.script.runtime import time
from sonolus.script.sprite import Sprite

from sekai.lib import archetype_names
from sekai.lib.options import Options
from sekai.lib.slot_effect import (
    SLOT_EFFECT_DURATION,
    SLOT_GLOW_EFFECT_DURATION,
    draw_slot_effect,
    draw_slot_glow_effect,
)


class SlotGlowEffect(PlayArchetype):
    name = archetype_names.SLOT_GLOW_EFFECT

    sprite: Sprite = entity_memory()
    start_time: float = entity_memory()
    lane: float = entity_memory()
    size: float = entity_memory()
    y_offset: float = entity_memory()
    end_time: float = entity_memory()

    def initialize(self):
        self.end_time = self.start_time + SLOT_GLOW_EFFECT_DURATION / Options.effect_animation_speed

    def update_parallel(self):
        if time() > self.end_time:
            self.despawn = True
            return
        draw_slot_glow_effect(
            self.sprite,
            self.start_time,
            self.end_time,
            self.lane,
            0.5,
            y_offset=self.y_offset,
        )


class SlotEffect(PlayArchetype):
    name = archetype_names.SLOT_EFFECT

    sprite: Sprite = entity_memory()
    start_time: float = entity_memory()
    lane: float = entity_memory()
    y_offset: float = entity_memory()
    end_time: float = entity_memory()

    def initialize(self):
        self.end_time = self.start_time + SLOT_EFFECT_DURATION / Options.effect_animation_speed

    def update_parallel(self):
        if time() > self.end_time:
            self.despawn = True
            return
        draw_slot_effect(
            self.sprite,
            self.start_time,
            self.end_time,
            self.lane,
            y_offset=self.y_offset,
        )


SLOT_EFFECT_ARCHETYPES = (
    SlotGlowEffect,
    SlotEffect,
)
