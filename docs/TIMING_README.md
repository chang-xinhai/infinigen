# Time Recording for Indoor Generation Pipeline

This document describes the time recording functionality added to `generate_indoors.py` to help analyze and optimize the performance of the indoor generation pipeline.

## Overview

The time recording system tracks the execution time of each major stage in the indoor generation pipeline and provides detailed reports and visualizations to help identify performance bottlenecks.

## Features

- **Detailed Stage Timing**: Records execution time for all major pipeline stages
- **Visual Reports**: Generates bar charts, pie charts, and detailed breakdowns
- **JSON Export**: Saves detailed timing data in machine-readable format  
- **Console Summary**: Displays formatted timing summary with ASCII progress bars
- **Bottleneck Identification**: Highlights the most time-consuming stages

## Usage

### Enable Time Recording

Add the `--time_record` flag when running the indoor generation:

```bash
python infinigen_examples/generate_indoors.py \
    --output_folder ./my_scene \
    --seed 42 \
    --time_record \
    --task coarse
```

### Generated Files

When time recording is enabled, the following files will be created in your output folder:

1. **`timing_report.json`** - Detailed timing data in JSON format
2. **`timing_chart.png`** - Bar chart and pie chart visualization
3. **`timing_detailed_chart.png`** - Detailed horizontal bar chart with percentages
4. **Console output** - Formatted timing summary printed to terminal

### Example Output

The console will display a comprehensive timing report like:

```
================================================================================
INDOOR GENERATION PIPELINE - TIMING REPORT  
================================================================================
Total Execution Time: 245.67 seconds
Number of Stages: 18

Stage Breakdown:
--------------------------------------------------------------------------------
Stage                          Duration (s)    Percentage   Bar
--------------------------------------------------------------------------------
solve_large                    89.23           36.3%        ██████████████████████████████
solve_medium                   45.67           18.6%        ███████████████
solve_small                    32.10           13.1%        ███████████
populate_assets                28.45           11.6%        █████████████
floating_objs                  15.89           6.5%         ██████████
room_walls                     12.34           5.0%         ████████
terrain                        8.67            3.5%         ██████
solve_rooms                    7.23            2.9%         █████
...
================================================================================

Top 5 Time-Consuming Stages:
--------------------------------------------------
1. solve_large: 89.23s (36.3%)
2. solve_medium: 45.67s (18.6%)  
3. solve_small: 32.10s (13.1%)
4. populate_assets: 28.45s (11.6%)
5. floating_objs: 15.89s (6.5%)
================================================================================
```

## Pipeline Stages Tracked

The time recording system tracks these major pipeline stages:

### Core Generation Stages
- **terrain** - Terrain generation
- **sky_lighting** - Lighting setup
- **solve_rooms** - Room layout solving
- **solve_large** - Large object placement (floor/wall objects)
- **solve_medium** - Medium object placement (wall/ceiling objects)  
- **solve_small** - Small object placement (tabletop objects)

### Asset and Decoration Stages
- **populate_assets** - Asset population
- **floating_objs** - Floating object placement
- **room_doors** - Door placement and decoration
- **room_windows** - Window placement and decoration
- **room_stairs** - Stair generation
- **skirting_floor** - Floor skirting boards
- **skirting_ceiling** - Ceiling skirting boards

### Room Processing Stages  
- **room_pillars** - Pillar generation
- **room_walls** - Wall material and decoration
- **room_floors** - Floor material and decoration
- **room_ceilings** - Ceiling material and decoration

### Camera and Final Stages
- **pose_cameras** - Camera positioning
- **animate_cameras** - Camera animation setup
- **lights_off** - Light cleanup
- **invisible_room_ceilings** - Ceiling visibility setup
- **overhead_cam** - Overhead camera setup
- **hide_other_rooms** - Room visibility management
- **nature_backdrop** - Outdoor environment setup

## Analyzing Results

### Identifying Bottlenecks

1. **Check the Top 5 list** - Focus optimization efforts on the highest time consumers
2. **Look for unexpected outliers** - Stages taking much longer than expected may indicate issues
3. **Compare percentages** - Stages taking >20% of total time are good optimization candidates

### Common Optimization Strategies

Based on timing results, consider these optimizations:

- **solve_large/medium/small taking too long?**
  - Reduce `solve_steps_large`, `solve_steps_medium`, `solve_steps_small` parameters
  - Enable `abort_unsatisfied_*` parameters to fail fast on impossible constraints

- **populate_assets taking too long?**
  - Reduce the number of asset types being loaded
  - Use simpler asset variants

- **floating_objs taking too long?**
  - Reduce `num_floating` parameter
  - Disable collision detection with `enable_collision_*=False`

- **room decoration stages taking too long?**
  - Simplify material complexity
  - Reduce decoration density

## Integration with Existing Workflows

The time recording is designed to be non-intrusive:

- **Zero overhead when disabled** - No performance impact when `--time_record` is not used
- **Compatible with all configs** - Works with any gin configuration
- **Preserves existing output** - All normal output files are still generated
- **Safe failure mode** - If visualization libraries are missing, timing data is still saved as JSON

## Dependencies

For full functionality (including charts), install:

```bash
pip install matplotlib>=3.5.0
```

Without matplotlib, timing data will still be recorded and displayed in the console, but charts won't be generated.

## Troubleshooting

### No timing files generated
- Ensure `--time_record` flag is specified
- Check that the output folder is writable
- Verify the generation completed without errors

### Charts not generated
- Install matplotlib: `pip install matplotlib`
- Check console for import warnings

### Inaccurate timing
- Time recording adds minimal overhead (~0.1% typical)
- System load and other processes can affect measurements
- Run multiple tests for consistent results

## Technical Details

### Implementation

The timing system uses a `TimeRecorder` class that:
- Wraps each `p.run_stage()` call with timing measurement
- Maintains ordered lists of stages and their durations
- Provides multiple output formats (JSON, console, charts)

### Data Format

The JSON output contains:
```json
{
  "total_time_seconds": 245.67,
  "stage_count": 18,
  "stage_timings": [
    {
      "stage": "terrain",
      "duration_seconds": 8.67,
      "percentage": 3.5
    },
    ...
  ]
}
```

This data can be easily processed by external analysis tools or scripts.
