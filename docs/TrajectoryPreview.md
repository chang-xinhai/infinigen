# Interactive Trajectory Preview

This document describes a fast Blender-based preview workflow for tuning indoor whole-home trajectory parameters without running a full structured-light capture.

## Goal

Use this workflow when trajectory planning is the bottleneck in your iteration loop:

1. regenerate only `trajectory/scene.blend`
2. open that animated scene in Blender
3. switch the viewport to the active camera
4. play the animation interactively to inspect motion quality

This is intended for camera-motion tuning, not for final image-quality evaluation.

## Launch Script

Run:

```bash
bash scripts/launch/preview_existing_seed_trajectory.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    test_traj
```

Behavior:

1. validates `seed_42/coarse/scene.blend`
2. reruns `--task trajectory` into `seed_42/trajectory/`
3. launches Blender GUI on `seed_42/trajectory/scene.blend`
4. runs `scripts/blender_trajectory_preview.py` to:
   switch `VIEW_3D` to the active camera
   set viewport shading
   optionally unhide renderable objects for a closer preview
   autoplay the timeline

Default setting:

- `SETTING=test_traj`

That makes the preview workflow convenient for handheld-like trajectory tuning. Pass `full` when you want to preview the exact trajectory preset used by the full capture pipeline.

## Useful Environment Knobs

The shell wrapper accepts these environment variables:

- `REUSE_EXISTING_TRAJECTORY=1`
  Skip trajectory regeneration and just reopen the saved animation.
- `BLENDER_VIEWPORT_SHADING=SOLID|MATERIAL|RENDERED|WIREFRAME`
  Default is `MATERIAL`. Use `RENDERED` for a closer RGB approximation, usually with Eevee.
- `BLENDER_RENDER_ENGINE=BLENDER_EEVEE`
  Used when `BLENDER_VIEWPORT_SHADING=RENDERED`.
- `BLENDER_AUTO_PLAY=0`
  Open the scene and stay paused on the first frame.
- `BLENDER_HIDE_OVERLAYS=0`
  Keep Blender overlays visible.
- `BLENDER_UNHIDE_RENDERABLES=0`
  Keep the repository's viewport-hiding behavior. This can be faster on heavy scenes but less representative.

Example:

```bash
REUSE_EXISTING_TRAJECTORY=1 \
BLENDER_VIEWPORT_SHADING=RENDERED \
BLENDER_RENDER_ENGINE=BLENDER_EEVEE \
bash scripts/launch/preview_existing_seed_trajectory.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    full
```

## What This Preview Is And Is Not

This preview is useful for:

- walking speed
- turn smoothness
- room-entry behavior
- orbit behavior
- collision or near-wall problems
- whether the path subjectively feels handheld or robotic

This preview is not a pixel-faithful substitute for final rendered RGB:

- viewport `MATERIAL` mode is only an approximation
- viewport `RENDERED` with Eevee is still not the same as final Cycles output
- structured-light projector behavior is not previewed here
- final render-only effects may differ

Use this preview to tune trajectory parameters quickly, then use `capture_existing_seed_scene.sh` or the benchmark pipeline for final validation.
