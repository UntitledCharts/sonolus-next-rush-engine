from sonolus.script.archetype import EntityRef, WatchArchetype, callback, imported
from sonolus.script.runtime import is_replay

from sekai.lib import archetype_names
from sekai.lib.baseevent import init_event_list
from sekai.lib.buckets import init_buckets
from sekai.lib.events import SkillEffects
from sekai.lib.layer import (
    LAYER_BACKGROUND_SIDE,
    LAYER_DAMAGE,
    LAYER_GAUGE,
    LAYER_JUDGMENT,
    LAYER_SKILL_BAR,
    LAYER_SKILL_ETC,
    LAYER_STAGE,
    get_z,
)
from sekai.lib.layout import init_layout
from sekai.lib.level_config import EngineRevision, init_level_config
from sekai.lib.note import init_life, init_score
from sekai.lib.options import Options
from sekai.lib.particle import init_particles
from sekai.lib.skin import init_skin
from sekai.lib.stage import schedule_lane_sfx
from sekai.lib.streams import Streams
from sekai.lib.ui import init_ui
from sekai.watch import custom_elements, note
from sekai.watch.dynamic_stage import WatchCameraChange
from sekai.watch.events import Fever, Skill
from sekai.watch.static_stage import WatchScheduledLaneEffect, WatchStaticStage


@level_memory
class LayerCache:
    judgment: float
    judgment1: float
    judgment2: float
    damage: float
    fever_chance_cover: float
    fever_chance_side: float
    fever_chance_gauge: float
    skill_bar: float
    skill_etc: float


@level_data
class LastNote:
    last_time: float


class WatchInitialization(WatchArchetype):
    name = archetype_names.INITIALIZATION

    revision: EngineRevision = imported(name="revision", default=EngineRevision.LATEST)
    replay_revision: EngineRevision = imported(name="replayRevision", default=EngineRevision.BASE)
    initial_life: int = imported(name="initialLife", default=1000)
    first_camera_ref: EntityRef[WatchCameraChange] = imported(name="firstCamera")

    is_multi: bool = imported()

    @callback(order=-1)
    def preprocess(self):
        if is_replay():
            self.revision = self.replay_revision
        init_level_config(self.revision)
        init_layout()
        init_skin()
        init_particles()
        init_ui()
        init_buckets()
        init_score(note.WATCH_NOTE_ARCHETYPES)
        init_life(note.WATCH_NOTE_ARCHETYPES, self.initial_life)

        LayerCache.judgment = get_z(layer=LAYER_JUDGMENT)
        LayerCache.judgment1 = get_z(layer=LAYER_JUDGMENT, etc=1)
        LayerCache.judgment2 = get_z(layer=LAYER_JUDGMENT, etc=2)
        LayerCache.damage = get_z(layer=LAYER_DAMAGE)
        LayerCache.fever_chance_cover = get_z(layer=LAYER_BACKGROUND_SIDE)
        LayerCache.fever_chance_side = get_z(layer=LAYER_STAGE)
        LayerCache.fever_chance_gauge = get_z(layer=LAYER_GAUGE)
        LayerCache.skill_bar = get_z(layer=LAYER_SKILL_BAR)
        LayerCache.skill_etc = get_z(layer=LAYER_SKILL_ETC)

        custom_elements.LifeManager.life = 1000

        init_event_list(self.first_camera_ref)
        WatchStaticStage.spawn()

        for input_time, lanes in Streams.empty_input_lanes.iter_items_from(-2):
            for lane in lanes:
                schedule_lane_sfx(lane, input_time)
                WatchScheduledLaneEffect.spawn(lane=lane, target_time=input_time)

        sorted_linked_list()


def sorted_linked_list():
    entity_count = 0
    while entity_info_at(entity_count).index == entity_count:
        entity_count += 1
    note_head, note_length, skill_head, skill_length = initial_list(entity_count)

    sorted_skill_head = +EntityRef[Skill]
    if skill_length > 0:
        sorted_skill_head @= sort_entities(skill_head, Skill)
        count_skill(sorted_skill_head.index)

    if note_length > 0:
        sorted_note_head = sort_entities(note_head, note.WatchBaseNote)
        setting_combo(sorted_note_head.index, sorted_skill_head.index)


def initial_list(entity_count):
    note_head = 0
    note_length = 0
    skill_head = 0
    skill_length = 0

    note_id = note.WatchBaseNote._compile_time_id()
    skill_id = Skill._compile_time_id()
    for i in range(entity_count):
        entity_index = entity_count - 1 - i
        info = entity_info_at(entity_index)
        mro = WatchArchetype._get_mro_id_array(info.archetype_id)
        is_note = note_id in mro
        is_skill = skill_id in mro
        if (is_note and note.WatchBaseNote.at(entity_index).is_scored) or is_skill:
            if is_note:
                note.WatchBaseNote.at(entity_index).init_data()
                note.WatchBaseNote.at(entity_index).next_ref.index = note_head
                note_head = entity_index
                note_length += 1
            elif is_skill:
                Skill.at(entity_index).next_ref.index = skill_head
                skill_head = entity_index
                skill_length += 1

    return note_head, note_length, skill_head, skill_length


def sort_entities(index: int, entity_cls):
    head = entity_cls.at(index)
    return sort_linked_entities(
        head.ref(),
        get_value=lambda head: head.calc_time,
        get_next_ref=lambda head: head.next_ref,
    )


def setting_combo(head: int, skill: int) -> None:
    ptr = head
    skill_ptr = skill
    combo = 0
    count = 0
    ap = False
    accuracy = head
    damage_flash = head
    total_weight = 0
    while ptr > 0:
        if skill_ptr > 0 and note.WatchBaseNote.at(ptr).target_time >= Skill.at(skill_ptr).start_time:
            if Skill.at(skill_ptr).effect == SkillEffects.HEAL:
                skill_ptr = Skill.at(skill_ptr).next_ref.index
            elif (
                Skill.at(skill_ptr).effect == SkillEffects.SCORE or Skill.at(skill_ptr).effect == SkillEffects.JUDGMENT
            ):
                note.WatchBaseNote.at(ptr).entity_score_multiplier += (
                    note.WatchBaseNote.at(ptr).archetype_score_multiplier
                    + note.WatchBaseNote.at(ptr).entity_score_multiplier
                )
                if note.WatchBaseNote.at(ptr).target_time > Skill.at(skill_ptr).start_time + 6:
                    skill_ptr = Skill.at(skill_ptr).next_ref.index

        judgment = note.WatchBaseNote.at(ptr).judgment
        if is_replay() and judgment in (Judgment.GOOD, Judgment.MISS):
            combo = 0
            if Fever.fever_chance_time <= note.WatchBaseNote.at(ptr).calc_time < Fever.fever_start_time:
                Fever.fever_chance_cant_super_fever = True
        else:
            combo += 1
        note.WatchBaseNote.at(ptr).combo = combo

        if is_replay() and judgment != Judgment.PERFECT:
            ap = True
        if is_replay() and ap:
            note.WatchBaseNote.at(ptr).at(ptr).ap = True

        if is_replay() and judgment != Judgment.PERFECT and note.WatchBaseNote.at(ptr).at(ptr).played_hit_effects:
            note.WatchBaseNote.at(ptr).at(accuracy).next_ref_accuracy.index = ptr
            accuracy = ptr

        if is_replay() and judgment == Judgment.MISS:
            note.WatchBaseNote.at(ptr).at(damage_flash).next_ref_damage_flash.index = ptr
            damage_flash = ptr

        count += 1
        note.WatchBaseNote.at(ptr).count = count
        if Fever.fever_chance_time <= note.WatchBaseNote.at(ptr).calc_time < Fever.fever_start_time:
            Fever.fever_first_count = (
                min(note.WatchBaseNote.at(ptr).count, Fever.fever_first_count)
                if Fever.fever_first_count != 0
                else note.WatchBaseNote.at(ptr).count
            )
            Fever.fever_last_count = max(note.WatchBaseNote.at(ptr).count, Fever.fever_last_count)

        total_weight += level_score().perfect_multiplier * (
            level_score().consecutive_perfect_cap
            + note.WatchBaseNote.at(ptr).archetype_score_multiplier
            + note.WatchBaseNote.at(ptr).entity_score_multiplier
        )

        LastNote.last_time = max(LastNote.last_time, note.WatchBaseNote.at(ptr).calc_time)
        ptr = note.WatchBaseNote.at(ptr).next_ref.index

    if total_weight == 0:
        scale_factor = 1000000
    else:
        scale_factor = 1000000 / total_weight
    calculate_score(head, 1000000, scale_factor)


def calculate_score(head: int, max_score: int, scale_factor: float):
    ptr = head
    count = 0
    score = 0
    if Options.custom_score == 2:
        score = 100
        custom_elements.ScoreIndicator.score = 100
    custom_elements.ScoreIndicator.first = note.WatchBaseNote.at(head).calc_time
    while ptr > 0:
        # score = judgmentMultiplier * (consecutiveJudgmentMultiplier + archetypeMultiplier + entityMultiplier)
        judgment_multiplier = 0
        consecutive_judgment_multiplier = 0
        if is_replay():
            match note.WatchBaseNote.at(ptr).judgment:
                case Judgment.PERFECT:
                    judgment_multiplier = level_score().perfect_multiplier
                    consecutive_judgment_multiplier = min(
                        level_score().consecutive_perfect_multiplier * level_score().consecutive_perfect_step,
                        level_score().consecutive_perfect_cap,
                    )
                case Judgment.GREAT:
                    judgment_multiplier = level_score().great_multiplier
                    consecutive_judgment_multiplier = min(
                        level_score().consecutive_great_multiplier * level_score().consecutive_great_step,
                        level_score().consecutive_great_cap,
                    )
                case Judgment.GOOD:
                    judgment_multiplier = level_score().good_multiplier
                    consecutive_judgment_multiplier = min(
                        level_score().consecutive_good_multiplier * level_score().consecutive_good_step,
                        level_score().consecutive_good_cap,
                    )
                case Judgment.MISS:
                    judgment_multiplier = 0
                    consecutive_judgment_multiplier = 0
        else:
            judgment_multiplier = level_score().perfect_multiplier
            consecutive_judgment_multiplier = min(
                level_score().consecutive_perfect_multiplier * level_score().consecutive_perfect_step,
                level_score().consecutive_perfect_cap,
            )
        match Options.custom_score:
            case 1:
                score = clamp(
                    score
                    + (
                        (
                            judgment_multiplier
                            * (
                                consecutive_judgment_multiplier
                                + note.WatchBaseNote.at(ptr).archetype_score_multiplier
                                + note.WatchBaseNote.at(ptr).entity_score_multiplier
                            )
                            * scale_factor
                        )
                        / max_score
                        * 100
                    ),
                    0,
                    100,
                )
                note.WatchBaseNote.at(ptr).score = score
            case 2:
                score = clamp(
                    score
                    - (
                        (
                            (level_score().perfect_multiplier - judgment_multiplier)
                            * (
                                consecutive_judgment_multiplier
                                + note.WatchBaseNote.at(ptr).archetype_score_multiplier
                                + note.WatchBaseNote.at(ptr).entity_score_multiplier
                            )
                            * scale_factor
                        )
                        / max_score
                        * 100
                    ),
                    0,
                    100,
                )
                note.WatchBaseNote.at(ptr).score = score
            case 3:
                count += 1
                score += (((1 - abs(note.WatchBaseNote.at(ptr).accuracy)) * 100) - score) / count
                note.WatchBaseNote.at(ptr).score = score

        ptr = note.WatchBaseNote.at(ptr).next_ref.index


def count_skill(head: int) -> None:
    ptr = head
    count = 0
    life = 1000
    while ptr > 0:
        Skill.at(ptr).count = count
        count += 1
        if Skill.at(ptr).effect == SkillEffects.HEAL:
            life = clamp(life + 250, 0, 2000)
        Skill.at(ptr).current_life = life
        ptr = Skill.at(ptr).next_ref.index
