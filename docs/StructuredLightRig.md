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

The manifest-driven capture path now writes calibration to
`output/calibration/calibration.npz` and optionally
`output/calibration/calibration.jsonl`.

`calibration.npz` keeps the same dense-scene aggregation idea as the older
`parameters.npz` payload and stores:

- `baseline`
- `intrinsic.{L,R,RGB,Proj}`
- `rel_R.{L,R,RGB}`
- `rel_T.{L,R,RGB}`
- `frame_ids[*]`
- `extrinsic[*].{L,R,RGB}` for the cameras requested by the capture manifest
- `patterns[*]`

`rel_T.RGB` is the static translation of the RGB camera relative to the
projector origin in rig coordinates. With the default config it is:

```text
[-0.03025, 0, 0]
```

## Config knob

Use `render_structured_light.sl_rgb_offset_scale` in
`infinigen_examples/configs_indoor/structured_light.gin` to move RGB farther
left or right without changing the IR stereo baseline.

Pattern selection is controlled by `render_structured_light.sl_pattern_names`
and the capture manifest selected by the launch script.

With the default config, pattern assets are loaded from the built-in repository
directory `data/patterns/`. Use `render_structured_light.sl_pattern_dir` only
when you intentionally want to override those shipped assets.

## Pattern capture lighting

RGB baseline captures now render with the structured-light projector disabled.
IR pattern captures preserve that same scene-lighting baseline and only enable
the structured-light projector on top. In other words, RGB and IR should share
the same background brightness, while only the projected region becomes brighter
in IR. The render path now also applies the same preview denoising and sample
clamp settings to both RGB and IR captures so the background appearance stays
consistent apart from the projector contribution.

To keep dim indoor scenes from collapsing into underexposed captures, the
structured-light config now treats
`render_structured_light.sl_preview_world_strength` as a floor for the shared
RGB/IR world background strength. The default config also disables the
camera-attached preview point light to avoid a center-bright hotspot.

If you intentionally want the older projector-only behavior for debugging, set
`render_structured_light.sl_pattern_keep_scene_lighting = False` in
`infinigen_examples/configs_indoor/structured_light.gin`.

## Default projector tuning

The default projector settings in
`infinigen_examples/configs_indoor/structured_light.gin` now track the
current bright structured-light indoor capture defaults:

- `sl_proj_fov_delta_deg = -5.0`
- `sl_proj_dlp_size = 8.4`
- `sl_proj_energy = 1000.0`
- `configure_render_cycles.exposure = 10`

This indoor structured-light config intentionally renders much brighter than
the base indoor defaults so RGB frames do not remain underexposed in dark
houses. Because that stronger ambient baseline can wash out projected patterns,
the default projector energy is also raised substantially to preserve IR
pattern contrast.
