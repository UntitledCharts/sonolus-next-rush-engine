from sonolus.script.array import Array, Dim
from sonolus.script.bucket import Judgment
from sonolus.script.globals import level_data
from sonolus.script.particle import Particle, ParticleGroup, StandardParticle, particle, particle_group, particles
from sonolus.script.record import Record

from sekai.lib.note_style import NoteStyle, NoteVisualFamily
from sekai.lib.options import Version

PARTICLE_COLORS = ("Neutral", "Red", "Green", "Blue", "Yellow", "Purple", "Cyan", "Black")


@particles
class BaseParticles:
    lane: StandardParticle.LANE_LINEAR

    normal_note_lane_linear: Particle = particle("Sekai Note Lane Linear")
    normal_slide_note_lane_linear: Particle = particle("Sekai Slide Lane Linear")
    normal_flick_note_lane_linear: Particle = particle("Sekai Flick Lane Linear")
    normal_down_flick_note_lane_linear: Particle = particle("Sekai Down Flick Lane Linear")
    critical_note_lane_linear: Particle = particle("Sekai Critical Lane Linear")
    critical_slide_note_lane_linear: Particle = particle("Sekai Critical Slide Lane Linear")
    critical_flick_note_lane_linear: Particle = particle("Sekai Critical Flick Lane Linear")
    critical_down_flick_note_lane_linear: Particle = particle("Sekai Critical Down Flick Lane Linear")

    note_circular_cyan: StandardParticle.NOTE_CIRCULAR_TAP_CYAN
    note_circular_cyan_great: Particle = particle("Sekai Circular Tap Cyan Great")
    note_circular_cyan_good: Particle = particle("Sekai Circular Tap Cyan Good")
    note_linear_cyan: StandardParticle.NOTE_LINEAR_TAP_CYAN
    note_linear_cyan_great: Particle = particle("Sekai Linear Tap Cyan Great")
    note_linear_cyan_good: Particle = particle("Sekai Linear Tap Cyan Good")
    note_slot_linear_cyan: Particle = particle("Sekai Slot Linear Tap Cyan")
    note_slot_linear_cyan_great: Particle = particle("Sekai Slot Linear Tap Cyan Great")
    note_slot_linear_cyan_good: Particle = particle("Sekai Slot Linear Tap Cyan Good")

    note_circular_green: StandardParticle.NOTE_CIRCULAR_TAP_GREEN
    note_linear_green: StandardParticle.NOTE_LINEAR_TAP_GREEN
    note_slot_linear_green: Particle = particle("Sekai Slot Linear Tap Green")

    note_circular_red: StandardParticle.NOTE_CIRCULAR_TAP_RED
    note_linear_red: StandardParticle.NOTE_LINEAR_TAP_RED
    note_slot_linear_alternative_red: Particle = particle("Sekai Slot Linear Alternative Red")
    note_directional_red: StandardParticle.NOTE_LINEAR_ALTERNATIVE_RED

    trace_note_circular_green: Particle = particle("Sekai Trace Note Circular Green")
    trace_note_linear_green: Particle = particle("Sekai Trace Note Linear Green")

    note_circular_yellow: StandardParticle.NOTE_CIRCULAR_TAP_YELLOW
    note_linear_yellow: StandardParticle.NOTE_LINEAR_TAP_YELLOW
    note_slot_linear_yellow: Particle = particle("Sekai Slot Linear Tap Yellow")

    note_circular_slide_yellow: Particle = particle("Sekai Critical Slide Circular Yellow")
    note_linear_slide_yellow: Particle = particle("Sekai Critical Slide Linear Yellow")
    note_slot_linear_slide_yellow: Particle = particle("Sekai Slot Linear Slide Tap Yellow")

    note_circular_flick_yellow: Particle = particle("Sekai Critical Flick Circular Yellow")
    note_linear_flick_yellow: Particle = particle("Sekai Critical Flick Linear Yellow")
    note_slot_linear_flick_yellow: Particle = particle("Sekai Slot Linear Alternative Yellow")
    note_directional_yellow: StandardParticle.NOTE_LINEAR_ALTERNATIVE_YELLOW

    trace_note_circular_yellow: Particle = particle("Sekai Trace Note Circular Yellow")
    trace_note_linear_yellow: Particle = particle("Sekai Trace Note Linear Yellow")

    slide_tick_note_circular_green: StandardParticle.NOTE_CIRCULAR_ALTERNATIVE_GREEN

    slide_tick_note_circular_yellow: StandardParticle.NOTE_CIRCULAR_ALTERNATIVE_YELLOW

    slide_connector_circular_green: StandardParticle.NOTE_CIRCULAR_HOLD_GREEN
    slide_connector_linear_green: StandardParticle.NOTE_LINEAR_HOLD_GREEN
    slide_connector_trail_linear_green: Particle = particle("Sekai Normal Slide Trail Linear")
    slide_connector_slot_linear_green: Particle = particle("Sekai Slot Linear Slide Green")

    slide_connector_circular_yellow: StandardParticle.NOTE_CIRCULAR_HOLD_YELLOW
    slide_connector_linear_yellow: StandardParticle.NOTE_LINEAR_HOLD_YELLOW
    slide_connector_trail_linear_yellow: Particle = particle("Sekai Critical Slide Trail Linear")
    slide_connector_slot_linear_yellow: Particle = particle("Sekai Slot Linear Slide Yellow")

    note_circular_purple: StandardParticle.NOTE_CIRCULAR_TAP_PURPLE
    note_linear_purple: StandardParticle.NOTE_LINEAR_TAP_PURPLE

    normal_note_circular: Particle = particle("Sekai Normal Note Circular")
    normal_note_linear: Particle = particle("Sekai Normal Note Linear")
    normal_note_slot_linear: Particle = particle("Sekai Normal Note Slot Linear")

    slide_note_circular: Particle = particle("Sekai Slide Note Circular")
    slide_note_linear: Particle = particle("Sekai Slide Note Linear")
    slide_note_slot_linear: Particle = particle("Sekai Slide Note Slot Linear")

    flick_note_circular: Particle = particle("Sekai Flick Note Circular")
    flick_note_linear: Particle = particle("Sekai Flick Note Linear")
    flick_note_slot_linear: Particle = particle("Sekai Flick Note Slot Linear")

    flick_note_directional: Particle = particle("Sekai Flick Note Directional")

    down_flick_note_circular: Particle = particle("Sekai Down Flick Note Circular")
    down_flick_note_linear: Particle = particle("Sekai Down Flick Note Linear")
    down_flick_note_slot_linear: Particle = particle("Sekai Down Flick Note Slot Linear")

    down_flick_note_directional: Particle = particle("Sekai Down Flick Note Directional")

    trace_note_circular: Particle = particle("Sekai Trace Note Circular")
    trace_note_linear: Particle = particle("Sekai Trace Note Linear")

    critical_note_circular: Particle = particle("Sekai Critical Note Circular")
    critical_note_linear: Particle = particle("Sekai Critical Note Linear")
    critical_note_slot_linear: Particle = particle("Sekai Critical Note Slot Linear")

    critical_slide_note_circular: Particle = particle("Sekai Critical Slide Note Circular")
    critical_slide_note_linear: Particle = particle("Sekai Critical Slide Note Linear")
    critical_slide_note_slot_linear: Particle = particle("Sekai Critical Slide Note Slot Linear")

    critical_flick_note_circular: Particle = particle("Sekai Critical Flick Note Circular")
    critical_flick_note_linear: Particle = particle("Sekai Critical Flick Note Linear")
    critical_flick_note_slot_linear: Particle = particle("Sekai Critical Flick Note Slot Linear")

    critical_note_directional: Particle = particle("Sekai Critical Note Directional")

    critical_down_flick_note_circular: Particle = particle("Sekai Critical Down Flick Note Circular")
    critical_down_flick_note_linear: Particle = particle("Sekai Critical Down Flick Note Linear")
    critical_down_flick_note_slot_linear: Particle = particle("Sekai Critical Down Flick Note Slot Linear")

    critical_down_flick_note_directional: Particle = particle("Sekai Critical Down Flick Note Directional")

    critical_trace_note_circular: Particle = particle("Sekai Critical Trace Note Circular")
    critical_trace_note_linear: Particle = particle("Sekai Critical Trace Note Linear")

    normal_slide_tick_note: Particle = particle("Sekai Normal Slide Tick Note")

    critical_slide_tick_note: Particle = particle("Sekai Critical Slide Tick Note")

    normal_slide_connector_circular: Particle = particle("Sekai Normal Slide Connector Circular")
    normal_slide_connector_linear: Particle = particle("Sekai Normal Slide Connector Linear")
    normal_slide_connector_trail_linear: Particle = particle("Sekai Normal Slide Connector Trail Linear")
    normal_slide_connector_slot_linear: Particle = particle("Sekai Normal Slide Connector Slot Linear")

    critical_slide_connector_circular: Particle = particle("Sekai Critical Slide Connector Circular")
    critical_slide_connector_linear: Particle = particle("Sekai Critical Slide Connector Linear")
    critical_slide_connector_trail_linear: Particle = particle("Sekai Critical Slide Connector Trail Linear")
    critical_slide_connector_slot_linear: Particle = particle("Sekai Critical Slide Connector Slot Linear")

    damage_note_circular: Particle = particle("Sekai Damage Note Circular")
    damage_note_linear: Particle = particle("Sekai Damage Note Linear")

    fever_chance_text: Particle = particle("Sekai Fever Chance Text")
    fever_chance_lane: Particle = particle("Sekai Fever Chance Lane")
    fever_start_text: Particle = particle("Sekai Fever Text")
    fever_start_lane: Particle = particle("Sekai Fever Lane")
    super_fever_start_text: Particle = particle("Sekai Super Fever Text")
    super_fever_start_lane: Particle = particle("Sekai Super Fever Lane")
    super_fever_start_effect: Particle = particle("Sekai Super Fever Effect")
    fever_border: Particle = particle("Sekai Fever Border")

    # sekai version checker
    v3: Particle = particle("Never delete the sekai version checker=v3")
    v1: Particle = particle("Never delete the sekai version checker=v1")
    lightweight: Particle = particle("Lightweight=True")

    colored_normal_note_circular: ParticleGroup = particle_group(
        f"Sekai Normal Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_normal_note_linear: ParticleGroup = particle_group(
        f"Sekai Normal Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_normal_note_lane_linear: ParticleGroup = particle_group(
        f"Sekai Note Lane Linear {color}" for color in PARTICLE_COLORS
    )
    colored_normal_note_slot_linear: ParticleGroup = particle_group(
        f"Sekai Normal Note Slot Linear {color}" for color in PARTICLE_COLORS
    )
    colored_slide_note_circular: ParticleGroup = particle_group(
        f"Sekai Slide Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_slide_note_linear: ParticleGroup = particle_group(
        f"Sekai Slide Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_normal_slide_note_lane_linear: ParticleGroup = particle_group(
        f"Sekai Slide Lane Linear {color}" for color in PARTICLE_COLORS
    )
    colored_slide_note_slot_linear: ParticleGroup = particle_group(
        f"Sekai Slide Note Slot Linear {color}" for color in PARTICLE_COLORS
    )
    colored_flick_note_circular: ParticleGroup = particle_group(
        f"Sekai Flick Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_flick_note_linear: ParticleGroup = particle_group(
        f"Sekai Flick Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_flick_note_directional: ParticleGroup = particle_group(
        f"Sekai Flick Note Directional {color}" for color in PARTICLE_COLORS
    )
    colored_normal_flick_note_lane_linear: ParticleGroup = particle_group(
        f"Sekai Flick Lane Linear {color}" for color in PARTICLE_COLORS
    )
    colored_flick_note_slot_linear: ParticleGroup = particle_group(
        f"Sekai Flick Note Slot Linear {color}" for color in PARTICLE_COLORS
    )
    colored_down_flick_note_circular: ParticleGroup = particle_group(
        f"Sekai Down Flick Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_down_flick_note_linear: ParticleGroup = particle_group(
        f"Sekai Down Flick Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_down_flick_note_directional: ParticleGroup = particle_group(
        f"Sekai Down Flick Note Directional {color}" for color in PARTICLE_COLORS
    )
    colored_normal_down_flick_note_lane_linear: ParticleGroup = particle_group(
        f"Sekai Down Flick Lane Linear {color}" for color in PARTICLE_COLORS
    )
    colored_down_flick_note_slot_linear: ParticleGroup = particle_group(
        f"Sekai Down Flick Note Slot Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_note_circular: ParticleGroup = particle_group(
        f"Sekai Critical Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_critical_note_linear: ParticleGroup = particle_group(
        f"Sekai Critical Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_note_lane_linear: ParticleGroup = particle_group(
        f"Sekai Critical Lane Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_note_slot_linear: ParticleGroup = particle_group(
        f"Sekai Critical Note Slot Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_slide_note_circular: ParticleGroup = particle_group(
        f"Sekai Critical Slide Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_critical_slide_note_linear: ParticleGroup = particle_group(
        f"Sekai Critical Slide Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_slide_note_lane_linear: ParticleGroup = particle_group(
        f"Sekai Critical Slide Lane Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_slide_note_slot_linear: ParticleGroup = particle_group(
        f"Sekai Critical Slide Note Slot Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_flick_note_circular: ParticleGroup = particle_group(
        f"Sekai Critical Flick Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_critical_flick_note_linear: ParticleGroup = particle_group(
        f"Sekai Critical Flick Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_note_directional: ParticleGroup = particle_group(
        f"Sekai Critical Note Directional {color}" for color in PARTICLE_COLORS
    )
    colored_critical_flick_note_lane_linear: ParticleGroup = particle_group(
        f"Sekai Critical Flick Lane Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_flick_note_slot_linear: ParticleGroup = particle_group(
        f"Sekai Critical Flick Note Slot Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_down_flick_note_circular: ParticleGroup = particle_group(
        f"Sekai Critical Down Flick Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_critical_down_flick_note_linear: ParticleGroup = particle_group(
        f"Sekai Critical Down Flick Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_down_flick_note_directional: ParticleGroup = particle_group(
        f"Sekai Critical Down Flick Note Directional {color}" for color in PARTICLE_COLORS
    )
    colored_critical_down_flick_note_lane_linear: ParticleGroup = particle_group(
        f"Sekai Critical Down Flick Lane Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_down_flick_note_slot_linear: ParticleGroup = particle_group(
        f"Sekai Critical Down Flick Note Slot Linear {color}" for color in PARTICLE_COLORS
    )
    colored_trace_note_linear: ParticleGroup = particle_group(
        f"Sekai Normal Trace Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_trace_note_circular: ParticleGroup = particle_group(
        f"Sekai Normal Trace Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_critical_trace_note_linear: ParticleGroup = particle_group(
        f"Sekai Critical Trace Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_trace_note_circular: ParticleGroup = particle_group(
        f"Sekai Critical Trace Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_normal_slide_tick_note: ParticleGroup = particle_group(
        f"Sekai Normal Slide Tick Note {color}" for color in PARTICLE_COLORS
    )
    colored_critical_slide_tick_note: ParticleGroup = particle_group(
        f"Sekai Critical Slide Tick Note {color}" for color in PARTICLE_COLORS
    )
    colored_damage_note_circular: ParticleGroup = particle_group(
        f"Sekai Damage Note Circular {color}" for color in PARTICLE_COLORS
    )
    colored_damage_note_linear: ParticleGroup = particle_group(
        f"Sekai Damage Note Linear {color}" for color in PARTICLE_COLORS
    )
    colored_normal_slide_connector_circular: ParticleGroup = particle_group(
        f"Sekai Normal Slide Connector Circular {color}" for color in PARTICLE_COLORS
    )
    colored_normal_slide_connector_linear: ParticleGroup = particle_group(
        f"Sekai Normal Slide Connector Linear {color}" for color in PARTICLE_COLORS
    )
    colored_normal_slide_connector_trail_linear: ParticleGroup = particle_group(
        f"Sekai Normal Slide Connector Trail Linear {color}" for color in PARTICLE_COLORS
    )
    colored_normal_slide_connector_slot_linear: ParticleGroup = particle_group(
        f"Sekai Normal Slide Connector Slot Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_slide_connector_circular: ParticleGroup = particle_group(
        f"Sekai Critical Slide Connector Circular {color}" for color in PARTICLE_COLORS
    )
    colored_critical_slide_connector_linear: ParticleGroup = particle_group(
        f"Sekai Critical Slide Connector Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_slide_connector_trail_linear: ParticleGroup = particle_group(
        f"Sekai Critical Slide Connector Trail Linear {color}" for color in PARTICLE_COLORS
    )
    colored_critical_slide_connector_slot_linear: ParticleGroup = particle_group(
        f"Sekai Critical Slide Connector Slot Linear {color}" for color in PARTICLE_COLORS
    )


EMPTY_PARTICLE = Particle(-1)


class NoteParticleSet(Record):
    circular: Particle
    circular_great: Particle
    circular_good: Particle
    linear: Particle
    linear_great: Particle
    linear_good: Particle
    directional: Particle
    tick: Particle
    lane: Particle
    lane_basic: Particle
    slot_linear: Particle
    slot_linear_great: Particle
    slot_linear_good: Particle

    def get_circular(self, judgment: Judgment = Judgment.PERFECT):
        result = +Particle
        match judgment:
            case Judgment.PERFECT:
                result @= self.circular
            case Judgment.GREAT:
                if self.circular_great != EMPTY_PARTICLE and self.circular_great.is_available:
                    result @= self.circular_great
                else:
                    result @= self.circular
            case _:
                if self.circular_good != EMPTY_PARTICLE and self.circular_good.is_available:
                    result @= self.circular_good
                else:
                    result @= self.circular
        return result

    def get_linear(self, judgment: Judgment = Judgment.PERFECT):
        result = +Particle
        match judgment:
            case Judgment.PERFECT:
                result @= self.linear
            case Judgment.GREAT:
                if self.linear_great != EMPTY_PARTICLE and self.linear_great.is_available:
                    result @= self.linear_great
                else:
                    result @= self.linear
            case _:
                if self.linear_good != EMPTY_PARTICLE and self.linear_good.is_available:
                    result @= self.linear_good
                else:
                    result @= self.linear
        return result

    def get_slot_linear(self, judgment: Judgment = Judgment.PERFECT):
        result = +Particle
        match judgment:
            case Judgment.PERFECT:
                result @= self.slot_linear
            case Judgment.GREAT:
                if self.slot_linear_great != EMPTY_PARTICLE and self.slot_linear_great.is_available:
                    result @= self.slot_linear_great
                else:
                    result @= self.slot_linear
            case _:
                if self.slot_linear_good != EMPTY_PARTICLE and self.slot_linear_good.is_available:
                    result @= self.slot_linear_good
                else:
                    result @= self.slot_linear
        return result


class ColoredNoteParticleSet(Record):
    """Color-dependent effects; judgment variants are shared across colors."""

    circular: Particle
    linear: Particle
    directional: Particle
    tick: Particle
    lane: Particle
    lane_basic: Particle
    slot_linear: Particle

    @classmethod
    def of(cls, particles: NoteParticleSet):
        return cls(
            circular=particles.circular,
            linear=particles.linear,
            directional=particles.directional,
            tick=particles.tick,
            lane=particles.lane,
            lane_basic=particles.lane_basic,
            slot_linear=particles.slot_linear,
        )


class JudgmentParticles(Record):
    circular_great: Particle
    circular_good: Particle
    linear_great: Particle
    linear_good: Particle
    slot_linear_great: Particle
    slot_linear_good: Particle


class UIChecker(Record):
    v1: Particle
    v3: Particle

    @property
    def check(self):
        result = 0
        if self.v1.is_available:
            result = Version.v1
        else:
            result = Version.v3
        return result


EMPTY_NOTE_PARTICLE_SET = NoteParticleSet(
    circular=EMPTY_PARTICLE,
    circular_great=EMPTY_PARTICLE,
    circular_good=EMPTY_PARTICLE,
    linear=EMPTY_PARTICLE,
    linear_great=EMPTY_PARTICLE,
    linear_good=EMPTY_PARTICLE,
    directional=EMPTY_PARTICLE,
    tick=EMPTY_PARTICLE,
    lane=EMPTY_PARTICLE,
    lane_basic=EMPTY_PARTICLE,
    slot_linear=EMPTY_PARTICLE,
    slot_linear_great=EMPTY_PARTICLE,
    slot_linear_good=EMPTY_PARTICLE,
)


class ActiveConnectorParticleSet(Record):
    circular: Particle
    linear: Particle
    trail_linear: Particle
    slot_linear: Particle


def _note_color_sources(
    *,
    circular: ParticleGroup | None = None,
    linear: ParticleGroup | None = None,
    directional: ParticleGroup | None = None,
    tick: ParticleGroup | None = None,
    lane: ParticleGroup | None = None,
    slot_linear: ParticleGroup | None = None,
) -> NoteParticleSet:
    """Return the first particle of each group, or EMPTY_PARTICLE for omitted groups."""
    return NoteParticleSet(
        circular=Particle(circular.start_id) if circular is not None else EMPTY_PARTICLE,
        linear=Particle(linear.start_id) if linear is not None else EMPTY_PARTICLE,
        directional=Particle(directional.start_id) if directional is not None else EMPTY_PARTICLE,
        tick=Particle(tick.start_id) if tick is not None else EMPTY_PARTICLE,
        lane=Particle(lane.start_id) if lane is not None else EMPTY_PARTICLE,
        slot_linear=Particle(slot_linear.start_id) if slot_linear is not None else EMPTY_PARTICLE,
        lane_basic=EMPTY_PARTICLE,
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )


# Source tables live in ROM; preprocessing selects available effects.
COLORED_NOTE_PARTICLE_BASES = Array(
    _note_color_sources(  # normal_note
        circular=BaseParticles.colored_normal_note_circular,
        linear=BaseParticles.colored_normal_note_linear,
        lane=BaseParticles.colored_normal_note_lane_linear,
        slot_linear=BaseParticles.colored_normal_note_slot_linear,
    ),
    _note_color_sources(  # slide_note
        circular=BaseParticles.colored_slide_note_circular,
        linear=BaseParticles.colored_slide_note_linear,
        lane=BaseParticles.colored_normal_slide_note_lane_linear,
        slot_linear=BaseParticles.colored_slide_note_slot_linear,
    ),
    _note_color_sources(  # flick_note
        circular=BaseParticles.colored_flick_note_circular,
        linear=BaseParticles.colored_flick_note_linear,
        directional=BaseParticles.colored_flick_note_directional,
        lane=BaseParticles.colored_normal_flick_note_lane_linear,
        slot_linear=BaseParticles.colored_flick_note_slot_linear,
    ),
    _note_color_sources(  # down_flick_note
        circular=BaseParticles.colored_down_flick_note_circular,
        linear=BaseParticles.colored_down_flick_note_linear,
        directional=BaseParticles.colored_down_flick_note_directional,
        lane=BaseParticles.colored_normal_down_flick_note_lane_linear,
        slot_linear=BaseParticles.colored_down_flick_note_slot_linear,
    ),
    _note_color_sources(  # critical_note
        circular=BaseParticles.colored_critical_note_circular,
        linear=BaseParticles.colored_critical_note_linear,
        lane=BaseParticles.colored_critical_note_lane_linear,
        slot_linear=BaseParticles.colored_critical_note_slot_linear,
    ),
    _note_color_sources(  # critical_slide_note
        circular=BaseParticles.colored_critical_slide_note_circular,
        linear=BaseParticles.colored_critical_slide_note_linear,
        lane=BaseParticles.colored_critical_slide_note_lane_linear,
        slot_linear=BaseParticles.colored_critical_slide_note_slot_linear,
    ),
    _note_color_sources(  # critical_flick_note
        circular=BaseParticles.colored_critical_flick_note_circular,
        linear=BaseParticles.colored_critical_flick_note_linear,
        directional=BaseParticles.colored_critical_note_directional,
        lane=BaseParticles.colored_critical_flick_note_lane_linear,
        slot_linear=BaseParticles.colored_critical_flick_note_slot_linear,
    ),
    _note_color_sources(  # critical_down_flick_note
        circular=BaseParticles.colored_critical_down_flick_note_circular,
        linear=BaseParticles.colored_critical_down_flick_note_linear,
        directional=BaseParticles.colored_critical_down_flick_note_directional,
        lane=BaseParticles.colored_critical_down_flick_note_lane_linear,
        slot_linear=BaseParticles.colored_critical_down_flick_note_slot_linear,
    ),
    _note_color_sources(  # trace_note
        linear=BaseParticles.colored_trace_note_linear,
        tick=BaseParticles.colored_trace_note_circular,
    ),
    _note_color_sources(  # trace_flick_note
        directional=BaseParticles.colored_flick_note_directional,
        lane=BaseParticles.colored_normal_flick_note_lane_linear,
    ),
    _note_color_sources(  # trace_down_flick_note
        directional=BaseParticles.colored_down_flick_note_directional,
        lane=BaseParticles.colored_normal_down_flick_note_lane_linear,
    ),
    _note_color_sources(  # critical_trace_note
        linear=BaseParticles.colored_critical_trace_note_linear,
        tick=BaseParticles.colored_critical_trace_note_circular,
    ),
    _note_color_sources(  # critical_trace_flick_note
        directional=BaseParticles.colored_critical_note_directional,
        lane=BaseParticles.colored_critical_flick_note_lane_linear,
    ),
    _note_color_sources(  # critical_trace_down_flick_note
        directional=BaseParticles.colored_critical_down_flick_note_directional,
        lane=BaseParticles.colored_critical_down_flick_note_lane_linear,
    ),
    _note_color_sources(  # normal_slide_tick_note
        tick=BaseParticles.colored_normal_slide_tick_note,
    ),
    _note_color_sources(  # critical_slide_tick_note
        tick=BaseParticles.colored_critical_slide_tick_note,
    ),
    _note_color_sources(  # damage_note
        circular=BaseParticles.colored_damage_note_circular,
        linear=BaseParticles.colored_damage_note_linear,
    ),
)

COLORED_CONNECTOR_PARTICLE_BASES = Array(
    ActiveConnectorParticleSet(
        circular=Particle(BaseParticles.colored_normal_slide_connector_circular.start_id),
        linear=Particle(BaseParticles.colored_normal_slide_connector_linear.start_id),
        trail_linear=Particle(BaseParticles.colored_normal_slide_connector_trail_linear.start_id),
        slot_linear=Particle(BaseParticles.colored_normal_slide_connector_slot_linear.start_id),
    ),
    ActiveConnectorParticleSet(
        circular=Particle(BaseParticles.colored_critical_slide_connector_circular.start_id),
        linear=Particle(BaseParticles.colored_critical_slide_connector_linear.start_id),
        trail_linear=Particle(BaseParticles.colored_critical_slide_connector_trail_linear.start_id),
        slot_linear=Particle(BaseParticles.colored_critical_slide_connector_slot_linear.start_id),
    ),
)


def first_available_particle(*args: Particle) -> Particle:
    result = +EMPTY_PARTICLE
    for e in args:
        if e.is_available:
            result @= e
            break
    return result


@level_data
class ActiveParticles:
    lane: Particle

    note_palette: Array[Array[ColoredNoteParticleSet, Dim[9]], Dim[17]]
    note_judgments: Array[JudgmentParticles, Dim[17]]
    connector_palette: Array[Array[ActiveConnectorParticleSet, Dim[9]], Dim[2]]

    normal_note: NoteParticleSet
    slide_note: NoteParticleSet
    flick_note: NoteParticleSet
    down_flick_note: NoteParticleSet
    critical_note: NoteParticleSet
    critical_slide_note: NoteParticleSet
    critical_flick_note: NoteParticleSet
    critical_down_flick_note: NoteParticleSet
    trace_note: NoteParticleSet
    trace_flick_note: NoteParticleSet
    trace_down_flick_note: NoteParticleSet
    critical_trace_note: NoteParticleSet
    critical_trace_flick_note: NoteParticleSet
    critical_trace_down_flick_note: NoteParticleSet
    normal_slide_tick_note: NoteParticleSet
    critical_slide_tick_note: NoteParticleSet
    damage_note: NoteParticleSet

    normal_slide_connector: ActiveConnectorParticleSet
    critical_slide_connector: ActiveConnectorParticleSet

    fever_chance_text: Particle
    fever_chance_lane: Particle
    fever_start_text: Particle
    fever_start_lane: Particle
    super_fever_start_text: Particle
    super_fever_start_lane: Particle
    super_fever_start_effect: Particle
    fever_border: Particle

    ui_checker: UIChecker
    lightweight: Particle


def init_particles():
    ActiveParticles.lane @= BaseParticles.lane

    ActiveParticles.normal_note @= NoteParticleSet(
        circular=first_available_particle(
            BaseParticles.normal_note_circular,
            BaseParticles.note_circular_cyan,
        ),
        circular_great=BaseParticles.note_circular_cyan_great,
        circular_good=BaseParticles.note_circular_cyan_good,
        linear=first_available_particle(
            BaseParticles.normal_note_linear,
            BaseParticles.note_linear_cyan,
        ),
        linear_great=BaseParticles.note_linear_cyan_great,
        linear_good=BaseParticles.note_linear_cyan_good,
        directional=EMPTY_PARTICLE,
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.normal_note_lane_linear,
        ),
        lane_basic=BaseParticles.lane,
        slot_linear=first_available_particle(
            BaseParticles.normal_note_slot_linear,
            BaseParticles.note_slot_linear_cyan,
        ),
        slot_linear_great=BaseParticles.note_slot_linear_cyan_great,
        slot_linear_good=BaseParticles.note_slot_linear_cyan_good,
    )
    ActiveParticles.slide_note @= NoteParticleSet(
        circular=first_available_particle(
            BaseParticles.slide_note_circular,
            BaseParticles.note_circular_green,
        ),
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=first_available_particle(
            BaseParticles.slide_note_linear,
            BaseParticles.note_linear_green,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=EMPTY_PARTICLE,
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.normal_slide_note_lane_linear,
            BaseParticles.normal_note_lane_linear,
        ),
        lane_basic=BaseParticles.lane,
        slot_linear=first_available_particle(
            BaseParticles.slide_note_slot_linear,
            BaseParticles.note_slot_linear_green,
        ),
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.flick_note @= NoteParticleSet(
        circular=first_available_particle(
            BaseParticles.flick_note_circular,
            BaseParticles.note_circular_red,
        ),
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=first_available_particle(
            BaseParticles.flick_note_linear,
            BaseParticles.note_linear_red,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=first_available_particle(
            BaseParticles.flick_note_directional,
            BaseParticles.note_directional_red,
        ),
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            # Disabled unless explicitly set, so no fallback
            BaseParticles.normal_flick_note_lane_linear,
        ),
        lane_basic=EMPTY_PARTICLE,
        slot_linear=first_available_particle(
            BaseParticles.flick_note_slot_linear,
            BaseParticles.note_slot_linear_alternative_red,
        ),
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.down_flick_note @= NoteParticleSet(
        circular=first_available_particle(
            BaseParticles.down_flick_note_circular,
            BaseParticles.flick_note_circular,
            BaseParticles.note_circular_red,
        ),
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=first_available_particle(
            BaseParticles.down_flick_note_linear,
            BaseParticles.flick_note_linear,
            BaseParticles.note_linear_red,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=first_available_particle(
            BaseParticles.down_flick_note_directional,
            BaseParticles.flick_note_directional,
            BaseParticles.note_directional_red,
        ),
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.normal_down_flick_note_lane_linear,
            BaseParticles.normal_flick_note_lane_linear,
        ),
        lane_basic=EMPTY_PARTICLE,
        slot_linear=first_available_particle(
            BaseParticles.down_flick_note_slot_linear,
            BaseParticles.flick_note_slot_linear,
            BaseParticles.note_slot_linear_alternative_red,
        ),
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.critical_note @= NoteParticleSet(
        circular=first_available_particle(
            BaseParticles.critical_note_circular,
            BaseParticles.note_circular_yellow,
        ),
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=first_available_particle(
            BaseParticles.critical_note_linear,
            BaseParticles.note_linear_yellow,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=EMPTY_PARTICLE,
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.critical_note_lane_linear,
        ),
        lane_basic=BaseParticles.lane,
        slot_linear=first_available_particle(
            BaseParticles.critical_note_slot_linear,
            BaseParticles.note_slot_linear_yellow,
        ),
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.critical_slide_note @= NoteParticleSet(
        circular=first_available_particle(
            BaseParticles.critical_slide_note_circular,
            BaseParticles.note_circular_slide_yellow,
            BaseParticles.critical_note_circular,
            BaseParticles.note_circular_yellow,
        ),
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=first_available_particle(
            BaseParticles.critical_slide_note_linear,
            BaseParticles.note_linear_slide_yellow,
            BaseParticles.critical_note_linear,
            BaseParticles.note_linear_yellow,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=EMPTY_PARTICLE,
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.critical_slide_note_lane_linear,
            BaseParticles.critical_note_lane_linear,
        ),
        lane_basic=BaseParticles.lane,
        slot_linear=first_available_particle(
            BaseParticles.critical_slide_note_slot_linear,
            BaseParticles.note_slot_linear_slide_yellow,
            BaseParticles.critical_note_slot_linear,
            BaseParticles.note_slot_linear_yellow,
        ),
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.critical_flick_note @= NoteParticleSet(
        circular=first_available_particle(
            BaseParticles.critical_flick_note_circular,
            BaseParticles.note_circular_flick_yellow,
            BaseParticles.critical_note_circular,
            BaseParticles.note_circular_yellow,
        ),
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=first_available_particle(
            BaseParticles.critical_flick_note_linear,
            BaseParticles.note_linear_flick_yellow,
            BaseParticles.critical_note_linear,
            BaseParticles.note_linear_yellow,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=first_available_particle(
            BaseParticles.critical_note_directional,
            BaseParticles.note_directional_yellow,
        ),
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.critical_flick_note_lane_linear,
        ),
        lane_basic=BaseParticles.lane,
        slot_linear=first_available_particle(
            BaseParticles.critical_flick_note_slot_linear,
            BaseParticles.note_slot_linear_flick_yellow,
            BaseParticles.critical_note_slot_linear,
            BaseParticles.note_slot_linear_yellow,
        ),
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.critical_down_flick_note @= NoteParticleSet(
        circular=first_available_particle(
            BaseParticles.critical_down_flick_note_circular,
            BaseParticles.critical_flick_note_circular,
            BaseParticles.note_circular_flick_yellow,
            BaseParticles.critical_note_circular,
            BaseParticles.note_circular_yellow,
        ),
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=first_available_particle(
            BaseParticles.critical_down_flick_note_linear,
            BaseParticles.critical_flick_note_linear,
            BaseParticles.note_linear_flick_yellow,
            BaseParticles.critical_note_linear,
            BaseParticles.note_linear_yellow,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=first_available_particle(
            BaseParticles.critical_down_flick_note_directional,
            BaseParticles.critical_note_directional,
            BaseParticles.note_directional_yellow,
        ),
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.critical_down_flick_note_lane_linear,
            BaseParticles.critical_flick_note_lane_linear,
        ),
        lane_basic=BaseParticles.lane,
        slot_linear=first_available_particle(
            BaseParticles.critical_down_flick_note_slot_linear,
            BaseParticles.critical_flick_note_slot_linear,
            BaseParticles.note_slot_linear_flick_yellow,
            BaseParticles.critical_note_slot_linear,
            BaseParticles.note_slot_linear_yellow,
        ),
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.trace_note @= NoteParticleSet(
        circular=EMPTY_PARTICLE,
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=first_available_particle(
            BaseParticles.trace_note_linear,
            BaseParticles.trace_note_linear_green,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=EMPTY_PARTICLE,
        tick=first_available_particle(
            BaseParticles.trace_note_circular,
            BaseParticles.trace_note_circular_green,
        ),
        lane=EMPTY_PARTICLE,
        lane_basic=EMPTY_PARTICLE,
        slot_linear=EMPTY_PARTICLE,
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.trace_flick_note @= NoteParticleSet(
        circular=EMPTY_PARTICLE,
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=EMPTY_PARTICLE,
        directional=first_available_particle(
            BaseParticles.flick_note_directional,
            BaseParticles.note_directional_red,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.normal_flick_note_lane_linear,
        ),
        lane_basic=EMPTY_PARTICLE,
        slot_linear=EMPTY_PARTICLE,
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.trace_down_flick_note @= NoteParticleSet(
        circular=EMPTY_PARTICLE,
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=EMPTY_PARTICLE,
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=first_available_particle(
            BaseParticles.down_flick_note_directional,
            BaseParticles.flick_note_directional,
            BaseParticles.note_directional_red,
        ),
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.normal_down_flick_note_lane_linear,
            BaseParticles.normal_flick_note_lane_linear,
        ),
        lane_basic=EMPTY_PARTICLE,
        slot_linear=EMPTY_PARTICLE,
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.critical_trace_note @= NoteParticleSet(
        circular=EMPTY_PARTICLE,
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=first_available_particle(
            BaseParticles.critical_trace_note_linear,
            BaseParticles.trace_note_linear_yellow,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=EMPTY_PARTICLE,
        tick=first_available_particle(
            BaseParticles.critical_trace_note_circular,
            BaseParticles.trace_note_circular_yellow,
        ),
        lane=EMPTY_PARTICLE,
        lane_basic=EMPTY_PARTICLE,
        slot_linear=EMPTY_PARTICLE,
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.critical_trace_flick_note @= NoteParticleSet(
        circular=EMPTY_PARTICLE,
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=EMPTY_PARTICLE,
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=first_available_particle(
            BaseParticles.critical_note_directional,
            BaseParticles.note_directional_yellow,
        ),
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.critical_flick_note_lane_linear,
        ),
        lane_basic=EMPTY_PARTICLE,
        slot_linear=EMPTY_PARTICLE,
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.critical_trace_down_flick_note @= NoteParticleSet(
        circular=EMPTY_PARTICLE,
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=EMPTY_PARTICLE,
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=first_available_particle(
            BaseParticles.critical_down_flick_note_directional,
            BaseParticles.critical_note_directional,
            BaseParticles.note_directional_yellow,
        ),
        tick=EMPTY_PARTICLE,
        lane=first_available_particle(
            BaseParticles.critical_down_flick_note_lane_linear,
            BaseParticles.critical_flick_note_lane_linear,
        ),
        lane_basic=EMPTY_PARTICLE,
        slot_linear=EMPTY_PARTICLE,
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.normal_slide_tick_note @= NoteParticleSet(
        circular=EMPTY_PARTICLE,
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=EMPTY_PARTICLE,
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=EMPTY_PARTICLE,
        tick=first_available_particle(
            BaseParticles.normal_slide_tick_note,
            BaseParticles.slide_tick_note_circular_green,
        ),
        lane=EMPTY_PARTICLE,
        lane_basic=EMPTY_PARTICLE,
        slot_linear=EMPTY_PARTICLE,
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.critical_slide_tick_note @= NoteParticleSet(
        circular=EMPTY_PARTICLE,
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=EMPTY_PARTICLE,
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=EMPTY_PARTICLE,
        tick=first_available_particle(
            BaseParticles.critical_slide_tick_note,
            BaseParticles.slide_tick_note_circular_yellow,
        ),
        lane=EMPTY_PARTICLE,
        lane_basic=EMPTY_PARTICLE,
        slot_linear=EMPTY_PARTICLE,
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )
    ActiveParticles.damage_note @= NoteParticleSet(
        circular=first_available_particle(
            BaseParticles.damage_note_circular,
        ),
        circular_great=EMPTY_PARTICLE,
        circular_good=EMPTY_PARTICLE,
        linear=first_available_particle(
            BaseParticles.damage_note_linear,
        ),
        linear_great=EMPTY_PARTICLE,
        linear_good=EMPTY_PARTICLE,
        directional=EMPTY_PARTICLE,
        tick=EMPTY_PARTICLE,
        lane=EMPTY_PARTICLE,
        lane_basic=EMPTY_PARTICLE,
        slot_linear=EMPTY_PARTICLE,
        slot_linear_great=EMPTY_PARTICLE,
        slot_linear_good=EMPTY_PARTICLE,
    )

    ActiveParticles.normal_slide_connector @= ActiveConnectorParticleSet(
        circular=first_available_particle(
            BaseParticles.normal_slide_connector_circular,
            BaseParticles.slide_connector_circular_green,
        ),
        linear=first_available_particle(
            BaseParticles.normal_slide_connector_linear,
            BaseParticles.slide_connector_linear_green,
        ),
        trail_linear=first_available_particle(
            BaseParticles.normal_slide_connector_trail_linear,
            BaseParticles.slide_connector_trail_linear_green,
        ),
        slot_linear=first_available_particle(
            BaseParticles.normal_slide_connector_slot_linear,
            BaseParticles.slide_connector_slot_linear_green,
        ),
    )
    ActiveParticles.critical_slide_connector @= ActiveConnectorParticleSet(
        circular=first_available_particle(
            BaseParticles.critical_slide_connector_circular,
            BaseParticles.slide_connector_circular_yellow,
        ),
        linear=first_available_particle(
            BaseParticles.critical_slide_connector_linear,
            BaseParticles.slide_connector_linear_yellow,
        ),
        trail_linear=first_available_particle(
            BaseParticles.critical_slide_connector_trail_linear,
            BaseParticles.slide_connector_trail_linear_yellow,
        ),
        slot_linear=first_available_particle(
            BaseParticles.critical_slide_connector_slot_linear, BaseParticles.slide_connector_slot_linear_yellow
        ),
    )

    ActiveParticles.fever_chance_text @= BaseParticles.fever_chance_text
    ActiveParticles.fever_chance_lane @= BaseParticles.fever_chance_lane
    ActiveParticles.fever_start_text @= BaseParticles.fever_start_text
    ActiveParticles.fever_start_lane @= BaseParticles.fever_start_lane
    ActiveParticles.super_fever_start_text @= BaseParticles.super_fever_start_text
    ActiveParticles.super_fever_start_lane @= BaseParticles.super_fever_start_lane
    ActiveParticles.super_fever_start_effect @= BaseParticles.super_fever_start_effect
    ActiveParticles.fever_border @= BaseParticles.fever_border

    ActiveParticles.ui_checker @= UIChecker(v1=BaseParticles.v1, v3=BaseParticles.v3)
    ActiveParticles.lightweight @= BaseParticles.lightweight

    init_particle_palettes()


def colored_particle(base: Particle, fallback: Particle, style: int) -> Particle:
    result = +fallback
    if base.id >= 0:
        candidate = Particle(base.id + style - 1)
        if candidate.is_available:
            result @= candidate
    return result


def init_particle_palettes():
    defaults = Array(
        ActiveParticles.normal_note,
        ActiveParticles.slide_note,
        ActiveParticles.flick_note,
        ActiveParticles.down_flick_note,
        ActiveParticles.critical_note,
        ActiveParticles.critical_slide_note,
        ActiveParticles.critical_flick_note,
        ActiveParticles.critical_down_flick_note,
        ActiveParticles.trace_note,
        ActiveParticles.trace_flick_note,
        ActiveParticles.trace_down_flick_note,
        ActiveParticles.critical_trace_note,
        ActiveParticles.critical_trace_flick_note,
        ActiveParticles.critical_trace_down_flick_note,
        ActiveParticles.normal_slide_tick_note,
        ActiveParticles.critical_slide_tick_note,
        ActiveParticles.damage_note,
    )
    for family in range(len(defaults)):
        fallback = defaults[family]
        ActiveParticles.note_palette[family][0] @= ColoredNoteParticleSet.of(fallback)
        ActiveParticles.note_judgments[family] @= JudgmentParticles(
            circular_great=fallback.circular_great,
            circular_good=fallback.circular_good,
            linear_great=fallback.linear_great,
            linear_good=fallback.linear_good,
            slot_linear_great=fallback.slot_linear_great,
            slot_linear_good=fallback.slot_linear_good,
        )
    ActiveParticles.connector_palette[0][0] @= ActiveParticles.normal_slide_connector
    ActiveParticles.connector_palette[1][0] @= ActiveParticles.critical_slide_connector

    for family in range(len(ActiveParticles.note_palette)):
        base = COLORED_NOTE_PARTICLE_BASES[family]
        fallback = ActiveParticles.note_palette[family][0]
        for style in range(1, len(ActiveParticles.note_palette[family])):
            ActiveParticles.note_palette[family][style] @= ColoredNoteParticleSet(
                circular=colored_particle(base.circular, fallback.circular, style),
                linear=colored_particle(base.linear, fallback.linear, style),
                directional=colored_particle(base.directional, fallback.directional, style),
                tick=colored_particle(base.tick, fallback.tick, style),
                lane=colored_particle(base.lane, fallback.lane, style),
                lane_basic=fallback.lane_basic,
                slot_linear=colored_particle(base.slot_linear, fallback.slot_linear, style),
            )

    for family in range(len(ActiveParticles.connector_palette)):
        base = COLORED_CONNECTOR_PARTICLE_BASES[family]
        fallback = ActiveParticles.connector_palette[family][0]
        for style in range(1, len(ActiveParticles.connector_palette[family])):
            ActiveParticles.connector_palette[family][style] @= ActiveConnectorParticleSet(
                circular=colored_particle(base.circular, fallback.circular, style),
                linear=colored_particle(base.linear, fallback.linear, style),
                trail_linear=colored_particle(base.trail_linear, fallback.trail_linear, style),
                slot_linear=colored_particle(base.slot_linear, fallback.slot_linear, style),
            )


def styled_note_particles(family: NoteVisualFamily, style: NoteStyle) -> NoteParticleSet:
    if style < NoteStyle.DEFAULT or style > NoteStyle.BLACK or style != int(style):
        style = NoteStyle.DEFAULT
    particles = ActiveParticles.note_palette[family][style]
    judgments = ActiveParticles.note_judgments[family]
    return NoteParticleSet(
        circular=particles.circular,
        circular_great=judgments.circular_great,
        circular_good=judgments.circular_good,
        linear=particles.linear,
        linear_great=judgments.linear_great,
        linear_good=judgments.linear_good,
        directional=particles.directional,
        tick=particles.tick,
        lane=particles.lane,
        lane_basic=particles.lane_basic,
        slot_linear=particles.slot_linear,
        slot_linear_great=judgments.slot_linear_great,
        slot_linear_good=judgments.slot_linear_good,
    )


def get_styled_connector_particles(style: int, critical: bool) -> ActiveConnectorParticleSet:
    if style < NoteStyle.DEFAULT or style > NoteStyle.BLACK or style != int(style):
        style = NoteStyle.DEFAULT
    if critical:
        return ActiveParticles.connector_palette[1][style]
    return ActiveParticles.connector_palette[0][style]
