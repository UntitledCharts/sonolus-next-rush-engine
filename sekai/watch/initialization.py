from math import floor

from sonolus.script.archetype import (
    EntityRef,
    WatchArchetype,
    callback,
    entity_info_at,
    imported,
)
from sonolus.script.bucket import Judgment
from sonolus.script.interval import clamp
from sonolus.script.runtime import is_replay, level_score

from sekai.lib import archetype_names
from sekai.lib.baseevent import init_event_list
from sekai.lib.buckets import init_buckets
from sekai.lib.custom_elements import LifeManager
from sekai.lib.initialization import LastNote, LayerCache, calculate_note_weight, sort_entities_by_time
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
from sekai.lib.layout import init_layout, init_ui_margin
from sekai.lib.level_config import (
    EngineRevision,
    init_level_config,
    init_particle_version,
    init_ui_version,
)
from sekai.lib.note import init_life, init_score
from sekai.lib.options import Options, SkillMode
from sekai.lib.particle import ActiveParticles, init_particles
from sekai.lib.skin import ActiveSkin, init_skin
from sekai.lib.stage import schedule_lane_sfx
from sekai.lib.streams import Streams
from sekai.lib.ui import init_ui
from sekai.watch import custom_elements, note
from sekai.watch.dynamic_stage import WatchCameraChange
from sekai.watch.events import Fever, Skill
from sekai.watch.static_stage import WatchScheduledLaneEffect, WatchStaticStage


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
        init_ui_version(ActiveSkin.ui_checker.check)
        init_ui_margin()
        init_ui()
        init_buckets()
        init_particle_version(ActiveParticles.ui_checker.check)
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

        LifeManager.life = self.initial_life
        LifeManager.initial_life = self.initial_life
        LifeManager.max_life = max(2000, self.initial_life * 2)

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
        sorted_skill_head @= sort_entities_by_time(skill_head, Skill)
        count_skill(sorted_skill_head.index)

    if note_length > 0:
        sorted_note_head = sort_entities_by_time(note_head, note.WatchBaseNote)
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


def setting_combo(head: int, skill: int) -> None:
    ptr = head
    skill_ptr = skill
    combo = 0
    count = 0
    ap = False
    accuracy = head
    damage_flash = head
    total_weight = 0.0
    total_weight_compensation = 0.0
    current_note_weight = 0.0

    while ptr > 0:
        if skill_ptr > 0 and note.WatchBaseNote.at(ptr).target_time >= Skill.at(skill_ptr).start_time:
            if Skill.at(skill_ptr).effect == SkillMode.HEAL:
                skill_ptr = Skill.at(skill_ptr).next_ref.index
            elif Skill.at(skill_ptr).effect == SkillMode.SCORE or Skill.at(skill_ptr).effect == SkillMode.JUDGMENT:
                if note.WatchBaseNote.at(ptr).target_time <= Skill.at(skill_ptr).start_time + 6:
                    note.WatchBaseNote.at(ptr).entity_score_multiplier += (
                        note.WatchBaseNote.at(ptr).archetype_score_multiplier
                        + note.WatchBaseNote.at(ptr).entity_score_multiplier
                    )
                else:
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

        current_note_weight = level_score().perfect_multiplier * calculate_note_weight(
            perfect_step=count,
            great_step=count,
            good_step=count,
            archetype_multiplier=note.WatchBaseNote.at(ptr).archetype_score_multiplier,
            entity_multiplier=note.WatchBaseNote.at(ptr).entity_score_multiplier,
        )

        y = current_note_weight - total_weight_compensation
        t = total_weight + y
        total_weight_compensation = (t - total_weight) - y
        total_weight = t

        LastNote.last_time = max(LastNote.last_time, note.WatchBaseNote.at(ptr).calc_time)
        ptr = note.WatchBaseNote.at(ptr).next_ref.index

    calculate_score(head, 1000000, total_weight)


def calculate_score(head: int, max_score: int, total_weight: float):
    ptr = head
    count = 0
    score = 0
    current_raw_score = 0.0
    raw_score_compensation = 0.0
    acc_sum = 0.0
    acc_compensation = 0.0
    processed_weight = 0.0
    processed_weight_compensation = 0.0
    perfect_step = 0
    great_step = 0
    good_step = 0
    total_weight = total_weight if total_weight > 0 else 1.0
    if Options.custom_score == 2:
        custom_elements.ScoreIndicator.percentage = 100
    custom_elements.ScoreIndicator.first = note.WatchBaseNote.at(head).calc_time
    while ptr > 0:
        count += 1
        # score = judgmentMultiplier * (consecutiveJudgmentMultiplier + archetypeMultiplier + entityMultiplier)
        judgment_multiplier = 0
        if is_replay():
            match note.WatchBaseNote.at(ptr).judgment:
                case Judgment.PERFECT:
                    judgment_multiplier = level_score().perfect_multiplier
                    perfect_step += 1
                    great_step += 1
                    good_step += 1
                case Judgment.GREAT:
                    judgment_multiplier = level_score().great_multiplier
                    perfect_step = 0
                    great_step += 1
                    good_step += 1
                case Judgment.GOOD:
                    judgment_multiplier = level_score().good_multiplier
                    perfect_step = 0
                    great_step = 0
                    good_step += 1
                case Judgment.MISS:
                    judgment_multiplier = 0
                    perfect_step = 0
                    great_step = 0
                    good_step = 0
        else:
            judgment_multiplier = level_score().perfect_multiplier
            perfect_step += 1
            great_step += 1
            good_step += 1

        inv_perfect_step = (
            1.0 / level_score().consecutive_perfect_step if level_score().consecutive_perfect_step > 0 else 0.0
        )
        inv_great_step = 1.0 / level_score().consecutive_great_step if level_score().consecutive_great_step > 0 else 0.0
        inv_good_step = 1.0 / level_score().consecutive_good_step if level_score().consecutive_good_step > 0 else 0.0
        note_raw_score = judgment_multiplier * (
            (
                min(
                    floor(perfect_step * inv_perfect_step + 1e-9) * level_score().consecutive_perfect_multiplier,
                    (level_score().consecutive_perfect_cap * inv_perfect_step)
                    * level_score().consecutive_perfect_multiplier,
                )
                + min(
                    floor(great_step * inv_great_step + 1e-9) * level_score().consecutive_great_multiplier,
                    (level_score().consecutive_great_cap * inv_great_step) * level_score().consecutive_great_multiplier,
                )
                + min(
                    floor(good_step * inv_good_step + 1e-9) * level_score().consecutive_good_multiplier,
                    (level_score().consecutive_good_cap * inv_good_step) * level_score().consecutive_good_multiplier,
                )
            )
            + note.WatchBaseNote.at(ptr).archetype_score_multiplier
            + note.WatchBaseNote.at(ptr).entity_score_multiplier
        )
        raw_calc = (note_raw_score * max_score) / total_weight
        note.WatchBaseNote.at(ptr).note_raw_score = raw_calc

        y = note_raw_score - raw_score_compensation
        t = current_raw_score + y
        raw_score_compensation = (t - current_raw_score) - y
        current_raw_score = t

        final_calc = (current_raw_score / total_weight) * max_score
        score = clamp(
            final_calc,
            0,
            max_score,
        )
        note.WatchBaseNote.at(ptr).score = score

        match Options.custom_score:
            case 1:
                note.WatchBaseNote.at(ptr).percentage = (current_raw_score / total_weight) * 100.0
            case 2:
                note_ideal_weight = level_score().perfect_multiplier * (
                    (
                        min(
                            floor(count * inv_perfect_step + 1e-9) * level_score().consecutive_perfect_multiplier,
                            (level_score().consecutive_perfect_cap * inv_perfect_step)
                            * level_score().consecutive_perfect_multiplier,
                        )
                        + min(
                            floor(count * inv_great_step + 1e-9) * level_score().consecutive_great_multiplier,
                            (level_score().consecutive_great_cap * inv_great_step)
                            * level_score().consecutive_great_multiplier,
                        )
                        + min(
                            floor(count * inv_good_step + 1e-9) * level_score().consecutive_good_multiplier,
                            (level_score().consecutive_good_cap * inv_good_step)
                            * level_score().consecutive_good_multiplier,
                        )
                    )
                    + note.WatchBaseNote.at(ptr).archetype_score_multiplier
                    + note.WatchBaseNote.at(ptr).entity_score_multiplier
                )
                y2 = note_ideal_weight - processed_weight_compensation
                t2 = processed_weight + y2
                processed_weight_compensation = (t2 - processed_weight) - y2
                processed_weight = t2

                current_loss = processed_weight - current_raw_score
                current_visible_score = total_weight - current_loss
                percent = (current_visible_score / total_weight) * 100.0
                note.WatchBaseNote.at(ptr).percentage = clamp(percent, 0.0, 100.0)
            case 3:
                current_acc = (1 - abs(note.WatchBaseNote.at(ptr).accuracy)) * 100

                y = current_acc - acc_compensation
                t = acc_sum + y
                acc_compensation = (t - acc_sum) - y
                acc_sum = t

                note.WatchBaseNote.at(ptr).percentage = acc_sum / count

        ptr = note.WatchBaseNote.at(ptr).next_ref.index


def count_skill(head: int) -> None:
    ptr = head
    count = 0
    life = LifeManager.initial_life
    while ptr > 0:
        Skill.at(ptr).count = count
        count += 1
        if Skill.at(ptr).effect == SkillMode.HEAL:
            life = clamp(life + 250, 0, LifeManager.max_life)
        Skill.at(ptr).current_life = life
        ptr = Skill.at(ptr).next_ref.index
