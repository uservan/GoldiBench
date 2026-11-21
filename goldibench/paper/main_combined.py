"""Merged main table (user 2026-11-14: program + GUI in one double-column table, pass and closeness at L1-L3, a family
column with one rule between families; pass rates shaded on a blue scale, negative closeness in red). Reads
tab/main_prog.tex and tab/main_gui.tex (written by main_tables.py) and writes tab/main.tex, keeping its caption."""
import os,re
PAPER=os.environ.get('GOLDIBENCH_PAPER', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'paper_out'))
for _d in ('tab', 'fig'): os.makedirs(os.path.join(PAPER, _d), exist_ok=True)
# (family, [(label in the table, row name in main_prog / main_gui)])
FAM=[('Qwen3.5',[(s,f'Qwen3.5-{s}') for s in ('0.8B','2B','4B','9B','27B','35B-A3B','122B-A10B','397B-A17B')]),
     ('GLM-5.3',[('Flash','GLM-5.3-Flash')]),('DeepSeek-V4.1',[('Flash','DeepSeek-V4.1-Flash')]),('Step-3.7',[('Flash','Step-3.7-Flash')]),
     ('Nemotron-3.5',[('Super-VL','Nemotron-3.5-Super-VL')]),
     ('UI-TARS',[('2B','UI-TARS-2B'),('7B','UI-TARS-7B'),('72B','UI-TARS-72B'),('1.5-7B','UI-TARS-1.5-7B')]),
     ('OpenCUA',[('7B','OpenCUA-7B'),('32B','OpenCUA-32B'),('72B','OpenCUA-72B')]),
     ('GUI-Owl-1.5',[('32B','GUI-Owl-1.5-32B')]),('EvoCUA',[('32B','EvoCUA-32B')]),('Holo4',[('35B','Holo4-35B'),('27B','Holo4-27B')]),
     ('Claude',[('Opus 5.5','Claude Opus 5.5')]),('GPT',[('6.1','GPT-6.1')])]
def rows(f):
    R={}
    for l in open(f):
        if '&' in l and 'multicolumn' not in l and not l.strip().startswith('Model'):
            c=[x.strip() for x in l.strip().rstrip('\\').strip().split('&')]
            if len(c)==7:R[c[0]]=c[1:]
    return R
def _num(c):
    m=re.search(r'(\$-\$)?([0-9.]+)',c);return None if not m else (-1 if m.group(1) else 1)*float(m.group(2))
def style(cells):
    """pass rates shaded in one blue, depth ~ sqrt(pass) (2026-11-15 user: L2 and L3 must differ visibly and the size trend show;
    a linear scale left every L2 / L3 cell near white); no other colour"""
    out=[]
    for j,c in enumerate(cells):
        v=_num(c)
        if v is None:out.append(c)
        elif j<3:out.append(f'\\cellcolor{{CliffBlue!{round(50*(max(v,0)/100)**0.5)}}}{c}')   # shade ~ sqrt(pass): small L2 / L3 rates stay visible
        else:out.append(c)
    return out
HEAD=r"""  \label{tab:main}
  \small\setlength{\tabcolsep}{3.5pt}\renewcommand{\arraystretch}{0.92}   % 2026-11-15 user: \\small, natural width (no stretch to the page)
  \begin{tabular}{@{}ll ccc@{\hspace{6pt}}ccc@{\hspace{14pt}}ccc@{\hspace{6pt}}ccc@{}}
    \toprule
    & & \multicolumn{6}{c}{Program channel} & \multicolumn{6}{c}{GUI channel} \\
    \cmidrule(r{14pt}){3-8}\cmidrule{9-14}
    & & \multicolumn{3}{c}{pass (\%)} & \multicolumn{3}{c}{closeness} & \multicolumn{3}{c}{pass (\%)} & \multicolumn{3}{c}{closeness} \\
    \cmidrule(r{6pt}){3-5}\cmidrule(r{14pt}){6-8}\cmidrule(r{6pt}){9-11}\cmidrule{12-14}
    Family & Model & L1 & L2 & L3 & L1 & L2 & L3 & L1 & L2 & L3 & L1 & L2 & L3 \\"""
def main():
    old=open(f'{PAPER}/tab/main.tex').read() if os.path.exists(f'{PAPER}/tab/main.tex') else ''
    cap=(old[old.index(r'  \caption{'):old.index(r'  \label{tab:main}')] if r'  \label{tab:main}' in old else
         '  \\caption{Main results: pass rate (\\%) and mean closeness per level, program and GUI channel.}\n')   # no earlier table: default caption
    P=rows(f'{PAPER}/tab/main_prog.tex');G=rows(f'{PAPER}/tab/main_gui.tex');dash=['--']*6
    L=[r'\begin{table*}[t]',r'  \centering',cap.rstrip('\n'),HEAD]
    for fam,ms in FAM:
        L.append(r'    \midrule')
        for i,(lab,n) in enumerate(ms):
            f=(fam if len(ms)==1 else f'\\multirow{{{len(ms)}}}{{*}}{{{fam}}}') if i==0 else ''
            L.append(f'    {f:<28} & {lab:<10} & '+' & '.join(style(P.get(n,dash))+style(G.get(n,dash)))+r' \\')
    L+=[r'    \bottomrule',r'  \end{tabular}',r'\end{table*}']
    open(f'{PAPER}/tab/main.tex','w').write('\n'.join(L)+'\n');print('wrote tab/main.tex')
if __name__=='__main__':main()
