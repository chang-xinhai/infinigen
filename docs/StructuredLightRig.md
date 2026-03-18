# Structured-Light Rig Layout

This document records the current structured-light rig geometry used by
`infinigen/core/rendering/structured_light.py`.

## Current local layout

The rig is parented under one root empty and moves as a unit. In local rig
coordinates along the `X` axis, the default ordering is:

```text
RGB -- L -------- Projector -------- R
```

With the current indoor config:

- `baseline = 0.055 m`
- `L.x = -baseline / 2`
- `R.x = +baseline / 2`
- `Projector.x = 0`
- `RGB.x = baseline * sl_rgb_offset_scale`
- default `sl_rgb_offset_scale = -0.55`, so `RGB.x = -0.03025 m`

This places RGB slightly left of the left IR camera instead of co-locating it
with the projector.

## Calibration outputs

`structured_light/parameters.json` and `structured_light/parameters.npz` store:

- `intrinsic.{L,R,RGB,Proj}`
- `extrinsic[*].{L,R,RGB}`
- `rel_R.{L,R,RGB}`
- `rel_T.{L,R,RGB}`

`rel_T.RGB` is the static translation of the RGB camera relative to the
projector origin in rig coordinates. With the default config it is:

```text
[-0.03025, 0, 0]
```

## Config knob

Use `render_structured_light.sl_rgb_offset_scale` in
`infinigen_examples/configs_indoor/structured_light.gin` to move RGB farther
left or right without changing the IR stereo baseline.
