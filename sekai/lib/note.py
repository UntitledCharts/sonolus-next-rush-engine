from collections.abc import Iterable
from enum import IntEnum, auto
from typing import assert_never, cast

from sonolus.script.archetype import EntityRef, HapticType, PlayArchetype, WatchArchetype, get_archetype_by_name
from sonolus.script.bucket import Bucket, Judgment
from sonolus.script.easing import ease_in_cubic
from sonolus.script.effect import Effect
from sonolus.script.interval import Interval, lerp, remap_clamped
from sonolus.script.quad import Quad
from sonolus.script.runtime import is_tutorial, is_watch, level_life, level_score, time
from sonolus.script.sprite import Sprite
from sonolus.script.vec import Vec2

from sekai.lib import archetype_names
from sekai.lib.buckets import (
    EMPTY_JUDGMENT_WINDOW,
    FLICK_CRITICAL_WINDOW,
    FLICK_NORMAL_WINDOW,
    FLICK_NORMAL_WINDOW_BAD,
    SLIDE_END_CRITICAL_WINDOW,
    SLIDE_END_FLICK_CRITICAL_WINDOW,
    SLIDE_END_FLICK_NORMAL_WINDOW,
    SLIDE_END_NORMAL_WINDOW,
    SLIDE_END_TRACE_CRITICAL_WINDOW,
    SLIDE_END_TRACE_NORMAL_WINDOW,
    SLIDE_TICK_JUDGMENT_WINDOW,
    TAP_CRITICAL_WINDOW,
    TAP_CRITICAL_WINDOW_BAD,
    TAP_NORMAL_WINDOW,
    TAP_NORMAL_WINDOW_BAD,
    TRACE_CRITICAL_WINDOW,
    TRACE_FLICK_CRITICAL_WINDOW,
    TRACE_FLICK_NORMAL_WINDOW,
    TRACE_NORMAL_WINDOW,
    Buckets,
    SekaiWindow,
)
from sekai.lib.connector import ActiveConnectorKind, ConnectorKind, get_active_connector_z_offset
from sekai.lib.ease import EaseType, ease
from sekai.lib.effect import EMPTY_EFFECT, SFX_DISTANCE, Effects, first_available_effect
from sekai.lib.layer import (
    LAYER_GUIDE_CONNECTOR_OVER,
    LAYER_NOTE_ARROW,
    LAYER_NOTE_ARROW_CRITICAL,
    LAYER_NOTE_BODY,
    LAYER_NOTE_FLICK_BODY,
    LAYER_NOTE_SLIM_BODY,
    LAYER_NOTE_TICK,
    get_z,
    get_z_alt,
)
from sekai.lib.layout import (
    DynamicLayout,
    FlickDirection,
    Hitbox,
    approach,
    get_alpha,
    iter_slot_lanes,
    layout_circular_effect,
    layout_flick_arrow,
    layout_flick_arrow_fallback,
    layout_lane,
    layout_linear_effect,
    layout_regular_note_body,
    layout_regular_note_body_fallback,
    layout_rotated2_linear_effect,
    layout_slim_note_body,
    layout_slim_note_body_fallback,
    layout_tick,
    layout_tick_effect,
    preempt_time,
    progress_to,
)
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import Options, ScoreMode, Version, VibrateMode
from sekai.lib.particle import (
    EMPTY_NOTE_PARTICLE_SET,
    ActiveParticles,
    BaseParticles,
    NoteParticleSet,
)
from sekai.lib.skin import (
    EMPTY_NOTE_SPRITE_SET,
    ActiveSkin,
    ArrowRenderType,
    ArrowSpriteSet,
    BodyRenderType,
    BodySpriteSet,
    NoteSpriteSet,
)
from sekai.lib.slot_effect import (
    SLOT_EFFECT_DURATION,
    SLOT_GLOW_EFFECT_DURATION,
    draw_slot_effect,
    draw_slot_glow_effect,
)
from sekai.lib.timescale import (
    CompositeTime,
    group_force_note_speed,
    group_scaled_time_to_first_time,
    group_scaled_time_to_first_time_2,
)


class NoteKind(IntEnum):
    NORM_TAP = auto()
    CRIT_TAP = auto()

    NORM_FLICK = auto()
    CRIT_FLICK = auto()

    NORM_TRACE = auto()
    CRIT_TRACE = auto()

    NORM_TRACE_FLICK = auto()
    CRIT_TRACE_FLICK = auto()

    NORM_RELEASE = auto()
    CRIT_RELEASE = auto()

    NORM_HEAD_TAP = auto()
    CRIT_HEAD_TAP = auto()

    NORM_HEAD_FLICK = auto()
    CRIT_HEAD_FLICK = auto()

    NORM_HEAD_TRACE = auto()
    CRIT_HEAD_TRACE = auto()

    NORM_HEAD_TRACE_FLICK = auto()
    CRIT_HEAD_TRACE_FLICK = auto()

    NORM_HEAD_RELEASE = auto()
    CRIT_HEAD_RELEASE = auto()

    NORM_TAIL_TAP = auto()
    CRIT_TAIL_TAP = auto()

    NORM_TAIL_FLICK = auto()
    CRIT_TAIL_FLICK = auto()

    NORM_TAIL_TRACE = auto()
    CRIT_TAIL_TRACE = auto()

    NORM_TAIL_TRACE_FLICK = auto()
    CRIT_TAIL_TRACE_FLICK = auto()

    NORM_TAIL_RELEASE = auto()
    CRIT_TAIL_RELEASE = auto()

    NORM_TICK = auto()
    CRIT_TICK = auto()
    HIDE_TICK = auto()

    DAMAGE = auto()

    ANCHOR = auto()


def init_score(note_archetypes: Iterable[type[PlayArchetype | WatchArchetype]]):
    match LevelConfig.score_mode:
        case ScoreMode.WEIGHTED_COMBO | ScoreMode.UNWEIGHTED_COMBO:
            level_score().update(
                perfect_multiplier=1.0,
                great_multiplier=0.7,
                good_multiplier=0.5,
                consecutive_great_multiplier=0.1,  # Note that the base tap note multiplier is 10 not 1
                consecutive_great_step=100,
                consecutive_great_cap=1000,
            )
        case ScoreMode.WEIGHTED_FLAT | ScoreMode.UNWEIGHTED_FLAT:
            level_score().update(
                perfect_multiplier=3.0,
                great_multiplier=2.0,
                good_multiplier=1.0,
            )
        case _:
            assert_never(LevelConfig.score_mode)

    match LevelConfig.score_mode:
        case ScoreMode.WEIGHTED_COMBO | ScoreMode.WEIGHTED_FLAT:
            for note_archetype in note_archetypes:
                kind = cast(NoteKind, note_archetype.key)
                match kind:
                    case NoteKind.NORM_TAP | NoteKind.NORM_HEAD_TAP | NoteKind.NORM_TAIL_TAP:
                        weight = 10
                    case NoteKind.CRIT_TAP | NoteKind.CRIT_HEAD_TAP | NoteKind.CRIT_TAIL_TAP:
                        weight = 20
                    case NoteKind.NORM_FLICK | NoteKind.NORM_HEAD_FLICK | NoteKind.NORM_TAIL_FLICK:
                        weight = 10
                    case NoteKind.CRIT_FLICK | NoteKind.CRIT_HEAD_FLICK | NoteKind.CRIT_TAIL_FLICK:
                        weight = 30
                    case NoteKind.NORM_TRACE | NoteKind.NORM_HEAD_TRACE | NoteKind.NORM_TAIL_TRACE:
                        weight = 1
                    case NoteKind.CRIT_TRACE | NoteKind.CRIT_HEAD_TRACE | NoteKind.CRIT_TAIL_TRACE:
                        weight = 2
                    case NoteKind.NORM_TRACE_FLICK | NoteKind.NORM_HEAD_TRACE_FLICK | NoteKind.NORM_TAIL_TRACE_FLICK:
                        weight = 10
                    case NoteKind.CRIT_TRACE_FLICK | NoteKind.CRIT_HEAD_TRACE_FLICK | NoteKind.CRIT_TAIL_TRACE_FLICK:
                        weight = 30
                    case NoteKind.NORM_RELEASE | NoteKind.NORM_HEAD_RELEASE | NoteKind.NORM_TAIL_RELEASE:
                        weight = 10
                    case NoteKind.CRIT_RELEASE | NoteKind.CRIT_HEAD_RELEASE | NoteKind.CRIT_TAIL_RELEASE:
                        weight = 20
                    case NoteKind.NORM_TICK | NoteKind.CRIT_TICK | NoteKind.HIDE_TICK:
                        weight = 1
                    case NoteKind.DAMAGE:
                        weight = 1
                    case NoteKind.ANCHOR:
                        weight = 1  # Doesn't really matter since anchors are not scored
                    case _:
                        assert_never(kind)
                note_archetype.archetype_score_multiplier = weight
        case ScoreMode.UNWEIGHTED_COMBO | ScoreMode.UNWEIGHTED_FLAT:
            for note_archetype in note_archetypes:
                note_archetype.archetype_score_multiplier = 10
        case _:
            assert_never(LevelConfig.score_mode)


def init_life(
    note_archetypes: Iterable[type[PlayArchetype | WatchArchetype]],
    initial_life: int,
):
    for note_archetype in note_archetypes:
        init_note_life(note_archetype)
    level_life().update(initial=initial_life, maximum=max(2000, initial_life + 1000))


def init_note_life(archetype: type[PlayArchetype | WatchArchetype]):
    kind = cast(NoteKind, archetype.key)
    match kind:
        case (
            NoteKind.NORM_TAP
            | NoteKind.CRIT_TAP
            | NoteKind.NORM_FLICK
            | NoteKind.CRIT_FLICK
            | NoteKind.NORM_TRACE
            | NoteKind.CRIT_TRACE
            | NoteKind.NORM_TRACE_FLICK
            | NoteKind.CRIT_TRACE_FLICK
            | NoteKind.NORM_RELEASE
            | NoteKind.CRIT_RELEASE
            | NoteKind.NORM_HEAD_TAP
            | NoteKind.CRIT_HEAD_TAP
            | NoteKind.NORM_HEAD_FLICK
            | NoteKind.CRIT_HEAD_FLICK
            | NoteKind.NORM_HEAD_TRACE
            | NoteKind.CRIT_HEAD_TRACE
            | NoteKind.NORM_HEAD_TRACE_FLICK
            | NoteKind.CRIT_HEAD_TRACE_FLICK
            | NoteKind.NORM_HEAD_RELEASE
            | NoteKind.CRIT_HEAD_RELEASE
            | NoteKind.NORM_TAIL_TAP
            | NoteKind.CRIT_TAIL_TAP
            | NoteKind.NORM_TAIL_FLICK
            | NoteKind.CRIT_TAIL_FLICK
            | NoteKind.NORM_TAIL_TRACE
            | NoteKind.CRIT_TAIL_TRACE
            | NoteKind.NORM_TAIL_TRACE_FLICK
            | NoteKind.CRIT_TAIL_TRACE_FLICK
            | NoteKind.NORM_TAIL_RELEASE
            | NoteKind.CRIT_TAIL_RELEASE
        ):
            archetype.life.miss_increment = -80
        case NoteKind.NORM_TICK | NoteKind.CRIT_TICK | NoteKind.HIDE_TICK | NoteKind.DAMAGE:
            archetype.life.miss_increment = -40
        case NoteKind.ANCHOR:
            pass
        case _:
            assert_never(kind)


def map_note_kind(kind: NoteKind) -> NoteKind:
    return kind


def mirror_flick_direction(direction: FlickDirection) -> FlickDirection:
    match direction:
        case FlickDirection.UP_OMNI:
            return FlickDirection.UP_OMNI
        case FlickDirection.DOWN_OMNI:
            return FlickDirection.DOWN_OMNI
        case FlickDirection.UP_LEFT:
            return FlickDirection.UP_RIGHT
        case FlickDirection.UP_RIGHT:
            return FlickDirection.UP_LEFT
        case FlickDirection.DOWN_LEFT:
            return FlickDirection.DOWN_RIGHT
        case FlickDirection.DOWN_RIGHT:
            return FlickDirection.DOWN_LEFT
        case _:
            assert_never(direction)


def get_visual_spawn_time(
    timescale_group: int | EntityRef,
    target_scaled_time: CompositeTime | float,
):
    if isinstance(target_scaled_time, CompositeTime):
        target_scaled_time = target_scaled_time.total
    force_speed = group_force_note_speed(timescale_group)
    return min(
        group_scaled_time_to_first_time(timescale_group, target_scaled_time - preempt_time(force_speed) * 3),
        group_scaled_time_to_first_time_2(timescale_group, target_scaled_time + preempt_time(force_speed) * 3),
        -2 if -3 <= progress_to(target_scaled_time, -2, force_speed) <= 6 else 1e8,
    )


def get_attach_params(
    ease_type: EaseType,
    head_lane: float,
    head_size: float,
    head_target_time: float,
    tail_lane: float,
    tail_size: float,
    tail_target_time: float,
    target_time: float,
):
    if abs(head_target_time - tail_target_time) < 1e-6:
        frac = 0.5
    else:
        frac = remap_clamped(head_target_time, tail_target_time, 0.0, 1.0, target_time)
    eased_frac = ease(ease_type, frac)
    lane = lerp(head_lane, tail_lane, eased_frac)
    size = lerp(head_size, tail_size, eased_frac)
    return lane, size


def draw_note(
    kind: NoteKind,
    lane: float,
    size: float,
    visual_progress: float,
    direction: FlickDirection,
    target_time: float,
):
    if not DynamicLayout.progress_start <= visual_progress <= DynamicLayout.progress_cutoff:
        return
    travel = approach(visual_progress)
    sprite_set = get_note_sprite_set(kind, direction)
    draw_note_body(sprite_set.body, kind, lane, size, travel, target_time)
    draw_note_arrow(sprite_set.arrow, kind, lane, size, travel, target_time, direction)
    draw_note_tick(sprite_set.tick, lane, travel, target_time)


def draw_slide_note_head(
    kind: NoteKind,
    connector_kind: ActiveConnectorKind,
    lane: float,
    size: float,
    target_time: float,
    visual_progress: float = 1.0,
):
    if Options.hidden > 0:
        return
    match connector_kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_FAKE_NORMAL:
            kind = note_kind_as_normal(kind)
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.ACTIVE_FAKE_CRITICAL:
            kind = note_kind_as_critical(kind)
        case _:
            assert_never(connector_kind)
    travel = approach(visual_progress)
    sprite_set = get_note_sprite_set(kind, FlickDirection.UP_OMNI)
    etc = get_active_connector_z_offset(connector_kind, False)
    draw_note_body(sprite_set.body, kind, lane, size, travel, target_time, etc)
    draw_note_tick(sprite_set.tick, lane, travel, target_time, etc)


def note_kind_as_normal(kind: NoteKind) -> NoteKind:
    match kind:
        case NoteKind.CRIT_TAP:
            return NoteKind.NORM_TAP
        case NoteKind.CRIT_FLICK:
            return NoteKind.NORM_FLICK
        case NoteKind.CRIT_TRACE:
            return NoteKind.NORM_TRACE
        case NoteKind.CRIT_TRACE_FLICK:
            return NoteKind.NORM_TRACE_FLICK
        case NoteKind.CRIT_RELEASE:
            return NoteKind.NORM_RELEASE
        case NoteKind.CRIT_HEAD_TAP:
            return NoteKind.NORM_HEAD_TAP
        case NoteKind.CRIT_HEAD_FLICK:
            return NoteKind.NORM_HEAD_FLICK
        case NoteKind.CRIT_HEAD_TRACE:
            return NoteKind.NORM_HEAD_TRACE
        case NoteKind.CRIT_HEAD_TRACE_FLICK:
            return NoteKind.NORM_HEAD_TRACE_FLICK
        case NoteKind.CRIT_HEAD_RELEASE:
            return NoteKind.NORM_HEAD_RELEASE
        case NoteKind.CRIT_TAIL_TAP:
            return NoteKind.NORM_TAIL_TAP
        case NoteKind.CRIT_TAIL_FLICK:
            return NoteKind.NORM_TAIL_FLICK
        case NoteKind.CRIT_TAIL_TRACE:
            return NoteKind.NORM_TAIL_TRACE
        case NoteKind.CRIT_TAIL_TRACE_FLICK:
            return NoteKind.NORM_TAIL_TRACE_FLICK
        case NoteKind.CRIT_TAIL_RELEASE:
            return NoteKind.NORM_TAIL_RELEASE
        case NoteKind.CRIT_TICK:
            return NoteKind.NORM_TICK
        case _:
            return kind


def note_kind_as_critical(kind: NoteKind) -> NoteKind:
    match kind:
        case NoteKind.NORM_TAP:
            return NoteKind.CRIT_TAP
        case NoteKind.NORM_FLICK:
            return NoteKind.CRIT_FLICK
        case NoteKind.NORM_TRACE:
            return NoteKind.CRIT_TRACE
        case NoteKind.NORM_TRACE_FLICK:
            return NoteKind.CRIT_TRACE_FLICK
        case NoteKind.NORM_RELEASE:
            return NoteKind.CRIT_RELEASE
        case NoteKind.NORM_HEAD_TAP:
            return NoteKind.CRIT_HEAD_TAP
        case NoteKind.NORM_HEAD_FLICK:
            return NoteKind.CRIT_HEAD_FLICK
        case NoteKind.NORM_HEAD_TRACE:
            return NoteKind.CRIT_HEAD_TRACE
        case NoteKind.NORM_HEAD_TRACE_FLICK:
            return NoteKind.CRIT_HEAD_TRACE_FLICK
        case NoteKind.NORM_HEAD_RELEASE:
            return NoteKind.CRIT_HEAD_RELEASE
        case NoteKind.NORM_TAIL_TAP:
            return NoteKind.CRIT_TAIL_TAP
        case NoteKind.NORM_TAIL_FLICK:
            return NoteKind.CRIT_TAIL_FLICK
        case NoteKind.NORM_TAIL_TRACE:
            return NoteKind.CRIT_TAIL_TRACE
        case NoteKind.NORM_TAIL_TRACE_FLICK:
            return NoteKind.CRIT_TAIL_TRACE_FLICK
        case NoteKind.NORM_TAIL_RELEASE:
            return NoteKind.CRIT_TAIL_RELEASE
        case NoteKind.NORM_TICK:
            return NoteKind.CRIT_TICK
        case _:
            return kind


def get_note_sprite_set(kind: NoteKind, direction: FlickDirection) -> NoteSpriteSet:
    result = +NoteSpriteSet
    match kind:
        case NoteKind.NORM_TAP:
            result @= ActiveSkin.normal_note
        case NoteKind.CRIT_TAP:
            result @= ActiveSkin.critical_note
        case NoteKind.NORM_FLICK | NoteKind.NORM_HEAD_FLICK | NoteKind.NORM_TAIL_FLICK:
            if direction in {FlickDirection.UP_OMNI, FlickDirection.UP_LEFT, FlickDirection.UP_RIGHT}:
                result @= ActiveSkin.flick_note
            else:
                result @= ActiveSkin.down_flick_note
        case NoteKind.CRIT_FLICK | NoteKind.CRIT_HEAD_FLICK | NoteKind.CRIT_TAIL_FLICK:
            if direction in {FlickDirection.UP_OMNI, FlickDirection.UP_LEFT, FlickDirection.UP_RIGHT}:
                result @= ActiveSkin.critical_flick_note
            else:
                result @= ActiveSkin.critical_down_flick_note
        case NoteKind.NORM_TRACE | NoteKind.NORM_HEAD_TRACE | NoteKind.NORM_TAIL_TRACE:
            result @= ActiveSkin.trace_note
        case NoteKind.CRIT_TRACE | NoteKind.CRIT_HEAD_TRACE | NoteKind.CRIT_TAIL_TRACE:
            result @= ActiveSkin.critical_trace_note
        case NoteKind.NORM_TRACE_FLICK | NoteKind.NORM_HEAD_TRACE_FLICK | NoteKind.NORM_TAIL_TRACE_FLICK:
            if direction in {FlickDirection.UP_OMNI, FlickDirection.UP_LEFT, FlickDirection.UP_RIGHT}:
                result @= ActiveSkin.trace_flick_note
            else:
                result @= ActiveSkin.trace_down_flick_note
        case NoteKind.CRIT_TRACE_FLICK | NoteKind.CRIT_HEAD_TRACE_FLICK | NoteKind.CRIT_TAIL_TRACE_FLICK:
            if direction in {FlickDirection.UP_OMNI, FlickDirection.UP_LEFT, FlickDirection.UP_RIGHT}:
                result @= ActiveSkin.critical_trace_flick_note
            else:
                result @= ActiveSkin.critical_trace_down_flick_note
        case (
            NoteKind.NORM_RELEASE
            | NoteKind.NORM_HEAD_TAP
            | NoteKind.NORM_HEAD_RELEASE
            | NoteKind.NORM_TAIL_TAP
            | NoteKind.NORM_TAIL_RELEASE
        ):
            result @= ActiveSkin.slide_note
        case (
            NoteKind.CRIT_RELEASE
            | NoteKind.CRIT_HEAD_TAP
            | NoteKind.CRIT_HEAD_RELEASE
            | NoteKind.CRIT_TAIL_TAP
            | NoteKind.CRIT_TAIL_RELEASE
        ):
            result @= ActiveSkin.critical_slide_note
        case NoteKind.NORM_TICK:
            result @= ActiveSkin.normal_slide_tick_note
        case NoteKind.CRIT_TICK:
            result @= ActiveSkin.critical_slide_tick_note
        case NoteKind.HIDE_TICK | NoteKind.ANCHOR:
            result @= EMPTY_NOTE_SPRITE_SET
        case NoteKind.DAMAGE:
            result @= ActiveSkin.damage_note
        case _:
            assert_never(kind)
    return result


def get_note_body_layer(kind: NoteKind) -> int:
    match kind:
        case (
            NoteKind.NORM_FLICK
            | NoteKind.CRIT_FLICK
            | NoteKind.NORM_HEAD_FLICK
            | NoteKind.CRIT_HEAD_FLICK
            | NoteKind.NORM_TAIL_FLICK
            | NoteKind.CRIT_TAIL_FLICK
        ):
            return LAYER_NOTE_FLICK_BODY
        case (
            NoteKind.NORM_TRACE
            | NoteKind.CRIT_TRACE
            | NoteKind.NORM_TRACE_FLICK
            | NoteKind.CRIT_TRACE_FLICK
            | NoteKind.NORM_HEAD_TRACE
            | NoteKind.CRIT_HEAD_TRACE
            | NoteKind.NORM_HEAD_TRACE_FLICK
            | NoteKind.CRIT_HEAD_TRACE_FLICK
            | NoteKind.NORM_TAIL_TRACE
            | NoteKind.CRIT_TAIL_TRACE
            | NoteKind.NORM_TAIL_TRACE_FLICK
            | NoteKind.CRIT_TAIL_TRACE_FLICK
            | NoteKind.DAMAGE
        ):
            return LAYER_NOTE_SLIM_BODY
        case _:
            return LAYER_NOTE_BODY


def draw_note_body(
    sprites: BodySpriteSet,
    kind: NoteKind,
    lane: float,
    size: float,
    travel: float,
    target_time: float,
    etc: int = 0,
):
    layer = get_note_body_layer(kind)
    a = get_alpha(target_time)
    z = get_z(layer, time=target_time, lane=lane, etc=etc)
    match sprites.render_type:
        case BodyRenderType.NORMAL:
            left_layout, middle_layout, right_layout = layout_regular_note_body(
                lane, size, travel, lane - size < -6 or lane + size > 6
            )
            sprites.left.draw(left_layout, z=z, a=a)
            sprites.middle.draw(middle_layout, z=z, a=a)
            sprites.right.draw(right_layout, z=z, a=a)
        case BodyRenderType.SLIM:
            left_layout, middle_layout, right_layout = layout_slim_note_body(
                lane, size, travel, lane - size < -6 or lane + size > 6
            )
            sprites.left.draw(left_layout, z=z, a=a)
            sprites.middle.draw(middle_layout, z=z, a=a)
            sprites.right.draw(right_layout, z=z, a=a)
        case BodyRenderType.NORMAL_FALLBACK:
            layout = layout_regular_note_body_fallback(lane, size, travel, lane - size < -6 or lane + size > 6)
            sprites.middle.draw(layout, z=z, a=a)
        case BodyRenderType.SLIM_FALLBACK:
            layout = layout_slim_note_body_fallback(lane, size, travel, lane - size < -6 or lane + size > 6)
            sprites.middle.draw(layout, z=z, a=a)


def draw_note_tick(sprite: Sprite, lane: float, travel: float, target_time: float, etc: int = 0):
    a = get_alpha(target_time)
    z = get_z(LAYER_NOTE_TICK, time=target_time, lane=lane, etc=etc)
    layout = layout_tick(lane, travel)
    sprite.draw(layout, z=z, a=a)


def draw_note_arrow(
    sprites: ArrowSpriteSet,
    kind: NoteKind,
    lane: float,
    size: float,
    travel: float,
    target_time: float,
    direction: FlickDirection,
):
    match direction:
        case _ if Options.marker_animation:
            period = 0.5
            animation_progress = (time() / period) % 1
        case FlickDirection.UP_LEFT | FlickDirection.UP_OMNI | FlickDirection.UP_RIGHT:
            animation_progress = 0.2
        case FlickDirection.DOWN_LEFT | FlickDirection.DOWN_OMNI | FlickDirection.DOWN_RIGHT:
            animation_progress = 0.8
        case _:
            assert_never(direction)
    animation_alpha = (1 - ease_in_cubic(animation_progress)) if Options.marker_animation else 1
    a = get_alpha(target_time) * animation_alpha
    z = get_z(get_flick_layer(kind), time=target_time, lane=lane, etc=direction)
    match sprites.render_type:
        case ArrowRenderType.NORMAL:
            layout = layout_flick_arrow(lane, size, direction, travel, animation_progress)
            sprites.get_sprite(size, direction).draw(layout, z=z, a=a)
        case ArrowRenderType.FALLBACK:
            layout = layout_flick_arrow_fallback(lane, size, direction, travel, animation_progress)
            sprites.get_sprite(size, direction).draw(layout, z=z, a=a)


def get_flick_layer(kind: NoteKind) -> int:
    match kind:
        case (
            NoteKind.CRIT_FLICK
            | NoteKind.CRIT_HEAD_FLICK
            | NoteKind.CRIT_TAIL_FLICK
            | NoteKind.CRIT_TRACE_FLICK
            | NoteKind.CRIT_HEAD_TRACE_FLICK
            | NoteKind.CRIT_TAIL_TRACE_FLICK
        ):
            return LAYER_NOTE_ARROW_CRITICAL
        case _:
            return LAYER_NOTE_ARROW


def get_note_particles(kind: NoteKind, direction: FlickDirection) -> NoteParticleSet:
    result = +NoteParticleSet
    match kind:
        case NoteKind.NORM_TAP:
            result @= ActiveParticles.normal_note
        case (
            NoteKind.NORM_RELEASE
            | NoteKind.NORM_HEAD_TAP
            | NoteKind.NORM_HEAD_RELEASE
            | NoteKind.NORM_TAIL_TAP
            | NoteKind.NORM_TAIL_RELEASE
        ):
            result @= ActiveParticles.slide_note
        case NoteKind.NORM_FLICK | NoteKind.NORM_HEAD_FLICK | NoteKind.NORM_TAIL_FLICK:
            if direction in {FlickDirection.UP_OMNI, FlickDirection.UP_LEFT, FlickDirection.UP_RIGHT}:
                result @= ActiveParticles.flick_note
            else:
                result @= ActiveParticles.down_flick_note
        case NoteKind.NORM_TRACE | NoteKind.NORM_HEAD_TRACE | NoteKind.NORM_TAIL_TRACE:
            result @= ActiveParticles.trace_note
        case NoteKind.NORM_TRACE_FLICK | NoteKind.NORM_HEAD_TRACE_FLICK | NoteKind.NORM_TAIL_TRACE_FLICK:
            if direction in {FlickDirection.UP_OMNI, FlickDirection.UP_LEFT, FlickDirection.UP_RIGHT}:
                result @= ActiveParticles.trace_flick_note
            else:
                result @= ActiveParticles.trace_down_flick_note
        case NoteKind.CRIT_TAP:
            result @= ActiveParticles.critical_note
        case (
            NoteKind.CRIT_RELEASE
            | NoteKind.CRIT_HEAD_TAP
            | NoteKind.CRIT_HEAD_RELEASE
            | NoteKind.CRIT_TAIL_TAP
            | NoteKind.CRIT_TAIL_RELEASE
        ):
            result @= ActiveParticles.critical_slide_note
        case NoteKind.CRIT_FLICK | NoteKind.CRIT_HEAD_FLICK | NoteKind.CRIT_TAIL_FLICK:
            if direction in {FlickDirection.UP_OMNI, FlickDirection.UP_LEFT, FlickDirection.UP_RIGHT}:
                result @= ActiveParticles.critical_flick_note
            else:
                result @= ActiveParticles.critical_down_flick_note
        case NoteKind.CRIT_TRACE | NoteKind.CRIT_HEAD_TRACE | NoteKind.CRIT_TAIL_TRACE:
            result @= ActiveParticles.critical_trace_note
        case NoteKind.CRIT_TRACE_FLICK | NoteKind.CRIT_HEAD_TRACE_FLICK | NoteKind.CRIT_TAIL_TRACE_FLICK:
            if direction in {FlickDirection.UP_OMNI, FlickDirection.UP_LEFT, FlickDirection.UP_RIGHT}:
                result @= ActiveParticles.critical_trace_flick_note
            else:
                result @= ActiveParticles.critical_trace_down_flick_note
        case NoteKind.NORM_TICK:
            result @= ActiveParticles.normal_slide_tick_note
        case NoteKind.CRIT_TICK:
            result @= ActiveParticles.critical_slide_tick_note
        case NoteKind.HIDE_TICK | NoteKind.ANCHOR:
            result @= EMPTY_NOTE_PARTICLE_SET
        case NoteKind.DAMAGE:
            result @= ActiveParticles.damage_note
        case _:
            assert_never(kind)
    return result


class NoteEffectKind(IntEnum):
    DEFAULT = 0
    NONE = 1
    NORM_BASIC = 2
    NORM_FLICK = 3
    NORM_TRACE = 4
    NORM_TICK = 5
    CRIT_BASIC = 6
    CRIT_FLICK = 7
    CRIT_TRACE = 8
    CRIT_TICK = 9
    DAMAGE = 10


def get_note_effect_kind(kind: NoteKind, override: NoteEffectKind = NoteEffectKind.DEFAULT) -> NoteEffectKind:
    match override:
        case NoteEffectKind.DEFAULT:
            match kind:
                case (
                    NoteKind.NORM_TAP
                    | NoteKind.NORM_RELEASE
                    | NoteKind.NORM_HEAD_TAP
                    | NoteKind.NORM_HEAD_RELEASE
                    | NoteKind.NORM_TAIL_TAP
                    | NoteKind.NORM_TAIL_RELEASE
                    | NoteKind.CRIT_RELEASE
                    | NoteKind.CRIT_HEAD_TAP
                    | NoteKind.CRIT_HEAD_RELEASE
                    | NoteKind.CRIT_TAIL_TAP
                    | NoteKind.CRIT_TAIL_RELEASE
                ):
                    return NoteEffectKind.NORM_BASIC
                case (
                    NoteKind.NORM_FLICK
                    | NoteKind.NORM_TRACE_FLICK
                    | NoteKind.NORM_HEAD_FLICK
                    | NoteKind.NORM_HEAD_TRACE_FLICK
                    | NoteKind.NORM_TAIL_FLICK
                    | NoteKind.NORM_TAIL_TRACE_FLICK
                ):
                    return NoteEffectKind.NORM_FLICK
                case NoteKind.NORM_TRACE | NoteKind.NORM_HEAD_TRACE | NoteKind.NORM_TAIL_TRACE:
                    return NoteEffectKind.NORM_TRACE
                case NoteKind.NORM_TICK:
                    return NoteEffectKind.NORM_TICK
                case NoteKind.CRIT_TAP:
                    return NoteEffectKind.CRIT_BASIC
                case (
                    NoteKind.CRIT_FLICK
                    | NoteKind.CRIT_TRACE_FLICK
                    | NoteKind.CRIT_HEAD_FLICK
                    | NoteKind.CRIT_HEAD_TRACE_FLICK
                    | NoteKind.CRIT_TAIL_FLICK
                    | NoteKind.CRIT_TAIL_TRACE_FLICK
                ):
                    return NoteEffectKind.CRIT_FLICK
                case NoteKind.CRIT_TRACE | NoteKind.CRIT_HEAD_TRACE | NoteKind.CRIT_TAIL_TRACE:
                    return NoteEffectKind.CRIT_TRACE
                case NoteKind.CRIT_TICK:
                    return NoteEffectKind.CRIT_TICK
                case NoteKind.HIDE_TICK | NoteKind.ANCHOR:
                    return NoteEffectKind.NONE
                case NoteKind.DAMAGE:
                    return NoteEffectKind.DAMAGE
                case _:
                    assert_never(kind)
        case _:
            return override


def get_note_effect(kind: NoteEffectKind, judgment: Judgment):
    result = Effect(-1)
    assert kind != NoteEffectKind.DEFAULT, "Unexpected NoteEffectKind.DEFAULT argument to get_note_effect"
    match kind:
        case NoteEffectKind.NORM_BASIC:
            match judgment:
                case Judgment.PERFECT:
                    result @= Effects.normal_perfect
                case Judgment.GREAT:
                    result @= Effects.normal_great
                case Judgment.GOOD:
                    result @= Effects.normal_good
                case Judgment.MISS:
                    result @= Effects.normal_good
                case _:
                    assert_never(judgment)
        case NoteEffectKind.NORM_FLICK:
            match judgment:
                case Judgment.PERFECT:
                    result @= Effects.flick_perfect
                case Judgment.GREAT:
                    result @= Effects.flick_perfect
                case Judgment.GOOD:
                    result @= Effects.flick_perfect
                case Judgment.MISS:
                    result @= Effects.flick_perfect
                case _:
                    assert_never(judgment)
        case NoteEffectKind.NORM_TRACE:
            if judgment != Judgment.MISS:
                result @= first_available_effect(Effects.normal_trace, Effects.normal_perfect)
            else:
                result @= EMPTY_EFFECT
        case NoteEffectKind.NORM_TICK:
            if judgment != Judgment.MISS:
                result @= first_available_effect(Effects.normal_tick, Effects.normal_perfect)
            else:
                result @= EMPTY_EFFECT
        case NoteEffectKind.CRIT_BASIC:
            if judgment != Judgment.MISS:
                result @= first_available_effect(Effects.critical_tap, Effects.normal_perfect)
            else:
                result @= EMPTY_EFFECT
        case NoteEffectKind.CRIT_FLICK:
            if judgment != Judgment.MISS:
                result @= first_available_effect(Effects.critical_flick, Effects.flick_perfect)
            else:
                result @= EMPTY_EFFECT
        case NoteEffectKind.CRIT_TRACE:
            if judgment != Judgment.MISS:
                result @= first_available_effect(Effects.critical_trace, Effects.normal_perfect)
            else:
                result @= EMPTY_EFFECT
        case NoteEffectKind.CRIT_TICK:
            if judgment != Judgment.MISS:
                result @= first_available_effect(Effects.critical_tick, Effects.normal_perfect)
            else:
                result @= EMPTY_EFFECT
        case NoteEffectKind.NONE:
            result @= EMPTY_EFFECT
        case NoteEffectKind.DAMAGE:
            if judgment == Judgment.MISS:
                result @= Effects.normal_good
            else:
                result @= EMPTY_EFFECT
        case _:
            assert_never(kind)
    return result


def play_note_hit_effects(
    kind: NoteKind,
    effect_kind: NoteEffectKind,
    lane: float,
    size: float,
    direction: FlickDirection,
    judgment: Judgment,
    y_offset: float = 0.0,
    pivot_lane: float = 0.0,
    half_offset: bool = False,
):
    # Damage with overridden sfx can play, so this goes before the damage check
    sfx = get_note_effect(effect_kind, judgment)
    if Options.sfx_enabled and not Options.auto_sfx and not is_watch() and sfx.is_available:
        sfx.play(SFX_DISTANCE)
    if kind == NoteKind.DAMAGE and judgment == Judgment.PERFECT:
        return
    particles = get_note_particles(kind, direction)
    if Options.note_effect_enabled:
        linear_particle = particles.get_linear(judgment)
        if linear_particle.is_available:
            layout = layout_linear_effect(lane, shear=0, y_offset=y_offset)
            if linear_particle == particles.linear_good:
                for slot_lane in iter_slot_lanes(lane, size):
                    layout @= layout_linear_effect(slot_lane, shear=0)
                    linear_particle.spawn(layout, duration=0.5 / Options.effect_animation_speed)
            else:
                linear_particle.spawn(layout, duration=0.5 / Options.effect_animation_speed)
        circular_particle = particles.get_circular(judgment)
        if circular_particle.is_available:
            layout = layout_circular_effect(lane, w=1.75, h=1.05, y_offset=y_offset)
            if circular_particle == particles.circular_good:
                for slot_lane in iter_slot_lanes(lane, size):
                    layout @= layout_circular_effect(slot_lane, w=1.75, h=1.05)
                circular_particle.spawn(layout, duration=0.6 / Options.effect_animation_speed)
            else:
                circular_particle.spawn(layout, duration=0.6 / Options.effect_animation_speed)
        if particles.directional.is_available:
            degree = (
                45
                if kind
                in (
                    NoteKind.CRIT_FLICK,
                    NoteKind.CRIT_HEAD_FLICK,
                    NoteKind.CRIT_HEAD_TRACE_FLICK,
                    NoteKind.CRIT_TAIL_FLICK,
                    NoteKind.CRIT_TAIL_TRACE_FLICK,
                )
                and LevelConfig.particle_version == Version.v1
                else 22.5
            )
            match direction:
                case FlickDirection.UP_OMNI | FlickDirection.DOWN_OMNI:
                    shear = 0
                case FlickDirection.UP_LEFT | FlickDirection.DOWN_RIGHT:
                    shear = degree
                case FlickDirection.UP_RIGHT | FlickDirection.DOWN_LEFT:
                    shear = -degree
                case _:
                    assert_never(direction)
            layout = layout_rotated2_linear_effect(lane, degree=shear, y_offset=y_offset)
            particles.directional.spawn(layout, duration=0.32 / Options.effect_animation_speed)
        if particles.tick.is_available:
            layout = layout_tick_effect(lane, y_offset=y_offset)
            particles.tick.spawn(layout, duration=0.6 / Options.effect_animation_speed)
        slot_linear_particle = particles.get_slot_linear()
        if slot_linear_particle.is_available:
            for slot_lane in iter_slot_lanes(lane, size, pivot_lane=pivot_lane, half_offset=half_offset):
                layout = layout_linear_effect(slot_lane, shear=0, y_offset=y_offset)
                slot_linear_particle.spawn(layout, duration=0.5 / Options.effect_animation_speed)
    if Options.lane_effect_enabled:
        lane_y_offset = (
            y_offset if kind in {NoteKind.CRIT_FLICK, NoteKind.CRIT_HEAD_FLICK, NoteKind.CRIT_TAIL_FLICK} else 0.0
        )
        if particles.lane.is_available:
            if particles.lane.id != BaseParticles.critical_flick_note_lane_linear.id:
                for slot_lane in iter_slot_lanes(lane, size):
                    layout = layout_lane(slot_lane, 0.5, y_offset=lane_y_offset)
                    particles.lane.spawn(layout, duration=1 / Options.effect_animation_speed)
        elif particles.lane_basic.is_available:
            for slot_lane in iter_slot_lanes(lane, size):
                layout = layout_lane(slot_lane, 0.5, y_offset=lane_y_offset)
                particles.lane_basic.spawn(layout, duration=0.3 / Options.effect_animation_speed)
    if Options.slot_effect_enabled and not is_watch():
        schedule_note_slot_effects(
            kind,
            lane,
            size,
            time(),
            direction,
            judgment,
            y_offset=y_offset,
            pivot_lane=pivot_lane,
            half_offset=half_offset,
        )


def get_note_haptic_feedback(kind: NoteKind, judgment: Judgment) -> HapticType:
    if judgment == Judgment.MISS and Options.vibrate_mode in {VibrateMode.MISS, VibrateMode.MISS_AND_GOOD}:
        return HapticType.LONG
    if judgment == Judgment.GOOD and Options.vibrate_mode in {VibrateMode.MISS_AND_GOOD}:
        return HapticType.LONG
    if not Options.tap_haptics_enabled or judgment not in {Judgment.PERFECT, Judgment.GREAT}:
        return HapticType.NONE
    match kind:
        case (
            NoteKind.NORM_FLICK
            | NoteKind.CRIT_FLICK
            | NoteKind.NORM_HEAD_FLICK
            | NoteKind.CRIT_HEAD_FLICK
            | NoteKind.NORM_TAIL_FLICK
            | NoteKind.CRIT_TAIL_FLICK
        ):
            return HapticType.HEAVY
        case (
            NoteKind.NORM_TAP
            | NoteKind.NORM_HEAD_TAP
            | NoteKind.NORM_TAIL_TAP
            | NoteKind.CRIT_TAP
            | NoteKind.CRIT_HEAD_TAP
            | NoteKind.CRIT_TAIL_TAP
            | NoteKind.NORM_RELEASE
            | NoteKind.CRIT_RELEASE
            | NoteKind.NORM_HEAD_RELEASE
            | NoteKind.CRIT_HEAD_RELEASE
            | NoteKind.NORM_TAIL_RELEASE
            | NoteKind.CRIT_TAIL_RELEASE
        ):
            return HapticType.MEDIUM
        case (
            NoteKind.NORM_TRACE
            | NoteKind.CRIT_TRACE
            | NoteKind.NORM_TRACE_FLICK
            | NoteKind.CRIT_TRACE_FLICK
            | NoteKind.NORM_HEAD_TRACE
            | NoteKind.CRIT_HEAD_TRACE
            | NoteKind.NORM_TAIL_TRACE
            | NoteKind.CRIT_TAIL_TRACE
            | NoteKind.NORM_HEAD_TRACE_FLICK
            | NoteKind.CRIT_HEAD_TRACE_FLICK
            | NoteKind.NORM_TAIL_TRACE_FLICK
            | NoteKind.CRIT_TAIL_TRACE_FLICK
            | NoteKind.NORM_TICK
            | NoteKind.CRIT_TICK
        ):
            return HapticType.LIGHT
        case _:
            return HapticType.NONE


def schedule_note_auto_sfx(kind: NoteEffectKind, target_time: float, accuracy: float = 0):
    if not Options.sfx_enabled:
        return
    if not Options.auto_sfx:
        return
    sfx = get_note_effect(kind, Judgment.PERFECT)
    if sfx.is_available:
        sfx.schedule(target_time, SFX_DISTANCE)


def schedule_note_sfx(kind: NoteEffectKind, judgment: Judgment, target_time: float):
    if not Options.sfx_enabled:
        return
    sfx = get_note_effect(kind, judgment)
    if sfx.is_available:
        sfx.schedule(target_time, SFX_DISTANCE)


def schedule_note_slot_effects(
    kind: NoteKind,
    lane: float,
    size: float,
    target_time: float,
    direction: FlickDirection,
    judgment: Judgment = Judgment.PERFECT,
    y_offset: float = 0.0,
    pivot_lane: float = 0.0,
    half_offset: bool = False,
):
    if is_tutorial():
        return
    if not Options.slot_effect_enabled:
        return
    sprite_set = get_note_sprite_set(kind, direction)
    slot_sprite = sprite_set.slot
    if slot_sprite.is_available:
        for slot_lane in iter_slot_lanes(lane, size, pivot_lane=pivot_lane, half_offset=half_offset):
            get_archetype_by_name(archetype_names.SLOT_EFFECT).spawn(
                sprite=slot_sprite, start_time=target_time, lane=slot_lane, y_offset=y_offset
            )
    slot_glow_sprite = sprite_set.slot_glow.get_sprite(judgment)
    if slot_glow_sprite.is_available:
        for slot_lane in iter_slot_lanes(lane, size):
            get_archetype_by_name(archetype_names.SLOT_GLOW_EFFECT).spawn(
                sprite=slot_glow_sprite, start_time=target_time, lane=slot_lane, size=size, y_offset=y_offset
            )


def draw_tutorial_note_slot_effects(
    kind: NoteKind,
    lane: float,
    size: float,
    start_time: float,
    direction: FlickDirection,
    pivot_lane: float = 0.0,
    half_offset: bool = False,
):
    sprite_set = get_note_sprite_set(kind, direction)
    slot_sprite = sprite_set.slot
    if slot_sprite.is_available and time() < start_time + SLOT_EFFECT_DURATION / Options.effect_animation_speed:
        for slot_lane in iter_slot_lanes(lane, size, pivot_lane=pivot_lane, half_offset=half_offset):
            draw_slot_effect(
                sprite=slot_sprite,
                start_time=start_time,
                end_time=start_time + SLOT_EFFECT_DURATION / Options.effect_animation_speed,
                lane=slot_lane,
            )
    slot_glow_sprite = sprite_set.slot_glow.perfect
    if (
        slot_glow_sprite.is_available
        and time() < start_time + SLOT_GLOW_EFFECT_DURATION / Options.effect_animation_speed
    ):
        draw_slot_glow_effect(
            sprite=slot_glow_sprite,
            start_time=start_time,
            end_time=start_time + SLOT_GLOW_EFFECT_DURATION / Options.effect_animation_speed,
            lane=lane,
            size=size,
        )


def get_note_window(kind: NoteKind, is_connector_tick) -> SekaiWindow:
    result = +SekaiWindow
    match kind:
        case NoteKind.NORM_TAP | NoteKind.NORM_HEAD_TAP | NoteKind.NORM_TAIL_TAP:
            result @= TAP_NORMAL_WINDOW
        case NoteKind.CRIT_TAP | NoteKind.CRIT_HEAD_TAP | NoteKind.CRIT_TAIL_TAP:
            result @= TAP_CRITICAL_WINDOW
        case NoteKind.NORM_FLICK | NoteKind.NORM_HEAD_FLICK:
            result @= FLICK_NORMAL_WINDOW
        case NoteKind.CRIT_FLICK | NoteKind.CRIT_HEAD_FLICK:
            result @= FLICK_CRITICAL_WINDOW
        case NoteKind.NORM_TAIL_FLICK:
            result @= SLIDE_END_FLICK_NORMAL_WINDOW
        case NoteKind.CRIT_TAIL_FLICK:
            result @= SLIDE_END_FLICK_CRITICAL_WINDOW
        case NoteKind.NORM_TRACE | NoteKind.NORM_HEAD_TRACE:
            result @= TRACE_NORMAL_WINDOW
        case NoteKind.CRIT_TRACE | NoteKind.CRIT_HEAD_TRACE:
            result @= TRACE_CRITICAL_WINDOW
        case NoteKind.NORM_TRACE_FLICK | NoteKind.NORM_HEAD_TRACE_FLICK | NoteKind.NORM_TAIL_TRACE_FLICK:
            result @= TRACE_FLICK_NORMAL_WINDOW
        case NoteKind.CRIT_TRACE_FLICK | NoteKind.CRIT_HEAD_TRACE_FLICK | NoteKind.CRIT_TAIL_TRACE_FLICK:
            result @= TRACE_FLICK_CRITICAL_WINDOW
        case NoteKind.NORM_RELEASE | NoteKind.NORM_HEAD_RELEASE | NoteKind.NORM_TAIL_RELEASE:
            result @= SLIDE_END_NORMAL_WINDOW
        case NoteKind.CRIT_RELEASE | NoteKind.CRIT_HEAD_RELEASE | NoteKind.CRIT_TAIL_RELEASE:
            result @= SLIDE_END_CRITICAL_WINDOW
        case NoteKind.NORM_TAIL_TRACE:
            result @= SLIDE_END_TRACE_NORMAL_WINDOW
        case NoteKind.CRIT_TAIL_TRACE:
            result @= SLIDE_END_TRACE_CRITICAL_WINDOW
        case NoteKind.NORM_TAIL_TRACE_FLICK:
            result @= TRACE_FLICK_NORMAL_WINDOW
        case NoteKind.CRIT_TAIL_TRACE_FLICK:
            result @= TRACE_FLICK_CRITICAL_WINDOW
        case NoteKind.NORM_TICK | NoteKind.CRIT_TICK | NoteKind.HIDE_TICK:
            if is_connector_tick:
                result @= EMPTY_JUDGMENT_WINDOW
            else:
                result @= SLIDE_TICK_JUDGMENT_WINDOW
        case NoteKind.ANCHOR | NoteKind.DAMAGE:
            result @= EMPTY_JUDGMENT_WINDOW
        case _:
            assert_never(kind)
    return result


def get_note_window_bad(kind: NoteKind) -> Interval:
    result = +Interval
    match kind:
        case NoteKind.NORM_TAP | NoteKind.NORM_HEAD_TAP | NoteKind.NORM_TAIL_TAP:
            result @= TAP_NORMAL_WINDOW_BAD
        case NoteKind.CRIT_TAP | NoteKind.CRIT_HEAD_TAP | NoteKind.CRIT_TAIL_TAP:
            result @= TAP_CRITICAL_WINDOW_BAD
        case NoteKind.NORM_FLICK | NoteKind.NORM_HEAD_FLICK:
            result @= FLICK_NORMAL_WINDOW_BAD
        case NoteKind.CRIT_FLICK | NoteKind.CRIT_HEAD_FLICK:
            result @= FLICK_NORMAL_WINDOW_BAD
        case NoteKind.DAMAGE:
            result @= Interval(0, 0)
        case (
            NoteKind.NORM_TAIL_FLICK
            | NoteKind.CRIT_TAIL_FLICK
            | NoteKind.NORM_TRACE
            | NoteKind.NORM_HEAD_TRACE
            | NoteKind.CRIT_TRACE
            | NoteKind.CRIT_HEAD_TRACE
            | NoteKind.NORM_TRACE_FLICK
            | NoteKind.NORM_HEAD_TRACE_FLICK
            | NoteKind.NORM_TAIL_TRACE_FLICK
            | NoteKind.CRIT_TRACE_FLICK
            | NoteKind.CRIT_HEAD_TRACE_FLICK
            | NoteKind.CRIT_TAIL_TRACE_FLICK
            | NoteKind.NORM_RELEASE
            | NoteKind.NORM_HEAD_RELEASE
            | NoteKind.NORM_TAIL_RELEASE
            | NoteKind.CRIT_RELEASE
            | NoteKind.CRIT_HEAD_RELEASE
            | NoteKind.CRIT_TAIL_RELEASE
            | NoteKind.NORM_TAIL_TRACE
            | NoteKind.CRIT_TAIL_TRACE
            | NoteKind.NORM_TAIL_TRACE_FLICK
            | NoteKind.CRIT_TAIL_TRACE_FLICK
            | NoteKind.NORM_TICK
            | NoteKind.CRIT_TICK
            | NoteKind.HIDE_TICK
            | NoteKind.ANCHOR
        ):
            result @= Interval(-1, -1)
        case _:
            assert_never(kind)
    return result


def get_note_bucket(kind: NoteKind) -> Bucket:
    result = Bucket(-1)
    match kind:
        case NoteKind.NORM_TAP:
            result @= Buckets.normal_tap
        case NoteKind.CRIT_TAP:
            result @= Buckets.critical_tap
        case NoteKind.NORM_FLICK:
            result @= Buckets.normal_flick
        case NoteKind.CRIT_FLICK:
            result @= Buckets.critical_flick
        case NoteKind.NORM_TRACE:
            result @= Buckets.normal_trace
        case NoteKind.CRIT_TRACE:
            result @= Buckets.critical_trace
        case NoteKind.NORM_TRACE_FLICK:
            result @= Buckets.normal_trace_flick
        case NoteKind.CRIT_TRACE_FLICK:
            result @= Buckets.critical_trace_flick
        case NoteKind.NORM_HEAD_TAP:
            result @= Buckets.normal_head_tap
        case NoteKind.CRIT_HEAD_TAP:
            result @= Buckets.critical_head_tap
        case NoteKind.NORM_HEAD_FLICK:
            result @= Buckets.normal_head_flick
        case NoteKind.CRIT_HEAD_FLICK:
            result @= Buckets.critical_head_flick
        case NoteKind.NORM_HEAD_TRACE:
            result @= Buckets.normal_head_trace
        case NoteKind.CRIT_HEAD_TRACE:
            result @= Buckets.critical_head_trace
        case NoteKind.NORM_HEAD_TRACE_FLICK:
            result @= Buckets.normal_head_trace_flick
        case NoteKind.CRIT_HEAD_TRACE_FLICK:
            result @= Buckets.critical_head_trace_flick
        case NoteKind.NORM_TAIL_FLICK:
            result @= Buckets.normal_tail_flick
        case NoteKind.CRIT_TAIL_FLICK:
            result @= Buckets.critical_tail_flick
        case NoteKind.NORM_TAIL_TRACE:
            result @= Buckets.normal_tail_trace
        case NoteKind.CRIT_TAIL_TRACE:
            result @= Buckets.critical_tail_trace
        case NoteKind.NORM_TAIL_TRACE_FLICK:
            result @= Buckets.normal_tail_trace_flick
        case NoteKind.CRIT_TAIL_TRACE_FLICK:
            result @= Buckets.critical_tail_trace_flick
        case NoteKind.NORM_TAIL_RELEASE:
            result @= Buckets.normal_tail_release
        case NoteKind.CRIT_TAIL_RELEASE:
            result @= Buckets.critical_tail_release
        case (
            NoteKind.NORM_RELEASE
            | NoteKind.CRIT_RELEASE
            | NoteKind.NORM_HEAD_RELEASE
            | NoteKind.CRIT_HEAD_RELEASE
            | NoteKind.NORM_TAIL_TAP
            | NoteKind.CRIT_TAIL_TAP
            | NoteKind.NORM_TICK
            | NoteKind.CRIT_TICK
            | NoteKind.HIDE_TICK
            | NoteKind.ANCHOR
            | NoteKind.DAMAGE
        ):
            result @= Bucket(-1)
        case _:
            assert_never(kind)
    return result


def get_leniency(kind: NoteKind) -> float:
    if kind == NoteKind.DAMAGE:
        return 0.0
    # For notes without input, this value doesn't matter
    return 1.0


def has_tap_input(kind: NoteKind) -> bool:
    return kind in {
        NoteKind.NORM_TAP,
        NoteKind.CRIT_TAP,
        NoteKind.NORM_FLICK,
        NoteKind.CRIT_FLICK,
        NoteKind.NORM_HEAD_TAP,
        NoteKind.CRIT_HEAD_TAP,
        NoteKind.NORM_HEAD_FLICK,
        NoteKind.CRIT_HEAD_FLICK,
        NoteKind.NORM_TAIL_TAP,
        NoteKind.CRIT_TAIL_TAP,
    }


def has_release_input(kind: NoteKind) -> bool:
    return kind in {
        NoteKind.NORM_RELEASE,
        NoteKind.CRIT_RELEASE,
        NoteKind.NORM_HEAD_RELEASE,
        NoteKind.CRIT_HEAD_RELEASE,
        NoteKind.NORM_TAIL_RELEASE,
        NoteKind.CRIT_TAIL_RELEASE,
    }


def is_head(kind: NoteKind) -> bool:
    return kind in {
        NoteKind.NORM_HEAD_TAP,
        NoteKind.CRIT_HEAD_TAP,
        NoteKind.NORM_HEAD_FLICK,
        NoteKind.CRIT_HEAD_FLICK,
        NoteKind.NORM_HEAD_TRACE,
        NoteKind.CRIT_HEAD_TRACE,
        NoteKind.NORM_HEAD_TRACE_FLICK,
        NoteKind.CRIT_HEAD_TRACE_FLICK,
        NoteKind.NORM_HEAD_RELEASE,
        NoteKind.CRIT_HEAD_RELEASE,
    }


def is_critical(kind: NoteKind) -> bool:
    return kind in {
        NoteKind.CRIT_TAP,
        NoteKind.CRIT_FLICK,
        NoteKind.CRIT_TRACE,
        NoteKind.CRIT_TRACE_FLICK,
        NoteKind.CRIT_RELEASE,
        NoteKind.CRIT_HEAD_TAP,
        NoteKind.CRIT_HEAD_FLICK,
        NoteKind.CRIT_HEAD_TRACE,
        NoteKind.CRIT_HEAD_TRACE_FLICK,
        NoteKind.CRIT_HEAD_RELEASE,
        NoteKind.CRIT_TAIL_TAP,
        NoteKind.CRIT_TAIL_FLICK,
        NoteKind.CRIT_TAIL_TRACE,
        NoteKind.CRIT_TAIL_TRACE_FLICK,
        NoteKind.CRIT_TAIL_RELEASE,
        NoteKind.CRIT_TICK,
    }


HITBOX_DEBUG_BORDER_THICKNESS = 0.01
HITBOX_DEBUG_END_HALF_HEIGHT = 0.05
HITBOX_DEBUG_END_WIDTH = 0.04
HITBOX_DEBUG_DOT_HALF = 0.012
HITBOX_DEBUG_TRIANGLE_HEIGHT = 0.2
HITBOX_DEBUG_APEX_HALF = 0.012


def draw_hitbox_line(sprite: Sprite, p1: Vec2, p2: Vec2, thickness: float, z: float, a: float):
    ortho = (p2 - p1).orthogonal().normalize_or_zero() * (thickness / 2)
    sprite.draw(
        Quad(
            bl=p1 - ortho,
            br=p2 - ortho,
            tr=p2 + ortho,
            tl=p1 + ortho,
        ),
        z=z,
        a=a,
    )


def draw_hitbox_marker(
    l: Vec2,
    r: Vec2,
    main_sprite: Sprite,
    dot_sprite: Sprite,
    z: float,
    z_dot: float,
    a: float,
):
    t = HITBOX_DEBUG_BORDER_THICKNESS
    end_h = HITBOX_DEBUG_END_HALF_HEIGHT
    end_w = HITBOX_DEBUG_END_WIDTH
    dot = HITBOX_DEBUG_DOT_HALF
    axis = (r - l).normalize_or_zero()
    ortho = axis.orthogonal()
    li = l + axis * end_w
    ri = r - axis * end_w
    main_sprite.draw(
        Quad(
            bl=li - ortho * t,
            tl=li + ortho * t,
            tr=ri + ortho * t,
            br=ri - ortho * t,
        ),
        z=z,
        a=a,
    )
    main_sprite.draw(
        Quad(
            bl=l - ortho * end_h,
            tl=l + ortho * end_h,
            tr=li + ortho * t,
            br=li - ortho * t,
        ),
        z=z,
        a=a,
    )
    main_sprite.draw(
        Quad(
            bl=ri - ortho * t,
            tl=ri + ortho * t,
            tr=r + ortho * end_h,
            br=r - ortho * end_h,
        ),
        z=z,
        a=a,
    )
    dot_sprite.draw(
        Quad(
            bl=l - ortho * dot,
            tl=l + ortho * dot,
            tr=l + axis * (2 * dot) + ortho * dot,
            br=l + axis * (2 * dot) - ortho * dot,
        ),
        z=z_dot,
        a=a,
    )
    dot_sprite.draw(
        Quad(
            bl=r - axis * (2 * dot) - ortho * dot,
            tl=r - axis * (2 * dot) + ortho * dot,
            tr=r + ortho * dot,
            br=r - ortho * dot,
        ),
        z=z_dot,
        a=a,
    )


def draw_hitbox_bounds_overlay(bounds: Quad, alpha: float = 1.0):
    t = HITBOX_DEBUG_BORDER_THICKNESS
    a = alpha
    z_bounds = get_z_alt(LAYER_GUIDE_CONNECTOR_OVER, 0)
    draw_hitbox_line(ActiveSkin.guide_blue, bounds.tl, bounds.tr, t, z_bounds, a)
    draw_hitbox_line(ActiveSkin.guide_blue, bounds.bl, bounds.br, t, z_bounds, a)
    draw_hitbox_line(ActiveSkin.guide_blue, bounds.tl, bounds.bl, t, z_bounds, a)
    draw_hitbox_line(ActiveSkin.guide_blue, bounds.tr, bounds.br, t, z_bounds, a)
    draw_hitbox_line(ActiveSkin.guide_blue, bounds.tl, bounds.br, t, z_bounds, a)
    draw_hitbox_line(ActiveSkin.guide_blue, bounds.tr, bounds.bl, t, z_bounds, a)


def draw_hitbox_overlay(hitbox: Hitbox, draw_target: bool, alpha: float = 1.0):
    t = HITBOX_DEBUG_BORDER_THICKNESS
    a = alpha
    z_triangle = get_z_alt(LAYER_GUIDE_CONNECTOR_OVER, 1)
    z_apex = get_z_alt(LAYER_GUIDE_CONNECTOR_OVER, 2)
    z_target = get_z_alt(LAYER_GUIDE_CONNECTOR_OVER, 3)
    z_target_dot = get_z_alt(LAYER_GUIDE_CONNECTOR_OVER, 4)

    draw_hitbox_bounds_overlay(hitbox.bounds, alpha)

    if draw_target:
        l = hitbox.target.l
        r = hitbox.target.r
        axis = (r - l).normalize_or_zero()
        ortho = axis.orthogonal()
        apex_half = HITBOX_DEBUG_APEX_HALF
        target_apex = (l + r) / 2 + ortho * HITBOX_DEBUG_TRIANGLE_HEIGHT
        draw_hitbox_line(
            ActiveSkin.guide_red,
            l,
            target_apex,
            t,
            z_triangle,
            a,
        )
        draw_hitbox_line(
            ActiveSkin.guide_red,
            r,
            target_apex,
            t,
            z_triangle,
            a,
        )
        ActiveSkin.guide_red.draw(
            Quad(
                bl=target_apex - axis * apex_half - ortho * apex_half,
                tl=target_apex - axis * apex_half + ortho * apex_half,
                tr=target_apex + axis * apex_half + ortho * apex_half,
                br=target_apex + axis * apex_half - ortho * apex_half,
            ),
            z=z_apex,
            a=a,
        )
        draw_hitbox_marker(
            l=l,
            r=r,
            main_sprite=ActiveSkin.guide_red,
            dot_sprite=ActiveSkin.guide_black,
            z=z_target,
            z_dot=z_target_dot,
            a=a,
        )
