"""Closed models on Amazon Bedrock behind the OpenAI-style /v1/chat/completions endpoint that run_agent.py already speaks,
so the agent harness, prompts, images and round logic stay identical to the open-model runs (2026-11-08, user request).

  Claude (opus55 ...)       Anthropic SDK, AnthropicBedrock (bedrock-runtime; the Mantle endpoint is not enabled on this
                            account: 404 for every model id, 2026-11-08); the turn schema as structured output
                            (output_config.format); thinking always on, effort from MODELS (temperature / seed are
                            not accepted by these models and are dropped)
  others (gpt61sol, kimi31, grok47)  bedrock-runtime Converse; the JSON schema is appended to the request as text
                            (no constrained decoding there; temperature is rejected, provider default sampling); the reply's JSON object is extracted; run_agent retries
                            invalid JSON 3x as for the open models
Every call is written to the cost ledger <DATA>/logs/bedrock_ledger.jsonl (time, model, tokens, USD at PRICES, whether
the price is an assumption); `python bedrock_proxy.py --ledger` prints the totals.

  <bedrock env>/bin/python bedrock_proxy.py [--port 8101]     (AWS credentials: the instance role, region us-west-2)
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import argparse,asyncio,base64,json,re,sys,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from aiohttp import web
import boto3
from botocore.config import Config
from anthropic import AsyncAnthropicBedrock
import anthropic

LEDGER=Path(str(gbpaths.DATA)+'/logs/bedrock_ledger.jsonl')
REGION='us-west-2'
# served name -> (backend, Bedrock id, extra)
MODELS={'opus55':('claude','us.anthropic.claude-opus-5-5',{'effort':'high'}),
        'opus55max':('claude','us.anthropic.claude-opus-5-5',{'effort':'max'}),   # does more thinking help? (2026-11-08)
        'gpt61sol':('converse','us.openai.gpt-6.1-sol',{}),   # reasoning on by default (redacted), provider-default effort: effort high
        # (18:45-18:50) cost 4x per call ($0.098 vs $0.023); the user chose the default (plan A, 2026-11-08)
}   # kimi31 (throttled) and grok47 (10+ min per call) dropped by the user on 2026-11-08; prices kept for the ledger
# USD per 1M tokens (input, output, assumed?). Claude: Anthropic list price (Bedrock bills separately; check the AWS bill).
# Kimi K3.1: aws.amazon.com/bedrock/pricing, 2026-11-08 (US cross-region $4.40 / $22; global $4.00 / $20, kept the higher). GPT-6.1 / Grok 4.7: not on the public page,
# not readable through the Pricing API with this role -> conservative placeholder, flagged.
PRICES={'opus55':(4.0,20.0,False),'opus55max':(4.0,20.0,False),'kimi31':(4.4,22.0,False),'gpt61sol':(5.0,25.0,True),'grok47':(5.0,25.0,True)}

import os
BUDGET=float(os.environ.get('BEDROCK_BUDGET_USD','250'))   # ledger total (all runs) above which new requests are refused
_SP={'off':0,'usd':0.0}
def spent():   # several proxy processes may share the ledger, so it is re-read on every request -- incrementally
    # (2026-11-14: re-parsing the whole 41 MB ledger per request made the proxy CPU-bound under ~100 concurrent episodes;
    # a line still being written by another process is left for the next call instead of failing to parse)
    if not LEDGER.exists():return 0.0
    with open(LEDGER,'rb') as f:
        f.seek(_SP['off']);chunk=f.read()
    end=chunk.rfind(b'\n')+1
    for l in chunk[:end].splitlines():
        try:_SP['usd']+=json.loads(l).get('usd',0)
        except ValueError:pass
    _SP['off']+=end;return _SP['usd']

def log(model,inp,out,extra=None):
    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    pi,po,assumed=PRICES[model];usd=inp*pi/1e6+out*po/1e6
    with LEDGER.open('a') as f:
        f.write(json.dumps({'t':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'model':model,'input_tokens':inp,'output_tokens':out,
                            'usd':round(usd,6),'price_assumed':assumed,**(extra or {})})+'\n')

def ledger_summary():
    tot={}
    for j in map(json.loads,open(LEDGER)) if LEDGER.exists() else []:
        s=tot.setdefault(j['model'],[0,0,0,0.0,j['price_assumed']]);s[0]+=1;s[1]+=j['input_tokens'];s[2]+=j['output_tokens'];s[3]+=j['usd']
    print(f"{'model':10s} {'calls':>6s} {'input tok':>11s} {'output tok':>11s} {'USD':>9s}")
    for m,(c,i,o,u,a) in sorted(tot.items()):print(f"{m:10s} {c:6d} {i:11d} {o:11d} {u:9.2f}{'  (price assumed)' if a else ''}")
    print(f"{'total':10s} {sum(v[0] for v in tot.values()):6d} {'':11s} {'':11s} {sum(v[3] for v in tot.values()):9.2f}")

def data_url(u):
    m=re.match(r'data:image/(\w+);base64,(.*)',u,re.S);return m.group(1).replace('jpg','jpeg'),m.group(2)

# ---- Claude (Anthropic SDK on Bedrock) ----
def to_anthropic(msgs):
    out=[]
    for m in msgs:
        c=m['content']
        if isinstance(c,str):out.append({'role':m['role'],'content':c});continue
        blocks=[]
        for p in c:
            if p['type']=='text':blocks.append({'type':'text','text':p['text']})
            else:fmt,b=data_url(p['image_url']['url']);blocks.append({'type':'image','source':{'type':'base64','media_type':f'image/{fmt}','data':b}})
        out.append({'role':m['role'],'content':blocks})
    return out

UNSUPPORTED={'minimum','maximum','exclusiveMinimum','exclusiveMaximum','multipleOf','minLength','maxLength','maxItems','pattern'}
def strict(s):
    """Structured outputs: additionalProperties false on every object; numeric / length / item-count constraints are not
    supported (400), so they are dropped here and the full schema goes into the prompt as text (out-of-range values are
    clipped by ops.clean in run_agent, as for every model)."""
    if isinstance(s,dict):
        s={k:strict(v) for k,v in s.items() if k not in UNSUPPORTED and not (k=='minItems' and isinstance(v,int) and v>1)}
        if s.get('type')=='object':s.setdefault('additionalProperties',False)
        return s
    return [strict(x) for x in s] if isinstance(s,list) else s

async def call_claude(client,name,bid,extra,body):
    schema=body.get('response_format',{}).get('json_schema',{}).get('schema')
    oc={'effort':extra['effort']}
    # 2026-11-15: a 'system' message (V-6 judge) must be the top-level system parameter on Bedrock Claude (400 otherwise)
    sysmsg=[m for m in body['messages'] if m['role']=='system']
    msgs=to_anthropic([m for m in body['messages'] if m['role']!='system'])
    kw={'system':'\n\n'.join(m['content'] if isinstance(m['content'],str) else ''.join(p.get('text','') for p in m['content']) for m in sysmsg)} if sysmsg else {}
    if schema:
        oc['format']={'type':'json_schema','schema':strict(schema)}
        last=msgs[-1]['content'];last=[{'type':'text','text':last}] if isinstance(last,str) else last
        msgs[-1]['content']=last+[{'type':'text','text':'\nThe reply must also respect every bound in this JSON schema:\n'+json.dumps(schema)}]
    mode='structured'
    try:
        async with client.messages.stream(model=bid,max_tokens=body.get('max_tokens',32000),messages=msgs,output_config=oc,**kw) as st:
            msg=await st.get_final_message()
    except anthropic.BadRequestError as e:
        # L3 offers every tool: the schema compiles to a grammar Bedrock rejects ("compiled grammar is too large").
        # Then the schema stays in the prompt as text only and the JSON object is extracted, as for the Converse models.
        if 'grammar is too large' not in str(e):raise
        mode='text';oc.pop('format',None)
        msgs[-1]['content'][-1]['text']='\nReply with exactly one JSON object and nothing else. It must validate against this JSON schema:\n'+json.dumps(schema)
        async with client.messages.stream(model=bid,max_tokens=body.get('max_tokens',32000),messages=msgs,output_config=oc,**kw) as st:
            msg=await st.get_final_message()
    u=msg.usage;log(name,u.input_tokens+(u.cache_read_input_tokens or 0)+(u.cache_creation_input_tokens or 0),u.output_tokens,{'stop':msg.stop_reason,'format':mode})
    text=''.join(b.text for b in msg.content if b.type=='text')
    if mode=='text':text=extract_json(text)
    return text,('length' if msg.stop_reason=='max_tokens' else 'stop' if msg.stop_reason!='refusal' else 'refusal')

# ---- other providers (Converse) ----
RT=boto3.client('bedrock-runtime',region_name=REGION,config=Config(retries={'max_attempts':10,'mode':'adaptive'},read_timeout=900))
POOL=ThreadPoolExecutor(64)

def to_converse(msgs,schema):
    out=[]
    for m in msgs:
        if m['role']=='system':continue   # system turns go to Converse's system field (call_converse; OSWorld PromptAgent, 2026-11-11)
        c=m['content'];blocks=[]
        for p in ([{'type':'text','text':c}] if isinstance(c,str) else c):
            if p['type']=='text':blocks.append({'text':p['text']})
            else:fmt,b=data_url(p['image_url']['url']);blocks.append({'image':{'format':fmt,'source':{'bytes':base64.b64decode(b)}}})
        out.append({'role':m['role'],'content':blocks})
    if schema:out[-1]['content'].append({'text':'\nReply with exactly one JSON object and nothing else. It must validate against this JSON schema:\n'+json.dumps(schema)})
    return out

def extract_json(t):
    t=re.sub(r'^```(?:json)?\s*|\s*```$','',t.strip())
    i,j=t.find('{'),t.rfind('}');return t[i:j+1] if i>=0 and j>i else t

def call_converse(name,bid,extra,body):
    schema=body.get('response_format',{}).get('json_schema',{}).get('schema')
    kw={'additionalModelRequestFields':extra} if extra else {}
    sysmsg=[c if isinstance(c,str) else ''.join(p.get('text','') for p in c) for c in (m['content'] for m in body['messages'] if m['role']=='system')]
    if sysmsg:kw['system']=[{'text':t} for t in sysmsg]
    r=RT.converse(modelId=bid,messages=to_converse(body['messages'],schema),
                  inferenceConfig={'maxTokens':body.get('max_tokens',32000)},**kw)   # these models reject temperature (2026-11-08)
    u=r['usage'];inp=u['inputTokens']+u.get('cacheReadInputTokens',0)+u.get('cacheWriteInputTokens',0)
    log(name,inp,u['outputTokens'],{'stop':r.get('stopReason'),'raw_usage':u,'request_fields':extra or None})
    text=''.join(x.get('text','') for x in r['output']['message']['content'])
    # JSON extraction only for schema requests (run_agent); free-text callers (GUI agents) get the reply unchanged
    return (extract_json(text) if schema else text),('length' if r.get('stopReason')=='max_tokens' else 'stop')

async def handle(request):
    body=await request.json();name=body['model']
    if name not in MODELS:return web.json_response({'error':f'unknown model {name}'},status=404)
    kind,bid,extra=MODELS[name]
    if (sp:=spent())>=BUDGET:return web.json_response({'error':f'budget reached: ${sp:.2f} >= ${BUDGET:.2f} (BEDROCK_BUDGET_USD)'},status=503)
    try:
        if kind=='claude':text,fin=await call_claude(request.app['claude'],name,bid,extra,body)
        else:text,fin=await asyncio.get_running_loop().run_in_executor(POOL,call_converse,name,bid,extra,body)
    except (anthropic.APIError,Exception) as e:
        with LEDGER.open('a') as f:f.write(json.dumps({'t':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'model':name,'input_tokens':0,'output_tokens':0,'usd':0,'price_assumed':PRICES[name][2],'error':repr(e)[:300]})+'\n')
        return web.json_response({'error':repr(e)[:500]},status=502)
    return web.json_response({'choices':[{'message':{'role':'assistant','content':text},'finish_reason':fin}]})

async def health(request):return web.Response(text='ok')
async def models(request):return web.json_response({'object':'list','data':[{'id':m,'object':'model'} for m in MODELS]})   # reachability check of run_gui_osworld

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8101);ap.add_argument('--ledger',action='store_true');a=ap.parse_args()
    if a.ledger:ledger_summary();return
    app=web.Application(client_max_size=256*1024**2);app['claude']=AsyncAnthropicBedrock(aws_region=REGION,max_retries=6,timeout=900)
    app.router.add_post('/v1/chat/completions',handle);app.router.add_get('/health',health);app.router.add_get('/v1/models',models)
    web.run_app(app,host='127.0.0.1',port=a.port,print=None)

if __name__=='__main__':main()
