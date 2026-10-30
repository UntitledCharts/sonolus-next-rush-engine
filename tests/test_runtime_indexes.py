"""Execute dense slot state, event cursors and Scroll time trees in the VM."""

import bisect
import gzip
import struct
import unittest
from collections import Counter

from sonolus.backend.blocks import PlayBlock
from sonolus.backend.interpret import Interpreter
from sonolus.backend.node import FunctionNode
from sonolus.backend.ops import Op
from sonolus.build.engine import package_engine, unpackage_data
from sonolus.script.archetype import EntityRef, PlayArchetype, entity_memory, imported
from sonolus.script.array import Array
from sonolus.script.engine import EngineData, PlayMode
from sonolus.script.sprite import Sprite

from sekai.lib import baseevent as events
from sekai.lib import slot_effect as slots
from sekai.lib import timescale as ts
from sekai.lib.skin import BaseSkin
from sekai.play.timescale import TimescaleChange, TimescaleGroup

_HAS_CURSOR = hasattr(events, "query_event_list_from")
_SLOT_IDS = Array(
    *(i for i, name in enumerate(BaseSkin._sprites_) if name.startswith("Sekai Slot") and "Slider Hold" not in name)
)


class IndexedEvent(PlayArchetype, events.BaseEvent):
    time: float = imported()
    next_ref: EntityRef[IndexedEvent] = imported(name="next")


class IndexProbe(PlayArchetype):
    mode: int = imported()
    count: int = imported()
    iterations: int = imported()
    query: float = imported()
    strict: bool = imported()
    cursor: int = entity_memory()
    following: int = entity_memory()
    total: float = entity_memory()

    def preprocess(self):
        if self.mode == 0:
            slots.clear_slot_effects()
            for i in range(self.count):
                slots.next_slot_generation(Sprite(_SLOT_IDS[i]), 0)
        elif self.mode == 1:
            events.init_event_list(IndexedEvent.at(1).ref())
        else:
            ts.initialize_timescale_group(TimescaleGroup.at(1))

    def update_sequential(self):
        if self.mode == 0:
            for i in range(self.iterations):
                for k in range(self.count):
                    sprite = Sprite(_SLOT_IDS[k])
                    self.total += slots.next_slot_generation(sprite, i + 1)
                    self.total += slots.is_slot_generation_visible(sprite, 0)
        elif self.mode == 1:
            for i in range(self.iterations):
                if _HAS_CURSOR:
                    a, b = events.query_event_list_from(
                        IndexedEvent.at(1).ref(),
                        self.query + i / 100000,
                        lambda event: event.time,
                        self.cursor,
                        self.strict,
                    )
                else:
                    a, b = events.query_event_list(
                        IndexedEvent.at(1).ref(),
                        self.query + i / 100000,
                        lambda event: event.time,
                        self.strict,
                    )
                self.cursor, self.following = a.index, b.index
                self.total += a.index
        else:
            for i in range(self.iterations):
                now = self.query if self.iterations == 1 else (1.25 if i % 2 == 0 else self.count - 2.25)
                self.cursor = ts.locate_time(1, now)
                self.total += self.cursor


class CountingRunner(Interpreter):
    def __init__(self):
        super().__init__()
        self.calls = Counter()

    def run(self, node):
        if isinstance(node, FunctionNode):
            self.calls[node.func] += 1
        return super().run(node)


def compile_fixture():
    packaged = package_engine(
        EngineData(play=PlayMode(archetypes=[IndexProbe, TimescaleGroup, TimescaleChange, IndexedEvent]))
    )
    payload = unpackage_data(packaged.play_data)
    nodes = []
    for node in payload["nodes"]:
        nodes.append(
            node["value"] if "value" in node else FunctionNode(Op(node["func"]), tuple(nodes[i] for i in node["args"]))
        )
    rom = gzip.decompress(packaged.rom)
    return payload, nodes, list(struct.unpack(f"<{len(rom) // 4}f", rom))


def make_runner(compiled, mode, count, iterations=1, query=0, strict=False, duplicate_times=False, mixed=False):
    payload, nodes, rom = compiled
    runner = CountingRunner()
    runner.blocks = {block: [0.0] * 65536 for block in PlayBlock}
    runner.blocks[PlayBlock.EngineRom] = rom.copy()
    values = {"mode": mode, "count": count, "iterations": iterations, "query": query, "strict": strict}
    for field in payload["archetypes"][0]["imports"]:
        runner.set(PlayBlock.EntityData, field["index"], values[field["name"]])

    def set_data(cls, index, name, value):
        fields = cls._imported_fields_ | cls._data_fields_
        runner.set(PlayBlock.EntityDataArray, index * payload["entityDataLength"] + fields[name].offset, value)

    if mode == 1:
        for i in range(count):
            index = i + 1
            runner.set(PlayBlock.EntityInfoArray, index * 3, index)
            runner.set(PlayBlock.EntityInfoArray, index * 3 + 1, 3)
            set_data(IndexedEvent, index, "time", i // 3 if duplicate_times else i)
            set_data(IndexedEvent, index, "next_ref", index + 1 if index < count else 0)
    elif mode == 2:
        runner.set(PlayBlock.EntityInfoArray, 3, 1)
        runner.set(PlayBlock.EntityInfoArray, 4, 1)
        set_data(TimescaleGroup, 1, "first_ref", 2 if count else 0)
        for i in range(count):
            index = i + 2
            runner.set(PlayBlock.EntityInfoArray, index * 3, index)
            runner.set(PlayBlock.EntityInfoArray, index * 3 + 1, 2)
            for name, value in {
                "beat": i // 3 if duplicate_times else i,
                "timescale": (-1 if i % 3 == 0 else 1),
                "timescale_group": 1,
                "transition_style": (i % 2 if mixed else 1),
                "next_ref": index + 1 if i + 1 < count else 0,
            }.items():
                set_data(TimescaleChange, index, name, value)
    runner.run(nodes[payload["archetypes"][0]["preprocess"]["index"]])
    boot_ops = sum(runner.calls.values())
    runner.calls.clear()
    return runner, boot_ops


def invoke(compiled, runner, query=None, strict=None):
    payload, nodes, _ = compiled
    for name, value in (("query", query), ("strict", strict)):
        if value is not None:
            runner.set(PlayBlock.EntityData, IndexProbe._imported_fields_[name].offset, value)
    runner.run(nodes[payload["archetypes"][0]["updateSequential"]["index"]])
    return tuple(
        runner.get(PlayBlock.EntityMemory, IndexProbe._memory_fields_[name].offset)
        for name in ("cursor", "following", "total")
    )


class CompiledRuntimeIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = compile_fixture()

    def test_slot_generations_and_seventh_bundle_in_compiled_memory(self):
        runner, _ = make_runner(self.compiled, 0, 16, iterations=6)
        assert invoke(self.compiled, runner)[2] == 16 * 26

    def test_event_cursor_keeps_duplicates_left_limits_and_rewinds(self):
        runner, _ = make_runner(self.compiled, 1, 64, duplicate_times=True)
        times = [i // 3 for i in range(64)]
        for strict in (False, True):
            for query in (-1, 0, 0.1, 3, 10, 100, -1, 1, 4, 4):
                a, b, _ = invoke(self.compiled, runner, query, strict)
                position = bisect.bisect_left(times, query) if strict else bisect.bisect_right(times, query)
                assert (a, b) == (position, position + 1 if position < len(times) else 0)

    def test_scroll_and_mixed_groups_keep_duplicate_target_times(self):
        for mixed in (False, True):
            runner, _ = make_runner(self.compiled, 2, 64, duplicate_times=True, mixed=mixed)
            times = [i // 3 for i in range(64)]
            for query in (-1, 0, 0.1, 3, 10, 100, -1, 1, 4, 4):
                cursor, _, _ = invoke(self.compiled, runner, query)
                expected = bisect.bisect_right(times, query)
                assert cursor == (expected + 1 if expected else 0)


if __name__ == "__main__":
    unittest.main()
