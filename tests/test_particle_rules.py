"""Sekai's per-prefab ring pools and per-lane restart behavior."""

import unittest
from unittest.mock import patch

from sonolus.script.bucket import Judgment
from sonolus.script.debug import simulation_context
from sonolus.script.particle import Particle
from sonolus.script.quad import Quad

from sekai.lib import particle_manager as manager
from sekai.lib.note_style import NoteVisualFamily as Family


class ParticleRuleTests(unittest.TestCase):
    def setUp(self):
        self.context = simulation_context()
        self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.spawned = 0
        self.destroyed = []
        self.pages = []
        for patcher in (
            patch("sonolus.script.particle._spawn_particle_effect", side_effect=self.spawn),
            patch("sonolus.script.particle._destroy_particle_effect", side_effect=self.destroyed.append),
            patch.object(manager, "time", return_value=0),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def spawn(self, *args):
        self.spawned += 1
        return self.spawned

    def emit(self, pool, lanes, aura_limit=12):
        particle = Particle(4)
        lanes = list(lanes)
        for start in range(0, len(lanes), manager.PARTICLE_PAGE_SIZE):
            page = +manager.ParticlePage
            self.pages.append(page)
            for lane in lanes[start : start + manager.PARTICLE_PAGE_SIZE]:
                manager.emit_particle(particle, +Quad, 1, pool, lane, True, page, aura_limit=aura_limit)
        for page in self.pages:
            manager.update_particle_page(page)

    def test_aura_counts_lanes_and_replaces_only_the_oldest_members(self):
        self.emit(manager.note_particle_pool(0, 0), range(8))
        self.emit(manager.note_particle_pool(0, 0), range(8))
        assert self.destroyed == [1, 2, 3, 4]
        assert self.spawned == 16

    def test_wide_stage_grows_aura_without_changing_gen_limit(self):
        pool = manager.note_particle_pool(0, 0)
        self.emit(pool, range(24), aura_limit=24)
        assert not self.destroyed
        self.emit(pool, [0], aura_limit=12)
        assert self.destroyed == [1]
        self.emit(manager.note_particle_pool(0, 1), range(7), aura_limit=24)
        assert self.destroyed == [1, 26]

    def test_gen_keeps_six_but_flash_and_connection_keep_five(self):
        for family, component, limit in ((0, 1, 6), (6, 2, 5), (10, 3, 5), (8, 3, 12)):
            pool = manager.note_particle_pool(family, component)
            before = len(self.destroyed)
            first = self.spawned + 1
            for _ in range(limit):
                self.emit(pool, [0])
            assert len(self.destroyed) == before
            self.emit(pool, [0])
            assert self.destroyed[-1] == first

    def test_disjoint_lanes_have_no_six_note_cap_and_overlap_restarts_only_its_lane(self):
        pool = manager.note_particle_pool(7, 5)
        for lane in range(12):
            self.emit(pool, [lane + 0.5])
        assert not self.destroyed
        self.emit(pool, [3.5, 4.5])
        assert self.destroyed == [4, 5]
        # Normal and critical flick lane prefabs are independent, even with the same fallback resource.
        self.emit(manager.note_particle_pool(6, 5), [3.5, 4.5])
        assert self.destroyed == [4, 5]

    def test_normal_and_slide_share_lanes_but_have_separate_aura_and_gen_pools(self):
        assert manager.note_particle_pool(0, 5) == manager.note_particle_pool(4, 5)
        assert manager.note_particle_pool(3, 5) == manager.note_particle_pool(5, 5)
        assert manager.note_particle_pool(0, 0) != manager.note_particle_pool(4, 0)
        assert manager.note_particle_pool(0, 1) != manager.note_particle_pool(4, 1)
        for judgment, expected in ((Judgment.PERFECT, 0), (Judgment.GREAT, 1), (Judgment.GOOD, 2)):
            assert manager.note_effect_pool_family(Family.NORMAL_NOTE, judgment) == expected
            assert manager.note_effect_pool_family(Family.FLICK_NOTE, judgment) == 6

    def test_hold_reserves_ten_pairs_per_type_without_stealing_or_retrying(self):
        normal = [manager.reserve_hold_particles(owner, False) for owner in range(10)]
        critical = [manager.reserve_hold_particles(owner + 10, True) for owner in range(10)]
        assert normal == list(range(1, 11))
        assert critical == list(range(11, 21))
        assert manager.reserve_hold_particles(20, False) == 0
        manager.release_hold_particles(normal[0], 99)
        assert manager.reserve_hold_particles(20, False) == 0
        manager.release_hold_particles(normal[0], 0)
        assert manager.reserve_hold_particles(21, False) == 1

    def test_empty_lane_restarts_only_the_matching_lane(self):
        for lane in (0.5, 1.5, 0.5):
            manager.emit_empty_lane_particle(Particle(4), +Quad, 1, lane)
        assert self.destroyed == [1]

    def test_seek_invalidates_pages_and_finished_handles_are_not_destroyed(self):
        self.emit(manager.note_particle_pool(0, 0), range(12))
        manager.clear_particles()
        self.emit(manager.note_particle_pool(0, 0), range(12))
        assert self.destroyed == list(range(1, 13))
        with patch.object(manager, "time", return_value=2):
            for page in self.pages:
                manager.update_particle_page(page)
        assert self.destroyed == list(range(1, 13))
        assert manager.ParticlePage._size_() <= 24


if __name__ == "__main__":
    unittest.main()
