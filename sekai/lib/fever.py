from typing import Any, Protocol, Self

from sonolus.script.archetype import EntityRef
from sonolus.script.containers import sort_linked_entities
from sonolus.script.debug import require
from sonolus.script.globals import level_data
from sonolus.script.interval import clamp


@level_data
class FeverWindows:
    chance_head: int
    start_head: int


class FeverEventLike(Protocol):
    start_time: float
    end_time: float
    chance_index: int
    next_ref: EntityRef[Any]

    def ref(self) -> EntityRef[Self]: ...


class FeverEventClass(Protocol):
    def at(self, index: int) -> FeverEventLike: ...


def prepare_fever_windows(chances: FeverEventClass, starts: FeverEventClass):
    # Authored entities hold the lists: O(F log F) sorting, O(F) pairing, no capacity limit.
    if FeverWindows.chance_head > 0:
        FeverWindows.chance_head = sort_linked_entities(
            chances.at(FeverWindows.chance_head).ref(),
            get_value=lambda event: event.start_time,
            get_next_ref=lambda event: event.next_ref,
        ).index
    if FeverWindows.start_head > 0:
        FeverWindows.start_head = sort_linked_entities(
            starts.at(FeverWindows.start_head).ref(),
            get_value=lambda event: event.start_time,
            get_next_ref=lambda event: event.next_ref,
        ).index

    chance_index = FeverWindows.chance_head
    start_index = FeverWindows.start_head
    while chance_index > 0:
        require(start_index > 0, "FeverChance requires a following FeverStart")
        chance = chances.at(chance_index)
        start = starts.at(start_index)
        require(chance.start_time < start.start_time, "FeverStart must follow FeverChance")
        if chance.next_ref.index > 0:
            require(
                start.start_time <= chance.next_ref.get().start_time,
                "FeverChance periods must not overlap",
            )
        chance.end_time = start.start_time
        start.chance_index = chance_index
        chance_index = chance.next_ref.index
        start_index = start.next_ref.index
    require(start_index == 0, "FeverStart requires a preceding FeverChance")


def advance_fever_window(chances: FeverEventClass, index: int, target_time: float) -> int:
    # Called during the existing sorted note pass. Each window is visited at most once.
    while index > 0 and target_time >= chances.at(index).end_time:
        index = chances.at(index).next_ref.index
    return index


def fever_percentage(hits: int, count: int, cant_super: bool, previous: float) -> float:
    # Retain the legacy last_count - first_count scale, with a safe empty/single-note denominator.
    return clamp(hits / max(count - 1, 1), 0, 0.9 if not cant_super or previous >= 0.9 else 0.89)
