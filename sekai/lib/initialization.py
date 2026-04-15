from math import floor
from typing import Any, Protocol

from sonolus.script.archetype import EntityRef
from sonolus.script.containers import sort_linked_entities
from sonolus.script.globals import level_data, level_memory
from sonolus.script.runtime import level_score


@level_memory
class LayerCache:
    judgment: float
    judgment1: float
    judgment2: float
    damage: float
    fever_chance_cover: float
    fever_chance_side: float
    fever_chance_text: float
    fever_chance_gauge: float
    skill_bar: float
    skill_etc: float


@level_data
class LastNote:
    last_time: float


def calculate_note_weight(
    perfect_step: int, great_step: int, good_step: int, archetype_multiplier: float, entity_multiplier: float
) -> float:
    ls = level_score()
    inv_perfect_step = 1.0 / ls.consecutive_perfect_step if ls.consecutive_perfect_step > 0 else 0.0
    inv_great_step = 1.0 / ls.consecutive_great_step if ls.consecutive_great_step > 0 else 0.0
    inv_good_step = 1.0 / ls.consecutive_good_step if ls.consecutive_good_step > 0 else 0.0

    return (
        min(
            floor(perfect_step * inv_perfect_step + 1e-9) * ls.consecutive_perfect_multiplier,
            (ls.consecutive_perfect_cap * inv_perfect_step) * ls.consecutive_perfect_multiplier,
        )
        + min(
            floor(great_step * inv_great_step + 1e-9) * ls.consecutive_great_multiplier,
            (ls.consecutive_great_cap * inv_great_step) * ls.consecutive_great_multiplier,
        )
        + min(
            floor(good_step * inv_good_step + 1e-9) * ls.consecutive_good_multiplier,
            (ls.consecutive_good_cap * inv_good_step) * ls.consecutive_good_multiplier,
        )
        + archetype_multiplier
        + entity_multiplier
    )


class SortableEntity(Protocol):
    @property
    def calc_time(self) -> float: ...

    @property
    def next_ref(self) -> EntityRef[Any]: ...

    def ref(self) -> EntityRef[Any]: ...


class SortableArchetypeClass(Protocol):
    def at(self, index: int, check: bool = True) -> SortableEntity: ...


def sort_entities_by_time(index: int, entity_cls: SortableArchetypeClass):
    head = entity_cls.at(index)

    def get_time(h: SortableEntity) -> float:
        return h.calc_time

    def get_next(h: SortableEntity) -> EntityRef[Any]:
        return h.next_ref

    return sort_linked_entities(
        head.ref(),
        get_value=get_time,
        get_next_ref=get_next,
    )
