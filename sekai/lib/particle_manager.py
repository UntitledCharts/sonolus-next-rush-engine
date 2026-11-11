from __future__ import annotations

from math import floor, inf

from sonolus.script.array import Array, Dim
from sonolus.script.bucket import Judgment
from sonolus.script.containers import VarArray
from sonolus.script.globals import level_memory
from sonolus.script.particle import Particle, ParticleHandle
from sonolus.script.quad import Quad
from sonolus.script.record import Record
from sonolus.script.runtime import time

from sekai.lib.note_style import NoteVisualFamily
from sekai.lib.particle import EMPTY_PARTICLE

PARTICLE_PAGE_SIZE = 8
AURA_POOL_LIMIT = 12
GEN_POOL_LIMIT = 6
FLASH_POOL_LIMIT = 5
CONNECTION_POOL_LIMIT = 5
HOLD_POOL_LIMIT = 10
LANE_COUNT = 254
FLASH_POOL_START = 13 * 3
LANE_POOL_START = FLASH_POOL_START + 2
PARTICLE_POOL_COUNT = LANE_POOL_START + 4
_POOL_LIMITS = Array(
    *(
        12 if family in (8, 9) else 5 if family in (10, 11) else 6 if component in (0, 1) else 12
        for family in range(13)
        for component in range(3)
    ),
    FLASH_POOL_LIMIT,
    FLASH_POOL_LIMIT,
    1,
    1,
    1,
    1,
)


def note_effect_pool_family(family: NoteVisualFamily, judgment: Judgment) -> int:
    match family:
        case NoteVisualFamily.NORMAL_NOTE:
            return 0 if judgment == Judgment.PERFECT else 1 if judgment == Judgment.GREAT else 2
        case NoteVisualFamily.CRITICAL_NOTE:
            return 3
        case NoteVisualFamily.SLIDE_NOTE:
            return 4
        case NoteVisualFamily.CRITICAL_SLIDE_NOTE:
            return 5
        case (
            NoteVisualFamily.FLICK_NOTE
            | NoteVisualFamily.DOWN_FLICK_NOTE
            | NoteVisualFamily.TRACE_FLICK_NOTE
            | NoteVisualFamily.TRACE_DOWN_FLICK_NOTE
        ):
            return 6
        case (
            NoteVisualFamily.CRITICAL_FLICK_NOTE
            | NoteVisualFamily.CRITICAL_DOWN_FLICK_NOTE
            | NoteVisualFamily.CRITICAL_TRACE_FLICK_NOTE
            | NoteVisualFamily.CRITICAL_TRACE_DOWN_FLICK_NOTE
        ):
            return 7
        case NoteVisualFamily.TRACE_NOTE:
            return 8
        case NoteVisualFamily.CRITICAL_TRACE_NOTE:
            return 9
        case NoteVisualFamily.NORMAL_SLIDE_TICK_NOTE:
            return 10
        case NoteVisualFamily.CRITICAL_SLIDE_TICK_NOTE:
            return 11
        case _:
            return 12


def note_particle_pool(family: int, component: int) -> int:
    if component == 2:
        return FLASH_POOL_START + int(family == 7)
    if component == 5:
        lane_family = 2 if family == 6 else 3 if family == 7 else 1 if family in (3, 5) else 0
        return LANE_POOL_START + lane_family
    render_component = 1 if component in (1, 3) else 2 if component == 4 else 0
    return family * 3 + render_component


class ParticlePageEntry(Record):
    handle: ParticleHandle
    ticket: int


class ParticlePage(Record):
    pool_id: int
    serial: int  # Lane generation, or the first live entry index in a ring pool.
    version: int
    epoch: int
    end_time: float
    entries: VarArray[ParticlePageEntry, Dim[8]]


@level_memory
class ParticleHandler:
    epoch: int
    serials: Array[int, Dim[PARTICLE_POOL_COUNT]]
    aura_limits: Array[int, Dim[PARTICLE_POOL_COUNT]]
    lanes: Array[Array[int, Dim[LANE_COUNT]], Dim[4]]
    hold_owners: Array[int, Dim[2 * HOLD_POOL_LIMIT]]
    hold_deadlines: Array[float, Dim[2 * HOLD_POOL_LIMIT]]
    hold_epochs: Array[int, Dim[2 * HOLD_POOL_LIMIT]]
    empty_handles: Array[int, Dim[LANE_COUNT]]
    empty_deadlines: Array[float, Dim[LANE_COUNT]]


def clear_particles():
    ParticleHandler.epoch += 1
    for i in range(LANE_COUNT):
        if ParticleHandler.empty_handles[i] > 0 and time() < ParticleHandler.empty_deadlines[i]:
            ParticleHandle(ParticleHandler.empty_handles[i] - 1).destroy()
        ParticleHandler.empty_handles[i] = 0


def emit_empty_lane_particle(particle: Particle, layout: Quad, duration: float, lane: float):
    index = floor(lane) + 127
    if not 0 <= index < LANE_COUNT or particle == EMPTY_PARTICLE:
        return
    if ParticleHandler.empty_handles[index] > 0 and time() < ParticleHandler.empty_deadlines[index]:
        ParticleHandle(ParticleHandler.empty_handles[index] - 1).destroy()
    ParticleHandler.empty_handles[index] = particle.spawn(layout, duration=duration).id + 1
    ParticleHandler.empty_deadlines[index] = time() + duration


def reserve_hold_particles(owner: int, critical: bool, end_time: float = inf) -> int:
    first = int(critical) * HOLD_POOL_LIMIT
    for slot in range(first, first + HOLD_POOL_LIMIT):
        if (
            ParticleHandler.hold_owners[slot] == 0
            or ParticleHandler.hold_epochs[slot] != ParticleHandler.epoch
            or time() >= ParticleHandler.hold_deadlines[slot]
        ):
            ParticleHandler.hold_owners[slot] = owner + 1
            ParticleHandler.hold_deadlines[slot] = end_time
            ParticleHandler.hold_epochs[slot] = ParticleHandler.epoch
            return slot + 1
    return 0


def release_hold_particles(slot: int, owner: int):
    if slot > 0 and ParticleHandler.hold_owners[slot - 1] == owner + 1:
        ParticleHandler.hold_owners[slot - 1] = 0


def emit_particle(
    particle: Particle,
    layout: Quad,
    duration: float,
    pool_id: int,
    lane: float,
    managed: bool,
    page: ParticlePage | None = None,
    aura_limit: int = AURA_POOL_LIMIT,
):
    if particle == EMPTY_PARTICLE:
        return
    if not managed:
        particle.spawn(layout, duration=duration)
        return
    assert page is not None
    if _POOL_LIMITS[pool_id] == AURA_POOL_LIMIT:
        ParticleHandler.aura_limits[pool_id] = max(ParticleHandler.aura_limits[pool_id], aura_limit)
    if len(page.entries) == 0:
        page.pool_id = pool_id
        page.epoch = ParticleHandler.epoch
        page.end_time = time() + duration
        page.serial = 0
        if pool_id >= LANE_POOL_START:
            ParticleHandler.serials[pool_id] += 1
            page.serial = ParticleHandler.serials[pool_id]
    ticket = 0
    if pool_id >= LANE_POOL_START:
        ticket = floor(lane) + 127
        if not 0 <= ticket < LANE_COUNT:
            return
        ParticleHandler.lanes[pool_id - LANE_POOL_START][ticket] = page.serial
    else:
        ParticleHandler.serials[pool_id] += 1
        ticket = ParticleHandler.serials[pool_id]
    page.entries.append(ParticlePageEntry(particle.spawn(layout, duration=duration), ticket))
    page.version = -1


def update_particle_page(page: ParticlePage) -> bool:
    if len(page.entries) == 0:
        return True
    if time() >= page.end_time:
        page.entries.clear()
        return True
    if page.epoch != ParticleHandler.epoch:
        destroy_particle_page(page)
        return True
    serial = ParticleHandler.serials[page.pool_id]
    if page.version == serial:
        return False
    page.version = serial
    if page.pool_id < LANE_POOL_START:
        limit = max(_POOL_LIMITS[page.pool_id], ParticleHandler.aura_limits[page.pool_id])
        while page.serial < len(page.entries):
            entry = page.entries[page.serial]
            if entry.handle.id >= 0:
                if serial - entry.ticket < limit:
                    return False
                entry.handle.destroy()
                entry.handle.id = -1
            page.serial += 1
        page.entries.clear()
        return True
    alive = 0
    for entry in page.entries:
        if entry.handle.id < 0:
            continue
        if ParticleHandler.lanes[page.pool_id - LANE_POOL_START][entry.ticket] == page.serial:
            alive += 1
        else:
            entry.handle.destroy()
            entry.handle.id = -1
    if alive == 0:
        page.entries.clear()
    return alive == 0


def destroy_particle_page(page: ParticlePage):
    """Release live handles when a Watch seek terminates their emitter."""
    if time() < page.end_time:
        for entry in page.entries:
            if entry.handle.id >= 0:
                entry.handle.destroy()
    page.entries.clear()
