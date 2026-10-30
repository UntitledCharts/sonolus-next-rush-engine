"""Particle limits apply to complete emissions, with critical lane overlap as an exception."""

import struct
import unittest
from unittest.mock import patch

from sonolus.script.debug import simulation_context
from sonolus.script.particle import Particle
from sonolus.script.quad import Quad

from sekai.lib import particle_manager as manager
from sekai.play.mode import play_mode
from sekai.watch.mode import watch_mode


class ParticleRuleTests(unittest.TestCase):
    def setUp(self):
        self.context = simulation_context()
        self.context.__enter__()
        self.spawned = 0
        self.destroyed = []
        self.spawn_patch = patch("sonolus.script.particle._spawn_particle_effect", side_effect=self.spawn)
        self.destroy_patch = patch(
            "sonolus.script.particle._destroy_particle_effect", side_effect=self.destroyed.append
        )
        self.spawn_patch.start()
        self.destroy_patch.start()
        self.pages = []
        self.clock = patch.object(manager, "time", return_value=0)
        self.clock.start()
        self.storage = {}
        self.storage_patch = patch.object(manager, "particle_storage", side_effect=self.owner_storage)
        self.storage_patch.start()

    def tearDown(self):
        self.clock.stop()
        self.storage_patch.stop()
        self.destroy_patch.stop()
        self.spawn_patch.stop()
        self.context.__exit__(None, None, None)

    def spawn(self, *args):
        self.spawned += 1
        return self.spawned

    def owner_storage(self, owner):
        if owner not in self.storage:
            self.storage[owner] = +manager.ParticleStorage
        return self.storage[owner]

    def test_authored_owners_share_the_same_storage_layout(self):
        for mode in (play_mode, watch_mode):
            owners = 0
            for cls in mode.archetypes:
                cls._init_fields()
                if "particle_storage" in cls._shared_memory_fields_:
                    owners += 1
                    field = cls._shared_memory_fields_["particle_storage"]
                    assert field.offset == 0
                    assert field.type is manager.ParticleStorage
            assert owners > 2

    def refresh(self):
        for page in self.pages:
            manager.update_particle_page(page)

    def emit(self, particle_id, group, kind, slots):
        particle = Particle(particle_id)
        chunk = manager.begin_particle_chunk(particle, group, kind)
        slots = list(slots)
        if kind == manager.ParticleManageKind.LANE and slots:
            manager.prepare_particle_lanes(chunk, particle, min(slots), max(slots))
        for start in range(0, len(slots), manager.PARTICLE_PAGE_SIZE):
            page = +manager.ParticlePage
            self.pages.append(page)
            for slot in slots[start : start + manager.PARTICLE_PAGE_SIZE]:
                manager.emit_particle(particle, +Quad, 1, kind, slot, chunk, True, page)
        self.refresh()

    def test_two_arrows_with_the_default_group_both_survive(self):
        for _ in range(2):
            self.emit(4, 0, manager.ParticleManageKind.REST, [0])
        assert self.spawned == 2
        assert not self.destroyed

    def test_only_the_seventh_arrow_removes_the_oldest(self):
        for group in range(6):
            self.emit(4, group, manager.ParticleManageKind.REST, [0])
        assert not self.destroyed
        self.emit(4, 6, manager.ParticleManageKind.REST, [0])
        assert self.destroyed == [1]

    def test_twelve_members_count_as_one_bundle(self):
        for group in range(6):
            self.emit(5, group, manager.ParticleManageKind.MULTI, range(12))
        assert not self.destroyed
        self.emit(5, 6, manager.ParticleManageKind.MULTI, range(12))
        assert set(self.destroyed) == set(range(1, 13))

    def test_critical_lane_overlap_keeps_the_uncovered_old_lanes(self):
        self.emit(7, 0, manager.ParticleManageKind.LANE, [-1.5, -0.5, 0.5])
        self.emit(7, 1, manager.ParticleManageKind.LANE, [0.5, 1.5])
        assert self.destroyed == [3]

    def test_other_bundles_cannot_evict_an_arrow_before_its_sixth_successor(self):
        self.emit(5, 1, manager.ParticleManageKind.MULTI, range(255))
        self.emit(4, 2, manager.ParticleManageKind.REST, [0])
        first_arrow = self.spawned
        self.emit(4, 3, manager.ParticleManageKind.REST, [0])
        assert first_arrow not in self.destroyed
        assert not self.destroyed

    def test_repeated_wide_bundles_keep_six_without_a_fixed_handle_pool(self):
        for group in range(10):
            self.emit(5, 0, manager.ParticleManageKind.MULTI, range(256))
            assert len(self.destroyed) == max(0, group - 5) * 256
        assert set(self.destroyed) == set(range(1, 1025))
        assert manager.ParticleHandler.serials[5] == 10
        live = [entry.handle.id for page in self.pages for entry in page.entries if entry.handle.id >= 0]
        assert live == list(range(1025, 2561))

    def test_empty_emissions_do_not_consume_a_bundle_or_evict_effects(self):
        for group in range(6):
            self.emit(4, group, manager.ParticleManageKind.REST, [0])
        for _ in range(10):
            manager.begin_particle_chunk(Particle(4), 6, manager.ParticleManageKind.REST)
        assert manager.ParticleHandler.serials[4] == 6
        assert not self.destroyed

    def test_hash_colliding_kinds_and_large_owner_ids_stay_independent(self):
        for particle_id in (1, 32, 63):
            for owner in range(8192, 8198):
                self.emit(particle_id, owner, manager.ParticleManageKind.REST, [0])
        assert not self.destroyed
        self.emit(32, 100000, manager.ParticleManageKind.REST, [0])
        assert self.destroyed == [7]

    def test_clearing_is_safe_before_reusing_an_owner(self):
        self.emit(7, 0, manager.ParticleManageKind.LANE, [-1.5, -0.5, 0.5])
        manager.clear_particles()
        self.refresh()
        assert self.destroyed == [1, 2, 3]
        self.destroyed.clear()
        self.emit(7, 0, manager.ParticleManageKind.LANE, [-1.5, -0.5, 0.5])
        assert not self.destroyed
        assert manager.ParticleHandler.serials[7] == 8

    def test_covered_lane_bundles_make_room_before_the_six_bundle_cap(self):
        for owner in range(6):
            self.emit(7, owner, manager.ParticleManageKind.LANE, [owner + 0.5])
        self.emit(7, 6, manager.ParticleManageKind.LANE, [4.5, 5.5])
        assert self.destroyed == [5, 6]
        assert sum(chunk.remaining > 0 for chunk in manager.ParticleHandler.critical_lanes) == 5

    def test_page_private_and_owner_shared_storage_stay_small(self):
        assert manager.ParticlePage._size_() <= 40
        assert manager.ParticleStorage._size_() == 4

    def test_expired_particles_do_not_force_removal_of_a_live_bundle(self):
        for owner in range(6):
            self.emit(4, owner, manager.ParticleManageKind.REST, [0])
        with patch.object(manager, "time", return_value=2):
            self.emit(4, 6, manager.ParticleManageKind.REST, [0])
        assert not self.destroyed
        assert manager.ParticleHandler.serials[4] == 7

    def test_shared_stride_does_not_exceed_the_original_44_slots(self):
        for mode in (play_mode, watch_mode):
            for archetype in mode.archetypes:
                archetype._init_fields()
                assert sum(f.type._size_() for f in archetype._shared_memory_fields_.values()) <= 44
                assert sum(f.type._size_() for f in archetype._memory_fields_.values()) <= 64

    def test_every_supported_critical_kind_has_six_independent_slots(self):
        expected = []
        for particle_id in manager.CRITICAL_LANE_IDS:
            first = self.spawned + 1
            for owner in range(6):
                self.emit(particle_id, owner, manager.ParticleManageKind.LANE, [owner - 10.5])
            self.emit(particle_id, 6, manager.ParticleManageKind.LANE, [10.5])
            expected.append(first)
        assert self.destroyed == expected

    def test_repeated_full_overlap_does_not_age_out_an_uncovered_old_bundle(self):
        self.emit(7, 0, manager.ParticleManageKind.LANE, [-5.5])
        for owner in range(1, 20):
            self.emit(7, owner, manager.ParticleManageKind.LANE, [0.5])
        assert 1 not in self.destroyed
        assert self.destroyed == list(range(2, 20))

    def test_generic_lane_counts_normal_and_critical_together(self):
        for owner in range(6):
            self.emit(0, owner, manager.ParticleManageKind.MULTI, [0.5, 1.5])
        self.emit(0, 6, manager.ParticleManageKind.LANE, [5.5])
        assert self.destroyed == [1, 2]
        for owner in range(7, 20):
            self.emit(0, owner, manager.ParticleManageKind.LANE, [5.5])
        assert set(range(3, 13)).isdisjoint(self.destroyed)
        assert sum(chunk.remaining > 0 for chunk in manager.ParticleHandler.critical_lanes) == 6

    def test_last_mask_word_keeps_count_and_flags_exact_in_f32(self):
        self.emit(7, 0, manager.ParticleManageKind.LANE, [i + 0.5 for i in range(-127, 127)])
        chunks = [c for c in manager.ParticleHandler.critical_lanes if c.remaining > 0]
        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.remaining == 254
        assert chunk.overlaps
        for word in chunk.lanes:
            assert struct.unpack("<f", struct.pack("<f", word))[0] == word
        self.emit(7, 1, manager.ParticleManageKind.LANE, [i + 0.5 for i in range(110, 127)])
        assert chunk.remaining == 237
        assert chunk.overlaps
        assert set(self.destroyed) == set(range(238, 255))

    def test_clear_reused_bundle_owners_cannot_resurrect_old_pages(self):
        self.emit(5, 0, manager.ParticleManageKind.MULTI, range(20))
        manager.clear_particles()
        self.emit(5, 0, manager.ParticleManageKind.MULTI, range(20))
        assert self.destroyed == list(range(1, 21))
        assert self.spawned == 40

    def test_watch_termination_releases_live_page_handles(self):
        self.emit(5, 0, manager.ParticleManageKind.MULTI, range(12))
        manager.destroy_particle_page(self.pages[0])
        assert self.destroyed == list(range(1, manager.PARTICLE_PAGE_SIZE + 1))
        assert len(self.pages[0].entries) == 0
        for page in self.pages[1:]:
            manager.destroy_particle_page(page)
        assert self.destroyed == list(range(1, 13))

    def test_arrow_cache_collision_cannot_remove_another_kind(self):
        arrow_ids = [i for i in range(manager.PARTICLE_KIND_COUNT) if manager._is_arrow(i)]
        first = arrow_ids[0]
        other = next(i for i in arrow_ids[1:] if i % 4 == first % 4)
        self.emit(first, 0, manager.ParticleManageKind.REST, [0])
        self.emit(other, 1, manager.ParticleManageKind.REST, [0])
        assert not self.destroyed
        for owner in range(2, 8):
            self.emit(first, owner, manager.ParticleManageKind.REST, [0])
        assert self.destroyed == [1]
        assert any(len(page.entries) == 1 for page in self.pages)

    def test_arrow_cache_does_not_destroy_unset_handles_at_negative_time(self):
        with patch.object(manager, "time", return_value=-5):
            manager.clear_particles()
        assert not self.destroyed
        particle_id = next(i for i in range(manager.PARTICLE_KIND_COUNT) if manager._is_arrow(i))
        with patch.object(manager, "time", return_value=-2):
            self.emit(particle_id, 0, manager.ParticleManageKind.REST, [0])
        assert not self.destroyed
        with patch.object(manager, "time", return_value=-3):
            manager.clear_particles()
        assert self.destroyed == [1]

    def test_arrow_cache_reassignment_waits_for_expiry_and_skips_finished_handles(self):
        arrow_ids = [i for i in range(manager.PARTICLE_KIND_COUNT) if manager._is_arrow(i)]
        first = arrow_ids[0]
        other = next(i for i in arrow_ids[1:] if i % 4 == first % 4)
        self.emit(first, 0, manager.ParticleManageKind.REST, [0])
        with patch.object(manager, "time", return_value=2):
            self.emit(other, 1, manager.ParticleManageKind.REST, [0])
        assert not self.destroyed
        assert not any(len(page.entries) for page in self.pages)


if __name__ == "__main__":
    unittest.main()
