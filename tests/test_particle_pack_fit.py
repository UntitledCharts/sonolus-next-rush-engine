"""SCP-only coordinate correction, skin-stamp exclusion, and alias preservation."""

import copy
import math
import unittest

from tools.fit_particle_pack import billboard_transform, fit, lane_transform


def apply(transform, corners):
    return {
        output: sum(corners.get(name, 0) * weight for name, weight in expression.items())
        for output, expression in transform.items()
    }


class ParticlePackFitTests(unittest.TestCase):
    def test_billboard_keeps_anchor_size_and_rotation_without_lane_shear(self):
        for rotation in (-1.2, 0, 0.7):
            for width in (0.03, 0.2, 1.4):
                for shear in (-0.8, 0, 0.8):
                    dx = width * math.cos(rotation)
                    dy = width * math.sin(rotation)
                    corners = {
                        "x1": 0.6,
                        "y1": -0.4,
                        "x4": 0.6 + dx,
                        "y4": -0.4 + dy,
                        "x2": 0.6 - dy + shear * dx,
                        "y2": -0.4 + dx + shear * dy,
                        "x3": 0.6 + dx - dy + shear * dx,
                        "y3": -0.4 + dy + dx + shear * dy,
                    }
                    result = apply(billboard_transform(), corners)
                    assert result["x1"] == corners["x1"]
                    assert result["y4"] == corners["y4"]
                    top_x = result["x2"] - result["x1"]
                    top_y = result["y2"] - result["y1"]
                    assert math.isclose(top_x * dx + top_y * dy, 0, abs_tol=1e-12)
                    assert math.isclose(math.hypot(top_x, top_y), width, abs_tol=1e-12)

    def test_lane_reverses_existing_engine_overshoot_trim(self):
        original = {"x1": -1, "y1": -1, "x2": -0.2, "y2": 0.9, "x3": 0.2, "y3": 0.9, "x4": 1, "y4": -1}
        cropped = dict(original)
        for axis in ("x", "y"):
            for top, bottom in ((2, 1), (3, 4)):
                cropped[f"{axis}{top}"] = (original[f"{axis}{top}"] + 0.07 * original[f"{axis}{bottom}"]) / 1.07
        for name, value in apply(lane_transform(), cropped).items():
            assert math.isclose(value, original[name], abs_tol=1e-12)

    def test_skin_stamp_removed_but_sparks_circular_projection_and_fever_kept(self):
        def particle(sprite):
            return {"sprite": sprite, "start": 0, "duration": 0.1, "r": {"from": {}, "to": {}}}

        def effect(name, sprites):
            return {
                "name": name,
                "transform": {},
                "groups": [{"count": 7, "particles": [particle(i) for i in sprites]}],
            }

        center = effect("Sekai Good Normal Note Linear", [39])
        alias_center = effect("Sekai Linear Tap Cyan Good", [39])
        slot = copy.deepcopy(center)
        slot["name"] = "Sekai Good Normal Note Slot Linear"
        alias_slot = copy.deepcopy(alias_center)
        alias_slot["name"] = "Sekai Slot Linear Tap Cyan Good"
        circular = effect("Sekai Critical Flick Note Circular", [74, 47])
        sparks = effect("Sekai Critical Flick Note Slot Linear", [81, 47, 68, 69])
        fever = effect("Sekai Fever Border", [32, 33])
        data = {"effects": [center, alias_center, slot, alias_slot, circular, sparks, fever]}
        fit(data)
        assert not slot["groups"]
        assert not alias_slot["groups"]
        assert circular["transform"] == {}
        assert [p["sprite"] for p in circular["groups"][0]["particles"]] == [47]
        assert [p["sprite"] for p in sparks["groups"][0]["particles"]] == [47, 68, 69]
        assert sparks["groups"][0]["count"] == 7
        assert [p["sprite"] for p in fever["groups"][0]["particles"]] == [32, 33]


if __name__ == "__main__":
    unittest.main()
