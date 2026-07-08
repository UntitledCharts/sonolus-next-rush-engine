from math import ceil, floor

from sonolus.script.array import Dim
from sonolus.script.containers import ArrayMap, Pair
from sonolus.script.globals import level_memory
from sonolus.script.interval import lerp, unlerp_clamped
from sonolus.script.runtime import time
from sonolus.script.sprite import Sprite

from sekai.lib.layer import LAYER_SLOT_EFFECT, LAYER_SLOT_GLOW_EFFECT, get_z
from sekai.lib.layout import (
    AffineTransform2d,
    DynamicLayout,
    approach,
    layout_slot_effect,
    layout_slot_glow_effect,
    tilt_depth,
    visible_lane_range_at,
)
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import Options, Version
from sekai.lib.particle import ActiveParticles

SLOT_GLOW_EFFECT_DURATION = 0.25
SLOT_EFFECT_DURATION = 0.5

SLOT_EFFECT_LIMIT = 6.0


@level_memory
class SlotEffectHandler:
    slots: ArrayMap[float, Pair[float, float], Dim[256]]


def clear_slot_effects():
    SlotEffectHandler.slots.clear()


def next_slot_generation(sprite: Sprite, group_id: float) -> float:
    sprite_id = sprite.id
    if sprite_id in SlotEffectHandler.slots:
        entry = SlotEffectHandler.slots[sprite_id]
        if entry.second == group_id:
            return entry.first
        generation = entry.first + 1
    else:
        generation = 0.0
    SlotEffectHandler.slots[sprite_id] = Pair(generation, group_id)
    return generation


def is_slot_generation_visible(sprite: Sprite, generation: float) -> bool:
    sprite_id = sprite.id
    if sprite_id not in SlotEffectHandler.slots:
        return True
    return SlotEffectHandler.slots[sprite_id].first - generation < SLOT_EFFECT_LIMIT


def slot_glow_progress_height(progress: float) -> float:
    return unlerp_clamped(1, 0.8, progress) if LevelConfig.ui_version == Version.v3 else 1 - lerp(1, 0, progress) ** 3


def draw_slot_glow_effect(
    sprite: Sprite,
    start_time: float,
    end_time: float,
    lane: float,
    size: float,
    y_offset: float = 0.0,
    *,
    transform: AffineTransform2d,
):
    progress = unlerp_clamped(start_time, end_time, time())
    height = slot_glow_progress_height(progress)
    layout = transform.transform_quad(layout_slot_glow_effect(lane, size, height, y_offset=y_offset))
    z = get_z(LAYER_SLOT_GLOW_EFFECT, start_time, lane, invert_time=True)
    a = lerp(1, 0, progress)
    lightweight = 0.25 if ActiveParticles.lightweight.is_available else 1
    sprite.draw(layout, z=z, a=a * lightweight)


def draw_slot_effect(
    sprite: Sprite,
    start_time: float,
    end_time: float,
    lane: float,
    y_offset: float = 0.0,
    *,
    transform: AffineTransform2d,
):
    progress = unlerp_clamped(start_time, end_time, time())
    layout = transform.transform_quad(layout_slot_effect(lane, y_offset=y_offset))
    z = get_z(LAYER_SLOT_EFFECT, start_time, lane, invert_time=True)
    a = lerp(1, 0, progress)
    lightweight = 0.25 if ActiveParticles.lightweight.is_available else 1
    sprite.draw(layout, z=z, a=a * lightweight)


def draw_slot_effects_in_range(
    sprite: Sprite,
    start_time: float,
    end_time: float,
    left: int,
    right: int,
    shift: float,
    y_offset: float = 0.0,
    *,
    transform: AffineTransform2d,
):
    """Draw slot effects at lanes i + 0.5 + shift for i in [left, right), skipping off-screen slots."""
    progress = unlerp_clamped(start_time, end_time, time())
    a = lerp(1, 0, progress)
    lightweight = 0.25 if ActiveParticles.lightweight.is_available else 1
    travel = approach(1 - y_offset)
    nh = DynamicLayout.note_h
    lo_b, hi_b = visible_lane_range_at(tilt_depth(1 + nh, travel), transform)
    lo_t, hi_t = visible_lane_range_at(tilt_depth(1 - nh, travel), transform)
    lo = min(lo_b, lo_t)
    hi = max(hi_b, hi_t)
    first = max(left, floor(lo - shift) - 1)
    last = min(right, ceil(hi - shift) + 1)
    for i in range(first, last):
        lane = i + 0.5 + shift
        layout = transform.transform_quad(layout_slot_effect(lane, y_offset=y_offset))
        z = get_z(LAYER_SLOT_EFFECT, start_time, lane, invert_time=True)
        sprite.draw(layout, z=z, a=a * lightweight)


def draw_slot_glow_effects_in_range(
    sprite: Sprite,
    start_time: float,
    end_time: float,
    left: int,
    right: int,
    y_offset: float = 0.0,
    *,
    transform: AffineTransform2d,
):
    """Draw per-lane slot glow effects at lanes i + 0.5 for i in [left, right), skipping off-screen slots."""
    progress = unlerp_clamped(start_time, end_time, time())
    height = slot_glow_progress_height(progress)
    a = lerp(1, 0, progress)
    lightweight = 0.25 if ActiveParticles.lightweight.is_available else 1
    travel = approach(1 - y_offset)
    lo, hi = visible_lane_range_at(travel, transform)
    # The glow top edge spreads outward by the factor s, so widen the range accordingly.
    s = 1 + 0.25 * Options.slot_effect_size
    lo = min(lo, lo / s)
    hi = max(hi, hi / s)
    first = max(left, floor(lo) - 1)
    last = min(right, ceil(hi) + 1)
    for i in range(first, last):
        lane = i + 0.5
        layout = transform.transform_quad(layout_slot_glow_effect(lane, 0.5, height, y_offset=y_offset))
        z = get_z(LAYER_SLOT_GLOW_EFFECT, start_time, lane, invert_time=True)
        sprite.draw(layout, z=z, a=a * lightweight)
