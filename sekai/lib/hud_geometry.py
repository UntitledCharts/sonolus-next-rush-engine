"""OpenSekai FrontUIView camera and SpriteAnchor reference coordinates.

Unity uses a 1920x1080 reference camera at 108 pixels/unit (half height 5).
All offsets below are world units relative to the top left/right SpriteAnchor.
"""

REFERENCE_ASPECT = 16 / 9


def hud_unit(aspect: float) -> float:
    return min(1.0, aspect / REFERENCE_ASPECT) / 5


def hud_anchor(aspect: float, safe_aspect: float, right: bool) -> tuple[float, float]:
    # SpriteAnchorSizeOffset = -0.1 world units, not a fixed screen inset.
    top = 1 - 0.1 * hud_unit(aspect)
    x = top * safe_aspect * (1 if right else -1)
    return x, top


# The flattened Next RUSH v3 sprites resample the LiveAtlas artwork at 90%.
SKIN_PIXELS_PER_UNIT = 108 * 0.9
SCORE_WIDTH = 600 / SKIN_PIXELS_PER_UNIT
SCORE_HEIGHT = 128 / SKIN_PIXELS_PER_UNIT
# ScoreGauge's left edge is (3.7862 - 2.4542003, -0.42 - 0.10000026).
# In the flattened sprite that landmark is at pixel (110, 59.5).
SCORE_X = 3.7862 - 2.4542003 + (300 - 110) / SKIN_PIXELS_PER_UNIT
SCORE_Y = -0.42 - 0.10000026 + (59.5 - 64) / SKIN_PIXELS_PER_UNIT
LIFE_WIDTH = 400 / SKIN_PIXELS_PER_UNIT
LIFE_HEIGHT = 93 / SKIN_PIXELS_PER_UNIT
# PauseButton is at root (-0.61, -0.602) + (0, 0.08).
# Its center in Life Bar Pause is pixel (354, 51).
LIFE_X = -0.61 + (200 - 354) / SKIN_PIXELS_PER_UNIT
LIFE_Y = -0.522 + (51 - 46.5) / SKIN_PIXELS_PER_UNIT
MENU_X = -0.61
MENU_Y = -0.522
MENU_SIZE = 96 / 108
SKILL_X = 1.7111
SKILL_Y = -3.22
SKILL_WIDTH = 4.08
SKILL_HEIGHT = 1.36
