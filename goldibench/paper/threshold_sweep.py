"""Pass rate under other pass rules (Supp.): closeness >= t (t in 0.6..0.9) with dE <= 4, and dE <= 4 alone.
Same aggregation as main_tables.py (per app: mean over seeds, missing episodes fail; then mean over the five apps).
Legality is kept: a program episode with violations, or a GUI episode stopped by a gate, fails under every rule.
Reports, per channel and level, every model's pass rate per rule and Kendall tau of the model order vs. the default rule.
  python scripts/paper/threshold_sweep.py   -> logs/threshold_sweep.json"""
import json,os,statistics as st,itertools
from concurrent.futures import ThreadPoolExecutor
import sys;sys.path.insert(0,os.path.dirname(__file__))
from main_tables import D,APPS,LEVELS,PROG,GUI,ntasks
RULES=[('c0.60',0.60,4),('c0.70',0.70,4),('c0.75',0.75,4),('c0.80',0.80,4),('c0.90',0.90,4),('dE4',None,4)]
def ok(c,de,t,b):return de is not None and de<=b and (t is None or c>=t)
def prog():
    E={}
    for a in APPS:
        for r in ['b1t32']+[f'b1t32_s{s}' for s in range(1,5)]:
            f=f'{D}/bench_b1_{a}/runs/{r}/scores.json'
            if not os.path.exists(f):continue
            for e in json.load(open(f))['episodes']:
                legal=not e.get('violations');E.setdefault((a,e['model'],e['level'],r),[]).append((legal,e['closeness'],e.get('de00'),bool(e['pass'])))
    return E,{a:ntasks(f'{D}/bench_b1_{a}/tasks.jsonl') for a in APPS},[x[1] for x in PROG if x]
def gui():
    jobs=[];ms={row[1] for row in GUI if row}
    for a in APPS:
        for r in ['b1g100_s0','b1g100_s1','b1g100_s2','b1g100_closed']:
            R=f'{D}/bench_b1_{a}_gui/runs/{r}'
            for d in os.listdir(R) if os.path.isdir(R) else []:
                t=d.split('_',2)
                if len(t)==3 and t[1] in LEVELS and t[2] in ms:jobs.append((a,r,t[2],t[1],f'{R}/{d}/episode.json'))
    def rd(p):
        try:ev=json.load(open(p)).get('eval') or {}
        except Exception:return None
        return ('gate' not in ev and ev.get('closeness') is not None,float(ev.get('closeness') or 0),ev.get('de00'),bool(ev.get('pass')))
    with ThreadPoolExecutor(64) as ex:vals=list(ex.map(lambda j:rd(j[4]),jobs))
    E={}
    for (a,r,m,lv,_),v in zip(jobs,vals):
        E.setdefault((a,m,lv,r),[])
        if v:E[a,m,lv,r].append(v)
    return E,{a:ntasks(f'{D}/bench_b1_{a}_gui/tasks.jsonl') for a in APPS},[x[1] for x in GUI if x]
def rates(E,N,models):
    out={};chk=[]
    for m in models:
        for lv in LEVELS:
            per=[]
            for a in APPS:
                runs=[v for (aa,mm,l,r),v in E.items() if aa==a and mm==m and l==lv]
                if not runs:break
                per.append({k:st.mean(100*sum(1 for g,c,de,p in eps if g and ok(c,de,t,b))/N[a][lv] for eps in runs) for k,t,b in RULES})
                chk+= [(g and ok(c,de,0.75,4))==p for eps in runs for g,c,de,p in eps]
            if len(per)==len(APPS):out[m,lv]={k:st.mean(x[k] for x in per) for k,_,_ in RULES}
    return out,sum(chk)/max(1,len(chk))
def tau(x,y):
    s=0;n=0
    for i,j in itertools.combinations(range(len(x)),2):
        a=(x[i]-x[j]);b=(y[i]-y[j])
        if a==0 or b==0:continue
        s+=1 if a*b>0 else -1;n+=1
    return s/n if n else float('nan')
res={}
for ch,f in (('program',prog),('gui',gui)):
    E,N,models=f();R,agree=rates(E,N,models);print(ch,'default rule reproduces stored pass on %.4f of episodes'%agree)
    res[ch]={}
    for lv in LEVELS:
        ms=[m for m in models if (m,lv) in R];base=[R[m,lv]['c0.75'] for m in ms]
        row={k:{'mean':round(st.mean(R[m,lv][k] for m in ms),1),'max':round(max(R[m,lv][k] for m in ms),1),
                'tau_vs_0.75':round(tau(base,[R[m,lv][k] for m in ms]),2),
                'max_abs_change':round(max(abs(R[m,lv][k]-R[m,lv]['c0.75']) for m in ms),1)} for k,_,_ in RULES}
        res[ch][lv]=row;print(ch,lv,json.dumps(row))
    res[ch]['models']={f'{m}|{lv}':{k:round(v,1) for k,v in R[m,lv].items()} for (m,lv) in R}
json.dump(res,open('logs/threshold_sweep.json','w'),indent=1)
