from __future__ import annotations

from sonolus.script.archetype import (
    EntityRef,
    PlayArchetype,
    StandardImport,
    callback,
    entity_data,
    imported,
    shared_memory,
)
from sonolus.script.runtime import time

from sekai.lib import archetype_names
from sekai.lib.ease import EaseType
from sekai.lib.timescale import RunSummary, TimelineError, TransitionStyle, initialize_timescale_group, prepare_group
from sekai.lib.timescale_math import TimePosition


class TimescaleChange(PlayArchetype):
    name = archetype_names.TIMESCALE_CHANGE
    beat: StandardImport.BEAT
    timescale: StandardImport.TIMESCALE
    timescale_skip: StandardImport.TIMESCALE_SKIP
    timescale_group: StandardImport.TIMESCALE_GROUP
    timescale_ease: EaseType = imported(name="#TIMESCALE_EASE", default=EaseType.NONE)
    transition_style: TransitionStyle = imported(name="transitionStyle", default=TransitionStyle.TIMESCALE)
    hide_notes: bool = imported(name="hideNotes")
    next_ref: EntityRef[TimescaleChange] = imported(name="next")
    event_start: float = entity_data()
    event_end: float = entity_data()
    converted_skip: float = entity_data()
    position: TimePosition = entity_data()
    scroll_skip: TimePosition = entity_data()
    scroll_skip_base: float = entity_data()
    ordinal: int = entity_data()
    prev_ref: int = entity_data()
    run_first: int = entity_data()
    run_end: int = entity_data()  # Stored on the first marker of each run.
    prev_run: int = entity_data()
    validation_owner: int = entity_data()
    jump_end: int = entity_data()
    jump_width: int = entity_data()
    jump: RunSummary = entity_data()
    note_visibility_start: float = entity_data()

    def spawn_order(self) -> float:
        return 1e8

    def should_spawn(self) -> bool:
        return False


class TimescaleGroup(PlayArchetype):
    name = archetype_names.TIMESCALE_GROUP
    first_ref: EntityRef[TimescaleChange] = imported(name="first")
    force_note_speed: float = imported(name="forceNoteSpeed")
    valid: bool = entity_data()
    has_scroll: bool = entity_data()
    monotone_targets: bool = entity_data()
    identity: bool = entity_data()
    error_code: TimelineError = entity_data()
    used: bool = entity_data()
    effective_preempt: float = entity_data()
    needed_start: float = entity_data()
    needed_end: float = entity_data()
    note_visibility_end: float = entity_data()
    lookup_ref: int = shared_memory()
    current_event: int = shared_memory()
    current_run: int = shared_memory()
    current_speed: float = shared_memory()
    current_constant: bool = shared_memory()
    coordinate: TimePosition = shared_memory()
    time_valid: bool = shared_memory()
    last_updated: float = shared_memory()
    future_gain: float = shared_memory()
    future_offset: float = shared_memory()
    past_gain: float = shared_memory()
    past_offset: float = shared_memory()
    hide_notes: bool = shared_memory()
    event_start: float = shared_memory()
    event_end: float = shared_memory()
    v0: float = shared_memory()
    v1: float = shared_memory()
    ease: EaseType = shared_memory()
    style: TransitionStyle = shared_memory()
    last_spawn_target: float = shared_memory()
    last_spawn_ceiling: float = shared_memory()
    last_spawn_time: float = shared_memory()
    spawn_cursor_valid: bool = shared_memory()

    @callback(order=-2)
    def preprocess(self):
        initialize_timescale_group(self)

    @callback(order=-3)
    def update_sequential(self):
        assert self.used
        prepare_group(self.index, time())
        # Prepare the group before despawning so notes and connectors can draw
        # their final frame, even if a time jump passes the group's end.
        if time() > self.needed_end:
            self.despawn = True

    def spawn_order(self) -> float:
        return self.needed_start

    def should_spawn(self) -> bool:
        return self.used and time() >= self.needed_start
