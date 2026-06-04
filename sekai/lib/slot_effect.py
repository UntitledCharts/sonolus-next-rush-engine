from sonolus.script.array import Dim
from sonolus.script.containers import ArrayMap
from sonolus.script.globals import level_memory
from sonolus.script.interval import lerp, unlerp_clamped
from sonolus.script.runtime import time
from sonolus.script.sprite import Sprite

from sekai.lib.layer import LAYER_SLOT_EFFECT, LAYER_SLOT_GLOW_EFFECT, get_z
from sekai.lib.layout import layout_slot_effect, layout_slot_glow_effect
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import Version
from sekai.lib.particle import ActiveParticles

SLOT_GLOW_EFFECT_DURATION = 0.25
SLOT_EFFECT_DURATION = 0.5

SLOT_EFFECT_LIMIT = 6.0


@level_memory
class SlotEffectHandler:
    generations: ArrayMap[float, float, Dim[256]]
    last_group: ArrayMap[float, float, Dim[256]]


def clear_slot_effects():
    SlotEffectHandler.generations.clear()
    SlotEffectHandler.last_group.clear()


def next_slot_generation(sprite: Sprite, group_id: float) -> float:
    sprite_id = sprite.id
    if sprite_id in SlotEffectHandler.last_group and SlotEffectHandler.last_group[sprite_id] == group_id:
        return SlotEffectHandler.generations[sprite_id]
    if sprite_id in SlotEffectHandler.generations:
        generation = SlotEffectHandler.generations[sprite_id] + 1
    else:
        generation = 0.0
    SlotEffectHandler.generations[sprite_id] = generation
    SlotEffectHandler.last_group[sprite_id] = group_id
    return generation


def is_slot_generation_visible(sprite: Sprite, generation: float) -> bool:
    sprite_id = sprite.id
    if sprite_id not in SlotEffectHandler.generations:
        return True
    return SlotEffectHandler.generations[sprite_id] - generation < SLOT_EFFECT_LIMIT


def draw_slot_glow_effect(
    sprite: Sprite,
    start_time: float,
    end_time: float,
    lane: float,
    size: float,
    y_offset: float = 0.0,
):
    progress = unlerp_clamped(start_time, end_time, time())
    height = unlerp_clamped(1, 0.8, progress) if LevelConfig.ui_version == Version.v3 else 1 - lerp(1, 0, progress) ** 3
    layout = layout_slot_glow_effect(lane, size, height, y_offset=y_offset)
    z = get_z(LAYER_SLOT_GLOW_EFFECT, start_time, lane)
    a = lerp(1, 0, progress)
    lightweight = 0.25 if ActiveParticles.lightweight.is_available else 1
    sprite.draw(layout, z=z, a=a * lightweight)


def draw_slot_effect(
    sprite: Sprite,
    start_time: float,
    end_time: float,
    lane: float,
    y_offset: float = 0.0,
):
    progress = unlerp_clamped(start_time, end_time, time())
    layout = layout_slot_effect(lane, y_offset=y_offset)
    z = get_z(LAYER_SLOT_EFFECT, start_time, lane, invert_time=True)
    a = lerp(1, 0, progress)
    lightweight = 0.25 if ActiveParticles.lightweight.is_available else 1
    sprite.draw(layout, z=z, a=a * lightweight)
