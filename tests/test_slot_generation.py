import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.debug import simulation_context
from sonolus.script.sprite import Sprite

from sekai.lib import note as notes
from sekai.lib import skin
from sekai.lib import slot_effect as slots
from sekai.lib.layout import FlickDirection, NoteStageParams


class HiddenNoteEffectTests(unittest.TestCase):
    def test_hidden_notes_skip_visual_family_lookup(self):
        with (
            simulation_context(),
            patch.object(notes, "Options", SimpleNamespace(slot_effect_enabled=True)),
            patch.object(notes, "is_tutorial", return_value=False),
            patch.object(notes, "get_note_visual_family", side_effect=AssertionError("hidden visual family")),
        ):
            for kind in (notes.NoteKind.HIDE_TICK, notes.NoteKind.HIDE_DAMAGE_TICK, notes.NoteKind.ANCHOR):
                with self.subTest(kind=kind):
                    notes.schedule_note_slot_effects(kind, 0, 2, 1, FlickDirection.UP_OMNI, stage=+NoteStageParams)
                    notes.handle_note_particles(
                        kind, notes.NoteEffectKind.NONE, 0, 2, FlickDirection.UP_OMNI, notes.Judgment.PERFECT
                    )


class SlotGenerationIndexTests(unittest.TestCase):
    def test_all_note_slot_bindings_have_dense_indices(self):
        supported = set(slots._SLOT_SPRITE_IDS)
        for name in dir(skin.BaseSkin):
            if name.startswith("slot_") and "slider_hold" not in name:
                sprite = getattr(skin.BaseSkin, name)
                if isinstance(sprite, Sprite):
                    assert sprite.id in supported
        for row in skin._STYLE_NOTES:
            for note in row:
                for sprite in (note.slot, note.slot_glow.perfect, note.slot_glow.great, note.slot_glow.good):
                    if sprite.id >= 0:
                        assert sprite.id in supported
        assert len(supported) == slots.SLOT_KIND_COUNT
        assert 3 * slots.SLOT_KIND_COUNT + 1 < 769

    def test_generations_match_the_original_map_including_clears_and_group_zero(self):
        rng = random.Random(215)
        with simulation_context():
            slots.clear_slot_effects()
            reference = {}
            history = []
            for step in range(2000):
                if step % 53 == 0:
                    slots.clear_slot_effects()
                    reference.clear()
                sprite = Sprite(rng.choice(slots._SLOT_SPRITE_IDS))
                group = rng.choice((0, 0, 1, 2, 3, 100000))
                previous = reference.get(sprite.id)
                generation = 0 if previous is None else previous[0] + (previous[1] != group)
                reference[sprite.id] = (generation, group)
                assert slots.next_slot_generation(sprite, group) == generation
                history.append((sprite, generation))
                for old_sprite, old_generation in rng.sample(history, min(8, len(history))):
                    entry = reference.get(old_sprite.id)
                    expected = entry is not None and entry[0] - old_generation < 12
                    assert slots.is_slot_generation_visible(old_sprite, old_generation) == expected

    def test_only_the_thirteenth_lane_retires_the_first(self):
        with simulation_context():
            slots.clear_slot_effects()
            for sprite_id in slots._SLOT_SPRITE_IDS:
                sprite = Sprite(sprite_id)
                first = slots.next_slot_generation(sprite, 0)
                assert slots.next_slot_generation(sprite, 0) == first
                for group in range(1, 12):
                    slots.next_slot_generation(sprite, group)
                    assert slots.is_slot_generation_visible(sprite, first)
                slots.next_slot_generation(sprite, 12)
                assert not slots.is_slot_generation_visible(sprite, first)


class AuraSlotPoolTests(unittest.TestCase):
    def test_wide_notes_partially_recycle_slots_and_share_glow_generation(self):
        with simulation_context():
            sprite, glow = Sprite(slots._SLOT_SPRITE_IDS[0]), Sprite(slots._SLOT_SPRITE_IDS[1])
            slots.clear_slot_effects()
            first = slots.next_slot_generation(sprite, 1, 8, 0)
            assert slots.next_slot_generation(glow, 1, 8, 0) == first
            slots.next_slot_generation(sprite, 2, 8, 0)
            assert [slots.is_slot_generation_visible(sprite, first + i, 0) for i in range(8)] == [False] * 4 + [
                True
            ] * 4
            slots.next_slot_generation(sprite, 3, 20, 1)
            assert slots.is_slot_generation_visible(sprite, first + 7, 0)


class ExpandedAuraSlotTests(unittest.TestCase):
    def test_twenty_four_lane_stage_keeps_all_slots_and_glows(self):
        with simulation_context():
            sprite = Sprite(slots._SLOT_SPRITE_IDS[0])
            glow = Sprite(slots._SLOT_SPRITE_IDS[1])
            slots.clear_slot_effects()
            pool = 13 * 24
            first = slots.next_slot_generation(sprite, 1, 24, pool)
            assert slots.next_slot_generation(glow, 1, 24, pool) == first
            assert all(slots.is_slot_generation_visible(sprite, first + i, pool) for i in range(24))
            slots.next_slot_generation(sprite, 2, 1, 13 * 12)
            assert not slots.is_slot_generation_visible(sprite, first, pool)
            assert all(slots.is_slot_generation_visible(glow, first + i, pool) for i in range(1, 24))
