"""Single-column figure: judge-stress-test examples where a wrong-magnitude result is visibly wrong but the VLM judge
passes it (PSBench prompt verbatim). Rows: START / target / wrong result, annotated with the judge verdicts and the
reference metric. Sources:
  ps:<task>:<cand>   PSBench judge stress test (motivation/e3: 5 judges x 3 repeats; CIEDE2000 to the author's result)
  dt:<task>:<cand>   darktable judge stress test (motivation/e3x: 2 judges x 3 repeats x explicit / vague; our metric)
  <python with matplotlib> scripts/paper/fig_judge_examples.py [--examples ps:586:half ps:312:over] [--out ...pdf]"""
import argparse,collections,csv,json,os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..');MOT=os.path.join(ROOT,'motivation')
INK,BAD,EDGE='#0b0b0b','#d03b3b','#c3c2b7'
LABEL={'half':'×0.5 strength','over':'×3 strength','opposite':'opposite'}

def verdicts(f,keys):
    v=collections.defaultdict(list)
    for j in map(json.loads,open(f)):
        if j['passed'] is not None and j['task_id'] in keys:v[(j['task_id'],j['candidate'])].append(j['passed'])
    return v

def example(src,t,c):
    """-> (start, target, wrong) paths, judge passes, judgements, metric text"""
    if src=='ps':
        p={r['candidate']:r['path'] for r in csv.DictReader(open(f'{MOT}/e3/candidates_manifest.csv')) if r['task_id']==t}
        de={r['candidate']:float(r['de00_mean']) for r in csv.DictReader(open(f'{MOT}/e3/reference_metrics.csv')) if r['task_id']==t}
        v=verdicts(f'{MOT}/e3/judgments.jsonl',{t})[(t,c)]
        return (p['identity'],p['end'],p[c]),sum(v),len(v),f'CIEDE2000: fail ($\\Delta E$ {de[c]:.1f})'
    man={(r['task_id'],r['candidate']):r for r in csv.DictReader(open(f'{MOT}/e3x/candidates_manifest.csv'))}
    ks={f'{t}_explicit',f'{t}_vague'};vv=verdicts(f'{MOT}/e3x/judgments.jsonl',ks);v=sum((vv[(k,c)] for k in sorted(ks)),[])
    m=man[(f'{t}_explicit',c)]
    return (man[(f'{t}_explicit','identity')]['path'],man[(f'{t}_explicit','end')]['path'],m['path']),sum(v),len(v),\
           f'ours: fail ($\\Delta E$ {float(m["de00"]):.1f})'

def thumb(p,w=420):
    im=Image.open(p).convert('RGB');return im.resize((w,round(im.height*w/im.width)),Image.LANCZOS)

def main(examples,out):
    plt.rcParams.update({'font.family':'DejaVu Sans','pdf.fonttype':42})
    rows=[(c,)+example(*e.split(':')) for e in examples for c in [e.split(':')[2]]];n=len(rows)
    ims=[[thumb(p) for p in r[1]] for r in rows]
    # row height follows the image aspect (all three cells of a row share START's aspect)
    W=3.3;cw=(W-0.06)/3;hs=[cw*im[0].height/im[0].width for im in ims];gap=0.3;top=0.17
    H=top+sum(hs)+gap*n
    fig=plt.figure(figsize=(W,H));y=H-top
    for i,(r,im) in enumerate(zip(rows,ims)):
        c,paths,ok,tot,metric=r;y-=hs[i]
        for j in range(3):
            ax=fig.add_axes([(0.01+j*(cw+0.02))/W,y/H,cw/W,hs[i]/H])
            ax.imshow(im[j].resize((im[0].width,im[0].height)) if j else im[0],aspect='auto');ax.set_xticks([]);ax.set_yticks([])
            for s in ax.spines.values():s.set_linewidth(0.4);s.set_color(EDGE)
            if i==0:ax.set_title(['START','Target','Wrong result'][j],fontsize=7,color=INK,pad=2)
            if j==2:
                for s in ax.spines.values():s.set_linewidth(1.2);s.set_color(BAD)
                ax.text(0.03,0.95,LABEL[c],transform=ax.transAxes,ha='left',va='top',fontsize=5.2,color='#ffffff',
                        bbox=dict(boxstyle='round,pad=0.25',fc='#0b0b0bb0',ec='none'))
                ax.text(0.5,-0.04/hs[i],f'VLM judge: pass {ok}/{tot}',transform=ax.transAxes,ha='center',va='top',fontsize=5.4,color=INK)
                ax.text(0.5,-0.15/hs[i],metric,transform=ax.transAxes,ha='center',va='top',fontsize=5.4,color=BAD)
        y-=gap
    os.makedirs(os.path.dirname(out),exist_ok=True);fig.savefig(out,dpi=300);print('wrote',out)
    for e,r in zip(examples,rows):print(' ',e,f'judge {r[2]}/{r[3]}',r[4])

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--examples',nargs='+',default=['ps:586:half','ps:312:over'])
    ap.add_argument('--out',default=os.path.join(os.environ.get('GOLDIBENCH_PAPER', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'paper_out')),'fig','judge_examples.pdf'));a=ap.parse_args();main(a.examples,a.out)
