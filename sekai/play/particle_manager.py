from __future__ import annotations

from sonolus.script.archetype import (
    PlayArchetype,
    entity_memory,
)
from sonolus.script.bucket import Judgment

from sekai.lib import archetype_names
from sekai.lib.layout import FlickDirection
from sekai.lib.note import NoteEffectKind, NoteKind, handle_note_particles


class ParticleManager(PlayArchetype):
    name = archetype_names.PARTICLE_MANAGER

    kind: NoteKind = entity_memory()
    effect_kind: NoteEffectKind = entity_memory()
    lane: float = entity_memory()
    size: float = entity_memory()
    direction: FlickDirection = entity_memory()
    judgment: Judgment = entity_memory()
    y_offset: float = entity_memory()
    pivot_lane: float = entity_memory()
    half_offset: bool = entity_memory()
    target_time: float = entity_memory()

    def update_sequential(self):
        if self.despawn:
            return
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
        )

    def update_parallel(self):
        if self.despawn:
            return
        self.despawn = True
