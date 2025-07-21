#!/bin/bash

# =============================================================================
# Infinigen Kitchen Scene Generation Script
# 
# This script generates kitchen scenes using the Infinigen system with the 
# following features:
# - Single room mode (only kitchens, no other rooms)
# - Rooms centered at world origin (0,0,0)
# - Configurable lighting, object density, and export settings
# - Robust error handling and logging
# - USD and OBJ export support with fallback
# =============================================================================

set -e  # Exit on any error

# =============================================================================
# CONFIGURATION SECTION
# =============================================================================

# Basic scene settings
readonly NUM_SCENES=5
readonly SCENE_NAME="kitchen_0720_3"
readonly TEXTURE_RESOLUTION=1024
readonly START_SEED=0

# Directory structure
readonly OUTPUT_DIR="outputs/${SCENE_NAME}/dataset"
readonly EXPORT_DIR="outputs/${SCENE_NAME}/export"
readonly LOG_DIR="logs/${SCENE_NAME}"
readonly LOG_FILE="${LOG_DIR}/kitchen_generation.log"

# Lighting configuration options
declare -ra LIGHTING_CONFIGS=(
    # Bright daylight: No lights off, strong sun, high exposure
    "compose_indoors.lights_off_chance=0.0 nishita_lighting.strength=0.4 nishita_lighting.sun_elevation=60 configure_render_cycles.exposure=2.5"
    
    # Moderate lighting: Some lights off, medium sun, standard exposure  
    "compose_indoors.lights_off_chance=0.3 nishita_lighting.strength=0.35 nishita_lighting.sun_elevation=45 configure_render_cycles.exposure=3.0"
    
    # Evening/dim: Few lights off, low sun, high exposure to compensate
    "compose_indoors.lights_off_chance=0.1 nishita_lighting.strength=0.3 nishita_lighting.sun_elevation=30 configure_render_cycles.exposure=3.5"
)

# Object density settings (controls furniture and item placement)
declare -ra SOLVE_CONFIGS=(
    # Dense: More furniture and objects, longer generation time
    "compose_indoors.solve_steps_large=150 compose_indoors.solve_steps_medium=60 compose_indoors.solve_steps_small=10"
    
    # Moderate: Balanced furniture placement and generation speed
    "compose_indoors.solve_steps_large=100 compose_indoors.solve_steps_medium=40 compose_indoors.solve_steps_small=5"
    
    # Sparse: Minimal furniture, faster generation
    "compose_indoors.solve_steps_large=80 compose_indoors.solve_steps_medium=30 compose_indoors.solve_steps_small=3"
)

# Error handling and feature control
declare -ra ERROR_HANDLING_CONFIGS=(
    # Conservative: Enable ALL features for rich kitchen scenes
    "solve_objects.abort_unsatisfied=False compose_indoors.solve_medium_enabled=True compose_indoors.solve_small_enabled=True"
    
    # Balanced: Disable problematic features for better success rate
    "solve_objects.abort_unsatisfied=False compose_indoors.solve_medium_enabled=True compose_indoors.solve_small_enabled=False"
    
    # Minimal: Only basic kitchen elements for maximum reliability
    "solve_objects.abort_unsatisfied=False compose_indoors.solve_medium_enabled=False compose_indoors.solve_small_enabled=False"
)

# Floating objects (items not placed on surfaces)
declare -ra FLOATING_CONFIGS=(
    # No floating objects for cleaner scenes
    "compose_indoors.floating_objs_enabled=False"
    
    # Few floating objects for some variety
    "compose_indoors.floating_objs_enabled=True compose_indoors.num_floating=15"
    
    # Many floating objects for busy/lived-in feel  
    "compose_indoors.floating_objs_enabled=True compose_indoors.num_floating=25"
)

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

# Initialize logging and directory structure
setup_environment() {
    echo "Setting up environment for kitchen generation..."
    
    # Create necessary directories
    mkdir -p "$OUTPUT_DIR" "$EXPORT_DIR" "$LOG_DIR"
    
    # Initialize log file with header
    cat > "$LOG_FILE" << EOF
===============================================================================
Infinigen Kitchen Scene Generation Log
===============================================================================
Started: $(date)
Scenes to generate: $NUM_SCENES
Scene name prefix: $SCENE_NAME
Texture resolution: ${TEXTURE_RESOLUTION}x${TEXTURE_RESOLUTION}
===============================================================================

EOF
    
    echo "Environment setup complete."
    echo "Logs will be written to: $LOG_FILE"
    echo "Scenes will be saved to: $OUTPUT_DIR"
    echo "Exports will be saved to: $EXPORT_DIR"
}

# Log message with timestamp to both console and file
log_message() {
    local message="$(date '+%H:%M:%S') - $1"
    echo "$message" | tee -a "$LOG_FILE"
}

# Check if the previous command succeeded and log result
check_command_success() {
    local operation_name="$1"
    
    if [ $? -eq 0 ]; then
        log_message "✅ SUCCESS: $operation_name"
        return 0
    else
        log_message "❌ FAILED: $operation_name"
        return 1
    fi
}

# Format duration from seconds to human-readable format
format_duration() {
    local total_seconds=$1
    local minutes=$((total_seconds / 60))
    local seconds=$((total_seconds % 60))
    echo "${minutes}m ${seconds}s"
}

# =============================================================================
# SCENE GENERATION FUNCTIONS
# =============================================================================

# Generate a single kitchen scene with specified parameters
generate_kitchen_scene() {
    local scene_id=$1
    local seed=$2  
    local lighting_config=$3
    local solve_config=$4
    local floating_config=$5
    local error_config=$6
    
    # Setup paths and timing
    local scene_name="kitchen_${scene_id}_seed_${seed}"
    local output_folder="$OUTPUT_DIR/$scene_name"
    local export_folder="$EXPORT_DIR/$scene_name"
    local total_start_time=$(date +%s)
    
    log_message ""
    log_message "🏠 Starting Kitchen Scene $scene_id (seed: $seed)"
    log_message "   Output: $output_folder"
    log_message "   Export: $export_folder"
    
    # Phase 1: Generate the 3D scene
    if generate_scene_geometry "$scene_id" "$seed" "$output_folder" "$lighting_config" "$solve_config" "$floating_config" "$error_config"; then
        local gen_time=$?
        
        # Phase 2: Export the scene to USD/OBJ format
        if export_scene_data "$scene_id" "$output_folder" "$export_folder"; then
            local export_time=$?
            
            # Phase 3: Create documentation and summary
            create_scene_documentation "$scene_id" "$seed" "$export_folder" "$gen_time" "$export_time" "$lighting_config" "$solve_config" "$floating_config" "$error_config"
            
            local total_time=$(( $(date +%s) - total_start_time ))
            log_message "🎉 Kitchen $scene_id completed successfully in $(format_duration $total_time)"
            return 0
        else
            log_message "💥 Kitchen $scene_id export failed"
            return 1
        fi
    else
        log_message "💥 Kitchen $scene_id generation failed"
        return 1
    fi
}

# Generate the 3D scene geometry using Infinigen
generate_scene_geometry() {
    local scene_id=$1
    local seed=$2
    local output_folder=$3
    local lighting_config=$4
    local solve_config=$5
    local floating_config=$6
    local error_config=$7
    
    local start_time=$(date +%s)
    log_message "🔄 Generating 3D scene geometry..."
    
    # Run Infinigen scene generation with kitchen-only constraints
    python -m infinigen_examples.generate_indoors \
        --seed "$seed" \
        --task coarse \
        --output_folder "$output_folder" \
        --configs fast_solve.gin overhead.gin \
        --overrides \
            compose_indoors.terrain_enabled=False \
            compose_indoors.overhead_cam_enabled=True \
            restrict_solving.solve_max_rooms=1 \
            restrict_solving.restrict_parent_rooms=[\"Kitchen\"] \
            home_room_constraints.has_fewer_rooms=True \
            $error_config \
            $lighting_config \
            $solve_config \
            $floating_config \
        > "${LOG_DIR}/generate_${scene_id}_seed_${seed}.log" 2>&1
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if check_command_success "Scene generation for kitchen $scene_id"; then
        log_message "   ⏱️  Scene geometry generated in $(format_duration $duration)"
        return $duration
    else
        log_message "   ❌ Scene generation failed after $(format_duration $duration)"
        log_message "   � Check detailed logs: ${LOG_DIR}/generate_${scene_id}_seed_${seed}.log"
        return 1
    fi
}

# Export the generated scene to USD format with OBJ fallback
export_scene_data() {
    local scene_id=$1
    local output_folder=$2
    local export_folder=$3
    
    local start_time=$(date +%s)
    log_message "🔄 Exporting scene data..."
    
    # Attempt USD export first (preferred format)
    if attempt_usd_export "$scene_id" "$output_folder" "$export_folder"; then
        local duration=$(( $(date +%s) - start_time ))
        log_message "   ✅ USD export completed in $(format_duration $duration)"
        return $duration
    else
        log_message "   ⚠️  USD export failed, trying OBJ fallback..."
        
        # Fallback to OBJ export
        if attempt_obj_export "$scene_id" "$output_folder" "$export_folder"; then
            local duration=$(( $(date +%s) - start_time ))
            log_message "   ✅ OBJ export completed in $(format_duration $duration)"  
            return $duration
        else
            log_message "   ❌ Both USD and OBJ exports failed"
            return 1
        fi
    fi
}

# Attempt to export scene in USD format
attempt_usd_export() {
    local scene_id=$1
    local output_folder=$2
    local export_folder=$3
    
    python -m infinigen.tools.export \
        --input_folder "$output_folder" \
        --output_folder "$export_folder" \
        --format usdc \
        --resolution $TEXTURE_RESOLUTION \
        --omniverse \
        --overrides \
            export_curr_scene.glass_mats_enabled=False \
            export_curr_scene.transparency_enabled=False \
        > "${LOG_DIR}/export_usd_${scene_id}.log" 2>&1
    
    return $?
}

# Attempt to export scene in OBJ format (fallback)
attempt_obj_export() {
    local scene_id=$1
    local output_folder=$2
    local export_folder=$3
    
    python -m infinigen.tools.export \
        --input_folder "$output_folder" \
        --output_folder "$export_folder" \
        --format obj \
        --resolution $TEXTURE_RESOLUTION \
        > "${LOG_DIR}/export_obj_${scene_id}.log" 2>&1
    
    return $?
}

# Create documentation file for the generated scene
create_scene_documentation() {
    local scene_id=$1
    local seed=$2
    local export_folder=$3
    local gen_time=$4
    local export_time=$5
    local lighting_config=$6
    local solve_config=$7
    local floating_config=$8
    local error_config=$9
    
    local total_time=$((gen_time + export_time))
    local scene_size=$(du -sh "${OUTPUT_DIR}/kitchen_${scene_id}_seed_${seed}" 2>/dev/null | cut -f1 || echo "N/A")
    local export_size=$(du -sh "$export_folder" 2>/dev/null | cut -f1 || echo "N/A")
    
    cat > "$export_folder/kitchen_info.txt" << EOF
===============================================================================
Kitchen Scene Documentation
===============================================================================
Generated: $(date)
Scene ID: $scene_id
Random Seed: $seed
Texture Resolution: ${TEXTURE_RESOLUTION}x${TEXTURE_RESOLUTION}

Performance Metrics:
  Scene Generation Time: $(format_duration $gen_time)
  Export Processing Time: $(format_duration $export_time)
  Total Processing Time: $(format_duration $total_time)
  Scene Data Size: $scene_size
  Export Data Size: $export_size

Generation Configuration:
  Lighting Setup: $lighting_config
  Object Density: $solve_config
  Floating Objects: $floating_config
  Error Handling: $error_config

Single Room Features:
  ✓ Only kitchen room generated (no other room types)
  ✓ Room centered at world origin (0, 0, 0)
  ✓ All furniture and objects moved with room
  ✓ Unused rooms deleted from scene

File Structure:
  Blender Scene: $(realpath "${OUTPUT_DIR}/kitchen_${scene_id}_seed_${seed}/scene.blend")
  USD Export: $(realpath "$export_folder")/export_scene.blend/export_scene.usdc
  Physics Data: $(realpath "$export_folder")/export_scene.blend/solve_state.json
  Generation Logs: $(realpath "${LOG_DIR}")/generate_${scene_id}_seed_${seed}.log

Usage Instructions:
  1. Load in Blender: python -m infinigen.launch_blender [scene.blend path]
  2. Import USD: Use USD importer in your 3D software
  3. Physics simulation: Load solve_state.json for constraint data
===============================================================================
EOF
    
    log_message "   📋 Scene documentation created"
    log_message "   💾 Scene size: $scene_size, Export size: $export_size"
}

# =============================================================================
# BATCH PROCESSING AND REPORTING
# =============================================================================

# Process all kitchen scenes in batch
process_all_kitchens() {
    log_message ""
    log_message "🚀 Starting batch kitchen generation..."
    log_message "   Total scenes: $NUM_SCENES"
    log_message "   Starting seed: $START_SEED"
    
    local successful_scenes=0
    
    for scene_index in $(seq 0 $((NUM_SCENES - 1))); do
        # Select configuration based on scene index (cycling through options)
        local lighting_idx=0  # Use consistent lighting for now
        local solve_idx=0     # Use DENSE object density for more items
        local floating_idx=1  # Add some floating objects for realism
        local error_idx=0     # Use conservative error handling for full features
        
        local lighting_config="${LIGHTING_CONFIGS[$lighting_idx]}"
        local solve_config="${SOLVE_CONFIGS[$solve_idx]}"
        local floating_config="${FLOATING_CONFIGS[$floating_idx]}"
        local error_config="${ERROR_HANDLING_CONFIGS[$error_idx]}"
        
        local seed=$((START_SEED + scene_index))
        
        # Generate individual kitchen scene
        if generate_kitchen_scene "$scene_index" "$seed" "$lighting_config" "$solve_config" "$floating_config" "$error_config"; then
            ((successful_scenes++))
        fi
        
        # Progress update
        local progress=$((scene_index + 1))
        local percentage=$((progress * 100 / NUM_SCENES))
        log_message ""
        log_message "📊 Progress: $progress/$NUM_SCENES ($percentage%) - $successful_scenes successful"
    done
    
    # Generate final summary report
    create_batch_summary_report $successful_scenes
    
    log_message ""
    log_message "🏁 Batch processing completed!"
    log_message "   Success rate: $successful_scenes/$NUM_SCENES ($(( successful_scenes * 100 / NUM_SCENES ))%)"
}

# Create comprehensive summary report for the batch
create_batch_summary_report() {
    local successful_scenes=$1
    local summary_file="$EXPORT_DIR/kitchen_generation_summary.txt"
    
    log_message "📄 Creating batch summary report..."
    
    cat > "$summary_file" << EOF
===============================================================================
Kitchen Generation Batch Summary
===============================================================================
Completed: $(date)
Total Scenes Requested: $NUM_SCENES
Successfully Generated: $successful_scenes
Success Rate: $(( successful_scenes * 100 / NUM_SCENES ))%
Texture Resolution: ${TEXTURE_RESOLUTION}x${TEXTURE_RESOLUTION}

Individual Scene Results:
EOF

    # List results for each scene
    for scene_index in $(seq 0 $((NUM_SCENES - 1))); do
        local seed=$((START_SEED + scene_index))
        local scene_name="kitchen_${scene_index}_seed_${seed}"
        local usd_file="$EXPORT_DIR/$scene_name/export_scene.blend/export_scene.usdc"
        local obj_file="$EXPORT_DIR/$scene_name/export_scene.blend/"
        
        if [ -f "$usd_file" ]; then
            echo "  ✅ Kitchen $scene_index (seed: $seed) - USD export successful" >> "$summary_file"
        elif [ -d "$obj_file" ]; then
            echo "  ⚠️  Kitchen $scene_index (seed: $seed) - OBJ export (USD failed)" >> "$summary_file"
        else
            echo "  ❌ Kitchen $scene_index (seed: $seed) - Generation failed" >> "$summary_file"
        fi
    done
    
    cat >> "$summary_file" << EOF

Storage Information:
  Total Export Size: $(du -sh "$EXPORT_DIR" 2>/dev/null | cut -f1 || echo "N/A")
  Total Scene Size: $(du -sh "$OUTPUT_DIR" 2>/dev/null | cut -f1 || echo "N/A")
  Log Files Size: $(du -sh "$LOG_DIR" 2>/dev/null | cut -f1 || echo "N/A")

Directory Structure:
  Scene Data: $OUTPUT_DIR
  Exported Files: $EXPORT_DIR
  Log Files: $LOG_DIR
  Summary Report: $summary_file

Next Steps:
  1. Review failed scenes in log files if success rate < 100%
  2. Load successful scenes in Blender or USD-compatible software
  3. Use physics data (solve_state.json) for simulation setup
  4. Consider adjusting configuration for failed scenes and re-running

Generated with Infinigen Kitchen Generation Script
===============================================================================
EOF
    
    log_message "   📋 Summary report saved: $summary_file"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    echo "==============================================================================="
    echo "🏠 Infinigen Kitchen Scene Generator"
    echo "==============================================================================="
    echo ""
    echo "This script will generate $NUM_SCENES kitchen scenes with the following features:"
    echo "  • Single room mode (kitchens only, no other rooms)"
    echo "  • Rooms centered at world origin (0,0,0)"  
    echo "  • USD export with OBJ fallback"
    echo "  • Comprehensive logging and documentation"
    echo ""
    echo "Scene name: $SCENE_NAME"
    echo "Texture resolution: ${TEXTURE_RESOLUTION}x${TEXTURE_RESOLUTION}"
    echo "Starting seed: $START_SEED"
    echo ""
    
    # Setup environment and start processing
    setup_environment
    process_all_kitchens
    
    echo ""
    echo "==============================================================================="
    echo "� Kitchen Generation Complete!"
    echo "==============================================================================="
    echo "📊 Summary: $EXPORT_DIR/kitchen_generation_summary.txt"
    echo "📝 Detailed logs: $LOG_FILE"
    echo "📁 Scene files: $OUTPUT_DIR"
    echo "📦 Export files: $EXPORT_DIR"
    echo ""
    echo "To view a generated kitchen:"
    echo "  python -m infinigen.launch_blender $OUTPUT_DIR/kitchen_0_seed_0/scene.blend"
    echo "==============================================================================="
}

# Run the main function if this script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
