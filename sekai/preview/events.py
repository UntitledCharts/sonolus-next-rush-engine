from __future__ import annotations

from sonolus.script.archetype import (
    EntityRef,
    PreviewArchetype,
    StandardImport,
    callback,
    entity_data,
    imported,
    shared_memory,
)
from sonolus.script.printing import PrintColor, PrintFormat
from sonolus.script.timing import beat_to_time

from sekai.lib import archetype_names
from sekai.lib.fever import FeverWindows
from sekai.lib.layer import LAYER_FEVER_LINE_BOTTOM, LAYER_FEVER_LINE_TOP, LAYER_SKILL_LINE, get_z_alt
from sekai.lib.skin import ActiveSkin
from sekai.preview.layout import layout_preview_bar_line, print_at_time


class PreviewSkill(PreviewArchetype):
    name = archetype_names.SKILL

    beat: StandardImport.BEAT = imported()

    time: float = entity_data()

    next_ref: EntityRef[PreviewSkill] = shared_memory()
    num: int = shared_memory()

    def preprocess(self):
        self.time = beat_to_time(self.beat)

    def render(self):
        ActiveSkin.skill_line.draw(
            layout_preview_bar_line(self.time, "both"),
            z=get_z_alt(LAYER_SKILL_LINE).tuple,
            a=0.8,
        )
        print_at_time(
            self.num,
            self.time,
            fmt=PrintFormat.NUMBER,
            color=PrintColor.GREEN,
            side="left",
        )
        print_at_time(
            round(self.time),
            self.time,
            fmt=PrintFormat.TIME,
            color=PrintColor.GREEN,
            side="right",
        )


class PreviewFeverChance(PreviewArchetype):
    name = archetype_names.FEVER_CHANCE

    beat: StandardImport.BEAT = imported()

    time: float = entity_data()
    end_time: float = entity_data()
    next_ref: EntityRef[PreviewFeverChance] = entity_data()

    @property
    def start_time(self) -> float:
        return self.time

    @callback(order=-4)
    def preprocess(self):
        self.time = beat_to_time(self.beat)
        self.next_ref.index = FeverWindows.chance_head
        FeverWindows.chance_head = self.index

    def render(self):
        ActiveSkin.fever_chance_line.draw(
            layout_preview_bar_line(self.time, "right"),
            z=get_z_alt(LAYER_FEVER_LINE_TOP).tuple,
            a=0.8,
        )
        ActiveSkin.fever_start_line.draw(
            layout_preview_bar_line(self.time, "left_only"),
            z=get_z_alt(LAYER_FEVER_LINE_BOTTOM).tuple,
            a=0.8,
        )
        print_at_time(
            round(self.time),
            self.time,
            fmt=PrintFormat.TIME,
            color=PrintColor.CYAN,
            side="right",
        )
        print_at_time(
            round(self.end_time),
            self.time,
            fmt=PrintFormat.TIME,
            color=PrintColor.BLUE,
            side="left",
        )


class PreviewFeverStart(PreviewArchetype):
    name = archetype_names.FEVER_START

    beat: StandardImport.BEAT = imported()

    time: float = entity_data()
    next_ref: EntityRef[PreviewFeverStart] = entity_data()
    chance_index: int = entity_data()

    @property
    def start_time(self) -> float:
        return self.time

    @callback(order=-4)
    def preprocess(self):
        self.time = beat_to_time(self.beat)
        self.next_ref.index = FeverWindows.start_head
        FeverWindows.start_head = self.index

    def render(self):
        ActiveSkin.fever_start_line.draw(
            layout_preview_bar_line(self.time, "right"),
            z=get_z_alt(LAYER_FEVER_LINE_TOP).tuple,
            a=0.8,
        )
        ActiveSkin.fever_chance_line.draw(
            layout_preview_bar_line(self.time, "left_only"),
            z=get_z_alt(LAYER_FEVER_LINE_BOTTOM).tuple,
            a=0.8,
        )
        print_at_time(
            round(self.time),
            self.time,
            fmt=PrintFormat.TIME,
            color=PrintColor.BLUE,
            side="right",
        )
        print_at_time(
            round(PreviewFeverChance.at(self.chance_index).time),
            self.time,
            fmt=PrintFormat.TIME,
            color=PrintColor.CYAN,
            side="left",
        )


PREVIEW_EVENT_ARCHETYPES = (PreviewSkill, PreviewFeverChance, PreviewFeverStart)
