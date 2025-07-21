#!/bin/bash

# =============================================================================
# Simple Infinigen Kitchen Scene Generation Script
# 
# This script generates kitchen scenes using kitchen_only.gin configuration
# Features:
# - Simple logging with timestamps
# - Scene generation using working kitchen_only.gin
# - USD export with OBJ fallback
# - Clean file structure
# =============================================================================

set -e  # Exit on any error

# =============================================================================
# CONFIGURATION
# =============================================================================

# Basic settings
readonly NUM_SCENES=5
readonly SCENE_NAME="kitchen_0721"
readonly TEXTURE_RESOLUTION=1024
readonly START_SEED=0

# Directory structure
readonly BASE_DIR="outputs"
readonly OUTPUT_DIR="${BASE_DIR}/${SCENE_NAME}"
readonly LOG_DIR="${OUTPUT_DIR}/logs"
readonly EXPORT_DIR="${OUTPUT_DIR}/exports"
readonly SCENES_DIR="${OUTPUT_DIR}/scenes"

# =============================================================================
# LOGGING UTILITIES
# =============================================================================

# Initialize logging
setup_logging() {
    mkdir -p "$LOG_DIR" "$EXPORT_DIR" "$SCENES_DIR"
    
    local main_log="$LOG_DIR/kitchen_generation.log"
    
    cat > "$main_log" << EOF
===============================================================================
Kitchen Generation Started: $(date)
===============================================================================
Number of scenes: $NUM_SCENES
Starting seed: $START_SEED
Output directory: $OUTPUT_DIR
Using kitchen_only.gin configuration
===============================================================================

EOF
    
    echo "📁 Created directories:"
    echo "   Scenes: $SCENES_DIR" 
    echo "   Exports: $EXPORT_DIR"
    echo "   Logs: $LOG_DIR"
    echo ""
}

# Log message with timestamp
log_msg() {
    local message="[$(date '+%H:%M:%S')] $1"
    echo "$message"
    echo "$message" >> "$LOG_DIR/kitchen_generation.log"
}

# =============================================================================
# SCENE GENERATION
# =============================================================================

# Generate a single kitchen scene
generate_kitchen() {
    local scene_id=$1
    local seed=$2
    
    local scene_name="${SCENE_PREFIX}_${scene_id}_seed_${seed}"
    local scene_output="$SCENES_DIR/$scene_name"
    local export_output="$EXPORT_DIR/$scene_name"
    
    log_msg "🏠 Starting $scene_name"
    
    # Generate scene
    log_msg "   🔄 Generating scene..."
    if python -m infinigen_examples.generate_indoors \
        --seed "$seed" \
        --task coarse \
        --output_folder "$scene_output" \
        --configs kitchen_only.gin \
        > "$LOG_DIR/generate_${scene_name}.log" 2>&1; then
        
        log_msg "   ✅ Scene generated successfully"
        
        # Export scene
        log_msg "   🔄 Exporting scene..."
        if export_scene "$scene_name" "$scene_output" "$export_output"; then
            log_msg "   🎉 $scene_name completed successfully"
            return 0
        else
            log_msg "   ❌ Export failed for $scene_name"
            return 1
        fi
    else
        log_msg "   ❌ Scene generation failed for $scene_name"
        log_msg "   📄 Check log: $LOG_DIR/generate_${scene_name}.log"
        return 1
    fi
}

# Export scene to USD with OBJ fallback
export_scene() {
    local scene_name=$1
    local scene_folder=$2
    local export_folder=$3
    
    # Try USD export first
    if python -m infinigen.tools.export \
        --input_folder "$scene_folder" \
        --output_folder "$export_folder" \
        --format usdc \
        --resolution $TEXTURE_RESOLUTION \
        > "$LOG_DIR/export_usd_${scene_name}.log" 2>&1; then
        
        log_msg "   💎 USD export completed"
        return 0
    else
        log_msg "   ⚠️  USD export failed, trying OBJ..."
        
        # Fallback to OBJ
        if python -m infinigen.tools.export \
            --input_folder "$scene_folder" \
            --output_folder "$export_folder" \
            --format obj \
            --resolution $TEXTURE_RESOLUTION \
            > "$LOG_DIR/export_obj_${scene_name}.log" 2>&1; then
            
            log_msg "   📦 OBJ export completed"
            return 0
        else
            log_msg "   💥 Both USD and OBJ exports failed"
            return 1
        fi
    fi
}

# =============================================================================
# BATCH PROCESSING
# =============================================================================

# Generate all kitchen scenes
generate_all_kitchens() {
    local successful=0
    local failed=0
    
    log_msg "🚀 Starting batch generation of $NUM_SCENES kitchens"
    log_msg ""
    
    for i in $(seq 0 $((NUM_SCENES - 1))); do
        local seed=$((START_SEED + i))
        
        if generate_kitchen "$i" "$seed"; then
            ((successful++))
        else
            ((failed++))
        fi
        
        log_msg ""
        log_msg "📊 Progress: $((i + 1))/$NUM_SCENES (Success: $successful, Failed: $failed)"
        log_msg ""
    done
    
    # Create summary
    create_summary $successful $failed
}

# Create summary report
create_summary() {
    local successful=$1
    local failed=$2
    local total=$((successful + failed))
    
    local summary_file="$OUTPUT_DIR/SUMMARY.txt"
    
    cat > "$summary_file" << EOF
===============================================================================
Kitchen Generation Summary
===============================================================================
Completed: $(date)
Total scenes: $total
Successful: $successful
Failed: $failed
Success rate: $(( successful * 100 / total ))%

Directory Structure:
├── scenes/          # Generated Blender scenes
├── exports/         # USD/OBJ exports  
├── logs/           # Generation and export logs
└── SUMMARY.txt     # This summary

Generated Scenes:
EOF

    for i in $(seq 0 $((NUM_SCENES - 1))); do
        local seed=$((START_SEED + i))
        local scene_name="${SCENE_PREFIX}_${i}_seed_${seed}"
        local scene_file="$SCENES_DIR/$scene_name/scene.blend"
        local export_dir="$EXPORT_DIR/$scene_name"
        
        if [ -f "$scene_file" ]; then
            if [ -d "$export_dir" ] && [ "$(ls -A "$export_dir" 2>/dev/null)" ]; then
                echo "✅ $scene_name - Scene + Export OK" >> "$summary_file"
            else
                echo "⚠️  $scene_name - Scene OK, Export Failed" >> "$summary_file"
            fi
        else
            echo "❌ $scene_name - Generation Failed" >> "$summary_file"
        fi
    done
    
    cat >> "$summary_file" << EOF

Usage:
To view a scene: python -m infinigen.launch_blender $SCENES_DIR/kitchen_0_seed_0/scene.blend
To find exports: ls $EXPORT_DIR/
To check logs: ls $LOG_DIR/

Generated with Simple Kitchen Generator
===============================================================================
EOF
    
    log_msg "📋 Summary created: $summary_file"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    echo "==============================================================================="
    echo "🏠 Simple Kitchen Generator"
    echo "==============================================================================="
    echo "Generating $NUM_SCENES kitchen scenes using kitchen_only.gin"
    echo "Starting seed: $START_SEED"
    echo "Output directory: $OUTPUT_DIR"
    echo ""
    
    # Setup and run
    setup_logging
    generate_all_kitchens
    
    echo ""
    echo "==============================================================================="
    echo "🎉 Generation Complete!"
    echo "==============================================================================="
    echo "� Results: $OUTPUT_DIR"
    echo "� Summary: $OUTPUT_DIR/SUMMARY.txt"
    echo "� Logs: $LOG_DIR/"
    echo ""
    echo "To view first scene:"
    echo "python -m infinigen.launch_blender $SCENES_DIR/${SCENE_PREFIX}_0_seed_${START_SEED}/scene.blend"
    echo "==============================================================================="
}

# Run main function
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
