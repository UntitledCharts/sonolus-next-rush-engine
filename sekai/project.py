from sonolus.script.engine import Engine, EngineData
from sonolus.script.project import Project

from sekai.lib.converter import convert_extended_level_data
from sekai.lib.options import Options
from sekai.lib.ui import ui_config
from sekai.play.mode import play_mode
from sekai.preview.mode import preview_mode
from sekai.server_resources import load_resources
from sekai.test_level import load_levels
from sekai.tutorial.mode import tutorial_mode
from sekai.watch.mode import watch_mode

engine = Engine(
    name="next-rush-dev",
    title="Next RUSH",
    thumbnail="../js/res/thumbnail.png",
    skin="coconut-next-sekai-1",
    background="coconut-next-sekai-1",
    effect="coconut-next-sekai-1",
    particle="coconut-next-sekai-1",
    data=EngineData(
        ui=ui_config,
        options=Options,
        play=play_mode,
        watch=watch_mode,
        preview=preview_mode,
        tutorial=tutorial_mode,
    ),
)

project = Project(
    engine=engine,
    levels=load_levels,
    resources=load_resources(),
    converters={
        "chcy-extended": convert_extended_level_data,
    },
)
