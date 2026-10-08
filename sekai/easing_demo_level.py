"""All easing types on slides, with stage, camera, and timescale examples."""

from sekai.level_utils import (
    LevelBpmChange,
    LevelCameraChange,
    LevelEntities,
    LevelNote,
    LevelSlide,
    LevelStage,
    LevelStageMaskChange,
    LevelStagePivotChange,
    LevelStageStyleChange,
    LevelStageTransformChange,
    LevelTimescaleChange,
    LevelTimescaleGroup,
    _build_silent_wav,
    build_level,
)
from sekai.lib.connector import ConnectorKind
from sekai.lib.ease import EaseType
from sekai.lib.note import NoteKind
from sekai.lib.stage import DivisionParity, JudgeLineColor, StageBorderStyle

BPM = 120.0
FAMILIES = ("QUAD", "SINE", "CUBIC", "QUART", "QUINT", "EXPO", "CIRC", "BACK", "ELASTIC", "STEP")
MODES = ("IN", "OUT", "IN_OUT", "OUT_IN")
MODE_LANES = (-4.5, -1.5, 1.5, 4.5)
SLIDE_BEATS = 1.0
ROW_BEATS = 4.0
SLIDES_START = 4.0
EVENTS_START = SLIDES_START + ROW_BEATS * (len(FAMILIES) + 1)
TIMESCALE_START = EVENTS_START + 16.0
TIMESCALE_EASES = (
    EaseType.NONE,
    EaseType.LINEAR,
    EaseType.IN_OUT_SINE,
    EaseType.OUT_EXPO,
    EaseType.IN_CIRC,
    EaseType.OUT_IN_QUINT,
    EaseType.OUT_STEP,
    EaseType.IN_OUT_STEP,
    EaseType.OUT_IN_STEP,
)
END_BEAT = TIMESCALE_START + 4.0 * len(TIMESCALE_EASES) + 8.0

entities: list[LevelEntities] = [LevelBpmChange(beat=0.0, bpm=BPM)]


def eased_slide(beat: float, lane: float, ease: EaseType, *, size: float = 0.75, tail_size: float | None = None):
    """Add a two-lane slide with attached ticks."""
    slide = LevelSlide()
    head = LevelNote(
        beat=beat,
        lane=lane - 1.0,
        size=size,
        kind=NoteKind.NORM_HEAD_TAP,
        segment_kind=ConnectorKind.ACTIVE_NORMAL,
        connector_ease=ease,
    )
    tail = LevelNote(
        beat=beat + SLIDE_BEATS,
        lane=lane + 1.0,
        size=size if tail_size is None else tail_size,
        kind=NoteKind.NORM_TAIL_RELEASE,
    )
    ticks = [
        LevelNote(beat=beat + SLIDE_BEATS * i / 4, lane=0.0, size=0.0, kind=NoteKind.NORM_TICK, attach=slide)
        for i in (1, 2, 3)
    ]
    slide.notes = [head, *ticks, tail]
    entities.append(slide)


# Four modes per family, then linear, NONE, and changing widths.
for row, family in enumerate(FAMILIES):
    for lane, mode in zip(MODE_LANES, MODES, strict=True):
        eased_slide(SLIDES_START + ROW_BEATS * row, lane, EaseType[f"{mode}_{family}"])
eased_slide(SLIDES_START + ROW_BEATS * len(FAMILIES), MODE_LANES[0], EaseType.LINEAR)
eased_slide(SLIDES_START + ROW_BEATS * len(FAMILIES), MODE_LANES[1], EaseType.NONE)
# Overshoot past a narrow tail makes the size cross zero.
eased_slide(SLIDES_START + ROW_BEATS * len(FAMILIES), MODE_LANES[2], EaseType.OUT_ELASTIC, size=1.5, tail_size=0.1)
eased_slide(SLIDES_START + ROW_BEATS * len(FAMILIES), MODE_LANES[3], EaseType.IN_OUT_BACK, size=0.2, tail_size=1.5)

# Circular guide with zero-width ends.
entities.append(
    LevelSlide(
        notes=[
            LevelNote(
                beat=EVENTS_START - 2 + SLIDE_BEATS * i / 2,
                lane=0.0,
                size=size,
                kind=NoteKind.ANCHOR,
                is_separator=True,
                segment_kind=ConnectorKind.GUIDE_GREEN,
                connector_ease=ease,
            )
            for i, (size, ease) in enumerate(
                ((0.0, EaseType.OUT_CIRC), (1.5, EaseType.IN_CIRC), (0.0, EaseType.LINEAR))
            )
        ]
    )
)

# Stage movement, masks, offsets, and alpha.
stage = LevelStage(
    from_start=True,
    until_end=True,
    mask_changes=[
        LevelStageMaskChange(beat=0.0, lane=0.0, size=6.0),
        LevelStageMaskChange(beat=EVENTS_START, lane=0.0, size=6.0, ease=EaseType.OUT_ELASTIC),
        LevelStageMaskChange(beat=EVENTS_START + 4, lane=0.0, size=3.0, ease=EaseType.IN_OUT_BACK),
        LevelStageMaskChange(beat=EVENTS_START + 8, lane=0.0, size=6.0),
    ],
    pivot_changes=[
        LevelStagePivotChange(
            beat=beat,
            lane=0.0,
            division_size=2.0,
            division_parity=DivisionParity.EVEN,
            abs_y_offset=offset,
            y_beat_offset=0.0,
            ease=ease,
        )
        for beat, offset, ease in (
            (0.0, 0.0, EaseType.LINEAR),
            (EVENTS_START, 0.0, EaseType.OUT_BACK),
            (EVENTS_START + 4, 0.3, EaseType.IN_OUT_ELASTIC),
            (EVENTS_START + 8, 0.0, EaseType.LINEAR),
        )
    ],
    style_changes=[
        LevelStageStyleChange(
            beat=beat,
            judge_line_color=JudgeLineColor.NEUTRAL,
            left_border_style=StageBorderStyle.DEFAULT,
            right_border_style=StageBorderStyle.DEFAULT,
            lane_alpha=1.0,
            judge_line_alpha=1.0,
            note_alpha=alpha,
            ease=ease,
        )
        for beat, alpha, ease in (
            (0.0, 1.0, EaseType.LINEAR),
            (EVENTS_START + 8, 0.8, EaseType.IN_OUT_BACK),
            (EVENTS_START + 10, 0.4, EaseType.OUT_ELASTIC),
            (EVENTS_START + 12, 1.0, EaseType.LINEAR),
        )
    ],
    transform_changes=[
        LevelStageTransformChange(beat=beat, x_lane_translate=translate, ease=ease)
        for beat, translate, ease in (
            (0.0, 0.0, EaseType.LINEAR),
            (EVENTS_START, 0.0, EaseType.OUT_ELASTIC),
            (EVENTS_START + 2, 2.0, EaseType.IN_OUT_STEP),
            (EVENTS_START + 4, -2.0, EaseType.OUT_BACK),
            (EVENTS_START + 6, 0.0, EaseType.LINEAR),
        )
    ],
)
entities.append(stage)
entities.extend(
    LevelNote(beat=EVENTS_START + i * 0.5, lane=(i % 4) * 2 - 3.0, size=1.0, kind=NoteKind.NORM_TAP, stage=stage)
    for i in range(32)
)

entities.extend(
    LevelCameraChange(beat=beat, rotate=rotate, zoom=zoom, ease=ease)
    for beat, rotate, zoom, ease in (
        (0.0, 0.0, 1.0, EaseType.LINEAR),
        (EVENTS_START + 12, 0.0, 1.0, EaseType.OUT_ELASTIC),
        (EVENTS_START + 14, 10.0, 1.2, EaseType.IN_OUT_BACK),
        (EVENTS_START + 16, 0.0, 1.0, EaseType.LINEAR),
    )
)

# Timescale examples over a steady stream of notes.
timescale_changes = [LevelTimescaleChange(beat=0.0, timescale=1.0)]
for i, ease in enumerate(TIMESCALE_EASES):
    beat = TIMESCALE_START + 4.0 * i
    timescale_changes += [
        LevelTimescaleChange(beat=beat, timescale=0.5, timescale_ease=ease),
        LevelTimescaleChange(beat=beat + 2, timescale=2.0, timescale_ease=ease),
    ]
timescale_changes.append(LevelTimescaleChange(beat=TIMESCALE_START + 4.0 * len(TIMESCALE_EASES), timescale=1.0))
timescale_group = LevelTimescaleGroup(changes=timescale_changes)
entities.append(timescale_group)
entities.extend(
    LevelNote(
        beat=TIMESCALE_START + i * 0.25,
        lane=-4.0 + (i % 9),
        size=0.5,
        kind=NoteKind.NORM_TAP,
        timescale_group=timescale_group,
    )
    for i in range(16 * len(TIMESCALE_EASES))
)

level = build_level(
    name="easing-demo",
    title="Easing Demo",
    bgm=_build_silent_wav(END_BEAT * 60 / BPM),
    entities=entities,
)
