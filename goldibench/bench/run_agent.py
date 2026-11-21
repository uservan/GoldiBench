"""Pilot knowledge channel: a VLM edits by writing darktable programs, sees each render, and revises.

Levels (same hidden program and target):
  L1  instruction lists modules and exact settings; START shown; modules limited to the task's set
  L2  START + TARGET + the task's module set (no settings)
  L3  START + TARGET; any module of the library
Each round the model returns the full program; we render it and show RESULT (no numeric feedback; only the newest RESULT
image stays in the history, older ones are replaced by a placeholder, so a request never exceeds 3 images).
Up to --rounds rounds or until the model says done. Every round is logged; resumable per (task, level, model).
Episodes go to runs/<--run>/<task>/<level>_<model>/ so harness versions never mix (v1 = the first pilot, under tasks/).
--manual: the app's manual (darktable 5.6, GIMP 3.0, RawPedia) is installed as a skill, consulted the VisualSkill way (manual.py). The first message
names the skill only; instead of a program the model may reply with a tool call: {"tool": "read_skill"} (SKILL.md: how
to consult + table of contents), {"tool": "list_topics"} or {"tool": "load_topic", "topic": t} (one manual page,
verbatim). The result comes back in the next message. Tool calls do not use up rendering rounds (at most TOOL_CALLS per
episode).
--knowledge image|image_state (L2 only): the Effect Oracle. An effect sheet of the task's tools (knowledge.py) is shown
after TARGET: `image` on a reference photo outside the task set, `image_state` on START itself (never the TARGET program).
`table_state` gives the image_state renders as measured statistics (text), `table_state_diff` adds TARGET - START on the
same statistics (perception oracle).
--minimanual visual|text (L2 only): the task's mini manual in the first message after TARGET (minimanual.py): a reference
card per task tool written by an open model from the manual + an effect sheet of the task tools on an exemplar (visual),
or the same cards without the sheet (text). The rest of the prompt is unchanged.
--tasks-file: run only the task ids listed in the file (subsets, e.g. the B-1 manual experiment).
--feedback numeric: each RESULT also reports its mean CIEDE2000 to TARGET and START's (the signal search.py uses).
--forced: every one of --rounds rounds is used (the prompt says so; done is ignored). Without it ~95 % of v5 episodes
set done=true on their first program and never see a RESULT.
--log-replies (off by default; added after the paper, it does not change prompts, sampling or scoring): every model call
is appended to <episode>/calls.jsonl in full: the reply message (content, reasoning_content / reasoning, tool_calls),
finish_reason, usage (prompt / completion / reasoning tokens as the server reports them) and latency. The paper's runs
did not have it: they kept only the program and the first 400 characters of the rationale (episode.json).
"""
from pathlib import Path
import argparse,asyncio,base64,io,json,sys,time
from concurrent.futures import ThreadPoolExecutor
import httpx
from PIL import Image
sys.path.insert(0,str(Path(__file__).parent))
import gbpaths
import ops,manual,knowledge,minimanual
from make_pilot import l1_text,OUT,lab,de

MODELS={'qwen35':('http://localhost:8001/v1','Qwen3.5-397B-A17B-FP8'),'glm53':('http://localhost:8002/v1','GLM-5.3-Flash')}
# Qwen3.5 size ladder (paper-plan D-3 / M-V1, M-V4 on the program channel; scripts/pipelines/b1_ladder.sh); 397B = qwen35
MODELS.update({f'qwen35_{k}':(f'http://localhost:{p}/v1',f'Qwen3.5-{n}') for k,p,n in
               [('0.8b',8031,'0.8B'),('2b',8032,'2B'),('4b',8033,'4B'),('9b',8034,'9B'),('27b',8035,'27B'),('35b_a3b',8036,'35B-A3B'),('122b_a10b',8037,'122B-A10B-FP8')]})
# further open multimodal models (paper-plan models step; scripts/pipelines/b1_more.sh), ports as in e3_more_judges.sh
MODELS.update({'dsv41':('http://localhost:8003/v1','DeepSeek-V4.1-Flash'),'step37':('http://localhost:8004/v1','Step-3.7-Flash-FP8'),
               'nemo35':('http://localhost:8005/v1','NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16')})
# closed models on Amazon Bedrock through bedrock_proxy.py (2026-11-08)
MODELS.update({k:('http://localhost:8102/v1',k) for k in ('opus55','opus55max','gpt61sol')})
# Your own models: configs/models.yaml, section `program:` (any OpenAI-compatible chat endpoint; optional api_key_env).
# Entries there override the paper defaults above (local vLLM servers, scripts/serve_vllm.sh; closed models: bedrock_proxy.py).
_CFG=gbpaths.models('program')
MODELS.update({k:(v['base_url'].rstrip('/'),v['model']) for k,v in _CFG.items()})   # 8102 from 18:10: gpt61sol at reasoning effort high   # grok47 / kimi31 dropped by the user (2026-11-08)
RENDER=ThreadPoolExecutor(8)   # darktable already uses many threads per render
TOOL_CALLS=8

def img(p,bound=768):
    im=Image.open(p).convert('RGB');im.thumbnail((bound,bound));b=io.BytesIO();im.save(b,'JPEG',quality=90)
    return {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()}}

def turn_schema(allowed,can_read=False):
    s=ops.schema(allowed);s['properties']['done']={'type':'boolean'};s['required']=['rationale','steps','done']
    if not can_read:return s
    tool=lambda name,**props:{'type':'object','additionalProperties':False,'required':['tool',*props],
                              'properties':{'tool':{'const':name},**props}}
    return {'anyOf':[tool('read_skill'),tool('list_topics'),tool('load_topic',topic={'type':'string'}),s]}

def manual_note():
    return (f'\nINSTALLED SKILL: {manual.SKILL_NAME}: {manual.skill_desc()}\n'
            'Tools (reply with exactly one tool call instead of a program; the result comes in the next message): '
            '{"tool": "read_skill"} returns its SKILL.md (how to consult it and its table of contents); '
            '{"tool": "list_topics"} lists topic names; {"tool": "load_topic", "topic": "<topic>"} returns one topic. '
            f'Tool calls do not use up rendering rounds; up to {TOOL_CALLS} per task, at any step. Before writing a program '
            f'where you are unsure what a {ops.UNIT_WORD} or setting does, read the skill and load the matching topic.\n')

def tool_result(reply):
    t=reply['tool']
    if t=='read_skill':return manual.skill_md()
    if t=='list_topics':return '\n'.join(manual.pages())
    topic=str(reply.get('topic','')).strip().removesuffix('/guide.md').strip('/')
    return manual.read(topic) if topic in manual.pages() else f'unknown topic "{topic}"; call list_topics for valid names.'

def end_text(forced):
    if not forced:return 'Return the program. Set done=true when you are satisfied.'
    return (f'Return the program. You get {forced} rounds: after each one you see its RESULT and write the full program '
            'again; the program of the last round is scored (done is ignored).')

def tool_content(reply):
    """The tool result as message content: text, plus the figures of a VisualSkill multimodal topic (manual.read_parts)."""
    if reply['tool']!='load_topic' or str(reply.get('topic','')).strip().removesuffix('/guide.md').strip('/') not in manual.pages():
        return [{'type':'text','text':tool_result(reply)}]
    topic=str(reply['topic']).strip().removesuffix('/guide.md').strip('/')
    return [{'type':'text','text':x} if isinstance(x,str) else img(x,1024) for x in manual.read_parts(topic)]

def merge_text(parts):
    out=[]
    for c in parts:
        if c['type']=='text' and out and out[-1]['type']=='text':out[-1]={'type':'text','text':out[-1]['text']+c['text']}
        else:out.append(c)
    return out

def first_message(task,level,d,allowed,use_manual=False,know=None,forced=0,mini=None):
    u=ops.UNIT_WORD
    head=(f'You edit photos in {ops.PRODUCT} by writing a program: a list of steps, each naming a {u} id and the fields you set. '
          f'Fields you omit keep the {u} default. '+ops.order_note()+'\n'
          f'Available {u}s:\n'+ops.spec_text(allowed)+'\n'+(manual_note() if use_manual else '')+'\n')
    if level=='L1':
        return [{'type':'text','text':head+'Task: '+l1_text(task['program'])+'\nSTART:'},img(d/'start.png'),
                {'type':'text','text':end_text(forced)}]
    goal=('Task: edit START so that it matches TARGET as closely as possible. '+
          (f"The target was produced with exactly these {ops.UNIT_WORD}s: {', '.join(allowed)}. " if level=='L2' else f'Any of the {ops.UNIT_WORD}s may be needed. '))
    if know in('table_state','table_state_diff'):sheet=[{'type':'text','text':knowledge.table_for(task,know=='table_state_diff')}]
    elif know=='diff_image':sheet=[{'type':'text','text':knowledge.DIFF_NOTE},img(knowledge.diff_image_for(task),2400)]
    elif know:sheet=[{'type':'text','text':knowledge.note(know)},img(knowledge.sheet_for(task,know),2400)]   # rows stay legible
    else:sheet=[]
    if mini:sheet=minimanual.blocks(task,mini=='visual',img)
    return [{'type':'text','text':head+goal+'\nSTART:'},img(d/'start.png'),{'type':'text','text':'TARGET:'},img(d/'target.png'),*sheet,
            {'type':'text','text':end_text(forced)}]

def feedback(d,out):
    lt=lab(d/'target.png')
    return (f'. Distance to TARGET (mean CIEDE2000, lower is better): {de(lab(out),lt):.2f}; '
            f'START was {de(lab(d/"start.png"),lt):.2f}')

def log_call(run,r,calls,attempt,body,resp,dt):
    """--log-replies: one line per model call with the full reply and the server's token usage (images not repeated)."""
    try:j=resp.json()
    except ValueError:j={'raw':resp.text[:20000]}
    ch=(j.get('choices') or [{}])[0];msg=ch.get('message') or {}
    rec={'round':r,'tool_calls_so_far':calls,'attempt':attempt,'seed':body.get('seed'),'model':body.get('model'),
         'http_status':resp.status_code,'latency_s':round(dt,3),'finish_reason':ch.get('finish_reason'),
         'content':msg.get('content'),'reasoning_content':msg.get('reasoning_content',msg.get('reasoning')),
         'tool_calls':msg.get('tool_calls'),'usage':j.get('usage'),'error':j.get('error') or (None if ch else j)}
    with open(run/'calls.jsonl','a') as f:f.write(json.dumps(rec)+'\n')

async def episode(client,sem,args,key,task,level):
    base,model=MODELS[key];d=OUT/'tasks'/task['task_id'];run=OUT/'runs'/args.run/task['task_id']/f'{level}_{key}';run.mkdir(parents=True,exist_ok=True)
    allowed=task['modules'] if level in('L1','L2') else list(ops.OPS)
    msgs=[{'role':'user','content':first_message(task,level,d,allowed,args.manual,args.knowledge,args.rounds if args.forced else 0,args.minimanual)}];rounds=[];calls=0;r=0
    async with sem:
        while r<args.rounds:
            # Two images + a 10-module schema: reasoning alone can pass 6k tokens, so leave room for the answer.
            can_read=args.manual and calls<TOOL_CALLS
            body={'model':model,'messages':msgs,'temperature':0.6,'top_p':0.95,'seed':args.seed+r+100*calls,'max_tokens':args.max_tokens,
                  'response_format':{'type':'json_schema','json_schema':{'name':'turn','schema':turn_schema(allowed,can_read)}}}
            reply=None;errors=[]
            for attempt in range(3):
                try:
                    t0=time.time()
                    resp=await client.post(f'{base}/chat/completions',json=body,timeout=900,headers=gbpaths.api_headers(_CFG.get(key)))
                    if args.log_replies:log_call(run,r,calls,attempt,body,resp,time.time()-t0)
                    resp.raise_for_status()
                    ch=resp.json()['choices'][0];content=ch['message']['content']
                    try:reply=json.loads(content);break
                    except (json.JSONDecodeError,TypeError):errors.append({'finish_reason':ch.get('finish_reason'),'tail':str(content)[-200:]})
                except (httpx.HTTPError,KeyError,IndexError) as e:errors.append({'exception':repr(e)[:300]})
                body['seed']+=1000
            if reply is None:rounds.append({'round':r,'error':'no valid reply','attempts':errors});break
            if 'tool' in reply:
                calls+=1;rounds.append({'round':r,'tool':reply['tool'],'topic':reply.get('topic'),'retries':errors})
                # Figures of earlier topics are dropped (image limit per request): START, TARGET, newest RESULT, newest topic.
                for m in msgs[1:]:
                    if m['role']=='user' and m['content'][0].get('text','').startswith('TOOL RESULT'):
                        m['content']=[c if c['type']=='text' else {'type':'text','text':'[earlier figure omitted]'} for c in m['content']]
                msgs+=[{'role':'assistant','content':json.dumps(reply)},
                       {'role':'user','content':merge_text([{'type':'text','text':f"TOOL RESULT ({reply['tool']}):\n"},*tool_content(reply),{'type':'text','text':'\n\n'+
                        (f'({TOOL_CALLS-calls} tool calls left.) Return the program, or call another tool.' if calls<TOOL_CALLS else
                         'No tool calls left. Return the program.')}])}]
                continue
            prog,v0=ops.from_steps(reply.get('steps'));prog,viol=ops.clean(prog,allowed);viol=v0+viol
            out=run/f'round{r}.png'
            try:await asyncio.get_running_loop().run_in_executor(RENDER,ops.render,task['source_path'],prog,out)
            except Exception as e:   # a program the app cannot render (e.g. an Inkscape filter past the timeout) fails the episode
                rounds.append({'round':r,'error':'render failed','program_failed':prog,'detail':repr(e)[:300]});break
            rounds.append({'round':r,'program':prog,'violations':viol,'retries':errors,'done':bool(reply.get('done')),'rationale':str(reply.get('rationale',''))[:400]})
            if (reply.get('done') and not args.forced) or r==args.rounds-1:break
            r+=1
            # Servers accept 4 images per request (START, TARGET, ...): keep only the newest RESULT image.
            for m in msgs[1:]:
                if m['role']=='user':m['content']=[c if c['type']=='text' else {'type':'text','text':'[earlier RESULT image omitted]'} for c in m['content']]
            msgs+= [{'role':'assistant','content':json.dumps(reply)},
                    {'role':'user','content':[{'type':'text','text':'RESULT of your program'+(f" (ignored: {'; '.join(viol)})" if viol else '')+
                     (feedback(d,out) if args.feedback else '')+':'},img(out),
                     {'type':'text','text':(f'Round {r+1} of {args.rounds}: return the full program again, changed to get closer '
                      'to TARGET or unchanged.' if args.forced else 'Revise the full program if needed, or keep it and set done=true.')}]}]
    rec={'task_id':task['task_id'],'level':level,'model':key,'rounds':rounds}
    (run/'episode.json').write_text(json.dumps(rec,indent=1));print(task['task_id'],level,key,len(rounds),flush=True)
    return rec

async def main_async(args):
    tasks=[json.loads(l) for l in gbpaths.open_tasks(OUT/'tasks.jsonl')]
    if args.limit:tasks=tasks[:args.limit]   # smoke tests only
    if args.tasks_file:keep=open(args.tasks_file).read().split();tasks=[t for t in tasks if t['task_id'] in keep]
    jobs=[(k,t,l) for k in args.models for t in tasks for l in args.levels if not (OUT/'runs'/args.run/t['task_id']/f'{l}_{k}'/'episode.json').exists()]
    sems={k:asyncio.Semaphore(args.concurrency) for k in args.models}
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=None)) as client:
        await asyncio.gather(*[episode(client,sems[k],args,k,t,l) for k,t,l in jobs])
    print(json.dumps({'episodes':len(jobs)}))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--models',nargs='+',default=list(MODELS));ap.add_argument('--levels',nargs='+',default=['L1','L2','L3'])
    ap.add_argument('--run',default='v2');ap.add_argument('--rounds',type=int,default=4);ap.add_argument('--seed',type=int,default=0);ap.add_argument('--concurrency',type=int,default=16)
    ap.add_argument('--manual',nargs='?',const='manual',choices=['manual','visualskill_mm','visualskill_text'],
                    help='install the app manual (or VisualSkill\'s own skill for the app) as a load_topic skill (manual.py)')
    ap.add_argument('--knowledge',choices=['image','image_state','table_state','table_state_diff','diff_image'],help='Effect Oracle after TARGET (L2 only)')
    ap.add_argument('--minimanual',choices=['visual','text'],help='per-task mini manual after TARGET (L2 only, minimanual.py)')
    ap.add_argument('--tasks-file',help='only these task ids (one per line)')
    ap.add_argument('--feedback',choices=['numeric'],help='report the distance to TARGET with every RESULT')
    ap.add_argument('--forced',action='store_true',help='use every round (done ignored)')
    ap.add_argument('--limit',type=int,help='first N tasks only (smoke test)')
    ap.add_argument('--max-tokens',type=int,default=16000,help='per-call output budget (reasoning + answer)')
    ap.add_argument('--log-replies',action='store_true',help='save every model call in full (reply, reasoning, usage, latency) to <episode>/calls.jsonl')
    args=ap.parse_args()
    if OUT.name.startswith(('bench_b1_','bench_b2_')):   # new benchmark sets: only frozen, unchanged tasks (freeze_b1.py --approved)
        import hashlib
        f=OUT/'FROZEN'
        if not f.exists():raise SystemExit(f'{OUT.name} is not frozen: run report_b1.py, get sign-off, then freeze_b1.py --approved')
        h=json.loads(f.read_text())['tasks']
        bad=[t for t,x in h.items() if hashlib.sha256((OUT/'tasks'/t/'program.json').read_bytes()).hexdigest()!=x]
        if bad:raise SystemExit(f'{OUT.name}: tasks changed after freezing: {bad[:5]}')
        listed={json.loads(l)['task_id'] for l in gbpaths.open_tasks(OUT/'tasks.jsonl')}   # tasks.jsonl must list exactly the frozen tasks
        if listed!=set(h):raise SystemExit(f'{OUT.name}: tasks.jsonl does not match FROZEN (extra {sorted(listed-set(h))[:5]}, missing {sorted(set(h)-listed)[:5]})')
    if args.manual and args.manual!='manual':manual.use(args.manual)
    if args.knowledge and args.levels!=['L2']:ap.error('--knowledge is for L2 (the sheet covers the task tools)')
    if args.minimanual and args.levels!=['L2']:ap.error('--minimanual is for L2 (it covers the task tools)')
    if args.minimanual:   # sheets and cards up front (renders + one writer call per tool), not inside the episode loop
        keep=open(args.tasks_file).read().split() if args.tasks_file else None
        for t in [json.loads(l) for l in gbpaths.open_tasks(OUT/'tasks.jsonl')]:
            if keep is None or t['task_id'] in keep:minimanual.blocks(t,True,lambda p,b:None)
    if args.knowledge:   # build sheets up front (GIMP / darktable renders), not inside the episode loop
        keep=open(args.tasks_file).read().split() if args.tasks_file else None
        for t in [json.loads(l) for l in gbpaths.open_tasks(OUT/'tasks.jsonl')]:
            if keep is None or t['task_id'] in keep:
                if args.knowledge=='diff_image':knowledge.diff_image_for(t)
                else:knowledge.sheet_for(t,'image_state' if 'table' in args.knowledge else args.knowledge)
    asyncio.run(main_async(args))
if __name__=='__main__':main()
