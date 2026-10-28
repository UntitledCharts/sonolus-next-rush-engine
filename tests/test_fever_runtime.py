"""Compile and execute fever pairing and the sorted note sweep in the Sonolus VM."""

from __future__ import annotations

import gzip
import random
import struct
import unittest

from sonolus.backend.blocks import PlayBlock
from sonolus.backend.interpret import Interpreter
from sonolus.backend.node import FunctionNode
from sonolus.backend.ops import Op
from sonolus.build.engine import package_engine, unpackage_data
from sonolus.script.archetype import EntityRef, PlayArchetype, entity_data, imported, shared_memory
from sonolus.script.engine import EngineData, PlayMode

from sekai.lib.fever import FeverWindows, advance_fever_window, prepare_fever_windows


class VMFeverChance(PlayArchetype):
    start_time: float = imported()
    end_time: float = entity_data()
    next_ref: EntityRef[VMFeverChance] = entity_data()
    counter: int = entity_data()


class VMFeverStart(PlayArchetype):
    start_time: float = imported()
    next_ref: EntityRef[VMFeverStart] = entity_data()
    chance_index: int = entity_data()


class VMFeverNote(PlayArchetype):
    target_time: float = imported()
    fever_index: int = shared_memory()


class VMFeverProbe(PlayArchetype):
    note_count: int = imported()
    window_count: int = imported()

    def preprocess(self):
        FeverWindows.chance_head = 0
        FeverWindows.start_head = 0
        for i in range(self.window_count):
            index = self.note_count + i + 1
            chance = VMFeverChance.at(index)
            chance.next_ref.index = FeverWindows.chance_head
            FeverWindows.chance_head = index
            index += self.window_count
            start = VMFeverStart.at(index)
            start.next_ref.index = FeverWindows.start_head
            FeverWindows.start_head = index
        prepare_fever_windows(VMFeverChance, VMFeverStart)
        cursor = FeverWindows.chance_head
        for i in range(1, self.note_count + 1):
            n = VMFeverNote.at(i)
            cursor = advance_fever_window(VMFeverChance, cursor, n.target_time)
            if cursor > 0 and VMFeverChance.at(cursor).start_time <= n.target_time:
                n.fever_index = cursor
                VMFeverChance.at(cursor).counter += 1


class FeverInterpreter(Interpreter):
    def __init__(self):
        super().__init__()
        self.operations = 0

    def run(self, node):
        if isinstance(node, FunctionNode):
            self.operations += 1
        return super().run(node)


class CompiledFeverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        packaged = package_engine(
            EngineData(
                play=PlayMode(
                    archetypes=[VMFeverProbe, VMFeverNote, VMFeverChance, VMFeverStart],
                )
            )
        )
        cls.payload = unpackage_data(packaged.play_data)
        cls.nodes = []
        for n in cls.payload["nodes"]:
            cls.nodes.append(
                n["value"] if "value" in n else FunctionNode(Op(n["func"]), tuple(cls.nodes[i] for i in n["args"]))
            )
        rom = gzip.decompress(packaged.rom)
        cls.rom = list(struct.unpack(f"<{len(rom) // 4}f", rom))

    def execute(self, chances, starts, times):
        n, f = len(times), len(chances)
        assert f == len(starts)
        r = FeverInterpreter()
        r.blocks = {block: [0.0] * 65536 for block in PlayBlock}
        r.blocks[PlayBlock.EngineRom] = self.rom.copy()
        data_stride = self.payload["entityDataLength"]
        shared_stride = self.payload["entitySharedMemoryLength"]
        for name, value in (("note_count", n), ("window_count", f)):
            r.set(PlayBlock.EntityData, VMFeverProbe._imported_fields_[name].offset, value)
        for _cls, values, first, archetype in (
            (VMFeverNote, times, 1, 1),
            (VMFeverChance, chances, n + 1, 2),
            (VMFeverStart, starts, n + f + 1, 3),
        ):
            for i, value in enumerate(values, first):
                r.set(PlayBlock.EntityInfoArray, i * 3, i)
                r.set(PlayBlock.EntityInfoArray, i * 3 + 1, archetype)
                r.set(PlayBlock.EntityDataArray, i * data_stride, value)
        r.run(self.nodes[self.payload["archetypes"][0]["preprocess"]["index"]])
        assignments = [
            int(
                r.get(
                    PlayBlock.EntitySharedMemoryArray,
                    i * shared_stride + VMFeverNote._shared_memory_fields_["fever_index"].offset,
                )
            )
            for i in range(1, n + 1)
        ]
        windows = []
        for i, start in enumerate(chances, n + 1):
            fields = VMFeverChance._data_fields_
            windows.append(
                (
                    start,
                    r.get(PlayBlock.EntityDataArray, i * data_stride + fields["end_time"].offset),
                    r.get(PlayBlock.EntityDataArray, i * data_stride + fields["counter"].offset),
                )
            )
        return assignments, windows, r.operations

    def test_compiled_pairing_and_counts_match_original_time_ranges(self):
        rng = random.Random(115)
        for count in (0, 1, 8, 64):
            chances = [i * 4 - 1 for i in range(count)]
            starts = [i + 2 for i in chances]
            pairs = dict(zip(chances, starts, strict=True))
            rng.shuffle(chances)
            rng.shuffle(starts)
            times = sorted(rng.randrange(-8, max(1, count) * 16 + 4) / 4 for _ in range(max(1, count) * 8))
            assignments, windows, _ = self.execute(chances, starts, times)
            for a, b, n in windows:
                assert b == pairs[a]
                assert n == sum(a <= t < b for t in times)
            expected = [
                next((len(times) + i + 1 for i, a in enumerate(chances) if a <= t < pairs[a]), 0) for t in times
            ]
            assert assignments == expected

    def test_touching_periods_and_duplicate_notes_keep_half_open_boundaries(self):
        times = [-1, 0, 0, 0.5, 1, 1, 1.5, 2]
        assignments, windows, _ = self.execute([1, 0], [2, 1], times)
        assert assignments == [0, 10, 10, 10, 9, 9, 9, 0]
        assert windows == [(1, 2, 3), (0, 1, 3)]


if __name__ == "__main__":
    unittest.main()
