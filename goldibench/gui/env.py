"""OSWorld-style environment for the darktable GUI bench: reset(task) / step(action) / evaluate().

Task configs follow OSWorld's JSON shape (id, snapshot, instruction, config, evaluator, related_apps) plus our fields
(level, allowed_modules, target). Actions are OSWorld computer_13 dicts:
  MOVE_TO x y | CLICK x y [button] [num_clicks] | RIGHT_CLICK x y | DOUBLE_CLICK x y | MOUSE_DOWN/MOUSE_UP [button]
  DRAG_TO x y (from the current pointer) | SCROLL x y dy | TYPING text | PRESS key | HOTKEY keys | WAIT | DONE | FAIL
Observation: {'screenshot': PIL image (1920x1080)}. The target image is given to the agent, never put on the desktop;
no terminal or file dialogs are offered (darktable is the only app, opened on the START image).

evaluate(): the edit is read from darktable's XMP sidecar and re-rendered by us with darktable-cli at the size TARGET was
rendered (<=1024 px), then scored exactly like the program bench (score.py): pass = closeness >= 0.75 and dE00 <= 4.
Legality gate: at L1/L2 every user-added module must be in allowed_modules (otherwise the episode fails).
"""
import sys,time,shutil,subprocess,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
from desktop import Desktop
import dt_params,score
from make_pilot import passed

DEFAULT_OPS={'colorin','colorout','gamma','flip'}   # auto-applied by darktable to every JPEG/PNG, before any edit
BUTTON={'left':1,'middle':2,'right':3}
KEYS={'enter':'Return','return':'Return','esc':'Escape','escape':'Escape','backspace':'BackSpace','tab':'Tab','delete':'Delete',
      'space':'space','up':'Up','down':'Down','left':'Left','right':'Right','ctrl':'ctrl','shift':'shift','alt':'alt',
      '-':'minus','.':'period','+':'plus',',':'comma','/':'slash'}

def keysym(k):
    k=str(k);return KEYS.get(k.lower(),k)

class DarktableEnv:
    def __init__(self,workdir,display=None):
        self.work=Path(workdir);self.display=display;self.d=None;self.task=None

    def reset(self,task):
        self.close();self.task=task
        image=next(c['parameters']['path'] for c in task['config'] if c['type']=='open_image')
        self.d=Desktop(self.work,self.display).start(image);self.actions=[]
        return self.observe()

    def observe(self):return {'screenshot':self.d.screenshot()}

    def step(self,a):
        """Executes one action dict; returns (obs, done, info)."""
        t=a.get('action_type','').upper();d=self.d;self.actions.append(a);info={}
        try:
            if t=='MOVE_TO':d.move(a['x'],a['y'])
            elif t in('CLICK','RIGHT_CLICK','DOUBLE_CLICK'):
                b=3 if t=='RIGHT_CLICK' else BUTTON.get(a.get('button','left'),1);n=2 if t=='DOUBLE_CLICK' else int(a.get('num_clicks',1))
                d.move(a['x'],a['y']);time.sleep(0.2)
                for _ in range(n):   # press/release as separate events: darktable's popups ignore an instant xdotool click
                    d.xdo('mousedown',b);time.sleep(0.12);d.xdo('mouseup',b);time.sleep(0.08)
            elif t=='MOUSE_DOWN':d.xdo('mousedown',BUTTON.get(a.get('button','left'),1))
            elif t=='MOUSE_UP':d.xdo('mouseup',BUTTON.get(a.get('button','left'),1))
            elif t=='DRAG_TO':
                loc=dict(l.split('=',1) for l in d.xdo('getmouselocation','--shell').split('\n') if '=' in l)
                d.drag(int(loc['X']),int(loc['Y']),a['x'],a['y'])
            elif t=='SCROLL':d.scroll(a['x'],a['y'],int(a.get('dy',1)))
            elif t=='TYPING':
                for ch in str(a.get('text','')):d.key(keysym(ch) if not ch.isalnum() else ch)
            elif t=='PRESS':d.key(keysym(a['key']))
            elif t=='HOTKEY':d.key('+'.join(keysym(k) for k in a['keys']))
            elif t=='WAIT':time.sleep(1.5)
            elif t in('DONE','FAIL'):return self.observe(),True,{'end':t}
            else:info['error']=f'unknown action_type {t!r}'
        except (KeyError,ValueError,TypeError) as e:info['error']=f'bad action: {e!r}'[:200]
        time.sleep(0.8)   # let darktable process and redraw the preview
        return self.observe(),False,info

    def history(self):
        """User edits in the active history: [(module, enabled, params)], default JPEG modules removed."""
        return [h for h in dt_params.read_history(self.d.sidecar() or '') if h[0] not in DEFAULT_OPS]

    def evaluate(self):
        self.d.flush()   # darktable writes the sidecar lazily
        ev=self.task['evaluator'];target=ev['expected']['path'];hist=self.history()
        used=sorted({op for op,en,_ in hist if en});allowed=self.task.get('allowed_modules')
        out={'modules_used':used,'history_len':len(hist)}
        if allowed is not None and set(used)-set(allowed):
            return {**out,'pass':False,'gate':f'modules not allowed: {sorted(set(used)-set(allowed))}'}
        result=self.work/'result.png';side=self.d.sidecar()
        img=next(c['parameters']['path'] for c in self.task['config'] if c['type']=='open_image')
        if side is None:shutil.copy(ev['start_path'],result)   # nothing edited: the result is START
        else:
            with tempfile.TemporaryDirectory() as tmp:
                x=Path(tmp)/'edit.xmp';x.write_text(side);result.unlink(missing_ok=True)
                r=subprocess.run([str(dt_params.DT),img,str(x),str(result),'--width','1024','--height','1024','--core',
                                  '--configdir',str(Path(tmp)/'conf'),'--library',':memory:'],capture_output=True,text=True,timeout=600)
                if r.returncode or not result.exists():return {**out,'pass':False,'gate':'render failed: '+r.stderr[-300:]}
        lt=score.lab(target);lr=score.lab(result)
        if lr.shape!=lt.shape:return {**out,'pass':False,'gate':f'geometry changed: output {lr.shape[:2]} vs target {lt.shape[:2]}'}   # crop / lens / rotate
        d0=score.de(score.lab(ev['start_path']),lt);dd=score.de(lr,lt)
        return {**out,'de00':round(dd,3),'d0':round(d0,3),'closeness':round(1-dd/d0,4),'pass':passed(dd,d0)}

    def close(self):
        if self.d:self.d.close();self.d=None
