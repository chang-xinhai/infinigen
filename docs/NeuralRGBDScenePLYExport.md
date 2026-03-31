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
- defaults to approximately uniform world-space surface sampling
- writes per-point normals as `nx ny nz`
- skips hidden objects by default
- supports optional inclusion of hidden objects

Default export uses `surface` sampling. The point count is driven by surface area
and `sample_spacing`, so the resulting point cloud density is much less sensitive
to the underlying mesh tessellation. This is intended for evaluation and
reconstruction workflows where reference point density should stay roughly
uniform across the scene.

## Single Scene Export

Use the generic Blender-side exporter directly:

```bash
python -m infinigen.launch_blender -m infinigen.tools.export_scene_ply -- \
    --input_blend data/neural_rgbd/blendswap_scenes/breakfast_room/scene.blend \
    --output_path outputs/benchmark/neural_rgbd/scene_ply/breakfast_room/breakfast_room.ply \
    --sample_mode surface \
    --sample_spacing 0.2 \
    --overwrite
```

Useful flags:

- `--ascii` writes ASCII PLY instead of binary little-endian PLY
- `--include_hidden` includes hidden objects
- `--sample_mode vertices` exports only evaluated mesh vertices
- `--sample_mode surface` exports approximately uniform surface samples
- `--sample_spacing <float>` controls surface sample density in Blender world units
- `--include_vertices` additionally includes original mesh vertices in surface mode
- `--overwrite` replaces an existing output file

## Batch Export

To export all benchmark scenes in one command with the default surface-sampled output:

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
- `POINT_SAMPLING_MODE=surface` is the default and selects approximately uniform surface sampling
- `POINT_SAMPLE_SPACING=0.2` is the default target spacing for surface mode
- `INCLUDE_VERTICES=1` additionally includes raw mesh vertices in the export
- `OVERWRITE=0` fails if the output already exists

## Validation

Focused regression coverage for this workflow lives in:

- `tests/tools/test_export_scene_ply.py`
- `tests/core/test_neural_rgbd_scene_ply_export_script.py`
