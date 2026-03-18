#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Structured Light rendering for Infinigen Indoors
# ─────────────────────────────────────────────────────────────
#
# This script demonstrates the full pipeline:
#   1. Generate an indoor scene (coarse)
#   2. Render standard RGB + GT (optional, for comparison)
#   3. Render Structured Light data (L_Image, R_Image, L_Depth, R_Depth, RGB, etc.)
#
# Usage:
#   bash scripts/launch/structured_light_indoors.sh [SEED] [ROOM_TYPE|ALL]
#
# Examples:
#   bash scripts/launch/structured_light_indoors.sh 0
#   bash scripts/launch/structured_light_indoors.sh 0 ALL
#   bash scripts/launch/structured_light_indoors.sh 42 Bedroom
#
# ─────────────────────────────────────────────────────────────

set -e

SEED="${1:-0}"
ROOM_TYPE="${2:-ALL}"
OUTPUT_ROOT="outputs/test/generate_whole_home"
OUTPUT_DIR="${OUTPUT_ROOT}/seed_${SEED}"

COARSE_CONFIGS=(fast_solve.gin)
RENDER_CONFIGS=(fast_solve.gin)
SL_CONFIGS=(fast_solve.gin structured_light.gin)
COARSE_OVERRIDES=(compose_indoors.terrain_enabled=False)

if [[ -n "${ROOM_TYPE}" && "${ROOM_TYPE}" != "ALL" ]]; then
    COARSE_CONFIGS+=(singleroom.gin)
    RENDER_CONFIGS+=(singleroom.gin)
    SL_CONFIGS=(fast_solve.gin singleroom.gin structured_light.gin)
    COARSE_OVERRIDES+=("restrict_solving.restrict_parent_rooms=[\"${ROOM_TYPE}\"]")
    SCENE_SCOPE="single-room (${ROOM_TYPE})"
else
    SCENE_SCOPE="whole-home"
fi

echo "═══════════════════════════════════════════════════════════"
echo "  Structured Light Pipeline"
echo "  Seed: ${SEED}  Scope: ${SCENE_SCOPE}"
echo "  Output: ${OUTPUT_DIR}"
echo "═══════════════════════════════════════════════════════════"

# ── Step 1: Generate scene ─────────────────────────────────────
echo ""
echo ">>> Step 1/3: Generating indoor scene (coarse) ..."
python -m infinigen_examples.generate_indoors \
    --seed "${SEED}" \
    --task coarse \
    --output_folder "${OUTPUT_DIR}/coarse" \
    -g "${COARSE_CONFIGS[@]}" \
    -p "${COARSE_OVERRIDES[@]}"

echo ">>> Scene generated at ${OUTPUT_DIR}/coarse/scene.blend"

# ── Step 2 (optional): Render standard RGB ─────────────────────
# Uncomment the block below if you also want standard RGB renders.
#
# echo ""
# echo ">>> Step 2/3: Rendering standard RGB ..."
# python -m infinigen_examples.generate_indoors \
#     --seed "${SEED}" \
#     --task render \
#     --input_folder "${OUTPUT_DIR}/coarse" \
#     --output_folder "${OUTPUT_DIR}/frames" \
#     -g "${RENDER_CONFIGS[@]}"

# ── Step 3: Render Structured Light ────────────────────────────
echo ""
echo ">>> Step 3/3: Rendering Structured Light data ..."
python -m infinigen_examples.generate_indoors \
    --seed "${SEED}" \
    --task structured_light \
    --input_folder "${OUTPUT_DIR}/coarse" \
    --output_folder "${OUTPUT_DIR}/sl_frames" \
    -g "${SL_CONFIGS[@]}"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Done!"
echo "  Scene:  ${OUTPUT_DIR}/coarse/scene.blend"
echo "  Capture root:  ${OUTPUT_DIR}/sl_frames"
echo ""
echo "  Output structure:"
echo "    output/rgb/                              — RGB image/depth/normal"
echo "    output/IR_left/ and output/IR_right/     — per-pattern IR images"
echo "    output/calibration/calibration.npz       — aggregated calibration"
echo "    structured_light/patterns/               — copied pattern png files"
echo "═══════════════════════════════════════════════════════════"
