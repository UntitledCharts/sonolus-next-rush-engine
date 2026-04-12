# Next Rush Extended Level Data Format

## Skill

Represents a skill activation event.

### Fields

* **#BEAT (float)**
* **effect (int)**: The type of skill effect to apply. Takes on one of the following values:
  * SCORE = 0
  * HEAL = 1
  * JUDGMENT = 2
* **level (int)**: The displayed level of the skill. Must be an integer between 1 and 4. Defaults to 1.

## FeverChance

Represents the start of the fever chance period.

**Note:** A level can contain exactly one `FeverChance` and exactly one `FeverStart` event. They must always appear as a pair, and `FeverChance` must occur at an earlier `#BEAT` than `FeverStart`.

### Fields

* **#BEAT (float)**
* **force (bool)**: Whether to force the fever chance UI and effects to appear even in scenarios where they normally wouldn't (e.g., solo play).

## FeverStart

Represents the start of the active fever period.

**Note:** A level can contain exactly one `FeverStart` event, which must be paired with and occur strictly after the `FeverChance` event.

### Fields

* **#BEAT (float)**