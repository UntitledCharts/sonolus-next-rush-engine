from enum import IntEnum

from sonolus.script.easing import (
    ease_in_back,
    ease_in_circ,
    ease_in_cubic,
    ease_in_elastic,
    ease_in_expo,
    ease_in_out_back,
    ease_in_out_circ,
    ease_in_out_cubic,
    ease_in_out_elastic,
    ease_in_out_expo,
    ease_in_out_quad,
    ease_in_out_quart,
    ease_in_out_quint,
    ease_in_out_sine,
    ease_in_quad,
    ease_in_quart,
    ease_in_quint,
    ease_in_sine,
    ease_out_back,
    ease_out_circ,
    ease_out_cubic,
    ease_out_elastic,
    ease_out_expo,
    ease_out_in_back,
    ease_out_in_circ,
    ease_out_in_cubic,
    ease_out_in_elastic,
    ease_out_in_expo,
    ease_out_in_quad,
    ease_out_in_quart,
    ease_out_in_quint,
    ease_out_in_sine,
    ease_out_quad,
    ease_out_quart,
    ease_out_quint,
    ease_out_sine,
    linstep,
)
from sonolus.script.interval import unlerp, unlerp_clamped


class EaseType(IntEnum):
    NONE = 0
    LINEAR = 1
    IN_QUAD = 2
    OUT_QUAD = 3
    IN_OUT_QUAD = 4
    OUT_IN_QUAD = 5
    IN_SINE = 6
    OUT_SINE = 7
    IN_OUT_SINE = 8
    OUT_IN_SINE = 9
    IN_CUBIC = 10
    OUT_CUBIC = 11
    IN_OUT_CUBIC = 12
    OUT_IN_CUBIC = 13
    IN_QUART = 14
    OUT_QUART = 15
    IN_OUT_QUART = 16
    OUT_IN_QUART = 17
    IN_QUINT = 18
    OUT_QUINT = 19
    IN_OUT_QUINT = 20
    OUT_IN_QUINT = 21
    IN_EXPO = 22
    OUT_EXPO = 23
    IN_OUT_EXPO = 24
    OUT_IN_EXPO = 25
    IN_CIRC = 26
    OUT_CIRC = 27
    IN_OUT_CIRC = 28
    OUT_IN_CIRC = 29
    IN_BACK = 30
    OUT_BACK = 31
    IN_OUT_BACK = 32
    OUT_IN_BACK = 33
    IN_ELASTIC = 34
    OUT_ELASTIC = 35
    IN_OUT_ELASTIC = 36
    OUT_IN_ELASTIC = 37
    IN_STEP = 38
    OUT_STEP = 39
    IN_OUT_STEP = 40
    OUT_IN_STEP = 41


class EaseFamily(IntEnum):
    QUAD = 0
    SINE = 1
    CUBIC = 2
    QUART = 3
    QUINT = 4
    EXPO = 5
    CIRC = 6
    BACK = 7
    ELASTIC = 8
    STEP = 9


class EaseMode(IntEnum):
    IN = 0
    OUT = 1
    IN_OUT = 2
    OUT_IN = 3


def ease_family(ease_type: EaseType) -> EaseFamily:
    return (ease_type - EaseType.IN_QUAD) // 4


def ease_mode(ease_type: EaseType) -> EaseMode:
    return (ease_type - EaseType.IN_QUAD) % 4


def is_curved_ease(ease_type: EaseType) -> bool:
    return EaseType.IN_QUAD <= ease_type <= EaseType.OUT_IN_ELASTIC


def is_step_ease(ease_type: EaseType) -> bool:
    return ease_type == EaseType.NONE or ease_type >= EaseType.IN_STEP


def is_in_step_ease(ease_type: EaseType) -> bool:
    return ease_type in (EaseType.NONE, EaseType.IN_STEP)


def in_out_step_jump_time(t_a: float, t_b: float) -> float:
    return (t_a + t_b) / 2


def in_out_step_progress(t: float, t_a: float, t_b: float, right_limit: bool, exact: bool = False) -> float:
    # Times within rounding error of the jump count as on it, unless exact.
    jump_time = in_out_step_jump_time(t_a, t_b)
    tolerance = min(max(1.0, abs(jump_time)) * 2**-21, (t_b - t_a) / 8)
    if exact:
        tolerance = 0.0
    if right_limit:
        return 1.0 if t >= jump_time - tolerance else 0.0
    return 1.0 if t > jump_time + tolerance else 0.0


def event_progress(
    ease_type: EaseType, t: float, t_a: float, t_b: float, right_limit: bool, exact: bool = False
) -> float:
    if ease_type == EaseType.IN_OUT_STEP:
        return in_out_step_progress(t, t_a, t_b, right_limit, exact)
    return ease(ease_type, (t - t_a) / (t_b - t_a))


def ease_overshoot(ease_type: EaseType) -> float:
    """Return an upper bound on easing overshoot."""
    if EaseType.IN_ELASTIC <= ease_type <= EaseType.OUT_IN_ELASTIC:
        return 0.374
    if EaseType.IN_BACK <= ease_type <= EaseType.OUT_IN_BACK:
        return 0.101
    return 0.0


def eased_range(a: float, b: float, ease_type: EaseType) -> tuple[float, float]:
    margin = ease_overshoot(ease_type) * abs(b - a)
    return min(a, b) - margin, max(a, b) + margin


def ease_complement(ease_type: EaseType) -> EaseType:
    """Return the easing for reversed endpoints."""
    if ease_type == EaseType.NONE:
        return EaseType.OUT_STEP
    if ease_type >= EaseType.IN_QUAD:
        if ease_mode(ease_type) == EaseMode.IN:
            return ease_type + 1
        if ease_mode(ease_type) == EaseMode.OUT:
            return ease_type - 1
    return ease_type


def safe_unlerp(a: float, b: float, x: float, fallback: float = 0.5) -> float:
    if abs(a - b) < 1e-6:
        return fallback
    return unlerp(a, b, x)


def safe_unlerp_clamped(a: float, b: float, x: float, fallback: float = 0.5) -> float:
    if abs(a - b) < 1e-6:
        return fallback
    return unlerp_clamped(a, b, x)


def ease(ease_type: EaseType, x: float) -> float:
    match ease_type:
        case EaseType.LINEAR:
            return linstep(x)
        case EaseType.IN_QUAD:
            return ease_in_quad(x)
        case EaseType.OUT_QUAD:
            return ease_out_quad(x)
        case EaseType.IN_OUT_QUAD:
            return ease_in_out_quad(x)
        case EaseType.OUT_IN_QUAD:
            return ease_out_in_quad(x)
        case EaseType.IN_SINE:
            return ease_in_sine(x)
        case EaseType.OUT_SINE:
            return ease_out_sine(x)
        case EaseType.IN_OUT_SINE:
            return ease_in_out_sine(x)
        case EaseType.OUT_IN_SINE:
            return ease_out_in_sine(x)
        case EaseType.IN_CUBIC:
            return ease_in_cubic(x)
        case EaseType.OUT_CUBIC:
            return ease_out_cubic(x)
        case EaseType.IN_OUT_CUBIC:
            return ease_in_out_cubic(x)
        case EaseType.OUT_IN_CUBIC:
            return ease_out_in_cubic(x)
        case EaseType.IN_QUART:
            return ease_in_quart(x)
        case EaseType.OUT_QUART:
            return ease_out_quart(x)
        case EaseType.IN_OUT_QUART:
            return ease_in_out_quart(x)
        case EaseType.OUT_IN_QUART:
            return ease_out_in_quart(x)
        case EaseType.IN_QUINT:
            return ease_in_quint(x)
        case EaseType.OUT_QUINT:
            return ease_out_quint(x)
        case EaseType.IN_OUT_QUINT:
            return ease_in_out_quint(x)
        case EaseType.OUT_IN_QUINT:
            return ease_out_in_quint(x)
        case EaseType.IN_EXPO:
            return ease_in_expo(x)
        case EaseType.OUT_EXPO:
            return ease_out_expo(x)
        case EaseType.IN_OUT_EXPO:
            return ease_in_out_expo(x)
        case EaseType.OUT_IN_EXPO:
            return ease_out_in_expo(x)
        case EaseType.IN_CIRC:
            return ease_in_circ(x)
        case EaseType.OUT_CIRC:
            return ease_out_circ(x)
        case EaseType.IN_OUT_CIRC:
            return ease_in_out_circ(x)
        case EaseType.OUT_IN_CIRC:
            return ease_out_in_circ(x)
        case EaseType.IN_BACK:
            return ease_in_back(x)
        case EaseType.OUT_BACK:
            return ease_out_back(x)
        case EaseType.IN_OUT_BACK:
            return ease_in_out_back(x)
        case EaseType.OUT_IN_BACK:
            return ease_out_in_back(x)
        case EaseType.IN_ELASTIC:
            return ease_in_elastic(x)
        case EaseType.OUT_ELASTIC:
            return ease_out_elastic(x)
        case EaseType.IN_OUT_ELASTIC:
            return ease_in_out_elastic(x)
        case EaseType.OUT_IN_ELASTIC:
            return ease_out_in_elastic(x)
        case _:
            # Steps keep their held value at 0 and 1.
            if x < 0:
                return 0.0
            if x > 1:
                return 1.0
            if ease_type == EaseType.OUT_STEP:
                return 1.0
            if ease_type == EaseType.IN_OUT_STEP:
                return 0.0 if x < 0.5 else 1.0
            if ease_type == EaseType.OUT_IN_STEP:
                return 0.5
            return 0.0
