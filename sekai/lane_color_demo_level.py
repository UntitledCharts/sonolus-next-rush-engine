"""Lane and judgment line color fades with notes on transformed stages."""

from sekai.level_utils import (
    LevelBpmChange,
    LevelEntities,
    LevelNote,
    LevelSlide,
    LevelStage,
    LevelStageMaskChange,
    LevelStagePivotChange,
    LevelStageStyleChange,
    LevelStageTransformChange,
    _build_silent_wav,
    build_level,
)
from sekai.lib.connector import ConnectorKind
from sekai.lib.ease import EaseType
from sekai.lib.layout import FlickDirection, StageTransformAnchor
from sekai.lib.note import NoteKind
from sekai.lib.note_style import NoteStyle
from sekai.lib.stage import DivisionParity, JudgeLineColor, JudgeLineStyle, StageBorderStyle

BPM = 120.0
LANE_COLORS = tuple(NoteStyle)
JUDGE_LINE_COLORS = tuple(JudgeLineColor)
FADE_BEATS = 2.0
LANE_FADES_START = 18.0
LANE_FADE_ALPHAS = (1.0, 0.5, 0.2)
JUDGE_LINE_START = 112.0
SHARED_START = 154.0
END_BEAT = SHARED_START + 18.0
STREAM_LANES = (-1.5, -0.5, 0.5, 1.5)


def style(
    beat: float,
    lane_color: NoteStyle = NoteStyle.DEFAULT,
    ease: EaseType = EaseType.LINEAR,
    *,
    judge_line_color: JudgeLineColor = JudgeLineColor.NEUTRAL,
    judge_line_style: JudgeLineStyle = JudgeLineStyle.DEFAULT,
    border_style: StageBorderStyle = StageBorderStyle.DEFAULT,
    lane_alpha: float = 1.0,
    judge_line_alpha: float = 1.0,
    full_width: bool = False,
    note_alpha: float = 1.0,
) -> LevelStageStyleChange:
    return LevelStageStyleChange(
        beat=beat,
        judge_line_color=judge_line_color,
        left_border_style=border_style,
        right_border_style=border_style,
        lane_alpha=lane_alpha,
        judge_line_alpha=judge_line_alpha,
        judge_line_style=judge_line_style,
        full_width=full_width,
        note_alpha=note_alpha,
        lane_color=lane_color,
        ease=ease,
    )


def pivot(
    beat: float, lane: float, size: float, parity: DivisionParity, ease: EaseType = EaseType.LINEAR
) -> LevelStagePivotChange:
    return LevelStagePivotChange(
        beat=beat,
        lane=lane,
        division_size=size,
        division_parity=parity,
        abs_y_offset=0.0,
        y_beat_offset=0.0,
        ease=ease,
    )


def side_stage(start: float, end: float, lane: float, size: float, styles: list[LevelStageStyleChange]) -> LevelStage:
    return LevelStage(
        mask_changes=[
            LevelStageMaskChange(beat=start, lane=lane, size=size, ease=EaseType.NONE),
            LevelStageMaskChange(beat=end, lane=lane, size=size),
        ],
        pivot_changes=[pivot(start, lane, 2.0, DivisionParity.EVEN)],
        style_changes=styles,
    )


main_styles = [
    # Each lane color, held.
    *(style(FADE_BEATS * i, color, EaseType.NONE) for i, color in enumerate(LANE_COLORS)),
    # Fade through every lane color at each alpha, with same-beat alpha changes between sections.
    *(
        style(LANE_FADES_START + FADE_BEATS * (len(LANE_COLORS) * block + i), color, lane_alpha=alpha)
        for block, alpha in enumerate(LANE_FADE_ALPHAS)
        for i, color in enumerate((*LANE_COLORS, NoteStyle.DEFAULT))
    ),
    # The middle of three stages.
    style(72.0),
    style(80.0, NoteStyle.RED),
    # Lane color with lane alpha, overshooting.
    style(88.0, ease=EaseType.OUT_BACK),
    style(90.0, NoteStyle.BLUE, EaseType.OUT_BACK, lane_alpha=0.3),
    style(92.0, NoteStyle.YELLOW, EaseType.OUT_BACK),
    style(94.0, NoteStyle.PURPLE, EaseType.OUT_BACK, lane_alpha=0.5),
    # Full width on, then off.
    style(96.0, NoteStyle.RED),
    style(98.0, NoteStyle.GREEN, full_width=True),
    # Overlapping stages.
    style(100.0),
    style(104.0, NoteStyle.PURPLE),
    # Stepped and elastic eases.
    style(108.0, ease=EaseType.IN_OUT_STEP),
    style(110.0, NoteStyle.RED, EaseType.OUT_ELASTIC),
    # Judgment line colors.
    *(style(JUDGE_LINE_START + FADE_BEATS * i, judge_line_color=color) for i, color in enumerate(JUDGE_LINE_COLORS)),
    # Border styles: Default -> Light, then Medium -> Disabled.
    style(128.0, judge_line_color=JudgeLineColor.RED),
    style(130.0, judge_line_color=JudgeLineColor.BLUE, border_style=StageBorderStyle.LIGHT),
    style(131.0, judge_line_color=JudgeLineColor.BLUE, border_style=StageBorderStyle.MEDIUM),
    style(133.0, judge_line_color=JudgeLineColor.RED, border_style=StageBorderStyle.DISABLED),
    # Full width on, then off.
    style(134.0),
    style(136.0, judge_line_color=JudgeLineColor.GREEN, full_width=True),
    # Division parity changes.
    style(138.0, judge_line_color=JudgeLineColor.YELLOW),
    style(140.0, judge_line_color=JudgeLineColor.CYAN),
    # Judgment line alpha 0.5, then a single line.
    style(142.0, judge_line_color=JudgeLineColor.RED, judge_line_alpha=0.5),
    style(144.0, judge_line_color=JudgeLineColor.BLUE, judge_line_alpha=0.5),
    style(145.0, judge_line_color=JudgeLineColor.BLUE, judge_line_style=JudgeLineStyle.SINGLE_LINE),
    style(147.0, judge_line_color=JudgeLineColor.GREEN, judge_line_style=JudgeLineStyle.SINGLE_LINE),
    # Division parity changes alone.
    style(148.0, ease=EaseType.NONE),
    # Notes on a moved, masked, transformed stage.
    style(SHARED_START, ease=EaseType.NONE, note_alpha=0.6),
    style(SHARED_START + 8, note_alpha=0.6),
    style(SHARED_START + 10, ease=EaseType.NONE, judge_line_style=JudgeLineStyle.SINGLE_LINE, note_alpha=0.6),
]

main_stage = LevelStage(
    from_start=True,
    until_end=True,
    mask_changes=[
        LevelStageMaskChange(beat=0.0, lane=0.0, size=6.0, ease=EaseType.NONE),
        LevelStageMaskChange(beat=72.0, lane=0.0, size=2.0, ease=EaseType.NONE),
        LevelStageMaskChange(beat=88.0, lane=0.0, size=6.0, ease=EaseType.NONE),
        LevelStageMaskChange(beat=SHARED_START, lane=1.0, size=3.0, ease=EaseType.NONE, mask_notes=True),
        LevelStageMaskChange(beat=END_BEAT, lane=1.0, size=3.0, mask_notes=True),
    ],
    pivot_changes=[
        pivot(0.0, 0.0, 2.0, DivisionParity.EVEN, EaseType.NONE),
        pivot(138.0, 0.0, 3.0, DivisionParity.EVEN),
        pivot(140.0, 0.0, 3.0, DivisionParity.ODD),
        pivot(142.0, 0.0, 3.0, DivisionParity.EVEN, EaseType.NONE),
        pivot(148.0, 0.0, 3.0, DivisionParity.EVEN),
        pivot(150.0, 0.0, 3.0, DivisionParity.ODD),
        pivot(152.0, 0.0, 3.0, DivisionParity.EVEN),
        pivot(SHARED_START, 2.0, 3.0, DivisionParity.EVEN, EaseType.NONE),
        pivot(SHARED_START + 8, 2.0, 3.0, DivisionParity.EVEN),
        pivot(SHARED_START + 10, 2.0, 3.0, DivisionParity.ODD, EaseType.NONE),
    ],
    style_changes=main_styles,
    transform_changes=[
        LevelStageTransformChange(beat=0.0, ease=EaseType.NONE),
        LevelStageTransformChange(
            beat=SHARED_START,
            rotate=10.0,
            x_lane_translate=1.0,
            y_lane_translate=0.3,
            anchor=StageTransformAnchor.CENTER,
            ease=EaseType.NONE,
            elevation=0.5,
        ),
    ],
)

entities: list[LevelEntities] = [
    LevelBpmChange(beat=0.0, bpm=BPM),
    main_stage,
    side_stage(72.0, 88.0, -4.0, 2.0, [style(72.0)]),
    side_stage(72.0, 88.0, 4.0, 2.0, [style(72.0, NoteStyle.RED)]),
    side_stage(
        100.0,
        108.0,
        2.0,
        3.0,
        [style(100.0, ease=EaseType.NONE), style(102.0), style(106.0, NoteStyle.CYAN), style(108.0)],
    ),
]

# A steady tap stream, doubled during the parity changes with color fades.
stream_beats = [*range(2, 138), *(138 + i / 2 for i in range(8)), *range(142, 152)]
entities.extend(
    LevelNote(
        beat=beat,
        lane=STREAM_LANES[i % len(STREAM_LANES)],
        size=0.5,
        kind=NoteKind.NORM_TAP,
        stage=main_stage,
    )
    for i, beat in enumerate(stream_beats)
)

shared_slide = LevelSlide()
shared_slide.notes = [
    LevelNote(
        beat=SHARED_START + 2,
        lane=-2.0,
        size=1.0,
        kind=NoteKind.NORM_HEAD_TAP,
        stage=main_stage,
        segment_kind=ConnectorKind.ACTIVE_NORMAL,
    ),
    *(
        LevelNote(beat=SHARED_START + 2 + i, lane=0.0, size=0.0, kind=NoteKind.NORM_TICK, attach=shared_slide)
        for i in (1, 2, 3)
    ),
    LevelNote(beat=SHARED_START + 6, lane=1.0, size=1.0, kind=NoteKind.NORM_TAIL_RELEASE, stage=main_stage),
]
entities.append(shared_slide)
entities.extend(
    LevelNote(
        beat=SHARED_START + 7 + i / 2, lane=-4.0 + 2 * (i % 4), size=1.0, kind=NoteKind.NORM_TAP, stage=main_stage
    )
    for i in range(14)
)
entities.extend(
    LevelNote(
        beat=SHARED_START + 15 + i / 2,
        lane=-3.0 + 2 * i,
        size=1.0,
        kind=NoteKind.NORM_FLICK,
        direction=FlickDirection.UP_OMNI,
        stage=main_stage,
    )
    for i in range(4)
)

level = build_level(
    name="lane-color-demo",
    title="Lane and Judgment Line Colors",
    bgm=_build_silent_wav(END_BEAT * 60 / BPM),
    entities=entities,
)
level.description = {
    "en": "Silent audio. Sections, in beats:\n"
    "0-18: each lane color, held.\n"
    "18-72: lane color fades through every color, at lane alpha 1, then 0.5, then 0.2.\n"
    "72-88: three stages side by side. The middle one fades between its neighbors' colors "
    "and never looks more see-through than they do.\n"
    "88-96: lane color and lane alpha fade together with an overshooting ease.\n"
    "96-100: a lane color fade while Full Width turns on and off.\n"
    "100-108: two overlapping stages with lane color fades at different times.\n"
    "108-112: stepped and elastic lane color fades.\n"
    "112-128: judgment line color fades through every color.\n"
    "128-134: judgment line color fades with border style changes.\n"
    "134-138: judgment line color fades while Full Width turns on and off.\n"
    "138-142: judgment line color fades with division parity changes, under taps.\n"
    "142-148: judgment line color fades at judgment line alpha 0.5, then on a single line.\n"
    "148-152: division parity changes with no color change.\n"
    "154-172: a moved pivot, masked notes, note alpha 0.6, a stage transform, a parity change "
    "and a single line, under taps, a slide and flicks."
}
