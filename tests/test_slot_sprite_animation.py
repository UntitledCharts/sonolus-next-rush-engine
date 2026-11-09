"""Respect active Unity modules rather than unused serialized animation curves."""

import unittest
from itertools import pairwise
from math import isclose
from types import SimpleNamespace
from unittest.mock import patch

from sonolus.script.debug import simulation_context

from sekai.lib import slot_animation as animation
from sekai.lib.options import Version


class SlotSpriteAnimationTests(unittest.TestCase):
    def test_v3_slot_base_size_is_constant_for_all_profiles(self):
        with simulation_context(), patch.object(animation, "LevelConfig", SimpleNamespace(ui_version=Version.v3)):
            for pool in range(13):
                for progress in (0, 0.1, 0.25, 0.5, 0.75, 1):
                    scale, alpha = animation.slot_appearance(progress, pool)
                    assert scale == 1
                    assert 0 <= alpha <= 1

    def test_normal_base_alpha_matches_active_source_gradient(self):
        # fx_note_normal_aura/base ColorModule, quantized Unity gradient times.
        points = [(0, 1), (5714 / 65535, 1), (16860 / 65535, 0.5019608), (47194 / 65535, 0.14117648), (1, 0)]
        with simulation_context(), patch.object(animation, "LevelConfig", SimpleNamespace(ui_version=Version.v3)):
            for progress in (0, 0.05, 0.2, 0.5, 0.8, 1):
                left, right = next((a, b) for a, b in pairwise(points) if a[0] <= progress <= b[0])
                expected = left[1] + (right[1] - left[1]) * (progress - left[0]) / (right[0] - left[0])
                _, actual = animation.slot_appearance(progress, 0)
                assert isclose(actual, expected, abs_tol=0.007)
            assert animation.slot_effect_duration(0) == 0.48

    def test_v1_legacy_slot_still_fades_at_fixed_size(self):
        with simulation_context(), patch.object(animation, "LevelConfig", SimpleNamespace(ui_version=Version.v1)):
            for progress in (0, 0.5, 1):
                assert animation.slot_appearance(progress, 0) == (1, 1 - progress)
            assert animation.slot_effect_duration(0) == 0.5


if __name__ == "__main__":
    unittest.main()
