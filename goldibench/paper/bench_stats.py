"""Tab. bench-stats (Supp. B, dataset statistics) from the public dataset: dev / test split, operation-library size (Ops),
median number of parameter values per task (Val.), median CIEDE2000 between START and TARGET, share of generated
candidates kept (Kept), tasks in the GUI channel, and the PlayRaw real-edit row.
Dev / test, Kept and PlayRaw need the optional parts of the dataset (scripts/download_data.sh --provenance --playraw);
without them they print as --.
  Kept = candidates that passed every check / candidates (generation_log.jsonl entries that are not intermediate
  revisions; = Cand. and Kept of Tab. drops). PlayRaw Kept = kept / (kept + drops.jsonl).
  python goldibench/paper/bench_stats.py"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import collections, importlib, json, os, statistics as st
import gbpaths

D = gbpaths.DATA
APPS = [('darktable', 'darktable'), ('rawtherapee', 'RawTherapee'), ('gimp', 'GIMP'), ('inkscape', 'Inkscape'), ('blender', 'Blender')]


def kept(a):
    f = D / f'bench_b1_{a}' / 'generation_log.jsonl'
    if not f.exists():
        return '--'
    fin = [r for r in map(json.loads, open(f)) if not r.get('intermediate')]
    return f"{100 * sum(r.get('status') == 'ok' for r in fin) / len(fin):.0f}%"


def main():
    mf = D / 'bench_b1_final' / 'manifest.jsonl'
    split = collections.Counter((m['app'], m['split']) for m in map(json.loads, open(mf))) if mf.exists() else None
    print(f"{'App':14s} {'Dev / test':>10s} {'Ops':>4s} {'Val.':>5s} {'dE':>5s} {'Kept':>5s} {'GUI':>4s}")
    for a, name in APPS:
        T = [json.loads(l) for l in gbpaths.open_tasks(D / f'bench_b1_{a}' / 'tasks.jsonl')]
        ops = len(importlib.import_module(f'ops_{a}').OPS)
        val = st.median(sum(len(m) for m in t['program'].values()) for t in T)
        de = st.median(t['start_target_de00'] for t in T)
        gui = sum(1 for _ in open(D / f'bench_b1_{a}_gui' / 'tasks.jsonl')) // 3      # one line per task and level
        dt = f"{split[a, 'dev']} / {split[a, 'test']}" if split else '--'
        print(f'{name:14s} {dt:>10s} {ops:4d} {val:5g} {de:5.1f} {kept(a):>5s} {gui:4d}')
    b2 = D / 'bench_b2_darktable'
    if (b2 / 'tasks.jsonl').exists():   # PlayRaw real edits: Ops = darktable modules used by the replayed edits
        T = [json.loads(l) for l in open(b2 / 'tasks.jsonl')]
        drops = sum(1 for _ in open(b2 / 'drops.jsonl')) if (b2 / 'drops.jsonl').exists() else 0
        ops = len({m for t in T for m in t['program']})
        val = st.median(sum(len(m) for m in t['program'].values()) for t in T)
        de = st.median(t['start_target_de00'] for t in T)
        print(f"{'PlayRaw (real)':14s} {f'{len(T)} tasks':>10s} {ops:4d} {val:5g} {de:5.1f} {f'{100 * len(T) / (len(T) + drops):.0f}%':>5s} {'--':>4s}")
    else:
        print(f"{'PlayRaw (real)':14s} {'--':>10s}   (scripts/download_data.sh --playraw)")


if __name__ == '__main__':
    main()
