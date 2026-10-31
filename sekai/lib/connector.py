from collections.abc import Callable
from enum import IntEnum
from math import atan2, ceil, cos, floor, inf, log, pi, sin, sqrt
from struct import pack, unpack
from typing import Any, Literal, Self, assert_never, cast, overload

from sonolus.script.archetype import EntityRef
from sonolus.script.array import Array, Dim
from sonolus.script.containers import VarArray
from sonolus.script.easing import ease_in_circ, ease_in_out_circ, ease_out_circ, ease_out_in_circ
from sonolus.script.effect import Effect, LoopedEffectHandle
from sonolus.script.globals import level_memory
from sonolus.script.interval import clamp, lerp, remap_clamped
from sonolus.script.particle import Particle, ParticleHandle
from sonolus.script.quad import Quad, QuadLike
from sonolus.script.record import Record
from sonolus.script.runtime import offset_adjusted_time, screen, time
from sonolus.script.sprite import Sprite
from sonolus.script.timing import beat_to_time
from sonolus.script.values import alloc
from sonolus.script.vec import Vec2

from sekai.lib.ease import (
    EaseType,
    ease,
    ease_overshoot,
    is_curved_ease,
    is_in_step_ease,
    is_step_ease,
    safe_unlerp,
    safe_unlerp_clamped,
)
from sekai.lib.effect import Effects
from sekai.lib.layer import Layer, ZIndexes, get_z, layers
from sekai.lib.layout import (
    IDENTITY_STAGE_SCREEN_TRANSFORM,
    ApproachCache,
    DynamicLayout,
    StageScreenTransform,
    StageTransform,
    approach,
    blend_stage_transform,
    get_alpha,
    inverse_approach_tilt,
    iter_slot_lanes,
    layout_circular_effect,
    layout_linear_effect,
    layout_slide_connector_segment,
    layout_slot_glow_effect,
    quad_touches_screen,
    st_slide_connector_segment,
    stage_projection_blend_frac,
    stage_transform_is_identity,
    tilt_width_factor,
    transformed_vec_at,
)
from sekai.lib.level_config import LevelConfig
from sekai.lib.note_style import NoteStyle
from sekai.lib.options import Options, Version
from sekai.lib.particle import ActiveParticles, get_styled_connector_particles
from sekai.lib.skin import (
    ActiveConnectorSpriteSet,
    ActiveSkin,
    get_styled_active_connector_sprites,
    get_styled_damage_connector_sprites,
)
from sekai.lib.stage import VisualMask
from sekai.lib.timescale import iter_timescale_changes_in_group_from_time

type ElevationTransform = Callable[[float, float], StageTransform]

CONNECTOR_TRAIL_SPAWN_PERIOD = 0.1
CONNECTOR_SLOT_SPAWN_PERIOD = 0.2
CONNECTOR_THROUGH_JUDGE_LINE_DESPAWN_DELAY = 5.0
CONNECTOR_LENIENCY = 1
CONNECTOR_PARTICLE_ACTIVE_DELAY = 0.05
CONNECTOR_ZERO_SIZE_FALLBACK = 1e-3
CONNECTOR_ALPHA_ERROR = 1 / 192
CONNECTOR_ALPHA_SEGMENT_LENGTH = 2 * (32 / 1080)
CONNECTOR_MIN_SEGMENT_LENGTH = 2 * (4 / 1080)
CONNECTOR_CURVE_ERROR = 2 * (2 / 1080)
CONNECTOR_CURVE_PIECES = 8
CONNECTOR_CURVE_PIECE_THRESHOLD = 32


def connector_endpoint_ease(ease_type: EaseType, ease_frac: float) -> float:
    # Keep step endpoints at their note positions.
    if ease_frac <= 0:
        return 0.0
    if ease_frac >= 1:
        return 1.0
    return ease(ease_type, ease_frac)


def get_connector_interp_frac(
    ease_type: EaseType,
    head_ease_frac: float,
    tail_ease_frac: float,
    target_ease_frac: float,
    fallback_frac: float,
) -> float:
    if is_in_step_ease(ease_type):
        return 0.0
    return get_connector_interp_frac_from_eased_endpoints(
        ease_type,
        connector_endpoint_ease(ease_type, head_ease_frac),
        connector_endpoint_ease(ease_type, tail_ease_frac),
        target_ease_frac,
        fallback_frac,
    )


def get_connector_interp_frac_from_eased_endpoints(
    ease_type: EaseType,
    head_eased: float,
    tail_eased: float,
    target_ease_frac: float,
    fallback_frac: float,
) -> float:
    return safe_unlerp(
        head_eased,
        tail_eased,
        ease(ease_type, target_ease_frac),
        fallback_frac,
    )


def get_connector_fractions(
    ease_type: EaseType,
    head_target_time: float,
    head_ease_frac: float,
    tail_target_time: float,
    tail_ease_frac: float,
    target_time: float,
) -> tuple[float, float]:
    target_frac = safe_unlerp_clamped(head_target_time, tail_target_time, target_time)
    target_ease_frac = lerp(head_ease_frac, tail_ease_frac, target_frac)
    interp_frac = get_connector_interp_frac(
        ease_type,
        head_ease_frac,
        tail_ease_frac,
        target_ease_frac,
        target_frac,
    )
    return target_frac, interp_frac


def _connector_alpha_position(note: Any) -> float:
    if note.is_attached:
        head = note.attach_head_ref.get()
        tail = note.attach_tail_ref.get()
        if head.beat == tail.beat:
            return lerp(head.elevation, tail.elevation, note.head_ease_frac)
    return note.elevation


def _connector_alpha_root_frac(note: Any, head: Any, tail: Any) -> float:
    if note.index == head.index:
        return 0.0
    if note.index == tail.index:
        return 1.0
    if note.is_attached and note.attach_head_ref.index == head.index and note.attach_tail_ref.index == tail.index:
        return note.head_ease_frac
    return -1.0


def get_connector_alpha_frac(note: Any, segment_head: Any, segment_tail: Any) -> float:
    """Return linear alpha progress from authored time or elevation."""
    if segment_head.beat != segment_tail.beat:
        return safe_unlerp_clamped(segment_head.target_time, segment_tail.target_time, note.target_time)
    if note.index == segment_head.index:
        return 0.0
    if note.index == segment_tail.index:
        return 1.0

    # Attachment fractions handle equal note heights on stages with different elevations.
    source_ref = +segment_head.ref()
    if not segment_head.is_attached:
        source_ref @= segment_tail.ref()
        if not segment_tail.is_attached:
            source_ref @= note.ref()
    source = source_ref.get()
    if source.is_attached:
        head = source.attach_head_ref.get()
        tail = source.attach_tail_ref.get()
        if head.beat == tail.beat:
            start = _connector_alpha_root_frac(segment_head, head, tail)
            end = _connector_alpha_root_frac(segment_tail, head, tail)
            position = _connector_alpha_root_frac(note, head, tail)
            if min(start, end, position) >= 0:
                return safe_unlerp_clamped(start, end, position)

    return safe_unlerp_clamped(
        _connector_alpha_position(segment_head),
        _connector_alpha_position(segment_tail),
        _connector_alpha_position(note),
    )


class ConnectorKind(IntEnum):
    NONE = 0

    ACTIVE_NORMAL = 1
    ACTIVE_CRITICAL = 2
    DAMAGE = 3
    FAKE_ACTIVE_NORMAL = 51
    FAKE_ACTIVE_CRITICAL = 52
    FAKE_DAMAGE = 53

    ACTIVE_NORMAL_NEUTRAL = 11
    ACTIVE_NORMAL_RED = 12
    ACTIVE_NORMAL_GREEN = 13
    ACTIVE_NORMAL_BLUE = 14
    ACTIVE_NORMAL_YELLOW = 15
    ACTIVE_NORMAL_PURPLE = 16
    ACTIVE_NORMAL_CYAN = 17
    ACTIVE_NORMAL_BLACK = 18
    ACTIVE_CRITICAL_NEUTRAL = 21
    ACTIVE_CRITICAL_RED = 22
    ACTIVE_CRITICAL_GREEN = 23
    ACTIVE_CRITICAL_BLUE = 24
    ACTIVE_CRITICAL_YELLOW = 25
    ACTIVE_CRITICAL_PURPLE = 26
    ACTIVE_CRITICAL_CYAN = 27
    ACTIVE_CRITICAL_BLACK = 28
    DAMAGE_NEUTRAL = 31
    DAMAGE_RED = 32
    DAMAGE_GREEN = 33
    DAMAGE_BLUE = 34
    DAMAGE_YELLOW = 35
    DAMAGE_PURPLE = 36
    DAMAGE_CYAN = 37
    DAMAGE_BLACK = 38
    FAKE_ACTIVE_NORMAL_NEUTRAL = 61
    FAKE_ACTIVE_NORMAL_RED = 62
    FAKE_ACTIVE_NORMAL_GREEN = 63
    FAKE_ACTIVE_NORMAL_BLUE = 64
    FAKE_ACTIVE_NORMAL_YELLOW = 65
    FAKE_ACTIVE_NORMAL_PURPLE = 66
    FAKE_ACTIVE_NORMAL_CYAN = 67
    FAKE_ACTIVE_NORMAL_BLACK = 68
    FAKE_ACTIVE_CRITICAL_NEUTRAL = 71
    FAKE_ACTIVE_CRITICAL_RED = 72
    FAKE_ACTIVE_CRITICAL_GREEN = 73
    FAKE_ACTIVE_CRITICAL_BLUE = 74
    FAKE_ACTIVE_CRITICAL_YELLOW = 75
    FAKE_ACTIVE_CRITICAL_PURPLE = 76
    FAKE_ACTIVE_CRITICAL_CYAN = 77
    FAKE_ACTIVE_CRITICAL_BLACK = 78
    FAKE_DAMAGE_NEUTRAL = 81
    FAKE_DAMAGE_RED = 82
    FAKE_DAMAGE_GREEN = 83
    FAKE_DAMAGE_BLUE = 84
    FAKE_DAMAGE_YELLOW = 85
    FAKE_DAMAGE_PURPLE = 86
    FAKE_DAMAGE_CYAN = 87
    FAKE_DAMAGE_BLACK = 88

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


class SegmentPresentation(IntEnum):
    DEFAULT = 0
    FULL_SCREEN = 1


ActiveConnectorKind = Literal[
    ConnectorKind.ACTIVE_NORMAL,
    ConnectorKind.ACTIVE_CRITICAL,
    ConnectorKind.FAKE_ACTIVE_NORMAL,
    ConnectorKind.FAKE_ACTIVE_CRITICAL,
    ConnectorKind.ACTIVE_NORMAL_NEUTRAL,
    ConnectorKind.ACTIVE_NORMAL_RED,
    ConnectorKind.ACTIVE_NORMAL_GREEN,
    ConnectorKind.ACTIVE_NORMAL_BLUE,
    ConnectorKind.ACTIVE_NORMAL_YELLOW,
    ConnectorKind.ACTIVE_NORMAL_PURPLE,
    ConnectorKind.ACTIVE_NORMAL_CYAN,
    ConnectorKind.ACTIVE_NORMAL_BLACK,
    ConnectorKind.ACTIVE_CRITICAL_NEUTRAL,
    ConnectorKind.ACTIVE_CRITICAL_RED,
    ConnectorKind.ACTIVE_CRITICAL_GREEN,
    ConnectorKind.ACTIVE_CRITICAL_BLUE,
    ConnectorKind.ACTIVE_CRITICAL_YELLOW,
    ConnectorKind.ACTIVE_CRITICAL_PURPLE,
    ConnectorKind.ACTIVE_CRITICAL_CYAN,
    ConnectorKind.ACTIVE_CRITICAL_BLACK,
    ConnectorKind.FAKE_ACTIVE_NORMAL_NEUTRAL,
    ConnectorKind.FAKE_ACTIVE_NORMAL_RED,
    ConnectorKind.FAKE_ACTIVE_NORMAL_GREEN,
    ConnectorKind.FAKE_ACTIVE_NORMAL_BLUE,
    ConnectorKind.FAKE_ACTIVE_NORMAL_YELLOW,
    ConnectorKind.FAKE_ACTIVE_NORMAL_PURPLE,
    ConnectorKind.FAKE_ACTIVE_NORMAL_CYAN,
    ConnectorKind.FAKE_ACTIVE_NORMAL_BLACK,
    ConnectorKind.FAKE_ACTIVE_CRITICAL_NEUTRAL,
    ConnectorKind.FAKE_ACTIVE_CRITICAL_RED,
    ConnectorKind.FAKE_ACTIVE_CRITICAL_GREEN,
    ConnectorKind.FAKE_ACTIVE_CRITICAL_BLUE,
    ConnectorKind.FAKE_ACTIVE_CRITICAL_YELLOW,
    ConnectorKind.FAKE_ACTIVE_CRITICAL_PURPLE,
    ConnectorKind.FAKE_ACTIVE_CRITICAL_CYAN,
    ConnectorKind.FAKE_ACTIVE_CRITICAL_BLACK,
]

DamageConnectorKind = Literal[
    ConnectorKind.DAMAGE,
    ConnectorKind.FAKE_DAMAGE,
    ConnectorKind.DAMAGE_NEUTRAL,
    ConnectorKind.DAMAGE_RED,
    ConnectorKind.DAMAGE_GREEN,
    ConnectorKind.DAMAGE_BLUE,
    ConnectorKind.DAMAGE_YELLOW,
    ConnectorKind.DAMAGE_PURPLE,
    ConnectorKind.DAMAGE_CYAN,
    ConnectorKind.DAMAGE_BLACK,
    ConnectorKind.FAKE_DAMAGE_NEUTRAL,
    ConnectorKind.FAKE_DAMAGE_RED,
    ConnectorKind.FAKE_DAMAGE_GREEN,
    ConnectorKind.FAKE_DAMAGE_BLUE,
    ConnectorKind.FAKE_DAMAGE_YELLOW,
    ConnectorKind.FAKE_DAMAGE_PURPLE,
    ConnectorKind.FAKE_DAMAGE_CYAN,
    ConnectorKind.FAKE_DAMAGE_BLACK,
]

SlideConnectorKind = ActiveConnectorKind | DamageConnectorKind

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

BaseActiveConnectorKind = Literal[
    ConnectorKind.ACTIVE_NORMAL,
    ConnectorKind.ACTIVE_CRITICAL,
    ConnectorKind.FAKE_ACTIVE_NORMAL,
    ConnectorKind.FAKE_ACTIVE_CRITICAL,
]
BaseDamageConnectorKind = Literal[ConnectorKind.DAMAGE, ConnectorKind.FAKE_DAMAGE]
BaseConnectorKind = BaseActiveConnectorKind | BaseDamageConnectorKind | GuideConnectorKind | Literal[ConnectorKind.NONE]


class ConnectorVisualState(IntEnum):
    WAITING = 0
    INACTIVE = 1
    ACTIVE = 2


CONNECTOR_SFX_ACTIVE_TIME_INIT = -1e8
CONNECTOR_SFX_INACTIVE_TIME_INIT = 1e8


class ConnectorSfxTimes(Record):
    active_time: float
    inactive_time: float


class ConnectorSfxEvent(Record):
    times: ConnectorSfxTimes
    kind: ConnectorKind


@level_memory
class ConnectorSfxState:
    active_time: float
    inactive_time: float
    kind: ConnectorKind
    active_head_index: int


class ConnectorMaskStatus(IntEnum):
    OUTSIDE = -1
    NEEDS_CLIPPING = 0
    INSIDE = 1


@overload
def get_connector_base_kind(kind: ActiveConnectorKind) -> BaseActiveConnectorKind: ...


@overload
def get_connector_base_kind(kind: DamageConnectorKind) -> BaseDamageConnectorKind: ...


@overload
def get_connector_base_kind(
    kind: ActiveConnectorKind | DamageConnectorKind,
) -> BaseActiveConnectorKind | BaseDamageConnectorKind: ...


@overload
def get_connector_base_kind(kind: GuideConnectorKind) -> GuideConnectorKind: ...


@overload
def get_connector_base_kind(kind: ConnectorKind) -> BaseConnectorKind: ...


def get_connector_base_kind(kind: ConnectorKind) -> BaseConnectorKind:
    if ConnectorKind.ACTIVE_NORMAL_NEUTRAL <= kind <= ConnectorKind.ACTIVE_NORMAL_BLACK:
        return ConnectorKind.ACTIVE_NORMAL
    if ConnectorKind.ACTIVE_CRITICAL_NEUTRAL <= kind <= ConnectorKind.ACTIVE_CRITICAL_BLACK:
        return ConnectorKind.ACTIVE_CRITICAL
    if ConnectorKind.DAMAGE_NEUTRAL <= kind <= ConnectorKind.DAMAGE_BLACK:
        return ConnectorKind.DAMAGE
    if ConnectorKind.FAKE_ACTIVE_NORMAL_NEUTRAL <= kind <= ConnectorKind.FAKE_ACTIVE_NORMAL_BLACK:
        return ConnectorKind.FAKE_ACTIVE_NORMAL
    if ConnectorKind.FAKE_ACTIVE_CRITICAL_NEUTRAL <= kind <= ConnectorKind.FAKE_ACTIVE_CRITICAL_BLACK:
        return ConnectorKind.FAKE_ACTIVE_CRITICAL
    if ConnectorKind.FAKE_DAMAGE_NEUTRAL <= kind <= ConnectorKind.FAKE_DAMAGE_BLACK:
        return ConnectorKind.FAKE_DAMAGE
    return cast(BaseConnectorKind, kind)


def get_connector_style(kind: ConnectorKind) -> NoteStyle:
    """Return the note color override, or DEFAULT for guides and uncolored kinds."""
    if get_connector_base_kind(kind) != kind:
        return cast(NoteStyle, kind % 10)
    return NoteStyle.DEFAULT


def is_fake_active_connector(kind: ConnectorKind, *, base_kind: BaseConnectorKind | None = None) -> bool:
    if base_kind is None:
        base_kind = get_connector_base_kind(kind)
    return base_kind in {ConnectorKind.FAKE_ACTIVE_NORMAL, ConnectorKind.FAKE_ACTIVE_CRITICAL}


def is_fake_connector(kind: ConnectorKind) -> bool:
    return is_fake_active_connector(kind) or get_connector_base_kind(kind) == ConnectorKind.FAKE_DAMAGE


def should_show_connector_hitbox(kind: ConnectorKind, *, base_kind: BaseConnectorKind | None = None) -> bool:
    # Damage connectors handle input, but their ticks already show the input bounds.
    if base_kind is None:
        base_kind = get_connector_base_kind(kind)
    return base_kind in {ConnectorKind.ACTIVE_NORMAL, ConnectorKind.ACTIVE_CRITICAL}


def get_connector_input_leniency(kind: ConnectorKind, *, base_kind: BaseConnectorKind | None = None) -> float:
    if base_kind is None:
        base_kind = get_connector_base_kind(kind)
    if base_kind == ConnectorKind.DAMAGE:
        return 0.0
    return CONNECTOR_LENIENCY


def get_active_connector_sprites(kind: ActiveConnectorKind) -> ActiveConnectorSpriteSet:
    result = +ActiveConnectorSpriteSet
    base_kind = get_connector_base_kind(kind)
    match base_kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_NORMAL:
            result @= ActiveSkin.active_slide_connector
            if get_connector_style(kind) != NoteStyle.DEFAULT:
                result @= get_styled_active_connector_sprites(get_connector_style(kind), False)
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
            result @= ActiveSkin.critical_active_slide_connector
            if get_connector_style(kind) != NoteStyle.DEFAULT:
                result @= get_styled_active_connector_sprites(get_connector_style(kind), True)
        case _:
            assert_never(base_kind)
    return result


def get_guide_connector_sprite(kind: GuideConnectorKind) -> Sprite:
    result = +Sprite
    match get_connector_base_kind(kind):
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


def get_damage_connector_sprite(kind: ConnectorKind = ConnectorKind.DAMAGE) -> Sprite:
    result = +Sprite
    result @= ActiveSkin.damage_slide_connector
    if get_connector_style(kind) != NoteStyle.DEFAULT:
        result @= get_styled_damage_connector_sprites(get_connector_style(kind)).connection.normal
    return result


def get_damage_connector_active_sprite(kind: ConnectorKind = ConnectorKind.DAMAGE) -> Sprite:
    result = +Sprite
    result @= ActiveSkin.damage_slide_connector_active
    if get_connector_style(kind) != NoteStyle.DEFAULT:
        result @= get_styled_damage_connector_sprites(get_connector_style(kind)).connection.active
    return result


def get_connector_depth_layer(base_kind: BaseConnectorKind, layer: ConnectorLayer) -> Layer:
    result = +Layer
    active = base_kind in {
        ConnectorKind.ACTIVE_NORMAL,
        ConnectorKind.ACTIVE_CRITICAL,
        ConnectorKind.FAKE_ACTIVE_NORMAL,
        ConnectorKind.FAKE_ACTIVE_CRITICAL,
    }
    match layer:
        case ConnectorLayer.TOP:
            if active:
                result @= layers.active_slide_connector_top
            else:
                result @= layers.guide_connector_top
        case ConnectorLayer.BOTTOM:
            if active:
                result @= layers.active_slide_connector_bottom
            else:
                result @= layers.guide_connector_bottom
        case ConnectorLayer.UNDER:
            if active:
                result @= layers.active_slide_connector_under
            else:
                result @= layers.guide_connector_under
        case ConnectorLayer.OVER:
            if active:
                result @= layers.active_slide_connector_over
            else:
                result @= layers.guide_connector_over
        case _:
            assert_never(layer)
    return result


def get_connector_depth_order(base_kind: BaseConnectorKind, active: bool = False) -> int:
    match base_kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_NORMAL:
            return 3 - active
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
            return 1 - active
        case ConnectorKind.DAMAGE | ConnectorKind.FAKE_DAMAGE:
            return 9 - active
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
            return base_kind - ConnectorKind.GUIDE_NEUTRAL
        case ConnectorKind.NONE:
            return 0
        case _:
            assert_never(base_kind)


def get_connector_z(
    kind: ConnectorKind, target_time: float, lane: float, active: bool, layer: ConnectorLayer, *, elevation: float = 0.0
) -> ZIndexes:
    result = +ZIndexes
    base_kind = get_connector_base_kind(kind)
    if base_kind != ConnectorKind.NONE:
        result @= get_z(
            get_connector_depth_layer(base_kind, layer),
            time=target_time,
            lane=lane,
            etc=get_connector_depth_order(base_kind, active),
            elevation=elevation,
            invert_time=True,
        )
    return result


def get_guide_connector_layer_z(
    layer: ConnectorLayer, target_time: float, lane: float, etc: int, *, elevation: float = 0.0
) -> ZIndexes:
    return get_z(
        get_connector_depth_layer(ConnectorKind.GUIDE_NEUTRAL, layer),
        time=target_time,
        lane=lane,
        etc=etc,
        elevation=elevation,
        invert_time=True,
    )


def get_active_connector_z_offset(kind: ActiveConnectorKind | DamageConnectorKind, active: bool) -> int:
    base_kind = get_connector_base_kind(kind)
    match base_kind:
        case (
            ConnectorKind.ACTIVE_NORMAL
            | ConnectorKind.FAKE_ACTIVE_NORMAL
            | ConnectorKind.ACTIVE_CRITICAL
            | ConnectorKind.FAKE_ACTIVE_CRITICAL
            | ConnectorKind.DAMAGE
            | ConnectorKind.FAKE_DAMAGE
        ):
            return get_connector_depth_order(base_kind, active)
        case _:
            assert_never(base_kind)


def get_connector_alpha_option(kind: ConnectorKind, *, base_kind: BaseConnectorKind | None = None) -> float:
    if base_kind is None:
        base_kind = get_connector_base_kind(kind)
    match base_kind:
        case (
            ConnectorKind.ACTIVE_NORMAL
            | ConnectorKind.FAKE_ACTIVE_NORMAL
            | ConnectorKind.ACTIVE_CRITICAL
            | ConnectorKind.FAKE_ACTIVE_CRITICAL
        ):
            return Options.slide_alpha
        case ConnectorKind.DAMAGE | ConnectorKind.FAKE_DAMAGE:
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
            assert_never(base_kind)


def get_connector_quality_option(kind: ConnectorKind, *, base_kind: BaseConnectorKind | None = None) -> float:
    if base_kind is None:
        base_kind = get_connector_base_kind(kind)
    match base_kind:
        case (
            ConnectorKind.ACTIVE_NORMAL
            | ConnectorKind.FAKE_ACTIVE_NORMAL
            | ConnectorKind.ACTIVE_CRITICAL
            | ConnectorKind.FAKE_ACTIVE_CRITICAL
        ):
            return Options.slide_quality
        case ConnectorKind.DAMAGE | ConnectorKind.FAKE_DAMAGE:
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
            assert_never(base_kind)


class ConnectorRenderInfo(Record):
    """Immutable sprite selection and integer depth inputs prepared after skin initialization."""

    base_kind: BaseConnectorKind
    normal_sprite: Sprite
    active_sprite: Sprite
    depth_layer: Layer
    normal_depth_order: int


def get_connector_render_info(kind: ConnectorKind, layer: ConnectorLayer) -> ConnectorRenderInfo:
    normal_sprite = Sprite(-1)
    active_sprite = Sprite(-1)
    base_kind = get_connector_base_kind(kind)
    match base_kind:
        case (
            ConnectorKind.ACTIVE_NORMAL
            | ConnectorKind.ACTIVE_CRITICAL
            | ConnectorKind.FAKE_ACTIVE_NORMAL
            | ConnectorKind.FAKE_ACTIVE_CRITICAL
        ):
            sprites = get_active_connector_sprites(cast(ActiveConnectorKind, kind))
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
            sprites = get_guide_connector_sprite(cast(GuideConnectorKind, kind))
            normal_sprite @= sprites
        case ConnectorKind.DAMAGE:
            normal_sprite @= get_damage_connector_sprite(kind)
            active_sprite @= get_damage_connector_active_sprite(kind)
        case ConnectorKind.FAKE_DAMAGE:
            normal_sprite @= get_damage_connector_sprite(kind)
        case ConnectorKind.NONE:
            pass
        case _:
            assert_never(base_kind)

    result = ConnectorRenderInfo(
        base_kind=base_kind,
        normal_sprite=normal_sprite,
        active_sprite=active_sprite,
        depth_layer=Layer(0, 0),
        normal_depth_order=0,
    )
    if base_kind != ConnectorKind.NONE:
        result.depth_layer = get_connector_depth_layer(base_kind, layer)
        result.normal_depth_order = get_connector_depth_order(base_kind)
    return result


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
    presentation: SegmentPresentation,
    bypass_tail_target_time_check: bool,
    head_transform: StageTransform | None,
    tail_transform: StageTransform | None,
    head_note_alpha: float,
    tail_note_alpha: float,
    head_mask: VisualMask | None = None,
    tail_mask: VisualMask | None = None,
    shared_transform: bool = False,
    ease_over_elevation: bool = False,
    elevation_transform: ElevationTransform | None = None,
    head_alpha_frac: float = -1.0,
    tail_alpha_frac: float = -1.0,
    render_info: ConnectorRenderInfo | None = None,
):
    elevation_dynamic = ease_over_elevation and not shared_transform
    match presentation:
        case SegmentPresentation.DEFAULT:
            if (
                (
                    head_visual_progress < DynamicLayout.progress_start
                    and tail_visual_progress < DynamicLayout.progress_start
                )
                or (
                    head_visual_progress > DynamicLayout.progress_cutoff
                    and tail_visual_progress > DynamicLayout.progress_cutoff
                )
                or (
                    head_visual_progress == tail_visual_progress
                    and not elevation_dynamic
                    and (shared_transform or head_transform == tail_transform)
                )
            ):
                return
        case SegmentPresentation.FULL_SCREEN:
            if head_target_time == tail_target_time or not (
                min(head_target_time, tail_target_time) <= time() <= max(head_target_time, tail_target_time)
            ):
                return
        case _:
            assert_never(presentation)

    if Options.disable_fake_notes and is_fake_connector(kind):
        return

    if head_note_alpha <= 0 and tail_note_alpha <= 0:
        return

    if render_info is None:
        if kind == ConnectorKind.NONE:
            return
        render_info = get_connector_render_info(kind, layer)
    base_kind = render_info.base_kind
    normal_sprite = render_info.normal_sprite
    active_sprite = render_info.active_sprite
    if base_kind == ConnectorKind.NONE:
        return

    match base_kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.ACTIVE_CRITICAL:
            segment_head_alpha = 1.0
            segment_tail_alpha = 1.0
        case ConnectorKind.FAKE_ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
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
        case ConnectorKind.FAKE_DAMAGE:
            segment_head_alpha = 1.0
            segment_tail_alpha = 1.0
            visual_state = ConnectorVisualState.WAITING
        case ConnectorKind.DAMAGE:
            segment_head_alpha = 1.0
            segment_tail_alpha = 1.0
        case _:
            assert_never(base_kind)

    if head_alpha_frac < 0:
        head_alpha_frac = safe_unlerp_clamped(segment_head_target_time, segment_tail_target_time, head_target_time)
    if tail_alpha_frac < 0:
        tail_alpha_frac = safe_unlerp_clamped(segment_head_target_time, segment_tail_target_time, tail_target_time)
    head_alpha = (
        lerp(
            segment_head_alpha,
            segment_tail_alpha,
            head_alpha_frac,
        )
        * head_note_alpha
    )
    tail_alpha = (
        lerp(
            segment_head_alpha,
            segment_tail_alpha,
            tail_alpha_frac,
        )
        * tail_note_alpha
    )

    if time() >= tail_target_time and not bypass_tail_target_time_check:
        return

    z_normal = +ZIndexes
    z_active = +ZIndexes
    z_normal @= get_z(
        render_info.depth_layer,
        time=segment_head_target_time,
        lane=segment_head_lane,
        etc=render_info.normal_depth_order,
        invert_time=True,
    )
    if visual_state == ConnectorVisualState.ACTIVE and active_sprite.is_available:
        z_active @= get_z(
            render_info.depth_layer,
            time=segment_head_target_time,
            lane=segment_head_lane,
            etc=render_info.normal_depth_order - 1,
            invert_time=True,
        )
    else:
        z_active @= z_normal

    match presentation:
        case SegmentPresentation.DEFAULT:
            # Split in-out steps at the jump.
            piece_count = 1
            split_frac = 1.0
            if ease_type == EaseType.IN_OUT_STEP and (
                head_ease_frac < 0.5 < tail_ease_frac or (ease_over_elevation and tail_ease_frac < 0.5 < head_ease_frac)
            ):
                piece_count = 2
                split_frac = (0.5 - head_ease_frac) / (tail_ease_frac - head_ease_frac)
            for piece in range(piece_count):
                first_piece = piece == 0
                last_piece = piece == piece_count - 1
                piece_ease_type = ease_type
                constant_interp_frac = -1.0
                if is_step_ease(ease_type):
                    piece_ease_type = EaseType.NONE
                    constant_interp_frac = get_connector_interp_frac(
                        ease_type,
                        head_ease_frac,
                        tail_ease_frac,
                        ((head_ease_frac if first_piece else 0.5) + (tail_ease_frac if last_piece else 0.5)) / 2,
                        0.0,
                    )
                draw_connector_default(
                    segment_head_target_time=segment_head_target_time,
                    kind=kind,
                    base_kind=render_info.base_kind,
                    visual_state=visual_state,
                    ease_type=piece_ease_type,
                    normal_sprite=normal_sprite,
                    active_sprite=active_sprite,
                    z_normal=z_normal,
                    z_active=z_active,
                    head_lane=head_lane,
                    head_size=head_size,
                    head_visual_progress=(
                        head_visual_progress
                        if first_piece
                        else lerp(head_visual_progress, tail_visual_progress, split_frac)
                    ),
                    head_target_time=(
                        head_target_time if first_piece else lerp(head_target_time, tail_target_time, split_frac)
                    ),
                    head_ease_frac=head_ease_frac if first_piece else 0.5,
                    head_alpha=head_alpha if first_piece else lerp(head_alpha, tail_alpha, split_frac),
                    tail_lane=tail_lane,
                    tail_size=tail_size,
                    tail_visual_progress=(
                        tail_visual_progress
                        if last_piece
                        else lerp(head_visual_progress, tail_visual_progress, split_frac)
                    ),
                    tail_target_time=(
                        tail_target_time if last_piece else lerp(head_target_time, tail_target_time, split_frac)
                    ),
                    tail_ease_frac=tail_ease_frac if last_piece else 0.5,
                    tail_alpha=tail_alpha if last_piece else lerp(head_alpha, tail_alpha, split_frac),
                    head_transform=head_transform,
                    tail_transform=tail_transform,
                    head_mask=head_mask,
                    tail_mask=tail_mask,
                    shared_transform=shared_transform,
                    constant_interp_frac=constant_interp_frac,
                    ease_over_elevation=ease_over_elevation,
                    elevation_transform=elevation_transform,
                    elevation_start_frac=0.0 if first_piece else split_frac,
                    elevation_end_frac=1.0 if last_piece else split_frac,
                )
        case SegmentPresentation.FULL_SCREEN:
            if head_transform is not None and tail_transform is not None:
                judge_frac = safe_unlerp_clamped(head_target_time, tail_target_time, time())
                elevation = lerp(head_transform.projection.elevation, tail_transform.projection.elevation, judge_frac)
                z_normal.z2 += elevation
                z_active.z2 += elevation
            draw_connector_full_screen(
                kind=kind,
                base_kind=render_info.base_kind,
                visual_state=visual_state,
                normal_sprite=normal_sprite,
                active_sprite=active_sprite,
                z_normal=z_normal,
                z_active=z_active,
                head_target_time=head_target_time,
                head_alpha=head_alpha,
                tail_target_time=tail_target_time,
                tail_alpha=tail_alpha,
            )
        case _:
            assert_never(presentation)


def masked_connector_extents_by_limits(
    lane: float,
    size: float,
    mask_left: float,
    mask_right: float,
) -> tuple[float, float, float]:
    """Return the masked lane, render size, and masked size for a connector endpoint."""
    if mask_right < mask_left:
        mask_left = (mask_left + mask_right) / 2
        mask_right = mask_left
    masked_left = clamp(lane - size, mask_left, mask_right)
    masked_right = clamp(lane + size, mask_left, mask_right)
    masked_size = (masked_right - masked_left) / 2
    mask_size = max(0.0, (mask_right - mask_left) / 2)
    render_size = min(masked_size if masked_size > 0 else CONNECTOR_ZERO_SIZE_FALLBACK, mask_size)
    render_lane = clamp((masked_left + masked_right) / 2, mask_left + render_size, mask_right - render_size)
    return render_lane, render_size, masked_size


class ConnectorRenderCache(Record):
    transform_valid: bool
    constant_transform: bool
    translation_only: bool
    no_stage_rotation: bool
    rigid_transform: bool
    interp_frac: float
    transform: StageScreenTransform
    camera_rotated: bool
    camera_cos: float
    camera_sin: float
    edge_valid: bool
    left: Vec2
    right: Vec2
    elevation: float

    @classmethod
    def new(cls) -> Self:
        result = +cls
        result.camera_rotated = DynamicLayout.rotate != 0
        if result.camera_rotated:
            result.camera_cos = cos(-DynamicLayout.rotate)
            result.camera_sin = sin(-DynamicLayout.rotate)
        return result

    def prepare_transform(self, head: StageTransform, tail: StageTransform, constant_transform: bool):
        self.constant_transform = constant_transform
        if constant_transform:
            self.translation_only = head.sr == 0 and head.projection == IDENTITY_STAGE_SCREEN_TRANSFORM
        else:
            self.no_stage_rotation = head.sr == 0 and tail.sr == 0
            self.rigid_transform = (
                head.projection == IDENTITY_STAGE_SCREEN_TRANSFORM
                and tail.projection == IDENTITY_STAGE_SCREEN_TRANSFORM
            )
            self.translation_only = self.no_stage_rotation and self.rigid_transform

    def update_transform(self, head: StageTransform, tail: StageTransform, interp_frac: float):
        if not self.transform_valid or (not self.constant_transform and self.interp_frac != interp_frac):
            if self.constant_transform:
                self.transform @= head.to_screen_transform()
            elif self.no_stage_rotation:
                projection_frac = stage_projection_blend_frac(head.projection, tail.projection, interp_frac)
                self.transform @= StageScreenTransform(
                    a00=lerp(head.projection.a00, tail.projection.a00, projection_frac),
                    a01=lerp(head.projection.a01, tail.projection.a01, projection_frac),
                    a02=lerp(head.projection.a02, tail.projection.a02, projection_frac)
                    + lerp(head.tx, tail.tx, interp_frac),
                    a10=lerp(head.projection.a10, tail.projection.a10, projection_frac),
                    a11=lerp(head.projection.a11, tail.projection.a11, projection_frac),
                    a12=lerp(head.projection.a12, tail.projection.a12, projection_frac)
                    + lerp(head.ty, tail.ty, interp_frac),
                    elevation=lerp(head.projection.elevation, tail.projection.elevation, projection_frac),
                )
            elif self.rigid_transform:
                rotation = lerp(head.sr, tail.sr, interp_frac)
                stage_cos = cos(rotation)
                stage_sin = sin(rotation)
                pivot_x = lerp(head.px, tail.px, interp_frac)
                pivot_y = lerp(head.py, tail.py, interp_frac)
                self.transform @= StageScreenTransform(
                    a00=stage_cos,
                    a01=stage_sin,
                    a02=pivot_x * (1 - stage_cos) - stage_sin * pivot_y + lerp(head.tx, tail.tx, interp_frac),
                    a10=-stage_sin,
                    a11=stage_cos,
                    a12=pivot_y * (1 - stage_cos) + stage_sin * pivot_x + lerp(head.ty, tail.ty, interp_frac),
                    elevation=0.0,
                )
            else:
                self.transform @= blend_stage_transform(head, tail, interp_frac).to_screen_transform()
            self.interp_frac = interp_frac
            self.transform_valid = True

    def update_edge(
        self,
        lane: float,
        size: float,
        travel: float,
        interp_frac: float,
        has_transform: bool,
        head: StageTransform | None,
        tail: StageTransform | None,
        ease_over_elevation: bool = False,
        elevation_transform: ElevationTransform | None = None,
        elevation_frac: float = 0.0,
    ):
        width = tilt_width_factor(travel)
        left_x = (lane - size) * width * DynamicLayout.w_scale + DynamicLayout.x_translate
        right_x = (lane + size) * width * DynamicLayout.w_scale + DynamicLayout.x_translate
        y = travel * DynamicLayout.h_scale + DynamicLayout.t
        if self.camera_rotated:
            self.left @= Vec2(
                left_x * self.camera_cos - y * self.camera_sin,
                left_x * self.camera_sin + y * self.camera_cos,
            )
            self.right @= Vec2(
                right_x * self.camera_cos - y * self.camera_sin,
                right_x * self.camera_sin + y * self.camera_cos,
            )
        else:
            self.left @= Vec2(left_x, y)
            self.right @= Vec2(right_x, y)
        self.elevation = 0.0
        if has_transform:
            assert head is not None
            assert tail is not None
            if ease_over_elevation:
                assert elevation_transform is not None
                transform = elevation_transform(interp_frac, elevation_frac).to_screen_transform()
                self.left @= transform.apply(self.left)
                self.right @= transform.apply(self.right)
                self.elevation = transform.elevation
            elif self.translation_only:
                if self.constant_transform:
                    x_offset = head.tx
                    y_offset = head.ty
                else:
                    x_offset = lerp(head.tx, tail.tx, interp_frac)
                    y_offset = lerp(head.ty, tail.ty, interp_frac)
                self.left.x += x_offset
                self.left.y += y_offset
                self.right.x += x_offset
                self.right.y += y_offset
            else:
                self.update_transform(head, tail, interp_frac)
                self.left @= self.transform.apply(self.left)
                self.right @= self.transform.apply(self.right)
                self.elevation = self.transform.elevation
        self.edge_valid = True


def connector_mask_status(
    start_lane: float, start_size: float, end_lane: float, end_size: float, left: float, right: float
) -> ConnectorMaskStatus:
    """Classify a connector whose edges each move in one direction."""
    # Let clipping handle zero-width endpoints so their fallback widths respect the mask.
    if start_size <= 0 or end_size <= 0:
        return ConnectorMaskStatus.NEEDS_CLIPPING
    left_min = min(start_lane - start_size, end_lane - end_size)
    right_max = max(start_lane + start_size, end_lane + end_size)
    if right_max <= left or left_min >= right:
        return ConnectorMaskStatus.OUTSIDE
    if left_min >= left and right_max <= right:
        return ConnectorMaskStatus.INSIDE
    return ConnectorMaskStatus.NEEDS_CLIPPING


def connector_span_length(
    start_lane: float,
    start_size: float,
    start_travel: float,
    end_lane: float,
    end_size: float,
    end_travel: float,
    head_transform: StageTransform | None = None,
    tail_transform: StageTransform | None = None,
    start_interp_frac: float = 0.0,
    end_interp_frac: float = 1.0,
    *,
    has_transform: bool = True,
    transforms_equal: bool | None = None,
) -> float:
    """Estimate the guide's span from its projected endpoint edges."""
    if (
        not has_transform
        or head_transform is None
        or tail_transform is None
        or (head_transform == tail_transform if transforms_equal is None else transforms_equal)
    ):
        start_width = tilt_width_factor(start_travel) * DynamicLayout.w_scale
        end_width = tilt_width_factor(end_travel) * DynamicLayout.w_scale
        left_change = (end_lane - end_size) * end_width - (start_lane - start_size) * start_width
        right_change = (end_lane + end_size) * end_width - (start_lane + start_size) * start_width
        y_change = (end_travel - start_travel) * DynamicLayout.h_scale
        if has_transform and head_transform is not None and tail_transform is not None:
            p = head_transform.projection
            if p.a00 != 1 or p.a01 != 0 or p.a10 != 0 or p.a11 != 1:
                camera_cos = cos(-DynamicLayout.rotate)
                camera_sin = sin(-DynamicLayout.rotate)
                left_x = left_change * camera_cos - y_change * camera_sin
                left_y = left_change * camera_sin + y_change * camera_cos
                right_x = right_change * camera_cos - y_change * camera_sin
                right_y = right_change * camera_sin + y_change * camera_cos
                return sqrt(
                    max(
                        (p.a00 * left_x + p.a01 * left_y) ** 2 + (p.a10 * left_x + p.a11 * left_y) ** 2,
                        (p.a00 * right_x + p.a01 * right_y) ** 2 + (p.a10 * right_x + p.a11 * right_y) ** 2,
                    )
                )
        # Fixed rotations and translations do not change the edge lengths.
        return sqrt(max(left_change**2, right_change**2) + y_change**2)

    start_transform = blend_stage_transform(head_transform, tail_transform, start_interp_frac).to_screen_transform()
    end_transform = blend_stage_transform(head_transform, tail_transform, end_interp_frac).to_screen_transform()
    segment = st_slide_connector_segment(
        start_lane,
        start_size,
        start_travel,
        end_lane,
        end_size,
        end_travel,
        start_transform,
        end_transform,
    )
    return max((segment.tl - segment.bl).magnitude, (segment.tr - segment.br).magnitude)


def connector_segment_count(geometry_detail: float, alpha_range: float, quality: float, path_length: float) -> int:
    geometry_count = ceil(geometry_detail * quality)
    alpha_detail = alpha_range * quality / (2 * CONNECTOR_ALPHA_ERROR)
    alpha_count = ceil(alpha_detail)
    scaled_length = path_length * quality
    nominal_count = scaled_length / CONNECTOR_ALPHA_SEGMENT_LENGTH
    if nominal_count < alpha_count:
        error_ratio = max(1, alpha_detail / max(1, nominal_count))
        alpha_count = floor(min(alpha_count, nominal_count * sqrt(error_ratio)))
    return max(1, floor(min(max(geometry_count, alpha_count), scaled_length / CONNECTOR_MIN_SEGMENT_LENGTH)))


def draw_connector_default_segment(
    visual_state: ConnectorVisualState,
    normal_sprite: Sprite,
    active_sprite: Sprite,
    z_normal: ZIndexes,
    z_active: ZIndexes,
    base_a: float,
    segment_head_target_time: float,
    start_lane: float,
    start_size: float,
    start_travel: float,
    start_interp_frac: float,
    end_lane: float,
    end_size: float,
    end_travel: float,
    end_interp_frac: float,
    has_transform: bool,
    head_transform: StageTransform | None,
    tail_transform: StageTransform | None,
    render_cache: ConnectorRenderCache,
    cache_edges: bool = False,
    ease_over_elevation: bool = False,
    elevation_transform: ElevationTransform | None = None,
    start_elevation_frac: float = 0.0,
    end_elevation_frac: float = 1.0,
):
    if base_a <= 0:
        render_cache.edge_valid = False
        return
    layout = +Quad
    segment_z_normal = +z_normal
    segment_z_active = +z_active
    if not cache_edges and not has_transform:
        layout @= layout_slide_connector_segment(start_lane, start_size, start_travel, end_lane, end_size, end_travel)
    else:
        # The draw loop invalidates this edge at clipped spans and invisible gaps.
        if not cache_edges or not render_cache.edge_valid:
            render_cache.update_edge(
                start_lane,
                start_size,
                start_travel,
                start_interp_frac,
                has_transform,
                head_transform,
                tail_transform,
                ease_over_elevation,
                elevation_transform,
                start_elevation_frac,
            )
        start_left = +render_cache.left
        start_right = +render_cache.right
        start_elevation = render_cache.elevation
        render_cache.update_edge(
            end_lane,
            end_size,
            end_travel,
            end_interp_frac,
            has_transform,
            head_transform,
            tail_transform,
            ease_over_elevation,
            elevation_transform,
            end_elevation_frac,
        )
        if has_transform:
            # Keep the segment below both endpoint notes without accumulating depth offsets.
            elevation = min(start_elevation, render_cache.elevation)
            segment_z_normal.z2 += elevation
            segment_z_active.z2 += elevation
        if start_travel >= end_travel:
            layout @= Quad(bl=start_left, br=start_right, tl=render_cache.left, tr=render_cache.right)
        else:
            layout @= Quad(bl=render_cache.left, br=render_cache.right, tl=start_left, tr=start_right)

    draw_connector_quad(
        layout,
        visual_state,
        normal_sprite,
        active_sprite,
        segment_z_normal,
        segment_z_active,
        base_a,
        segment_head_target_time,
    )


def draw_connector_masked_segment(
    visual_state: ConnectorVisualState,
    normal_sprite: Sprite,
    active_sprite: Sprite,
    z_normal: ZIndexes,
    z_active: ZIndexes,
    base_a: float,
    segment_head_target_time: float,
    start_lane: float,
    start_size: float,
    start_travel: float,
    start_interp_frac: float,
    end_lane: float,
    end_size: float,
    end_travel: float,
    end_interp_frac: float,
    has_transform: bool,
    head_transform: StageTransform | None,
    tail_transform: StageTransform | None,
    render_cache: ConnectorRenderCache,
    head_mask: VisualMask,
    tail_mask: VisualMask,
    same_mask_stage: bool,
    ease_over_elevation: bool = False,
    elevation_transform: ElevationTransform | None = None,
    start_elevation_frac: float = 0.0,
    end_elevation_frac: float = 1.0,
):
    # Clipping can move the endpoints, so the previous edge cannot be reused.
    render_cache.edge_valid = False
    if same_mask_stage:
        # Split where either connector edge crosses a mask bound so each subsegment is clipped exactly.
        split_fracs = VarArray[float, Dim[5]].new()
        split_fracs.append(1.0)
        start_left = start_lane - start_size
        end_left = end_lane - end_size
        start_right = start_lane + start_size
        end_right = end_lane + end_size
        left_min = min(start_left, end_left)
        left_max = max(start_left, end_left)
        right_min = min(start_right, end_right)
        right_max = max(start_right, end_right)
        if left_min < head_mask.left < left_max:
            split_fracs.append((head_mask.left - start_left) / (end_left - start_left))
        if left_min < head_mask.right < left_max:
            split_fracs.append((head_mask.right - start_left) / (end_left - start_left))
        if right_min < head_mask.left < right_max:
            split_fracs.append((head_mask.left - start_right) / (end_right - start_right))
        if right_min < head_mask.right < right_max:
            split_fracs.append((head_mask.right - start_right) / (end_right - start_right))
        split_fracs.sort()

        subsegment_start_lane, subsegment_start_size, subsegment_start_masked_size = masked_connector_extents_by_limits(
            start_lane,
            start_size,
            head_mask.left,
            head_mask.right,
        )
        subsegment_start_travel = start_travel
        subsegment_start_interp_frac = start_interp_frac
        subsegment_start_frac = 0.0
        for subsegment_end_frac in split_fracs:
            if subsegment_end_frac <= subsegment_start_frac:
                continue
            subsegment_end_unmasked_lane = lerp(start_lane, end_lane, subsegment_end_frac)
            subsegment_end_unmasked_size = lerp(start_size, end_size, subsegment_end_frac)
            subsegment_end_lane, subsegment_end_size, subsegment_end_masked_size = masked_connector_extents_by_limits(
                subsegment_end_unmasked_lane,
                subsegment_end_unmasked_size,
                head_mask.left,
                head_mask.right,
            )
            subsegment_end_travel = lerp(start_travel, end_travel, subsegment_end_frac)
            subsegment_end_interp_frac = lerp(start_interp_frac, end_interp_frac, subsegment_end_frac)
            if subsegment_start_masked_size > 0 or subsegment_end_masked_size > 0:
                draw_connector_default_segment(
                    visual_state=visual_state,
                    normal_sprite=normal_sprite,
                    active_sprite=active_sprite,
                    z_normal=z_normal,
                    z_active=z_active,
                    base_a=base_a,
                    segment_head_target_time=segment_head_target_time,
                    start_lane=subsegment_start_lane,
                    start_size=subsegment_start_size,
                    start_travel=subsegment_start_travel,
                    start_interp_frac=subsegment_start_interp_frac,
                    end_lane=subsegment_end_lane,
                    end_size=subsegment_end_size,
                    end_travel=subsegment_end_travel,
                    end_interp_frac=subsegment_end_interp_frac,
                    has_transform=has_transform,
                    head_transform=head_transform,
                    tail_transform=tail_transform,
                    render_cache=render_cache,
                    ease_over_elevation=ease_over_elevation,
                    elevation_transform=elevation_transform,
                    start_elevation_frac=lerp(start_elevation_frac, end_elevation_frac, subsegment_start_frac),
                    end_elevation_frac=lerp(start_elevation_frac, end_elevation_frac, subsegment_end_frac),
                )
            subsegment_start_frac = subsegment_end_frac
            subsegment_start_lane = subsegment_end_lane
            subsegment_start_size = subsegment_end_size
            subsegment_start_masked_size = subsegment_end_masked_size
            subsegment_start_travel = subsegment_end_travel
            subsegment_start_interp_frac = subsegment_end_interp_frac
    else:
        last_mask_left = lerp(head_mask.left, tail_mask.left, start_interp_frac)
        last_mask_right = lerp(head_mask.right, tail_mask.right, start_interp_frac)
        next_mask_left = lerp(head_mask.left, tail_mask.left, end_interp_frac)
        next_mask_right = lerp(head_mask.right, tail_mask.right, end_interp_frac)
        # Split moving-mask crossings so hidden endpoints cannot discard a visible interior.
        split_fracs = VarArray[float, Dim[6]].new()
        split_fracs.append(1.0)
        for distances in Array(
            Vec2(start_lane - start_size - last_mask_left, end_lane - end_size - next_mask_left),
            Vec2(start_lane - start_size - last_mask_right, end_lane - end_size - next_mask_right),
            Vec2(start_lane + start_size - last_mask_left, end_lane + end_size - next_mask_left),
            Vec2(start_lane + start_size - last_mask_right, end_lane + end_size - next_mask_right),
            Vec2(last_mask_right - last_mask_left, next_mask_right - next_mask_left),
        ):
            start_distance = distances.x
            end_distance = distances.y
            if min(start_distance, end_distance) < 0 < max(start_distance, end_distance):
                split_fracs.append(-start_distance / (end_distance - start_distance))
        split_fracs.sort()

        subsegment_start_lane, subsegment_start_size, subsegment_start_masked_size = masked_connector_extents_by_limits(
            start_lane,
            start_size,
            last_mask_left,
            last_mask_right,
        )
        subsegment_start_frac = 0.0
        subsegment_start_travel = start_travel
        subsegment_start_interp_frac = start_interp_frac
        for subsegment_end_frac in split_fracs:
            if subsegment_end_frac <= subsegment_start_frac:
                continue
            subsegment_end_lane, subsegment_end_size, subsegment_end_masked_size = masked_connector_extents_by_limits(
                lerp(start_lane, end_lane, subsegment_end_frac),
                lerp(start_size, end_size, subsegment_end_frac),
                lerp(last_mask_left, next_mask_left, subsegment_end_frac),
                lerp(last_mask_right, next_mask_right, subsegment_end_frac),
            )
            subsegment_end_travel = lerp(start_travel, end_travel, subsegment_end_frac)
            subsegment_end_interp_frac = lerp(start_interp_frac, end_interp_frac, subsegment_end_frac)
            if subsegment_start_masked_size > 0 or subsegment_end_masked_size > 0:
                draw_connector_default_segment(
                    visual_state=visual_state,
                    normal_sprite=normal_sprite,
                    active_sprite=active_sprite,
                    z_normal=z_normal,
                    z_active=z_active,
                    base_a=base_a,
                    segment_head_target_time=segment_head_target_time,
                    start_lane=subsegment_start_lane,
                    start_size=subsegment_start_size,
                    start_travel=subsegment_start_travel,
                    start_interp_frac=subsegment_start_interp_frac,
                    end_lane=subsegment_end_lane,
                    end_size=subsegment_end_size,
                    end_travel=subsegment_end_travel,
                    end_interp_frac=subsegment_end_interp_frac,
                    has_transform=has_transform,
                    head_transform=head_transform,
                    tail_transform=tail_transform,
                    render_cache=render_cache,
                    ease_over_elevation=ease_over_elevation,
                    elevation_transform=elevation_transform,
                    start_elevation_frac=lerp(start_elevation_frac, end_elevation_frac, subsegment_start_frac),
                    end_elevation_frac=lerp(start_elevation_frac, end_elevation_frac, subsegment_end_frac),
                )
            subsegment_start_frac = subsegment_end_frac
            subsegment_start_lane = subsegment_end_lane
            subsegment_start_size = subsegment_end_size
            subsegment_start_masked_size = subsegment_end_masked_size
            subsegment_start_travel = subsegment_end_travel
            subsegment_start_interp_frac = subsegment_end_interp_frac
    render_cache.edge_valid = False


def connector_is_off_screen(
    start_travel: float,
    end_travel: float,
    head_transform: StageTransform | None,
    tail_transform: StageTransform | None,
) -> bool:
    if DynamicLayout.rotate != 0:
        return False
    head_y_offset = 0.0
    tail_y_offset = 0.0
    if head_transform is not None:
        if head_transform.sr != 0 or head_transform.projection.elevation != 0:
            return False
        head_y_offset = head_transform.ty
    if tail_transform is not None:
        if tail_transform.sr != 0 or tail_transform.projection.elevation != 0:
            return False
        tail_y_offset = tail_transform.ty
    if head_y_offset != tail_y_offset:
        return False
    start_y = start_travel * DynamicLayout.h_scale + DynamicLayout.t + head_y_offset
    end_y = end_travel * DynamicLayout.h_scale + DynamicLayout.t + tail_y_offset
    return max(start_y, end_y) < screen().b or min(start_y, end_y) > screen().t


def clip_connector_progress_to_screen(
    start: float,
    end: float,
    head_transform: StageTransform | None,
    tail_transform: StageTransform | None,
    transforms_equal: bool | None = None,
) -> tuple[float, float]:
    """Trim the vertical span when screen y depends only on connector progress."""
    can_clip = DynamicLayout.rotate == 0 and (
        head_transform == tail_transform if transforms_equal is None else transforms_equal
    )
    y_offset = DynamicLayout.t
    y_scale = DynamicLayout.h_scale
    if head_transform is not None:
        if head_transform.sr != 0 or head_transform.projection.elevation != 0:
            can_clip = False
        y_offset += head_transform.ty
    if can_clip and abs(y_scale) >= 1e-8:
        start_travel = approach(start)
        end_travel = approach(end)
        # Leave a small margin for the numerical inverse at low stage tilt.
        screen_start = (screen().b - 1e-4 - y_offset) / y_scale
        screen_end = (screen().t + 1e-4 - y_offset) / y_scale
        travel_min = min(screen_start, screen_end)
        travel_max = max(screen_start, screen_end)
        if max(start_travel, end_travel) <= travel_min or min(start_travel, end_travel) >= travel_max:
            end = start
        else:
            # Only invert travel values within the connector's span. Values outside
            # the approach curve's domain, such as above the vanishing point, have no inverse.
            clipped_start = clamp(start_travel, travel_min, travel_max)
            clipped_end = clamp(end_travel, travel_min, travel_max)
            progress_min = min(start, end)
            progress_max = max(start, end)
            if clipped_start != start_travel:
                start = clamp(inverse_approach_tilt(clipped_start), progress_min, progress_max)
            if clipped_end != end_travel:
                end = clamp(inverse_approach_tilt(clipped_end), progress_min, progress_max)
    return start, end


CURVE_BINS = 16
CURVE_BIN_SAMPLES = 16
CURVE_LEVELS = 5
CURVE_TABLE_SIZE = sum(CURVE_BINS - 2**level + 1 for level in range(CURVE_LEVELS))


def _ease_derivative_bounds() -> Array:
    """Estimate slope and curvature bounds for each ease."""
    values = []
    h = 1e-4
    for ease_index in range(EaseType.OUT_IN_STEP + 1):
        ease_type = cast(EaseType, ease_index)
        curved = is_curved_ease(ease_type) or ease_type == EaseType.LINEAR
        for order in (1, 2):
            runs = []
            for i in range(CURVE_BINS):
                largest = 0.0
                for j in range(CURVE_BIN_SAMPLES + 1):
                    # Avoid jumps and vertical slopes at endpoints.
                    x = clamp((i + j / CURVE_BIN_SAMPLES) / CURVE_BINS, 1e-3, 1 - 1e-3)
                    if ease_type in (EaseType.OUT_IN_EXPO, EaseType.OUT_IN_ELASTIC) and x == 0.5:
                        # Keep midpoint samples on one side of the jump.
                        x = 0.5 - 2 * h if i < CURVE_BINS // 2 else 0.5 + 2 * h
                    before, at, after = (ease(ease_type, x + d) for d in (-h, 0, h)) if curved else (0, 0, 0)
                    derivative = (after - before) / (2 * h) if order == 1 else (after - 2 * at + before) / (h * h)
                    largest = max(largest, abs(derivative))
                runs.append(largest)
            level = [runs]
            while len(level[-1]) > 1:
                previous = level[-1]
                width = 2 ** (len(level) - 1)
                level.append([max(previous[i], previous[i + width]) for i in range(len(previous) - width)])
            values.extend(value for run in level for value in run)
    return Array(*values)


CURVE_DERIVATIVE_BOUNDS = _ease_derivative_bounds()


def ease_derivative_bound(ease_type: EaseType, order: int, start: float, end: float) -> float:
    first = cast(int, clamp(floor(start * CURVE_BINS), 0, CURVE_BINS - 1))
    last = cast(int, clamp(ceil(end * CURVE_BINS) - 1, first, CURVE_BINS - 1))
    run = 1
    offset = 0
    while run * 2 <= last - first + 1:
        offset += CURVE_BINS - run + 1
        run *= 2
    base = (ease_type * 2 + order - 1) * CURVE_TABLE_SIZE + offset
    return max(CURVE_DERIVATIVE_BOUNDS[base + first], CURVE_DERIVATIVE_BOUNDS[base + last - run + 1])


def connector_curve_detail(
    ease_type: EaseType,
    head_eased: float,
    tail_eased: float,
    start_ease_frac: float,
    end_ease_frac: float,
    left_change: float,
    right_change: float,
    start_travel: float,
    end_travel: float,
) -> float:
    """Estimate segments needed to limit visible curve error."""
    start_width = tilt_width_factor(start_travel)
    end_width = tilt_width_factor(end_travel)
    if (
        is_step_ease(ease_type)
        or (left_change == 0 and right_change == 0)
        or abs(tail_eased - head_eased) < 1e-6
        or min(start_width, end_width) <= 0
    ):
        return 0.0
    start = min(start_ease_frac, end_ease_frac)
    end = max(start_ease_frac, end_ease_frac)
    span = end - start
    lane_change = max(abs(left_change), abs(right_change)) / abs(tail_eased - head_eased)
    approach_rate = abs(log(end_width / start_width))
    width = max(start_width, end_width) * DynamicLayout.w_scale
    bend = span * ease_derivative_bound(ease_type, 2, start, end) + approach_rate * ease_derivative_bound(
        ease_type, 1, start, end
    )
    return sqrt(width * lane_change * span * bend / (8 * CONNECTOR_CURVE_ERROR))


def circular_connector_ease(ease_type: EaseType, frac: float) -> float:
    if ease_type == EaseType.IN_CIRC:
        return ease_in_circ(frac)
    if ease_type == EaseType.OUT_CIRC:
        return ease_out_circ(frac)
    if ease_type == EaseType.IN_OUT_CIRC:
        return ease_in_out_circ(frac)
    return ease_out_in_circ(frac)


class CircularConnectorSpan(Record):
    end: float
    travel: float
    interp: float
    depth: int
    middle_travel: float
    middle_interp: float


def connector_edge_distance_squared(point: Vec2, start: Vec2, end: Vec2) -> float:
    delta = end - start
    offset = point - start
    length_squared = delta.dot(delta)
    frac = clamp(offset.dot(delta) / length_squared, 0, 1) if length_squared > 0 else 0.0
    residual = offset - delta * frac
    return residual.dot(residual)


def circular_connector_fracs(
    result: VarArray[float, Dim[128]],
    ease_type: EaseType,
    start_ease_frac: float,
    end_ease_frac: float,
    start_progress: float,
    end_progress: float,
    head_lane: float,
    head_size: float,
    tail_lane: float,
    tail_size: float,
    head_eased: float,
    tail_eased: float,
    quality: float,
) -> None:
    """Approximate circular curves using their rendered screen edges."""
    result.clear()
    approach_cache = +ApproachCache
    approach_cache.prepare()

    def interp_at(frac: float) -> float:
        return safe_unlerp(
            head_eased, tail_eased, circular_connector_ease(ease_type, lerp(start_ease_frac, end_ease_frac, frac)), frac
        )

    def edges_at(travel: float, interp: float) -> tuple[Vec2, Vec2]:
        lane = lerp(head_lane, tail_lane, interp)
        size = lerp(head_size, tail_size, interp)
        if size <= 0:
            size = CONNECTOR_ZERO_SIZE_FALLBACK
        width = tilt_width_factor(travel) * DynamicLayout.w_scale
        y = travel * DynamicLayout.h_scale
        return Vec2((lane - size) * width, y), Vec2((lane + size) * width, y)

    # Depth-first traversal through depth 16 needs at most 17 pending spans.
    pending = +Array[CircularConnectorSpan, Dim[17]]
    first = 0.0
    first_travel = approach_cache.at(start_progress)
    first_left, first_right = edges_at(first_travel, interp_at(0.0))
    last_travel = approach_cache.at(end_progress)
    middle_travel = approach_cache.at(lerp(start_progress, end_progress, 0.5))
    pending.set_unchecked(
        0,
        CircularConnectorSpan(
            1.0,
            last_travel,
            interp_at(1.0),
            0,
            middle_travel,
            interp_at(0.5),
        ),
    )
    pending_count = 1
    tolerance = CONNECTOR_CURVE_ERROR / (2 * quality * quality)
    while pending_count > 0:
        pending_count -= 1
        # Copy before the child writes reuse this slot.
        span = +pending.get_unchecked(pending_count)
        last, last_travel, depth = span.end, span.travel, span.depth
        middle_travel, middle_interp = span.middle_travel, span.middle_interp
        last_left, last_right = edges_at(last_travel, span.interp)
        middle_left, middle_right = edges_at(middle_travel, middle_interp)
        error_squared = max(
            connector_edge_distance_squared(middle_left, first_left, last_left),
            connector_edge_distance_squared(middle_right, first_right, last_right),
        )
        left_middle_travel = 0.0
        left_middle_interp = 0.0
        right_middle_travel = 0.0
        right_middle_interp = 0.0
        for sample in Array(0.25, 0.75):
            frac = lerp(first, last, sample)
            travel = approach_cache.at(lerp(start_progress, end_progress, frac))
            interp = interp_at(frac)
            left, right = edges_at(travel, interp)
            error_squared = max(
                error_squared,
                connector_edge_distance_squared(left, first_left, last_left),
                connector_edge_distance_squared(right, first_right, last_right),
            )
            if sample == 0.25:
                left_middle_travel = travel
                left_middle_interp = interp
            else:
                right_middle_travel = travel
                right_middle_interp = interp
        if error_squared <= tolerance * tolerance or depth >= 16:
            result.append(last)
            # Reuse this endpoint as the next span's start.
            first = last
            first_left @= last_left
            first_right @= last_right
        else:
            if len(result) + pending_count + 2 > 128:
                result.clear()
                return
            middle = (first + last) / 2
            # Parent quarter samples become the children's midpoints.
            pending.set_unchecked(
                pending_count,
                CircularConnectorSpan(
                    last, last_travel, span.interp, depth + 1, right_middle_travel, right_middle_interp
                ),
            )
            pending.set_unchecked(
                pending_count + 1,
                CircularConnectorSpan(
                    middle, middle_travel, middle_interp, depth + 1, left_middle_travel, left_middle_interp
                ),
            )
            pending_count += 2


def _connector_ease_turns() -> tuple[Array, Array]:
    # Derivative zeros of the SDK Back/Elastic curves, with compound joins.
    def elastic_roots(rate: float, frequency: float, phase: float, lower: float, upper: float) -> list[float]:
        angle = atan2(-frequency, rate)
        return [
            (angle + index * pi - phase) / frequency
            for index in range(-30, 31)
            if lower < (angle + index * pi - phase) / frequency < upper
        ]

    rate = 10 * log(2)
    c4, c5 = 2 * pi / 3, 2 * pi / 4.5
    back = 2 * 1.70158 / (3 * 2.70158)
    back_in_out = 2 * (1.70158 * 1.525) / (3 * (1.70158 * 1.525 + 1))
    rows = (
        [back],
        [1 - back],
        [back_in_out / 2, 0.5, 1 - back_in_out / 2],
        [(1 - back) / 2, 0.5, (1 + back) / 2],
        # Zero crossings expose the small lobes beside pinned endpoints.
        [0.025, *elastic_roots(rate, 10 * c4, -10.75 * c4, 0, 1)],
        [*elastic_roots(-rate, 10 * c4, -0.75 * c4, 0, 1), 0.975],
        [
            *elastic_roots(2 * rate, 20 * c5, -11.125 * c5, 0, 0.5),
            0.5,
            *elastic_roots(-2 * rate, 20 * c5, -11.125 * c5, 0.5, 1),
        ],
        [
            *elastic_roots(-2 * rate, 20 * c4, -0.75 * c4, 0, 0.5),
            0.5,
            *elastic_roots(2 * rate, 20 * c4, -20.75 * c4, 0.5, 1),
        ],
    )
    values: list[float] = []
    offsets = [0]
    for row in rows:
        values.extend(unpack("f", pack("f", value))[0] for value in row)
        offsets.append(len(values))
    return Array(*values), Array(*offsets)


CONNECTOR_EASE_TURNS, CONNECTOR_EASE_TURN_OFFSETS = _connector_ease_turns()


class ElevationConnectorSample(Record):
    left: Vec2
    right: Vec2
    raw_left: Vec2
    raw_right: Vec2
    rotation: float


class ElevationConnectorSpan(Record):
    end: float
    sample: ElevationConnectorSample
    middle: ElevationConnectorSample
    depth: int


def elevation_connector_edge_error(first: Vec2, last: Vec2, quarter: Vec2, middle: Vec2, three_quarters: Vec2) -> float:
    dx, dy = last.x - first.x, last.y - first.y
    length_squared = dx * dx + dy * dy
    previous = 0.0
    error_squared = 0.0
    for point in Array(quarter, middle, three_quarters):
        px, py = point.x - first.x, point.y - first.y
        projection = (px * dx + py * dy) / length_squared if length_squared > 0 else 0.0
        if projection < previous - 1e-12 or projection > 1 + 1e-12:
            return inf
        previous = projection
        frac = clamp(projection, 0, 1)
        error_squared = max(error_squared, (px - dx * frac) ** 2 + (py - dy * frac) ** 2)
    return error_squared


def elevation_connector_fracs(
    result: VarArray[float, Dim[128]],
    ease_type: EaseType,
    head_eased: float,
    tail_eased: float,
    start_ease_frac: float,
    end_ease_frac: float,
    start_visual_progress: float,
    end_visual_progress: float,
    head_lane: float,
    head_size: float,
    tail_lane: float,
    tail_size: float,
    elevation_start_frac: float,
    elevation_end_frac: float,
    start_frac: float,
    end_frac: float,
    elevation_transform: ElevationTransform,
    quality: float,
    constant_interp_frac: float,
    minimum_detail: float = 0.0,
    head_mask: VisualMask | None = None,
    tail_mask: VisualMask | None = None,
) -> None:
    """Sample projected connector edges, including stage transforms."""
    result.clear()
    if quality <= 0:
        result.append(1.0)
        return

    mask_enabled = False
    if head_mask is not None and tail_mask is not None:
        mask_enabled = head_mask.enabled and tail_mask.enabled
    constant_progress = start_visual_progress == end_visual_progress
    fixed_width = 0.0
    fixed_y = 0.0
    approach_cache = +ApproachCache
    if constant_progress:
        travel = approach(start_visual_progress)
        fixed_width = tilt_width_factor(travel) * DynamicLayout.w_scale
        fixed_y = travel * DynamicLayout.h_scale + DynamicLayout.t
    else:
        approach_cache.prepare()

    def edges_at(frac: float) -> ElevationConnectorSample:
        global_frac = lerp(start_frac, end_frac, frac)
        interp_frac = constant_interp_frac
        if interp_frac < 0:
            interp_frac = get_connector_interp_frac_from_eased_endpoints(
                ease_type, head_eased, tail_eased, lerp(start_ease_frac, end_ease_frac, frac), global_frac
            )
        lane = lerp(head_lane, tail_lane, interp_frac)
        size = lerp(head_size, tail_size, interp_frac)
        if size <= 0:
            size = CONNECTOR_ZERO_SIZE_FALLBACK
        width = fixed_width
        y = fixed_y
        if not constant_progress:
            travel = approach_cache.at(lerp(start_visual_progress, end_visual_progress, frac))
            width = tilt_width_factor(travel) * DynamicLayout.w_scale
            y = travel * DynamicLayout.h_scale + DynamicLayout.t
        stage = elevation_transform(interp_frac, lerp(elevation_start_frac, elevation_end_frac, global_frac))
        transform = stage.to_screen_transform()
        raw_left = transform.apply(
            Vec2((lane - size) * width + DynamicLayout.x_translate, y).rotate(-DynamicLayout.rotate)
        )
        raw_right = transform.apply(
            Vec2((lane + size) * width + DynamicLayout.x_translate, y).rotate(-DynamicLayout.rotate)
        )
        left = alloc(Vec2)
        right = alloc(Vec2)
        if head_mask is not None and tail_mask is not None and mask_enabled:
            mask_left = lerp(head_mask.left, tail_mask.left, interp_frac)
            mask_right = lerp(head_mask.right, tail_mask.right, interp_frac)
            left_lane = clamp(lane - size, mask_left, mask_right)
            right_lane = clamp(lane + size, mask_left, mask_right)
            left @= transform.apply(
                Vec2(left_lane * width + DynamicLayout.x_translate, y).rotate(-DynamicLayout.rotate)
            )
            right @= transform.apply(
                Vec2(right_lane * width + DynamicLayout.x_translate, y).rotate(-DynamicLayout.rotate)
            )
        else:
            left @= raw_left
            right @= raw_right
        return ElevationConnectorSample(left, right, raw_left, raw_right, stage.sr)

    turn_first = 0
    turn_end = 0
    if (
        EaseType.IN_BACK <= ease_type <= EaseType.OUT_IN_ELASTIC
        and constant_interp_frac < 0
        and abs(tail_eased - head_eased) >= 1e-6
        and start_ease_frac != end_ease_frac
    ):
        index = ease_type - EaseType.IN_BACK
        turn_first = cast(int, CONNECTOR_EASE_TURN_OFFSETS.get_unchecked(index))
        turn_end = cast(int, CONNECTOR_EASE_TURN_OFFSETS.get_unchecked(index + 1))
        lower = min(start_ease_frac, end_ease_frac)
        upper = max(start_ease_frac, end_ease_frac)
        while turn_first < turn_end and CONNECTOR_EASE_TURNS.get_unchecked(turn_first) <= lower:
            turn_first += 1
        while turn_first < turn_end and CONNECTOR_EASE_TURNS.get_unchecked(turn_end - 1) >= upper:
            turn_end -= 1
    turn_index = turn_first
    turn_step = 1
    if end_ease_frac < start_ease_frac:
        turn_index = turn_end - 1
        turn_step = -1
    remaining_turns = turn_end - turn_first
    pending = alloc(Array[ElevationConnectorSpan, Dim[17]])
    first = 0.0
    first_sample = edges_at(first)
    tolerance = CONNECTOR_CURVE_ERROR / (2 * quality * quality)
    while remaining_turns >= 0:
        last = 1.0
        if remaining_turns > 0:
            last = (CONNECTOR_EASE_TURNS.get_unchecked(turn_index) - start_ease_frac) / (
                end_ease_frac - start_ease_frac
            )
            turn_index += turn_step
        pending.set_unchecked(0, ElevationConnectorSpan(last, edges_at(last), edges_at((first + last) / 2), 0))
        pending_count = 1
        while pending_count > 0:
            pending_count -= 1
            # Copy before the child writes reuse this slot.
            span = +pending.get_unchecked(pending_count)
            last, depth = span.end, span.depth
            final, middle = span.sample, span.middle
            left_middle = edges_at(lerp(first, last, 0.25))
            right_middle = edges_at(lerp(first, last, 0.75))
            error_squared = max(
                elevation_connector_edge_error(
                    first_sample.left, final.left, left_middle.left, middle.left, right_middle.left
                ),
                elevation_connector_edge_error(
                    first_sample.right, final.right, left_middle.right, middle.right, right_middle.right
                ),
            )
            if mask_enabled:
                # Raw edges detect curves entering the mask between samples.
                error_squared = max(
                    error_squared,
                    elevation_connector_edge_error(
                        first_sample.raw_left,
                        final.raw_left,
                        left_middle.raw_left,
                        middle.raw_left,
                        right_middle.raw_left,
                    ),
                    elevation_connector_edge_error(
                        first_sample.raw_right,
                        final.raw_right,
                        left_middle.raw_right,
                        middle.raw_right,
                        right_middle.raw_right,
                    ),
                )
            min_rotation = min(
                first_sample.rotation, final.rotation, left_middle.rotation, middle.rotation, right_middle.rotation
            )
            max_rotation = max(
                first_sample.rotation, final.rotation, left_middle.rotation, middle.rotation, right_middle.rotation
            )
            if (
                error_squared <= tolerance * tolerance
                # Unwrapped angles prevent full turns from aliasing all samples.
                and max_rotation - min_rotation <= pi / 4
                and (last - first) * minimum_detail <= 1
            ) or depth >= 16:
                result.append(last)
                first = last
                first_sample @= final
            elif len(result) + pending_count + remaining_turns + 2 > 128:
                # Fall back to uniform sampling across the full curve.
                result.clear()
                for index in range(128):
                    result.append((index + 1) / 128)
                return
            else:
                # Parent quarter samples become the children's midpoints.
                pending.set_unchecked(pending_count, ElevationConnectorSpan(last, final, right_middle, depth + 1))
                pending.set_unchecked(
                    pending_count + 1, ElevationConnectorSpan((first + last) / 2, middle, left_middle, depth + 1)
                )
                pending_count += 2
        remaining_turns -= 1


def draw_connector_default(
    kind: ConnectorKind,
    visual_state: ConnectorVisualState,
    segment_head_target_time: float,
    ease_type: EaseType,
    normal_sprite: Sprite,
    active_sprite: Sprite,
    z_normal: ZIndexes,
    z_active: ZIndexes,
    head_lane: float,
    head_size: float,
    head_visual_progress: float,
    head_target_time: float,
    head_ease_frac: float,
    head_alpha: float,
    tail_lane: float,
    tail_size: float,
    tail_visual_progress: float,
    tail_target_time: float,
    tail_ease_frac: float,
    tail_alpha: float,
    head_transform: StageTransform | None = None,
    tail_transform: StageTransform | None = None,
    head_mask: VisualMask | None = None,
    tail_mask: VisualMask | None = None,
    shared_transform: bool = False,
    constant_interp_frac: float = -1.0,
    ease_over_elevation: bool = False,
    elevation_transform: ElevationTransform | None = None,
    elevation_start_frac: float = 0.0,
    elevation_end_frac: float = 1.0,
    base_kind: BaseConnectorKind | None = None,
):
    start_visual_progress = clamp(head_visual_progress, DynamicLayout.progress_start, DynamicLayout.progress_cutoff)
    end_visual_progress = clamp(tail_visual_progress, DynamicLayout.progress_start, DynamicLayout.progress_cutoff)
    elevation_dynamic = ease_over_elevation and not shared_transform
    transforms_equal = not elevation_dynamic and (shared_transform or head_transform == tail_transform)
    if not elevation_dynamic:
        start_visual_progress, end_visual_progress = clip_connector_progress_to_screen(
            start_visual_progress, end_visual_progress, head_transform, tail_transform, transforms_equal
        )
    if start_visual_progress == end_visual_progress and (
        transforms_equal or head_visual_progress != tail_visual_progress
    ):
        return
    start_frac = safe_unlerp_clamped(head_visual_progress, tail_visual_progress, start_visual_progress, 0.0)
    end_frac = safe_unlerp_clamped(head_visual_progress, tail_visual_progress, end_visual_progress, 1.0)
    start_ease_frac = lerp(head_ease_frac, tail_ease_frac, start_frac)
    end_ease_frac = lerp(head_ease_frac, tail_ease_frac, end_frac)
    head_eased = connector_endpoint_ease(ease_type, head_ease_frac)
    tail_eased = connector_endpoint_ease(ease_type, tail_ease_frac)
    start_interp_frac = constant_interp_frac
    end_interp_frac = constant_interp_frac
    if constant_interp_frac < 0:
        start_interp_frac = get_connector_interp_frac_from_eased_endpoints(
            ease_type, head_eased, tail_eased, start_ease_frac, start_frac
        )
        end_interp_frac = get_connector_interp_frac_from_eased_endpoints(
            ease_type, head_eased, tail_eased, end_ease_frac, end_frac
        )
    start_travel = approach(start_visual_progress)
    end_travel = approach(end_visual_progress)
    start_lane = lerp(head_lane, tail_lane, start_interp_frac)
    end_lane = lerp(head_lane, tail_lane, end_interp_frac)
    start_size = lerp(head_size, tail_size, start_interp_frac)
    end_size = lerp(head_size, tail_size, end_interp_frac)
    if head_size <= 0 and tail_size <= 0:
        return
    start_alpha = lerp(head_alpha, tail_alpha, start_frac)
    end_alpha = lerp(head_alpha, tail_alpha, end_frac)
    alpha_option = get_connector_alpha_option(kind, base_kind=base_kind)
    if alpha_option <= 0 or max(start_alpha, end_alpha) <= 0:
        return
    if not elevation_dynamic and connector_is_off_screen(
        start_travel,
        end_travel,
        head_transform,
        tail_transform,
    ):
        return
    mask_enabled = False
    same_mask_stage = False
    if head_mask is not None and tail_mask is not None:
        mask_enabled = head_mask.enabled and tail_mask.enabled
        same_mask_stage = mask_enabled and head_mask.stage_index > 0 and head_mask.stage_index == tail_mask.stage_index
    if same_mask_stage and ease_overshoot(ease_type) == 0:
        assert head_mask is not None
        # Edges stay between their endpoints when the easing does not overshoot.
        mask_status = connector_mask_status(start_lane, start_size, end_lane, end_size, head_mask.left, head_mask.right)
        if mask_status == ConnectorMaskStatus.OUTSIDE:
            return
        if mask_status == ConnectorMaskStatus.INSIDE:
            mask_enabled = False

    vertical_span = abs((end_travel - start_travel) * DynamicLayout.h_scale)
    has_transform = elevation_dynamic or (
        head_transform is not None
        and tail_transform is not None
        and not (
            stage_transform_is_identity(head_transform)
            and (transforms_equal or stage_transform_is_identity(tail_transform))
        )
    )
    constant_transform = has_transform and transforms_equal
    heterogeneous_endpoints = (has_transform and not constant_transform) or (mask_enabled and not same_mask_stage)
    geometry_detail = 20.0
    quality = get_connector_quality_option(kind, base_kind=base_kind)
    circular_fracs = alloc(VarArray[float, Dim[128]])
    circular_fracs.clear()
    if ease_over_elevation and quality > 0:
        assert elevation_transform is not None
        elevation_connector_fracs(
            circular_fracs,
            ease_type,
            head_eased,
            tail_eased,
            start_ease_frac,
            end_ease_frac,
            start_visual_progress,
            end_visual_progress,
            head_lane,
            head_size,
            tail_lane,
            tail_size,
            elevation_start_frac,
            elevation_end_frac,
            start_frac,
            end_frac,
            elevation_transform,
            quality,
            constant_interp_frac,
            0.0
            if min(start_alpha, end_alpha) * alpha_option >= 1
            else abs(end_alpha - start_alpha) * alpha_option * quality / (2 * CONNECTOR_ALPHA_ERROR),
            head_mask,
            tail_mask,
        )
    elif (
        EaseType.IN_CIRC <= ease_type <= EaseType.OUT_IN_CIRC
        and quality > 0
        and constant_interp_frac < 0
        and not has_transform
        and not mask_enabled
        and abs(tail_eased - head_eased) >= 1e-6
        and (
            head_alpha == tail_alpha
            or min(start_alpha, end_alpha) * alpha_option >= 1
            or abs(end_alpha - start_alpha) * alpha_option * quality <= 2 * CONNECTOR_ALPHA_ERROR
        )
    ):
        circular_connector_fracs(
            circular_fracs,
            ease_type,
            start_ease_frac,
            end_ease_frac,
            start_visual_progress,
            end_visual_progress,
            head_lane,
            head_size,
            tail_lane,
            tail_size,
            head_eased,
            tail_eased,
            quality,
        )
    if len(circular_fracs) > 0:
        geometry_detail = len(circular_fracs) / quality
    elif not heterogeneous_endpoints:
        geometry_detail = connector_curve_detail(
            ease_type,
            head_eased,
            tail_eased,
            start_ease_frac,
            end_ease_frac,
            tail_lane - tail_size - (head_lane - head_size),
            tail_lane + tail_size - (head_lane + head_size),
            start_travel,
            end_travel,
        )

    if (
        geometry_detail * quality <= 1
        and head_alpha == tail_alpha
        and (not has_transform or constant_transform)
        and not mask_enabled
    ):
        if start_size <= 0 and end_size <= 0:
            return
        layout = layout_slide_connector_segment(
            start_lane,
            start_size if start_size > 0 else CONNECTOR_ZERO_SIZE_FALLBACK,
            start_travel,
            end_lane,
            end_size if end_size > 0 else CONNECTOR_ZERO_SIZE_FALLBACK,
            end_travel,
        )
        midpoint_time = (
            lerp(head_target_time, tail_target_time, start_frac) + lerp(head_target_time, tail_target_time, end_frac)
        ) / 2
        base_a = clamp(get_alpha(midpoint_time) * (start_alpha + end_alpha) / 2 * alpha_option, 0, 1)
        if base_a > 0:
            if has_transform:
                assert head_transform is not None
                transform = head_transform.to_screen_transform()
                layout @= transform.transform_quad(layout)
                segment_z_normal = +z_normal
                segment_z_active = +z_active
                segment_z_normal.z2 += transform.elevation
                segment_z_active.z2 += transform.elevation
                draw_connector_quad(
                    layout,
                    visual_state,
                    normal_sprite,
                    active_sprite,
                    segment_z_normal,
                    segment_z_active,
                    base_a,
                    animation_start_time=segment_head_target_time,
                )
            else:
                draw_connector_quad(
                    layout,
                    visual_state,
                    normal_sprite,
                    active_sprite,
                    z_normal,
                    z_active,
                    base_a,
                    animation_start_time=segment_head_target_time,
                )
        return

    approach_cache = +ApproachCache
    approach_cache.prepare()
    path_length = inf
    alpha_range = abs(end_alpha - start_alpha) * alpha_option
    if min(start_alpha, end_alpha) * alpha_option >= 1:
        alpha_range = 0.0
    alpha_detail = alpha_range / (2 * CONNECTOR_ALPHA_ERROR)
    minimum_span = max(
        ceil(geometry_detail * quality) * CONNECTOR_MIN_SEGMENT_LENGTH,
        ceil(alpha_detail * quality) * CONNECTOR_ALPHA_SEGMENT_LENGTH,
    )
    if not heterogeneous_endpoints and (has_transform or vertical_span * quality < minimum_span):
        path_length = connector_span_length(
            start_lane,
            start_size,
            start_travel,
            end_lane,
            end_size,
            end_travel,
            head_transform,
            tail_transform,
            start_interp_frac,
            end_interp_frac,
            has_transform=has_transform,
            transforms_equal=transforms_equal,
        )
    last_travel = start_travel
    last_lane = start_lane
    last_size = start_size
    last_alpha = start_alpha
    last_target_time = lerp(head_target_time, tail_target_time, start_frac)
    last_interp_frac = start_interp_frac
    last_elevation_frac = lerp(elevation_start_frac, elevation_end_frac, start_frac)
    render_cache = ConnectorRenderCache.new()
    if has_transform:
        assert head_transform is not None
        assert tail_transform is not None
        render_cache.prepare_transform(head_transform, tail_transform, constant_transform)

    segment_count = connector_segment_count(geometry_detail, alpha_range, quality, path_length)
    if len(circular_fracs) > 0:
        segment_count = len(circular_fracs)
    # Use fewer segments where the curve bends less.
    piece_counts = VarArray[int, Dim[CONNECTOR_CURVE_PIECES]].new()
    geometry_count = ceil(geometry_detail * quality)
    if (
        not heterogeneous_endpoints
        and len(circular_fracs) == 0
        and geometry_count > CONNECTOR_CURVE_PIECE_THRESHOLD
        and geometry_count >= segment_count
    ):
        alpha_count = ceil(connector_segment_count(0.0, alpha_range, quality, path_length) / CONNECTOR_CURVE_PIECES)
        piece_start_travel = start_travel
        total = 0
        for piece in range(CONNECTOR_CURVE_PIECES):
            piece_end_travel = approach(
                lerp(start_visual_progress, end_visual_progress, (piece + 1) / CONNECTOR_CURVE_PIECES)
            )
            detail = connector_curve_detail(
                ease_type,
                head_eased,
                tail_eased,
                lerp(start_ease_frac, end_ease_frac, piece / CONNECTOR_CURVE_PIECES),
                lerp(start_ease_frac, end_ease_frac, (piece + 1) / CONNECTOR_CURVE_PIECES),
                tail_lane - tail_size - (head_lane - head_size),
                tail_lane + tail_size - (head_lane + head_size),
                piece_start_travel,
                piece_end_travel,
            )
            piece_counts.append(max(1, ceil(detail * quality), alpha_count))
            total += piece_counts[piece]
            piece_start_travel = piece_end_travel
        if total < segment_count:
            segment_count = total
        else:
            piece_counts.clear()
    if len(piece_counts) == 0:
        piece_counts.append(segment_count)
    cache_edges = segment_count > 1
    piece_size = 1 / len(piece_counts)
    for piece in range(len(piece_counts)):
        piece_start = piece * piece_size
        segment_size = piece_size / piece_counts[piece]
        for piece_segment in range(1, piece_counts[piece] + 1):
            segment_frac = piece_start + piece_segment * segment_size
            if len(circular_fracs) > 0:
                segment_frac = circular_fracs[piece_segment - 1]
            next_frac = lerp(start_frac, end_frac, segment_frac)
            next_elevation_frac = lerp(elevation_start_frac, elevation_end_frac, next_frac)
            next_ease_frac = lerp(start_ease_frac, end_ease_frac, segment_frac)
            next_interp_frac = constant_interp_frac
            if constant_interp_frac < 0:
                next_interp_frac = get_connector_interp_frac_from_eased_endpoints(
                    ease_type, head_eased, tail_eased, next_ease_frac, next_frac
                )
            next_visual_progress = lerp(start_visual_progress, end_visual_progress, segment_frac)
            next_travel = approach_cache.at(next_visual_progress)
            next_lane = lerp(head_lane, tail_lane, next_interp_frac)
            next_size = lerp(head_size, tail_size, next_interp_frac)
            next_alpha = lerp(head_alpha, tail_alpha, next_frac)
            next_target_time = lerp(head_target_time, tail_target_time, next_frac)

            opacity = get_alpha((last_target_time + next_target_time) / 2) * alpha_option
            base_a = clamp((last_alpha + next_alpha) / 2 * opacity, 0, 1)

            segment_mask_enabled = mask_enabled
            segment_visible = base_a > 0
            if segment_visible and mask_enabled and same_mask_stage:
                assert head_mask is not None
                mask_status = connector_mask_status(
                    last_lane, last_size, next_lane, next_size, head_mask.left, head_mask.right
                )
                segment_visible = mask_status != ConnectorMaskStatus.OUTSIDE
                segment_mask_enabled = mask_status == ConnectorMaskStatus.NEEDS_CLIPPING
            if not segment_visible:
                render_cache.edge_valid = False
            elif segment_mask_enabled:
                assert head_mask is not None
                assert tail_mask is not None
                draw_connector_masked_segment(
                    segment_head_target_time=segment_head_target_time,
                    visual_state=visual_state,
                    normal_sprite=normal_sprite,
                    active_sprite=active_sprite,
                    z_normal=z_normal,
                    z_active=z_active,
                    base_a=base_a,
                    start_lane=last_lane,
                    start_size=last_size,
                    start_travel=last_travel,
                    start_interp_frac=last_interp_frac,
                    end_lane=next_lane,
                    end_size=next_size,
                    end_travel=next_travel,
                    end_interp_frac=next_interp_frac,
                    has_transform=has_transform,
                    head_transform=head_transform,
                    tail_transform=tail_transform,
                    render_cache=render_cache,
                    head_mask=head_mask,
                    tail_mask=tail_mask,
                    same_mask_stage=same_mask_stage,
                    ease_over_elevation=ease_over_elevation,
                    elevation_transform=elevation_transform,
                    start_elevation_frac=last_elevation_frac,
                    end_elevation_frac=next_elevation_frac,
                )
            elif last_size > 0 or next_size > 0:
                # Give zero-width endpoints a small drawable width.
                draw_connector_default_segment(
                    segment_head_target_time=segment_head_target_time,
                    visual_state=visual_state,
                    normal_sprite=normal_sprite,
                    active_sprite=active_sprite,
                    z_normal=z_normal,
                    z_active=z_active,
                    base_a=base_a,
                    start_lane=last_lane,
                    start_size=last_size if last_size > 0 else CONNECTOR_ZERO_SIZE_FALLBACK,
                    start_travel=last_travel,
                    start_interp_frac=last_interp_frac,
                    end_lane=next_lane,
                    end_size=next_size if next_size > 0 else CONNECTOR_ZERO_SIZE_FALLBACK,
                    end_travel=next_travel,
                    end_interp_frac=next_interp_frac,
                    has_transform=has_transform,
                    head_transform=head_transform,
                    tail_transform=tail_transform,
                    render_cache=render_cache,
                    cache_edges=cache_edges,
                    ease_over_elevation=ease_over_elevation,
                    elevation_transform=elevation_transform,
                    start_elevation_frac=last_elevation_frac,
                    end_elevation_frac=next_elevation_frac,
                )

            else:
                render_cache.edge_valid = False

            last_travel = next_travel
            last_lane = next_lane
            last_size = next_size
            last_alpha = next_alpha
            last_target_time = next_target_time
            last_interp_frac = next_interp_frac
            last_elevation_frac = next_elevation_frac


def get_cross_fate_opacities(a, t, period):
    phase = (t % period) / period
    opacity2_base = 1 - abs(1 - 2 * phase)
    opacity1_base = 1 - opacity2_base
    correction = 0.6
    opacity1 = a * (opacity1_base + correction * opacity1_base * opacity2_base)
    opacity2 = a * (opacity2_base + correction * opacity1_base * opacity2_base)

    return opacity1, opacity2


def draw_connector_full_screen(
    kind: ConnectorKind,
    visual_state: ConnectorVisualState,
    normal_sprite: Sprite,
    active_sprite: Sprite,
    z_normal: ZIndexes,
    z_active: ZIndexes,
    head_target_time: float,
    head_alpha: float,
    tail_target_time: float,
    tail_alpha: float,
    base_kind: BaseConnectorKind | None = None,
):
    judge_frac = safe_unlerp_clamped(head_target_time, tail_target_time, time())
    judge_alpha = lerp(head_alpha, tail_alpha, judge_frac)
    base_a = clamp(get_alpha(time()) * judge_alpha * get_connector_alpha_option(kind, base_kind=base_kind), 0, 1)
    if base_a > 0:
        draw_connector_quad(screen(), visual_state, normal_sprite, active_sprite, z_normal, z_active, base_a)


def draw_connector_quad(
    layout: QuadLike,
    visual_state: ConnectorVisualState,
    normal_sprite: Sprite,
    active_sprite: Sprite,
    z_normal: ZIndexes,
    z_active: ZIndexes,
    base_a: float,
    animation_start_time: float = 0.0,
):
    if visual_state == ConnectorVisualState.ACTIVE and active_sprite.is_available:
        if Options.connector_animation:
            normal_alpha, active_alpha = get_cross_fate_opacities(base_a, time() - animation_start_time, 0.5)
            normal_sprite.draw(layout, z=z_normal.tuple, a=normal_alpha)
            active_sprite.draw(layout, z=z_active.tuple, a=active_alpha)
        else:
            normal_sprite.draw(layout, z=z_normal.tuple, a=base_a)
    else:
        normal_sprite.draw(
            layout, z=z_normal.tuple, a=base_a * (1 if visual_state != ConnectorVisualState.INACTIVE else 0.5)
        )


class ActiveConnectorInfo(Record):
    # Connector entity index plus one; zero means no selection.
    visual_connector_index: int
    visual_update_time: float
    input_bounds: Quad
    is_active: bool
    active_start_time: float
    connector_kind: ConnectorKind


def inactive_connector_sfx_times() -> ConnectorSfxTimes:
    return ConnectorSfxTimes(
        active_time=CONNECTOR_SFX_ACTIVE_TIME_INIT,
        inactive_time=CONNECTOR_SFX_INACTIVE_TIME_INIT,
    )


def init_connector_sfx_times():
    ConnectorSfxState.active_time = CONNECTOR_SFX_ACTIVE_TIME_INIT
    ConnectorSfxState.inactive_time = CONNECTOR_SFX_INACTIVE_TIME_INIT
    ConnectorSfxState.kind = ConnectorKind.NONE
    ConnectorSfxState.active_head_index = 0


def is_sfx_connector(kind: ConnectorKind) -> bool:
    return get_connector_base_kind(kind) in {
        ConnectorKind.ACTIVE_NORMAL,
        ConnectorKind.ACTIVE_CRITICAL,
        ConnectorKind.FAKE_ACTIVE_NORMAL,
        ConnectorKind.FAKE_ACTIVE_CRITICAL,
    }


def get_connector_sfx_kind(kind: ConnectorKind) -> ConnectorKind:
    if get_connector_base_kind(kind) in {ConnectorKind.ACTIVE_CRITICAL, ConnectorKind.FAKE_ACTIVE_CRITICAL}:
        return ConnectorKind.ACTIVE_CRITICAL
    return ConnectorKind.ACTIVE_NORMAL


def activate_connector_sfx(
    kind: ActiveConnectorKind,
    event_time: float,
    active_head_target_time: float,
    active_tail_target_time: float,
    active_head_index: int,
) -> ConnectorSfxTimes:
    sfx_time = clamp(event_time, active_head_target_time, active_tail_target_time)
    if ConnectorSfxState.inactive_time == CONNECTOR_SFX_INACTIVE_TIME_INIT:
        ConnectorSfxState.inactive_time = sfx_time
    ConnectorSfxState.active_time = sfx_time
    ConnectorSfxState.kind = get_connector_sfx_kind(kind)
    ConnectorSfxState.active_head_index = active_head_index
    return ConnectorSfxTimes(ConnectorSfxState.active_time, ConnectorSfxState.inactive_time)


def deactivate_connector_sfx(
    event_time: float,
    active_head_target_time: float,
    active_tail_target_time: float,
) -> ConnectorSfxTimes:
    ConnectorSfxState.inactive_time = clamp(event_time, active_head_target_time, active_tail_target_time)
    return ConnectorSfxTimes(ConnectorSfxState.active_time, ConnectorSfxState.inactive_time)


def connector_sfx_is_active(times: ConnectorSfxTimes) -> bool:
    return times.active_time >= times.inactive_time


def current_connector_sfx_is_active() -> bool:
    return (
        ConnectorSfxState.active_time >= ConnectorSfxState.inactive_time
        and offset_adjusted_time() >= ConnectorSfxState.active_time
    )


def update_circular_connector_particle(
    handle: ParticleHandle,
    kind: ActiveConnectorKind,
    lane: float,
    replace: bool,
    y_offset: float = 0.0,
    *,
    transform: StageScreenTransform,
):
    if not Options.note_effect_enabled:
        return
    layout = transform.transform_quad(layout_circular_effect(lane, w=3.5, h=2.1, y_offset=y_offset))
    if replace or handle.id == 0:
        particle = +Particle(-1)
        base_kind = get_connector_base_kind(kind)
        match base_kind:
            case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_NORMAL:
                particle @= ActiveParticles.normal_slide_connector.circular
                if get_connector_style(kind) != NoteStyle.DEFAULT:
                    particle @= get_styled_connector_particles(get_connector_style(kind), False).circular
            case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
                particle @= ActiveParticles.critical_slide_connector.circular
                if get_connector_style(kind) != NoteStyle.DEFAULT:
                    particle @= get_styled_connector_particles(get_connector_style(kind), True).circular
            case _:
                assert_never(base_kind)
        replace_looped_particle(handle, particle, layout, duration=1 / Options.effect_animation_speed)
    else:
        update_looped_particle(handle, layout)


def update_linear_connector_particle(
    handle: ParticleHandle,
    kind: ActiveConnectorKind,
    lane: float,
    replace: bool,
    y_offset: float = 0.0,
    *,
    transform: StageScreenTransform,
):
    if not Options.note_effect_enabled:
        return
    layout = transform.transform_billboard(
        layout_linear_effect(lane, shear=0, y_offset=y_offset), transformed_vec_at(lane, approach(1 - y_offset))
    )
    particle = +Particle
    if replace or handle.id == 0:
        base_kind = get_connector_base_kind(kind)
        match base_kind:
            case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_NORMAL:
                particle @= ActiveParticles.normal_slide_connector.linear
                if get_connector_style(kind) != NoteStyle.DEFAULT:
                    particle @= get_styled_connector_particles(get_connector_style(kind), False).linear
            case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
                particle @= ActiveParticles.critical_slide_connector.linear
                if get_connector_style(kind) != NoteStyle.DEFAULT:
                    particle @= get_styled_connector_particles(get_connector_style(kind), True).linear
            case _:
                assert_never(base_kind)
        replace_looped_particle(handle, particle, layout, duration=1 / Options.effect_animation_speed)
    else:
        update_looped_particle(handle, layout)


def spawn_linear_connector_trail_particle(
    kind: ActiveConnectorKind,
    lane: float,
    y_offset: float = 0.0,
    *,
    transform: StageScreenTransform,
):
    if not Options.note_effect_enabled:
        return
    layout = transform.transform_billboard(
        layout_linear_effect(lane, shear=0, y_offset=y_offset), transformed_vec_at(lane, approach(1 - y_offset))
    )
    particle = +Particle
    base_kind = get_connector_base_kind(kind)
    match base_kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_NORMAL:
            particle @= ActiveParticles.normal_slide_connector.trail_linear
            if get_connector_style(kind) != NoteStyle.DEFAULT:
                particle @= get_styled_connector_particles(get_connector_style(kind), False).trail_linear
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
            particle @= ActiveParticles.critical_slide_connector.trail_linear
            if get_connector_style(kind) != NoteStyle.DEFAULT:
                particle @= get_styled_connector_particles(get_connector_style(kind), True).trail_linear
        case _:
            assert_never(base_kind)
    particle.spawn(layout, duration=0.5 / Options.effect_animation_speed)


def spawn_connector_slot_particles(
    kind: ActiveConnectorKind,
    lane: float,
    size: float,
    y_offset: float = 0.0,
    *,
    transform: StageScreenTransform,
):
    if not Options.note_effect_enabled:
        return
    particle = +Particle
    base_kind = get_connector_base_kind(kind)
    match base_kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_NORMAL:
            particle @= ActiveParticles.normal_slide_connector.slot_linear
            if get_connector_style(kind) != NoteStyle.DEFAULT:
                particle @= get_styled_connector_particles(get_connector_style(kind), False).slot_linear
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
            particle @= ActiveParticles.critical_slide_connector.slot_linear
            if get_connector_style(kind) != NoteStyle.DEFAULT:
                particle @= get_styled_connector_particles(get_connector_style(kind), True).slot_linear
        case _:
            assert_never(base_kind)
    for slot_lane in iter_slot_lanes(lane, size):
        layout = transform.transform_billboard(
            layout_linear_effect(slot_lane, shear=0, y_offset=y_offset),
            transformed_vec_at(slot_lane, approach(1 - y_offset)),
        )
        if not quad_touches_screen(layout):
            continue
        particle.spawn(layout, duration=0.5 / Options.effect_animation_speed)


def draw_connector_slot_glow_effect(
    kind: ActiveConnectorKind,
    start_time: float,
    lane: float,
    size: float,
    y_offset: float = 0.0,
    *,
    transform: StageScreenTransform,
):
    if not Options.slot_effect_enabled:
        return
    sprite = +Sprite
    base_kind = get_connector_base_kind(kind)
    match base_kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_NORMAL:
            sprite @= ActiveSkin.active_slide_connector.slot_glow
            if get_connector_style(kind) != NoteStyle.DEFAULT:
                sprite @= get_styled_active_connector_sprites(get_connector_style(kind), False).slot_glow
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
            sprite @= ActiveSkin.critical_active_slide_connector.slot_glow
            if get_connector_style(kind) != NoteStyle.DEFAULT:
                sprite @= get_styled_active_connector_sprites(get_connector_style(kind), True).slot_glow
        case _:
            assert_never(base_kind)
    height = (
        0.85 + (1.2 - 0.85) * ((cos((time() - start_time) * 8 * pi) + 1) / 2)  # min + (max - min) * osc
        if LevelConfig.ui_version == Version.v3
        else 0.2 + (1.2 - 0.2) * ((sin((time() - start_time) * 2.5 * pi) + 1) / 2)
    )
    ex = 0.035 * abs(2 * size) + 0.08 if LevelConfig.ui_version == Version.v3 else 0
    layout = transform.transform_billboard(
        layout_slot_glow_effect(lane, size + ex, height, y_offset=y_offset),
        transformed_vec_at(lane, approach(1 - y_offset)),
    )
    if not quad_touches_screen(layout):
        return
    z = get_z(layers.slot_glow_effect, start_time, lane, elevation=transform.elevation, invert_time=True)
    a = remap_clamped(start_time, start_time + 0.25, 0.0, 0.25, time())
    lightweight = 0.25 if ActiveParticles.lightweight.is_available else 1
    sprite.draw(layout, z=z.tuple, a=a * lightweight)


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
    base_kind = get_connector_base_kind(kind)
    match base_kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_NORMAL:
            effect @= Effects.normal_hold
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
            effect @= Effects.critical_hold
        case _:
            assert_never(base_kind)
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
    base_kind = get_connector_base_kind(kind)
    match base_kind:
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_NORMAL:
            effect @= Effects.normal_hold
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
            effect @= Effects.critical_hold
        case _:
            assert_never(base_kind)
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


def schedule_connector_sfx_between(
    kind: ActiveConnectorKind,
    start_time: float,
    end_time: float,
):
    if not Options.sfx_enabled:
        return
    if end_time <= start_time:
        return
    effect = +Effect
    match get_connector_base_kind(kind):
        case ConnectorKind.ACTIVE_NORMAL | ConnectorKind.FAKE_ACTIVE_NORMAL:
            effect @= Effects.normal_hold
        case ConnectorKind.ACTIVE_CRITICAL | ConnectorKind.FAKE_ACTIVE_CRITICAL:
            effect @= Effects.critical_hold
        case _:
            assert_never(kind)
    schedule_looped_sfx(effect, start_time, end_time)


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
