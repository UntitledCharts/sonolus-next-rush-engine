from math import floor

from sonolus.script.archetype import PlayArchetype, callback, entity_memory
from sonolus.script.bucket import Judgment
from sonolus.script.globals import level_memory
from sonolus.script.interval import clamp
from sonolus.script.runtime import level_score, time

from sekai.lib import archetype_names
from sekai.lib.buckets import SekaiWindow
from sekai.lib.custom_elements import (
    draw_combo_label,
    draw_combo_number,
    draw_damage_flash,
    draw_judgment_accuracy,
    draw_judgment_text,
)
from sekai.lib.options import Options
from sekai.play import initialization, note
from sekai.play.events import Fever


def spawn_custom(
    judgment: Judgment,
    accuracy: float,
    windows: SekaiWindow,
    wrong_way: bool,
    target_time: float,
    index: int,
):
    ComboJudge.spawn(
        index=index,
        target_time=target_time,
        spawn_time=time(),
        judgment=judgment,
        accuracy=accuracy,
    )
    if judgment != Judgment.PERFECT and windows.bad.start < accuracy < windows.bad.end:
        JudgmentAccuracy.spawn(
            spawn_time=time(),
            judgment=judgment,
            accuracy=accuracy,
            windows=windows,
            wrong_way=wrong_way,
        )
    if judgment == Judgment.MISS:
        DamageFlash.spawn(spawn_time=time())


@level_memory
class ComboJudgeMemory:
    ap: bool
    combo_check: int
    latest_judge_id: int


@level_memory
class ScoreIndicator:
    score: float
    note_score: float
    note_time: float
    percentage: float
    total_weight: float
    total_weight_compensation: float
    acc_sum: float
    acc_compensation: float
    processed_weight: float
    processed_weight_compensation: float
    max_score: int
    current_raw_score: float
    raw_score_compensation: float
    count: int
    perfect_step: int
    great_step: int
    good_step: int


@level_memory
class LifeManager:
    life: int


class ComboJudge(PlayArchetype):
    target_time: float = entity_memory()
    spawn_time: float = entity_memory()
    judgment: Judgment = entity_memory()
    accuracy: float = entity_memory()
    windows: SekaiWindow = entity_memory()
    wrong_way: bool = entity_memory()
    my_judge_id: int = entity_memory()
    index: int = entity_memory()

    check: bool = entity_memory()
    combo: int = entity_memory()
    z: float = entity_memory()
    z1: float = entity_memory()
    z2: float = entity_memory()
    name = archetype_names.COMBO_JUDGE

    def initialize(self):
        self.z = initialization.LayerCache.judgment
        self.z1 = initialization.LayerCache.judgment1
        self.z2 = initialization.LayerCache.judgment2

    def update_parallel(self):
        if self.my_judge_id != ComboJudgeMemory.latest_judge_id:
            self.despawn = True
            return
        draw_combo_label(ap=ComboJudgeMemory.ap, z=self.z, z1=self.z1, combo=self.combo)
        draw_combo_number(
            draw_time=self.spawn_time, ap=ComboJudgeMemory.ap, combo=self.combo, z=self.z, z1=self.z1, z2=self.z2
        )
        draw_judgment_text(
            draw_time=self.spawn_time,
            judgment=self.judgment,
            windows=self.windows,
            accuracy=self.accuracy,
            z=self.z,
        )

    @callback(order=3)
    def update_sequential(self):
        if self.check:
            return
        self.check = True

        ComboJudgeMemory.latest_judge_id += 1
        self.my_judge_id = ComboJudgeMemory.latest_judge_id

        if self.judgment in (Judgment.MISS, Judgment.GOOD):
            ComboJudgeMemory.combo_check = 0
            self.combo = ComboJudgeMemory.combo_check
        else:
            ComboJudgeMemory.combo_check += 1
            self.combo = ComboJudgeMemory.combo_check

        if self.judgment != Judgment.PERFECT:
            ComboJudgeMemory.ap = True

        self.check_fever_count()

        self.calculate_score()

        self.calculate_life()

    def check_fever_count(self):
        if Fever.fever_chance_time <= self.target_time < Fever.fever_start_time:
            if self.judgment in (Judgment.MISS, Judgment.GOOD):
                Fever.fever_chance_cant_super_fever = True
            else:
                Fever.fever_chance_current_combo += 1

    def calculate_score(self):
        if Options.custom_score == 0 and not Options.custom_score_bar:
            return
        # score = judgmentMultiplier * (consecutiveJudgmentMultiplier + archetypeMultiplier + entityMultiplier)
        judgment_multiplier = 0
        match self.judgment:
            case Judgment.PERFECT:
                judgment_multiplier = level_score().perfect_multiplier
                ScoreIndicator.perfect_step += 1
                ScoreIndicator.great_step += 1
                ScoreIndicator.good_step += 1
            case Judgment.GREAT:
                judgment_multiplier = level_score().great_multiplier
                ScoreIndicator.perfect_step = 0
                ScoreIndicator.great_step += 1
                ScoreIndicator.good_step += 1
            case Judgment.GOOD:
                judgment_multiplier = level_score().good_multiplier
                ScoreIndicator.perfect_step = 0
                ScoreIndicator.great_step = 0
                ScoreIndicator.good_step += 1
            case Judgment.MISS:
                judgment_multiplier = 0
                ScoreIndicator.perfect_step = 0
                ScoreIndicator.great_step = 0
                ScoreIndicator.good_step = 0

        inv_perfect_step = (
            1.0 / level_score().consecutive_perfect_step if level_score().consecutive_perfect_step > 0 else 0.0
        )
        inv_great_step = 1.0 / level_score().consecutive_great_step if level_score().consecutive_great_step > 0 else 0.0
        inv_good_step = 1.0 / level_score().consecutive_good_step if level_score().consecutive_good_step > 0 else 0.0
        note_raw_score = judgment_multiplier * (
            (
                min(
                    floor(ScoreIndicator.perfect_step * inv_perfect_step)
                    * level_score().consecutive_perfect_multiplier,
                    (level_score().consecutive_perfect_cap * inv_perfect_step)
                    * level_score().consecutive_perfect_multiplier,
                )
                + min(
                    floor(ScoreIndicator.great_step * inv_great_step) * level_score().consecutive_great_multiplier,
                    (level_score().consecutive_great_cap * inv_great_step) * level_score().consecutive_great_multiplier,
                )
                + min(
                    floor(ScoreIndicator.good_step * inv_good_step) * level_score().consecutive_good_multiplier,
                    (level_score().consecutive_good_cap * inv_good_step) * level_score().consecutive_good_multiplier,
                )
            )
            + note.BaseNote.at(self.index).archetype_score_multiplier
            + note.BaseNote.at(self.index).entity_score_multiplier
        )
        raw_calc = (note_raw_score * ScoreIndicator.max_score) / ScoreIndicator.total_weight
        note_score = raw_calc
        ScoreIndicator.note_score = note_score if note_score > 0 else ScoreIndicator.note_score
        ScoreIndicator.note_time = self.spawn_time if note_score > 0 else ScoreIndicator.note_time

        y = note_raw_score - ScoreIndicator.raw_score_compensation
        t = ScoreIndicator.current_raw_score + y
        ScoreIndicator.raw_score_compensation = (t - ScoreIndicator.current_raw_score) - y
        ScoreIndicator.current_raw_score = t

        final_calc = (ScoreIndicator.current_raw_score / ScoreIndicator.total_weight) * ScoreIndicator.max_score
        ScoreIndicator.score = clamp(
            final_calc,
            0,
            ScoreIndicator.max_score,
        )
        match Options.custom_score:
            case 1:
                ScoreIndicator.percentage = (ScoreIndicator.current_raw_score / ScoreIndicator.total_weight) * 100.0
            case 2:
                ideal_combo = note.BaseNote.at(self.index).count
                note_ideal_weight = level_score().perfect_multiplier * (
                    (
                        min(
                            floor(ideal_combo * inv_perfect_step) * level_score().consecutive_perfect_multiplier,
                            (level_score().consecutive_perfect_cap * inv_perfect_step)
                            * level_score().consecutive_perfect_multiplier,
                        )
                        + min(
                            floor(ideal_combo * inv_great_step) * level_score().consecutive_great_multiplier,
                            (level_score().consecutive_great_cap * inv_great_step)
                            * level_score().consecutive_great_multiplier,
                        )
                        + min(
                            floor(ideal_combo * inv_good_step) * level_score().consecutive_good_multiplier,
                            (level_score().consecutive_good_cap * inv_good_step)
                            * level_score().consecutive_good_multiplier,
                        )
                    )
                    + note.BaseNote.at(self.index).archetype_score_multiplier
                    + note.BaseNote.at(self.index).entity_score_multiplier
                )
                y2 = note_ideal_weight - ScoreIndicator.processed_weight_compensation
                t2 = ScoreIndicator.processed_weight + y2
                ScoreIndicator.processed_weight_compensation = (t2 - ScoreIndicator.processed_weight) - y2
                ScoreIndicator.processed_weight = t2

                current_loss = ScoreIndicator.processed_weight - ScoreIndicator.current_raw_score
                current_visible_score = ScoreIndicator.total_weight - current_loss
                percent = (current_visible_score / ScoreIndicator.total_weight) * 100.0
                ScoreIndicator.percentage = clamp(percent, 0.0, 100.0)
            case 3:
                ScoreIndicator.count += 1
                current_acc = (1 - abs(self.accuracy)) * 100

                y = current_acc - ScoreIndicator.acc_compensation
                t = ScoreIndicator.acc_sum + y
                ScoreIndicator.acc_compensation = (t - ScoreIndicator.acc_sum) - y
                ScoreIndicator.acc_sum = t

                ScoreIndicator.percentage = ScoreIndicator.acc_sum / ScoreIndicator.count

    def calculate_life(self):
        if not Options.custom_life_bar:
            return
        if LifeManager.life == 0:
            return
        match self.judgment:
            case Judgment.PERFECT:
                LifeManager.life += (
                    note.BaseNote.at(self.index).archetype_life.perfect_increment
                    + note.BaseNote.at(self.index).entity_life.perfect_increment
                )
            case Judgment.GREAT:
                LifeManager.life += (
                    note.BaseNote.at(self.index).archetype_life.great_increment
                    + note.BaseNote.at(self.index).entity_life.great_increment
                )
            case Judgment.GOOD:
                LifeManager.life += (
                    note.BaseNote.at(self.index).archetype_life.good_increment
                    + note.BaseNote.at(self.index).entity_life.good_increment
                )
            case Judgment.MISS:
                LifeManager.life += (
                    note.BaseNote.at(self.index).archetype_life.miss_increment
                    + note.BaseNote.at(self.index).entity_life.miss_increment
                )
        LifeManager.life = clamp(LifeManager.life, 0, 2000)


@level_memory
class JudgmentAccuracyMemory:
    combo_check: int


class JudgmentAccuracy(PlayArchetype):
    spawn_time: float = entity_memory()
    judgment: Judgment = entity_memory()
    accuracy: float = entity_memory()
    windows: SekaiWindow = entity_memory()
    wrong_way: bool = entity_memory()
    z: float = entity_memory()
    check: bool = entity_memory()
    combo: int = entity_memory()
    name = archetype_names.JUDGMENT_ACCURACY

    def initialize(self):
        self.z = initialization.LayerCache.judgment

    def update_parallel(self):
        if self.combo != JudgmentAccuracyMemory.combo_check:
            self.despawn = True
            return
        if time() >= self.spawn_time + 0.5:
            self.despawn = True
            return
        if not Options.custom_accuracy:
            self.despawn = True
            return
        draw_judgment_accuracy(
            judgment=self.judgment,
            accuracy=self.accuracy,
            windows=self.windows,
            wrong_way=self.wrong_way,
            z=self.z,
        )

    @callback(order=3)
    def update_sequential(self):
        if self.check:
            return
        self.check = True
        JudgmentAccuracyMemory.combo_check += 1
        self.combo = JudgmentAccuracyMemory.combo_check


@level_memory
class DamageFlashMemory:
    combo_check: int


class DamageFlash(PlayArchetype):
    spawn_time: float = entity_memory()
    check: bool = entity_memory()
    combo: int = entity_memory()
    z: float = entity_memory()
    name = archetype_names.DAMAGE_FLASH

    def initialize(self):
        self.z = initialization.LayerCache.damage

    def update_parallel(self):
        if self.combo != DamageFlashMemory.combo_check:
            self.despawn = True
            return
        if time() >= self.spawn_time + 0.35:
            self.despawn = True
            return
        if not Options.custom_damage:
            self.despawn = True
            return
        draw_damage_flash(draw_time=self.spawn_time, z=self.z)

    @callback(order=3)
    def update_sequential(self):
        if self.check:
            return
        self.check = True
        DamageFlashMemory.combo_check += 1
        self.combo = DamageFlashMemory.combo_check


CUSTOM_ARCHETYPES = (
    ComboJudge,
    JudgmentAccuracy,
    DamageFlash,
)
