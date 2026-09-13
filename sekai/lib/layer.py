from sonolus.script import runtime
from sonolus.script.record import Record

LAYER_BACKGROUND = 0.5
LAYER_ACTIVE_SLIDE_CONNECTOR_UNDER = 1
LAYER_GUIDE_CONNECTOR_UNDER = 2
LAYER_BACKGROUND_SIDE = 2.2
LAYER_BACKGROUND_COVER = 2.4
LAYER_STAGE_COVER = 2.6
LAYER_GAUGE = 2.8
LAYER_STAGE = 3
LAYER_COVER = 4
LAYER_COVER_LINE = 4.2
LAYER_STAGE_LANE = 4.4
LAYER_JUDGMENT_LINE = 4.6
LAYER_JUDGMENT_SKILL = 4.8
LAYER_SLOT_EFFECT = 5
LAYER_BEAT_LINE = 6
LAYER_ACTIVE_SLIDE_CONNECTOR_BOTTOM = 7
LAYER_GUIDE_CONNECTOR_BOTTOM = 8
LAYER_ACTIVE_SLIDE_CONNECTOR_TOP = 9
LAYER_GUIDE_CONNECTOR_TOP = 10
LAYER_PREVIEW_COVER = 11
LAYER_SIM_LINE = 12
LAYER_TIME_LINE = 13
LAYER_BPM_LINE = 14
LAYER_TIMESCALE_LINE = 15
LAYER_SKILL_LINE = 15.25
LAYER_FEVER_LINE_BOTTOM = 15.5
LAYER_FEVER_LINE_TOP = 15.75
LAYER_NOTE_SLIM_BODY = 16
LAYER_NOTE_FLICK_BODY = 17
LAYER_NOTE_BODY = 18
LAYER_NOTE_TICK = 19
LAYER_NOTE_ARROW = 20
LAYER_NOTE_ARROW_CRITICAL = 20.5
LAYER_SLOT_GLOW_EFFECT = 21
LAYER_ACTIVE_SLIDE_CONNECTOR_OVER = 22
LAYER_GUIDE_CONNECTOR_OVER = 23
LAYER_DAMAGE = 23.2
LAYER_SKILL_BAR = 23.4
LAYER_SKILL_ETC = 23.6
LAYER_JUDGMENT = 23.8
LAYER_OVERLAY = 24


class Layer(Record):
    layer: float
    sublayer: float


class _Layers(Record):
    @property
    def background_cover(self) -> Layer:
        return Layer(0, 0)

    @property
    def active_slide_connector_under(self) -> Layer:
        return Layer(1, 0)

    @property
    def guide_connector_under(self) -> Layer:
        return Layer(2, 0)

    @property
    def stage(self) -> Layer:
        if runtime.is_preview():
            return Layer(3, 0)
        return Layer(16, -9)

    @property
    def cover(self) -> Layer:
        if runtime.is_preview():
            return Layer(4, 0)
        return Layer(16, -8)

    @property
    def slot_effect(self) -> Layer:
        if runtime.is_preview():
            return Layer(5, 0)
        return Layer(16, -7)

    @property
    def beat_line(self) -> Layer:
        return Layer(6, 0)

    @property
    def active_slide_connector_bottom(self) -> Layer:
        if runtime.is_preview():
            return Layer(7, 0)
        return Layer(16, -5)

    @property
    def guide_connector_bottom(self) -> Layer:
        if runtime.is_preview():
            return Layer(8, 0)
        return Layer(16, -4)

    @property
    def active_slide_connector_top(self) -> Layer:
        if runtime.is_preview():
            return Layer(9, 0)
        return Layer(16, -3)

    @property
    def guide_connector_top(self) -> Layer:
        if runtime.is_preview():
            return Layer(10, 0)
        return Layer(16, -2)

    @property
    def preview_cover(self) -> Layer:
        return Layer(11, 0)

    @property
    def sim_line(self) -> Layer:
        if runtime.is_preview():
            return Layer(12, 0)
        return Layer(16, -1)

    @property
    def time_line(self) -> Layer:
        return Layer(13, 0)

    @property
    def bpm_line(self) -> Layer:
        return Layer(14, 0)

    @property
    def timescale_line(self) -> Layer:
        return Layer(15, 0)

    @property
    def note(self) -> Layer:
        return Layer(16, 0)

    @property
    def note_slim_body(self) -> Layer:
        return Layer(16, 0)

    @property
    def note_flick_body(self) -> Layer:
        return Layer(16, 1)

    @property
    def note_body(self) -> Layer:
        return Layer(16, 2)

    @property
    def note_tick(self) -> Layer:
        return Layer(16, 3)

    @property
    def note_arrow(self) -> Layer:
        return Layer(16, 4)

    @property
    def slot_glow_effect(self) -> Layer:
        return Layer(16, 5)

    @property
    def active_slide_connector_over(self) -> Layer:
        return Layer(22, 0)

    @property
    def guide_connector_over(self) -> Layer:
        return Layer(23, 0)

    @property
    def overlay(self) -> Layer:
        return Layer(24, 0)


layers = _Layers()


class ZIndexes(Record):
    z1: float
    z2: float
    z3: float
    z4: float

    @property
    def tuple(self) -> tuple[float, float, float, float]:
        return self.z1, self.z2, self.z3, self.z4


def get_z(
    layer: Layer | float,
    time: float = 0.0,
    lane: float = 0.0,
    etc: int = 0,
    *,
    elevation: float = 0.0,
    invert_time: bool = False,
) -> ZIndexes:
    layer = resolve_layer(layer)
    return ZIndexes(
        z1=layer.layer,
        z2=elevation + layer.sublayer * 0.01,
        z3=time - runtime.time() if invert_time else runtime.time() - time,
        z4=abs(lane) + (1 / 20) * (lane > 0) + etc * 1e-6,
    )


def get_z_alt(layer: Layer | float, order: int = 0, *, elevation: float = 0.0) -> ZIndexes:
    layer = resolve_layer(layer)
    return ZIndexes(
        z1=layer.layer,
        z2=elevation + layer.sublayer * 0.01,
        z3=order,
        z4=0.0,
    )


def resolve_layer(layer: Layer | float) -> Layer:
    if isinstance(layer, Layer):
        return layer
    result = Layer(layer, 0)
    if layer == LAYER_ACTIVE_SLIDE_CONNECTOR_UNDER:
        result @= layers.active_slide_connector_under
    elif layer == LAYER_GUIDE_CONNECTOR_UNDER:
        result @= layers.guide_connector_under
    elif layer == LAYER_BACKGROUND_COVER:
        result @= Layer(LAYER_BACKGROUND_COVER, 0)
    elif layer == LAYER_STAGE:
        result @= layers.stage
    elif layer == LAYER_COVER:
        result @= layers.cover
    elif layer == LAYER_SLOT_EFFECT:
        result @= layers.slot_effect
    elif layer == LAYER_BEAT_LINE:
        result @= layers.beat_line
    elif layer == LAYER_ACTIVE_SLIDE_CONNECTOR_BOTTOM:
        result @= layers.active_slide_connector_bottom
    elif layer == LAYER_GUIDE_CONNECTOR_BOTTOM:
        result @= layers.guide_connector_bottom
    elif layer == LAYER_ACTIVE_SLIDE_CONNECTOR_TOP:
        result @= layers.active_slide_connector_top
    elif layer == LAYER_GUIDE_CONNECTOR_TOP:
        result @= layers.guide_connector_top
    elif layer == LAYER_PREVIEW_COVER:
        result @= layers.preview_cover
    elif layer == LAYER_SIM_LINE:
        result @= layers.sim_line
    elif layer == LAYER_TIME_LINE:
        result @= layers.time_line
    elif layer == LAYER_BPM_LINE:
        result @= layers.bpm_line
    elif layer == LAYER_TIMESCALE_LINE:
        result @= layers.timescale_line
    elif layer == LAYER_NOTE_SLIM_BODY:
        result @= layers.note_slim_body
    elif layer == LAYER_NOTE_FLICK_BODY:
        result @= layers.note_flick_body
    elif layer == LAYER_NOTE_BODY:
        result @= layers.note_body
    elif layer == LAYER_NOTE_TICK:
        result @= layers.note_tick
    elif layer == LAYER_NOTE_ARROW:
        result @= layers.note_arrow
    elif layer == LAYER_SLOT_GLOW_EFFECT:
        result @= layers.slot_glow_effect
    elif layer == LAYER_ACTIVE_SLIDE_CONNECTOR_OVER:
        result @= layers.active_slide_connector_over
    elif layer == LAYER_GUIDE_CONNECTOR_OVER:
        result @= layers.guide_connector_over
    elif layer == LAYER_OVERLAY:
        result @= layers.overlay
    elif layer == LAYER_NOTE_ARROW_CRITICAL:
        result @= Layer(16, 4.5)
    elif layer == LAYER_COVER_LINE:
        result @= Layer(16, -7.8)
    elif layer == LAYER_STAGE_LANE:
        result @= Layer(16, -7.6)
    elif layer == LAYER_JUDGMENT_LINE:
        result @= Layer(16, -7.4)
    elif layer == LAYER_JUDGMENT_SKILL:
        result @= Layer(16, -7.2)
    return result
