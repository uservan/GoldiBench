"""Validation report of the B-1 sets made by gen_b1.py: settings, every gate's criterion and numbers, drops by reason.
Reads <DATA>/bench_b1_<app>/{tasks/*/program.json, generation_log.jsonl}; writes <DATA>/bench_b1_report.{md,json}.

  python report_b1.py [app ...]   (default: every bench_b1_* set)
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import collections,json,statistics as st,sys
from pathlib import Path
DATA=gbpaths.DATA
GATES=[('C3_total','START→TARGET dE in [6, 30] ([6, 45] for 5 steps); single structural tool: own bound (sharpen, blur … 3)'),('C2_repeat','render twice: dE ≤ 0.05'),
       ('V3','mean-shift and Reinhard shortcuts fail'),('C4_necessary','dropping any step fails'),
       ('V2','×0.9 / ×1.1 pass, ×0.5 / ×1.5 fail'),('coverage','operation use ≤ cap')]

def reason_gate(s):
    for key,pre in [('C3_total','C3 total'),('C2_repeat','C2'),('V3','V-3'),('C4_necessary','C4'),('V2','V-2'),('coverage','coverage')]:
        if s.startswith(pre):return key
    return 'ok' if s=='ok' else ('error' if s.startswith('error') else 'other')

def q(xs):
    xs=sorted(xs)
    return '–' if not xs else f'{xs[0]:.2f} / {st.median(xs):.2f} / {xs[-1]:.2f}'

def app_report(app):
    d=DATA/f'bench_b1_{app}'
    tasks=[json.loads(p.read_text()) for p in sorted((d/'tasks').glob('*/program.json'))]
    log=[json.loads(l) for l in open(d/'generation_log.jsonl')] if (d/'generation_log.jsonl').exists() else []
    att=[r for r in log if 'attempt' in r and not r.get('intermediate')]
    revs=[r for r in log if r.get('intermediate')]
    drops=collections.Counter(reason_gate(r['status']) for r in att if r['status']!='ok')
    c=lambda t,k:t['checks'].get(k,{})
    nec=[min(v['closeness'] for v in c(t,'C4_necessary').values()) for t in tasks if t['steps']>1]
    nec_de=[min(v['de'] for v in c(t,'C4_necessary').values()) for t in tasks if t['steps']>1]
    v2=lambda f:[c(t,'V2')[f]['de'] for t in tasks if 'de' in c(t,'V2').get(f,{})]
    v3=lambda n:[c(t,'V3')[n]['closeness'] for t in tasks]
    usage=collections.Counter(m for t in tasks for m in t['program'])
    return {'app':app,'tasks':len(tasks),'attempts':len(att),'accept_rate':round(len(tasks)/len(att),3) if att else None,
            'drops':dict(drops),'slots_failed':sum(r['status'].startswith('slot failed') for r in log),
            'by_steps':dict(sorted(collections.Counter(t['steps'] for t in tasks).items())),
            'by_generator':dict(collections.Counter(t['generator'] for t in tasks)),
            'usage':dict(usage),'unused_ops':[],
            'numbers':{'C3 total dE':q([c(t,'C3_total')['de'] for t in tasks]),'C2 repeat dE':q([c(t,'C2_repeat')['de'] for t in tasks]),
                       'C4 min dE without one step':q(nec_de),'C4 max closeness without one step':q([x for x in nec]),
                       'V-2 ×0.9 dE':q(v2('0.9')),'V-2 ×1.1 dE':q(v2('1.1')),'V-2 ×0.5 dE':q(v2('0.5')),'V-2 ×1.5 dE':q(v2('1.5')),
                       'V-3 mean-shift closeness':q(v3('mean_shift')),'V-3 Reinhard closeness':q(v3('reinhard')),
                       'SSIM START–TARGET':q([t['checks'].get('ssim_start_target',1) for t in tasks]),
                       'interval clipped (tasks)':str(sum(bool(t['interval_clipped']) for t in tasks)),
                       'attempts per task':q([t['attempts'] for t in tasks])},
            'examples':[{'id':t['task_id'],'steps':t['steps'],'gen':t['generator'],'intent':t['intent'],'order':t['order']} for t in tasks[:6]]}

def main():
    apps=sys.argv[1:] or sorted(p.name[len('bench_b1_'):] for p in DATA.glob('bench_b1_*') if p.is_dir())
    reps=[app_report(a) for a in apps]
    import ops_darktable  # noqa: library sizes for the unused-operation column
    for r in reps:
        import importlib;lib=importlib.import_module(f"ops_{r['app']}");r['unused_ops']=[m for m in lib.OPS if m not in r['usage']]
    L=['# B-1 validation report (gen_b1.py)','','## Settings','',
       '- Generator: LLM sees START + operation library + manual workflow page + manual page per operation; writes intent, '
       'k operations in order, an interval per field. Qwen3.5-397B and GLM-5.3 alternate (blocks of 5 slots). Values drawn '
       'uniformly in the intervals.','- Step counts: k = 1..5, equal quota. Pass rule: closeness ≥ 0.75 and dE ≤ 4.','',
       '| gate | criterion |','|---|---|']+[f'| {g} | {c} |' for g,c in GATES]
    L+=['','## Per app','','| app | tasks | attempts | accept % | steps 1/2/3/4/5 | qwen35 / glm53 | unused ops |','|---|---|---|---|---|---|---|']
    for r in reps:
        L.append(f"| {r['app']} | {r['tasks']} | {r['attempts']} | {100*(r['accept_rate'] or 0):.0f} | "
                 +'/'.join(str(r['by_steps'].get(k,0)) for k in range(1,6))+f" | {r['by_generator'].get('qwen35',0)} / {r['by_generator'].get('glm53',0)} | {', '.join(r['unused_ops']) or '–'} |")
    L+=['','## Drops by gate (attempts)','','| app | '+' | '.join(g for g,_ in GATES)+' | error |','|---|'+'---|'*(len(GATES)+1)]
    for r in reps:L.append(f"| {r['app']} | "+' | '.join(str(r['drops'].get(g,0)) for g,_ in GATES)+f" | {r['drops'].get('error',0)} |")
    L+=['','## Check numbers on accepted tasks (min / median / max)','','| check | '+' | '.join(r['app'] for r in reps)+' |','|---|'+'---|'*len(reps)]
    for k in reps[0]['numbers'] if reps else []:L.append(f'| {k} | '+' | '.join(r['numbers'][k] for r in reps)+' |')
    L+=['','## Example intents','']
    for r in reps:
        for e in r['examples'][:3]:L.append(f"- **{r['app']} {e['id']}** ({e['steps']} steps, {e['gen']}): {e['intent']} → {', '.join(e['order'])}")
    (DATA/'bench_b1_report.md').write_text('\n'.join(L)+'\n');(DATA/'bench_b1_report.json').write_text(json.dumps(reps,indent=1))
    print('\n'.join(L))

if __name__=='__main__':main()
