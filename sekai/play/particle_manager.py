from __future__ import annotations

from sonolus.script.archetype import (
    PlayArchetype,
    entity_memory,
)
from sonolus.script.bucket import Judgment

from sekai.lib import archetype_names
from sekai.lib.layout import FlickDirection, StageScreenTransform
from sekai.lib.note import NoteEffectKind, NoteKind, handle_note_particles
from sekai.lib.note_style import NoteStyle
from sekai.lib.particle_manager import ParticlePage, update_particle_page


class ParticleManager(PlayArchetype):
    name = archetype_names.PARTICLE_MANAGER

    kind: NoteKind = entity_memory()
    style: NoteStyle = entity_memory()
    effect_kind: NoteEffectKind = entity_memory()
    lane: float = entity_memory()
    size: float = entity_memory()
    direction: FlickDirection = entity_memory()
    judgment: Judgment = entity_memory()
    y_offset: float = entity_memory()
    pivot_lane: float = entity_memory()
    half_offset: bool = entity_memory()
    target_time: float = entity_memory()
    group_id: float = entity_memory()
    lane_particles: bool = entity_memory()
    transform: StageScreenTransform = entity_memory()

    check: bool = entity_memory()

    component: int = entity_memory()
    page_index: int = entity_memory()
    page: ParticlePage = entity_memory()

    def update_sequential(self):
        if self.check:
            return
        self.check = True
        handle_note_particles(
            self.kind,
            self.effect_kind,
            self.lane,
            self.size,
            self.direction,
            self.judgment,
            y_offset=self.y_offset,
            pivot_lane=self.pivot_lane,
            half_offset=self.half_offset,
            group_id=self.group_id,
            lane_particles=self.lane_particles,
            transform=self.transform,
            style=self.style,
            component=self.component,
            page_index=self.page_index,
            page=self.page,
        )

    def update_parallel(self):
        if self.despawn:
            return
        if update_particle_page(self.page):
            self.despawn = True
