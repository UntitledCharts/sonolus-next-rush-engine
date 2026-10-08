"""Compare frame-cached Watch geometry with event queries at jumps and rewinds."""

import unittest
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import patch

from sekai.lib import stage as stage_lib
from sekai.lib.ease import EaseType
from sekai.watch import note as watch_note
from sekai.watch.dynamic_stage import WatchDynamicStage


class EventRef:
    """In-memory references for the real event-list search and stage evaluators."""

    events: ClassVar[dict[int, Any]] = {}

    def __init__(self, index=0):
        self.index = index

    def get(self):
        return self.events[self.index]

    def with_archetype(self, archetype):
        return self

    def __pos__(self):
        return EventRef(self.index)


class NoteView(SimpleNamespace):
    """Bind the real note properties and methods to explicit test data."""

    def __getattr__(self, name):
        member = getattr(watch_note.WatchBaseNote, name)
        if isinstance(member, property):
            assert member.fget is not None
            return member.fget(self)
        return member.__get__(self)


def event_list(values):
    start = len(EventRef.events) + 1
    for i, value in enumerate(values):
        index = start + i
        following = EventRef(index + 1 if i + 1 < len(values) else 0)
        EventRef.events[index] = SimpleNamespace(
            **value,
            next_ref=following,
            skip_refs=[following],
            skip_levels=1,
        )
    return EventRef(start)


def make_stage(index, easing, *, masking=True) -> Any:
    times = (0, 4, 4, 8)  # Include simultaneous events and both step midpoints.
    masks = event_list(
        [
            {"time": t, "lane": lane + index * 0.25, "size": size, "mask_notes": masking and i != 2, "ease": easing}
            for i, (t, lane, size) in enumerate(zip(times, (-1.5, 1, -0.5, 3), (3, 0.2, 1, 0), strict=True))
        ]
    )
    pivots = event_list(
        [
            {
                "time": t,
                "lane": lane + index * 0.5,
                "division_size": 2,
                "division_parity": 0,
                "y_offset": 0,
                "ease": easing,
            }
            for t, lane in zip(times, (-3, 3, -1, 4), strict=True)
        ]
    )
    styles = event_list(
        [
            {
                "time": t,
                "ease": easing,
                "judge_line_color": 0,
                "judge_line_style": 0,
                "left_border_style": 0,
                "right_border_style": 0,
                "lane_alpha": 0,
                "judge_line_alpha": 1,
                "full_width": i % 2 == 1,
                "division_line_alpha": 1,
                "note_alpha": 1,
            }
            for i, t in enumerate(times)
        ]
    )
    return SimpleNamespace(
        index=index,
        first_mask_change_ref=masks,
        first_pivot_change_ref=pivots,
        first_style_change_ref=styles,
        first_transform_change_ref=EventRef(),
        props=+stage_lib.StageProps,
        fever_boundary=lambda: None,
    )


def note_view(stage=None, *, lane: float = 0, size: float = 2):
    return NoteView(
        is_attached=False,
        stage_ref=SimpleNamespace(index=stage.index if stage else 0, get=lambda: stage),
        rel_lane=lane,
        lane=lane,
        size=size,
    )


class WatchStageCacheTests(unittest.TestCase):
    def setUp(self):
        EventRef.events = {}
        self.now = 0
        self.enterContext(patch.object(stage_lib.runtime, "time", side_effect=lambda: self.now))
        self.enterContext(patch.object(watch_note, "time", side_effect=lambda: self.now))
        self.enterContext(patch.object(stage_lib, "get_archetype_by_name", return_value=SimpleNamespace))
        self.enterContext(patch.object(stage_lib, "get_event_as", side_effect=lambda ref, archetype: ref.get()))

    def check_frame(self, notes):
        for note in notes:
            # The unchanged arbitrary-time API is the previous implementation's result.
            expected = note.visual_extents_at(self.now, right_limit=True)
            particles = note._stage_lane_particles_at(self.now, right_limit=True)
            with (
                patch.object(watch_note, "get_stage_props", side_effect=AssertionError("requeried stage")),
                patch.object(watch_note, "get_stage_pivot_lane", side_effect=AssertionError("requeried pivot")),
            ):
                assert note.visual_extents == expected
                assert note.visual_lane_particles == particles

    def test_all_easings_match_current_event_queries_after_jumps_and_rewinds(self):
        for easing in EaseType:
            with self.subTest(easing=easing):
                EventRef.events = {}
                head_stage = make_stage(1, easing)
                tail_stage = make_stage(2, easing, masking=False)
                masked_tail_stage = make_stage(3, easing)
                head = note_view(head_stage, lane=0.75, size=6)
                tail = note_view(tail_stage, lane=-0.25, size=0.2)
                masked_tail = note_view(masked_tail_stage, lane=-0.75, size=0.5)
                notes = [note_view(), note_view(head_stage, size=0), head, tail, masked_tail]
                for endpoint in (head, tail, masked_tail):
                    for frac in (-0.25, 0, 0.5, 1, 1.25):
                        attached = note_view(head_stage, size=1.5)
                        attached.is_attached = True
                        attached.attach_head_ref = SimpleNamespace(get=lambda head=head: head)
                        attached.attach_tail_ref = SimpleNamespace(get=lambda endpoint=endpoint: endpoint)
                        attached.attach_eased_frac = frac
                        notes.append(attached)
                # Samples include exact jumps, adjacent representable times, and backwards seeks.
                for self.now in (
                    -1,
                    0,
                    1,
                    2 - 1e-10,
                    2,
                    2 + 1e-10,
                    3.9,
                    4 - 1e-10,
                    4,
                    4 + 1e-10,
                    6 - 1e-10,
                    6,
                    6 + 1e-10,
                    8,
                    9,
                    4,
                    2,
                    0,
                    8,
                    1,
                ):
                    WatchDynamicStage.update_sequential(head_stage)
                    WatchDynamicStage.update_sequential(tail_stage)
                    WatchDynamicStage.update_sequential(masked_tail_stage)
                    self.check_frame(notes)

    def test_arbitrary_time_queries_keep_left_limit_at_event_boundaries(self):
        stage = make_stage(1, EaseType.LINEAR)
        note = note_view(stage, lane=0.5, size=0.1)
        self.now = 4
        WatchDynamicStage.update_sequential(stage)
        left = note.visual_extents_at(self.now)
        right = note.visual_extents_at(self.now, right_limit=True)
        assert left != right
        assert note.visual_extents == right
        # Reading a different time never reads the current frame cache.
        assert note.visual_extents_at(1) != right

    def test_no_event_stage_and_unstaged_note_use_default_values(self):
        stage: Any = SimpleNamespace(
            index=1,
            first_mask_change_ref=EventRef(),
            first_pivot_change_ref=EventRef(),
            first_style_change_ref=EventRef(),
            first_transform_change_ref=EventRef(),
            props=+stage_lib.StageProps,
            fever_boundary=lambda: None,
        )
        for self.now in (-1, 0, 3, 1):
            WatchDynamicStage.update_sequential(stage)
            self.check_frame([note_view(), note_view(stage, lane=2)])


if __name__ == "__main__":
    unittest.main()
