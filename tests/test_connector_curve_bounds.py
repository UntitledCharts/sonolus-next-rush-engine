"""Constant-time range queries retain the renderer's existing subdivision bounds."""

import unittest
from math import ceil, floor

from sekai.lib import connector
from sekai.lib.ease import EaseType


def previous_bound(ease_type, order, start, end):
    first = max(0, min(15, floor(start * 16)))
    last = max(first, min(15, ceil(end * 16) - 1))
    run, offset = 1, 0
    while run * 2 <= last - first + 1:
        offset += 16 - run + 1
        run *= 2
    base = (ease_type * 2 + order - 1) * connector.CURVE_TABLE_SIZE + offset
    return max(connector.CURVE_DERIVATIVE_BOUNDS[base + first],
               connector.CURVE_DERIVATIVE_BOUNDS[base + last - run + 1])


class ConnectorCurveBoundsTests(unittest.TestCase):
    def test_all_bins_boundaries_and_clipped_ranges_match_exactly(self):
        points = [-2, -1e-10, 0, 1, 1 + 1e-10, 2]
        points += [i / 16 + delta for i in range(17) for delta in (-1e-10, 0, 1e-10)]
        for ease_type in EaseType:
            for start in points:
                for end in points:
                    slope, curvature = connector._ease_slope_and_curvature(ease_type, start, end)
                    assert slope == previous_bound(ease_type, 1, start, end)
                    assert curvature == previous_bound(ease_type, 2, start, end)
                    assert connector.ease_derivative_bound(ease_type, 1, start, end) == slope
                    assert connector.ease_derivative_bound(ease_type, 2, start, end) == curvature


if __name__ == "__main__":
    unittest.main()
