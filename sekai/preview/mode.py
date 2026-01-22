from sonolus.script.engine import PreviewMode

from sekai.lib.skin import BaseSkin
from sekai.preview.bpm_change import PreviewBpmChange
from sekai.preview.connector import PreviewConnector
from sekai.preview.dynamic_stage import (
    PreviewCameraChange,
    PreviewDynamicStage,
    PreviewStageMaskChange,
    PreviewStagePivotChange,
    PreviewStageStyleChange,
)
from sekai.preview.events import PREVIEW_EVENT_ARCHETYPES
from sekai.preview.initialization import PreviewInitialization
from sekai.preview.note import PREVIEW_NOTE_ARCHETYPES
from sekai.preview.sim_line import PreviewSimLine
from sekai.preview.timescale import PreviewTimescaleChange, PreviewTimescaleGroup

preview_mode = PreviewMode(
    archetypes=[
        PreviewInitialization,
        PreviewCameraChange,
        PreviewDynamicStage,
        PreviewStageMaskChange,
        PreviewStagePivotChange,
        PreviewStageStyleChange,
        PreviewBpmChange,
        PreviewTimescaleGroup,
        PreviewTimescaleChange,
        *PREVIEW_NOTE_ARCHETYPES,
        PreviewConnector,
        PreviewSimLine,
        *PREVIEW_EVENT_ARCHETYPES,
    ],
    skin=BaseSkin,
)
