import math

from sekai.level_utils import (
    LevelBpmChange,
    LevelNote,
    LevelSlide,
    LevelStage,
    LevelStageMaskChange,
    LevelStagePivotChange,
    LevelStageStyleChange,
    LevelStageTransformChange,
    build_level,
)
from sekai.lib.connector import ConnectorKind
from sekai.lib.ease import EaseType
from sekai.lib.layout import (
    FIELD_B_FACTOR,
    FIELD_T_FACTOR,
    FIELD_W_FACTOR,
    TARGET_ASPECT_RATIO,
    StageTransformAnchor,
)
from sekai.lib.note import NoteKind
from sekai.lib.stage import DivisionParity, JudgeLineColor, StageBorderStyle

NUM_STAGES = 7
STAGE_HALF_WIDTH = 1.0  # A mask size of 1 makes each stage 2 lanes wide.

# Measure the distance from the judge line to the vanishing point in lane widths at the judge line.
# This level uses the default camera throughout, so stage tilt is always 1 and a lane is w_scale wide.
# Stage transforms fix the field's aspect ratio at TARGET_ASPECT_RATIO, which gives the distance below.
VANISH_DIST = (FIELD_T_FACTOR - FIELD_B_FACTOR) / (TARGET_ASPECT_RATIO * FIELD_W_FACTOR)

# Place each judge-line center VANISH_DIST from a shared vanishing point and rotate its stage to face it.
# Neighboring stages then meet along their side borders. Half the angle between stages comes from the
# right triangle formed by the vanishing point, a judge-line center, and one end of that judge line.
ARC_STEP = 2 * math.atan(STAGE_HALF_WIDTH / VANISH_DIST)

BPM = 60.0
SLIDE_BEATS_PER_STAGE = 0.25
LTR_SLIDE_START_BEAT = 2.0
RTL_SLIDE_START_BEAT = 9.0


def arc_angle(index: int) -> float:
    """Return the stage's angle around the vanishing point, measured counterclockwise from straight down."""
    return (index - (NUM_STAGES - 1) / 2) * ARC_STEP


def stage_is_visible(index: int) -> bool:
    """Return whether the stage should be visible.

    Show every other stage, including the first and last. The stages fill the arc, but setting
    lane and judge-line alpha to 0 hides three of them.
    The resulting gaps expose the borders of the four visible stages. Hidden stages keep their
    masks, so slide joints still pass through them.
    """
    return index % 2 == 0


def arc_stage(index: int) -> LevelStage:
    # Move the judge-line center around the shared vanishing point and rotate the stage to face it.
    # Negate the angle because the engine's rotate field uses positive values for clockwise rotation.
    angle = arc_angle(index)
    alpha = 1.0 if stage_is_visible(index) else 0.0
    return LevelStage(
        from_start=True,
        until_end=True,
        mask_changes=[
            LevelStageMaskChange(beat=0.0, lane=0.0, size=STAGE_HALF_WIDTH, ease=EaseType.LINEAR),
        ],
        pivot_changes=[
            LevelStagePivotChange(
                beat=0.0,
                lane=0.0,
                division_size=2.0,
                division_parity=DivisionParity.ODD,
                abs_y_offset=0.0,
                y_beat_offset=0.0,
                ease=EaseType.LINEAR,
            ),
        ],
        style_changes=[
            LevelStageStyleChange(
                beat=0.0,
                judge_line_color=JudgeLineColor.PURPLE,
                left_border_style=StageBorderStyle.DEFAULT,
                right_border_style=StageBorderStyle.DEFAULT,
                lane_alpha=alpha,
                judge_line_alpha=alpha,
                ease=EaseType.LINEAR,
            ),
        ],
        transform_changes=[
            LevelStageTransformChange(
                beat=0.0,
                rotate=-math.degrees(angle),
                x_lane_translate=VANISH_DIST * math.sin(angle),
                y_lane_translate=VANISH_DIST * (1 - math.cos(angle)),
                anchor=StageTransformAnchor.DEFAULT,
                ease=EaseType.LINEAR,
            ),
        ],
    )


arc_stages = [arc_stage(i) for i in range(NUM_STAGES)]


def sweep_slide(start_beat: float, stage_order: list[LevelStage]) -> LevelSlide:
    """Build a hold across the stages with a tap head, one tick on each intermediate stage, and a release tail."""
    last = len(stage_order) - 1
    slide = LevelSlide()
    slide.notes = [
        LevelNote(
            beat=start_beat + i * SLIDE_BEATS_PER_STAGE,
            lane=0.0,
            size=1.0,
            kind=NoteKind.NORM_HEAD_TAP if i == 0 else NoteKind.NORM_TAIL_RELEASE if i == last else NoteKind.NORM_TICK,
            stage=stage,
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
            connector_ease=EaseType.LINEAR,
        )
        for i, stage in enumerate(stage_order)
    ]
    return slide


ltr_slide = sweep_slide(LTR_SLIDE_START_BEAT, arc_stages)
rtl_slide = sweep_slide(RTL_SLIDE_START_BEAT, arc_stages[::-1])

# Halfway through the slide, IN_QUAD easing puts the connector one quarter of the way between the
# outer stage transforms. The attached tick must have the same hitbox as the active connector.
nonlinear_transform_slide = LevelSlide(
    notes=[
        LevelNote(
            beat=5.0,
            lane=0.0,
            size=1.0,
            kind=NoteKind.NORM_HEAD_TAP,
            stage=arc_stages[0],
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
            connector_ease=EaseType.IN_QUAD,
        ),
        LevelNote(
            beat=7.0,
            lane=0.0,
            size=1.0,
            kind=NoteKind.NORM_TAIL_RELEASE,
            stage=arc_stages[-1],
        ),
    ]
)
nonlinear_transform_tick = LevelNote(
    beat=6.0,
    lane=0.0,
    size=0.0,
    kind=NoteKind.NORM_TICK,
    attach=nonlinear_transform_slide,
)
nonlinear_transform_slide.notes.insert(1, nonlinear_transform_tick)

entities = [
    LevelBpmChange(beat=0.0, bpm=BPM),
    *arc_stages,
    ltr_slide,
    nonlinear_transform_slide,
    rtl_slide,
]

level = build_level(
    name="arc-test",
    title="Arc Test",
    bgm=None,
    entities=entities,
)
