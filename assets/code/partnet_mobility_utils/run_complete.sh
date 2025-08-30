#!/bin/bash

# Complete PartNet Mobility Data Processing Pipeline Script

# ============================================================================
# CONFIGURATION: Edit this section to specify which steps to run
# ============================================================================

# Specify which steps to run (step1, step2, step3, step4)
# Example configurations:

running_steps=(step4)

# ============================================================================
# END CONFIGURATION
# ============================================================================

echo "=== PartNet Mobility Data Processing Pipeline ==="
echo "Configured to run steps: ${running_steps[*]}"
echo ""

# Activate conda environment
conda activate sapien

# Set path variables
RAW_DATA_DIR="/home/xinhai/Documents/cuakr-docker/scene/infinigen/assets/partnet_mobility/raw_data"
OUTPUT_DIR="./output"
VALID_OUTPUT_DIR="$OUTPUT_DIR/valid"
CATEGORY_OUTPUT_DIR="$OUTPUT_DIR/category"
PROCESSED_DATA_DIR="/home/xinhai/Documents/cuakr-docker/scene/infinigen/assets/partnet_mobility/processed_data"

# Create output directories
mkdir -p "$VALID_OUTPUT_DIR"
mkdir -p "$CATEGORY_OUTPUT_DIR"

# Function to run step 1
run_step1() {
    echo "Step 1: Detecting invalid data..."
    conda run --live-stream --name sapien python scripts/detect_invalid.py "$RAW_DATA_DIR" "$VALID_OUTPUT_DIR"
}

# Function to run step 2
run_step2() {
    echo "Step 2: Splitting data by category..."
    conda run --live-stream --name sapien python scripts/split_by_category.py "$RAW_DATA_DIR" "$CATEGORY_OUTPUT_DIR"
}

# Function to run step 3
run_step3() {
    echo "Step 3: Reorganizing data to processed_data directory..."
    conda run --live-stream --name sapien python scripts/reorganize_data.py \
        "$RAW_DATA_DIR" \
        "$VALID_OUTPUT_DIR/all_ids.txt" \
        "$CATEGORY_OUTPUT_DIR" \
        "$PROCESSED_DATA_DIR"
}

# Function to run step 4
run_step4() {
    echo "Step 4: Converting URDF to USD..."

    # Using Isaac Sim 4.2.0
    conda activate cuakr-docker

    # URDF to USD conversion configuration (only used if step4 is in running_steps)
    # Modes: "all", "random", "category", "object"
    usd_conversion_mode="all"
    usd_random_count=5                           # For random mode
    usd_category_name="Microwave"                # For category mode  
    usd_object_id="7167"                         # For object mode

    if [[ " ${running_steps[*]} " =~ " step4 " ]]; then
        echo "USD conversion mode: $usd_conversion_mode"
        case $usd_conversion_mode in
            "random") echo "Random objects count: $usd_random_count" ;;
            "category") echo "Target category: $usd_category_name" ;;
            "object") echo "Target object ID: $usd_object_id" ;;
        esac
    fi

    echo "Conversion mode: $usd_conversion_mode"
    
    case $usd_conversion_mode in
        "all")
            echo "Converting all objects to USD..."
            conda run --live-stream --name cuakr-docker python scripts/batch_urdf_to_usd.py --processed_data_dir "$PROCESSED_DATA_DIR" --mode all
            ;;
        "random")
            echo "Converting $usd_random_count random objects to USD..."
            conda run --live-stream --name cuakr-docker python scripts/batch_urdf_to_usd.py --processed_data_dir "$PROCESSED_DATA_DIR" --mode random --count "$usd_random_count"
            ;;
        "category")
            echo "Converting category '$usd_category_name' to USD..."
            conda run --live-stream --name cuakr-docker python scripts/batch_urdf_to_usd.py --processed_data_dir "$PROCESSED_DATA_DIR" --mode category --category "$usd_category_name"
            ;;
        "object")
            echo "Converting object '$usd_object_id' to USD..."
            conda run --live-stream --name cuakr-docker python scripts/batch_urdf_to_usd.py --processed_data_dir "$PROCESSED_DATA_DIR" --mode object --object-id "$usd_object_id"
            ;;
        *)
            echo "Invalid conversion mode: $usd_conversion_mode. Skipping URDF to USD conversion."
            return 1
            ;;
    esac
}

# Function to display statistics
display_stats() {
    echo ""
    echo "=== Processing Results Statistics ==="
    if [ -f "$VALID_OUTPUT_DIR/well_formed.txt" ]; then
        echo "Total valid objects: $(wc -l < $VALID_OUTPUT_DIR/well_formed.txt)"
    fi
    if [ -d "$CATEGORY_OUTPUT_DIR" ]; then
        echo "Number of categories: $(ls $CATEGORY_OUTPUT_DIR/*.txt 2>/dev/null | wc -l)"
    fi
    if [ -d "$PROCESSED_DATA_DIR" ]; then
        echo "Categories in processed_data directory:"
        ls -d "$PROCESSED_DATA_DIR"/*/ 2>/dev/null | while read dir; do
            category=$(basename "$dir")
            count=$(ls -d "$dir"/*/ 2>/dev/null | wc -l)
            echo "  $category: $count objects"
        done
    fi
    
    # Display USD conversion stats if available
    if [ -f "$PROCESSED_DATA_DIR/usd_conversion_stats.json" ]; then
        echo ""
        echo "=== USD Conversion Statistics ==="
        python3 -c "
import json
with open('$PROCESSED_DATA_DIR/usd_conversion_stats.json', 'r') as f:
    stats = json.load(f)
    print(f'Total USD conversions attempted: {stats.get(\"total_attempted\", 0)}')
    print(f'Total USD conversions successful: {stats.get(\"total_successful\", 0)}')
    print(f'Total USD conversions failed: {stats.get(\"total_failed\", 0)}')
    if stats.get('total_attempted', 0) > 0:
        success_rate = stats.get('total_successful', 0) / stats.get('total_attempted', 1) * 100
        print(f'USD conversion success rate: {success_rate:.1f}%')
    categories_processed = stats.get('categories_processed', [])
    if categories_processed:
        print(f'Categories with USD files: {len(categories_processed)}')
        print(f'Category list: {sorted(categories_processed)}')
"
    fi
}

# Execute based on configured steps
echo "=== Starting Configured Pipeline ==="

for step in "${running_steps[@]}"; do
    case $step in
        "step1")
            run_step1
            ;;
        "step2")
            run_step2
            ;;
        "step3")
            run_step3
            ;;
        "step4")
            run_step4
            ;;
        *)
            echo "Warning: Unknown step '$step'. Skipping."
            ;;
    esac
done

echo "=== Pipeline Completed ==="
display_stats