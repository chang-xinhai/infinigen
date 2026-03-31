# Depth EXR To PNG

This utility converts depth `.exr` files into colorized `.png` previews for quick inspection.

Script:

- `scripts/benchmark/depth_exr_to_png.py`

## Single File

```bash
python scripts/benchmark/depth_exr_to_png.py \
    outputs/structured_light/scene_a/output/rgb/depth/frame_0001.exr
```

This writes:

```text
outputs/structured_light/scene_a/output/rgb/depth/frame_0001.png
```

## Directory Batch Conversion

```bash
python scripts/benchmark/depth_exr_to_png.py \
    outputs/structured_light/scene_a/output/rgb/depth \
    --recursive
```

By default, PNG files are written next to the source EXRs.

## Write To Another Root

```bash
python scripts/benchmark/depth_exr_to_png.py \
    outputs/structured_light \
    --recursive \
    --output-root outputs/depth_png_preview
```

This preserves the relative directory layout under the output root.

## Useful Flags

- `--recursive` recursively scans directories
- `--pattern "*.exr"` filters directory input with a glob
- `--output-root <dir>` writes PNGs under a separate root
- `--overwrite` replaces existing PNG outputs

## Notes

- The script uses the repository's existing depth EXR loader and depth colormap.
- Invalid depth values are sanitized before colorization.
