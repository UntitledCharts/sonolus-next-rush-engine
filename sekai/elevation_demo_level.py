"""Five adjoining two-lane stages with a repeating tap-and-flick pattern."""

from sekai.level_utils import (
    LevelBpmChange,
    LevelCameraChange,
    LevelEntities,
    LevelNote,
    LevelStage,
    LevelStageMaskChange,
    LevelStagePivotChange,
    LevelStageStyleChange,
    LevelStageTransformChange,
    _build_silent_wav,
    build_level,
)
from sekai.lib.ease import EaseType
from sekai.lib.layout import FlickDirection
from sekai.lib.note import NoteKind
from sekai.lib.stage import DivisionParity, JudgeLineColor, StageBorderStyle

BPM = 120.0
END_BEAT = 40.0
STAGE_LANES = (-4.0, -2.0, 0.0, 2.0, 4.0)
STAGE_HALF_WIDTH = 1.0
STAGE_COLORS = (
    JudgeLineColor.YELLOW,
    JudgeLineColor.GREEN,
    JudgeLineColor.CYAN,
    JudgeLineColor.GREEN,
    JudgeLineColor.YELLOW,
)
DIRECTIONS = (
    FlickDirection.UP_LEFT,
    FlickDirection.UP_LEFT,
    FlickDirection.UP_OMNI,
    FlickDirection.UP_RIGHT,
    FlickDirection.UP_RIGHT,
)

# beat, elevations. Higher outer stages prevent background overlap.
POSES = (
    (0, (-1,) * 5),
    (1, (-1,) * 5),
    (4, (0,) * 5),
    (6, (0,) * 5),
    (10, (2, 1, 0, 1, 2)),
    (14, (4, 2, 0, 2, 4)),
    (18, (4, 3, 2, 3, 4)),
    (30, (4, 3, 2, 3, 4)),
    (34, (2, 1, 0, 1.5, 3)),
    (36, (1, 0.5, 0, 0.5, 1)),
    (37, (1, 0.5, 0, 0.5, 1)),
    (39, (0,) * 5),
    (40, (0,) * 5),
)

# Each pose sets the beat, note and judge-line alpha, background alpha, and whether to separate the borders.
# Borders merge when the stages have equal elevations or the camera has zero tilt.
STYLE_POSES = (
    (0, 0, 0, False),
    (1, 0, 0, False),
    (4, 1, 1, False),
    (6, 1, 1, False),
    (10, 1, 1, True),
    (20, 1, 1, True),
    (24, 1, 1, False),
    (26, 1, 1, False),
    (30, 1, 1, True),
    (37, 1, 1, True),
    (39, 1, 1, False),
    (40, 0, 0, False),
)


def demo_stage(index: int) -> LevelStage:
    lane = STAGE_LANES[index]
    return LevelStage(
        from_start=True,
        until_end=True,
        mask_changes=[LevelStageMaskChange(beat=0, lane=lane, size=STAGE_HALF_WIDTH)],
        pivot_changes=[
            LevelStagePivotChange(
                beat=0,
                lane=lane,
                division_size=1,
                division_parity=DivisionParity.EVEN,
                abs_y_offset=0,
                y_beat_offset=0,
            )
        ],
        transform_changes=[
            LevelStageTransformChange(
                beat=beat,
                elevation=elevations[index],
                ease=EaseType.IN_OUT_QUAD,
            )
            for beat, elevations in POSES
        ],
        style_changes=[
            LevelStageStyleChange(
                beat=beat,
                judge_line_color=STAGE_COLORS[index],
                left_border_style=StageBorderStyle.DEFAULT if index == 0 or separated else StageBorderStyle.LIGHT,
                right_border_style=StageBorderStyle.DEFAULT
                if index == len(STAGE_LANES) - 1 or separated
                else StageBorderStyle.LIGHT,
                lane_alpha=0.25 * background,
                judge_line_alpha=foreground,
                note_alpha=foreground,
                division_line_alpha=0.4,
                ease=EaseType.IN_OUT_QUAD,
            )
            for beat, foreground, background, separated in STYLE_POSES
        ],
    )


stages = [demo_stage(index) for index in range(len(STAGE_LANES))]
camera_changes = [
    LevelCameraChange(beat=beat, stage_tilt=tilt, ease=EaseType.IN_OUT_QUAD)
    for beat, tilt in ((0, 1), (20, 1), (24, 0), (26, 0), (30, 1))
]
entities: list[LevelEntities] = [LevelBpmChange(beat=0, bpm=BPM), *stages, *camera_changes]


def add_note(beat: float, index: int, kind: NoteKind):
    entities.append(
        LevelNote(
            beat=beat,
            lane=0,
            size=STAGE_HALF_WIDTH,
            kind=kind,
            stage=stages[index],
            direction=DIRECTIONS[index],
        )
    )


PATTERN = (
    ((2,), NoteKind.CRIT_TAP),
    ((1, 3), NoteKind.NORM_TAP),
    ((0, 4), NoteKind.NORM_FLICK),
    ((1, 3), NoteKind.NORM_TAP),
)
for start in range(4, int(END_BEAT), 4):
    for offset, (indices, kind) in enumerate(PATTERN):
        # Flicks only in the low opening and closing phrases.
        if kind == NoteKind.NORM_FLICK and 4 < start < END_BEAT - 4:
            kind = NoteKind.NORM_TAP
        for index in indices:
            add_note(start + offset, index, kind)

level = build_level(
    name="elevation-demo",
    title="Elevation Demo",
    bgm=_build_silent_wav(END_BEAT * 60 / BPM),
    entities=entities,
)
