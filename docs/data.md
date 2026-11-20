# Data and logs: where everything is

Three Hugging Face datasets hold everything of the paper except model weights.

| repo | what | size |
|---|---|---|
| [VanWang/GoldiBench](https://huggingface.co/datasets/VanWang/GoldiBench) | the benchmark: 500 tasks + inputs the code needs | ~6 GB |
| [VanWang/GoldiBench-logs](https://huggingface.co/datasets/VanWang/GoldiBench-logs) | every run of the project: model outputs, programs, GUI actions, screenshots, scores, costs | tens of GB |
| [VanWang/ves-raw-snapshot-20261120](https://huggingface.co/datasets/VanWang/ves-raw-snapshot-20261120) | raw snapshot of the research tree (all non-image files, original layout) for tracing anything back | few GB |

Machine-specific information (host names, cluster IPs, storage paths, user names, keys) was redacted everywhere:
`<ROOT>` = the research root, `<HOST>`, `<IP>`, `<USER>`, `<EMAIL>`, `<REDACTED>`. Paths inside the dataset are relative.

## 1. GoldiBench (the benchmark)

Same layout as the code expects under `GOLDIBENCH_DATA`:

```
bench_b1_<app>/                    program channel, app in darktable rawtherapee gimp inkscape blender
  tasks.jsonl                      one task per line (100): task_id, app, kind (single / multi / long), program (the hidden
                                   answer {tool: {field: value}}), modules (the task's tools), order, intervals (accepted
                                   value ranges), intent (the look in words), l1_instruction (L1 text), source / source_path
                                   (input image or scene), start_target_de00, checks (verification results), generator,
                                   reasons, manual_pages, attempts, revisions
  FROZEN                           sha256 of every task program; runs refuse changed or unlisted tasks
  tasks/<task_id>/start.png        START render (the input as the agent sees it)
  tasks/<task_id>/target.png       TARGET render of the hidden program
  tasks/<task_id>/program.json     the hidden program
  tasks/<task_id>/_val_*.png       validation renders: oracle replay, x0.5 (half), x0.9, x1.1, over-strength
  verify.json                      per-task verification (oracle, strength scaling, single-tool removal)
  magnitude_curve.json             closeness vs. strength scaling of every task (Fig. strength)
  v3_more.json, search.json        extra checks / numeric-search reference (darktable)
  knowledge/                       pre-rendered effect sheets and difference images of the L2 interventions
bench_b1_<app>_gui/                GUI channel
  tasks.jsonl                      one GUI task per line and level (id = <task_id>_<level>): instruction, config (file to
                                   open), allowed_modules, program / gui_program, target, evaluator, kind, level
  tasks/<task_id>/                 start.png / target.png used by the GUI evaluator
  replay_validation*.json          the hidden program replayed through the GUI (task kept only if replay reproduces TARGET)
  rejected.json, unreachable.json  tasks dropped from the GUI channel and why
sources/                           input photos (PSBench) referenced by source_path
assets/                            Blender scenes (Poly Haven) and SVGs (Openclipart) referenced by source_path
manuals/                           application manuals (the --manual intervention); minimanual/: mini manuals and the
                                   task subsets of the Sec. 5 interventions (minimanual/subsets/<app>.txt)
```

## 2. GoldiBench-logs (the paper's experiments, for analysis and rebuttal)

Only the experiments of the paper (no smoke tests, pilots, abandoned or superseded runs), laid out as
`<program|gui>/<app>/<model>/<condition>/seed<k>/{episodes.parquet, steps.parquet, images.tar, raw.tar.zst}`, plus
`supporting/` (validation, motivation experiments, computed paper numbers), `cost/` (every closed-model API call: tokens,
USD), `runs.csv` and `episodes_paper.parquet`. The dataset's README is the full reference: what is and is not included,
the condition ↔ original run name table, every column, which screenshots are saved, cost notes and how it was built:
https://huggingface.co/datasets/VanWang/GoldiBench-logs

Download parts with `scripts/download_logs.sh --channel gui --app gimp --model gpt61gui` or `--tables-only`.

## 3. Raw snapshot

`snapshot_v2/<unit>.tar.zst` (non-image files, original layout, redacted) + `manifests_v2/<unit>.tsv` (path, bytes,
sha256 of the original file, redaction counts). `code__visual-effect-skills` is the full research code base including
every pipeline script that launched the paper's runs (`scripts/pipelines/`) and the day-by-day notes (`docs/resume-*.md`).
