"""Scripted GUI replay of a program: the same clicks and keystrokes a person would use (search module, expand it, pick
the tab, right-click the slider, type the value, Return). Used to check that every task is reachable through the GUI
(oracle replay) and to calibrate gui_map.
"""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
import gui_map as G

def open_module(d,module):
    d.click(*G.CLEAR);time.sleep(0.4);d.click(*G.SEARCH);time.sleep(0.3);d.type(G.GUI[module][0]);time.sleep(1.0)
    d.click(*G.TOP_ROW);time.sleep(1.2)

def close_module(d):
    d.click(*G.TOP_ROW);time.sleep(0.6)

def set_value(d,y,text):
    """Right-click the slider at row y (opens the fine-tune popup), type, Return. Move away first so no tooltip covers it."""
    d.move(1000,870);time.sleep(0.3);d.move(G.SLIDER_X,y);time.sleep(0.3)
    d.xdo('mousedown',3);time.sleep(0.15);d.xdo('mouseup',3);time.sleep(0.6)
    for ch in text:d.key({'-':'minus','.':'period','+':'plus'}.get(ch,ch))
    d.key('Return');time.sleep(0.8)

def set_combo(d,y,text):
    """Click the dropdown row (opens its popup list), type the entry text (filters the list), Return."""
    d.move(1000,870);time.sleep(0.3);d.click(G.SLIDER_X,y);time.sleep(0.6);d.type(text);time.sleep(0.4)
    d.key('Return');time.sleep(0.8)

def fmt(v):
    return f'{v:.4f}'.rstrip('0').rstrip('.') if v!=int(v) else str(int(v))

def apply(d,program,fixed=None):
    """program {module: {field: program value}}; fixed adds fields that must be set to leave GUI defaults."""
    for m,params in program.items():
        open_module(d,m);tab=G.DEFAULT_TAB
        fields={**(fixed or {}).get(m,{}),**params}
        # default-tab fields first: after another tab is clicked the panel has scrolled (see gui_map.TABS)
        for f in sorted(fields,key=lambda f:(G.GUI[m][1][f][0] or G.DEFAULT_TAB)!=G.DEFAULT_TAB):
            t=G.GUI[m][1][f][0] or G.DEFAULT_TAB;y=G.GUI[m][1][f][2]
            if t!=tab:d.click(*G.TABS[m][t]);time.sleep(0.8);tab=t
            v=fields[f];v=v[0] if isinstance(v,list) else v
            if (m,f) in G.COMBO:set_combo(d,y,G.display(m,f,v))
            else:set_value(d,y,fmt(G.display(m,f,v)))
        if tab==G.DEFAULT_TAB:close_module(d)   # after a tab click the header has scrolled away; the next search hides it
