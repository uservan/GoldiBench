"""Where each Inkscape bench operation lives in the Inkscape 1.4.4 GUI (app_envs.InkscapeDesktop, 1920x1080) and the
scripted replay of a program (oracle replay, C5). Measured on screenshots 2026-11-11.

A program is one filter on a group of the whole drawing (ops_inkscape.build): Edit > Select All in All Layers, Object >
Group, then Filters > Filter Editor: "+" (new filter), tick "Filter" (apply it to the selection), and add the program's
SVG filter primitives in order from the "Add effect" list. Primitives without an explicit input take the previous
result (SVG default), which is what the program does for every single-primitive operation. Drop shadow and roughen use
two inputs: the replay drags the input handle onto the right row (or onto the Source Graphic column), as a user wires
the Filter Editor. Values are user units (lengths = program value x L, L = 1 % of (page width + height) / 2).
Opacity is the group's opacity (Fill and Stroke, Opacity %). Combo boxes are set with the keyboard (open, arrows, Return).
The Filter Editor window is moved to (600, 80), 800 x 960, and its list / settings divider dragged to y=650 first.
"""
import time,xml.etree.ElementTree as ET,colorsys
import sys;from pathlib import Path;sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
import ops_inkscape as O

FE_MENU=(352,12);FE_ITEM=(398,62);WIN=(600,80,800,960);DIVIDER=((1000,297),(1000,650))
PLUS=(1338,163);FILTER_TICK=(619,162);ADD_ARROW=(1298,200)
ADD={'feGaussianBlur':(1141,310),'feOffset':(1115,342),'feComposite':(1281,405),'feMerge':(1116,437),'feColorMatrix':(1135,500),
     'feComponentTransfer':(1312,500),'feFlood':(1114,595),'feTurbulence':(1130,627),'feDisplacementMap':(1307,278)}
ROW0_TOP=223;ROW_H={1:23,2:44};TRI_X0=847;TRI_DX=16.2;SRC_GRAPHIC_X=1360;ROW_X=650
OPACITY=(1810,985)
# settings of the selected primitive (below the list)
BLUR=(1303,704);OFFSET={'dx':(1317,729),'dy':(1317,760)};FLOOD_OPACITY=(1335,742);COMPOSITE_OP=(1057,708)
CM_TYPE=(1057,708);CM_CELL_X=[747,783,819,855,891];CM_CELL_Y=[741,764,787,810]
CT_COMBO={'R':712,'G':761,'B':810};CT_X=1080;CT_FIELD_X=1325;CT_FIELD_DY=[35,65,95]
TURB_TYPE=(1057,707);TURB={'freq':(1306,742),'octaves':(1326,802),'seed':(1323,832)}
DISP={'scale':(1326,704),'x':(1065,737),'y':(1065,775)}
HUE_ANGLE=(1325,742)   # Color Matrix type Hue Rotate: its single value (measured by the replay check)

def fmt(v):
    s=f'{float(v):.5f}'.rstrip('0').rstrip('.');return '0' if s in ('-0','') else s

def unit(svg):
    x,y,w,h=O.page(ET.parse(svg).getroot());return (w+h)/2/100

def primitives(program,L):
    """[(primitive, settings, wiring)] in filter order; wiring: {'in'|'in2'|'add': row index of the source, -1 = SourceGraphic}."""
    out=[];prev=lambda:len(out)-1
    for m,v in program.items():
        if m=='opacity':continue
        cur=prev()   # result the operation reads (-1: SourceGraphic)
        if m=='blur':out.append(('feGaussianBlur',{'std':v.get('radius',0)*L},{}))
        elif m=='hue_rotate':out.append(('feColorMatrix',{'type':'hueRotate','angle':v.get('angle',0)%360},{}))   # the GUI accepts 0..360; -30.7 == 329.3
        elif m=='saturate':
            k=v.get('amount',1);rw,gw,bw=0.213,0.715,0.072
            mtx=[[rw+(1-rw)*k,gw-gw*k,bw-bw*k,0,0],[rw-rw*k,gw+(1-gw)*k,bw-bw*k,0,0],[rw-rw*k,gw-gw*k,bw+(1-bw)*k,0,0],[0,0,0,1,0]]
            out.append(('feColorMatrix',{'type':'matrix','matrix':mtx},{}))
        elif m=='tint':
            s=v.get('strength',0);cr,cg,cb=colorsys.hls_to_rgb(v.get('hue',0)/360,0.5,1.0);d=[1-s+s*c for c in (cr,cg,cb)]
            out.append(('feColorMatrix',{'type':'matrix','matrix':[[d[0],0,0,0,0],[0,d[1],0,0,0],[0,0,d[2],0,0],[0,0,0,1,0]]},{}))
        elif m=='brightness':out.append(('feComponentTransfer',{'func':'linear','vals':[1,v.get('offset',0)]},{}))
        elif m=='contrast':s=v.get('amount',1);out.append(('feComponentTransfer',{'func':'linear','vals':[s,0.5-0.5*s]},{}))
        elif m=='gamma':out.append(('feComponentTransfer',{'func':'gamma','vals':[1,v.get('exponent',1),0]},{}))
        elif m=='posterize':
            n=int(round(v.get('levels',4)));out.append(('feComponentTransfer',{'func':'discrete','table':' '.join(f'{k/(n-1):.4f}' for k in range(n))},{}))
        elif m=='drop_shadow':
            o=v.get('offset',0)*L;b=len(out)
            out+= [('feGaussianBlur',{'std':v.get('blur',0)*L},{}),('feOffset',{'dx':o,'dy':o},{}),('feFlood',{'opacity':v.get('opacity',0)},{}),
                   ('feComposite',{'op':'in'},{'in2':b+1}),('feMerge',{},{'nodes':[b+3,cur]})]   # composite in = flood (previous)
        elif m=='roughen':
            t=len(out);out+=[('feTurbulence',{'freq':1/(4*L),'octaves':3,'seed':7},{}),('feDisplacementMap',{'scale':v.get('scale',0)*L},{'in':cur,'in2':t})]
        else:raise ValueError(m)
    return out

def slots(p,wiring):
    """input slots the row shows once wired (a merge shows one empty slot below its nodes)"""
    if p in ('feDisplacementMap','feComposite'):return 2
    if p=='feMerge':return len(wiring.get('nodes',[]))+1
    return 1
def rows(prims):
    """(top y, height) of each row of the list (23 px per input slot, measured)."""
    y=ROW0_TOP;out=[]
    for p,_,w in prims:
        n=slots(p,w);h=ROW_H[1] if n==1 else ROW_H[2]+(n-2)*21;out.append((y,h));y+=h
    return out
TRI_RGB=(207,206,205)
def find_tri(d,y):
    """x of the input handle (a grey triangle) on screen line y of the list; None if none."""
    import numpy as np
    a=np.asarray(d.screenshot(),dtype=int)[y,600:1360];ok=(abs(a-np.array(TRI_RGB)).max(axis=1)<=8)
    runs=[];x=0
    while x<len(ok):
        if ok[x]:
            e=x
            while e<len(ok) and ok[e]:e+=1
            if e-x>=3:runs.append((x+e)//2+600)
            x=e
        else:x+=1
    return runs[-1] if runs else None
def slot_y(top,h,k):
    return top+h//2 if h==ROW_H[1] else top+11+21*k

def field(d,x,y,v):
    d.click(x,y);time.sleep(0.25);d.key('ctrl+a');d.type(fmt(v));d.key('Return');time.sleep(0.5)
def text(d,x,y,t):
    d.click(x,y);time.sleep(0.25);d.key('ctrl+a');d.type(t);d.key('Return');time.sleep(0.5)
def combo(d,x,y,steps):
    d.click(x,y);time.sleep(0.8)
    for _ in range(abs(steps)):d.key('Down' if steps>0 else 'Up');time.sleep(0.12)
    d.key('Return');time.sleep(0.8)
def drag(d,a,b,steps=6):
    """slow press-move-release: a quick xdotool drag left Inkscape's Filter Editor stuck mid-drag (X calls timed out)"""
    d.move(*a);time.sleep(0.3);d.xdo('mousedown',1);time.sleep(0.3)
    for k in range(1,steps+1):d.move(a[0]+(b[0]-a[0])*k/steps,a[1]+(b[1]-a[1])*k/steps);time.sleep(0.15)
    time.sleep(0.3);d.xdo('mouseup',1);time.sleep(0.8)

def replay(d,program,svg_src):
    L=unit(svg_src);prims=primitives(program,L)
    d.focus_main();d.key('ctrl+alt+a');time.sleep(0.6);d.key('ctrl+g');time.sleep(0.8)
    if 'opacity' in program:field(d,*OPACITY,100*program['opacity'].get('opacity',1))
    if not prims:return
    d.click(*FE_MENU);time.sleep(0.8);d.click(*FE_ITEM);time.sleep(2.5)
    w=d.xdo('search','--onlyvisible','--name','Filter Editor').split()[0];d.xdo('windowmove',w,WIN[0],WIN[1]);d.xdo('windowsize',w,WIN[2],WIN[3]);time.sleep(1)
    d.click(*PLUS);time.sleep(1.2);d.click(*FILTER_TICK);time.sleep(1.2);drag(d,*DIVIDER,steps=8)
    built=[]
    for i,(p,s,wiring) in enumerate(prims):
        if built:   # new effects are inserted after the selected row: select the last one first
            t,h=rows(built)[-1];d.click(ROW_X,t+h//2);time.sleep(0.6)
        d.click(*ADD_ARROW);time.sleep(0.9);d.click(*ADD[p]);time.sleep(1.3);built.append((p,s,{}))
        set_values(d,p,s)
        def target(k,y):
            if k<0:return (SRC_GRAPHIC_X,y)
            t,hh=rows(built)[k];return (ROW_X,t+hh//2)
        conns=[(0,wiring['in'])] if 'in' in wiring else []
        if 'in2' in wiring:conns.append((1,wiring['in2']))
        for k,src in conns+[(k,src) for k,src in enumerate(wiring.get('nodes',[]))]:
            if p=='feMerge':built[-1]=(p,s,{'nodes':[0]*k})   # k nodes so far: the free slot is slot k
            top,h=rows(built)[i];y=slot_y(top,h,k);x=find_tri(d,y)
            if x is None:raise RuntimeError(f'no input handle for {p} slot {k} at y={y}')
            drag(d,(x,y),target(src,y));time.sleep(0.4)
        built[-1]=(p,s,wiring)

def set_values(d,p,s):
    if p=='feGaussianBlur':field(d,*BLUR,s['std'])
    elif p=='feOffset':field(d,*OFFSET['dx'],s['dx']);field(d,*OFFSET['dy'],s['dy'])
    elif p=='feFlood':field(d,*FLOOD_OPACITY,s['opacity'])
    elif p=='feComposite':combo(d,*COMPOSITE_OP,1)   # Over -> In
    elif p=='feColorMatrix':
        if s['type']=='hueRotate':combo(d,*CM_TYPE,2);time.sleep(0.8);field(d,*HUE_ANGLE,s['angle'])
        else:
            for r_,row in enumerate(s['matrix']):
                for c_,v in enumerate(row):
                    if abs(v-(1.0 if r_==c_ else 0.0))<1e-9:continue
                    x,y=CM_CELL_X[c_],CM_CELL_Y[r_];d.click(x,y);time.sleep(0.4);d.click(x,y);time.sleep(0.4)
                    d.key('ctrl+a');d.type(fmt(v));d.key('Return');time.sleep(0.5)
    elif p=='feComponentTransfer':
        steps={'discrete':2,'linear':3,'gamma':4}[s['func']]
        for ch in ('B','G','R'):   # bottom first: an expanded channel only moves the channels below it
            y=CT_COMBO[ch];combo(d,CT_X,y,steps);time.sleep(1.0)   # the panel re-lays out after the type change
            if s['func']=='discrete':   # the first keystroke re-lays out the panel (only "0" kept, b016): type it again
                text(d,CT_FIELD_X,y+CT_FIELD_DY[0],s['table']);time.sleep(1.5);text(d,CT_FIELD_X,y+CT_FIELD_DY[0],s['table'])
            else:
                for k,v in enumerate(s['vals']):field(d,CT_FIELD_X,y+CT_FIELD_DY[k],v)
    elif p=='feTurbulence':
        combo(d,*TURB_TYPE,1)   # Turbulence -> Fractal Noise
        field(d,*TURB['freq'],s['freq']);field(d,*TURB['octaves'],s['octaves']);field(d,*TURB['seed'],s['seed'])
    elif p=='feDisplacementMap':
        field(d,*DISP['scale'],s['scale']);combo(d,*DISP['x'],-3);combo(d,*DISP['y'],-2)   # Alpha -> Red / Green
    elif p=='feMerge':pass

NAMES={'feGaussianBlur':'Gaussian Blur','feOffset':'Offset','feFlood':'Flood','feComposite':'Composite','feMerge':'Merge',
       'feColorMatrix':'Color Matrix','feComponentTransfer':'Component Transfer','feTurbulence':'Turbulence','feDisplacementMap':'Displacement Map'}
def l1_text(program,svg_src):
    L=unit(svg_src);prims=primitives(program,L);parts=['Edit > Select All in All Layers, then Object > Group']
    if 'opacity' in program:parts.append(f"Fill and Stroke: Opacity (%) = {fmt(100*program['opacity'].get('opacity',1))}")
    if prims:
        steps=[]
        for i,(p,s,w) in enumerate(prims):
            desc={'feGaussianBlur':lambda:f"standard deviation {fmt(s['std'])}",'feOffset':lambda:f"dx {fmt(s['dx'])}, dy {fmt(s['dy'])}",
                  'feFlood':lambda:f"black, opacity {fmt(s['opacity'])}",'feComposite':lambda:'operator In',
                  'feMerge':lambda:'','feColorMatrix':lambda:(f"type Hue Rotate, {fmt(s['angle'])} degrees" if s['type']=='hueRotate' else
                      'type Matrix, values (row by row) '+' | '.join(' '.join(fmt(x) for x in row) for row in s['matrix'])),
                  'feComponentTransfer':lambda:(f"R, G and B Discrete Values, table {s['table']}" if s['func']=='discrete' else
                      f"R, G and B {s['func'].capitalize()}, "+', '.join(f'{n} {fmt(x)}' for n,x in zip(('slope','intercept') if s['func']=='linear' else ('amplitude','exponent','offset'),s['vals']))),
                  'feTurbulence':lambda:f"type Fractal Noise, size (base frequency) {fmt(s['freq'])}, detail 3, seed 7",
                  'feDisplacementMap':lambda:f"scale {fmt(s['scale'])}, X displacement Red, Y displacement Green"}[p]()
            src=lambda k:'Source Graphic' if k<0 else f'effect {k+1}'
            wire=('; input 1 = '+src(w['in']) if 'in' in w else '')+('; input 2 = '+src(w['in2']) if 'in2' in w else '')+('; merge inputs = '+' then '.join(src(k) for k in w['nodes']) if 'nodes' in w else '')
            steps.append(f'{i+1}. {NAMES[p]}'+(f' ({desc})' if desc else '')+wire)
        parts.append('Filters > Filter Editor: new filter applied to the group, effects in this order: '+'; '.join(steps))
    return parts
