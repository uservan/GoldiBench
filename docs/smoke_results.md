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
