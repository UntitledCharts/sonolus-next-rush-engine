from __future__ import annotations

from sonolus.script.archetype import WatchArchetype, entity_memory
from sonolus.script.array import Dim
from sonolus.script.containers import ArrayMap, ArraySet
from sonolus.script.globals import level_memory
from sonolus.script.particle import ParticleHandle
from sonolus.script.record import Record
from sonolus.script.runtime import is_skip, time

from sekai.lib import archetype_names
from sekai.lib.layout import layout_lane
from sekai.lib.options import Options
from sekai.lib.particle import NoteParticleSet


class ParticleEntry(Record):
    particle: ParticleHandle
    spawn_time: float


@level_memory
class ParticleHandler:
    critical_flick_lane_effect: ArrayMap[float, ParticleEntry, Dim[32]]


class ParticleManager(WatchArchetype):
    particle: ParticleHandle = entity_memory()
    particles: NoteParticleSet = entity_memory()
    lane: float = entity_memory()
    size: float = entity_memory()
    target_time: float = entity_memory()
    check: bool = entity_memory()
    name = archetype_names.PARTICLE_MANAGER

    def spawn_time(self) -> float:
        return self.target_time

    def despawn_time(self) -> float:
        return self.target_time + 1

    def update_sequential(self):
        if is_skip():
            ParticleHandler.critical_flick_lane_effect.clear()
            self.check = False
            return
        if self.check:
            return
        layout = layout_lane(self.lane, self.size)
        handle_critical_flick_lane_effect(
            self.particles.lane.spawn(layout, duration=1 / Options.effect_animation_speed), self.lane, self.target_time
        )
        self.check = True

    def update_parallel(self):
        if is_skip():
            self.particle.destroy()

    def terminate(self):
        self.check = False


def handle_critical_flick_lane_effect(particle: ParticleHandle, lane: float, spawn_time: float):
    keys_to_remove = ArraySet[float, Dim[32]].new()
    diff = abs(time() - spawn_time)

    for key, entry in ParticleHandler.critical_flick_lane_effect.items():
        if diff > 1:
            entry.particle.destroy()
            keys_to_remove.add(key)

    for key in keys_to_remove:
        ParticleHandler.critical_flick_lane_effect.__delitem__(key)

    if ParticleHandler.critical_flick_lane_effect.__len__() >= 6:
        oldest_key = -999
        oldest_time = 1e8

        for key, entry in ParticleHandler.critical_flick_lane_effect.items():
            if entry.spawn_time < oldest_time:
                oldest_time = entry.spawn_time
                oldest_key = key

        if oldest_key != -999:
            entry_to_remove = ParticleHandler.critical_flick_lane_effect.pop(oldest_key)
            if entry_to_remove:
                entry_to_remove.particle.destroy()

    if lane in ParticleHandler.critical_flick_lane_effect:
        ParticleHandler.critical_flick_lane_effect[lane].particle.destroy()

    new_entry = ParticleEntry(particle=particle, spawn_time=spawn_time)
    ParticleHandler.critical_flick_lane_effect[lane] = new_entry
