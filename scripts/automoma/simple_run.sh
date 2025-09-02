data_folder="outputs/kitchen_test/0827_2"
scene_folder="$data_folder/scenes"
export_folder="$data_folder/exports"
TEXTURE_RESOLUTION=512

python -m infinigen_examples.generate_indoors --seed 42 --task coarse \
  --output_folder "$scene_folder" --configs kitchen_only.gin

python -m infinigen.tools.export \
        --input_folder "$scene_folder" \
        --output_folder "$export_folder" \
        --format usdc \
        --resolution $TEXTURE_RESOLUTION \
        --omniverse

# /home/xinhai/Documents/cuakr-docker/scene/infinigen/assets/partnet_mobility/processed_data/Microwave/7263/mobility/mobility.usd