"""Human study (paper Sec. 4.1, Supp. C.1): build the (TARGET, CANDIDATE) pairs that humans and VLM judges rate.

Per app 30 frozen tasks (seeded, 6 per step count) x 5-6 candidates, chosen to straddle the pass boundary:
  x0.75, x1.25                      the whole program scaled (make_pilot.scaled)
  x0.5 or x1.5 (alternating)        clearly under / over
  x0.9 or x1.1 (alternating)        near the target (should pass)
  agent L2                          a real L2 result of the program channel's main run (b1t32), random model
  drop step or agent L3 (alt.)      one step left out (multi-step tasks) / a real L3 result
plus every 10th task an attention check: CANDIDATE = TARGET (exact).
A scaling that runs into a parameter bound falls back to a milder factor (x1.25 -> x1.15 -> x0.85, x1.5 -> x1.35 -> x0.5,
x1.1 -> x1.05 -> x0.95, ...; the strength actually rendered is stored as 'as'); a missing agent result falls back to x0.9.
Per pair: dE00, closeness, the pass verdict and the detail closeness dc (dc = 1 - |D(cand) - D(target)| / |D(start) -
D(target)|, D = mean |Laplacian| of L*; reported only).
Agent candidates are the episode's final render (final_rerender.png); when the runs were restored from the logs dataset
(scripts/restore_runs.sh, no images) the final program is re-rendered, as score.py does.
Writes <out>/<app>/<task>_<cand>.png and <out>/pairs_<app>.jsonl (resumable). The paper's pairs are released
(supporting/validation_v5/v5/pairs_<app>.jsonl + the candidate images).

  BENCH_APP=<app> BENCH_SET=bench_b1_<app> python -m goldibench.judge.v5_pairs [--out <GOLDIBENCH_JUDGE_OUT>/v5] [--workers 8] [--limit N]
"""
import argparse, json, random, shutil, threading, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import color
from goldibench.judge import common as C

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'bench'))
import make_pilot as mp, ops  # noqa: E402

MODELS = ['qwen35', 'glm53', 'dsv41', 'step37', 'nemo35', 'qwen35_0.8b', 'qwen35_2b', 'qwen35_4b', 'qwen35_9b', 'qwen35_27b', 'qwen35_35b_a3b', 'qwen35_122b_a10b']


def detail(p):
    L = color.rgb2lab(np.asarray(Image.open(p).convert('RGB'), np.float32) / 255)[..., 0]; return float(np.abs(ndimage.laplace(L)).mean())


def plan(tasks, rng):
    """Task sample and candidate specs: (name, kind, arg)."""
    by = {}
    for t in tasks: by.setdefault(min(len(t['program']), 5), []).append(t)
    pick = [t for k in sorted(by) for t in rng.sample(sorted(by[k], key=lambda t: t['task_id']), min(6, len(by[k])))]
    out = []
    for i, t in enumerate(sorted(pick, key=lambda t: t['task_id'])):
        c = [('x0.75', 'scale', 0.75), ('x1.25', 'scale', 1.25), ('x0.5', 'scale', 0.5) if i % 2 else ('x1.5', 'scale', 1.5),
             ('x0.9', 'scale', 0.9) if i % 2 == 0 else ('x1.1', 'scale', 1.1), ('agentL2', 'agent', 'L2')]
        c.append(('drop', 'drop', rng.choice(sorted(t['program']))) if i % 2 == 0 and len(t['program']) > 1 else ('agentL3', 'agent', 'L3'))
        if i % 10 == 0: c.append(('check', 'exact', None))
        out.append((t, c))
    return out


def has_final(ep):
    """The episode has a final render (the paper's runs), or, restored without images, a final program that score.py
    would re-render (at least one round with a program, no render failure)."""
    if (ep / 'final_rerender.png').exists(): return True
    if not (ep / 'episode.json').exists(): return False
    e = json.loads((ep / 'episode.json').read_text())
    return any('program' in x for x in e['rounds']) and not any(x.get('error') == 'render failed' for x in e['rounds'])


def agent_render(t, lvl, m, f):
    ep = mp.OUT / 'runs/b1t32' / t['task_id'] / f'{lvl}_{m}'
    if (ep / 'final_rerender.png').exists(): shutil.copy(ep / 'final_rerender.png', f); return True
    e = json.loads((ep / 'episode.json').read_text()); r = [x for x in e['rounds'] if 'program' in x]
    if not r or any(x.get('error') == 'render failed' for x in e['rounds']): return False
    ops.render(t['source_path'], r[-1]['program'], f); return True


def make(t, name, kind, arg, f, rng):
    """Render / copy one candidate to f. Returns a provenance dict, or None when it cannot be made."""
    d = mp.OUT / 'tasks' / t['task_id']
    if kind == 'exact': shutil.copy(d / 'target.png', f); return {}
    if kind == 'agent':
        ms = [m for m in MODELS if has_final(mp.OUT / 'runs/b1t32' / t['task_id'] / f'{arg}_{m}')]
        if not ms: return None
        m = rng.choice(ms)
        return {'model': m} if agent_render(t, arg, m, f) else None
    if kind == 'drop': p = ({x: v for x, v in t['program'].items() if x != arg}, False)
    else: p = mp.scaled(t['program'], arg)
    if p[1]:
        for alt in {0.75: [0.85], 1.25: [1.15, 0.85], 0.5: [0.6], 1.5: [1.35, 0.5], 0.9: [0.95], 1.1: [1.05, 0.95]}.get(arg, []):
            p = mp.scaled(t['program'], alt)
            if not p[1]: name = f'x{alt}'; break
        else: return None
    ops.render(t['source_path'], p[0], f); return {'as': name}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--workers', type=int, default=8); ap.add_argument('--seed', type=int, default=20261107)
    ap.add_argument('--out', default=str(C.OUT / 'v5')); ap.add_argument('--limit', type=int, help='first N candidates only (quick check)')
    a = ap.parse_args()
    out = Path(a.out) / ops.APP; out.mkdir(parents=True, exist_ok=True); pf = Path(a.out) / f'pairs_{ops.APP}.jsonl'
    done = {(r['task_id'], r['cand']) for r in map(json.loads, open(pf))} if pf.exists() else set()
    tasks = [json.loads(l) for l in C.gbpaths.open_tasks(mp.OUT / 'tasks.jsonl')]; rng = random.Random(f'{a.seed}|{ops.APP}')
    jobs = [(t, c) for t, cs in plan(tasks, rng) for c in cs]
    jobs = [j for j in jobs[:a.limit] if (j[0]['task_id'], j[1][0]) not in done]; lock = threading.Lock()

    def one(j):
        t, (name, kind, arg) = j; f = out / f"{t['task_id']}_{name}.png"; r2 = random.Random(f"{a.seed}|{t['task_id']}|{name}")
        prov = make(t, name, kind, arg, f, r2)
        if prov is None:   # fallback: x0.9 (near the target, should pass)
            p = mp.scaled(t['program'], 0.9)
            if p[1]: print(t['task_id'], name, 'skipped', flush=True); return
            ops.render(t['source_path'], p[0], f); prov = {'as': 'x0.9'}
        d = mp.OUT / 'tasks' / t['task_id']; ls, lt, lr = mp.lab(d / 'start.png'), mp.lab(d / 'target.png'), mp.lab(f)
        d0, dd = mp.de(ls, lt), mp.de(lr, lt); Ds, Dt, Dr = detail(d / 'start.png'), detail(d / 'target.png'), detail(f)
        row = {'app': ops.APP, 'task_id': t['task_id'], 'steps': len(t['program']), 'cand': name, 'kind': kind, 'arg': arg, **prov,
               'path': str(f), 'de': round(dd, 3), 'de0': round(d0, 3), 'closeness': round(1 - dd / d0, 3), 'pass': mp.passed(dd, d0),
               'dc': (round(1 - abs(Dr - Dt) / abs(Ds - Dt), 3) if abs(Ds - Dt) > 1e-6 else None)}
        with lock: open(pf, 'a').write(json.dumps(row) + '\n')
        print(t['task_id'], name, row['pass'], row['closeness'], flush=True)
    with ThreadPoolExecutor(a.workers) as ex: list(ex.map(one, jobs))
    print('ALL DONE', pf)


if __name__ == '__main__':
    main()
