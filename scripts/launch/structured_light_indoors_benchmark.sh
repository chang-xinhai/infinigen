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
#   ENABLE_WHOLE_HOME_WALK=1
#   REUSE_EXISTING_COARSE=0
#   PARALLEL_MODE=coarse_only
#   MAX_PARALLEL_SCENES=2
#   SL_MAX_SAMPLES=128

set -euo pipefail

NUM_SCENES="${NUM_SCENES:-${1:-1}}"
SEED_START="${SEED_START:-${2:-0}}"
ROOM_TYPE="${ROOM_TYPE:-${3:-ALL}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${4:-outputs/benchmark/structured_light_indoors}}"

RUN_STANDARD_RENDER="${RUN_STANDARD_RENDER:-0}"
ENABLE_MULTISTORY="${ENABLE_MULTISTORY:-0}"
ENABLE_WHOLE_HOME_WALK="${ENABLE_WHOLE_HOME_WALK:-1}"
REUSE_EXISTING_COARSE="${REUSE_EXISTING_COARSE:-0}"
PARALLEL_MODE="${PARALLEL_MODE:-coarse_only}"
MAX_PARALLEL_SCENES="${MAX_PARALLEL_SCENES:-10}"
FAIL_ON_ANY_SEED_FAILURE="${FAIL_ON_ANY_SEED_FAILURE:-1}"
PYTHON_BIN="${PYTHON_BIN:-python}"

SL_MAX_SAMPLES="${SL_MAX_SAMPLES:-128}"
WALK_CAMERA_HEIGHT_M="${WALK_CAMERA_HEIGHT_M:-1.55}"
WALK_FPS="${WALK_FPS:-8}"
WALK_STEP_M="${WALK_STEP_M:-0.05}"
WALK_CLEARANCE_M="${WALK_CLEARANCE_M:-0.20}"
WALK_PATH_MARGIN_M="${WALK_PATH_MARGIN_M:-0.18}"
WALK_PATH_RESOLUTION="${WALK_PATH_RESOLUTION:-160000}"

COARSE_CONFIGS=(benchmark.gin real_geometry_with_bump.gin)
TRAJECTORY_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin)
RENDER_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin)
SL_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin structured_light.gin)

COMMON_OVERRIDES=("compose_indoors.terrain_enabled=False")
TRAJECTORY_OVERRIDES=(
    "animate_whole_home_walk.camera_height_m=${WALK_CAMERA_HEIGHT_M}"
    "animate_whole_home_walk.planner_fps=${WALK_FPS}"
    "animate_whole_home_walk.traversal_point_step_m=${WALK_STEP_M}"
    "animate_whole_home_walk.clearance_m=${WALK_CLEARANCE_M}"
    "animate_whole_home_walk.path_margin_m=${WALK_PATH_MARGIN_M}"
    "animate_whole_home_walk.path_resolution=${WALK_PATH_RESOLUTION}"
)

SL_OVERRIDES=(
    "render_structured_light.sl_max_samples=${SL_MAX_SAMPLES}"
)

LOG_ROOT="${OUTPUT_ROOT}/logs"
SUMMARY_FILE="${LOG_ROOT}/benchmark_summary.tsv"
mkdir -p "${LOG_ROOT}"

declare -A COARSE_STATUS
declare -A POST_STATUS
declare -a ACTIVE_COARSE_PIDS=()
declare -a ACTIVE_COARSE_SEEDS=()

if [[ "${ENABLE_MULTISTORY}" == "1" ]]; then
    COARSE_CONFIGS+=(multistory.gin)
    TRAJECTORY_CONFIGS+=(multistory.gin)
    RENDER_CONFIGS=(benchmark.gin real_geometry_with_bump.gin multistory.gin whole_home_walk.gin)
    SL_CONFIGS=(benchmark.gin real_geometry_with_bump.gin multistory.gin whole_home_walk.gin structured_light.gin)
fi

if [[ -n "${ROOM_TYPE}" && "${ROOM_TYPE}" != "ALL" ]]; then
    COARSE_CONFIGS+=(singleroom.gin)
    TRAJECTORY_CONFIGS+=(singleroom.gin)
    if [[ "${ENABLE_MULTISTORY}" == "1" ]]; then
        RENDER_CONFIGS=(benchmark.gin real_geometry_with_bump.gin multistory.gin singleroom.gin whole_home_walk.gin)
    else
        RENDER_CONFIGS=(benchmark.gin real_geometry_with_bump.gin singleroom.gin whole_home_walk.gin)
    fi
    if [[ "${ENABLE_MULTISTORY}" == "1" ]]; then
        SL_CONFIGS=(benchmark.gin real_geometry_with_bump.gin multistory.gin singleroom.gin whole_home_walk.gin structured_light.gin)
    else
        SL_CONFIGS=(benchmark.gin real_geometry_with_bump.gin singleroom.gin whole_home_walk.gin structured_light.gin)
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
echo "  Whole-home walk: ${ENABLE_WHOLE_HOME_WALK}"
echo "  Reuse existing coarse: ${REUSE_EXISTING_COARSE}"
echo "  Parallel mode: ${PARALLEL_MODE}"
echo "  Max parallel scenes: ${MAX_PARALLEL_SCENES}"
echo "  SL max samples: ${SL_MAX_SAMPLES}"
echo "  Walk camera height: ${WALK_CAMERA_HEIGHT_M}"
echo "  Walk fps: ${WALK_FPS}"
echo "  Walk step: ${WALK_STEP_M}"
echo "  Fail on any seed failure: ${FAIL_ON_ANY_SEED_FAILURE}"
echo "═══════════════════════════════════════════════════════════"

run_coarse() {
    local seed="$1"
    local output_dir="$2"

    "${PYTHON_BIN}" -m infinigen_examples.generate_indoors \
        --seed "${seed}" \
        --task coarse \
        --output_folder "${output_dir}/coarse" \
        -g "${COARSE_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}"
}

run_trajectory() {
    local seed="$1"
    local output_dir="$2"

    "${PYTHON_BIN}" -m infinigen_examples.generate_indoors \
        --seed "${seed}" \
        --task trajectory \
        --input_folder "${output_dir}/coarse" \
        --output_folder "${output_dir}/trajectory" \
        -g "${TRAJECTORY_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}" "${TRAJECTORY_OVERRIDES[@]}"
}

run_render_and_sl() {
    local seed="$1"
    local output_dir="$2"
    local render_input="${output_dir}/coarse"

    if [[ "${ENABLE_WHOLE_HOME_WALK}" == "1" ]]; then
        echo ""
        echo ">>> Step 2/4: Planning whole-home walk trajectory ..."
        run_trajectory "${seed}" "${output_dir}"
        render_input="${output_dir}/trajectory"
    fi

    if [[ "${RUN_STANDARD_RENDER}" == "1" ]]; then
        echo ""
        echo ">>> Step 3/4: Rendering standard RGB ..."
        "${PYTHON_BIN}" -m infinigen_examples.generate_indoors \
            --seed "${seed}" \
            --task render \
            --input_folder "${render_input}" \
            --output_folder "${output_dir}/frames" \
            -g "${RENDER_CONFIGS[@]}" \
            -p "${COMMON_OVERRIDES[@]}"
    else
        echo ""
        echo ">>> Step 3/4: Skipped standard RGB render (RUN_STANDARD_RENDER=0)"
    fi

    echo ""
    echo ">>> Step 4/4: Rendering structured light ..."
    "${PYTHON_BIN}" -m infinigen_examples.generate_indoors \
        --seed "${seed}" \
        --task structured_light \
        --input_folder "${render_input}" \
        --output_folder "${output_dir}/sl_frames" \
        -g "${SL_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}" "${SL_OVERRIDES[@]}"
}

mark_existing_or_pending_coarse() {
    local seed="$1"
    local output_dir="$2"
    if [[ "${REUSE_EXISTING_COARSE}" == "1" && -f "${output_dir}/coarse/scene.blend" ]]; then
        COARSE_STATUS["${seed}"]="success"
        POST_STATUS["${seed}"]="pending"
        echo "Reusing existing coarse scene for seed=${seed} at ${output_dir}/coarse/scene.blend"
        return 0
    fi
    return 1
}

collect_finished_coarse_jobs() {
    local remaining_pids=()
    local remaining_seeds=()
    local pid
    local seed
    local rc
    local idx

    for idx in "${!ACTIVE_COARSE_PIDS[@]}"; do
        pid="${ACTIVE_COARSE_PIDS[$idx]}"
        seed="${ACTIVE_COARSE_SEEDS[$idx]}"

        if kill -0 "${pid}" 2>/dev/null; then
            remaining_pids+=("${pid}")
            remaining_seeds+=("${seed}")
            continue
        fi

        set +e
        wait "${pid}"
        rc=$?
        set -e

        if [[ "${rc}" -eq 0 ]]; then
            COARSE_STATUS["${seed}"]="success"
        else
            COARSE_STATUS["${seed}"]="failed(${rc})"
            echo "WARNING: coarse generation failed for seed ${seed} with exit code ${rc}. See ${LOG_ROOT}/seed_${seed}_coarse.log"
        fi
    done

    ACTIVE_COARSE_PIDS=("${remaining_pids[@]}")
    ACTIVE_COARSE_SEEDS=("${remaining_seeds[@]}")
}

wait_for_slot() {
    collect_finished_coarse_jobs
    while [[ "${#ACTIVE_COARSE_PIDS[@]}" -ge "${MAX_PARALLEL_SCENES}" ]]; do
        sleep 1
        collect_finished_coarse_jobs
    done
}

wait_for_all_coarse() {
    collect_finished_coarse_jobs
    while [[ "${#ACTIVE_COARSE_PIDS[@]}" -gt 0 ]]; do
        sleep 1
        collect_finished_coarse_jobs
    done
}

run_postprocess_with_status() {
    local seed="$1"
    local output_dir="$2"
    local log_file="$3"
    local rc

    set +e
    (
        run_render_and_sl "${seed}" "${output_dir}"
    ) >"${log_file}" 2>&1
    rc=$?
    set -e

    if [[ "${rc}" -eq 0 ]]; then
        POST_STATUS["${seed}"]="success"
    else
        POST_STATUS["${seed}"]="failed(${rc})"
        echo "WARNING: render/structured-light failed for seed ${seed} with exit code ${rc}. See ${log_file}"
    fi
}

write_summary() {
    local coarse_ok=0
    local coarse_failed=0
    local post_ok=0
    local post_failed=0
    local post_skipped=0
    local any_failed=0
    local seed
    local coarse_state
    local post_state

    : >"${SUMMARY_FILE}"
    printf "seed\tcoarse\tpostprocess\n" >>"${SUMMARY_FILE}"

    for ((i = 0; i < NUM_SCENES; i++)); do
        seed=$((SEED_START + i))
        coarse_state="${COARSE_STATUS[${seed}]:-not_started}"
        post_state="${POST_STATUS[${seed}]:-not_started}"
        printf "%s\t%s\t%s\n" "${seed}" "${coarse_state}" "${post_state}" >>"${SUMMARY_FILE}"

        if [[ "${coarse_state}" == "success" ]]; then
            ((coarse_ok += 1))
        else
            ((coarse_failed += 1))
            any_failed=1
        fi

        case "${post_state}" in
            success)
                ((post_ok += 1))
                ;;
            skipped)
                ((post_skipped += 1))
                ;;
            failed*)
                ((post_failed += 1))
                any_failed=1
                ;;
            *)
                any_failed=1
                ;;
        esac
    done

    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  Benchmark generation complete"
    echo "  Scenes written under: ${OUTPUT_ROOT}"
    echo "  Logs written under: ${LOG_ROOT}"
    echo "  Summary written to: ${SUMMARY_FILE}"
    echo "  Coarse success: ${coarse_ok}"
    echo "  Coarse failed: ${coarse_failed}"
    echo "  Post success: ${post_ok}"
    echo "  Post failed: ${post_failed}"
    echo "  Post skipped: ${post_skipped}"
    echo "  Scene file: seed_<N>/coarse/scene.blend"
    echo "  Trajectory file: seed_<N>/trajectory/scene.blend"
    echo "  SL output: seed_<N>/sl_frames/structured_light/"
    echo "═══════════════════════════════════════════════════════════"

    if [[ "${any_failed}" -eq 1 && "${FAIL_ON_ANY_SEED_FAILURE}" == "1" ]]; then
        return 1
    fi
}

if [[ "${PARALLEL_MODE}" == "coarse_only" ]]; then
    for ((i = 0; i < NUM_SCENES; i++)); do
        SEED=$((SEED_START + i))
        OUTPUT_DIR="${OUTPUT_ROOT}/seed_${SEED}"
        LOG_FILE="${LOG_ROOT}/seed_${SEED}_coarse.log"

        mkdir -p "${OUTPUT_DIR}"
        if mark_existing_or_pending_coarse "${SEED}" "${OUTPUT_DIR}"; then
            continue
        fi

        COARSE_STATUS["${SEED}"]="running"
        POST_STATUS["${SEED}"]="pending"
        echo ""
        echo "-----------------------------------------------------------"
        echo "Benchmark scene $((i + 1))/${NUM_SCENES}  seed=${SEED}"
        echo "Output: ${OUTPUT_DIR}"
        echo "Coarse log: ${LOG_FILE}"
        echo "-----------------------------------------------------------"
        echo ">>> Step 1/4: Queueing benchmark indoor scene generation ..."

        wait_for_slot
        (
            run_coarse "${SEED}" "${OUTPUT_DIR}"
        ) >"${LOG_FILE}" 2>&1 &
        ACTIVE_COARSE_PIDS+=("$!")
        ACTIVE_COARSE_SEEDS+=("${SEED}")
    done

    wait_for_all_coarse

    for ((i = 0; i < NUM_SCENES; i++)); do
        SEED=$((SEED_START + i))
        OUTPUT_DIR="${OUTPUT_ROOT}/seed_${SEED}"
        LOG_FILE="${LOG_ROOT}/seed_${SEED}_render_sl.log"

        if [[ "${COARSE_STATUS[${SEED}]}" != "success" ]]; then
            POST_STATUS["${SEED}"]="skipped"
            echo ""
            echo "-----------------------------------------------------------"
            echo "Skipping post-processing for seed=${SEED}"
            echo "Reason: coarse generation status is ${COARSE_STATUS[${SEED}]}"
            echo "-----------------------------------------------------------"
            continue
        fi

        echo ""
        echo "-----------------------------------------------------------"
        echo "Post-processing scene $((i + 1))/${NUM_SCENES}  seed=${SEED}"
        echo "Render/SL log: ${LOG_FILE}"
        echo "-----------------------------------------------------------"

        run_postprocess_with_status "${SEED}" "${OUTPUT_DIR}" "${LOG_FILE}"
    done
elif [[ "${PARALLEL_MODE}" == "off" ]]; then
    for ((i = 0; i < NUM_SCENES; i++)); do
        SEED=$((SEED_START + i))
        OUTPUT_DIR="${OUTPUT_ROOT}/seed_${SEED}"
        LOG_FILE="${LOG_ROOT}/seed_${SEED}.log"

        mkdir -p "${OUTPUT_DIR}"
        if mark_existing_or_pending_coarse "${SEED}" "${OUTPUT_DIR}"; then
            run_postprocess_with_status "${SEED}" "${OUTPUT_DIR}" "${LOG_FILE}"
            continue
        fi

        COARSE_STATUS["${SEED}"]="running"
        POST_STATUS["${SEED}"]="pending"
        echo ""
        echo "-----------------------------------------------------------"
        echo "Benchmark scene $((i + 1))/${NUM_SCENES}  seed=${SEED}"
        echo "Output: ${OUTPUT_DIR}"
        echo "Log: ${LOG_FILE}"
        echo "-----------------------------------------------------------"

        set +e
        (
            echo ">>> Step 1/4: Generating benchmark indoor scene ..."
            run_coarse "${SEED}" "${OUTPUT_DIR}"
            run_render_and_sl "${SEED}" "${OUTPUT_DIR}"
        ) >"${LOG_FILE}" 2>&1
        RC=$?
        set -e

        if [[ "${RC}" -eq 0 ]]; then
            COARSE_STATUS["${SEED}"]="success"
            POST_STATUS["${SEED}"]="success"
        elif [[ -e "${OUTPUT_DIR}/coarse/scene.blend" ]]; then
            COARSE_STATUS["${SEED}"]="success"
            POST_STATUS["${SEED}"]="failed(${RC})"
            echo "WARNING: render/structured-light failed for seed ${SEED} with exit code ${RC}. See ${LOG_FILE}"
        else
            COARSE_STATUS["${SEED}"]="failed(${RC})"
            POST_STATUS["${SEED}"]="skipped"
            echo "WARNING: coarse generation failed for seed ${SEED} with exit code ${RC}. See ${LOG_FILE}"
        fi
    done
else
    echo "Unsupported PARALLEL_MODE=${PARALLEL_MODE}"
    echo "Supported values: off, coarse_only"
    exit 1
fi

write_summary
