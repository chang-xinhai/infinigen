conda activate sapien

conda run --live-stream --name sapien python scripts/detect_invalid.py /home/xinhai/Documents/cuakr-docker/scene/infinigen/assets/partnet_mobility/raw_data ./output/valid
conda run --live-stream --name sapien python scripts/split_by_category.py /home/xinhai/Documents/cuakr-docker/scene/infinigen/assets/partnet_mobility/raw_data ./output/category

