"""Full-width figure for Sec. 3.1 (data pipeline + dataset statistics; user 2026-11-10: production only, the dataset
statistics merged in, images instead of text lists, CVPR-style). Top: one darktable task (b057) through generation:
START -> generator LLM proposes value ranges (bars: library range, LLM range, sampled value) -> the program rendered
step by step into TARGET -> the strength check (program at x0.5 / x1 / x1.5, only x1 passes). Bottom: the benchmark,
one row per application: example targets, tasks by program length, START-TARGET CIEDE2000.
Data:
  task, intent, ranges, program, renders   bench_b1_darktable/tasks.jsonl, tasks/b057/{start,step1,step2,target}.png
  library ranges                           scripts/bench/ops_darktable.py
  x0.5 / x1.5 renders + scores             paper_figs/darktable_b057/ (make_pilot.scaled + ops.render, as magnitude_curve.py;
                                           rendered by kimgs() when absent, needs darktable: scripts/setup_darktable.sh)
  thumbnails, statistics, split            bench_b1_<app>/tasks.jsonl; dev / test split and real-edit count from
                                           bench_b1_final/manifest.jsonl, bench_b2_darktable (download_data.sh --provenance --playraw;
                                           without them the paper's counts)
  <python with matplotlib> scripts/paper/fig_pipeline.py [--out ...pdf]"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import argparse,collections,importlib,json,os,sys
import numpy as np
from matplotlib.patches import FancyBboxPatch,Rectangle
from figstyle import *

APP,TID='darktable','b057'
THUMBS={'darktable':'b057','rawtherapee':'b024','gimp':'b004','inkscape':'b028','blender':'b036'}
V2={0.5:(6.30,0.52,False),1:(0.0,1.0,True),1.5:(7.42,0.43,False)}   # paper_figs/darktable_b057/README.txt
SPLIT_PAPER={'dev':101,'test':399};REAL_PAPER=160   # Sec. 3 of the paper (used when the manifests are not there)
KDIR=f'{D}/paper_figs/darktable_b057'

def kimgs(t):
    """The x0.5 / x1 / x1.5 renders of the task's program (make_pilot.scaled + ops.render, as magnitude_curve.py) in
    <data>/paper_figs/darktable_b057/; rendered when absent (needs darktable: scripts/setup_darktable.sh), and the scores
    printed to compare with V2."""
    if all(os.path.exists(f'{KDIR}/k{f:g}.png') for f in V2):return
    os.environ.setdefault('BENCH_APP',APP);import ops,make_pilot
    from score import lab,de
    os.makedirs(KDIR,exist_ok=True);tk=f'{D}/bench_b1_{APP}/tasks/{TID}';lt=lab(f'{tk}/target.png');d0=de(lab(f'{tk}/start.png'),lt)
    for f in V2:
        prog=make_pilot.scaled(t['program'],f)[0];o=f'{KDIR}/k{f:g}.png';ops.render(t['source_path'],prog,o)
        e=de(lab(o),lt);print(f'x{f:g}: dE {e:.2f} closeness {1-e/d0:.2f} pass {make_pilot.passed(e,d0)} (paper {V2[f]})')
BARS=[('exposure','exposure','exposure'),('colorbalancergb','vibrance','vibrance'),('vignette','brightness','vignette')]
STEP=['#c9def8','#93bdf0','#5b9be4','#2a78d6','#104281']
TINT='white'

def group(ax,x,y,w,h,title,num=None):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=0.05',fc=TINT,ec='#b9cbe6',lw=0.6,ls=(0,(3,2))))
    if not title:return
    # title centred in the box; the step number sits just left of it
    t=ax.text(x+w/2+(0.08 if num else 0),y+h-0.06,title,ha='center',va='top',fontsize=8.5,fontweight='semibold',color=INK)
    if num:
        r=ax.figure.canvas.get_renderer();bb=t.get_window_extent(r).transformed(ax.transData.inverted())
        ax.text(bb.x0-0.06,y+h-0.06,str(num),ha='right',va='top',fontsize=8.5,fontweight='bold',color=ACC)

def main(out):
    t=next(json.loads(l) for l in gbpaths.open_tasks(f'{D}/bench_b1_{APP}/tasks.jsonl') if json.loads(l)['task_id']==TID)
    lib=importlib.import_module('ops_'+APP).OPS
    T={a:[json.loads(l) for l in gbpaths.open_tasks(f'{D}/bench_b1_{a}/tasks.jsonl')] for a in APPS}
    # the dev / test split manifest and the real-edit set (bench_b2_darktable) are optional parts of the dataset
    # (download_data.sh --provenance --playraw); their counts are taken from the paper when the files are absent
    mf=f'{D}/bench_b1_final/manifest.jsonl'
    if os.path.exists(mf):M=[json.loads(l) for l in open(mf)];sp=collections.Counter(m['split'] for m in M)
    else:M=[t for a in APPS for t in T[a]];sp=SPLIT_PAPER
    rf=f'{D}/bench_b2_darktable/tasks.jsonl'
    real=sum(1 for _ in gbpaths.open_tasks(rf)) if os.path.exists(rf) else REAL_PAPER
    kimgs(t)
    c=Canvas(6.9,2.88);ax=c.ax;tk=f'{D}/bench_b1_{APP}/tasks/{TID}'
    yb,yt=1.2,2.84;g=0.06;xs=[0.03];ws=[1.34,1.3,1.82,2.2]
    for w in ws[:-1]:xs.append(xs[-1]+w+g)
    for i,(x,w,ti) in enumerate(zip(xs,ws,['Start asset','Propose ranges','Sample & render','Check'])):
        group(ax,x,yb,w,yt-yb,ti,i+1)
    for i in range(1,4):c.arrow(xs[i]-g+0.005,xs[i]-0.005,yb+0.62)
    top=yt-0.26
    # 1 start asset
    S=load(f'{tk}/start.png',1000);x=xs[0]+0.08;w=ws[0]-0.16;h=c.img(S,x,top-w*S.height/S.width,w)
    ax.text(x,top-h-0.06,'PSBench photo',ha='left',va='top',fontsize=6.8,color=INK2)
    # 2 propose: LLM chip + range bars
    x=xs[1]+0.08;w=ws[1]-0.16
    ax.add_patch(FancyBboxPatch((x,top-0.38),w,0.38,boxstyle='round,pad=0,rounding_size=0.05',fc='white',ec=ACC,lw=0.7))
    ax.text(x+0.07,top-0.05,'Generator LLM',ha='left',va='top',fontsize=7.4,fontweight='semibold',color=INK)
    ax.text(x+0.07,top-0.19,'“make the portrait pop\nwith a warm, sunlit look”',ha='left',va='top',fontsize=6.6,style='italic',color=INK2,linespacing=1.05)
    for k,(m,f,lab) in enumerate(BARS):
        lo,hi=lib[m][2][f][:2];a,b=t['intervals'][m][f];v=t['program'][m][f]
        y=top-0.6-k*0.24;X=lambda q:x+(q-lo)/(hi-lo)*w
        ax.text(x,y+0.075,lab,ha='left',va='bottom',fontsize=6.8,color=INK)
        ax.add_patch(Rectangle((x,y-0.02),w,0.04,fc='#e2e6ec',ec='none'))
        ax.add_patch(Rectangle((X(a),y-0.045),X(b)-X(a),0.09,fc='#93bdf0',ec='none'))
        ax.plot([X(v)],[y],'o',ms=3.6,mfc='#104281',mec='white',mew=0.5,zorder=4)
    ax.text(x,yb+0.05,'LLM range, sampled value',ha='left',va='bottom',fontsize=6.4,color=MUTED)
    # 3 sample & render: two step renders stacked to the height of TARGET, labels on the images
    x=xs[2]+0.08;w=ws[2]-0.16;sg=0.06;vg=0.06
    steps=[load(f'{tk}/{n}.png',700) for n in ('step1','step2')];Ti=load(f'{tk}/target.png',1000);r=Ti.height/Ti.width
    tw=(w-sg+vg/(2*r))/1.5;th=tw*r;sh=(th-vg)/2;sw=sh/r
    for k,(im,lab) in enumerate(zip(steps,('+ exposure','+ color bal.'))):
        c.img(im,x,top-sh-k*(sh+vg),sw,sh,label=lab)
    c.img(Ti,x+sw+sg,top-th,tw,label='TARGET')
    ax.text(x+sw+sg+tw,top-th-0.05,'+ vignetting = TARGET',ha='right',va='top',fontsize=6.6,color=INK2)
    ax.text(x,top-th-0.05,'one step at a time',ha='left',va='top',fontsize=6.6,color=INK2)
    # 4 check: strength sweep with images, the other checks listed below
    x=xs[3]+0.08;w=ws[3]-0.16;n=3;gg=0.06;iw=(w-gg*(n-1))/n
    for k,f in enumerate((0.5,1,1.5)):
        im=load(f'{D}/paper_figs/darktable_b057/k{f}.png',700);de,cl,ok=V2[f];col=PASS if ok else FAIL
        xx=x+k*(iw+gg);h=c.img(im,xx,top-iw*im.height/im.width,iw,ec=col,lw=1.1)
        ax.text(xx+iw/2,top-h-0.04,f'×{f:g} strength',ha='center',va='top',fontsize=6.8,color=INK)
        ax.text(xx+iw/2,top-h-0.15,'passes' if ok else f'fails ({cl:.2f})',ha='center',va='top',fontsize=6.8,color=col,fontweight='semibold')
    y=top-h-0.31
    for k,(b,rest) in enumerate([('Exact:','replay and re-render give TARGET'),('Visible:','6 ≤ ΔE ≤ 30, no clipping'),
                                 ('Needed:','dropping any step fails'),('Not trivial:','colour transfer fails'),
                                 ('Plausible:','accepted by two VLM judges')]):
        yy=y-k*0.105
        ax.text(x,yy,b,ha='left',va='top',fontsize=6.6,color=INK,fontweight='semibold')
        ax.text(x+0.5,yy,rest,ha='left',va='top',fontsize=6.6,color=INK2)
    # bottom: the benchmark
    group(ax,0.03,0.04,6.84,1.1,None)
    ax.text(0.03+6.84/2,1.08,f'Benchmark:  {len(M)} tasks in 5 applications  ·  dev {sp["dev"]} / test {sp["test"]}  ·  + {real} real edits',
            ha='center',va='top',fontsize=8.5,fontweight='semibold',color=INK)
    rows=list(APPS);ny=len(rows);y0,y1=0.22,0.83
    tw=0.5;x=0.13
    for k,a in enumerate(rows):
        xx=x+k*(tw+0.07);c.img(square(load(f'{D}/bench_b1_{a}/tasks/{THUMBS[a]}/target.png',600)),xx,0.27,tw)
        ax.text(xx+tw/2,0.22,APP_NAMES[a],ha='center',va='top',fontsize=6.6,color=INK2)
    def chart(x0,w,title):
        a=c.fig.add_axes([x0/c.W,y0/c.H,w/c.W,(y1-y0)/c.H]);a.set_facecolor('none')
        for s in ('top','right','left'):a.spines[s].set_visible(False)
        a.spines['bottom'].set_color(EDGE);a.spines['bottom'].set_linewidth(0.5);a.tick_params(length=0,labelsize=6.4,colors=INK2,pad=1)
        a.set_ylim(-0.5,ny-0.5);a.set_yticks(range(ny));a.set_yticklabels([APP_NAMES[r] for r in rows][::-1],fontsize=6.6,color=INK)
        a.set_title(title,fontsize=7,color=INK,loc='left',pad=2,fontweight='semibold');a.grid(axis='x',color=RULE,lw=0.4);a.set_axisbelow(True)
        return a
    a=chart(3.55,1.45,'Steps per task')
    for j,r in enumerate(rows[::-1]):
        cn=collections.Counter(len(t['order']) for t in T[r]);x0=0
        for k in range(1,6):
            v=cn.get(k,0);a.barh(j,max(v-0.8,0),left=x0+0.4,height=0.62,color=STEP[k-1],lw=0);x0+=v
    a.set_xlim(0,100);a.set_xticks([0,50,100])
    for k in range(5):
        a.add_patch(Rectangle((52+k*10,ny-0.32),4.5,0.28,color=STEP[k],clip_on=False,lw=0,transform=a.transData))
        a.text(57.5+k*10,ny-0.18,str(k+1),fontsize=6,color=INK2,va='center',clip_on=False)
    a=chart(5.5,1.27,'START vs TARGET (ΔE)');a.set_yticklabels([])
    for j,r in enumerate(rows[::-1]):
        d=np.array([t['start_target_de00'] for t in T[r]]);q5,q25,q50,q75,q95=np.percentile(d,[5,25,50,75,95])
        a.plot([q5,q95],[j,j],color=INK2,lw=0.6);a.add_patch(Rectangle((q25,j-0.24),q75-q25,0.48,fc='#93bdf0',ec='none'))
        a.plot([q50,q50],[j-0.24,j+0.24],color='#104281',lw=1.2)
    a.axvline(4,color=FAIL,lw=0.7,ls=(0,(2,1.5)));a.text(3.4,(ny-1)/2,'pass bound',fontsize=6.2,color=FAIL,va='center',ha='right',rotation=90)
    a.set_xlim(0,30);a.set_xticks([0,10,20,30])
    c.save(out)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=os.path.join(PAPER,'fig','pipeline.pdf'));main(ap.parse_args().out)
