from __future__ import annotations

from enum import IntEnum

from sonolus.script.array import Dim
from sonolus.script.containers import ArrayMap, VarArray
from sonolus.script.globals import level_memory
from sonolus.script.particle import Particle, ParticleHandle
from sonolus.script.quad import Quad
from sonolus.script.record import Record
from sonolus.script.runtime import time

CHUNK_COUNT = 6.0

PARTICLE_ID_STRIDE = 8192.0
SLOT_OFFSET = 512.0

PURGE_BATCH = 64


class ParticleManageKind(IntEnum):
    LANE = 0
    REST = 1
    MULTI = 2


class ParticleEntry(Record):
    particle: ParticleHandle
    chunk_id: float
    particle_id: float
    end_time: float


@level_memory
class ParticleHandler:
    entries: ArrayMap[float, ParticleEntry, Dim[512]]
    chunk_ids: ArrayMap[float, float, Dim[256]]
    serial: float


def clear_particles():
    for entry in ParticleHandler.entries.values():
        entry.particle.destroy()
    ParticleHandler.entries.clear()
    ParticleHandler.chunk_ids.clear()


def begin_particle_chunk(particle: Particle) -> float:
    particle_id = particle.id
    prev = ParticleHandler.chunk_ids[particle_id] if particle_id in ParticleHandler.chunk_ids else -1.0  # noqa: SIM401
    chunk = (prev + 1) % CHUNK_COUNT
    ParticleHandler.chunk_ids[particle_id] = chunk
    batched = True
    while batched:
        batch = +VarArray[float, PURGE_BATCH]
        for key, entry in ParticleHandler.entries.items():
            if entry.end_time <= time() or (entry.particle_id == particle_id and entry.chunk_id == chunk):
                entry.particle.destroy()
                batch.append(key)
                if batch.is_full():
                    break
        for key in batch:
            del ParticleHandler.entries[key]
        batched = batch.is_full()
    return chunk


def emit_particle(
    particle: Particle,
    layout: Quad,
    duration: float,
    manage_kind: ParticleManageKind,
    slot: float,
    chunk: float,
    managed: bool,
):
    if not managed:
        particle.spawn(layout, duration=duration)
        return
    particle_id = particle.id
    if manage_kind == ParticleManageKind.LANE:
        key = particle_id * PARTICLE_ID_STRIDE + (slot * 2 + SLOT_OFFSET)
        if key in ParticleHandler.entries:
            ParticleHandler.entries[key].particle.destroy()
        elif ParticleHandler.entries.is_full():
            particle.spawn(layout, duration=duration)
            return
    else:
        if ParticleHandler.entries.is_full():
            particle.spawn(layout, duration=duration)
            return
        ParticleHandler.serial += 1
        key = -ParticleHandler.serial
    handle = particle.spawn(layout, duration=duration)
    ParticleHandler.entries[key] = ParticleEntry(
        particle=handle,
        chunk_id=chunk,
        particle_id=particle_id,
        end_time=time() + duration,
    )
