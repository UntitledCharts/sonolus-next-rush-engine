from sekai.arc_test_level import level as arc_level
from sekai.elevation_demo_level import level as elevation_demo_level
from sekai.level_utils import (
    LevelBpmChange,
    LevelCameraChange,
    LevelFeverChance,
    LevelFeverStart,
    LevelNote,
    LevelSkill,
    LevelSlide,
    LevelStage,
    LevelStageMaskChange,
    LevelStagePivotChange,
    LevelStageStyleChange,
    LevelStageTransformChange,
    build_level,
)
from sekai.lib.connector import ConnectorKind, ConnectorLayer, SegmentPresentation
from sekai.lib.ease import EaseType
from sekai.lib.layout import StageTransformAnchor
from sekai.lib.note import NoteKind
from sekai.lib.stage import DivisionParity, JudgeLineColor, JudgeLineStyle, StageBorderStyle

SLIDE_START_BEAT = 4.0
SLIDE_END_BEAT = 20.0
NUM_REGULAR_TICKS = 33  # head + 31 ticks + tail (~2 non-attached ticks/sec at BPM 60)
ATTACHED_PER_GAP = 3  # ~6 attached ticks/sec at BPM 60

STAGE_B_HALF_PERIOD_BEATS = 1.0  # 2-beat full back-and-forth = 2 seconds at BPM 60
STAGE_B_LANES = (-2.0, 2.0)  # right swing pulled in to leave room for the right-hand flick stage
STAGE_B_END_BEAT = SLIDE_END_BEAT + 4.0

RIGHT_FLICK_LANE = 5.0  # center of the right-hand flick stage (mask lanes 4..6)


def _stage_b_oscillation_beats() -> list[float]:
    beats: list[float] = []
    beat = 0.0
    while beat <= STAGE_B_END_BEAT + 1e-6:
        beats.append(beat)
        beat += STAGE_B_HALF_PERIOD_BEATS
    return beats


STAGE_A_LANE = -5.0
STAGE_A_Y_OFFSETS = (0.0, 0.8)  # Move the left stage's judge line up and down while the camera tilts.

# Change stage_a's y offset whenever stage_b switches direction.
stage_a_pivot_changes = [
    LevelStagePivotChange(
        beat=beat,
        lane=STAGE_A_LANE,
        division_size=1.0,
        division_parity=DivisionParity.EVEN,
        abs_y_offset=STAGE_A_Y_OFFSETS[i % 2],
        y_beat_offset=0.0,
        ease=EaseType.IN_OUT_QUAD,
    )
    for i, beat in enumerate(_stage_b_oscillation_beats())
]

stage_a = LevelStage(
    from_start=True,
    until_end=True,
    mask_changes=[
        LevelStageMaskChange(beat=0.0, lane=STAGE_A_LANE, size=1.0, mask_notes=True, ease=EaseType.LINEAR),
    ],
    pivot_changes=stage_a_pivot_changes,
    style_changes=[
        LevelStageStyleChange(
            beat=0.0,
            judge_line_color=JudgeLineColor.GREEN,
            left_border_style=StageBorderStyle.DEFAULT,
            right_border_style=StageBorderStyle.DEFAULT,
            alpha=1.0,
            lane_alpha=1.0,
            judge_line_alpha=1.0,
            ease=EaseType.LINEAR,
        ),
    ],
)

stage_b_mask_changes = [
    LevelStageMaskChange(
        beat=beat,
        lane=STAGE_B_LANES[i % 2],
        size=2.0,
        ease=EaseType.IN_OUT_QUAD,
    )
    for i, beat in enumerate(_stage_b_oscillation_beats())
]

stage_b_pivot_changes = [
    LevelStagePivotChange(
        beat=beat,
        lane=STAGE_B_LANES[i % 2],
        division_size=1.0,
        division_parity=DivisionParity.EVEN,
        abs_y_offset=0.0,
        y_beat_offset=0.0,
        ease=EaseType.IN_OUT_QUAD,
    )
    for i, beat in enumerate(_stage_b_oscillation_beats())
]

# Fade stage_b's lane dividers over the song by reducing division_line_alpha, which multiplies lane_alpha.
# This leaves the judge line and borders unchanged.
stage_b = LevelStage(
    from_start=True,
    until_end=True,
    mask_changes=stage_b_mask_changes,
    pivot_changes=stage_b_pivot_changes,
    style_changes=[
        LevelStageStyleChange(
            beat=0.0,
            judge_line_color=JudgeLineColor.PURPLE,
            left_border_style=StageBorderStyle.DEFAULT,
            right_border_style=StageBorderStyle.DEFAULT,
            alpha=1.0,
            lane_alpha=1.0,
            judge_line_alpha=1.0,
            division_line_alpha=1.0,
            ease=EaseType.IN_OUT_QUAD,
        ),
        LevelStageStyleChange(
            beat=18.0,
            judge_line_color=JudgeLineColor.PURPLE,
            left_border_style=StageBorderStyle.DEFAULT,
            right_border_style=StageBorderStyle.DEFAULT,
            alpha=1.0,
            lane_alpha=1.0,
            judge_line_alpha=1.0,
            division_line_alpha=0.25,
            ease=EaseType.IN_OUT_QUAD,
        ),
    ],
    transform_changes=[
        LevelStageTransformChange(beat=0.0, ease=EaseType.IN_OUT_QUAD),
        LevelStageTransformChange(
            beat=8.0,
            rotate=12.0,
            x_lane_translate=0.4,
            y_lane_translate=0.7,
            anchor=StageTransformAnchor.CENTER,
            ease=EaseType.IN_OUT_QUAD,
        ),
        LevelStageTransformChange(beat=16.0, ease=EaseType.IN_OUT_QUAD),
    ],
)

# Change only the camera tilt so its effect is easy to inspect. Notes run over beats 4-20.
# Reduce the tilt, hold it over beats 10-14, then return close to the original perspective.
camera_changes = [
    LevelCameraChange(beat=0.0, stage_tilt=1.0, ease=EaseType.IN_OUT_QUAD),  # classic perspective
    LevelCameraChange(beat=4.0, stage_tilt=1.0, ease=EaseType.IN_OUT_QUAD),
    LevelCameraChange(beat=10.0, stage_tilt=0.4, ease=EaseType.IN_OUT_QUAD),  # reduced tilt
    LevelCameraChange(beat=14.0, stage_tilt=0.4, ease=EaseType.IN_OUT_QUAD),  # hold for inspection
    LevelCameraChange(beat=20.0, stage_tilt=0.99, ease=EaseType.IN_OUT_QUAD),  # back to classic
]

regular_beats = [
    SLIDE_START_BEAT + i * (SLIDE_END_BEAT - SLIDE_START_BEAT) / (NUM_REGULAR_TICKS - 1)
    for i in range(NUM_REGULAR_TICKS)
]

slide = LevelSlide()
slide_notes: list[LevelNote] = []
attached_notes: list[LevelNote] = []

for i, beat in enumerate(regular_beats):
    is_first = i == 0
    is_last = i == NUM_REGULAR_TICKS - 1
    stage = stage_a if i % 2 == 0 else stage_b
    size = 1 if i % 2 == 0 else 2
    if is_first:
        kind = NoteKind.NORM_HEAD_TAP
    elif is_last:
        kind = NoteKind.NORM_TAIL_TAP
    else:
        kind = NoteKind.NORM_TICK
    slide_notes.append(
        LevelNote(
            beat=beat,
            lane=0.0,
            size=size,
            kind=kind,
            stage=stage,
            is_separator=is_first or is_last,
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
            connector_ease=EaseType.IN_OUT_QUAD,
        )
    )
    if not is_last:
        next_beat = regular_beats[i + 1]
        for j in range(1, ATTACHED_PER_GAP + 1):
            frac = j / (ATTACHED_PER_GAP + 1)
            attached_notes.append(
                LevelNote(
                    beat=beat + frac * (next_beat - beat),
                    lane=0.0,
                    size=0.0,
                    kind=NoteKind.NORM_TICK,
                    stage=None,
                    attach=slide,
                )
            )

slide.notes = slide_notes


def _ease_in_out_quad(x: float) -> float:
    x = max(0.0, min(1.0, x))
    if x < 0.5:
        return 2 * x * x
    return 1 - 2 * (1 - x) ** 2


def _stage_b_pivot_at_beat(beat: float) -> float:
    pivot_beats = _stage_b_oscillation_beats()
    pivot_lanes = [STAGE_B_LANES[i % 2] for i in range(len(pivot_beats))]
    if beat <= pivot_beats[0]:
        return pivot_lanes[0]
    if beat >= pivot_beats[-1]:
        return pivot_lanes[-1]
    for i in range(len(pivot_beats) - 1):
        t_a = pivot_beats[i]
        t_b = pivot_beats[i + 1]
        if t_a <= beat <= t_b:
            frac = (beat - t_a) / (t_b - t_a)
            return pivot_lanes[i] + (pivot_lanes[i + 1] - pivot_lanes[i]) * _ease_in_out_quad(frac)
    return pivot_lanes[-1]


def _slide_abs_lane(i: int) -> float:
    if i % 2 == 0:
        return STAGE_A_LANE
    return _stage_b_pivot_at_beat(regular_beats[i])


guide_stage = LevelStage(
    from_start=True,
    until_end=True,
    pivot_changes=[
        LevelStagePivotChange(
            beat=0.0,
            lane=0.0,
            division_size=1.0,
            division_parity=DivisionParity.EVEN,
            abs_y_offset=0.0,
            y_beat_offset=0.0,
            ease=EaseType.LINEAR,
        ),
    ],
)

guide_slide = LevelSlide()
guide_slide.notes = [
    LevelNote(
        beat=beat,
        lane=_slide_abs_lane(i),
        size=1.0 if i % 2 == 0 else 2.0,
        kind=NoteKind.ANCHOR,
        stage=guide_stage,
        is_separator=True,
        segment_kind=ConnectorKind.GUIDE_RED,
        connector_ease=EaseType.IN_OUT_QUAD,
    )
    for i, beat in enumerate(regular_beats)
]

fever_chance = LevelFeverChance(beat=1.0, force=True)
fever_start = LevelFeverStart(beat=100)
test_skill = LevelSkill(beat=1.0, effect=4)


# Test SegmentPresentation.FULL_SCREEN while the camera tilt changes. Between a segment's head and tail
# times, its guide sprite should fill the screen using the segment's alpha at the judge line.
# Successive segments change alpha so the overlay changes intensity. It should disappear outside beats
# 8-12.5 and cover the whole screen even during the interval with reduced tilt at beats 10-14.
full_screen_guide_segments = [(8.0, 0.15), (9.5, 2), (11.0, 0.15), (12.5, 0.4)]
full_screen_guide = LevelSlide()
full_screen_guide.notes = [
    LevelNote(
        beat=beat,
        lane=0.0,
        size=1.0,
        kind=NoteKind.ANCHOR,
        stage=guide_stage,
        is_separator=True,
        segment_kind=ConnectorKind.GUIDE_BLUE,
        segment_alpha=alpha,
        segment_presentation=SegmentPresentation.FULL_SCREEN,
        connector_ease=EaseType.LINEAR,
        segment_layer=ConnectorLayer.OVER,
    )
    for beat, alpha in full_screen_guide_segments
]


# Put a flick on every beat on the right stage to inspect its body and arrow as the camera tilts.
# This stage's mask covers lanes 4..6, just beyond stage_b's rightmost position, so the masks don't overlap.
#
# Also test judge_line_style and full_width. Start with a normal red judge line, then fade to SINGLE_LINE
# while the camera holds its reduced tilt. Keep the line within lanes 4..6 so its appearance and the
# lack of flick slot effects are easy to inspect. Finally, widen it to the full screen and restore
# the default judge-line style.
def _right_flick_style(beat: float, style: JudgeLineStyle, full_width: bool) -> LevelStageStyleChange:
    return LevelStageStyleChange(
        beat=beat,
        judge_line_color=JudgeLineColor.RED,
        judge_line_style=style,
        left_border_style=StageBorderStyle.DEFAULT,
        right_border_style=StageBorderStyle.DEFAULT,
        full_width=full_width,
        alpha=1.0,
        lane_alpha=1.0,
        judge_line_alpha=1.0,
        division_line_alpha=1.0,
        ease=EaseType.IN_OUT_QUAD,
    )


right_flick_stage = LevelStage(
    from_start=True,
    until_end=True,
    mask_changes=[
        LevelStageMaskChange(beat=0.0, lane=RIGHT_FLICK_LANE, size=1.0, mask_notes=True, ease=EaseType.LINEAR),
    ],
    pivot_changes=[
        LevelStagePivotChange(
            beat=0.0,
            lane=RIGHT_FLICK_LANE,
            division_size=1.0,
            division_parity=DivisionParity.EVEN,
            abs_y_offset=0.0,
            y_beat_offset=0.0,
            ease=EaseType.LINEAR,
        ),
    ],
    style_changes=[
        _right_flick_style(0.0, JudgeLineStyle.DEFAULT, full_width=False),
        _right_flick_style(6.0, JudgeLineStyle.DEFAULT, full_width=False),  # hold default
        _right_flick_style(9.0, JudgeLineStyle.SINGLE_LINE, full_width=False),  # fade to single line
        _right_flick_style(14.0, JudgeLineStyle.SINGLE_LINE, full_width=False),  # hold single line (slot effect off)
        _right_flick_style(17.0, JudgeLineStyle.SINGLE_LINE, full_width=True),  # widen to full-width single line
        _right_flick_style(19.0, JudgeLineStyle.SINGLE_LINE, full_width=True),  # hold full-width single line
        _right_flick_style(20.0, JudgeLineStyle.DEFAULT, full_width=True),  # full-width default judge line
    ],
)

right_flicks = [
    LevelNote(
        beat=float(b),
        # Cycle through outside, clipped, and visible notes on both sides.
        lane=(-3.0, -1.5, 0.0, 1.5, 3.0)[(b - 1) % 5],
        size=1.0,
        kind=NoteKind.CRIT_FLICK,
        stage=right_flick_stage,
    )
    for b in range(1, int(SLIDE_END_BEAT) + 1)
]

# Clip the original connector geometry to the shared stage mask instead of connecting its masked endpoints.
masked_connector_slide = LevelSlide(
    notes=[
        LevelNote(
            beat=21.0,
            lane=-1.5,
            size=1.0,
            kind=NoteKind.NORM_HEAD_TAP,
            stage=right_flick_stage,
            is_separator=True,
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
        ),
        LevelNote(
            beat=22.0,
            lane=3.0,
            size=1.0,
            kind=NoteKind.NORM_TICK,
            stage=right_flick_stage,
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
        ),
        LevelNote(
            beat=23.0,
            lane=1.5,
            size=1.0,
            kind=NoteKind.NORM_TAIL_TAP,
            stage=right_flick_stage,
            is_separator=True,
        ),
    ]
)

# Endpoints outside opposite mask bounds leave the middle of the connector visible.
masked_outside_connector_slide = LevelSlide(
    notes=[
        LevelNote(
            beat=24.0,
            lane=-3.0,
            size=1.0,
            kind=NoteKind.NORM_HEAD_TAP,
            stage=right_flick_stage,
            is_separator=True,
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
        ),
        LevelNote(
            beat=25.0,
            lane=3.0,
            size=1.0,
            kind=NoteKind.NORM_TAIL_TAP,
            stage=right_flick_stage,
            is_separator=True,
        ),
    ]
)


# Exercise interpolated masks between stages with note masking enabled, then verify that the connector
# remains unmasked when either endpoint does not use note masking.
mixed_stage_mask_connector_slide = LevelSlide(
    notes=[
        LevelNote(
            beat=27.0,
            lane=1.5,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=stage_a,
            is_separator=True,
            segment_kind=ConnectorKind.GUIDE_PURPLE,
            connector_ease=EaseType.LINEAR,
        ),
        LevelNote(
            beat=30.0,
            lane=-1.5,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=right_flick_stage,
            is_separator=True,
            segment_kind=ConnectorKind.GUIDE_BLUE,
            connector_ease=EaseType.LINEAR,
        ),
        LevelNote(
            beat=33.0,
            lane=3.5,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=guide_stage,
            is_separator=True,
            segment_kind=ConnectorKind.GUIDE_GREEN,
            connector_ease=EaseType.LINEAR,
        ),
        LevelNote(
            beat=36.0,
            lane=1.5,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=stage_a,
            is_separator=True,
            segment_kind=ConnectorKind.NONE,
            connector_ease=EaseType.LINEAR,
        ),
    ]
)


# The first connector has zero size at both endpoints; the second has zero size only at its head.
zero_size_connector_slide = LevelSlide(
    notes=[
        LevelNote(
            beat=38.0,
            lane=-2.0,
            size=0.0,
            kind=NoteKind.ANCHOR,
            stage=guide_stage,
            is_separator=True,
            segment_kind=ConnectorKind.GUIDE_YELLOW,
            connector_ease=EaseType.LINEAR,
        ),
        LevelNote(
            beat=39.0,
            lane=0.0,
            size=0.0,
            kind=NoteKind.ANCHOR,
            stage=guide_stage,
            is_separator=True,
            segment_kind=ConnectorKind.GUIDE_CYAN,
            connector_ease=EaseType.LINEAR,
        ),
        LevelNote(
            beat=40.0,
            lane=2.0,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=guide_stage,
            is_separator=True,
            segment_kind=ConnectorKind.NONE,
            connector_ease=EaseType.LINEAR,
        ),
    ]
)


entities = [
    LevelBpmChange(beat=0.0, bpm=60.0),
    stage_a,
    stage_b,
    guide_stage,
    right_flick_stage,
    *camera_changes,
    slide,
    guide_slide,
    fever_chance,
    fever_start,
    test_skill,
    full_screen_guide,
    masked_connector_slide,
    masked_outside_connector_slide,
    mixed_stage_mask_connector_slide,
    zero_size_connector_slide,
    *attached_notes,
    *right_flicks,
]

level = build_level(
    name="test",
    title="Test",
    bgm=None,
    entities=entities,
)


def _mask_lab_style(masked: bool, beat: float = 0.0) -> LevelStageStyleChange:
    return LevelStageStyleChange(
        beat=beat,
        judge_line_color=JudgeLineColor.CYAN if masked else JudgeLineColor.NEUTRAL,
        left_border_style=StageBorderStyle.DEFAULT,
        right_border_style=StageBorderStyle.DEFAULT,
        lane_alpha=1.0,
        judge_line_alpha=1.0,
    )


def _mask_lab_stage(lane: float, mask_notes: bool) -> LevelStage:
    return LevelStage(
        from_start=True,
        until_end=True,
        mask_changes=[LevelStageMaskChange(beat=0.0, lane=lane, size=2.0, mask_notes=mask_notes)],
        pivot_changes=[
            LevelStagePivotChange(
                beat=0.0,
                lane=lane,
                division_size=1.0,
                division_parity=DivisionParity.EVEN,
                abs_y_offset=0.0,
                y_beat_offset=0.0,
            )
        ],
        style_changes=[_mask_lab_style(mask_notes)],
    )


# The left stage masks relative lanes [-2, 2]. Keep the right stage unmasked for comparison until the final connector.
mask_lab_stage = _mask_lab_stage(-3.0, mask_notes=True)
mask_lab_control_stage = _mask_lab_stage(3.0, mask_notes=False)
mask_lab_control_stage.style_changes = [
    _mask_lab_style(False, beat=0.0),
    _mask_lab_style(False, beat=54.0),
    _mask_lab_style(True, beat=54.5),
]
mask_lab_control_stage.mask_changes = [
    LevelStageMaskChange(beat=0.0, lane=3.0, size=2.0, mask_notes=False),
    LevelStageMaskChange(beat=54.0, lane=3.0, size=2.0, mask_notes=False),
    LevelStageMaskChange(beat=54.5, lane=3.0, size=2.0, mask_notes=True),
]
mask_lab_stage.style_changes = [
    _mask_lab_style(True, beat=0.0),
    _mask_lab_style(False, beat=36.0),
    _mask_lab_style(True, beat=40.0),
]
mask_lab_stage.mask_changes = [
    LevelStageMaskChange(beat=0.0, lane=-3.0, size=2.0, mask_notes=True),
    LevelStageMaskChange(beat=36.0, lane=-3.0, size=2.0, mask_notes=False),
    LevelStageMaskChange(beat=40.0, lane=-3.0, size=2.0, mask_notes=True),
    LevelStageMaskChange(beat=42.0, lane=-3.0, size=2.0, mask_notes=True),
    LevelStageMaskChange(beat=44.0, lane=-3.0, size=1.0, mask_notes=True, ease=EaseType.IN_OUT_QUAD),
    LevelStageMaskChange(beat=46.0, lane=-3.0, size=3.0, mask_notes=True, ease=EaseType.IN_OUT_QUAD),
    LevelStageMaskChange(beat=49.0, lane=-3.0, size=2.0, mask_notes=True, ease=EaseType.IN_OUT_QUAD),
]
# The transform jumps when masking changes at beats 36 and 40. At those exact beats, judgment geometry
# must use the previous transform, as attached notes do. It must use the new transform immediately afterward.
mask_lab_stage.transform_changes = [
    LevelStageTransformChange(beat=0.0, ease=EaseType.NONE),
    LevelStageTransformChange(beat=36.0, x_lane_translate=2.0, ease=EaseType.NONE),
    LevelStageTransformChange(beat=40.0, ease=EaseType.LINEAR),
]
mask_lab_lanes = (-3.0, -1.5, 0.0, 1.5, 3.0)
# Masking clips the outer notes and their base hitboxes to zero width at the nearest mask edge.
# Show Hitboxes should show a two-lane-wide input region because one lane of leniency is then added on each side.
mask_lab_notes = [
    LevelNote(
        beat=float(i + 1) + (0.25 if stage is mask_lab_control_stage else 0.0),
        lane=lane,
        size=1.0,
        kind=NoteKind.NORM_TAP,
        stage=stage,
    )
    for stage in (mask_lab_stage, mask_lab_control_stage)
    for i, lane in enumerate(mask_lab_lanes)
]

# Hold from beats 8-20; the active head must follow the connector through each masking case.
mask_lab_active_slide = LevelSlide(
    notes=[
        LevelNote(
            beat=8.0,
            lane=-1.5,
            size=1.0,
            kind=NoteKind.NORM_HEAD_TAP,
            stage=mask_lab_stage,
            is_separator=True,
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
            connector_ease=EaseType.IN_OUT_QUAD,
        ),
        LevelNote(
            beat=12.0,
            lane=3.0,
            size=1.0,
            kind=NoteKind.NORM_TICK,
            stage=mask_lab_stage,
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
            connector_ease=EaseType.LINEAR,
        ),
        LevelNote(
            beat=16.0,
            lane=-3.0,
            size=1.0,
            kind=NoteKind.NORM_TICK,
            stage=mask_lab_stage,
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
            connector_ease=EaseType.IN_OUT_QUAD,
        ),
        LevelNote(
            beat=20.0,
            lane=1.5,
            size=1.0,
            kind=NoteKind.NORM_TAIL_TAP,
            stage=mask_lab_stage,
            is_separator=True,
        ),
    ]
)
mask_lab_attached_notes = [
    LevelNote(
        beat=beat,
        lane=0.0,
        size=0.0,
        kind=NoteKind.NORM_TICK,
        stage=None,
        attach=mask_lab_active_slide,
    )
    for beat in (10.0, 14.0, 18.0)
]

# Offset the unmasked control to show raw geometry without creating cross-stage sim lines.
mask_lab_control_slide = LevelSlide(
    notes=[
        LevelNote(
            beat=n.beat + 0.25,
            lane=n.lane,
            size=n.size,
            kind=n.kind,
            stage=mask_lab_control_stage,
            is_separator=n.is_separator,
            segment_kind=n.segment_kind,
            connector_ease=n.connector_ease,
        )
        for n in mask_lab_active_slide.notes
    ]
)

# Endpoints outside the same mask bound leave the connector hidden.
mask_lab_same_side_connector = LevelSlide(
    notes=[
        LevelNote(
            beat=22.0,
            lane=-3.5,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=mask_lab_stage,
            is_separator=True,
            segment_kind=ConnectorKind.GUIDE_BLUE,
        ),
        LevelNote(
            beat=24.0,
            lane=-3.0,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=mask_lab_stage,
            is_separator=True,
        ),
    ]
)


# With the endpoints beyond opposite mask edges, the middle of the connector should remain visible up to each edge.
mask_lab_opposite_connector = LevelSlide(
    notes=[
        LevelNote(
            beat=26.0,
            lane=-3.0,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=mask_lab_stage,
            is_separator=True,
            segment_kind=ConnectorKind.GUIDE_PURPLE,
        ),
        LevelNote(
            beat=28.0,
            lane=3.0,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=mask_lab_stage,
            is_separator=True,
        ),
    ]
)


# Attached notes use the same mask cross-section as their connectors: beat 23 is fully outside, while 26.5 is partial.
mask_lab_connector_attached_notes = [
    LevelNote(beat=23.0, lane=0.0, size=0.0, kind=NoteKind.NORM_TICK, attach=mask_lab_same_side_connector),
    LevelNote(beat=26.5, lane=0.0, size=0.0, kind=NoteKind.NORM_TICK, attach=mask_lab_opposite_connector),
]

# Notes outside the mask at beats 30 and 32 emit particles at the mask edge.
# Partially clipped notes at beats 31 and 33 provide a comparison.
mask_lab_effect_notes = [
    LevelNote(beat=30.0, lane=-3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=31.0, lane=-1.5, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=32.0, lane=3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=33.0, lane=1.5, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
]


# Toggle masking during beats 35-41, then narrow and widen the mask over beats 42-46. Note pairs also test sim lines.
# Notes exactly at a masking change use the previous state, so beat 36 stays masked and beat 40 stays unmasked.
mask_lab_transition_notes = [
    LevelNote(beat=35.0, lane=3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=35.0, lane=0.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=36.0, lane=3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=37.0, lane=3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=37.0, lane=0.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=39.0, lane=-3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=39.0, lane=0.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=40.0, lane=3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=41.0, lane=-3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=41.0, lane=0.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=43.0, lane=-1.5, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=43.0, lane=0.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=45.0, lane=1.5, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=45.0, lane=0.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=47.0, lane=2.5, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=47.0, lane=0.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
]


# Keep the active head stationary while the mask changes to check that its hitbox still matches the connector.
def _mask_lab_transition_slide(stage: LevelStage) -> LevelSlide:
    beats = (34.0, 38.0, 42.0, 46.0, 48.0)
    return LevelSlide(
        notes=[
            LevelNote(
                beat=beat,
                lane=1.5,
                size=1.0,
                kind=NoteKind.NORM_HEAD_TAP
                if i == 0
                else NoteKind.NORM_TAIL_TAP
                if i == len(beats) - 1
                else NoteKind.NORM_TICK,
                stage=stage,
                is_separator=i == 0 or i == len(beats) - 1,
                segment_kind=ConnectorKind.ACTIVE_NORMAL if i < len(beats) - 1 else ConnectorKind.NONE,
                connector_ease=EaseType.LINEAR,
            )
            for i, beat in enumerate(beats)
        ]
    )


mask_lab_transition_slide = _mask_lab_transition_slide(mask_lab_stage)
mask_lab_transition_control_slide = _mask_lab_transition_slide(mask_lab_control_stage)
for note in mask_lab_transition_control_slide.notes:
    note.beat += 0.25
# Attached ticks exactly at both masking changes should use the previous mask state, just like standalone notes.
mask_lab_transition_attached_notes = [
    LevelNote(beat=beat, lane=0.0, size=0.0, kind=NoteKind.NORM_TICK, attach=mask_lab_transition_slide)
    for beat in (36.0, 40.0)
]


# Sim lines: 50 uses clipped centers; 51/52 hide one endpoint; 53 is the visible control.
# Seek through the 34-48 slide to test replay cleanup.
mask_lab_sim_notes = [
    LevelNote(beat=50.0, lane=-1.5, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=50.0, lane=1.5, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=51.0, lane=-3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=51.0, lane=0.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=52.0, lane=0.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=52.0, lane=3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=53.0, lane=-0.5, size=0.5, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
    LevelNote(beat=53.0, lane=0.5, size=0.5, kind=NoteKind.NORM_TAP, stage=mask_lab_stage),
]


# Enable note masking on the right stage for this section. The purple connector interpolates between the two stage
# masks. The yellow connector uses the same lane 0 geometry but has an unmasked tail, so its full width stays visible.
# The purple connector should match the yellow connector's width in the middle.
mask_lab_different_stage_connector = LevelSlide(
    notes=[
        LevelNote(
            beat=56.0,
            lane=3.0,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=mask_lab_stage,
            is_separator=True,
            segment_kind=ConnectorKind.GUIDE_PURPLE,
            connector_ease=EaseType.LINEAR,
            segment_layer=ConnectorLayer.OVER,
        ),
        LevelNote(
            beat=59.0,
            lane=-3.0,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=mask_lab_control_stage,
            is_separator=True,
            segment_kind=ConnectorKind.NONE,
            connector_ease=EaseType.LINEAR,
        ),
    ]
)


mask_lab_different_stage_control_connector = LevelSlide(
    notes=[
        LevelNote(
            beat=56.0,
            lane=3.0,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=mask_lab_stage,
            is_separator=True,
            segment_kind=ConnectorKind.GUIDE_YELLOW,
            connector_ease=EaseType.LINEAR,
            segment_layer=ConnectorLayer.UNDER,
        ),
        LevelNote(
            beat=59.0,
            lane=0.0,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=None,
            is_separator=True,
            segment_kind=ConnectorKind.NONE,
            connector_ease=EaseType.LINEAR,
        ),
    ]
)


# The purple attached note is masked between two masked stages; the yellow one stays unmasked like its connector.
mask_lab_different_stage_attached_notes = [
    LevelNote(
        beat=57.5,
        lane=0.0,
        size=0.0,
        kind=NoteKind.NORM_TICK,
        attach=mask_lab_different_stage_connector,
    ),
    LevelNote(
        beat=58.0,
        lane=0.0,
        size=0.0,
        kind=NoteKind.NORM_TICK,
        attach=mask_lab_different_stage_control_connector,
    ),
]


# Check that attached notes and their connector stay aligned as the connector moves across both mask edges.
# The ticks are fully hidden, partly visible, fully visible, partly visible, and fully hidden, in that order.
# In preview, each tick's body should match the connector's width and position at that beat. With Show Hitboxes
# enabled, its hitbox should match the active connector's at judgment time, including the leniency added after
# masking when the visible width is zero.
mask_lab_parity_section = LevelSlide(
    notes=[
        LevelNote(
            beat=5.5,
            lane=-4.0,
            size=1.0,
            kind=NoteKind.NORM_HEAD_TAP,
            stage=mask_lab_stage,
            is_separator=True,
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
            connector_ease=EaseType.LINEAR,
        ),
        LevelNote(
            beat=7.5,
            lane=4.0,
            size=1.0,
            kind=NoteKind.NORM_TAIL_TAP,
            stage=mask_lab_stage,
            is_separator=True,
        ),
    ]
)
mask_lab_parity_attached_notes = [
    LevelNote(beat=beat, lane=0.0, size=0.0, kind=NoteKind.NORM_TICK, attach=mask_lab_parity_section)
    for beat in (5.75, 6.0, 6.5, 7.0, 7.25)
]
mask_lab_parity_section.notes[1:1] = mask_lab_parity_attached_notes


# The tick at beat 63 attaches exactly to a joint, so its attachment head and tail reference the same note.
# Its attachment fraction therefore defaults to 0.5. The tick at beat 64 also has a fraction of 0.5 because
# it is halfway between two different joints. These ticks are consecutive separators, so they create a
# connector whose endpoint attachment fractions are equal. Its drawing and hitbox must still move between the ticks.
mask_lab_exact_joint_reference = LevelSlide(
    notes=[
        LevelNote(
            beat=61.0,
            lane=-1.0,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=mask_lab_stage,
            segment_kind=ConnectorKind.GUIDE_CYAN,
            connector_ease=EaseType.LINEAR,
            segment_layer=ConnectorLayer.UNDER,
        ),
        LevelNote(
            beat=63.0,
            lane=2.5,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=mask_lab_stage,
            segment_kind=ConnectorKind.GUIDE_CYAN,
            connector_ease=EaseType.LINEAR,
            segment_layer=ConnectorLayer.UNDER,
        ),
        LevelNote(
            beat=65.0,
            lane=-1.0,
            size=1.0,
            kind=NoteKind.ANCHOR,
            stage=mask_lab_stage,
        ),
    ]
)
mask_lab_exact_joint_section = LevelSlide(
    notes=[
        LevelNote(
            beat=62.0,
            lane=-1.0,
            size=1.0,
            kind=NoteKind.NORM_HEAD_TAP,
            stage=mask_lab_stage,
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
            connector_ease=EaseType.LINEAR,
        ),
        LevelNote(
            beat=66.0,
            lane=-1.0,
            size=1.0,
            kind=NoteKind.NORM_TAIL_TAP,
            stage=mask_lab_stage,
        ),
    ]
)
mask_lab_exact_joint_note = LevelNote(
    beat=63.0,
    lane=0.0,
    size=0.0,
    kind=NoteKind.NORM_TICK,
    is_separator=True,
    segment_kind=ConnectorKind.ACTIVE_NORMAL,
    attach=mask_lab_exact_joint_reference,
)
mask_lab_midpoint_attached_note = LevelNote(
    beat=64.0,
    lane=0.0,
    size=0.0,
    kind=NoteKind.NORM_TICK,
    is_separator=True,
    segment_kind=ConnectorKind.ACTIVE_NORMAL,
    attach=mask_lab_exact_joint_reference,
)
mask_lab_exact_joint_section.notes[1:1] = [mask_lab_exact_joint_note, mask_lab_midpoint_attached_note]


mask_lab_level = build_level(
    name="mask-notes-test",
    title="Mask Notes Test",
    bgm=None,
    entities=[
        LevelBpmChange(beat=0.0, bpm=60.0),
        mask_lab_stage,
        mask_lab_control_stage,
        mask_lab_active_slide,
        mask_lab_control_slide,
        mask_lab_same_side_connector,
        mask_lab_opposite_connector,
        mask_lab_different_stage_control_connector,
        mask_lab_different_stage_connector,
        mask_lab_parity_section,
        mask_lab_exact_joint_reference,
        mask_lab_exact_joint_section,
        mask_lab_transition_slide,
        mask_lab_transition_control_slide,
        *mask_lab_notes,
        *mask_lab_attached_notes,
        *mask_lab_connector_attached_notes,
        *mask_lab_different_stage_attached_notes,
        *mask_lab_transition_attached_notes,
        *mask_lab_effect_notes,
        *mask_lab_transition_notes,
        *mask_lab_sim_notes,
    ],
)


def load_levels():
    yield level
    yield mask_lab_level
    yield arc_level
    yield elevation_demo_level
