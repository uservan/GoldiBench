# Judge experiments and the human study (paper Sec. 2 and Sec. 4.1)

Code: `goldibench/judge/`. Run every command from the repository root (`python -m goldibench.judge.<script>`).
Data: `scripts/download_supporting.sh` (below). Outputs of new runs go to `$GOLDIBENCH_JUDGE_OUT` (default
`<data>/judge_runs`); the released files are never overwritten.

| paper | experiment | build | judge | numbers |
|---|---|---|---|---|
| Sec. 2, Fig. 2c, Supp. A.4, Tab. app-e3 | **E3** judge stress test: PSBench's judge on controlled wrong versions of PSBench's reference result (60 tasks, 5 open judges × 3 repeats) | `psbench_candidates.py` | `psbench_judge.py --exp e3` | `motivation_numbers.py` |
| same | E3 control: the judge shown the reference (2 judges), near-correct ×0.9 / ×1.1 added | (built on the fly) | `psbench_ref.py` | `motivation_numbers.py` |
| same | CIEDE2000 ≤ 3 against the reference | – | `reference_metrics.py` | `motivation_numbers.py` |
| Sec. 2, Fig. 2d, Supp. A.5, Tab. app-e3x | **E3-X** the same test on real darktable renders (56 tasks × explicit / vague) | `e3x_darktable.py make` | `psbench_judge.py --exp e3x` | `motivation_numbers.py` |
| Sec. 2, Supp. A.6, Tab. app-c1 | **C1** editing without the software (Qwen-Image-Edit-2511 on the 600 PSBench tasks) | `c1_image_edit.py` | `psbench_judge.py --exp c1` | `motivation_numbers.py` |
| Sec. 4.1, Tab. judge, Supp. C.1 | **Human study**: 913 (TARGET, CANDIDATE) pairs | `v5_pairs.py`, page `v5_page.py` | `v6_judge.py` (VLM judges) | `human_agreement.py` |

The judges are OpenAI-compatible endpoints (`goldibench/judge/common.py` `JUDGES`: the paper's vLLM ports 8001-8005 and
`goldibench/bench/bedrock_proxy.py` on 8101 for GPT-6.1 / Opus 5.5). Serve the open ones with `scripts/serve_vllm.sh` and the
flags of `docs/conditions.md`; add or override judges in a `judge:` section of `configs/models.yaml` (same fields as `program:`).
The PSBench judge prompt, image encoding and pass rule are imported verbatim from PSBench (`photoshop_evaluators.py` @ 5a9a911).

## Data

```bash
bash scripts/download_data.sh            # the benchmark (START / TARGET of the human-study pairs)
bash scripts/download_supporting.sh      # supporting/ of VanWang/GoldiBench-logs + PSBench code + the 60 E3 PSBench tasks
                                         # (--psbench-all: all 600 PSBench tasks, for C1)
bash scripts/restore_runs.sh --channel program   # only to rebuild the human-study pairs (agent candidates)
```
`$GOLDIBENCH_DATA/supporting/` then holds:

| path | content |
|---|---|
| `motivation_repo/visual-effect-skills/motivation/e3/` | E3 `candidates_manifest.csv`, `judgments.jsonl` (5 judges × 3 repeats), `judgments_ref.jsonl` (control), `reference_metrics.csv` |
| `motivation_repo/.../motivation/e3x/` | E3-X `candidates_manifest.csv` (with our metric's pass, clipping flags), `judgments.jsonl` |
| `motivation_repo/.../motivation/c1/` | C1 manifest and `judgments.jsonl` (the edited images are not released) |
| `motivation_repo/.../motivation/v5/annotation_key.csv` | human study: item id → app, task, candidate, dE, closeness, pass |
| `motivation_repo/.../motivation/benchmark_audit/` | task inventory and task-phrasing labels (Sec. 2.1 / 2.2; E3 samples its tasks from `split_full.csv`) |
| `motivation_e3/e3/candidates/<task>/<cand>.{webp,png}` | the E3 candidates (8 per task) |
| `motivation_e3x/e3x/{renders,tasks}/` | E3-X darktable renders and the 112 PSBench-style task folders (instruction, rubric, START, END) |
| `validation_v5/v5/pairs_<app>.jsonl`, `<app>/<task>_<cand>.{webp,png}` | the 913 human-study pairs and candidate images |
| `validation_v5/v5/v6_judgments.jsonl` | VLM judges on the pairs: Qwen3.5 and GLM-5.3 3 repeats, GPT-6.1 and Opus 5.5 1 valid repeat (Opus' first 913 calls failed with HTTP 400 and are kept with `reaches = null`; they are skipped) |
| `validation_v5/v5/human_ratings.jsonl` | the human ratings (one row per rater × item: `done` yes / no / unsure, `degree` none / under / ok / over / wrong, time in ms) |
| `PSBench/`, `PSBench-data/` | PSBench's code and task folders |

Images are released as WebP (quality 90); `download_supporting.sh` writes a PNG next to each, which the judges read. Paths
in the released manifests keep the original layout with the storage prefix redacted (`<ROOT>/visual_effect_data/...`);
`common.vpath` maps them to the downloaded files.

## Reproduce the paper's numbers (no GPU, seconds)

```bash
python -m goldibench.judge.motivation_numbers --check   # Tab. app-e3, app-e3x, app-c1, Sec. 2 / Fig. 2c-d numbers
python -m goldibench.judge.human_agreement --check      # Tab. judge, Sec. 4.1 and Supp. C.1 numbers
```
`--check` compares every printed number with the paper's and exits 1 on a mismatch (also `tests/judge_numbers.sh`).
Both accept other judgment files (`--e3 ... --c1`, `--judgments`, `--ratings`), e.g. a rerun.

## Rerun the experiments

```bash
# E3: candidates (bit-identical to the released ones), judges, control, reference metric
python -m goldibench.judge.psbench_candidates
python -m goldibench.judge.psbench_judge --exp e3 --manifest $GOLDIBENCH_JUDGE_OUT/e3/candidates_manifest.csv
python -m goldibench.judge.psbench_ref --manifest $GOLDIBENCH_JUDGE_OUT/e3/candidates_manifest.csv
python -m goldibench.judge.reference_metrics
python -m goldibench.judge.motivation_numbers --e3 $GOLDIBENCH_JUDGE_OUT/e3/judgments.jsonl \
    --e3-ref $GOLDIBENCH_JUDGE_OUT/e3/judgments_ref.jsonl --e3-metrics $GOLDIBENCH_JUDGE_OUT/e3/reference_metrics.csv
# E3-X on the released task folders and renders
python -m goldibench.judge.psbench_judge --exp e3x
# human study: pairs (needs the apps and the restored program runs), page, VLM judges
BENCH_APP=gimp BENCH_SET=bench_b1_gimp python -m goldibench.judge.v5_pairs     # per app
python -m goldibench.judge.v5_page --out page/ && python -m http.server -d page/
python -m goldibench.judge.v6_judge --judges qwen35 glm53 && python -m goldibench.judge.v6_judge --judges opus55 gpt61sol --repeats 1
python -m goldibench.judge.human_agreement --judgments $GOLDIBENCH_JUDGE_OUT/v5/v6_judgments.jsonl
```
Every script takes `--limit` / `--limit-tasks` for a quick check. The judges sample (temperature 0.6), so a rerun's
pass rates differ from the paper's by sampling noise; the candidate builders are deterministic.

The annotation page ran as a claude.ai artifact in the paper (answers in the artifact's database). Opened from a plain web
server it keeps answers in the browser and offers a JSON export; `v5_page.py --import-answers <exports...>
--ratings-out human_ratings.jsonl` converts them.

## Checked before release (2026-11-21)

- All Sec. 2 numbers (Tab. app-e3, app-e3x with CIs, app-c1, the pooled numbers of Sec. 2) and all Sec. 4.1 / Supp. C.1
  numbers (Tab. judge, agreement 72.5 %, away from the boundary, threshold 0.71 [0.60, 0.83], closeness bins, per-app
  range, judges' degree answers) reproduce exactly from the released files.
- `psbench_candidates.py`: the 60 sampled tasks equal the paper's; 350 of the 360 candidates are bit-identical
  (sha256). The other 10 belong to the two tasks whose END is resized to START (023, 156): the Lanczos resize of the
  current Pillow differs in the last bit (mean |difference| to the paper's candidates <= 1e-5).
  The PSBench task files from HF `zyn1216/PSBench` @ 929d071 are byte-identical to the copy used in the paper.
- `reference_metrics.py` (4 tasks): 27 of 32 rows identical; the 5 others are task 156 (resized END), dE differences
  <= 0.006, SSIM <= 0.0001, no pass decision changes.
- `v5_pairs.py` (darktable, 12 pairs incl. two agent candidates re-rendered from runs restored from the logs): every
  field identical to the released pairs. `v5_page.py`: the 913 item ids and the batch of every item equal the released
  key; the page tested headless (answers, submit, export).
- Judges end to end through `bedrock_proxy.py` (USD < 1): `v6_judge.py` (GPT-6.1, Opus 5.5, 8 pairs: same output format, 13 of
  16 verdicts as released), `psbench_judge.py --exp e3` (12 candidates), `psbench_ref.py` (10 calls). The open judges
  (vLLM) were not rerun for the release.
