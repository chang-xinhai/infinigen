# Structured-Light Indoor Benchmark

This workflow is for generating a small set of higher-quality indoor structured-light scenes for benchmark use, rather than fast iteration.

## Files

- `infinigen_examples/configs_indoor/benchmark.gin`
- `scripts/launch/structured_light_indoors_benchmark.sh`

## What Changes Relative To The Fast Script

The benchmark config increases floor-plan search and object-placement optimization, and it restores richer room layouts by disabling the `has_fewer_rooms=True` shortcut used in `fast_solve.gin`.

The benchmark script also layers in:

- `real_geometry_with_bump.gin` for richer room geometry
- optional `multistory.gin` when `ENABLE_MULTISTORY=1`
- a batch loop over multiple seeds
- log files under `OUTPUT_ROOT/logs/`
- optional background parallelism for the `coarse` stage
- explicit environment-variable entry points for key benchmark hyperparameters

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

## Main Hyperparameters

You can override these directly at launch time:

```bash
NUM_SCENES=10 \
SEED_START=0 \
ROOM_TYPE=ALL \
OUTPUT_ROOT=outputs/benchmark/structured_light_indoors \
RUN_STANDARD_RENDER=0 \
ENABLE_MULTISTORY=0 \
PARALLEL_MODE=coarse_only \
MAX_PARALLEL_SCENES=2 \
FLOORPLAN_DIVIDE_TRIALS=140 \
FLOORPLAN_ITERS_MULT=320 \
SOLVE_STEPS_LARGE=450 \
SOLVE_STEPS_MEDIUM=280 \
SOLVE_STEPS_SMALL=90 \
SL_MAX_SAMPLES=128 \
bash scripts/launch/structured_light_indoors_benchmark.sh
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

## Parallelism Guidance

`coarse` generation is primarily Python solver work plus Blender scene construction, so it benefits from CPU-side parallelism. Structured-light rendering uses Blender Cycles with `scene.cycles.device = "GPU"` and should usually remain single-scene on a single-GPU workstation.

Recommended starting point on a 1x RTX 3090 + 62 GiB RAM machine:

```bash
PARALLEL_MODE=coarse_only MAX_PARALLEL_SCENES=2 \
bash scripts/launch/structured_light_indoors_benchmark.sh
```

## Validation

Recommended first pass:

```bash
NUM_SCENES=1 SEED_START=0 bash scripts/launch/structured_light_indoors_benchmark.sh
```
