from sonolus.script.sprite import ZIndex

LAYER_BACKGROUND = -4
LAYER_ACTIVE_SLIDE_CONNECTOR_UNDER = -3
LAYER_GUIDE_CONNECTOR_UNDER = -2
LAYER_BACKGROUND_SIDE = -1
LAYER_BACKGROUND_COVER = 0
LAYER_STAGE_COVER = 1
LAYER_GAUGE = 2
LAYER_STAGE = 3
LAYER_COVER = 4
LAYER_COVER_LINE = 5
LAYER_STAGE_LANE = 6
LAYER_JUDGMENT_LINE = 7
LAYER_JUDGMENT_SKILL = 8
LAYER_SLOT_EFFECT = 9

LAYER_BEAT_LINE = 10
LAYER_ACTIVE_SLIDE_CONNECTOR_BOTTOM = 11
LAYER_GUIDE_CONNECTOR_BOTTOM = 12
LAYER_ACTIVE_SLIDE_CONNECTOR_TOP = 13
LAYER_GUIDE_CONNECTOR_TOP = 14
LAYER_PREVIEW_COVER = 15
LAYER_SIM_LINE = 16
LAYER_TIME_LINE = 17
LAYER_BPM_LINE = 18
LAYER_TIMESCALE_LINE = 19
LAYER_SKILL_LINE = 20
LAYER_FEVER_LINE_BOTTOM = 21
LAYER_FEVER_LINE_TOP = 22

LAYER_NOTE_SLIM_BODY = 23
LAYER_NOTE_FLICK_BODY = 24
LAYER_NOTE_BODY = 25
LAYER_NOTE_TICK = 26
LAYER_NOTE_ARROW = 27
LAYER_NOTE_ARROW_CRITICAL = 28
LAYER_SLOT_GLOW_EFFECT = 29

LAYER_ACTIVE_SLIDE_CONNECTOR_OVER = 30
LAYER_GUIDE_CONNECTOR_OVER = 31

LAYER_DAMAGE = 32
LAYER_SKILL_BAR = 33
LAYER_SKILL_ETC = 34
LAYER_JUDGMENT = 35


# def get_z(
#     layer: int,
#     time: float = 0.0,
#     lane: float = 0.0,
#     etc: int = 0,
#     *,
#     invert_time: bool = False,
# ) -> float:
#     quantized_time = (runtime.time() * 256) // 256
#     return make_comparable_float(
#         quantize_to_step(layer, start=-4, stop=40, step=1),
#         quantize_to_step(
#             time - quantized_time if invert_time else quantized_time - time, start=-30, stop=30, step=1 / 256
#         ),
#         quantize_to_step(abs(lane), start=0, stop=16, step=1 / 8),
#         quantize_to_step(etc, start=0, stop=12, step=1),
#         quantize_to_step(lane > 0, start=0, stop=2, step=1),
#     )


# def get_z_alt(layer: int, sublayer: int) -> float:
#   return make_comparable_float(
#       quantize_to_step(layer, start=-1, stop=28, step=1),
#       quantize_to_step(sublayer, start=0, stop=73728000, step=1),
#   )


def get_z(
    layer: int,
    time: float = 0.0,
    lane: float = 0.0,
    etc: int = 0,
    *,
    invert_time: bool = False,
) -> ZIndex:
    lane_side = lane > 0
    etc_lane = etc * 2 + lane_side
    return (
        layer,
        time if invert_time else -time,
        abs(lane),
        etc_lane,
    )


def get_z_alt(layer: int, sublayer: int = 0) -> ZIndex:
    return (
        layer,
        sublayer,
    )
