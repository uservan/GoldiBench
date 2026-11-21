"""Numbers of the judge experiments of paper Sec. 2 (Fig. 2c / 2d, Supp. A.4-A.6: Tab. app-e3, app-e3x, app-c1),
computed from the judgments (released ones by default, or new runs of psbench_judge.py / psbench_ref.py).

Aggregation as in the paper: E3 pools judges, repeats and tasks per candidate (per group in Tab. app-e3); E3-X and C1
average the three repeats per task, then over tasks, with a task-level bootstrap 95 % CI (4000 resamples, seed 0);
E3-X leaves out candidates whose program the app's ranges clipped. Judgments with passed = None (no valid reply after
three attempts) are left out.

  python -m goldibench.judge.motivation_numbers [--check]
      [--e3 FILE] [--e3-ref FILE] [--e3-metrics FILE] [--e3x FILE] [--c1 FILE]
--check compares every number with the value printed in the paper and exits 1 on a mismatch.
"""
import argparse, collections, csv, json, statistics as st, sys
from goldibench.judge import common as C

PAPER = {
    # Tab. app-e3, judge without reference (five judges, pooled), explicit / vague
    'e3 noref explicit': {'end': 82, 'half': 45, 'over': 52, 'opposite': 25, 'naive_global': 42, 'identity': 3},
    'e3 noref vague': {'end': 86, 'half': 64, 'over': 63, 'opposite': 26, 'naive_global': 32, 'identity': 8},
    # Sec. 2 / Fig. 2c: pooled over task types
    'e3 noref pooled': {'end': 84, 'half': 55, 'over': 58},
    # Tab. app-e3, judge shown the reference (two judges, pooled)
    'e3 ref pooled': {'end': 91, 'near_0.9': 86, 'near_1.1': 88, 'half': 22, 'over': 20, 'opposite': 5, 'naive_global': 22, 'identity': 1},
    'e3 ref glm53': {'half': 36, 'over': 34}, 'e3 ref qwen35': {'half': 8, 'over': 6},
    # Tab. app-e3, CIEDE2000 <= 3 against END
    'e3 ciede<=3': {'end': 100, 'near_0.9': 87, 'near_1.1': 90, 'half': 18, 'over': 5, 'opposite': 2, 'naive_global': 22, 'identity': 5},
    # Tab. app-e3x: identity, x0.5 [CI], END, our metric x0.5 / END
    'e3x glm53 explicit': {'identity': 16, 'half': (98, 96, 100), 'end': 98, 'metric half': 0, 'metric end': 100},
    'e3x glm53 vague': {'identity': 10, 'half': (82, 74, 90), 'end': 92, 'metric half': 0, 'metric end': 100},
    'e3x qwen35 explicit': {'identity': 0, 'half': (59, 48, 70), 'end': 88, 'metric half': 0, 'metric end': 100},
    'e3x qwen35 vague': {'identity': 1, 'half': (65, 53, 76), 'end': 92, 'metric half': 0, 'metric end': 100},
    'e3x half pooled': 76,   # Sec. 2: "the judge passes 76 % of them"
    # Tab. app-c1: start image / image model / reference result, Qwen3.5 / GLM-5.3
    'c1 easy': {'identity': (4, 17), 'edit': (64, 76), 'end': (92, 96)},
    'c1 medium': {'identity': (5, 11), 'edit': (47, 62), 'end': (89, 83)},
    'c1 hard': {'identity': (5, 14), 'edit': (96, 86), 'end': (97, 93)},
    'c1 n': {'easy': 200, 'medium': 203, 'hard': 197},
}


def rows(path, cond=None):
    for j in map(json.loads, open(path)):
        if j.get('passed') is None: continue
        if cond and j.get('condition') != cond: continue
        yield j


def pooled(js, key):
    c = collections.defaultdict(list)
    for j in js: c[key(j)].append(j['passed'])
    return {k: round(100 * sum(v) / len(v)) for k, v in c.items()}


def per_task(path, man, by, clipped_out=False):
    """(judge, by, candidate) -> (mean, lo, hi) over tasks of the per-task mean over repeats."""
    cells = collections.defaultdict(lambda: collections.defaultdict(list))
    for j in rows(path):
        r = man[(j['task_id'], j['candidate'])]
        if clipped_out and r.get('clipped') == 'True': continue
        cells[(j['judge'], r[by], j['candidate'])][j['task_id']].append(j['passed'])
    return {k: (C.boot(st.mean(x) for x in v.values()), len(v)) for k, v in cells.items()}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--check', action='store_true')
    ap.add_argument('--e3', default=str(C.MOT / 'e3/judgments.jsonl')); ap.add_argument('--e3-ref', default=str(C.MOT / 'e3/judgments_ref.jsonl'))
    ap.add_argument('--e3-metrics', default=str(C.MOT / 'e3/reference_metrics.csv')); ap.add_argument('--e3x', default=str(C.MOT / 'e3x/judgments.jsonl'))
    ap.add_argument('--c1', default=str(C.MOT / 'c1/judgments.jsonl')); a = ap.parse_args()
    fail = []; R = round

    print('## E3 judge stress test (Tab. app-e3, Fig. 2c): pass rate %')
    g = pooled(rows(a.e3), lambda j: (j['group'], j['candidate'])); p = pooled(rows(a.e3), lambda j: j['candidate'])
    cand = ['end', 'near_0.9', 'near_1.1', 'half', 'over', 'opposite', 'naive_global', 'identity']
    print(f"{'scorer':22s} " + ' '.join(f'{c:>12s}' for c in cand))
    print(f"{'judge, no ref (e / v)':22s} " + ' '.join(f"{(str(g[('explicit', c)]) + ' / ' + str(g[('vague', c)])) if ('explicit', c) in g else '-':>12s}" for c in cand))
    for grp in ('explicit', 'vague'):
        for c, v in PAPER[f'e3 noref {grp}'].items(): C.check(f'e3 noref {grp} {c}', g[(grp, c)], v, fail)
    for c, v in PAPER['e3 noref pooled'].items(): C.check(f'e3 noref pooled {c}', p[c], v, fail)
    ref = pooled(rows(a.e3_ref, 'ref'), lambda j: j['candidate']); refj = pooled(rows(a.e3_ref, 'ref'), lambda j: (j['judge'], j['candidate']))
    print(f"{'judge, with ref':22s} " + ' '.join(f'{ref.get(c, "-"):>12}' for c in cand))
    for c, v in PAPER['e3 ref pooled'].items(): C.check(f'e3 ref {c}', ref[c], v, fail)
    for jd in ('glm53', 'qwen35'):
        for c, v in PAPER[f'e3 ref {jd}'].items(): C.check(f'e3 ref {jd} {c}', refj[(jd, c)], v, fail)
    m = collections.defaultdict(list)
    for r in csv.DictReader(open(a.e3_metrics)): m[r['candidate']].append(float(r['de00_mean']) <= 3)
    ci = {k: R(100 * sum(v) / len(v)) for k, v in m.items()}
    print(f"{'CIEDE2000 <= 3':22s} " + ' '.join(f'{ci.get(c, "-"):>12}' for c in cand))
    for c, v in PAPER['e3 ciede<=3'].items(): C.check(f'e3 ciede {c}', ci[c], v, fail)
    print(f"pooled no ref: END {p['end']}, x0.5 {p['half']}, x3 {p['over']};  with ref: GLM-5.3 x0.5/x3 {refj[('glm53', 'half')]}/{refj[('glm53', 'over')]},"
          f" Qwen3.5 {refj[('qwen35', 'half')]}/{refj[('qwen35', 'over')]}")
    wj = pooled(rows(a.e3), lambda j: (j['judge'], j['group'], j['candidate']))
    wm = [v for (jd, gr, c), v in wj.items() if c in ('half', 'over')]
    print(f'wrong-magnitude (x0.5, x3) pass per judge x task type: {min(wm)}-{max(wm)} %')
    nr = pooled(rows(a.e3_ref, 'noref'), lambda j: j['candidate'])
    print(f"near-correct without reference: x0.9 {nr.get('near_0.9')}, x1.1 {nr.get('near_1.1')}")

    print('\n## E3-X darktable (Tab. app-e3x, Fig. 2d): pass rate % [95 % CI]')
    man = {(r['task_id'], r['candidate']): r for r in csv.DictReader(open(C.MOT / 'e3x/candidates_manifest.csv'))}
    t = per_task(a.e3x, man, 'group', clipped_out=True)
    met = collections.defaultdict(list)
    for r in man.values():
        if r.get('clipped') != 'True': met[(r['group'], r['candidate'])].append(r['metric_pass'] == 'True')
    halves = []
    print(f"{'judge':8s} {'instruction':11s} {'identity':>8s} {'x0.5':>14s} {'END':>5s}  metric x0.5 / END")
    for jd in ('glm53', 'qwen35'):
        for grp in ('explicit', 'vague'):
            (ih, _, _), _ = t[(jd, grp, 'identity')]; (hm, hl, hh), _ = t[(jd, grp, 'half')]; (em, _, _), _ = t[(jd, grp, 'end')]
            mh, me = R(100 * st.mean(met[(grp, 'half')])), R(100 * st.mean(met[(grp, 'end')])); halves.append(hm)
            print(f'{jd:8s} {grp:11s} {R(ih):8d} {R(hm):4d} [{R(hl)}, {R(hh)}] {R(em):5d}  {mh} / {me}')
            want = PAPER[f'e3x {jd} {grp}']
            for k, got in (('identity', R(ih)), ('half', (R(hm), R(hl), R(hh))), ('end', R(em)), ('metric half', mh), ('metric end', me)):
                C.check(f'e3x {jd} {grp} {k}', got, want[k], fail)
    C.check('e3x half pooled', R(st.mean(halves)), PAPER['e3x half pooled'], fail)
    print(f'x0.5 pooled over judges and instructions: {R(st.mean(halves))} %')

    print('\n## C1 editing without the software (Tab. app-c1): PSBench judge pass %, Qwen3.5 / GLM-5.3')
    man = {(r['task_id'], r['candidate']): r for r in csv.DictReader(open(C.MOT / 'c1/candidates_manifest.csv'))}
    t = per_task(a.c1, man, 'difficulty')
    print(f"{'difficulty':12s} {'start image':>12s} {'image model':>12s} {'reference':>12s}")
    for d in ('easy', 'medium', 'hard'):
        n = t[('qwen35', d, 'edit')][1]; C.check(f'c1 n {d}', n, PAPER['c1 n'][d], fail)
        vals = {c: (R(t[('qwen35', d, c)][0][0]), R(t[('glm53', d, c)][0][0])) for c in ('identity', 'edit', 'end')}
        print(f'{d + " (" + str(n) + ")":12s} ' + ' '.join(f'{f"{x} / {y}":>12s}' for x, y in vals.values()))
        for c, v in vals.items(): C.check(f'c1 {d} {c}', v, PAPER[f'c1 {d}'][c], fail)
    t = per_task(a.c1, man, 'e1_class')
    print('image model by task-phrasing class (Qwen3.5 / GLM-5.3): ' + ', '.join(
        f"{cl} {R(t[('qwen35', cl, 'edit')][0][0])} / {R(t[('glm53', cl, 'edit')][0][0])}" for cl in sorted({k[1] for k in t if k[1]})))

    print(f'\n{"ALL MATCH THE PAPER" if not fail else "MISMATCHES:"}')
    for f in fail: print('  ' + f)
    if a.check and fail: sys.exit(1)


if __name__ == '__main__':
    main()
