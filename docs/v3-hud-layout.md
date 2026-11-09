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

## Common custom elements

Judgment and combo sprites have no version split and now use center-camera
coordinates for both v1/v3. Judgment is at (0, -1.17); timing feedback is at
(0, -0.59). Combo digits are centered at (6.217, 0.607), with a 0.95-world-unit
advance, and its label is at (6.241, 1.513). Judgment sizing uses judgment UI
scale independently from combo UI scale. The engine-only percentage display is
kept above the combo group; OpenSekai has no equivalent percentage readout.

Versioned score/life number placement changes apply only to v3. Score uses the
source NumberRoot's right alignment and 0.305 advance; life uses its right-aligned
root and 0.325 advance scaled by the source 0.63 root scale. v1 metric-number
placement remains unchanged.

## Visible glyph bounds

The Next RUSH 150x150 combo canvases include considerable transparent padding:
normal digits occupy approximately 50-79 pixels horizontally and 97-101 pixels
vertically. The 40x40 metric canvases also differ from OpenSekai's trimmed sprite
rectangles and pivots. `font_metrics.py` registers each digit's visible alpha
bounds and source pivot independently from the fixed layout advance. AP and glow
images share the main glyph canvas registration; fallback fonts are left alone.
Metric ink fitting is v3-only, while combo fitting follows the shared combo path.
The calibration targets the inspected Dropbox v3 skins (all four variants use
the same normal combo glyph bounds), not arbitrary external fonts.

Validation uses real engine Sprite.draw calls captured from the Sonolus simulation
and composites the actual SCP atlas in draw order. At 1080-high reference size,
visible combo 1234 and metric digits 1-8 differ from OpenSekai's source atlas
bounds by at most one pixel. Separate 4:3 and 21:9 fixtures cover 1111 and 8888.
These are offline raster checks, not screenshots from a Sonolus client. They
check geometry and texture padding, not client-specific filtering or color space.
