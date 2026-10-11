"""Projected polynomial connectors stay within their screen-space chord budget."""

import gzip
import math
import random
import struct
import unittest
from typing import Any, cast

from sonolus.backend.blocks import PlayBlock
from sonolus.backend.interpret import Interpreter
from sonolus.backend.node import FunctionNode
from sonolus.backend.ops import Op
from sonolus.build.engine import package_engine, unpackage_data
from sonolus.script.archetype import PlayArchetype, imported
from sonolus.script.debug import simulation_context
from sonolus.script.engine import EngineData, PlayMode
from sonolus.script.sprite import Sprite

from sekai.lib import connector
from sekai.lib.ease import EaseType
from sekai.lib.layer import ZIndexes
from sekai.lib.layout import APPROACH_SCALE, DynamicLayout, StageScreenTransform, StageTransform
from sekai.lib.options import Options


def polynomial(ease_type, value):
    if ease_type == EaseType.IN_QUAD:
        return value * value
    if ease_type == EaseType.OUT_QUAD:
        return value * (2 - value)
    return value


def projected_curve(ease_type, start, end, head, denominator, first, rate, direction, translation):
    def at(t):
        travel = first * math.exp(rate * t)
        interp = (polynomial(ease_type, start + (end - start) * t) - polynomial(ease_type, head)) / denominator
        return tuple(interp * (travel * d + tr) for d, tr in zip(direction, translation, strict=True)), travel

    return at


class ConnectorChordErrorTests(unittest.TestCase):
    def test_rom_bounds_cover_the_green_function_after_f32_rounding(self):
        rng = random.Random(381)
        for rate in [0, 1e-8, 0.05, 12, 64] + [rng.uniform(0.001, 64) for _ in range(500)]:
            bound = connector.EXPONENTIAL_CHORD_BOUNDS[min(192, math.floor(rate * 16))]
            bound = struct.unpack("f", struct.pack("f", bound))[0]
            for i in range(1, 100):
                t = i / 100
                value = t * (1 - t) / 2 if rate < 1e-6 else (
                    t - math.expm1(rate * t) / math.expm1(rate)
                ) / rate
                assert value <= bound + 1e-12, (rate, t, value, bound)

    def test_dense_projected_edges_include_partial_reverse_and_translated_spans(self):
        rng = random.Random(910)
        with simulation_context():
            DynamicLayout.w_scale = 1
            for case in range(500):
                ease_type = rng.choice((EaseType.LINEAR, EaseType.IN_QUAD, EaseType.OUT_QUAD))
                start, end = sorted((rng.uniform(0, 0.45), rng.uniform(0.55, 1)))
                if case % 2:
                    start, end = end, start
                head, tail = (0, 1) if case % 3 else (0.03, 0.98)
                denominator = polynomial(ease_type, tail) - polynomial(ease_type, head)
                rate = rng.choice((-1, 1)) * 10 ** rng.uniform(-5, 1)
                first = rng.uniform(0.01, 1) * math.exp(-max(0, rate))
                last = first * math.exp(rate)
                quality = rng.choice((0.25, 0.5, 1, 2, 4))
                # A constant stage/camera mapping sends the horizontal basis here.
                direction = (rng.uniform(-3, 3), rng.uniform(-3, 3))
                translation = (rng.uniform(-1, 1), rng.uniform(-1, 1)) if case % 4 else (0, 0)
                detail = connector.polynomial_connector_detail(
                    ease_type, polynomial(ease_type, head), polynomial(ease_type, tail),
                    start, end, math.hypot(*direction), first, last, quality, math.hypot(*translation),
                )
                count = max(1, math.ceil(detail * quality))
                tolerance = connector.CONNECTOR_CURVE_ERROR / (quality * quality)

                point = projected_curve(ease_type, start, end, head, denominator, first, rate, direction, translation)

                for segment in range(count):
                    lo, hi = segment / count, (segment + 1) / count
                    p0, d0 = point(lo)
                    p1, d1 = point(hi)
                    for sample in range(1, 17):
                        p, d = point(lo + (hi - lo) * sample / 17)
                        frac = (d - d0) / (d1 - d0)
                        error = math.hypot(*(p[i] - (p0[i] + frac * (p1[i] - p0[i])) for i in (0, 1)))
                        assert error <= tolerance + 1e-9, (case, count, error, tolerance)

    def test_zero_source_uses_a_single_segment(self):
        with simulation_context():
            DynamicLayout.w_scale = 1
            assert connector.polynomial_connector_detail(EaseType.LINEAR, 0, 1, 0, 1, 0, 0.1, 1, 1) == 0


class ProjectedConnectorProbe(PlayArchetype):
    ease_type: EaseType = imported()

    def preprocess(self):
        DynamicLayout.progress_start = 0
        DynamicLayout.progress_cutoff = 1.1
        DynamicLayout.t = 0.7
        DynamicLayout.w_scale = 0.12
        DynamicLayout.h_scale = -1.4
        DynamicLayout.stage_tilt = 1
        DynamicLayout.size_zoom = 1

    def update_parallel(self):
        transform = +StageTransform
        transform.sr = 0.2
        transform.tx = 0.1
        transform.ty = -0.1
        transform.projection @= StageScreenTransform(a00=16, a01=0.3, a02=0, a10=0, a11=0.5, a12=0, elevation=0)
        connector.draw_connector_default(
            kind=connector.ConnectorKind.ACTIVE_NORMAL, visual_state=connector.ConnectorVisualState.WAITING,
            segment_head_target_time=10, ease_type=self.ease_type,
            normal_sprite=Sprite(1), active_sprite=Sprite(2), z_normal=+ZIndexes, z_active=+ZIndexes,
            head_lane=-0.625, head_size=0.125, head_visual_progress=1, head_target_time=10,
            head_ease_frac=0, head_alpha=1,
            tail_lane=0.625, tail_size=0.25, tail_visual_progress=0.2, tail_target_time=11,
            tail_ease_frac=1, tail_alpha=1,
            head_transform=transform, tail_transform=transform, shared_transform=True,
        )


class DrawInterpreter(Interpreter):
    def __init__(self):
        super().__init__()
        self.draws = []

    def run(self, node):
        if isinstance(node, FunctionNode):
            if node.func == Op.Draw:
                self.draws.append([self.run(arg) for arg in node.args])
                return 0
            if node.func == Op.HasSkinSprite:
                return 1
        return super().run(node)


class CompiledConnectorChordErrorTests(unittest.TestCase):
    def test_high_quality_projection_retains_the_chord_budget_with_piece_allocation(self):
        packaged = package_engine(EngineData(play=PlayMode(archetypes=[ProjectedConnectorProbe])))
        data = cast(dict[str, Any], unpackage_data(packaged.play_data))
        nodes = []
        for node in data["nodes"]:
            nodes.append(node["value"] if "value" in node else
                         FunctionNode(Op(node["func"]), tuple(nodes[i] for i in node["args"])))
        rom = gzip.decompress(packaged.rom)
        archetype = data["archetypes"][0]
        for ease_type in (EaseType.LINEAR, EaseType.IN_QUAD, EaseType.OUT_QUAD):
            runner = DrawInterpreter()
            runner.blocks = {block: [0.0] * 8192 for block in PlayBlock}
            runner.blocks[PlayBlock.EngineRom] = list(struct.unpack(f"<{len(rom) // 4}f", rom))
            runner.blocks[PlayBlock.RuntimeEnvironment][:3] = [1.7777778, 0, 0]
            for name, field in vars(type(Options)).items():
                if hasattr(field, "info") and hasattr(field, "index"):
                    runner.set(PlayBlock.LevelOption, field.index, 4 if name == "slide_quality" else field.info.default)
            runner.set(PlayBlock.EntityData, archetype["imports"][0]["index"], ease_type)
            runner.run(nodes[archetype["preprocess"]["index"]])
            runner.run(nodes[archetype["updateParallel"]["index"]])
            assert runner.draws
            left = [(q[1:3], q[3:5]) for q in runner.draws]
            right = [(q[7:9], q[5:7]) for q in runner.draws]
            for i in range(1001):
                t = i / 1000
                interp = polynomial(ease_type, t)
                depth = APPROACH_SCALE ** (0.8 * t)
                for sign, edges in ((-1, left), (1, right)):
                    lane, size = -0.625 + 1.25 * interp, 0.125 + 0.125 * interp
                    x, y = (lane + sign * size) * depth * 0.12, depth * -1.4 + 0.7
                    x, y = 16 * x + 0.3 * y, 0.5 * y
                    point = (math.cos(0.2) * x + math.sin(0.2) * y + 0.1,
                             -math.sin(0.2) * x + math.cos(0.2) * y - 0.1)
                    error = min(distance_to_segment(point, start, end) for start, end in edges)
                    assert error <= connector.CONNECTOR_CURVE_ERROR / 16 + 1e-6, (ease_type, t, error)


def distance_to_segment(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    norm = dx * dx + dy * dy
    frac = max(0, min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / norm)) if norm else 0
    return math.hypot(point[0] - start[0] - frac * dx, point[1] - start[1] - frac * dy)


if __name__ == "__main__":
    unittest.main()
