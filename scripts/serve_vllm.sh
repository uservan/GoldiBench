#!/usr/bin/env bash
# Serve one open model with vLLM as an OpenAI-compatible endpoint (http://localhost:<port>/v1).
# Usage: scripts/serve_vllm.sh <hf_repo_id_or_local_dir> <served_name> <port> <gpu_ids e.g. 0,1,2,3> [extra vllm args...]
#   served_name must match `model:` of the entry in configs/models.yaml (and run_agent.py's MODELS for the paper models).
# Settings of the paper: --max-model-len 65536 (32k answer budget), 8 images per prompt for GUI agents (VLLM_MM).
# vllm: $VLLM_BIN, else `vllm` on PATH (scripts/setup_env.sh builds the pinned env from env/vllm_env.lock.txt).
set -euo pipefail
model=$1 name=$2 port=$3 gpus=$4; shift 4
VLLM=${VLLM_BIN:-$(command -v vllm || echo "${VE_LOCAL:-$HOME/.cache/goldibench}/envs/vllm/bin/vllm")}
[ -x "$VLLM" ] || { echo "vllm not found: set VLLM_BIN or run scripts/setup_env.sh" >&2; exit 1; }
MM=${VLLM_MM:-'{"image":8}'}
tp=$(awk -F, '{print NF}' <<<"$gpus")
CUDA_VISIBLE_DEVICES=$gpus exec "$VLLM" serve "$model" \
  --served-model-name "$name" --port "$port" --tensor-parallel-size "$tp" \
  --max-model-len "${MAX_MODEL_LEN:-65536}" --limit-mm-per-prompt "$MM" --gpu-memory-utilization 0.9 \
  --trust-remote-code "$@"
