# OpenSekai input behavior

Reference: `gaven1880/OpenSekai` commit `1c3ceb540224caa4c35085938fd6485beab0e4a1`.
These gameplay paths are shared by v1 and v3.

## Overlapping taps

`Core/Live/LiveLogic.cs` resolves shared candidates across inputs before pruning
an individual input's candidates by time, grade, and distance. Next RUSH now
assigns every eligible tap candidate to its closest eligible starting touch first.
Equal distances favor the earlier touch in the input list. Ownership stays fixed
while each touch chooses at most one note. A note discarded by its owner cannot
be reassigned to a more distant finger in a later allocation round.

The regression fixture uses adjacent centers 0 and 1 and touches at 0.4 and 1.8.
Both notes first belong to the first finger, which selects the first note. The
second note remains unclaimed in that input pass, matching the source procedure.
Accurately separated touches still judge both notes. The engine's existing
same-beat priority of tap notes over trace-flick capture remains an extension.

## Hold-end releases

`AddCheckLongInputedNormalNoteTouch` permits a release candidate when there is no
recent note-input record for that touch, when its grade is above GREAT, or when
more than `1/6` second has elapsed since that input record. Next RUSH now records
actual touch event times, including eligible beginnings discarded by ownership
pruning and pending standalone flick input, rather than
storing a deadline based on a previously judged note's scheduled time.

PERFECT releases bypass the recent-input restriction. Other releases use their
actual event time and a strict `> 1/6` comparison. The former 250 ms restriction
and its exemption based on whether another finger was holding are removed.
The same predicate is used in both the direct release scan and dense shortlists.
History disappears when the touch disappears; another finger does not inherit it.

## Flick displacement and physical calibration

The source SUS path uses `DPI / 2.54 * 0.083333` pixels as its reference-frame
movement threshold. `FlickNote.UpdateDelta` scales frame motion by
`deltaTime / 0.016667`. Thus both ordinary and trace/hold-end flicks now require:

```
frame displacement squared > reference distance squared * (deltaTime / 0.016667)^2
```

A nonpositive frame duration follows the source's unscaled fallback. Equality
is insufficient. Motion and direction use the actual frame delta, rather than
Sonolus's reported speed and angle. Movements are not accumulated across frames.

Sonolus does not supply display DPI or physical viewport dimensions. An advanced
Gameplay option, **Play Area Short Side (cm)**, supplies the physical length of
the shorter side of the visible play area. The conversion is:

```
reference distance = min(viewport width, viewport height) / short_side_cm * 0.083333
```

Set it to the measured visible play area's short side, excluding letterboxing
outside the Sonolus viewport. The default **7 cm is an estimate**, not automatic
device detection. With correct calibration the conversion is algebraically the
same as the source DPI formula. A larger setting lowers the screen-space movement
threshold. The calculation is independent of lanes, stage zoom, stage rotation,
stage aspect locking, UI version, and note width. Touch sampling differences and
inaccurate physical calibration can still cause different device behavior.

## Validation and remaining differences

The tests compare a list-based translation of the source candidate pipeline with
the engine for mixed grades, ties, preclaimed notes, multiple touches, and dense
windows. They also execute compiled Sonolus input allocation. Dedicated tests
cover the earlier counterexamples, real event timestamps, the strict 1/6-second
boundary, history cleanup, and the source DPI/motion formula at 30–240 fps.

BAD still shares Sonolus's internal MISS grade and life deduction. That separately
reported difference is outside these three changes. Next RUSH's extra note types
and dynamic-stage features also have no complete one-to-one source counterpart.
