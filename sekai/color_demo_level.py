"""A short phrase per note and connector color."""

from sekai.level_utils import (
    LevelBpmChange,
    LevelEntities,
    LevelNote,
    LevelSlide,
    LevelStage,
    LevelStageMaskChange,
    _build_silent_wav,
    build_level,
)
from sekai.lib.connector import ConnectorKind
from sekai.lib.layout import FlickDirection
from sekai.lib.note import NoteKind
from sekai.lib.note_style import NoteStyle

BPM = 160.0
START_BEAT = 2.0
SECTION_BEATS = 4.0
STYLES = tuple(NoteStyle)
END_BEAT = START_BEAT + SECTION_BEATS * len(STYLES) + 2.0
NORMAL_LANE = -5.0
CRITICAL_LANE = 5.0
DAMAGE_LANE = -1.0
FAKE_NORMAL_LANE = -3.0
FAKE_CRITICAL_LANE = 3.0
FAKE_DAMAGE_LANE = 1.0
NOTE_SIZE = 1.0

stage = LevelStage(
    from_start=True,
    until_end=True,
    mask_changes=[LevelStageMaskChange(beat=0, lane=0, size=6)],
)
entities: list[LevelEntities] = [LevelBpmChange(beat=0, bpm=BPM), stage]


def connector_kind(style: NoteStyle, family: int, *, fake: bool = False) -> ConnectorKind:
    value = family if style == NoteStyle.DEFAULT else 10 * family + style
    return ConnectorKind(value + (50 if fake else 0))


def add_pair(
    beat: float,
    style: NoteStyle,
    family: str,
    lane: float,
    direction: FlickDirection = FlickDirection.UP_OMNI,
):
    for prefix, note_lane in (("NORM", -lane), ("CRIT", lane)):
        entities.append(
            LevelNote(
                beat=beat,
                lane=note_lane,
                size=NOTE_SIZE,
                kind=NoteKind[f"{prefix}_{family}"],
                direction=direction,
                style=style,
                stage=stage,
            )
        )


def add_slide(
    beat: float,
    style: NoteStyle,
    critical: bool,
    *,
    fake: bool = False,
):
    prefix = "CRIT" if critical else "NORM"
    if fake:
        lane = FAKE_CRITICAL_LANE if critical else FAKE_NORMAL_LANE
    else:
        lane = CRITICAL_LANE if critical else NORMAL_LANE
    kind = connector_kind(style, 2 if critical else 1, fake=fake)
    slide = LevelSlide()
    for offset, suffix in (
        (0, "HEAD_TAP"),
        (0.5, "TICK"),
        (1.5, "TAIL_RELEASE"),
    ):
        slide.notes.append(
            LevelNote(
                beat=beat + offset,
                lane=lane,
                size=NOTE_SIZE,
                kind=NoteKind[f"{prefix}_{suffix}"],
                style=style,
                is_fake=fake,
                segment_kind=kind,
                stage=stage,
            )
        )
    entities.append(slide)
    entities.append(
        LevelNote(
            beat=beat + 1,
            lane=0,
            size=0,
            kind=NoteKind[f"{prefix}_TICK"],
            style=style,
            is_fake=fake,
            attach=slide,
        )
    )


def add_damage_slide(beat: float, style: NoteStyle, *, fake: bool):
    entities.append(
        LevelSlide(
            notes=[
                LevelNote(
                    beat=beat + offset,
                    lane=FAKE_DAMAGE_LANE if fake else DAMAGE_LANE,
                    size=NOTE_SIZE,
                    kind=NoteKind.DAMAGE,
                    style=style,
                    is_fake=fake,
                    segment_kind=connector_kind(style, 3, fake=fake),
                    stage=stage,
                )
                for offset in (0, 1.5)
            ]
        )
    )


for index, style in enumerate(STYLES):
    beat = START_BEAT + index * SECTION_BEATS
    add_pair(beat, style, "TAP", 5)
    add_pair(beat, style, "FLICK", 3)
    add_pair(beat, style, "FLICK", 1, FlickDirection.DOWN_OMNI)
    add_pair(beat + 1, style, "TRACE", 5)
    add_pair(beat + 1, style, "TRACE_FLICK", 3)
    add_pair(beat + 1, style, "TRACE_FLICK", 1, FlickDirection.DOWN_OMNI)
    for critical in (False, True):
        add_slide(beat + 2, style, critical)
        add_slide(beat + 2, style, critical, fake=True)
    add_damage_slide(beat + 2, style, fake=False)
    add_damage_slide(beat + 2, style, fake=True)

level = build_level(
    name="color-demo",
    title="Note and Connector Colors",
    bgm=_build_silent_wav(END_BEAT * 60 / BPM),
    entities=entities,
)
level.description = {
    "en": "One phrase per color: taps and flicks, traces, then holds with ticks. "
    "Normal notes are left and critical notes right. Silent audio; use autoplay or watch mode."
}
