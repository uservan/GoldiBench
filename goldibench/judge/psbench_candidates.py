"""E3 (paper Sec. 2, Supp. A.4): sample PSBench tasks by task-phrasing class and build scripted candidate results.

Tasks: 30 explicit + 30 vague (missing tool / missing values) PSBench tasks, sampled (seed 0) from the tasks on which
the three task-phrasing voters agreed unanimously or by majority (motivation/benchmark_audit/split_full.csv).
Candidates, from START and PSBench's reference result END (delta = END - START, pixel space):
  end (author reference), identity (START), half (START + 0.5 delta), over (START + 3 delta), opposite (START - delta),
  naive_global (one global Lab mean / std transfer towards END: right direction, no local work);
  psbench_ref.py adds near_0.9 / near_1.1 (START + 0.9 / 1.1 delta).
Writes <out>/candidates/<task>/<cand>.png and <out>/candidates_manifest.csv (same columns as the released manifest).
The released manifest (supporting/motivation_repo/.../motivation/e3/candidates_manifest.csv) lists the paper's 60 tasks.

  python -m goldibench.judge.psbench_candidates [--out <GOLDIBENCH_JUDGE_OUT>/e3] [--n-per-class 30] [--seed 0]
"""
from pathlib import Path
import argparse, csv, hashlib, json, random
import numpy as np
from PIL import Image
from skimage import color
from goldibench.judge import common as C

VAGUE = {'vague_missing_tool', 'vague_missing_values'}


def load(task):
    """START and END of a PSBench task as float RGB in [0, 1] (END resized to START when they differ in scale)."""
    d = C.PSDATA / task; t = json.loads((d / f'{task}.json').read_text())
    start = Image.open(d / t['resources']['input_file']).convert('RGB'); end = Image.open(d / t['reference_output']['expected_file']).convert('RGB')
    if end.size != start.size: end = end.resize(start.size, Image.Resampling.LANCZOS)   # 2 hard tasks differ only in scale
    return np.asarray(start, np.float32) / 255, np.asarray(end, np.float32) / 255


def naive_global(start, end):
    """One global Lab mean/std transfer from START towards END: right direction, no local work."""
    a, b = color.rgb2lab(start), color.rgb2lab(end)
    out = (a - a.mean((0, 1))) / (a.std((0, 1)) + 1e-6) * b.std((0, 1)) + b.mean((0, 1))
    return np.clip(color.lab2rgb(out), 0, 1)


def save(arr, path):
    path.parent.mkdir(parents=True, exist_ok=True); Image.fromarray((np.clip(arr, 0, 1) * 255).round().astype(np.uint8)).save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def candidates(start, end):
    delta = end - start
    return {'end': end, 'identity': start, 'half': start + 0.5 * delta, 'over': start + 3 * delta, 'opposite': start - delta,
            'naive_global': naive_global(start, end)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--n-per-class', type=int, default=30); ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', default=str(C.OUT / 'e3')); ap.add_argument('--tasks', nargs='*', help='only these task ids (quick check)')
    args = ap.parse_args(); out = Path(args.out)
    inv = {r['task_id']: r for r in csv.DictReader(open(C.MOT / 'benchmark_audit/task_inventory.csv', encoding='utf-8')) if r['benchmark'] == 'PSBench'}
    split = [r for r in csv.DictReader(open(C.MOT / 'benchmark_audit/split_full.csv'))
             if r['benchmark'] == 'PSBench' and r['agree'] in ('all', 'majority')]
    rng = random.Random(args.seed); picked = []
    for group, keep in [('explicit', lambda c: c == 'explicit'), ('vague', lambda c: c in VAGUE)]:
        pool = sorted((r for r in split if keep(r['class'])), key=lambda r: r['task_id'])
        picked += [dict(r, group=group) for r in rng.sample(pool, min(args.n_per_class, len(pool)))]
    print(json.dumps({'sampled': sorted(r['task_id'] for r in picked)}))
    if args.tasks: picked = [r for r in picked if r['task_id'] in set(args.tasks)]
    manifest = []
    for r in picked:
        task = r['task_id']; start, end = load(task)
        for name, arr in candidates(start, end).items():
            p = out / 'candidates' / task / f'{name}.png'
            manifest.append(dict(task_id=task, group=r['group'], e1_class=r['class'], difficulty=inv[task]['difficulty'], candidate=name,
                                 path=str(p), sha256_16=save(arr, p), mean_abs_diff_to_end=round(float(np.abs(np.clip(arr, 0, 1) - end).mean()), 5)))
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'candidates_manifest.csv').open('w', newline='') as h:
        w = csv.DictWriter(h, list(manifest[0])); w.writeheader(); w.writerows(manifest)
    tiers = {}
    for r in picked: tiers.setdefault(r['group'], {}).setdefault(inv[r['task_id']]['difficulty'], 0); tiers[r['group']][inv[r['task_id']]['difficulty']] += 1
    print(json.dumps({'tasks': len(picked), 'candidates': len(manifest), 'tiers': tiers, 'out': str(out)}))


if __name__ == '__main__':
    main()
