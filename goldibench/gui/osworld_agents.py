"""Published open GUI agents on the darktable desktop, each with its own official prompt, parser and settings.

EvoCUA, OpenCUA, GUI-Owl-1.5 and UI-TARS-1.5 are the agent classes in OSWorld's mm_agents (cloned under
$VE_LOCAL/apps/gui_agents/OSWorld), built with the arguments of their OSWorld run scripts. They return pyautogui code,
which OSWorld runs inside the VM; here it runs against a stand-in pyautogui that drives our Xvfb desktop through
DarktableEnv.step. Holo4 has no open harness (H Company's hai-agents runtime is closed), so HoloAgent follows the
published function-calling guide (hub.hcompany.ai, models-api) with the system prompt and desktop tools seen in H
Company's OSWorld trajectories (Hcompany/trajectories); shell, file and app-specific parts are dropped (holo_system.txt).

TARGET at L2/L3: the official agents accept one screenshot per step, so each model is reached through a local proxy
that removes a `[[TARGET_IMAGE:<path>]]` marker from the instruction and puts that image at the start of the first user
message. Everything else in the request is forwarded unchanged to the vLLM server.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import base64,io,json,os,re,sys,threading,time,types,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from PIL import Image

LOCAL=Path(os.environ.get('VE_LOCAL',str(gbpaths.LOCAL)))
OSWORLD=LOCAL/'apps/gui_agents/OSWorld'
SCREEN=(1920,1080)
MARK=re.compile(r'\s*\[\[TARGET_IMAGE:([^\]]+)\]\]')
TARGET_LABEL='TARGET (what the photo should look like when the edit is done):'

# name: (agent kind, vLLM port, served model name)
MODELS={'holo4_35b':('holo',8011,'Holo4-35B-A3B-FP8'),'holo4_27b':('holo',8016,'Holo4-27B-FP8'),
        'guiowl15_32b':('owl15',8012,'GUI-Owl-1.5-32B-Instruct'),'evocua_32b':('evocua',8013,'EvoCUA-32B-20260105'),
        'opencua_72b':('opencua',8014,'OpenCUA-72B'),'uitars15_7b':('uitars15',8015,'UI-TARS-1.5-7B'),
        # size ladders (paper-plan D-3): OpenCUA 7B / 32B / 72B, UI-TARS (v1) 2B / 7B / 72B
        'opencua_7b':('opencua',8021,'OpenCUA-7B'),'opencua_32b':('opencua',8022,'OpenCUA-32B'),
        'uitars_2b':('uitars',8023,'UI-TARS-2B-SFT'),'uitars_7b':('uitars',8024,'UI-TARS-7B-DPO'),
        'uitars_72b':('uitars',8025,'UI-TARS-72B-DPO'),
        # general-VLM control (paper-plan D-3, optional): Qwen3.5 sizes through OSWorld's mm_agents.qwen.QwenAgent
        'qwen35gui_397b':('qwen',8041,'Qwen3.5-397B-A17B-FP8'),'qwen35gui_122b':('qwen',8042,'Qwen3.5-122B-A10B-FP8'),
        'qwen35gui_27b':('qwen',8043,'Qwen3.5-27B'),'qwen35gui_9b':('qwen',8044,'Qwen3.5-9B'),
        'qwen35gui_35b_a3b':('qwen',8045,'Qwen3.5-35B-A3B'),'qwen35gui_4b':('qwen',8046,'Qwen3.5-4B'),
        'qwen35gui_2b':('qwen',8047,'Qwen3.5-2B'),'qwen35gui_0.8b':('qwen',8048,'Qwen3.5-0.8B'),
        # closed models (2026-11-11, pilot): port = bedrock_proxy.py (ledger, BEDROCK_BUDGET_USD). Claude through OSWorld's
        # own computer-use agent (mm_agents.anthropic, Bedrock); GPT-6.1 has no computer-use tool on Bedrock, so it runs
        # through OSWorld's generic PromptAgent (screenshot -> pyautogui, the GPT baseline of the OSWorld paper)
        'opus55gui':('claude',8102,'us.anthropic.claude-opus-5-5'),'gpt61gui':('prompt',8102,'gpt61sol'),
        # 2026-11-13 control (user approved +$300): GPT-6.1 through the same PromptAgent, but one GUI action per screenshot
        # (told in the system prompt and enforced in run_code), like Claude's computer-use tool. GIMP + Inkscape L1 only,
        # run b1g100_closed1a: does GPT's lower GUI L1 come from several blind actions per step?
        'gpt61gui1a':('prompt1a',8102,'gpt61sol'),
        # 2026-11-15 (docs/plan-extra-experiments-2026-11-15.md, D): the general VLMs of the program channel on the GUI, through
        # the same generic PromptAgent as GPT-6.1 (screenshot -> pyautogui), served locally with vLLM
        'glm53gui':('promptlocal',8052,'GLM-5.3-Flash'),'dsv41gui':('promptlocal',8053,'DeepSeek-V4.1-Flash'),
        'step37gui':('promptlocal',8054,'Step-3.7-Flash-FP8'),'nemo35gui':('promptlocal',8055,'NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16')}
# Your own GUI models: configs/models.yaml, section `gui:` ({kind, port, model}); kind = one of the adapters above
# (holo, uitars, opencua, owl15, evocua, prompt, claude, ...), port = local OpenAI-compatible server (scripts/serve_vllm.sh).
MODELS.update({k:(v['kind'],int(v['port']),v['model']) for k,v in gbpaths.models('gui').items()})
ONE_ACTION_NOTE=('\n\nIMPORTANT: return exactly ONE GUI action per step (a single click, doubleClick, write, press, hotkey, scroll or '
                 'drag) and nothing else. You get a new screenshot after every action; do not chain several actions in one code block.')
class _OneAction(Exception):pass

def data_url(img):
    b=io.BytesIO();img.save(b,'PNG');return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()

def target_part(path):
    im=Image.open(path).convert('RGB');im.thumbnail((1024,1024));return {'type':'image_url','image_url':{'url':data_url(im)}}

def inject_target(body):
    """Moves the image named by the instruction marker to the start of the first user message."""
    target=None
    for m in body.get('messages',[]):
        c=m.get('content')
        if isinstance(c,str):
            if MARK.search(c):target=MARK.search(c).group(1);m['content']=MARK.sub('',c)
        elif isinstance(c,list):
            for p in c:
                if isinstance(p,dict) and isinstance(p.get('text'),str) and MARK.search(p['text']):
                    target=MARK.search(p['text']).group(1);p['text']=MARK.sub('',p['text'])
    if target:
        u=next(m for m in body['messages'] if m['role']=='user')
        if isinstance(u['content'],str):u['content']=[{'type':'text','text':u['content']}]
        u['content'][:0]=[{'type':'text','text':TARGET_LABEL},target_part(target)]
    return body

# 2026-11-12: replicas of a slow model on other nodes. GUI_UPSTREAMS (default logs/gui_upstreams.json, re-read when it changes)
# maps a local vLLM port to a list of "host:port" servers of the same model; each request goes to the one with the fewest
# requests in flight from this process, connection errors fall through to the next. No entry: 127.0.0.1:<port> as before.
UPSTREAMS_FILE=os.environ.get('GUI_UPSTREAMS',
    str(gbpaths.DATA)+'/logs/gui_upstreams.json')
_up={'mtime':None,'map':{}};_inflight={};_lock=threading.Lock()
def upstreams(port):
    try:
        m=os.stat(UPSTREAMS_FILE).st_mtime
        if m!=_up['mtime']:_up['map']=json.load(open(UPSTREAMS_FILE));_up['mtime']=m
    except Exception:pass
    # a "<short hostname>:<port>" key overrides "<port>" on that host (2026-11-12: shared replicas were flooded by every node)
    import socket
    return _up['map'].get(f"{socket.gethostname().split('.')[0]}:{port}") or _up['map'].get(str(port)) or [f'127.0.0.1:{port}']

# --log-replies (run_gui_osworld.py; off by default, added after the paper): every model call of an episode is appended in
# full to <episode>/calls.jsonl (reply message incl. reasoning and tool calls, finish_reason, usage, latency). Open models
# and the PromptAgent go through an episode-own proxy (start_proxy(log=...)); Claude's calls are logged in claude_agent.
EPISODE_LOG=threading.local()   # .path = calls.jsonl of the episode running in this thread (Claude)
_log_lock=threading.Lock()
def log_reply(path,rec):
    if not path:return
    with _log_lock,open(path,'a') as f:f.write(json.dumps(rec,default=str)+'\n')

def _call_record(body,code,out,dt):
    try:j=json.loads(out)
    except ValueError:j={'raw':out[:20000].decode('utf-8','replace')}
    ch=(j.get('choices') or [{}])[0] if isinstance(j,dict) else {};msg=ch.get('message') or {}
    return {'t':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'model':body.get('model'),'seed':body.get('seed'),
            'n_messages':len(body.get('messages',[])),'http_status':code,'latency_s':round(dt,3),
            'finish_reason':ch.get('finish_reason'),'content':msg.get('content'),
            'reasoning_content':msg.get('reasoning_content',msg.get('reasoning')),'tool_calls':msg.get('tool_calls'),
            'usage':j.get('usage') if isinstance(j,dict) else None,'error':j.get('error') if isinstance(j,dict) else None}

_servers={}
def stop_proxy(url):
    srv=_servers.pop(url,None)
    if srv:srv.shutdown();srv.server_close()

def start_proxy(port,seed=None,log=None):
    """OpenAI-compatible proxy on a free local port in front of the vLLM server(s) of `port`; returns its base URL.
    `seed` is added to every request that has none (vLLM per-request sampling seed; repeat runs differ only by it).
    `log`: path of a calls.jsonl that gets every request's full reply and usage (--log-replies)."""
    class H(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if seed is not None:body.setdefault('seed',seed)
            data=json.dumps(inject_target(body)).encode()
            with _lock:ups=sorted(upstreams(port),key=lambda u:_inflight.get(u,0))
            err=None;t0=time.time()
            for u in ups:
                with _lock:_inflight[u]=_inflight.get(u,0)+1
                try:
                    req=urllib.request.Request(f'http://{u}{self.path}',data,{'Content-Type':'application/json'})
                    try:
                        with urllib.request.urlopen(req,timeout=900) as r:code,out=r.status,r.read()
                    except urllib.error.HTTPError as e:code,out=e.code,e.read()
                    break
                except (urllib.error.URLError,ConnectionError) as e:err=e;continue
                finally:
                    with _lock:_inflight[u]-=1
            else:raise err
            if log:log_reply(log,_call_record(body,code,out,time.time()-t0))
            self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(out)))
            self.end_headers();self.wfile.write(out)
        def do_GET(self):
            with urllib.request.urlopen(f'http://{upstreams(port)[0]}{self.path}',timeout=30) as r:out=r.read()
            self.send_response(200);self.end_headers();self.wfile.write(out)
    srv=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=srv.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{srv.server_address[1]}/v1';_servers[url]=srv
    return url

# ---- pyautogui stand-in: every call becomes one DarktableEnv.step action ----
class PyAutoGUI:
    def __init__(self,env,limit=None):self.env=env;self.done=None;self.errors=[];self.limit=limit;self.n=0
    def _do(self,**a):
        if self.limit is not None and self.n>=self.limit:raise _OneAction()   # gpt61gui1a: the rest of the code block is dropped
        self.n+=1
        _,done,info=self.env.step(a)
        if info.get('error'):self.errors.append(info['error'])
        if done:self.done=info.get('end')
    def _xy(self,x,y):
        if isinstance(x,(tuple,list)):x,y=x[:2]
        if x is None:return None
        return min(SCREEN[0]-1,max(0,round(x))),min(SCREEN[1]-1,max(0,round(y)))
    def _at(self,x,y,**a):
        p=self._xy(x,y)
        if p:a.update(x=p[0],y=p[1])
        elif 'x' not in a:   # no coordinates: act where the pointer is
            loc=dict(l.split('=',1) for l in self.env.d.xdo('getmouselocation','--shell').split('\n') if '=' in l)
            a.update(x=int(loc['X']),y=int(loc['Y']))
        return a
    def click(self,x=None,y=None,clicks=1,interval=0.0,button='left',**_):
        self._do(**self._at(x,y,action_type='CLICK',button=str(button).lower(),num_clicks=int(clicks)))
    def leftClick(self,x=None,y=None,**k):self.click(x,y,button='left')
    def rightClick(self,x=None,y=None,**_):self._do(**self._at(x,y,action_type='RIGHT_CLICK'))
    def middleClick(self,x=None,y=None,**_):self.click(x,y,button='middle')
    def doubleClick(self,x=None,y=None,button='left',**_):self._do(**self._at(x,y,action_type='DOUBLE_CLICK'))
    def tripleClick(self,x=None,y=None,button='left',**_):self.click(x,y,clicks=3,button=button)
    def moveTo(self,x=None,y=None,*a,**_):self._do(**self._at(x,y,action_type='MOVE_TO'))
    def moveRel(self,dx=0,dy=0,*a,**_):
        loc=self.position();self.moveTo(loc[0]+dx,loc[1]+dy)
    move=moveRel
    def dragTo(self,x=None,y=None,*a,button='left',**_):self._do(**self._at(x,y,action_type='DRAG_TO'))
    def dragRel(self,dx=0,dy=0,*a,**_):
        loc=self.position();self.dragTo(loc[0]+dx,loc[1]+dy)
    def mouseDown(self,x=None,y=None,button='left',**_):
        if self._xy(x,y):self.moveTo(x,y)
        self._do(action_type='MOUSE_DOWN',button=str(button).lower())
    def mouseUp(self,x=None,y=None,button='left',**_):
        if self._xy(x,y):self.moveTo(x,y)
        self._do(action_type='MOUSE_UP',button=str(button).lower())
    def scroll(self,clicks,x=None,y=None,**_):   # pyautogui: positive = up; DarktableEnv: dy > 0 = down
        self._do(**self._at(x,y,action_type='SCROLL',dy=-int(clicks)))
    vscroll=scroll
    def hscroll(self,clicks,x=None,y=None,**_):
        self.keyDown('shift');self.scroll(clicks,x,y);self.keyUp('shift')
    def write(self,message,interval=0.0,**_):
        if isinstance(message,(list,tuple)):
            for k in message:self.press(k)
        else:self._do(action_type='TYPING',text=str(message))
    typewrite=write
    def press(self,keys,presses=1,interval=0.0,**_):
        for _ in range(int(presses)):
            for k in (keys if isinstance(keys,(list,tuple)) else [keys]):self._do(action_type='PRESS',key=k)
    def hotkey(self,*keys,**_):
        if len(keys)==1 and isinstance(keys[0],(list,tuple)):keys=keys[0]
        self._do(action_type='HOTKEY',keys=list(keys))
    def keyDown(self,key,**_):
        from env import keysym;self.env.d.xdo('keydown',keysym(key))
    def keyUp(self,key,**_):
        from env import keysym;self.env.d.xdo('keyup',keysym(key))
    def position(self):
        loc=dict(l.split('=',1) for l in self.env.d.xdo('getmouselocation','--shell').split('\n') if '=' in l)
        return int(loc['X']),int(loc['Y'])
    def size(self):return SCREEN
    def sleep(self,s):time.sleep(min(float(s),5))

def run_code(env,code,one=False):
    """Runs one action from an OSWorld agent: 'DONE' / 'FAIL' / 'WAIT' or pyautogui code. Returns (end or None, errors).
    one=True (gpt61gui1a): only the first GUI action of the code runs; 'single-action: dropped' is recorded when more followed."""
    if isinstance(code,dict):   # AnthropicAgent: {'action_type': 'DONE'|'FAIL'|..., 'command': pyautogui code} (OSWorld DesktopEnv.step)
        t=str(code.get('action_type','')).upper();code=t if t in ('DONE','FAIL','WAIT','CALL_USER') else code.get('command','')
    c=str(code).strip()
    if c.upper() in ('DONE','FAIL'):return c.upper(),[]
    if c.upper() in ('WAIT','CALL_USER'):time.sleep(2);return None,[]
    g=PyAutoGUI(env,limit=1 if one else None)
    clock=types.SimpleNamespace(sleep=g.sleep,time=time.time)
    # 2026-11-14: import lines are replaced by bindings instead of dropped, so aliases ('import pyautogui as p') and
    # 'from pyautogui import click' resolve; before, GPT-6.1 code using an alias failed with NameError (no action ran)
    def _clip(*a,**k):   # pyperclip on the episode's X display (GPT-6.1 pastes text through the clipboard)
        import subprocess
        return subprocess.run(['xclip','-selection','clipboard',*a],env=getattr(env.d,'env',None),capture_output=True,text=True,timeout=10,**k)
    clip=types.SimpleNamespace(copy=lambda t:_clip(input=str(t)) and None,paste=lambda:_clip('-o').stdout)
    # subprocess with the episode's X environment (in OSWorld the code runs inside the VM, where DISPLAY is set; GPT-6.1
    # calls xclip / xdotool through subprocess in ~4% of its steps). Episodes run in threads, so os.environ is not touched.
    import subprocess as _sp
    xenv=getattr(env.d,'env',None)
    def _wrap(f):
        def w(*a,**k):
            if xenv is not None:k.setdefault('env',xenv)
            k.setdefault('timeout',30) if f is not _sp.Popen else None
            return f(*a,**k)
        return w
    # Isolation (2026-11-14): in OSWorld the code runs inside the episode's own VM; here it runs on the host next to ~100
    # other episodes. Process-killing commands (GPT-6.1 ran 'pkill -9 blender', which killed every episode's Blender) are
    # refused, and recursive file searches from the root (a glob('/**') over the 470 TB /shared hung a run for hours) are
    # confined to the episode's own home directory, the size of the VM's file system.
    import glob as _glob,os as _os,re as _re
    home=(xenv or {}).get('HOME') or '/tmp'
    KILL=_re.compile(r'(^|[\s;&|/\'"])(pkill|killall|kill|xkill)(\s|$)')
    def _cmd(a):return ' '.join(map(str,a[0])) if a and isinstance(a[0],(list,tuple)) else str(a[0] if a else '')
    def _wrap2(f,name):
        def w(*a,**k):
            if KILL.search(_cmd(a)) or KILL.search(str(k.get('args',''))):
                return _sp.CompletedProcess(a[0] if a else '',1,'','') if name!='Popen' else _sp.Popen(['true'])
            return _wrap(f)(*a,**k)
        return w
    sub=types.SimpleNamespace(**{k:getattr(_sp,k) for k in dir(_sp) if not k.startswith('_')})
    for k in ('run','call','check_call','check_output','Popen'):setattr(sub,k,_wrap2(getattr(_sp,k),k))
    # getoutput / getstatusoutput take no timeout ('find / -name blender' ran 74 min on /shared): shell, 30 s, episode env
    def _gso(cmd):
        if KILL.search(str(cmd)):return 1,''
        try:r=_sp.run(str(cmd),shell=True,capture_output=True,text=True,env=xenv,timeout=30);return r.returncode,(r.stdout+r.stderr).rstrip('\n')
        except _sp.TimeoutExpired:return 124,''
    sub.getstatusoutput=_gso;sub.getoutput=lambda cmd:_gso(cmd)[1]
    def _confine(p):p=str(p);return home+p if p.startswith('/') and not p.startswith((home,'/tmp')) else p
    gl=types.SimpleNamespace(**{k:getattr(_glob,k) for k in dir(_glob) if not k.startswith('_')})
    gl.glob=lambda p,*a,**k:_glob.glob(_confine(p) if '**' in str(p) else p,*a,**k)
    gl.iglob=lambda p,*a,**k:_glob.iglob(_confine(p) if '**' in str(p) else p,*a,**k)
    osm=types.SimpleNamespace(**{k:getattr(_os,k) for k in dir(_os) if not k.startswith('__')})
    osm.walk=lambda top,*a,**k:_os.walk(home if str(top) in ('/','') or not str(top).startswith((home,'/tmp')) else top,*a,**k)
    osm.kill=lambda *a,**k:None;osm.killpg=lambda *a,**k:None
    osm.system=lambda c:1 if KILL.search(str(c)) else _sp.call(str(c),shell=True,env=xenv,timeout=30)
    ns={'pyautogui':g,'time':clock,'pyperclip':clip,'subprocess':sub,'glob':gl,'os':osm}
    mods={'pyautogui':g,'time':clock,'pyperclip':clip,'subprocess':sub,'glob':gl,'os':osm};keep=[]
    for l in c.split('\n'):
        m=re.match(r'\s*import\s+(.+)$',l);f=re.match(r'\s*from\s+(\w+)\s+import\s+(.+)$',l)
        if m and any(p.split()[0] in mods or p.split()[0]=='pyperclip' for p in m.group(1).split(',') if p.split()):
            other=[]   # 'import pyautogui, time, subprocess': bind ours, really import the rest
            for p in m.group(1).split(','):
                w=p.split()
                if not w:continue
                if w[0] in mods:ns[w[2] if len(w)==3 and w[1]=='as' else w[0]]=mods[w[0]]
                elif w[0]!='pyperclip':other.append(p.strip())
            if other:keep.append(l[:len(l)-len(l.lstrip())]+'import '+', '.join(other))
            continue
        if f and f.group(1) in mods:
            for p in f.group(2).strip('() ').split(','):
                w=p.split()
                if not w:continue
                if w[0]=='*':ns.update({k:getattr(mods[f.group(1)],k) for k in dir(mods[f.group(1)]) if not k.startswith('_')})
                else:ns[w[2] if len(w)==3 and w[1]=='as' else w[0]]=getattr(mods[f.group(1)],w[0])
            continue
        if f and f.group(1)=='pyperclip':continue
        keep.append(l)
    src='\n'.join(keep)
    try:exec(src,ns)
    except _OneAction:g.errors.append('single-action: dropped')
    except Exception as e:g.errors.append(f'code error: {e!r}'[:200])
    return g.done,g.errors

# ---- official agents ----
def osworld_path():
    if str(OSWORLD) not in sys.path:sys.path.insert(0,str(OSWORLD))
    sys.modules.setdefault('oss2',types.ModuleType('oss2'))   # Aliyun upload client; images are sent inline instead
    # mm_agents.agent (PromptAgent) imports every provider SDK at the top; only its OpenAI-style path is used here
    for m in ('dashscope','groq','google','google.generativeai','google.api_core','google.api_core.exceptions'):
        try:__import__(m)
        except ImportError:
            mod=sys.modules[m]=types.ModuleType(m)
            if m=='groq':mod.Groq=None
            if m=='google.api_core.exceptions':
                for n in ('InvalidArgument','ResourceExhausted','InternalServerError','BadRequest'):setattr(mod,n,type(n,(Exception,),{}))

def own_client(agent,base_url):
    """UI-TARS agents read their server from the process-wide DOUBAO_API_URL when built; with several UI-TARS models
    built concurrently another thread can change it first, so each agent gets a client for its own proxy."""
    from openai import OpenAI
    agent.vlm=OpenAI(base_url=base_url,api_key='EMPTY');return agent

_tl=threading.local()
class _ReqShim:
    """requests stand-in for mm_agents.agent: inside a promptlocal call (_tl.base set) chat/completions goes to that base."""
    def __init__(self,mod):self._m=mod
    def __getattr__(self,k):return getattr(self._m,k)
    def post(self,url,*a,**k):
        b=getattr(_tl,'base',None)
        if b and url.endswith('/chat/completions'):url=b.rstrip('/')+'/chat/completions'
        return self._m.post(url,*a,**k)

def make_agent(name,base_url,max_steps,manual=False,system_info=None):
    kind,_,served=MODELS[name];osworld_path()
    if kind=='evocua':   # README evaluation command
        os.environ['OPENAI_BASE_URL']=base_url;os.environ['OPENAI_API_KEY']='EMPTY'
        from mm_agents.evocua.evocua_agent import EvoCUAAgent
        return EvoCUAAgent(model=served,max_tokens=32768,top_p=0.9,temperature=0.01,max_steps=max_steps,prompt_style='S2',
                           max_history_turns=4,screen_size=SCREEN,coordinate_type='relative',resize_factor=32)
    if kind=='opencua':   # run_multienv_opencua.py defaults
        import httpx
        from mm_agents.opencua import opencua_agent as oc
        a=oc.OpenCUAAgent(model=served,history_type='action_history',max_steps=max_steps,max_image_history_length=3,
                          max_tokens=2048,top_p=0.9,temperature=0,cot_level='l2',screen_size=SCREEN,coordinate_type='qwen25')
        def call_llm(payload,model):   # the official method posts to the authors' hosted endpoint
            for _ in range(5):
                r=httpx.post(base_url+'/chat/completions',json=payload,timeout=900)
                if r.status_code==200 and r.json()['choices'][0].get('finish_reason')=='stop':return r.json()['choices'][0]['message']['content']
                time.sleep(2)
            raise RuntimeError(f'OpenCUA call failed: {r.status_code} {r.text[:200]}')
        a.call_llm=call_llm;return a
    if kind=='owl15':   # run_multienv_gui_owl15.py defaults, OpenAI engine
        from mm_agents import owl15_agent as ow
        ow.get_image_url=lambda b64:'data:image/png;base64,'+b64
        return ow.Owl15Agent(model=served,api_url=base_url,api_key='EMPTY',history_n=5,max_trajectory_length=50,
                             top_p=0.9,top_k=1,temperature=0.0,engine='openai',keep_full_response=0)
    if kind=='uitars15':   # run_multienv_uitars15_v1.py, qwen25vl_normal; typing without the clipboard swap
        os.environ['DOUBAO_API_URL']=base_url;os.environ['DOUBAO_API_KEY']='EMPTY'
        from mm_agents.uitars15_v1 import UITARSAgent
        a=UITARSAgent(model=served,action_space='pyautogui',observation_type='screenshot',max_trajectory_length=max_steps,
                           model_type='qwen25vl',runtime_conf={'infer_mode':'qwen25vl_normal','prompt_style':'qwen25vl_normal',
                           'input_swap':False,'language':'English','history_n':5,'max_pixels':16384*28*28,'min_pixels':100*28*28,
                           'callusr_tolerance':3,'temperature':0.0,'top_k':-1,'top_p':0.9,'max_tokens':1000})
        return own_client(a,base_url)
    if kind=='uitars':   # scripts/python/run_multienv_uitars.py defaults (UI-TARS v1); typing without the clipboard swap
        os.environ['DOUBAO_API_URL']=base_url;os.environ['DOUBAO_API_KEY']='EMPTY'
        from mm_agents.uitars_agent import UITARSAgent
        a=UITARSAgent(model=served,max_tokens=1500,top_p=0.9,temperature=1.0,action_space='pyautogui',
                           observation_type='screenshot',max_trajectory_length=max_steps,
                           runtime_conf={'infer_mode':'qwen2vl_user','prompt_style':'qwen2vl_user','input_swap':False,
                                         'language':'English','max_steps':max_steps,'history_n':5,
                                         'screen_height':SCREEN[1],'screen_width':SCREEN[0]})
        return own_client(a,base_url)
    if kind=='qwen':   # scripts/python/run_multienv_qwen.py defaults (relative coords, history 100, thinking off)
        from mm_agents.qwen import QwenAgent
        return QwenAgent(model=served,max_tokens=32768,top_p=0.9,temperature=0.0,action_space='pyautogui',
                         observation_type='screenshot',coordinate_type='relative',add_thought_prefix=False,history_n=100,
                         image_max=20,fold_size=10,enable_thinking=False,base_url=base_url,api_key='EMPTY')
    if kind=='claude':return claude_agent(served,max_steps)
    if kind in ('prompt','prompt1a','promptlocal'):   # OSWorld run.py defaults except max_tokens (1500 leaves no room for GPT-6.1's hidden reasoning)
        os.environ['OPENAI_BASE_URL']=base_url;os.environ['OPENAI_API_KEY']='EMPTY'
        import mm_agents.agent as pa
        from mm_agents.agent import PromptAgent
        if not getattr(pa,'_ve_wrapped',False):   # its parser splits the reply on ';', which breaks a comment such as
            orig=pa.parse_code_from_string        # '# menu is open; click X' into a code line: drop comment lines first
            pa.parse_code_from_string=lambda t:orig('\n'.join(l for l in t.split('\n') if not l.strip().startswith('#')));pa._ve_wrapped=True
        a=PromptAgent(model=served,max_tokens=16000,top_p=0.9,temperature=1.0,action_space='pyautogui',
                      observation_type='screenshot',max_trajectory_length=3)
        if kind=='prompt1a':a.system_message+=ONE_ACTION_NOTE
        if kind=='promptlocal':   # PromptAgent routes by model-name prefix; a local vLLM model takes its OpenAI-compatible branch
            # 2026-11-15: that branch reads the process-wide OPENAI_BASE_URL at call time, so two promptlocal models in one
            # process sent each other's requests (404 model does not exist). The call now goes to this agent's own proxy:
            # base_url is kept per thread for the duration of the call and the module's requests.post is redirected to it.
            if not isinstance(pa.requests,_ReqShim):pa.requests=_ReqShim(pa.requests)
            orig_call=a.call_llm
            def call(payload,_a=a,_orig=orig_call,_base=base_url):
                m=_a.model;_a.model='gpt-local';_tl.base=_base
                try:return _orig(payload)
                finally:_a.model=m;_tl.base=None
            a.call_llm=call
        return a
    if kind=='holo':return HoloAgent(served,base_url,max_steps,manual,system_info)
    if manual:raise ValueError(f'{name}: the manual is only wired into HoloAgent')
    raise KeyError(name)

# ---- Claude: OSWorld's AnthropicAgent on Bedrock (run_multienv_claude.py defaults: max_tokens 16000, adaptive thinking,
# 720p API resolution, 10 most recent screenshots). Every request passes api_fallback_create, the agent's own indirection
# point; it is wrapped to (1) put TARGET (instruction marker) at the start of the first user message, as start_proxy does
# for the open models, (2) refuse requests once the shared Bedrock ledger reaches BEDROCK_BUDGET_USD, (3) log the cost.
CLAUDE_PRICE=(4.0,20.0)   # USD per 1M input / output tokens, as opus55 in bedrock_proxy.py
_claude_lock=threading.Lock()
def _ledger():
    return Path(str(gbpaths.DATA)+'/logs/bedrock_ledger.jsonl')
def _spent():
    L=_ledger();return sum(json.loads(l).get('usd',0) for l in open(L)) if L.exists() else 0.0

def _anthropic_target(messages):
    first=next((m for m in messages if m['role']=='user'),None)
    if not first or not isinstance(first['content'],list):return
    for i,p in enumerate(first['content']):
        if p.get('type')=='text' and MARK.search(p['text']):
            path=MARK.search(p['text']).group(1);p['text']=MARK.sub('',p['text'])
            im=Image.open(path).convert('RGB');im.thumbnail((1024,1024));b=io.BytesIO();im.save(b,'PNG')
            first['content'][:0]=[{'type':'text','text':TARGET_LABEL},
                                  {'type':'image','source':{'type':'base64','media_type':'image/png','data':base64.b64encode(b.getvalue()).decode()}}]
            return

def claude_agent(model,max_steps):
    osworld_path()
    import mm_agents.anthropic.main as cm
    from mm_agents.anthropic.utils import APIProvider
    if not getattr(cm,'_ve_wrapped',False):
        orig=cm.api_fallback_create
        def create(client,_agent=None,**kw):
            budget=float(os.environ.get('BEDROCK_BUDGET_USD','inf'))   # optional spending cap (USD) over the cost ledger
            if (sp:=_spent())>=budget:raise OSError(f'budget reached: ${sp:.2f} >= ${budget:.2f} (BEDROCK_BUDGET_USD)')   # harness error, retried later
            _anthropic_target(kw['messages'])
            t0=time.time();r=orig(client,_agent=_agent,**kw);u=r.usage
            path=getattr(EPISODE_LOG,'path',None)
            if path:   # --log-replies: content blocks in full (text, thinking, tool_use), usage, stop reason
                blocks=[b.model_dump() if hasattr(b,'model_dump') else str(b) for b in (r.content or [])]
                for b in blocks:   # the signature of a thinking block is an opaque blob, not model output
                    if isinstance(b,dict) and b.get('signature'):b['signature']=f"<{len(b['signature'])} chars>"
                log_reply(path,{'t':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'model':kw.get('model'),
                                'n_messages':len(kw.get('messages',[])),'latency_s':round(time.time()-t0,3),'finish_reason':r.stop_reason,
                                'content':blocks,'usage':u.model_dump() if hasattr(u,'model_dump') else str(u)})
            inp=u.input_tokens+(getattr(u,'cache_read_input_tokens',0) or 0)+(getattr(u,'cache_creation_input_tokens',0) or 0)
            usd=inp*CLAUDE_PRICE[0]/1e6+u.output_tokens*CLAUDE_PRICE[1]/1e6
            _ledger().parent.mkdir(parents=True,exist_ok=True)   # a fresh data dir has no logs/ yet
            with _claude_lock,_ledger().open('a') as f:
                f.write(json.dumps({'t':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'model':'opus55gui','input_tokens':inp,
                                    'output_tokens':u.output_tokens,'usd':round(usd,6),'price_assumed':False,'stop':r.stop_reason})+'\n')
            return r
        cm.api_fallback_create=create;cm._ve_wrapped=True
    return cm.AnthropicAgent(model=model,provider=getattr(APIProvider,os.environ.get('GOLDIBENCH_ANTHROPIC_PROVIDER','ANTHROPIC').upper()),max_tokens=16000,thinking_mode='adaptive',
                             screen_size=SCREEN,max_steps=max_steps,api_resolution='720p',only_n_most_recent_images=10)

# ---- Holo4 (function calling) ----
def _pt(desc):return {'type':'string','description':desc}
_XY={'element':_pt('Detailed description of the target UI element.'),
     'x':{'type':'integer','description':'X coordinate as integer in [0, 1000].'},
     'y':{'type':'integer','description':'Y coordinate as integer in [0, 1000].'}}
def _tool(name,desc,props,req):return {'type':'function','function':{'name':name,'description':desc,
                                       'parameters':{'type':'object','properties':props,'required':req}}}
HOLO_TOOLS=[
    _tool('click_desktop','Click at (x, y).',{**_XY,'button':{'type':'string','enum':['left','right','middle']}},['element','x','y']),
    _tool('double_click_desktop','Double-click at (x, y).',_XY,['element','x','y']),
    _tool('move_to_desktop','Move the pointer to (x, y).',_XY,['element','x','y']),
    _tool('write_at_desktop','Click at (x, y), then type content.',{**_XY,'content':_pt('Text to type.'),
          'overwrite':{'type':'boolean','description':'Select all existing text first.'},'press_enter':{'type':'boolean'}},['element','x','y','content']),
    _tool('write_desktop','Type content into the focused element.',{'content':_pt('Text to type.'),'overwrite':{'type':'boolean'},
          'press_enter':{'type':'boolean'}},['content']),
    _tool('scroll_desktop','Scroll at (x, y).',{**_XY,'direction':{'type':'string','enum':['up','down','left','right']},
          'scroll_size':{'type':'integer','description':'Number of wheel clicks.'}},['element','x','y','direction']),
    _tool('drag_and_drop','Drag from (x1, y1) to (x2, y2).',{'description':_pt('What is dragged and where.'),
          **{k:{'type':'integer','description':'Coordinate as integer in [0, 1000].'} for k in ('x1','y1','x2','y2')}},['description','x1','y1','x2','y2']),
    _tool('hotkey_desktop','Press a key or key combination.',{'keys':{'type':'array','items':{'type':'string'},'description':'e.g. ["ctrl", "a"]'}},['keys']),
    _tool('key_down_desktop','Hold a key down.',{'key':_pt('Key name.')},['key']),
    _tool('key_up_desktop','Release a held key.',{'key':_pt('Key name.')},['key']),
    _tool('mouse_down_desktop','Press a mouse button at the pointer.',{'button':{'type':'string','enum':['left','right','middle']}},[]),
    _tool('mouse_up_desktop','Release a mouse button at the pointer.',{'button':{'type':'string','enum':['left','right','middle']}},[]),
    _tool('wait_desktop','Wait, then take a new screenshot.',{'seconds':{'type':'number'}},[]),
    _tool('update_plan','Record the working plan.',{'goals':{'type':'array','items':{'type':'object'}}},['goals']),
    _tool('answer','Provide a final answer.',{'content':_pt('Final answer.')},['content'])]

def holo_code(name,a):
    """One Holo tool call -> pyautogui code on the 1920x1080 screen (Holo points on a 0-1000 grid)."""
    X=lambda v:round(float(v)*SCREEN[0]/1000);Y=lambda v:round(float(v)*SCREEN[1]/1000)
    if name=='click_desktop':
        b=a.get('button','left');return f"pyautogui.rightClick({X(a['x'])},{Y(a['y'])})" if b=='right' else f"pyautogui.click({X(a['x'])},{Y(a['y'])},button={b!r})"
    if name=='double_click_desktop':return f"pyautogui.doubleClick({X(a['x'])},{Y(a['y'])})"
    if name=='move_to_desktop':return f"pyautogui.moveTo({X(a['x'])},{Y(a['y'])})"
    if name in ('write_at_desktop','write_desktop'):
        c=[f"pyautogui.click({X(a['x'])},{Y(a['y'])})"] if name=='write_at_desktop' else []
        if a.get('overwrite'):c.append("pyautogui.hotkey('ctrl','a')")
        c.append(f"pyautogui.write({str(a['content'])!r})")
        if a.get('press_enter'):c.append("pyautogui.press('enter')")
        return '\n'.join(c)
    if name=='scroll_desktop':
        n=int(a.get('scroll_size',3));d=a.get('direction','down');n=n if d in ('up','left') else -n
        return f"pyautogui.{'h' if d in ('left','right') else ''}scroll({n},{X(a['x'])},{Y(a['y'])})"
    if name=='drag_and_drop':return f"pyautogui.moveTo({X(a['x1'])},{Y(a['y1'])})\npyautogui.dragTo({X(a['x2'])},{Y(a['y2'])})"
    if name=='hotkey_desktop':return f"pyautogui.hotkey(*{list(a['keys'])!r})"
    if name=='key_down_desktop':return f"pyautogui.keyDown({a['key']!r})"
    if name=='key_up_desktop':return f"pyautogui.keyUp({a['key']!r})"
    if name=='mouse_down_desktop':return f"pyautogui.mouseDown(button={a.get('button','left')!r})"
    if name=='mouse_up_desktop':return f"pyautogui.mouseUp(button={a.get('button','left')!r})"
    if name=='wait_desktop':return f"time.sleep({min(float(a.get('seconds',2)),5)})"
    raise KeyError(name)

# ---- darktable manual (GUI edition) as tools, as in run_gui_agent.py --manual ----
MANUAL_CALLS=8
MANUAL_TOOLS=[_tool('read_skill','Return the darktable-manual SKILL.md: how to consult it and its table of contents.',{},[]),
              _tool('list_topics','List the manual topic names.',{},[]),
              _tool('load_topic','Return one manual topic.',{'topic':_pt('Topic name from the table of contents.')},['topic'])]
MANUAL_NAMES={'read_skill','list_topics','load_topic'}

def manual_note():
    import manual
    return (f'\n\nINSTALLED SKILL: {manual.SKILL_NAME}: {manual.skill_desc()}\n'
            'Tools: read_skill returns its SKILL.md (how to consult it and its table of contents); list_topics lists topic '
            'names; load_topic returns one topic. Manual reads do not use up steps; up to '
            f'{MANUAL_CALLS} per task, at any step. Where you are unsure how a darktable control works or what a module or '
            'setting does, read the skill and load the matching topic.')

def manual_result(name,a):
    import manual
    if name=='read_skill':return manual.skill_md()
    if name=='list_topics':return '\n'.join(manual.pages())
    topic=str(a.get('topic','')).strip().removesuffix('/guide.md').strip('/')
    return manual.read(topic) if topic in manual.pages() else f'unknown topic "{topic}"; call list_topics for valid names.'

class HoloAgent:
    """Loop from H Company's function-calling guide: tools with tool_choice=required, thinking on, temperature 0.8,
    screenshots wrapped in <observation> and only the last 3 kept, reasoning not replayed, tool results returned."""
    DARKTABLE_INFO='The only application is darktable, already open in the darkroom view on the photo to edit. darktable saves edits automatically.'
    def __init__(self,served,base_url,max_steps,manual=False,system_info=None):
        from openai import OpenAI
        self.model=served;self.client=OpenAI(base_url=base_url,api_key='EMPTY',timeout=900);self.max_steps=max_steps
        self.system=(Path(__file__).with_name('holo_system.txt')).read_text().replace('{max_steps}',str(max_steps))
        if system_info:self.system=self.system.replace(self.DARKTABLE_INFO,system_info)   # osworld_sanity.py: the stock Ubuntu desktop
        self.manual=manual
    def reset(self,*a,**k):self.messages=[];self.pending=[];self.calls=0
    def predict(self,instruction,obs):
        if not self.messages:
            self.messages=[{'role':'system','content':self.system},{'role':'user','content':instruction+(manual_note() if self.manual else '')}]
        self.messages+=self.pending;self.pending=[]
        shot='data:image/png;base64,'+base64.b64encode(obs['screenshot']).decode()
        self.messages.append({'role':'user','content':[{'type':'text','text':'<observation>\n'},{'type':'image_url','image_url':{'url':shot}},
                                                        {'type':'text','text':'\n</observation>'}]})
        n=0   # keep the last 3 screenshots
        for m in reversed(self.messages):
            if isinstance(m['content'],list):
                for i,p in enumerate(m['content']):
                    if p.get('type')=='image_url' and '<observation>' in json.dumps(m['content'][0]):
                        n+=1
                        if n>3:m['content'][i]={'type':'text','text':'[screenshot evicted]'}
        text=''
        while True:   # manual reads are answered at once and do not use up a step
            can_read=self.manual and self.calls<MANUAL_CALLS
            r=self.client.chat.completions.create(model=self.model,messages=self.messages,tools=HOLO_TOOLS+(MANUAL_TOOLS if can_read else []),
                                                  tool_choice='required',temperature=0.8,max_tokens=8192,
                                                  extra_body={'chat_template_kwargs':{'enable_thinking':True}})
            msg=r.choices[0].message;calls=msg.tool_calls or []
            self.messages.append({'role':'assistant','content':msg.content or '',
                                  **({'tool_calls':[{'id':c.id,'type':'function','function':{'name':c.function.name,'arguments':c.function.arguments}} for c in calls]} if calls else {})})
            text+=(getattr(msg,'reasoning',None) or getattr(msg,'reasoning_content',None) or '')[-1500:]+'\n'+(msg.content or '')
            reads=[c for c in calls if c.function.name in MANUAL_NAMES]
            for c in reads:
                self.calls+=1
                try:a=json.loads(c.function.arguments or '{}')
                except json.JSONDecodeError:a={}
                text+=f'\n{c.function.name}({json.dumps(a)[:200]})'
                res=manual_result(c.function.name,a) if can_read else 'Error: no manual reads left.'
                self.messages.append({'role':'tool','tool_call_id':c.id,'content':res+f'\n({max(0,MANUAL_CALLS-self.calls)} manual reads left)'})
            calls=[c for c in calls if c.function.name not in MANUAL_NAMES]
            if calls or not reads:break
        actions=[]
        for c in calls:
            try:a=json.loads(c.function.arguments or '{}')
            except json.JSONDecodeError as e:self.pending.append({'role':'tool','tool_call_id':c.id,'content':f'Error: invalid JSON arguments ({e})'});break
            name=c.function.name;text+=f'\n{name}({json.dumps(a)[:300]})'
            if name=='answer':actions.append('DONE');break
            if name=='update_plan':self.pending.append({'role':'tool','tool_call_id':c.id,'content':'Plan updated.'});continue
            try:actions.append(holo_code(name,a));self.pending.append({'role':'tool','tool_call_id':c.id,'content':'Done.'})
            except (KeyError,ValueError,TypeError) as e:
                self.pending.append({'role':'tool','tool_call_id':c.id,'content':f'Error: {e!r}'});break
        return text,actions
