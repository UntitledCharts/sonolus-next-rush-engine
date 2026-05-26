from enum import IntEnum
from math import ceil, cos, pi, sin
from typing import Literal, assert_never

from sonolus.script.archetype import EntityRef
from sonolus.script.effect import Effect, LoopedEffectHandle
from sonolus.script.interval import clamp, lerp, remap_clamped, unlerp_clamped
from sonolus.script.particle import Particle, ParticleHandle
from sonolus.script.quad import Quad, QuadLike
from sonolus.script.record import Record
from sonolus.script.runtime import time
from sonolus.script.sprite import Sprite
from sonolus.script.timing import beat_to_time

from sekai.lib.ease import EaseType, ease
from sekai.lib.effect import Effects
from sekai.lib.layer import (
    LAYER_ACTIVE_SLIDE_CONNECTOR_BOTTOM,
    LAYER_ACTIVE_SLIDE_CONNECTOR_OVER,
    LAYER_ACTIVE_SLIDE_CONNECTOR_TOP,
    LAYER_ACTIVE_SLIDE_CONNECTOR_UNDER,
    LAYER_GUIDE_CONNECTOR_BOTTOM,
    LAYER_GUIDE_CONNECTOR_OVER,
    LAYER_GUIDE_CONNECTOR_TOP,
    LAYER_GUIDE_CONNECTOR_UNDER,
    LAYER_SLOT_GLOW_EFFECT,
    get_z,
)
from sekai.lib.layout import (
    DynamicLayout,
    approach,
    get_alpha,
    iter_slot_lanes,
    layout_circular_effect,
    layout_linear_effect,
    layout_slide_connector_segment,
    layout_slot_glow_effect,
    pre_rotation_vec_at,
)
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import Options, Version
from sekai.lib.particle import ActiveParticles
from sekai.lib.skin import ActiveConnectorSpriteSet, ActiveSkin
from sekai.lib.timescale import iter_timescale_changes_in_group_from_time

CONNECTOR_TRAIL_SPAWN_PERIOD = 0.1
CONNECTOR_SLOT_SPAWN_PERIOD = 0.2
CONNECTOR_THROUGH_JUDGE_LINE_DESPAWN_DELAY = 5.0
CONNECTOR_LENIENCY = 1


class ConnectorKind(IntEnum):
    NONE = 0

    ACTIVE_NORMAL = 1
    ACTIVE_CRITICAL = 2
    ACTIVE_FAKE_NORMAL = 51
    ACTIVE_FAKE_CRITICAL = 52

    GUIDE_NEUTRAL = 101
    GUIDE_RED = 102
    GUIDE_GREEN = 103
    GUIDE_BLUE = 104
    GUIDE_YELLOW = 105
    GUIDE_PURPLE = 106
    GUIDE_CYAN = 107
    GUIDE_BLACK = 108


class ConnectorLayer(IntEnum):
    TOP = 0
    BOTTOM = 1
    UNDER = 2
    OVER = 3


ActiveConnectorKind = Literal[
    ConnectorKind.ACTIVE_NORMAL,
    ConnectorKind.ACTIVE_CRITICAL,
    ConnectorKind.ACTIVE_FAKE_NORMAL,
    ConnectorKind.ACTIVE_FAKE_CRITICAL,
]

GuideConnectorKind = Literal[
    ConnectorKind.GUIDE_NEUTRAL,
    ConnectorKind.GUIDE_RED,
    ConnectorKind.GUIDE_GREEN,
    ConnectorKind.GUIDE_BLUE,
    ConnectorKind.GUIDE_YELLOW,
    ConnectorKind.GUIDE_PURPLE,
    ConnectorKind.GUIDE_CYAN,
    ConnectorKind.GUIDE_BLACK,
]


class ConnectorVisualState(IntEnum):
    WAITING = 0
    INACTIVE = 1
    ACTIVE = 2


def get_active_connector_sprites(kind: ActiveConnectorKind) -> ActiveConnectorSpriteSet:
    result = +ActiveConnectorSpriteSet
    match kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_FAKE_NORMAL:
            result @= ActiveSkin.active_slide_connector
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
            result @= ActiveSkin.critical_active_slide_connector
        case _:
            assert_never(kind)
    return result


def get_guide_connector_sprite(kind: GuideConnectorKind) -> Sprite:
    result = +Sprite
    match kind:
        case ConnectorKind.GUIDE_NEUTRAL:
            result @= ActiveSkin.guide_neutral
        case ConnectorKind.GUIDE_RED:
            result @= ActiveSkin.guide_red
        case ConnectorKind.GUIDE_GREEN:
            result @= ActiveSkin.guide_green
        case ConnectorKind.GUIDE_BLUE:
            result @= ActiveSkin.guide_blue
        case ConnectorKind.GUIDE_YELLOW:
            result @= ActiveSkin.guide_yellow
        case ConnectorKind.GUIDE_PURPLE:
            result @= ActiveSkin.guide_purple
        case ConnectorKind.GUIDE_CYAN:
            result @= ActiveSkin.guide_cyan
        case ConnectorKind.GUIDE_BLACK:
            result @= ActiveSkin.guide_black
        case _:
            assert_never(kind)
    return result


def get_connector_z(kind: ConnectorKind, target_time: float, lane: float, active: bool, layer: ConnectorLayer) -> float:
    match kind:
        case (
            ConnectorKind.ACTIVE_NORMAL
            | ConnectorKind.ACTIVE_FAKE_NORMAL
            | ConnectorKind.ACTIVE_CRITICAL
            | ConnectorKind.ACTIVE_FAKE_CRITICAL
        ):
            match layer:
                case ConnectorLayer.TOP:
                    return get_z(
                        LAYER_ACTIVE_SLIDE_CONNECTOR_TOP,
                        time=target_time,
                        lane=lane,
                        etc=get_active_connector_z_offset(kind, active),
                        invert_time=True,
                    )
                case ConnectorLayer.BOTTOM:
                    return get_z(
                        LAYER_ACTIVE_SLIDE_CONNECTOR_BOTTOM,
                        time=target_time,
                        lane=lane,
                        etc=get_active_connector_z_offset(kind, active),
                        invert_time=True,
                    )
                case ConnectorLayer.UNDER:
                    return get_z(
                        LAYER_ACTIVE_SLIDE_CONNECTOR_UNDER,
                        time=target_time,
                        lane=lane,
                        etc=get_active_connector_z_offset(kind, active),
                        invert_time=True,
                    )
                case ConnectorLayer.OVER:
                    return get_z(
                        LAYER_ACTIVE_SLIDE_CONNECTOR_OVER,
                        time=target_time,
                        lane=lane,
                        etc=get_active_connector_z_offset(kind, active),
                        invert_time=True,
                    )
                case _:
                    assert_never(layer)
        case (
            ConnectorKind.GUIDE_NEUTRAL
            | ConnectorKind.GUIDE_RED
            | ConnectorKind.GUIDE_GREEN
            | ConnectorKind.GUIDE_BLUE
            | ConnectorKind.GUIDE_YELLOW
            | ConnectorKind.GUIDE_PURPLE
            | ConnectorKind.GUIDE_CYAN
            | ConnectorKind.GUIDE_BLACK
        ):
            match layer:
                case ConnectorLayer.TOP:
                    return get_z(
                        LAYER_GUIDE_CONNECTOR_TOP,
                        time=target_time,
                        lane=lane,
                        etc=kind - ConnectorKind.GUIDE_NEUTRAL,
                        invert_time=True,
                    )
                case ConnectorLayer.BOTTOM:
                    return get_z(
                        LAYER_GUIDE_CONNECTOR_BOTTOM,
                        time=target_time,
                        lane=lane,
                        etc=kind - ConnectorKind.GUIDE_NEUTRAL,
                        invert_time=True,
                    )
                case ConnectorLayer.UNDER:
                    return get_z(
                        LAYER_GUIDE_CONNECTOR_UNDER,
                        time=target_time,
                        lane=lane,
                        etc=kind - ConnectorKind.GUIDE_NEUTRAL,
                        invert_time=True,
                    )
                case ConnectorLayer.OVER:
                    return get_z(
                        LAYER_GUIDE_CONNECTOR_OVER,
                        time=target_time,
                        lane=lane,
                        etc=kind - ConnectorKind.GUIDE_NEUTRAL,
                        invert_time=True,
                    )
                case _:
                    assert_never(layer)
        case ConnectorKind.NONE:
            return 0.0
        case _:
            assert_never(kind)


def get_active_connector_z_offset(kind: ActiveConnectorKind, active: bool) -> int:
    match kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_FAKE_NORMAL:
            return 3 - active
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
            return 1 - active
        case _:
            assert_never(kind)


def get_connector_alpha_option(kind: ConnectorKind) -> float:
    match kind:
        case (
            ConnectorKind.ACTIVE_NORMAL
            | ConnectorKind.ACTIVE_FAKE_NORMAL
            | ConnectorKind.ACTIVE_CRITICAL
            | ConnectorKind.ACTIVE_FAKE_CRITICAL
        ):
            return Options.slide_alpha
        case (
            ConnectorKind.GUIDE_NEUTRAL
            | ConnectorKind.GUIDE_RED
            | ConnectorKind.GUIDE_GREEN
            | ConnectorKind.GUIDE_BLUE
            | ConnectorKind.GUIDE_YELLOW
            | ConnectorKind.GUIDE_PURPLE
            | ConnectorKind.GUIDE_CYAN
            | ConnectorKind.GUIDE_BLACK
        ):
            return Options.guide_alpha
        case ConnectorKind.NONE:
            return 0.0
        case _:
            assert_never(kind)


def get_connector_quality_option(kind: ConnectorKind) -> float:
    match kind:
        case (
            ConnectorKind.ACTIVE_NORMAL
            | ConnectorKind.ACTIVE_FAKE_NORMAL
            | ConnectorKind.ACTIVE_CRITICAL
            | ConnectorKind.ACTIVE_FAKE_CRITICAL
        ):
            return Options.slide_quality
        case (
            ConnectorKind.GUIDE_NEUTRAL
            | ConnectorKind.GUIDE_RED
            | ConnectorKind.GUIDE_GREEN
            | ConnectorKind.GUIDE_BLUE
            | ConnectorKind.GUIDE_YELLOW
            | ConnectorKind.GUIDE_PURPLE
            | ConnectorKind.GUIDE_CYAN
            | ConnectorKind.GUIDE_BLACK
        ):
            return Options.guide_quality
        case ConnectorKind.NONE:
            return 0
        case _:
            assert_never(kind)


def draw_connector(
    kind: ConnectorKind,
    visual_state: ConnectorVisualState,
    ease_type: EaseType,
    head_lane: float,
    head_size: float,
    head_visual_progress: float,
    head_target_time: float,
    head_ease_frac: float,
    tail_lane: float,
    tail_size: float,
    tail_visual_progress: float,
    tail_target_time: float,
    tail_ease_frac: float,
    segment_head_target_time: float,
    segment_head_lane: float,
    segment_head_alpha: float,
    segment_tail_target_time: float,
    segment_tail_alpha: float,
    layer: ConnectorLayer,
    bypass_tail_target_time_check: bool = False,
):
    if (
        (head_visual_progress < DynamicLayout.progress_start and tail_visual_progress < DynamicLayout.progress_start)
        or (
            head_visual_progress > DynamicLayout.progress_cutoff
            and tail_visual_progress > DynamicLayout.progress_cutoff
        )
        or head_visual_progress == tail_visual_progress
    ):
        return

    if Options.disable_fake_notes and kind in {
        ConnectorKind.ACTIVE_FAKE_NORMAL,
        ConnectorKind.ACTIVE_FAKE_CRITICAL,
    }:
        return

    if ease_type == EaseType.NONE:
        tail_lane = head_lane
        tail_size = head_size

    normal_sprite = Sprite(-1)
    active_sprite = Sprite(-1)
    match kind:
        case (
            ConnectorKind.ACTIVE_NORMAL
            | ConnectorKind.ACTIVE_CRITICAL
            | ConnectorKind.ACTIVE_FAKE_NORMAL
            | ConnectorKind.ACTIVE_FAKE_CRITICAL
        ):
            sprites = get_active_connector_sprites(kind)
            normal_sprite @= sprites.connection.normal
            active_sprite @= sprites.connection.active
        case (
            ConnectorKind.GUIDE_NEUTRAL
            | ConnectorKind.GUIDE_RED
            | ConnectorKind.GUIDE_GREEN
            | ConnectorKind.GUIDE_BLUE
            | ConnectorKind.GUIDE_YELLOW
            | ConnectorKind.GUIDE_PURPLE
            | ConnectorKind.GUIDE_CYAN
            | ConnectorKind.GUIDE_BLACK
        ):
            sprites = get_guide_connector_sprite(kind)
            normal_sprite @= sprites
        case ConnectorKind.NONE:
            return
        case _:
            assert_never(kind)

    match kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_CRITICAL:
            segment_head_alpha = 1.0
            segment_tail_alpha = 1.0
        case ConnectorKind.ACTIVE_FAKE_NORMAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
            segment_head_alpha = 1.0
            segment_tail_alpha = 1.0
            if visual_state == ConnectorVisualState.INACTIVE:
                visual_state = ConnectorVisualState.ACTIVE
        case (
            ConnectorKind.GUIDE_NEUTRAL
            | ConnectorKind.GUIDE_RED
            | ConnectorKind.GUIDE_GREEN
            | ConnectorKind.GUIDE_BLUE
            | ConnectorKind.GUIDE_YELLOW
            | ConnectorKind.GUIDE_PURPLE
            | ConnectorKind.GUIDE_CYAN
            | ConnectorKind.GUIDE_BLACK
        ):
            visual_state = ConnectorVisualState.WAITING
        case _:
            assert_never(kind)

    head_alpha = remap_clamped(
        segment_head_target_time, segment_tail_target_time, segment_head_alpha, segment_tail_alpha, head_target_time
    )
    tail_alpha = remap_clamped(
        segment_head_target_time, segment_tail_target_time, segment_head_alpha, segment_tail_alpha, tail_target_time
    )

    if time() >= tail_target_time and not bypass_tail_target_time_check:
        return
    start_visual_progress = clamp(head_visual_progress, DynamicLayout.progress_start, DynamicLayout.progress_cutoff)
    end_visual_progress = clamp(tail_visual_progress, DynamicLayout.progress_start, DynamicLayout.progress_cutoff)
    start_frac = unlerp_clamped(head_visual_progress, tail_visual_progress, start_visual_progress)
    end_frac = unlerp_clamped(head_visual_progress, tail_visual_progress, end_visual_progress)
    start_ease_frac = lerp(head_ease_frac, tail_ease_frac, start_frac)
    end_ease_frac = lerp(head_ease_frac, tail_ease_frac, end_frac)
    eased_head_ease_frac = ease(ease_type, head_ease_frac)
    eased_tail_ease_frac = ease(ease_type, tail_ease_frac)
    start_interp_frac = unlerp_clamped(eased_head_ease_frac, eased_tail_ease_frac, ease(ease_type, start_ease_frac))
    end_interp_frac = unlerp_clamped(eased_head_ease_frac, eased_tail_ease_frac, ease(ease_type, end_ease_frac))
    start_travel = approach(start_visual_progress)
    end_travel = approach(end_visual_progress)
    start_lane = lerp(head_lane, tail_lane, start_interp_frac)
    end_lane = lerp(head_lane, tail_lane, end_interp_frac)
    start_size = max(1e-3, lerp(head_size, tail_size, start_interp_frac))  # Lightweight rendering needs >0 size.
    end_size = max(1e-3, lerp(head_size, tail_size, end_interp_frac))  # Lightweight rendering needs >0 size.
    start_alpha = lerp(head_alpha, tail_alpha, start_frac)
    end_alpha = lerp(head_alpha, tail_alpha, end_frac)
    start_pos_y = pre_rotation_vec_at(start_lane, start_travel).y
    end_pos_y = pre_rotation_vec_at(end_lane, end_travel).y

    delta_alpha = abs(start_alpha - end_alpha) * get_connector_alpha_option(kind)
    scale = delta_alpha * max(1.0, abs(start_pos_y - end_pos_y)) * 3 if delta_alpha else 0.0
    match ease_type:
        case EaseType.NONE:
            pass
        case _:
            left_start_lane = start_lane - start_size
            left_end_lane = end_lane - end_size
            right_start_lane = start_lane + start_size
            right_end_lane = end_lane + end_size
            if abs(start_size - end_size) < 0.1:
                ref_start_lane = start_lane
                ref_end_lane = end_lane
                ref_head_lane = head_lane
                ref_tail_lane = tail_lane
            elif abs(left_start_lane - left_end_lane) > abs(right_start_lane - right_end_lane):
                ref_start_lane = left_start_lane
                ref_end_lane = left_end_lane
                ref_head_lane = head_lane - head_size
                ref_tail_lane = tail_lane - tail_size
            else:
                ref_start_lane = right_start_lane
                ref_end_lane = right_end_lane
                ref_head_lane = head_lane + head_size
                ref_tail_lane = tail_lane + tail_size
            if ref_head_lane != ref_tail_lane:
                start_ref = pre_rotation_vec_at(ref_start_lane, start_travel)
                end_ref = pre_rotation_vec_at(ref_end_lane, end_travel)
                max_offset = 0.0
                for r in (0.25, 0.5, 0.75):
                    ease_frac = lerp(start_ease_frac, end_ease_frac, r)
                    interp_frac = unlerp_clamped(eased_head_ease_frac, eased_tail_ease_frac, ease(ease_type, ease_frac))
                    visual_progress = lerp(start_visual_progress, end_visual_progress, r)
                    travel = approach(visual_progress)
                    lane = lerp(ref_head_lane, ref_tail_lane, interp_frac)
                    pos = pre_rotation_vec_at(lane, travel)
                    ref_pos = lerp(start_ref, end_ref, unlerp_clamped(start_travel, end_travel, travel))
                    max_offset = max(max_offset, abs(pos.x - ref_pos.x))
                scale = max(scale, max_offset**0.5 * 2.5)
    quality = get_connector_quality_option(kind)
    segment_count = max(1, ceil(scale * quality * 10))
    z_normal = get_connector_z(kind, segment_head_target_time, segment_head_lane, active=False, layer=layer)
    if visual_state == ConnectorVisualState.ACTIVE and active_sprite.is_available:
        z_active = get_connector_z(kind, segment_head_target_time, segment_head_lane, active=True, layer=layer)
    else:
        z_active = z_normal

    last_travel = start_travel
    last_lane = start_lane
    last_size = start_size
    last_alpha = start_alpha
    last_target_time = lerp(head_target_time, tail_target_time, start_frac)

    anim_factor1, anim_factor2 = (1, 1)
    if visual_state == ConnectorVisualState.ACTIVE and active_sprite.is_available and Options.connector_animation:
        anim_factor1, anim_factor2 = get_cross_fate_opacities(1.0, time() - segment_head_target_time, 0.5)

    for i in range(1, segment_count + 1):
        segment_frac = i / segment_count
        next_frac = lerp(start_frac, end_frac, segment_frac)
        next_ease_frac = lerp(start_ease_frac, end_ease_frac, segment_frac)
        next_interp_frac = unlerp_clamped(eased_head_ease_frac, eased_tail_ease_frac, ease(ease_type, next_ease_frac))
        next_visual_progress = lerp(start_visual_progress, end_visual_progress, segment_frac)
        next_travel = approach(next_visual_progress)
        next_lane = lerp(head_lane, tail_lane, next_interp_frac)
        next_size = max(1e-3, lerp(head_size, tail_size, next_interp_frac))
        next_alpha = lerp(head_alpha, tail_alpha, next_frac)
        next_target_time = lerp(head_target_time, tail_target_time, next_frac)

        base_a = clamp(
            get_alpha((last_target_time + next_target_time) / 2)
            * (last_alpha + next_alpha)
            / 2
            * get_connector_alpha_option(kind),
            0,
            1,
        )

        layout = layout_slide_connector_segment(
            start_lane=last_lane,
            start_size=last_size,
            start_travel=last_travel,
            end_lane=next_lane,
            end_size=next_size,
            end_travel=next_travel,
        )

        if visual_state == ConnectorVisualState.ACTIVE and active_sprite.is_available:
            if Options.connector_animation:
                normal_sprite.draw(layout, z=z_normal, a=base_a * anim_factor1)
                active_sprite.draw(layout, z=z_active, a=base_a * anim_factor2)
            else:
                normal_sprite.draw(layout, z=z_normal, a=base_a)
        else:
            normal_sprite.draw(
                layout, z=z_normal, a=base_a * (1 if visual_state != ConnectorVisualState.INACTIVE else 0.5)
            )

        last_travel = next_travel
        last_lane = next_lane
        last_size = next_size
        last_alpha = next_alpha
        last_target_time = next_target_time


def get_cross_fate_opacities(a, t, period):
    phase = (t % period) / period
    opacity2_base = 1 - abs(1 - 2 * phase)
    opacity1_base = 1 - opacity2_base
    correction = 0.6
    opacity1 = a * (opacity1_base + correction * opacity1_base * opacity2_base)
    opacity2 = a * (opacity2_base + correction * opacity1_base * opacity2_base)

    return opacity1, opacity2


class ActiveConnectorInfo(Record):
    visual_lane: float
    visual_size: float
    visual_y_offset: float
    input_bounds: Quad
    is_active: bool
    active_start_time: float
    connector_kind: ConnectorKind


def update_circular_connector_particle(
    handle: ParticleHandle,
    kind: ActiveConnectorKind,
    lane: float,
    replace: bool,
    y_offset: float = 0.0,
):
    if not Options.note_effect_enabled:
        return
    layout = layout_circular_effect(lane, w=3.5, h=2.1, y_offset=y_offset)
    if replace or handle.id == 0:
        particle = +Particle(-1)
        match kind:
            case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_FAKE_NORMAL:
                particle @= ActiveParticles.normal_slide_connector.circular
            case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
                particle @= ActiveParticles.critical_slide_connector.circular
            case _:
                assert_never(kind)
        replace_looped_particle(handle, particle, layout, duration=1 / Options.effect_animation_speed)
    else:
        update_looped_particle(handle, layout)


def update_linear_connector_particle(
    handle: ParticleHandle,
    kind: ActiveConnectorKind,
    lane: float,
    replace: bool,
    y_offset: float = 0.0,
):
    if not Options.note_effect_enabled:
        return
    layout = layout_linear_effect(lane, shear=0, y_offset=y_offset)
    particle = +Particle
    if replace or handle.id == 0:
        match kind:
            case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_FAKE_NORMAL:
                particle @= ActiveParticles.normal_slide_connector.linear
            case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
                particle @= ActiveParticles.critical_slide_connector.linear
            case _:
                assert_never(kind)
        replace_looped_particle(handle, particle, layout, duration=1 / Options.effect_animation_speed)
    else:
        update_looped_particle(handle, layout)


def spawn_linear_connector_trail_particle(
    kind: ActiveConnectorKind,
    lane: float,
    y_offset: float = 0.0,
):
    if not Options.note_effect_enabled:
        return
    layout = layout_linear_effect(lane, shear=0, y_offset=y_offset)
    particle = +Particle
    match kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_FAKE_NORMAL:
            particle @= ActiveParticles.normal_slide_connector.trail_linear
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
            particle @= ActiveParticles.critical_slide_connector.trail_linear
        case _:
            assert_never(kind)
    particle.spawn(layout, duration=0.5 / Options.effect_animation_speed)


def spawn_connector_slot_particles(
    kind: ActiveConnectorKind,
    lane: float,
    size: float,
    y_offset: float = 0.0,
):
    if not Options.note_effect_enabled:
        return
    particle = +Particle
    match kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_FAKE_NORMAL:
            particle @= ActiveParticles.normal_slide_connector.slot_linear
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
            particle @= ActiveParticles.critical_slide_connector.slot_linear
        case _:
            assert_never(kind)
    for slot_lane in iter_slot_lanes(lane, size):
        layout = layout_linear_effect(slot_lane, shear=0, y_offset=y_offset)
        particle.spawn(layout, duration=0.5 / Options.effect_animation_speed)


def draw_connector_slot_glow_effect(
    kind: ActiveConnectorKind,
    start_time: float,
    lane: float,
    size: float,
    y_offset: float = 0.0,
):
    if not Options.slot_effect_enabled:
        return
    sprite = +Sprite
    match kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_FAKE_NORMAL:
            sprite @= ActiveSkin.active_slide_connector.slot_glow
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
            sprite @= ActiveSkin.critical_active_slide_connector.slot_glow
        case _:
            assert_never(kind)
    height = (
        0.85 + (1.2 - 0.85) * ((cos((time() - start_time) * 8 * pi) + 1) / 2)  # min + (max - min) * osc
        if LevelConfig.ui_version == Version.v3
        else 0.2 + (1.2 - 0.2) * ((sin((time() - start_time) * 2.5 * pi) + 1) / 2)
    )
    ex = 0.035 * abs(2 * size) + 0.08 if LevelConfig.ui_version == Version.v3 else 0
    layout = layout_slot_glow_effect(lane, size + ex, height, y_offset=y_offset)
    z = get_z(LAYER_SLOT_GLOW_EFFECT, start_time, lane, invert_time=True)
    a = remap_clamped(start_time, start_time + 0.25, 0.0, 0.25, time())
    lightweight = 0.25 if ActiveParticles.lightweight.is_available else 1
    sprite.draw(layout, z=z, a=a * lightweight)


def update_connector_sfx(
    handle: LoopedEffectHandle,
    kind: ActiveConnectorKind,
    replace: bool,
):
    if not Options.sfx_enabled:
        return
    if Options.auto_sfx:
        return
    effect = +Effect
    match kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_FAKE_NORMAL:
            effect @= Effects.normal_hold
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
            effect @= Effects.critical_hold
        case _:
            assert_never(kind)
    if replace:
        replace_looped_sfx(handle, effect)
    elif handle.id == 0:
        handle @= effect.loop()


def schedule_connector_sfx(
    kind: ActiveConnectorKind,
    timescale_group: int | EntityRef,
    start_time: float,
    end_time: float,
):
    if not Options.sfx_enabled:
        return
    effect = +Effect
    match kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_FAKE_NORMAL:
            effect @= Effects.normal_hold
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
            effect @= Effects.critical_hold
        case _:
            assert_never(kind)
    last_start_time = start_time
    hide = False
    for group in iter_timescale_changes_in_group_from_time(timescale_group, start_time):
        group_time = beat_to_time(group.beat)
        if group_time <= start_time:
            hide = group.hide_notes
            continue
        if group_time >= end_time:
            break
        if hide and not group.hide_notes:
            last_start_time = group_time
        elif not hide and group.hide_notes and group_time > last_start_time:
            schedule_looped_sfx(effect, last_start_time, group_time)
        hide = group.hide_notes
    if not hide and end_time > last_start_time:
        schedule_looped_sfx(effect, last_start_time, end_time)


def replace_looped_particle(handle: ParticleHandle, particle: Particle, layout: QuadLike, duration: float):
    if handle.id != 0:
        handle.destroy()
    handle @= particle.spawn(layout, duration / Options.effect_animation_speed, loop=True)


def update_looped_particle(handle: ParticleHandle, layout: QuadLike):
    if handle.id != 0:
        handle.move(layout)


def destroy_looped_particle(handle: ParticleHandle):
    if handle.id != 0:
        handle.destroy()
        handle.id = 0


def replace_looped_sfx(handle: LoopedEffectHandle, effect: Effect):
    if handle.id != 0:
        handle.stop()
    handle @= effect.loop()


def destroy_looped_sfx(handle: LoopedEffectHandle):
    if handle.id != 0:
        handle.stop()
        handle.id = 0


def schedule_looped_sfx(effect: Effect, start_time: float, end_time: float):
    effect.schedule_loop(start_time).stop(end_time)
