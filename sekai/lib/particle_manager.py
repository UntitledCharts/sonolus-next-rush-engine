from __future__ import annotations

from enum import IntEnum

from sonolus.script.array import Dim
from sonolus.script.containers import ArrayMap, VarArray
from sonolus.script.globals import level_memory
from sonolus.script.particle import Particle, ParticleHandle
from sonolus.script.quad import Quad
from sonolus.script.record import Record

PARTICLE_ID_STRIDE = 8192.0
SLOT_OFFSET = 512.0

PURGE_BATCH = 64


class ParticleManageKind(IntEnum):
    LANE = 0
    REST = 1
    MULTI = 2


class ParticleEntry(Record):
    particle: ParticleHandle
    particle_id: float
    chunk_key: float
    chunk_serial: float


@level_memory
class ParticleHandler:
    entries: ArrayMap[float, ParticleEntry, Dim[8192]]
    chunk_serial: float
    entry_serial: float


def clear_particles():
    for entry in ParticleHandler.entries.values():
        entry.particle.destroy()
    ParticleHandler.entries.clear()
    ParticleHandler.chunk_serial = 0
    ParticleHandler.entry_serial = 0


def purge_particle_chunk(chunk_key: float):
    batched = True
    while batched:
        batch = +VarArray[float, PURGE_BATCH]
        for key, entry in ParticleHandler.entries.items():
            if entry.chunk_key == chunk_key:
                entry.particle.destroy()
                batch.append(key)
                if batch.is_full():
                    break
        for key in batch:
            del ParticleHandler.entries[key]
        batched = batch.is_full()


def begin_particle_chunk(particle: Particle) -> float:
    particle_id = particle.id
    active_chunks = +VarArray[float, Dim[6]]
    oldest_chunk_key = 0.0
    oldest_chunk_serial = ParticleHandler.chunk_serial + 1
    for entry in ParticleHandler.entries.values():
        if entry.particle_id != particle_id:
            continue
        if entry.chunk_serial < oldest_chunk_serial:
            oldest_chunk_key = entry.chunk_key
            oldest_chunk_serial = entry.chunk_serial
        seen = False
        for chunk_key in active_chunks:
            if chunk_key == entry.chunk_key:
                seen = True
                break
        if not seen and not active_chunks.is_full():
            active_chunks.append(entry.chunk_key)
    if active_chunks.is_full():
        purge_particle_chunk(oldest_chunk_key)
    ParticleHandler.chunk_serial += 1
    return ParticleHandler.chunk_serial


def evict_oldest_particle_chunk(particle_id: float):
    oldest_chunk_key = 0.0
    oldest_chunk_serial = ParticleHandler.chunk_serial + 1
    for entry in ParticleHandler.entries.values():
        if entry.particle_id != particle_id:
            continue
        if entry.chunk_serial < oldest_chunk_serial:
            oldest_chunk_key = entry.chunk_key
            oldest_chunk_serial = entry.chunk_serial
    if oldest_chunk_serial > ParticleHandler.chunk_serial:
        return
    purge_particle_chunk(oldest_chunk_key)


def emit_particle(
    particle: Particle,
    layout: Quad,
    duration: float,
    manage_kind: ParticleManageKind,
    slot: float,
    chunk_key: float,
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
    else:
        ParticleHandler.entry_serial += 1
        key = -ParticleHandler.entry_serial
    if ParticleHandler.entries.is_full():
        evict_oldest_particle_chunk(particle_id)
    handle = particle.spawn(layout, duration=duration)
    ParticleHandler.entries[key] = ParticleEntry(
        particle=handle,
        particle_id=particle_id,
        chunk_key=chunk_key,
        chunk_serial=ParticleHandler.chunk_serial,
    )
