"""Column figure for Sec. 5 (fig:rounds): mean CIEDE2000 to TARGET after each of the four forced rounds, with the
RESULT image only (b1forced, dashed) and with RESULT plus the measured distance (b1fb, solid), at L2 and L3.
Groups: the 12 open models pooled, Claude Opus 5.5, GPT-6.1. Only episodes present in both runs with all four rounds
(the closed models' forced runs are incomplete, Bedrock budget), so the two lines of a group are paired.
Data: bench_b1_<app>/runs/{b1forced,b1fb}/scores.json (per_round = mean CIEDE2000 after each round).
  <python with matplotlib> scripts/paper/fig_rounds.py [--out ...pdf]"""
import argparse,json,os,statistics as st
from figstyle import *

OPEN=['dsv41','glm53','nemo35','step37','qwen35','qwen35_0.8b','qwen35_2b','qwen35_4b','qwen35_9b','qwen35_27b',
      'qwen35_35b_a3b','qwen35_122b_a10b']
GROUPS=[('12 open models',OPEN,'#9a9a9a','o'),('Opus 5.5',['opus55'],'#eb6834','s'),('GPT-6.1',['gpt61sol'],'#2a78d6','^')]

def load(run):
    E={}
    for a in APPS:
        for e in json.load(open(f'{D}/bench_b1_{a}/runs/{run}/scores.json'))['episodes']:
            if len(e.get('per_round',[]))==4:E[(a,e['task_id'],e['level'],e['model'])]=e
    return E

def main(out):
    F,B=load('b1forced'),load('b1fb')
    fig=plt.figure(figsize=(3.33,1.6))
    axs=[fig.add_axes([0.11,0.2,0.38,0.6]),fig.add_axes([0.6,0.2,0.38,0.6])]
    for ax,lv in zip(axs,('L2','L3')):
        for name,ms,col,mk in GROUPS:
            ks=[k for k in B if k[2]==lv and k[3] in ms and k in F]
            for R,ls,lab in ((F,(0,(2.5,1.5)),None),(B,'-',name)):
                y=[st.mean(R[k]['per_round'][i] for k in ks) for i in range(4)]
                ax.plot(range(1,5),y,color=col,ls=ls,lw=1.1,marker=mk,ms=2.8,mew=0,label=lab)
            print(lv,name,len(ks))
        ax.axhline(4,color=FAIL,lw=0.6,ls=(0,(1,1.5)))
        ax.set_title(lv,fontsize=7,color=INK,pad=2,fontweight='semibold')
        ax.set_xticks([1,2,3,4]);ax.set_xlim(0.8,4.2);ax.set_ylim(0,13);ax.set_yticks([0,4,8,12])
        ax.set_xlabel('round',fontsize=7,color=INK,labelpad=1)
        for s in ('top','right'):ax.spines[s].set_visible(False)
        for s in ('left','bottom'):ax.spines[s].set_color(EDGE);ax.spines[s].set_linewidth(0.5)
        ax.tick_params(length=2,width=0.5,color=EDGE,labelsize=6.4,labelcolor=INK2,pad=1.5)
        ax.grid(axis='y',color=RULE,lw=0.4);ax.set_axisbelow(True)
    axs[0].set_ylabel('ΔE to TARGET',fontsize=7,color=INK,labelpad=1.5)
    h,l=axs[0].get_legend_handles_labels()
    from matplotlib.lines import Line2D
    h+= [Line2D([],[],color=INK2,lw=1.1),Line2D([],[],color=INK2,lw=1.1,ls=(0,(2.5,1.5)))];l+=['+ distance','image only']
    fig.legend(h,l,loc='upper center',ncol=5,frameon=False,fontsize=6.2,handlelength=1.6,columnspacing=0.7,handletextpad=0.3,
               bbox_to_anchor=(0.53,1.01),labelcolor=INK)
    os.makedirs(os.path.dirname(out),exist_ok=True);fig.savefig(out);print('wrote',out)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=os.path.join(PAPER,'fig','rounds.pdf'));main(ap.parse_args().out)
