from __future__ import annotations

from sonolus.script.archetype import (
    PlayArchetype,
    entity_memory,
)
from sonolus.script.array import Dim
from sonolus.script.containers import ArrayMap, ArraySet
from sonolus.script.globals import level_memory
from sonolus.script.particle import ParticleHandle
from sonolus.script.record import Record
from sonolus.script.runtime import time

from sekai.lib import archetype_names


class ParticleEntry(Record):
    particle: ParticleHandle
    spawn_time: float


@level_memory
class ParticleHandler:
    critical_flick_lane_effect: ArrayMap[float, ParticleEntry, Dim[32]]


class ParticleManager(PlayArchetype):
    particle: ParticleHandle = entity_memory()
    lane: float = entity_memory()
    spawn_time: float = entity_memory()
    name = archetype_names.PARTICLE_MANAGER

    def update_sequential(self):
        if self.despawn:
            return
        handle_critical_flick_lane_effect(self.particle, self.lane, self.spawn_time)
        self.despawn = True


def handle_critical_flick_lane_effect(particle: ParticleHandle, lane: float, spawn_time: float):
    keys_to_remove = ArraySet[float, Dim[32]].new()
    ttl_limit = time() - 1

    for key, entry in ParticleHandler.critical_flick_lane_effect.items():
        if entry.spawn_time < ttl_limit:
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
