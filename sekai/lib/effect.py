from sonolus.script.effect import Effect, StandardEffect, effect, effects

EMPTY_EFFECT = Effect(-1)


@effects
class Effects:
    stage: StandardEffect.STAGE

    normal_perfect: StandardEffect.PERFECT
    normal_great: StandardEffect.GREAT
    normal_good: StandardEffect.GOOD

    flick_perfect: StandardEffect.PERFECT_ALTERNATIVE
    flick_great: StandardEffect.GREAT_ALTERNATIVE
    flick_good: StandardEffect.GOOD_ALTERNATIVE

    normal_hold: StandardEffect.HOLD
    normal_tick: Effect = effect("Sekai Tick")

    critical_tap: Effect = effect("Sekai Critical Tap")
    critical_flick: Effect = effect("Sekai Critical Flick")
    critical_hold: Effect = effect("Sekai Critical Hold")
    critical_tick: Effect = effect("Sekai Critical Tick")

    normal_trace: Effect = effect("Sekai Trace")
    critical_trace: Effect = effect("Sekai Critical Trace")

    skill: Effect = effect("Sekai Skill")

SFX_DISTANCE = 0.0167


def first_available_effect(*args: Effect) -> Effect:
    result = +EMPTY_EFFECT
    for e in args:
        if e.is_available:
            result @= e
            break
    return result
