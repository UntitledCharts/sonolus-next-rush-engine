from sonolus.script.engine import WatchMode

from sekai.lib.buckets import Buckets
from sekai.lib.effect import Effects
from sekai.lib.particle import BaseParticles
from sekai.lib.skin import BaseSkin
from sekai.watch.bpm_change import WatchBpmChange
from sekai.watch.connector import WATCH_CONNECTOR_ARCHETYPES
from sekai.watch.custom_elements import CUSTOM_ARCHETYPES
from sekai.watch.dynamic_stage import (
    WatchCameraChange,
    WatchDynamicStage,
    WatchStageMaskChange,
    WatchStagePivotChange,
    WatchStageStyleChange,
)
from sekai.watch.events import EVENT_ARCHETYPES
from sekai.watch.initialization import WatchInitialization
from sekai.watch.note import WATCH_NOTE_ARCHETYPES
from sekai.watch.particle_manager import ParticleManager
from sekai.watch.sim_line import WatchSimLine
from sekai.watch.slot_effect import WATCH_SLOT_EFFECT_ARCHETYPES
from sekai.watch.static_stage import WatchScheduledLaneEffect, WatchStaticStage
from sekai.watch.timescale import WatchTimescaleChange, WatchTimescaleGroup
from sekai.watch.update_spawn import update_spawn

watch_mode = WatchMode(
    archetypes=[
        WatchInitialization,
        WatchCameraChange,
        WatchDynamicStage,
        WatchStageMaskChange,
        WatchStagePivotChange,
        WatchStageStyleChange,
        WatchStaticStage,
        WatchScheduledLaneEffect,
        WatchBpmChange,
        WatchTimescaleGroup,
        WatchTimescaleChange,
        *WATCH_NOTE_ARCHETYPES,
        *WATCH_CONNECTOR_ARCHETYPES,
        *WATCH_SLOT_EFFECT_ARCHETYPES,
        WatchSimLine,
        *CUSTOM_ARCHETYPES,
        ParticleManager,
        *EVENT_ARCHETYPES,
    ],
    skin=BaseSkin,
    effects=Effects,
    particles=BaseParticles,
    buckets=Buckets,
    update_spawn=update_spawn,
)
