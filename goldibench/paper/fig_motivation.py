"""Motivation figure (paper Sec. 2): four panels, every number read from the motivation data files.
  (a) R1 + E1: request / task phrasing, real requests vs benchmark tasks (share of edit requests / edit tasks)
  (b) E1b: published OSWorld-Verified success on the feasible OSWorld GIMP tasks by class (adjudicated labels, 95 % CI)
  (c) E3: PSBench candidates, VLM judge without / with the reference vs CIEDE2000 <= 3
  (d) E3-X: darktable real renders, VLM judge vs our metric (unclipped candidates)
  (e) one E3 example (2026-11-16 user: the former Fig. judge-examples folded in as a fifth column): target and the
      x3-strength result the judge passes (fig_judge_examples.example)
  <python with matplotlib> scripts/paper/fig_motivation.py [--out <overleaf>/fig/motivation.pdf]"""
import argparse,collections,csv,json,os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..')
M=os.path.join(ROOT,'motivation');A=os.path.join(M,'benchmark_audit')
# reference palette (dataviz skill): ordinal blue steps 250 / 450 / 650; categorical slots orange, yellow, aqua
ORD=['#86b6ef','#2a78d6','#104281'];JUDGE,JUDGEREF,METRIC='#eb6834','#eda100','#1baf7a'
INK,INK2,MUTED,GRID,AXIS,SURF='#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7','#ffffff'
CLASSES=('explicit','vague_missing_values','vague_missing_tool')

def panel_a():
    rows=[]
    s=json.load(open(f'{A}/r1_summary.json'))
    for k,lab in (('photoshop_request','r/PhotoshopRequest'),('editmyraw','r/editmyraw'),('gimp','GIMP forums'),('darktable','darktable forums')):
        b=s[k]['both_agree'];rows.append((lab,[b[c] for c in CLASSES],b['edit_requests']))
    # PSBench per difficulty: majority class of 3 voters (split_full.csv); counts as in results_summary E1
    for lab,c in (('PSBench easy',(114,44,41)),('PSBench medium',(25,42,134)),('PSBench hard',(0,3,194))):
        n=sum(c);rows.append((lab,[100*x/n for x in c],n))
    # other benchmarks: Qwen3.5 labels, edit tasks only (ui_operation / no_edit dropped, as R1 drops non-requests)
    cnt=collections.defaultdict(collections.Counter)
    for r in csv.DictReader(open(f'{A}/split_nonps_v2.csv')):cnt[r['benchmark']][r['class_qwen35']]+=1
    for b,lab in (('OSWorld','OSWorld GIMP'),('OSExpert','OSExpert'),('CUA-World','CUA-World')):
        n=sum(cnt[b][c] for c in CLASSES);rows.append((lab,[100*cnt[b][c]/n for c in CLASSES],n))
    return rows

def panel_b():
    out=[]
    for r in csv.DictReader(open(f'{A}/success_by_class.csv')):
        if r['tasks']=='feasible' and r['labels']=='adjudicated' and r['class'] in('ui_operation',)+CLASSES[1:]:
            out.append((r['class'],100*float(r['success']),100*float(r['ci_lo']),100*float(r['ci_hi']),int(r['n_tasks'])))
    order={'ui_operation':0,'vague_missing_values':1,'vague_missing_tool':2};return sorted(out,key=lambda x:order[x[0]])

def rate(f,keep=lambda j:True):
    c=collections.defaultdict(lambda:[0,0])
    for j in map(json.loads,open(f)):
        if j['passed'] is None or not keep(j):continue
        c[j['candidate']][0]+=j['passed'];c[j['candidate']][1]+=1
    return {k:100*a/b for k,(a,b) in c.items()}

def panel_c():
    nr=rate(f'{M}/e3/judgments.jsonl');wr=rate(f'{M}/e3/judgments_ref.jsonl')
    m=collections.defaultdict(list)
    for r in csv.DictReader(open(f'{M}/e3/reference_metrics.csv')):m[r['candidate']].append(float(r['de00_mean'])<=3)
    de={k:100*sum(v)/len(v) for k,v in m.items()};cands=('end','half','over')
    return [[nr[c] for c in cands],[wr[c] for c in cands],[de[c] for c in cands]]

def panel_d():
    man={(r['task_id'],r['candidate']):r for r in csv.DictReader(open(f'{M}/e3x/candidates_manifest.csv'))}
    ok=lambda j:man[(j['task_id'],j['candidate'])]['clipped']=='False'
    jr=rate(f'{M}/e3x/judgments.jsonl',ok);mm=collections.defaultdict(list)
    for r in man.values():
        if r['clipped']=='False':mm[r['candidate']].append(r['metric_pass']=='True')
    mt={k:100*sum(v)/len(v) for k,v in mm.items()};cands=('end','half')
    return [[jr[c] for c in cands],[mt[c] for c in cands]]

def style(ax,ygrid=True):
    for s in ('top','right'):ax.spines[s].set_visible(False)
    for s in ('left','bottom'):ax.spines[s].set_color(AXIS);ax.spines[s].set_linewidth(0.6)
    ax.tick_params(colors=INK2,labelsize=6.5,length=2,width=0.5)
    if ygrid:ax.yaxis.grid(True,color=GRID,lw=0.5);ax.set_axisbelow(True)

def grouped(ax,series,colors,names,xt,title):
    n=len(series);w=0.8/n
    for i,(vals,col) in enumerate(zip(series,colors)):
        xs=[k+(i-(n-1)/2)*w for k in range(len(xt))]
        bars=ax.bar(xs,vals,w*0.92,color=col,edgecolor=SURF,lw=0.6,label=names[i])
        for x,v in zip(xs,vals):ax.text(x,v+2,f'{v:.0f}',ha='center',va='bottom',fontsize=5.5,color=INK2)
    ax.set_xticks(range(len(xt)));ax.set_xticklabels(xt,fontsize=6.5,color=INK)
    ax.set_ylim(0,112);ax.set_yticks([0,50,100]);ax.set_ylabel('pass rate (%)',fontsize=6.5,color=INK2)
    ax.set_title(title,fontsize=7,color=INK,loc='center',pad=3);style(ax)

def main(out):
    plt.rcParams.update({'font.family':'DejaVu Sans','pdf.fonttype':42})
    fig=plt.figure(figsize=(6.875,2.3))
    gs=fig.add_gridspec(1,5,width_ratios=[1.25,0.8,1.0,0.72,0.7],wspace=0.55,left=0.15,right=0.985,top=0.87,bottom=0.25)
    # (a)
    ax=fig.add_subplot(gs[0]);rows=panel_a()[::-1];y=[i if i<6 else i+1.3 for i in range(len(rows))]
    for yi,(lab,sh,n) in zip(y,rows):
        left=0
        for v,col in zip(sh,ORD):
            ax.barh(yi,v,0.72,left=left,color=col,edgecolor=SURF,lw=0.6);left+=v
    ax.set_yticks(y);ax.set_yticklabels([f'{r[0]}' for r in rows],fontsize=6,color=INK)
    ax.set_xlim(0,100);ax.set_xticks([0,50,100]);ax.set_xlabel('share of edit requests / tasks (%)',fontsize=6.2,color=INK2,labelpad=1)
    ax.text(1,y[-1]+0.75,'Real requests',fontsize=6,color=INK,fontweight='bold',va='center')
    ax.text(1,y[5]+0.75,'Benchmark tasks',fontsize=6,color=INK,fontweight='bold',va='center')
    ax.set_ylim(-0.6,y[-1]+1.2)
    style(ax,ygrid=False);ax.xaxis.grid(True,color=GRID,lw=0.5);ax.set_axisbelow(True)
    ax.set_title('(a) Request / task phrasing',fontsize=7,color=INK,loc='center',pad=3)
    LEG=dict(ncol=3,fontsize=5.8,frameon=False,loc='lower left',handlelength=1,columnspacing=0.9,handletextpad=0.4,borderaxespad=0)
    LEGY=0.03   # both legends on the same baseline
    fig.legend([Patch(color=c) for c in ORD],['explicit','missing values','missing tool'],bbox_to_anchor=(0.16,LEGY),**LEG)
    # (b)
    ax=fig.add_subplot(gs[1]);b=panel_b()
    xs=range(len(b));ax.bar(xs,[r[1] for r in b],0.62,color=ORD[1],edgecolor=SURF,lw=0.6)
    for x,r in zip(xs,b):   # no CI drawn for n = 2 (degenerate bootstrap)
        if r[4]>2:ax.errorbar([x],[r[1]],yerr=[[r[1]-r[2]],[r[3]-r[1]]],fmt='none',ecolor=INK2,elinewidth=0.6,capsize=1.5)
    for x,r in zip(xs,b):ax.text(x,4,f'{r[1]:.0f}',ha='center',va='bottom',fontsize=5.8,color=SURF)
    ax.set_xticks(list(xs));ax.set_xticklabels(['UI\nop.','miss.\nvalues','miss.\ntool'],fontsize=5.6,color=INK)
    ax.set_ylim(0,100);ax.set_yticks([0,50,100]);ax.set_ylabel('agent success (%)',fontsize=6.5,color=INK2)
    ax.set_title('(b) Agent success',fontsize=7,color=INK,loc='center',pad=3);style(ax)
    # (c)
    ax=fig.add_subplot(gs[2])
    grouped(ax,panel_c(),[JUDGE,JUDGEREF,METRIC],['VLM judge','VLM judge + reference','CIEDE2000 / our metric'],
            ['correct','×0.5','×3'],'(c) Judge: PSBench')
    # (d)
    ax=fig.add_subplot(gs[3])
    grouped(ax,panel_d(),[JUDGE,METRIC],['VLM judge','metric'],['correct','×0.5'],'(d) Judge: darktable')
    ax.set_ylabel('')
    fig.legend([Patch(color=c) for c in (JUDGE,JUDGEREF,METRIC)],['VLM judge','VLM judge + reference','reference metric'],
               bbox_to_anchor=(0.6,LEGY),**LEG)
    # (e) one example: target vs x3 result, judge verdicts and the reference metric
    from fig_judge_examples import example,thumb
    paths,ok,tot,_=example('ps','312','over')
    import re as _re;de=float(_re.search(r'([0-9.]+)\)',_).group(1))
    sub=gs[4].subgridspec(2,1,hspace=0.12);T=thumb(paths[1],500);Wr=thumb(paths[2],500).resize(T.size)
    for k,(im,lab,ec,lw) in enumerate(((T,'target',AXIS,0.5),(Wr,'×3 strength',JUDGE,1.2))):
        a=fig.add_subplot(sub[k]);a.imshow(im,aspect='auto');a.set_xticks([]);a.set_yticks([])
        for sp in a.spines.values():sp.set_color(ec);sp.set_linewidth(lw)
        a.text(0.04,0.93,lab,transform=a.transAxes,ha='left',va='top',fontsize=5.2,color='#ffffff',bbox=dict(boxstyle='round,pad=0.2',fc='#0b0b0bb0',ec='none'))
        if k==0:a.set_title('(e) Example',fontsize=7,color=INK,loc='center',pad=3)
        else:
            a.text(0.5,-0.08,f'judge: pass {ok}/{tot}',transform=a.transAxes,ha='center',va='top',fontsize=5.8,color=JUDGE,fontweight='bold')
            a.text(0.5,-0.3,f'metric: fail',transform=a.transAxes,ha='center',va='top',fontsize=5.8,color=METRIC,fontweight='bold')
    os.makedirs(os.path.dirname(out),exist_ok=True);fig.savefig(out,dpi=250)   # PDF only (vector) for the paper
    print('wrote',out)
    for r in panel_a()[::-1][::-1]:print('  a',r[0],[round(x) for x in r[1]],'n',r[2])
    print('  b',[(r[0],round(r[1]),round(r[2]),round(r[3]),r[4]) for r in panel_b()])
    print('  c',[[round(v) for v in s] for s in panel_c()]);print('  d',[[round(v) for v in s] for s in panel_d()])

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=os.path.join(ROOT,'6af23dcfd2c227248fab917b','fig','motivation.pdf'))
    main(ap.parse_args().out)
