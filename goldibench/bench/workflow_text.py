"""Manual text the B-1 generator gives the LLM (docs/paper-plan.md §3 B-1 step 3: "asset + operation library + workflow
text from the manual"). Per app: one general workflow page, and for every library operation the official manual page
that documents it. Pages are plain text, whitespace-normalised and cut to a fixed length; a page shared by several
operations is included once. Sources (SOURCE.json in each directory):
  darktable 5.6 user manual, GIMP 3.0 manual, RawPedia (RawTherapee), Tavmjong Bah's Inkscape manual (filter chapters),
  Blender 4.5 manual.
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import html,os,re
from pathlib import Path
M=Path(str(gbpaths.DATA)+'/manuals')
PAGE_CHARS=1800; WORKFLOW_CHARS=3000

# operation -> manual page (path under M)
PAGES={
 'darktable':{'exposure':'darktable-5.6-text/exposure.txt','colisa':'darktable-5.6-text/contrast-brightness-saturation.txt',
   'levels':'darktable-5.6-text/levels.txt','shadhi':'darktable-5.6-text/shadows-and-highlights.txt',
   'colorbalancergb':'darktable-5.6-text/color-balance-rgb.txt','splittoning':'darktable-5.6-text/split-toning.txt',
   'bilat':'darktable-5.6-text/local-contrast.txt','sharpen':'darktable-5.6-text/sharpen.txt',
   'vignette':'darktable-5.6-text/vignetting.txt','hazeremoval':'darktable-5.6-text/haze-removal.txt'},
 'gimp':{'brightness_contrast':'gimp-3.0-text/gimp-tool-brightness-contrast.txt','exposure':'gimp-3.0-text/gimp-filter-exposure.txt',
   'color_temperature':'gimp-3.0-text/gimp-filter-color-temperature.txt','hue_saturation':'gimp-3.0-text/gimp-tool-hue-saturation.txt',
   'color_balance':'gimp-3.0-text/gimp-tool-color-balance.txt','levels':'gimp-3.0-text/gimp-tool-levels.txt',
   'shadows_highlights':'gimp-3.0-text/gimp-filter-shadows-highlights.txt','unsharp_mask':'gimp-3.0-text/gimp-filter-unsharp-mask.txt',
   'gaussian_blur':'gimp-3.0-text/gimp-filter-gaussian-blur.txt','vignette':'gimp-3.0-text/gimp-filter-vignette.txt',
   'softglow':'gimp-3.0-text/gimp-filter-softglow.txt'},
 'rawtherapee':{'exposure':'rawpedia-text/exposure.txt','lab':'rawpedia-text/lab-adjustments.txt',
   'shadows_highlights':'rawpedia-text/shadows-highlights.txt','vibrance':'rawpedia-text/vibrance.txt',
   'local_contrast':'rawpedia-text/local-contrast.txt','sharpening':'rawpedia-text/sharpening.txt',
   'white_balance':'rawpedia-text/white-balance.txt','dehaze':'rawpedia-text/haze-removal.txt',
   'vignette':'rawpedia-text/vignetting-filter.txt','soft_light':'rawpedia-text/soft-light.txt','color_toning':'rawpedia-text/color-toning.txt'},
 'inkscape':{'blur':'inkscape-tavmjong/Filters-Pixel.html','opacity':'inkscape-tavmjong/Filters-Compositing.html',
   'hue_rotate':'inkscape-tavmjong/Filters-Color.html','saturate':'inkscape-tavmjong/Filters-Color.html',
   'brightness':'inkscape-tavmjong/Filters-Color.html','contrast':'inkscape-tavmjong/Filters-Color.html',
   'gamma':'inkscape-tavmjong/Filters-Color.html','tint':'inkscape-tavmjong/Filters-Color.html',
   'posterize':'inkscape-tavmjong/Filters-Color.html','drop_shadow':'inkscape-tavmjong/Filters-Example-DropShadow.html',
   'roughen':'inkscape-tavmjong/Filters-ComplexExamples.html'},
 'blender':{'exposure':'blender-4.5/render_color_management.html','gamma':'blender-4.5/render_color_management.html',
   'white_balance':'blender-4.5/render_color_management.html','world':'blender-4.5/render_lights_world.html',
   'sun':'blender-4.5/render_lights_light_object.html','floor':'blender-4.5/render_shader_nodes_shader_principled.html',
   'haze':'blender-4.5/render_shader_nodes_shader_volume_principled.html'},
}
# For a page that documents several operations: the excerpt of that operation starts at its own section heading.
KEY={'blender':{'exposure':'Exposure','gamma':'Gamma','white_balance':'White Balance','sun':'Sun','floor':'Base Color',
                'haze':'Density','world':'Strength'},
     'inkscape':{'blur':'Gaussian Blur','hue_rotate':'Hue Rotate','saturate':'Saturate','brightness':'Component Transfer',
                 'contrast':'Component Transfer','gamma':'Gamma','posterize':'Discrete','tint':'Color Matrix','roughen':'Turbulence'}}
WORKFLOW={'darktable':'darktable/docs.darktable.org/usermanual/5.6/en/overview/workflow/process/index.html',
          'gimp':'gimp3/docs.gimp.org/3.0/en/tone-mapping-tutorial.html',
          'rawtherapee':'rawtherapee/RawPedia/content/getting_started/index.md',
          'inkscape':'inkscape-tavmjong/Filters-BasicUse.html',
          'blender':'blender-4.5/render_lights_world.html'}

def text(path,limit):
    p=M/path
    if p.is_dir():s='\n'.join(f.read_text(errors='ignore') for f in sorted(p.rglob('*.md')))
    else:s=p.read_text(encoding='latin-1' if p.suffix=='.html' and 'inkscape' in path else 'utf-8',errors='ignore')
    if p.suffix in('.html','.md') or p.is_dir():
        s=re.sub(r'(?is)<(script|style|nav|header|footer)\b.*?</\1>',' ',s)
        s=html.unescape(re.sub(r'<[^>]+>',' ',s))
        s=re.sub(r'(?m)^\s*[-+]{3}.*$|\{\{[^}]*\}\}|!\[[^\]]*\]\([^)]*\)','',s)   # Hugo front matter / shortcodes / images
    s=re.sub(r'\s+',' ',s).strip()
    for mark in ('Back to top Toggle Light / Dark / Auto color theme Toggle table of contents sidebar','Toggle table of contents sidebar'):
        if mark in s:s=s.split(mark,1)[1].strip();break
    return s[:limit]

def section(path,key,limit):
    s=text(path,10**6);i=s.lower().find(key.lower())
    return s[max(i,0):max(i,0)+limit]

def manual_block(app,ops_):
    """(workflow text, per-operation manual text) for the prompt, plus the pages used (provenance)."""
    used=[WORKFLOW[app]];seen={};parts=[]
    for m in ops_:
        p=PAGES[app][m];k=KEY.get(app,{}).get(m)
        if p not in used:used.append(p)
        if k and len(text(p,10**6))>2*PAGE_CHARS:parts.append(f'[{m}] {section(p,k,PAGE_CHARS//2)}');continue
        if p in seen:parts.append(f'[{m}] see the manual page quoted for {seen[p]}');continue
        seen[p]=m;parts.append(f'[{m}] {text(p,PAGE_CHARS)}')
    return text(WORKFLOW[app],WORKFLOW_CHARS),'\n\n'.join(parts),used

if __name__=='__main__':
    import sys
    app=sys.argv[1] if len(sys.argv)>1 else 'darktable'
    for a in ([app] if app!='all' else list(PAGES)):
        for m,p in PAGES[a].items():assert (M/p).exists(),(a,m,p)
        assert (M/WORKFLOW[a]).exists(),(a,WORKFLOW[a])
        w,b,u=manual_block(a,list(PAGES[a]))
        print(a,'workflow',len(w),'chars | ops',len(b),'chars |',len(u),'pages | sample:',w[:160].replace('\n',' '))
