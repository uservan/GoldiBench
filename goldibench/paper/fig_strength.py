"""Column figure for Sec. 4.1 (fig:strength): the hidden program of every task rescaled to k times its distance from
neutral (k = -1 reverses it; the 12 strengths evenly spaced on the x axis), rendered and scored against TARGET. Left: pass rate per application; right: median
closeness. The band marks the strengths the Sensitive check requires to pass (x0.9-1.1).
Data: bench_b1_<app>/magnitude_curve.json (scripts/bench/magnitude_curve.py, 12 strengths x 100 tasks per app).
  <python with matplotlib> scripts/paper/fig_strength.py [--out ...pdf]"""
import argparse,json,os,statistics as st
from figstyle import *

KS=[-1,0,0.25,0.5,0.75,0.9,1,1.1,1.25,1.5,2,3]
# 2026-11-14 (user): same look as Fig. scaling (fig_scaling_sub.py), "academic": STIX serif as the CVPR body, closed black
# frame, inward ticks, dotted grid; applications told apart by colour + marker (filled / hollow alternate), muted palette.
plt.rcParams.update({'font.family':'serif','font.serif':['STIXGeneral'],'mathtext.fontset':'stix','font.size':7,
                     'xtick.direction':'in','ytick.direction':'in','axes.linewidth':0.6})
COL=['#1f4e9c','#c0392b','#2e8b57','#d68910','#7d3c98']   # fixed order = APPS; first three as L1 / L2 / L3 in Fig. scaling
MK=['o','s','^','D','v'];HOLLOW=[False,True,False,True,False]

def main(out,png=None):
    R={a:json.load(open(f'{D}/bench_b1_{a}/magnitude_curve.json')) for a in APPS}
    fig=plt.figure(figsize=(3.33,1.38))
    axs=[fig.add_axes([0.105,0.2,0.375,0.6]),fig.add_axes([0.605,0.2,0.375,0.6])]
    for ax,key,yl,lim in ((axs[0],'pass','Pass rate (%)',(-5,105)),(axs[1],'closeness','Median closeness',(-1.1,1.1))):
        ax.axvspan(KS.index(0.9)-0.25,KS.index(1.1)+0.25,color='#bdbdbd',alpha=0.35,lw=0,zorder=0)
        for i,a in enumerate(APPS):
            xs,ys=[],[]
            for k in KS:
                rk=[r[key] for r in R[a] if r['k']==k]
                if rk:xs.append(KS.index(k));ys.append(100*st.mean(rk) if key=='pass' else st.median(rk))
            ax.plot(xs,ys,color=COL[i],lw=0.9,marker=MK[i],ms=3.0,mew=0.7,mec=COL[i],mfc='white' if HOLLOW[i] else COL[i],
                    label=APP_NAMES[a],zorder=3,clip_on=False)
        ax.set_xlim(-0.5,len(KS)-0.5);ax.set_xticks(range(len(KS)))
        ax.set_xticklabels(['$-1$','0','','0.5','','','1','','','1.5','2','3'])
        ax.set_ylim(*lim);ax.set_ylabel(yl,fontsize=6.8,labelpad=1.5);ax.set_xlabel('Strength $k$',fontsize=6.8,labelpad=1)
        for s_ in ax.spines.values():s_.set_linewidth(0.6);s_.set_color('black')
        ax.tick_params(labelsize=6.8,length=2.2,width=0.5,pad=1.8,top=True,right=True)
        ax.tick_params(axis='x',top=False)
        ax.grid(axis='y',color='#c8c8c8',lw=0.4,ls=(0,(1,1.5)),zorder=0);ax.set_axisbelow(True)
    axs[0].set_yticks([0,50,100]);axs[1].set_yticks([-1,0,0.75]);axs[1].set_yticklabels(['$-1$','0','0.75'])
    axs[1].axhline(0.75,color='black',lw=0.6,ls=(0,(3,1.5)),zorder=2)
    h,l=axs[0].get_legend_handles_labels()
    fig.legend(h,l,loc='upper center',ncol=5,frameon=False,fontsize=6.8,handlelength=1.7,columnspacing=0.7,handletextpad=0.3,
               bbox_to_anchor=(0.5,1.02))
    os.makedirs(os.path.dirname(out),exist_ok=True);fig.savefig(out);print('wrote',out)
    if png:fig.savefig(png,dpi=300);print('wrote',png)
    for a in APPS:   # numbers for the text
        r=R[a];cl=[x for x in r if x['k']==1.1 and not x['pass']]
        print(a,len(r),{k:round(100*st.mean(x['pass'] for x in r if x['k']==k)) for k in KS if any(x['k']==k for x in r)},
              'x1.1 fails clipped',sum(x['clipped'] for x in cl),'/',len(cl))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=os.path.join(PAPER,'fig','strength.pdf'));ap.add_argument('--png')
    a=ap.parse_args();main(a.out,a.png)
