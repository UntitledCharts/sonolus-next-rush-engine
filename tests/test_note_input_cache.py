"""Interpret cached input windows initialized through another entity."""

import gzip
import struct
import unittest
from typing import Any, cast

from sonolus.backend.blocks import PlayBlock
from sonolus.backend.interpret import Interpreter
from sonolus.backend.node import FunctionNode
from sonolus.backend.ops import Op
from sonolus.build.engine import package_engine, unpackage_data
from sonolus.script.archetype import PlayArchetype
from sonolus.script.engine import EngineData, PlayMode

from sekai.lib.note import NoteKind
from sekai.play.note import BaseNote


class WindowNote(BaseNote):
    # Keep the real note fields and init_data, and isolate that initialization
    # from rendering, stage setup, and the rest of the level lifecycle.
    preprocess = PlayArchetype.preprocess
    spawn_order = PlayArchetype.spawn_order
    should_spawn = PlayArchetype.should_spawn
    initialize = PlayArchetype.initialize
    update_sequential = PlayArchetype.update_sequential
    touch = PlayArchetype.touch
    update_parallel = PlayArchetype.update_parallel
    terminate = PlayArchetype.terminate


CachedTap = WindowNote.derive("CachedTap", is_scored=True, key=NoteKind.NORM_TAP)
CachedTick = WindowNote.derive("CachedTick", is_scored=True, key=NoteKind.NORM_TICK)
CachedDamage = WindowNote.derive("CachedDamage", is_scored=True, key=NoteKind.HIDE_DAMAGE_TICK)


class WindowInitializer(PlayArchetype):
    def preprocess(self):
        CachedTap.at(1, check=False).init_data()
        CachedTick.at(2, check=False).init_data()
        CachedDamage.at(3, check=False).init_data()


class NoteInputCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        packaged = package_engine(
            EngineData(play=PlayMode(archetypes=[WindowInitializer, CachedTap, CachedTick, CachedDamage]))
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

    def setUp(self):
        self.interpreter = Interpreter()
        for block in PlayBlock:
            self.interpreter.blocks[block] = [0.0] * 512
        self.interpreter.blocks[PlayBlock.EngineRom] = self.rom.copy()
        for index in (1, 2, 3):
            self.interpreter.set(PlayBlock.EntityInfoArray, index * 3, index)
            self.interpreter.set(PlayBlock.EntityInfoArray, index * 3 + 1, index)
        self.interpreter.set(PlayBlock.RuntimeEnvironment, 3, 0.075)
        self.set_field(1, "beat", 3.9)
        self.set_field(2, "beat", 4)
        self.set_field(3, "beat", 4)

    def set_field(self, index, name, value, *, shared=False):
        fields = CachedTap._shared_memory_fields_ if shared else CachedTap._imported_fields_ | CachedTap._data_fields_
        length = self.payload["entitySharedMemoryLength" if shared else "entityDataLength"]
        block = PlayBlock.EntitySharedMemoryArray if shared else PlayBlock.EntityDataArray
        self.interpreter.set(block, index * length + fields[name].offset, value)

    def get_field(self, index, name, slot=0, *, shared=False):
        fields = CachedTap._shared_memory_fields_ if shared else CachedTap._imported_fields_ | CachedTap._data_fields_
        length = self.payload["entitySharedMemoryLength" if shared else "entityDataLength"]
        block = PlayBlock.EntitySharedMemoryArray if shared else PlayBlock.EntityDataArray
        return self.interpreter.get(block, index * length + fields[name].offset + slot)

    def initialize(self):
        callback = self.payload["archetypes"][0]["preprocess"]["index"]
        self.interpreter.run(self.nodes[callback])

    def test_input_offset_applies_to_both_cached_boundaries(self):
        self.initialize()
        for slot, expected in enumerate((3.9 - 7.5 / 60, 3.9 + 7.5 / 60)):
            assert abs(self.get_field(1, "unadjusted_input_interval", slot, shared=True) - expected) < 1e-12
            assert abs(self.get_field(1, "input_interval", slot, shared=True) - expected - 0.075) < 1e-12

    def test_standalone_and_connector_ticks_keep_different_windows(self):
        self.initialize()
        assert self.get_field(2, "unadjusted_input_interval", shared=True) == 4 - 5 / 60
        self.set_field(2, "data_init_done", 0)
        self.set_field(2, "active_head_ref", 1)
        self.initialize()
        assert self.get_field(2, "unadjusted_input_interval", shared=True) == 4
        assert self.get_field(2, "unadjusted_input_interval", 1, shared=True) == 4

    def test_damage_tick_start_is_clipped_to_the_slide_head(self):
        self.set_field(3, "active_head_ref", 1)
        self.initialize()
        assert self.get_field(3, "unadjusted_input_interval", shared=True) == 3.9
        assert self.get_field(3, "unadjusted_input_interval", 1, shared=True) == 4

    def test_repeat_initialization_preserves_cached_windows(self):
        self.initialize()
        self.set_field(1, "beat", 8)
        self.interpreter.set(PlayBlock.RuntimeEnvironment, 3, 0.25)
        self.initialize()
        assert self.get_field(1, "target_time") == 3.9
        assert abs(self.get_field(1, "input_interval", shared=True) - (3.9 - 7.5 / 60 + 0.075)) < 1e-12


if __name__ == "__main__":
    unittest.main()
