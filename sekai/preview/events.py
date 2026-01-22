from sonolus.script.archetype import EntityRef, PreviewArchetype, StandardImport, entity_data, imported, shared_memory
from sonolus.script.globals import level_data
from sonolus.script.printing import PrintColor, PrintFormat
from sonolus.script.timing import beat_to_time

from sekai.lib import archetype_names
from sekai.lib.layer import LAYER_FEVER_LINE_BOTTOM, LAYER_FEVER_LINE_TOP, LAYER_SKILL_LINE, get_z
from sekai.lib.skin import ActiveSkin
from sekai.preview.layout import layout_preview_bar_line, print_at_time


@level_data
class PreviewEvents:
    fever_chance_time: float
    fever_start_time: float


class PreviewSkill(PreviewArchetype):
    name = archetype_names.SKILL

    beat: StandardImport.BEAT = imported()

    time: float = entity_data()

    next_ref: EntityRef[PreviewSkill] = shared_memory()  # noqa: F821
    num: int = shared_memory()

    def preprocess(self):
        self.time = beat_to_time(self.beat)

    def render(self):
        ActiveSkin.skill_line.draw(
            layout_preview_bar_line(self.time, "both"),
            z=get_z(LAYER_SKILL_LINE),
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

    def preprocess(self):
        self.time = beat_to_time(self.beat)
        PreviewEvents.fever_chance_time = (
            min(self.time, PreviewEvents.fever_chance_time) if PreviewEvents.fever_chance_time != 0 else self.time
        )

    def render(self):
        if self.time != PreviewEvents.fever_chance_time:
            return
        ActiveSkin.fever_chance_line.draw(
            layout_preview_bar_line(self.time, "right"),
            z=get_z(LAYER_FEVER_LINE_TOP),
            a=0.8,
        )
        ActiveSkin.fever_start_line.draw(
            layout_preview_bar_line(self.time, "left_only"),
            z=get_z(LAYER_FEVER_LINE_BOTTOM),
            a=0.8,
        )
        print_at_time(
            round(PreviewEvents.fever_chance_time),
            PreviewEvents.fever_chance_time,
            fmt=PrintFormat.TIME,
            color=PrintColor.CYAN,
            side="right",
        )
        print_at_time(
            round(PreviewEvents.fever_start_time),
            PreviewEvents.fever_chance_time,
            fmt=PrintFormat.TIME,
            color=PrintColor.BLUE,
            side="left",
        )


class PreviewFeverStart(PreviewArchetype):
    name = archetype_names.FEVER_START

    beat: StandardImport.BEAT = imported()

    time: float = entity_data()

    def preprocess(self):
        self.time = beat_to_time(self.beat)
        PreviewEvents.fever_start_time = (
            min(self.time, PreviewEvents.fever_start_time) if PreviewEvents.fever_start_time != 0 else self.time
        )

    def render(self):
        if self.time != PreviewEvents.fever_start_time:
            return
        ActiveSkin.fever_start_line.draw(
            layout_preview_bar_line(self.time, "right"),
            z=get_z(LAYER_FEVER_LINE_TOP),
            a=0.8,
        )
        ActiveSkin.fever_chance_line.draw(
            layout_preview_bar_line(self.time, "left_only"),
            z=get_z(LAYER_FEVER_LINE_BOTTOM),
            a=0.8,
        )
        print_at_time(
            round(PreviewEvents.fever_start_time),
            PreviewEvents.fever_start_time,
            fmt=PrintFormat.TIME,
            color=PrintColor.BLUE,
            side="right",
        )
        print_at_time(
            round(PreviewEvents.fever_chance_time),
            PreviewEvents.fever_start_time,
            fmt=PrintFormat.TIME,
            color=PrintColor.CYAN,
            side="left",
        )


PREVIEW_EVENT_ARCHETYPES = (PreviewSkill, PreviewFeverChance, PreviewFeverStart)
