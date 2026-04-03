from sekai.lib.layout import init_layout
from sekai.lib.level_config import init_level_config
from sekai.lib.particle import init_particles
from sekai.lib.skin import init_skin
from sekai.lib.ui import init_ui


def preprocess():
    init_level_config()
    init_layout()
    init_skin()
    init_ui()
    init_particles()
