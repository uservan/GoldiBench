"""Main results as two half-column tables (user 2026-11-14): program channel and GUI channel, every model, per level L1 / L2 / L3
the pass rate (%) and the mean closeness. Same rule for both channels: per app the mean over the seeds that exist, then the mean
over the five apps (each weighs the same). Missing / hung episodes count as failures with closeness 0.
Program: runs b1t32, b1t32_s1..s4 of bench_b1_<app> (closed models: b1t32 only), scores.json episodes.
GUI: runs b1g100_s0..2 (all GUI agents 3 seeds since 2026-11-16; general VLMs GLM / DeepSeek / Step / Nemotron: s0 only) and b1g100_closed, 100 steps.
Closeness: mean, and mean clipped at -1 (GUI results can move far from TARGET). Output: logs/main_tables.json, .md."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import json,os,statistics as st
from concurrent.futures import ThreadPoolExecutor
D=str(gbpaths.DATA)
APPS=('darktable','rawtherapee','gimp','inkscape','blender');LEVELS=('L1','L2','L3')
PROG=[('Qwen3.5-0.8B','qwen35_0.8b'),('Qwen3.5-2B','qwen35_2b'),('Qwen3.5-4B','qwen35_4b'),('Qwen3.5-9B','qwen35_9b'),
      ('Qwen3.5-27B','qwen35_27b'),('Qwen3.5-35B-A3B','qwen35_35b_a3b'),('Qwen3.5-122B-A10B','qwen35_122b_a10b'),
      ('Qwen3.5-397B-A17B','qwen35'),None,('GLM-5.3-Flash','glm53'),None,('DeepSeek-V4.1-Flash','dsv41'),None,('Step-3.7-Flash','step37'),
      None,('Nemotron-3.5-Super-VL','nemo35'),None,('Claude Opus 5.5','opus55'),None,('GPT-6.1','gpt61sol')]   # 2026-11-14 user: a rule between families
GUI=[('Qwen3.5-0.8B','qwen35gui_0.8b'),('Qwen3.5-2B','qwen35gui_2b'),('Qwen3.5-4B','qwen35gui_4b'),('Qwen3.5-9B','qwen35gui_9b'),
     ('Qwen3.5-27B','qwen35gui_27b'),('Qwen3.5-35B-A3B','qwen35gui_35b_a3b'),('Qwen3.5-122B-A10B','qwen35gui_122b'),
     ('Qwen3.5-397B-A17B','qwen35gui_397b'),None,('GLM-5.3-Flash','glm53gui'),None,('DeepSeek-V4.1-Flash','dsv41gui'),None,
     ('Step-3.7-Flash','step37gui'),None,('Nemotron-3.5-Super-VL','nemo35gui'),None,('UI-TARS-2B','uitars_2b'),('UI-TARS-7B','uitars_7b'),('UI-TARS-72B','uitars_72b'),
     ('UI-TARS-1.5-7B','uitars15_7b'),None,('OpenCUA-7B','opencua_7b'),('OpenCUA-32B','opencua_32b'),('OpenCUA-72B','opencua_72b'),None,
     ('GUI-Owl-1.5-32B','guiowl15_32b'),None,('EvoCUA-32B','evocua_32b'),None,('Holo4-35B','holo4_35b'),('Holo4-27B','holo4_27b'),None,
     ('Claude Opus 5.5','opus55gui'),None,('GPT-6.1','gpt61gui')]

def ntasks(path):
    n={}
    for l in open(path):
        t=json.loads(l)
        if 'level' in t or 'id' in t:lv=t.get('level') or t['id'].split('_')[-1];n[lv]=n.get(lv,0)+1
        else:   # program channel: one line per task, all three levels
            for lv in LEVELS:n[lv]=n.get(lv,0)+1
    return n

def agg(eps_by_run,n):
    """eps_by_run: list (one per seed run) of lists of (pass, closeness) for one app / model / level; pad to n tasks."""
    p,c,cc=[],[],[]
    for eps in eps_by_run:
        eps=list(eps)+[(False,0.0)]*(n-len(eps))
        p.append(100*st.mean(x for x,_ in eps));c.append(st.mean(y for _,y in eps));cc.append(st.mean(max(-1.0,y) for _,y in eps))
    return st.mean(p),st.mean(c),st.mean(cc)

def prog():
    out={}
    for a in APPS:
        n=ntasks(f'{D}/bench_b1_{a}/tasks.jsonl');runs={}
        for r in ['b1t32']+[f'b1t32_s{s}' for s in range(1,5)]:
            f=f'{D}/bench_b1_{a}/runs/{r}/scores.json'
            if not os.path.exists(f):continue
            for e in json.load(open(f))['episodes']:runs.setdefault((e['model'],e['level'],r),[]).append((bool(e['pass']),float(e['closeness'])))
        for row in PROG:
            if not row:continue
            for lv in LEVELS:
                er=[v for (m,l,r),v in runs.items() if m==row[1] and l==lv]
                if er:out[row[1],lv,a]=(agg(er,n[lv]),len(er))
    return out

def read(p):
    try:ev=json.load(open(p)).get('eval') or {};return bool(ev.get('pass')),float(ev.get('closeness') or 0.0)
    except Exception:return None

def gui():
    jobs=[];ms={row[1] for row in GUI if row}
    for a in APPS:
        for r in ['b1g100_s0','b1g100_s1','b1g100_s2','b1g100_closed']:
            R=f'{D}/bench_b1_{a}_gui/runs/{r}'
            for d in os.listdir(R) if os.path.isdir(R) else []:
                t=d.split('_',2)
                if len(t)==3 and t[1] in LEVELS and t[2] in ms:jobs.append((a,r,t[2],t[1],f'{R}/{d}/episode.json'))
    with ThreadPoolExecutor(64) as ex:vals=list(ex.map(lambda j:read(j[4]),jobs))
    runs={}
    for (a,r,m,lv,_),v in zip(jobs,vals):
        runs.setdefault((a,m,lv,r),[])
        if v:runs[a,m,lv,r].append(v)
    out={}
    for a in APPS:
        n=ntasks(f'{D}/bench_b1_{a}_gui/tasks.jsonl')
        for row in GUI:
            if not row:continue
            for lv in LEVELS:
                er=[v for (aa,m,l,r),v in runs.items() if aa==a and m==row[1] and l==lv]
                if er:out[row[1],lv,a]=(agg(er,n[lv]),len(er))
    return out

def table(rows,cells):
    res={}
    for row in rows:
        if not row:continue
        for lv in LEVELS:
            v=[cells[row[1],lv,a][0] for a in APPS if (row[1],lv,a) in cells]
            if len(v)==len(APPS):res[row[1],lv]=tuple(st.mean(x[i] for x in v) for i in range(3))
    return res

PAPER=__import__('os').environ.get('GOLDIBENCH_PAPER', 'paper_tex')
APPN={'darktable':'dt','rawtherapee':'RT','gimp':'GIMP','inkscape':'Ink','blender':'Blender'}

def num(v,d):
    if abs(v)<0.5*10**-d:v=0.0
    return f'{v:.{d}f}' if v>=0 else f'$-${abs(v):.{d}f}'

def bold_cols(rows,vals):
    """per column: the unique maximum (as printed) is bold"""
    best={}
    for j in range(len(next(iter(vals.values())))):
        col=[vals[r][j] for r in vals];mx=max(col)
        if col.count(mx)==1:best[j]=mx
    return best

def main_tex(rows,T,label,caption):
    vals={}
    for row in rows:
        if row and (row[1],'L1') in T:
            m=row[1];vals[m]=[round(T[m,lv][0],1) for lv in LEVELS]+[round(T[m,lv][2],2) for lv in LEVELS]
    best=bold_cols(rows,vals)
    L=[r'\begin{table}[t]',r'  \centering',f'  \\caption{{{caption}}}',f'  \\label{{{label}}}',
       r'  \setlength{\tabcolsep}{4pt}',r'  \resizebox{\linewidth}{!}{%',r'  \begin{tabular}{@{}l ccc @{\hspace{6pt}} ccc@{}}',r'    \toprule',
       r'    & \multicolumn{3}{c}{pass (\%)} & \multicolumn{3}{c}{closeness} \\',r'    \cmidrule(r{6pt}){2-4}\cmidrule{5-7}',
       r'    Model & L1 & L2 & L3 & L1 & L2 & L3 \\',r'    \midrule']
    for row in rows:
        if not row:L.append(r'    \midrule');continue
        if row[1] not in vals:continue
        cells=[]
        for j,v in enumerate(vals[row[1]]):
            t=num(v,1 if j<3 else 2);cells.append(f'\\textbf{{{t}}}' if best.get(j)==v else t)
        L.append(f'    {row[0]:<22} & '+' & '.join(cells)+r' \\')
    L+=[r'    \bottomrule',r'  \end{tabular}}',r'\end{table}']   # 2026-11-14 user: scaled to the column width
    return '\n'.join(L)+'\n'

def app_tex(rows,cells,label,caption):
    L=[r'\begin{table*}[t]',r'  \centering',r'  \footnotesize',f'  \\caption{{{caption}}}',f'  \\label{{{label}}}',
       r'  \setlength{\tabcolsep}{3.4pt}',r'  \begin{tabular}{@{}l '+r' @{\hspace{7pt}} '.join(['ccccc']*3)+'@{}}',r'    \toprule',
       r'    & \multicolumn{5}{c}{L1} & \multicolumn{5}{c}{L2} & \multicolumn{5}{c}{L3} \\',
       r'    \cmidrule(r{7pt}){2-6}\cmidrule(r{7pt}){7-11}\cmidrule{12-16}',
       r'    Model & '+' & '.join([APPN[a] for a in APPS]*3)+r' \\',r'    \midrule']
    for row in rows:
        if not row:L.append(r'    \midrule');continue
        if (row[1],'L1',APPS[0]) not in cells:continue
        L.append(f'    {row[0]:<22} & '+' & '.join(f'{cells[row[1],lv,a][0][0]:.0f}' if (row[1],lv,a) in cells else '--' for lv in LEVELS for a in APPS)+r' \\')
    L+=[r'    \bottomrule',r'  \end{tabular}',r'\end{table*}']
    return '\n'.join(L)+'\n'

def main():
    pc=prog();gc=gui();P=table(PROG,pc);G=table(GUI,gc)
    json.dump({'program':{f'{m}|{lv}':v for (m,lv),v in P.items()},'gui':{f'{m}|{lv}':v for (m,lv),v in G.items()},
               'program_per_app':{f'{m}|{lv}|{a}':v for (m,lv,a),v in pc.items()},'gui_per_app':{f'{m}|{lv}|{a}':v for (m,lv,a),v in gc.items()}},
              open(f'{D}/logs/main_tables.json','w'),indent=1)
    os.makedirs(f'{PAPER}/tab',exist_ok=True)
    CL=r'closeness: mean over episodes of $1-\Delta E(\text{RESULT},\text{TARGET})/\Delta E(\text{START},\text{TARGET})$, each clipped at $-1$'
    open(f'{PAPER}/tab/main_prog.tex','w').write(main_tex(PROG,P,'tab:main-prog',
        r'\textbf{Program channel.} Pass rate and mean closeness per level, mean over the five applications (each weighs the same; '
        r'100 tasks per application and level). Open models: mean of 5 seeds; closed models: one run. '+CL+'.'))
    open(f'{PAPER}/tab/main_gui.tex','w').write(main_tex(GUI,G,'tab:main-gui',
        r'\textbf{GUI channel} (100 steps). As Tab.~\ref{tab:main-prog} on the GUI tasks (53--100 per application and level). '
        r'GUI agents and Qwen3.5: mean of 3 seeds; GLM-5.3, DeepSeek-V4.1, Step-3.7, Nemotron-3.5 (OSWorld screenshot-to-pyautogui agent) and '
        r'closed models: one run. Episodes in which the agent left the application hung count as failures.'))
    open(f'{PAPER}/tab/app_prog.tex','w').write(app_tex(PROG,pc,'tab:app-prog',
        r'\textbf{Program channel per application}: pass rate (\%), seeds as in Tab.~\ref{tab:main}. '
        r'dt: darktable, RT: RawTherapee, Ink: Inkscape.'))
    open(f'{PAPER}/tab/app_gui.tex','w').write(app_tex(GUI,gc,'tab:app-gui',
        r'\textbf{GUI channel per application}: pass rate (\%), 100 steps, seeds as in Tab.~\ref{tab:main}. '
        r'Tasks per level: darktable 53, RawTherapee 100, GIMP 100, Inkscape 73, Blender 100.'))
    print('wrote tab/main_prog.tex tab/main_gui.tex tab/app_prog.tex tab/app_gui.tex')
    import main_combined;main_combined.main()   # merged double-column tab/main.tex (2026-11-14)

if __name__=='__main__':main()
