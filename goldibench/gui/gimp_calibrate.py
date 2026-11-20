"""Check gimp_map against GIMP itself, one fresh desktop per filter:
  probe:    type a display value into every bench field (gimp_replay), OK, read the saved layer filter and compare the
            stored property with gimp_map.program(display value).
  defaults: OK without touching anything; the stored config = the GUI's defaults. Compared with the defaults the
            program bench renders with (gegl op defaults + ops_gimp.SETTINGS, read in gimp-console), every property
            where they differ is listed: the GUI bench must state those values in L1 (make_gimp_gui_tasks.py).
Writes bench_gimp_gui1/calibration.json. Usage: gimp_calibrate.py [tool ...]
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import json,os,shutil,subprocess,sys,tempfile,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
import gimp_map as G,gimp_replay as R,ops_gimp
from gimp_env import GimpDesktop,render_xcf,LOCAL

DATA=gbpaths.DATA
OUT=DATA/'bench_gimp_gui1'
IMAGE=DATA/'bench_gimp1/tasks/s00/start.png'
PROBE={'brightness_contrast':{'brightness':51,'contrast':-38},'exposure':{'black_level':0.02,'exposure':-0.8},
       'color_temperature':{'intended_temperature':8000},'hue_saturation':{'hue':30,'saturation':-40,'lightness':15},
       'color_balance':{'cyan_red':25,'magenta_green':-30,'yellow_blue':40},'levels':{'low_input':30,'gamma':1.6,'high_input':220},
       'shadows_highlights':{'shadows':40,'highlights':-30},'unsharp_mask':{'radius':2.5,'amount':1.2},'gaussian_blur':{'size':4},
       'vignette':{'radius':1.8,'softness':0.5},'softglow':{'glow_radius':12,'brightness':0.4}}
CONSOLE=r'''
import json,gi
gi.require_version('Gimp','3.0')
from gi.repository import Gimp,Gio
img=Gimp.Image.new(8,8,Gimp.ImageBaseType.RGB);l=Gimp.Layer.new(img,'l',8,8,Gimp.ImageType.RGB_IMAGE,100,Gimp.LayerMode.NORMAL);img.insert_layer(l,None,0)
out={}
for op in OPS:
    c=Gimp.DrawableFilter.new(l,op,'').get_config();d={}
    for p in c.list_properties():
        try:v=c.get_property(p.name)
        except Exception as e:v='<%s>'%type(e).__name__
        d[p.name]=v if isinstance(v,(int,float,bool,str,type(None))) else str(v)
    out[op]=d
json.dump(out,open(DEST,'w'),indent=1)
'''

def console_defaults():
    dest=OUT/'gegl_defaults.json'
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(ops_gimp._template(),tmp,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.ready'))
        code=f'OPS={list(ops_gimp.OP.values())!r};DEST={str(dest)!r}\n'+CONSOLE
        Path(tmp,'c.py').write_text(code)
        subprocess.run([str(ops_gimp.APPRUN),'-i','-n','--no-fonts','-d','--quit','--batch-interpreter','python-fu-eval','-b',
                        f"exec(open({str(Path(tmp,'c.py'))!r}).read())"],capture_output=True,timeout=600,cwd=tmp,env={**os.environ,'HOME':tmp})
    return json.loads(dest.read_text())

def session(tool,mode):
    work=LOCAL/f'gui_work/gimp_cal_{mode}_{tool}';d=GimpDesktop(work).start(IMAGE)
    try:
        if mode=='probe':R.apply(d,{tool:{f:G.program(tool,f,x) for f,x in PROBE[tool].items()}})
        else:
            main=d.window();R.open_filter(d,tool);w,x,y=R.dialog(d,main);ok=G.FIELDS[tool][1]
            time.sleep(1.0);d.click(x+ok[0],y+ok[1]);time.sleep(2.5)
        d.screenshot().save(OUT/f'calibration_{mode}_{tool}.png')
        rec=render_xcf(d.save_xcf(work/'cal.xcf'),work/'cal.png')
        fs=[f for f in rec['filters'] if f['op']==ops_gimp.OP[tool]]
        return tool,mode,(fs[-1]['props'] if fs else None),len(rec['filters'])
    finally:d.close()

def main(tools):
    OUT.mkdir(parents=True,exist_ok=True);tools=tools or list(G.FIELDS)
    gegl=console_defaults();rows=[];diffs={}
    with ThreadPoolExecutor(11) as ex:res=list(ex.map(lambda j:session(*j),[(t,m) for t in tools for m in('probe','defaults')]))
    for tool,mode,props,n in res:
        if props is None:rows.append({'tool':tool,'mode':mode,'error':f'no {ops_gimp.OP[tool]} filter saved ({n} filters)'});print(rows[-1]);continue
        if mode=='probe':
            for f,shown in PROBE[tool].items():
                want=ops_gimp.props(tool,{f:G.program(tool,f,shown)})
                for k,v in want.items():
                    if k in ops_gimp.SETTINGS.get(tool,{}):continue
                    got=props.get(k);ok=isinstance(got,(int,float)) and abs(got-v)<=2e-3*max(1,abs(v))
                    rows.append({'tool':tool,'field':f,'prop':k,'typed':shown,'stored':got,'expected':v,'ok':ok});print(json.dumps(rows[-1]))
        else:
            ref={**gegl[ops_gimp.OP[tool]],**{k:(v['name'] if isinstance(v,dict) else v) for k,v in ops_gimp.SETTINGS.get(tool,{}).items()}}
            dd={}
            for k,v in props.items():
                r=ref.get(k)
                if isinstance(v,(int,float)) and isinstance(r,(int,float)) and not isinstance(v,bool):same=abs(v-r)<=1e-6*max(1,abs(r))
                else:same=str(v).split('.')[-1].split(' ')[0].upper().strip('<>')==str(r).split('.')[-1].split(' ')[0].upper().strip('<>') or str(v)==str(r)
                if not same:dd[k]={'gui':v,'program':r}
            diffs[tool]=dd;print(tool,'GUI defaults that differ from the program renderer:',json.dumps(dd))
    (OUT/'calibration.json').write_text(json.dumps({'probe':rows,'default_diffs':diffs},indent=1,default=str))
    print('probe ok',sum(r.get('ok',False) for r in rows),'/',len(rows))

if __name__=='__main__':main(sys.argv[1:])
