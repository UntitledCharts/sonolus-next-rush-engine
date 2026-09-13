from math import trunc
from typing import Self

from sonolus.script.easing import ease_in_out_quad, ease_out_in_quad, ease_out_quad
from sonolus.script.record import Record

from sekai.lib.ease import EaseType


class TimePosition(Record):
    """Scaled time split into whole seconds and a signed fraction.

    Keeping the parts separate preserves small differences at large times.
    Whole seconds remain exact in f32 through 2**24. A stored fraction may
    round to -1 or 1.
    """

    whole: float
    fraction: float

    @staticmethod
    def of(value: float) -> TimePosition:
        whole = trunc(value)
        return TimePosition(whole, value - whole)

    def add(self, value: float) -> Self:
        # Truncate toward zero to preserve small negative fractions.
        whole = trunc(value)
        remainder = self.fraction + (value - whole)
        carry = trunc(remainder)
        return type(self)(self.whole + whole + carry, remainder - carry)

    def difference(self, other: Self) -> float:
        return (self.whole - other.whole) + (self.fraction - other.fraction)


def _ease(ease: int, u: float) -> float:
    if ease == EaseType.NONE:
        return 0.0
    if ease == EaseType.LINEAR:
        return u
    if ease == EaseType.IN_QUAD:
        # A direct square lets the optimizer combine surrounding multiplications.
        return u * u
    if ease == EaseType.OUT_QUAD:
        return ease_out_quad(u)
    if ease == EaseType.IN_OUT_QUAD:
        return ease_in_out_quad(u)
    assert ease == EaseType.OUT_IN_QUAD, "Unknown timescale easing"
    return ease_out_in_quad(u)


def _complement(ease: int) -> int:
    if ease == EaseType.IN_QUAD:
        return EaseType.OUT_QUAD
    if ease == EaseType.OUT_QUAD:
        return EaseType.IN_QUAD
    return ease


def speed_at(v0: float, v1: float, ease: int, start: float, end: float, t: float) -> float:
    if ease == EaseType.NONE or t <= start:
        return v0
    if t >= end:
        return v1
    if v1 >= v0:
        return v0 + (v1 - v0) * _ease(ease, (t - start) / (end - start))
    return v1 + (v0 - v1) * _ease(_complement(ease), (end - t) / (end - start))


def _piece(v0: float, v1: float, ease: int, span: float, left: float, right: float, width: float) -> float:
    # Evaluate falling curves from the lower speed to reduce rounding error.
    if v1 < v0:
        v0, v1 = v1, v0
        ease = _complement(ease)
        left, right = span - right, span - left
    first = left / span
    middle = first + width / span * 0.5
    last = right / span
    # The 1:4:1 weights give the exact average of a quadratic, apart from rounding.
    average_ease = (_ease(ease, first) + 4 * _ease(ease, middle) + _ease(ease, last)) / 6
    return width * (v0 + (v1 - v0) * average_ease)


def integrate_times(v0: float, v1: float, ease: int, start: float, end: float, left: float, right: float) -> float:
    if start == end or left == right:
        return 0.0
    orientation = 1.0
    if left > right:
        left, right = right, left
        orientation = -1.0
    width = right - left
    if ease == EaseType.NONE:
        return orientation * width * v0
    span = end - start
    lo, hi = left - start, right - start
    midpoint = span * 0.5
    if ease in (EaseType.IN_OUT_QUAD, EaseType.OUT_IN_QUAD) and lo < midpoint < hi:
        first = _piece(v0, v1, ease, span, lo, midpoint, midpoint - lo)
        last = _piece(v0, v1, ease, span, midpoint, hi, hi - midpoint)
        return orientation * (first + last)
    return orientation * _piece(v0, v1, ease, span, lo, hi, width)
