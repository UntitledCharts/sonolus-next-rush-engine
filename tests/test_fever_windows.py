"""Repeat fever windows without chart changes, shared-state leaks or runtime scans."""

from __future__ import annotations

import random
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

# Register modes before importing the mutually dependent note and UI modules.
from sekai.play.mode import play_mode
from sekai.watch.mode import watch_mode

# isort: split

from sonolus.script.bucket import Judgment
from sonolus.script.debug import simulation_context
from sonolus.script.interval import clamp

from sekai.lib import fever
from sekai.play import custom_elements as play_ui
from sekai.play import events as play_events
from sekai.play import initialization as play_init
from sekai.preview import events as preview_events
from sekai.watch import events as watch_events
from sekai.watch import initialization as watch_init


class Ref:
    def __init__(self, registry, index=0):
        self.registry = registry
        self.index = index

    def get(self):
        return self.registry.at(self.index)


class Registry:
    def __init__(self):
        self.entities = {}
        self.reads = 0

    def at(self, index):
        self.reads += 1
        return self.entities[index]

    def add(self, index, **fields):
        entity = SimpleNamespace(index=index, **fields)
        entity.ref = lambda: Ref(self, index)
        self.entities[index] = entity
        return entity


def sort_fake(head, *, get_value, get_next_ref):
    nodes = []
    while head.index:
        node = head.get()
        nodes.append(node)
        head = Ref(head.registry, get_next_ref(node).index)
    nodes.sort(key=get_value)
    for i, node in enumerate(nodes):
        get_next_ref(node).index = nodes[i + 1].index if i + 1 < len(nodes) else 0
    return nodes[0].ref()


class FeverWindowTests(unittest.TestCase):
    def setUp(self):
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(simulation_context())
        self.heads = SimpleNamespace(chance_head=0, start_head=0)
        self.stack.enter_context(patch.object(fever, "FeverWindows", self.heads))
        self.stack.enter_context(patch.object(fever, "sort_linked_entities", sort_fake))
        self.chances = Registry()
        self.starts = Registry()
        self.now = 0
        self.skipping = False
        self.particles = []
        self.state = SimpleNamespace(fever_chance_current_combo=0, latest_note_time=-1e8)

    def prepare(self, starts, ends):
        self.heads.chance_head = 0
        self.heads.start_head = 0
        self.chances.entities.clear()
        self.starts.entities.clear()
        for i, t in enumerate(starts, 1):
            self.chances.add(
                i,
                start_time=t,
                time=t,
                end_time=0,
                counter=0,
                hits=0,
                cant_super=False,
                percentage=0,
                checker=0,
                force=True,
                despawn=False,
                next_ref=Ref(self.chances, self.heads.chance_head),
            )
            self.heads.chance_head = i
        for i, t in enumerate(ends, 1):
            self.starts.add(i, start_time=t, time=t, chance_index=0, next_ref=Ref(self.starts, self.heads.start_head))
            self.heads.start_head = i
        fever.prepare_fever_windows(self.chances, self.starts)

    def link_notes(self, times, judgments=None):
        registry = Registry()
        judgments = judgments or [Judgment.PERFECT] * len(times)
        for i, (t, judgment) in enumerate(zip(times, judgments, strict=True), 1):
            registry.add(
                i,
                target_time=t,
                calc_time=t,
                count=0,
                fever_index=0,
                fever_hits=0,
                judgment=judgment,
                played_hit_effects=False,
                ap=False,
                archetype_score_multiplier=1,
                entity_score_multiplier=0,
                score_next_ref=Ref(registry, i + 1 if i < len(times) else 0),
                at=registry.at,
            )
        return registry

    def assign_notes(self, module, notes, replay=False):
        cls = module.note.BaseNote if module is play_init else module.note.WatchBaseNote
        with ExitStack() as stack:
            stack.enter_context(patch.object(cls, "at", notes.at))
            stack.enter_context(patch.object(module, "FeverWindows", self.heads))
            stack.enter_context(patch.object(module, "FeverChance", self.chances))
            stack.enter_context(patch.object(module, "Options", SimpleNamespace(custom_score=1)))
            stack.enter_context(patch.object(module, "LastNote", SimpleNamespace(last_time=-1e8)))
            stack.enter_context(patch.object(module, "calculate_note_weight", return_value=1))
            stack.enter_context(patch.object(module, "level_score", return_value=SimpleNamespace(perfect_multiplier=1)))
            if module is play_init:
                stack.enter_context(
                    patch.object(
                        module.custom_elements,
                        "ScoreIndicator",
                        SimpleNamespace(
                            total_weight=SimpleNamespace(add=lambda _: None),
                        ),
                    )
                )
                module.setting_count(1 if notes.entities else 0, 0)
            else:
                stack.enter_context(patch.object(module, "is_replay", return_value=replay))
                stack.enter_context(patch.object(module, "calculate_score"))
                stack.enter_context(patch.object(module.custom_elements.DamageFlash, "spawn"))
                module.setting_combo(1 if notes.entities else 0, 0)

    def runtime(self, module):
        self.stack.enter_context(patch.object(module, "time", lambda: self.now))
        self.stack.enter_context(
            patch.object(module, "Options", SimpleNamespace(fever_effect=0, forced_fever_chance=True))
        )
        self.stack.enter_context(
            patch.object(module, "spawn_fever_chance_particle", lambda: self.particles.append("chance"))
        )
        self.stack.enter_context(patch.object(module, "spawn_fever_start_particle", lambda p: self.particles.append(p)))
        for name in ("draw_fever_side_cover", "draw_fever_side_bar", "draw_fever_gauge"):
            self.stack.enter_context(patch.object(module, name))
        if module is watch_events:
            self.stack.enter_context(patch.object(module, "Fever", self.state))
            self.stack.enter_context(patch.object(module, "is_skip", lambda: self.skipping))

    def test_existing_imports_and_shared_memory_stride_are_unchanged(self):
        for mode in (play_mode, watch_mode):
            lengths = []
            for cls in mode.archetypes:
                cls.schema()
                lengths.append(
                    max((f.offset + f.type._size_() for f in cls._shared_memory_fields_.values()), default=0)
                )
                if cls.name in ("FeverChance", "FeverStart"):
                    fields = {f.data_name for f in cls._imported_fields_.values()}
                    assert fields == ({"#BEAT", "force"} if cls.name == "FeverChance" else {"#BEAT"})
            assert max(lengths) == 44

    def test_unsorted_and_zero_time_pairs(self):
        self.prepare([10, -2, 0], [1, 12, -1])
        assert [(c.start_time, c.end_time) for c in self.chances.entities.values()] == [(10, 12), (-2, -1), (0, 1)]
        assert [(s.time, self.chances.at(s.chance_index).start_time) for s in self.starts.entities.values()] == [
            (1, 0),
            (12, 10),
            (-1, -2),
        ]

    def test_overlap_duplicate_unpaired_and_reversed_events_are_invalid(self):
        for a, b in (([1, 2], [3, 4]), ([1, 1], [2, 3]), ([1], []), ([], [1]), ([2], [1]), ([1], [1]), ([1], [2, 3])):
            with self.subTest(chances=a, starts=b), self.assertRaises(AssertionError):  # noqa: PT027
                self.prepare(a, b)

    def test_no_fever_events_is_valid(self):
        self.prepare([], [])
        assert fever.advance_fever_window(self.chances, 0, 100) == 0

    def test_both_modes_assign_boundary_notes_to_exactly_one_period(self):
        for module in (play_init, watch_init):
            self.prepare([1, 0, 3], [2, 1, 4])
            times = [-1, 0, 0.5, 1, 1, 1.5, 2, 2.5, 3, 3.9, 4]
            notes = self.link_notes(times)
            self.assign_notes(module, notes)
            assert [c.counter for c in self.chances.entities.values()] == [3, 2, 2]
            if module is play_init:
                assert [n.fever_index for n in notes.entities.values()] == [0, 2, 2, 1, 1, 1, 0, 0, 3, 3, 0]
            else:
                assert [n.fever_hits for n in notes.entities.values()] == [0, 1, 2, 1, 2, 3, 0, 0, 1, 2, 0]

    def test_random_period_counts_match_a_simple_reference(self):
        rng = random.Random(115)
        for module in (play_init, watch_init):
            for _ in range(12):
                pairs = [(i * 4, i * 4 + rng.choice((1, 2, 3))) for i in range(20)]
                starts, ends = [a for a, _ in pairs], [b for _, b in pairs]
                rng.shuffle(starts)
                rng.shuffle(ends)
                self.prepare(starts, ends)
                times = sorted(rng.randrange(-4, 330) / 4 for _ in range(300))
                notes = self.link_notes(times)
                self.assign_notes(module, notes)
                for c in self.chances.entities.values():
                    assert c.counter == sum(c.start_time <= t < c.end_time for t in times)

    def test_legacy_single_pair_fill_scale_and_super_latch_are_preserved(self):
        for count in range(2, 60):
            for hits in range(count + 1):
                for cant_super, previous in ((False, 0), (True, 0), (True, 0.9)):
                    expected = clamp(hits / (count - 1), 0, 0.9 if not cant_super or previous >= 0.9 else 0.89)
                    assert fever.fever_percentage(hits, count, cant_super, previous) == expected
        assert fever.fever_percentage(0, 0, False, 0) == 0
        assert fever.fever_percentage(1, 1, False, 0) == 0.9

    def test_play_judgments_update_only_their_assigned_window_even_when_late(self):
        self.prepare([0, 1], [1, 2])
        notes = self.link_notes([0.5, 1, 1.5, 2])
        self.assign_notes(play_init, notes)
        with patch.object(play_ui.note.BaseNote, "at", notes.at), patch.object(play_ui, "FeverChance", self.chances):
            for index, judgment in ((2, Judgment.PERFECT), (1, Judgment.MISS), (3, Judgment.GREAT), (4, Judgment.MISS)):
                play_ui.ComboJudge.check_fever_count(SimpleNamespace(note_index=index, judgment=judgment))
        assert (self.chances.at(1).hits, self.chances.at(1).cant_super) == (0, True)
        assert (self.chances.at(2).hits, self.chances.at(2).cant_super) == (2, False)

    def test_play_hit_update_cost_does_not_depend_on_window_count(self):
        for count in (1, 128, 1024):
            self.prepare(list(range(0, count * 2, 2)), list(range(1, count * 2 + 1, 2)))
            with (
                patch.object(play_ui.note.BaseNote, "at", return_value=SimpleNamespace(fever_index=count)),
                patch.object(play_ui, "FeverChance", self.chances),
            ):
                self.chances.reads = 0
                for _ in range(100):
                    play_ui.ComboJudge.check_fever_count(SimpleNamespace(note_index=1, judgment=Judgment.PERFECT))
                assert self.chances.reads == 100

    def test_each_play_window_emits_its_own_chance_and_start(self):
        self.prepare([0, 4, 8], [2, 6, 10])
        self.runtime(play_events)
        for c in self.chances.entities.values():
            c.counter = 10
            c.hits = 5
            self.now = c.start_time
            play_events.FeverChance.update_parallel(c)
            self.now = c.end_time
            play_events.FeverChance.update_parallel(c)
            assert c.despawn
        assert self.particles == ["chance", 5 / 9, "chance", 5 / 9, "chance", 5 / 9]

    def test_watch_failures_and_prefix_hits_reset_for_each_window(self):
        self.prepare([0, 2], [1, 3])
        notes = self.link_notes(
            [0, 0.2, 0.4, 1.5, 2, 2.2, 2.4],
            [
                Judgment.PERFECT,
                Judgment.MISS,
                Judgment.GREAT,
                Judgment.PERFECT,
                Judgment.PERFECT,
                Judgment.PERFECT,
                Judgment.PERFECT,
            ],
        )
        self.assign_notes(watch_init, notes, replay=True)
        assert [(c.counter, c.hits, c.cant_super) for c in self.chances.entities.values()] == [
            (3, 2, True),
            (3, 3, False),
        ]
        assert notes.at(5).fever_hits == 1
        self.runtime(watch_events)
        for c in self.chances.entities.values():
            self.now = c.end_time
            self.state.latest_note_time = 4
            watch_events.FeverChance.update_parallel(c)
        assert self.particles == [0.89, 0.9]

    def test_watch_seek_restores_each_windows_fill_and_one_shot_state(self):
        self.prepare([0, 4], [2, 6])
        self.runtime(watch_events)
        a, b = self.chances.at(1), self.chances.at(2)
        a.counter, a.hits, a.cant_super = 10, 9, True
        b.counter, b.hits = 10, 9
        self.now = 5
        self.state.latest_note_time, self.state.fever_chance_current_combo = 4.5, 3
        watch_events.FeverChance.update_parallel(b)
        assert b.percentage == 3 / 9
        self.now = 1
        self.skipping = True
        self.state.latest_note_time, self.state.fever_chance_current_combo = 0.5, 6
        watch_events.FeverChance.update_parallel(a)
        assert a.percentage == 6 / 9
        self.now = 2.5
        self.state.latest_note_time = 3
        watch_events.FeverChance.update_parallel(a)
        assert a.percentage == 0.89
        assert watch_events.FeverChance.despawn_time(a) == 3
        assert watch_events.FeverChance.despawn_time(b) == 7
        self.now = 4
        self.state.latest_note_time = 3
        watch_events.FeverChance.update_parallel(b)
        assert b.percentage == 0

    def test_preview_displays_each_pair_and_its_own_partner_time(self):
        self.prepare([0, 10], [4, 14])
        calls = []
        line = SimpleNamespace(draw=lambda *_, **__: None)
        with (
            patch.object(preview_events, "ActiveSkin", SimpleNamespace(fever_chance_line=line, fever_start_line=line)),
            patch.object(preview_events, "layout_preview_bar_line", return_value=None),
            patch.object(preview_events, "print_at_time", side_effect=lambda value, t, **_: calls.append((value, t))),
            patch.object(preview_events, "PreviewFeverChance", self.chances),
        ):
            # Keep the real render method while replacing cross-entity lookups.
            for c in self.chances.entities.values():
                _PREVIEW_CHANCE_RENDER(c)
            for s in self.starts.entities.values():
                preview_events.PreviewFeverStart.render(s)
        assert calls == [(0, 0), (4, 0), (10, 10), (14, 10), (4, 4), (0, 4), (14, 14), (10, 14)]


_PREVIEW_CHANCE_RENDER = preview_events.PreviewFeverChance.render


if __name__ == "__main__":
    unittest.main()
