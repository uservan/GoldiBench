"""OSWorld-style environment for the GIMP GUI bench (bench_gimp_gui1): GIMP 3.2.6 in a disposable Xvfb desktop.

Same action / observation interface as env.DarktableEnv (step() is inherited). GIMP opens the full-resolution source
photo, as the program bench renders TARGET from it. GIMP 3 applies Colors / Filters entries as non-destructive layer
filters by default, so the edit is read back from the image itself:
  1. GIMP is started with the Script-Fu server (`-b`, a free localhost port per desktop); evaluate() asks it to save the
     open image as XCF. Nothing is shown on the screen and the agent never has to save or export.
  2. gimp-console loads that XCF (gimp_xcf.py), lists the layer filters with their settings, flattens and scales it to
     <= 1024 px exactly like the program bench, and the result is scored like the program bench (pass = closeness
     >= 0.75 and dE00 <= 4).
A filter dialog left open without OK is not part of the image (its preview is not saved). Legality gate at L1/L2: every
visible layer filter must be one of the task's filters. Filters applied with "Merge filter" ticked become pixels and are
not visible to the gate (counted in 'merged_edit' when the pixels differ from START).
"""
import json,os,shutil,signal,socket,struct,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
from desktop import Desktop,W,H,LOCAL
from env import DarktableEnv
import ops_gimp,score
from make_pilot import passed

APPRUN=LOCAL/'apps/gimp-3.2.6/squashfs-root/AppRun'
READER=Path(__file__).with_name('gimp_xcf.py')
# gimprc additions: no update check (offline, its failure pops a message over the canvas); keep an embedded color profile
# without asking (JPEGs with an sRGB profile otherwise open a modal dialog before the image), as the program bench's
# non-interactive load does. Every episode starts from a fresh copy of the same home, so GIMP's default single-window
# layout (toolbox left, docks right) is the first screen.
GIMPRC='(check-updates no)\n(color-profile-policy keep)\n'
OP_TOOL={op:tool for tool,op in ops_gimp.OP.items()}

def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

def script_fu(port,cmd,timeout=120):
    """One request to GIMP's Script-Fu server ('G' + length + script -> 'G' + error flag + length + text)."""
    with socket.create_connection(('127.0.0.1',port),timeout=timeout) as s:
        b=cmd.encode();s.sendall(b'G'+struct.pack('>H',len(b))+b);h=b''
        while len(h)<4:
            c=s.recv(4-len(h))
            if not c:raise ConnectionError('script-fu server closed the connection')
            h+=c
        n=struct.unpack('>H',h[2:4])[0];d=b''
        while len(d)<n:
            c=s.recv(n-len(d))
            if not c:break
            d+=c
    return h[1]==0,d.decode(errors='replace')

class GimpDesktop(Desktop):
    def start(self,image):
        if self.dir.exists():shutil.rmtree(self.dir)
        (self.dir/'img').mkdir(parents=True)
        self.image=self.dir/'img'/('start'+Path(image).suffix.lower());shutil.copy(image,self.image)
        shutil.copytree(ops_gimp._template(),self.dir,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.ready'))
        self.env['HOME']=str(self.dir)
        rc=self.dir/'.config/GIMP/3.2/gimprc';rc.parent.mkdir(parents=True,exist_ok=True)
        rc.write_text((rc.read_text() if rc.exists() else '')+GIMPRC)
        r,w=os.pipe()
        xkb=['-xkbdir',os.environ['XKB_DIR']] if os.environ.get('XKB_DIR') else []
        x=subprocess.Popen(['Xvfb','-displayfd',str(w),'-screen','0',f'{W}x{H}x24','-nolisten','tcp',*xkb],pass_fds=(w,),
                           stdout=open(self.dir/'xvfb.log','w'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        os.close(w);self.procs.append(x)
        with os.fdopen(r) as f:num=f.readline().strip()
        if not num.isdigit():self.close();raise RuntimeError('Xvfb did not start: '+(self.dir/'xvfb.log').read_text()[-300:])
        self._set_display(int(num));self.env['HOME']=str(self.dir)
        # openbox exits at once when it finds no theme ("Unable to load a theme"), leaving no window manager, so filter
        # dialogs never get keyboard focus. Point it at the config and themes of the unpacked copy (setup_xtools.sh).
        # Normal windows (the GIMP image window) have no title bar and are sized to the screen in start(), so the layout
        # is the same in every episode; dialogs keep their frame and can be moved.
        ob=Path(shutil.which('openbox')).resolve().parent.parent.parent
        rc=(ob/'etc/xdg/openbox/rc.xml').read_text()
        a,b=rc.index('<applications>'),rc.index('</applications>')+len('</applications>')
        rc=rc[:a]+'<applications><application type="normal"><decor>no</decor><maximized>yes</maximized></application></applications>'+rc[b:]
        (self.dir/'.config/openbox').mkdir(parents=True,exist_ok=True);(self.dir/'.config/openbox/rc.xml').write_text(rc)
        self.procs.append(subprocess.Popen(['openbox'],env={**self.env,'XDG_CONFIG_DIRS':str(ob/'etc/xdg'),'XDG_DATA_DIRS':str(ob/'usr/share')},
                                           stdout=open(self.dir/'openbox.log','w'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,
                                           start_new_session=True,cwd=self.dir))
        time.sleep(1)
        if self.procs[-1].poll() is not None:self.close();raise RuntimeError('openbox exited: '+(self.dir/'openbox.log').read_text()[-300:])
        for attempt in range(3):
            self.port=free_port()
            # --new-instance: GIMPs started together otherwise hand their command line to one another and hang
            g=self._spawn([str(APPRUN),'--new-instance','--no-splash','--batch-interpreter','plug-in-script-fu-eval','-b',
                           f'(plug-in-script-fu-server #:run-mode RUN-NONINTERACTIVE #:ip "127.0.0.1" #:port {self.port} #:logfile "")',
                           str(self.image)],f'gimp{attempt}.log')
            for _ in range(240):
                if (self.window() and self.ready()) or g.poll() is not None:break
                time.sleep(0.5)
            if self.window() and self.ready():break
            if g.poll() is None:os.killpg(g.pid,signal.SIGKILL)
            self.procs.remove(g);time.sleep(1)
        else:
            self.close();raise RuntimeError('GIMP window / script-fu server did not come up')
        time.sleep(2)
        wid=self.window();self.xdo('windowsize',wid,str(W),str(H));self.xdo('windowmove',wid,'0','0')
        time.sleep(1.5);return self

    def ready(self):
        try:return script_fu(self.port,'(car (gimp-get-images))',timeout=5)[0]
        except OSError:return False

    def window(self):
        out=self.xdo('search','--onlyvisible','--name',' GIMP$');return out.split('\n')[0] if out else None

    def save_xcf(self,path):
        """Saves the first open image (the START photo unless the agent opened others) as XCF; None when no image is open."""
        ok,ids=script_fu(self.port,'(car (gimp-get-images))')
        if not ok:raise RuntimeError('script-fu: '+ids)
        nums=[int(t) for t in ids.strip('#()').split() if t.lstrip('-').isdigit()]
        if not nums:return None
        ok,msg=script_fu(self.port,f'(gimp-file-save RUN-NONINTERACTIVE {min(nums)} "{path}")',timeout=600)
        if not ok or not Path(path).exists():raise RuntimeError('script-fu save failed: '+msg[:300])
        return Path(path)

def render_xcf(xcf,out,size=1024,timeout=900):
    """gimp-console: list layer filters of xcf and render it like the program bench; returns the filter record."""
    with tempfile.TemporaryDirectory(dir=os.environ.get('VE_TMP')) as tmp:
        shutil.copytree(ops_gimp._template(),tmp,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.ready'))
        Path(out).unlink(missing_ok=True);rec=Path(str(xcf)+'.json');rec.unlink(missing_ok=True)
        cmd=f"XCF={str(xcf)!r};OUT={str(out)!r};SIZE={int(size)};exec(open({str(READER)!r}).read())"
        r=subprocess.run([str(ops_gimp.APPRUN),'-i','-n','--no-fonts','-d','--quit','--batch-interpreter','python-fu-eval','-b',cmd],
                         capture_output=True,text=True,timeout=timeout,cwd=tmp,env={**os.environ,'HOME':tmp})
        if rec.exists() and json.loads(rec.read_text())['layers']==0:return json.loads(rec.read_text())
        if not rec.exists() or not Path(out).exists():raise RuntimeError('gimp-console render failed: '+(r.stdout+r.stderr)[-600:])
        return json.loads(rec.read_text())

class GimpEnv(DarktableEnv):
    def reset(self,task):
        self.close();self.task=task
        image=next(c['parameters']['path'] for c in task['config'] if c['type']=='open_image')
        self.d=GimpDesktop(self.work,self.display).start(image);self.actions=[]
        return self.observe()

    def evaluate(self):
        ev=self.task['evaluator'];target=ev['expected']['path'];result=self.work/'result.png'
        xcf=self.d.save_xcf(self.work/'result.xcf')
        if xcf is None:return {'pass':False,'gate':'no image open'}
        rec=render_xcf(xcf,result)
        if not rec['layers']:return {'pass':False,'gate':'image has no layers'}
        filters=[f for f in rec['filters'] if f['visible']]
        used=[OP_TOOL.get(f['op'],f['op']) for f in filters]
        out={'modules_used':sorted(set(used)),'filters':rec['filters'],'layers':rec['layers']}
        lt=score.lab(target);lr=score.lab(result);ls=score.lab(ev['start_path'])
        if lr.shape!=lt.shape:return {**out,'pass':False,'gate':f'geometry changed: output {lr.shape[:2]} vs target {lt.shape[:2]}'}
        if not filters and score.de(lr,ls)>0.05:out['merged_edit']=True   # pixels changed without any layer filter
        allowed=self.task.get('allowed_modules')
        if allowed is not None and set(used)-set(allowed):
            return {**out,'pass':False,'gate':f'filters not allowed: {sorted(set(used)-set(allowed))}'}
        d0=score.de(ls,lt);dd=score.de(lr,lt)
        return {**out,'de00':round(dd,3),'d0':round(d0,3),'closeness':round(1-dd/d0,4),'pass':passed(dd,d0)}
