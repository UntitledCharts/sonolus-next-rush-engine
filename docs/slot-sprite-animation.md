# Slot sprite animation audit

OpenSekai reference: tutorial/effect_asset/live/tap_effect/0,
`fx_note_normal_aura.prefab` and its critical, long and flick counterparts.

The floor-stamp objects (`base`/`base_bg`) serialize a SizeModule curve from
0.39 to 1.3, but **SizeModule.enabled is 0**. The earlier engine incorrectly
played this inactive curve. Their scale is now constant. The enabled ColorModule
still fades the stamp. Lifetimes remain per source family: normal/critical 0.48,
slide 0.45, critical slide 0.65, flick 0.5, critical flick 0.48 seconds.

The upward glow is a separate `aura` object whose SizeModule is enabled; its
height curves remain animated. Those weighted curves are sampled at 129 points,
so they approximate rather than exactly evaluate Unity's weighted splines.
The skin's baked texture, alpha blending, and projection also prevent claiming
pixel-identical output to the Unity particle renderer. The legacy v1 branch
continues to use its previously requested fixed-size, linear-fade behavior.
