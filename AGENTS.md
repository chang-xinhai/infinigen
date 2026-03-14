# AGENTS.md

## Purpose

This file guides code agents working in this repository.

This repository is used to build a high-quality simulated structured-light dataset on top of Infinigen. The long-term goal is to leverage Infinigen's large-scale scene generation capability, extend the scene pipeline, add scene tuning and randomness, integrate new assets such as Objaverse content and floating objects, capture multi-view trajectories, and produce RGB plus structured-light observations for training feed-forward structured-light reconstruction models.

This file is written for code agents such as Codex, Claude, and GPT-style engineering agents. It is not primarily written for general human contributors.

## Project Focus

There is no single task priority ordering. Work is usually parallel across several major tracks:

1. Infinigen scene generation
2. Camera trajectory planning
3. Structured-light rendering
4. Asset integration and randomization
5. Recurring engineering work such as test repair, local validation, refactoring, and documentation

Current near-term emphasis:

1. Camera trajectory planning
2. Asset integration plus randomization

Structured-light rendering already has a core implementation and should be treated as an existing system to extend carefully.

## Core Files And Starting Points

Before making changes, read only the documentation and code that are relevant to the current task. Do not bulk-read the whole repository.

Default starting points:

1. `docs/` with task-specific selection by document title
2. `scripts/launch/structured_light_indoors.sh` for the end-to-end indoor structured-light pipeline
3. `infinigen/core/rendering/structured_light.py` for the structured-light core implementation
4. `infinigen_examples/configs_indoor/` for indoor gin configs, especially structured-light-related settings
5. `tests/` for local verification patterns and task-specific regression coverage

Important working rule:

1. Start from relevant existing docs before changing code
2. After finishing a task, update existing docs or create a new task-specific document under `docs/` when the change introduces a new workflow, new behavior, new outputs, or new operational constraints

## Expected Workflow For Agents

Use this workflow by default unless the task clearly requires a different order:

1. Identify which of the main tracks the task belongs to: scene generation, trajectory planning, structured-light rendering, or asset/randomization work
2. Read only the relevant docs and code entry points
3. Prefer small, local, reversible changes over broad rewrites
4. Reuse and extend existing scripts, gin configs, and pipeline code where possible
5. Add or update focused tests in `tests/` for the changed behavior
6. Run the smallest meaningful validation first
7. When the task is substantial or pipeline-facing, run the full structured-light launch script
8. Update documentation in `docs/` if the task changed usage, outputs, assumptions, or workflow

## Modification Boundaries

### Encouraged Changes

Agents are encouraged to modify:

1. `scripts/` scripts
2. `infinigen_examples/configs_indoor/` gin configuration files
3. The implementation pipeline for the targeted task
4. `docs/` documentation

### Changes That Require User Approval First

Agents must ask for approval before:

1. Changing the structured-light camera rig or camera layout
2. Changing the main Infinigen generation pipeline in ways that affect behavior beyond the local task
3. Performing large-scale formatting or repository-wide style rewrites
4. Modifying anything under `outputs/`
5. Changing environment dependencies, installation flows, or package requirements

### Forbidden Changes

Do not proactively modify these areas:

1. `infinigen/OcMesher`
2. `infinigen/infinigen_gpl`
3. Other third-party or vendored dependency code unless the user explicitly asks for it

## Testing And Validation

Use the `infinigen` conda environment for all validation work.

Default validation policy:

1. Minimal validation: add or update a focused test function under `tests/` to verify the local change
2. Full validation: run the relevant part of the structured-light pipeline through `scripts/launch/structured_light_indoors.sh`

Testing expectations:

1. Do not stop at static reasoning when a local test can be written
2. Prefer targeted tests over broad expensive runs for the first validation pass
3. When changing pipeline behavior, rendering behavior, config behavior, or output schema, run the launch script unless the user explicitly waives it

## Randomness And Reproducibility

Any work involving randomness must make the seed explicit.

Agents should:

1. Preserve or expose seeds in scripts, configs, docs, and test cases
2. Make new scripts reproducible by default
3. Document any non-deterministic behavior that cannot be fully controlled

## Engineering Style

Default engineering expectations:

1. Prefer small-step modifications
2. Favor reproducible scripts and deterministic task entry points
3. Avoid unnecessary new dependencies
4. Do not preserve Infinigen's original generality at the expense of this repository's structured-light dataset goals
5. Keep task-specific logic clear rather than over-abstracting early-stage systems

## Documentation Policy

Documentation is part of the deliverable.

Agents should:

1. Check `docs/` first by matching the task to the most relevant document titles
2. Update existing docs when behavior changes
3. Create a new `docs/XXX.md` file when the task introduces a new workflow, subsystem, experiment protocol, or output convention that is not documented yet
4. Keep docs operational and concrete, including commands, paths, assumptions, and output locations where useful

## Commit And Pull Request Guidance

Use standard Angular-style conventional commits.

Examples:

1. `feat: add trajectory sampler for structured-light indoor capture`
2. `fix: correct structured-light depth export resolution`
3. `docs: document indoor structured-light output layout`
4. `test: add regression coverage for projector pattern export`

PRs or final delivery notes should clearly state:

1. Why the change was made
2. Which subsystem was affected
3. Which commands were run
4. Which tests or scripts passed
5. Whether gin configs, rendering parameters, or output structure changed
6. Where generated outputs can be found when relevant

## Structured-Light Notes

Current structured-light core file:

1. `infinigen/core/rendering/structured_light.py`

Treat changes there as high-impact. Small bug fixes and local improvements are acceptable, but changes to camera structure or fundamental pipeline behavior require approval first.

The current indoor structured-light launch entry point is:

1. `scripts/launch/structured_light_indoors.sh`

Agents working on trajectory planning or asset/randomization should integrate with this pipeline where possible instead of introducing disconnected workflows.

## Target Dataset Layout

The intended dataset structure is:

1. Each scene contains many trajectories
2. Each trajectory contains many frames
3. Each frame contains:
   RGB image
   Depth image
   IR-left image for 8 patterns
   IR-right image for 8 patterns
   Pattern image for 8 patterns

Additional dataset constraints:

1. RGB image and depth image share one intermediate RGB camera
2. Depth must be stored in both `png` and `exr`
3. Standard resolution is `848x480`

When implementing new pipeline behavior, naming schemes, exporters, or output folders, align with this target layout unless the user explicitly requests a deviation.
