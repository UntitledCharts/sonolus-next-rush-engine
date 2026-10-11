"""Input indexing preserves stable ties, overlap priority, and allocation rounds."""

import gzip
import random
import struct
import unittest
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from sonolus.backend.blocks import PlayBlock
from sonolus.backend.interpret import Interpreter
from sonolus.backend.node import FunctionNode
from sonolus.backend.ops import Op
from sonolus.build.engine import package_engine, unpackage_data
from sonolus.script.archetype import EntityRef, PlayArchetype, entity_memory, imported, shared_memory
from sonolus.script.array import Dim
from sonolus.script.containers import VarArray
from sonolus.script.debug import simulation_context
from sonolus.script.engine import EngineData, PlayMode
from sonolus.script.globals import level_memory
from sonolus.script.interval import Interval
from sonolus.script.quad import Quad, Rect
from sonolus.script.record import Record
from sonolus.script.runtime import Touch
from sonolus.script.values import alloc
from sonolus.script.vec import Vec2

from sekai.lib.buckets import SLIDE_END_LOCKOUT_DURATION
from sekai.lib.layout import DynamicLayout, Hitbox, HitboxTarget, segment_closeness_score
from sekai.lib.note import NoteKind, is_head
from sekai.play import input_manager as manager
from sekai.play.input_index import TapPriorityQuery, sort_input_notes


class Ref:
    def __init__(self, index, registry):
        self.index = index
        self.registry = registry

    def get(self):
        return self.registry[self.index]


class ActiveRefs(list):
    def get_unchecked(self, index):
        return self[index]


def make_notes(specs):
    registry = {}
    for i, spec in enumerate(specs, 1):
        x, width = spec["x"], spec["width"]
        registry[i] = SimpleNamespace(
            beat=spec["beat"],
            target_time=spec["target_time"],
            is_trace_flick=spec["trace"],
            captured_touch_id=spec["captured"],
            captured_touch_time=0,
            kind=spec["kind"],
            unadjusted_input_interval=Interval(*spec["interval"]),
            hitbox=Hitbox(
                target=HitboxTarget(Vec2(x - width, 0), Vec2(x + width, 0)),
                bounds=Rect(x - width, x + width, 1, -1).as_quad(),
            ),
        )
    return ActiveRefs(Ref(i, registry) for i in registry), registry


def reference_allocate(active, touches):
    active.sort(key=lambda ref: ref.get().target_time)
    assigned = [i >= len(touches) or not touches[i].started for i in range(manager.INPUT_SLOTS)]
    empty, releases = [], []
    for _ in range(manager.INPUT_SLOTS):
        scores = [0.0] * manager.INPUT_SLOTS
        preferred = [-1] * manager.INPUT_SLOTS
        for i, touch in enumerate(touches[: manager.INPUT_SLOTS]):
            if assigned[i]:
                continue
            for j, ref in enumerate(active):
                target = ref.get()
                if target.captured_touch_id or touch.time not in target.unadjusted_input_interval:
                    continue
                if not target.hitbox.bounds.contains_point(touch.position):
                    continue
                if target.is_trace_flick and any(
                    not other.get().is_trace_flick
                    and other.get().beat == target.beat
                    and not other.get().captured_touch_id
                    and touch.time in other.get().unadjusted_input_interval
                    and other.get().hitbox.bounds.contains_point(touch.position)
                    for other in active
                ):
                    continue
                score = (
                    segment_closeness_score(touch.position, target.hitbox.target)
                    + (1 - target.target_time) / manager.INPUT_SCORE_TIME_SCALE
                )
                if preferred[i] == -1 or score > scores[i]:
                    scores[i], preferred[i] = score, j
        winners = [
            i
            for i in range(manager.INPUT_SLOTS)
            if preferred[i] >= 0
            and not any(
                preferred[j] == preferred[i] and (scores[j] > scores[i] or (scores[j] == scores[i] and j < i))
                for j in range(manager.INPUT_SLOTS)
                if j != i
            )
        ]
        if not winners:
            break
        for i in winners:
            target = active[preferred[i]].get()
            touch = touches[i]
            empty.append(touch.id)
            if not is_head(target.kind) and not target.is_trace_flick:
                releases.append((touch.id, target.target_time + SLIDE_END_LOCKOUT_DURATION))
            target.captured_touch_id = touch.id
            target.captured_touch_time = min(touch.time, touch.start_time)
            assigned[i] = True
    return empty, releases


class InputIndexTests(unittest.TestCase):
    def test_sort_preserves_ties_for_sorted_reverse_and_shuffled_windows(self):
        rng = random.Random(1304)
        with simulation_context():
            for count in (0, 1, 15, 16, 32, 64, 256):
                for shape in range(3):
                    values = [float(i // 3) for i in range(count)]
                    if shape == 1:
                        values.reverse()
                    if shape == 2:
                        rng.shuffle(values)
                    registry = {i: SimpleNamespace(target_time=t) for i, t in enumerate(values, 1)}
                    active = ActiveRefs(Ref(i, registry) for i in registry)
                    expected = sorted(registry, key=lambda i: registry[i].target_time)
                    sort_input_notes(active)
                    assert [ref.index for ref in active] == expected

    def test_priority_index_matches_scans_and_is_refreshed_after_capture(self):
        with simulation_context():
            specs = [
                {
                    "beat": i % 5 - 2,
                    "target_time": 1,
                    "trace": i % 3 == 0,
                    "captured": int(i % 7 == 0),
                    "x": i % 3 - 1,
                    "width": 0.75,
                    "kind": NoteKind.NORM_TAP,
                    "interval": (0.5, 1.5),
                }
                for i in range(64)
            ]
            active, registry = make_notes(specs)
            touch = SimpleNamespace(time=1, position=Vec2(0, 0))
            with patch.object(
                manager, "note", SimpleNamespace(NoteMemory=SimpleNamespace(active_tap_input_notes=active))
            ):
                for round_index in range(2):
                    query = TapPriorityQuery.new()
                    for beat in (-3, -2, -1, 0, 1, 2, 3, 0, -1):
                        assert query.contains(
                            active, touch, beat, manager.has_priority_tap
                        ) == manager.has_priority_tap(cast(Touch, touch), beat)
                    if round_index == 0:
                        for target in registry.values():
                            target.captured_touch_id = 99

    def test_priority_cache_matches_scans_before_and_after_many_queries(self):
        with simulation_context():
            specs = [
                {
                    "beat": (i * 31) % 97 - 48,
                    "target_time": 1,
                    "trace": i < 24,
                    "captured": 0,
                    "x": 0,
                    "width": 1,
                    "kind": NoteKind.NORM_TAP,
                    "interval": (0, 2),
                }
                for i in range(96)
            ]
            active, _ = make_notes(specs)
            touch = SimpleNamespace(time=1, position=Vec2(0, 0))
            with patch.object(
                manager, "note", SimpleNamespace(NoteMemory=SimpleNamespace(active_tap_input_notes=active))
            ):
                query = TapPriorityQuery.new()
                for beat in range(-60, 60):
                    assert query.contains(active, touch, beat, manager.has_priority_tap) == manager.has_priority_tap(
                        cast(Touch, touch), beat
                    )

    def test_full_allocator_matches_previous_choices_and_lockouts(self):
        rng = random.Random(277)
        with simulation_context():
            for case in range(32):
                specs = []
                for _ in range(rng.choice((8, 16, 32, 64))):
                    trace = rng.random() < 0.65
                    specs.append(
                        {
                            "beat": rng.choice((-2, -0.5, 0, 1, 2)),
                            "target_time": rng.choice((0.98, 1, 1.02)),
                            "trace": trace,
                            "captured": 99 if rng.random() < 0.1 else 0,
                            "x": rng.choice((-1, 0, 1)),
                            "width": rng.choice((0.5, 1.5)),
                            "kind": NoteKind.NORM_TRACE_FLICK if trace else NoteKind.NORM_TAP,
                            "interval": rng.choice(((0.5, 1.5), (0, 0.99), (1, 1.2))),
                        }
                    )
                touches = [
                    SimpleNamespace(
                        id=i + 1,
                        started=rng.random() < 0.9,
                        time=1,
                        start_time=rng.choice((0.9, 1)),
                        position=Vec2(rng.choice((-1, 0, 1)), 0),
                    )
                    for i in range(rng.randrange(1, 7))
                ]
                expected, expected_registry = make_notes(specs)
                actual, actual_registry = make_notes(specs)
                expected_events = reference_allocate(expected, touches)
                empty, releases = [], []
                with (
                    patch.object(
                        manager, "note", SimpleNamespace(NoteMemory=SimpleNamespace(active_tap_input_notes=actual))
                    ),
                    patch.object(manager, "processed_touches", return_value=touches),
                    patch.object(manager, "time", return_value=1),
                    patch.object(manager, "DynamicLayout", SimpleNamespace(w_scale=1)),
                    patch.object(manager, "disallow_empty", side_effect=lambda t, events=empty: events.append(t.id)),
                    patch.object(
                        manager,
                        "disallow_release",
                        side_effect=lambda t, end, events=releases: events.append((t.id, end)),
                    ),
                ):
                    manager.preassign_taps()
                assert (empty, releases) == expected_events, case
                if any(touch.started for touch in touches[: manager.INPUT_SLOTS]):
                    assert [ref.index for ref in actual] == [ref.index for ref in expected], case
                assert [(n.captured_touch_id, n.captured_touch_time) for n in actual_registry.values()] == [
                    (n.captured_touch_id, n.captured_touch_time) for n in expected_registry.values()
                ], case


class IdleInputTests(unittest.TestCase):
    def test_empty_windows_and_ineligible_touches_skip_sorting_and_assignment(self):
        for assign, flag, active_name in (
            (manager.preassign_taps, "started", "active_tap_input_notes"),
            (manager.preassign_releases, "ended", "active_release_input_notes"),
        ):
            for count, touch_count, eligible_index in ((0, 2, 0), (32, 0, -1), (256, 16, -1), (32, 17, 16)):
                active = [None] * count
                touches = [SimpleNamespace(**{flag: i == eligible_index}) for i in range(touch_count)]
                with (
                    patch.object(manager, "note", SimpleNamespace(NoteMemory=SimpleNamespace(**{active_name: active}))),
                    patch.object(manager, "processed_touches", return_value=touches),
                    patch.object(manager, "sort_input_notes") as sort,
                    patch.object(manager, "disallow_empty") as disallow,
                ):
                    assign()
                    sort.assert_not_called()
                    disallow.assert_not_called()

    def test_later_eligible_input_preserves_stable_ties_after_idle_callbacks(self):
        with simulation_context():
            for assign, flag, active_name in (
                (manager.preassign_taps, "started", "active_tap_input_notes"),
                (manager.preassign_releases, "ended", "active_release_input_notes"),
            ):
                specs = [
                    {
                        "beat": i,
                        "target_time": 1 if i % 3 else 1.01,
                        "trace": False,
                        "captured": 0,
                        "x": 0,
                        "width": 1,
                        "kind": NoteKind.NORM_TAP,
                        "interval": (0, 2),
                    }
                    for i in range(32)
                ]
                active, registry = make_notes(specs)
                for target in registry.values():
                    target.active_head_ref = SimpleNamespace(index=0)
                touch = SimpleNamespace(id=1, started=False, ended=False, time=1, start_time=0.9, position=Vec2(0, 0))
                with (
                    patch.object(manager, "note", SimpleNamespace(NoteMemory=SimpleNamespace(**{active_name: active}))),
                    patch.object(manager, "processed_touches", return_value=[touch]),
                    patch.object(manager, "time", return_value=1),
                    patch.object(manager, "DynamicLayout", SimpleNamespace(w_scale=1)),
                    patch.object(manager, "disallow_empty"),
                    patch.object(manager, "disallow_release"),
                    patch.object(manager, "is_allowed_release", return_value=True),
                ):
                    for _ in range(3):
                        assign()
                    setattr(touch, flag, True)
                    assign()
                assert registry[2].captured_touch_id == 1
                assert sum(target.captured_touch_id != 0 for target in registry.values()) == 1
                assert [ref.index for ref in active] == sorted(registry, key=lambda i: registry[i].target_time)


class FixtureConnectorInfo(Record):
    input_bounds: Quad


class FixtureHead(PlayArchetype):
    active_connector_info: FixtureConnectorInfo = shared_memory()


class FixtureNote(PlayArchetype):
    target_time: float = shared_memory()
    beat: float = shared_memory()
    is_trace_flick: bool = shared_memory()
    captured_touch_id: int = shared_memory()
    captured_touch_time: float = shared_memory()
    kind: NoteKind = shared_memory()
    unadjusted_input_interval: Interval = shared_memory()
    hitbox: Hitbox = shared_memory()
    active_head_ref: EntityRef[FixtureHead] = shared_memory()


@level_memory
class FixtureNotes:
    active_tap_input_notes: VarArray[EntityRef[FixtureNote], Dim[256]]
    active_release_input_notes: VarArray[EntityRef[FixtureNote], Dim[256]]


def fixture_time():
    return 1.0


def run_fixture(probe, assign):
    manager.InputState.processed_touches.clear()
    manager.InputState.disallowed_empty_touches.clear()
    manager.InputState.disallowed_release_touches.clear()
    FixtureNotes.active_tap_input_notes.clear()
    FixtureNotes.active_release_input_notes.clear()
    DynamicLayout.w_scale = 1
    for i in range(probe.touch_count):
        touch = alloc(Touch)
        touch.id = i + 1
        touch.started = probe.touch_events == 0 or (probe.touch_events == 3 and i == 16)
        touch.ended = probe.touch_events == 2 or (probe.touch_events == 4 and i == 16)
        touch.time = 1
        touch.start_time = 0.9
        touch.position = Vec2(0, 0)
        manager.InputState.processed_touches.append(touch)
    for i in range(probe.note_count):
        target = FixtureNote.at(i + 1)
        target.beat = 1 if probe.same_beat else (i * 31) % probe.note_count if probe.beat_order else i
        target.target_time = 1 if probe.shape == 2 else 1 + (probe.note_count - i if probe.shape == 1 else i) / 512
        target.is_trace_flick = i < probe.trace_count
        target.kind = NoteKind.NORM_TRACE_FLICK if target.is_trace_flick else NoteKind.NORM_TAP
        target.captured_touch_id = 0
        target.captured_touch_time = 0
        target.unadjusted_input_interval = Interval(0, 2)
        target.hitbox = Hitbox(HitboxTarget(Vec2(-1, 0), Vec2(1, 0)), Rect(-1, 1, 1, -1).as_quad())
        target.active_head_ref.index = 0
        FixtureNotes.active_tap_input_notes.append(target.ref())
        FixtureNotes.active_release_input_notes.append(target.ref())
    assign()
    probe.captured = 0
    probe.snapshot = 0
    for i in range(probe.note_count):
        target = FixtureNote.at(i + 1)
        probe.captured += target.captured_touch_id != 0
        probe.snapshot += (i + 1) * target.captured_touch_id


class CompiledInputProbe(PlayArchetype):
    note_count: int = imported()
    trace_count: int = imported()
    touch_count: int = imported()
    shape: int = imported()
    same_beat: bool = imported()
    touch_events: int = imported()
    beat_order: bool = imported()
    captured: int = entity_memory()
    snapshot: float = entity_memory()

    def update_sequential(self):
        run_fixture(self, manager.preassign_taps)


class CompiledReleaseProbe(CompiledInputProbe):
    def update_sequential(self):
        run_fixture(self, manager.preassign_releases)


class CompiledInputIndexTests(unittest.TestCase):
    def test_compiled_sort_priority_and_allocation_rounds(self):
        fixture_module = ModuleType("fixture_notes")
        fixture_module.__dict__["NoteMemory"] = FixtureNotes
        with (
            patch.object(manager, "note", fixture_module),
            patch.object(manager, "time", fixture_time),
        ):
            packaged = package_engine(
                EngineData(play=PlayMode(archetypes=[FixtureHead, FixtureNote, CompiledInputProbe, CompiledReleaseProbe]))
            )
        payload = cast(dict[str, Any], unpackage_data(packaged.play_data))
        nodes = []
        for node in payload["nodes"]:
            nodes.append(
                node["value"]
                if "value" in node
                else FunctionNode(Op(node["func"]), tuple(nodes[i] for i in node["args"]))
            )
        rom = gzip.decompress(packaged.rom)
        for probe_index, count, shape, traces, touches, events, same_beat, expected_count, expected in (
            (2, 32, 0, 0, 2, 0, False, 2, 5),
            (2, 32, 1, 32, 2, 0, False, 2, 94),
            (2, 32, 2, 32, 2, 0, False, 2, 5),
            (2, 32, 2, 31, 2, 0, True, 2, 34),
            (2, 32, 2, 32, 16, 0, False, 16, 1496),
            (2, 32, 2, 32, 17, 0, False, 16, 1496),
            (2, 256, 1, 256, 16, 1, False, 0, 0),
            (2, 32, 1, 0, 17, 3, False, 0, 0),
            (2, 0, 0, 0, 2, 0, False, 0, 0),
            (3, 32, 1, 0, 2, 2, False, 2, 94),
            (3, 32, 2, 0, 2, 2, False, 2, 5),
            (3, 32, 2, 0, 17, 2, False, 16, 1496),
            (3, 256, 1, 0, 16, 1, False, 0, 0),
            (3, 32, 1, 0, 17, 4, False, 0, 0),
            (3, 0, 0, 0, 2, 2, False, 0, 0),
            (2, 128, 2, 64, 2, 0, False, 2, 5),
            (2, 128, 2, 127, 2, 0, True, 2, 130),
        ):
            archetype = payload["archetypes"][probe_index]
            runner = Interpreter()
            runner.blocks = {block: [0.0] * 32768 for block in PlayBlock}
            runner.blocks[PlayBlock.EngineRom] = list(struct.unpack(f"<{len(rom) // 4}f", rom))
            values = {
                "note_count": count,
                "trace_count": traces,
                "touch_count": touches,
                "shape": shape,
                "same_beat": same_beat,
                "touch_events": events,
                "beat_order": count == 128,
            }
            for field in archetype["imports"]:
                runner.set(PlayBlock.EntityData, field["index"], values[field["name"]])
            runner.run(nodes[archetype["updateSequential"]["index"]])
            assert runner.get(PlayBlock.EntityMemory, CompiledInputProbe._memory_fields_["captured"].offset) == expected_count
            assert runner.get(PlayBlock.EntityMemory, CompiledInputProbe._memory_fields_["snapshot"].offset) == expected


if __name__ == "__main__":
    unittest.main()
