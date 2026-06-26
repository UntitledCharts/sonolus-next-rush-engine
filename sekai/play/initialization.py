from sonolus.script.archetype import EntityRef, PlayArchetype, callback, entity_info_at, exported, imported
from sonolus.script.runtime import level_score

from sekai.lib import archetype_names
from sekai.lib.baseevent import init_event_list
from sekai.lib.buckets import init_buckets
from sekai.lib.connector import (
    CONNECTOR_SFX_ACTIVE_TIME_INIT,
    CONNECTOR_SFX_INACTIVE_TIME_INIT,
    ActiveConnectorKind,
    ConnectorKind,
    connector_sfx_matches_kind,
    init_connector_sfx_times,
    schedule_connector_sfx,
)
from sekai.lib.initialization import LastNote, calculate_note_weight, sort_entities_by_time
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
from sekai.lib.ui import init_ui
from sekai.play import custom_elements, input_manager, note, static_stage
from sekai.play.common import init_play_common
from sekai.play.connector import Connector, ConnectorSfxManager
from sekai.play.dynamic_stage import CameraChange
from sekai.play.events import Fever, Skill


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
        init_ui_margin()
        init_ui()
        init_buckets()
        init_particle_version(ActiveParticles.ui_checker.check)
        init_score(note.NOTE_ARCHETYPES)
        init_life(note.NOTE_ARCHETYPES, self.initial_life)
        init_play_common()
        init_connector_sfx_times()
        init_event_list(self.first_camera_ref)

        custom_elements.LifeManager.life = self.initial_life
        custom_elements.LifeManager.initial_life = self.initial_life
        custom_elements.LifeManager.max_life = max(2000, self.initial_life * 2)

        sorted_linked_list()
        if Options.auto_sfx:
            schedule_auto_connector_sfx()

    def initialize(self):
        static_stage.StaticStage.spawn()
        input_manager.InputManager.spawn()
        ConnectorSfxManager.spawn()
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
        sorted_skill_head @= sort_entities_by_time(skill_head, Skill)
        count_skill(sorted_skill_head.index)

    if note_length > 0:
        sorted_note_head = sort_entities_by_time(note_head, note.BaseNote)
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
        if is_note:
            note.BaseNote.at(entity_index).init_data()
            if note.BaseNote.at(entity_index).is_scored:
                note.BaseNote.at(entity_index).next_ref.index = note_head
                note_head = entity_index
                note_length += 1
        elif is_skill:
            Skill.at(entity_index).next_ref.index = skill_head
            skill_head = entity_index
            skill_length += 1

    return note_head, note_length, skill_head, skill_length


def schedule_auto_connector_sfx():
    entity_count = 0
    while entity_info_at(entity_count).index == entity_count:
        entity_count += 1
    schedule_auto_connector_sfx_kind(entity_count, ConnectorKind.ACTIVE_NORMAL)
    schedule_auto_connector_sfx_kind(entity_count, ConnectorKind.ACTIVE_CRITICAL)


def schedule_auto_connector_sfx_kind(entity_count: int, sfx_kind: ActiveConnectorKind):
    connector_id = Connector._compile_time_id()
    current_time = -1e8
    active_time = CONNECTOR_SFX_ACTIVE_TIME_INIT
    inactive_time = CONNECTOR_SFX_INACTIVE_TIME_INIT
    active_connector_index = 0

    while True:
        next_time = 1e8
        for i in range(entity_count):
            info = entity_info_at(i)
            mro = PlayArchetype._get_mro_id_array(info.archetype_id)
            if connector_id not in mro:
                continue
            connector = Connector.at(i)
            if connector.active_head_ref.index <= 0:
                continue
            if not connector_sfx_matches_kind(connector.segment_head.segment_kind, sfx_kind):
                continue
            if connector.active_head.target_time == connector.active_tail.target_time:
                # Zero-length slide: its activation and release land on the same instant, which the
                # hold-wins-over-release tie-break would otherwise leave stuck on. It holds for no
                # duration, so skip it entirely.
                continue
            active_event_time = connector.active_head.target_time
            inactive_event_time = connector.active_tail.target_time
            if current_time < active_event_time < next_time:
                next_time = active_event_time
            if current_time < inactive_event_time < next_time:
                next_time = inactive_event_time
        if next_time == 1e8:
            break
        if active_time >= inactive_time and active_connector_index > 0:
            active_connector = Connector.at(active_connector_index)
            schedule_connector_sfx(
                sfx_kind,
                active_connector.segment_head.timescale_group,
                current_time,
                next_time,
            )
        for i in range(entity_count):
            info = entity_info_at(i)
            mro = PlayArchetype._get_mro_id_array(info.archetype_id)
            if connector_id not in mro:
                continue
            connector = Connector.at(i)
            if connector.active_head_ref.index <= 0:
                continue
            if not connector_sfx_matches_kind(connector.segment_head.segment_kind, sfx_kind):
                continue
            if connector.active_head.target_time == connector.active_tail.target_time:
                # See the matching skip above: a zero-length slide must not touch the hold state.
                continue
            if connector.active_head.target_time == next_time:
                if inactive_time == CONNECTOR_SFX_INACTIVE_TIME_INIT:
                    inactive_time = next_time
                active_time = next_time
                active_connector_index = i
            if connector.active_tail.target_time == next_time:
                inactive_time = next_time
        current_time = next_time

    if active_time >= inactive_time and active_connector_index > 0:
        active_connector = Connector.at(active_connector_index)
        schedule_connector_sfx(
            sfx_kind,
            active_connector.segment_head.timescale_group,
            current_time,
            LastNote.last_time,
        )


def setting_count(head: int, skill: int) -> None:
    ptr = head
    skill_ptr = skill
    count = 0
    current_note_weight = 0.0

    custom_elements.ScoreIndicator.max_score = 1000000
    while ptr > 0:
        if skill_ptr > 0 and note.BaseNote.at(ptr).target_time >= Skill.at(skill_ptr).start_time:
            if Skill.at(skill_ptr).effect == SkillMode.HEAL:
                skill_ptr = Skill.at(skill_ptr).next_ref.index
            elif Skill.at(skill_ptr).effect == SkillMode.SCORE or Skill.at(skill_ptr).effect == SkillMode.JUDGMENT:
                if note.BaseNote.at(ptr).target_time <= Skill.at(skill_ptr).start_time + 6:
                    note.BaseNote.at(ptr).entity_score_multiplier += (
                        note.BaseNote.at(ptr).archetype_score_multiplier + note.BaseNote.at(ptr).entity_score_multiplier
                    )
                else:
                    skill_ptr = Skill.at(skill_ptr).next_ref.index
        count += 1
        note.BaseNote.at(ptr).count += count

        # arcade score = judgmentMultiplier * (consecutiveJudgmentMultiplier + archetypeMultiplier + entityMultiplier)
        current_note_weight = level_score().perfect_multiplier * calculate_note_weight(
            perfect_step=count,
            great_step=count,
            good_step=count,
            archetype_multiplier=note.BaseNote.at(ptr).archetype_score_multiplier,
            entity_multiplier=note.BaseNote.at(ptr).entity_score_multiplier,
        )
        custom_elements.ScoreIndicator.total_weight.add(current_note_weight)

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


def count_skill(head: int) -> None:
    ptr = head
    count = 0
    while ptr > 0:
        Skill.at(ptr).count = count
        count += 1
        ptr = Skill.at(ptr).next_ref.index
