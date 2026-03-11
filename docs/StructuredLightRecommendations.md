# Structured Light Recommendations

本文档结合 `.idea/deepsl-data/README.md` 中你已有的 NSL_Data / ProcTHOR 背景，总结如果后续要基于 Infinigen 构建大规模高质量 Structured Light 数据集，应该优先关注什么。

## 先讲结论

如果目标是训练 feed-forward structured light reconstruction model，Infinigen 相比 ProcTHOR 的最大价值不是“更容易渲染”，而是：

1. 更强的几何与材质多样性。
2. 更可控的 camera / lighting / clutter / scene randomness。
3. 更容易系统性地做 domain randomization。
4. 更适合后续加入“投影仪 + 双目/单目相机 + 精确标定”的仿真管线。

但要真正服务 Structured Light，单纯复用 RGB/GT 渲染还不够，后续最值得投入的是“采集系统建模”和“投影模式仿真”两层。

## 和 ProcTHOR 路线的差异

ProcTHOR 的优势在于：

- 室内布局稳定。
- 资产语义明确。
- 批量生成速度通常较好。

Infinigen 的优势在于：

- 材质更程序化，变化范围更大。
- 几何细节更丰富，不容易过拟合到有限资产库。
- 摄像机、动画、场景复杂度的可调空间更大。

如果你原先 NSL_Data 的瓶颈在于：

- 资产重复度高
- 材质分布窄
- 表面法线/微结构不够复杂
- 相机轨迹不够丰富

那么 Infinigen 很适合作为 ProcTHOR 的补充域，而不是完全替代域。

## 建议的总体路线

我建议你把后续工作拆成四层。

### 第一层：先把 Infinigen 当成“高质量场景与轨迹生成器”

这一层不要急着改核心渲染。

先稳定生成：

- 室内 singleroom / multistory 场景
- 随机游走视频
- 多机位视角
- 几种复杂度等级的场景

你现在最先该关注：

1. `infinigen_examples/generate_indoors.py`
2. `docs/HelloRoom.md`
3. `docs/ConfiguringCameras.md`
4. `docs/ConfiguringInfinigen.md`
5. `infinigen_examples/configs_indoor/*.gin`

### 第二层：引入 Structured Light 采集系统参数化

当场景能稳定批量生成后，再把真实结构光系统抽象成以下参数：

1. 投影仪内参
2. 相机内参
3. 投影仪到相机的外参
4. baseline
5. 曝光、gamma、噪声、动态范围
6. projector defocus / blur
7. 相机 motion blur / rolling shutter / shot noise
8. 投影图案类型

这部分你可以直接借鉴 `.idea/deepsl-data/README.md` 中已有的 `parameters.npz` 组织方式，不建议重新发明一套格式。

## 对 Structured Light 真正关键的因素

对于结构光重建，以下因素通常比“场景有多好看”更重要。

### 1. 投影图案与材质相互作用

尤其要覆盖：

- 高反光材质
- 低反照率材质
- 饱和高亮区域
- 玻璃 / 半透明 / 镜面
- 高频纹理表面
- 凹凸法线细节

Infinigen 在材质程序化这件事上很强，所以你应该重点保留：

- 粗糙度随机化
- 法线细节
- 局部污渍、老化、划痕
- 次表面或近似半透明材质

### 2. 相机轨迹与遮挡

如果模型以后要适应机器人或手持设备采集，训练数据里必须大量出现：

- 近距离视角变化
- 快速角度变化
- 遮挡穿插
- 出现细长结构与家具边缘
- 大平面和高频 clutter 混合

因此，随机游走视频非常有价值。

### 3. 标定一致性

Structured Light 不是普通 RGB 重建，几何监督高度依赖投影仪-相机系统标定。

建议你尽早固定并持久化：

- 每个 scene 的 rig 参数
- 每一帧的外参
- 投影图案编号
- 曝光与渲染设置

这部分建议单独输出到 `parameters.npz` 或 `parameters.json`，不要只靠日志保存。

## Infinigen 上最值得改的地方

如果后续真的要做 Structured Light 数据生产，优先级最高的改造建议如下。

### 1. 增加 projector rig

当前 Infinigen 默认是 camera rig。

建议新增一个与 camera rig 并列的 projector rig，并保存：

- projector intrinsic
- projector extrinsic
- projector pattern id
- projector image plane resolution

从工程角度讲，这比直接把 projector 写死进渲染脚本更稳，因为后面需要做 sweep。

### 2. 保留并导出几何真值

结构光训练时，建议同时保留：

- Depth
- Normal
- Instance / Object id
- Camera extrinsic / intrinsic
- Projector extrinsic / intrinsic

若后续模型会做 multi-view 或时序融合，还应保留：

- frame index
- camera trajectory id
- scene seed

### 3. 单独做 pattern simulation 层

不要把所有逻辑塞进场景生成脚本。

更稳妥的做法是把流程拆成：

1. Infinigen 生成场景与 camera trajectory
2. Structured Light 渲染脚本读取 scene
3. 再注入 projector / pattern / exposure / sensor noise

这样后面如果你要替换 pattern family，不需要重新改场景生成逻辑。

### 4. 区分预览数据与正式数据

建议明确保留两套配置：

- preview/dev：低采样、短视频、低并发成本
- production/high-quality：高采样、长视频、完整 GT

你当前已经开始做 timing / CPU / GPU 统计，这非常对。正式数据集生产前，一定要先用 preview 配置做 profiling。

## 关于高质量随机游走视频的建议

针对 `docs/ConfiguringCameras.md`，如果目标是 Structured Light，建议优先尝试室内随机游走视频，并把重点放在：

1. `rrt_cam_indoors.gin`
2. `monocular_video.gin`
3. `iterate_scene_tasks.frame_range`
4. `compute_base_views.min_candidates_ratio`
5. `compose_indoors.animate_cameras_enabled`

比较实用的策略是：

- 先用短片段验证，例如 12 到 24 帧。
- 再逐步扩展到 48、96、192 帧。
- 先固定单房间，再扩展到多房间。
- 先固定少量资产与较快 solver，再逐渐提高复杂度。

这样能避免一开始就把成本耗在“超长视频 + 超复杂场景 + 高采样渲染”。

## 数据集设计建议

如果目标是训练泛化更强的模型，建议数据集不要只采一种室内分布。

推荐按如下维度做分桶：

1. 场景类型：卧室、客厅、厨房、餐厅、浴室。
2. 几何复杂度：简洁、中等、拥挤。
3. 材质难度：漫反射、混合、强反射/半透明。
4. 相机运动：静态、慢速随机游走、快速随机游走。
5. 投影难度：低频 pattern、高频 pattern、多 pattern family。

后续训练时，你可以显式控制各桶比例，而不是只依赖随机采样。

## 你现在最值得继续推进的事项

1. 先稳定一套室内视频生成配置，并确认输出路径和统计脚本工作正常。
2. 把 projector rig 和 pattern 渲染参数设计成单独的元数据层。
3. 沿用 `.idea/deepsl-data/README.md` 的 `parameters.npz` 思路，统一保存标定信息。
4. 用当前新增的 `statistics` 管线，先找出哪一类 scene / camera 设置最耗时。
5. 等 profiling 稳定后，再决定是否进一步改 `manage_jobs` 或 Blender 渲染策略来追求吞吐。

## 不建议现在就做的事

1. 不建议一开始就大改 Infinigen 核心 scene generation 逻辑。
2. 不建议先追求“所有 scene 都超高质量”，这会让 profiling 失真且开发速度很慢。
3. 不建议把 structured light pattern、sensor noise、scene generation 混成一个大脚本。

## 推荐关注的代码入口

建议后续优先看这些位置：

1. `infinigen_examples/generate_indoors.py`
2. `infinigen/core/placement/camera_trajectories.py`
3. `infinigen/core/placement/camera.py`
4. `infinigen/core/execute_tasks.py`
5. `infinigen/core/rendering/render.py`
6. `infinigen_examples/configs_indoor/rrt_cam_indoors.gin`
7. `infinigen/datagen/manage_jobs.py`
8. `.idea/deepsl-data/README.md`

如果下一步要正式接 projector / pattern 仿真，建议再新增一个专门面向 structured light 的渲染脚本，而不是继续把逻辑塞进现有 demo 命令里。