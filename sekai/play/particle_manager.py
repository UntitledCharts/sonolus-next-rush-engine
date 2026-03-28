from __future__ import annotations

from sonolus.script.archetype import (
    PlayArchetype,
    entity_memory,
)
from sonolus.script.particle import ParticleHandle
from sonolus.script.record import Record

from sekai.lib import archetype_names
from sekai.lib.particle import NoteParticleSet
from sekai.lib.particle_manager import handle_critical_flick_lane_effect


class ParticleEntry(Record):
    particle: ParticleHandle
    spawn_time: float
    chunk_id: float


class ParticleManager(PlayArchetype):
    particles: NoteParticleSet = entity_memory()
    lane: float = entity_memory()
    size: float = entity_memory()
    spawn_time: float = entity_memory()
    name = archetype_names.PARTICLE_MANAGER

    def update_sequential(self):
        if self.despawn:
            return
        handle_critical_flick_lane_effect(self.particles, self.lane, self.size, self.spawn_time)
        self.despawn = True
