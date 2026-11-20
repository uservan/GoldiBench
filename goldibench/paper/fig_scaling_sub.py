"""Sec. 4.3 figure as four separate subfigures (user 2026-11-14: one PDF per panel, placed with \\subfigure in LaTeX):
fig/scaling_prog.pdf (Qwen3.5, program channel), fig/scaling_qwen.pdf (Qwen3.5, GUI), fig/scaling_opencua.pdf, fig/scaling_uitars.pdf.
Each: pass % (five-app mean since 2026-11-14) per level (L1 / L2 / L3) vs model size; shaded band = sd over seeds. Same canvas, axes rectangle and y scale
in every file, so the four line up side by side; the legend is in the first one only.
GUI: 100 steps, runs b1g100_s0-2; an episode without episode.json (the agent left GIMP hung) counts as a failure.
Program: b1t32 seeds 0-4 (scores files). Numbers also go to logs/sec43_gimp.json."""
import json,os,statistics as st
from figstyle import plt,PAPER,D,INK,INK2,MUTED,RULE

LOG=f'{D}/logs';LEVELS=('L1','L2','L3')
# 2026-11-14 (user): "more academic", wider rectangles: Times-like serif (STIX, as the CVPR body), closed frame, inward ticks,
# dotted grid, error bars with caps; levels told apart by colour + marker + line style; one-row legend above every panel.
plt.rcParams.update({'font.family':'serif','font.serif':['STIXGeneral'],'mathtext.fontset':'stix','font.size':7,
                     'xtick.direction':'in','ytick.direction':'in','axes.linewidth':0.6})
STY={'L1':dict(color='#1f4e9c',marker='o',ls='-',mfc='#1f4e9c'),
     'L2':dict(color='#c0392b',marker='s',ls=(0,(4,1.6)),mfc='white'),
     'L3':dict(color='#2e8b57',marker='^',ls=(0,(1,1.3)),mfc='#2e8b57')}
TOP={'prog':100,'qwen':80,'opencua':80,'uitars':40}
DX={'L1':0,'L2':-0.06,'L3':0.06}   # small x offsets so the L2 / L3 markers near 0 do not cover each other
PANELS=[('prog','program',[('2B','qwen35_2b'),('4B','qwen35_4b'),('9B','qwen35_9b'),('27B','qwen35_27b')]),
        ('qwen','gui',[('2B','qwen35gui_2b'),('4B','qwen35gui_4b'),('9B','qwen35gui_9b'),('27B','qwen35gui_27b')]),
        ('opencua','gui',[('7B','opencua_7b'),('32B','opencua_32b'),('72B','opencua_72b')]),
        ('uitars','gui',[('2B','uitars_2b'),('7B','uitars_7b'),('72B','uitars_72b')])]

# 2026-11-14 (user): five-app mean (logs/sec43_data.json from sec43_data.py: per-app pass %, apps weigh the same; mean / sd over seeds;
# hung GUI episodes count as failures). L2 on its own right axis so it does not sit on L3; its range is chosen so that every
# L2 point is drawn below the L1 point of the same size (at most 2/3 of its height) wherever L1 is above the floor (>= 1 %).
S43=json.load(open(f'{LOG}/sec43_data.json'))
def get(kind,m,lv):
    c=S43['program_qwen' if kind=='program' else 'gui'][f'{m}|{lv}'];return c['mean5'],c['sd_seeds']
NICE=[1,1.5,2,2.5,3,4,5,6,8,10,12,15,20,25,30,40,50,60,80,100]
def nice(v):return next(n for n in NICE if n>=min(v,100))

W,H=1.68,1.35;RECT=[0.2,0.15,0.6,0.7]   # 2026-11-16: taller now that the figure is in the supplementary (was 0.95 high, user asked to fix the cramped look)

def line(ax,xl,mu,sd,lv):
    sty=STY[lv]
    return ax.errorbar(xl,mu,yerr=sd,color=sty['color'],ls=sty['ls'],marker=sty['marker'],ms=3.8,lw=1.0,mfc=sty['mfc'],
                       mec=sty['color'],mew=0.9,elinewidth=0.6,capsize=1.8,capthick=0.6,label=lv,clip_on=False)

def panel(key,kind,ms,data,legend=True):
    fig=plt.figure(figsize=(W,H));ax=fig.add_axes(RECT);x=list(range(len(ms)))
    v={lv:[data[m,lv] for _,m in ms] for lv in LEVELS}
    l1=[a for a,_ in v['L1']];l2=[a for a,_ in v['L2']]
    top=min(100,nice(1.15*max(a+b for a,b in v['L1'])))
    need=[b*top/a*1.5 for a,b in zip(l1,l2) if a>=1]+[max(a+b for a,b in v['L2'])/0.6]
    topR=nice(max(need))
    ax2=ax.twinx();ax2.set_position(RECT)
    h=[line(ax,x,*zip(*v['L1']),'L1'),line(ax2,[i+DX['L2'] for i in x],*zip(*v['L2']),'L2'),line(ax,[i+DX['L3'] for i in x],*zip(*v['L3']),'L3')]
    ax.set_zorder(ax2.get_zorder()+1);ax.patch.set_visible(False)   # L1 / L3 drawn over L2
    for a,t in ((ax,top),(ax2,topR)):
        a.set_ylim(-0.05*t,t);a.yaxis.set_major_locator(plt.MaxNLocator(3,steps=[1,2,2.5,5,10]))
        a.tick_params(labelsize=7,length=2.2,width=0.5,pad=1.8)
    ax.set_xlim(-0.35,len(ms)-0.65);ax.set_xticks(x);ax.set_xticklabels([s for s,_ in ms])
    ax.tick_params(axis='x',which='both',top=False,pad=3)
    red=STY['L2']['color'];ax2.tick_params(axis='y',colors=red);ax2.spines['right'].set_color(red)
    ax.grid(axis='y',color='#c8c8c8',lw=0.4,ls=(0,(1,1.5)),zorder=0)
    for a in (ax,ax2):
        for n,s_ in a.spines.items():s_.set_linewidth(0.6);s_.set_color(red if n=='right' else 'black')
    ax.set_ylabel('L1 / L3 pass (%)',fontsize=6.8,labelpad=1.5)
    ax2.set_ylabel('L2 pass (%)',fontsize=6.8,labelpad=2,color=red)
    ax.legend(h,['L1','L2','L3'],loc='lower center',bbox_to_anchor=(0.5,1.0),ncol=3,fontsize=6.8,frameon=False,handlelength=2.0,
              columnspacing=0.9,handletextpad=0.35,borderaxespad=0.15)
    out=os.path.join(PAPER,'fig',f'scaling_{key}.pdf');fig.savefig(out);plt.close(fig);print('wrote',out,'axes',top,topR)

def main():
    data={(m,lv):get(kind,m,lv) for _,kind,ms in PANELS for _,m in ms for lv in LEVELS}
    for key,kind,ms in PANELS:panel(key,kind,ms,data)
    for key,kind,ms in PANELS:print(key,' | '.join(f"{s}: "+'/'.join(f"{data[m,lv][0]:.1f}" for lv in LEVELS) for s,m in ms))

if __name__=='__main__':main()
