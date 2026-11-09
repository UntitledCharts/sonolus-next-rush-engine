# Fitting the motion-fixed particle pack to the current engine

`tools/fit_particle_pack.py` reads the inspected Dropbox export
`particle-sekai-motion-fixed.scp` (data SHA-1
`3b6089816fd3ac1ceef51e05a140255cfee1fb78`) and creates a separate SCP.
It does not modify engine particle layouts, spawn counts, or resource selection.

## Coordinate transforms

Sonolus corner order is bottom-left, top-left, top-right, bottom-right.
Linear effect layouts currently include lane-dependent shear. The SCP rebuilds
its top edge from the bottom edge's perpendicular using linear corner
expressions. This retains position, effect size and stage rotation while giving
bilinearly interpolated motion/rotation an orthogonal frame. Directional effects
retain the rotation already applied to their bottom edge. Circular effects retain
the engine's current projected quadrilateral; this is still a bilinear perspective
approximation, not a custom 3D camera.

Named lane resources use unit-height particles, whereas the engine crops their
quad for a legacy 1.07 overshoot. The pack applies `top = 1.07*top - 0.07*bottom`
to recover the reference top in the ordinary crop case. The standard fallback
`#LANE_LINEAR` remains unchanged because its layout is not overshoot-compensated.
The correction is approximate when dynamic-stage clipping selects another bound.

Near-2pi angle discontinuities in short critical-tap segments are unwrapped.
Long intentional spins, timing, easing and random-variable coefficients remain.

## Skin-owned effects

The verified atlas's rectangular floor/slot stamps (74, 75, 81, 98) are omitted;
the skin supplies the slot stamp. Diamonds, sparks and stars remain, including
per-lane Aura emitters. The Good per-lane aliases also omit the identical Gen group
already emitted at the note center. Empty bindings are retained to prevent a
fallback from reintroducing those effects.

Standalone slot-glow emitters were already absent from the inspected pack.
The narrow line textures 32/33 belong to Fever Border, not slot glow, and remain.
The center Gen's blurred spots also remain: they are not the skin's vertical glow.

SCP resource hashes and all effect sprite references are validated after writing.
The script refuses other source data hashes so atlas indices cannot remove an
unrelated third-party effect.
