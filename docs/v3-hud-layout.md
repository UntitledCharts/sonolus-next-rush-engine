# v3 HUD reference geometry

The v3 HUD uses the front UI camera, independently of stage projection.
Reference: gaven1880/OpenSekai commit `1c3ceb540224caa4c35085938fd6485beab0e4a1`.

- `CameraSizeUpdater`: 1920 x 1080, 108 pixels/unit, Both sizing mode.
  Half height is `5 * max(1, (16/9) / aspect)`.
- `SpriteAnchor`: top is camera half height minus 0.1 world units. Horizontal
  anchors use the safe-area aspect. Its extra inset reservation is represented
  in 1080-high reference pixels; Sonolus does not expose physical display
  resolution, so the original fixed 60 physical pixels cannot be reproduced
  exactly on every resolution.
- `FrontUIView.prefab`: ScoreBase (3.7862, -0.42), ScoreGauge offset
  (-2.4542003, -0.10000026), gauge size (4.923, 0.22).
- Life root (-0.61, -0.602), pause offset (0, 0.08), pause sprite 96/108 units.
  Life gauge center offset (-1.7946, 0.082), full size (2.45, 0.144).
- `SkillTextView.prefab`: position (1.7111, -3.22), base size (4.08, 1.36).

The Dropbox `skin3-guide-active.scp` variants all use Score Bar 600x128,
Life Bar Pause 400x93, and Skill Bar Score 400x133. They flatten multiple Unity
sprites into one image. HUD artwork is calibrated at 97.2 pixels/world unit
(90% of the original atlas scale); the pause center is (354, 51) in its sprite,
and the score gauge landmark is (110, 59.5). Raster boundaries and baked artwork
can differ from the original individually rendered sprites by a few pixels.

The engine menu's invisible hitbox is centered on that same pause landmark.
Life UI scaling moves both together; menu scaling changes only hitbox size.
Gauge/body/cap widths use the actual 250+11 pixel life-gauge split. Number/rank
positions follow the frame, so independent screen/aspect offsets cannot drift.

Validation covers 9:16, 4:3, 16:10, 16:9, 19.5:9, 21:9, and 32:9 with multiple
life and menu scales, plus skill animation and asymmetric safe-area insets.
The HUD render paths are also compiled with the Sonolus compiler. This does
not replace checking the artwork in a Sonolus client.
