from __future__ import annotations

from math import ceil, floor

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
    chunk_id: float


@level_memory
class ParticleHandler:
    critical_flick_lane_effect: ArrayMap[float, ParticleEntry, Dim[256]]
    current_chunk_id: float


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

        handle_critical_flick_lane_effect(self.particles, self.lane, self.size, self.target_time)
        self.check = True

    def terminate(self):
        self.check = False


def handle_critical_flick_lane_effect(particles: NoteParticleSet, center_lane: float, size: float, spawn_time: float):
    ParticleHandler.current_chunk_id = (ParticleHandler.current_chunk_id + 1) % 6
    chunk_id = ParticleHandler.current_chunk_id

    keys_to_remove = ArraySet[float, Dim[256]].new()
    diff = abs(time() - spawn_time)

    for key, entry in ParticleHandler.critical_flick_lane_effect.items():
        if diff > 1 or entry.chunk_id == chunk_id or abs(time() - entry.spawn_time) > 1:
            entry.particle.destroy()
            keys_to_remove.add(key)

    for key in keys_to_remove:
        ParticleHandler.critical_flick_lane_effect.__delitem__(key)

    min_i = floor(center_lane - size)
    max_i = ceil(center_lane + size) - 1

    if min_i < -127:
        left_max_i = min(-128, max_i)

        idx = -127.0
        if idx in ParticleHandler.critical_flick_lane_effect:
            ParticleHandler.critical_flick_lane_effect[idx].particle.destroy()

        merged_center = (min_i + left_max_i + 1) / 2
        merged_size = (left_max_i - min_i + 1) / 2

        layout = layout_lane(merged_center, merged_size)
        p = particles.lane.spawn(layout, duration=1 / Options.effect_animation_speed)
        ParticleHandler.critical_flick_lane_effect[idx] = ParticleEntry(
            particle=p, spawn_time=spawn_time, chunk_id=chunk_id
        )

    if max_i > 126:
        right_min_i = max(127, min_i)

        idx = 127.0
        if idx in ParticleHandler.critical_flick_lane_effect:
            ParticleHandler.critical_flick_lane_effect[idx].particle.destroy()

        merged_center = (right_min_i + max_i + 1) / 2
        merged_size = (max_i - right_min_i + 1) / 2

        layout = layout_lane(merged_center, merged_size)
        p = particles.lane.spawn(layout, duration=1 / Options.effect_animation_speed)
        ParticleHandler.critical_flick_lane_effect[idx] = ParticleEntry(
            particle=p, spawn_time=spawn_time, chunk_id=chunk_id
        )

    start_i = max(-127, min_i)
    end_i = min(126, max_i)

    for i in range(start_i, end_i + 1):
        slot_lane = i + 0.5
        if slot_lane in ParticleHandler.critical_flick_lane_effect:
            ParticleHandler.critical_flick_lane_effect[slot_lane].particle.destroy()

        layout = layout_lane(slot_lane, 0.5)
        p = particles.lane.spawn(layout, duration=1 / Options.effect_animation_speed)

        ParticleHandler.critical_flick_lane_effect[slot_lane] = ParticleEntry(
            particle=p, spawn_time=spawn_time, chunk_id=chunk_id
        )
