#!/usr/bin/env bash
# OpenCUA (7B / 32B / 72B) does not load under the main vLLM env (tokenizer error "unk_token should not be set in
# dumping mode"); the paper served it from a separate env with the vLLM version its model card names.
# Serve with: VLLM_BIN=$VE_LOCAL/envs/opencua/bin/vllm MAX_MODEL_LEN=32768 scripts/serve_vllm.sh xlangai/OpenCUA-7B OpenCUA-7B 8021 0 --trust-remote-code
set -euo pipefail
LOCAL=${VE_LOCAL:-$HOME/.cache/goldibench}
ENV=$LOCAL/envs/opencua
[ -x "$ENV/bin/vllm" ] && { echo "OpenCUA env exists: $ENV"; exit 0; }
uv venv -q -p 3.12 "$ENV"
VIRTUAL_ENV=$ENV uv pip install -q vllm==0.12.0 tiktoken blobfile --torch-backend=auto
"$ENV/bin/python" -c 'import vllm; print("vllm", vllm.__version__)'
