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
through Bedrock: GPT-6.1 and Claude Opus 5.5 pass L1 on darktable and GIMP. Total Bedrock cost of these tests: USD 0.32.

Fixed by these tests: GUI agent dependencies (extra `gui`), the separate OpenCUA env (`scripts/setup_opencua_env.sh`),
the cost-ledger directory for a fresh data dir, the GUI default task sets.

## Sample rerun of every paper condition with full-reply logging (2026-11-21)

Clean install (fresh clone, dataset from the Hub, applications from their official downloads, vLLM 0.31.0), 3 tasks per
application, every condition of the paper, `--log-replies` on. Packaged as `supplementary/` of `VanWang/GoldiBench-logs`
(episodes, steps, every call with full reply / reasoning / tokens, renders and full GUI trajectories, comparison with the
paper's records). Program channel: Qwen3.5-9B and Step-3.7-Flash on all conditions (main L1-L3, manual, table, tdiff,
diffimg, minimanual visual / text, forced, forced + numeric feedback), Claude Opus 5.5 on main, manual, forced, feedback
(1 task / app). GUI channel (100 steps, seed 0): Holo4-35B-A3B-FP8 and Qwen3.5-9B (OSWorld QwenAgent) on L1-L3 of all
5 apps; Claude Opus 5.5 computer use on L1 + L2 of all 5 apps and L3 of darktable (1 task / app).

| channel | condition | model | episodes | pass (rerun) | pass (paper, same tasks) | closeness (rerun / paper) |
|---|---|---|---|---|---|---|
| program | main | qwen35_9b | 45 | 0.36 | 0.34 (5 seeds) | 0.25 / 0.16 |
| program | main | step37 | 45 | 0.36 | 0.33 | 0.29 / 0.31 |
| program | main | opus55 | 15 | 0.33 | 0.33 | 0.48 / 0.47 |
| program | manual | qwen35_9b / step37 / opus55 | 15 / 15 / 5 | 0.00 / 0.07 / 0.00 | 0.00 / 0.00 / 0.00 | 0.24 / 0.16, 0.25 / -0.01, 0.28 / 0.25 |
| program | table | qwen35_9b / step37 | 15 / 15 | 0.00 / 0.07 | 0.07 / 0.00 | -0.53 / -0.55, -0.05 / 0.08 |
| program | tdiff | qwen35_9b / step37 | 15 / 15 | 0.13 / 0.07 | 0.20 / 0.07 | 0.09 / 0.19, 0.11 / 0.14 |
| program | diffimg | qwen35_9b / step37 | 15 / 15 | 0.00 / 0.07 | 0.07 / 0.07 | -0.09 / -0.17, 0.12 / 0.01 |
| program | minimanual visual | qwen35_9b / step37 | 15 / 15 | 0.00 / 0.00 | 0.00 / 0.00 | -0.28 / -0.76, -0.19 / 0.06 |
| program | minimanual text | qwen35_9b / step37 | 15 / 15 | 0.07 / 0.00 | 0.00 / 0.07 | -0.23 / -0.42, 0.14 / 0.10 |
| program | forced | qwen35_9b / step37 / opus55 | 30 / 30 / 10 | 0.07 / 0.00 / 0.10 | 0.00 / 0.00 / 0.10 | -0.14 / -0.12, -0.14 / -0.08, 0.32 / 0.30 |
| program | forced + feedback | qwen35_9b / step37 / opus55 | 30 / 30 / 10 | 0.03 / 0.03 / 0.10 | 0.00 / 0.07 / 0.10 | 0.07 / -0.04, 0.00 / 0.21, 0.35 / 0.40 |
| GUI | main | holo4_35b | 45 | 0.11 | 0.08 (3 seeds) | 0.03 / -0.06 |
| GUI | main | qwen35gui_9b | 45 | 0.02 | 0.00 (3 seeds) | -0.41 / -0.47 |
| GUI | main | opus55gui | 11 | 0.45 | 0.45 | 0.62 / 0.68 |

No harness errors in 531 episodes / 8,936 calls (no failed render, model call, GUI harness error or agent exception).
Same failure modes as the paper: L1 passes and L2 / L3 mostly fail; on `tdiff` / `table` the reasoning often runs into
the 32k budget (step37 tdiff "no valid reply" 13 / 15 here, 12 / 15 in the paper); GUI agents mostly stop at 100 steps.
Bedrock cost of the rerun: USD 23.09. Single episodes differ from the paper's (sampling is not bit-reproducible).

## Final commit on a new host (2026-11-22)

`git clone` of master `11817cc` (after the `uv.lock` refresh: protobuf 5.29.6), same clean-room steps as above, Holo4-35B-A3B
weights from Hugging Face, `LOG_REPLIES=1 tests/smoke.sh`: SMOKE OK, no harness errors, every episode has its `calls.jsonl`.
L1 passes on all five apps (closeness 1.00); L2 darktable 0.20, RawTherapee pass 0.82, GIMP 0.18, Inkscape 0.23,
Blender −1.05; GUI darktable L1 15 steps, closeness 0.05.
Found on the way: `setup_apps.sh` / `setup_darktable.sh` did not stop on a failed download and then recorded the sha256 of
only the files that arrived (fixed). inkscape.org served only the first 19.9 MB of the AppImage that day; the copy used
has the sha256 of the original download.

## The parts no earlier test covered (2026-11-22)

Same clean install, public data only.

- **GUI channel, measured TARGET − START** (run `b1g100_closed_tdiff` of the paper; here Holo4-35B-A3B, darktable and
  GIMP task b000, L2, 10 steps, `GUI_KNOWLEDGE=table_state_diff`): runs end to end, no harness error; the statistics reach
  the agent (its first reasoning quotes "TARGET minus START: L* +7.7, …"; prompt 7,826 tokens vs 6,695 without).
- **Building the benchmark** (`gen_b1.py` → `verify_b1.py` → `report_b1.py` → `freeze_b1.py`, darktable). Generators stood
  in for by Qwen3.5-9B under both served names (pipeline test, not generation quality): candidates are proposed, rendered
  and rejected by the gates (C3, C4, V-2, V-3); none passed with the 9B model, as expected. `verify_b1.py` on the released
  darktable set: all 100 tasks re-checked, 0 with problems (`VERIFY_WORKERS=16`, ~15 min).
  `freeze_b1.py --per-k 12` (check only): all checks pass, split dev 20 / test 80 as released. The released sets have
  uneven step-count buckets (frozen after the human review), so the default `--per-k 20` reports darktable k=4 19, k=5 12.
  Fixed on the way: `gen_b1.py` needed the full PSBench download (`<id>/<id>.json`); the dataset ships only the start
  images, so every photo-app candidate failed (now falls back to `<id>_start.*`). `verify_b1.py` resolved the released
  sets' dataset-relative `source_path` against the working directory (now against `GOLDIBENCH_DATA`). A reply without
  content (reasoning used the budget) now says so instead of a `TypeError`.
- **PlayRaw** (`DT_LIBRARY=playraw`, run `b2t32`): the released set could not be re-rendered (bundles, raw files and XMP
  sidecars were missing; `source_path` was a placeholder) and `score.py` crashed on the 6 tasks without images. The
  dataset now has `bench_b2_darktable/{bundles,raw,xmp}` for the 154 licensed tasks; `source_path` points at the bundle,
  `FROZEN` regenerated (programs unchanged); `run_agent.py` / `score.py` skip the 6 tasks without images. Fresh
  `download_data.sh --playraw`: sha256 OK; replaying the hidden programs from the released bundles reproduces TARGET
  (max ΔE 0.0002 on the sampled tasks); `score.py` validation of all 154 tasks: oracle max ΔE 0.21, ×0.9 / ×1.1 pass,
  identity / ×0.5 / over fail on every task; Qwen3.5-9B run (2 tasks, L1 + L2) and scoring OK (L1 pass, L2 fail).
