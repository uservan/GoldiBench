"""Plausibility gate for generated tasks: is TARGET a result a professional would deliver for the stated intent?

Used only to filter generated tasks (never to score agents). Pixel statistics (clipping, chroma, cast) do not separate
broken edits from strong but plausible ones on the first 33 samples (2026-11-01), so a VLM judges, and the judge is a
different model from the task's generator (Qwen3.5 tasks are judged by GLM-5.3 and vice versa). The judge is validated
against the visual review of the samples before it is used as a gate (validate()).

  python plausible.py validate    # agreement with the visual labels of the first samples
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import base64,io,json,sys
import httpx
from PIL import Image
GEN={'qwen35':('http://localhost:8001/v1','Qwen3.5-397B-A17B-FP8'),'glm53':('http://localhost:8002/v1','GLM-5.3-Flash')}
OTHER={'qwen35':'glm53','glm53':'qwen35'}
Q=('Image 1 is the original, image 2 is the edited result. The client asked for: "{intent}".\n'
   'Judge only whether image 2 is a result a competent professional editor could deliver to a client for that request. '
   'It may be bold or stylised if the request asks for it. It is NOT acceptable if it shows a defect: a garish or '
   'unnatural colour cast over the whole image, large areas crushed to black or blown to white that lose the subject or '
   'scene, posterisation / banding, halos or other processing artefacts, or a look that contradicts the request. '
   'Return JSON: {{"acceptable": true/false, "defects": [..short names..], "reason": "one sentence"}}.')
SCHEMA={'type':'object','additionalProperties':False,'required':['acceptable','defects','reason'],
        'properties':{'acceptable':{'type':'boolean'},'defects':{'type':'array','items':{'type':'string','maxLength':40},'maxItems':5},
                      'reason':{'type':'string','maxLength':300}}}

def b64(p):
    im=Image.open(p).convert('RGB');im.thumbnail((768,768));b=io.BytesIO();im.save(b,'JPEG',quality=90)
    return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()

def judge(start,target,intent,judge_key,seed=0):
    base,model=GEN[judge_key]
    body={'model':model,'temperature':0,'seed':seed,'max_tokens':6000,
          'messages':[{'role':'user','content':[{'type':'text','text':Q.format(intent=intent)},
                       {'type':'image_url','image_url':{'url':b64(start)}},{'type':'image_url','image_url':{'url':b64(target)}}]}],
          'response_format':{'type':'json_schema','json_schema':{'name':'plausible','schema':SCHEMA}}}
    body['max_tokens']=16000;err=None
    for attempt in range(3):
        try:
            r=httpx.post(f'{base}/chat/completions',json=body,timeout=900);r.raise_for_status()
            return {**json.loads(r.json()['choices'][0]['message']['content']),'judge':judge_key}
        except Exception as e:err=f'{type(e).__name__}: {str(e)[:120]}';body['seed']+=1000
    return {'acceptable':None,'defects':[],'reason':f'no answer ({err})','judge':judge_key}

# Visual review of the first samples (2026-11-01, by inspection of START / TARGET): broken edits and borderline ones.
LABELS={'bad':{('darktable','b007'),('gimp','b003'),('gimp','b002'),('inkscape','b003')},
        'borderline':{('gimp','b000'),('darktable','b008')}}

def validate():
    import glob
    from concurrent.futures import ThreadPoolExecutor
    D=str(gbpaths.DATA)+'/'
    items=[]
    for p in sorted(glob.glob(D+'bench_b1_*/tasks/*/program.json')):
        t=json.load(open(p));d=p.rsplit('/',1)[0];app=t['app']
        lab='bad' if (app,t['task_id']) in LABELS['bad'] else ('borderline' if (app,t['task_id']) in LABELS['borderline'] else 'ok')
        items+=[(app,t['task_id'],lab,d,t['intent'],j) for j in ('qwen35','glm53')]
    with ThreadPoolExecutor(16) as ex:res=list(ex.map(lambda x:judge(x[3]+'/start.png',x[3]+'/target.png',x[4],x[5]),items))
    rows=[]
    for (app,tid,lab,_,_,j),r in zip(items,res):rows.append({'app':app,'task':tid,'label':lab,'judge':j,'acceptable':r['acceptable'],'defects':r['defects'],'reason':r['reason']})
    for j in ('qwen35','glm53'):
        rs=[r for r in rows if r['judge']==j]
        for lab in ('bad','borderline','ok'):
            x=[r for r in rs if r['label']==lab];print(f'{j} {lab}: {sum(r["acceptable"] is False for r in x)}/{len(x)} rejected, {sum(r["acceptable"] is None for r in x)} no answer')
    for r in rows:
        if r['acceptable'] is None or (r['label']=='bad' and r['acceptable']) or (r['label']=='ok' and r['acceptable'] is False):
            print('disagree',r['judge'],r['app'],r['task'],r['label'],r['acceptable'],r['defects'],r['reason'][:150])
    json.dump(rows,open(D+'bench_b1_plausible_validation.json','w'),indent=1)

if __name__=='__main__' and sys.argv[1:]==['validate']:validate()
