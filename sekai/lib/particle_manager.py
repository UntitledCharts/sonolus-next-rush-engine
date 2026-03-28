from __future__ import annotations

from math import ceil, floor

from sonolus.script.array import Dim
from sonolus.script.containers import ArrayMap
from sonolus.script.globals import level_memory
from sonolus.script.particle import ParticleHandle
from sonolus.script.record import Record
from sonolus.script.runtime import time

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


def _spawn_and_register_particle(
    particles: NoteParticleSet, map_key: float, center: float, size: float, spawn_time: float, chunk_id: float
):
    if map_key in ParticleHandler.critical_flick_lane_effect:
        ParticleHandler.critical_flick_lane_effect[map_key].particle.destroy()

    layout = layout_lane(center, size)
    p = particles.lane.spawn(layout, duration=1 / Options.effect_animation_speed)

    ParticleHandler.critical_flick_lane_effect[map_key] = ParticleEntry(
        particle=p, spawn_time=spawn_time, chunk_id=chunk_id
    )


def handle_critical_flick_lane_effect(
    particles: NoteParticleSet, center_lane: float, size: float, spawn_time: float, force_clear: bool = False
):
    ParticleHandler.current_chunk_id = (ParticleHandler.current_chunk_id + 1) % 6
    chunk_id = ParticleHandler.current_chunk_id

    for key, entry in ParticleHandler.critical_flick_lane_effect.items():
        if force_clear or entry.chunk_id == chunk_id or abs(time() - entry.spawn_time) > 1:
            entry.particle.destroy()
            del ParticleHandler.critical_flick_lane_effect[key]

    min_i = floor(center_lane - size)
    max_i = ceil(center_lane + size) - 1

    if min_i < -127:
        left_max_i = min(-128, max_i)
        merged_center = (min_i + left_max_i + 1) / 2
        merged_size = (left_max_i - min_i + 1) / 2
        _spawn_and_register_particle(particles, -127.0, merged_center, merged_size, spawn_time, chunk_id)

    if max_i > 126:
        right_min_i = max(127, min_i)
        merged_center = (right_min_i + max_i + 1) / 2
        merged_size = (max_i - right_min_i + 1) / 2
        _spawn_and_register_particle(particles, 127.0, merged_center, merged_size, spawn_time, chunk_id)

    start_i = max(-127, min_i)
    end_i = min(126, max_i)

    for i in range(start_i, end_i + 1):
        slot_lane = i + 0.5
        _spawn_and_register_particle(particles, slot_lane, slot_lane, 0.5, spawn_time, chunk_id)
