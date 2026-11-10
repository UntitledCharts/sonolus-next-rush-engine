"""OpenSekai flick motion in calibrated Sonolus touch coordinates."""

from sonolus.script.vec import Vec2

SEKAI_REFERENCE_FRAME = 0.016667
SEKAI_FLICK_DISTANCE_CM = 0.083333


def flick_distance(short_side: float, short_side_cm: float) -> float:
    # Sonolus exposes no DPI. Calibrating the physical viewport length gives
    # the same pixels/cm conversion without coupling input to stage geometry.
    return short_side / max(short_side_cm, 1) * SEKAI_FLICK_DISTANCE_CM


def has_flick_motion(delta: Vec2, frame_delta: float, distance: float) -> bool:
    frame_scale = frame_delta / SEKAI_REFERENCE_FRAME if frame_delta > 0 else 1.0
    return delta.dot(delta) > distance * distance * frame_scale * frame_scale
