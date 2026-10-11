from __future__ import annotations

from enum import IntEnum

from sonolus.script.array import Array, Dim
from sonolus.script.containers import VarArray
from sonolus.script.globals import level_memory
from sonolus.script.particle import Particle, ParticleHandle
from sonolus.script.quad import Quad
from sonolus.script.record import Record

from sekai.lib.particle import EMPTY_PARTICLE

PARTICLE_ID_STRIDE = 8192.0
SLOT_OFFSET = 512.0
PARTICLE_INDEX_BUCKETS = 31
PARTICLE_LINK_STRIDE = 512


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
    # Two references fit exactly in one f32 slot (each is at most 256).
    key_chunk_links: int
    particle_links: int

    @property
    def key_next(self) -> int:
        return self.key_chunk_links % PARTICLE_LINK_STRIDE

    @key_next.setter
    def key_next(self, value: int):
        self.key_chunk_links += value - self.key_next

    @property
    def chunk_next(self) -> int:
        return self.key_chunk_links // PARTICLE_LINK_STRIDE

    @chunk_next.setter
    def chunk_next(self, value: int):
        self.key_chunk_links += (value - self.chunk_next) * PARTICLE_LINK_STRIDE

    @property
    def older(self) -> int:
        return self.particle_links % PARTICLE_LINK_STRIDE

    @older.setter
    def older(self, value: int):
        self.particle_links += value - self.older

    @property
    def newer(self) -> int:
        return self.particle_links // PARTICLE_LINK_STRIDE

    @newer.setter
    def newer(self, value: int):
        self.particle_links += (value - self.newer) * PARTICLE_LINK_STRIDE


@level_memory
class ParticleHandler:
    entries: VarArray[ParticleEntry, Dim[256]]
    chunk_serial: float
    entry_serial: float
    # References are entry indices plus one; zero is an empty bucket/list.
    key_heads: Array[int, Dim[31]]
    chunk_heads: Array[int, Dim[31]]
    particle_heads: Array[int, Dim[31]]
    particle_tails: Array[int, Dim[31]]


def _bucket(key: float) -> int:
    return int(abs(key) % PARTICLE_INDEX_BUCKETS)


def _find_entry_index(key: float) -> int:
    ref = ParticleHandler.key_heads[_bucket(key)]
    while ref > 0:
        entry = ParticleHandler.entries[ref - 1]
        if entry.key == key:
            return ref - 1
        ref = entry.key_next
    return -1


def _unindex_bucket(index: int, heads: Array[int, Dim[31]], chunk: bool):
    entry = ParticleHandler.entries[index]
    bucket = _bucket(entry.chunk_key if chunk else entry.key)
    ref = heads[bucket]
    previous = 0
    while ref > 0:
        current = ParticleHandler.entries[ref - 1]
        following = current.chunk_next if chunk else current.key_next
        if ref == index + 1:
            if previous == 0:
                heads[bucket] = following
            elif chunk:
                ParticleHandler.entries[previous - 1].chunk_next = following
            else:
                ParticleHandler.entries[previous - 1].key_next = following
            return
        previous = ref
        ref = following


def _index_buckets(index: int):
    entry = ParticleHandler.entries[index]
    key_bucket = _bucket(entry.key)
    chunk_bucket = _bucket(entry.chunk_key)
    entry.key_next = ParticleHandler.key_heads[key_bucket]
    entry.chunk_next = ParticleHandler.chunk_heads[chunk_bucket]
    ParticleHandler.key_heads[key_bucket] = index + 1
    ParticleHandler.chunk_heads[chunk_bucket] = index + 1


def _index_entry(index: int):
    _index_buckets(index)
    entry = ParticleHandler.entries[index]
    bucket = _bucket(entry.particle_id)
    entry.older = ParticleHandler.particle_tails[bucket]
    entry.newer = 0
    if entry.older > 0:
        ParticleHandler.entries[entry.older - 1].newer = index + 1
    else:
        ParticleHandler.particle_heads[bucket] = index + 1
    ParticleHandler.particle_tails[bucket] = index + 1


def _unindex_entry(index: int):
    _unindex_bucket(index, ParticleHandler.key_heads, False)
    _unindex_bucket(index, ParticleHandler.chunk_heads, True)
    entry = ParticleHandler.entries[index]
    bucket = _bucket(entry.particle_id)
    if entry.older > 0:
        ParticleHandler.entries[entry.older - 1].newer = entry.newer
    else:
        ParticleHandler.particle_heads[bucket] = entry.newer
    if entry.newer > 0:
        ParticleHandler.entries[entry.newer - 1].older = entry.older
    else:
        ParticleHandler.particle_tails[bucket] = entry.older


def _swap_remove_entry(index: int):
    _unindex_entry(index)
    last = len(ParticleHandler.entries) - 1
    if index != last:
        _unindex_bucket(last, ParticleHandler.key_heads, False)
        _unindex_bucket(last, ParticleHandler.chunk_heads, True)
        moved = +ParticleHandler.entries[last]
        bucket = _bucket(moved.particle_id)
        if moved.older > 0:
            ParticleHandler.entries[moved.older - 1].newer = index + 1
        else:
            ParticleHandler.particle_heads[bucket] = index + 1
        if moved.newer > 0:
            ParticleHandler.entries[moved.newer - 1].older = index + 1
        else:
            ParticleHandler.particle_tails[bucket] = index + 1
        ParticleHandler.entries[index] = moved
        _index_buckets(index)
    ParticleHandler.entries.pop()


def clear_particles():
    for entry in ParticleHandler.entries:
        entry.particle.destroy()
    ParticleHandler.entries.clear()
    ParticleHandler.chunk_serial = 0
    ParticleHandler.entry_serial = 0
    for i in range(PARTICLE_INDEX_BUCKETS):
        ParticleHandler.key_heads[i] = 0
        ParticleHandler.chunk_heads[i] = 0
        ParticleHandler.particle_heads[i] = 0
        ParticleHandler.particle_tails[i] = 0


def purge_particle_chunk(chunk_key: float):
    bucket = _bucket(chunk_key)
    matches = +VarArray[int, Dim[256]]
    ref = ParticleHandler.chunk_heads[bucket]
    while ref > 0:
        entry = ParticleHandler.entries[ref - 1]
        if entry.chunk_key == chunk_key:
            matches.append(ref - 1)
        ref = entry.chunk_next
    # Descending removals retain the previous swap-removal order and eviction ties.
    matches.sort()
    for i in range(len(matches) - 1, -1, -1):
        index = matches[i]
        ParticleHandler.entries[index].particle.destroy()
        _swap_remove_entry(index)


def particle_slot_key(particle_id: float, slot: float) -> float:
    return particle_id * PARTICLE_ID_STRIDE + slot


def begin_particle_chunk(particle: Particle, group_id: float, manage_kind: ParticleManageKind) -> float:
    if particle == EMPTY_PARTICLE:
        return 0.0
    particle_id = particle.id
    # Preserve the complete entity group ID. Folding IDs into six slots made unrelated
    # simultaneous notes (for example groups 1 and 7) destroy each other's particles.
    chunk_key = particle_slot_key(particle_id, group_id)
    if manage_kind != ParticleManageKind.REST:
        purge_particle_chunk(chunk_key)
    ParticleHandler.chunk_serial += 1
    return chunk_key


def evict_oldest_particle_entry(particle_id: float):
    ref = ParticleHandler.particle_heads[_bucket(particle_id)]
    while ref > 0 and ParticleHandler.entries[ref - 1].particle_id != particle_id:
        ref = ParticleHandler.entries[ref - 1].newer
    oldest_index = ref - 1
    oldest_serial = ParticleHandler.chunk_serial + 1
    if ref > 0:
        oldest_serial = ParticleHandler.entries[oldest_index].chunk_serial
        # Preserve the previous array-index tie break within the oldest chunk.
        while ref > 0 and ParticleHandler.entries[ref - 1].chunk_serial == oldest_serial:
            if ParticleHandler.entries[ref - 1].particle_id == particle_id:
                oldest_index = min(oldest_index, ref - 1)
            ref = ParticleHandler.entries[ref - 1].newer
    if oldest_serial >= ParticleHandler.chunk_serial:
        # Do not evict the batch currently being emitted just because this kind
        # has no older entries. Reclaim older effects of other kinds instead.
        oldest_serial = ParticleHandler.chunk_serial + 1
        for i in range(len(ParticleHandler.entries)):
            if ParticleHandler.entries[i].chunk_serial < oldest_serial:
                oldest_serial = ParticleHandler.entries[i].chunk_serial
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
        slot = chunk_key - particle_id * PARTICLE_ID_STRIDE
        key = particle_slot_key(particle_id, slot)
    elif manage_kind == ParticleManageKind.LANE:
        key = particle_id * PARTICLE_ID_STRIDE + (slot * 2 + SLOT_OFFSET)
    else:
        ParticleHandler.entry_serial += 1
        key = -ParticleHandler.entry_serial

    index = -1 if manage_kind == ParticleManageKind.MULTI else _find_entry_index(key)
    if index >= 0:
        ParticleHandler.entries[index].particle.destroy()
        _unindex_entry(index)
    elif ParticleHandler.entries.is_full():
        evict_oldest_particle_entry(particle_id)

    handle = particle.spawn(layout, duration=duration)
    new_entry = ParticleEntry(
        key=key,
        particle=handle,
        particle_id=particle_id,
        chunk_key=chunk_key,
        chunk_serial=ParticleHandler.chunk_serial,
        key_chunk_links=0,
        particle_links=0,
    )
    if index >= 0:
        ParticleHandler.entries[index] = new_entry
        _index_entry(index)
    else:
        ParticleHandler.entries.append(new_entry)
        _index_entry(len(ParticleHandler.entries) - 1)
