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

export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl}"
mkdir -p "${MPLCONFIGDIR}"

WALK_CAMERA_HEIGHT_M="${WALK_CAMERA_HEIGHT_M:-1.55}"
WALK_FPS="${WALK_FPS:-3}"
WALK_STEP_M="${WALK_STEP_M:-0.15}"
WALK_CLEARANCE_M="${WALK_CLEARANCE_M:-0.20}"
WALK_PATH_MARGIN_M="${WALK_PATH_MARGIN_M:-0.18}"
WALK_PATH_RESOLUTION="${WALK_PATH_RESOLUTION:-160000}"
WALK_ROOM_SWEEP_ANGLE_DEG="${WALK_ROOM_SWEEP_ANGLE_DEG:-180.0}"
WALK_ROOM_SWEEP_YAW_SPEED_DEG_S="${WALK_ROOM_SWEEP_YAW_SPEED_DEG_S:-40.0}"
WALK_ENABLE_ROOM_ORBIT="${WALK_ENABLE_ROOM_ORBIT:-False}"
WALK_ROOM_GRID_STEP_M="${WALK_ROOM_GRID_STEP_M:-0.10}"
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

REUSE_EXISTING_TRAJECTORY="${REUSE_EXISTING_TRAJECTORY:-1}"
FRAME_RANGE="${FRAME_RANGE:-}"

RUN_TAG_DEFAULT="f${WALK_FPS}_h${WALK_CAMERA_HEIGHT_M}_step${WALK_STEP_M}_${MODE}"
RUN_TAG="${RUN_TAG:-${RUN_TAG_DEFAULT}}"
SAFE_RUN_TAG="${RUN_TAG//./p}"

TRAJECTORY_DIR="${TRAJECTORY_DIR:-${SCENE_DIR}/trajectory_${SAFE_RUN_TAG}}"
RGB_ROOT="${RGB_ROOT:-${SCENE_DIR}_${SAFE_RUN_TAG}_rgb}"
RGB_OUTPUT_FOLDER="${RGB_OUTPUT_FOLDER:-${RGB_ROOT}/render}"
SL_OUTPUT_FOLDER="${SL_OUTPUT_FOLDER:-${SCENE_DIR}/sl_frames_${SAFE_RUN_TAG}}"
LOG_DIR="${LOG_DIR:-${SCENE_DIR}/logs}"
mkdir -p "${LOG_DIR}"

TRAJECTORY_LOG="${LOG_DIR}/${SAFE_RUN_TAG}_trajectory.log"
RGB_LOG="${LOG_DIR}/${SAFE_RUN_TAG}_rgb.log"
SL_LOG="${LOG_DIR}/${SAFE_RUN_TAG}_structured_light.log"

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
    "animate_whole_home_walk.room_sweep_angle_deg=${WALK_ROOM_SWEEP_ANGLE_DEG}"
    "animate_whole_home_walk.room_sweep_yaw_speed_deg_s=${WALK_ROOM_SWEEP_YAW_SPEED_DEG_S}"
    "animate_whole_home_walk.enable_room_orbit=${WALK_ENABLE_ROOM_ORBIT}"
    "animate_whole_home_walk.room_grid_step_m=${WALK_ROOM_GRID_STEP_M}"
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

print_header() {
    echo "═══════════════════════════════════════════════════════════"
    echo "  Existing Seed Scene Capture"
    echo "  Scene dir: ${SCENE_DIR}"
    echo "  Mode: ${MODE}"
    echo "  Scene seed: ${SCENE_SEED}"
    echo "  Run tag: ${SAFE_RUN_TAG}"
    echo "  Trajectory dir: ${TRAJECTORY_DIR}"
    echo "  RGB root: ${RGB_ROOT}"
    echo "  Structured-light output: ${SL_OUTPUT_FOLDER}"
    echo "  Walk fps: ${WALK_FPS}"
    echo "  Walk height: ${WALK_CAMERA_HEIGHT_M}"
    echo "  Walk step: ${WALK_STEP_M}"
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
        --output_folder "${RGB_OUTPUT_FOLDER}" \
        -g "${RENDER_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}" "${RGB_OVERRIDES[@]}" \
        >"${RGB_LOG}" 2>&1

    if [[ "${RGB_DELETE_EXR_AFTER_RENDER}" == "1" ]]; then
        find "${RGB_ROOT}" -type f -name 'Image_*.exr' -delete
    fi

    if [[ "${GENERATE_PREVIEW_ARTIFACTS}" == "1" ]]; then
        "${PY_CMD[@]}" - <<PY
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(${RGB_ROOT@Q})
img_dir = root / "frames" / "Image" / "camera_0"
images = sorted(img_dir.glob("Image_0_0_*.png"))
if not images:
    raise SystemExit(f"No RGB png frames found under {img_dir}")

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
        --output_folder "${SL_OUTPUT_FOLDER}" \
        -g "${SL_CONFIGS[@]}" \
        -p "${COMMON_OVERRIDES[@]}" "${SL_OVERRIDES[@]}" \
        >"${SL_LOG}" 2>&1
}

print_summary() {
    echo "### Summary"
    echo "Trajectory scene: ${TRAJECTORY_DIR}/scene.blend"
    echo "Trajectory metadata: ${TRAJECTORY_DIR}/trajectory_metadata.json"
    if [[ -d "${RGB_ROOT}/frames/Image/camera_0" ]]; then
        echo "RGB png frames: $(find "${RGB_ROOT}/frames/Image/camera_0" -maxdepth 1 -name '*.png' | wc -l)"
        echo "RGB frames dir: ${RGB_ROOT}/frames/Image/camera_0"
        echo "Camera params dir: ${RGB_ROOT}/frames/camview/camera_0"
        if [[ -f "${RGB_ROOT}/rgb_contact_sheet.png" ]]; then
            echo "RGB contact sheet: ${RGB_ROOT}/rgb_contact_sheet.png"
        fi
    fi
    if [[ -d "${SL_OUTPUT_FOLDER}/structured_light" ]]; then
        echo "Structured-light dir: ${SL_OUTPUT_FOLDER}/structured_light"
    fi
    echo "Logs:"
    echo "  trajectory: ${TRAJECTORY_LOG}"
    if [[ -f "${RGB_LOG}" ]]; then
        echo "  rgb: ${RGB_LOG}"
    fi
    if [[ -f "${SL_LOG}" ]]; then
        echo "  structured_light: ${SL_LOG}"
    fi
}

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

print_summary
