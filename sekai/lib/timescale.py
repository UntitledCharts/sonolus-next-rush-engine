from __future__ import annotations

from collections.abc import Iterator
from math import inf
from typing import Protocol, assert_never, cast

from sonolus.script import runtime
from sonolus.script.archetype import EntityRef, get_archetype_by_name
from sonolus.script.interval import remap
from sonolus.script.record import Record
from sonolus.script.timing import TimescaleEase, beat_to_time

from sekai.lib import archetype_names
from sekai.lib.options import Options

MIN_START_TIME = -2.0


class CompositeTime(Record):
    base: float
    delta: float

    @property
    def total(self) -> float:
        return self.base + self.delta


class TimescaleChangeLike(Protocol):
    beat: float
    timescale: float
    timescale_skip: float
    timescale_ease: TimescaleEase
    hide_notes: bool
    next_ref: EntityRef

    cached_time: float
    cached_skip_time: float

    @classmethod
    def at(cls, index: int) -> TimescaleChangeLike: ...

    @property
    def index(self) -> int: ...


class TimescaleGroupLike(Protocol):
    first_ref: EntityRef
    time_to_scaled_time: TimeToScaledTime
    time_to_last_change_index: TimeToLastChangeIndex
    scaled_time_to_first_time: ScaledTimeToFirstTime
    scaled_time_to_first_time_2: ScaledTimeToFirstTime
    current_scaled_time: CompositeTime
    hide_notes: bool
    force_note_speed: float

    @classmethod
    def at(cls, index: int) -> TimescaleGroupLike: ...

    def update(self) -> None: ...


class TimeToScaledTime(Record):
    last_timescale: float
    last_time: float
    last_scaled_time: float
    last_ease: TimescaleEase
    first_change_index: int
    next_change_index: int
    next_time: float
    next_timescale: float

    def init(self, next_index: int):
        self.first_change_index = next_index
        self.reset()

    def reset(self):
        self.last_timescale = 1.0
        self.last_time = MIN_START_TIME
        self.last_scaled_time = MIN_START_TIME
        self.last_ease = TimescaleEase.NONE
        self.next_change_index = self.first_change_index
        self.next_time = MIN_START_TIME
        self.next_timescale = 1.0

    def get(self, time: float) -> CompositeTime:
        result = +CompositeTime
        if time <= MIN_START_TIME or Options.disable_timescale:
            result.base = time
            return result
        if time < self.last_time:
            self.reset()
        if self.next_time > MIN_START_TIME and time < self.next_time:  # if caching
            if abs(self.next_time - self.last_time) < 1e-6:
                result.base = self.last_scaled_time
                return result
            match self.last_ease:
                case TimescaleEase.NONE:
                    result.base = self.last_scaled_time
                    result.delta = (time - self.last_time) * self.last_timescale
                    return result
                case TimescaleEase.LINEAR:
                    avg_timescale = (
                        self.last_timescale
                        + remap(self.last_time, self.next_time, self.last_timescale, self.next_timescale, time)
                    ) / 2
                    result.base = self.last_scaled_time
                    result.delta = (time - self.last_time) * avg_timescale
                    return result
                case _:
                    assert_never(self.last_ease)
        for change in iter_timescale_changes(self.next_change_index):
            next_timescale = change.timescale
            next_time = change.cached_time
            self.next_timescale = next_timescale
            match self.last_ease:
                case TimescaleEase.NONE:
                    next_scaled_time = self.last_scaled_time + (next_time - self.last_time) * self.last_timescale
                case TimescaleEase.LINEAR:
                    next_scaled_time = (
                        self.last_scaled_time
                        + (next_time - self.last_time) * (next_timescale + self.last_timescale) / 2
                    )
                case _:
                    assert_never(self.last_ease)
            skip_scaled_time = change.cached_skip_time
            if time == next_time:
                result.base = next_scaled_time + skip_scaled_time
                return result
            if time < next_time:
                if abs(next_time - self.last_time) < 1e-6:
                    result.base = self.last_scaled_time
                    return result
                match self.last_ease:
                    case TimescaleEase.NONE:
                        result.base = self.last_scaled_time
                        result.delta = (time - self.last_time) * self.last_timescale
                        return result
                    case TimescaleEase.LINEAR:
                        avg_timescale = (
                            self.last_timescale
                            + remap(self.last_time, next_time, self.last_timescale, next_timescale, time)
                        ) / 2
                        result.base = self.last_scaled_time
                        result.delta = (time - self.last_time) * avg_timescale
                        return result
                    case _:
                        assert_never(self.last_ease)
            self.last_timescale = next_timescale
            self.last_time = next_time
            self.last_scaled_time = next_scaled_time + skip_scaled_time
            self.last_ease = change.timescale_ease
            self.next_change_index = change.next_ref.index
        self.next_time = inf
        self.next_timescale = self.last_timescale

        result.base = self.last_scaled_time
        result.delta = (time - self.last_time) * self.last_timescale
        return result


class TimeToLastChangeIndex(Record):
    last_time: float
    first_change_index: int
    current_change_index: int
    next_change_index: int
    next_time: float

    def init(self, next_index: int):
        self.first_change_index = next_index
        self.reset()

    def reset(self):
        self.last_time = MIN_START_TIME
        self.current_change_index = 0
        self.next_change_index = self.first_change_index
        self.next_time = MIN_START_TIME

    def get(self, time: float) -> int:
        if time < self.last_time:
            self.reset()
        if self.next_time > MIN_START_TIME and time < self.next_time:
            return self.current_change_index
        for change in iter_timescale_changes(self.next_change_index):
            next_time = beat_to_time(change.beat)
            self.next_time = next_time
            if time < next_time:
                return self.current_change_index
            self.last_time = next_time
            self.current_change_index = change.index
            self.next_change_index = change.next_ref.index
        self.next_time = inf
        return self.current_change_index


class ScaledTimeToFirstTime(Record):
    last_timescale: float
    last_time: float
    last_scaled_time: float
    last_ease: TimescaleEase
    first_change_index: int
    next_change_index: int
    last_query_scaled_time: float

    def init(self, next_index: int):
        self.first_change_index = next_index
        self.reset()

    def reset(self):
        self.last_timescale = 1.0
        self.last_time = MIN_START_TIME
        self.last_scaled_time = MIN_START_TIME
        self.last_ease = TimescaleEase.NONE
        self.next_change_index = self.first_change_index
        self.last_query_scaled_time = MIN_START_TIME

    def get(self, scaled_time: float) -> float:
        if Options.disable_timescale:
            return scaled_time
        if scaled_time < self.last_query_scaled_time or self.last_query_scaled_time < MIN_START_TIME:
            self.reset()
        self.last_query_scaled_time = scaled_time
        for change in iter_timescale_changes(self.next_change_index):
            next_timescale = change.timescale
            next_time = change.cached_time
            match self.last_ease:
                case TimescaleEase.NONE:
                    next_scaled_time = self.last_scaled_time + (next_time - self.last_time) * self.last_timescale
                    if (self.last_scaled_time <= scaled_time <= next_scaled_time and self.last_timescale > 0) or (
                        self.last_scaled_time >= scaled_time >= next_scaled_time and self.last_timescale < 0
                    ):
                        if abs(next_scaled_time - self.last_scaled_time) < 1e-6:
                            return self.last_time
                        return remap(self.last_scaled_time, next_scaled_time, self.last_time, next_time, scaled_time)
                case TimescaleEase.LINEAR:
                    next_scaled_time = (
                        self.last_scaled_time
                        + (next_time - self.last_time) * (next_timescale + self.last_timescale) / 2
                    )
                    if abs(next_time - self.last_time) < 1e-6:
                        lo_scaled_time = min(self.last_scaled_time, next_scaled_time)
                        hi_scaled_time = max(self.last_scaled_time, next_scaled_time)
                        if lo_scaled_time <= scaled_time <= hi_scaled_time:
                            return self.last_time
                    else:
                        a = (next_timescale - self.last_timescale) / (next_time - self.last_time)
                        b = self.last_timescale
                        c = self.last_scaled_time - scaled_time

                        first_time = inf
                        found_time = False

                        if abs(a) < 1e-6:
                            if abs(b) > 1e-6:
                                dt = -c / b
                                if 0 <= dt <= (next_time - self.last_time):
                                    first_time = min(first_time, self.last_time + dt)
                                    found_time = True
                        else:
                            discriminant = b * b - 2 * a * c
                            if discriminant >= 0:
                                sqrt_discriminant = discriminant**0.5
                                for dt in ((-b + sqrt_discriminant) / a, (-b - sqrt_discriminant) / a):
                                    if 0 <= dt <= (next_time - self.last_time):
                                        first_time = min(first_time, self.last_time + dt)
                                        found_time = True

                        if found_time:
                            return first_time
                case _:
                    assert_never(self.last_ease)
            skip_scaled_time = change.timescale_skip * 60 / beat_to_bpm(change.beat)
            if (next_scaled_time <= scaled_time <= next_scaled_time + skip_scaled_time) or (
                next_scaled_time + skip_scaled_time <= scaled_time <= next_scaled_time
            ):
                return next_time
            self.last_timescale = next_timescale
            self.last_time = next_time
            self.last_scaled_time = next_scaled_time + skip_scaled_time
            self.last_ease = change.timescale_ease
            self.next_change_index = change.next_ref.index
        if self.last_timescale == 0:
            return inf
        additional_time = (scaled_time - self.last_scaled_time) / self.last_timescale
        if additional_time < 0:
            return inf
        return self.last_time + additional_time


def timescale_change_archetype() -> type[TimescaleChangeLike]:
    return cast(type[TimescaleChangeLike], get_archetype_by_name(archetype_names.TIMESCALE_CHANGE))


def timescale_group_archetype() -> type[TimescaleGroupLike]:
    return cast(type[TimescaleGroupLike], get_archetype_by_name(archetype_names.TIMESCALE_GROUP))


def iter_timescale_changes(index: int) -> Iterator[TimescaleChangeLike]:
    while True:
        if index <= 0:
            return
        change = timescale_change_archetype().at(index)
        yield change
        index = change.next_ref.index


def group_scaled_time(group: int | EntityRef) -> CompositeTime:
    if isinstance(group, EntityRef):
        group = group.index
    result = +CompositeTime
    if group <= 0 or Options.disable_timescale:
        result.base = runtime.time()
    else:
        result @= timescale_group_archetype().at(group).current_scaled_time
    return result


def group_hide_notes(group: int | EntityRef) -> bool:
    if Options.disable_timescale:
        return False
    if isinstance(group, EntityRef):
        group = group.index
    if group <= 0:
        return False
    return timescale_group_archetype().at(group).hide_notes


def group_force_note_speed(group: int | EntityRef) -> float:
    if isinstance(group, EntityRef):
        group = group.index
    if group <= 0:
        return 0.0
    return timescale_group_archetype().at(group).force_note_speed


def iter_timescale_changes_in_group_from_time(
    group: int | EntityRef,
    time: float,
) -> Iterator[TimescaleChangeLike]:
    if isinstance(group, EntityRef):
        group = group.index
    if group <= 0 or Options.disable_timescale:
        return
    group_entity = timescale_group_archetype().at(group)
    next_index = group_entity.time_to_last_change_index.get(time)
    if next_index <= 0:
        next_index = group_entity.first_ref.index
    while next_index > 0:
        change = timescale_change_archetype().at(next_index)
        next_index = change.next_ref.index
        yield change


def group_time_to_scaled_time(
    group: int | EntityRef,
    time: float,
) -> CompositeTime:
    if isinstance(group, EntityRef):
        group = group.index
    return timescale_group_archetype().at(group).time_to_scaled_time.get(time)


def group_scaled_time_to_first_time(
    group: int | EntityRef,
    scaled_time: float,
) -> float:
    if isinstance(group, EntityRef):
        group = group.index
    return timescale_group_archetype().at(group).scaled_time_to_first_time.get(scaled_time)


def group_scaled_time_to_first_time_2(
    group: int | EntityRef,
    scaled_time: float,
) -> float:
    # This is a second function so that we don't have to reset the timescale groups as often
    if isinstance(group, EntityRef):
        group = group.index
    return timescale_group_archetype().at(group).scaled_time_to_first_time_2.get(scaled_time)


def update_timescale_group(group: int | EntityRef) -> None:
    if isinstance(group, EntityRef):
        group = group.index
    if group <= 0:
        return
    timescale_group_archetype().at(group).update()
