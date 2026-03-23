from __future__ import annotations

from sonolus.script.archetype import (
    EntityRef,
    PlayArchetype,
    StandardImport,
    callback,
    entity_data,
    entity_memory,
    imported,
    shared_memory,
)
from sonolus.script.globals import level_memory
from sonolus.script.interval import clamp
from sonolus.script.runtime import add_life_scheduled, is_multiplayer, offset_adjusted_time, time
from sonolus.script.timing import beat_to_time

from sekai.lib import archetype_names
from sekai.lib.effect import Effects
from sekai.lib.events import (
    draw_fever_gauge,
    draw_fever_side_bar,
    draw_fever_side_cover,
    draw_judgment_effect,
    draw_skill_bar,
    spawn_fever_chance_particle,
    spawn_fever_start_particle,
)
from sekai.lib.options import Options, SkillMode
from sekai.lib.skin import ActiveSkin
from sekai.lib.streams import Streams
from sekai.play import custom_elements, initialization


@level_memory
class SkillActive:
    judgment: bool


class Skill(PlayArchetype):
    beat: StandardImport.BEAT
    effect: SkillMode = imported(name="effect", default=SkillMode.LEVEL_DEFAULT)
    level: int = imported(name="level", default=1)
    start_time: float = entity_data()
    count: int = shared_memory()
    next_ref: EntityRef[Skill] = entity_data()
    z: float = entity_memory()
    z2: float = entity_memory()
    check: bool = entity_memory()
    end_time_3: float = entity_memory()
    end_time_6: float = entity_memory()
    name = archetype_names.SKILL

    @callback(order=-2)
    def preprocess(self):
        self.effect = SkillMode.from_options(Options.skill_mode, self.effect)
        self.start_time = beat_to_time(self.beat)
        if Options.hide_ui != 3 and Options.skill_effect and ActiveSkin.skill_bar_score.is_available:
            Effects.skill.schedule(self.start_time)
        if self.effect == SkillMode.HEAL:
            add_life_scheduled(250, self.start_time)

    def initialize(self):
        self.z = initialization.LayerCache.skill_bar
        self.z2 = initialization.LayerCache.skill_etc

    def spawn_order(self):
        return self.start_time

    def should_spawn(self):
        return time() >= self.start_time

    def update_parallel(self):
        current_time = time()
        elapsed = current_time - self.start_time
        if current_time < self.end_time_3:
            draw_skill_bar(self.z, self.z2, elapsed, self.count, self.effect, self.level)
        if (current_time >= self.end_time_3 and self.effect != SkillMode.JUDGMENT) or current_time >= self.end_time_6:
            self.despawn = True
            return
        if self.effect == SkillMode.JUDGMENT:
            draw_judgment_effect(elapsed)

    def update_sequential(self):
        if time() >= self.end_time_6:
            SkillActive.judgment = False
            return
        if not SkillActive.judgment and self.effect == SkillMode.JUDGMENT:
            SkillActive.judgment = True
        if not self.check and custom_elements.LifeManager.life > 0 and self.effect == SkillMode.HEAL:
            custom_elements.LifeManager.life += 250
            custom_elements.LifeManager.life = clamp(
                custom_elements.LifeManager.life, 0, custom_elements.LifeManager.max_life
            )
        self.check = True

    @property
    def calc_time(self) -> float:
        return self.start_time


@level_memory
class Fever:
    fever_chance_time: float
    fever_start_time: float
    fever_chance_current_combo: int
    fever_chance_cant_super_fever: bool
    fever_last_count: int
    fever_first_count: int


class FeverChance(PlayArchetype):
    beat: StandardImport.BEAT
    force: bool = imported(name="force")
    start_time: float = entity_memory()
    checker: bool = entity_memory()
    counter: int = entity_memory()
    percentage: float = entity_memory()
    name = archetype_names.FEVER_CHANCE
    z: float = entity_memory()
    z2: float = entity_memory()
    z3: float = entity_memory()

    @callback(order=-2)
    def preprocess(self):
        self.start_time = beat_to_time(self.beat)
        Fever.fever_chance_time = (
            min(self.start_time, Fever.fever_chance_time) if Fever.fever_chance_time != 0 else self.start_time
        )

    def initialize(self):
        self.z = initialization.LayerCache.fever_chance_cover
        self.z2 = initialization.LayerCache.fever_chance_side
        self.z3 = initialization.LayerCache.fever_chance_gauge

    def spawn_order(self):
        return self.start_time

    def should_spawn(self):
        return time() >= self.start_time

    def update_parallel(self):
        current_time = time()
        elapsed = current_time - self.start_time

        show_ui = is_multiplayer() or Options.forced_fever_chance or self.force

        if current_time >= Fever.fever_start_time:
            if show_ui:
                spawn_fever_start_particle(self.percentage)
            self.despawn = True
            return
        if current_time >= Fever.fever_chance_time and not self.checker:
            if show_ui:
                spawn_fever_chance_particle()
            self.checker = True
        self.percentage = clamp(
            Fever.fever_chance_current_combo / self.counter,
            0,
            0.9 if not Fever.fever_chance_cant_super_fever or self.percentage >= 0.9 else 0.89,
        )

        Streams.fever_chance_counter[self.index][offset_adjusted_time()] = self.percentage

        if show_ui:
            if Options.fever_effect == 0:
                draw_fever_side_cover(self.z, elapsed)
            draw_fever_side_bar(self.z2, elapsed)
            draw_fever_gauge(self.z3, self.percentage)

    @callback(order=3)
    def update_sequential(self):
        if self.checker:
            return
        self.counter = Fever.fever_last_count - Fever.fever_first_count


class FeverStart(PlayArchetype):
    beat: StandardImport.BEAT
    start_time: float = entity_memory()
    name = archetype_names.FEVER_START

    @callback(order=-2)
    def preprocess(self):
        self.start_time = beat_to_time(self.beat)
        Fever.fever_start_time = (
            min(self.start_time, Fever.fever_start_time) if Fever.fever_start_time != 0 else self.start_time
        )

    def spawn_order(self):
        return 1e8

    def should_spawn(self):
        return False


EVENT_ARCHETYPES = (Skill, FeverChance, FeverStart)
