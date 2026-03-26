# Neural RGB-D Scene PLY Export

This document describes the scene-level PLY point-cloud export workflow added for Neural RGB-D benchmark scenes.

The implementation has two layers:

1. a reusable Blender-side exporter under `infinigen/tools`
2. a one-click batch wrapper under `scripts/benchmark/neural_rgbd`

## Goal

Given a Neural RGB-D `.blend` scene, export a single `.ply` file containing the evaluated scene geometry as a world-space point cloud.

Current behavior:

- opens the source `.blend`
- evaluates mesh modifiers before export
- exports vertices as points rather than writing mesh faces
- writes per-point normals as `nx ny nz`
- skips hidden objects by default
- supports optional inclusion of hidden objects

## Single Scene Export

Use the generic Blender-side exporter directly:

```bash
python -m infinigen.launch_blender -m infinigen.tools.export_scene_ply -- \
    --input_blend data/neural_rgbd/blendswap_scenes/breakfast_room/scene.blend \
    --output_path outputs/benchmark/neural_rgbd/scene_ply/breakfast_room/breakfast_room.ply \
    --overwrite
```

Useful flags:

- `--ascii` writes ASCII PLY instead of binary little-endian PLY
- `--include_hidden` includes hidden objects
- `--overwrite` replaces an existing output file

## Batch Export

To export all benchmark scenes in one command:

```bash
SCENES=ALL \
CONDA_ENV=infinigen \
bash scripts/benchmark/neural_rgbd/export_all_neural_rgbd_scene_ply.sh
```

Default output layout:

```text
outputs/benchmark/neural_rgbd/scene_ply/<scene_name>/<scene_name>.ply
```

Example for a subset:

```bash
SCENES="breakfast_room whiteroom" \
CONDA_ENV=infinigen \
bash scripts/benchmark/neural_rgbd/export_all_neural_rgbd_scene_ply.sh
```

## Batch Wrapper Environment Variables

- `DATASET_ROOT` overrides the Neural RGB-D dataset root
- `OUTPUT_ROOT` overrides the export destination root
- `SCENES` selects `ALL` or a space-separated subset
- `ASCII_PLY=1` writes ASCII PLY
- `INCLUDE_HIDDEN=1` includes hidden objects
- `OVERWRITE=0` fails if the output already exists

## Validation

Focused regression coverage for this workflow lives in:

- `tests/tools/test_export_scene_ply.py`
- `tests/core/test_neural_rgbd_scene_ply_export_script.py`
