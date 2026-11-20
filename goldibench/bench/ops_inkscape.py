"""Operation library on Inkscape 1.4.4 (BENCH_APP=inkscape). Start assets are CC0 Openclipart illustrations
(fetch_openclipart.py). A program is applied the way an Inkscape user applies it to a whole drawing: select all, group,
then filters (Filters menu / Filter Editor) and the group's opacity (Fill and Stroke). It is written into the SVG as
one <filter> in <defs> whose primitives run in program order (ORDERED) on a group wrapping every drawable child of the
root, so the edit state is the SVG itself. Renders: inkscape --export-area-page on a white background, long side = size.

Lengths (blur, shadow offset, roughen scale) are in % of the page's (width + height) / 2, so the same value looks
alike on documents of any size (Inkscape's Blur % is defined on the object's bounding box the same way).
Colour primitives run in sRGB (color-interpolation-filters="sRGB", as Inkscape's own preset filters).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
import colorsys,os,re,subprocess,tempfile
import xml.etree.ElementTree as ET

LOCAL=Path(os.environ.get('VE_LOCAL',str(gbpaths.LOCAL)))
INKSCAPE=LOCAL/'apps/inkscape-1.4.4/squashfs-root/AppRun'
DATA=gbpaths.DATA
SVG='http://www.w3.org/2000/svg';ET.register_namespace('',SVG)
for p,u in {'inkscape':'http://www.inkscape.org/namespaces/inkscape','sodipodi':'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd',
            'xlink':'http://www.w3.org/1999/xlink','rdf':'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            'dc':'http://purl.org/dc/elements/1.1/','cc':'http://creativecommons.org/ns#'}.items():ET.register_namespace(p,u)

PRODUCT='Inkscape'
ORDERED=True
UNIT_WORD='filter'
DOMAIN='vector illustration'
# filter -> (name shown to models, what it does, {field: (min, max, unit/help)})
OPS={
 'blur':('Blur (Fill and Stroke)','Gaussian blur of the whole drawing; 0.1 slightly softens the lines, 0.2 is clearly soft, 0.4 is a strong blur',{'radius':(0.0,0.4,'% of page size')}),   # was 0-1.5: every accepted radius >= 0.44 wrecked the drawing (B-1 review round 3)
 'opacity':('Opacity (Fill and Stroke)','opacity of the whole drawing over the white page',{'opacity':(0.25,1.0,'')}),
 'hue_rotate':('Hue Rotate (Filter Editor: Color Matrix)','rotates every hue',{'angle':(-180.0,180.0,'degrees')}),
 'saturate':('Saturate (Filter Editor: Color Matrix)','scales colour saturation (0 = grey)',{'amount':(0.0,2.5,'')}),
 'brightness':('Brightness (Filter Editor: Component Transfer, linear)','adds to R, G and B',{'offset':(-0.35,0.35,'')}),
 'contrast':('Contrast (Filter Editor: Component Transfer, linear)','scales R, G and B around mid grey',{'amount':(0.4,2.0,'')}),
 'gamma':('Gamma (Filter Editor: Component Transfer, gamma)','R, G, B raised to this exponent (>1 darker midtones)',{'exponent':(0.4,2.5,'')}),
 'tint':('Colorize (Filters > Color > Colorize)','multiplies the colours towards one hue (hue in degrees: 0 red, 120 green, 240 blue); no effect while strength is 0',{'hue':(0.0,360.0,'degrees'),'strength':(0.0,0.8,'')}),
 'posterize':('Posterize (Filters > Color > Posterize)','reduces each channel to this many levels',{'levels':(2.0,6.0,'')}),
 'drop_shadow':('Drop Shadow (Filters > Shadows and Glows)','black shadow under the drawing; visible only when offset (or blur) and opacity are both > 0',
                {'offset':(0.0,3.0,'% of page size'),'blur':(0.0,2.0,'% of page size'),'opacity':(0.0,1.0,'')}),
 'roughen':('Roughen (Filters > Distort)','wobbles edges with turbulence noise',{'scale':(0.0,3.0,'% of page size')}),
}
# directions for LLM-designed multi-filter programs (make_pilot.llm_program)
STYLES=['warm sunset palette','cool moonlit night look','faded vintage print','soft dreamy glow','bold pop-art colours',
        'muted pastel look','retro screen-printed poster','sticker with a drop shadow','rough hand-made look','dark moody look']
FIXED={}
NEUTRAL={'blur':{'radius':0},'opacity':{'opacity':1},'hue_rotate':{'angle':0},'saturate':{'amount':1},'brightness':{'offset':0},
         'contrast':{'amount':1},'gamma':{'exponent':1},'tint':{'strength':0},'drop_shadow':{'offset':0,'blur':0,'opacity':0},
         'roughen':{'scale':0}}
HUE_PAIRS={'hue':'strength'}
DECIMALS={'posterize':{'levels':0},'hue_rotate':{'angle':1},'tint':{'hue':0}}
MIN_DE_LOCAL={'blur':3.0,'roughen':3.0,'drop_shadow':3.0}

def sources():
    """Start assets: (source id, path) of the Openclipart SVGs fetch_openclipart.py kept (CC0, colourful), by id."""
    import json
    d=DATA/'assets/openclipart';kept=sorted({json.loads(l)['id'] for l in open(d/'fetch_log.jsonl') if json.loads(l)['keep']})
    return [(f'openclipart:{i}',d/'raw'/f'{i}.svg') for i in kept]

UNITS={'px':1,'':1,'pt':4/3,'pc':16,'in':96,'mm':96/25.4,'cm':96/2.54}
def page(root):
    """(x, y, w, h) of the page in user units: the viewBox, else width / height in px."""
    vb=root.get('viewBox')
    if vb:return tuple(float(v) for v in re.split(r'[\s,]+',vb.strip()))
    def px(a):
        m=re.match(r'\s*([\d.eE+-]+)\s*([a-z%]*)',root.get(a,'100'));return float(m.group(1))*UNITS.get(m.group(2),1)
    return 0.0,0.0,px('width'),px('height')

def q(tag):return f'{{{SVG}}}{tag}'
def prim(f,tag,**a):
    e=ET.SubElement(f,q(tag),{k.replace('_','-') if k not in ('in_','in2') else k.rstrip('_'):str(v) for k,v in a.items()});return e
def transfer(f,src,res,**funcs):
    e=prim(f,'feComponentTransfer',in_=src,result=res)
    for ch in 'RGB':prim(e,f'feFunc{ch}',**funcs)
    return res

def build(root,steps):
    """Write steps [(filter, {field: value})] into the parsed SVG root (in place)."""
    x,y,w,h=page(root);L=(w+h)/2/100   # 1 % of the page size in user units
    keep={q('defs'),q('metadata'),'{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}namedview',q('title'),q('desc'),q('style')}
    kids=[c for c in list(root) if c.tag not in keep]
    g=ET.Element(q('g'),{'id':'bench_edit'})
    for c in kids:root.remove(c);g.append(c)
    root.append(g)
    opacity=next((v['opacity'] for m,v in steps if m=='opacity'),None)
    if opacity is not None:g.set('opacity',str(opacity))
    chain=[(m,v) for m,v in steps if m!='opacity']
    if not chain:return root
    defs=root.find(q('defs'))
    if defs is None:defs=ET.Element(q('defs'));root.insert(0,defs)
    pad=0.1
    f=ET.SubElement(defs,q('filter'),{'id':'bench_filter','filterUnits':'userSpaceOnUse','primitiveUnits':'userSpaceOnUse',
        'x':str(x-pad*w),'y':str(y-pad*h),'width':str(w*(1+2*pad)),'height':str(h*(1+2*pad)),'color-interpolation-filters':'sRGB'})
    cur='SourceGraphic'
    for i,(m,v) in enumerate(chain):
        r=f'r{i}'
        if m=='blur':prim(f,'feGaussianBlur',in_=cur,stdDeviation=v.get('radius',0)*L,result=r)
        elif m=='hue_rotate':prim(f,'feColorMatrix',in_=cur,type='hueRotate',values=v.get('angle',0),result=r)
        elif m=='saturate':
            # the SVG 'saturate' matrix written out: Inkscape clamps type="saturate" values to [0, 1] (SVG 1.1)
            k=v.get('amount',1);rw,gw,bw=0.213,0.715,0.072
            mtx=[[rw+(1-rw)*k,gw-gw*k,bw-bw*k],[rw-rw*k,gw+(1-gw)*k,bw-bw*k],[rw-rw*k,gw-gw*k,bw+(1-bw)*k]]
            prim(f,'feColorMatrix',in_=cur,type='matrix',result=r,values='  '.join(' '.join(f'{c:.5f}' for c in row)+' 0 0' for row in mtx)+'  0 0 0 1 0')
        elif m=='brightness':transfer(f,cur,r,type='linear',slope=1,intercept=v.get('offset',0))
        elif m=='contrast':s=v.get('amount',1);transfer(f,cur,r,type='linear',slope=s,intercept=0.5-0.5*s)
        elif m=='gamma':transfer(f,cur,r,type='gamma',amplitude=1,exponent=v.get('exponent',1),offset=0)
        elif m=='posterize':
            n=int(round(v.get('levels',4)));transfer(f,cur,r,type='discrete',tableValues=' '.join(f'{k/(n-1):.4f}' for k in range(n)))
        elif m=='tint':
            s=v.get('strength',0);cr,cg,cb=colorsys.hls_to_rgb(v.get('hue',0)/360,0.5,1.0)
            d=[1-s+s*c for c in (cr,cg,cb)]
            prim(f,'feColorMatrix',in_=cur,type='matrix',result=r,
                 values=f'{d[0]} 0 0 0 0  0 {d[1]} 0 0 0  0 0 {d[2]} 0 0  0 0 0 1 0')
        elif m=='drop_shadow':
            o=v.get('offset',0)*L
            prim(f,'feGaussianBlur',in_=cur,stdDeviation=v.get('blur',0)*L,result=f'{r}b')
            prim(f,'feOffset',in_=f'{r}b',dx=o,dy=o,result=f'{r}o')
            prim(f,'feFlood',flood_color='#000000',flood_opacity=v.get('opacity',0),result=f'{r}c')
            prim(f,'feComposite',in_=f'{r}c',in2=f'{r}o',operator='in',result=f'{r}s')
            mg=prim(f,'feMerge',result=r);prim(mg,'feMergeNode',in_=f'{r}s');prim(mg,'feMergeNode',in_=cur)
        elif m=='roughen':
            prim(f,'feTurbulence',type='fractalNoise',baseFrequency=1/(4*L),numOctaves=3,seed=7,result=f'{r}t')
            prim(f,'feDisplacementMap',in_=cur,in2=f'{r}t',scale=v.get('scale',0)*L,xChannelSelector='R',yChannelSelector='G',result=r)
        else:raise ValueError(m)
        cur=r
    g.set('filter','url(#bench_filter)')
    return root

def write_svg(src,steps,out):
    tree=ET.parse(src);build(tree.getroot(),steps);tree.write(out,xml_declaration=True,encoding='utf-8');return Path(out)

def export(svg,out,size):
    x,y,w,h=page(ET.parse(svg).getroot());dim='--export-width' if w>=h else '--export-height'
    r=subprocess.run([str(INKSCAPE),str(svg),'--export-type=png',f'--export-filename={out}',f'{dim}={size}','--export-area-page',
                      '--export-background=white','--export-background-opacity=1'],capture_output=True,text=True,timeout=180)
    if not Path(out).exists():raise RuntimeError('inkscape export failed: '+(r.stdout+r.stderr)[-500:])
    return Path(out)

def render_steps(src,steps,out,size):
    out=Path(out)
    with tempfile.TemporaryDirectory(dir=os.environ.get('VE_TMP')) as t:
        svg=write_svg(src,steps,Path(t)/'edit.svg');export(svg,Path(t)/'o.png',size or 1024)
        from PIL import Image
        Image.open(Path(t)/'o.png').convert('RGB').save(out)   # white page already composited; drop alpha like the other apps
    return out
