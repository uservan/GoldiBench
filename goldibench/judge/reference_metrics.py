"""E3 (paper Sec. 2, Fig. 2c, Supp. A.4): can a reference-based metric separate correct from wrong results where the
reference-free VLM judge cannot?

Every E3 candidate (plus near_0.9 / near_1.1) is rebuilt from START and END and scored against END by CIEDE2000
(mean, p95) and SSIM, at <= 1024 px on the long side (full-resolution CIEDE2000 on large PSBench images takes hours).
The paper's rule: mean CIEDE2000 <= 3.
Output: <GOLDIBENCH_JUDGE_OUT>/e3/reference_metrics.csv (columns as the released file) and a summary next to the VLM
judges' pass rates (released judgments).

  python -m goldibench.judge.reference_metrics [--manifest ...] [--limit-tasks N]
"""
from pathlib import Path
import argparse, csv, json, statistics as st
import numpy as np
from PIL import Image
from skimage import color
from skimage.metrics import structural_similarity
from goldibench.judge import common as C
from goldibench.judge.psbench_candidates import load, naive_global

STRENGTH = {'end': 1.0, 'near_0.9': 0.9, 'near_1.1': 1.1, 'half': 0.5, 'over': 3.0, 'opposite': -1.0, 'identity': 0.0}


def shrink(a, side=1024):
    h, w = a.shape[:2]; k = side / max(h, w)
    if k >= 1: return a
    return np.asarray(Image.fromarray((a * 255).round().astype(np.uint8)).resize((round(w * k), round(h * k)), Image.Resampling.LANCZOS), np.float32) / 255


def scores(arr, end, lab_end):
    arr = np.clip(arr, 0, 1); de = color.deltaE_ciede2000(color.rgb2lab(arr), lab_end)
    return float(de.mean()), float(np.percentile(de, 95)), float(structural_similarity(arr, end, channel_axis=2, data_range=1.0))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--manifest', default=str(C.MOT / 'e3' / 'candidates_manifest.csv'))
    ap.add_argument('--out', default=str(C.OUT / 'e3' / 'reference_metrics.csv')); ap.add_argument('--limit-tasks', type=int)
    a = ap.parse_args()
    man = list(csv.DictReader(open(a.manifest)))
    tasks = {r['task_id']: r for r in man}
    if a.limit_tasks: tasks = dict(list(tasks.items())[:a.limit_tasks])
    rows = []
    for t, meta in tasks.items():
        start, end = (shrink(x) for x in load(t)); delta = end - start; lab_end = color.rgb2lab(end)
        cands = {k: start + s * delta for k, s in STRENGTH.items()}
        cands['naive_global'] = naive_global(start, end)
        for name, arr in cands.items():
            m, p95, ss = scores(arr, end, lab_end)
            rows.append({'task_id': t, 'group': meta['group'], 'difficulty': meta['difficulty'], 'candidate': name,
                         'de00_mean': round(m, 3), 'de00_p95': round(p95, 3), 'ssim': round(ss, 4)})
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', newline='') as h:
        w = csv.DictWriter(h, list(rows[0])); w.writeheader(); w.writerows(rows)
    vlm = {}
    for j in map(json.loads, open(C.MOT / 'e3' / 'judgments.jsonl')):
        if j['passed'] is not None and j['task_id'] in tasks: vlm.setdefault(j['candidate'], []).append(j['passed'])
    print(f"{'candidate':13s} {'dE00 mean (median)':>19s} {'SSIM (median)':>14s} {'pass@dE<=3':>11s} {'VLM pass':>9s}")
    for c in ['end', 'near_0.9', 'near_1.1', 'half', 'over', 'opposite', 'naive_global', 'identity']:
        r = [x for x in rows if x['candidate'] == c]; de = [x['de00_mean'] for x in r]
        tol = 100 * sum(d <= 3.0 for d in de) / len(de); v = vlm.get(c)
        print(f"{c:13s} {st.median(de):19.2f} {st.median(x['ssim'] for x in r):14.3f} {tol:10.0f}% {('%8.0f%%' % (100 * sum(v) / len(v))) if v else '   (n/a)':>9s}")
    print('wrote', out)


if __name__ == '__main__':
    main()
