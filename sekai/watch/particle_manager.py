from __future__ import annotations

from sonolus.script.archetype import WatchArchetype, entity_memory
from sonolus.script.particle import ParticleHandle
from sonolus.script.record import Record
from sonolus.script.runtime import is_skip, time

from sekai.lib import archetype_names
from sekai.lib.particle import NoteParticleSet
from sekai.lib.particle_manager import ParticleHandler, handle_critical_flick_lane_effect


class ParticleEntry(Record):
    particle: ParticleHandle
    spawn_time: float
    chunk_id: float


class ParticleManager(WatchArchetype):
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

        is_time_skipped = abs(time() - self.target_time) > 1
        handle_critical_flick_lane_effect(
            self.particles, self.lane, self.size, self.target_time, force_clear=is_time_skipped
        )
        self.check = True

    def terminate(self):
        self.check = False
