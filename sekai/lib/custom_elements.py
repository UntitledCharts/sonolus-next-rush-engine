from enum import IntEnum
from math import floor, sin

from sonolus.script.array import Array, Dim
from sonolus.script.containers import VarArray
from sonolus.script.globals import level_memory
from sonolus.script.interval import clamp, unlerp, unlerp_clamped
from sonolus.script.record import Record
from sonolus.script.runtime import aspect_ratio, is_replay, is_watch, runtime_ui, screen, time
from sonolus.script.sprite import Sprite, ZIndex
from sonolus.script.vec import Vec2

from sekai.lib import font_metrics
from sekai.lib import hud_geometry as hud
from sekai.lib.layer import (
    LAYER_DAMAGE,
    LAYER_JUDGMENT,
    get_z_alt,
)
from sekai.lib.layout import (
    ComboType,
    Quad,
    UIMargin,
    layout_center_ui,
    layout_dead_effect_quads,
    v3_align_bar_point,
    v3_hud_anchor,
)
from sekai.lib.level_config import LevelConfig
from sekai.lib.options import Options, Version
from sekai.lib.skin import (
    ActiveSkin,
)

AP_EFFECT_SPEED = 4.1887903

COMBO_NUMBER_FALLBACK_SCALE = 0.67


@level_memory
class FixedUiLayout:
    combo_label: Quad
    judgment_accuracy: Quad
    damage_flash: Array[Quad, Dim[4]]
    combo_h: float
    combo_w: float
    combo_h2: float
    combo_w2: float
    combo_gap: float
    combo_gap2: float
    combo_s2_start: float
    judgment_h: float
    judgment_w: float


def init_fixed_ui_layout():
    ui = runtime_ui()

    # These elements have no v1/v3 split: apply the center-camera layout to both.
    combo_scale = ui.combo_config.scale
    judgment_scale = ui.judgment_config.scale
    FixedUiLayout.combo_label = layout_center_ui(
        Vec2(6.241, 1.513), w=(192 / 108) * combo_scale / 2, h=(77 / 108) * combo_scale / 2
    )
    FixedUiLayout.judgment_accuracy = layout_center_ui(
        Vec2(0, -1.17 + 0.58), w=(164 / 108) * 0.8 * judgment_scale / 2, h=(50 / 108) * 0.8 * judgment_scale / 2
    )
    FixedUiLayout.damage_flash = layout_dead_effect_quads()
    fallback = COMBO_NUMBER_FALLBACK_SCALE if ActiveSkin.combo_number.is_fallback else 1.0
    FixedUiLayout.combo_h = (150 / 108) * combo_scale * fallback
    FixedUiLayout.combo_w = FixedUiLayout.combo_h
    FixedUiLayout.combo_h2 = FixedUiLayout.combo_h * (0.25 / 0.23)
    FixedUiLayout.combo_w2 = FixedUiLayout.combo_h2
    FixedUiLayout.combo_gap = 0.95 * combo_scale - FixedUiLayout.combo_w
    FixedUiLayout.combo_gap2 = 0.95 * combo_scale * (0.25 / 0.23) - FixedUiLayout.combo_w2
    FixedUiLayout.combo_s2_start = 0.23 / 0.25
    # Judgment size must follow judgment scaling, independently of combo scale.
    FixedUiLayout.judgment_h = (80 / 108) * judgment_scale
    FixedUiLayout.judgment_w = (310 / 108) * judgment_scale


class ComboNumberCache(Record):
    # Sixteen digits cover combo counts through 2**53.
    # Least significant digit first, so extraction takes one division per digit.
    digits: VarArray[int, Dim[16]]
    start_x: float
    start_x2: float

    def set_combo(self, combo: int):
        self.digits.clear()
        remaining = combo
        while remaining > 0:
            self.digits.append(remaining % 10)
            remaining //= 10
        digit_count = len(self.digits)
        total_width = digit_count * FixedUiLayout.combo_w + (digit_count - 1) * FixedUiLayout.combo_gap
        total_width2 = digit_count * FixedUiLayout.combo_w2 + (digit_count - 1) * FixedUiLayout.combo_gap2
        self.start_x = 6.217 - total_width / 2
        self.start_x2 = 6.217 - total_width2 / 2


@level_memory
class LifeManager:
    life: float
    initial_life: int
    max_life: int
    decrease_life: int
    first: float


class NeumaierSum(Record):
    base: float
    c: float

    @property
    def total(self) -> float:
        return self.base + self.c

    def add(self, value: float) -> None:
        t = self.base + value
        if abs(self.base) >= abs(value):
            self.c += (self.base - t) + value
        else:
            self.c += (value - t) + self.base
        self.base = t


@level_memory
class ScoreIndicator:
    score: float
    note_score: float
    note_time: float
    percentage: float
    ap: bool
    first: float

    # Play
    total_weight: NeumaierSum
    acc_sum: NeumaierSum
    processed_weight: NeumaierSum
    current_raw_score: NeumaierSum
    max_score: int
    count: int
    perfect_step: int
    great_step: int
    good_step: int


def draw_combo_label(ap: bool, combo: int):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.combo_label.available:
        return
    if is_watch() and Options.auto_judgment and not is_replay():
        return
    if not Options.custom_combo:
        return
    if combo == 0:
        return

    ui = runtime_ui()

    a = ui.combo_config.alpha * (sin(time() * AP_EFFECT_SPEED) + 1) * 0.5
    layout = FixedUiLayout.combo_label
    if ap or not Options.ap_effect:
        ActiveSkin.combo_label.get_sprite(ComboType.NORMAL).draw(
            quad=layout, z=get_z_alt(LAYER_JUDGMENT, 1).tuple, a=ui.combo_config.alpha
        )
    else:
        ActiveSkin.combo_label.get_sprite(ComboType.AP).draw(
            quad=layout, z=get_z_alt(LAYER_JUDGMENT, 1).tuple, a=ui.combo_config.alpha
        )
        ActiveSkin.combo_label.get_sprite(ComboType.GLOW).draw(quad=layout, z=get_z_alt(LAYER_JUDGMENT).tuple, a=a)


def draw_combo_number(draw_time: float, ap: bool, cache: ComboNumberCache):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.combo_number.available:
        return
    if is_watch() and Options.auto_judgment and not is_replay():
        return
    if not Options.custom_combo:
        return
    digit_count = len(cache.digits)
    if digit_count == 0:
        return

    ui = runtime_ui()

    screen_center = Vec2(x=6.217, y=0.787 - 0.18)

    s = 0.6 + 0.4 * unlerp_clamped(draw_time, draw_time + 0.112, time())
    s2_start = FixedUiLayout.combo_s2_start
    s2 = s2_start + (1 - s2_start) * unlerp_clamped(draw_time + 0.112, draw_time + 0.192, time())

    a = ui.combo_config.alpha
    a2 = (
        ui.combo_config.alpha * unlerp(draw_time + 0.192, draw_time + 0.112, time())
        if time() >= draw_time + 0.112
        else 0
    )
    a3 = ui.combo_config.alpha * (sin(time() * AP_EFFECT_SPEED) + 1) * 0.5

    drawing_combo = ComboNumberLayout(
        core=CoreConfig(
            ap=ap,
            combo_number=0,
            digit_count=digit_count,
            is_score=False,
        ),
        design=ScoreDesignConfig(s_int=1, s_dot=1, s_dec=1, s_pct=1),
        common=CommonConfig(
            center_x=screen_center.x,
            center_y=screen_center.y,
        ),
        alpha=AlphaConfig(
            a=a,
            a2=a2,
            a3=a3,
        ),
        layout1=LayoutConfig(
            width=FixedUiLayout.combo_w,
            gap=FixedUiLayout.combo_gap,
            scale=s,
            height=FixedUiLayout.combo_h,
            start_x=cache.start_x,
        ),
        layout2=LayoutConfig(
            width=FixedUiLayout.combo_w2,
            gap=FixedUiLayout.combo_gap2,
            scale=s2,
            height=FixedUiLayout.combo_h2,
            start_x=cache.start_x2,
        ),
    )
    drawing_combo.draw_number(
        z=get_z_alt(LAYER_JUDGMENT).tuple,
        z1=get_z_alt(LAYER_JUDGMENT, 1).tuple,
        z2=get_z_alt(LAYER_JUDGMENT, 2).tuple,
        digits=cache.digits,
    )


def draw_score_number(ap: bool, score: float, alpha: float = 1.0):
    if Options.hide_ui >= 2:
        return

    if Options.custom_score == 0:
        return

    if Options.auto_judgment and is_watch() and not is_replay():
        return

    ui = runtime_ui()

    if score == 0:
        n_int = 1
    else:
        n_int = 0
        temp_n = score
        while temp_n > 0:
            temp_n = temp_n // 10
            n_int += 1
    digit_count = n_int + 6

    screen_center = Vec2(x=6.217, y=2.0)

    fallback_scale = COMBO_NUMBER_FALLBACK_SCALE if ActiveSkin.combo_number.is_fallback else 1.0
    base_h = (150 / 108) * ui.combo_config.scale * 0.4 * fallback_scale
    base_w = base_h

    s = 1.0

    a = ui.combo_config.alpha
    a3 = ui.combo_config.alpha * (sin(time() * AP_EFFECT_SPEED) + 1) * 0.5

    h, w = base_h, base_w

    digit_gap = 0.95 * ui.combo_config.scale * 0.4 - w

    s_int = 1.0
    s_dot = 0.5
    s_dec = 0.6
    s_pct = 1.0

    count_large = n_int + 2
    count_dot = 1
    count_small = 2

    total_w_factor = (count_large * s_int) + (count_dot * s_dot) + (count_small * s_dec) + s_pct
    total_gap_factor = (n_int - 1) * s_int + (s_int + s_dot) + s_int + (s_int + s_dec) / 2 + s_dec + (s_dec + s_pct) / 2

    total_width = (total_w_factor * w) + (total_gap_factor * digit_gap)

    start_x = screen_center.x - total_width / 2

    drawing_combo = ComboNumberLayout(
        core=CoreConfig(
            ap=ap,
            combo_number=score,
            digit_count=digit_count,
            is_score=True,
        ),
        design=ScoreDesignConfig(s_int=s_int, s_dot=s_dot, s_dec=s_dec, s_pct=s_pct),
        common=CommonConfig(
            center_x=screen_center.x,
            center_y=screen_center.y,
        ),
        alpha=AlphaConfig(a=a * alpha, a2=0, a3=a3 * alpha),
        layout1=LayoutConfig(width=w, gap=digit_gap, scale=s, height=h, start_x=start_x),
        layout2=LayoutConfig(width=0, gap=0, scale=0, height=0, start_x=0),
    )
    drawing_combo.draw_number(z=0, z1=get_z_alt(LAYER_JUDGMENT).tuple, z2=get_z_alt(LAYER_JUDGMENT, 1).tuple)


class CoreConfig(Record):
    ap: bool
    combo_number: int | float
    digit_count: int
    is_score: bool


class CommonConfig(Record):
    center_x: float
    center_y: float


class AlphaConfig(Record):
    a: float
    a2: float
    a3: float


class LayoutConfig(Record):
    width: float
    gap: float
    scale: float
    height: float
    start_x: float


class ScoreDesignConfig(Record):
    s_int: float
    s_dot: float
    s_dec: float
    s_pct: float


class ComboNumberLayout(Record):
    core: CoreConfig
    design: ScoreDesignConfig
    common: CommonConfig
    alpha: AlphaConfig
    layout1: LayoutConfig
    layout2: LayoutConfig

    def layout_combo_number(self, l: float, r: float, t: float, b: float) -> Quad:
        return layout_center_ui(Vec2((l + r) / 2, (t + b) / 2), w=(r - l) / 2, h=(b - t) / 2)

    def draw_number(self, z, z1, z2, digits: VarArray[int, Dim[16]] | None = None):
        s_inv = 1 - self.layout1.scale
        s2_inv = 1 - self.layout2.scale

        current_x1 = self.layout1.start_x

        baseline_y1 = self.common.center_y + self.layout1.height / 2

        n_int = self.core.digit_count - 6 if self.core.is_score else 0

        for i in range(self.core.digit_count):
            digit = 0
            if self.core.is_score:
                gap_factor = 0
                scale_factor = 0
                layout_scale_factor = 0
                if i < n_int:
                    digit = floor(self.core.combo_number / (10 ** (n_int - 1 - i))) % 10  # Integer part
                    scale_factor = self.design.s_int
                    layout_scale_factor = self.design.s_int
                    if i == n_int - 1:
                        gap_factor = (self.design.s_int + self.design.s_dot) / 2
                    else:
                        gap_factor = self.design.s_int
                elif i == n_int:
                    digit = 10  # Dot(.)
                    scale_factor = self.design.s_int
                    gap_factor = (self.design.s_dot + self.design.s_int) / 2
                    layout_scale_factor = self.design.s_dot
                elif i == n_int + 1 or i == n_int + 2:
                    decimal_idx = i - n_int
                    digit = floor(self.core.combo_number * (10**decimal_idx)) % 10
                    scale_factor = self.design.s_int
                    layout_scale_factor = self.design.s_int
                    if i == n_int + 2:
                        gap_factor = (self.design.s_int + self.design.s_dec) / 2
                    else:
                        gap_factor = self.design.s_int
                elif i == n_int + 3 or i == n_int + 4:
                    decimal_idx = i - n_int
                    digit = floor(self.core.combo_number * (10**decimal_idx)) % 10
                    scale_factor = self.design.s_dec
                    layout_scale_factor = self.design.s_dec
                    if i == n_int + 4:
                        gap_factor = (self.design.s_dec + self.design.s_pct) / 2
                    else:
                        gap_factor = self.design.s_dec
                elif i == n_int + 5:
                    digit = 11  # Percent(%)
                    scale_factor = self.design.s_dec
                    gap_factor = self.design.s_pct
                    layout_scale_factor = self.design.s_pct

                layout_w1 = self.layout1.width * layout_scale_factor

                draw_w1 = self.layout1.width * scale_factor
                draw_h1 = self.layout1.height * scale_factor

                this_gap1 = self.layout1.gap * gap_factor

                digit_center_x = current_x1 + layout_w1 / 2

                unscaled_b1 = baseline_y1
                unscaled_t1 = baseline_y1 - draw_h1

                current_x1 += layout_w1 + this_gap1

                final_draw_w1 = draw_w1

                digit_center_x2 = 0
                final_draw_w2 = 0
                unscaled_t2 = 0
                unscaled_b2 = 0
            else:
                if digits is None:
                    digit = floor(self.core.combo_number / 10 ** (self.core.digit_count - 1 - i)) % 10
                else:
                    digit = digits[self.core.digit_count - 1 - i]

                final_draw_w1 = self.layout1.width
                final_draw_w2 = self.layout2.width

                digit_center_x = (
                    self.layout1.start_x + (i * (self.layout1.width + self.layout1.gap)) + self.layout1.width / 2
                )
                digit_center_x2 = (
                    self.layout2.start_x + (i * (self.layout2.width + self.layout2.gap)) + self.layout2.width / 2
                )

                unscaled_t1 = self.common.center_y - self.layout1.height / 2
                unscaled_b1 = self.common.center_y + self.layout1.height / 2
                unscaled_t2 = self.common.center_y - self.layout2.height / 2
                unscaled_b2 = self.common.center_y + self.layout2.height / 2

            if not ActiveSkin.combo_number.is_fallback and digit < 10:
                # Preserve cell advances; fit only the image drawn inside each
                # cell, including transparent padding and the source pivot.
                for shadow in range(2):
                    width = final_draw_w1 if shadow == 0 else final_draw_w2
                    height = (unscaled_b1 - unscaled_t1) if shadow == 0 else (unscaled_b2 - unscaled_t2)
                    dx = width * font_metrics.COMBO_DX[digit]
                    dy = height * font_metrics.COMBO_DY[digit]
                    center_y = ((unscaled_t1 + unscaled_b1) if shadow == 0 else (unscaled_t2 + unscaled_b2)) / 2 + dy
                    height *= font_metrics.COMBO_H[digit]
                    if shadow == 0:
                        digit_center_x += dx
                        final_draw_w1 *= font_metrics.COMBO_W[digit]
                        unscaled_t1 = center_y - height / 2
                        unscaled_b1 = center_y + height / 2
                    else:
                        digit_center_x2 += dx
                        final_draw_w2 *= font_metrics.COMBO_W[digit]
                        unscaled_t2 = center_y - height / 2
                        unscaled_b2 = center_y + height / 2

            l1 = self.layout1.scale * (digit_center_x - final_draw_w1 / 2) + s_inv * self.common.center_x
            r1 = self.layout1.scale * (digit_center_x + final_draw_w1 / 2) + s_inv * self.common.center_x
            t1 = self.layout1.scale * unscaled_t1 + s_inv * self.common.center_y
            b1 = self.layout1.scale * unscaled_b1 + s_inv * self.common.center_y

            digit_layout = self.layout_combo_number(l=l1, r=r1, t=t1, b=b1)

            l2 = self.layout2.scale * (digit_center_x2 - final_draw_w2 / 2) + s2_inv * self.common.center_x
            r2 = self.layout2.scale * (digit_center_x2 + final_draw_w2 / 2) + s2_inv * self.common.center_x
            t2 = self.layout2.scale * unscaled_t2 + s2_inv * self.common.center_y
            b2 = self.layout2.scale * unscaled_b2 + s2_inv * self.common.center_y

            digit_layout2 = self.layout_combo_number(l=l2, r=r2, t=t2, b=b2)

            if not self.core.ap and Options.ap_effect and not ActiveSkin.combo_number.is_fallback:
                ActiveSkin.combo_number.get_sprite(combo=digit, combo_type=ComboType.GLOW).draw(
                    quad=digit_layout, z=z2, a=self.alpha.a3
                )
                if not self.core.is_score:
                    ActiveSkin.combo_number.get_sprite(combo=digit, combo_type=ComboType.AP).draw(
                        quad=digit_layout2, z=z, a=self.alpha.a2
                    )
                ActiveSkin.combo_number.get_sprite(combo=digit, combo_type=ComboType.AP).draw(
                    quad=digit_layout, z=z1, a=self.alpha.a
                )
            else:
                if not self.core.is_score:
                    ActiveSkin.combo_number.get_sprite(combo=digit, combo_type=ComboType.NORMAL).draw(
                        quad=digit_layout2, z=z, a=self.alpha.a2
                    )
                ActiveSkin.combo_number.get_sprite(combo=digit, combo_type=ComboType.NORMAL).draw(
                    quad=digit_layout, z=z1, a=self.alpha.a
                )


def draw_judgment_text(draw_time: float, sprite: Sprite):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.judgment.available:
        return
    if not Options.custom_judgment:
        return
    if time() >= draw_time + 0.5:
        return

    ui = runtime_ui()

    screen_center = Vec2(x=0, y=-1.17)

    h, w = FixedUiLayout.judgment_h, FixedUiLayout.judgment_w
    a = ui.judgment_config.alpha * unlerp_clamped(draw_time, draw_time + 0.064, time())
    s = unlerp_clamped(draw_time, draw_time + 0.064, time())
    layout = layout_center_ui(screen_center, w=w * s / 2, h=h * s / 2)
    sprite.draw(quad=layout, z=get_z_alt(LAYER_JUDGMENT).tuple, a=a)


def draw_judgment_accuracy(sprite: Sprite):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.accuracy_warning.available:
        return
    if not Options.custom_accuracy:
        return
    if not ActiveSkin.judgment.available:
        return
    if not Options.custom_judgment:
        return

    ui = runtime_ui()

    a = ui.judgment_config.alpha
    layout = FixedUiLayout.judgment_accuracy
    sprite.draw(quad=layout, z=LAYER_JUDGMENT, a=a)


def draw_damage_flash(draw_time: float):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.damage_flash.is_available:
        return
    if not Options.custom_damage:
        return

    t = unlerp_clamped(draw_time, draw_time + 0.35, time())
    a = 0.768 * t**0.1 * (1 - t) ** 1.35

    for k in range(len(FixedUiLayout.damage_flash)):
        ActiveSkin.damage_flash.draw(quad=FixedUiLayout.damage_flash[k], z=LAYER_DAMAGE, a=a * 0.8)


def draw_life_number(number: int, z: ZIndex, alpha: float = 1.0):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.ui_number.available:
        return
    if not Options.custom_life_bar:
        return

    ui = runtime_ui()

    if number == 0:
        digit_count = 1
    else:
        digit_count = 0
        temp_n = number
        while temp_n > 0:
            temp_n = temp_n // 10
            digit_count += 1

    scale_ratio = min(1, aspect_ratio() / (16 / 9))

    bar_h_unscaled = (
        0.196 * ui.secondary_metric_config.scale
        if LevelConfig.ui_version == Version.v3
        else 0.23 * ui.secondary_metric_config.scale
    )
    bar_h_current = bar_h_unscaled * scale_ratio
    y_shift = (bar_h_unscaled - bar_h_current) / 2

    y_offset = 0
    margin_offset = 0
    h = 0
    w = 0
    digit_gap = 0
    match LevelConfig.ui_version:
        case Version.v3:
            margin_offset = 0.625
            y_offset = 0.04314
            h = 0.06141 * ui.secondary_metric_config.scale * scale_ratio
            w = h
            digit_gap = w * -0.3
        case Version.v1:
            margin_offset = 0.5
            y_offset = 0.06314
            h = 0.08141 * ui.secondary_metric_config.scale * scale_ratio
            w = h
            digit_gap = w * -0.4

    bar_base_w = 0.827
    final_scale = ui.secondary_metric_config.scale * scale_ratio
    current_bar_w = bar_base_w * final_scale

    bar_center_x = screen().r - UIMargin.life_bar_x * scale_ratio - (current_bar_w / 2)
    number_center_x = bar_center_x + (margin_offset * final_scale)

    center_y = UIMargin.life_bar_y + (y_offset * final_scale) + y_shift

    screen_center = Vec2(x=number_center_x - (current_bar_w / 2), y=center_y)

    if LevelConfig.ui_version == Version.v3:
        unit = hud.hud_unit(aspect_ratio()) * ui.secondary_metric_config.scale
        w = h = 0.48 * 0.63 * unit
        digit_gap = 0.325 * 0.63 * unit - w
        screen_center @= v3_hud_anchor(True) + Vec2(-0.61 - 0.666, -0.602 + 0.3584) * unit
        screen_center.x += w / 2

    drawing_ui = UILayout(
        core=UICoreConfig(number, digit_count, mode=UIMode.LIFE),
        common=CommonConfig(
            center_x=screen_center.x,
            center_y=screen_center.y,
        ),
        layout=UILayoutConfig(width=w, gap=digit_gap, height=h, start_x=screen_center.x, alignment=UIAlignment.RIGHT),
    )
    drawing_ui.draw_number(z=z, a=alpha)


def draw_score_bar_number(number: int, z: ZIndex, alpha: float = 1.0):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.ui_number.available:
        return
    if not Options.custom_score_bar:
        return

    ui = runtime_ui()

    if number == 0:
        digit_count = 1
    else:
        digit_count = 0
        temp_n = number
        while temp_n > 0:
            temp_n = temp_n // 10
            digit_count += 1

    scale_ratio = min(1, aspect_ratio() / (16 / 9))

    bar_h_unscaled = (
        0.27 * ui.primary_metric_config.scale
        if LevelConfig.ui_version == Version.v3
        else 0.32 * ui.primary_metric_config.scale
    )
    bar_h_current = bar_h_unscaled * scale_ratio
    y_shift = (bar_h_unscaled - bar_h_current) / 2

    margin_offset = 0
    y_offset = 0
    h = 0
    w = 0
    digit_gap = 0
    match LevelConfig.ui_version:
        case Version.v3:
            margin_offset = 1.02
            y_offset = -0.077
            h = 0.0913 * ui.primary_metric_config.scale * scale_ratio
            w = h
            digit_gap = w * -0.3
        case Version.v1:
            margin_offset = 1.025
            y_offset = -0.07
            h = 0.14141 * ui.primary_metric_config.scale * scale_ratio
            w = h
            digit_gap = w * -0.5

    bar_base_w = 0.27 * 4.6
    final_scale = ui.primary_metric_config.scale * scale_ratio
    current_bar_w = bar_base_w * final_scale

    bar_center_x = screen().l + UIMargin.score_bar_x * scale_ratio + (current_bar_w / 2)
    number_center_x = bar_center_x - (margin_offset * final_scale)

    center_y = UIMargin.score_bar_y + (y_offset * final_scale) + y_shift

    screen_center = Vec2(x=number_center_x + (current_bar_w / 2), y=center_y)

    alignment = UIAlignment.LEFT
    if LevelConfig.ui_version == Version.v3:
        unit = hud.hud_unit(aspect_ratio()) * ui.primary_metric_config.scale
        w = h = 0.48 * 0.94 * unit
        digit_gap = 0.305 * unit - w
        screen_center @= (
            v3_hud_anchor() + Vec2(3.7862 - 0.067200184 - 0.029999971, -0.42 - 0.2470001 - 0.26999998) * unit
        )
        screen_center.x += w / 2
        alignment = UIAlignment.RIGHT

    drawing_ui = UILayout(
        core=UICoreConfig(number, digit_count, mode=UIMode.SCORE_BAR),
        common=CommonConfig(
            center_x=screen_center.x,
            center_y=screen_center.y,
        ),
        layout=UILayoutConfig(width=w, gap=digit_gap, height=h, start_x=screen_center.x, alignment=alignment),
    )
    drawing_ui.draw_number(z=z, a=alpha)


def draw_score_bar_raw_number(number: int, z: ZIndex, time: float, alpha: float = 1.0):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.ui_number.available:
        return
    if not Options.custom_score_bar:
        return
    if time > 1:
        return
    if number == 0:
        return

    ui = runtime_ui()

    if number == 0:
        digit_count = 1
    else:
        digit_count = 0
        temp_n = number
        while temp_n > 0:
            temp_n = temp_n // 10
            digit_count += 1

    scale_ratio = min(1, aspect_ratio() / (16 / 9))

    bar_h_unscaled = (
        0.27 * ui.primary_metric_config.scale
        if LevelConfig.ui_version == Version.v3
        else 0.32 * ui.primary_metric_config.scale
    )
    bar_h_current = bar_h_unscaled * scale_ratio
    y_shift = (bar_h_unscaled - bar_h_current) / 2

    margin_offset = 0
    y_offset = 0
    h = 0
    w = 0
    digit_gap = 0
    match LevelConfig.ui_version:
        case Version.v3:
            margin_offset = 0.56 + (0.492 - 0.56) * clamp(time / 0.2, 0, 1)
            y_offset = -0.10
            h = 0.06 * ui.primary_metric_config.scale * scale_ratio
            w = h
            digit_gap = w * -0.3
        case Version.v1:
            margin_offset = 0.51 + (0.442 - 0.51) * clamp(time / 0.2, 0, 1)
            y_offset = -0.085
            h = 0.09 * ui.primary_metric_config.scale * scale_ratio
            w = h
            digit_gap = w * -0.5

    bar_base_w = 0.27 * 4.6
    final_scale = ui.primary_metric_config.scale * scale_ratio
    current_bar_w = bar_base_w * final_scale

    bar_center_x = screen().l + UIMargin.score_bar_x * scale_ratio + (current_bar_w / 2)
    number_center_x = bar_center_x - (margin_offset * final_scale)

    center_y = UIMargin.score_bar_y + (y_offset * final_scale) + y_shift

    screen_center = Vec2(x=number_center_x + (current_bar_w / 2), y=center_y)

    if LevelConfig.ui_version == Version.v3:
        screen_center @= v3_align_bar_point(screen_center, False)
        factor = (128 / (108 * 0.9)) / (5 * 0.27)
        w *= factor
        h *= factor
        digit_gap *= factor

    drawing_ui = UILayout(
        core=UICoreConfig(number, digit_count, mode=UIMode.SCORE_ADD),
        common=CommonConfig(
            center_x=screen_center.x,
            center_y=screen_center.y,
        ),
        layout=UILayoutConfig(width=w, gap=digit_gap, height=h, start_x=screen_center.x, alignment=UIAlignment.LEFT),
    )
    a = clamp(time / 0.2, 0, 1) * alpha
    drawing_ui.draw_number(z=z, a=a)


class UIMode(IntEnum):
    LIFE = 0
    SCORE_BAR = 1
    SCORE_ADD = 2


class UIAlignment(IntEnum):
    LEFT = 0
    RIGHT = 1
    CENTER = 2


class UICoreConfig(Record):
    number: int
    digit_count: int
    mode: UIMode


class UILayoutConfig(Record):
    width: float
    gap: float
    height: float
    start_x: float
    alignment: int


class UILayout(Record):
    core: UICoreConfig
    common: CommonConfig
    layout: UILayoutConfig

    def layout_combo_number(self, l: float, r: float, t: float, b: float) -> Quad:
        return Quad(
            bl=Vec2(l, b),
            br=Vec2(r, b),
            tl=Vec2(l, t),
            tr=Vec2(r, t),
        )

    def draw_number(self, z, a: float = 1):
        s_inv = 0

        item_count = self.core.digit_count
        if self.core.mode == UIMode.SCORE_BAR:
            item_count = 8
        elif self.core.mode == UIMode.SCORE_ADD:
            item_count = self.core.digit_count + 1

        total_width = 0
        if item_count > 0:
            total_width = item_count * self.layout.width + (item_count - 1) * self.layout.gap

        base_x = self.layout.start_x

        if self.layout.alignment == UIAlignment.RIGHT:
            base_x = self.layout.start_x - total_width
        elif self.layout.alignment == UIAlignment.CENTER:
            base_x = self.layout.start_x - total_width / 2

        fit_score_ink = LevelConfig.ui_version == Version.v3 and self.core.mode == UIMode.SCORE_BAR
        ink_cursor = base_x
        ink_gap = self.layout.width * font_metrics.SCORE_INK_GAP
        if fit_score_ink:
            ink_total = (item_count - 1) * ink_gap
            for i in range(item_count):
                digit = int(floor(self.core.number / 10 ** (7 - i)) % 10)
                ink_total += self.layout.width * (
                    font_metrics.METRIC_INK_RIGHT[digit] - font_metrics.METRIC_INK_LEFT[digit]
                )
            # Stable visible right edge; a narrow trailing '1' must not move it.
            ink_cursor = (
                self.layout.start_x
                - self.layout.width / 2
                + self.layout.width * font_metrics.METRIC_INK_RIGHT[0]
                - ink_total
            )

        for i in range(item_count):
            digit = 0

            if self.core.mode == UIMode.SCORE_BAR:
                power_of_ten = 10 ** (7 - i)

                if self.core.number < power_of_ten and i < 7:
                    digit = 10  # 'special 0'
                else:
                    digit = floor(self.core.number / power_of_ten) % 10

            elif self.core.mode == UIMode.SCORE_ADD:
                if i == 0:
                    digit = 11  # '+'
                else:
                    real_i = i - 1
                    digit = floor(self.core.number / 10 ** (self.core.digit_count - 1 - real_i)) % 10

            else:  # UIMode.LIFE
                digit = floor(self.core.number / 10 ** (self.core.digit_count - 1 - i)) % 10

            final_draw_w = self.layout.width

            digit_center_x = base_x + (i * (self.layout.width + self.layout.gap)) + self.layout.width / 2
            metric_digit = 0 if digit == 10 else digit
            if fit_score_ink:
                digit_center_x = ink_cursor - self.layout.width * font_metrics.METRIC_INK_LEFT[metric_digit]
                ink_cursor += (
                    self.layout.width
                    * (font_metrics.METRIC_INK_RIGHT[metric_digit] - font_metrics.METRIC_INK_LEFT[metric_digit])
                    + ink_gap
                )

            unscaled_t = self.common.center_y + self.layout.height / 2
            unscaled_b = self.common.center_y - self.layout.height / 2

            if LevelConfig.ui_version == Version.v3 and metric_digit < 10:
                digit_center_x += self.layout.width * font_metrics.METRIC_DX[metric_digit]
                center_y = self.common.center_y + self.layout.height * font_metrics.METRIC_DY[metric_digit]
                final_draw_w *= font_metrics.METRIC_W[metric_digit]
                height = self.layout.height * font_metrics.METRIC_H[metric_digit]
                unscaled_t = center_y + height / 2
                unscaled_b = center_y - height / 2

            l = (digit_center_x - final_draw_w / 2) + s_inv * self.common.center_x
            r = (digit_center_x + final_draw_w / 2) + s_inv * self.common.center_x
            t = unscaled_t + s_inv * self.common.center_y
            b = unscaled_b + s_inv * self.common.center_y

            digit_layout = self.layout_combo_number(l=l, r=r, t=t, b=b)
            if self.core.mode == UIMode.LIFE:
                ActiveSkin.life.number.get_sprite(number=digit).draw(quad=digit_layout, z=z, a=a)
            else:
                ActiveSkin.ui_number.get_sprite(number=digit).draw(quad=digit_layout, z=z, a=a)
