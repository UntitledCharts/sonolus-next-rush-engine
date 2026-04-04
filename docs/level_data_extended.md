# Next Rush Extended Level Data Format

## Skill

Represents a skill activation event.

### Fields

* **#BEAT (float)**
* **effect (int)**: The type of skill effect to apply. Takes on one of the following values:
  * SCORE = 0
  * HEAL = 1
  * JUDGMENT = 2
* **level (int)**: The displayed level of the skill. Defaults to 1.

## FeverChance

Represents the start of the fever chance period.

### Fields

* **#BEAT (float)**
* **force (bool)**: Whether to force the fever chance UI and effects to appear even in scenarios where they normally wouldn't (e.g., solo play).

## FeverStart

Represents the start of the active fever period.

### Fields

* **#BEAT (float)**