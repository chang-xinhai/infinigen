#!/bin/bash

# =============================================================================
# Infinigen Multi-Room Scene Generation and Export Script
# Generate 30 different Kitchen+Living+Dining room combinations and export to IsaacSim
# =============================================================================

# =============================================================================
# GLOBAL CONFIGURATION - Easy to modify settings
# =============================================================================

# Basic settings
NUM_SCENES=5
SCENE_DATE="scene_0623"
TEXTURE_RESOLUTION=2048

# Room combination presets - Choose one by uncommenting
ROOM_CONFIG="KITCHEN_ONLY"
# ROOM_CONFIG="LIVING_ONLY"
# ROOM_CONFIG="DINING_ONLY"
# ROOM_CONFIG="KITCHEN_LIVING"
# ROOM_CONFIG="KITCHEN_DINING"
# ROOM_CONFIG="LIVING_DINING"
# ROOM_CONFIG="ALL_COMBINATIONS"
# ROOM_CONFIG="CUSTOM"

# Custom room combinations (only used if ROOM_CONFIG="CUSTOM")
# Format: "Room1,Room2,Room3" - Available rooms: Kitchen, LivingRoom, DiningRoom, Bathroom, Bedroom
CUSTOM_ROOMS=(
    "Kitchen,LivingRoom,DiningRoom"
    "Bathroom,Bedroom"
)

# Advanced settings
OUTPUT_BASE="outputs/${SCENE_DATE}/dataset"
EXPORT_BASE="outputs/${SCENE_DATE}/exports"
LOG_BASE="logs/${SCENE_DATE}"
LOG_FILE="${LOG_BASE}/generate_rooms.log"

# Create necessary directories
mkdir -p "$OUTPUT_BASE"
mkdir -p "$EXPORT_BASE"
mkdir -p "$LOG_BASE"

# =============================================================================
# Room Configuration Setup
# =============================================================================

# Function to set room combinations based on ROOM_CONFIG
setup_room_combinations() {
    case $ROOM_CONFIG in
        "KITCHEN_ONLY")
            ROOM_COMBINATIONS=("Kitchen")
            echo "🏠 Room Config: Kitchen Only"
            ;;
        "LIVING_ONLY")
            ROOM_COMBINATIONS=("LivingRoom")
            echo "🏠 Room Config: Living Room Only"
            ;;
        "DINING_ONLY")
            ROOM_COMBINATIONS=("DiningRoom")
            echo "🏠 Room Config: Dining Room Only"
            ;;
        "KITCHEN_LIVING")
            ROOM_COMBINATIONS=("Kitchen,LivingRoom")
            echo "🏠 Room Config: Kitchen + Living Room"
            ;;
        "KITCHEN_DINING")
            ROOM_COMBINATIONS=("Kitchen,DiningRoom")
            echo "🏠 Room Config: Kitchen + Dining Room"
            ;;
        "LIVING_DINING")
            ROOM_COMBINATIONS=("LivingRoom,DiningRoom")
            echo "🏠 Room Config: Living Room + Dining Room"
            ;;
        "ALL_COMBINATIONS")
            ROOM_COMBINATIONS=(
                "Kitchen,LivingRoom,DiningRoom"
                "Kitchen,LivingRoom"
                "LivingRoom,DiningRoom" 
                "Kitchen,DiningRoom"
                "Kitchen"
                "LivingRoom"
                "DiningRoom"
            )
            echo "🏠 Room Config: All Combinations (7 variants)"
            ;;
        "CUSTOM")
            ROOM_COMBINATIONS=("${CUSTOM_ROOMS[@]}")
            echo "🏠 Room Config: Custom (${#CUSTOM_ROOMS[@]} variants)"
            ;;
        *)
            echo "❌ Error: Unknown ROOM_CONFIG: $ROOM_CONFIG"
            echo "Available options: KITCHEN_ONLY, LIVING_ONLY, DINING_ONLY, KITCHEN_LIVING, KITCHEN_DINING, LIVING_DINING, ALL_COMBINATIONS, CUSTOM"
            exit 1
            ;;
    esac
    
    echo "📋 Configured ${#ROOM_COMBINATIONS[@]} room combination(s):"
    for i in "${!ROOM_COMBINATIONS[@]}"; do
        echo "   $((i+1)). ${ROOM_COMBINATIONS[i]}"
    done
    echo ""
}

# Setup room combinations
setup_room_combinations

# Initialize log file
echo "===============================================" > "$LOG_FILE"
echo "Infinigen Multi-Room Scene Generation Started" >> "$LOG_FILE"
echo "Start time: $(date)" >> "$LOG_FILE"
echo "Room Configuration: $ROOM_CONFIG" >> "$LOG_FILE"
echo "Number of scenes: $NUM_SCENES" >> "$LOG_FILE"
echo "Number of room combinations: ${#ROOM_COMBINATIONS[@]}" >> "$LOG_FILE"
echo "Texture resolution: $TEXTURE_RESOLUTION" >> "$LOG_FILE"
echo "===============================================" >> "$LOG_FILE"

# Define room type combinations
# NOTE: This is now set by the setup_room_combinations() function above
# declare -a ROOM_COMBINATIONS=(
#     "Kitchen,LivingRoom,DiningRoom"
#     "Kitchen,LivingRoom"
#     "LivingRoom,DiningRoom" 
#     "Kitchen,DiningRoom"
# )

# Define different configuration options to create variation
declare -a LIGHTING_CONFIGS=(
    "compose_indoors.lights_off_chance=0.0 nishita_lighting.strength=0.35 nishita_lighting.sun_elevation=50 configure_render_cycles.exposure=2.5"
    "compose_indoors.lights_off_chance=0.2 nishita_lighting.strength=0.4 nishita_lighting.sun_elevation=40 configure_render_cycles.exposure=3.0"
    "compose_indoors.lights_off_chance=0.4 nishita_lighting.strength=0.45 nishita_lighting.sun_elevation=60 configure_render_cycles.exposure=3.5"
    "compose_indoors.lights_off_chance=0.1 nishita_lighting.strength=0.3 nishita_lighting.sun_elevation=35 configure_render_cycles.exposure=2.8"
    "compose_indoors.lights_off_chance=0.3 nishita_lighting.strength=0.5 nishita_lighting.sun_elevation=55 configure_render_cycles.exposure=3.2"
)

declare -a SOLVE_STEPS_CONFIGS=(
    "compose_indoors.solve_steps_large=100 compose_indoors.solve_steps_medium=40 compose_indoors.solve_steps_small=5"
    "compose_indoors.solve_steps_large=150 compose_indoors.solve_steps_medium=60 compose_indoors.solve_steps_small=10"
    "compose_indoors.solve_steps_large=80 compose_indoors.solve_steps_medium=30 compose_indoors.solve_steps_small=3"
)

declare -a FLOATING_CONFIGS=(
    "compose_indoors.floating_objs_enabled=False"
    "compose_indoors.floating_objs_enabled=True compose_indoors.num_floating=15"
    "compose_indoors.floating_objs_enabled=True compose_indoors.num_floating=25"
)

# Function: log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Function: check command execution result
check_result() {
    if [ $? -eq 0 ]; then
        log_message "✅ $1 completed successfully"
        return 0
    else
        log_message "❌ $1 failed"
        return 1
    fi
}

# Function: generate single scene
generate_scene() {
    local scene_id=$1
    local seed=$2
    local room_combo=$3
    local lighting_config=$4
    local solve_config=$5
    local floating_config=$6
    
    local scene_name="scene_${scene_id}_seed_${seed}"
    local output_folder="$OUTPUT_BASE/$scene_name"
    local export_folder="$EXPORT_BASE/$scene_name"
    
    log_message "Starting scene generation $scene_id (seed: $seed)"
    log_message "Room combination: $room_combo"
    log_message "Output folder: $output_folder"
    
    # Build room restriction parameters
    local room_restriction=""
    # Always apply room restriction for single rooms and combinations
    IFS=',' read -ra ROOMS <<< "$room_combo"
    room_list=""
    for room in "${ROOMS[@]}"; do
        if [ -z "$room_list" ]; then
            room_list="\"$room\""
        else
            room_list="$room_list,\"$room\""
        fi
    done
    room_restriction="restrict_solving.restrict_parent_rooms=[$room_list]"
    
    # Generate scene
    log_message "Generating scene file..."
    python -m infinigen_examples.generate_indoors \
        --seed $seed \
        --task coarse \
        --output_folder "$output_folder" \
        -g fast_solve.gin overhead.gin \
        -p compose_indoors.terrain_enabled=False \
           compose_indoors.overhead_cam_enabled=True \
           restrict_solving.solve_max_rooms=3 \
           $room_restriction \
           $lighting_config \
           $solve_config \
           $floating_config \
        > "${LOG_BASE}/generate_${scene_name}.log" 2>&1
    
    if check_result "Scene $scene_id generation"; then
        # Export USD file
        log_message "Exporting scene $scene_id to USD format..."
        python -m infinigen.tools.export \
            --input_folder "$output_folder" \
            --output_folder "$export_folder" \
            -f usdc \
            -r $TEXTURE_RESOLUTION \
            --omniverse \
            > "${LOG_BASE}/export_${scene_name}.log" 2>&1
        
        if check_result "Scene $scene_id USD export"; then
            # Record scene information
            local info_file="$export_folder/scene_info.txt"
            cat > "$info_file" << EOF
Scene Information
=================
Scene ID: $scene_id
Random seed: $seed
Generation time: $(date)
Room combination: $room_combo
Texture resolution: ${TEXTURE_RESOLUTION}x${TEXTURE_RESOLUTION}
Lighting config: $lighting_config
Solver config: $solve_config
Floating objects config: $floating_config

File paths:
- Scene file: $output_folder
- Export file: $export_folder
- USD file: $export_folder/export_scene.blend/export_scene.usdc
- Physics config: $export_folder/export_scene.blend/solve_state.json

IsaacSim import command:
python isaac_sim.py --scene-path $export_folder/export_scene.blend/export_scene.usdc --json-path $export_folder/export_scene.blend/solve_state.json
EOF
            
            # Calculate file sizes
            local scene_size=$(du -sh "$output_folder" | cut -f1)
            local export_size=$(du -sh "$export_folder" | cut -f1)
            
            log_message "Scene $scene_id completed - Scene size: $scene_size, Export size: $export_size"
            
            # Optional: delete intermediate files to save space (uncomment to enable)
            # rm -rf "$output_folder"
            # log_message "Deleted intermediate files for scene $scene_id to save space"
            
        else
            log_message "Scene $scene_id export failed, keeping original files"
        fi
    else
        log_message "Scene $scene_id generation failed"
    fi
    
    echo "----------------------------------------"
}

# Main generation loop
log_message "Starting batch scene generation..."

for i in $(seq 0 $((NUM_SCENES-1))); do
    # Use different configuration combinations to create variation
    room_combo_idx=$((i % ${#ROOM_COMBINATIONS[@]}))
    lighting_idx=$((i % ${#LIGHTING_CONFIGS[@]}))
    solve_idx=$((i % ${#SOLVE_STEPS_CONFIGS[@]}))
    floating_idx=$((i % ${#FLOATING_CONFIGS[@]}))
    
    room_combo="${ROOM_COMBINATIONS[$room_combo_idx]}"
    lighting_config="${LIGHTING_CONFIGS[$lighting_idx]}"
    solve_config="${SOLVE_STEPS_CONFIGS[$solve_idx]}"
    floating_config="${FLOATING_CONFIGS[$floating_idx]}"
    
    # Use scene ID as seed to ensure reproducibility
    seed=$i
    
    generate_scene $i $seed "$room_combo" "$lighting_config" "$solve_config" "$floating_config"
    
    # Show progress
    progress=$((i + 1))
    percentage=$((progress * 100 / NUM_SCENES))
    log_message "Progress: $progress/$NUM_SCENES ($percentage%)"
done

# Generate summary report
log_message "Generating summary report..."

SUMMARY_FILE="$EXPORT_BASE/generation_summary.txt"
cat > "$SUMMARY_FILE" << EOF
Infinigen Multi-Room Scene Generation Summary Report
===================================================

Generation time: $(date)
Room Configuration: $ROOM_CONFIG
Total scenes: $NUM_SCENES
Room combinations used: ${#ROOM_COMBINATIONS[@]}
Texture resolution: ${TEXTURE_RESOLUTION}x${TEXTURE_RESOLUTION}

Successfully generated scenes:
EOF

# Count successfully generated scenes
success_count=0
for i in $(seq 0 $((NUM_SCENES-1))); do
    scene_name="scene_${i}_seed_${i}"
    usd_file="$EXPORT_BASE/$scene_name/export_scene.blend/export_scene.usdc"
    if [ -f "$usd_file" ]; then
        echo "✅ Scene $i (seed: $i) - $scene_name" >> "$SUMMARY_FILE"
        success_count=$((success_count + 1))
    else
        echo "❌ Scene $i (seed: $i) - Generation failed" >> "$SUMMARY_FILE"
    fi
done

cat >> "$SUMMARY_FILE" << EOF

Statistics:
- Successfully generated: $success_count/$NUM_SCENES
- Success rate: $((success_count * 100 / NUM_SCENES))%
- Total export size: $(du -sh "$EXPORT_BASE" | cut -f1)

Usage instructions:
1. Each scene's USD file is located at: $EXPORT_BASE/scene_X_seed_X/export_scene.blend/export_scene.usdc
2. Physics properties file is located at: $EXPORT_BASE/scene_X_seed_X/export_scene.blend/solve_state.json
3. For detailed scene information, check scene_info.txt in each scene folder

IsaacSim batch import script example:
for i in \$(seq 0 $((success_count-1))); do
    python isaac_sim.py \\
        --scene-path $EXPORT_BASE/scene_\${i}_seed_\${i}/export_scene.blend/export_scene.usdc \\
        --json-path $EXPORT_BASE/scene_\${i}_seed_\${i}/export_scene.blend/solve_state.json
done
EOF

# Create IsaacSim import script
ISAAC_SCRIPT="$EXPORT_BASE/load_scenes_in_isaac.sh"
cat > "$ISAAC_SCRIPT" << 'EOF'
#!/bin/bash
# IsaacSim scene import script
# Usage: ./load_scenes_in_isaac.sh [scene_number]

EXPORT_BASE="outputs/scene_0623/exports"

if [ -z "$1" ]; then
    echo "Usage: $0 <scene_number>"
    echo "Example: $0 5  # Load scene 5"
    echo "Or: $0 all  # Load all scenes sequentially"
    exit 1
fi

if [ "$1" = "all" ]; then
    for i in $(seq 0 29); do
        scene_name="scene_${i}_seed_${i}"
        usd_file="$EXPORT_BASE/$scene_name/export_scene.blend/export_scene.usdc"
        json_file="$EXPORT_BASE/$scene_name/export_scene.blend/solve_state.json"
        
        if [ -f "$usd_file" ]; then
            echo "Loading scene $i..."
            python isaac_sim.py --scene-path "$usd_file" --json-path "$json_file"
        else
            echo "Scene $i does not exist, skipping"
        fi
    done
else
    scene_name="scene_${1}_seed_${1}"
    usd_file="$EXPORT_BASE/$scene_name/export_scene.blend/export_scene.usdc"
    json_file="$EXPORT_BASE/$scene_name/export_scene.blend/solve_state.json"
    
    if [ -f "$usd_file" ]; then
        echo "Loading scene $1..."
        python isaac_sim.py --scene-path "$usd_file" --json-path "$json_file"
    else
        echo "Error: Scene $1 does not exist"
        exit 1
    fi
fi
EOF

chmod +x "$ISAAC_SCRIPT"

# Complete
end_time=$(date)
log_message "==============================================="
log_message "All scene generation completed!"
log_message "Completion time: $end_time"
log_message "Successfully generated: $success_count/$NUM_SCENES scenes"
log_message "Summary report: $SUMMARY_FILE"
log_message "IsaacSim import script: $ISAAC_SCRIPT"
log_message "==============================================="

echo ""
echo "🎉 Batch generation completed!"
echo "📊 Summary report: $SUMMARY_FILE"
echo "🚀 IsaacSim import: $ISAAC_SCRIPT"
echo "📝 Detailed log: $LOG_FILE"
echo ""
echo "Usage examples:"
echo "  View summary: cat $SUMMARY_FILE"
echo "  Load single scene: $ISAAC_SCRIPT 5"
echo "  Load all scenes: $ISAAC_SCRIPT all"
