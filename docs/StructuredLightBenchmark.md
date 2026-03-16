# Structured-Light Indoor Benchmark

This workflow is for generating a small set of indoor structured-light benchmark scenes with slightly higher quality than `fast_solve.gin`, without paying the previous order-of-magnitude runtime cost.

## Files

- `infinigen_examples/configs_indoor/benchmark.gin`
- `scripts/launch/structured_light_indoors_benchmark.sh`

## What Changes Relative To The Fast Script

The benchmark config increases floor-plan search and object-placement optimization relative to `fast_solve.gin`, but it stays in the same general runtime regime by keeping `has_fewer_rooms=True` and using moderate solve counts.

The benchmark script also layers in:

- `real_geometry_with_bump.gin` for richer room geometry
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
PARALLEL_MODE=coarse_only \
MAX_PARALLEL_SCENES=2 \
SL_MAX_SAMPLES=128 \
FAIL_ON_ANY_SEED_FAILURE=1 \
bash scripts/launch/structured_light_indoors_benchmark.sh
```

Additional compatibility knobs:

- `FAIL_ON_ANY_SEED_FAILURE=1` keeps processing all seeds but returns a non-zero exit code at the end if any seed failed
- `FAIL_ON_ANY_SEED_FAILURE=0` keeps processing all seeds and returns success even when some seeds fail
- `PYTHON_BIN=/path/to/python` overrides the Python executable used by the launch script

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
- `sl_frames/structured_light/` stores structured-light outputs
- `frames/` is generated only when `RUN_STANDARD_RENDER=1`
- `logs/seed_<N>_coarse.log` stores coarse-generation logs
- `logs/seed_<N>_render_sl.log` stores render and structured-light logs in `coarse_only` mode
- `logs/seed_<N>.log` stores the full run in `off` mode
- `logs/benchmark_summary.tsv` stores per-seed `coarse` and `postprocess` status for the full batch

When a seed fails during `coarse`, the benchmark script now keeps running the remaining seeds, marks the failed seed in `benchmark_summary.tsv`, and skips render / structured-light post-processing for that seed instead of aborting the entire batch immediately.

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
