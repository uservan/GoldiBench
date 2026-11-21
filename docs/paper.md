# Reproducing the paper's tables, numbers and figures

Everything below runs on the public data only: the benchmark ([VanWang/GoldiBench](https://huggingface.co/datasets/VanWang/GoldiBench))
and the run logs ([VanWang/GoldiBench-logs](https://huggingface.co/datasets/VanWang/GoldiBench-logs)). No model is called;
only Fig. pipeline renders three images with darktable.

## Setup

```bash
uv sync --extra paper
export GOLDIBENCH_DATA=$PWD/data GOLDIBENCH_PAPER=$PWD/paper_out
bash scripts/download_data.sh --provenance --playraw   # the benchmark (~9 GB download, ~16 GB unpacked) + split, generation logs, PlayRaw
bash scripts/restore_runs.sh --supporting \
     --images 'program/rawtherapee/gpt61sol/main/seed0' \
     --images 'program/darktable/*/forced_feedback/seed0'
python goldibench/paper/score_report.py          # text reports of every program run (read by qwen_seeds_l2 / sec43_data)
bash scripts/setup_darktable.sh                  # only for fig_pipeline.py (renders the x0.5 / x1.5 images once)
```

`restore_runs.sh` puts the runs back into the original layout (`<data>/bench_b1_<app>[_gui]/runs/<run>/`, raw records:
episode.json, scores.json, run logs; a few GB) and the paper's own computed numbers into `<data>/paper_numbers_original/`
for comparison. `--supporting` adds the Sec. 2 / Sec. 4 data (`<data>/motivation`, `<data>/e3`, `<data>/e3x`, `<data>/v5`);
`--images UNIT` adds the renders of a logs folder (WebP at the original paths; the figure scripts use them where the PNG is
absent). Paths stored inside the logs start with `<ROOT>/visual_effect_data/`; `goldibench/paper/paperdata.py` maps them
to `GOLDIBENCH_DATA`.

## Script → paper item

Outputs: tables to `$GOLDIBENCH_PAPER/tab/`, figures to `$GOLDIBENCH_PAPER/fig/` (or `--out`), numbers to `<data>/logs/`
and stdout. "Checked" = regenerated on a clean install from the public data on 2026-11-21 and compared with the paper
source and `<data>/paper_numbers_original/`.

| script | paper item | checked |
|---|---|---|
| `main_tables.py` | Tab. main (`tab/main_prog.tex`, `main_gui.tex`, combined `main.tex`), Tabs. app-prog / app-gui (Supp. D) | identical (all LaTeX rows; `logs/main_tables.json` identical, 2,691 values) |
| `main_combined.py` | Tab. main as one table (run by `main_tables.py`) | rows identical; the caption is kept from an existing `tab/main.tex` |
| `main_ci.py` | 95% bootstrap intervals (Supp. D, caption of Tab. main) | `logs/main_ci.json` identical |
| `threshold_sweep.py` | Tab. thresholds, other pass rules (Supp. D.2) | `logs/threshold_sweep.json` identical; all 48 cells and τ of the table match |
| `interventions.py` | Tab. interventions (Sec. 5), Tab. interventions-full (Supp. D) | `logs/interv12.json` identical; every program cell (pass, Δ, Δcl, significance marks) matches. GUI row: see below |
| `ch5_numbers.py` | numbers in the text of Sec. 5 (rounds, per-app, loose rule) | forced / feedback rows match the tables; inputs identical |
| `score_report.py` | text reports `logs/bench_b1_<app>_scores_<run>.txt` | all 65 reports of the paper's runs byte-identical to the originals |
| `qwen_seeds_l2.py` | Qwen3.5 L2 over 5 seeds (Supp. D) | output identical to the one from the original reports |
| `sec43_data.py` | Sec. 4.3 / Figs. scaling (`logs/sec43_data.json`, `.md`) | `.md` identical; `.json`: 575 of 576 values identical, one closeness differs in the 3rd decimal (0.093 vs 0.092, not used in the paper) |
| `fig_scaling_sub.py` | Fig. scaling (`scaling_prog/qwen/opencua/uitars.pdf`, Supp. D) | vector paths and text identical (matplotlib 3.10.9) |
| `fig_rounds.py` | Fig. rounds (Supp. D) | identical (matplotlib 3.10.9) |
| `fig_strength.py` | Fig. strength (Sec. 4.1) | identical (matplotlib 3.10.9) |
| `fig_teaser.py` | Fig. 1 | vectors and text identical; images from the WebP logs (max pixel difference 2/255) |
| `fig_task_example.py` | Fig. task example (Sec. 3.2) | vectors and text identical; images WebP (max 3/255) |
| `fig_motivation.py` | Fig. motivation (Sec. 1 / 2) | vectors and text identical; images WebP |
| `fig_pipeline.py` | Fig. pipeline (Sec. 3.1) | text identical; the x0.5 / x1 / x1.5 renders reproduce the paper's scores exactly (dE 6.30 / 0.00 / 7.42); three label boxes differ by < 0.5 pt (font metrics) |
| `bench_stats.py` | Tab. bench-stats (Supp. B) | every cell matches (Dev / test, Kept and the PlayRaw row need `download_data.sh --provenance --playraw`) |
| `fig_judge_examples.py`, `fig_human_pairs.py`, `fig_scaling.py`, `fig_scaling_lines.py` | earlier figure versions, not in the final paper | run; `fig_human_pairs.py` now skips unparsed (null) judge verdicts |
| `split_submission.py` | splits the compiled PDF into main paper and supplement | utility, no data |

**matplotlib version.** The paper's figures were made with matplotlib 3.10.9. With 3.10.9 the regenerated PDFs have the
same vector paths as the paper's (0 pt difference); with 3.11 the plotted data are the same but layout details shift by
up to ~1.5 pt.

## Notes

- **GUI row of Tab. interventions** ("Statistics of TARGET − START, GUI": Opus 5.5 10.4 → 30.4, GPT-6.1 28.0 → 39.2):
  from the runs `bench_b1_<app>_gui/runs/b1g100_closed_tdiff` (logs `gui/<app>/<model>/tdiff/seed0`, added 2026-11-21;
  restored by `restore_runs.sh`). Checked on the original runs: identical to the paper, 125 pairs per model.
- **Dev / test split** (Sec. 3, Fig. pipeline, Tab. bench-stats: dev 101 / test 399), **Kept %** (Tab. bench-stats) and the
  **160 PlayRaw real edits** (Sec. 3, Sec. 4 "Generated tasks behave like real edits", Tab. bench-stats) come with
  `download_data.sh --provenance --playraw` (added 2026-11-21); without them `bench_stats.py` prints `--` and
  `fig_pipeline.py` prints the paper's counts.
- The judging experiments themselves (Sec. 2 / Sec. 4: VLM judges, human study) are released as data
  (`restore_runs.sh --supporting`); their figures are reproduced above.
