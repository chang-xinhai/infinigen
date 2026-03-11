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
#   bash scripts/launch/structured_light_indoors.sh [SEED] [ROOM_TYPE]
#
# Examples:
#   bash scripts/launch/structured_light_indoors.sh 0 DiningRoom
#   bash scripts/launch/structured_light_indoors.sh 42 Bedroom
#   bash scripts/launch/structured_light_indoors.sh 123
#
# ─────────────────────────────────────────────────────────────

set -e

SEED="${1:-0}"
ROOM_TYPE="${2:-DiningRoom}"
OUTPUT_ROOT="outputs/structured_light"
OUTPUT_DIR="${OUTPUT_ROOT}/seed_${SEED}"

echo "═══════════════════════════════════════════════════════════"
echo "  Structured Light Pipeline"
echo "  Seed: ${SEED}  Room: ${ROOM_TYPE}"
echo "  Output: ${OUTPUT_DIR}"
echo "═══════════════════════════════════════════════════════════"

# ── Step 1: Generate scene ─────────────────────────────────────
echo ""
echo ">>> Step 1/3: Generating indoor scene (coarse) ..."
python -m infinigen_examples.generate_indoors \
    --seed "${SEED}" \
    --task coarse \
    --output_folder "${OUTPUT_DIR}/coarse" \
    -g fast_solve.gin singleroom.gin \
    -p compose_indoors.terrain_enabled=False \
       restrict_solving.restrict_parent_rooms="[\"${ROOM_TYPE}\"]"

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
#     -g fast_solve.gin singleroom.gin

# ── Step 3: Render Structured Light ────────────────────────────
echo ""
echo ">>> Step 3/3: Rendering Structured Light data ..."
python -m infinigen_examples.generate_indoors \
    --seed "${SEED}" \
    --task structured_light \
    --input_folder "${OUTPUT_DIR}/coarse" \
    --output_folder "${OUTPUT_DIR}/sl_frames" \
    -g fast_solve.gin singleroom.gin structured_light.gin

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Done!"
echo "  Scene:  ${OUTPUT_DIR}/coarse/scene.blend"
echo "  SL output:  ${OUTPUT_DIR}/sl_frames/structured_light/"
echo ""
echo "  Output structure:"
echo "    {frame}_{pattern}_{L/R}_Image.{exr,png}  — IR images"
echo "    {frame}_{L/R}_Depth.exr                  — IR depth"
echo "    {frame}_{L/R}_Normal.exr                 — IR normals"
echo "    {frame}_RGB_Image.{exr,png}              — RGB (no proj)"
echo "    {frame}_RGB_Depth.exr                    — RGB depth"
echo "    parameters.npz / parameters.json         — calibration"
echo "    patterns/                                — pattern images"
echo "═══════════════════════════════════════════════════════════"
