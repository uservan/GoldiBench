"""Fig. 1 teaser (user 2026-11-16: new, in the paper's style). Full width, three panels:
 (1) a request describes the look: RawTherapee b053, START / TARGET / GPT-6.1 at L2 (right tools, wrong amounts; it stopped
     after its first render), with the parameters it chose against the hidden ones;
 (2) agents operate but miss the amount: pass rate at L1 / L2 / L3, program and GUI channel (main_tables.json);
 (3) why: L2 pass rate with tool knowledge, the difference as an image, and the measured difference (Tab. interventions;
     open models from logs/interv12.json, closed models as in the paper).
Everything except the closed-model intervention numbers is read from the data.
  <python with matplotlib> scripts/paper/fig_teaser.py [--out ...pdf]"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import argparse,json,textwrap
from figstyle import *
from matplotlib.patches import FancyBboxPatch

APP,TID='rawtherapee','b053'
LVC=LV

def bars_cliff(fig,c,x,y,w,h):
    M=json.load(open(f'{D}/logs/main_tables.json'))
    groups=[('Program',[('Qwen3.5\n397B','program','qwen35'),('Opus\n5.5','program','opus55'),('GPT\n6.1','program','gpt61sol')]),
            ('GUI',[('Holo4\n27B','gui','holo4_27b'),('Opus\n5.5','gui','opus55gui'),('GPT\n6.1','gui','gpt61gui')])]
    a=fig.add_axes([x/c.W,y/c.H,w/c.W,h/c.H]);bw=0.26;xs=[];labs=[];k=0
    for gi,(g,ms) in enumerate(groups):
        for lab,ch,m in ms:
            for j,lv in enumerate(('L1','L2','L3')):
                v=M[ch][f'{m}|{lv}'][0]
                a.bar(k+(j-1)*bw,v,bw*0.92,color=LVC[j],lw=0)
                if j>0:a.text(k+(j-1)*bw,v+2,f'{v:.0f}',ha='center',va='bottom',fontsize=5.2,color=INK2)
            xs.append(k);labs.append(lab);k+=1
        if gi==0:k+=0.4
    a.set_xticks(xs);a.set_xticklabels(labs,fontsize=5.6,linespacing=0.95)
    a.set_ylim(0,112);a.set_yticks([0,50,100]);a.tick_params(axis='y',labelsize=5.6,length=2,pad=1);a.tick_params(axis='x',length=0,pad=2)
    a.set_ylabel('pass (%)',fontsize=6,labelpad=1)
    for s in ('top','right'):a.spines[s].set_visible(False)
    for s in ('left','bottom'):a.spines[s].set_color(MUTED);a.spines[s].set_linewidth(0.5)
    a.axvline(2.7,color=RULE,lw=0.6)
    for gx,g in ((1,'program channel'),(4.4,'GUI channel')):a.text(gx,106,g,ha='center',va='bottom',fontsize=6,color=INK2,style='italic')
    lx=x-0.22
    for j,lv in enumerate(('L1 tools + values','L2 tools only','L3 goal only')):
        c.ax.add_patch(FancyBboxPatch((lx,y+h+0.09),0.07,0.07,boxstyle='square,pad=0',fc=LVC[j],ec='none'))
        c.ax.text(lx+0.1,y+h+0.125,lv,ha='left',va='center',fontsize=5.8,color=INK2);lx+=[0.72,0.62,0.6][j]

def bars_why(fig,c,x,y,w,h):
    I=json.load(open(f'{D}/logs/interv12.json'))
    op=lambda r:(I[f'{r}|open12']['before'],I[f'{r}|open12']['after'])
    # closed models: paper Tab. interventions (30-task subsets)
    rows={'Open (12)':[op('b1man')[0],op('b1man')[1],op('b1diffimg')[1],op('b1tdiff')[1]],
          'Opus 5.5':[12.7,14.0,None,34.0],'GPT-6.1':[17.3,16.7,None,47.3]}
    cols=['#c9c9c6','#9a9a9a','#86b6ef',ACC];names=['default','+ manual','+ diff. as image','+ diff. measured']
    a=fig.add_axes([x/c.W,y/c.H,w/c.W,h/c.H]);bw=0.2
    for i,(g,vs) in enumerate(rows.items()):
        for j,v in enumerate(vs):
            px=i+(j-1.5)*bw
            if v is None:a.text(px,1,'–',ha='center',va='bottom',fontsize=5.5,color=MUTED);continue
            a.bar(px,v,bw*0.9,color=cols[j],lw=0)
            if j==3 or (j==2):a.text(px,v+1,f'{v:.0f}',ha='center',va='bottom',fontsize=5.2,color=ACC if j==3 else INK2,fontweight='semibold' if j==3 else 'normal')
    a.set_xticks(range(3));a.set_xticklabels(['Open\n(12 models)','Opus\n5.5','GPT\n6.1'],fontsize=5.6,linespacing=0.95)
    a.set_ylim(0,54);a.set_yticks([0,25,50]);a.tick_params(axis='y',labelsize=5.6,length=2,pad=1);a.tick_params(axis='x',length=0,pad=2)
    a.set_ylabel('L2 pass (%)',fontsize=6,labelpad=1)
    for s in ('top','right'):a.spines[s].set_visible(False)
    for s in ('left','bottom'):a.spines[s].set_color(MUTED);a.spines[s].set_linewidth(0.5)
    for j,n in enumerate(['default','+ manual','+ diff. as image','+ diff. measured']):
        lx=x-0.22+(j%2)*0.8;ly=y+h+0.2-0.1*(j//2)
        c.ax.add_patch(FancyBboxPatch((lx,ly-0.035),0.07,0.07,boxstyle='square,pad=0',fc=cols[j],ec='none'))
        c.ax.text(lx+0.1,ly,n,ha='left',va='center',fontsize=5.8,color=INK2)

def main(out):
    t=next(json.loads(l) for l in gbpaths.open_tasks(f'{D}/bench_b1_{APP}/tasks.jsonl') if json.loads(l)['task_id']==TID)
    ep=json.load(open(f'{D}/bench_b1_{APP}/runs/b1t32/{TID}/L2_gpt61sol/episode.json'))
    sc=next(e for e in json.load(open(f'{D}/bench_b1_{APP}/runs/b1t32/scores.json'))['episodes']
            if e['task_id']==TID and e['level']=='L2' and e['model']=='gpt61sol')
    prog=t['program'] if isinstance(t['program'],dict) else eval(t['program'])
    gp=ep['rounds'][-1]['program'];gp=gp if isinstance(gp,dict) else eval(gp)
    c=Canvas(6.9,1.65);ax=c.ax;H=c.H;top=H-0.25
    xa,wa=0.03,2.36;xb,wb=2.46,2.42;xc,wc=4.95,1.92   # 2026-11-16 user: shorter figure
    c.panel(xa,wa,title='A request describes the look',num=1)
    c.panel(xb,wb,title='Agents operate, but miss the amount',num=2)
    c.panel(xc,wc,title='Why: reading the difference',num=3)
    # (1) request (first clauses), START / TARGET / GPT-6.1 at L2, chosen vs hidden values in one line
    q=t['intent'].split(', and ')[0].rstrip('.')+', …'
    ax.text(xa+0.1,top,'\n'.join(textwrap.wrap('“'+q+'”',62)),ha='left',va='top',fontsize=6.0,color=INK2,style='italic',linespacing=1.05)
    ims=[load(f'{D}/bench_b1_{APP}/tasks/{TID}/{n}.png',900) for n in ('start','target')]+[load(f'{D}/bench_b1_{APP}/runs/b1t32/{TID}/L2_gpt61sol/final_rerender.png',900)]
    iw=0.6;g=0.07;x0=xa+0.09;iy=top-0.21
    for k,(im,lab) in enumerate(zip(ims,['START','TARGET','GPT-6.1, L2'])):
        c.img(im,x0+k*(iw+g),iy-iw*im.height/im.width,iw,label=lab,ec=FAIL if k==2 else None,lw=1.1 if k==2 else 0.5)
    ih=iw*ims[0].height/ims[0].width;yb=iy-ih-0.04
    ax.text(x0+2*(iw+g)+iw+0.05,iy-ih/2+0.07,'fail',ha='left',va='center',fontsize=6.6,color=FAIL,fontweight='semibold')
    ax.text(x0+2*(iw+g)+iw+0.05,iy-ih/2-0.05,f"ΔE {sc['de00']:.1f}",ha='left',va='center',fontsize=6.2,color=FAIL)
    rows=[('temperature',gp['white_balance']['temperature'],prog['white_balance']['temperature'],'{:.0f}'),
          ('exposure',gp['exposure']['compensation'],prog['exposure']['compensation'],'{:.2f}'),
          ('vignette',gp['vignette']['strength'],prog['vignette']['strength'],'{:.2f}')]
    ax.text(x0,yb,'Right tools, wrong amounts (chosen / target):',ha='left',va='top',fontsize=5.9,color=INK,fontweight='semibold')
    xx=x0
    for n,v,tv,f in rows:
        for s_,col,wt in ((n+' ',INK2,'normal'),(f.format(v),FAIL,'semibold'),(' / '+f.format(tv)+'   ',MUTED,'normal')):
            tt=ax.text(xx,yb-0.115,s_,ha='left',va='top',fontsize=5.7,color=col,fontweight=wt)
            c.fig.canvas.draw() if xx==x0 and n=='temperature' and s_==n+' ' else None
            xx+=tt.get_window_extent(renderer=c.fig.canvas.get_renderer()).width/c.fig.dpi
    # (2) cliff, (3) why
    bars_cliff(c.fig,c,xb+0.3,0.27,wb-0.38,H-0.27-0.5)
    bars_why(c.fig,c,xc+0.3,0.27,wc-0.38,H-0.27-0.6)
    c.save(out)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=os.path.join(PAPER,'fig','teaser.pdf'));main(ap.parse_args().out)
