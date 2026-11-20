# Paper runs → commands

Run names are the directory names under `data/bench_b1_<app>/runs/` (program channel) and `data/bench_b1_<app>_gui/runs/`
(GUI channel), the same names as in the logs dataset (`VanWang/GoldiBench-logs`, column `run`).
Common settings of the program channel: `--rounds 4 --max-tokens 32000`, vLLM servers with `--max-model-len 65536`
(`scripts/serve_vllm.sh`), temperature 0.6, top-p 0.95. GUI channel: 100 steps, screenshot 1920×1080.

| run | where in the paper | command (per app: `BENCH_APP=<app> BENCH_SET=bench_b1_<app>`) |
|---|---|---|
| `b1t32` | Tab. main, program channel (seed 0) | `run_agent.py --models M --levels L1 L2 L3 --run b1t32 --rounds 4 --max-tokens 32000` |
| `b1t32_s1` … `b1t32_s4` | Tab. main, more seeds (open models) | same, `--run b1t32_s<k>` with another sampling seed (`--seed`) |
| `b1man` | Sec. 5, manual as a skill | `... --levels L2 --manual --tasks-file data/minimanual/subsets/<app>.txt --run b1man` |
| `b1mmv` | Sec. 5, mini manual (cards + effect sheet) | `... --levels L2 --minimanual visual --tasks-file ... --run b1mmv` |
| `b1mmt` | Sec. 5, mini manual (cards only) | `... --levels L2 --minimanual text --tasks-file ... --run b1mmt` |
| `b1table` | Sec. 5, measured statistics of the tools' effects | `... --levels L2 --knowledge table_state --tasks-file ... --run b1table` |
| `b1tdiff` | Sec. 5, measured TARGET−START difference | `... --levels L2 --knowledge table_state_diff --tasks-file ... --run b1tdiff` |
| `b1diffimg` | Sec. 5, the difference shown as an image | `... --levels L2 --knowledge diff_image --tasks-file ... --run b1diffimg` |
| `b1forced` | Sec. 5, forced to use all four rounds | `... --levels L2 L3 --forced --tasks-file ... --run b1forced` |
| `b1fb` | Sec. 5, forced rounds + numeric distance feedback | `... --levels L2 L3 --forced --feedback numeric --tasks-file ... --run b1fb` |
| `b1g100_s0..s2` | Tab. main, GUI channel (3 seeds) | `run_gui_osworld.py --models M --levels L1 L2 L3 --run b1g100_s<k> --seed <k> --max-steps 100` |
| `b1g100_closed` | Tab. main, GUI channel, closed models | `run_gui_osworld.py --models opus55gui gpt61gui --run b1g100_closed --max-steps 100` |

Score: `score.py --run <run>` (program) and `score_gui.py --run <run>` (GUI).
Other run names in the logs (`b1smoke*`, `bdk_*`, `_closed_seed1_unused`, `b1tdiff_gpt*`, `b1g_s*` (40-step GUI runs),
`b1g100_closed1a`, `b1g100_closed_tdiff`, backups) are smoke tests, pilots, controls and superseded runs; the logs dataset
marks every run with `in_paper` and `paper_use`. The exact shell pipelines that launched every run (including seeds and
model groups) are kept verbatim in the raw snapshot (`VanWang/ves-raw-snapshot-20261120`, `snapshot_v2/code__visual-effect-skills.tar.zst`,
`scripts/pipelines/`).

## vLLM server flags of the paper

`scripts/serve_vllm.sh <weights> <served_name> <port> <gpus> [flags]` adds `--max-model-len 65536` (override with
`MAX_MODEL_LEN`) and `--limit-mm-per-prompt '{"image":8}'` (override with `VLLM_MM`). Extra flags per model:

| served name (port in the built-in MODELS) | channel | extra flags |
|---|---|---|
| Qwen3.5-397B-A17B-FP8 (8001), -122B-A10B-FP8, -35B-A3B, -27B, -9B, -4B | program | `--reasoning-parser qwen3` |
| Qwen3.5-2B, Qwen3.5-0.8B | program | none |
| Qwen3.5 sizes as GUI agents (8041-8048) | GUI | `VLLM_MM='{"image":24}' --default-chat-template-kwargs '{"enable_thinking":false}'` |
| GLM-5.3-Flash (8002) | both | none |
| DeepSeek-V4.1-Flash (8003) | both | `--tokenizer-mode deepseek_v41 --reasoning-parser deepseek_v41` |
| Step-3.7-Flash-FP8 (8004) | both | `--reasoning-parser step3p5 --trust-remote-code` |
| NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16 (8005) | both | `--reasoning-parser nemotron_v3 --trust-remote-code` |
| Holo4-35B-A3B-FP8 (8011), Holo4-27B-FP8 (8016) | GUI (+ program smoke) | `--enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3` |
| GUI-Owl-1.5-32B-Instruct (8012) | GUI | `MAX_MODEL_LEN=32768` (+ the model card's `--mm-processor-kwargs`) |
| EvoCUA-32B-20260105 (8013) | GUI | none |
| OpenCUA-7B / 32B / 72B (8021 / 8022 / 8014) | GUI | `MAX_MODEL_LEN=32768 --trust-remote-code` (OpenCUA's own vLLM build) |
| UI-TARS-2B-SFT / 7B-DPO / 72B-DPO, UI-TARS-1.5-7B (8023-8025, 8015) | GUI | `MAX_MODEL_LEN=32768` |

The exact launch lines (GPU groups, memory fractions) are in the raw snapshot, `scripts/pipelines/b1_iter.sh`,
`b1_gui*.sh`, `extra_open.sh`, `b1_more.sh`.
