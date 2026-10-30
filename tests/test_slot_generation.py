import random
import unittest

from sonolus.script.debug import simulation_context
from sonolus.script.sprite import Sprite

from sekai.lib import skin
from sekai.lib import slot_effect as slots


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
                    expected = entry is None or entry[0] - old_generation < 6
                    assert slots.is_slot_generation_visible(old_sprite, old_generation) == expected

    def test_only_the_seventh_distinct_bundle_retires_the_first(self):
        with simulation_context():
            slots.clear_slot_effects()
            for sprite_id in slots._SLOT_SPRITE_IDS:
                sprite = Sprite(sprite_id)
                first = slots.next_slot_generation(sprite, 0)
                assert slots.next_slot_generation(sprite, 0) == first
                for group in range(1, 6):
                    slots.next_slot_generation(sprite, group)
                    assert slots.is_slot_generation_visible(sprite, first)
                slots.next_slot_generation(sprite, 6)
                assert not slots.is_slot_generation_visible(sprite, first)
