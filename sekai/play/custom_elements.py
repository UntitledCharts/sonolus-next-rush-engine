from sonolus.script.archetype import PlayArchetype, callback, entity_memory
from sonolus.script.bucket import Judgment, JudgmentWindow
from sonolus.script.globals import level_memory
from sonolus.script.interval import Interval, clamp
from sonolus.script.runtime import level_score, time

from sekai.lib import archetype_names
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
    windows: JudgmentWindow,
    windows_bad: Interval,
    wrong_way: bool,
    check_pass: bool,
    target_time: float,
    index: int,
):
    ComboJudge.spawn(
        index=index,
        target_time=target_time,
        spawn_time=time(),
        judgment=judgment,
        windows_bad=windows_bad,
        accuracy=accuracy,
        check_pass=check_pass,
    )
    if judgment != Judgment.PERFECT and check_pass:
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
    scale_factor: float
    max_score: int
    current_raw_score: float
    count: int


@level_memory
class LifeManager:
    life: int


class ComboJudge(PlayArchetype):
    target_time: float = entity_memory()
    spawn_time: float = entity_memory()
    judgment: Judgment = entity_memory()
    accuracy: Judgment = entity_memory()
    windows: JudgmentWindow = entity_memory()
    windows_bad: Interval = entity_memory()
    wrong_way: bool = entity_memory()
    check_pass: bool = entity_memory()
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
            windows_bad=self.windows_bad,
            accuracy=self.accuracy,
            check_pass=self.check_pass,
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
        # score = judgmentMultiplier * (consecutiveJudgmentMultiplier(is not support in sekai rush custom elements) + archetypeMultiplier + entityMultiplier)
        judgment_multiplier = 0
        match self.judgment:
            case Judgment.PERFECT:
                judgment_multiplier = level_score().perfect_multiplier
            case Judgment.GREAT:
                judgment_multiplier = level_score().great_multiplier
            case Judgment.GOOD:
                judgment_multiplier = level_score().good_multiplier
            case Judgment.MISS:
                judgment_multiplier = 0

        note_raw_score = judgment_multiplier * (
            note.BaseNote.at(self.index).archetype_score_multiplier
            + note.BaseNote.at(self.index).entity_score_multiplier
        )
        note_score = round(note_raw_score * ScoreIndicator.scale_factor)
        ScoreIndicator.note_score = note_score if note_score > 0 else ScoreIndicator.note_score
        ScoreIndicator.note_time = self.spawn_time if note_score > 0 else ScoreIndicator.note_time
        ScoreIndicator.current_raw_score += note_raw_score
        ScoreIndicator.score = clamp(
            round(ScoreIndicator.current_raw_score * ScoreIndicator.scale_factor),
            0,
            ScoreIndicator.max_score,
        )
        match Options.custom_score:
            case 1:
                ScoreIndicator.percentage = ScoreIndicator.score / ScoreIndicator.max_score * 100
            case 2:
                ScoreIndicator.percentage = clamp(
                    ScoreIndicator.percentage
                    - (
                        (
                            (level_score().perfect_multiplier - judgment_multiplier)
                            * (
                                note.BaseNote.at(self.index).archetype_score_multiplier
                                + note.BaseNote.at(self.index).entity_score_multiplier
                            )
                            * ScoreIndicator.scale_factor
                        )
                        / ScoreIndicator.max_score
                        * 100
                    ),
                    0,
                    100,
                )
            case 3:
                ScoreIndicator.count += 1
                ScoreIndicator.percentage += (
                    ((1 - abs(self.accuracy)) * 100) - ScoreIndicator.percentage
                ) / ScoreIndicator.count

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
    windows: JudgmentWindow = entity_memory()
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
