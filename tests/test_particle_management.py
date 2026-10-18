"""Run the real scheduling and keeper callbacks in the Sonolus interpreter."""

import gzip
import struct
import unittest
from collections import Counter
from typing import Any, cast
from unittest.mock import patch

from sonolus.backend.blocks import PlayBlock
from sonolus.backend.interpret import Interpreter
from sonolus.backend.node import FunctionNode
from sonolus.backend.ops import Op
from sonolus.build.engine import package_engine, unpackage_data
from sonolus.script.archetype import PlayArchetype, entity_memory, imported, shared_memory
from sonolus.script.bucket import Judgment
from sonolus.script.engine import EngineData, PlayMode
from sonolus.script.particle import Particle
from sonolus.script.quad import Quad

from sekai.lib import particle_manager as manager
from sekai.lib.layout import IDENTITY_STAGE_SCREEN_TRANSFORM, DynamicLayout, FlickDirection
from sekai.lib.note import NoteEffectKind, NoteKind, schedule_note_particles
from sekai.lib.options import Options
from sekai.lib.particle import EMPTY_NOTE_PARTICLE_SET
from sekai.play.particle_manager import ParticleManager


class CompiledParticleProbe(PlayArchetype):
    name = "NormalTapNote"
    particle_storage: manager.ParticleStorage = shared_memory()
    particle_id: int = imported()
    owner: int = imported()
    kind: manager.ParticleManageKind = imported()
    count: int = imported()
    first: int = imported()
    component: int = imported()
    page_index: int = imported()
    page: manager.ParticlePage = entity_memory()

    def preprocess(self):
        manager.clear_particles()
        DynamicLayout.t = 0.7
        DynamicLayout.w_scale = 0.12
        DynamicLayout.h_scale = -1.4
        DynamicLayout.stage_tilt = 1
        DynamicLayout.size_zoom = 1

    def update_sequential(self):
        particle = Particle(self.particle_id)
        ref = manager.begin_particle_chunk(particle, self.owner, self.kind, self.component, self.page_index)
        if self.kind == manager.ParticleManageKind.LANE:
            manager.prepare_particle_lanes(ref, particle, self.first + 0.5, self.first + self.count - 0.5)
        start = self.page_index * manager.PARTICLE_PAGE_SIZE
        for i in range(start, min(self.count, start + manager.PARTICLE_PAGE_SIZE)):
            manager.emit_particle(particle, +Quad, 1, self.kind, self.first + i + 0.5, ref, True, self.page)

    def update_parallel(self):
        if manager.update_particle_page(self.page):
            self.despawn = True


class ScheduledFlickProbe(PlayArchetype):
    owner: int = imported()
    critical: bool = imported()
    size: float = imported()

    def update_sequential(self):
        schedule_note_particles(
            NoteKind.CRIT_FLICK if self.critical else NoteKind.NORM_FLICK,
            NoteEffectKind.CRIT_FLICK if self.critical else NoteEffectKind.NORM_FLICK,
            0,
            self.size,
            0,
            FlickDirection.UP_OMNI,
            Judgment.PERFECT,
            group_id=self.owner,
            transform=IDENTITY_STAGE_SCREEN_TRANSFORM,
        )


def critical_particles(kind, direction, style):
    result = +EMPTY_NOTE_PARTICLE_SET
    result.linear = Particle(2)
    result.circular = Particle(3)
    result.directional = Particle(4)
    result.slot_linear = Particle(5)
    result.lane = Particle(7)
    return result


class ParticleInterpreter(Interpreter):
    def __init__(self):
        super().__init__()
        self.spawned = 0
        self.effects = []
        self.destroyed = []
        self.queued = []
        self.keepers = []
        self.calls = Counter()

    def run(self, node):
        if isinstance(node, FunctionNode):
            self.calls[node.func] += 1
            if node.func == Op.HasParticleEffect:
                return int(self.run(node.args[0]) >= 0)
            if node.func in (Op.SpawnParticleEffect, Op.DestroyParticleEffect, Op.Spawn):
                args = [self.run(arg) for arg in node.args]
                if node.func == Op.SpawnParticleEffect:
                    self.spawned += 1
                    self.effects.append((self.spawned, args[0]))
                    return self.spawned
                if node.func == Op.Spawn:
                    self.queued.append((int(args[0]), args[1:]))
                    return 0
                self.destroyed.append(args[0])
                return 0
        return super().run(node)


class CompiledParticleManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("sekai.lib.note.get_note_particles", critical_particles):
            packaged = package_engine(
                EngineData(play=PlayMode(archetypes=[CompiledParticleProbe, ScheduledFlickProbe, ParticleManager]))
            )
        cls.payload = cast(dict[str, Any], unpackage_data(packaged.play_data))
        cls.nodes = []
        for node in cls.payload["nodes"]:
            cls.nodes.append(
                node["value"]
                if "value" in node
                else FunctionNode(Op(node["func"]), tuple(cls.nodes[i] for i in node["args"]))
            )
        rom = gzip.decompress(packaged.rom)
        cls.rom = list(struct.unpack(f"<{len(rom) // 4}f", rom))

    def invoke(self, runner, archetype_id, callback, memory=None, values=None):
        archetype = self.payload["archetypes"][archetype_id]
        runner.blocks[PlayBlock.EntityMemory] = memory if memory is not None else [0.0] * 256
        runner.blocks[PlayBlock.EntityDespawn] = [0.0]
        runner.blocks[PlayBlock.EntityData] = [0.0] * 64
        if values:
            for field in archetype["imports"]:
                runner.set(PlayBlock.EntityData, field["index"], values[field["name"]])
        runner.blocks[PlayBlock.TemporaryMemory] = [0.0] * 16384
        runner.run(self.nodes[archetype[callback]["index"]])
        return runner.blocks[PlayBlock.EntityMemory]

    def runner(self):
        runner = ParticleInterpreter()
        runner.blocks = {block: [0.0] * 8192 for block in PlayBlock}
        runner.blocks[PlayBlock.EntitySharedMemoryArray] = [0.0] * (300 * 128)
        runner.blocks[PlayBlock.EngineRom] = self.rom
        runner.blocks[PlayBlock.RuntimeEnvironment][:3] = [16 / 9, 0, 0]
        for field in vars(type(Options)).values():
            if hasattr(field, "info") and hasattr(field, "index"):
                runner.set(PlayBlock.LevelOption, field.index, field.info.default)
        self.invoke(runner, 0, "preprocess")
        return runner

    def refresh(self, runner):
        for archetype, memory in runner.keepers:
            self.invoke(runner, archetype, "updateParallel", memory)

    def emit(self, runner, particle_id, owner, kind, count, first=0, component=0, refresh=True):
        for page_index in range((count + manager.PARTICLE_PAGE_SIZE - 1) // manager.PARTICLE_PAGE_SIZE):
            values = {
                "particle_id": particle_id,
                "owner": owner,
                "kind": kind,
                "count": count,
                "first": first,
                "component": component,
                "page_index": page_index,
            }
            memory = self.invoke(runner, 0, "updateSequential", values=values)
            runner.keepers.append((0, memory))
        if refresh:
            self.refresh(runner)

    def schedule(self, runner, owner, critical=True, size=6):
        self.invoke(runner, 1, "updateSequential", values={"owner": owner, "critical": critical, "size": size})

    def start_queued(self, runner):
        for archetype, memory in runner.queued:
            memory = memory + [0.0] * (256 - len(memory))
            self.invoke(runner, archetype, "updateSequential", memory)
            runner.keepers.append((archetype, memory))
        runner.queued.clear()
        self.refresh(runner)

    def test_compiled_six_bundles_then_seventh_removes_only_the_oldest(self):
        runner = self.runner()
        for owner in range(6):
            self.emit(runner, 5, owner, manager.ParticleManageKind.MULTI, 12)
        assert not runner.destroyed
        self.emit(runner, 5, 6, manager.ParticleManageKind.MULTI, 12)
        assert set(runner.destroyed) == set(range(1, 13))

    def test_compiled_default_group_two_arrows_both_survive(self):
        runner = self.runner()
        for _ in range(2):
            self.emit(runner, 4, 0, manager.ParticleManageKind.REST, 1, component=-1)
        assert runner.spawned == 2
        assert not runner.destroyed

    def test_compiled_wide_bundles_have_no_global_handle_capacity_eviction(self):
        runner = self.runner()
        for owner in range(10):
            self.emit(runner, 5, owner, manager.ParticleManageKind.MULTI, 256)
        assert runner.spawned == 2560
        assert set(runner.destroyed) == set(range(1, 1025))

    def test_compiled_partial_lane_replacement_and_clear(self):
        runner = self.runner()
        self.emit(runner, 7, 0, manager.ParticleManageKind.LANE, 4, -2)
        self.emit(runner, 7, 1, manager.ParticleManageKind.LANE, 2, 0)
        assert runner.destroyed == [3, 4]
        self.invoke(runner, 0, "preprocess")
        self.refresh(runner)
        assert sorted(runner.destroyed) == list(range(1, 7))
        self.emit(runner, 7, 0, manager.ParticleManageKind.LANE, 2)
        assert runner.spawned == 8

    def test_real_simultaneous_flicks_keep_both_arrows_with_an_existing_wide_bundle(self):
        runner = self.runner()
        self.emit(runner, 1, 0, manager.ParticleManageKind.MULTI, 256)
        for owner in (1, 2):
            self.schedule(runner, owner)
        self.start_queued(runner)
        assert Counter(kind for _, kind in runner.effects) == {1: 256, 2: 2, 3: 2, 4: 2, 5: 24, 7: 24}
        arrows = {handle for handle, kind in runner.effects if kind == 4}
        assert len(arrows) == 2
        assert arrows.isdisjoint(runner.destroyed)
        assert len(runner.destroyed) == 12  # Only the first critical lane bundle overlaps.

    def test_real_normal_lanes_keep_both_overlapping_bundles(self):
        runner = self.runner()
        for owner in (1, 2):
            self.schedule(runner, owner, critical=False)
        self.start_queued(runner)
        assert sum(kind == 7 for _, kind in runner.effects) == 24
        assert not runner.destroyed

    def test_real_seventh_same_frame_bundle_is_removed_before_presentation(self):
        runner = self.runner()
        for owner in range(7):
            self.schedule(runner, owner, critical=False)
        self.start_queued(runner)
        first = runner.effects[:27]
        assert {handle for handle, _ in first} == set(runner.destroyed)

    def test_compiled_interleaved_pages_do_not_revive_an_evicted_bundle(self):
        runner = self.runner()
        for owner in range(7):
            values = {
                "particle_id": 5,
                "owner": owner,
                "kind": manager.ParticleManageKind.MULTI,
                "count": 32,
                "first": 0,
                "component": 0,
                "page_index": 0,
            }
            memory = self.invoke(runner, 0, "updateSequential", values=values)
            runner.keepers.append((0, memory))
        assert runner.spawned == 7 * manager.PARTICLE_PAGE_SIZE
        values["owner"] = 0
        values["page_index"] = 1
        self.invoke(runner, 0, "updateSequential", values=values)
        assert runner.spawned == 7 * manager.PARTICLE_PAGE_SIZE
        self.refresh(runner)
        assert set(runner.destroyed) == set(range(1, manager.PARTICLE_PAGE_SIZE + 1))

    def test_real_wide_critical_flick_pages_form_one_lane_bundle(self):
        runner = self.runner()
        self.schedule(runner, 1, critical=True, size=128)
        self.start_queued(runner)
        assert sum(kind == 7 for _, kind in runner.effects) == 254
        assert not runner.destroyed

    def test_natural_expiry_releases_pages_without_destroying_finished_handles(self):
        runner = self.runner()
        self.emit(runner, 4, 0, manager.ParticleManageKind.REST, 1)
        runner.blocks[PlayBlock.RuntimeUpdate][0] = 2
        self.refresh(runner)
        assert not runner.destroyed
        offset = CompiledParticleProbe._memory_fields_["page"].offset
        assert runner.keepers[0][1][offset + manager.ParticlePage._size_() - 1] == 0


if __name__ == "__main__":
    unittest.main()
