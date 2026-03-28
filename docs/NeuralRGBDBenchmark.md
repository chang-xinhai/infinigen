# Neural RGB-D Benchmark

This document describes the independent Neural RGB-D benchmark workflow implemented under `scripts/benchmark/neural_rgbd`.

The benchmark is intentionally separate from the main Infinigen indoor generation pipeline. It reuses existing rendering components where useful, but it does not modify the main scene-generation flow.

## Goal

For a Neural RGB-D scene such as `breakfast_room`, the benchmark pipeline does three things in order:

1. import the official RGB camera poses into an Infinigen-compatible trajectory scene
2. rerender RGB from the provided `.blend` scene and compare against the official `images/img*.png`
3. run structured-light rendering on top of that imported trajectory

Default pose source:

- `blender_poses`

Alternative pose source:

- `poses.txt`
- `trainval_poses.txt`

## Entry Points

Primary wrapper:

```bash
bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task trajectory render structured_light
```

Direct Python entry:

```bash
python scripts/benchmark/neural_rgbd/run_neural_rgbd.py \
    --scene_name breakfast_room \
    --task trajectory render structured_light
```

All-scene wrapper:

```bash
bash scripts/benchmark/neural_rgbd/run_all_neural_rgbd.sh
```

By default, outputs go to:

```text
outputs/benchmark/neural_rgbd/<scene_name>/<pose_source_stem>/
```

For example:

```text
outputs/benchmark/neural_rgbd/breakfast_room/blender_poses/
```

## Trajectory Import

Import the official Neural RGB-D poses and write an animated trajectory scene:

```bash
bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task trajectory
```

Important behavior:

- reads `data/neural_rgbd/blendswap_scenes/<scene_name>/*.blend`
- reads `focal.txt` and the selected pose file
- interprets `poses.txt` and `trainval_poses.txt` as OpenGL / NeRF-style camera-to-world matrices
- interprets `blender_poses` as Blender-world camera-to-world matrices from `data/neural_rgbd/blender_poses/*.txt`
- applies a benchmark-local scene calibration only for the OpenGL pose sources
- bypasses benchmark-local scene calibration when `--pose_source blender_poses` is used
- creates a single benchmark camera rig named `camrig.0`
- creates an active camera named `camera_0_0`
- disables Blender auto-pack for the imported benchmark scene before saving the trajectory copy
- replaces missing external `bpy.data.images` entries with a generated placeholder so owner-local texture paths do not break trajectory export
- writes `trajectory/scene.blend`
- writes `trajectory/trajectory_metadata.json`

The imported trajectory uses Blender frame `1` for official `img0.png`, frame `2` for `img1.png`, and so on.

Use `--frame_start` and `--frame_end` when you want a smaller validation subset. These are 1-based Blender frame indices over the imported trajectory.

Example:

```bash
bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task trajectory \
    --frame_start 1 \
    --frame_end 8
```

When you have the owner-provided Blender pose archive available locally, prefer:

```bash
bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task trajectory render
```

The benchmark expects the archive to be unpacked under:

```text
data/neural_rgbd/blender_poses/
```

with one flattened `4x4` matrix per line, for example:

```text
data/neural_rgbd/blender_poses/blender_breakfast_poses.txt
```

`whiteroom` is a special case in the owner archive: the local importer selects every other line from `blender_whiteroom_poses.txt` so the archive matches the published RGB frame count.

## Preview

After trajectory import, preview the camera motion in Blender:

```bash
bash scripts/benchmark/neural_rgbd/preview_neural_rgbd_trajectory.sh \
    outputs/benchmark/neural_rgbd/breakfast_room/blender_poses
```

This opens `trajectory/scene.blend` and reuses `scripts/blender_trajectory_preview.py`.

## RGB Reproduction

Render RGB from the imported trajectory scene and compare against the official Neural RGB-D RGB frames:

```bash
bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task render
```

Optional controls:

- `--render_engine KEEP|CYCLES|BLENDER_EEVEE`
- `--render_samples <N>`
- `--frame_start <frame>`
- `--frame_end <frame>`

RGB outputs:

```text
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/frames/rgb/
```

Camera parameter outputs:

```text
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/frames/camview/
```

Comparison reports:

```text
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/frames/comparison/summary.json
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/frames/comparison/frames.jsonl
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/frames/comparison/frames.tsv
```

The benchmark currently reports:

- per-frame MAE
- per-frame MSE
- per-frame PSNR
- per-frame max absolute pixel difference
- exact-match counts

## Structured Light

Run structured-light rendering from the imported Neural RGB-D trajectory:

```bash
bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task structured_light
```

The benchmark passes the imported Neural RGB-D trajectory and matching output frame geometry into the existing `render_structured_light()` implementation. The structured-light IR/projector rig geometry is intended to come from the configured Infinigen structured-light gin settings rather than from the Neural RGB-D RGB focal length. This keeps brightness and scene-lighting behavior aligned with the repository's normal structured-light pipeline while still allowing a benchmark-local projector FOV adjustment.

Depth export behavior for this benchmark is now explicitly metric-oriented:

- structured-light RGB depth EXRs are written as camera-space `+Z` depth, not raw Blender ray distance
- invalid / background depth pixels are written as `0` instead of Blender's large sentinel values
- when `--pose_source blender_poses` is used, the benchmark estimates a per-scene metric output scale from the matching `poses.txt` trajectory and applies that scale during structured-light export

Structured-light outputs go under:

```text
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/sl_frames/
```

The final rerendered RGB and IR observations that follow the repository's structured-light layout are written under:

```text
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/sl_frames/output/rgb/
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/sl_frames/output/IR_left/
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/sl_frames/output/IR_right/
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/sl_frames/output/calibration/
outputs/benchmark/neural_rgbd/<scene>/<pose_stem>/sl_frames/structured_light/patterns/
```

The standalone `frames/` tree remains the validation-oriented RGB reproduction and comparison stage. The `sl_frames/` tree is the main rerendered benchmark deliverable.

## Gin Config Support

The benchmark CLI supports optional gin configs and overrides:

```bash
bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task structured_light \
    -g structured_light.gin \
    -p render_structured_light.sl_max_samples=1
```

Resolution and focal-matching parameters required for Neural RGB-D import are set explicitly by the benchmark code. Other structured-light settings may still be controlled through gin.

The benchmark also forces Blender `scene.render.resolution_percentage = 100` during trajectory import, RGB rerender, and structured-light capture so owner-local or source-scene preview scale settings do not silently shrink outputs below the dataset resolution.

By default, `run_all_neural_rgbd.sh` loads `structured_light_neural_rgbd.gin` in addition to the normal Infinigen structured-light configs. That benchmark-local file is intentionally narrow in scope and currently applies four benchmark-local rig/projector tweaks:

- `render_structured_light.sl_baseline = 0.2`
- `render_structured_light.sl_rgb_offset_scale = -0.5`
- `render_structured_light.sl_proj_fov_delta_deg = 10.0`
- `render_structured_light.sl_proj_energy = 1200.0`

This keeps the background and scene-lighting behavior on the normal Infinigen path while making the structured-light stereo baseline 20 cm, forcing RGB to overlap the left IR camera exactly, and making the pattern slightly wider and slightly brighter for Neural RGB-D scenes.

Reference values:

- main Infinigen indoor default `sl_proj_fov_delta_deg = -5.0`
- main Infinigen indoor default `sl_proj_energy = 1000.0`
- Neural RGB-D benchmark default `sl_proj_fov_delta_deg = 10.0`
- Neural RGB-D benchmark default `sl_proj_energy = 1200.0`

Recommended manual tuning for `sl_proj_energy`:

- try `1300.0` first if the pattern is still just a little too dim
- try `1100.0` if highlights start to wash out

## Notes And Current Assumptions

- default pose source is `blender_poses`
- `poses.txt` and `trainval_poses.txt` remain available for diagnostics and legacy comparisons
- the benchmark expects exactly one `.blend` file per scene directory
- frame `1` maps to official `img0.png`
- the Neural RGB-D pose files are not treated as OpenCV camera poses
- the default world mapping first converts OpenGL-world Y-up coordinates into Blender-world Z-up coordinates
- `breakfast_room` currently uses an additional validated scene calibration and minimal scene override to correct scene-scale mismatch and obvious lighting/background mismatches
- `blender_poses` bypasses that scene calibration because the matrices are consumed as Blender-world camera-to-world poses
- structured-light export still applies a benchmark-local metric output scale for `blender_poses`, derived from the paired `poses.txt` trajectory, so RGB reproduction can stay on the Blender archive path without leaving depth in arbitrary Blender scene units
- the imported benchmark camera uses the repository camera naming convention so existing camera-parameter exporters and preview scripts can be reused
- this workflow does not modify the main Infinigen structured-light core file

## Reference

The local `blender_poses` workflow was added after reviewing the owner-provided Blender pose archive shared in GitHub issue `#4`:

- <https://github.com/dazinovic/neural-rgbd-surface-reconstruction/issues/4>

## One-Click Full Run

Run every available Neural RGB-D scene through trajectory import, RGB validation render, and structured-light capture:

```bash
bash scripts/benchmark/neural_rgbd/run_all_neural_rgbd.sh
```

Useful overrides:

- `SCENES="breakfast_room whiteroom"` limits the run to selected scenes
- by default, the wrapper excludes `full_kitchen`, `morning_apartment`, and `whiteroom`; in this checkout `full_kitchen` maps to the local scene directory `complete_kitchen`, so the default all-scene run processes exactly 6 scenes
- `TASKS="trajectory structured_light"` skips the standalone RGB comparison stage
- `FRAME_END=8` runs a short validation subset per scene
- `OUTPUT_ROOT=/tmp/neural_rgbd_full` changes the benchmark output root
- `POSE_SOURCE=poses.txt` forces the older OpenGL pose path

The wrapper writes per-scene logs under:

```text
outputs/benchmark/neural_rgbd/logs/
```

and a TSV summary at:

```text
outputs/benchmark/neural_rgbd/logs/run_all_summary.tsv
```

GPU selection:

- `GPU_IDS=2` restricts the benchmark to one GPU
- `GPU_IDS=2,3` launches two parallel workers, one pinned to GPU `2` and one pinned to GPU `3`
- `MAX_PARALLEL_SCENES=1` throttles the worker count below the number of visible GPUs when needed
- `ISOLATE_RUNTIME=1` is the default and gives each worker-scene run its own `TMPDIR`, `XDG_*`, and `BLENDER_USER_*` runtime directories to avoid concurrent Blender state collisions
- `KEEP_RUNTIME=1` keeps those per-scene runtime directories on disk for debugging failed runs

Structured-light defaults in the all-scene wrapper now follow the existing indoor capture pipeline more closely:

- `structured_light.gin`
- `full.gin`
- `structured_light_neural_rgbd.gin`
- `infinigen_examples/configs_indoor/capture_manifests/full.yaml`

The benchmark-local `structured_light_neural_rgbd.gin` keeps the background lighting on the normal Infinigen path while also forcing the Neural RGB-D structured-light rig to use a 20 cm stereo baseline with RGB and `l_cam` perfectly overlapping.

If you want a different capture profile, override:

- `STRUCTURED_LIGHT_SETTING`
- `STRUCTURED_LIGHT_MANIFEST`
- `STRUCTURED_LIGHT_CONFIGS`
- `STRUCTURED_LIGHT_OVERRIDES`

## Recommended Validation Order

1. `--task trajectory`
2. preview `trajectory/scene.blend`
3. `--task render` on a short frame range and inspect `frames/comparison/summary.json`
4. `--task structured_light` on the same short frame range
