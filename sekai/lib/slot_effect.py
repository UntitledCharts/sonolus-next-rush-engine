from sonolus.script.interval import lerp, unlerp_clamped
from sonolus.script.runtime import time
from sonolus.script.sprite import Sprite

from sekai.lib.layer import LAYER_SLOT_EFFECT, LAYER_SLOT_GLOW_EFFECT, get_z
from sekai.lib.layout import layout_slot_effect, layout_slot_glow_effect
from sekai.lib.options import Options

SLOT_GLOW_EFFECT_DURATION = 0.25
SLOT_EFFECT_DURATION = 0.5


def draw_slot_glow_effect(
    sprite: Sprite,
    start_time: float,
    end_time: float,
    lane: float,
    size: float,
    y_offset: float = 0.0,
):
    progress = unlerp_clamped(start_time, end_time, time())
    height = unlerp_clamped(1, 0.8, progress) if Options.version == 0 else 1 - lerp(1, 0, progress) ** 3
    layout = layout_slot_glow_effect(lane, size, height, y_offset=y_offset)
    z = get_z(LAYER_SLOT_GLOW_EFFECT, start_time, lane)
    a = lerp(1, 0, progress)
    sprite.draw(layout, z=z, a=a)


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
    sprite.draw(layout, z=z, a=a)
