"""Invisible visual-only connectors do not spawn; hidden input connectors remain."""

import math
import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from sekai.lib.connector import ConnectorKind
from sekai.play import connector as play
from sekai.watch import connector as watch


class PreprocessContinuedError(Exception):
    pass


class Endpoint:
    preprocess_done = True
    is_attached = False
    stage_ref = SimpleNamespace(index=0)
    elevation = 0

    @property
    def connector_ease(self):
        raise PreprocessContinuedError


def fake_connector(active):
    endpoint = Endpoint()
    return SimpleNamespace(
        head=endpoint, tail=endpoint, active_head=endpoint, active_tail=endpoint,
        segment_head=SimpleNamespace(
            preprocess_done=True, segment_kind=ConnectorKind.ACTIVE_NORMAL if active else ConnectorKind.GUIDE_RED
        ),
        segment_tail=SimpleNamespace(preprocess_done=True),
        active_head_ref=SimpleNamespace(index=1 if active else 0),
        active_tail_ref=SimpleNamespace(index=1 if active else 0),
    )


class ConnectorVisibilityOptionTests(unittest.TestCase):
    def test_invisible_visual_only_connectors_remain_unscheduled(self):
        for module, archetype in ((play, play.Connector), (watch, watch.WatchConnector)):
            with (
                self.subTest(mode=module.__name__),
                patch.object(module, "schedule_connector_sfx_after_notes"),
                patch.object(module, "get_connector_alpha_option", return_value=0),
            ):
                entity = fake_connector(False)
                archetype.preprocess(cast(Any, entity))
                assert entity.scheduled_spawn_time == math.inf
                assert entity.start_time == math.inf

    def test_visible_and_input_connectors_continue_preprocessing(self):
        for module, archetype in ((play, play.Connector), (watch, watch.WatchConnector)):
            for active, alpha in ((False, 0.6), (True, 0)):
                with (
                    self.subTest(mode=module.__name__, active=active),
                    patch.object(module, "schedule_connector_sfx_after_notes"),
                    patch.object(module, "get_connector_alpha_option", return_value=alpha),
                    self.assertRaises(PreprocessContinuedError),  # noqa: PT027
                ):
                    archetype.preprocess(cast(Any, fake_connector(active)))


if __name__ == "__main__":
    unittest.main()
