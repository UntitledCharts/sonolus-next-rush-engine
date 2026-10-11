"""Indexed particle management preserves replacement order without estimating expiry."""

import gzip
import random
import struct
import unittest
from typing import Any, cast
from unittest.mock import patch

from sonolus.backend.blocks import PlayBlock
from sonolus.backend.interpret import Interpreter
from sonolus.backend.node import FunctionNode
from sonolus.backend.ops import Op
from sonolus.build.engine import package_engine, unpackage_data
from sonolus.script.archetype import PlayArchetype, entity_memory, imported
from sonolus.script.bucket import Judgment
from sonolus.script.debug import simulation_context
from sonolus.script.engine import EngineData, PlayMode
from sonolus.script.particle import Particle
from sonolus.script.quad import Quad

from sekai.lib import particle_manager as manager
from sekai.lib.layout import DynamicLayout, FlickDirection
from sekai.lib.note import NoteEffectKind, NoteKind, handle_note_particles
from sekai.lib.options import Options
from sekai.lib.particle import EMPTY_NOTE_PARTICLE_SET


class CompiledParticleProbe(PlayArchetype):
    particle_id: int = imported()
    group_id: int = imported()
    manage_kind: manager.ParticleManageKind = imported()
    count: int = imported()
    snapshot: float = entity_memory()
    entry_count: int = entity_memory()

    def preprocess(self):
        manager.clear_particles()

    def update_sequential(self):
        particle = Particle(self.particle_id)
        chunk = manager.begin_particle_chunk(particle, self.group_id, self.manage_kind)
        for slot in range(self.count):
            manager.emit_particle(particle, +Quad, 0.01, self.manage_kind, slot, chunk, True)
        self.entry_count = len(manager.ParticleHandler.entries)
        self.snapshot = 0
        for i in range(self.entry_count):
            entry = manager.ParticleHandler.entries[i]
            self.snapshot += (i + 1) * (
                entry.key + entry.particle.id * 3 + entry.particle_id * 5 + entry.chunk_key * 7 + entry.chunk_serial * 11
            )


def critical_particles(kind, direction, style):
    result = +EMPTY_NOTE_PARTICLE_SET
    result.linear = Particle(2)
    result.circular = Particle(3)
    result.directional = Particle(4)
    result.slot_linear = Particle(5)
    result.lane = Particle(6)
    return result


class CompiledCriticalFlickProbe(PlayArchetype):
    def preprocess(self):
        manager.clear_particles()
        DynamicLayout.t = 0.7
        DynamicLayout.w_scale = 0.12
        DynamicLayout.h_scale = -1.4
        DynamicLayout.stage_tilt = 1
        DynamicLayout.size_zoom = 1

    def update_sequential(self):
        handle_note_particles(
            NoteKind.CRIT_FLICK, NoteEffectKind.CRIT_FLICK, 0, 6,
            FlickDirection.UP_OMNI, Judgment.PERFECT, group_id=1000,
        )


class ParticleInterpreter(Interpreter):
    def __init__(self):
        super().__init__()
        self.spawned = 0
        self.effects = []
        self.destroyed = []

    def run(self, node):
        if isinstance(node, FunctionNode) and node.func == Op.HasParticleEffect:
            return int(self.run(node.args[0]) >= 0)
        if isinstance(node, FunctionNode) and node.func in (Op.SpawnParticleEffect, Op.DestroyParticleEffect):
            args = [self.run(arg) for arg in node.args]
            if node.func == Op.SpawnParticleEffect:
                self.spawned += 1
                self.effects.append((self.spawned, args[0]))
                return self.spawned
            self.destroyed.append(args[0])
            return 0
        return super().run(node)


class ReferencePool:
    def __init__(self):
        self.entries = []
        self.serial = 0
        self.entry_serial = 0
        self.handle = 0
        self.destroyed = []

    def remove(self, index):
        self.destroyed.append(self.entries[index][1])
        self.entries[index] = self.entries[-1]
        self.entries.pop()

    def begin(self, particle_id, group, kind):
        chunk = particle_id * manager.PARTICLE_ID_STRIDE + group
        if kind != manager.ParticleManageKind.REST:
            for index in range(len(self.entries) - 1, -1, -1):
                if self.entries[index][3] == chunk:
                    self.remove(index)
        self.serial += 1
        return chunk

    def emit(self, particle_id, kind, slot, chunk):
        if kind == manager.ParticleManageKind.REST:
            key = chunk
        elif kind == manager.ParticleManageKind.LANE:
            key = particle_id * manager.PARTICLE_ID_STRIDE + slot * 2 + manager.SLOT_OFFSET
        else:
            self.entry_serial += 1
            key = -self.entry_serial
        index = -1
        if kind != manager.ParticleManageKind.MULTI:
            index = next((i for i, entry in enumerate(self.entries) if entry[0] == key), -1)
        if index >= 0:
            self.destroyed.append(self.entries[index][1])
        elif len(self.entries) == 256:
            # Prefer older effects of this kind, never the batch being emitted
            # while older effects of other kinds can make room.
            eligible = [i for i, entry in enumerate(self.entries) if entry[2] == particle_id and entry[4] < self.serial]
            if not eligible:
                eligible = list(range(len(self.entries)))
            victim = min(eligible, key=lambda i: (self.entries[i][4], i))
            self.remove(victim)
        self.handle += 1
        entry = (key, self.handle, particle_id, chunk, self.serial)
        if index >= 0:
            self.entries[index] = entry
        else:
            self.entries.append(entry)


class ParticleManagementTests(unittest.TestCase):
    def setUp(self):
        self.context = simulation_context()
        self.context.__enter__()
        self.spawned = 0
        self.destroyed = []
        self.spawn_patch = patch("sonolus.script.particle._spawn_particle_effect", side_effect=self.spawn)
        self.destroy_patch = patch("sonolus.script.particle._destroy_particle_effect", side_effect=self.destroyed.append)
        self.spawn_patch.start()
        self.destroy_patch.start()
        self.reference = ReferencePool()

    def tearDown(self):
        self.destroy_patch.stop()
        self.spawn_patch.stop()
        self.context.__exit__(None, None, None)

    def spawn(self, *args):
        self.spawned += 1
        return self.spawned

    def assert_pool(self):
        entries = manager.ParticleHandler.entries
        actual = [(e.key, e.particle.id, e.particle_id, e.chunk_key, e.chunk_serial) for e in entries]
        assert actual == self.reference.entries
        assert self.destroyed == self.reference.destroyed
        assert len(entries) <= 256
        for index, entry in enumerate(entries):
            assert manager._find_entry_index(entry.key) == index
        for bucket in range(manager.PARTICLE_INDEX_BUCKETS):
            ref = manager.ParticleHandler.particle_heads[bucket]
            previous = 0
            seen = []
            while ref > 0:
                assert ref not in seen
                seen.append(ref)
                entry = entries[ref - 1]
                assert manager._bucket(entry.particle_id) == bucket
                assert entry.older == previous
                previous, ref = ref, entry.newer
            assert manager.ParticleHandler.particle_tails[bucket] == previous
            assert len(seen) == sum(manager._bucket(e.particle_id) == bucket for e in entries)

    def batch(self, particle_id, group, kind, slots):
        particle = Particle(particle_id)
        expected_chunk = self.reference.begin(particle_id, group, kind)
        chunk = manager.begin_particle_chunk(particle, group, kind)
        assert chunk == expected_chunk
        for slot in slots:
            self.reference.emit(particle_id, kind, slot, chunk)
            manager.emit_particle(particle, +Quad, 0.01, kind, slot, chunk, True)

    def test_collision_replacement_purge_and_swaps_match_the_previous_rules(self):
        rng = random.Random(602)
        kinds = list(manager.ParticleManageKind)
        for batch in range(700):
            # Repeated groups, hash collisions, equal-age batches, and lane-key replacements.
            self.batch(rng.choice((1, 2, 3, 32, 33, 34, 63)), rng.choice((1, 7, 32, 63, rng.randrange(2000))),
                       rng.choice(kinds), [rng.randrange(-6, 7) for _ in range(rng.randrange(1, 9))])
            if batch % 13 == 0:
                self.assert_pool()
        self.assert_pool()

    def test_full_rest_and_new_kind_pools_remain_bounded(self):
        for group in range(256):
            self.batch(1, group, manager.ParticleManageKind.REST, [0])
        self.assert_pool()
        self.batch(1, 1000, manager.ParticleManageKind.REST, [0])
        self.batch(2, 1000, manager.ParticleManageKind.MULTI, range(6))
        self.assert_pool()

    def test_full_pool_keeps_all_twelve_new_effects(self):
        for previous_count in (0, 5, 12):
            with self.subTest(previous_count=previous_count):
                manager.clear_particles()
                self.reference = ReferencePool()
                self.reference.handle = self.spawned
                self.destroyed.clear()
                self.batch(1, 1, manager.ParticleManageKind.MULTI, range(256 - previous_count))
                if previous_count:
                    self.batch(2, 2, manager.ParticleManageKind.MULTI, range(previous_count))
                first_handle = self.spawned + 1
                self.batch(2, 3, manager.ParticleManageKind.MULTI, range(12))
                survivors = {e.particle.id for e in manager.ParticleHandler.entries}
                assert set(range(first_handle, first_handle + 12)) <= survivors
                self.assert_pool()

    def test_entries_persist_until_replaced_or_cleared_regardless_of_duration(self):
        self.batch(1, 1, manager.ParticleManageKind.MULTI, range(6))
        assert len(manager.ParticleHandler.entries) == 6
        assert not self.destroyed
        manager.clear_particles()
        assert self.destroyed == list(range(1, 7))
        self.reference = ReferencePool()
        self.reference.handle = self.spawned
        self.destroyed.clear()
        self.batch(1, 1, manager.ParticleManageKind.MULTI, range(6))
        self.assert_pool()


class CompiledParticleManagementTests(unittest.TestCase):
    def test_compiled_twelve_lane_critical_flick_keeps_every_effect(self):
        with patch("sekai.lib.note.get_note_particles", critical_particles):
            packaged = package_engine(EngineData(play=PlayMode(
                archetypes=[CompiledParticleProbe, CompiledCriticalFlickProbe]
            )))
        payload = cast(dict[str, Any], unpackage_data(packaged.play_data))
        nodes = []
        for node in payload["nodes"]:
            nodes.append(node["value"] if "value" in node else
                         FunctionNode(Op(node["func"]), tuple(nodes[i] for i in node["args"])))
        rom = gzip.decompress(packaged.rom)
        fill, flick = payload["archetypes"]
        for initial_count in (0, 256):
            with self.subTest(initial_count=initial_count):
                runner = ParticleInterpreter()
                runner.blocks = {block: [0.0] * 8192 for block in PlayBlock}
                runner.blocks[PlayBlock.EngineRom] = list(struct.unpack(f"<{len(rom) // 4}f", rom))
                runner.blocks[PlayBlock.RuntimeEnvironment][:3] = [16 / 9, 0, 0]
                for field in vars(type(Options)).values():
                    if hasattr(field, "info") and hasattr(field, "index"):
                        runner.set(PlayBlock.LevelOption, field.index, field.info.default)
                runner.run(nodes[flick["preprocess"]["index"]])
                values = {"particle_id": 1, "group_id": 1, "manage_kind": manager.ParticleManageKind.MULTI,
                          "count": initial_count}
                for field in fill["imports"]:
                    runner.set(PlayBlock.EntityData, field["index"], values[field["name"]])
                runner.blocks[PlayBlock.TemporaryMemory] = [0.0] * 8192
                runner.run(nodes[fill["updateSequential"]["index"]])
                runner.blocks[PlayBlock.TemporaryMemory] = [0.0] * 8192
                runner.run(nodes[flick["updateSequential"]["index"]])
                emitted = [(handle, kind) for handle, kind in runner.effects if handle > initial_count]
                assert {kind: sum(k == kind for _, k in emitted) for kind in range(2, 7)} == {
                    2: 1, 3: 1, 4: 1, 5: 12, 6: 12,
                }
                assert not {handle for handle, _ in emitted}.intersection(runner.destroyed)
                assert len(runner.destroyed) == (27 if initial_count else 0)

    def test_compiled_collisions_eviction_and_capacity_match_the_reference(self):
        packaged = package_engine(EngineData(play=PlayMode(archetypes=[CompiledParticleProbe])))
        payload = cast(dict[str, Any], unpackage_data(packaged.play_data))
        nodes = []
        for node in payload["nodes"]:
            nodes.append(node["value"] if "value" in node else
                         FunctionNode(Op(node["func"]), tuple(nodes[i] for i in node["args"])))
        runner = ParticleInterpreter()
        runner.blocks = {block: [0.0] * 8192 for block in PlayBlock}
        rom = gzip.decompress(packaged.rom)
        runner.blocks[PlayBlock.EngineRom] = list(struct.unpack(f"<{len(rom) // 4}f", rom))
        archetype = payload["archetypes"][0]
        fields = {field["name"]: field["index"] for field in archetype["imports"]}
        runner.run(nodes[archetype["preprocess"]["index"]])
        reference = ReferencePool()
        rng = random.Random(307)
        for batch in range(320):
            particle_id = rng.choice((1, 2, 32, 33, 63))
            kind = rng.choice(list(manager.ParticleManageKind))
            group = rng.choice((1, 32, 63, batch))
            count = rng.randrange(1, 9)
            chunk = reference.begin(particle_id, group, kind)
            for slot in range(count):
                reference.emit(particle_id, kind, slot, chunk)
            for name, value in (("particle_id", particle_id), ("group_id", group),
                                ("manage_kind", kind), ("count", count)):
                runner.set(PlayBlock.EntityData, fields[name], value)
            runner.blocks[PlayBlock.TemporaryMemory] = [0.0] * 8192
            runner.run(nodes[archetype["updateSequential"]["index"]])
            expected = sum((i + 1) * (e[0] + e[1] * 3 + e[2] * 5 + e[3] * 7 + e[4] * 11)
                           for i, e in enumerate(reference.entries))
            assert runner.get(PlayBlock.EntityMemory, CompiledParticleProbe._memory_fields_["snapshot"].offset) == expected
            assert runner.get(PlayBlock.EntityMemory, CompiledParticleProbe._memory_fields_["entry_count"].offset) == len(reference.entries)
            assert runner.destroyed == reference.destroyed


if __name__ == "__main__":
    unittest.main()
