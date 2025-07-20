#!/bin/bash

# =============================================================================
# Infinigen Kitchen Scene Generation Script
# Generate kitchen rooms with customizable settings and export to USD format
# =============================================================================

# =============================================================================
# BASIC CONFIGURATION - Modify these settings as needed
# =============================================================================

# Number of kitchen scenes to generate
NUM_SCENES=5

# Scene identifier for output folders
SCENE_NAME="kitchen_0720"

# Texture resolution for exported models (higher = better quality, larger files)
TEXTURE_RESOLUTION=1024

# Random seed starting point (each scene uses consecutive seeds)
START_SEED=0

# =============================================================================
# LIGHTING SETTINGS - Controls scene illumination
# =============================================================================

# Lighting configuration options (script will cycle through these)
LIGHTING_CONFIGS=(
    # Bright daylight setup
    "compose_indoors.lights_off_chance=0.0 nishita_lighting.strength=0.4 nishita_lighting.sun_elevation=60 configure_render_cycles.exposure=2.5"
    
    # Moderate lighting with some lights off
    "compose_indoors.lights_off_chance=0.3 nishita_lighting.strength=0.35 nishita_lighting.sun_elevation=45 configure_render_cycles.exposure=3.0"
    
    # Evening/darker setup
    "compose_indoors.lights_off_chance=0.1 nishita_lighting.strength=0.3 nishita_lighting.sun_elevation=30 configure_render_cycles.exposure=3.5"
)

# =============================================================================
# OBJECT DENSITY SETTINGS - Controls how many objects are placed
# =============================================================================

SOLVE_CONFIGS=(
    # Dense object placement (more items, longer generation time)
    "compose_indoors.solve_steps_large=150 compose_indoors.solve_steps_medium=60 compose_indoors.solve_steps_small=10"
    
    # Moderate object placement (balanced)
    "compose_indoors.solve_steps_large=100 compose_indoors.solve_steps_medium=40 compose_indoors.solve_steps_small=5"
    
    # Sparse object placement (fewer items, faster generation)
    "compose_indoors.solve_steps_large=80 compose_indoors.solve_steps_medium=30 compose_indoors.solve_steps_small=3"
)

# =============================================================================
# ERROR HANDLING SETTINGS - Controls how to handle generation failures
# =============================================================================

ERROR_HANDLING_CONFIGS=(
    # Strict mode (fail on any constraint violation)
    "solve_objects.abort_unsatisfied=False compose_indoors.solve_medium_enabled=True compose_indoors.kitchen_island_enabled=True"
    
    # Relaxed mode (ignore most constraint violations, disable problematic items)
    "solve_objects.abort_unsatisfied=False compose_indoors.solve_medium_enabled=False compose_indoors.kitchen_island_enabled=False"
    
    # Minimal mode (only basic kitchen items)
    "solve_objects.abort_unsatisfied=False compose_indoors.solve_medium_enabled=False compose_indoors.kitchen_island_enabled=False compose_indoors.solve_small_enabled=False"
)

# =============================================================================
# FLOATING OBJECTS SETTINGS - Objects not placed on surfaces
# =============================================================================

FLOATING_CONFIGS=(
    # No floating objects
    "compose_indoors.floating_objs_enabled=False"
    
    # Few floating objects (15 items)
    "compose_indoors.floating_objs_enabled=True compose_indoors.num_floating=15"
    
    # Many floating objects (25 items)
    "compose_indoors.floating_objs_enabled=True compose_indoors.num_floating=25"
)

# =============================================================================
# SETUP DIRECTORIES AND LOGGING
# =============================================================================

OUTPUT_DIR="outputs/${SCENE_NAME}/dataset"
EXPORT_DIR="exports/${SCENE_NAME}/export"
LOG_DIR="logs/${SCENE_NAME}"
LOG_FILE="${LOG_DIR}/kitchen_generation.log"

# Create necessary directories
mkdir -p "$OUTPUT_DIR" "$EXPORT_DIR" "$LOG_DIR"

# Initialize log file
echo "Kitchen Scene Generation Started: $(date)" > "$LOG_FILE"
echo "Generating $NUM_SCENES kitchen scenes" >> "$LOG_FILE"
echo "=========================================" >> "$LOG_FILE"

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

# Function to log messages with timestamp
log_message() {
    echo "$(date '+%H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Function to check if previous command succeeded
check_success() {
    if [ $? -eq 0 ]; then
        log_message "✅ $1 completed successfully"
        return 0
    else
        log_message "❌ $1 failed"
        return 1
    fi
}

# =============================================================================
# KITCHEN GENERATION FUNCTION
# =============================================================================

generate_kitchen() {
    local scene_id=$1
    local seed=$2
    local lighting_config=$3
    local solve_config=$4
    local floating_config=$5
    local error_config=$6  # Add error handling config parameter
    
    local scene_name="kitchen_${scene_id}_seed_${seed}"
    local output_folder="$OUTPUT_DIR/$scene_name"
    local export_folder="$EXPORT_DIR/$scene_name"
    
    # Record start time for total timing
    local total_start_time=$(date +%s)
    
    log_message "Starting kitchen scene $scene_id (seed: $seed)"
    
    # Record generation start time
    local gen_start_time=$(date +%s)
    log_message "🔄 Starting scene generation..."
    
    # Generate kitchen scene using Infinigen
    python -m infinigen_examples.generate_indoors \
        --seed $seed \
        --task coarse \
        --output_folder "$output_folder" \
        -g fast_solve.gin overhead.gin \
        -p compose_indoors.terrain_enabled=False \
           compose_indoors.overhead_cam_enabled=True \
           restrict_solving.solve_max_rooms=1 \
           restrict_solving.restrict_parent_rooms=[\"Kitchen\"] \
           $error_config \
           $lighting_config \
           $solve_config \
           $floating_config \
        > "${LOG_DIR}/generate_${scene_name}.log" 2>&1
    
    # Calculate generation time
    local gen_end_time=$(date +%s)
    local gen_duration=$((gen_end_time - gen_start_time))
    local gen_minutes=$((gen_duration / 60))
    local gen_seconds=$((gen_duration % 60))
    
    if check_success "Kitchen $scene_id generation"; then
        log_message "⏱️  Scene generation completed in ${gen_minutes}m ${gen_seconds}s"
        
        # Record export start time
        local export_start_time=$(date +%s)
        log_message "🔄 Starting USD export..."
        
        # Export to USD format with error handling
        python -m infinigen.tools.export \
            --input_folder "$output_folder" \
            --output_folder "$export_folder" \
            -f usdc \
            -r $TEXTURE_RESOLUTION \
            --omniverse \
            -p export_curr_scene.glass_mats_enabled=False \
               export_curr_scene.transparency_enabled=False \
            > "${LOG_DIR}/export_${scene_name}.log" 2>&1
        
        # Calculate export time
        local export_end_time=$(date +%s)
        local export_duration=$((export_end_time - export_start_time))
        local export_minutes=$((export_duration / 60))
        local export_seconds=$((export_duration % 60))
        
        if check_success "Kitchen $scene_id USD export"; then
            log_message "⏱️  USD export completed in ${export_minutes}m ${export_seconds}s"
            
            # Calculate total time
            local total_end_time=$(date +%s)
            local total_duration=$((total_end_time - total_start_time))
            local total_minutes=$((total_duration / 60))
            local total_seconds=$((total_duration % 60))
            
            log_message "📊 TIMING SUMMARY for Kitchen $scene_id:"
            log_message "   - Generation Time: ${gen_minutes}m ${gen_seconds}s"
            log_message "   - Export Time: ${export_minutes}m ${export_seconds}s"
            log_message "   - Total Time: ${total_minutes}m ${total_seconds}s"
        else
            # Try alternative export method if first one fails
            log_message "🔄 Trying alternative export method..."
            local alt_export_start=$(date +%s)
            
            python -m infinigen.tools.export \
                --input_folder "$output_folder" \
                --output_folder "$export_folder" \
                -f obj \
                -r $TEXTURE_RESOLUTION \
                > "${LOG_DIR}/export_alt_${scene_name}.log" 2>&1
            
            local alt_export_end=$(date +%s)
            local alt_export_duration=$((alt_export_end - alt_export_start))
            local alt_export_minutes=$((alt_export_duration / 60))
            local alt_export_seconds=$((alt_export_duration % 60))
            
            if check_success "Kitchen $scene_id OBJ export"; then
                log_message "⏱️  Alternative OBJ export completed in ${alt_export_minutes}m ${alt_export_seconds}s"
                export_minutes=$alt_export_minutes
                export_seconds=$alt_export_seconds
                
                # Calculate total time
                local total_end_time=$(date +%s)
                local total_duration=$((total_end_time - total_start_time))
                local total_minutes=$((total_duration / 60))
                local total_seconds=$((total_duration % 60))
                
                log_message "📊 TIMING SUMMARY for Kitchen $scene_id (OBJ export):"
                log_message "   - Generation Time: ${gen_minutes}m ${gen_seconds}s"
                log_message "   - Export Time: ${export_minutes}m ${export_seconds}s"
                log_message "   - Total Time: ${total_minutes}m ${total_seconds}s"
            else
                # Both exports failed
                log_message "⏱️  Both USD and OBJ exports failed"
                local total_end_time=$(date +%s)
                local total_duration=$((total_end_time - total_start_time))
                local total_minutes=$((total_duration / 60))
                local total_seconds=$((total_duration % 60))
                log_message "📊 PARTIAL TIMING for Kitchen $scene_id (exports failed):"
                log_message "   - Generation Time: ${gen_minutes}m ${gen_seconds}s"
                log_message "   - Failed Export Attempts: ${export_minutes}m ${export_seconds}s + ${alt_export_minutes}m ${alt_export_seconds}s"
                log_message "   - Total Time: ${total_minutes}m ${total_seconds}s"
            fi
        fi
            cat > "$export_folder/kitchen_info.txt" << EOF
Kitchen Scene Information
========================
Scene ID: $scene_id
Random Seed: $seed
Generated: $(date)
Texture Resolution: ${TEXTURE_RESOLUTION}x${TEXTURE_RESOLUTION}

Timing Information:
- Generation Time: ${gen_minutes}m ${gen_seconds}s
- Export Time: ${export_minutes}m ${export_seconds}s
- Total Time: ${total_minutes}m ${total_seconds}s

Configuration:
- Lighting: $lighting_config
- Object Density: $solve_config
- Floating Objects: $floating_config

File Locations:
- Blender Scene: $output_folder/scene.blend
- USD Export: $export_folder/export_scene.blend/export_scene.usdc
- Physics Data: $export_folder/export_scene.blend/solve_state.json
EOF
            
            local scene_size=$(du -sh "$output_folder" 2>/dev/null | cut -f1 || echo "N/A")
            local export_size=$(du -sh "$export_folder" 2>/dev/null | cut -f1 || echo "N/A")
            log_message "Kitchen $scene_id complete - Scene: $scene_size, Export: $export_size"
        else
            # Export failed - still log generation time
            log_message "⏱️  USD export failed after ${export_minutes}m ${export_seconds}s"
            local total_end_time=$(date +%s)
            local total_duration=$((total_end_time - total_start_time))
            local total_minutes=$((total_duration / 60))
            local total_seconds=$((total_duration % 60))
            log_message "📊 PARTIAL TIMING for Kitchen $scene_id (export failed):"
            log_message "   - Generation Time: ${gen_minutes}m ${gen_seconds}s"
            log_message "   - Failed Export Time: ${export_minutes}m ${export_seconds}s"
            log_message "   - Total Time: ${total_minutes}m ${total_seconds}s"
        fi
    else
        # Generation failed - log what we can
        log_message "⏱️  Scene generation failed after ${gen_minutes}m ${gen_seconds}s"
        local total_end_time=$(date +%s)
        local total_duration=$((total_end_time - total_start_time))
        local total_minutes=$((total_duration / 60))
        local total_seconds=$((total_duration % 60))
        log_message "📊 FAILED TIMING for Kitchen $scene_id:"
        log_message "   - Failed Generation Time: ${gen_minutes}m ${gen_seconds}s"
        log_message "   - Total Time: ${total_minutes}m ${total_seconds}s"
    fi
    
    echo "----------------------------------------"
}

# =============================================================================
# MAIN GENERATION LOOP
# =============================================================================

log_message "Starting kitchen generation batch..."

for i in $(seq 0 $((NUM_SCENES-1))); do
    # Cycle through different configurations to create variety
    # lighting_idx=$((i % ${#LIGHTING_CONFIGS[@]}))
    # solve_idx=$((i % ${#SOLVE_CONFIGS[@]}))
    # floating_idx=$((i % ${#FLOATING_CONFIGS[@]}))

    lighting_idx=0
    solve_idx=1
    floating_idx=0
    error_idx=$((i % ${#ERROR_HANDLING_CONFIGS[@]}))  # Add error config cycling
    
    lighting_config="${LIGHTING_CONFIGS[$lighting_idx]}"
    solve_config="${SOLVE_CONFIGS[$solve_idx]}"
    floating_config="${FLOATING_CONFIGS[$floating_idx]}"
    error_config="${ERROR_HANDLING_CONFIGS[$error_idx]}"
    
    # Calculate seed for this scene
    seed=$((START_SEED + i))
    
    # Generate the kitchen scene
    generate_kitchen $i $seed "$lighting_config" "$solve_config" "$floating_config" "$error_config"
    
    # Show progress
    progress=$((i + 1))
    percentage=$((progress * 100 / NUM_SCENES))
    log_message "Progress: $progress/$NUM_SCENES ($percentage%)"
done

# =============================================================================
# GENERATE SUMMARY REPORT
# =============================================================================

log_message "Creating summary report..."

SUMMARY_FILE="$EXPORT_DIR/kitchen_summary.txt"
cat > "$SUMMARY_FILE" << EOF
Kitchen Generation Summary
=========================
Generated: $(date)
Total Scenes: $NUM_SCENES
Texture Resolution: ${TEXTURE_RESOLUTION}x${TEXTURE_RESOLUTION}

Generated Kitchens:
EOF

# Count successful generations
success_count=0
for i in $(seq 0 $((NUM_SCENES-1))); do
    scene_name="kitchen_${i}_seed_$((START_SEED + i))"
    usd_file="$EXPORT_DIR/$scene_name/export_scene.blend/export_scene.usdc"
    if [ -f "$usd_file" ]; then
        echo "✅ Kitchen $i (seed: $((START_SEED + i)))" >> "$SUMMARY_FILE"
        success_count=$((success_count + 1))
    else
        echo "❌ Kitchen $i - Generation failed" >> "$SUMMARY_FILE"
    fi
done

cat >> "$SUMMARY_FILE" << EOF

Results:
- Successfully generated: $success_count/$NUM_SCENES
- Success rate: $((success_count * 100 / NUM_SCENES))%
- Total export size: $(du -sh "$EXPORT_DIR" 2>/dev/null | cut -f1 || echo "N/A")

Usage:
- USD files are located in: $EXPORT_DIR/kitchen_X_seed_X/export_scene.blend/export_scene.usdc
- Physics data is located in: $EXPORT_DIR/kitchen_X_seed_X/export_scene.blend/solve_state.json
- Individual scene info: $EXPORT_DIR/kitchen_X_seed_X/kitchen_info.txt
EOF

# =============================================================================
# COMPLETION
# =============================================================================

log_message "========================================="
log_message "Kitchen generation completed!"
log_message "Successfully generated: $success_count/$NUM_SCENES kitchens"
log_message "Summary report: $SUMMARY_FILE"
log_message "Log file: $LOG_FILE"
log_message "========================================="

echo ""
echo "🏠 Kitchen Generation Complete!"
echo "📊 Summary: $SUMMARY_FILE"
echo "📝 Logs: $LOG_FILE"
echo "📁 Exports: $EXPORT_DIR"
echo ""
echo "To view a kitchen in Blender:"
echo "  python -m infinigen.launch_blender $OUTPUT_DIR/kitchen_0_seed_0/scene.blend"
