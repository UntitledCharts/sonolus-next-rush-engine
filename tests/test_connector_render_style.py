"""Prepared connector styles preserve compiled drawing across states and rewinds."""

import gzip
import struct
import unittest
from typing import Any, cast

from sonolus.backend.blocks import PlayBlock
from sonolus.backend.interpret import Interpreter
from sonolus.backend.node import FunctionNode
from sonolus.backend.ops import Op
from sonolus.build.engine import package_engine, unpackage_data
from sonolus.script.archetype import PlayArchetype, entity_memory, imported
from sonolus.script.engine import EngineData, PlayMode

from sekai.lib.connector import (
    ConnectorKind,
    ConnectorLayer,
    ConnectorRenderInfo,
    ConnectorVisualState,
    SegmentPresentation,
    draw_connector,
    get_connector_render_info,
)
from sekai.lib.ease import EaseType
from sekai.lib.layout import DynamicLayout, blend_stage_transform, identity_stage_transform
from sekai.lib.options import Options
from sekai.lib.skin import init_skin
from sekai.lib.stage import VisualMask


class RenderStyleProbe(PlayArchetype):
    kind: ConnectorKind = imported()
    layer: ConnectorLayer = imported()
    state: ConnectorVisualState = imported()
    presentation: SegmentPresentation = imported()
    ease_type: EaseType = imported()
    head_lane: float = imported()
    head_size: float = imported()
    tail_lane: float = imported()
    tail_size: float = imported()
    head_progress: float = imported()
    head_time: float = imported()
    head_frac: float = imported()
    segment_lane: float = imported()
    tail_progress: float = imported()
    duration: float = imported()
    geometry: int = imported()
    style: ConnectorRenderInfo = entity_memory()

    def preprocess(self):
        init_skin()
        DynamicLayout.progress_start = 0
        DynamicLayout.progress_cutoff = 1.1
        DynamicLayout.t = 0.7
        DynamicLayout.w_scale = 0.12
        DynamicLayout.h_scale = -1.4
        DynamicLayout.stage_tilt = 1
        DynamicLayout.size_zoom = 1
        DynamicLayout.rotate = 0
        DynamicLayout.rotate_sin = 0
        DynamicLayout.rotate_cos = 1

    def initialize(self):
        self.style = get_connector_render_info(self.kind, self.layer, 10, self.segment_lane)


def render_probe(probe, renderer, style=None):
    head = identity_stage_transform()
    tail = identity_stage_transform()
    if probe.geometry in {1, 2, 4}:
        head.sr = 0.4
        head.tx = 0.2
        head.projection.elevation = 1
        tail @= head
        if probe.geometry == 2:
            tail.sr = -0.2
            tail.ty = 0.2
        if probe.geometry == 4:
            tail.projection.a12 = 0.2
            tail.projection.elevation = 2
    mask = VisualMask(-2, 2, probe.geometry == 3, 1)

    def elevation_transform(interp_frac, elevation_frac):
        return blend_stage_transform(head, tail, elevation_frac)

    renderer(
        kind=probe.kind,
        visual_state=probe.state,
        ease_type=probe.ease_type,
        head_lane=probe.head_lane,
        head_size=probe.head_size,
        head_visual_progress=probe.head_progress,
        head_target_time=probe.head_time,
        head_ease_frac=probe.head_frac,
        tail_lane=probe.tail_lane,
        tail_size=probe.tail_size,
        tail_visual_progress=probe.tail_progress,
        tail_target_time=10 + probe.duration,
        tail_ease_frac=1,
        segment_head_target_time=10,
        segment_head_lane=probe.segment_lane,
        segment_head_alpha=0.4,
        segment_tail_target_time=10 + probe.duration,
        segment_tail_alpha=0.9,
        layer=probe.layer,
        presentation=probe.presentation,
        bypass_tail_target_time_check=True,
        head_transform=head,
        tail_transform=tail,
        head_note_alpha=1,
        tail_note_alpha=1,
        head_mask=mask,
        tail_mask=mask,
        shared_transform=probe.geometry in {0, 1, 3},
        ease_over_elevation=probe.geometry == 4,
        elevation_transform=elevation_transform,
        render_info=style,
    )


class UncachedStyleProbe(RenderStyleProbe):
    def update_parallel(self):
        render_probe(self, draw_connector)


class CachedStyleProbe(RenderStyleProbe):
    def update_parallel(self):
        render_probe(self, draw_connector, self.style)


class RenderCounter(Interpreter):
    def __init__(self, missing_sprites=False):
        super().__init__()
        self.ops = 0
        self.draws = []
        self.missing_sprites = missing_sprites

    def run(self, node):
        if isinstance(node, FunctionNode):
            self.ops += 1
            if node.func == Op.Draw:
                self.draws.append([self.run(arg) for arg in node.args])
                return 0
            if node.func == Op.HasSkinSprite:
                sprite_id = self.run(node.args[0])
                return int(sprite_id >= 0 and (not self.missing_sprites or sprite_id % 3 == 0))
        return super().run(node)


def load_probe(archetypes):
    packaged = package_engine(EngineData(play=PlayMode(archetypes=archetypes)))
    payload = cast(dict[str, Any], unpackage_data(packaged.play_data))
    nodes = []
    for node in payload["nodes"]:
        nodes.append(
            node["value"] if "value" in node else FunctionNode(Op(node["func"]), tuple(nodes[i] for i in node["args"]))
        )
    raw_rom = gzip.decompress(packaged.rom)
    rom = list(struct.unpack(f"<{len(raw_rom) // 4}f", raw_rom))
    return payload, nodes, rom


def prepare_probe(compiled, archetype_index, values, *, missing_sprites=False, options=None):
    payload, nodes, rom = compiled
    runner = RenderCounter(missing_sprites)
    runner.blocks = {block: [0.0] * 8192 for block in PlayBlock}
    runner.blocks[PlayBlock.EngineRom] = rom
    runner.blocks[PlayBlock.RuntimeEnvironment][:3] = [16 / 9, 0, 0]
    for name, field in vars(type(Options)).items():
        if hasattr(field, "info") and hasattr(field, "index"):
            runner.set(PlayBlock.LevelOption, field.index, (options or {}).get(name, field.info.default))
    archetype = payload["archetypes"][archetype_index]
    for field in archetype["imports"]:
        runner.set(PlayBlock.EntityData, field["index"], values[field["name"]])
    runner.run(nodes[archetype["preprocess"]["index"]])
    runner.set(PlayBlock.RuntimeUpdate, 0, 3)  # Prepare at a different time from every render sample.
    runner.run(nodes[archetype["initialize"]["index"]])
    return runner, nodes[archetype["updateParallel"]["index"]]


def default_probe_values(**overrides):
    return {
        "kind": ConnectorKind.ACTIVE_NORMAL,
        "layer": ConnectorLayer.TOP,
        "state": ConnectorVisualState.WAITING,
        "presentation": SegmentPresentation.DEFAULT,
        "ease_type": EaseType.IN_QUAD,
        "head_lane": -4,
        "head_size": 1,
        "tail_lane": 4,
        "tail_size": 2,
        "head_progress": 1,
        "head_time": 10,
        "head_frac": 0,
        "segment_lane": -4,
        "tail_progress": 0.2,
        "duration": 1,
        "geometry": 0,
    } | overrides


class ConnectorRenderStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = load_probe([UncachedStyleProbe, CachedStyleProbe])

    def assert_render_equal(self, values, *, missing_sprites=False, options=None):
        before, before_node = prepare_probe(self.compiled, 0, values, missing_sprites=missing_sprites, options=options)
        after, after_node = prepare_probe(self.compiled, 1, values, missing_sprites=missing_sprites, options=options)
        stored_style = after.blocks[PlayBlock.EntityMemory].copy()
        for now in (9, 10.5, 9.5, 10.75):
            for runner, node in ((before, before_node), (after, after_node)):
                runner.set(PlayBlock.RuntimeUpdate, 0, now)
                runner.draws.clear()
                runner.ops = 0
                runner.run(node)
            assert before.draws == after.draws
            assert stored_style == after.blocks[PlayBlock.EntityMemory]

    def test_all_kinds_layers_and_states_keep_sprite_and_depth_order(self):
        for index, kind in enumerate(ConnectorKind):
            with self.subTest(kind=kind):
                self.assert_render_equal(
                    default_probe_values(
                        kind=kind,
                        layer=list(ConnectorLayer)[index % len(ConnectorLayer)],
                        state=list(ConnectorVisualState)[index % len(ConnectorVisualState)],
                    )
                )

    def test_geometry_animation_options_and_missing_skin_fallbacks(self):
        for geometry in range(5):
            for presentation in SegmentPresentation:
                for missing_sprites in (False, True):
                    with self.subTest(geometry=geometry, presentation=presentation, missing_sprites=missing_sprites):
                        self.assert_render_equal(
                            default_probe_values(
                                kind=ConnectorKind.FAKE_ACTIVE_CRITICAL_BLUE,
                                geometry=geometry,
                                presentation=presentation,
                                state=ConnectorVisualState.ACTIVE,
                                ease_type=EaseType.IN_OUT_STEP if geometry == 3 else EaseType.OUT_QUAD,
                            ),
                            missing_sprites=missing_sprites,
                            options={
                                "slide_quality": 2,
                                "slide_alpha": 0.6,
                                "alternative_approach_curve": geometry == 2,
                            },
                        )

    def test_disabled_fake_notes_and_zero_alpha_still_hide_connectors(self):
        for options in ({"disable_fake_notes": True}, {"slide_alpha": 0}):
            self.assert_render_equal(default_probe_values(kind=ConnectorKind.FAKE_ACTIVE_NORMAL), options=options)

    def test_cached_style_reduces_render_work(self):
        values = default_probe_values(state=ConnectorVisualState.ACTIVE)
        before, before_node = prepare_probe(self.compiled, 0, values)
        after, after_node = prepare_probe(self.compiled, 1, values)
        for runner, node in ((before, before_node), (after, after_node)):
            runner.set(PlayBlock.RuntimeUpdate, 0, 9)
            runner.ops = 0
            runner.run(node)
        assert before.draws
        assert before.draws == after.draws
        assert after.ops < before.ops


if __name__ == "__main__":
    unittest.main()
