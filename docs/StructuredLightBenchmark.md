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
- review artifacts such as `rgb_first_frame.png`, `rgb_contact_sheet.png`, and `rgb_preview_stride4.gif` under `outputs/benchmark/structured_light_indoors/seed_0_rgb_v11/`

## Existing Seed Scene Capture

For batch reruns on already-generated benchmark scenes such as `outputs/benchmark/structured_light_indoors/seed_42/coarse/scene.blend`, use:

```bash
bash scripts/launch/capture_existing_seed_scene.sh <SCENE_DIR> [SETTING] [--resume] [--resume-from N]
```

where:

- `SCENE_DIR` is the seed root, for example `outputs/benchmark/structured_light_indoors/seed_42`
- `SETTING` selects the capture manifest and the output directory name, for example `test`, `rgb_only`, `debug`, or `full`

The script infers `scene_seed` from the `seed_<N>` folder name, reuses or regenerates `trajectory/`, and then runs one manifest-driven structured-light capture task. The manifest is the single source of truth for which patterns, cameras, formats, and calibration payloads are written. The matching `infinigen_examples/configs_indoor/<setting>.gin` file is the single source of truth for trajectory tuning, preview resolution, and structured-light render defaults for that setting.

Important detail:

- `seed_<N>/capture/<setting>/config/capture_manifest.yaml` is a post-run snapshot copied by the script for bookkeeping
- the actual pre-run configuration source is the manifest selected before launch, either `infinigen_examples/configs_indoor/capture_manifests/<setting>.yaml` or the file passed through `CAPTURE_MANIFEST=/path/to/custom.yaml`
- if you want to change outputs such as dropping RGB depth `png`, edit the source manifest before capture instead of editing the copied snapshot after capture
- in `--resume` mode, the script first tries to reuse `capture/<setting>/config/capture_manifest.yaml` so the rerun matches the interrupted run as closely as possible; if that archived manifest is missing, the script prints a warning and falls back to the configured manifest source

Resume notes:

- `--resume` keeps the existing output tree and skips frames whose required outputs already exist
- `CAPTURE_LOG_MODE=compact` is now the default and keeps only the first `CAPTURE_LOG_LINES` lines plus the last `CAPTURE_LOG_LINES` lines in `capture/<setting>/logs/render.log`
- in compact mode, `capture/<setting>/logs/render.tail.log` is updated as a live rolling tail while the job is active
- set `CAPTURE_LOG_MODE=full` to keep the previous full merged log behavior, or `CAPTURE_LOG_MODE=none` to disable command stdout/stderr capture entirely
- if a frame’s images are present but its calibration record is missing, resume will append the missing calibration entry without rerendering the frame
- `--resume-from N` forces resume to start considering frames from capture index `N`
- incremental calibration progress is written to `capture/<setting>/output/calibration/calibration.jsonl`
- aggregate calibration in `calibration.npz` is rebuilt at the end of a successful run
- the explicit completion marker for a fully consistent capture is `capture/<setting>/output/calibration/capture_complete.json`

### Full

Recommended command:

```bash
CONDA_ENV=infinigen_311 \
bash scripts/launch/capture_existing_seed_scene.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    full
```

This setting:

- uses `infinigen_examples/configs_indoor/full.gin` for the built-in trajectory and render defaults
- writes reusable walking animation to `seed_<N>/trajectory/`
- writes the capture to `seed_<N>/capture/full/`
- writes the selected manifest to `capture/full/config/capture_manifest.yaml`
- writes the merged run log to `capture/full/logs/render.log`
- default log retention is compact: `render.log` keeps the first 100 lines and the last 100 lines, while `render.tail.log` mirrors the live rolling tail during the run
- writes the scene-level depth histogram summary to `capture/full/stats/depth_histogram.{json,png}`
- writes selected pattern png files to `capture/full/structured_light/patterns/`
- writes actual render outputs to `capture/full/output/`
- writes incremental calibration progress to `capture/full/output/calibration/calibration.jsonl`
- writes aggregate calibration to `capture/full/output/calibration/calibration.npz`
- writes an explicit completion marker to `capture/full/output/calibration/capture_complete.json`

### RGB-only

Recommended command:

```bash
CONDA_ENV=infinigen_311 \
bash scripts/launch/capture_existing_seed_scene.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    rgb_only
```

This setting uses `infinigen_examples/configs_indoor/rgb_only.gin` together with `infinigen_examples/configs_indoor/capture_manifests/rgb_only.yaml`, disables L/R image export, and still writes RGB image, depth, normal, plus aggregate calibration under `seed_<N>/capture/rgb_only/output/`.

### Debug

For quick structured-light checks with one pattern and optional JSONL calibration:

```bash
CONDA_ENV=infinigen_311 \
bash scripts/launch/capture_existing_seed_scene.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    debug
```

This setting uses `infinigen_examples/configs_indoor/debug.gin` plus `infinigen_examples/configs_indoor/capture_manifests/debug.yaml`.

### Test

For the lightest built-in capture that still keeps one structured-light pattern:

```bash
CONDA_ENV=infinigen_311 \
bash scripts/launch/capture_existing_seed_scene.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    test
```

This setting uses `infinigen_examples/configs_indoor/test.gin` together with `infinigen_examples/configs_indoor/capture_manifests/test.yaml`, keeps only `rgb/image/*.png`, and writes one `d435` pattern image per IR camera.

### Test Trajectory

For handheld-like trajectory tuning with reduced render cost, use:

```bash
CONDA_ENV=infinigen \
FRAME_RANGE=0,39 \
timeout 1h bash scripts/launch/capture_existing_seed_scene.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    test_traj
```

This preset combines:

- `infinigen_examples/configs_indoor/test_traj.gin` for smoother walk defaults plus preview render settings
- `infinigen_examples/configs_indoor/capture_manifests/test_traj.yaml` for `rgb/image/*.png` plus one `d435` image per IR camera
- `planner_fps = 16`
- `traversal_speed_mps = 0.48`
- `traversal_point_step_m = 0.03`
- `room_sweep_angle_deg = 60.0`
- `enable_room_orbit = False`
- `handheld_lateral_amplitude_m = 0.0`
- `handheld_yaw_amplitude_deg = 0.0`
- `render_structured_light.sl_resolution_x = 320`
- `render_structured_light.sl_resolution_y = 240`
- `render_structured_light.sl_max_samples = 6`

`test_traj` regenerates `trajectory/` by default so trajectory-tuning changes take effect immediately. Set `REUSE_EXISTING_TRAJECTORY=1` only when you intentionally want to inspect an already-saved animation.

Use `FRAME_RANGE=start,end` to render only a short clip while checking motion quality, and wrap the command with shell `timeout 1h` to cap exploratory runs.

For an interactive Blender preview that regenerates only `trajectory/scene.blend` and then plays the animated camera path in the viewport, use:

```bash
bash scripts/launch/preview_existing_seed_trajectory.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    test_traj
```

See `docs/TrajectoryPreview.md` for viewport shading options and caveats versus final rendered RGB.

The rerun layout is now:

```text
seed_<N>/
├── coarse/
├── trajectory/
└── capture/
    └── <setting>/
        ├── config/
        ├── logs/
        │   ├── render.log
        │   └── render.tail.log
        ├── output/
        │   ├── calibration/
        │   ├── rgb/
        │   ├── IR_left/
        │   └── IR_right/
        ├── stats/
        └── structured_light/
            └── patterns/
```

### SLURM Batch Reruns

For multi-GPU reruns on already-generated scenes under `outputs/benchmark/structured_light_indoors/seed_<N>`, use:

```bash
bash scripts/launch/capture_existing_seed_scenes_parallel.sh [OUTPUT_ROOT] [SETTING] [single-scene args...]
```

The script:

- scans `seed_*` directories under `OUTPUT_ROOT`
- keeps only scenes with `coarse/scene.blend`
- skips already-completed scenes by default when `capture/<setting>/output/calibration/capture_complete.json` exists
- dynamically assigns the remaining scenes across available GPUs so faster workers keep pulling new scenes
- forwards any extra CLI arguments directly to `scripts/launch/capture_existing_seed_scene.sh`, so batch reruns stay aligned with the latest single-scene workflow
- gives each scene invocation an isolated runtime directory for `TMPDIR`, `MPLCONFIGDIR`, XDG cache/config, and Blender user config paths to avoid worker interference
- when runtime isolation is enabled, mirrors caller-visible Blender user addons and extension repos into each isolated worker runtime so addons such as `Projectors` remain available
- writes a batch summary to `OUTPUT_ROOT/logs/existing_seed_capture/summary_<setting>_<timestamp>.tsv`
- archives the batch launch settings to `OUTPUT_ROOT/logs/existing_seed_capture/batch_<setting>_<timestamp>.env`
- forwards `CAPTURE_LOG_MODE` and `CAPTURE_LOG_LINES` through the environment so every scene can use compact, full, or disabled logging consistently

Recommended H100 submission flow with the current `scripts/submit.sh` resource request of `8` GPUs and `120` CPUs:

```bash
CONDA_ENV=infinigen_311 \
MAX_PARALLEL_SCENES=8 \
TOTAL_CPUS=120 \
sbatch scripts/submit.sh \
    bash scripts/launch/capture_existing_seed_scenes_parallel.sh \
    outputs/benchmark/structured_light_indoors \
    full
```

`scripts/submit.sh` now executes the payload directly inside the batch allocation by default instead of wrapping it in a nested `srun` step. This avoids cluster setups where `srun` fails host lookup during step launch with errors such as `Unable to resolve "node003"`. If your SLURM deployment requires `srun`, set `SUBMIT_USE_SRUN=1` in the submission environment.

To batch-resume partially completed captures with the exact single-scene semantics, append the same flags you would use for one scene:

```bash
CONDA_ENV=infinigen_311 \
MAX_PARALLEL_SCENES=8 \
TOTAL_CPUS=120 \
bash scripts/launch/capture_existing_seed_scenes_parallel.sh \
    outputs/benchmark/structured_light_indoors \
    full \
    --resume \
    --resume-from 120
```

Useful overrides:

- `CAPTURE_LOG_MODE=compact|full|none` controls per-scene log retention; `compact` is the default
- `CAPTURE_LOG_LINES=<N>` changes how many first and last lines are kept in compact mode; the default is `100`
- `SKIP_COMPLETED=0` forces rerender even when the done marker already exists
- `GPU_IDS=0,1,2,3,4,5,6,7` pins the worker pool to an explicit GPU list
- `MAX_PARALLEL_SCENES=<N>` reduces concurrency below the number of visible GPUs
- `DONE_MARKER_REL=...` changes the completion check if you want a stricter or looser resume policy; the default is now `capture/<setting>/output/calibration/capture_complete.json`
- `ISOLATE_RUNTIME=0` disables the per-scene runtime sandbox if you explicitly want all workers to share the caller's temp/cache paths
- `INHERIT_BLENDER_ADDONS=0` disables mirroring caller-visible Blender addons and extensions into the isolated worker runtime; the default is `1`
- `BLENDER_USER_SCRIPTS=/path/to/.../scripts`, `BLENDER_ADDONS=/path/to/.../scripts/addons`, and `BLENDER_EXTENSIONS_USER=/path/to/.../extensions/user_default` let you point the isolated workers at explicit addon sources when auto-discovery is not enough
- `KEEP_RUNTIME=1` preserves the batch runtime directory under the temporary parent for postmortem debugging
- `SUBMIT_USE_SRUN=1` restores the old nested-`srun` launch behavior if your cluster needs it
- `CAPTURE_MANIFEST`, `FRAME_RANGE`, `REUSE_EXISTING_TRAJECTORY`, and `DEPTH_HISTOGRAM_*` are still runtime controls inherited by each single-scene job

### Main Config Files

Edit the setting gin when you want to change trajectory or render defaults:

- `infinigen_examples/configs_indoor/full.gin`
- `infinigen_examples/configs_indoor/test.gin`
- `infinigen_examples/configs_indoor/test_traj.gin`
- `infinigen_examples/configs_indoor/rgb_only.gin`
- `infinigen_examples/configs_indoor/debug.gin`

The shared built-in defaults for the non-`test_traj` presets live in:

- `infinigen_examples/configs_indoor/capture_existing_seed_defaults.gin`

Use the manifest when you want to change which cameras, patterns, output formats, or calibration payloads are written:

- `CAPTURE_MANIFEST`

The built-in manifests live under:

- `infinigen_examples/configs_indoor/capture_manifests/full.yaml`
- `infinigen_examples/configs_indoor/capture_manifests/test.yaml`
- `infinigen_examples/configs_indoor/capture_manifests/test_traj.yaml`
- `infinigen_examples/configs_indoor/capture_manifests/rgb_only.yaml`
- `infinigen_examples/configs_indoor/capture_manifests/debug.yaml`

The launch script resolves the manifest like this:

- default: `infinigen_examples/configs_indoor/capture_manifests/<SETTING>.yaml`
- override: `CAPTURE_MANIFEST=/path/to/custom.yaml`

The selected manifest is copied to `capture/<setting>/config/capture_manifest.yaml` after startup so each capture folder keeps a record of the exact inputs that were used.

### Editing Outputs Before Capture

To customize outputs, create or edit the source manifest before running the script.

The default `full.yaml` keeps RGB image in `png`, while depth and normal stay in `exr`:

```yaml
cameras:
  rgb:
    outputs:
      image:
        - png
      depth:
        - exr
      normal:
        - exr
```

If you want a different format mix, edit the source manifest before capture. For example, to write both `png` and `exr` for RGB image while also exporting depth and normal in both formats, change it to:

```yaml
cameras:
  rgb:
    outputs:
      image:
        - png
        - exr
      depth:
        - png
        - exr
      normal:
        - png
        - exr
```

The recommended workflow is to create a new manifest instead of editing `full.yaml` in place. For example:

```bash
cp infinigen_examples/configs_indoor/capture_manifests/full.yaml \
   infinigen_examples/configs_indoor/capture_manifests/full_exr_only.yaml
```

Then edit `full_exr_only.yaml` and run:

```bash
CAPTURE_MANIFEST=infinigen_examples/configs_indoor/capture_manifests/full_exr_only.yaml \
bash scripts/launch/capture_existing_seed_scene.sh \
    outputs/benchmark/structured_light_indoors/seed_42 \
    full_exr_only
```

This keeps behavior and output naming aligned:

- the source manifest controls what is rendered
- the positional `SETTING` or `CAPTURE_SETTING` names the output folder
- `capture/full_exr_only/config/capture_manifest.yaml` is just the archived copy of the source manifest used for that run

Operational controls:

- `REUSE_EXISTING_TRAJECTORY=1` reuses a previously generated trajectory scene
- `FRAME_RANGE=start,end` reruns only a subset of frames for the manifest-selected capture
- `DEPTH_HISTOGRAM_ENABLED=0` disables scene-level depth histogram generation
- `DEPTH_HISTOGRAM_BINS`, `DEPTH_HISTOGRAM_MIN_M`, and `DEPTH_HISTOGRAM_MAX_M` control histogram binning and clipping

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
