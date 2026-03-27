CONDA_ENV=infinigen GPU_IDS=0,1,2,3,4 TASKS='trajectory structured_light' bash scripts/benchmark/neural_rgbd/run_all_neural_rgbd.sh

CONDA_ENV=infinigen GPU_IDS=0 FRAME_END=2 TASKS='trajectory structured_light' bash scripts/benchmark/neural_rgbd/run_all_neural_rgbd.sh
