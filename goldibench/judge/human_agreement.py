"""Paper Sec. 4.1 (Tab. judge) and Supp. C.1: metric, VLM judges and humans on the 913 pairs of the human study.

Inputs (released, supporting/validation_v5 and motivation_repo):
  v5/pairs_<app>.jsonl         the pairs (v5_pairs.py): candidate kind, strength actually rendered ('as'), dE, closeness, pass
  v5/v6_judgments.jsonl        the VLM judges (v6_judge.py), 3 repeats per pair (rows with reaches = None are failed calls
                               and are left out; the majority of the valid repeats is the judge's verdict)
  v5/human_ratings.jsonl       the human ratings from the annotation page (v5_page.py), one row per rater x item
  motivation/v5/annotation_key.csv   item id -> (app, task, candidate, dE, closeness, pass)
A human 'yes' (the candidate reaches TARGET's effect) is a pass; with several raters the majority is used (ties: no pass).
Candidates are grouped by the strength actually rendered (v5_pairs.py falls back to a milder factor when the requested
one runs into a parameter bound). Known answer: exact (the hidden program), x0.9, x1.1 should pass; x0.5, x1.5 and drop
(one step left out) should fail. Boundary: x0.75 / x1.25. Agent: real L2 / L3 results of the program channel.
Best-matching threshold: the closeness threshold t (dE <= 4 kept) with the highest agreement with humans, on a 0.001
grid; 95 % CI from 1000 bootstrap resamples of the pairs (seed 0).

  python -m goldibench.judge.human_agreement [--check] [--ratings FILE] [--judgments FILE]
--check compares every number with the value printed in the paper and exits 1 on a mismatch.
"""
import argparse, collections, csv, json, random, sys
import numpy as np
from goldibench.judge import common as C

JUDGES = [('glm53', 'GLM'), ('qwen35', 'Qwen'), ('gpt61sol', 'GPT'), ('opus55', 'Opus')]
SHOULD = {'exact': True, 'x0.9': True, 'x1.1': True, 'x0.5': False, 'x1.5': False, 'drop': False}
PAPER = {   # Tab. judge: known-answer columns (exact .. drop), all, human agreement
    'n': {'exact': 15, 'x0.9': 80, 'x1.1': 65, 'x0.5': 96, 'x1.5': 33, 'drop': 59, 'all': 348, 'agree': 913},
    'GLM': [100, 100, 100, 38, 6, 14, 59, 57], 'Qwen': [100, 99, 100, 60, 18, 49, 72, 68],
    'GPT': [100, 100, 97, 83, 55, 76, 86, 75], 'Opus': [100, 100, 98, 81, 79, 63, 86, 72],
    'Humans': [80, 74, 86, 85, 73, 76, 80, None], 'Metric': [100, 100, 100, 100, 100, 100, 100, 73],
    # Sec. 4.1 text and Supp. C.1
    'metric agree': 72.5, 'away from boundary': {'Metric': 82, 'GPT': 81, 'Opus': 78, 'Qwen': 73, 'GLM': 60},
    'agent agree metric': 90, 'boundary agree range': (48, 58), 'boundary judge pass range': (71, 99),
    'boundary metric pass range': (31, 36), 'agent dE>6 open': (11, 43), 'agent dE>6 closed': (1, 6),
    'agent dE>6 humans': 2, 'agent dE>6 metric': 0, 'threshold': 0.71, 'threshold ci': (0.60, 0.83),
    'humans pass all': 38, 'humans pass by closeness': {(0.5, 0.6): 30, (0.7, 0.75): 51, (0.8, 0.9): 67},
    'per app metric agree range': (67, 80), 'same degree open': (41, 79), 'same degree closed': (17, 45),
    'pairs by kind': {'exact': 15, 'scale': 598, 'drop': 59, 'agent': 241}, 'metric pass all': 33,
}


def load(ratings, judgments):
    key = {r['item_id']: r for r in csv.DictReader(open(C.MOT / 'v5' / 'annotation_key.csv'))}
    pairs = {(r['app'], r['task_id'], r['cand']): r for a in C.APPS for r in map(json.loads, open(C.V5 / f'pairs_{a}.jsonl'))}
    by_pair = {(r['app'], r['task_id'], r['cand']): i for i, r in key.items()}
    hv = collections.defaultdict(list)
    for r in map(json.loads, open(ratings)):
        if r['done'] in ('yes', 'no'): hv[r['item_id']].append(r['done'] == 'yes')
    H = {i: sum(v) > len(v) / 2 for i, v in hv.items()}
    votes = collections.defaultdict(list)
    for j in map(json.loads, open(judgments)):
        if j.get('reaches') is None: continue
        votes[(j['judge'], by_pair[(j['app'], j['task_id'], j['cand'])])].append(j)
    S = {name: {} for _, name in JUDGES}; D = {name: {} for _, name in JUDGES}
    for (jd, i), v in votes.items():
        name = dict(JUDGES).get(jd)
        if name is None: continue
        S[name][i] = sum(x['reaches'] for x in v) > len(v) / 2
        D[name][i] = collections.Counter(x['degree'] for x in v).most_common(1)[0][0]
    S['Humans'] = H; S['Metric'] = {i: r['pass'] == 'True' for i, r in key.items()}

    def bucket(i):
        p = pairs[(key[i]['app'], key[i]['task_id'], key[i]['cand'])]
        if p['kind'] == 'exact': return 'exact'
        if p['kind'] == 'scale': return p.get('as') or f"x{p['arg']:g}"
        return 'drop' if p['kind'] == 'drop' else 'agent'
    B = {i: bucket(i) for i in key}
    return key, pairs, H, S, D, B


def pct(xs): return 100 * sum(xs) / len(xs) if xs else float('nan')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--check', action='store_true')
    ap.add_argument('--ratings', default=str(C.V5 / 'human_ratings.jsonl')); ap.add_argument('--judgments', default=str(C.V5 / 'v6_judgments.jsonl'))
    a = ap.parse_args(); fail = []; R = round
    key, pairs, H, S, D, B = load(a.ratings, a.judgments)
    agree = lambda s, ids: pct([S[s][i] == H[i] for i in ids if i in S[s] and i in H])

    print(f'## Tab. judge: {len(key)} pairs, {len(H)} with a human verdict')
    cols = list(SHOULD) + ['all', 'agree']
    n = {b: sum(B[i] == b for i in key) for b in SHOULD}; n['all'] = sum(n.values()); n['agree'] = len(H)
    print(f"{'':8s}" + ''.join(f'{c:>7s}' for c in cols)); print(f"{'n':8s}" + ''.join(f'{n[c]:7d}' for c in cols))
    for c in cols: C.check(f'n {c}', n[c], PAPER['n'][c], fail)
    for s in [x for _, x in JUDGES] + ['Humans', 'Metric']:
        vals = [R(pct([S[s][i] == SHOULD[b] for i in key if B[i] == b and i in S[s]])) for b in SHOULD]
        vals.append(R(pct([S[s][i] == SHOULD[B[i]] for i in key if B[i] in SHOULD and i in S[s]])))
        vals.append(None if s == 'Humans' else R(agree(s, key)))
        print(f'{s:8s}' + ''.join(f'{"--" if v is None else v:>7}' for v in vals))
        for c, v, w in zip(cols, vals, PAPER[s]): C.check(f'{s} {c}', v, w, fail)

    print('\n## Sec. 4.1 / Supp. C.1')
    m = agree('Metric', key); print(f'metric agrees with humans on {m:.1f} % of the pairs'); C.check('metric agree', R(m, 1), PAPER['metric agree'], fail)
    bnd = [i for i in key if B[i] in ('x0.75', 'x1.25')]; away = [i for i in key if i not in set(bnd)]
    aw = {s: R(agree(s, away)) for s in PAPER['away from boundary']}; print('agreement away from the boundary:', aw)
    for s, v in PAPER['away from boundary'].items(): C.check(f'away {s}', aw[s], v, fail)
    ag = [i for i in key if B[i] == 'agent']; x = R(agree('Metric', ag)); print(f'agreement on agent outputs (metric): {x}'); C.check('agent agree', x, PAPER['agent agree metric'], fail)
    ba = [R(agree(s, bnd)) for s in ['Metric'] + [x for _, x in JUDGES]]; print('agreement at x0.75 / x1.25 (metric, judges):', ba)
    C.check('boundary agree range', (min(ba), max(ba)), PAPER['boundary agree range'], fail)
    bp = {(s, b): R(pct([S[s][i] for i in key if B[i] == b])) for s in [x for _, x in JUDGES] + ['Metric', 'Humans'] for b in ('x0.75', 'x1.25')}
    print('pass at x0.75 / x1.25:', {s: (bp[(s, 'x0.75')], bp[(s, 'x1.25')]) for s in [x for _, x in JUDGES] + ['Metric', 'Humans']})
    jp = [bp[(s, b)] for _, s in JUDGES for b in ('x0.75', 'x1.25')]; mp = [bp[('Metric', b)] for b in ('x0.75', 'x1.25')]
    C.check('boundary judge pass', (min(jp), max(jp)), PAPER['boundary judge pass range'], fail); C.check('boundary metric pass', (min(mp), max(mp)), PAPER['boundary metric pass range'], fail)
    far = {lv: [i for i in ag if key[i]['cand'] == f'agent{lv}' and float(key[i]['de']) > 6] for lv in ('L2', 'L3')}
    fp = {(s, lv): R(pct([S[s][i] for i in far[lv]])) for s in S for lv in far}
    print('agent outputs with dE > 6, pass % (L2, L3):', {s: (fp[(s, 'L2')], fp[(s, 'L3')]) for s in S})
    for grp, names in (('open', ['GLM', 'Qwen']), ('closed', ['GPT', 'Opus'])):
        v = [fp[(s, lv)] for s in names for lv in far]; C.check(f'agent dE>6 {grp}', (min(v), max(v)), PAPER[f'agent dE>6 {grp}'], fail)
    allfar = far['L2'] + far['L3']
    for s, k in (('Humans', 'agent dE>6 humans'), ('Metric', 'agent dE>6 metric')): C.check(k, R(pct([S[s][i] for i in allfar])), PAPER[k], fail)
    print(f"  pooled L2+L3: humans {R(pct([S['Humans'][i] for i in allfar]))}, metric {R(pct([S['Metric'][i] for i in allfar]))}")

    ids = [i for i in key if i in H]
    c = np.array([float(key[i]['closeness']) for i in ids]); d = np.array([float(key[i]['de']) for i in ids]); h = np.array([H[i] for i in ids])
    ts = np.round(np.arange(0.30, 1.0, 0.001), 3)

    def best(idx):
        cc, dd, hh = c[idx], d[idx], h[idx]
        return ts[int(np.argmax([(((cc >= t) & (dd <= 4)) == hh).sum() for t in ts]))]
    t0 = best(np.arange(len(ids))); rng = random.Random(0)
    bs = sorted(best(np.array([rng.randrange(len(ids)) for _ in ids])) for _ in range(1000))
    lo, hi = bs[24], bs[974]
    print(f'best-matching threshold {t0:.3f} (95 % CI {lo:.2f}-{hi:.2f}); paper: closeness >= 0.75')
    C.check('threshold', R(float(t0), 2), PAPER['threshold'], fail); C.check('threshold ci', (R(float(lo), 2), R(float(hi), 2)), PAPER['threshold ci'], fail)

    x = R(pct(list(H.values()))); print(f'humans pass {x} % of the pairs'); C.check('humans pass all', x, PAPER['humans pass all'], fail)
    for (l, u), w in PAPER['humans pass by closeness'].items():
        v = R(pct([H[i] for i in ids if l <= float(key[i]['closeness']) < u])); print(f'  humans pass at closeness {l}-{u}: {v} %'); C.check(f'closeness {l}-{u}', v, w, fail)
    pa = {app: R(agree('Metric', [i for i in key if key[i]['app'] == app])) for app in C.APPS}; print('metric agreement per app:', pa)
    C.check('per app range', (min(pa.values()), max(pa.values())), PAPER['per app metric agree range'], fail)
    sm = {(s, b): R(pct([D[s][i] == 'same' for i in key if B[i] == b and i in D[s]])) for _, s in JUDGES for b in ('x0.5', 'x1.5')}
    print("judges answering 'same strength' on x0.5 / x1.5:", {s: (sm[(s, 'x0.5')], sm[(s, 'x1.5')]) for _, s in JUDGES})
    for grp, names in (('open', ['GLM', 'Qwen']), ('closed', ['GPT', 'Opus'])):
        v = [sm[(s, b)] for s in names for b in ('x0.5', 'x1.5')]; C.check(f'same degree {grp}', (min(v), max(v)), PAPER[f'same degree {grp}'], fail)
    kinds = collections.Counter(pairs[(key[i]['app'], key[i]['task_id'], key[i]['cand'])]['kind'] for i in key)
    print('pairs by kind:', dict(kinds), f"metric pass {R(pct([S['Metric'][i] for i in key]))} %")
    for k, v in PAPER['pairs by kind'].items(): C.check(f'kind {k}', kinds[k], v, fail)
    C.check('metric pass all', R(pct([S['Metric'][i] for i in key])), PAPER['metric pass all'], fail)

    print(f'\n{"ALL MATCH THE PAPER" if not fail else "MISMATCHES:"}')
    for f in fail: print('  ' + f)
    if a.check and fail: sys.exit(1)


if __name__ == '__main__':
    main()
