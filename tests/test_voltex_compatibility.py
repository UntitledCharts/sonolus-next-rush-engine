"""Voltex gauge and hide skills retain their behavior with master UI caches."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sonolus.script.bucket import Judgment
from sonolus.script.debug import simulation_context
from sonolus.script.quad import Rect
from sonolus.script.sprite import Sprite

from sekai.lib import custom_elements as ui
from sekai.lib import note
from sekai.lib.level_config import EngineRevision
from sekai.lib.options import GaugeMode, ScoreMode
from sekai.play import note as play_note


class VoltexCompatibilityTests(unittest.TestCase):
    def test_revision_two_retains_gauge_and_elevation_meanings(self):
        assert EngineRevision.GAUGE_REWORK == 2
        assert EngineRevision.APPARENT_ELEVATION == 2
        assert EngineRevision.LATEST >= EngineRevision.GAUGE_REWORK

    def test_gauges_keep_normalized_life_and_trace_half_weight(self):
        for gauge, perfect, great, good, miss in (
            (GaugeMode.STANDARD, 30, 20, -250, -500),
            (GaugeMode.HEAVY, 30, 0, -750, -1500),
            (GaugeMode.ULTIMA, 20, -500, -1000, -2000),
        ):
            with self.subTest(gauge=gauge):
                tap = SimpleNamespace(key=note.NoteKind.NORM_TAP, life=SimpleNamespace(update=Mock()))
                trace = SimpleNamespace(key=note.NoteKind.NORM_TRACE, life=SimpleNamespace(update=Mock()))
                native_life = SimpleNamespace(update=Mock())
                with (
                    patch.object(note, "Options", SimpleNamespace(gauge=gauge)),
                    patch.object(note, "level_life", return_value=native_life),
                ):
                    note.init_gauge_life([tap, trace], 1500, 2000)
                tap.life.update.assert_called_once_with(
                    perfect_increment=perfect,
                    great_increment=great,
                    good_increment=good,
                    miss_increment=miss,
                )
                trace.life.update.assert_called_once_with(
                    perfect_increment=perfect // 2,
                    great_increment=great // 2,
                    good_increment=good // 2,
                    miss_increment=miss // 2,
                )
                native_life.update.assert_called_once_with(initial=10000, maximum=10000)

    def test_arcade_score_keeps_one_million_perfect_and_fixed_judgment_weights(self):
        from sekai.play import custom_elements as play_ui

        for judgments, expected in (
            ([Judgment.PERFECT] * 3, 1000000),
            ([Judgment.PERFECT, Judgment.GREAT, Judgment.GOOD], 1000000 * 2 / 3),
        ):
            with (
                simulation_context(),
                patch.object(play_ui, "Options", SimpleNamespace(custom_score=1, custom_score_bar=True)),
                patch.object(note, "LevelConfig", SimpleNamespace(score_mode=ScoreMode.UNWEIGHTED_FLAT)),
                patch.object(
                    play_ui,
                    "level_score",
                    return_value=SimpleNamespace(
                        perfect_multiplier=3,
                        great_multiplier=2,
                        good_multiplier=1,
                    ),
                ),
                patch.object(
                    play_note.BaseNote,
                    "at",
                    return_value=SimpleNamespace(
                        archetype_score_multiplier=10,
                        entity_score_multiplier=0,
                    ),
                ),
            ):
                ui.ScoreIndicator.max_score = 1000000
                ui.ScoreIndicator.total_weight.add(90)
                for judgment in judgments:
                    play_ui.ComboJudge.calculate_score(
                        SimpleNamespace(
                            judgment=judgment,
                            note_index=1,
                            spawn_time=0,
                        )
                    )
                assert abs(ui.ScoreIndicator.score - expected) < 1e-6

    def test_hide_judgment_fades_the_cached_sprite(self):
        with (
            simulation_context(),
            patch.object(ui, "Options", SimpleNamespace(hide_ui=0, custom_judgment=True)),
            patch.object(ui, "ActiveSkin", SimpleNamespace(judgment=SimpleNamespace(available=True))),
            patch.object(ui, "is_watch", return_value=False),
            patch.object(ui, "time", return_value=0.75),
            patch.object(ui, "runtime_ui", return_value=SimpleNamespace(judgment_config=SimpleNamespace(alpha=0.8))),
            patch.object(ui, "layout_combo_label", return_value=Rect(l=0, r=1, b=0, t=1)),
            patch.object(Sprite, "draw") as draw,
        ):
            ui.FixedUiLayout.judgment_h = 0.1
            ui.FixedUiLayout.judgment_w = 0.4
            ui.SkillHide.judgment_hidden = 0.5
            ui.draw_judgment_text(0.5, Sprite(7))
            assert draw.call_count == 1
            assert draw.call_args.kwargs["a"] == 0.4
            draw.reset_mock()
            ui.SkillHide.judgment_hidden = 1
            ui.draw_judgment_text(0.5, Sprite(7))
            draw.assert_not_called()
