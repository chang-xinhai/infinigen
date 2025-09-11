#!/bin/bash

# =============================================================================
# Kitchen Scene Generation Pipeline
# 
# This script generates kitchen scenes with a clean 3-stage pipeline:
# 1. Scene Generation  -> scene_X_seedY/scene/
# 2. USD Export        -> scene_X_seedY/export/  
# 3. Object Extraction -> scene_X_seedY/info/
#
# Features:
# - Clean modular pipeline design
# - Direct output to final structure (no temp directories)
# - Standalone pipeline functions
# - Robust error handling and logging
# - Continues processing even when individual scenes fail
# =============================================================================

# Note: Removed 'set -e' to allow pipeline to continue when individual scenes fail

# =============================================================================
# CONFIGURATION
# =============================================================================

# Scene settings
readonly NUM_SCENES=5
readonly SCENE_NAME="kitchen_0911_9_test_smaller_steps"
readonly START_SEED=0

# Output structure
readonly BASE_DIR="output/kitchen_test"
readonly OUTPUT_DIR="${BASE_DIR}/${SCENE_NAME}"
readonly LOG_DIR="${OUTPUT_DIR}/logs"

# Export settings
readonly TEXTURE_RESOLUTION=1024

# =============================================================================
# UTILITIES
# =============================================================================

log() {
    echo "[$(date '+%H:%M:%S')] $1"
    echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_DIR/pipeline.log"
}

setup_workspace() {
    mkdir -p "$LOG_DIR"
    
    cat > "$LOG_DIR/pipeline.log" << EOF
===============================================================================
Kitchen Generation Pipeline Started: $(date)
===============================================================================
Scenes: $NUM_SCENES
Seeds: $START_SEED to $((START_SEED + NUM_SCENES - 1))
Output: $OUTPUT_DIR
Structure: scene_X_seedY/{scene,export,info}
===============================================================================

EOF
    
    log "� Pipeline initialized"
    log "📁 Output directory: $OUTPUT_DIR"
}

get_scene_dir() {
    local scene_id=$1
    local seed=$2
    echo "$OUTPUT_DIR/scene_${scene_id}_seed_${seed}"
}

# =============================================================================
# PIPELINE STAGE 1: SCENE GENERATION
# =============================================================================

generate_scene() {
    local scene_id=$1
    local seed=$2
    
    local scene_dir=$(get_scene_dir $scene_id $seed)
    local scene_output="$scene_dir/scene"
    
    log "🏠 [Stage 1] Generating scene_${scene_id}_seed_${seed}"
    log " Logging to $LOG_DIR/generate_scene_${scene_id}_seed_${seed}.log"

    # Create scene directory
    mkdir -p "$scene_output"
    
    # Generate scene directly to final location (ignore exit code)
    python -m infinigen_examples.generate_indoors \
        --seed "$seed" \
        --task coarse \
        --time_record \
        --output_folder "$scene_output" \
        --configs kitchen_only.gin \
        > "$LOG_DIR/generate_scene_${scene_id}_seed_${seed}.log" 2>&1
    
    # Verify generation by checking output file
    if [[ -f "$scene_output/scene.blend" && -s "$scene_output/scene.blend" ]]; then
        log "✅ [Stage 1] Scene generated successfully - scene.blend file created"
        return 0
    else
        log "❌ [Stage 1] Scene generation failed - scene.blend file missing or empty"
        return 1
    fi
}

# =============================================================================
# PIPELINE STAGE 2: USD EXPORT
# =============================================================================

export_scene() {
    local scene_id=$1
    local seed=$2
    
    local scene_dir=$(get_scene_dir $scene_id $seed)
    local scene_input="$scene_dir/scene"
    local export_output="$scene_dir/export"
    
    log "💎 [Stage 2] Exporting scene_${scene_id}_seed_${seed} to USD"
    log " Logging to $LOG_DIR/export_scene_${scene_id}_seed_${seed}.log"
    
    # Create export directory
    mkdir -p "$export_output"
    
    # Export to USD (ignore exit code)
    python -m infinigen.tools.export \
        --input_folder "$scene_input" \
        --output_folder "$export_output" \
        --format usdc \
        --resolution $TEXTURE_RESOLUTION \
        > "$LOG_DIR/export_scene_${scene_id}_seed_${seed}.log" 2>&1
    
    # Verify export by checking for USD files
    if find "$export_output" -name "*.usdc" -type f -size +0 | grep -q .; then
        local usd_count=$(find "$export_output" -name "*.usdc" -type f -size +0 | wc -l)
        log "✅ [Stage 2] USD export completed - found $usd_count USD file(s)"
        return 0
    else
        log "❌ [Stage 2] USD export failed - no valid .usdc files found"
        return 1
    fi
}

# =============================================================================
# PIPELINE STAGE 3: OBJECT EXTRACTION
# =============================================================================

extract_objects() {
    local scene_id=$1
    local seed=$2
    
    local scene_dir=$(get_scene_dir $scene_id $seed)
    local blend_file="$scene_dir/scene/scene.blend"
    local info_dir="$scene_dir/info"
    local metadata_file="$info_dir/metadata.json"
    
    log "🔍 [Stage 3] Extracting objects from scene_${scene_id}_seed_${seed}"
    log " Logging to $LOG_DIR/extract_scene_${scene_id}_seed_${seed}.log"

    # Create info directory
    mkdir -p "$info_dir"
    
    # Extract objects using the Python script (ignore exit code)
    python "scripts/automoma/extract_object_info.py" \
        --blend_file "$blend_file" \
        --output "$metadata_file" \
        > "$LOG_DIR/extract_scene_${scene_id}_seed_${seed}.log" 2>&1

    # Verify extraction by checking metadata file
    if [[ -f "$metadata_file" && -s "$metadata_file" ]]; then
        # Additional check: verify it's valid JSON
        if python -m json.tool "$metadata_file" > /dev/null 2>&1; then
            log "✅ [Stage 3] Object extraction completed - valid metadata.json created"
            return 0
        else
            log "❌ [Stage 3] Object extraction failed - metadata.json exists but is not valid JSON"
            return 1
        fi
    else
        log "❌ [Stage 3] Object extraction failed - metadata.json file missing or empty"
        return 1
    fi
}

# =============================================================================
# PIPELINE ORCHESTRATION
# =============================================================================

process_scene() {
    local scene_id=$1
    local seed=$2
    
    log ""
    log "🎬 Processing scene_${scene_id}_seed_${seed}"
    log "----------------------------------------"
    
    # Wrap each stage in error handling to ensure pipeline continues
    local stage1_success=false
    local stage2_success=false
    local stage3_success=false
    
    # Stage 1: Generate scene
    if generate_scene $scene_id $seed; then
        stage1_success=true
    else
        log "❌ Stage 1 (Generation) failed for scene_${scene_id}_seed_${seed}"
    fi
    
    # Stage 2: Export scene (only if stage 1 succeeded)
    if $stage1_success; then
        if export_scene $scene_id $seed; then
            stage2_success=true
        else
            log "❌ Stage 2 (Export) failed for scene_${scene_id}_seed_${seed}"
        fi
    else
        log "⏭️  Skipping Stage 2 (Export) - Stage 1 failed"
    fi
    
    # Stage 3: Extract objects (only if stage 1 succeeded)
    if $stage1_success; then
        if extract_objects $scene_id $seed; then
            stage3_success=true
        else
            log "❌ Stage 3 (Extraction) failed for scene_${scene_id}_seed_${seed}"
        fi
    else
        log "⏭️  Skipping Stage 3 (Extraction) - Stage 1 failed"
    fi
    
    # Report final status
    if $stage1_success && $stage2_success && $stage3_success; then
        log "🎉 All stages completed successfully for scene_${scene_id}_seed_${seed}"
        return 0
    else
        log "⚠️  Pipeline completed with some failures for scene_${scene_id}_seed_${seed}"
        log "   Stage 1 (Generation): $([ "$stage1_success" = true ] && echo "✅" || echo "❌")"
        log "   Stage 2 (Export): $([ "$stage2_success" = true ] && echo "✅" || echo "❌")"
        log "   Stage 3 (Extraction): $([ "$stage3_success" = true ] && echo "✅" || echo "❌")"
        return 1
    fi
}

run_pipeline() {
    local successful=0
    local failed=0
    
    log "🚀 Starting kitchen generation pipeline"
    log "Processing $NUM_SCENES scenes..."
    
    for i in $(seq 0 $((NUM_SCENES - 1))); do
        local seed=$((START_SEED + i))
        
        # Process scene with error isolation - continue even if one fails
        if process_scene $i $seed; then
            ((successful++))
            log "✅ Scene $((i + 1))/$NUM_SCENES completed successfully"
        else
            ((failed++))
            log "❌ Scene $((i + 1))/$NUM_SCENES failed - continuing with next scene"
        fi
        
        log ""
        log "📊 Progress: $((i + 1))/$NUM_SCENES | Success: $successful | Failed: $failed"
        
        # Add a small delay to avoid overwhelming the system
        sleep 1
    done
    
    log ""
    log "🏁 Pipeline finished processing all $NUM_SCENES scenes"
    log "Final results: $successful successful, $failed failed"
    
    # Generate summary
    create_summary $successful $failed
}

# =============================================================================
# SUMMARY GENERATION
# =============================================================================

create_summary() {
    local successful=$1
    local failed=$2
    local total=$((successful + failed))
    
    local summary_file="$OUTPUT_DIR/SUMMARY.txt"
    
    cat > "$summary_file" << EOF
===============================================================================
Kitchen Generation Pipeline Summary
===============================================================================
Date: $(date)
Total scenes: $total
Successful: $successful
Failed: $failed
Success rate: $(( successful * 100 / total ))%

Output Structure:
$OUTPUT_DIR/
├── scene_0_seed_${START_SEED}/
│   ├── scene/           # Blender files
│   ├── export/          # USD files  
│   └── info/            # Object metadata JSON
├── scene_1_seed_$((START_SEED + 1))/
│   └── ...
└── logs/               # Pipeline logs

Scene Status:
EOF

    for i in $(seq 0 $((NUM_SCENES - 1))); do
        local seed=$((START_SEED + i))
        local scene_dir=$(get_scene_dir $i $seed)
        local scene_name="scene_${i}_seed_${seed}"
        
        local scene_ok="❌"
        local export_ok="❌"
        local info_ok="❌"
        
        [[ -f "$scene_dir/scene/scene.blend" ]] && scene_ok="✅"
        [[ -n "$(find "$scene_dir/export" -name "*.usdc" 2>/dev/null)" ]] && export_ok="✅"
        [[ -f "$scene_dir/info/metadata.json" ]] && info_ok="✅"
        
        echo "$scene_name: Scene $scene_ok | Export $export_ok | Info $info_ok" >> "$summary_file"
    done
    
    cat >> "$summary_file" << EOF

Quick Start:
# View first scene
python -m infinigen.launch_blender $OUTPUT_DIR/scene_0_seed_${START_SEED}/scene/scene.blend

# Check object metadata  
cat $OUTPUT_DIR/scene_0_seed_${START_SEED}/info/metadata.json

# Browse exports
ls $OUTPUT_DIR/scene_0_seed_${START_SEED}/export/

Generated by Kitchen Pipeline v2.0
===============================================================================
EOF
    
    log "📋 Summary created: $summary_file"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    echo "==============================================================================="
    echo "🏠 Kitchen Generation Pipeline"
    echo "==============================================================================="
    echo "Scenes: $NUM_SCENES"
    echo "Seeds: $START_SEED to $((START_SEED + NUM_SCENES - 1))"
    echo "Output: $OUTPUT_DIR"
    echo ""
    echo "Pipeline: Generation → Export → Extraction"
    echo "Structure: scene_X_seedY/{scene,export,info}"
    echo "==============================================================================="
    echo ""
    
    # Initialize and run
    setup_workspace
    run_pipeline
    
    echo ""
    echo "==============================================================================="
    echo "🎉 Pipeline Complete!"
    echo "==============================================================================="
    echo "📁 Results: $OUTPUT_DIR"
    echo "📋 Summary: $OUTPUT_DIR/SUMMARY.txt"
    echo "📄 Logs: $LOG_DIR/"
    echo ""
    echo "First scene:"
    echo "  View: python -m infinigen.launch_blender $OUTPUT_DIR/scene_0_seed_${START_SEED}/scene/scene.blend"
    echo "  Info: cat $OUTPUT_DIR/scene_0_seed_${START_SEED}/info/metadata.json"
    echo "==============================================================================="
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
