from sonolus.script.archetype import PlayArchetype, callback, entity_memory
from sonolus.script.bucket import Judgment
from sonolus.script.globals import level_memory
from sonolus.script.interval import clamp
from sonolus.script.runtime import level_score, time

from sekai.lib import archetype_names
from sekai.lib.buckets import SekaiWindow
from sekai.lib.custom_elements import (
    LifeManager,
    ScoreIndicator,
    draw_combo_label,
    draw_combo_number,
    draw_damage_flash,
    draw_judgment_accuracy,
    draw_judgment_text,
)
from sekai.lib.initialization import calculate_note_weight
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
    played_hit_effects: bool,
):
    ComboJudge.spawn(
        index=index,
        target_time=target_time,
        spawn_time=time(),
        judgment=judgment,
        accuracy=accuracy,
        windows=windows,
    )
    if Options.custom_accuracy and judgment != Judgment.PERFECT and played_hit_effects:
        JudgmentAccuracy.spawn(
            spawn_time=time(),
            judgment=judgment,
            accuracy=accuracy,
            windows=windows,
            wrong_way=wrong_way,
        )
    if Options.custom_damage and judgment == Judgment.MISS:
        DamageFlash.spawn(spawn_time=time())


@level_memory
class ComboJudgeMemory:
    ap: bool
    combo_check: int
    latest_judge_id: int


class ComboJudge(PlayArchetype):
    target_time: float = entity_memory()
    spawn_time: float = entity_memory()
    judgment: Judgment = entity_memory()
    accuracy: float = entity_memory()
    windows: SekaiWindow = entity_memory()
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
        ls = level_score()
        judgment_multiplier = 0
        match self.judgment:
            case Judgment.PERFECT:
                judgment_multiplier = ls.perfect_multiplier
                ScoreIndicator.perfect_step += 1
                ScoreIndicator.great_step += 1
                ScoreIndicator.good_step += 1
            case Judgment.GREAT:
                judgment_multiplier = ls.great_multiplier
                ScoreIndicator.perfect_step = 0
                ScoreIndicator.great_step += 1
                ScoreIndicator.good_step += 1
            case Judgment.GOOD:
                judgment_multiplier = ls.good_multiplier
                ScoreIndicator.perfect_step = 0
                ScoreIndicator.great_step = 0
                ScoreIndicator.good_step += 1
            case Judgment.MISS:
                judgment_multiplier = 0
                ScoreIndicator.perfect_step = 0
                ScoreIndicator.great_step = 0
                ScoreIndicator.good_step = 0

        current_note = note.BaseNote.at(self.index)

        note_raw_score = judgment_multiplier * calculate_note_weight(
            perfect_step=ScoreIndicator.perfect_step,
            great_step=ScoreIndicator.great_step,
            good_step=ScoreIndicator.good_step,
            archetype_multiplier=current_note.archetype_score_multiplier,
            entity_multiplier=current_note.entity_score_multiplier,
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
                ideal_combo = current_note.count
                note_ideal_weight = ls.perfect_multiplier * calculate_note_weight(
                    perfect_step=ideal_combo,
                    great_step=ideal_combo,
                    good_step=ideal_combo,
                    archetype_multiplier=current_note.archetype_score_multiplier,
                    entity_multiplier=current_note.entity_score_multiplier,
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
        current_note = note.BaseNote.at(self.index)

        match self.judgment:
            case Judgment.PERFECT:
                LifeManager.life += (
                    current_note.archetype_life.perfect_increment + current_note.entity_life.perfect_increment
                )
            case Judgment.GREAT:
                LifeManager.life += (
                    current_note.archetype_life.great_increment + current_note.entity_life.great_increment
                )
            case Judgment.GOOD:
                LifeManager.life += current_note.archetype_life.good_increment + current_note.entity_life.good_increment
            case Judgment.MISS:
                LifeManager.life += current_note.archetype_life.miss_increment + current_note.entity_life.miss_increment
        LifeManager.life = clamp(LifeManager.life, 0, LifeManager.max_life)


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
