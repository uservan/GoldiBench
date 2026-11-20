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
