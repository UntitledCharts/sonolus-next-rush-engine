from math import inf

from sonolus.script.archetype import EntityRef, PlayArchetype, callback, entity_data, entity_memory, imported
from sonolus.script.runtime import time

from sekai.debug import DISABLE_NOTES
from sekai.lib import archetype_names
from sekai.lib.sim_line import draw_sim_line
from sekai.lib.timescale import MIN_START_TIME, TrajectoryCache, group_hide_notes
from sekai.lib.timescale_consumer import (
    note_visibility_end,
    note_visual_progress,
    prepare_note_trajectories,
    register_note_group_window,
    segment_visual_spawn_time,
)
from sekai.play.note import BaseNote


class SimLine(PlayArchetype):
    name = archetype_names.SIM_LINE

    left_ref: EntityRef[BaseNote] = imported(name="left")
    right_ref: EntityRef[BaseNote] = imported(name="right")

    left_trajectory_first: TrajectoryCache = entity_memory()
    left_trajectory_second: TrajectoryCache = entity_memory()
    right_trajectory_first: TrajectoryCache = entity_memory()
    right_trajectory_second: TrajectoryCache = entity_memory()

    spawn_time: float = entity_data()
    scheduled_spawn_time: float = entity_data()
    visibility_end_time: float = entity_data()

    @callback(order=1)
    def preprocess(self):
        self.spawn_time = inf
        self.scheduled_spawn_time = inf
        if DISABLE_NOTES:
            return
        if not self.left.preprocess_done or not self.right.preprocess_done:
            return
        # Hiding either endpoint hides the line.
        self.visibility_end_time = min(note_visibility_end(self.left), note_visibility_end(self.right))
        if self.visibility_end_time <= MIN_START_TIME:
            return
        start_time = min(
            self.left.start_time,
            self.right.start_time,
            segment_visual_spawn_time(
                self.left, self.right, min(self.left.target_time, self.right.target_time, self.visibility_end_time)
            ),
        )
        if start_time == inf or start_time >= self.visibility_end_time:
            return
        end_time = min(max(self.left.target_time, self.right.target_time), self.visibility_end_time) + 1.0
        self.left.extend_stage_windows(start_time - 1.0, end_time)
        self.right.extend_stage_windows(start_time - 1.0, end_time)

        # Keep timescale groups active through the line's final update.
        group_end = max(start_time, min(self.left.target_time, self.visibility_end_time))
        register_note_group_window(self.left, start_time, group_end)
        register_note_group_window(self.right, start_time, group_end)
        self.spawn_time = start_time
        self.scheduled_spawn_time = start_time

    def spawn_order(self) -> float:
        if DISABLE_NOTES:
            return 1e8
        return self.scheduled_spawn_time

    def should_spawn(self) -> bool:
        if DISABLE_NOTES:
            return False
        return time() >= self.scheduled_spawn_time

    def update_parallel(self):
        if time() < self.spawn_time:
            return
        if (
            self.left.is_despawned
            or self.right.is_despawned
            or time() > self.left.target_time
            or time() >= self.visibility_end_time
        ):
            self.despawn = True
            return
        if group_hide_notes(self.left.timescale_group) or group_hide_notes(self.right.timescale_group):
            return
        left_alpha = self.left.visual_note_alpha
        right_alpha = self.right.visual_note_alpha
        if left_alpha <= 0 or right_alpha <= 0:
            return
        left_lane, left_size = self.left.visual_extents
        right_lane, right_size = self.right.visual_extents
        if left_size <= 0 or right_size <= 0:
            return
        prepare_note_trajectories(self.left, self.left_trajectory_first, self.left_trajectory_second, time())
        prepare_note_trajectories(self.right, self.right_trajectory_first, self.right_trajectory_second, time())
        draw_sim_line(
            left_lane=left_lane,
            left_visual_progress=note_visual_progress(
                self.left, self.left_trajectory_first, self.left_trajectory_second, time()
            ),
            left_target_time=self.left.target_time,
            right_lane=right_lane,
            right_visual_progress=note_visual_progress(
                self.right, self.right_trajectory_first, self.right_trajectory_second, time()
            ),
            right_target_time=self.right.target_time,
            left_transform=self.left.visual_stage_transform().to_screen_transform(),
            right_transform=self.right.visual_stage_transform().to_screen_transform(),
            left_note_alpha=left_alpha,
            right_note_alpha=right_alpha,
        )

    @property
    def left(self) -> BaseNote:
        return self.left_ref.get()

    @property
    def right(self) -> BaseNote:
        return self.right_ref.get()
