#!/bin/bash
#SBATCH --partition=h100
#SBATCH --job-name=auto_task
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:8
#SBATCH --cpus-per-task=120
#SBATCH --time 3-00:00:00

set -euo pipefail

if [[ $# -eq 0 ]]; then
    echo "Usage: sbatch scripts/submit.sh <command> [args...]" >&2
    exit 1
fi

# The batch script itself already runs inside the allocated node. Launching the
# payload directly avoids clusters where nested srun job steps fail hostname
# resolution (for example, "Unable to resolve node003").
if [[ "${SUBMIT_USE_SRUN:-0}" == "1" ]]; then
    echo "[submit.sh] launching payload with srun"
    exec srun "$@"
fi

echo "[submit.sh] launching payload directly inside batch allocation"
exec "$@"
