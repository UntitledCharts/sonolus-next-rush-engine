from __future__ import annotations

from sonolus.script.archetype import (
    EntityRef,
    StandardImport,
    WatchArchetype,
    callback,
    entity_data,
    entity_memory,
    imported,
    shared_memory,
)
from sonolus.script.globals import level_memory
from sonolus.script.interval import clamp
from sonolus.script.runtime import add_life_scheduled, is_replay, is_skip, time
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
from sekai.lib.options import Options
from sekai.lib.skin import ActiveSkin, SkillEffects
from sekai.lib.streams import Streams
from sekai.watch import custom_elements, initialization


class Skill(WatchArchetype):
    beat: StandardImport.BEAT
    effect: SkillEffects = imported(name="effect", default=SkillEffects.SCORE)
    level: int = imported(name="level", default=1)
    start_time: float = entity_data()
    current_life: float = entity_data()
    name = archetype_names.SKILL
    z: float = entity_memory()
    z2: float = entity_memory()
    count: int = shared_memory()
    next_ref: EntityRef[Skill] = entity_data()

    @callback(order=-2)
    def preprocess(self):
        self.start_time = beat_to_time(self.beat)
        if Options.hide_ui != 3 and Options.skill_effect and ActiveSkin.skill_bar_score.is_available:
            Effects.skill.schedule(self.start_time)
        if self.effect == SkillEffects.HEAL:
            add_life_scheduled(250, self.start_time)

    def initialize(self):
        self.z = initialization.LayerCache.skill_bar
        self.z2 = initialization.LayerCache.skill_etc

    def spawn_time(self):
        return self.start_time

    def despawn_time(self):
        if self.next_ref.index > 0:
            return self.next_ref.get().calc_time
        else:
            return 1e8

    def update_parallel(self):
        if time() < self.start_time + 3:
            draw_skill_bar(self.z, self.z2, time() - self.start_time, self.count, self.effect, self.level)
        if time() < self.start_time + 6 and self.effect == SkillEffects.JUDGMENT:
            draw_judgment_effect(time() - self.start_time)

    def update_sequential(self):
        if not is_replay():
            custom_elements.LifeManager.life = self.current_life

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


class FeverChance(WatchArchetype):
    beat: StandardImport.BEAT
    force: bool = imported(name="force")
    start_time: float = entity_memory()
    checker: int = entity_memory()
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

    def spawn_time(self):
        return self.start_time

    def despawn_time(self):
        return Fever.fever_start_time + 1

    def update_parallel(self):
        if not is_replay() and not Options.forced_fever_chance and not self.force:
            return
        if is_skip():
            self.checker = 0
            if time() <= self.start_time:
                self.percentage = 0
        if self.checker >= 2:
            return
        if time() >= Fever.fever_start_time:
            spawn_fever_start_particle(self.percentage)
            self.checker = 2
            return
        if time() >= Fever.fever_chance_time and not self.checker:
            spawn_fever_chance_particle()
            self.checker = 1
        self.percentage = (
            clamp(
                Fever.fever_chance_current_combo / self.counter,
                0,
                0.9 if not Fever.fever_chance_cant_super_fever or self.percentage >= 0.9 else 0.89,
            )
            if not is_replay()
            else Streams.fever_chance_counter[self.index][time()]
        )
        if Options.fever_effect == 0:
            draw_fever_side_cover(self.z, time() - self.start_time)
        draw_fever_side_bar(self.z2, time() - self.start_time)
        draw_fever_gauge(self.z3, self.percentage)

    @callback(order=3)
    def update_sequential(self):
        if self.checker:
            return
        self.counter = Fever.fever_last_count - Fever.fever_first_count

    def terminate(self):
        self.percentage = 0
        self.checker = 0


class FeverStart(WatchArchetype):
    beat: StandardImport.BEAT
    start_time: float = entity_memory()
    name = archetype_names.FEVER_START

    @callback(order=-2)
    def preprocess(self):
        self.start_time = beat_to_time(self.beat)
        Fever.fever_start_time = (
            min(self.start_time, Fever.fever_start_time) if Fever.fever_start_time != 0 else self.start_time
        )

    def spawn_time(self):
        return 1e8

    def despawn_time(self):
        return 1e8


EVENT_ARCHETYPES = (Skill, FeverChance, FeverStart)
