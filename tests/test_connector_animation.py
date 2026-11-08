"""Sekai connector color phases under source-over blending."""

import unittest
from math import isclose
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.archetype import EntityRef, WatchArchetype
from sonolus.script.debug import simulation_context
from sonolus.script.quad import Quad
from sonolus.script.sprite import Sprite

from sekai.lib import connector, initialization
from sekai.lib.layer import ZIndexes
from sekai.lib.note import NoteKind
from sekai.lib.slot_animation import slot_appearance, slot_effect_duration, slot_glow_appearance, slot_glow_duration


class ConnectorAnimationTests(unittest.TestCase):
    def test_cosine_mixes_colors_without_adding_body_opacity(self):
        for a in (0, 0.2, 0.6, 1):
            for step in range(101):
                normal, active = connector.get_cross_fate_opacities(a, step / 200, 0.5)
                assert 0 <= normal <= 1
                assert 0 <= active <= 1
                assert isclose(normal + active, a, abs_tol=1e-12)
                # Equal texture alpha masks must never become more opaque when mixed.
                for texture_alpha in (0.1, 0.5, 1):
                    combined = normal * texture_alpha + active * texture_alpha * (1 - normal * texture_alpha)
                    assert combined <= a * texture_alpha + 1e-12
            assert connector.get_cross_fate_opacities(a, 0, 0.5) == (a, 0)
            normal, active = connector.get_cross_fate_opacities(a, 0.25, 0.5)
            assert isclose(normal, 0)
            assert isclose(active, a)
        # The cosine eases into the first eighth of the cycle.
        normal, active = connector.get_cross_fate_opacities(0.6, 0.0625, 0.5)
        mix = (1 - 2**-0.5) / 2
        assert isclose(normal, 0.6 * (1 - mix))
        assert isclose(active, 0.6 * mix)

    def test_missing_active_sprite_preserves_legacy_skin(self):
        with (
            simulation_context(),
            patch.object(connector, "Options", SimpleNamespace(connector_animation=True)),
            patch.object(connector, "time", return_value=0.125),
            patch.object(Sprite, "is_available", property(lambda s: s.id >= 0)),
            patch.object(Sprite, "draw") as draw,
        ):
            connector.draw_connector_quad(
                +Quad, connector.ConnectorVisualState.ACTIVE, Sprite(1), Sprite(-1), +ZIndexes, +ZIndexes, 0.6
            )
            assert draw.call_count == 1
            assert draw.call_args.kwargs["a"] == 0.6

    def test_guide_head_phase_crosses_separators_without_new_fields(self):
        with simulation_context():
            ref = EntityRef[WatchArchetype]
            registry = {}
            for index, previous, following in [(3, 0, 1), (1, 3, 2), (2, 1, 0)]:
                registry[index] = SimpleNamespace(
                    kind=NoteKind.ANCHOR,
                    segment_kind=connector.ConnectorKind.GUIDE_GREEN,
                    prev_ref=ref(previous),
                    next_ref=ref(following),
                    active_head_ref=ref(0),
                    ref=lambda index=index: ref(index),
                )
            registry[4] = SimpleNamespace(kind=NoteKind.NORM_TAP)
            calls = []

            class Notes:
                @staticmethod
                def _compile_time_id():
                    return 1

                @staticmethod
                def _get_mro_id_array(archetype):
                    return [archetype]

                @staticmethod
                def at(index):
                    calls.append(index)
                    return registry[index]

            with (
                patch.object(
                    initialization, "entity_info_at", side_effect=lambda i: SimpleNamespace(archetype_id=1 if i else 0)
                ),
                patch.object(EntityRef, "get", lambda r: Notes.at(r.index)),
            ):
                initialization.prepare_guide_heads(5, Notes)
            assert [registry[i].active_head_ref.index for i in (1, 2, 3)] == [3, 3, 3]
            assert len(calls) <= 2 * len(registry)

    def test_slot_curves_keep_native_attack_fade_and_per_type_duration(self):
        with simulation_context():
            height0, alpha0 = slot_glow_appearance(0)
            peak_height, peak_alpha = slot_glow_appearance(0.21)
            assert 0.48 < height0 < 0.5
            assert 0.5 < alpha0 < 0.51
            assert 0.99 < peak_height < 1.01
            assert peak_alpha > 0.98
            assert slot_glow_appearance(1)[1] == 0
            assert slot_glow_appearance(0, 6)[0] == 0  # Flick glow grows from zero.
            assert slot_glow_duration(4) == 0.4
            assert slot_glow_duration(6) == 0.35
            assert slot_effect_duration(0) == 0.48
            assert isclose(slot_appearance(0)[0], 0.39)
            assert isclose(slot_appearance(1)[0], 1.3)
