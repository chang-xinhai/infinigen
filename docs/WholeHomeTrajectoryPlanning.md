# Whole-Home Trajectory Planning for Structured-Light Benchmark

This document proposes a house-scale camera trajectory planning scheme for generating benchmark-quality indoor walking videos from existing Infinigen scenes, with strong compatibility with the current structured-light rendering pipeline.

Implementation status in this repository:

- a new `trajectory` task can animate an existing indoor `coarse/scene.blend`
- whole-home walk hyperparameters are exposed in `infinigen_examples/configs_indoor/whole_home_walk.gin`
- the benchmark launch script can reuse existing `coarse` scenes and render from the animated `trajectory` scene
- the currently validated runtime implementation uses `doorway_straight_segments` as its navigation realization mode instead of the heavier scene-wide BVH pathfinder
- doorway centers are inferred from adjacent room bounds instead of trusting door object origins, which avoids the `0,0` portal failure seen in the first draft
- room orbit is disabled by default in benchmark configs; the default room coverage motif is now door-to-room traversal plus in-place sweep

Validation status:

- validated on an existing benchmark scene copied from `outputs/benchmark/structured_light_indoors/seed_0/coarse`
- trajectory planning completed successfully in `infinigen_311` and wrote `trajectory/scene.blend` plus `trajectory_metadata.json`
- on `seed_0`, door centers now resolve to interior portal locations such as `(3.25, 3.5)`, `(7.75, 4.25)`, and `(5.0, 12.75)` instead of the invalid `(0, 0)` fallback
- structured-light rendering wrote complete low-resolution outputs for both 2-frame and 1-frame checks under `/tmp/whole_home_walk_e2e/seed_0/`
- the current `infinigen_311 + bpy` runtime still segfaults on shutdown after rendering completes, but the structured-light outputs are already present on disk when that happens

It is written for the current repository state where:

- scene generation already works for benchmark scenes such as `outputs/benchmark/structured_light_indoors/seed_0/coarse/scene.blend`
- structured-light rendering already reuses animated camera poses from the Infinigen camera rig
- the current indoor camera trajectory support is mainly fixed viewpoints, short random walks, or generic RRT motion

## Goal

Generate one or more long, coherent, room-scale walking trajectories per house that:

- stay physically plausible in Infinigen / Blender scenes
- cover the whole home instead of a single room
- are useful for reconstruction, stereo, and structured-light benchmarking
- preserve loop closure opportunities
- keep enough viewpoint change to be informative without becoming erratic
- remain compatible with the existing `coarse -> structured_light` workflow

## What Existing Code Already Gives Us

Relevant current entry points:

- `infinigen_examples/generate_indoors.py`
- `infinigen/core/placement/camera_trajectories.py`
- `infinigen/core/util/rrt.py`
- `infinigen/core/placement/path_finding.py`
- `infinigen/core/rendering/structured_light.py`
- `.idea/procthor_path_planning/generate_path.py`

Important current behavior:

1. `compose_indoors()` spawns camera rigs during `coarse` generation and animates them before saving `scene.blend`.
2. `render_structured_light()` later loads the saved scene and copies the animated pose from the Infinigen camera rig.
3. This means the main missing capability is not the structured-light renderer. It is a stronger whole-home trajectory planner for the coarse stage.

## Why The Current Indoor Trajectory Modes Are Not Enough

`docs/ConfiguringCameras.md` already states that indoor random walk is unlikely to find paths between rooms. That matches the current code:

- `random_walk` and `random_walk_forward` are local motion policies
- `rrt_cam_indoors.gin` improves obstacle avoidance, but it still samples motion in continuous free space without an explicit room-visit objective
- the current RRT validator mostly checks geometric validity and rough view quality, not room coverage or benchmark protocol

The old ProcTHOR helper under `.idea/procthor_path_planning/` is directionally useful because it already encodes:

- room graph traversal
- room center visitation
- doorway transitions
- center orbit / lookaround behavior

But it is still too weak for benchmark use because it does not robustly use Blender scene geometry for:

- navigable free-space extraction
- clearance from furniture and walls
- camera height constraints
- visibility quality control
- motion smoothness and frame informativeness

## External References And The Design Signals They Provide

### SIMS-V

SIMS-V explicitly generates trajectories that tour all rooms, traverse to each room center, and perform a 360-degree rotation there. This is the closest direct reference to your requested behavior.

Source:

- https://arxiv.org/html/2511.04668v2

Relevant signal:

- they capture multiple trajectories per environment
- they aim for comprehensive spatial coverage
- they use shortest-path traversal to room centers plus a full rotation at the center

This strongly supports using a room-graph planner rather than only local random walk.

### MegaSynth

MegaSynth emphasizes that wide-coverage scene reconstruction benefits from explicit control over camera poses, and it calls out that prior data often suffers from small camera motions. It also notes that default Infinigen videos can have too much consecutive-frame overlap, so they render at 6 FPS to reduce redundancy.

Source:

- https://arxiv.org/html/2412.14166v2

Relevant signal:

- wide-coverage reconstruction wants larger, intentional coverage
- overly redundant adjacent frames are wasteful
- camera placement and pose distribution matter at least as much as scene realism

This supports designing trajectories with informative motion, not just long duration.

### What Makes Good Synthetic Training Data for Zero-Shot Stereo Matching?

The appendix states that for indoor floating-object scenes they place 20 camera rigs with the default Infinigen placement algorithm, which tries to maximize the standard deviation of depth values.

Source:

- https://arxiv.org/html/2504.16930v3

Relevant signal:

- depth diversity is already a useful heuristic in this codebase
- viewpoint quality should not be purely geometric free-space validity

This suggests adding view-quality terms such as depth variation, wall proximity, and occlusion structure into trajectory scoring.

### RoomPlan / ARKit-style Capture Practice

Apple's RoomPlan writeup emphasizes scan guidance based on speed, lighting, and distance, and notes that real collection benefits from multiple motion patterns that capture walls, floor, ceiling, and room-defining objects.

Source:

- https://machinelearning.apple.com/research/roomplan

Relevant signal:

- motion speed and camera-to-surface distance should be controlled
- real scans do not rely on a single motion primitive
- room capture quality improves when trajectories explicitly target structural surfaces and salient objects

### LLFF

LLFF is not an indoor embodied navigation paper, but it is useful as a sampling principle reference: view quality depends on how densely the scene is sampled, and the required sampling density depends on scene geometry rather than a fixed generic FPS.

Source:

- https://bmild.github.io/llff/index.html

Relevant signal:

- frame spacing should be tied to geometry and intended reconstruction difficulty

This supports adaptive resampling by path length and nearest-scene depth rather than just raw Blender frame count.

## Proposed Planner: Hierarchical Whole-Home Coverage Planner

The proposed planner has three layers.

### Layer 1: House-Level Visit Order

Build a room connectivity graph and decide a room visitation sequence.

Input candidates:

- room meshes already produced by Infinigen
- door / portal geometry when available
- room centroids and room adjacency inferred from wall openings or mesh connectivity

Default behavior:

1. choose a start room, preferably a living room or the largest room by floor area
2. traverse all reachable rooms
3. return to the start room for loop closure

Recommended default traversal:

- weighted DFS with explicit backtracking through doorways

Why not plain shortest Hamiltonian-style ordering:

- houses naturally branch
- exact global optimization is unnecessary
- for reconstruction benchmarking, revisits and loop closures are actually useful

Recommended rule:

- prefer a traversal that visits each room at least once
- revisit articulation rooms such as living room, hallway, and kitchen
- close the trajectory by returning near the initial region

This is closer to real room scanning and better for global consistency than a single non-returning pass.

### Layer 2: Room-Level Coverage Motifs

Inside each room, do not just pass through the center. Use a room coverage motif.

Each room visit is broken into:

1. doorway entry segment
2. approach-to-center segment
3. center sweep segment
4. optional perimeter or object-facing segment
5. return-to-exit segment

Recommended default motif by room size:

- small rooms: center stop plus one slow 360-degree sweep
- medium rooms: center stop plus 360-degree sweep plus short offset arc
- large rooms: center sweep plus 2 to 4 anchor points around the room interior

The center sweep should not be a pure in-place rotation for every room. For reconstruction, pure yaw helps appearance coverage but contributes little translational parallax. Therefore:

- use a small-radius orbit when there is space
- fall back to in-place 360 only when the room is too tight

Recommended orbit radius:

- `r = clamp(0.35, 0.9, 0.45 * d_wall_min)`

where `d_wall_min` is the minimum horizontal distance from the room center to walls or large obstacles.

This is an inference from the reconstruction references above: the room needs both appearance coverage and usable baseline.

### Layer 3: Free-Space Path Realization

Once high-level waypoints are selected, realize them as a collision-safe walkable path in Blender space.

Do not use only line-of-sight interpolation. Instead:

1. extract a 2D walkable free-space map on the floor plane
2. shrink it by a clearance radius
3. connect waypoints with shortest paths on that free-space graph
4. smooth the polyline into a C1-continuous camera path
5. resample the path by metric distance

Recommended navigation representation:

- one navigation slice per floor level
- 2D occupancy at walking height using downward projection and obstacle inflation

This is much easier to stabilize than generic full-3D RRT for indoor walking.

## Compatibility With Infinigen / Blender

The planner should be highly compatible if it uses scene geometry that already exists after `compose_indoors()`:

- room meshes for inside / outside tests
- non-room objects for obstacle inflation
- existing BVH utilities for visibility and collision checking
- existing camera rig animation keyframing

The most compatible strategy is:

1. keep the existing camera rig format unchanged
2. keep the structured-light rig unchanged
3. replace only the logic that decides rig keyframes during `coarse`

That means:

- no change to the structured-light camera layout
- no change to the later `render_structured_light()` interface
- no change to dataset metadata format except adding richer trajectory metadata

## Proposed Motion And View Constraints

These defaults are aimed at reconstruction-friendly indoor walking.

### Height

Walking height:

- default sampled once per trajectory from `Uniform[1.2, 1.8]` m

Recommended benchmark default:

- `1.55 m`

Recommended production randomization:

- 50 percent of trajectories in `[1.45, 1.65]`
- 25 percent in `[1.2, 1.45]`
- 25 percent in `[1.65, 1.8]`

Reason:

- the center mass of real handheld and chest/head-mounted capture is closer to the middle band
- the tails help robustness to different operator heights and sensor mounting

### Translation Speed

Recommended walking speed:

- nominal `0.35 to 0.7 m/s`

Slow down at:

- doorway crossing
- entering cluttered rooms
- center sweep / orbit segments

Speed multipliers:

- hallway / open traversal: `1.0`
- doorway segment: `0.7`
- center orbit: `0.45`

### Rotation Rate

Recommended yaw rate cap:

- `20 to 35 deg/s` during general motion
- `35 to 60 deg/s` during deliberate center sweep

Pitch:

- mostly `[-12, 8] deg`
- allow occasional down-looking frames near tables, counters, sinks, and clutter

Roll:

- near zero for benchmark trajectories
- optional tiny handheld wobble only in training-only variants

### Clearance

Recommended camera-body clearance:

- `0.20 m` from walls
- `0.25 to 0.35 m` from large furniture

Recommended structured-light extra safety:

- reject frames whose nearest visible surface is below `0.20 m`

This is aligned with the filtering logic already seen in MegaSynth-style pipelines and prevents clipping or unusable high-disparity extremes.

## Reconstruction-Oriented View Objectives

The planner should optimize not only for reachability but also for view usefulness.

For each candidate key pose, compute a score from:

1. free-space validity
2. clearance validity
3. depth variation score
4. visible surface area score
5. room-boundary / doorway coverage score
6. novelty relative to recent frames
7. loop-closure opportunity score

Suggested score form:

`score = w_free + w_depth + w_surface + w_structure + w_novelty + w_loop`

Important practical rule:

- penalize long stretches of nearly identical views

This follows MegaSynth's observation that default video trajectories can have too much overlap between adjacent frames.

## Recommended Benchmark Trajectory Template

For a whole house, I recommend one primary benchmark template first.

### Template A: Coverage Walk

1. start in living room or largest shared room
2. do a partial sweep near the start to establish context
3. traverse rooms one by one using doorway graph traversal
4. in each room:
   - enter
   - move toward center
   - do a 270 to 360 degree sweep
   - if space permits, add a small orbit or side anchor
   - exit through the same doorway or next doorway
5. revisit the living room
6. finish near the initial region with a final short sweep

Properties:

- easy to explain
- loop closure built in
- strong whole-house coverage
- close to the behavior described in SIMS-V

### Template B: Coverage Walk Plus Object Bias

This is a later extension.

Same as Template A, but when a room contains large central furniture or strong geometry:

- table
- sofa
- bed
- kitchen island
- bathroom vanity

insert 1 to 2 short detours that view the object from multiple sides.

This improves reconstruction around occlusion-heavy assets and yields more realistic close-range parallax.

### Template C: Dual-Pass Benchmark

For stronger evaluation, create two synchronized protocols from the same scene:

- pass 1: conservative smooth walk
- pass 2: slightly different room order or different in-room anchor offsets

This supports:

- cross-trajectory registration
- loop closure stress
- multi-session reconstruction evaluation

I would not implement this first, but it is the right benchmark extension after the single-pass planner is stable.

## Concrete Default Settings

If we need one actionable initial setting, I recommend:

- one trajectory per house for MVP
- trajectory height fixed at `1.55 m`
- start room: largest room by floor area, with living room priority if available
- room traversal: weighted DFS over doorway graph, ending back at start room
- per room:
  - move to room center
  - perform `300 deg` sweep
  - if `d_wall_min >= 1.2 m`, replace in-place sweep with `0.4 to 0.7 m` radius orbit
- path resampling distance: `0.04 to 0.06 m`
- render FPS: `6 to 10`
- total path duration target: `60 to 180 s` depending on house size

For benchmark scenes, I would start with:

- `8 FPS`
- `0.05 m` resampling step
- no handheld shake
- almost zero roll
- deterministic seed-controlled traversal

## Why 8 FPS Is A Good Starting Point

This is not from a single paper, but it is consistent with the evidence:

- SIMS-V uses 10 FPS for room-touring video
- MegaSynth explicitly reduces video FPS to reduce excessive consecutive overlap
- structured-light data benefits from informative motion, not raw frame count

So `8 FPS` is a reasonable benchmark default for whole-home walking:

- enough temporal continuity
- less redundancy than 24 FPS
- easier storage and rendering budget

## Proposed Metadata Additions

In addition to existing camera calibration outputs, save trajectory metadata per scene:

- trajectory id
- planner version
- planner seed
- room visitation order
- waypoint list before smoothing
- resampled path points
- room segment boundaries
- doorway crossing indices
- per-frame room id
- per-frame motion state such as `traverse`, `sweep`, `orbit`, `doorway`

This will make downstream evaluation much easier.

## Recommended Implementation Strategy

### Stage 1: Minimal Viable Planner

Add a new indoor animation mode, for example:

- `animation_mode = "whole_home_walk"`

Implement:

1. room graph extraction
2. room ordering
3. center waypoint generation
4. doorway-aware path stitching
5. path smoothing and keyframing

At this stage, keep the camera mostly forward-looking along path tangent, with explicit sweep segments.

### Stage 2: Quality Filters

Add frame or waypoint rejection based on:

- clipping risk
- too-close surfaces
- too much empty wall
- too little depth variation
- too much similarity to previous frames

### Stage 3: Benchmark Protocol

Add a dedicated gin config and launch script path for benchmark whole-home videos.

Suggested config:

- `infinigen_examples/configs_indoor/whole_home_walk.gin`

Suggested script extension:

- `scripts/launch/structured_light_indoors_benchmark.sh`
- or a dedicated `scripts/launch/structured_light_whole_home_walk.sh`

### Stage 4: Structured-Light-Aware Refinement

Only after the planner is stable, add structured-light-specific preferences:

- avoid too many specular-only views in a row
- cap extreme near-field disparity
- encourage mixed fronto-parallel and oblique observations

## Recommended Code Integration Points

The least disruptive implementation plan is:

1. add a new planner module, for example:
   - `infinigen/core/placement/whole_home_trajectory.py`
2. call it from `generate_indoors.py` inside `animate_cameras()`
3. expose settings through a new gin config
4. keep `camera.spawn_camera_rigs()` and `render_structured_light()` unchanged

I do not recommend trying to force this entirely into the existing generic RRT policy. The problem is no longer just local collision-free motion. It is structured coverage planning with room semantics.

## Testing Plan

Minimal validation should include:

1. graph extraction test on a small indoor scene
2. planner determinism test with fixed seed
3. path validity test:
   - all sampled points lie in walkable free space
   - no segment intersects obstacle geometry
4. coverage test:
   - every reachable room is visited
5. regression test:
   - output trajectory metadata is written

Then run a small full pipeline check on:

- one existing benchmark scene
- one single-room scene
- one cluttered multi-room scene

The final validation should include the whole structured-light launch path because that is the actual downstream consumer.

## Final Recommendation

The best next implementation target is not generic “better RRT”.

It is a hierarchical planner with:

- room-graph traversal for global order
- room-specific coverage motifs for local completeness
- free-space path realization for physical plausibility
- reconstruction-oriented frame scoring for view usefulness

If we need one sentence for the implementation direction, it is:

Use a deterministic room-graph coverage walk with doorway-aware shortest paths and per-room center-orbit sweeps, then resample and smooth it into an Infinigen camera animation at controlled walking height and informative frame spacing.

Current implementation note:

The validated implementation currently realizes transitions as doorway-anchored straight segments with metric resampling. Scene-wide obstacle-aware BVH pathfinding remains a follow-up improvement once the heavier runtime path can be stabilized for benchmark scenes without causing memory pressure in this environment.
