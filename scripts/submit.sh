#!/bin/bash
#SBATCH --partition=h100
#SBATCH --job-name=auto_task
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=100
#SBATCH --time 3-00:00:00

# "$@" here will receive any commands you pass in from the command line
srun "$@"