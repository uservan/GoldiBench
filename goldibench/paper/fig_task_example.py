"""Full-width figure (1.5 in tall; user 2026-11-11: compressed, badges beside the edits) for Sec. 3.2 (task format and evaluation; user 2026-11-10: the judging example, separate from the
production figure fig_pipeline.py). Left: the task of fig_pipeline.py (darktable b057), START / TARGET and what the agent
is given at L1 / L2 / L3 (instruction text as generated from the program). Right: three agent edits at L2, re-rendered
from their programs and scored, with the closeness scale. Everything shown is read from the data:
  task, program, START / TARGET          bench_b1_<app>/tasks.jsonl, tasks/<id>/{start,target}.png
  agent edits, dE, closeness, pass        bench_b1_<app>/runs/<run>/<id>/L2_<model>/final_rerender.png, runs/<run>/scores.json
  <python with matplotlib> scripts/paper/fig_task_example.py [--out ...pdf]"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import argparse,json,os,textwrap
from matplotlib.patches import Rectangle,FancyBboxPatch,Wedge
import numpy as np
from figstyle import *

APP,TID,RUN='darktable','b057','b1fb'
MODELS=[('gpt61sol','GPT-6.1'),('qwen35','Qwen3.5-397B'),('qwen35_9b','Qwen3.5-9B')]
NAMES={'exposure':'exposure','colorbalancergb':'color balance rgb','vignette':'vignetting'}
def fmt(v):return f'{v:.2f}'.rstrip('0').rstrip('.') if isinstance(v,float) else str(v)

def main(out):
    t=next(json.loads(l) for l in gbpaths.open_tasks(f'{D}/bench_b1_{APP}/tasks.jsonl') if json.loads(l)['task_id']==TID)
    sc={e['model']:e for e in json.load(open(f'{D}/bench_b1_{APP}/runs/{RUN}/scores.json'))['episodes'] if e['task_id']==TID and e['level']=='L2'}
    c=Canvas(6.9,1.5);ax=c.ax;H=c.H;top=H-0.22;pad=0.08
    xa,wa,xb,wb=0.03,2.8,2.95,3.92
    c.panel(xa,wa,title='Task at three levels');c.panel(xb,wb,title='Agent edits at L2, re-rendered and scored')
    # left: START / TARGET column + level rows
    S,T=[load(f'{D}/bench_b1_{APP}/tasks/{TID}/{n}.png',900) for n in ('start','target')]
    iw=0.7;ih=iw*S.height/S.width;x=xa+pad
    c.img(S,x,top-ih,iw,label='START');c.img(T,x,top-2*ih-0.05,iw,label='TARGET')
    steps='; '.join(NAMES.get(m,m)+(' = ' if list(t['program'][m])[0]==m else f": {list(t['program'][m])[0]} = ")
                    +fmt(list(t['program'][m].values())[0])
                    +(', …' if len(t['program'][m])>1 else '') for m in t['order'])
    tools=', '.join(NAMES.get(m,m) for m in t['order'])
    m0=t['order'][0];short=steps.split('; ')[0]+'; '+'; '.join(NAMES.get(m,m)+': …' for m in t['order'][1:])   # values of the later steps elided to fit
    rows=[('L1','tools + values','START',f'Apply exactly: {short}'),('L2','tools only','START + TARGET',f'Produced with exactly: {tools}.'),
          ('L3','goal only','START + TARGET','Any of the 9 listed modules may be needed.')]
    # 2026-11-16 (user): the level and what it gives must stand out; the instruction wording is secondary (small, grey, italic)
    lx=x+iw+0.1;rh=(2*ih+0.05)/3
    for i,(lv,what,given,txt) in enumerate(rows):
        y=top-i*rh;lc=LV[i] if i else '#4f8fd9'
        ax.plot([lx,lx],[y-0.03,y-rh+0.04],color=LV[i],lw=2.2,solid_capstyle='butt')
        ax.text(lx+0.07,y-0.02,f'{lv}  {what}',ha='left',va='top',fontsize=7.6,fontweight='bold',color=lc)
        ax.text(lx+0.07,y-0.135,f'sees {given}',ha='left',va='top',fontsize=6.2,color=INK2)
        ax.text(lx+0.07,y-0.225,'\n'.join(textwrap.wrap(f'“{txt}”',58)),ha='left',va='top',fontsize=5.6,color=MUTED,
                style='italic',linespacing=1.1)
    # right: three agent edits, each with a score badge: ring gauge (filled share = closeness, notch at the 0.75 pass
    # line, value in the centre) and a drawn check / cross with pass / fail and dE
    x=xb+pad;w=wb-2*pad;n=len(MODELS);g=0.1;cw_=(w-g*(n-1))/n;rw=0.8
    def badge(cx,cy,e):
        col=PASS if e['pass'] else FAIL;R=0.13;th=0.028
        ax.add_patch(Wedge((cx,cy),R,0,360,width=th,fc='#e4e7eb',ec='none'))
        f=max(0.0,min(1.0,e['closeness']))
        if f>0:ax.add_patch(Wedge((cx,cy),R,90-360*f,90,width=th,fc=col,ec='none'))
        if e['closeness']<0:ax.add_patch(Wedge((cx,cy),R,90,90+360*min(1,-e['closeness']),width=th,fc='none',ec=col,lw=0.6,ls=(0,(1.5,1))))
        a=np.deg2rad(90-360*0.75)   # pass line
        ax.plot([cx+(R-th-0.004)*np.cos(a),cx+(R+0.004)*np.cos(a)],[cy+(R-th-0.004)*np.sin(a),cy+(R+0.004)*np.sin(a)],color='white',lw=1.6,solid_capstyle='butt',zorder=5)
        ax.text(cx,cy+0.005,f"{e['closeness']:.2f}",ha='center',va='center',fontsize=6.2,fontweight='semibold',color=INK)
        ix,iy=cx-0.1,cy-R-0.1;s_=0.032
        if e['pass']:ax.plot([ix-s_,ix-s_*0.25,ix+s_],[iy,iy-s_*0.75,iy+s_*0.8],color=col,lw=1.6,solid_capstyle='round',solid_joinstyle='round')
        else:
            ax.plot([ix-s_*0.75,ix+s_*0.75],[iy-s_*0.75,iy+s_*0.75],color=col,lw=1.6,solid_capstyle='round')
            ax.plot([ix-s_*0.75,ix+s_*0.75],[iy+s_*0.75,iy-s_*0.75],color=col,lw=1.6,solid_capstyle='round')
        ax.text(ix+s_+0.04,iy,'pass' if e['pass'] else 'fail',ha='left',va='center',fontsize=6.8,fontweight='semibold',color=col)
        ax.text(ix-s_,iy-0.12,f"ΔE = {e['de00']:.1f}",ha='left',va='center',fontsize=6.4,color=INK2)
        ax.text(ix-s_,iy-0.2,'to TARGET',ha='left',va='center',fontsize=5.4,color=MUTED)
    for k,(m,name) in enumerate(MODELS):
        e=sc[m];col=PASS if e['pass'] else FAIL
        im=load(f'{D}/bench_b1_{APP}/runs/{RUN}/{TID}/L2_{m}/final_rerender.png',900)
        xx=x+k*(cw_+g);h=c.img(im,xx,top-rw*im.height/im.width,rw,ec=col,lw=1.2)
        ax.text(xx,top-h-0.03,name,ha='left',va='top',fontsize=6.6,color=INK,fontweight='semibold')
        badge(xx+rw+0.2,top-0.2,e)
    # closeness scale under the badges: segments (worse / partial / pass), START and TARGET at 0 and 1, one pointer per edit
    lo,hi=-0.3,1.1;a0,a1=x+0.62,x+w-0.12;sy=0.3;bh=0.075
    X=lambda v:a0+(v-lo)/(hi-lo)*(a1-a0)
    ax.text(x,sy+0.01,'closeness',ha='left',va='center',fontsize=7.4,color=INK,fontweight='semibold')
    ax.text(x,sy-0.06,'pass: closeness ≥ 0.75\nand ΔE to TARGET ≤ 4',ha='left',va='top',fontsize=5.6,color=PASS,linespacing=1.1)
    for v0,v1,fc in ((lo,0,'#f6d3c9'),(0,0.75,'#e3e5e8'),(0.75,hi,'#bfe8d6')):
        ax.add_patch(FancyBboxPatch((X(v0),sy-bh/2),X(v1)-X(v0),bh,boxstyle='round,pad=0,rounding_size=0.02',fc=fc,ec='white',lw=1.2))
    ax.text(X(-0.15),sy,'worse',ha='center',va='center',fontsize=5.8,color='#b4472b')
    ax.text(X(0.375),sy,'partial',ha='center',va='center',fontsize=5.8,color=INK2)
    ax.text(X(0.93),sy,'pass',ha='center',va='center',fontsize=5.8,color='#127a55',fontweight='semibold')
    for v,lab in ((0,'START'),(1,'TARGET')):   # the two ends named on top of the bar
        ax.plot([X(v)]*2,[sy+bh/2,sy+bh/2+0.03],color=MUTED,lw=0.5)
        ax.text(X(v),sy+bh/2+0.035,lab,ha='center',va='bottom',fontsize=5.6,color=INK2)
    for m,name in MODELS:
        e=sc[m];col=PASS if e['pass'] else FAIL;px=X(e['closeness'])
        ax.plot([px],[sy-bh/2-0.035],marker='^',ms=4.6,mfc=col,mec='white',mew=0.5,zorder=4)
        ax.text(px,sy-bh/2-0.065,f"{e['closeness']:.2f}",ha='center',va='top',fontsize=6,color=col,fontweight='semibold')
    c.save(out)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=os.path.join(PAPER,'fig','task_example.pdf'));main(ap.parse_args().out)
