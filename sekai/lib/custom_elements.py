from enum import IntEnum
from math import cos, floor, pi

from sonolus.script.bucket import Judgment, JudgmentWindow
from sonolus.script.interval import Interval, clamp, unlerp, unlerp_clamped
from sonolus.script.record import Record
from sonolus.script.runtime import aspect_ratio, is_replay, is_watch, runtime_ui, screen, time
from sonolus.script.vec import Vec2

from sekai.lib.layout import (
    SCORE_BAR_BASE_Y,
    ComboType,
    Quad,
    layout_combo_label,
    transform_fixed_size,
    transform_quad,
)
from sekai.lib.options import Options
from sekai.lib.skin import (
    ActiveSkin,
)


def draw_combo_label(ap: bool, z: float, z1: float, combo: int):
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

    screen_center = Vec2(x=5.337, y=0.485)

    base_h = 0.04225 * ui.combo_config.scale
    base_w = base_h * 3.22 * 6.65
    h, w = transform_fixed_size(base_h, base_w)
    a = ui.combo_config.alpha * 0.8 * (cos(time() * pi) + 1) / 2
    layout = layout_combo_label(screen_center, w=w / 2, h=h / 2)
    if ap or not Options.ap_effect:
        ActiveSkin.combo_label.get_sprite(ComboType.NORMAL).draw(quad=layout, z=z1, a=ui.combo_config.alpha)
    else:
        ActiveSkin.combo_label.get_sprite(ComboType.AP).draw(quad=layout, z=z1, a=ui.combo_config.alpha)
        ActiveSkin.combo_label.get_sprite(ComboType.GLOW).draw(quad=layout, z=z, a=a)


def draw_combo_number(draw_time: float, ap: bool, combo: int, z: float, z1: float, z2: float):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.combo_number.available:
        return
    if is_watch() and Options.auto_judgment and not is_replay():
        return
    if not Options.custom_combo:
        return
    if combo == 0:
        return

    ui = runtime_ui()

    if combo == 0:
        digit_count = 1
    else:
        digit_count = 0
        temp_n = combo
        while temp_n > 0:
            temp_n = temp_n // 10
            digit_count += 1

    screen_center = Vec2(x=5.337, y=0.585)

    base_h = 0.1222 * ui.combo_config.scale
    base_h2 = 0.15886 * ui.combo_config.scale
    base_w = base_h * 0.79 * 7
    base_w2 = base_h2 * 0.79 * 7

    s = 0.6 + 0.4 * unlerp_clamped(draw_time, draw_time + 0.112, time())
    s2 = 0.762 + 0.231 * unlerp_clamped(draw_time + 0.112, draw_time + 0.192, time())

    a = ui.combo_config.alpha
    a2 = (
        ui.combo_config.alpha * unlerp(draw_time + 0.192, draw_time + 0.112, time())
        if time() >= draw_time + 0.112
        else 0
    )
    a3 = ui.combo_config.alpha * 0.8 * (cos(time() * pi) + 1) / 2

    h, w = transform_fixed_size(base_h, base_w)
    h2, w2 = transform_fixed_size(base_h2, base_w2)

    digit_gap = w * (0.24 + Options.combo_distance)
    digit_gap2 = w2 * (0.24 + Options.combo_distance)
    total_width = digit_count * w + (digit_count - 1) * digit_gap
    total_width2 = digit_count * w2 + (digit_count - 1) * digit_gap2
    start_x = screen_center.x - total_width / 2
    start_x2 = screen_center.x - total_width2 / 2

    drawing_combo = ComboNumberLayout(
        core=CoreConfig(
            ap=ap,
            combo_number=combo,
            digit_count=digit_count,
            is_score=False,
        ),
        design=ScoreDesignConfig(s_int=1, s_dot=1, s_dec=1, g_dec=1),
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
            width=w,
            gap=digit_gap,
            scale=s,
            height=h,
            start_x=start_x,
        ),
        layout2=LayoutConfig(
            width=w2,
            gap=digit_gap2,
            scale=s2,
            height=h2,
            start_x=start_x2,
        ),
    )
    drawing_combo.draw_number(z=z, z1=z1, z2=z2)


def draw_score_number(ap: bool, score: float, z1: float, z2: float):
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

    screen_center = Vec2(x=5.337, y=0.39)

    base_h = 0.1222 * ui.combo_config.scale * 0.4
    base_w = base_h * 0.79 * 7

    s = 1.0

    a = ui.combo_config.alpha
    a3 = ui.combo_config.alpha * 0.8 * (cos(time() * pi) + 1) / 2

    h, w = transform_fixed_size(base_h, base_w)

    digit_gap = w * (0.24 + Options.combo_distance)

    s_int = 1.0
    s_dot = 0.5
    s_dec = 0.6
    g_dec = 0.9

    count_large = n_int + 2
    count_dot = 1
    count_small = 3

    total_w_factor = (count_large * s_int) + (count_dot * s_dot) + (count_small * s_dec)
    total_gap_factor = (count_large * s_int) + (count_dot * s_dot) + (count_small * g_dec) - g_dec

    total_width = (total_w_factor * w) + (total_gap_factor * digit_gap)

    start_x = screen_center.x - total_width / 2

    drawing_combo = ComboNumberLayout(
        core=CoreConfig(
            ap=ap,
            combo_number=score,
            digit_count=digit_count,
            is_score=True,
        ),
        design=ScoreDesignConfig(s_int=s_int, s_dot=s_dot, s_dec=s_dec, g_dec=g_dec),
        common=CommonConfig(
            center_x=screen_center.x,
            center_y=screen_center.y,
        ),
        alpha=AlphaConfig(a=a, a2=0, a3=a3),
        layout1=LayoutConfig(width=w, gap=digit_gap, scale=s, height=h, start_x=start_x),
        layout2=LayoutConfig(width=0, gap=0, scale=0, height=0, start_x=0),
    )
    drawing_combo.draw_number(z=0, z1=z1, z2=z2)


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
    g_dec: float


class ComboNumberLayout(Record):
    core: CoreConfig
    design: ScoreDesignConfig
    common: CommonConfig
    alpha: AlphaConfig
    layout1: LayoutConfig
    layout2: LayoutConfig

    def layout_combo_number(self, l: float, r: float, t: float, b: float) -> Quad:
        return transform_quad(
            Quad(
                bl=Vec2(l, b),
                br=Vec2(r, b),
                tl=Vec2(l, t),
                tr=Vec2(r, t),
            )
        )

    def draw_number(self, z, z1, z2):
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
                    gap_factor = self.design.s_int
                    layout_scale_factor = self.design.s_int
                elif i == n_int:
                    digit = 10  # Dot(.)
                    scale_factor = self.design.s_int
                    gap_factor = self.design.s_dot
                    layout_scale_factor = self.design.s_dot
                elif i == n_int + 1 or i == n_int + 2:
                    decimal_idx = i - n_int
                    digit = floor(self.core.combo_number * (10**decimal_idx)) % 10
                    scale_factor = self.design.s_int
                    gap_factor = self.design.s_int
                    layout_scale_factor = self.design.s_int
                elif i == n_int + 3 or i == n_int + 4:
                    decimal_idx = i - n_int
                    digit = floor(self.core.combo_number * (10**decimal_idx)) % 10
                    scale_factor = self.design.s_dec
                    gap_factor = self.design.g_dec
                    layout_scale_factor = self.design.s_dec
                elif i == n_int + 5:
                    digit = 11  # Percent(%)
                    scale_factor = self.design.s_dec
                    gap_factor = self.design.g_dec
                    layout_scale_factor = self.design.s_dec

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
                digit = floor(self.core.combo_number / 10 ** (self.core.digit_count - 1 - i)) % 10

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

            if not self.core.ap and Options.ap_effect:
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


def draw_judgment_text(
    draw_time: float, judgment: Judgment, windows_bad: Interval, accuracy: float, check_pass: bool, z: float
):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.judgment.available:
        return
    if not Options.custom_judgment:
        return
    if time() >= draw_time + 0.5:
        return

    ui = runtime_ui()

    screen_center = Vec2(x=0, y=0.792)

    base_h = 0.09 * ui.combo_config.scale
    base_w = base_h * 27.3
    h, w = transform_fixed_size(base_h, base_w)
    a = ui.judgment_config.alpha * unlerp_clamped(draw_time, draw_time + 0.064, time())
    s = unlerp_clamped(draw_time, draw_time + 0.064, time())
    layout = layout_combo_label(screen_center, w=w * s / 2, h=h * s / 2)
    ActiveSkin.judgment.get_sprite(
        judgment_type=judgment, windows_bad=windows_bad, accuracy=accuracy, check_pass=check_pass
    ).draw(quad=layout, z=z, a=a)


def draw_judgment_accuracy(judgment: Judgment, accuracy: float, windows: JudgmentWindow, wrong_way: bool, z: float):
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

    screen_center = Vec2(x=0, y=0.723)

    base_h = 0.054 * 1.3 * ui.judgment_config.scale
    base_w = base_h * 23.6
    h, w = transform_fixed_size(base_h, base_w)
    a = ui.judgment_config.alpha
    layout = layout_combo_label(screen_center, w=w / 2, h=h / 2)
    ActiveSkin.accuracy_warning.get_sprite(
        judgment=judgment,
        windows=windows.perfect,
        accuracy=accuracy,
        wrong_way=wrong_way,
    ).draw(quad=layout, z=z, a=a)


def draw_damage_flash(draw_time: float, z: float):
    if Options.hide_ui >= 2:
        return
    if not ActiveSkin.damage_flash.is_available:
        return
    if not Options.custom_damage:
        return

    t = unlerp_clamped(draw_time, draw_time + 0.35, time())
    a = 0.768 * t**0.1 * (1 - t) ** 1.35

    for i in range(2):
        for j in range(2):
            l_val = screen().l if j == 0 else screen().r
            if i == 0:
                t_val = screen().t
            else:
                t_val = screen().b
            layout = Quad(
                bl=Vec2(l_val, 0),
                br=Vec2(0, 0),
                tl=Vec2(l_val, t_val),
                tr=Vec2(0, t_val),
            )
            ActiveSkin.damage_flash.draw(quad=layout, z=z, a=a * 0.8)


def draw_life_number(number: int, z: float):
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
    MARGIN = 0.28 if Options.version == 0 else 0.275  # noqa: N806
    LIFE_BAR_BASE_Y = 0.887 if Options.version == 0 else 0.875  # noqa: N806

    y_offset = 0
    margin_offset = 0
    h = 0
    w = 0
    digit_gap = 0
    match Options.version:
        case 0:
            margin_offset = 0.61
            y_offset = 0.04314
            h = 0.06141 * ui.secondary_metric_config.scale * scale_ratio
            w = h * 0.714
            digit_gap = w * (-0.04 + Options.combo_distance)
        case 1:
            margin_offset = 0.55
            y_offset = 0.06314
            h = 0.08141 * ui.secondary_metric_config.scale * scale_ratio
            w = h * 0.714
            digit_gap = w * (-0.1 + Options.combo_distance)

    bar_base_w = 0.827
    final_scale = ui.secondary_metric_config.scale * scale_ratio
    current_bar_w = bar_base_w * final_scale

    bar_center_x = screen().r - MARGIN - (current_bar_w / 2)
    number_center_x = bar_center_x + (margin_offset * final_scale)

    center_y = LIFE_BAR_BASE_Y + (y_offset * final_scale)

    screen_center = Vec2(x=number_center_x - (current_bar_w / 2), y=center_y)

    drawing_ui = UILayout(
        core=UICoreConfig(number, digit_count, mode=UIMode.LIFE),
        common=CommonConfig(
            center_x=screen_center.x,
            center_y=screen_center.y,
        ),
        layout=UILayoutConfig(width=w, gap=digit_gap, height=h, start_x=screen_center.x, alignment=UIAlignment.RIGHT),
    )
    drawing_ui.draw_number(z=z)


def draw_score_bar_number(number: int, z: float):
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
    MARGIN = 0.3 if Options.version == 0 else 0.2  # noqa: N806

    margin_offset = 0
    y_offset = 0
    h = 0
    w = 0
    digit_gap = 0
    match Options.version:
        case 0:
            margin_offset = 1.02
            y_offset = -0.09
            h = 0.09141 * ui.primary_metric_config.scale * scale_ratio
            w = h * 0.705
            digit_gap = w * (-0.04 + Options.combo_distance)
        case 1:
            margin_offset = 1.025
            y_offset = -0.07
            h = 0.14141 * ui.primary_metric_config.scale * scale_ratio
            w = h * 0.705
            digit_gap = w * (-0.3 + Options.combo_distance)

    bar_base_w = 0.27 * 4.6
    final_scale = ui.primary_metric_config.scale * scale_ratio
    current_bar_w = bar_base_w * final_scale

    bar_center_x = screen().l + MARGIN + (current_bar_w / 2)
    number_center_x = bar_center_x - (margin_offset * final_scale)

    center_y = SCORE_BAR_BASE_Y + (y_offset * final_scale)

    screen_center = Vec2(x=number_center_x + (current_bar_w / 2), y=center_y)

    drawing_ui = UILayout(
        core=UICoreConfig(number, digit_count, mode=UIMode.SCORE_BAR),
        common=CommonConfig(
            center_x=screen_center.x,
            center_y=screen_center.y,
        ),
        layout=UILayoutConfig(width=w, gap=digit_gap, height=h, start_x=screen_center.x, alignment=UIAlignment.LEFT),
    )
    drawing_ui.draw_number(z=z)


def draw_score_bar_raw_number(number: int, z: float, time: float):
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
    MARGIN = 0.3 if Options.version == 0 else 0.2  # noqa: N806

    margin_offset = 0
    y_offset = 0
    h = 0
    w = 0
    digit_gap = 0
    match Options.version:
        case 0:
            margin_offset = 0.56 + (0.492 - 0.56) * clamp(time / 0.2, 0, 1)
            y_offset = -0.102
            h = 0.06 * ui.primary_metric_config.scale * scale_ratio
            w = h * 0.705
            digit_gap = w * (-0.04 + Options.combo_distance)
        case 1:
            margin_offset = 0.51 + (0.442 - 0.51) * clamp(time / 0.2, 0, 1)
            y_offset = -0.085
            h = 0.09 * ui.primary_metric_config.scale * scale_ratio
            w = h * 0.705
            digit_gap = w * (-0.3 + Options.combo_distance)

    bar_base_w = 0.27 * 4.6
    final_scale = ui.primary_metric_config.scale * scale_ratio
    current_bar_w = bar_base_w * final_scale

    bar_center_x = screen().l + MARGIN + (current_bar_w / 2)
    number_center_x = bar_center_x - (margin_offset * final_scale)

    center_y = SCORE_BAR_BASE_Y + (y_offset * final_scale)

    screen_center = Vec2(x=number_center_x + (current_bar_w / 2), y=center_y)

    drawing_ui = UILayout(
        core=UICoreConfig(number, digit_count, mode=UIMode.SCORE_ADD),
        common=CommonConfig(
            center_x=screen_center.x,
            center_y=screen_center.y,
        ),
        layout=UILayoutConfig(width=w, gap=digit_gap, height=h, start_x=screen_center.x, alignment=UIAlignment.LEFT),
    )
    a = clamp(time / 0.2, 0, 1)
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

    def draw_number(self, z, a=1):
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

            unscaled_t = self.common.center_y + self.layout.height / 2
            unscaled_b = self.common.center_y - self.layout.height / 2

            l = (digit_center_x - final_draw_w / 2) + s_inv * self.common.center_x
            r = (digit_center_x + final_draw_w / 2) + s_inv * self.common.center_x
            t = unscaled_t + s_inv * self.common.center_y
            b = unscaled_b + s_inv * self.common.center_y

            digit_layout = self.layout_combo_number(l=l, r=r, t=t, b=b)
            if self.core.mode == UIMode.LIFE:
                ActiveSkin.life.number.get_sprite(number=digit).draw(quad=digit_layout, z=z, a=a)
            else:
                ActiveSkin.ui_number.get_sprite(number=digit).draw(quad=digit_layout, z=z, a=a)
