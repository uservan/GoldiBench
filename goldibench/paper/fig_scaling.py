"""Sec. 4.3 figure (user 2026-11-13): four small bar charts, three sizes each, showing that size raises L1 but not L2 / L3.
Panels: Qwen3.5 program channel, Qwen3.5 GUI (same three sizes), UI-TARS GUI, OpenCUA GUI. Every size is in Sec. 5.

Pass % per app first, then the mean over the five apps (each app weighs the same; GIMP has the most GUI tasks), then the
mean and sd over seeds (program: b1t32 seeds 0-4; GUI 100 steps: b1g100_s0-2, read from logs/gui100_progress.json, which
scripts/gui/gui100_progress.py writes). Output: <paper>/fig/scaling.pdf"""
import json,os,statistics as st
from figstyle import plt,PAPER,D,INK,INK2,MUTED,RULE,LV

APPS=('darktable','rawtherapee','gimp','inkscape','blender');LEVELS=('L1','L2','L3')
LOG=f'{D}/logs'

# 2026-11-14 (user): read logs/sec43_data.json (scripts/paper/sec43_data.py): five-app mean pass %, mean and sd over seeds;
# GUI episodes the model left hung (no episode.json) count as failures. Program channel: b1t32 seeds 0-4.
S43=json.load(open(f'{LOG}/sec43_data.json'))
def program(models):return {(m,lv):(S43['program_qwen'][f'{m}|{lv}']['mean5'],S43['program_qwen'][f'{m}|{lv}']['sd_seeds']) for m in models for lv in LEVELS}
def gui(models):return {(m,lv):(S43['gui'][f'{m}|{lv}']['mean5'],S43['gui'][f'{m}|{lv}']['sd_seeds']) for m in models for lv in LEVELS}

PANELS=[('Qwen3.5 · program',program,[('2B','qwen35_2b'),('4B','qwen35_4b'),('9B','qwen35_9b'),('27B','qwen35_27b')]),
        ('Qwen3.5 · GUI',gui,[('2B','qwen35gui_2b'),('4B','qwen35gui_4b'),('9B','qwen35gui_9b'),('27B','qwen35gui_27b')]),
        ('UI-TARS · GUI',gui,[('2B','uitars_2b'),('7B','uitars_7b'),('72B','uitars_72b')]),
        ('OpenCUA · GUI',gui,[('7B','opencua_7b'),('32B','opencua_32b'),('72B','opencua_72b')])]

def main():
    fig,axs=plt.subplots(2,2,figsize=(3.33,2.5))
    plt.subplots_adjust(left=0.1,right=0.99,top=0.84,bottom=0.09,wspace=0.28,hspace=0.6)
    w=0.26
    for ax,(title,fn,ms) in zip(axs.flat,PANELS):
        v=fn([m for _,m in ms])
        for j,lv in enumerate(LEVELS):
            ys=[v[m,lv][0] for _,m in ms];es=[v[m,lv][1] for _,m in ms];xs=[i+(j-1)*w for i in range(len(ms))]
            ax.bar(xs,ys,w,color=LV[j],label=lv,zorder=2)
            ax.errorbar(xs,ys,yerr=es,fmt='none',ecolor=INK2,elinewidth=0.5,capsize=1.2,capthick=0.5,zorder=3)
            for x,y in zip(xs,ys):
                if y<3:ax.text(x,y+1.5,f'{y:.0f}' if y>=0.5 else '0',ha='center',va='bottom',fontsize=4.5,color=MUTED)
        ax.set_xticks(range(len(ms)));ax.set_xticklabels([s for s,_ in ms],fontsize=6)
        top=105 if 'program' in title else 20
        ax.set_ylim(0,top);ax.set_title(title,fontsize=7,color=INK,pad=3,fontweight='semibold')
        ax.tick_params(axis='y',labelsize=5.5,length=2,color=MUTED);ax.tick_params(axis='x',length=0)
        ax.grid(axis='y',color=RULE,lw=0.4,zorder=0)
        for s in ('top','right'):ax.spines[s].set_visible(False)
        for s in ('left','bottom'):ax.spines[s].set_color(MUTED);ax.spines[s].set_linewidth(0.5)
    for ax in axs[:,0]:ax.set_ylabel('pass %',fontsize=6,color=INK2,labelpad=1)
    h,l=axs[0,0].get_legend_handles_labels()
    fig.legend(h,l,loc='upper center',ncol=3,fontsize=6,frameon=False,bbox_to_anchor=(0.55,1.0),handlelength=1,columnspacing=1)
    out=os.path.join(PAPER,'fig','scaling.pdf');fig.savefig(out);print('wrote',out)
    for title,fn,ms in PANELS:
        v=fn([m for _,m in ms]);print(title,' | '.join(f"{s}: "+'/'.join(f'{v[m,lv][0]:.1f}' for lv in LEVELS) for s,m in ms))

if __name__=='__main__':main()
