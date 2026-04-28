from typing import Any, Literal

from sonolus.script.archetype import PlayArchetype
from sonolus.script.level import ExternalEntityData, ExternalLevelData, LevelData
from sonolus.script.timing import TimescaleEase

from sekai.lib.connector import ConnectorKind
from sekai.lib.ease import EaseType
from sekai.lib.layout import FlickDirection
from sekai.play.bpm_change import BpmChange
from sekai.play.connector import Connector
from sekai.play.initialization import Initialization
from sekai.play.note import (
    AnchorNote,
    BaseNote,
    CriticalFlickNote,
    CriticalHeadTapNote,
    CriticalHeadTraceNote,
    CriticalTailFlickNote,
    CriticalTailReleaseNote,
    CriticalTailTraceNote,
    CriticalTapNote,
    CriticalTickNote,
    CriticalTraceFlickNote,
    CriticalTraceNote,
    DamageNote,
    NormalFlickNote,
    NormalHeadTapNote,
    NormalHeadTraceNote,
    NormalTailFlickNote,
    NormalTailReleaseNote,
    NormalTailTraceNote,
    NormalTapNote,
    NormalTickNote,
    NormalTraceFlickNote,
    NormalTraceNote,
    TransientHiddenTickNote,
)
from sekai.play.sim_line import SimLine
from sekai.play.timescale import TimescaleChange, TimescaleGroup

note_type_mapping = {
    "NormalTapNote": NormalTapNote,
    "CriticalTapNote": CriticalTapNote,
    "NormalFlickNote": NormalFlickNote,
    "CriticalFlickNote": CriticalFlickNote,
    "NormalSlideStartNote": NormalHeadTapNote,
    "CriticalSlideStartNote": CriticalHeadTapNote,
    "NormalSlideEndNote": NormalTailReleaseNote,
    "CriticalSlideEndNote": CriticalTailReleaseNote,
    "NormalSlideEndFlickNote": NormalTailFlickNote,
    "CriticalSlideEndFlickNote": CriticalTailFlickNote,
    "IgnoredSlideTickNote": TransientHiddenTickNote,
    "NormalSlideTickNote": NormalTickNote,
    "CriticalSlideTickNote": CriticalTickNote,
    "HiddenSlideTickNote": AnchorNote,
    "NormalAttachedSlideTickNote": NormalTickNote,
    "CriticalAttachedSlideTickNote": CriticalTickNote,
    "NormalTraceNote": NormalTraceNote,
    "CriticalTraceNote": CriticalTraceNote,
    "DamageNote": DamageNote,
    "NormalTraceFlickNote": NormalTraceFlickNote,
    "CriticalTraceFlickNote": CriticalTraceFlickNote,
    "NonDirectionalTraceFlickNote": NormalTraceFlickNote,
    "HiddenSlideStartNote": AnchorNote,
    "NormalTraceSlideStartNote": NormalHeadTraceNote,
    "CriticalTraceSlideStartNote": CriticalHeadTraceNote,
    "NormalTraceSlideEndNote": NormalTailTraceNote,
    "CriticalTraceSlideEndNote": CriticalTailTraceNote,
}


active_connector_kind_mapping = {
    "NormalSlideConnector": ConnectorKind.ACTIVE_NORMAL,
    "CriticalSlideConnector": ConnectorKind.ACTIVE_CRITICAL,
}

flick_direction_mapping = {
    -1: FlickDirection.UP_LEFT,
    0: FlickDirection.UP_OMNI,
    1: FlickDirection.UP_RIGHT,
}

ease_type_mapping = {
    -2: EaseType.OUT_IN_QUAD,
    -1: EaseType.OUT_QUAD,
    0: EaseType.LINEAR,
    1: EaseType.IN_QUAD,
    2: EaseType.IN_OUT_QUAD,
}

fade_alpha_mapping = {
    0: (1.0, 0.0),
    1: (1.0, 1.0),
    2: (0.0, 1.0),
}

guide_kind_mapping = {
    0: ConnectorKind.GUIDE_NEUTRAL,
    1: ConnectorKind.GUIDE_RED,
    2: ConnectorKind.GUIDE_GREEN,
    3: ConnectorKind.GUIDE_BLUE,
    4: ConnectorKind.GUIDE_YELLOW,
    5: ConnectorKind.GUIDE_PURPLE,
    6: ConnectorKind.GUIDE_CYAN,
    7: ConnectorKind.GUIDE_BLACK,
}


class ExtendedLevelData:
    entities: list[ExternalEntityData]
    entities_by_archetype: dict[str, list[tuple[int, ExternalEntityData]]]
    note_entities: list[tuple[int, ExternalEntityData]]
    connector_entities: list[tuple[int, ExternalEntityData]]

    def __init__(self, entities: list[ExternalEntityData]):
        self.entities = entities
        self.entities_by_archetype = {}
        self.note_entities = []
        self.connector_entities = []
        for i, entity in enumerate(entities):
            if entity.archetype not in self.entities_by_archetype:
                self.entities_by_archetype[entity.archetype] = []
            self.entities_by_archetype[entity.archetype].append((i, entity))

            if entity.archetype in note_type_mapping:
                self.note_entities.append((i, entity))
            if entity.archetype in active_connector_kind_mapping:
                self.connector_entities.append((i, entity))

    def iter_all(self):
        return iter(self.entities)

    def enumerate_all(self):
        return enumerate(self.entities)

    def iter_by_archetype(self, archetype: str):
        return (entity for i, entity in self.entities_by_archetype.get(archetype, []))

    def enumerate_by_archetype(self, archetype: str):
        return iter(self.entities_by_archetype.get(archetype, []))

    def __getitem__(self, index: int) -> ExternalEntityData:
        return self.entities[index]

    def iter_note_archetypes(self):
        return iter(self.note_entities)

    def iter_active_connector_archetypes(self):
        return iter(self.connector_entities)


def convert_extended_level_data(data: ExternalLevelData) -> LevelData | None:
    if not any(e.archetype == "TimeScaleGroup" for e in data.entities):
        return None
    extended_data = ExtendedLevelData(data.entities)
    bpm_changes = convert_bpm_changes(extended_data)
    timescale_groups_by_index, timescale_entities = convert_timescale_groups(extended_data)
    notes = convert_notes(extended_data, timescale_groups_by_index)
    guides = convert_guides(extended_data, timescale_groups_by_index)
    entities = [
        Initialization(),
        *bpm_changes,
        *timescale_entities,
        *notes,
        *guides,
    ]
    entities = sorted(entities, key=lambda e: (not isinstance(e, Initialization), (getattr(e, "beat", -1))))
    link_slide_notes(entities)
    return LevelData(
        bgm_offset=data.bgm_offset,
        entities=entities,
    )


def convert_timescale_groups(data: ExtendedLevelData) -> tuple[dict[int, TimescaleChange], list[PlayArchetype]]:
    groups_by_original_index = {}
    entities = []
    for i, entity in data.enumerate_by_archetype("TimeScaleGroup"):
        group = TimescaleGroup()
        changes = []
        raw_change = data[entity.data["first"]]
        while True:
            change = TimescaleChange(
                beat=raw_change.data["#BEAT"],
                timescale=raw_change.data["timeScale"],
                timescale_skip=0.0,
                timescale_group=group.ref(),
                timescale_ease=TimescaleEase.NONE,
            )
            if changes:
                changes[-1].next_ref = change.ref()
            changes.append(change)
            if raw_change.data.get("next", 0) <= 0:
                break
            raw_change = data[raw_change.data["next"]]
        if changes:
            group.first_ref = changes[0].ref()
        groups_by_original_index[i] = group
        entities.append(group)
        entities.extend(changes)
    return groups_by_original_index, entities


def convert_bpm_changes(data: ExtendedLevelData) -> list[PlayArchetype]:
    entities = []
    for entity in data.iter_by_archetype("#BPM_CHANGE"):
        bpm_change = BpmChange(
            beat=entity.data["#BEAT"],
            bpm=entity.data["#BPM"],
        )
        entities.append(bpm_change)
    return entities


def convert_notes(
    data: ExtendedLevelData, timescale_groups_by_index: dict[int, TimescaleChange]
) -> list[PlayArchetype]:
    entities = []
    notes_by_original_index = {}
    connectors_by_original_index = {}
    for i, entity in data.iter_note_archetypes():
        note_class = note_type_mapping[entity.archetype]
        note = note_class(
            beat=entity.data["#BEAT"],
            lane=entity.data.get("lane", 0.0),
            size=entity.data.get("size", 0.0),
            direction=flick_direction_mapping[entity.data.get("direction", 0)],
            segment_kind=ConnectorKind.ACTIVE_NORMAL,
        )
        entities.append(note)
        notes_by_original_index[i] = note
    for i, entity in data.iter_active_connector_archetypes():
        connector = Connector(
            head_ref=notes_by_original_index[entity.data["head"]].ref(),
            tail_ref=notes_by_original_index[entity.data["tail"]].ref(),
            segment_head_ref=notes_by_original_index[entity.data["start"]].ref(),
            segment_tail_ref=notes_by_original_index[entity.data["end"]].ref(),
            active_head_ref=notes_by_original_index[entity.data["start"]].ref(),
            active_tail_ref=notes_by_original_index[entity.data["end"]].ref(),
        )
        head = notes_by_original_index[entity.data["head"]]
        tail = notes_by_original_index[entity.data["tail"]]
        segment_head = notes_by_original_index[entity.data["start"]]
        head.connector_ease = ease_type_mapping[entity.data["ease"]]
        connector_kind = active_connector_kind_mapping[entity.archetype]
        head.segment_kind = connector_kind
        tail.segment_kind = connector_kind
        segment_head.segment_kind = connector_kind
        entities.append(connector)
        connectors_by_original_index[i] = connector
    for i, note in notes_by_original_index.items():
        entity = data[i]
        timescale_group_index = entity.data.get("timeScaleGroup", -1)
        if timescale_group_index in timescale_groups_by_index:
            note.timescale_group = timescale_groups_by_index[timescale_group_index].ref()
        attach_index = entity.data.get("attach", -1)
        if attach_index > 0:
            attach_connector = connectors_by_original_index[attach_index]
            note.attach_head_ref = attach_connector.head_ref
            note.attach_tail_ref = attach_connector.tail_ref
            note.is_attached = True
        slide_index = entity.data.get("slide", -1)
        if slide_index > 0:
            slide_connector = connectors_by_original_index[slide_index]
            note.active_head_ref = slide_connector.active_head_ref
    for entity in data.iter_by_archetype("SimLine"):
        sim_line = SimLine(
            left_ref=notes_by_original_index[entity.data["a"]].ref(),
            right_ref=notes_by_original_index[entity.data["b"]].ref(),
        )
        entities.append(sim_line)
    return entities


def convert_guides(
    data: ExtendedLevelData, timescale_groups_by_index: dict[int, TimescaleChange]
) -> list[PlayArchetype]:
    entities = []

    anchors_by_beat = {}
    anchor_positions = {}

    def get_anchor(
        beat: float,
        lane: float,
        size: float,
        timescale_group: Any,
        pos: Literal["segment_head", "segment_tail", "head", "tail"],
        segment_kind: ConnectorKind | None = None,
        segment_alpha: float | None = None,
        connector_ease: EaseType | None = None,
    ) -> BaseNote:
        if beat in anchors_by_beat:
            for anchor in anchors_by_beat[beat]:
                if pos in anchor_positions[anchor]:
                    continue
                if (
                    anchor.lane == lane
                    and anchor.size == size
                    and anchor.timescale_group == timescale_group
                    and (segment_kind is None or anchor.segment_kind in (segment_kind, -1))
                    and (segment_alpha is None or anchor.segment_alpha in (segment_alpha, -1))
                    and (connector_ease is None or anchor.connector_ease in (connector_ease, -1))
                ):
                    if segment_kind is not None and anchor.segment_kind == -1:
                        anchor.segment_kind = segment_kind
                    if segment_alpha is not None and anchor.segment_alpha == -1:
                        anchor.segment_alpha = segment_alpha
                    if connector_ease is not None and anchor.connector_ease == -1:
                        anchor.connector_ease = connector_ease
                    anchor_positions[anchor].add(pos)
                    return anchor
        anchor = AnchorNote(
            beat=beat,
            lane=lane,
            size=size,
            timescale_group=timescale_group,
            segment_kind=segment_kind if segment_kind is not None else -1,
            segment_alpha=segment_alpha if segment_alpha is not None else -1,
            connector_ease=connector_ease if connector_ease is not None else -1,
        )
        entities.append(anchor)
        if beat not in anchors_by_beat:
            anchors_by_beat[beat] = []
        anchors_by_beat[beat].append(anchor)
        anchor_positions[anchor] = {pos}
        return anchor

    for entity in data.iter_by_archetype("Guide"):
        start_beat = entity.data["startBeat"]
        start_lane = entity.data["startLane"]
        start_size = entity.data["startSize"]
        start_timescale_group = timescale_groups_by_index[entity.data["startTimeScaleGroup"]].ref()
        head_beat = entity.data["headBeat"]
        head_lane = entity.data["headLane"]
        head_size = entity.data["headSize"]
        head_timescale_group = timescale_groups_by_index[entity.data["headTimeScaleGroup"]].ref()
        tail_beat = entity.data["tailBeat"]
        tail_lane = entity.data["tailLane"]
        tail_size = entity.data["tailSize"]
        tail_timescale_group = timescale_groups_by_index[entity.data["tailTimeScaleGroup"]].ref()
        end_beat = entity.data["endBeat"]
        end_lane = entity.data["endLane"]
        end_size = entity.data["endSize"]
        end_timescale_group = timescale_groups_by_index[entity.data["endTimeScaleGroup"]].ref()
        ease = ease_type_mapping[entity.data.get("ease", 0)]
        start_alpha, end_alpha = fade_alpha_mapping[entity.data.get("fade", 1)]
        kind = guide_kind_mapping[entity.data.get("color", 0)]

        start = get_anchor(
            beat=start_beat,
            lane=start_lane,
            size=start_size,
            pos="segment_head",
            timescale_group=start_timescale_group,
            segment_kind=kind,
            segment_alpha=start_alpha,
        )
        end = get_anchor(
            beat=end_beat,
            lane=end_lane,
            size=end_size,
            pos="segment_tail",
            timescale_group=end_timescale_group,
            segment_kind=kind,
            segment_alpha=end_alpha,
        )
        head = get_anchor(
            beat=head_beat,
            lane=head_lane,
            size=head_size,
            pos="head",
            timescale_group=head_timescale_group,
            segment_kind=kind,
            connector_ease=ease,
        )
        tail = get_anchor(
            beat=tail_beat,
            lane=tail_lane,
            size=tail_size,
            pos="tail",
            timescale_group=tail_timescale_group,
            segment_kind=kind,
        )
        connector = Connector(
            head_ref=head.ref(),
            tail_ref=tail.ref(),
            segment_head_ref=start.ref(),
            segment_tail_ref=end.ref(),
        )
        entities.append(connector)

    for anchor_list in anchors_by_beat.values():
        for anchor in anchor_list:
            if anchor.segment_kind == -1:
                anchor.segment_kind = ConnectorKind.GUIDE_NEUTRAL
            if anchor.segment_alpha == -1:
                anchor.segment_alpha = 1.0
            if anchor.connector_ease == -1:
                anchor.connector_ease = EaseType.LINEAR

    return entities


def link_slide_notes(entities: list[PlayArchetype]) -> None:
    for entity in entities:
        if not isinstance(entity, Connector):
            continue
        head = entity.head_ref.get()
        tail = entity.tail_ref.get()
        head.next_ref = tail.ref()
