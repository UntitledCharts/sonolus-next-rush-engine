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

Versioned score/life number placement changes apply only to v3. Both metrics use the
source least-significant-digit SpriteRenderer root: score has a 0.305 world-unit
advance and 0.94 child scale; life has a 0.325 advance under a 0.63 root scale.
There is no extra text-block alignment or visible-gap kerning. v1 metric-number
placement remains unchanged.

## Visible glyph bounds

The Next RUSH 150x150 combo canvases include considerable transparent padding:
normal digits occupy approximately 50-79 pixels horizontally and 97-101 pixels
vertically. The 40x40 metric canvases also differ from OpenSekai's trimmed sprite
rectangles and pivots. `font_metrics.py` registers each digit's visible alpha
bounds and source pivot independently from the fixed layout advance. AP and glow
images share the main glyph canvas registration; fallback fonts are left alone.
Metric ink fitting is v3-only, while combo fitting follows the shared combo path.
The metric target includes the visible union of `NumberRoot` and
`NumberOutlineRoot`. Fitting the baked outlined glyph to only the source white
layer made score/life digits too small. At 1920x1080, source digit 0 including its
outline is approximately 50 pixels high for score and 33 for life (previous
white-only targets were approximately 41 and 27). The source atlas uses separate
white and outline textures; the skin bakes them together, so stroke proportions
can still differ despite matching outer bounds.
The calibration targets the inspected Dropbox v3 skins (all four variants use
the same normal combo glyph bounds), not arbitrary external fonts.

Validation uses real engine Sprite.draw calls captured from the Sonolus simulation
and composites the actual SCP atlas in draw order. At 1080-high reference size,
visible combo 1234 differs from OpenSekai's source atlas bounds by at most one
pixel. Score 12345678 and life 1000 also differ by at most one pixel at this
reference size when compared with both source font layers. Metric regression
fixtures cover all digits, dim leading zeroes, 4:3/16:9/21:9, and multiple UI
scales; their positions use the original fixed SpriteRenderer advances.
These are offline raster checks, not screenshots from a Sonolus client. They
check geometry and texture padding, not client-specific filtering or color space.

## Score frame registration

The source Unity gauge's 4.923 x 0.22 world rectangle cannot be applied directly
to this flattened skin: its raster opening and transparent padding differ.
The frame opening is approximately (109,50)-(577,71) at the half-alpha boundary.
The normal gauge's original texture has a 553x25 canvas with an ink right edge
at 549; the mask has distinct left padding (8 pixels at half alpha).
The gauge transform is fitted against the actual frame alpha edge, including
its partial opacity, using the middle horizontal/vertical scanlines. Its draw
rectangle in frame pixels is (108.1,48.65) with size (553*0.854,25*0.9275).
The mask's visible cut runs from 109 to 577; its own transparent left margin is
subtracted before drawing. This keeps each fill fraction registered to the same
frame. At 100% no v3 mask is drawn, so a minimum-width quad cannot leave a sliver.
