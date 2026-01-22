from sonolus.script.engine import PlayMode

from sekai.lib.buckets import Buckets
from sekai.lib.effect import Effects
from sekai.lib.particle import BaseParticles
from sekai.lib.skin import BaseSkin
from sekai.play.bpm_change import BpmChange
from sekai.play.connector import CONNECTOR_ARCHETYPES
from sekai.play.custom_elements import CUSTOM_ARCHETYPES
from sekai.play.dynamic_stage import CameraChange, DynamicStage, StageMaskChange, StagePivotChange, StageStyleChange
from sekai.play.events import EVENT_ARCHETYPES
from sekai.play.initialization import Initialization
from sekai.play.input_manager import InputManager
from sekai.play.note import NOTE_ARCHETYPES
from sekai.play.particle_manager import ParticleManager
from sekai.play.sim_line import SimLine
from sekai.play.slot_effect import SLOT_EFFECT_ARCHETYPES
from sekai.play.static_stage import StaticStage
from sekai.play.timescale import TimescaleChange, TimescaleGroup

play_mode = PlayMode(
    archetypes=[
        Initialization,
        CameraChange,
        DynamicStage,
        StageMaskChange,
        StagePivotChange,
        StageStyleChange,
        StaticStage,
        InputManager,
        BpmChange,
        TimescaleGroup,
        TimescaleChange,
        *NOTE_ARCHETYPES,
        *CONNECTOR_ARCHETYPES,
        *SLOT_EFFECT_ARCHETYPES,
        SimLine,
        *CUSTOM_ARCHETYPES,
        ParticleManager,
        *EVENT_ARCHETYPES,
    ],
    skin=BaseSkin,
    effects=Effects,
    particles=BaseParticles,
    buckets=Buckets,
)
