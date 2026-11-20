"""Scripted GIMP GUI replay of a program: the clicks and keystrokes a person would use (menu > filter, type each value
into its field, OK). Used for the oracle replay (every task reachable through the GUI) and to calibrate gimp_map.
"""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import gimp_map as G

FILTERS_SHIFT=25   # after the first filter of any menu, the Filters menu gains a "Recently Used" row above its submenus

def fmt(v,digits=4):
    s=f'{v:.{digits}f}'.rstrip('0').rstrip('.');return '0' if s in('-0','') else s

def dialog(d,main):
    """The filter dialog's window id, moved to DIALOG_AT; returns (id, x, y) as xdotool reports its position."""
    for _ in range(40):
        ws=[w for w in d.xdo('search','--onlyvisible','--name','.').split() if w!=main]
        ws=[w for w in ws if d.xdo('getwindowname',w) not in('GNU Image Manipulation Program','')]
        if ws:break
        time.sleep(0.25)
    else:raise RuntimeError('no filter dialog appeared')
    w=ws[-1];d.xdo('windowmove',w,*G.DIALOG_AT);time.sleep(0.6)
    geo=dict(l.strip().split(': ',1) for l in d.xdo('getwindowgeometry',w).split('\n')[1:] if ': ' in l)
    x,y=(int(v) for v in geo['Position'].split(' ')[0].split(','));return w,x,y

def open_filter(d,tool,filters_used=0):
    path=G.MENU[tool];shift=FILTERS_SHIFT if filters_used and path[0][0]==427 else 0
    for i,(x,y) in enumerate(path):
        y=y+shift if i>0 else y
        # hover a submenu row (a click on it toggles the submenu closed again), click the menu and the item
        if 0<i<len(path)-1:d.move(x,y);time.sleep(0.5);d.move(x+28,y);time.sleep(1.5)
        else:d.click(x,y);time.sleep(1.0)
    time.sleep(2.0)

def set_field(d,x,y,text):
    d.move(x,y);time.sleep(0.2);d.xdo('click','--repeat',3,'--delay',80,1);time.sleep(0.3)
    for ch in text:d.key({'-':'minus','.':'period'}.get(ch,ch))
    d.key('Tab');time.sleep(0.8)

def apply(d,program,shots=None):
    """program {tool: {field: program value}}, applied in order, one dialog each. shots: directory for a screenshot
    after each filter's dialog opens and after its OK (debugging)."""
    main=d.window();used=0
    for i,(tool,values) in enumerate(program.items()):
        open_filter(d,tool,used)
        if shots:d.screenshot().save(f'{shots}/{i}_{tool}_open.png')
        w,x,y=dialog(d,main)
        fields,ok=G.FIELDS[tool]
        for f,v in values.items():
            _,fx,fy,_=fields[f];set_field(d,x+fx,y+fy,fmt(G.shown(tool,f,v)))
        time.sleep(1.0);d.click(x+ok[0],y+ok[1]);time.sleep(2.5)
        if shots:d.screenshot().save(f'{shots}/{i}_{tool}_ok.png')
        used+=1
