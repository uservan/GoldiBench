"""Sec. 4.3 figure, line version (user 2026-11-14: "more academic"): pass % vs parameters (log), one line per family,
two panels L1 (operation) / L2 (effect judgement) on the same y scale; L3 (<= 1 % everywhere) is stated in the caption.
GUI channel: Qwen3.5 dense 2B-27B, UI-TARS 2B / 7B / 72B, OpenCUA 7B / 32B / 72B, 100 steps, seeds 0-2.
Program channel: Qwen3.5 (same sizes, b1t32 seeds 0-4), dashed.
VARIANT=mean5 (default): mean over the five apps (logs/sec43_data.json, scripts/paper/sec43_data.py), y 0-20, program only in
the L2 panel (its L1 is 92-100 %, off this scale). VARIANT=gimp: GIMP only, y 0-100, program in both panels.
Error bars: sd over seeds. Output: <paper>/fig/scaling.pdf (OUT overrides)."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import json,os,statistics as st
from figstyle import plt,PAPER,D,INK,INK2,MUTED,RULE,ACC

VARIANT=os.environ.get('VARIANT','mean5');LOG=f'{D}/logs'
S43=json.load(open(f'{LOG}/sec43_data.json'))
FAM=[('Qwen3.5',[(2,'qwen35gui_2b'),(4,'qwen35gui_4b'),(9,'qwen35gui_9b'),(27,'qwen35gui_27b')],ACC,'o'),
     ('OpenCUA',[(7,'opencua_7b'),(32,'opencua_32b'),(72,'opencua_72b')],'#e4572e','s'),
     ('UI-TARS',[(2,'uitars_2b'),(7,'uitars_7b'),(72,'uitars_72b')],'#1baf7a','^')]
PROG=[(2,'qwen35_2b'),(4,'qwen35_4b'),(9,'qwen35_9b'),(27,'qwen35_27b')]

def gui(m,lv):
    if VARIANT=='mean5':c=S43['gui'][f'{m}|{lv}'];return c['mean5'],c['sd_seeds']
    # GIMP only: per-seed pass % (GIMP dict below, read from the episodes)
    return GIMP[m,lv]

def prog(m,lv):
    if VARIANT=='mean5':c=S43['program_qwen'][f'{m}|{lv}'];return c['mean5'],c['sd_seeds']
    per=[]
    for s in range(5):
        for line in open(f'{LOG}/bench_b1_gimp_scores_b1t32{"" if s==0 else f"_s{s}"}.txt'):
            p=line.split()
            if len(p)>=8 and p[2]=='all' and p[0]==m and p[1]==lv:per.append(float(p[5]))
    return st.mean(per),st.stdev(per)

if VARIANT=='gimp':
    # GIMP pass % per seed, missing episodes (app hung) as failures, as sec43_data.py
    tasks=[json.loads(l) for l in gbpaths.open_tasks(f'{D}/bench_b1_gimp_gui/tasks.jsonl')]
    n_lv={lv:sum(1 for t in tasks if (t.get('level') or t['id'].split('_')[-1])==lv) for lv in ('L1','L2')}
    GIMP={}
    for _,ms,_,_ in FAM:
        for _,m in ms:
            for lv in ('L1','L2'):
                per=[]
                for s in '012':
                    R=f'{D}/bench_b1_gimp_gui/runs/b1g100_s{s}';k=0
                    for d in os.listdir(R):
                        if d.endswith(f'_{lv}_{m}') and os.path.exists(f'{R}/{d}/episode.json'):
                            k+=bool((json.load(open(f'{R}/{d}/episode.json')).get('eval') or {}).get('pass'))
                    per.append(100*k/n_lv[lv])
                GIMP[m,lv]=(st.mean(per),st.stdev(per))

def main():
    top=20 if VARIANT=='mean5' else 100
    fig,axs=plt.subplots(1,2,figsize=(3.33,1.62),sharey=True)
    plt.subplots_adjust(left=0.115,right=0.985,top=0.8,bottom=0.19,wspace=0.12)
    for ax,lv,title in zip(axs,('L1','L2'),('L1 · operation','L2 · effect judgement')):
        for name,ms,col,mk in FAM:
            xs=[x for x,_ in ms];v=[gui(m,lv) for _,m in ms]
            ax.errorbar(xs,[a for a,_ in v],yerr=[b for _,b in v],color=col,marker=mk,ms=3.2,lw=1.1,mew=0,
                        elinewidth=0.6,capsize=1.5,capthick=0.6,label=f'{name} (GUI)',zorder=3)
        if VARIANT=='gimp' or lv=='L2':
            v=[prog(m,lv) for _,m in PROG]
            ax.errorbar([x for x,_ in PROG],[a for a,_ in v],yerr=[b for _,b in v],color=ACC,marker='o',ms=3.2,lw=1.0,
                        ls=(0,(3,1.6)),mfc='white',mec=ACC,mew=0.8,elinewidth=0.6,capsize=1.5,capthick=0.6,
                        label='Qwen3.5 (program)',zorder=2)
        ax.set_xscale('log');ax.set_xlim(1.6,95);ax.set_ylim(0,top)
        ax.set_xticks([2,4,8,16,32,72]);ax.set_xticklabels(['2B','4B','8B','16B','32B','72B'],fontsize=6)
        ax.minorticks_off();ax.tick_params(axis='y',labelsize=6,length=2,color=MUTED);ax.tick_params(axis='x',length=2,color=MUTED)
        ax.set_title(title,fontsize=7,color=INK,pad=3,fontweight='semibold')
        ax.grid(axis='y',color=RULE,lw=0.4,zorder=0)
        for s in ('top','right'):ax.spines[s].set_visible(False)
        for s in ('left','bottom'):ax.spines[s].set_color(MUTED);ax.spines[s].set_linewidth(0.5)
    axs[0].set_ylabel('pass % '+('(5-app mean)' if VARIANT=='mean5' else '(GIMP)'),fontsize=6,color=INK2,labelpad=2)
    if VARIANT=='mean5':
        axs[0].annotate('Qwen3.5 (program):\nL1 92–100 %',xy=(0.97,0.97),xycoords='axes fraction',ha='right',va='top',
                        fontsize=5.3,color=ACC,linespacing=1.05)
    fig.text(0.55,0.015,'parameters (log scale)',ha='center',va='bottom',fontsize=6,color=INK2)
    h,l=axs[1].get_legend_handles_labels()
    h=[x[0] if isinstance(x,tuple) or hasattr(x,'lines') else x for x in h]
    fig.legend(h,l,loc='upper center',ncol=4,fontsize=5.6,frameon=False,bbox_to_anchor=(0.54,1.0),handlelength=1.8,
               columnspacing=0.8,handletextpad=0.4)
    out=os.environ.get('OUT') or os.path.join(PAPER,'fig','scaling.pdf');fig.savefig(out);print('wrote',out)
    if out.endswith('.pdf'):fig.savefig(out[:-4]+'.png',dpi=300) if os.environ.get('PNG') else None

if __name__=='__main__':main()
