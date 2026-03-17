# Structured-Light Indoor Benchmark

This workflow is for generating a small set of indoor structured-light benchmark scenes with slightly higher quality than `fast_solve.gin`, without paying the previous order-of-magnitude runtime cost.

## Files

- `infinigen_examples/configs_indoor/benchmark.gin`
- `infinigen_examples/configs_indoor/whole_home_walk.gin`
- `scripts/launch/structured_light_indoors_benchmark.sh`
- `scripts/launch/capture_existing_seed_scene.sh`

## What Changes Relative To The Fast Script

The benchmark config increases floor-plan search and object-placement optimization relative to `fast_solve.gin`, but it stays in the same general runtime regime by keeping `has_fewer_rooms=True` and using moderate solve counts.

The benchmark script also layers in:

- `real_geometry_with_bump.gin` for richer room geometry
- `whole_home_walk.gin` for whole-home camera trajectory planning on existing coarse scenes
- optional `multistory.gin` when `ENABLE_MULTISTORY=1`
- a batch loop over multiple seeds
- log files under `OUTPUT_ROOT/logs/`
- optional background parallelism for the `coarse` stage
- a single shared benchmark quality profile defined in `benchmark.gin`

## Default Command

```bash
bash scripts/launch/structured_light_indoors_benchmark.sh
```

By default this generates 10 scenes starting from `seed=0` under:

```bash
outputs/benchmark/structured_light_indoors/
```

Each scene is written to:

```bash
outputs/benchmark/structured_light_indoors/seed_<N>/
```

## Runtime Knobs

Scene-quality parameters now live in `infinigen_examples/configs_indoor/benchmark.gin` so they remain shared across scripts and direct `generate_indoors` invocations.

The launch script only exposes runtime controls:

```bash
NUM_SCENES=10 \
SEED_START=0 \
ROOM_TYPE=ALL \
OUTPUT_ROOT=outputs/benchmark/structured_light_indoors \
RUN_STANDARD_RENDER=0 \
ENABLE_MULTISTORY=0 \
ENABLE_WHOLE_HOME_WALK=1 \
REUSE_EXISTING_COARSE=0 \
PARALLEL_MODE=coarse_only \
MAX_PARALLEL_SCENES=2 \
SL_MAX_SAMPLES=128 \
WALK_CAMERA_HEIGHT_M=1.55 \
WALK_FPS=8 \
WALK_STEP_M=0.05 \
FAIL_ON_ANY_SEED_FAILURE=1 \
bash scripts/launch/structured_light_indoors_benchmark.sh
```

Additional compatibility knobs:

- `FAIL_ON_ANY_SEED_FAILURE=1` keeps processing all seeds but returns a non-zero exit code at the end if any seed failed
- `FAIL_ON_ANY_SEED_FAILURE=0` keeps processing all seeds and returns success even when some seeds fail
- `PYTHON_BIN=/path/to/python` overrides the Python executable used by the launch script
- `ENABLE_WHOLE_HOME_WALK=1` inserts a `trajectory` stage between `coarse` and rendering
- `REUSE_EXISTING_COARSE=1` skips scene generation for seeds that already have `coarse/scene.blend` and reuses those scenes for whole-home trajectory planning and rendering
- `WALK_CAMERA_HEIGHT_M`, `WALK_FPS`, `WALK_STEP_M`, `WALK_CLEARANCE_M`, `WALK_PATH_MARGIN_M`, and `WALK_PATH_RESOLUTION` override the default whole-home walk planner hyperparameters without editing code
- the default whole-home planner now uses `room_path_mode="collision_aware_grid"` with `room_grid_step_m=0.10` from `whole_home_walk.gin`

The current benchmark gin uses this moderate-quality profile:

```gin
FloorPlanSolver.n_divide_trials = 40
FloorPlanSolver.iters_mult = 45
home_room_constraints.has_fewer_rooms = True
solve_objects.addition_weight_scalar = 3.0
compose_indoors.solve_steps_large = 150
compose_indoors.solve_steps_medium = 65
compose_indoors.solve_steps_small = 10
```

You can also use positional arguments:

```bash
bash scripts/launch/structured_light_indoors_benchmark.sh 10 0 ALL outputs/benchmark/structured_light_indoors
```

## Examples

Generate 10 benchmark whole-home scenes:

```bash
NUM_SCENES=10 SEED_START=0 bash scripts/launch/structured_light_indoors_benchmark.sh
```

Generate 10 benchmark scenes with multistory homes enabled:

```bash
NUM_SCENES=10 SEED_START=100 ENABLE_MULTISTORY=1 bash scripts/launch/structured_light_indoors_benchmark.sh
```

Generate 10 benchmark scenes with 2-way parallel `coarse` generation:

```bash
NUM_SCENES=10 MAX_PARALLEL_SCENES=2 PARALLEL_MODE=coarse_only \
bash scripts/launch/structured_light_indoors_benchmark.sh
```

Generate only bedroom scenes:

```bash
NUM_SCENES=10 ROOM_TYPE=Bedroom bash scripts/launch/structured_light_indoors_benchmark.sh
```

## Output Layout

For each seed:

- `coarse/scene.blend` stores the generated scene
- `trajectory/scene.blend` stores the same scene with whole-home walking camera animation when the trajectory stage actually changes the scene
- `trajectory/trajectory_metadata.json` stores planner parameters, room order, and per-frame camera poses
- `sl_frames/structured_light/` stores structured-light outputs
- `frames/` is generated only when `RUN_STANDARD_RENDER=1`
- `logs/seed_<N>_coarse.log` stores coarse-generation logs
- `logs/seed_<N>_render_sl.log` stores render and structured-light logs in `coarse_only` mode
- `logs/seed_<N>.log` stores the full run in `off` mode
- `logs/benchmark_summary.tsv` stores per-seed `coarse` and `postprocess` status for the full batch

When a seed fails during `coarse`, the benchmark script now keeps running the remaining seeds, marks the failed seed in `benchmark_summary.tsv`, and skips render / structured-light post-processing for that seed instead of aborting the entire batch immediately.

When `ENABLE_WHOLE_HOME_WALK=1`, the script plans a whole-home trajectory from the generated or reused `coarse` scene first, writes the animated result under `trajectory/`, and renders standard RGB or structured-light data from that trajectory scene.

If you already have benchmark scenes under `outputs/benchmark/structured_light_indoors/seed_<N>/coarse/scene.blend`, you can reuse them directly:

```bash
NUM_SCENES=1 \
SEED_START=0 \
REUSE_EXISTING_COARSE=1 \
ENABLE_WHOLE_HOME_WALK=1 \
bash scripts/launch/structured_light_indoors_benchmark.sh
```

Low-cost validation example against an existing benchmark scene:

1. Copy `outputs/benchmark/structured_light_indoors/seed_0/coarse` to a temporary directory.
2. Run the `trajectory` task in `infinigen_311` with reduced planner settings such as `planner_fps=1`, `room_sweep_angle_deg=30`, and `traversal_point_step_m=0.8`.
3. Run `structured_light` from the generated `trajectory/scene.blend` with:
   - `execute_tasks.use_scene_frame_range=False`
   - `execute_tasks.frame_range=[1,1]` or `[1,2]`
   - low `sl_resolution_*`
   - `sl_max_samples=1`
   - a minimal `sl_pattern_dir` containing `white.png` and one pattern file

On the current machine this produces valid structured-light outputs, but Blender may still segfault during shutdown after the render completes. Treat the presence of expected files under `sl_frames/structured_light/` as the success condition for this temporary validation workflow.

For RGB-only trajectory preview renders on reused benchmark scenes, the most reliable low-cost command pattern is:

```bash
conda run -n infinigen_311 python -m infinigen_examples.generate_indoors \
    --seed 0 \
    --task render \
    --input_folder outputs/benchmark/structured_light_indoors/seed_0/trajectory \
    --output_folder outputs/benchmark/structured_light_indoors/seed_0/frames_preview \
    -g benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin \
    -p execute_tasks.use_scene_frame_range=True \
       full/render_image.passes_to_save=[] \
       full/render_image.override_num_samples=16 \
       full/render_image.render_resolution_override='(320, 240)' \
       full/render_image.preview_force_lighting=True
```

Notes:

- preview renders now auto-adjust camera sensor dimensions before saving camera parameters, so `320x240` runs can exit cleanly
- reused indoor benchmark scenes may already have most scene lights deleted by the `coarse` pipeline, so `full/render_image.preview_force_lighting=True` is the intended verification-time fallback
- the visible white speckle problem in old low-cost previews was not caused by `320x240` resolution itself; it came from low-sample Monte Carlo noise plus bright indirect transport, and the preview path now supports `full/render_image.preview_force_denoising=True`, `preview_disable_caustics=True`, and `preview_sample_clamp_*` overrides to control it
- for a cleaner isolated RGB-only rerender from an existing trajectory scene, point `--output_folder` at a fresh parent such as `outputs/.../seed_0_rgb_v11/render`; Infinigen will write the actual frame products under that parent’s sibling `frames/` directory
- on CPU-only machines, a full-sequence Cycles rerender is practical for this benchmark scene when stdout is redirected to a log file; if needed, the same command can be resumed in small `execute_tasks.frame_range=[start,end]` chunks without touching the trajectory scene

Validated full-sequence rerender example on the current machine:

```bash
MPLCONFIGDIR=/tmp/mpl conda run -n infinigen_311 python -m infinigen_examples.generate_indoors \
    --seed 0 \
    --task render \
    --input_folder outputs/benchmark/structured_light_indoors/seed_0/trajectory_check_fps3_v11 \
    --output_folder outputs/benchmark/structured_light_indoors/seed_0_rgb_v11/render \
    -g benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin \
    -p execute_tasks.use_scene_frame_range=True \
       full/render_image.passes_to_save=[] \
       full/render_image.override_num_samples=16 \
       full/render_image.render_resolution_override='(320, 240)' \
       full/render_image.preview_force_lighting=True \
       full/render_image.preview_world_strength=0.25 \
       full/render_image.preview_sun_energy=1.0 \
       full/render_image.preview_camera_light_energy=120.0 \
       full/render_image.preview_force_denoising=True \
       full/render_image.preview_disable_caustics=True \
       full/render_image.preview_sample_clamp_indirect=0.75 \
       full/render_image.preview_sample_clamp_direct=2.5
```

This validated run writes:

- `372` RGB pngs under `outputs/benchmark/structured_light_indoors/seed_0_rgb_v11/frames/Image/camera_0/`
- `372` RGB exrs under the same directory
- `372` camera parameter files under `outputs/benchmark/structured_light_indoors/seed_0_rgb_v11/frames/camview/camera_0/`
- review artifacts such as `rgb_contact_sheet.png` and `rgb_preview_stride4.gif` under `outputs/benchmark/structured_light_indoors/seed_0_rgb_v11/`

## Existing Seed Scene Capture

For batch reruns on already-generated benchmark scenes such as `outputs/benchmark/structured_light_indoors/seed_42/coarse/scene.blend`, use:

```bash
bash scripts/launch/capture_existing_seed_scene.sh <SCENE_DIR> <MODE>
```

where:

- `SCENE_DIR` is the seed root, for example `outputs/benchmark/structured_light_indoors/seed_42`
- `MODE` is `rgb_only` or `full`

The script infers `scene_seed` from the `seed_<N>` folder name, reruns the whole-home trajectory stage if needed, and then renders either RGB-only outputs or the full RGB + structured-light package.

### RGB-only

Recommended command:

```bash
CONDA_ENV=infinigen_311 \
RUN_TAG=fps3_rgb320 \
WALK_FPS=3 \
WALK_STEP_M=0.15 \
RGB_WIDTH=320 \
RGB_HEIGHT=240 \
RGB_SAMPLES=16 \
RGB_DELETE_EXR_AFTER_RENDER=1 \
bash scripts/launch/capture_existing_seed_scene.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    rgb_only
```

This mode:

- writes trajectory outputs to `outputs/benchmark/structured_light_indoors/seed_42/trajectory_<RUN_TAG>/`
- writes RGB outputs to `outputs/benchmark/structured_light_indoors/seed_42_<RUN_TAG>_rgb/frames/`
- deletes RGB `exr` files by default so the final RGB directory only keeps `png` frames plus camera metadata
- writes `rgb_contact_sheet.png` and `rgb_preview_stride*.gif` for quick inspection

### Full

Recommended command:

```bash
CONDA_ENV=infinigen_311 \
RUN_TAG=full_fps3 \
WALK_FPS=3 \
WALK_STEP_M=0.15 \
RGB_WIDTH=848 \
RGB_HEIGHT=480 \
RGB_SAMPLES=32 \
SL_MAX_SAMPLES=128 \
bash scripts/launch/capture_existing_seed_scene.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    full
```

This mode:

- reruns the whole-home trajectory into `trajectory_<RUN_TAG>/`
- rerenders standard RGB into `seed_42_<RUN_TAG>_rgb/frames/`
- keeps RGB `png + exr + camview` by default
- renders structured-light outputs into `seed_42/sl_frames_<RUN_TAG>/structured_light/`

### Main Knobs

Important trajectory controls:

- `WALK_CAMERA_HEIGHT_M`
- `WALK_FPS`
- `WALK_STEP_M`
- `WALK_CLEARANCE_M`
- `WALK_PATH_MARGIN_M`
- `WALK_ROOM_SWEEP_ANGLE_DEG`
- `WALK_ROOM_SWEEP_YAW_SPEED_DEG_S`
- `WALK_ENABLE_ROOM_ORBIT`
- `WALK_ROOM_GRID_STEP_M`
- `WALK_FORCE_OPEN_ACCESS_DOORS`
- `WALK_FORCE_OPEN_ACCESS_DOORS_MODE`

Important RGB render controls:

- `RGB_WIDTH`
- `RGB_HEIGHT`
- `RGB_SAMPLES`
- `RGB_FORCE_LIGHTING`
- `RGB_WORLD_STRENGTH`
- `RGB_SUN_ENERGY`
- `RGB_CAMERA_LIGHT_ENERGY`
- `RGB_FORCE_DENOISING`
- `RGB_DISABLE_CAUSTICS`
- `RGB_SAMPLE_CLAMP_INDIRECT`
- `RGB_SAMPLE_CLAMP_DIRECT`
- `RGB_DELETE_EXR_AFTER_RENDER`

Important structured-light controls:

- `SL_MAX_SAMPLES`

Operational controls:

- `RUN_TAG` controls output folder suffixes
- `REUSE_EXISTING_TRAJECTORY=1` reuses a previously generated trajectory scene
- `FRAME_RANGE=start,end` reruns only a subset of frames for both RGB and structured-light modes
- `RUN_RGB_RENDER_IN_FULL=0` skips standard RGB in `full` mode
- `RUN_STRUCTURED_LIGHT_IN_FULL=0` skips structured-light in `full` mode
- `GENERATE_PREVIEW_ARTIFACTS=0` disables contact sheet and gif generation

## Parallelism Guidance

`coarse` generation is primarily Python solver work plus Blender scene construction, so it benefits from CPU-side parallelism. Structured-light rendering uses Blender Cycles with `scene.cycles.device = "GPU"` and should usually remain single-scene on a single-GPU workstation.

Recommended starting point on a 1x RTX 3090 + 62 GiB RAM machine:

```bash
PARALLEL_MODE=coarse_only MAX_PARALLEL_SCENES=2 \
bash scripts/launch/structured_light_indoors_benchmark.sh
```

If scene generation stalls or total throughput drops, reduce `MAX_PARALLEL_SCENES` to `1`. The coarse stage is dominated by CPU-side solver work, and oversubscribing parallel scenes can make single-scene completion much slower.

## Validation

Recommended first pass:

```bash
NUM_SCENES=1 SEED_START=0 bash scripts/launch/structured_light_indoors_benchmark.sh
```
