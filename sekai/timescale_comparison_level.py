from typing import cast

from sonolus.script.level import LevelData

from sekai.level_utils import (
    LevelBpmChange,
    LevelNote,
    LevelStage,
    LevelStageMaskChange,
    LevelStagePivotChange,
    LevelStageStyleChange,
    LevelTimescaleChange,
    LevelTimescaleGroup,
    _build_silent_wav,
    build_level,
)
from sekai.lib.ease import EaseType
from sekai.lib.note import NoteKind
from sekai.lib.stage import DivisionParity, JudgeLineColor, StageBorderStyle
from sekai.lib.timescale import TransitionStyle
from sekai.play.sim_line import SimLine

DURATION = 10.0
NOTE_STEP = 0.125
STAGE_CENTERS = (-5.2, -3.9, -2.6, -1.3, 0.0, 1.3, 2.6, 3.9, 5.2)
STAGE_HALF_WIDTH = 0.5


def comparison_group(increase: TransitionStyle, decrease: TransitionStyle, ease: EaseType) -> LevelTimescaleGroup:
    return LevelTimescaleGroup(
        changes=[
            LevelTimescaleChange(0, 0.2, transition_style=increase),
            LevelTimescaleChange(1, 0.2, timescale_ease=ease, transition_style=increase),
            LevelTimescaleChange(2, 1, transition_style=increase),
            LevelTimescaleChange(3, 1, timescale_ease=ease, transition_style=decrease),
            LevelTimescaleChange(4, 0.2, transition_style=decrease),
            LevelTimescaleChange(5, -1, transition_style=increase),
            LevelTimescaleChange(6, -1, timescale_ease=ease, transition_style=increase),
            LevelTimescaleChange(7, 1, transition_style=increase),
            LevelTimescaleChange(8, 1, timescale_ease=ease, transition_style=decrease),
            LevelTimescaleChange(9, -1, transition_style=decrease),
            LevelTimescaleChange(10, -1, transition_style=decrease),
        ]
    )


groups = [
    comparison_group(increase, decrease, ease)
    for increase, decrease in (
        (TransitionStyle.TIMESCALE, TransitionStyle.TIMESCALE),
        (TransitionStyle.SCROLL, TransitionStyle.SCROLL),
        (TransitionStyle.TIMESCALE, TransitionStyle.SCROLL),
        (TransitionStyle.SCROLL, TransitionStyle.TIMESCALE),
    )
    for ease in (EaseType.LINEAR, EaseType.IN_OUT_QUAD)
]
stages = [
    LevelStage(
        from_start=True,
        until_end=True,
        mask_changes=[LevelStageMaskChange(beat=0, lane=center, size=STAGE_HALF_WIDTH, mask_notes=True)],
        pivot_changes=[
            LevelStagePivotChange(
                beat=0,
                lane=center,
                division_size=1,
                division_parity=DivisionParity.ODD,
                abs_y_offset=0,
                y_beat_offset=0,
            )
        ],
        style_changes=[
            LevelStageStyleChange(
                beat=0,
                judge_line_color=JudgeLineColor.PURPLE,
                left_border_style=StageBorderStyle.DEFAULT,
                right_border_style=StageBorderStyle.DEFAULT,
                lane_alpha=1,
                judge_line_alpha=1,
                division_line_alpha=0,
            )
        ],
    )
    for center in STAGE_CENTERS
]
# BPM 60 makes beats equal seconds.
streams = [
    [
        LevelNote(
            beat=i * NOTE_STEP,
            lane=0,
            size=0.45,
            kind=NoteKind.NORM_TAP,
            stage=stage,
            timescale_group=group,
        )
        for i in range(1, int(DURATION / NOTE_STEP) + 1)
    ]
    for stage, group in zip(stages, [None, *groups], strict=True)
]
level = build_level(
    name="timescale-transition-comparison",
    title="Timescale Transition Comparison",
    bgm=_build_silent_wav(DURATION),
    entities=[LevelBpmChange(0, 60), *stages, *groups, *(note for stream in streams for note in stream)],
)
# Remove the builder's simultaneous-note lines so columns stay visually separate.
level_data = cast(LevelData, level.data)
level_data.entities = [entity for entity in level_data.entities if not isinstance(entity, SimLine)]
level.description = {
    "en": "Nine columns, left to right: normal reference; timescale pair; scroll pair; "
    "timescale up / scroll down pair; scroll up / timescale down pair. "
    "Each pair uses linear easing, then quadratic in-out easing. "
    "First five seconds: hold 0.2, ramp to 1, hold 1, ramp to 0.2, hold 0.2. "
    "Next five seconds: hold -1, ramp to 1, hold 1, ramp to -1, hold -1. Each phase lasts one second. "
    "Matched taps every 0.125s. Silent audio; use autoplay to compare."
}
