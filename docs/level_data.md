# Next Sekai Level Data Format

## Initialization

Handles common initialization logic for the engine. Must appear exactly once as the first entity in level data.

### Fields

* **initialLife (int)**: The initial life value for the level. Defaults to 1000.
* **firstCamera (ref?[CameraChange])**: An optional reference to the first **CameraChange** entity.

## CameraChange

A camera change event. The presence of at least one **CameraChange** entity enables dynamic stages.

### Fields

* **#BEAT (float)**
* **lane (float)**: Horizontal camera position in stage lanes. Positive values pan the camera to the right (drawn objects shift left). Defaults to 0.
* **size (float)**: Visible width of the field, in lanes (half-width). A `size` of 6 covers the full default stage; smaller values zoom in (e.g. `size=3` is 2x zoom). Defaults to 6.
* **zoom (float)**: Uniform zoom on top of the perspective field. `1` is no zoom, `2` is 2x zoomed in, values below `1` zoom out.
* **zoomTargetLane (float)**: The lane that the zoom focuses on, **relative to `lane`**. `0` means the zoom expands around the camera's current center (the lane currently sitting at the judge line); positive values shift the focus right (in the lane direction), negative values shift it left. Defaults to 0.
* **zoomTargetY (float)**: The vertical point mapped onto the anchor, expressed like a pivot `yOffset` (`0` at the judge line, positive moves up the stage along the approach curve). Defaults to 0.
* **zoomVerticalAlign (ZoomVerticalAlign)**: Where the zoom target is placed vertically on screen. Takes on one of the following values:
  * DEFAULT = 0
  * CENTER = 1
* **rotate (float)**: Camera rotation in degrees about the screen center. Positive values rotate the camera to the left (or equivalently, rotates the world to the right).
* **stageTilt (float)**: Tilt of the stage perspective, in the range `[0, 1]` where 1 is the default and 0 means a flat vertical stage.
* **ease (EaseType)**
* **next (ref?[CameraChange])**: A reference to the next **CameraChange** event.

## Stage

Represents a dynamic stage. The presence of at least one **Stage** enables dynamic stages.

### Fields

* **fromStart (bool)**: If true, draw the stage from the level start, even before the first **StageMaskChange** event.
* **untilEnd (bool)**: If true, keep drawing the stage through the end of the level, even after the last **StageMaskChange** event.
* **firstMaskChange (ref?[StageMaskChange])**: A reference to the first **StageMaskChange** event.
* **firstPivotChange (ref?[StagePivotChange])**: A reference to the first **StagePivotChange** event.
* **firstStyleChange (ref?[StageStyleChange])**: A reference to the first **StageStyleChange** event.

## StageMaskChange

An event that controls the lane and size of a stage's mask.

### Fields

* **stage (ref[Stage])**: A reference to the **Stage** entity this event belongs to.
* **#BEAT (float)**
* **lane (float)**
* **size (float)**
* **ease (EaseType)**
* **next (ref?[StageMaskChange])**: A reference to the next **StageMaskChange** event.

## StagePivotChange

An event that controls the reference point for note and lane movement.

### Fields

* **stage (ref[Stage])**: A reference to the **Stage** entity this event belongs to.
* **#BEAT (float)**
* **lane (float)**
* **divisionSize (float)**: The number of lanes between dividers
* **divisionParity (DivisionParity)**: Whether the pivot falls on a divider (even) or between dividers (odd). Takes on one of the following values:
  * EVEN = 0
  * ODD = 1
* **yOffset (float)**: Vertical offset of the judge line. A value of 0 places the judge line at its default position; positive values move it up the stage.
* **yBeatOffset (float)**: Additional vertical offset expressed in beats. Resolved at preprocess time as an extra contribution to yOffset equal to `yBeatOffset * 60 / bpm / preempt_time()`, where `bpm` is the BPM at this event's beat and `preempt_time()` is the current note-speed-derived preempt time in seconds.
* **ease (EaseType)**
* **next (ref?[StagePivotChange])**: A reference to the next **StagePivotChange** event.

## StageStyleChange

An event that controls the visual style of a stage.

### Fields

* **stage (ref[Stage])**: A reference to the **Stage** entity this event belongs to.
* **#BEAT (float)**
* **judgeLineColor (JudgeLineColor)**
  * NEUTRAL = 0
  * RED = 1
  * GREEN = 2
  * BLUE = 3
  * YELLOW = 4
  * PURPLE = 5
  * CYAN = 6
  * BLACK = 7
* **leftBorderStyle (StageBorderStyle)**:
  * DEFAULT = 0
  * LIGHT = 1
  * DISABLED = 2
  * MEDIUM = 3
* **rightBorderStyle (StageBorderStyle)**:
  * DEFAULT = 0
  * LIGHT = 1
  * DISABLED = 2
  * MEDIUM = 3
* **alpha (float)**
* **laneAlpha (float)**
* **judgeLineAlpha (float)**
* **ease (EaseType)**
* **next (ref?[StageStyleChange])**: A reference to the next **StageStyleChange** event.

## #BPM_CHANGE

The standard bpm change archetype.

### Fields

* **#BEAT (float)**
* **#BPM (float)**

## #TIMESCALE_GROUP

Represents a timescale group and is referenced by notes and timescale changes.

### Fields

* **first (ref[#TIMESCALE_CHANGE])**: [Temporary] a reference to the first change
* **forceNoteSpeed (float)**: If greater than 0 (valid range 1–12), overrides the effective note speed for notes attached to this group, and bypasses the stage-cover FIXED_ONLY scroll-speed compensation. A value of 0 means follow the user's #NOTE_SPEED option.

## #TIMESCALE_CHANGE

A timescale change event.

### Fields

* **#BEAT (float)**
* **#TIMESCALE (float)**
* **#TIMESCALE_SKIP (float)**
* **#TIMESCALE_GROUP (ref[#TIMESCALE_GROUP])**
* **#TIMESCALE_EASE (TimescaleEaseType)**:
  * NONE = 0
  * LINEAR = 1
* **next (ref[#TIMESCALE_CHANGE])**: [Temporary] a reference to the next change
* **hideNotes**: Whether to hide notes while this change is active.

## *Note

Comprised of many archetypes according to the following naming scheme:
[![][image1]](https://tabatkins.github.io/railroad-diagrams/generator.html#Diagram%28%0A%20%20%20%20Choice%28%0A%20%20%20%20%20%20%20%200%2C%0A%20%20%20%20%20%20%20%20Sequence%28%0A%20%20%20%20%20%20%20%20%20%20%20%20Choice%280%2C%20Skip%28%29%2C%20Terminal%28%22Fake%22%29%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20Choice%28%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%200%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Sequence%28%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Choice%280%2C%20Terminal%28%22Normal%22%29%2C%20Terminal%28%22Critical%22%29%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Choice%28%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%200%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Sequence%28%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Choice%280%2C%20Skip%28%29%2C%20Terminal%28%22Head%22%29%2C%20Terminal%28%22Tail%22%29%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Choice%28%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%200%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22Tap%22%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22Flick%22%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22Trace%22%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22TraceFlick%22%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22Release%22%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22Tick%22%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22Damage%22%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22Anchor%22%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20%29%2C%0A%20%20%20%20%20%20%20%20%29%2C%0A%20%20%20%20%20%20%20%20Sequence%28%0A%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22Transient%22%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22Hidden%22%29%2C%0A%20%20%20%20%20%20%20%20%20%20%20%20Terminal%28%22Tick%22%29%2C%0A%20%20%20%20%20%20%20%20%29%2C%0A%20%20%20%20%29%2C%0A%20%20%20%20Terminal%28%22Note%22%29%2C%0A%29%0A)
[Transient] TransientHiddenTick is generated by the editor during export and should not be presented to charters.

### Fields

* **#BEAT (float)**
* **#TIMESCALE_GROUP (ref[#TIMESCALE_GROUP])**: The timescale group of the note.
* **stage (ref?[Stage])**: An optional reference to the **Stage** entity this note belongs to.
* **lane (float)**: The lane for the center of the note. When **stage** is set, this is interpreted relative to the pivot's lane at this note's beat (positive if the note is to the right of the pivot). When **stage** is not set, this is centered at 0 with typical values from -5.5 to 5.5 (the edges of the stage are at lane -6 and 6).
* **size (float)**: The size in lanes of *half* the note. E.g. a note of size 1 would take up two lanes and have an extent of (lane - size) to (lane + size). Typically ranges from 0.5 to 6.
* **direction (Direction)**: The direction of the note, for flicks. Has no effect on other notes. Takes on one of the following values:
  * UP_OMNI = 0
  * UP_LEFT = 1
  * UP_RIGHT = 2
  * DOWN_OMNI = 3
  * DOWN_LEFT = 4
  * DOWN_RIGHT = 5
* **next (ref[Note])**: [Editor] A reference to the next note in the slide, if any.
* **activeHead (ref?[Note])**: An optional reference to the starting note of the active slide. Used by tail flicks for input handling.
* **isAttached (bool)**: Whether this note's **lane, size**, and effective **timescale** should be calculated from **attachHead** and **attachTail**.
* **connectorEase (EaseType)**: What kind of easing is used for the connector immediately following this note. Takes on one of the following values:
  * NONE = 0
  * LINEAR = 1
  * IN_QUAD = 2
  * OUT_QUAD = 3
  * IN_OUT_QUAD = 4
  * OUT_IN_QUAD = 5
* **isSeparator**: [Editor] Whether this note is a connector segment separator. Head notes, tail notes, the first note of a slide, and the last note of a slide are always implicitly separators regardless of the value of this field.
* **segmentKind (ConnectorKind)**: What kind of connector comes in the connector segment after this note, if any. Takes on one of the following values:
  * NONE = 0
  * ACTIVE_NORMAL = 1
  * ACTIVE_CRITICAL = 2
  * FAKE_ACTIVE_NORMAL = 51
  * FAKE_ACTIVE_CRITICAL = 52
  * GUIDE_NEUTRAL = 101
  * GUIDE_RED = 102
  * GUIDE_GREEN = 103
  * GUIDE_BLUE = 104
  * GUIDE_YELLOW = 105
  * GUIDE_PURPLE = 106
  * GUIDE_CYAN = 107
  * GUIDE_BLACK = 108
* **segmentAlpha**: The alpha this note is at for guide connectors.
* **segmentLayer**: The z-layer the guide connector should be drawn at. Takes on one of the following values:
  * TOP = 0
  * BOTTOM = 1
  * UNDER = 2
  * OVER = 3
* **segmentThroughJudgeLine**: Whether connectors in this segment should draw themselves passing through the judge line rather than cutting off there. Defaults to false.
* **attachHead (ref?[Note])**: The optional head the note attaches to for its **lane**, **size**, and **effective timescale**.
* **attachTail (ref?[Note])**: The optional tail the note attaches to for its **lane**, **size**, and **effective timescale**.
* **effectKind (EffectKind)**: What kind of sound effect the note plays when hit. Takes on one of the following values:
  * DEFAULT = 0
  * NONE = 1
  * NORM_BASIC = 2
  * NORM_FLICK = 3
  * NORM_TRACE = 4
  * NORM_TICK = 5
  * CRIT_BASIC = 6
  * CRIT_FLICK = 7
  * CRIT_TRACE = 8
  * CRIT_TICK = 9
  * DAMAGE = 10

## Connector

[Transient] Computed from notes during export and should be ignored during import.
An active slide connector or guide.

## Fields

* **head (ref[Note])**: A reference to the previous (earlier beat) note this connector connects to. Used to calculate starting **beat**, **lane**, and **size**. Also used to obtain the **ease** type.
* **tail (ref[Note])**: A reference to the next (later beat) note this connector connects to. Used to calculate ending **beat**, **lane** and **size**
* **segmentHead (ref[Note])**: A reference to the previous separator note. Used to determine **kind** and **alpha**.
* **segmentTail (ref[Note])**: A reference to the next separator note. Used to determine **alpha**.
* **activeHead (ref?[Note])**: If this is part of an active slide, a reference to the start note of the slide. Used to determine when to start accepting input for an active slide.
* **activeTail (ref?[Note])**: If this is part of an active slide, a reference to the end note of the slide.
* **legacyHiddenPop (bool)**: Whether this connector should use the legacy hidden pop visibility window. Used only for compatibility with old converted level data.

## SimLine

[Transient] Computed from notes during export and should be ignored during import.
A simultaneous note line.

## Fields

* **left (ref[Note])**: A reference to the left note this connects to.
* **right (ref[Note])**: A reference to the right note this connects to.

[image1]: img/note_rr_diagram.png
