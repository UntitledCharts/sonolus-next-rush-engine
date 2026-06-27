from __future__ import annotations

from enum import IntEnum
from math import floor

from sonolus.script.array import Dim
from sonolus.script.containers import VarArray
from sonolus.script.globals import level_memory
from sonolus.script.particle import Particle, ParticleHandle
from sonolus.script.quad import Quad
from sonolus.script.record import Record

from sekai.lib.particle import EMPTY_PARTICLE

PARTICLE_ID_STRIDE = 8192.0
SLOT_OFFSET = 512.0

CHUNK_COUNT = 6.0


class ParticleManageKind(IntEnum):
    LANE = 0
    REST = 1
    MULTI = 2


class ParticleEntry(Record):
    key: float
    particle: ParticleHandle
    particle_id: float
    chunk_key: float
    chunk_serial: float


@level_memory
class ParticleHandler:
    entries: VarArray[ParticleEntry, Dim[256]]
    chunk_serial: float
    entry_serial: float


def _find_entry_index(key: float) -> int:
    for i in range(len(ParticleHandler.entries)):
        if ParticleHandler.entries[i].key == key:
            return i
    return -1


def _swap_remove_entry(index: int):
    last = len(ParticleHandler.entries) - 1
    if index != last:
        ParticleHandler.entries[index] = ParticleHandler.entries[last]
    ParticleHandler.entries.pop()


def clear_particles():
    for entry in ParticleHandler.entries:
        entry.particle.destroy()
    ParticleHandler.entries.clear()
    ParticleHandler.chunk_serial = 0
    ParticleHandler.entry_serial = 0


def purge_particle_chunk(chunk_key: float):
    i = len(ParticleHandler.entries) - 1
    while i >= 0:
        entry = ParticleHandler.entries[i]
        if entry.chunk_key == chunk_key:
            entry.particle.destroy()
            _swap_remove_entry(i)
        i -= 1


def particle_group_slot(group_id: float) -> float:
    return group_id - floor(group_id / CHUNK_COUNT) * CHUNK_COUNT


def particle_slot_key(particle_id: float, slot: float) -> float:
    return particle_id * PARTICLE_ID_STRIDE + slot


def begin_particle_chunk(particle: Particle, group_id: float, manage_kind: ParticleManageKind) -> float:
    if particle == EMPTY_PARTICLE:
        return 0.0
    particle_id = particle.id
    slot = particle_group_slot(group_id)
    chunk_key = particle_id * CHUNK_COUNT + slot
    if manage_kind != ParticleManageKind.REST:
        purge_particle_chunk(chunk_key)
    ParticleHandler.chunk_serial += 1
    return chunk_key


def evict_oldest_particle_entry(particle_id: float):
    oldest_index = -1
    oldest_chunk_serial = ParticleHandler.chunk_serial + 1
    for i in range(len(ParticleHandler.entries)):
        entry = ParticleHandler.entries[i]
        if entry.particle_id != particle_id:
            continue
        if entry.chunk_serial < oldest_chunk_serial:
            oldest_chunk_serial = entry.chunk_serial
            oldest_index = i
    if oldest_index < 0:
        return
    ParticleHandler.entries[oldest_index].particle.destroy()
    _swap_remove_entry(oldest_index)


def emit_particle(
    particle: Particle,
    layout: Quad,
    duration: float,
    manage_kind: ParticleManageKind,
    slot: float,
    chunk_key: float,
    managed: bool,
):
    if particle == EMPTY_PARTICLE:
        return
    if not managed:
        particle.spawn(layout, duration=duration)
        return
    particle_id = particle.id

    if manage_kind == ParticleManageKind.REST:
        slot = chunk_key - particle_id * CHUNK_COUNT
        key = particle_slot_key(particle_id, slot)
    elif manage_kind == ParticleManageKind.LANE:
        key = particle_id * PARTICLE_ID_STRIDE + (slot * 2 + SLOT_OFFSET)
    else:
        ParticleHandler.entry_serial += 1
        key = -ParticleHandler.entry_serial

    index = -1 if manage_kind == ParticleManageKind.MULTI else _find_entry_index(key)
    if index >= 0:
        ParticleHandler.entries[index].particle.destroy()
    elif manage_kind != ParticleManageKind.REST and ParticleHandler.entries.is_full():
        evict_oldest_particle_entry(particle_id)

    handle = particle.spawn(layout, duration=duration)
    new_entry = ParticleEntry(
        key=key,
        particle=handle,
        particle_id=particle_id,
        chunk_key=chunk_key,
        chunk_serial=ParticleHandler.chunk_serial,
    )
    if index >= 0:
        ParticleHandler.entries[index] = new_entry
    else:
        ParticleHandler.entries.append(new_entry)
