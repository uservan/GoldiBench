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

## 2. GoldiBench-logs (every run, for analysis and rebuttal)

```
<channel>/<app>/<model>/<condition>/seed<k>/      channel = program | gui; app = darktable ... blender
    episodes.parquet    one row per episode
    steps.parquet       one row per program round / GUI step
    images.tar          WebP renders / screenshots (member path = original path with .webp)
    raw.tar.zst         original episode records (episode.json), redacted
<channel>/<app>/_run/<run>/raw.tar.zst      run-level files (scores.json, run logs), under the original run name
other/<dir>/                                 smoke tests, pilots, backups, early experiments, top-level logs
episodes_all.parquet                         every episode in one table; episodes_paper.parquet: the paper's runs only
runs.csv                                     one row per run: channel, app, models, condition, in_paper, paper_use, counts
cost/calls.parquet, cost/summary.csv, cost/by_day.csv    closed-model API calls: tokens and USD
```

**condition**: `main` (Tab. main), `manual`, `tdiff` (measured TARGET−START difference), `table`, `diffimg`,
`minimanual_visual`, `minimanual_text`, `forced`, `forced_feedback`; other names are smoke / pilot / control runs.
**seed**: program `main` seed0 = run `b1t32`, seed1-4 = `b1t32_s1..s4`; GUI seed0-2 = `b1g100_s0..s2` (closed models: seed0).
Download a part with `scripts/download_logs.sh --channel gui --app gimp --model gpt61gui` (see its header).

**episodes** columns: unit, container, top_dir, run, app, channel (program / gui), episode_dir, task_id, level, model,
in_paper, paper_use, kind, end (done / rounds / max steps / DONE / error ...), n_rounds or n_steps, seconds (GUI), pass,
closeness, de00, d0, per_round_closeness, violations, modules_used, modules_true, final_program, scored, eval (GUI
evaluator output, JSON), extra (remaining fields of the record, JSON).

**steps** columns: unit, episode_dir, channel, model, task_id, level, step (round / step number), kind (program / tool /
error), program (JSON), rationale (the model's stated reason, <= 400 chars as logged), done, violations, tool / topic
(manual calls), retries (failed attempts, finish reasons), error, detail, response (GUI: the model's reply, last 3000
chars as logged), actions (GUI: executed code), errors, image (path of the screenshot / render inside images/*.tar).

### Which screenshots are included

The GUI runs produced about 10 million screenshots (one per step, 1920x1080, ~5 TB). Included as WebP:
- **program channel:** every round render of every episode;
- **GUI channel, full trajectory (every step):** all episodes of the closed models (Claude Opus 5.5, GPT-6.1), every
  passing episode, and every episode on 5 fixed sample tasks per application (`md5(task_id) % 20 == 0`, all models,
  levels and runs) for side-by-side comparison;
- **GUI channel, all other episodes:** the last screenshot (the agent's final state).

`episodes.full_trajectory_saved` says which case an episode is; `steps.image` is the saved WebP (null when not saved) and
`steps.screenshot_original` the original file name. The text of every step (model reply, actions, errors) is included for
every episode. Inside the GUI `work/` directories only small text state is kept (XMP / PP3 sidecars, configs, logs).

What the harness logged (nothing else exists): program channel = the parsed program + rationale of every round (not the
raw completion); GUI channel = the last 3000 characters of every reply + the executed actions + a screenshot per step;
closed models = tokens and USD per call (`cost/`); open models = no token counts.

Example (pandas):
```python
import pandas as pd, glob
ep = pd.concat(pd.read_parquet(f) for f in glob.glob('tables/episodes/bench_b1_*__runs__b1t32.parquet'))
ep[ep.in_paper].groupby(['model', 'level'])['pass'].mean()
```

## 3. Raw snapshot

`snapshot_v2/<unit>.tar.zst` (non-image files, original layout, redacted) + `manifests_v2/<unit>.tsv` (path, bytes,
sha256 of the original file, redaction counts). `code__visual-effect-skills` is the full research code base including
every pipeline script that launched the paper's runs (`scripts/pipelines/`) and the day-by-day notes (`docs/resume-*.md`).
