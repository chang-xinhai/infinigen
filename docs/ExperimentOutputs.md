# Experiment Outputs

本文档说明本次实验采用的输出组织方式，以及后续继续跑实验时推荐保持的目录规范。

## 总体原则

不要直接复用 README 或各个 markdown 示例里的默认 `outputs/...` 路径。

本次统一使用：

```text
outputs/experiments/
```

在其下按实验类型、seed、任务阶段继续分层，避免不同实验互相覆盖。

## 当前实验目录约定

### 1. HelloWorld

```text
outputs/experiments/hello_world/seed0000/
  coarse/
  fine/
  frames_rgb/
  frames_gt/
  tmp/
```

说明：

- `coarse/`：场景布局与粗场景结果，包含 `scene.blend`、`pipeline_coarse.csv`、`polycounts.txt` 等。
- `fine/`：`populate` 和 `fine_terrain` 后的场景，包含 `scene.blend`、`pipeline_fine.csv`。
- `frames_rgb/`：常规 RGB 渲染结果及若干 Blender pass。
- `frames_gt/`：平面着色的 GT 结果，常见包括 `Depth`、`Normal`、`Vector`、`UniqueInstances` 等。
- `tmp/`：渲染中间产物。

### 2. HelloRoom

```text
outputs/experiments/hello_room/seed0000/
  coarse/
  frames_rgb/
  frames_gt/
  tmp/
```

说明：

- `coarse/`：室内求解、家具布局、资产实例化后的主场景目录。
- `coarse/pipeline_coarse.csv`：记录各 stage 是否执行、内存、对象数量；现在也会记录 `duration_sec`。
- `coarse/optim_records.csv`：室内 solver 的优化记录。
- `coarse/optim_records.png`：solver 优化曲线图。
- `coarse/solve_state.json`：求解后的状态信息。
- `frames_rgb/`：常规渲染结果。
- `frames_gt/`：GT 渲染结果。

### 3. 参数扫描 / 统计实验

```text
outputs/experiments/stat_sweeps/
  indoor_smallsteps_seed0001/
    coarse/
      statistics/
  indoor_multicam_seed0002/
    coarse/
      statistics/
```

推荐继续沿用这一层次：

```text
outputs/experiments/stat_sweeps/<experiment_name>/coarse/
outputs/experiments/stat_sweeps/<experiment_name>/fine/
outputs/experiments/stat_sweeps/<experiment_name>/frames_rgb/
outputs/experiments/stat_sweeps/<experiment_name>/frames_gt/
```

其中 `<experiment_name>` 建议编码以下信息：

- 场景类型，例如 `hello_room`、`indoor_rrt_video`
- 关键改动，例如 `smallsteps`、`multicam`、`highres`
- seed，例如 `seed0003`

例如：

```text
indoor_rrt_video_seed0010
indoor_highquality_seed0005
indoor_smallsteps_seed0001
```

## statistics 目录说明

使用新增脚本包装运行后，会在目标 scene 目录下生成：

```text
<scene_output_dir>/statistics/
  run_metadata.json
  resource_usage.csv
  resource_usage.png
  summary.json
  summary.txt
  stage_durations.png
  stage_proportions.png
```

含义如下：

- `run_metadata.json`：命令行、时间戳、退出码、环境信息。
- `resource_usage.csv`：随时间采样的 CPU、RSS、GPU 利用率、GPU 显存。
- `resource_usage.png`：CPU / 内存 / GPU 使用率时间曲线。
- `summary.json`：机器可读的统计汇总。
- `summary.txt`：便于直接查看的文字版统计。
- `stage_durations.png`：各 stage 总耗时柱状图。
- `stage_proportions.png`：各 stage 耗时占比图。

## 新增统计脚本用法

新增脚本：

```bash
python scripts/scene_statistics.py
```

### 1. 包装运行并自动采样

```bash
python scripts/scene_statistics.py wrap \
  --scene-root outputs/experiments/stat_sweeps/indoor_smallsteps_seed0001/coarse \
  --label indoor_smallsteps_seed0001 \
  -- \
  python -m infinigen_examples.generate_indoors --seed 1 --task coarse \
    --output_folder outputs/experiments/stat_sweeps/indoor_smallsteps_seed0001/coarse \
    -g fast_solve.gin singleroom.gin \
    -p compose_indoors.terrain_enabled=False \
       restrict_solving.restrict_parent_rooms='["DiningRoom"]' \
       compose_indoors.solve_steps_large=30 \
       compose_indoors.solve_steps_medium=10 \
       compose_indoors.solve_steps_small=3
```

适合新实验。推荐优先使用这个模式。

### 2. 对已存在结果补做汇总

```bash
python scripts/scene_statistics.py summarize \
  --scene-root outputs/experiments/hello_room/seed0000/coarse
```

注意：如果该场景不是通过 `wrap` 模式运行，那么不会有 `resource_usage.csv`，只能汇总已有的 pipeline csv。

### 3. 聚合多个场景

```bash
python scripts/scene_statistics.py aggregate \
  --output-dir outputs/experiments/stat_sweeps/aggregate \
  outputs/experiments/stat_sweeps/indoor_smallsteps_seed0001/coarse \
  outputs/experiments/stat_sweeps/indoor_multicam_seed0002/coarse
```

会输出：

- `aggregate_summary.csv`
- `aggregate_total_stage_time.png`

后续如果需要，还可以继续按这个聚合入口扩展更多图表。

## 常看文件清单

如果你想快速定位一个实验是否成功，优先看：

1. `scene.blend`
2. `pipeline_coarse.csv` 或 `pipeline_fine.csv`
3. `summary.txt`
4. `resource_usage.png`
5. `stage_durations.png`
6. `optim_records.png`

## 推荐命名习惯

建议每次实验都固定：

1. 一个独立 `experiment_name`
2. 一个固定 `seed`
3. 单独的 `coarse/fine/frames/statistics` 子目录

这样后续做 sweep、做聚合、做 structured light 数据整理时，不需要再回头猜每个目录原本对应什么命令。