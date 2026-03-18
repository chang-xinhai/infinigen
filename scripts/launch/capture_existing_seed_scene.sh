#!/bin/bash
# Capture data from an existing benchmark seed scene.
#
# Usage:
#   bash scripts/launch/capture_existing_seed_scene.sh <SCENE_DIR> <MODE>
#
# Examples:
#   CONDA_ENV=infinigen_311 bash scripts/launch/capture_existing_seed_scene.sh \
#       outputs/benchmark/structured_light_indoors/seed_0 rgb_only
#
#   CONDA_ENV=infinigen_311 bash scripts/launch/capture_existing_seed_scene.sh \
#       outputs/benchmark/structured_light_indoors/seed_0 full

set -euo pipefail

SCENE_DIR="${1:-}"
MODE="${2:-rgb_only}"

if [[ -z "${SCENE_DIR}" ]]; then
    echo "Usage: bash scripts/launch/capture_existing_seed_scene.sh <SCENE_DIR> <MODE>"
    echo "  MODE: rgb_only | full"
    exit 1
fi

if [[ ! -f "${SCENE_DIR}/coarse/scene.blend" ]]; then
    echo "Expected coarse scene at ${SCENE_DIR}/coarse/scene.blend"
    exit 1
fi

if [[ "${MODE}" != "rgb_only" && "${MODE}" != "full" ]]; then
    echo "Invalid MODE=${MODE}. Expected rgb_only or full."
    exit 1
fi

SCENE_SEED="${SCENE_SEED:-}"
if [[ -z "${SCENE_SEED}" ]]; then
    SCENE_BASENAME="$(basename "${SCENE_DIR}")"
    if [[ "${SCENE_BASENAME}" =~ ^seed_([0-9]+)$ ]]; then
        SCENE_SEED="${BASH_REMATCH[1]}"
    else
        echo "Failed to infer scene seed from ${SCENE_DIR}. Set SCENE_SEED explicitly."
        exit 1
    fi
fi

CONDA_ENV="${CONDA_ENV:-}"
PYTHON_BIN="${PYTHON_BIN:-python}"
if [[ -n "${CONDA_ENV}" ]]; then
    PY_CMD=(conda run -n "${CONDA_ENV}" python)
else
    PY_CMD=("${PYTHON_BIN}")
fi
POST_PYTHON_BIN="${POST_PYTHON_BIN:-python}"

export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl}"
mkdir -p "${MPLCONFIGDIR}"

WALK_CAMERA_HEIGHT_M="${WALK_CAMERA_HEIGHT_M:-1.55}"
WALK_FPS="${WALK_FPS:-3}"
WALK_TRAVERSAL_SPEED_MPS="${WALK_TRAVERSAL_SPEED_MPS:-0.30}"
WALK_ORBIT_SPEED_MPS="${WALK_ORBIT_SPEED_MPS:-0.18}"
WALK_STEP_M="${WALK_STEP_M:-0.10}"
WALK_CLEARANCE_M="${WALK_CLEARANCE_M:-0.20}"
WALK_PATH_MARGIN_M="${WALK_PATH_MARGIN_M:-0.18}"
WALK_PATH_RESOLUTION="${WALK_PATH_RESOLUTION:-160000}"
WALK_ROOM_SWEEP_ANGLE_DEG="${WALK_ROOM_SWEEP_ANGLE_DEG:-180.0}"
WALK_ROOM_SWEEP_YAW_SPEED_DEG_S="${WALK_ROOM_SWEEP_YAW_SPEED_DEG_S:-24.0}"
WALK_ENABLE_ROOM_ORBIT="${WALK_ENABLE_ROOM_ORBIT:-False}"
WALK_ROOM_GRID_STEP_M="${WALK_ROOM_GRID_STEP_M:-0.10}"
WALK_HEIGHT_PERTURBATION_AMPLITUDE_M="${WALK_HEIGHT_PERTURBATION_AMPLITUDE_M:-0.04}"
WALK_HEIGHT_PERTURBATION_FREQUENCY_HZ="${WALK_HEIGHT_PERTURBATION_FREQUENCY_HZ:-0.35}"
WALK_FORCE_OPEN_ACCESS_DOORS="${WALK_FORCE_OPEN_ACCESS_DOORS:-True}"
WALK_FORCE_OPEN_ACCESS_DOORS_MODE="${WALK_FORCE_OPEN_ACCESS_DOORS_MODE:-hide}"

RGB_WIDTH="${RGB_WIDTH:-320}"
RGB_HEIGHT="${RGB_HEIGHT:-240}"
RGB_SAMPLES="${RGB_SAMPLES:-16}"
RGB_FORCE_LIGHTING="${RGB_FORCE_LIGHTING:-True}"
RGB_WORLD_STRENGTH="${RGB_WORLD_STRENGTH:-0.25}"
RGB_SUN_ENERGY="${RGB_SUN_ENERGY:-1.0}"
RGB_CAMERA_LIGHT_ENERGY="${RGB_CAMERA_LIGHT_ENERGY:-120.0}"
RGB_FORCE_DENOISING="${RGB_FORCE_DENOISING:-True}"
RGB_DISABLE_CAUSTICS="${RGB_DISABLE_CAUSTICS:-True}"
RGB_SAMPLE_CLAMP_INDIRECT="${RGB_SAMPLE_CLAMP_INDIRECT:-0.75}"
RGB_SAMPLE_CLAMP_DIRECT="${RGB_SAMPLE_CLAMP_DIRECT:-2.5}"
if [[ "${MODE}" == "rgb_only" ]]; then
    RGB_DELETE_EXR_AFTER_RENDER="${RGB_DELETE_EXR_AFTER_RENDER:-1}"
else
    RGB_DELETE_EXR_AFTER_RENDER="${RGB_DELETE_EXR_AFTER_RENDER:-0}"
fi
GENERATE_PREVIEW_ARTIFACTS="${GENERATE_PREVIEW_ARTIFACTS:-1}"
PREVIEW_GIF_STRIDE="${PREVIEW_GIF_STRIDE:-4}"

RUN_RGB_RENDER_IN_FULL="${RUN_RGB_RENDER_IN_FULL:-1}"
RUN_STRUCTURED_LIGHT_IN_FULL="${RUN_STRUCTURED_LIGHT_IN_FULL:-1}"
SL_MAX_SAMPLES="${SL_MAX_SAMPLES:-128}"

DEPTH_HISTOGRAM_ENABLED="${DEPTH_HISTOGRAM_ENABLED:-1}"
DEPTH_HISTOGRAM_BINS="${DEPTH_HISTOGRAM_BINS:-80}"
DEPTH_HISTOGRAM_MIN_M="${DEPTH_HISTOGRAM_MIN_M:-0.0}"
DEPTH_HISTOGRAM_MAX_M="${DEPTH_HISTOGRAM_MAX_M:-10.0}"
DEPTH_HISTOGRAM_SAMPLE_LIMIT="${DEPTH_HISTOGRAM_SAMPLE_LIMIT:-200000}"

REUSE_EXISTING_TRAJECTORY="${REUSE_EXISTING_TRAJECTORY:-1}"
FRAME_RANGE="${FRAME_RANGE:-}"

RUN_TAG_DEFAULT="mode-${MODE}_fps-${WALK_FPS}_speed-${WALK_TRAVERSAL_SPEED_MPS}_step-${WALK_STEP_M}"
RUN_TAG="${RUN_TAG:-${RUN_TAG_DEFAULT}}"
SAFE_RUN_TAG="${RUN_TAG//./p}"

CAPTURES_DIR="${CAPTURES_DIR:-${SCENE_DIR}/captures}"
CAPTURE_ROOT="${CAPTURE_ROOT:-${CAPTURES_DIR}/${SAFE_RUN_TAG}}"

TRAJECTORY_DIR="${TRAJECTORY_DIR:-${CAPTURE_ROOT}/trajectory}"
RGB_ROOT="${RGB_ROOT:-${CAPTURE_ROOT}/rgb}"
RGB_TASK_OUTPUT_DIR="${RGB_TASK_OUTPUT_DIR:-${RGB_ROOT}/render_task}"
RGB_FRAMES_DIR="${RGB_FRAMES_DIR:-${RGB_ROOT}/frames}"
SL_ROOT="${SL_ROOT:-${CAPTURE_ROOT}/structured_light}"
SL_TASK_OUTPUT_DIR="${SL_TASK_OUTPUT_DIR:-${SL_ROOT}/task}"
SL_FRAMES_DIR="${SL_FRAMES_DIR:-${SL_ROOT}/frames}"
STATS_DIR="${STATS_DIR:-${CAPTURE_ROOT}/stats}"
CONFIG_DIR="${CONFIG_DIR:-${CAPTURE_ROOT}/config}"
LOG_DIR="${LOG_DIR:-${CAPTURE_ROOT}/logs}"

mkdir -p "${CAPTURE_ROOT}" "${RGB_ROOT}" "${SL_ROOT}" "${STATS_DIR}" "${CONFIG_DIR}" "${LOG_DIR}"

TRAJECTORY_LOG="${LOG_DIR}/trajectory.log"
RGB_LOG="${LOG_DIR}/rgb.log"
SL_LOG="${LOG_DIR}/structured_light.log"
DEPTH_HISTOGRAM_LOG="${LOG_DIR}/depth_histogram.log"
CAPTURE_SETTINGS_FILE="${CONFIG_DIR}/capture_settings.env"
DEPTH_HISTOGRAM_JSON="${STATS_DIR}/depth_histogram.json"
DEPTH_HISTOGRAM_PNG="${STATS_DIR}/depth_histogram.png"

TRAJECTORY_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin)
RENDER_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin)
SL_CONFIGS=(benchmark.gin real_geometry_with_bump.gin whole_home_walk.gin structured_light.gin)

COMMON_OVERRIDES=("compose_indoors.terrain_enabled=False")
TRAJECTORY_OVERRIDES=(
    "animate_whole_home_walk.camera_height_m=${WALK_CAMERA_HEIGHT_M}"
    "animate_whole_home_walk.planner_fps=${WALK_FPS}"
    "animate_whole_home_walk.traversal_speed_mps=${WALK_TRAVERSAL_SPEED_MPS}"
    "animate_whole_home_walk.orbit_speed_mps=${WALK_ORBIT_SPEED_MPS}"
    "animate_whole_home_walk.traversal_point_step_m=${WALK_STEP_M}"
    "animate_whole_home_walk.clearance_m=${WALK_CLEARANCE_M}"
    "animate_whole_home_walk.path_margin_m=${WALK_PATH_MARGIN_M}"
    "animate_whole_home_walk.path_resolution=${WALK_PATH_RESOLUTION}"
    "animate_whole_home_walk.room_sweep_angle_deg=${WALK_ROOM_SWEEP_ANGLE_DEG}"
    "animate_whole_home_walk.room_sweep_yaw_speed_deg_s=${WALK_ROOM_SWEEP_YAW_SPEED_DEG_S}"
    "animate_whole_home_walk.enable_room_orbit=${WALK_ENABLE_ROOM_ORBIT}"
    "animate_whole_home_walk.room_grid_step_m=${WALK_ROOM_GRID_STEP_M}"
    "animate_whole_home_walk.height_perturbation_amplitude_m=${WALK_HEIGHT_PERTURBATION_AMPLITUDE_M}"
    "animate_whole_home_walk.height_perturbation_frequency_hz=${WALK_HEIGHT_PERTURBATION_FREQUENCY_HZ}"
    "animate_whole_home_walk.force_open_access_doors=${WALK_FORCE_OPEN_ACCESS_DOORS}"
    "animate_whole_home_walk.force_open_access_doors_mode=\"${WALK_FORCE_OPEN_ACCESS_DOORS_MODE}\""
)
RGB_OVERRIDES=(
    "execute_tasks.use_scene_frame_range=True"
    "full/render_image.passes_to_save=[]"
    "full/render_image.override_num_samples=${RGB_SAMPLES}"
    "full/render_image.render_resolution_override=(${RGB_WIDTH}, ${RGB_HEIGHT})"
    "full/render_image.preview_force_lighting=${RGB_FORCE_LIGHTING}"
    "full/render_image.preview_world_strength=${RGB_WORLD_STRENGTH}"
    "full/render_image.preview_sun_energy=${RGB_SUN_ENERGY}"
    "full/render_image.preview_camera_light_energy=${RGB_CAMERA_LIGHT_ENERGY}"
    "full/render_image.preview_force_denoising=${RGB_FORCE_DENOISING}"
    "full/render_image.preview_disable_caustics=${RGB_DISABLE_CAUSTICS}"
    "full/render_image.preview_sample_clamp_indirect=${RGB_SAMPLE_CLAMP_INDIRECT}"
    "full/render_image.preview_sample_clamp_direct=${RGB_SAMPLE_CLAMP_DIRECT}"
)
SL_OVERRIDES=(
    "execute_tasks.use_scene_frame_range=True"
    "render_structured_light.sl_max_samples=${SL_MAX_SAMPLES}"
)

if [[ -n "${FRAME_RANGE}" ]]; then
    IFS=',' read -r FRAME_START FRAME_END <<<"${FRAME_RANGE}"
    RGB_OVERRIDES=(
        "execute_tasks.use_scene_frame_range=False"
        "execute_tasks.frame_range=[${FRAME_START},${FRAME_END}]"
        "${RGB_OVERRIDES[@]:1}"
    )
    SL_OVERRIDES=(
        "execute_tasks.use_scene_frame_range=False"
        "execute_tasks.frame_range=[${FRAME_START},${FRAME_END}]"
        "${SL_OVERRIDES[@]:1}"
    )
fi

write_capture_settings() {
    {
        echo "SCENE_DIR=${SCENE_DIR}"
        echo "SCENE_SEED=${SCENE_SEED}"
        echo "MODE=${MODE}"
        echo "RUN_TAG=${RUN_TAG}"
        echo "SAFE_RUN_TAG=${SAFE_RUN_TAG}"
        echo "CAPTURE_ROOT=${CAPTURE_ROOT}"
        echo "TRAJECTORY_DIR=${TRAJECTORY_DIR}"
        echo "RGB_ROOT=${RGB_ROOT}"
        echo "RGB_TASK_OUTPUT_DIR=${RGB_TASK_OUTPUT_DIR}"
        echo "RGB_FRAMES_DIR=${RGB_FRAMES_DIR}"
        echo "SL_ROOT=${SL_ROOT}"
        echo "SL_TASK_OUTPUT_DIR=${SL_TASK_OUTPUT_DIR}"
        echo "SL_FRAMES_DIR=${SL_FRAMES_DIR}"
        echo "STATS_DIR=${STATS_DIR}"
        echo "LOG_DIR=${LOG_DIR}"
        echo "WALK_CAMERA_HEIGHT_M=${WALK_CAMERA_HEIGHT_M}"
        echo "WALK_FPS=${WALK_FPS}"
        echo "WALK_TRAVERSAL_SPEED_MPS=${WALK_TRAVERSAL_SPEED_MPS}"
        echo "WALK_ORBIT_SPEED_MPS=${WALK_ORBIT_SPEED_MPS}"
        echo "WALK_STEP_M=${WALK_STEP_M}"
        echo "WALK_CLEARANCE_M=${WALK_CLEARANCE_M}"
        echo "WALK_PATH_MARGIN_M=${WALK_PATH_MARGIN_M}"
        echo "WALK_ROOM_SWEEP_ANGLE_DEG=${WALK_ROOM_SWEEP_ANGLE_DEG}"
        echo "WALK_ROOM_SWEEP_YAW_SPEED_DEG_S=${WALK_ROOM_SWEEP_YAW_SPEED_DEG_S}"
        echo "WALK_ENABLE_ROOM_ORBIT=${WALK_ENABLE_ROOM_ORBIT}"
        echo "WALK_HEIGHT_PERTURBATION_AMPLITUDE_M=${WALK_HEIGHT_PERTURBATION_AMPLITUDE_M}"
        echo "WALK_HEIGHT_PERTURBATION_FREQUENCY_HZ=${WALK_HEIGHT_PERTURBATION_FREQUENCY_HZ}"
        echo "RGB_WIDTH=${RGB_WIDTH}"
        echo "RGB_HEIGHT=${RGB_HEIGHT}"
        echo "RGB_SAMPLES=${RGB_SAMPLES}"
        echo "SL_MAX_SAMPLES=${SL_MAX_SAMPLES}"
        echo "DEPTH_HISTOGRAM_ENABLED=${DEPTH_HISTOGRAM_ENABLED}"
        echo "DEPTH_HISTOGRAM_BINS=${DEPTH_HISTOGRAM_BINS}"
        echo "DEPTH_HISTOGRAM_MIN_M=${DEPTH_HISTOGRAM_MIN_M}"
        echo "DEPTH_HISTOGRAM_MAX_M=${DEPTH_HISTOGRAM_MAX_M}"
        if [[ -n "${FRAME_RANGE}" ]]; then
            echo "FRAME_RANGE=${FRAME_RANGE}"
        fi
    } >"${CAPTURE_SETTINGS_FILE}"
}

print_header() {
    echo "═══════════════════════════════════════════════════════════"
    echo "  Existing Seed Scene Capture"
    echo "  Scene dir: ${SCENE_DIR}"
    echo "  Mode: ${MODE}"
    echo "  Scene seed: ${SCENE_SEED}"
    echo "  Capture root: ${CAPTURE_ROOT}"
    echo "  Run tag: ${SAFE_RUN_TAG}"
    echo "  Trajectory dir: ${TRAJECTORY_DIR}"
    echo "  RGB frames dir: ${RGB_FRAMES_DIR}"
    echo "  Structured-light root: ${SL_ROOT}"
    echo "  Stats dir: ${STATS_DIR}"
    echo "  Walk fps: ${WALK_FPS}"
    echo "  Walk speed: ${WALK_TRAVERSAL_SPEED_MPS}"
    echo "  Walk step: ${WALK_STEP_M}"
    echo "  Height perturbation amplitude: ${WALK_HEIGHT_PERTURBATION_AMPLITUDE_M}"
    echo "  Height perturbation frequency: ${WALK_HEIGHT_PERTURBATION_FREQUENCY_HZ}"
    echo "  RGB resolution: ${RGB_WIDTH}x${RGB_HEIGHT}"
    echo "  RGB samples: ${RGB_SAMPLES}"
    echo "  SL max samples: ${SL_MAX_SAMPLES}"
    if [[ -n "${FRAME_RANGE}" ]]; then
        echo "  Frame range override: ${FRAME_RANGE}"
    fi
    echo "═══════════════════════════════════════════════════════════"
}

run_trajectory() {
    if [[ "${REUSE_EXISTING_TRAJECTORY}" == "1" && -f "${TRAJECTORY_DIR}/scene.blend" ]]; then
        echo "Reusing trajectory scene at ${TRAJECTORY_DIR}/scene.blend"
        return
    fi

    echo "### Trajectory"
    "${PY_CMD[@]}" -m infinigen_examples.generate_indoors \
        --seed "${SCENE_SEED}" \
        --task trajectory \
        --input_folder "${SCENE_DIR}/coarse" \
        --output_folder "${TRAJECTORY_DIR}" \
        -g "${TRAJECTORY_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}" "${TRAJECTORY_OVERRIDES[@]}" \
        >"${TRAJECTORY_LOG}" 2>&1
}

run_rgb_render() {
    echo "### RGB Render"
    "${PY_CMD[@]}" -m infinigen_examples.generate_indoors \
        --seed "${SCENE_SEED}" \
        --task render \
        --input_folder "${TRAJECTORY_DIR}" \
        --output_folder "${RGB_TASK_OUTPUT_DIR}" \
        -g "${RENDER_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}" "${RGB_OVERRIDES[@]}" \
        >"${RGB_LOG}" 2>&1

    if [[ "${RGB_DELETE_EXR_AFTER_RENDER}" == "1" ]]; then
        find "${RGB_ROOT}" -type f -name 'Image_*.exr' -delete
    fi

    if [[ "${GENERATE_PREVIEW_ARTIFACTS}" == "1" ]]; then
        "${POST_PYTHON_BIN}" - <<PY
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(${RGB_ROOT@Q})
img_dir = root / "frames" / "Image" / "camera_0"
images = sorted(img_dir.glob("Image_0_0_*.png"))
if not images:
    raise SystemExit(f"No RGB png frames found under {img_dir}")

first_frame = Image.open(images[0]).convert("RGB")
first_frame.save(root / "rgb_first_frame.png")

contact_indices = [round(i * (len(images) - 1) / 15) for i in range(16)]
contact_paths = [images[i] for i in contact_indices]
thumbs = []
for path in contact_paths:
    im = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(im)
    label = path.stem.split("_")[3]
    draw.rectangle((0, 0, 84, 22), fill=(0, 0, 0))
    draw.text((6, 4), label, fill=(255, 255, 255))
    thumbs.append(im)

cols, rows = 4, 4
w, h = thumbs[0].size
sheet = Image.new("RGB", (cols * w, rows * h), color=(255, 255, 255))
for idx, im in enumerate(thumbs):
    x = (idx % cols) * w
    y = (idx // cols) * h
    sheet.paste(im, (x, y))
sheet.save(root / "rgb_contact_sheet.png")

stride = max(1, int(${PREVIEW_GIF_STRIDE}))
gif_frames = [
    Image.open(path).convert("P", palette=Image.ADAPTIVE)
    for path in images[::stride]
]
gif_frames[0].save(
    root / "rgb_preview_stride${PREVIEW_GIF_STRIDE}.gif",
    save_all=True,
    append_images=gif_frames[1:],
    duration=180,
    loop=0,
    optimize=False,
)
PY
    fi
}

run_structured_light() {
    echo "### Structured Light"
    "${PY_CMD[@]}" -m infinigen_examples.generate_indoors \
        --seed "${SCENE_SEED}" \
        --task structured_light \
        --input_folder "${TRAJECTORY_DIR}" \
        --output_folder "${SL_TASK_OUTPUT_DIR}" \
        -g "${SL_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}" "${SL_OVERRIDES[@]}" \
        >"${SL_LOG}" 2>&1

    if [[ -e "${SL_FRAMES_DIR}" && ! -L "${SL_FRAMES_DIR}" ]]; then
        rm -rf "${SL_FRAMES_DIR}"
    fi
    if [[ -d "${SL_TASK_OUTPUT_DIR}/structured_light" ]]; then
        ln -sfn "task/structured_light" "${SL_FRAMES_DIR}"
    fi
}

run_depth_histogram() {
    if [[ "${DEPTH_HISTOGRAM_ENABLED}" != "1" ]]; then
        echo "Skipping depth histogram because DEPTH_HISTOGRAM_ENABLED=${DEPTH_HISTOGRAM_ENABLED}"
        return
    fi

    echo "### Depth Histogram"
    "${POST_PYTHON_BIN}" scripts/scene_depth_histogram.py \
        --capture-root "${CAPTURE_ROOT}" \
        --output-json "${DEPTH_HISTOGRAM_JSON}" \
        --output-png "${DEPTH_HISTOGRAM_PNG}" \
        --bins "${DEPTH_HISTOGRAM_BINS}" \
        --min-depth-m "${DEPTH_HISTOGRAM_MIN_M}" \
        --max-depth-m "${DEPTH_HISTOGRAM_MAX_M}" \
        --quantile-sample-limit "${DEPTH_HISTOGRAM_SAMPLE_LIMIT}" \
        >"${DEPTH_HISTOGRAM_LOG}" 2>&1
}

print_summary() {
    echo "### Summary"
    echo "Capture root: ${CAPTURE_ROOT}"
    echo "Settings file: ${CAPTURE_SETTINGS_FILE}"
    echo "Trajectory scene: ${TRAJECTORY_DIR}/scene.blend"
    echo "Trajectory metadata: ${TRAJECTORY_DIR}/trajectory_metadata.json"
    if [[ -d "${RGB_FRAMES_DIR}/Image/camera_0" ]]; then
        echo "RGB png frames: $(find "${RGB_FRAMES_DIR}/Image/camera_0" -maxdepth 1 -name '*.png' | wc -l)"
        echo "RGB frames dir: ${RGB_FRAMES_DIR}/Image/camera_0"
        echo "Camera params dir: ${RGB_FRAMES_DIR}/camview/camera_0"
        if [[ -f "${RGB_ROOT}/rgb_contact_sheet.png" ]]; then
            echo "RGB contact sheet: ${RGB_ROOT}/rgb_contact_sheet.png"
        fi
    fi
    if [[ -d "${SL_FRAMES_DIR}" ]]; then
        echo "Structured-light dir: ${SL_FRAMES_DIR}"
    fi
    if [[ -f "${DEPTH_HISTOGRAM_JSON}" ]]; then
        echo "Depth histogram json: ${DEPTH_HISTOGRAM_JSON}"
    fi
    if [[ -f "${DEPTH_HISTOGRAM_PNG}" ]]; then
        echo "Depth histogram png: ${DEPTH_HISTOGRAM_PNG}"
    fi
    echo "Logs:"
    echo "  trajectory: ${TRAJECTORY_LOG}"
    if [[ -f "${RGB_LOG}" ]]; then
        echo "  rgb: ${RGB_LOG}"
    fi
    if [[ -f "${SL_LOG}" ]]; then
        echo "  structured_light: ${SL_LOG}"
    fi
    if [[ -f "${DEPTH_HISTOGRAM_LOG}" ]]; then
        echo "  depth_histogram: ${DEPTH_HISTOGRAM_LOG}"
    fi
}

write_capture_settings
print_header
run_trajectory

case "${MODE}" in
    rgb_only)
        run_rgb_render
        ;;
    full)
        if [[ "${RUN_RGB_RENDER_IN_FULL}" == "1" ]]; then
            run_rgb_render
        fi
        if [[ "${RUN_STRUCTURED_LIGHT_IN_FULL}" == "1" ]]; then
            run_structured_light
        fi
        ;;
esac

run_depth_histogram
print_summary
