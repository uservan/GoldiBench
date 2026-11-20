"""Where each Blender bench field lives in the Blender 4.5.15 GUI (app_envs.BlenderDesktop, 1920x1080) and the scripted
replay of a program (oracle replay, C5). Measured on screenshots 2026-11-11.

The replay works like a user who maximises the Properties editor (Ctrl+Space over it) so every panel fits on screen,
and types each value into its field (a click on a number field without dragging starts text entry; Ctrl+A, value,
Return). The tab column of the Properties editor depends on the active object, so the program is applied in an order
that keeps the active object known: render / world settings, the ground (active in START), then the haze sphere and
the sun (each is active right after it is added). Objects are added in the 3D viewport with Shift+A and its search.
Values are the ones blender_bench.apply() sets (ops_blender): the GUI shows them unchanged (HSV of the ground colour:
Blender's picker shows the scene-linear HSV the program uses; angles in degrees).
"""
import math,time
MAX_AT=(1750,700);VIEW_AT=(900,600);VP=(700,500)
TAB={'render':(16,112),'world':(16,229),'object':(16,266),'material':(16,440),'light':(15,352)}
CM_HEADER=(112,900)           # Render tab, Color Management title (START: Sampling open above it)
CM={'ev':(1602,560),'gamma':(1602,583)};WB_BOX=(80,698);WB_ARROW=(64,698);WB={'temperature':(1346,728),'tint':(1346,752)}
WORLD_COLOR_ARROW=(54,238);WORLD_VECTOR_ARROW=(55,421);WORLD_ROT_Z=(1342,608);WORLD_STRENGTH=(1342,703)
BASE_COLOR=(1342,327);HSV={'hue':(1780,564),'saturation':(1780,584),'value':(1780,605)};ROUGHNESS=(1342,380)
F9={'segments':(922,550),'rings':(922,573),'radius':(922,597),'x':(922,666),'y':(922,687),'z':(922,708)}
MAT_NEW=(1000,196);SURFACE=(1340,290);SURFACE_REMOVE=(1000,337);VOLUME_HEADER=(81,324);VOLUME=(1340,355)
PRINCIPLED_VOLUME=(845,679);DENSITY=(1342,444)
OBJ_ROT={'x':(1320,241),'y':(1320,262),'z':(1320,283)};LIGHT={'strength':(1332,288),'angle':(1332,370)}
ORDER=['exposure','gamma','white_balance','world','floor','haze','sun']

def fmt(v):
    s=f'{float(v):.5f}'.rstrip('0').rstrip('.');return '0' if s in ('-0','') else s

def hover_click(d,x,y,mods=None):
    d.move(x,y);time.sleep(0.35)
    if mods:d.xdo('keydown',mods,'click','1','keyup',mods)
    else:d.xdo('click','1')
    time.sleep(0.8)
def field(d,x,y,v):
    hover_click(d,x,y);d.key('ctrl+a');d.type(fmt(v));d.key('Return');time.sleep(0.6)
def maximize(d):d.move(*MAX_AT);time.sleep(0.3);d.key('ctrl+space');time.sleep(1.2)
def restore(d):d.move(*VIEW_AT);time.sleep(0.3);d.key('ctrl+space');time.sleep(1.2)
def add(d,what):
    d.move(*VP);time.sleep(0.3);d.key('shift+a');time.sleep(1.0);d.type(what);time.sleep(1.0);d.key('Return');time.sleep(1.5)

def world_z(state):
    r=state.get('world:rotation') or [0,0,0];return math.degrees(float(r[2]))
def camera(state):return state['other:camera'][0]

def gui_values(program,state):
    """{tool: [(GUI field, value)]} in the replay's order: what L1 states."""
    out={}
    for tool in ORDER:
        if tool not in program:continue
        f=program[tool]
        if tool=='exposure':out[tool]=[('Exposure',f.get('ev',0.0))]
        elif tool=='gamma':out[tool]=[('Gamma',f.get('gamma',1.0))]
        elif tool=='white_balance':out[tool]=[('Temperature',f.get('temperature',6500.0)),('Tint',f.get('tint',10.0))]
        elif tool=='world':out[tool]=[('Strength',f.get('strength',1.0)),('Rotation Z',round(world_z(state)+f.get('rotation',0.0),3))]
        elif tool=='floor':out[tool]=[('Hue',f.get('hue',0.0)),('Saturation',f.get('saturation',0.0)),('Value',f.get('value',0.35)),('Roughness',f.get('roughness',0.8))]
        elif tool=='haze':
            c=camera(state);out[tool]=[('Segments',64),('Rings',32),('Radius',30),('Location X',c[0]),('Location Y',c[1]),('Location Z',c[2]),('Density',f.get('density',0.0))]
        elif tool=='sun':out[tool]=[('Rotation X',90-f.get('elevation',45.0)),('Rotation Y',0),('Rotation Z',f.get('azimuth',0.0)),('Strength',f.get('strength',0.0)),('Angle',2)]
    return out

def replay(d,program,state):
    v={t:dict(x) for t,x in gui_values(program,state).items()}
    if {'exposure','gamma','white_balance'}&set(v):
        maximize(d);hover_click(d,*TAB['render']);hover_click(d,*CM_HEADER,mods='ctrl')
        if 'exposure' in v:field(d,*CM['ev'],v['exposure']['Exposure'])
        if 'gamma' in v:field(d,*CM['gamma'],v['gamma']['Gamma'])
        if 'white_balance' in v:
            hover_click(d,*WB_BOX);hover_click(d,*WB_ARROW)
            field(d,*WB['temperature'],v['white_balance']['Temperature']);field(d,*WB['tint'],v['white_balance']['Tint'])
        restore(d)
    if 'world' in v:
        maximize(d);hover_click(d,*TAB['world']);hover_click(d,*WORLD_COLOR_ARROW);hover_click(d,*WORLD_VECTOR_ARROW)
        field(d,*WORLD_ROT_Z,v['world']['Rotation Z']);field(d,*WORLD_STRENGTH,v['world']['Strength']);restore(d)
    if 'floor' in v:   # the ground is the active object in START
        maximize(d);hover_click(d,*TAB['material']);hover_click(d,*BASE_COLOR)
        for k in ('hue','saturation','value'):field(d,*HSV[k],v['floor'][k.capitalize()])
        d.move(900,1000);time.sleep(0.8)   # leaving the picker closes it
        field(d,*ROUGHNESS,v['floor']['Roughness']);restore(d)
    if 'haze' in v:
        h=v['haze'];add(d,'uv sphere');d.move(*VP);time.sleep(0.3);d.key('F9');time.sleep(1.2)
        for k,lab in (('segments','Segments'),('rings','Rings'),('radius','Radius'),('x','Location X'),('y','Location Y'),('z','Location Z')):
            field(d,*F9[k],h[lab])
        d.move(1300,900);time.sleep(0.8)
        maximize(d);hover_click(d,*TAB['material']);hover_click(d,*MAT_NEW);hover_click(d,*SURFACE);hover_click(d,*SURFACE_REMOVE)
        hover_click(d,*VOLUME_HEADER);hover_click(d,*VOLUME);hover_click(d,*PRINCIPLED_VOLUME);field(d,*DENSITY,h['Density']);restore(d)
    if 'sun' in v:
        s=v['sun'];add(d,'sun');maximize(d);hover_click(d,*TAB['object'])
        for k in ('x','y','z'):field(d,*OBJ_ROT[k],s[f'Rotation {k.upper()}'])
        hover_click(d,*TAB['light']);field(d,*LIGHT['strength'],s['Strength']);field(d,*LIGHT['angle'],s['Angle']);restore(d)

PATH={'exposure':'Render Properties > Color Management: ','gamma':'Render Properties > Color Management: ',
      'white_balance':'Render Properties > Color Management > White Balance (tick it): ',
      'world':'World Properties > Surface (Background Strength; Color > Vector > Mapping Rotation Z, degrees): ',
      'floor':'the ground plane (bench_ground) > Material Properties > Principled BSDF (Base Color in the HSV tab of the colour picker): ',
      'haze':'Add > Mesh > UV Sphere (Adjust Last Operation: segments, rings, radius, location), then Material Properties: New, Surface = None (Remove), Volume = Principled Volume: ',
      'sun':'Add > Light > Sun, then Object Properties (rotation, degrees) and Object Data Properties (Strength, Angle in degrees): '}
def l1_text(program,state):
    return [PATH[t]+', '.join(f'{k} = {fmt(x)}' for k,x in vals) for t,vals in gui_values(program,state).items()]
