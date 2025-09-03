data_folder="outputs/kitchen_test/0902_1"
scene_folder="$data_folder/scene"
export_folder="$data_folder/export"
TEXTURE_RESOLUTION=1024

python -m infinigen_examples.generate_indoors --seed 42 --task coarse \
  --output_folder "$scene_folder" --configs kitchen_only.gin

python -m infinigen.tools.export \
        --input_folder "$scene_folder" \
        --output_folder "$export_folder" \
        --format usdc \
        --resolution $TEXTURE_RESOLUTION \
        --omniverse

# /home/xinhai/Documents/cuakr-docker/scene/infinigen/assets/partnet_mobility/processed_data/Microwave/7263/mobility/mobility.usd