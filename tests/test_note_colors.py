"""Color overrides preserve RUSH judgment effects and slide behavior."""

import unittest
from unittest.mock import patch

from sonolus.script.bucket import Judgment
from sonolus.script.debug import simulation_context
from sonolus.script.particle import Particle
from sonolus.script.sprite import Sprite

from sekai.lib import particle, skin
from sekai.lib.connector import ConnectorKind, get_connector_base_kind, get_connector_style
from sekai.lib.note_style import NoteStyle, NoteVisualFamily


class NoteColorTests(unittest.TestCase):
    def test_missing_color_particles_preserve_judgment_variants(self):
        with simulation_context(), patch.object(Particle, "is_available", property(lambda p: p.id >= 0)):
            particle.init_particles()
            default = +particle.ActiveParticles.normal_note
            with patch.object(Particle, "is_available", property(lambda p: False)):
                particle.init_particle_palettes()
            for style in NoteStyle:
                with self.subTest(style=style):
                    actual = particle.styled_note_particles(NoteVisualFamily.NORMAL_NOTE, style)
                    for judgment in (Judgment.PERFECT, Judgment.GREAT, Judgment.GOOD):
                        assert actual.get_circular(judgment) == default.get_circular(judgment)
                        assert actual.get_linear(judgment) == default.get_linear(judgment)
                        assert actual.get_slot_linear(judgment) == default.get_slot_linear(judgment)

    def test_color_slot_glows_fall_back_to_each_judgment(self):
        default = +skin.EMPTY_NOTE_SPRITE_SET
        default.slot_glow @= skin.SlotGlowSpriteSet(Sprite(10001), Sprite(10002), Sprite(10003))
        source = skin._style_note(NoteVisualFamily.NORMAL_NOTE, "Blue")
        with patch.object(Sprite, "is_available", property(lambda s: s.id >= 10000)):
            actual = skin._resolve_style_note(source, default)
            for judgment in (Judgment.PERFECT, Judgment.GREAT, Judgment.GOOD):
                assert actual.slot_glow.get_sprite(judgment) == default.slot_glow.get_sprite(judgment)
        with patch.object(Sprite, "is_available", property(lambda s: s.id >= 0)):
            actual = skin._resolve_style_note(source, default)
            for judgment in (Judgment.PERFECT, Judgment.GREAT, Judgment.GOOD):
                assert actual.slot_glow.get_sprite(judgment) == source.slot_glow.perfect

    def test_colored_connectors_keep_input_kind_and_color(self):
        for kind in ConnectorKind:
            if 10 < kind < 90 and kind not in {
                ConnectorKind.FAKE_ACTIVE_NORMAL,
                ConnectorKind.FAKE_ACTIVE_CRITICAL,
                ConnectorKind.FAKE_DAMAGE,
            }:
                with self.subTest(kind=kind):
                    assert get_connector_style(kind) == kind % 10
                    assert get_connector_base_kind(kind) in {
                        ConnectorKind.ACTIVE_NORMAL,
                        ConnectorKind.ACTIVE_CRITICAL,
                        ConnectorKind.DAMAGE,
                        ConnectorKind.FAKE_ACTIVE_NORMAL,
                        ConnectorKind.FAKE_ACTIVE_CRITICAL,
                        ConnectorKind.FAKE_DAMAGE,
                    }


if __name__ == "__main__":
    unittest.main()
