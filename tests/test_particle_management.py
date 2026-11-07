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
from sonolus.script.archetype import PlayArchetype, entity_memory, imported
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
    particle_id: int = imported()
    owner: int = imported()
    pool_id: int = imported()
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
        start = self.page_index * manager.PARTICLE_PAGE_SIZE
        for i in range(start, min(self.count, start + manager.PARTICLE_PAGE_SIZE)):
            manager.emit_particle(particle, +Quad, 1, self.pool_id, self.first + i + 0.5, True, self.page)

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
            aura_limit=max(12, int(2 * self.size)),
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

    def emit(self, runner, pool_id, count, first=0):
        for page_index in range((count + manager.PARTICLE_PAGE_SIZE - 1) // manager.PARTICLE_PAGE_SIZE):
            values = {
                "particle_id": 4,
                "owner": 0,
                "pool_id": pool_id,
                "count": count,
                "first": first,
                "component": 0,
                "page_index": page_index,
            }
            memory = self.invoke(runner, 0, "updateSequential", values=values)
            runner.keepers.append((0, memory))
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

    def test_compiled_aura_recycles_individual_lanes_across_pages(self):
        runner = self.runner()
        self.emit(runner, manager.note_particle_pool(0, 0), 16)
        assert runner.spawned == 16
        assert runner.destroyed == [1, 2, 3, 4]

    def test_intact_page_check_cost_does_not_grow_with_member_count(self):
        costs = []
        for count in (1, 8):
            runner = self.runner()
            pool = manager.note_particle_pool(0, 0)
            self.emit(runner, pool, count)
            memory = runner.keepers[0][1]
            self.invoke(
                runner,
                0,
                "updateSequential",
                values={
                    "particle_id": 4,
                    "owner": 0,
                    "pool_id": pool,
                    "count": 1,
                    "first": 0,
                    "component": 0,
                    "page_index": 0,
                },
            )
            runner.calls.clear()
            self.invoke(runner, 0, "updateParallel", memory)
            costs.append(sum(runner.calls.values()))
            assert not runner.destroyed
        assert costs[1] <= costs[0]

    def test_compiled_lane_replacement_and_seek(self):
        runner = self.runner()
        pool = manager.note_particle_pool(7, 5)
        self.emit(runner, pool, 12, -6)
        self.emit(runner, pool, 2, 0)
        assert runner.destroyed == [7, 8]
        self.invoke(runner, 0, "preprocess")
        self.refresh(runner)
        assert sorted(runner.destroyed) == list(range(1, 15))

    def test_real_flick_emissions_use_lane_aura_center_gen_and_five_flashes(self):
        runner = self.runner()
        for owner in range(7):
            self.schedule(runner, owner, size=6)
        self.start_queued(runner)
        assert Counter(kind for _, kind in runner.effects) == {2: 84, 3: 7, 4: 7, 5: 84, 7: 84}
        remaining = Counter(kind for handle, kind in runner.effects if handle not in runner.destroyed)
        assert remaining == {2: 12, 3: 6, 4: 5, 5: 12, 7: 12}

    def test_real_twenty_four_lane_stage_does_not_clip_aura(self):
        runner = self.runner()
        self.schedule(runner, 1, size=12)
        self.start_queued(runner)
        assert Counter(kind for _, kind in runner.effects) == {2: 24, 3: 1, 4: 1, 5: 24, 7: 24}
        assert not runner.destroyed

    def test_good_gen_is_still_one_center_particle(self):
        from sonolus.script.debug import simulation_context

        from sekai.lib.note import iter_note_particle_pages
        from sekai.lib.note_style import NoteStyle

        with (
            simulation_context(),
            patch("sekai.lib.note.get_note_particles", critical_particles),
            patch.object(Particle, "is_available", property(lambda self: self.id >= 0)),
        ):
            Options.note_effect_enabled = True
            Options.lane_effect_enabled = False
            pages = list(
                iter_note_particle_pages(
                    NoteKind.NORM_TAP, FlickDirection.UP_OMNI, Judgment.GOOD, 20, True, NoteStyle.DEFAULT
                )
            )
        assert [(c, p) for c, p in pages if c == 1] == [(1, 0)]


if __name__ == "__main__":
    unittest.main()
