from __future__ import annotations

from enum import IntEnum
from math import floor

from sonolus.script.archetype import get_archetype_by_name
from sonolus.script.array import Array, Dim
from sonolus.script.containers import VarArray
from sonolus.script.globals import level_memory
from sonolus.script.particle import Particle, ParticleHandle
from sonolus.script.quad import Quad
from sonolus.script.record import Record
from sonolus.script.runtime import time

from sekai.lib import archetype_names
from sekai.lib.particle import EMPTY_PARTICLE, BaseParticles

PARTICLE_KIND_COUNT = len(BaseParticles._particles_)
PARTICLE_CHUNKS_PER_KIND = 6
PARTICLE_PAGE_SIZE = 8
PARTICLE_ARROW_CACHE_SIZE = 4
PARTICLE_CHUNKS_PER_NOTE = 4  # Only linear/circular bundles, slot, and lane need a shared ticket.
PARTICLE_LANE_WORD_BITS = 24
PARTICLE_LANE_WORDS = 11
CRITICAL_LANE_IDS = (
    BaseParticles.lane.id,
    BaseParticles.critical_flick_note_lane_linear.id,
    BaseParticles.critical_down_flick_note_lane_linear.id,
    *range(
        BaseParticles.colored_critical_flick_note_lane_linear.start_id,
        BaseParticles.colored_critical_flick_note_lane_linear.start_id + 8,
    ),
    *range(
        BaseParticles.colored_critical_down_flick_note_lane_linear.start_id,
        BaseParticles.colored_critical_down_flick_note_lane_linear.start_id + 8,
    ),
)
CRITICAL_LANE_SLOTS = len(CRITICAL_LANE_IDS) * PARTICLE_CHUNKS_PER_KIND


class ParticleManageKind(IntEnum):
    LANE = 0
    REST = 1
    MULTI = 2


class ParticleStorage(Record):
    # Four tickets fit in the existing shared-memory padding (Watch: 40 + 4).
    tickets: Array[int, Dim[4]]


class CriticalLaneChunk(Record):
    # All 24 bits are exactly representable in f32, including 2**24 - 1.
    lanes: Array[int, Dim[11]]
    serial: int

    @property
    def remaining(self) -> int:
        # Lanes use bits 0..253. The last word has ten spare bits; eight hold
        # the remaining count, without adding a slot or losing f32 precision.
        return self.lanes[10] // 16384 % 256

    @remaining.setter
    def remaining(self, value: int):
        self.lanes[10] += (value - self.remaining) * 16384

    @property
    def overlaps(self) -> bool:
        return self.lanes[10] // 4194304 % 2 == 1

    @overlaps.setter
    def overlaps(self, value: bool):
        self.lanes[10] += (int(value) - int(self.overlaps)) * 4194304


class ParticlePageEntry(Record):
    handle: ParticleHandle
    lane: float


class ParticlePage(Record):
    particle_id: int
    lane_slot: int  # Slot index + one; zero for counter-managed effects.
    serial: int
    version: int
    end_time: float
    entries: VarArray[ParticlePageEntry, Dim[8]]


class CachedArrows(Record):
    particle_id: int  # ID + one; zero means unused.
    handles: Array[int, Dim[6]]  # Native ID + one; zero is an empty slot.
    deadlines: Array[float, Dim[6]]


@level_memory
class ParticleHandler:
    serials: Array[int, Dim[PARTICLE_KIND_COUNT]]
    critical_lanes: Array[CriticalLaneChunk, Dim[CRITICAL_LANE_SLOTS]]
    arrows: Array[CachedArrows, Dim[PARTICLE_ARROW_CACHE_SIZE]]


def particle_storage(owner: int) -> ParticleStorage:
    return get_archetype_by_name(archetype_names.NORMAL_TAP_NOTE).at(owner, check=False).particle_storage


def _ticket(ref: int) -> int:
    index = ref - 1
    return particle_storage(index // PARTICLE_CHUNKS_PER_NOTE).tickets[index % PARTICLE_CHUNKS_PER_NOTE]


def _set_ticket(ref: int, value: int):
    index = ref - 1
    particle_storage(index // PARTICLE_CHUNKS_PER_NOTE).tickets[index % PARTICLE_CHUNKS_PER_NOTE] = value


def clear_particles():
    # Skip one complete window on a seek. Tickets stay unique across reuse;
    # every old page is invalidated even if new effects spawn in the same frame.
    for particle_id in range(PARTICLE_KIND_COUNT):
        ParticleHandler.serials[particle_id] += PARTICLE_CHUNKS_PER_KIND
    for cache in ParticleHandler.arrows:
        for i in range(PARTICLE_CHUNKS_PER_KIND):
            if cache.handles[i] > 0 and time() < cache.deadlines[i]:
                ParticleHandle(cache.handles[i] - 1).destroy()
            cache.handles[i] = 0
        cache.particle_id = 0
    for chunk in ParticleHandler.critical_lanes:
        chunk.remaining = 0
        chunk.serial = 0


def begin_particle_chunk(
    particle: Particle,
    group_id: float,
    manage_kind: ParticleManageKind,
    component: int = -1,
    page_index: int = 0,
) -> int:
    if particle == EMPTY_PARTICLE or manage_kind == ParticleManageKind.REST:
        return 0
    index = component
    if component < 0:
        index = 0
    elif component >= 4:
        index = component - 2
    # Directional/tick effects are single emissions and never use shared tickets.
    ref = int(group_id) * PARTICLE_CHUNKS_PER_NOTE + index + 1
    if page_index == 0:
        _set_ticket(ref, 0)
    return ref


def _critical_lane_base(particle_id: int) -> int:
    if particle_id == BaseParticles.lane.id:
        return 0
    if particle_id == BaseParticles.critical_flick_note_lane_linear.id:
        return 6
    if particle_id == BaseParticles.critical_down_flick_note_lane_linear.id:
        return 12
    start = BaseParticles.colored_critical_flick_note_lane_linear.start_id
    if start <= particle_id < start + 8:
        return (3 + particle_id - start) * 6
    start = BaseParticles.colored_critical_down_flick_note_lane_linear.start_id
    assert start <= particle_id < start + 8
    return (11 + particle_id - start) * 6


def _critical_slot(particle_id: int, serial: int) -> int:
    base = _critical_lane_base(particle_id)
    for slot in range(base, base + PARTICLE_CHUNKS_PER_KIND):
        chunk = ParticleHandler.critical_lanes[slot]
        if chunk.serial == serial and chunk.remaining > 0:
            return slot
    return -1


def _lane_alive(chunk: CriticalLaneChunk, lane: float) -> bool:
    index = floor(lane) + 127
    bit = 2 ** (index % PARTICLE_LANE_WORD_BITS)
    return chunk.lanes[index // PARTICLE_LANE_WORD_BITS] // bit % 2 == 1


def prepare_particle_lanes(ref: int, particle: Particle, first: float, last: float, overlaps: bool = True):
    if _ticket(ref) != 0:
        return
    particle_id = particle.id
    first_index = floor(first) + 127
    last_index = floor(last) + 127
    base = _critical_lane_base(particle_id)
    free = -1
    oldest = base
    oldest_serial = ParticleHandler.serials[particle_id] + 1
    for slot in range(base, base + PARTICLE_CHUNKS_PER_KIND):
        old = ParticleHandler.critical_lanes[slot]
        if old.remaining > 0:
            removed = 0
            for index in range(first_index, last_index + 1 if overlaps and old.overlaps else first_index):
                bit = 2 ** (index % PARTICLE_LANE_WORD_BITS)
                word = index // PARTICLE_LANE_WORD_BITS
                if old.lanes[word] // bit % 2 == 1:
                    old.lanes[word] -= bit
                    removed += 1
            old.remaining -= removed
            if old.serial < oldest_serial:
                oldest = slot
                oldest_serial = old.serial
        if old.remaining == 0:
            free = slot
    # Fully covered groups are freed before applying the six-group limit.
    slot = free if free >= 0 else oldest
    chunk = ParticleHandler.critical_lanes[slot]
    for word in range(PARTICLE_LANE_WORDS):
        lo = max(first_index, word * PARTICLE_LANE_WORD_BITS)
        hi = min(last_index + 1, (word + 1) * PARTICLE_LANE_WORD_BITS)
        chunk.lanes[word] = (
            2 ** (hi - word * PARTICLE_LANE_WORD_BITS) - 2 ** (lo - word * PARTICLE_LANE_WORD_BITS) if lo < hi else 0
        )
    ParticleHandler.serials[particle_id] += 1
    chunk.serial = ParticleHandler.serials[particle_id]
    chunk.remaining = last_index - first_index + 1 if overlaps else 1
    chunk.overlaps = overlaps
    _set_ticket(ref, chunk.serial)


def _is_arrow(particle_id: int) -> bool:
    return particle_id in (
        BaseParticles.note_directional_red.id,
        BaseParticles.note_directional_yellow.id,
        BaseParticles.flick_note_directional.id,
        BaseParticles.down_flick_note_directional.id,
        BaseParticles.critical_note_directional.id,
        BaseParticles.critical_down_flick_note_directional.id,
    ) or any(
        group.start_id <= particle_id < group.start_id + group.size
        for group in (
            BaseParticles.colored_flick_note_directional,
            BaseParticles.colored_down_flick_note_directional,
            BaseParticles.colored_critical_note_directional,
            BaseParticles.colored_critical_down_flick_note_directional,
        )
    )


def _emit_cached_arrow(particle: Particle, layout: Quad, duration: float, serial: int) -> bool:
    # A collision falls back to a private page. Occupied kinds are never evicted
    # to make cache space; a slot may be reassigned only after all handles expire.
    cache = ParticleHandler.arrows[particle.id % PARTICLE_ARROW_CACHE_SIZE]
    if cache.particle_id != particle.id + 1:
        for i in range(PARTICLE_CHUNKS_PER_KIND):
            if cache.handles[i] > 0 and time() < cache.deadlines[i]:
                return False
        cache.particle_id = particle.id + 1
        for i in range(PARTICLE_CHUNKS_PER_KIND):
            cache.handles[i] = 0
    index = (serial - 1) % PARTICLE_CHUNKS_PER_KIND
    if cache.handles[index] > 0 and time() < cache.deadlines[index]:
        ParticleHandle(cache.handles[index] - 1).destroy()
    cache.handles[index] = particle.spawn(layout, duration=duration).id + 1
    cache.deadlines[index] = time() + duration
    return True


def emit_particle(
    particle: Particle,
    layout: Quad,
    duration: float,
    manage_kind: ParticleManageKind,
    slot: float,
    chunk_key: int,
    managed: bool,
    page: ParticlePage | None = None,
):
    if particle == EMPTY_PARTICLE:
        return
    if not managed:
        particle.spawn(layout, duration=duration)
        return
    assert page is not None
    particle_id = particle.id
    first = len(page.entries) == 0
    serial = 0 if first else page.serial
    lane_slot = -1
    if manage_kind == ParticleManageKind.LANE or (
        manage_kind == ParticleManageKind.MULTI and particle_id == BaseParticles.lane.id
    ):
        if first and manage_kind == ParticleManageKind.MULTI:
            prepare_particle_lanes(chunk_key, particle, 0, -1, overlaps=False)
        if first:
            serial = _ticket(chunk_key)
        lane_slot = _critical_slot(particle_id, serial) if first else page.lane_slot - 1
        if lane_slot < 0:
            return
        chunk = ParticleHandler.critical_lanes[lane_slot]
        if chunk.overlaps and not _lane_alive(chunk, slot):
            return
    else:
        if first and manage_kind == ParticleManageKind.MULTI:
            serial = _ticket(chunk_key)
        if serial == 0:
            ParticleHandler.serials[particle_id] += 1
            serial = ParticleHandler.serials[particle_id]
            if manage_kind == ParticleManageKind.MULTI:
                _set_ticket(chunk_key, serial)
        elif first and ParticleHandler.serials[particle_id] - serial >= PARTICLE_CHUNKS_PER_KIND:
            return
    if (
        manage_kind == ParticleManageKind.REST
        and _is_arrow(particle_id)
        and _emit_cached_arrow(particle, layout, duration, serial)
    ):
        return
    if first:
        page.particle_id = particle_id
        page.lane_slot = lane_slot + 1
        page.serial = serial
        page.version = ParticleHandler.serials[particle_id]
        page.end_time = time() + duration
    page.entries.append(ParticlePageEntry(particle.spawn(layout, duration=duration), slot))


def update_particle_page(page: ParticlePage) -> bool:
    if len(page.entries) == 0:
        return True
    if time() >= page.end_time:
        page.entries.clear()
        return True
    serial = ParticleHandler.serials[page.particle_id]
    if page.lane_slot == 0:
        if serial - page.serial < PARTICLE_CHUNKS_PER_KIND:
            return False
        destroy_particle_page(page)
        return True
    if page.version == serial:
        return False
    chunk = ParticleHandler.critical_lanes[page.lane_slot - 1]
    if chunk.serial != page.serial or chunk.remaining == 0:
        destroy_particle_page(page)
        return True
    page.version = serial
    if not chunk.overlaps:
        return False
    alive = 0
    for entry in page.entries:
        if entry.handle.id >= 0:
            if not _lane_alive(chunk, entry.lane):
                entry.handle.destroy()
                entry.handle.id = -1
            else:
                alive += 1
    if alive == 0:
        page.entries.clear()
    return alive == 0


def destroy_particle_page(page: ParticlePage):
    """Release a page before presentation, or when a Watch seek terminates it."""
    if time() < page.end_time:
        for entry in page.entries:
            if entry.handle.id >= 0:
                entry.handle.destroy()
    page.entries.clear()
