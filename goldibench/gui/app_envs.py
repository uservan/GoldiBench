"""OSWorld-style environments for the Inkscape, RawTherapee and Blender GUI benches (docs/gui-adapters.md).

Same interface and actions as env.DarktableEnv (reset / step / evaluate, OSWorld computer_13 dicts; step() inherited):
one disposable Xvfb desktop + openbox per episode, the app opened on the START file, nothing shared between episodes.
evaluate() reads the edit state the app itself keeps (Inkscape: the SVG, saved with Ctrl+S; RawTherapee: the pp3
sidecar the editor writes next to the image; Blender: the .blend, saved with Ctrl+S), re-renders it with the program
bench's own renderer at TARGET's size, and scores it exactly like the program bench (score.py: pass = closeness >= 0.75
and dE00 <= 4). Legality gate at L1 / L2: every tool the edit uses (read from the state, compared with START's state)
must be one of the task's tools; L3 allows any tool. A geometry change (other output size) fails, as on darktable / GIMP.
"""
import json,os,re,shutil,signal,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
from PIL import Image
from desktop import Desktop,W,H,LOCAL
from env import DarktableEnv
import score
from make_pilot import passed

HERE=Path(__file__).parent

class AppDesktop(Desktop):
    """Xvfb + openbox (normal windows undecorated and maximized, as GimpDesktop) + one app process."""
    TITLE='.'            # regex of the main window title
    def prepare(self,home,src):raise NotImplementedError   # fresh HOME config + the START copy; returns the app command
    def after_start(self):pass

    def start(self,src):
        if self.dir.exists():shutil.rmtree(self.dir)
        home=self.dir/'home';(self.dir/'img').mkdir(parents=True);home.mkdir()
        cmd=self.prepare(home,Path(src))
        r,w=os.pipe()
        xkb=['-xkbdir',os.environ['XKB_DIR']] if os.environ.get('XKB_DIR') else []
        x=subprocess.Popen(['Xvfb','-displayfd',str(w),'-screen','0',f'{W}x{H}x24','-nolisten','tcp',*xkb],pass_fds=(w,),
                           stdout=open(self._log('xvfb.log'),'w'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        os.close(w);self.procs.append(x)
        with os.fdopen(r) as f:num=f.readline().strip()
        if not num.isdigit():self.close();raise RuntimeError('Xvfb did not start: '+self._log('xvfb.log').read_text()[-300:])
        self._set_display(int(num));self.env['HOME']=str(home);self.env.update(self.extra_env(home))
        ob=Path(shutil.which('openbox')).resolve().parent.parent.parent
        rc=(ob/'etc/xdg/openbox/rc.xml').read_text()
        a,b=rc.index('<applications>'),rc.index('</applications>')+len('</applications>')
        rc=rc[:a]+'<applications><application type="normal"><decor>no</decor><maximized>yes</maximized></application></applications>'+rc[b:]
        (home/'.config/openbox').mkdir(parents=True,exist_ok=True);(home/'.config/openbox/rc.xml').write_text(rc)
        self.procs.append(subprocess.Popen(['openbox'],env={**self.env,'XDG_CONFIG_DIRS':str(ob/'etc/xdg'),'XDG_DATA_DIRS':str(ob/'usr/share')},
                                           stdout=open(self._log('openbox.log'),'w'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,
                                           start_new_session=True,cwd=self.dir))
        time.sleep(1)
        for attempt in range(3):
            self.app=self._spawn(cmd,f'app{attempt}.log')
            for _ in range(240):
                if self.window() or self.app.poll() is not None:break
                time.sleep(0.5)
            if self.window():break
            if self.app.poll() is None:os.killpg(self.app.pid,signal.SIGKILL)
            self.procs.remove(self.app);time.sleep(1)
        else:
            self.close();raise RuntimeError(f'{type(self).__name__}: window did not appear')
        time.sleep(self.SETTLE)
        wid=self.window();self.xdo('windowsize',wid,str(W),str(H));self.xdo('windowmove',wid,'0','0');time.sleep(1)
        self.after_start();return self

    def extra_env(self,home):return {}
    SETTLE=4
    def window(self):
        out=self.xdo('search','--onlyvisible','--name',self.TITLE);return out.split('\n')[0] if out else None
    def focus_main(self):
        wid=self.window()
        if wid:self.xdo('windowactivate','--sync',wid);time.sleep(0.3)
        return wid

def _size(path):
    w,h=Image.open(path).size;return max(w,h)

def _score(out,ev,result):
    target=ev['expected']['path'];lt=score.lab(target);lr=score.lab(str(result));ls=score.lab(ev['start_path'])
    if lr.shape!=lt.shape:return {**out,'pass':False,'gate':f'geometry changed: output {lr.shape[:2]} vs target {lt.shape[:2]}'}
    d0=score.de(ls,lt);dd=score.de(lr,lt)
    return {**out,'de00':round(dd,3),'d0':round(d0,3),'closeness':round(1-dd/d0,4),'pass':passed(dd,d0)}

def _gate(out,used,task):
    allowed=task.get('allowed_modules')
    if allowed is not None and set(used)-set(allowed):
        return {**out,'pass':False,'gate':f'tools not allowed: {sorted(set(used)-set(allowed))}'}
    return None

class AppEnv(DarktableEnv):
    DESKTOP=None
    def reset(self,task):
        self.close();self.task=task
        src=next(c['parameters']['path'] for c in task['config'] if c['type']=='open_image')
        self.d=self.DESKTOP(self.work,self.display).start(src);self.actions=[]
        return self.observe()

# ------------------------------------------------------------------ Inkscape 1.4.4
import ops_inkscape as OI,inkscape_start
INK_PREFS='''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<inkscape version="1" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">
  <group id="options" dpifixbackup="0">
    <group id="boot" enabled="0" showwelcome="0" showsplash="0" />
    <group id="autosave" enable="0" />
  </group>
</inkscape>
'''
class InkscapeDesktop(AppDesktop):
    TITLE=r'start\.svg - Inkscape$'
    SETTLE=4
    def prepare(self,home,src):
        (home/'.config/inkscape').mkdir(parents=True);(home/'.config/inkscape/preferences.xml').write_text(INK_PREFS)
        # pre-0.92 documents open behind a modal conversion dialog: open a copy with the current version
        # (inkscape_start.check: renders pixel-identical to the source for 99 / 100 B-1 sources; b112 is dropped)
        self.image=inkscape_start.gui_copy(src,self.dir/'img'/'start.svg');self.start_svg=self.image.read_bytes()
        return [str(OI.INKSCAPE),str(self.image)]
    def after_start(self):
        self.focus_main();self.key('5');time.sleep(1)   # View > Zoom > Page: the whole drawing on screen
    def save(self,timeout=30):
        """Ctrl+S on the main window (saves the open document in place, no dialog). True once the file changed."""
        before=self.image.stat().st_mtime_ns
        for attempt in range(3):
            self.focus_main();self.key('Escape');time.sleep(0.3);self.key('ctrl+s')
            t=time.time()
            while time.time()-t<timeout/3:
                if self.image.stat().st_mtime_ns!=before:time.sleep(1);return True
                time.sleep(0.3)
            if not self.xdo('getwindowname',self.window() or '').startswith('*'):return False   # nothing to save: unedited
        return False

# filter primitive -> the library ops it can belong to (gate); an element's opacity -> 'opacity'
INK_PRIM={'feGaussianBlur':{'blur','drop_shadow'},'feComponentTransfer':None,'feOffset':{'drop_shadow'},'feFlood':{'drop_shadow'},
          'feComposite':{'drop_shadow'},'feMerge':{'drop_shadow'},'feBlend':{'drop_shadow'},'feTurbulence':{'roughen'},
          'feDisplacementMap':{'roughen'}}
def ink_used(svg_bytes):
    """[(primitive or attribute, candidate ops)] of every filter primitive used by the drawing, plus opacity < 1.
    Inkscape's own Drop Shadow preset contains a feColorMatrix (the shadow colour) next to feFlood / feOffset, and applying
    a second preset merges it into the existing filter (smoke test 2026-11-11): inside a filter with feFlood + feOffset a
    colour matrix may also belong to drop_shadow."""
    import xml.etree.ElementTree as ET
    root=ET.fromstring(svg_bytes);out=[]
    for f in root.iter('{http://www.w3.org/2000/svg}filter'):
        tags={p.tag.split('}')[-1] for p in f};shadow={'feFlood','feOffset'}<=tags
        for p in f:
            tag=p.tag.split('}')[-1]
            if tag=='feColorMatrix':
                t=p.get('type','matrix');c={'hue_rotate'} if t=='hueRotate' else {'saturate','tint'}
                out.append((f'feColorMatrix:{t}',c|({'drop_shadow'} if shadow else set())))
            elif tag=='feComponentTransfer':
                ts={c.get('type','identity') for c in p};ops=set()
                if 'linear' in ts:ops|={'brightness','contrast'}
                if 'gamma' in ts:ops|={'gamma'}
                if ts&{'discrete','table'}:ops|={'posterize'}
                out.append((f'feComponentTransfer:{"/".join(sorted(ts))}',ops or {'brightness','contrast','gamma','posterize'}))
            elif tag in INK_PRIM:out.append((tag,INK_PRIM[tag]))
            else:out.append((tag,set()))   # a primitive outside the library (lighting, morphology, ...)
    for e in root.iter():
        op=e.get('opacity');st=re.search(r'(?:^|;)\s*opacity\s*:\s*([\d.eE+-]+)',e.get('style') or '')
        for v in (op,st.group(1) if st else None):
            try:
                if v is not None and float(v)<1:out.append(('opacity',{'opacity'}))
            except ValueError:pass
    return out

class InkscapeEnv(AppEnv):
    DESKTOP=InkscapeDesktop
    def evaluate(self):
        ev=self.task['evaluator'];saved=self.d.save()
        import xml.etree.ElementTree as ET
        for attempt in range(10):   # Inkscape may still be writing the file (a half-written SVG failed to parse once)
            svg=self.d.image.read_bytes()
            try:ET.fromstring(svg);break
            except ET.ParseError:time.sleep(1)
        # tools used: primitives / opacities the result has beyond those START already had
        from collections import Counter
        new=Counter(k for k,_ in ink_used(svg))-Counter(k for k,_ in ink_used(self.d.start_svg))
        cand={k:c for k,c in ink_used(svg)};used=set();bad=[]
        allowed=set(self.task.get('allowed_modules') or [])
        for k in new:
            c=cand[k]
            if self.task.get('allowed_modules') is None:used|=c
            elif c&allowed:used|=c&allowed
            else:bad.append(k)
        out={'saved':saved,'modules_used':sorted(used),'new_primitives':sorted(new)}
        if self.task.get('allowed_modules') is not None and bad:return {**out,'pass':False,'gate':f'tools not allowed: {sorted(bad)}'}
        result=self.work/'result.png'
        try:
            with tempfile.TemporaryDirectory() as t:
                (Path(t)/'r.svg').write_bytes(svg);OI.export(Path(t)/'r.svg',Path(t)/'o.png',_size(ev['expected']['path']))
                Image.open(Path(t)/'o.png').convert('RGB').save(result)
        except Exception as e:return {**out,'pass':False,'gate':f'render failed: {e!r}'[:300]}
        return _score(out,ev,result)

# ------------------------------------------------------------------ RawTherapee 5.13
import ops_rawtherapee as OR
RT_APPRUN=OR.LOCAL/'apps/rawtherapee-5.13/squashfs-root/AppRun'
RT_SECTION_TOOL={s:m for m,fs in OR.PP3.items() for s,_,_ in fs.values()}
RT_SECTION_TOOL.update({s:m for m,secs in OR.SECTION_KEYS.items() for s in secs})
RT_IGNORE={'Version','General','Exif','IPTC','Resize','PostDemosaicSharpening','Meta','Film Negative','MetaData','RAW'}   # bookkeeping / raw-only, not edits
# keys the editor rewrites on exit once anything was edited (checked: the render of START is identical, dE 0)
RT_AUTO={('Color Management','InputProfile'):{'(cameraICC)','(embedded)'},('Color Management','Will'):{'def','D65'}}
# written on exit whatever its value (perspective correction itself stays off): the focal length read from the file
RT_AUTO_ANY={('Perspective','CameraFocalLength')}
class RawTherapeeDesktop(AppDesktop):
    TITLE=r'^RawTherapee'
    SETTLE=6
    def prepare(self,home,src):
        cfg=home/'.config/RawTherapee-AppImage';cfg.mkdir(parents=True)
        shutil.copy(HERE/'rawtherapee_options.template',cfg/'options')   # a first run's options: no About window, ImgDefault=Neutral
        self.image=self.dir/'img'/('start'+src.suffix.lower());shutil.copy(src,self.image)
        return [str(RT_APPRUN),str(self.image)]
    def sidecar(self):
        p=self.image.with_name(self.image.name+'.pp3');return p.read_text() if p.exists() else None
    def finish(self,timeout=60):
        """Closes RawTherapee like a user (Alt+F4 -> openbox -> WM_DELETE_WINDOW): the editor writes the sidecar on exit."""
        if self.app.poll() is not None:return
        self.focus_main();self.key('Escape');time.sleep(0.3);self.key('alt+F4')
        t=time.time()
        while time.time()-t<timeout and self.app.poll() is None:time.sleep(0.5)

def rt_same(a,b,section=''):
    """Two pp3 sections are the same edit: both disabled (RawTherapee fills a disabled Crop with the image size on exit),
    or every key equal, numbers within 0.1 % (on exit it recomputes the 'Camera' white balance: 6504 -> 6501, 1 -> 0.99999)."""
    if a.get('Enabled')=='false' and b.get('Enabled','false')=='false' or b.get('Enabled')=='false' and a.get('Enabled','false')=='false':return True
    for k in set(a)|set(b):
        x,y=a.get(k),b.get(k)
        if x==y or {x,y}<=RT_AUTO.get((section,k),set()) or (section,k) in RT_AUTO_ANY:continue
        try:
            fx,fy=float(x),float(y)
            if abs(fx-fy)<=1e-3*max(abs(fx),abs(fy),1.0):continue
        except (TypeError,ValueError):pass
        return False
    return True

class RawTherapeeEnv(AppEnv):
    DESKTOP=RawTherapeeDesktop
    def reset(self,task):
        # the editor writes the sidecar when it opens the image: that is START's state for this image (crop = image size,
        # 'Camera' white balance of this file), the baseline every later change is compared with
        obs=super().reset(task);t=time.time()
        while self.d.sidecar() is None and time.time()-t<30:time.sleep(0.5)
        if self.d.sidecar() is None:   # the editor did not load the image (seen once in the replay check): harness error, retried
            raise RuntimeError('RawTherapee wrote no sidecar on open')
        self.base=self.d.sidecar();return obs
    def evaluate(self):
        ev=self.task['evaluator'];self.d.finish();side=self.d.sidecar() or self.base
        g=OR.read_pp3(side);base=OR.read_pp3(self.base)
        changed=sorted(s for s in set(g)|set(base) if s not in RT_IGNORE and not rt_same(g.get(s,{}),base.get(s,{}),s))
        used={RT_SECTION_TOOL.get(s,f'other:{s}') for s in changed}
        out={'modules_used':sorted(used),'changed_sections':changed}
        if (r:=_gate(out,used,self.task)):return r
        g['Resize']=OR.read_pp3(OR.pp3([],_size(ev['expected']['path'])))['Resize']
        text=''.join(f'[{s}]\n'+''.join(f'{k}={v}\n' for k,v in kv.items())+'\n' for s,kv in g.items())
        result=self.work/'result.png'
        img=next(c['parameters']['path'] for c in self.task['config'] if c['type']=='open_image')
        try:OR.render_pp3(img,text,result)
        except Exception as e:return {**out,'pass':False,'gate':f'render failed: {e!r}'[:300]}
        return _score(out,ev,result)

# ------------------------------------------------------------------ Blender 4.5.15
import ops_blender as OB,blender_start
BL_USERCFG=OB.LOCAL/'apps/gui_agents/blender_userconfig'
def blender_userconfig():
    """userpref.blend with the splash / Quick Setup off (first run otherwise shows it over the viewport)."""
    if not (BL_USERCFG/'userpref.blend').exists():
        BL_USERCFG.mkdir(parents=True,exist_ok=True)
        subprocess.run([str(OB.BLENDER),'-b','--factory-startup','--python-expr',
                        'import bpy;p=bpy.context.preferences;p.view.show_splash=False;p.use_preferences_save=False;bpy.ops.wm.save_userpref()'],
                       env={**os.environ,'BLENDER_USER_CONFIG':str(BL_USERCFG)},capture_output=True,timeout=300)
    return BL_USERCFG
STATE_PY=HERE/'blender_state.py'
def blender_state(blend):
    r=subprocess.run([str(OB.BLENDER),'-b','--factory-startup',str(blend),'--python',str(STATE_PY)],capture_output=True,text=True,timeout=300)
    m=re.search(r'^BENCH_STATE (.*)$',r.stdout,re.M)
    if not m:raise RuntimeError('blender state read failed: '+(r.stdout+r.stderr)[-500:])
    return json.loads(m.group(1))

class BlenderDesktop(AppDesktop):
    TITLE=r'Blender'
    SETTLE=6
    def extra_env(self,home):return {'BLENDER_USER_CONFIG':str(blender_userconfig())}
    def prepare(self,home,src):
        # START copies are cached per scene (absolute texture paths, blender_start.check pixel-identical)
        cache=OB.LOCAL/'apps/gui_agents/blender_start_cache'/src.name
        if not cache.exists():   # written under a unique name and renamed: two episodes of one scene once raced here
            cache.parent.mkdir(parents=True,exist_ok=True);tmp=cache.with_name(f'.{cache.stem}.{os.getpid()}.{time.time_ns()}.blend')
            blender_start.gui_copy(src,tmp);os.replace(tmp,cache)
        self.image=self.dir/'img'/'start.blend';shutil.copy(cache,self.image)
        return [str(OB.BLENDER),'-t','8',str(self.image)]   # 2026-11-12: 8 render threads (default: all 192 cores per instance)
    def save(self,timeout=40):
        before=self.image.stat().st_mtime_ns
        for attempt in range(3):
            self.focus_main();self.move(800,500);self.key('Escape');time.sleep(0.3);self.key('ctrl+s')
            t=time.time()
            while time.time()-t<timeout/3:
                if self.image.stat().st_mtime_ns!=before:time.sleep(1);return True
                time.sleep(0.3)
        return False

BL_IGNORE={'file'}
class BlenderEnv(AppEnv):
    DESKTOP=BlenderDesktop
    def reset(self,task):
        obs=super().reset(task);self.start_state=blender_state(self.d.image);return obs
    def evaluate(self):
        ev=self.task['evaluator'];saved=self.d.save()
        try:st=blender_state(self.d.image)
        except Exception as e:return {'saved':saved,'pass':False,'gate':f'{e!r}'[:300]}
        changed=sorted(k for k in set(st)|set(self.start_state) if st.get(k)!=self.start_state.get(k) and k not in BL_IGNORE)
        used={k.split(':')[0] for k in changed}
        out={'saved':saved,'modules_used':sorted(used),'changed':changed}
        if (r:=_gate(out,used,self.task)):return r
        result=self.work/'result.png'
        try:OB.render_steps(self.d.image,[],result,_size(ev['expected']['path']))
        except Exception as e:return {**out,'pass':False,'gate':f'render failed: {e!r}'[:300]}
        return _score(out,ev,result)

ENVS={'inkscape':InkscapeEnv,'rawtherapee':RawTherapeeEnv,'blender':BlenderEnv}
