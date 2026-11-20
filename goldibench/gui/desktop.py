"""A disposable X desktop running the darktable GUI, driven like an OSWorld VM (screenshot in, mouse/keyboard out).

One Desktop = one Xvfb display + openbox + darktable 5.6.2 opened in the darkroom on a single image, with its own config
dir and library (nothing shared between episodes). Actions go through xdotool, screenshots through ffmpeg x11grab.
The edit is read back from the XMP sidecar darktable rewrites next to the image after every change (write_sidecar_files=on
import; 'after edit' did not write it during the session), so the
evaluator can re-render it with darktable-cli exactly as it scores programs.

No KVM on the pilot nodes, hence Xvfb instead of a VM; the action/observation interface is the one OSWorld's
DesktopEnv exposes, so the same agent can later drive a container or a QCOW2 VM.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
import io,os,shutil,signal,subprocess,time
from PIL import Image

LOCAL=Path(os.environ.get('VE_LOCAL',str(gbpaths.LOCAL)))
APPRUN=LOCAL/'apps/darktable-5.6.2/squashfs-root/AppRun'
RC_TEMPLATE=Path(__file__).with_name('darktablerc.template')
W,H=1920,1080
# Settings that make every episode start from the same screen (tooltips off: they cover the slider under the
# pointer; no scrolling to an expanded module: slider positions must not depend on the panel's scroll state). The rest of the template is darktable 5.6.2's own
# first-run darktablerc.
RC={'ui/show_welcome_screen':'FALSE','write_sidecar_files':'on import','ui/hide_tooltips':'TRUE','darkroom/ui/scroll_to_module':'FALSE','ui_last/window_x':'0','ui_last/window_y':'0',
    'ui_last/window_w':str(W),'ui_last/window_h':str(H),'ui_last/fullscreen':'FALSE','ui_last/maximized':'TRUE'}

def _rc(path):
    lines=RC_TEMPLATE.read_text().splitlines() if RC_TEMPLATE.exists() else []
    keep=[l for l in lines if l.split('=',1)[0] not in RC]
    path.write_text('\n'.join(keep+[f'{k}={v}' for k,v in RC.items()])+'\n')

LOCAL_LOGS=Path(os.environ.get('GUI_LOCAL_LOGS',str(gbpaths.LOCAL)+'/episode_logs'))

class Desktop:
    def __init__(self,workdir,display=None):
        """display=None: start() lets Xvfb pick a free display (-displayfd), so concurrent desktops can never share one
        (a fixed number collided with a running desktop on 2026-10-24 and two agents drove the same screen).
        A number attaches to that existing display (for driving a desktop started elsewhere)."""
        self.dir=Path(workdir);self.procs=[];self._set_display(display)

    def _set_display(self,display):
        self.display=f':{display}' if display is not None else None
        self.env={**os.environ,'DISPLAY':self.display or '','HOME':str(self.dir),'GDK_BACKEND':'x11','NO_AT_BRIDGE':'1'}

    def _log(self,name):
        """Process logs on the node-local NVMe (2026-11-12): Xvfb writes an XKB warning to its log whenever a keymap is
        recompiled (xdotool key / type), so a /shared (FSx) stall blocked the X server and every screenshot on all nodes."""
        try:
            d=LOCAL_LOGS/'_'.join(Path(self.dir).resolve().parts[-5:]);d.mkdir(parents=True,exist_ok=True);return d/name
        except OSError:return self.dir/name

    def _spawn(self,args,log):
        p=subprocess.Popen(args,env=self.env,stdout=open(self._log(log),'w'),stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL,start_new_session=True,cwd=self.dir)
        self.procs.append(p);return p

    def start(self,image):
        """Fresh config + copy of `image`; returns once the darkroom window is up."""
        if self.dir.exists():shutil.rmtree(self.dir)
        (self.dir/'conf').mkdir(parents=True);(self.dir/'img').mkdir()
        self.image=self.dir/'img'/('start'+Path(image).suffix.lower());shutil.copy(image,self.image)
        _rc(self.dir/'conf'/'darktablerc')
        r,w=os.pipe()
        xkb=['-xkbdir',os.environ['XKB_DIR']] if os.environ.get('XKB_DIR') else []   # X tools unpacked without root (scripts/xtools_env.sh)
        x=subprocess.Popen(['Xvfb','-displayfd',str(w),'-screen','0',f'{W}x{H}x24','-nolisten','tcp',*xkb],pass_fds=(w,),
                           stdout=open(self._log('xvfb.log'),'w'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        os.close(w);self.procs.append(x)
        with os.fdopen(r) as f:num=f.readline().strip()   # written once the server accepts connections
        if not num.isdigit():self.close();raise RuntimeError('Xvfb did not start: '+self._log('xvfb.log').read_text()[-300:])
        self._set_display(int(num))
        self._spawn(['openbox'],'openbox.log');time.sleep(0.5)
        # darktable 5.6.2 sometimes aborts at startup (Gtk gtk_css_value_inherit_free assertion); a relaunch works.
        for attempt in range(4):
            dt=self._spawn([str(APPRUN),'--configdir',str(self.dir/'conf'),'--library',str(self.dir/'conf'/'library.db'),
                            '--disable-opencl',str(self.image)],f'darktable{attempt}.log')
            for _ in range(120):
                if self.window() or dt.poll() is not None:break
                time.sleep(0.5)
            if self.window():break
            if dt.poll() is None:os.killpg(dt.pid,signal.SIGKILL)
            self.procs.remove(dt);time.sleep(1)
        else:
            self.close();raise RuntimeError('darktable window did not appear')
        time.sleep(4)   # first full-resolution preview
        wid=self.window();self.xdo('windowsize',wid,str(W),str(H));self.xdo('windowmove',wid,'0','0')
        time.sleep(1);return self

    def xdo(self,*args):
        return subprocess.run(['xdotool',*map(str,args)],env=self.env,capture_output=True,text=True,timeout=30).stdout.strip()

    def window(self):
        out=self.xdo('search','--onlyvisible','--name','^darktable$');return out.split('\n')[0] if out else None

    def screenshot(self):
        for attempt in range(3):
            r=subprocess.run(['ffmpeg','-loglevel','error','-f','x11grab','-video_size',f'{W}x{H}','-i',self.display,
                              '-frames:v','1','-f','image2pipe','-vcodec','png','-'],env=self.env,capture_output=True,timeout=30)
            if r.stdout:return Image.open(io.BytesIO(r.stdout)).convert('RGB')
            time.sleep(1)
        raise RuntimeError('screenshot failed: '+r.stderr.decode(errors='ignore')[-300:])

    # --- actions (OSWorld computer_13 subset) ---
    def move(self,x,y):self.xdo('mousemove',int(x),int(y))
    def click(self,x,y,button=1,n=1):self.xdo('mousemove',int(x),int(y),'click','--repeat',n,button)
    def drag(self,x1,y1,x2,y2,steps=12):
        self.xdo('mousemove',int(x1),int(y1),'mousedown',1)
        for i in range(1,steps+1):self.xdo('mousemove',int(x1+(x2-x1)*i/steps),int(y1+(y2-y1)*i/steps));time.sleep(0.02)
        self.xdo('mouseup',1)
    def scroll(self,x,y,dy):
        self.xdo('mousemove',int(x),int(y),'click','--repeat',abs(int(dy)),5 if dy>0 else 4)   # dy>0 = down
    def type(self,text):self.xdo('type','--delay','30','--',text)   # '--': a value like '-0.59' was parsed as an option and never typed (2026-11-11)
    def key(self,combo):self.xdo('key',combo)

    def sidecar(self):
        """darktable's XMP for the image as last written (may lag the GUI by seconds; call flush() first)."""
        p=self.image.with_name(self.image.name+'.xmp');return p.read_text() if p.exists() else None

    def flush(self,timeout=20):
        """Make darktable write the current history: leaving the darkroom (click 'lighttable' in the view switcher)
        writes it synchronously. Ends the episode's interaction; waits until the sidecar has been rewritten."""
        p=self.image.with_name(self.image.name+'.xmp');before=p.stat().st_mtime_ns if p.exists() else 0
        self.click(1477,54)
        t=time.time()
        while time.time()-t<timeout:
            if p.exists() and p.stat().st_mtime_ns!=before:time.sleep(0.5);return True
            time.sleep(0.25)
        return False   # nothing new to write (no edit since the last write)

    def close(self):
        for p in reversed(self.procs):
            try:os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        for p in self.procs:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL)
        self.procs=[]
