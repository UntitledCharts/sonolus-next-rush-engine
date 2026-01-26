from enum import IntEnum

from sonolus.script.globals import level_data

from sekai.lib.options import Options, ScoreMode, SekaiVersion


class EngineRevision(IntEnum):
    BASE = 0
    SONOLUS_1_1_0 = 1

    LATEST = 1


@level_data
class LevelConfig:
    revision: EngineRevision
    score_mode: ScoreMode
    dynamic_stages: bool
    skip_default_stage: bool
    ui_version: SekaiVersion
    particle_version: SekaiVersion


def init_level_config(
    revision: EngineRevision = EngineRevision.LATEST,
):
    LevelConfig.revision = revision
    if revision >= EngineRevision.SONOLUS_1_1_0:
        LevelConfig.score_mode = Options.score_mode
    else:
        LevelConfig.score_mode = ScoreMode.WEIGHTED_COMBO


def init_ui_version(ui_version: SekaiVersion):
    LevelConfig.ui_version = ui_version


def init_particle_version(particle_version: SekaiVersion):
    LevelConfig.particle_version = particle_version
