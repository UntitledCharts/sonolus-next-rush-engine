from sonolus.script.archetype import EntityRef, WatchArchetype, callback, entity_memory
from sonolus.script.bucket import Judgment
from sonolus.script.globals import level_memory
from sonolus.script.runtime import is_replay

from sekai.lib import archetype_names
from sekai.lib.custom_elements import (
    draw_combo_label,
    draw_combo_number,
    draw_damage_flash,
    draw_judgment_accuracy,
    draw_judgment_text,
)
from sekai.lib.options import Options
from sekai.watch import initialization, note
from sekai.watch.events import Fever


def spawn_custom(
    next_ref: EntityRef[note.WatchBaseNote],
    next_ref_accuracy: EntityRef[note.WatchBaseNote],
    next_ref_damage_flash: EntityRef[note.WatchBaseNote],
    note_index: int,
    judgment: Judgment,
    played_hit_effects: bool,
):
    ComboJudge.spawn(
        next_ref=next_ref,
        note_index=note_index,
    )
    if judgment != Judgment.PERFECT and played_hit_effects and is_replay():
        JudgmentAccuracy.spawn(
            next_ref=next_ref_accuracy,
            note_index=note_index,
        )
    if judgment == Judgment.MISS and is_replay():
        DamageFlash.spawn(
            next_ref=next_ref_damage_flash,
            note_index=note_index,
        )


@level_memory
class ScoreIndicator:
    score: float
    percentage: float
    ap: bool
    first: float
    note_score: float
    note_time: float


@level_memory
class LifeManager:
    life: int
    decrease_life: int
    first: float


class ComboJudge(WatchArchetype):
    next_ref: EntityRef[note.WatchBaseNote] = entity_memory()
    note_index: int = entity_memory()
    z: float = entity_memory()
    z1: float = entity_memory()
    z2: float = entity_memory()
    checker: float = entity_memory()
    name = archetype_names.COMBO_JUDGE

    def initialize(self):
        self.z = initialization.LayerCache.judgment
        self.z1 = initialization.LayerCache.judgment1
        self.z2 = initialization.LayerCache.judgment2

    def spawn_time(self) -> float:
        return note.WatchBaseNote.at(self.note_index).calc_time

    def despawn_time(self):
        if self.next_ref.index > 0:
            return self.next_ref.get().calc_time
        else:
            return 1e8

    def update_parallel(self):
        draw_combo_label(
            ap=note.WatchBaseNote.at(self.note_index).ap,
            z=self.z,
            z1=self.z1,
            combo=note.WatchBaseNote.at(self.note_index).combo,
        )
        draw_combo_number(
            draw_time=self.spawn_time(),
            ap=note.WatchBaseNote.at(self.note_index).ap,
            combo=note.WatchBaseNote.at(self.note_index).combo,
            z=self.z,
            z1=self.z1,
            z2=self.z2,
        )
        draw_judgment_text(
            draw_time=self.spawn_time(),
            judgment=note.WatchBaseNote.at(self.note_index).judgment,
            windows_bad=note.WatchBaseNote.at(self.note_index).judgment_window_bad,
            accuracy=note.WatchBaseNote.at(self.note_index).accuracy,
            check_pass=note.WatchBaseNote.at(self.note_index).played_hit_effects,
            z=self.z,
        )

    @callback(order=3)
    def update_sequential(self):
        if self.checker:
            return
        if Fever.fever_chance_time <= note.WatchBaseNote.at(self.note_index).calc_time < Fever.fever_start_time:
            Fever.fever_chance_current_combo = note.WatchBaseNote.at(self.note_index).count - Fever.fever_first_count

        if Options.custom_score > 0 or Options.custom_score_bar:
            ScoreIndicator.score = note.WatchBaseNote.at(self.note_index).score
            ScoreIndicator.percentage = note.WatchBaseNote.at(self.note_index).percentage
            ScoreIndicator.ap = note.WatchBaseNote.at(self.note_index).ap
            note_score = note.WatchBaseNote.at(self.note_index).note_raw_score
            ScoreIndicator.note_score = note_score if note_score > 0 else ScoreIndicator.note_score
            ScoreIndicator.note_time = self.spawn_time() if note_score > 0 else ScoreIndicator.note_time

        self.checker = True

    def terminate(self):
        self.checker = False


class JudgmentAccuracy(WatchArchetype):
    next_ref: EntityRef[note.WatchBaseNote] = entity_memory()
    note_index: int = entity_memory()
    z: float = entity_memory()
    name = archetype_names.JUDGMENT_ACCURACY

    def initialize(self):
        self.z = initialization.LayerCache.judgment

    def spawn_time(self) -> float:
        if not Options.custom_accuracy:
            return 1e8
        return note.WatchBaseNote.at(self.note_index).calc_time

    def despawn_time(self):
        if (
            self.next_ref.index > 0
            and note.WatchBaseNote.at(self.note_index).calc_time + 0.5 >= self.next_ref.get().calc_time
        ):
            return self.next_ref.get().calc_time
        else:
            return note.WatchBaseNote.at(self.note_index).calc_time + 0.5

    def update_parallel(self):
        draw_judgment_accuracy(
            judgment=note.WatchBaseNote.at(self.note_index).judgment,
            windows=note.WatchBaseNote.at(self.note_index).judgment_window,
            accuracy=note.WatchBaseNote.at(self.note_index).accuracy,
            wrong_way=note.WatchBaseNote.at(self.note_index).wrong_way_check,
            z=self.z,
        )


class DamageFlash(WatchArchetype):
    next_ref: EntityRef[note.WatchBaseNote] = entity_memory()
    note_index: int = entity_memory()
    z: float = entity_memory()
    name = archetype_names.DAMAGE_FLASH

    def initialize(self):
        self.z = initialization.LayerCache.damage

    def spawn_time(self) -> float:
        if not Options.custom_damage:
            return 1e8
        return note.WatchBaseNote.at(self.note_index).calc_time

    def despawn_time(self):
        if (
            self.next_ref.index > 0
            and note.WatchBaseNote.at(self.note_index).calc_time + 0.35 >= self.next_ref.get().calc_time
        ):
            return self.next_ref.get().calc_time
        else:
            return note.WatchBaseNote.at(self.note_index).calc_time + 0.35

    def update_parallel(self):
        draw_damage_flash(draw_time=self.spawn_time(), z=self.z)


CUSTOM_ARCHETYPES = (ComboJudge, JudgmentAccuracy, DamageFlash)
