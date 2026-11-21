"""Column-width example figure (user 2026-11-10: was full width, too big for its content) for the human-agreement paragraph of Sec. 4.1 (placeholder until the raters' answers are
in; user 2026-11-10: "人工的部分先占位或者例子图"). Five (TARGET, CANDIDATE) pairs from the human-study pool, one per
application, with the metric's verdict, the two VLM judges' verdicts and an empty raters' row.
Data: visual_effect_data/v5/pairs_<app>.jsonl (candidates, closeness, pass), v5/v6_judgments.jsonl (VLM judges),
      bench_b1_<app>/tasks/<task>/target.png.
When the annotations are in, fill RATERS (task, cand) -> (yes votes, n).
  <python with matplotlib> scripts/paper/fig_human_pairs.py [--out ...pdf]"""
import argparse,collections,json,os
from matplotlib.patches import FancyBboxPatch
from figstyle import *
# 2026-11-14: serif (STIX) as the CVPR body and Figs. strength / scaling
plt.rcParams.update({'font.family':'serif','font.serif':['STIXGeneral'],'mathtext.fontset':'stix'})

# 2026-11-14 (user): middle two were near the threshold (closeness ~0.71) and looked like their targets; replaced by
# clearly wrong candidates that both VLM judges still pass (RawTherapee x1.5, GIMP x0.5; user: GIMP b072 drop did not work)
PAIRS=[('darktable','b009','x1.1'),('rawtherapee','b003','x1.5'),('gimp','b033','x0.5'),('inkscape','b014','agentL2')]
RATERS={}   # (app, task, cand) -> (yes, n), from the human study
JN={'glm53':'GLM','glm5':'GLM','qwen':'Qwen','qwen35':'Qwen'}

def what(r):
    if r['kind']=='scale':return '×'+(r.get('as') or f"x{r['arg']:g}")[1:]   # strength actually rendered
    if r['kind']=='drop':return 'step left out'
    return f"agent ({r['arg']})"

def main(out):
    P={(r['app'],r['task_id'],r['cand']):r for a in APPS for r in map(json.loads,open(f'{D}/v5/pairs_{a}.jsonl'))}
    J=collections.defaultdict(lambda:collections.defaultdict(list))
    for l in open(f'{D}/v5/v6_judgments.jsonl'):
        j=json.loads(l);J[(j['app'],j['task_id'],j['cand'])][JN.get(j['judge'],j['judge'])].append(j['reaches'])
    n=len(PAIRS);lw=0.5;cw=(3.33-lw-0.02)/n;iw=0.66;H=2.0
    c=Canvas(3.33,H);ax=c.ax;y_t=H-0.04-iw;y_c=y_t-0.04-iw
    yt=y_c-0.06;ys=[yt,yt-0.135,yt-0.27,yt-0.405]
    for lab,y,va in [('TARGET',y_t+iw/2,'center'),('CANDI-\nDATE',y_c+iw/2,'center')]+[(l,y,'top') for l,y in zip(['Edit','Metric','VLMs','Raters'],ys)]:
        ax.text(0.02,y,lab,ha='left',va=va,fontsize=6.2,fontweight='semibold',color=INK,linespacing=0.95)
    for i,(a,t,cand) in enumerate(PAIRS):
        r=P[(a,t,cand)];x0=lw+i*cw;xm=x0+cw/2;ok=r['pass'];col=PASS if ok else FAIL
        c.img(square(load(f'{D}/bench_b1_{a}/tasks/{t}/target.png',400)),xm-iw/2,y_t,iw)
        c.img(square(load(r['path'],400)),xm-iw/2,y_c,iw,ec=col,lw=1.0)
        ax.text(xm,ys[0],what(r),ha='center',va='top',fontsize=6,color=INK2)
        ax.text(xm,ys[1],f"{'pass' if ok else 'fail'} {r['closeness']:.2f}",ha='center',va='top',fontsize=6.2,color=col,fontweight='semibold')
        jd=J[(a,t,cand)];jd={k:[x for x in v if x is not None] for k,v in jd.items()};votes=[sum(v)*2>len(v) for v in jd.values() if v]   # unparsed verdicts (null) left out
        txt=f"{sum(votes)}/{len(votes)} pass"
        ax.text(xm,ys[2],txt,ha='center',va='top',fontsize=6,color=INK if all(v==ok for v in votes) else FAIL)
        rv=RATERS.get((a,t,cand))
        ax.text(xm,ys[3],f'{rv[0]}/{rv[1]} pass' if rv else '–/3',ha='center',va='top',fontsize=6,color=INK if rv else MUTED)
        print(a,t,cand,r['closeness'],ok,dict(jd))
    c.save(out)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=os.path.join(PAPER,'fig','human_pairs.pdf'));main(ap.parse_args().out)
