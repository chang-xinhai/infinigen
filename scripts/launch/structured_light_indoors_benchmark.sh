#!/bin/bash
# High-quality structured-light indoor benchmark generation.
#
# Default usage:
#   bash scripts/launch/structured_light_indoors_benchmark.sh
#
# Positional usage:
#   bash scripts/launch/structured_light_indoors_benchmark.sh [NUM_SCENES] [SEED_START] [ROOM_TYPE|ALL] [OUTPUT_ROOT]
#
# Environment-variable overrides:
#   NUM_SCENES=10
#   SEED_START=0
#   ROOM_TYPE=ALL
#   OUTPUT_ROOT=outputs/benchmark/structured_light_indoors
#   RUN_STANDARD_RENDER=0
#   ENABLE_MULTISTORY=0
#   PARALLEL_MODE=coarse_only
#   MAX_PARALLEL_SCENES=2
#   FLOORPLAN_DIVIDE_TRIALS=140
#   FLOORPLAN_ITERS_MULT=320
#   SOLVE_STEPS_LARGE=450
#   SOLVE_STEPS_MEDIUM=280
#   SOLVE_STEPS_SMALL=90
#   SL_MAX_SAMPLES=128

set -euo pipefail

NUM_SCENES="${NUM_SCENES:-${1:-40}}"
SEED_START="${SEED_START:-${2:-6}}"
ROOM_TYPE="${ROOM_TYPE:-${3:-ALL}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${4:-outputs/benchmark/structured_light_indoors}}"

RUN_STANDARD_RENDER="${RUN_STANDARD_RENDER:-0}"
ENABLE_MULTISTORY="${ENABLE_MULTISTORY:-0}"
PARALLEL_MODE="${PARALLEL_MODE:-coarse_only}"
MAX_PARALLEL_SCENES="${MAX_PARALLEL_SCENES:-20}"

FLOORPLAN_DIVIDE_TRIALS="${FLOORPLAN_DIVIDE_TRIALS:-140}"
FLOORPLAN_ITERS_MULT="${FLOORPLAN_ITERS_MULT:-320}"
SOLVE_STEPS_LARGE="${SOLVE_STEPS_LARGE:-450}"
SOLVE_STEPS_MEDIUM="${SOLVE_STEPS_MEDIUM:-280}"
SOLVE_STEPS_SMALL="${SOLVE_STEPS_SMALL:-90}"
SL_MAX_SAMPLES="${SL_MAX_SAMPLES:-128}"

COARSE_CONFIGS=(benchmark.gin real_geometry_with_bump.gin)
RENDER_CONFIGS=(benchmark.gin real_geometry_with_bump.gin)
SL_CONFIGS=(benchmark.gin real_geometry_with_bump.gin structured_light.gin)

COMMON_OVERRIDES=(
    "FloorPlanSolver.n_divide_trials=${FLOORPLAN_DIVIDE_TRIALS}"
    "FloorPlanSolver.iters_mult=${FLOORPLAN_ITERS_MULT}"
    "compose_indoors.solve_steps_large=${SOLVE_STEPS_LARGE}"
    "compose_indoors.solve_steps_medium=${SOLVE_STEPS_MEDIUM}"
    "compose_indoors.solve_steps_small=${SOLVE_STEPS_SMALL}"
    "compose_indoors.terrain_enabled=False"
)

SL_OVERRIDES=(
    "render_structured_light.sl_max_samples=${SL_MAX_SAMPLES}"
)

LOG_ROOT="${OUTPUT_ROOT}/logs"
mkdir -p "${LOG_ROOT}"

if [[ "${ENABLE_MULTISTORY}" == "1" ]]; then
    COARSE_CONFIGS+=(multistory.gin)
    RENDER_CONFIGS+=(multistory.gin)
    SL_CONFIGS=(benchmark.gin real_geometry_with_bump.gin multistory.gin structured_light.gin)
fi

if [[ -n "${ROOM_TYPE}" && "${ROOM_TYPE}" != "ALL" ]]; then
    COARSE_CONFIGS+=(singleroom.gin)
    RENDER_CONFIGS+=(singleroom.gin)
    if [[ "${ENABLE_MULTISTORY}" == "1" ]]; then
        SL_CONFIGS=(benchmark.gin real_geometry_with_bump.gin multistory.gin singleroom.gin structured_light.gin)
    else
        SL_CONFIGS=(benchmark.gin real_geometry_with_bump.gin singleroom.gin structured_light.gin)
    fi
    COMMON_OVERRIDES+=("restrict_solving.restrict_parent_rooms=[\"${ROOM_TYPE}\"]")
    SCENE_SCOPE="single-room (${ROOM_TYPE})"
else
    SCENE_SCOPE="whole-home"
fi

echo "═══════════════════════════════════════════════════════════"
echo "  Structured Light Indoor Benchmark"
echo "  Scenes: ${NUM_SCENES}"
echo "  Seed start: ${SEED_START}"
echo "  Scope: ${SCENE_SCOPE}"
echo "  Output root: ${OUTPUT_ROOT}"
echo "  Multistory: ${ENABLE_MULTISTORY}"
echo "  Parallel mode: ${PARALLEL_MODE}"
echo "  Max parallel scenes: ${MAX_PARALLEL_SCENES}"
echo "  FloorPlanSolver.n_divide_trials: ${FLOORPLAN_DIVIDE_TRIALS}"
echo "  FloorPlanSolver.iters_mult: ${FLOORPLAN_ITERS_MULT}"
echo "  solve_steps_large/medium/small: ${SOLVE_STEPS_LARGE}/${SOLVE_STEPS_MEDIUM}/${SOLVE_STEPS_SMALL}"
echo "  SL max samples: ${SL_MAX_SAMPLES}"
echo "═══════════════════════════════════════════════════════════"

run_coarse() {
    local seed="$1"
    local output_dir="$2"

    python -m infinigen_examples.generate_indoors \
        --seed "${seed}" \
        --task coarse \
        --output_folder "${output_dir}/coarse" \
        -g "${COARSE_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}"
}

run_render_and_sl() {
    local seed="$1"
    local output_dir="$2"

    if [[ "${RUN_STANDARD_RENDER}" == "1" ]]; then
        echo ""
        echo ">>> Step 2/3: Rendering standard RGB ..."
        python -m infinigen_examples.generate_indoors \
            --seed "${seed}" \
            --task render \
            --input_folder "${output_dir}/coarse" \
            --output_folder "${output_dir}/frames" \
            -g "${RENDER_CONFIGS[@]}" \
            -p "${COMMON_OVERRIDES[@]}"
    else
        echo ""
        echo ">>> Step 2/3: Skipped standard RGB render (RUN_STANDARD_RENDER=0)"
    fi

    echo ""
    echo ">>> Step 3/3: Rendering structured light ..."
    python -m infinigen_examples.generate_indoors \
        --seed "${seed}" \
        --task structured_light \
        --input_folder "${output_dir}/coarse" \
        --output_folder "${output_dir}/sl_frames" \
        -g "${SL_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}" "${SL_OVERRIDES[@]}"
}

wait_for_slot() {
    while true; do
        local running
        running=$(jobs -rp | wc -l)
        if [[ "${running}" -lt "${MAX_PARALLEL_SCENES}" ]]; then
            break
        fi
        wait -n
    done
}

if [[ "${PARALLEL_MODE}" == "coarse_only" ]]; then
    for ((i = 0; i < NUM_SCENES; i++)); do
        SEED=$((SEED_START + i))
        OUTPUT_DIR="${OUTPUT_ROOT}/seed_${SEED}"
        LOG_FILE="${LOG_ROOT}/seed_${SEED}_coarse.log"

        mkdir -p "${OUTPUT_DIR}"
        echo ""
        echo "-----------------------------------------------------------"
        echo "Benchmark scene $((i + 1))/${NUM_SCENES}  seed=${SEED}"
        echo "Output: ${OUTPUT_DIR}"
        echo "Coarse log: ${LOG_FILE}"
        echo "-----------------------------------------------------------"
        echo ">>> Step 1/3: Queueing benchmark indoor scene generation ..."

        wait_for_slot
        (
            run_coarse "${SEED}" "${OUTPUT_DIR}"
        ) >"${LOG_FILE}" 2>&1 &
    done

    wait

    for ((i = 0; i < NUM_SCENES; i++)); do
        SEED=$((SEED_START + i))
        OUTPUT_DIR="${OUTPUT_ROOT}/seed_${SEED}"
        LOG_FILE="${LOG_ROOT}/seed_${SEED}_render_sl.log"

        echo ""
        echo "-----------------------------------------------------------"
        echo "Post-processing scene $((i + 1))/${NUM_SCENES}  seed=${SEED}"
        echo "Render/SL log: ${LOG_FILE}"
        echo "-----------------------------------------------------------"

        (
            run_render_and_sl "${SEED}" "${OUTPUT_DIR}"
        ) >"${LOG_FILE}" 2>&1
    done
elif [[ "${PARALLEL_MODE}" == "off" ]]; then
    for ((i = 0; i < NUM_SCENES; i++)); do
        SEED=$((SEED_START + i))
        OUTPUT_DIR="${OUTPUT_ROOT}/seed_${SEED}"
        LOG_FILE="${LOG_ROOT}/seed_${SEED}.log"

        mkdir -p "${OUTPUT_DIR}"
        echo ""
        echo "-----------------------------------------------------------"
        echo "Benchmark scene $((i + 1))/${NUM_SCENES}  seed=${SEED}"
        echo "Output: ${OUTPUT_DIR}"
        echo "Log: ${LOG_FILE}"
        echo "-----------------------------------------------------------"

        (
            echo ">>> Step 1/3: Generating benchmark indoor scene ..."
            run_coarse "${SEED}" "${OUTPUT_DIR}"
            run_render_and_sl "${SEED}" "${OUTPUT_DIR}"
        ) >"${LOG_FILE}" 2>&1
    done
else
    echo "Unsupported PARALLEL_MODE=${PARALLEL_MODE}"
    echo "Supported values: off, coarse_only"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Benchmark generation complete"
echo "  Scenes written under: ${OUTPUT_ROOT}"
echo "  Logs written under: ${LOG_ROOT}"
echo "  Scene file: seed_<N>/coarse/scene.blend"
echo "  SL output: seed_<N>/sl_frames/structured_light/"
echo "═══════════════════════════════════════════════════════════"
