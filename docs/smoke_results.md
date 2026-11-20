# Smoke test results (2026-11-20, before release)

`tests/smoke.sh` on the released dataset, 1 task (b000) per application, program channel L1 + L2 (2 rounds), GUI channel
darktable L1 (15 steps). Servers started with `scripts/serve_vllm.sh` and the flags of `docs/conditions.md`. 8x H200.

| model | darktable | rawtherapee | gimp | inkscape | blender | GUI darktable L1 |
|---|---|---|---|---|---|---|
| Holo4-35B-A3B, L1 | pass (1.00) | pass (1.00) | pass (1.00) | pass (1.00) | pass (1.00) | ran 15 steps, no harness error |
| Holo4-35B-A3B, L2 | fail (0.20) | pass (0.82) | fail (0.18) | fail (0.23) | fail (−0.31) | |
| Qwen3.5-397B-A17B, L1 | pass (1.00) | pass (1.00) | pass (1.00) | pass (1.00) | pass (1.00) | |
| Qwen3.5-397B-A17B, L2 | fail (0.51) | pass (0.75) | fail (0.48) | fail (reasoning hit the 8k token budget) | fail (0.65) | |

Numbers in brackets: closeness. L1 passes everywhere; L2 mostly fails, as in the paper. The smoke test checks that the
harness works (model calls, renders, GUI desktop, scoring), not the models' scores (1 task, short budgets).

## Clean-room test (2026-11-20)

`git clone` of this repository on an empty directory, `uv sync`, `scripts/download_data.sh` (tar archives from the Hugging
Face dataset), `scripts/setup_darktable.sh` + `scripts/setup_apps.sh` (all five applications downloaded from their
official release URLs, sha256 recorded), `scripts/setup_gui.sh` (X tools + OSWorld at the pinned commit), then
`tests/smoke.sh` with Holo4-35B-A3B served by `scripts/serve_vllm.sh`:

| | darktable | rawtherapee | gimp | inkscape | blender | GUI darktable L1 |
|---|---|---|---|---|---|---|
| L1 | pass (1.00) | pass (1.00) | pass (1.00) | pass (1.00) | pass (1.00) | 15 steps, closeness 0.62 |
| L2 | fail (0.20) | pass (0.82) | fail (0.18) | fail (0.23) | fail (−0.31) | |

Issues found and fixed on the way: single-file dataset download hit Hugging Face rate limits (now tar archives),
`tests/smoke.sh` did not create a given `SMOKE_DIR`.

## Interventions and GUI channel on every app (2026-11-20, on the clean-room install)

`tests/interventions.sh` (Holo4-35B-A3B, L2, one task of the intervention subset, 2 rounds) on GIMP and darktable: all
eight condition flags run end to end: `--manual` (the model calls read_skill / load_topic), `--knowledge table_state`,
`table_state_diff`, `diff_image`, `--minimanual visual`, `text`, `--forced`, `--forced --feedback numeric` (both rounds used).

`tests/smoke.sh` GUI channel, Holo4-35B-A3B, task b000 L1, 15 steps: darktable (closeness 0.62), GIMP (pass, 1.00),
Inkscape (0.00), RawTherapee (0.00), Blender (pass, 0.78); no harness errors on any app.

`scripts/restore_runs.sh` + `goldibench/paper/main_tables.py`: the program-channel table regenerated from the logs dataset
is identical to the paper's (42 of 42 entries).

## Every GUI agent adapter and the closed models (2026-11-20)

GUI channel, darktable task b000 L1, 15 steps, clean-room install (`uv sync --extra gui`), weights at the paper's revisions:

| agent (adapter) | served with | result |
|---|---|---|
| Claude Opus 5.5 (OSWorld computer use, Bedrock) | `GOLDIBENCH_ANTHROPIC_PROVIDER=bedrock` | pass, closeness 1.00, 4 steps |
| GPT-6.1 (OSWorld PromptAgent, Bedrock via `bedrock_proxy.py`) | `bedrock_proxy.py --port 8102` | pass, closeness 1.00, 4 steps |
| Holo4-35B-A3B (holo) | vLLM, tool-call parser qwen3_coder | ran, see above |
| UI-TARS-2B-SFT (uitars) | vLLM, 32k | ran 5 steps; used a tool outside the task's set (gate) |
| UI-TARS-1.5-7B (uitars15) | vLLM, 32k | ran 15 steps, closeness 0.00 |
| OpenCUA-7B (opencua) | `scripts/setup_opencua_env.sh` (vLLM 0.12), 32k | ran 11 steps, closeness 0.00 |
| Qwen3.5-0.8B (qwen) | vLLM, enable_thinking false | ran 15 steps, closeness 0.00 |
| GUI-Owl-1.5-32B (owl15) | vLLM, 32k + mm-processor size | ran 15 steps, closeness 0.00 |
| EvoCUA-32B (evocua) | vLLM | ran 15 steps, closeness 0.00 |

Every agent produced well-formed replies and executable actions (no action errors, no harness errors). Program channel
through Bedrock: GPT-6.1 and Claude Opus 5.5 pass L1 on darktable and GIMP. Total cost of these tests: about USD 3.

Fixed by these tests: GUI agent dependencies (extra `gui`), the separate OpenCUA env (`scripts/setup_opencua_env.sh`),
the cost-ledger directory for a fresh data dir, the GUI default task sets.
