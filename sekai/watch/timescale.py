from __future__ import annotations

from sonolus.script.archetype import (
    EntityRef,
    StandardImport,
    WatchArchetype,
    callback,
    imported,
    shared_memory,
)
from sonolus.script.runtime import time

from sekai.lib import archetype_names
from sekai.lib.timescale import (
    CompositeTime,
    ScaledTimeToFirstTime,
    TimeToLastChangeIndex,
    TimeToScaledTime,
)


class WatchTimescaleChange(WatchArchetype):
    name = archetype_names.TIMESCALE_CHANGE

    beat: StandardImport.BEAT
    timescale: StandardImport.TIMESCALE
    timescale_skip: StandardImport.TIMESCALE_SKIP
    timescale_group: StandardImport.TIMESCALE_GROUP
    timescale_ease: StandardImport.TIMESCALE_EASE
    hide_notes: bool = imported(name="hideNotes")
    next_ref: EntityRef[WatchTimescaleChange] = imported(name="next")


class WatchTimescaleGroup(WatchArchetype):
    name = archetype_names.TIMESCALE_GROUP

    first_ref: EntityRef[WatchTimescaleChange] = imported(name="first")
    force_note_speed: float = imported(name="forceNoteSpeed")

    current_scaled_time: CompositeTime = shared_memory()
    last_change: EntityRef[WatchTimescaleChange] = shared_memory()
    hide_notes: bool = shared_memory()
    last_updated: float = shared_memory()

    time_to_scaled_time: TimeToScaledTime = shared_memory()
    time_to_last_change_index: TimeToLastChangeIndex = shared_memory()
    scaled_time_to_first_time: ScaledTimeToFirstTime = shared_memory()
    scaled_time_to_first_time_2: ScaledTimeToFirstTime = shared_memory()

    def spawn_time(self) -> float:
        return -1e8

    def despawn_time(self) -> float:
        return 1e8

    @callback(order=-2)
    def preprocess(self):
        self.time_to_scaled_time.init(self.first_ref.index)
        self.time_to_last_change_index.init(self.first_ref.index)
        self.scaled_time_to_first_time.init(self.first_ref.index)
        self.scaled_time_to_first_time_2.init(self.first_ref.index)
        self.last_updated = -1e8

    def update(self):
        if self.last_updated == time():
            return
        self.last_updated = time()
        self.current_scaled_time = self.time_to_scaled_time.get(time())
        self.last_change.index = self.time_to_last_change_index.get(time())
        if self.last_change.index > 0:
            self.hide_notes = self.last_change.get().hide_notes
        else:
            self.hide_notes = False
