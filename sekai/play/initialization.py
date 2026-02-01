from math import floor

from sonolus.script.archetype import EntityRef, PlayArchetype, callback, entity_info_at, exported, imported
from sonolus.script.containers import sort_linked_entities
from sonolus.script.globals import level_data, level_memory
from sonolus.script.runtime import level_score

from sekai.lib import archetype_names
from sekai.lib.baseevent import init_event_list
from sekai.lib.buckets import init_buckets
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
from sekai.lib.level_config import (
    EngineRevision,
    LevelConfig,
    init_level_config,
    init_particle_version,
    init_ui_version,
)
from sekai.lib.note import init_life, init_score
from sekai.lib.options import Options, SkillMode
from sekai.lib.particle import ActiveParticles, init_particles
from sekai.lib.skin import ActiveSkin, init_skin
from sekai.lib.ui import init_ui
from sekai.play import custom_elements, input_manager, note, static_stage
from sekai.play.common import init_play_common
from sekai.play.dynamic_stage import CameraChange
from sekai.play.events import Fever, Skill
from sekai.play.input_manager import InputManager
from sekai.play.note import NOTE_ARCHETYPES
from sekai.play.static_stage import StaticStage


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


class Initialization(PlayArchetype):
    name = archetype_names.INITIALIZATION

    revision: EngineRevision = imported(name="revision", default=EngineRevision.SONOLUS_1_1_0)
    initial_life: int = imported(name="initialLife", default=1000)
    first_camera_ref: EntityRef[CameraChange] = imported(name="firstCamera")

    replay_revision: EngineRevision = exported(name="replayRevision")

    @callback(order=-1)
    def preprocess(self):
        init_level_config(self.revision)
        init_layout()
        init_skin()
        init_particles()
        init_ui_version(ActiveSkin.ui_checker.check)
        init_ui(LevelConfig.ui_version)
        init_buckets()
        init_particle_version(ActiveParticles.ui_checker.check)
        init_score(note.NOTE_ARCHETYPES)
        init_life(note.NOTE_ARCHETYPES, self.initial_life)
        init_play_common()
        init_event_list(self.first_camera_ref)

        LayerCache.judgment = get_z(layer=LAYER_JUDGMENT)
        LayerCache.judgment1 = get_z(layer=LAYER_JUDGMENT, etc=1)
        LayerCache.judgment2 = get_z(layer=LAYER_JUDGMENT, etc=2)
        LayerCache.damage = get_z(layer=LAYER_DAMAGE)
        LayerCache.fever_chance_cover = get_z(layer=LAYER_BACKGROUND_SIDE)
        LayerCache.fever_chance_side = get_z(layer=LAYER_STAGE)
        LayerCache.fever_chance_gauge = get_z(layer=LAYER_GAUGE)
        LayerCache.skill_bar = get_z(layer=LAYER_SKILL_BAR)
        LayerCache.skill_etc = get_z(layer=LAYER_SKILL_ETC)

        sorted_linked_list()

    def initialize(self):
        static_stage.StaticStage.spawn()
        input_manager.InputManager.spawn()
        self.replay_revision = self.revision

    def spawn_order(self) -> float:
        return -1e8

    def should_spawn(self) -> bool:
        return True

    def update_parallel(self):
        self.despawn = True


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
        sorted_note_head = sort_entities(note_head, note.BaseNote)
        setting_count(sorted_note_head.index, sorted_skill_head.index)


def initial_list(entity_count):
    note_head = 0
    note_length = 0
    skill_head = 0
    skill_length = 0

    note_id = note.BaseNote._compile_time_id()
    skill_id = Skill._compile_time_id()
    for i in range(entity_count):
        entity_index: int = entity_count - 1 - i
        info = entity_info_at(entity_index)
        mro = PlayArchetype._get_mro_id_array(info.archetype_id)
        is_note = note_id in mro
        is_skill = skill_id in mro
        if (is_note and note.BaseNote.at(entity_index).is_scored) or is_skill:
            if is_note:
                note.BaseNote.at(entity_index).init_data()
                note.BaseNote.at(entity_index).next_ref.index = note_head
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


def setting_count(head: int, skill: int) -> None:
    ptr = head
    skill_ptr = skill
    count = 0
    current_note_weight = 0.0
    inv_perfect_step = (
        1.0 / level_score().consecutive_perfect_step if level_score().consecutive_perfect_step > 0 else 0.0
    )
    inv_great_step = 1.0 / level_score().consecutive_great_step if level_score().consecutive_great_step > 0 else 0.0
    inv_good_step = 1.0 / level_score().consecutive_good_step if level_score().consecutive_good_step > 0 else 0.0

    custom_elements.ScoreIndicator.max_score = 1000000
    while ptr > 0:
        if skill_ptr > 0 and note.BaseNote.at(ptr).target_time >= Skill.at(skill_ptr).start_time:
            if Skill.at(skill_ptr).effect == SkillMode.HEAL:
                skill_ptr = Skill.at(skill_ptr).next_ref.index
            elif Skill.at(skill_ptr).effect == SkillMode.SCORE or Skill.at(skill_ptr).effect == SkillMode.JUDGMENT:
                note.BaseNote.at(ptr).entity_score_multiplier += (
                    note.BaseNote.at(ptr).archetype_score_multiplier + note.BaseNote.at(ptr).entity_score_multiplier
                )
                if note.BaseNote.at(ptr).target_time > Skill.at(skill_ptr).start_time + 6:
                    skill_ptr = Skill.at(skill_ptr).next_ref.index
        count += 1
        note.BaseNote.at(ptr).count += count

        # arcade score = judgmentMultiplier * (consecutiveJudgmentMultiplier + archetypeMultiplier + entityMultiplier)
        current_note_weight = level_score().perfect_multiplier * (
            (
                min(
                    floor(count * inv_perfect_step) * level_score().consecutive_perfect_multiplier,
                    (level_score().consecutive_perfect_cap * inv_perfect_step)
                    * level_score().consecutive_perfect_multiplier,
                )
                + min(
                    floor(count * inv_great_step) * level_score().consecutive_great_multiplier,
                    (level_score().consecutive_great_cap * inv_great_step) * level_score().consecutive_great_multiplier,
                )
                + min(
                    floor(count * inv_good_step) * level_score().consecutive_good_multiplier,
                    (level_score().consecutive_good_cap * inv_good_step) * level_score().consecutive_good_multiplier,
                )
            )
            + note.BaseNote.at(ptr).archetype_score_multiplier
            + note.BaseNote.at(ptr).entity_score_multiplier
        )
        y = current_note_weight - custom_elements.ScoreIndicator.total_weight_compensation
        t = custom_elements.ScoreIndicator.total_weight + y
        custom_elements.ScoreIndicator.total_weight_compensation = (t - custom_elements.ScoreIndicator.total_weight) - y
        custom_elements.ScoreIndicator.total_weight = t

        if Fever.fever_chance_time <= note.BaseNote.at(ptr).target_time < Fever.fever_start_time:
            Fever.fever_first_count = (
                min(note.BaseNote.at(ptr).count, Fever.fever_first_count)
                if Fever.fever_first_count != 0
                else note.BaseNote.at(ptr).count
            )
            Fever.fever_last_count = max(note.BaseNote.at(ptr).count, Fever.fever_last_count)

        LastNote.last_time = max(LastNote.last_time, note.BaseNote.at(ptr).calc_time)
        ptr = note.BaseNote.at(ptr).next_ref.index

    if Options.custom_score == 2:
        custom_elements.ScoreIndicator.percentage = 100

    custom_elements.LifeManager.life = 1000


def count_skill(head: int) -> None:
    ptr = head
    count = 0
    while ptr > 0:
        Skill.at(ptr).count = count
        count += 1
        ptr = Skill.at(ptr).next_ref.index
