"""Tab. interventions (Sec. 5) and Tab. interventions-full (Supp.): each condition against the default run b1t32 on the
same L2 episodes (task, level, model): pass rate before -> after, McNemar (exact binomial on the discordant pairs), change of
the median closeness and its Wilcoxon signed-rank p. Groups: the twelve open models (open12), Qwen3.5-397B + GLM-5.3 (open2),
Opus 5.5, GPT-6.1.
Program rows read bench_b1_<app>/runs/<run>/scores.json. The GUI row ("Statistics of TARGET - START, GUI": runs
b1g100_closed_tdiff vs b1g100_closed of bench_b1_<app>_gui, closed GUI agents, eval in each episode.json) is
computed when those runs are present.
Output: <data>/logs/interv12.json (also read by fig_teaser.py) and both tables on stdout.
  python goldibench/paper/interventions.py"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import json, os, statistics as st
from scipy.stats import binomtest, wilcoxon

D = str(gbpaths.DATA)
APPS = ['darktable', 'rawtherapee', 'gimp', 'inkscape', 'blender']
OPEN = ['dsv41', 'glm53', 'nemo35', 'step37', 'qwen35', 'qwen35_0.8b', 'qwen35_2b', 'qwen35_4b', 'qwen35_9b', 'qwen35_27b',
        'qwen35_35b_a3b', 'qwen35_122b_a10b']
GROUPS = {'open12': OPEN, 'open2': ['qwen35', 'glm53'], 'opus55': ['opus55'], 'gpt61sol': ['gpt61sol']}
KNOW = ['b1man', 'b1mmt', 'b1mmv', 'b1table', 'b1tdiff', 'b1diffimg']
ROUNDS = ['b1forced', 'b1fb']


def load(run):
    E = {}
    for a in APPS:
        f = f'{D}/bench_b1_{a}/runs/{run}/scores.json'
        if not os.path.exists(f): continue
        for e in json.load(open(f))['episodes']: E[(a, e['task_id'], e['level'], e['model'])] = e
    return E


def stats(P):
    up = sum(1 for b, r in P if r['pass'] and not b['pass']); dn = sum(1 for b, r in P if b['pass'] and not r['pass'])
    d = [r['closeness'] - b['closeness'] for b, r in P]
    return {'n': len(P), 'before': round(100 * st.mean(b['pass'] for b, r in P), 2), 'after': round(100 * st.mean(r['pass'] for b, r in P), 2),
            'up': up, 'dn': dn, 'p': binomtest(up, up + dn).pvalue if up + dn else 1.0,
            'dcl_med': round(st.median(d), 3), 'p_cl': wilcoxon(d).pvalue if any(d) else 1.0}


def paired(base, R, models, level='L2'):
    return [(base[k], R[k]) for k in R if k in base and k[2] == level and k[3] in models]


def gui_load(run, level='L2'):
    """{(app, task, level, model): {'pass', 'closeness'}} from the eval in each GUI episode.json of a run (main_tables.read)."""
    E = {}
    for a in APPS:
        R = f'{D}/bench_b1_{a}_gui/runs/{run}'
        for d in sorted(os.listdir(R)) if os.path.isdir(R) else []:
            t = d.split('_', 2)
            if len(t) == 3 and t[1] == level:
                try: ev = json.load(open(f'{R}/{d}/episode.json')).get('eval') or {}
                except Exception: continue
                E[(a, t[0], t[1], t[2])] = {'pass': bool(ev.get('pass')), 'closeness': float(ev.get('closeness') or 0.0)}
    return E


def star(p): return '^{*}' if p < 0.001 else '^{\\dagger}' if p < 0.01 else '^{\\ddagger}' if p < 0.05 else ''


def main():
    B = load('b1t32'); out = {}
    for run in KNOW + ROUNDS:
        R = load(run)
        if not R: continue
        for g, ms in GROUPS.items():
            P = paired(B, R, ms)
            if P: out[f'{run}|{g}'] = stats(P)
    G = gui_load('b1g100_closed_tdiff')
    if G:
        GB = gui_load('b1g100_closed')
        for m in ('opus55gui', 'gpt61gui'):
            P = paired(GB, G, [m])
            if P: out[f'gui_tdiff|{m}'] = stats(P)
    os.makedirs(f'{D}/logs', exist_ok=True)
    # interv12.json keeps the knowledge / difference rows only (as used by fig_teaser.py); the round rows go to stdout
    json.dump({k: v for k, v in out.items() if k.split('|')[0] in KNOW}, open(f'{D}/logs/interv12.json', 'w'), indent=1)
    names = [('b1man', 'Full application manual'), ('b1mmt', 'Reference card per tool'), ('b1mmv', "Cards + each tool's effect on an image"),
             ('b1table', "Each setting's effect measured on START"), ('b1tdiff', 'Statistics of TARGET - START'),
             ('b1diffimg', 'the same, as an image of the difference'), ('b1forced', 'Four forced rounds, each RESULT shown'),
             ('b1fb', '+ dE to TARGET each round')]
    print(f"{'condition':42s} | " + ' | '.join(f'{g:>34s}' for g in ('open12', 'opus55', 'gpt61sol')))
    for run, name in names:
        cells = []
        for g in ('open12', 'opus55', 'gpt61sol'):
            s = out.get(f'{run}|{g}')
            cells.append('--' if s is None else f"{s['before']:.1f} -> {s['after']:.1f}{star(s['p'])} ({round(s['after'],1)-round(s['before'],1):+.1f}) dcl {s['dcl_med']:+.2f}{star(s['p_cl'])}")
        print(f'{name:42s} | ' + ' | '.join(f'{c:>34s}' for c in cells))
    if not G:
        print('the same, GUI channel: runs b1g100_closed_tdiff not found under bench_b1_<app>_gui/runs')
    else:
        print(f"{'the same, GUI channel':42s} | {'--':>34s} | " + ' | '.join(f'{c:>34s}' for c in (
            (lambda s: '--' if s is None else f"{s['before']:.1f} -> {s['after']:.1f}{star(s['p'])} ({round(s['after'],1)-round(s['before'],1):+.1f}) dcl {s['dcl_med']:+.2f}{star(s['p_cl'])} n={s['n']}")(out.get(f'gui_tdiff|{m}'))
            for m in ('opus55gui', 'gpt61gui'))))


if __name__ == '__main__':
    main()
