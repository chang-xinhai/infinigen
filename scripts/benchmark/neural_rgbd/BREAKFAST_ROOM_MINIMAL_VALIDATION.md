# Breakfast Room Minimal Validation

This file is a minimal command checklist for validating the Neural RGB-D benchmark pipeline on `breakfast_room` from scratch.

Assumptions:

- current working directory is the repository root: `/data/xinhai/projects/infinigen`
- the `infinigen` conda environment is available
- Blender is installed and can be found either through `BLENDER_BIN` or `PATH`

Recommended temporary output root:

```bash
export NRGBD_OUT=outputs/benchmark/neural_rgbd/test
rm -rf "${NRGBD_OUT}"
```

## 0. Environment Check

If you use `conda activate`:

```bash
conda activate infinigen
```

If you prefer one-shot execution:

```bash
export CONDA_ENV=infinigen
```

Optional quick input check:

```bash
ls data/neural_rgbd/blendswap_scenes/breakfast_room
ls data/neural_rgbd/neural_rgbd_data/breakfast_room
```

## 1. Import Neural RGB-D Trajectory

Minimal 1-frame import:

```bash
bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task trajectory \
    --frame_end 1 \
    --output_root "${NRGBD_OUT}"
```

The benchmark now defaults to `--pose_source blender_poses`. Use `--pose_source poses.txt` only when you explicitly want the older OpenGL pose path.

Expected files:

```bash
find "${NRGBD_OUT}/trajectory" -maxdepth 1 -type f | sort
```

You should see:

- `trajectory/scene.blend`
- `trajectory/trajectory_metadata.json`

Optional metadata check:

```bash
python - <<'PY'
import json
import os
from pathlib import Path
meta = json.loads(Path(os.environ["NRGBD_OUT"]).joinpath("trajectory/trajectory_metadata.json").read_text())
print(meta["scene_name"], meta["pose_source"], meta["frame_start"], meta["frame_end"], meta["selected_frame_count"])
PY
```

## 2. Preview The Imported Trajectory

Optional Blender preview:

```bash
bash scripts/benchmark/neural_rgbd/preview_neural_rgbd_trajectory.sh \
    "${NRGBD_OUT}"
```

If Blender is not in `PATH`:

```bash
BLENDER_BIN=/path/to/blender \
bash scripts/benchmark/neural_rgbd/preview_neural_rgbd_trajectory.sh \
    "${NRGBD_OUT}"
```

## 3. Minimal RGB Reproduction

Render only the first frame and generate the comparison report:

```bash
bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task render \
    --frame_end 1 \
    --output_root "${NRGBD_OUT}"
```

Expected outputs:

```bash
find "${NRGBD_OUT}/frames" -maxdepth 3 -type f | sort
```

Important files:

- `frames/rgb/img0.png`
- `frames/camview/camview_0_0_0001_0.npz`
- `frames/comparison/summary.json`
- `frames/comparison/frames.jsonl`
- `frames/comparison/frames.tsv`

Quick summary check:

```bash
python - <<'PY'
import json
import os
from pathlib import Path
summary = json.loads(Path(os.environ["NRGBD_OUT"]).joinpath("frames/comparison/summary.json").read_text())
print(summary)
PY
```

## 4. Minimal Structured-Light Validation

Run a single-frame structured-light capture with minimal sample count:

```bash
bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task structured_light \
    --frame_end 1 \
    --output_root "${NRGBD_OUT}" \
    -p render_structured_light.sl_max_samples=1
```

Expected outputs:

```bash
find "${NRGBD_OUT}/sl_frames" -maxdepth 5 -type f | sort
```

Important files:

- `sl_frames/output/rgb/image/frame_0000.png`
- `sl_frames/output/rgb/depth/frame_0000.png`
- `sl_frames/output/rgb/depth/frame_0000.exr`
- `sl_frames/output/IR_left/image/d415/frame_0000.png`
- `sl_frames/output/IR_right/image/d415/frame_0000.png`
- `sl_frames/output/calibration/calibration.npz`
- `sl_frames/structured_light/patterns/white.png`

Note:

- On this machine, the structured-light stage may finish writing outputs and then exit abnormally during Blender shutdown.
- Treat the presence of the expected files under `sl_frames/` as the success condition for this minimal validation.

## 5. Full Minimal Checklist

If you want the exact shortest sequence from zero:

```bash
export NRGBD_OUT=/tmp/neural_rgbd_breakfast_room_minimal
rm -rf "${NRGBD_OUT}"
conda activate infinigen

bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task trajectory \
    --frame_end 1 \
    --output_root "${NRGBD_OUT}"

bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task render \
    --frame_end 1 \
    --output_root "${NRGBD_OUT}"

bash scripts/benchmark/neural_rgbd/run_neural_rgbd.sh \
    --scene_name breakfast_room \
    --task structured_light \
    --frame_end 1 \
    --output_root "${NRGBD_OUT}" \
    -p render_structured_light.sl_max_samples=1
```

Final check:

```bash
find "${NRGBD_OUT}" -maxdepth 5 -type f | sort
```
