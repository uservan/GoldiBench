"""Where each RawTherapee bench field lives in the RawTherapee 5.13 GUI (app_envs.RawTherapeeDesktop, 1920x1080) and the
scripted replay of a program (oracle replay, C5). Measured on screenshots 2026-11-11.

Every tool sits in a tab of the right panel (icons at y=105); its panel is expanded by clicking its title and collapsed
again afterwards, so the other titles of the tab never move. Each field has a spin entry right of its label: the replay
triple-clicks it, types the value (display value = pp3 value: RawTherapee shows the stored number) and presses Return.
"""
import time
TABS={'exposure':1557,'detail':1598,'color':1640};TAB_Y=105
# tool -> (tab, y of the panel title, GUI name, {field: (GUI label, entry x, entry y with the panel expanded)})
GUI={
 'exposure':('exposure',144,'Exposure',{'compensation':('Exposure compensation',1828,342),'contrast':('Contrast',1838,602),
                                        'saturation':('Saturation',1838,644)}),
 'shadows_highlights':('exposure',175,'Shadows/Highlights',{'highlights':('Highlights',1835,246),'shadows':('Shadows',1835,338)}),
 'vignette':('exposure',299,'Vignette Filter',{'strength':('Strength',1830,331),'feather':('Feather',1835,373),'roundness':('Roundness',1835,415)}),
 'lab':('exposure',361,'L*a*b* Adjustments',{'brightness':('Lightness',1838,393),'chromaticity':('Chromaticity',1838,477)}),
 'sharpening':('detail',175,'Sharpening',{'radius':('Radius',1830,336),'amount':('Amount',1830,436)}),
 'local_contrast':('detail',206,'Local Contrast',{'radius':('Radius',1828,238),'amount':('Amount',1828,280)}),
 'dehaze':('detail',423,'Haze Removal',{'strength':('Strength',1835,455)}),
 'white_balance':('color',144,'White Balance',{'temperature':('Temperature',1830,268),'green':('Tint',1830,310)}),
 'vibrance':('color',206,'Vibrance',{'saturated':('Saturated tones',1838,238),'pastels':('Pastel tones',1838,280)}),
 'soft_light':('color',392,'Soft Light',{'strength':('Strength',1830,424)}),
}
ALWAYS_ON={'exposure','white_balance'}   # no on/off switch; every other tool is switched on by the power icon left of its title
POWER_X=1547
VIB_LINK=(1550,441)   # "Link pastel and saturated tones" (ticked by default: Saturated tones is greyed out)
PANEL_X=1650

# Color Toning, method "L*a*b* color correction grid": no entries; two points (shadows, highlights) start together in the
# centre of the 8x8 grid and are dragged. Grid edges = +-1 (pp3 stores x 12000); x = a (left green, right red),
# y = b (bottom blue, top yellow). The method combo and its "L*a*b* color correction grid" row, measured 2026-11-11.
CT=('color',454,'Color Toning');CT_METHOD=(1730,490);CT_GRID_ITEM=(1690,466)
CT_CENTER=(1707,679);CT_HALF=(162.5,162.0)
CT_FIRST='highlights'   # which point a drag from the centre picks up first (set by the replay check)
def ct_xy(a,b):return round(CT_CENTER[0]+a*CT_HALF[0]),round(CT_CENTER[1]-b*CT_HALF[1])

def fmt(v):
    s=f'{float(v):.4f}'.rstrip('0').rstrip('.');return '0' if s in ('-0','') else s

def set_field(d,x,y,v):
    d.click(x,y,1,3);time.sleep(0.25);d.key('ctrl+a');d.type(fmt(v));d.key('Return');time.sleep(0.6)

def replay(d,program):
    """Types the program into the GUI like a user: tab, expand the tool, each value into its entry, collapse."""
    for tool,vals in program.items():
        if tool=='color_toning':
            tab,ty,_=CT;d.click(TABS[tab],TAB_Y);time.sleep(0.8);d.click(POWER_X,ty);time.sleep(0.8);d.click(PANEL_X,ty);time.sleep(1.2)
            d.click(*CT_METHOD);time.sleep(1.0);d.click(*CT_GRID_ITEM);time.sleep(1.5)
            order=[CT_FIRST,'shadows' if CT_FIRST=='highlights' else 'highlights']
            for pt in order:
                a,b=vals.get(f'{pt}_a',0.0),vals.get(f'{pt}_b',0.0)
                if a or b:d.drag(*CT_CENTER,*ct_xy(a,b));time.sleep(1.0)
                else:order=order   # a point left in the centre is already (0, 0)
            d.click(PANEL_X,ty);time.sleep(0.8);continue
        tab,ty,_,fields=GUI[tool]
        d.click(TABS[tab],TAB_Y);time.sleep(0.8)
        if tool not in ALWAYS_ON:d.click(POWER_X,ty);time.sleep(0.8)
        d.click(PANEL_X,ty);time.sleep(1.2)
        if tool=='vibrance' and 'saturated' in vals:d.click(*VIB_LINK);time.sleep(0.5)
        for f,v in vals.items():
            _,x,y=fields[f];set_field(d,x,y,v)
        d.click(PANEL_X,ty);time.sleep(0.8)

def l1_text(program):
    parts=[]
    for tool,vals in program.items():
        if tool=='color_toning':
            parts.append('Color Toning (switch it on; Method = L*a*b* color correction grid; drag the two points of the grid, '
                         'whose edges are -1 and +1, a left to right, b bottom to top): '+
                         ', '.join(f'{pt} point at a = {fmt(vals.get(pt+"_a",0))}, b = {fmt(vals.get(pt+"_b",0))}' for pt in ('shadows','highlights')))
            continue
        tab,_,name,fields=GUI[tool]
        extra=' (untick "Link pastel and saturated tones")' if tool=='vibrance' and 'saturated' in vals else ''
        on='' if tool in ALWAYS_ON else ' (switch it on)'
        parts.append(f'{name}{on}{extra}: '+', '.join(f'{fields[f][0]} = {fmt(v)}' for f,v in vals.items()))
    return parts
