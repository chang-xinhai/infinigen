# AGENTS.md

## Purpose

This file guides code agents working on the `scripts/benchmark/neural_rgbd` subsystem.

This subsystem exists to reproduce the Neural RGB-D dataset scenes and camera trajectories inside this repository, then extend that reproduction pipeline with the repository's existing structured-light rendering workflow.

The goal is not to modify or generalize the main Infinigen pipeline. The goal is to build a clean, independent benchmark-oriented implementation for Neural RGB-D scenes that can call existing Infinigen components where useful.

This file is written for code agents such as Codex, Claude, and GPT-style engineering agents.

## Subsystem Goal

The Neural RGB-D benchmark workflow in this repository has three ordered stages:

1. Import the official Neural RGB-D camera trajectory into an Infinigen-compatible trajectory scene.
2. Re-render RGB from the provided Blender scene and verify that the rendered images match the official Neural RGB-D RGB frames as closely as possible.
3. Run structured-light rendering on top of the validated scene and trajectory using the existing repository structured-light implementation.

Do not skip this order.

If RGB reproduction is not validated first, do not treat structured-light output as trustworthy.

## Inputs And Dataset Layout

The benchmark implementation is expected to consume the dataset already stored under `data/neural_rgbd`.

Expected layout:

1. Scene Blender files:
   `data/neural_rgbd/blendswap_scenes/<scene_name>/...*.blend`
2. Scene data:
   `data/neural_rgbd/neural_rgbd_data/<scene_name>/`
3. Per-scene files:
   - `focal.txt`
   - `poses.txt`
   - `trainval_poses.txt`
   - `images/`
   - optional depth folders

Default pose source:

1. Use `blender_poses` by default when the owner-provided Blender pose archive is available locally under `data/neural_rgbd/blender_poses/`.
2. Support `poses.txt` and `trainval_poses.txt` as explicit alternatives.
3. Keep the selected pose source explicit in scripts, metadata, docs, and tests.

## Default Workflow For Agents

Use this workflow unless the task clearly requires something narrower:

1. Read only the docs and code relevant to Neural RGB-D reproduction.
2. Keep the implementation isolated under `scripts/benchmark/neural_rgbd` unless there is a clear reason to add small shared helpers elsewhere.
3. First implement trajectory import.
4. Then implement RGB reproduction and image comparison.
5. Then integrate structured-light rendering.
6. Add focused tests under `tests/` for each stage.
7. Run the smallest meaningful validation first.
8. Update `docs/` when behavior, workflow, outputs, assumptions, or commands change.

## Starting Points

Before making changes, prefer these entry points:

1. `AGENTS.md` at the repository root for global repo rules
2. `docs/StructuredLightBenchmark.md`
3. `docs/TrajectoryPreview.md`
4. `docs/GroundTruthAnnotations.md`
5. `scripts/launch/structured_light_indoors.sh`
6. `scripts/blender_trajectory_preview.py`
7. `infinigen/core/rendering/structured_light.py`
8. `tests/core/` for script and pipeline testing patterns

Read only what is needed for the current task. Do not bulk-read the entire repository.

## Scope Boundaries

### Encouraged Changes

Agents are encouraged to modify:

1. Files under `scripts/benchmark/neural_rgbd`
2. Focused benchmark-related tests under `tests/`
3. Benchmark-related documentation under `docs/`
4. Small glue code that helps this subsystem call existing Infinigen functionality without changing core behavior

### Changes That Require User Approval First

Agents must ask for approval before:

1. Changing the structured-light camera rig or camera layout
2. Changing the main Infinigen generation pipeline beyond what is needed for this local benchmark subsystem
3. Modifying anything under `outputs/`
4. Performing large-scale formatting or repository-wide rewrites
5. Changing environment dependencies, installation flows, or package requirements

### Forbidden Changes

Do not proactively modify these areas:

1. `infinigen/OcMesher`
2. `infinigen/infinigen_gpl`
3. Third-party or vendored code unless the user explicitly asks for it

## Implementation Requirements

### 1. Trajectory Import

The first required capability is conversion from Neural RGB-D camera poses into an Infinigen-compatible trajectory scene.

This stage should:

1. Load the original Neural RGB-D `.blend` scene.
2. Parse `focal.txt` and the selected pose file.
3. Convert the official camera poses into the coordinate convention needed by Blender and the local rendering pipeline.
4. Write an animated `trajectory/scene.blend` output.
5. Write `trajectory/trajectory_metadata.json`.

The output trajectory scene should be usable by preview-style workflows, including Blender-based camera motion inspection.

### 2. RGB Reproduction

The second required capability is RGB rerendering from the imported scene and trajectory.

This stage should:

1. Render from the imported trajectory scene.
2. Match the official Neural RGB-D RGB camera intrinsics as closely as possible.
3. Match the official RGB frame count and frame ordering.
4. Compare rerendered frames against `images/img*.png`.
5. Save scene-level and frame-level comparison results.

This is a benchmark reproduction stage, not just a generic render stage.

Success is not merely "the scene renders." Success means the repository can render from the same scene and trajectory and produce images that are as close as possible to the official Neural RGB-D RGB frames.

### 3. Structured-Light Rendering

Only after trajectory import and RGB reproduction are in place should structured-light rendering be added.

This stage should:

1. Reuse the imported trajectory scene.
2. Reuse the Neural RGB-D RGB camera trajectory as the benchmark reference path.
3. Call the existing repository structured-light implementation rather than reimplementing it.
4. Keep structured-light rig parameters explicit and configurable.
5. Preserve the repository's structured-light output conventions where practical.

The benchmark-local code should wrap the existing structured-light pipeline, not fork or rewrite the core structured-light system without approval.

## Metadata And Output Expectations

The benchmark implementation should produce clear, reproducible outputs.

At minimum, benchmark-local outputs should include:

1. A trajectory scene such as `trajectory/scene.blend`
2. A trajectory metadata file such as `trajectory/trajectory_metadata.json`
3. RGB rerender outputs
4. RGB comparison summaries
5. Structured-light outputs in the repository's normal structured-light layout

Trajectory metadata should explicitly record:

1. scene name
2. pose source
3. focal value
4. image size
5. frame range
6. per-frame pose samples
7. any coordinate-conversion assumptions used by the importer

## Testing And Validation

Use the `infinigen` conda environment for validation work.

Default validation policy:

1. Add or update focused tests under `tests/`
2. Prefer targeted validation before expensive full-scene reruns
3. When changing benchmark pipeline behavior, output layout, metadata schema, or rendering behavior, run the smallest realistic local validation that exercises the changed stage
4. When the benchmark pipeline becomes pipeline-facing or user-facing, run the relevant end-to-end benchmark command as well

Minimum expected coverage:

1. pose-file parsing
2. frame-count consistency with official images
3. trajectory metadata writing
4. trajectory scene generation
5. RGB rerender command behavior
6. RGB comparison report generation
7. structured-light stage handoff from imported trajectory scenes

Do not stop at static reasoning when a focused test can be written.

## Reproducibility

Any work involving randomness must make the seed explicit.

Agents should:

1. Preserve or expose seeds in scripts, configs, docs, and tests
2. Keep benchmark entry points deterministic by default
3. Document any non-deterministic behavior that cannot be fully controlled

Even though Neural RGB-D trajectories are externally provided, any additional benchmark-side randomized behavior must remain explicit and reproducible.

## Engineering Style

Default engineering expectations:

1. Prefer small-step, local, reversible changes
2. Avoid unnecessary new dependencies
3. Favor benchmark-specific clarity over premature abstraction
4. Reuse existing repository scripts and rendering components where that reduces risk
5. Do not expand scope into a generic scene-import framework unless the user explicitly asks for it

## Documentation Policy

Documentation is part of the deliverable.

Agents should:

1. Check existing `docs/` files first
2. Update an existing document when extending an already-documented workflow
3. Create a new Neural RGB-D benchmark document under `docs/` when introducing a new command path, workflow, output convention, or operational constraint
4. Keep docs concrete and operational, including commands, paths, assumptions, and output locations

Any new benchmark command should be documented before the task is considered complete.

## Delivery Notes

Use conventional commits when asked to prepare a commit.

Final delivery notes or PR summaries should clearly state:

1. why the change was made
2. which benchmark stage was affected
3. which commands were run
4. which tests passed
5. whether output layout, camera assumptions, or structured-light behavior changed
6. where generated benchmark outputs can be found when relevant
