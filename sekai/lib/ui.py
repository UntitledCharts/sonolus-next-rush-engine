from sonolus.script.runtime import HorizontalAlign, is_play, is_preview, is_tutorial, is_watch, runtime_ui, safe_area
from sonolus.script.ui import (
    EaseType,
    UiAnimation,
    UiAnimationTween,
    UiConfig,
    UiJudgmentErrorPlacement,
    UiJudgmentErrorStyle,
    UiMetric,
    UiVisibility,
)
from sonolus.script.vec import Vec2

from sekai.lib.layout import Layout
from sekai.lib.options import Options
from sekai.lib.skin import ActiveSkin

ui_config = UiConfig(
    scope="Sekai",
    primary_metric=UiMetric.ARCADE,
    secondary_metric=UiMetric.LIFE,
    menu_visibility=UiVisibility(scale=1, alpha=1),
    judgment_visibility=UiVisibility(scale=1, alpha=1),
    combo_visibility=UiVisibility(scale=1, alpha=1),
    progress_visibility=UiVisibility(scale=1, alpha=1),
    primary_metric_visibility=UiVisibility(scale=1, alpha=1),
    secondary_metric_visibility=UiVisibility(scale=1, alpha=1),
    tutorial_navigation_visibility=UiVisibility(scale=1, alpha=1),
    tutorial_instruction_visibility=UiVisibility(scale=1, alpha=1),
    judgment_animation=UiAnimation(
        scale=UiAnimationTween(
            start=0,
            end=1,
            duration=0.075,
            ease=EaseType.LINEAR,
        ),
        alpha=UiAnimationTween(
            start=1,
            end=0,
            duration=0.3,
            ease=EaseType.NONE,
        ),
    ),
    combo_animation=UiAnimation(
        scale=UiAnimationTween(
            start=0.6,
            end=1,
            duration=0.15,
            ease=EaseType.LINEAR,
        ),
        alpha=UiAnimationTween(
            start=1,
            end=1,
            duration=0,
            ease=EaseType.LINEAR,
        ),
    ),
    judgment_error_style=UiJudgmentErrorStyle.LATE,
    judgment_error_placement=UiJudgmentErrorPlacement.TOP,
    judgment_error_min=20,
)


def init_ui():
    ui = runtime_ui()

    gap = 0.05
    box = safe_area().shrink(Vec2(gap, gap))
    min_x_extent = min(box.r, -box.l)
    box.r = min_x_extent
    box.l = -min_x_extent
    show_ui = not Options.hide_ui
    custom_combo_label = not Options.custom_combo or not ActiveSkin.combo_label.available
    custom_combo_number = not Options.custom_combo or not ActiveSkin.combo_number.available
    custom_judgment = not Options.custom_judgment or not ActiveSkin.judgment.available
    custom_life_bar = not Options.custom_life_bar or not ActiveSkin.life.available or is_preview() or is_tutorial()
    custom_life_bar_margin = Vec2(0.26, 0) if is_play() or is_watch() else Vec2(0, 0)
    custom_score_bar = not Options.custom_score_bar or not ActiveSkin.score.available or is_preview() or is_tutorial()

    ui.menu.update(
        anchor=box.tr - custom_life_bar_margin,
        pivot=Vec2(1, 1),
        dimensions=Vec2(0.15, 0.15) * ui.menu_config.scale,
        alpha=ui.menu_config.alpha * show_ui * custom_life_bar,
        horizontal_align=HorizontalAlign.CENTER,
        background=True,
    )
    ui.primary_metric_bar.update(
        anchor=box.tl + custom_life_bar_margin,
        pivot=Vec2(0, 1),
        dimensions=Vec2(0.75, 0.15) * ui.primary_metric_config.scale,
        alpha=ui.primary_metric_config.alpha * show_ui * custom_score_bar,
        horizontal_align=HorizontalAlign.LEFT,
        background=True,
    )
    ui.primary_metric_value.update(
        anchor=box.tl + custom_life_bar_margin + Vec2(0.715, -0.035) * ui.primary_metric_config.scale,
        pivot=Vec2(1, 1),
        dimensions=Vec2(0, 0.08) * ui.primary_metric_config.scale,
        alpha=ui.primary_metric_config.alpha * show_ui * custom_score_bar,
        horizontal_align=HorizontalAlign.RIGHT,
        background=False,
    )
    ui.secondary_metric_bar.update(
        anchor=box.tr - Vec2(gap, 0) - custom_life_bar_margin - Vec2(0.15, 0) * ui.menu_config.scale,
        pivot=Vec2(1, 1),
        dimensions=Vec2(0.55, 0.15) * ui.secondary_metric_config.scale,
        alpha=ui.secondary_metric_config.alpha * show_ui * custom_life_bar,
        horizontal_align=HorizontalAlign.LEFT,
        background=True,
    )
    ui.secondary_metric_value.update(
        anchor=box.tr
        - Vec2(gap, 0)
        - custom_life_bar_margin
        - Vec2(0.15, 0) * ui.menu_config.scale
        - Vec2(0.035, 0.035) * ui.secondary_metric_config.scale,
        pivot=Vec2(1, 1),
        dimensions=Vec2(0, 0.08) * ui.secondary_metric_config.scale,
        alpha=ui.secondary_metric_config.alpha * show_ui * custom_life_bar,
        horizontal_align=HorizontalAlign.RIGHT,
        background=False,
    )
    ui.combo_value.update(
        anchor=Vec2(Layout.field_w * 0.35, Layout.field_h * 0.0875),
        pivot=Vec2(0.5, 0.7),
        dimensions=Vec2(0, Layout.field_h * 0.14 * 0.9) * ui.combo_config.scale,
        alpha=ui.combo_config.alpha * show_ui * custom_combo_number,
        horizontal_align=HorizontalAlign.CENTER,
        background=False,
    )
    ui.combo_text.update(
        anchor=Vec2(Layout.field_w * 0.35, Layout.field_h * 0.0875),
        pivot=Vec2(0.5, -2.1),
        dimensions=Vec2(0, Layout.field_h * 0.14 * 0.175) * ui.combo_config.scale,
        alpha=ui.combo_config.alpha * show_ui * custom_combo_label,
        horizontal_align=HorizontalAlign.CENTER,
        background=False,
    )
    ui.judgment.update(
        anchor=Vec2(0, Layout.field_h * -0.115),
        pivot=Vec2(0.5, 0.55),
        dimensions=Vec2(0, Layout.field_h * 0.04) * ui.judgment_config.scale,
        alpha=ui.judgment_config.alpha * show_ui * custom_judgment,
        horizontal_align=HorizontalAlign.CENTER,
        background=False,
    )
    ui.progress.update(
        anchor=box.bl,
        pivot=Vec2(0, 0),
        dimensions=Vec2(box.w, 0.15 * ui.progress_config.scale),
        alpha=ui.progress_config.alpha * show_ui,
        horizontal_align=HorizontalAlign.CENTER,
        background=True,
    )
    ui.progress_graph.update(
        anchor=box.bl + Vec2(0, gap + 0.15 * ui.progress_config.scale),
        pivot=Vec2(0, 0),
        dimensions=Vec2(box.w, 0.3 * ui.progress_config.scale),
        alpha=ui.progress_config.alpha * show_ui,
        horizontal_align=HorizontalAlign.CENTER,
        background=True,
    )
    ui.previous.update(
        anchor=Vec2(box.l, box.center.y),
        pivot=Vec2(0, 0.5),
        dimensions=Vec2(0.15, 0.15) * ui.navigation_config.scale,
        alpha=ui.navigation_config.alpha,
        background=True,
    )
    ui.next.update(
        anchor=Vec2(box.r, box.center.y),
        pivot=Vec2(1, 0.5),
        dimensions=Vec2(0.15, 0.15) * ui.navigation_config.scale,
        alpha=ui.navigation_config.alpha,
        background=True,
    )
    ui.instruction.update(
        anchor=Vec2(0, 0.4),
        pivot=Vec2(0.5, 0.5),
        dimensions=Vec2(1.2, 0.15) * ui.instruction_config.scale,
        alpha=ui.instruction_config.alpha,
        background=True,
    )
