# Activate conda environment
data_folder="output/kitchen_test/new_test"
scene_folder="$data_folder/scene"
export_folder="$data_folder/export"
TEXTURE_RESOLUTION=1024
seed=0

log_folder="$data_folder/log"
mkdir -p "$log_folder"

echo "Generating scene for seed $seed"

python -m infinigen_examples.generate_indoors \
        --seed "$seed" \
        --task coarse \
        --time_record \
        --output_folder "$scene_folder" \
        --configs kitchen_only.gin \
        >> "$log_folder/generate_scene_$seed.log" 2>&1

python -m infinigen.tools.export \
        --input_folder "$scene_folder" \
        --output_folder "$export_folder" \
        --format usdc \
        --resolution $TEXTURE_RESOLUTION \
        --omniverse \
        >> "$log_folder/export_scene_$seed.log" 2>&1

