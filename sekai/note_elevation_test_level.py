from sekai.level_utils import (
    LevelBpmChange,
    LevelCameraChange,
    LevelEntities,
    LevelNote,
    LevelSlide,
    LevelStage,
    LevelStageMaskChange,
    LevelStagePivotChange,
    LevelStageTransformChange,
    _build_silent_wav,
    build_level,
)
from sekai.lib.connector import ConnectorKind
from sekai.lib.ease import EaseType
from sekai.lib.layout import FlickDirection
from sekai.lib.note import NoteKind
from sekai.lib.stage import DivisionParity

stages = [
    LevelStage(
        from_start=True,
        until_end=True,
        mask_changes=[LevelStageMaskChange(beat=0, lane=lane, size=2)],
        pivot_changes=[
            LevelStagePivotChange(
                beat=0, lane=lane, division_size=1, division_parity=DivisionParity.EVEN, abs_y_offset=0, y_beat_offset=0
            )
        ],
        transform_changes=[LevelStageTransformChange(beat=0, elevation=elevation)],
    )
    for lane, elevation in ((-3, 0), (3, 1))
]
entities: list[LevelEntities] = [
    LevelBpmChange(beat=0, bpm=120),
    *stages,
    *[
        LevelCameraChange(beat=beat, stage_tilt=tilt, ease=EaseType.IN_OUT_QUAD)
        for beat, tilt in ((0, 1), (16, 1), (20, 0), (24, 0), (28, 1), (36, 1))
    ],
]

for beat in range(4, 36):
    offset = (-0.5, 0, 0.5, 1)[beat % 4]
    entities.extend(
        LevelNote(
            beat=beat,
            lane=-1,
            size=0.4,
            kind=NoteKind.NORM_FLICK if beat % 4 == 3 else NoteKind.NORM_TAP,
            direction=FlickDirection.UP_RIGHT,
            stage=stage,
            elevation=offset,
        )
        for stage in stages
    )

for start in (4, 12, 20, 28):
    for stage in stages:
        slide = LevelSlide()
        slide.notes = [
            LevelNote(
                beat=start,
                lane=1,
                size=0.4,
                kind=NoteKind.NORM_HEAD_TAP,
                stage=stage,
                elevation=-0.5,
                segment_kind=ConnectorKind.ACTIVE_NORMAL,
                connector_ease=EaseType.IN_OUT_QUAD,
            ),
            LevelNote(beat=start + 2, lane=0, size=0, kind=NoteKind.NORM_TICK, attach=slide),
            LevelNote(
                beat=start + 4,
                lane=1,
                size=0.4,
                kind=NoteKind.NORM_TAIL_FLICK,
                stage=stage,
                elevation=1,
            ),
        ]
        entities.append(slide)

entities.extend(
    LevelNote(beat=beat, lane=0, size=0.4, kind=NoteKind.CRIT_TAP, is_fake=True, elevation=2)
    for beat in (6, 14, 22, 30)
)

level = build_level(
    name="note-elevation-test",
    title="Note Elevation Test",
    bgm=_build_silent_wav(20),
    entities=entities,
)
