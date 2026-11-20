"""Where each bench field lives in the darktable 5.6.2 GUI (1920x1080 desktop.py layout) and how its displayed value
relates to the program value.

Each module is reached by typing its name in the module search box; the single match is then the top row (y=345) and
clicking it expands the module. Slider rows are fixed y positions after that (measured on screenshots); a right click on
the slider opens darktable's fine-tune popup, where typed digits + Return set the value in DISPLAY units.
display = scale * program + offset (the 4th entry is scale, or (scale, offset)), checked by calibrate.py: type a display
value, decode what darktable stored in the XMP.

colisa and levels are not here: both are deprecated in darktable 5.6 and cannot be added to a new edit from the GUI
(src/libs/modulegroups.c hides deprecated modules unless already enabled; the deprecated group is compiled out).
"""
SEARCH=(1720,312);CLEAR=(1893,312);TOP_ROW=(1640,345);SLIDER_X=1700
# Clicking a tab focuses the notebook and GTK scrolls the panel so the tabs sit at its top (41 px up for color balance rgb):
# 4-ways rows are measured in that scrolled state. 'master' is the tab shown on expand and is never clicked.
TABS={'colorbalancergb':{'4 ways':(1723,384)}};DEFAULT_TAB='master'
# module -> (search text, {field: (tab or None, label shown in GUI, y of slider bar, scale)})
GUI={
 'exposure':('exposure',{'exposure':(None,'exposure',443,1.0)}),
 'shadhi':('shadows and highlights',{'shadows':(None,'shadows',393,1.0),'highlights':(None,'highlights',431,1.0)}),
 'colorbalancergb':('color balance rgb',{
     'vibrance':('master','global vibrance',465,100.0),'contrast':('master','contrast',503,100.0),
     'saturation_global':('master','global saturation',753,100.0),
     'global_H':('4 ways','global offset: hue',454,1.0),'global_C':('4 ways','global offset: chroma',492,100.0),
     'shadows_H':('4 ways','shadows lift: hue',598,1.0),'shadows_C':('4 ways','shadows lift: chroma',636,100.0),
     'highlights_H':('4 ways','highlights gain: hue',742,1.0),'highlights_C':('4 ways','highlights gain: chroma',780,100.0)}),
 'splittoning':('split-toning',{'shadow_hue':(None,'shadows: hue',423,360.0),'shadow_saturation':(None,'shadows: saturation',461,1.0),
     'highlight_hue':(None,'highlights: hue',529,360.0),'highlight_saturation':(None,'highlights: saturation',567,1.0),
     'balance':(None,'balance',635,(-100.0,100.0))}),
 'bilat':('local contrast',{'mode':(None,'mode',383,1.0),'detail':(None,'detail',418,(100.0,100.0))}),
 'sharpen':('sharpen',{'radius':(None,'radius',393,1.0),'amount':(None,'amount',431,1.0)}),
 'vignette':('vignetting',{'scale':(None,'fall-off start',393,1.0),'brightness':(None,'brightness',469,1.0),'saturation':(None,'saturation',507,1.0)}),
 'hazeremoval':('haze removal',{'strength':(None,'strength',393,1.0)}),
}
# dropdowns (bauhaus combobox): program value -> entry text; the replay clicks the row, types the text, Return (B-1, 2026-11-02:
# its local contrast renders in bilateral-grid mode, the GUI opens in local laplacian; B-1 vignette fixes saturation 0)
COMBO={('bilat','mode'):{0:'bilateral grid',1:'local laplacian filter'}}
# unit printed after the value in the GUI (none for plain numbers)
# DT_GUI_DY shifts every y above by a constant: the right panel's vertical position depends on the node's rendering
# environment (after the 2026-11-02 restart it sat 19 px higher than when these rows were measured). Checked by replaying
# bench_gui1, whose tasks all passed with the original rows.
import os as _os
_DY=int(_os.environ.get('DT_GUI_DY','0'))
if _DY:
    SEARCH=(SEARCH[0],SEARCH[1]+_DY);CLEAR=(CLEAR[0],CLEAR[1]+_DY);TOP_ROW=(TOP_ROW[0],TOP_ROW[1]+_DY)
    TABS={m:{t:(x,y+_DY) for t,(x,y) in v.items()} for m,v in TABS.items()}
    GUI={m:(n,{f:(t,l,y+_DY,k) for f,(t,l,y,k) in fs.items()}) for m,(n,fs) in GUI.items()}
UNIT={('exposure','exposure'):' EV',('bilat','detail'):'%',('vignette','scale'):'%',('splittoning','shadow_hue'):'°',
      ('splittoning','highlight_hue'):'°',**{('colorbalancergb',f):('°' if f.endswith('_H') else '%') for f in
      ('vibrance','contrast','saturation_global','global_H','global_C','shadows_H','shadows_C','highlights_H','highlights_C')}}

def affine(module,field):
    k=GUI[module][1][field][3];return k if isinstance(k,tuple) else (k,0.0)

def display(module,field,value):
    if (module,field) in COMBO:return COMBO[(module,field)][int(value)]
    a,b=affine(module,field);return a*value+b

def program(module,field,shown):
    a,b=affine(module,field);return (shown-b)/a

def label(module,field):
    tab,lab,_,_=GUI[module][1][field];return (f'{tab} tab > ' if tab else '')+lab
