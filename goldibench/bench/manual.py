"""The app's manual as an environment resource (manual condition of run_agent.py --manual), for $BENCH_APP.

Like VisualSkill's skill directory (SKILL.md table of contents + one guide per topic, loaded on demand with load_topic),
but the content is the official manual verbatim, not a generated guide: one plain-text page per processing module
(all 84 pages of module-reference/processing-modules, not only the bench modules) and an INDEX listing every page with
the manual's own one-line description. The agent sees the INDEX and reads pages by name; nothing is truncated.
Pages are written once to manuals/darktable-5.6-text/.
use('gui') switches the process to the GUI edition (manuals/darktable-5.6-gui-text/): the same module pages plus the
manual's darkroom and user-interface chapters (module header, module controls / sliders, module groups, history ...),
topics named by their manual path (e.g. darkroom/processing-modules/module-controls).
Other apps, same interface (program edition only), the part of the manual that corresponds to the module reference:
  gimp         GIMP 3.0 manual (used for 3.2.6): every page reached from the Colors menu and the Filters chapters
               (manuals/gimp-3.0-text/, topic = page name, e.g. gimp-filter-vignette)
  rawtherapee  RawPedia at the pinned commit: every English page tagged 'Tool Description', tutorials excluded
               (manuals/rawpedia-text/, topic = page slug, e.g. vignetting-filter); Markdown kept, images dropped
use('visualskill_mm') / use('visualskill_text') instead installs VisualSkill's own published skill for the app
(XMHZZ2018/VisualSkills @582e6cc, skills/<app>-multimodal-stage2 or <app>-text-stage2; only GIMP has one among the bench
apps, written for GIMP 2.10): SKILL.md verbatim as read_skill, topic = guide folder, and load_topic returns guide.md with
its figures interleaved where the text cites them, as their tools/skill_server.py does (read_parts).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
import os,re
from bs4 import BeautifulSoup

DATA=gbpaths.DATA
SRC=DATA/'manuals/darktable/docs.darktable.org/usermanual/5.6/en/module-reference/processing-modules'
MANUAL=DATA/'manuals/darktable/docs.darktable.org/usermanual/5.6/en'
OUT=DATA/'manuals/darktable-5.6-text'
GUI_CHAPTERS=['darkroom','overview/user-interface']
EDITION='program'
APP=os.environ.get('BENCH_APP','darktable')
GIMP=DATA/'manuals/gimp3/docs.gimp.org/3.0/en'
RAWPEDIA=DATA/'manuals/rawtherapee/RawPedia/content'
if APP=='gimp':OUT=DATA/'manuals/gimp-3.0-text'
if APP=='rawtherapee':OUT=DATA/'manuals/rawpedia-text'
# Inkscape / Blender (added 2026-11-06 for the B-1 manual experiment): every page fetched for the generator, verbatim text
HTML_DIR={'inkscape':DATA/'manuals/inkscape-tavmjong','blender':DATA/'manuals/blender-4.5'}.get(APP)
if APP=='inkscape':OUT=DATA/'manuals/inkscape-tavmjong-text'
if APP=='blender':OUT=DATA/'manuals/blender-4.5-text'

VS=DATA/'sources/VisualSkills/skills'
FIG_REF=re.compile(r"`((?:fig\d+|ui-[^`\n]+)\.(?:png|jpe?g))`",re.I)   # as VisualSkills tools/skill_server.py

def use(edition):
    global OUT,EDITION,SKILL_NAME
    EDITION=edition
    if edition.startswith('visualskill'):
        OUT=VS/f'{APP}-{"multimodal" if edition=="visualskill_mm" else "text"}-stage2';SKILL_NAME=OUT.name
        assert OUT.is_dir(),f'VisualSkills has no skill for {APP}';return
    if APP!='darktable':
        assert edition=='manual',f'{APP} has no {edition} edition';return   # OUT already set for the app above
    OUT=DATA/('manuals/darktable-5.6-gui-text' if edition=='gui' else 'manuals/darktable-5.6-text')
# bench module id -> manual page (same as knowledge.PAGE)
PAGE={'exposure':'exposure','colisa':'contrast-brightness-saturation','levels':'levels','shadhi':'shadows-and-highlights',
      'colorbalancergb':'color-balance-rgb','splittoning':'split-toning','bilat':'local-contrast','sharpen':'sharpen',
      'vignette':'vignetting','hazeremoval':'haze-removal'}

def page_text(html):
    soup=BeautifulSoup(html,'html.parser')
    for t in soup(['script','style','nav','header','footer','aside']):t.decompose()
    node=soup.select_one('main') or soup.select_one('article') or soup.body
    for t in node(['a','em','strong','b','i','code','span','sub','sup']):t.unwrap()   # inline text stays on its line
    node.smooth()
    text=node.get_text('\n',strip=True).replace('🔗','')
    return re.sub(r'[ \t]+',' ',re.sub(r'\n\s*\n+','\n',text)).strip()

def description(text):
    """The manual's own 'description' line from the Technical information table."""
    lines=text.split('\n')
    for i,l in enumerate(lines[:-1]):
        if l.strip()=='description':return lines[i+1].strip()
    return ''

def _file(topic):return OUT/(topic.replace('/','__')+'.txt')

def first_sentence(text):
    """First sentence of the first prose paragraph after the title (RawPedia Markdown is hard-wrapped: join its lines)."""
    title,body=text.split('\n',1) if '\n' in text else (text,'')
    paras=[' '.join(p.split()) for p in re.split(r'\n\s*\n',body)] if '\n\n' in body else body.split('\n')
    for p in paras:
        if len(p)>40 and not p.startswith(('#','|','-','>','1.')):return re.split(r'(?<=[.!?])\s',p)[0][:200]
    return ''

def gimp_pages():
    """Pages linked from the Colors menu and from the Filters chapters (filters.html and its category pages)."""
    links=lambda p:[a['href'].split('#')[0] for a in BeautifulSoup((GIMP/p).read_text(errors='ignore'),'html.parser').select('a[href]')]
    menus=['gimp-colors-menu.html','filters.html'];seen=[]
    for m in menus:
        for h in links(m):
            if h in seen or h.startswith(('http','..')) or not (GIMP/h).exists():continue
            if re.match(r'(gimp-colors-.*-menu|filters-[a-z-]+)\.html$',h) and h not in menus:menus.append(h)
            if re.match(r'(gimp-filter-|gimp-tool-|gimp-colors-|gimp-layer-(white-balance|equalize)|gegl-|plug-in-|script-fu-|python-fu-)',h)\
               and not h.endswith('-menu.html'):seen.append(h)
    out=[]
    for h in seen:
        soup=BeautifulSoup((GIMP/h).read_text(errors='ignore'),'html.parser')
        for t in soup.select('div.navheader, div.navfooter, script, style'):t.decompose()
        text=page_text(str(soup));title=re.sub(r'^[\d.]+\s*','',text.split('\n')[0])
        paras=[' '.join(q.get_text(' ').split()) for q in soup.select('p') if not q.find_parent(class_=re.compile('figure|mediaobject|title'))]
        desc=next((re.split(r'(?<=[.!?])\s',q)[0][:200] for q in paras if len(q)>40),'')
        out.append((h.removesuffix('.html'),title,desc,text))
    return out

# Selective Editing (local_adjustments, 307k characters, ~75k tokens) alone would fill most of the 131k context and end the
# episode; it is a separate subsystem, not a bench tool. The longest darktable page is 47k characters.
SKIP_RAWPEDIA={'local_adjustments'}

def rawpedia_pages():
    out=[]
    for f in sorted(RAWPEDIA.rglob('*.md')):
        rel=f.relative_to(RAWPEDIA)
        if f.name.startswith('.') or re.search(r'\.[a-z]{2}\.md$',f.name) or f.name=='_index.md' or rel.parts[0]=='Tutorials':continue
        md=f.read_text(errors='ignore');m=re.match(r'---\n(.*?)\n---\n',md,re.S)
        if not m or "'Tool Description'" not in m.group(1) or 'REDIRECT' in md[m.end():][:200]:continue
        if rel.parts[0] in SKIP_RAWPEDIA:continue
        title=re.search(r'^title:\s*(.+)$',m.group(1),re.M).group(1).strip().strip('"\'')
        body=md[m.end():]
        body=re.sub(r'\{\{<.*?>\}\}','',body,flags=re.S)                        # Hugo shortcodes (images, figures)
        body=re.sub(r'!\[[^\]]*\]\([^)]*\)','',body)                             # Markdown images
        body=re.sub(r'\[([^\]]*)\]\([^)]*\)',r'\1',body)                           # links -> their text
        body=re.sub(r'<[^>]+>|__NOTOC__','',body);body=re.sub(r'\n\s*\n+','\n\n',body).strip()
        name=(rel.parent.name if f.name=='index.md' else f.stem)
        slug=re.sub(r'[^a-z0-9]+','-',name.lower()).strip('-')
        text=title+'\n'+body;out.append((slug,title,first_sentence(text),text))
    return out

def html_dir_pages():
    """Every fetched HTML page of the app's manual (Tavmjong Bah's Inkscape filter chapters, Blender 4.5 pages)."""
    out=[]
    for f in sorted(HTML_DIR.glob('*.html')):
        if f.name=='index.html':continue
        text=page_text(f.read_text(errors='ignore')).replace('\u00b6','');title=text.split('\n')[0][:120];desc=first_sentence(text)
        if title.startswith('Inkscape: Guide'):title,desc=desc.replace('Inkscape Filter Effects\u2014',''),''   # book title on every page
        out.append((f.stem.lower(),title,desc,text))
    return out

def build():
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    if APP!='darktable':
        pages_=gimp_pages() if APP=='gimp' else rawpedia_pages() if APP=='rawtherapee' else html_dir_pages()
        assert len({p for p,*_ in pages_})==len(pages_),'duplicate topic names'
        for name,title,desc,text in pages_:_file(name).write_text(text);rows.append((name,title,desc))
        (OUT/'INDEX.txt').write_text('\n'.join(f'- {p} ({t})'+(f': {d}' if d else '') for p,t,d in rows)+'\n');return
    pages=[(d.name,d) for d in sorted(SRC.iterdir()) if (d/'index.html').exists()]
    if EDITION=='gui':   # interface chapters first, then the module reference
        ui=[(str(f.parent.relative_to(MANUAL)),f.parent) for c in GUI_CHAPTERS for f in sorted((MANUAL/c).rglob('index.html'))]
        pages=ui+pages
    for name,d in pages:
        text=page_text((d/'index.html').read_text(errors='ignore'))
        _file(name).write_text(text);rows.append((name,text.split('\n')[0],description(text)))
    (OUT/'INDEX.txt').write_text('\n'.join(f'- {p} ({title})'+(f': {desc}' if desc else '') for p,title,desc in rows)+'\n')

def pages():
    if EDITION.startswith('visualskill'):return sorted(str(p.parent.relative_to(OUT)) for p in OUT.rglob('guide.md'))
    if not (OUT/'INDEX.txt').exists():build()
    return sorted(p.stem.replace('__','/') for p in OUT.glob('*.txt') if p.stem!='INDEX')

def index_text():
    pages();return (OUT/'INDEX.txt').read_text()

def read(name):
    if EDITION.startswith('visualskill'):return ''.join(x for x in read_parts(name) if isinstance(x,str))
    return _file(name).read_text()

def read_parts(name):
    """load_topic result as a list of text chunks and figure paths (VisualSkill: each figure right after the sentence
    citing it, uncited figures at the end; other editions: the page text only)."""
    if not EDITION.startswith('visualskill'):return [read(name)]
    folder=OUT/name;text=(folder/'guide.md').read_text();head=f'# {name}/guide.md\n\n'
    figs={f.name.lower():f for f in sorted(folder.iterdir()) if f.suffix.lower() in('.png','.jpg','.jpeg')} if EDITION=='visualskill_mm' else {}
    parts=[];cur=0;done=set()
    for m in FIG_REF.finditer(text):
        parts.append((head if cur==0 else '')+text[cur:m.end()]);cur=m.end();n=m.group(1).lower()
        if n in figs and n not in done:parts.append(figs[n]);done.add(n)
    if text[cur:] or cur==0:parts.append((head if cur==0 else '')+text[cur:])
    return parts+[f for n,f in figs.items() if n not in done]

# Skill interface, mirroring VisualSkill (skills/<app>-text-stage1/SKILL.md + load_topic / list_topics MCP tools).
SKILL_NAME={'darktable':'darktable-manual','gimp':'gimp-manual','rawtherapee':'rawtherapee-manual','inkscape':'inkscape-filters-manual',
            'blender':'blender-manual'}.get(APP)
SKILL_DESC={'darktable':'The darktable 5.6 user manual, processing-module reference (official text, verbatim). Consult it with load_topic.',
            'gimp':'The GIMP 3.0 user manual, Colors menu and Filters chapters (official text, verbatim). Consult it with load_topic.',
            'rawtherapee':'RawPedia, the official RawTherapee manual, tool descriptions (official text, verbatim). Consult it with load_topic.',
            'inkscape':'The Inkscape filter manual by Tavmjong Bah (filter chapters, verbatim). Consult it with load_topic.',
            'blender':'The Blender 4.5 manual pages for color management, lights, world, cameras and shaders (verbatim). Consult it with load_topic.'}.get(APP)
TITLE={'darktable':'# darktable 5.6 manual: processing modules','gimp':'# GIMP 3.0 manual: Colors and Filters',
       'rawtherapee':'# RawPedia (RawTherapee manual): tool descriptions','inkscape':'# Inkscape filters (Tavmjong Bah)',
       'blender':'# Blender 4.5 manual: color management, lights, world, cameras, shaders'}.get(APP)
def skill_desc():
    if EDITION.startswith('visualskill'):return re.search(r'^description:\s*"?(.*?)"?$',skill_md(),re.M).group(1)
    return SKILL_DESC if EDITION=='program' else ('The darktable 5.6 user manual: user interface, darkroom and processing-module '
                                                  'reference (official text, verbatim). Consult it with load_topic.')

def skill_md():
    if EDITION.startswith('visualskill'):return (OUT/'SKILL.md').read_text()
    title='# darktable 5.6 manual: user interface, darkroom and processing modules' if EDITION=='gui' else TITLE
    return (f'---\nname: {SKILL_NAME}\ndescription: "{skill_desc()}"\n---\n\n{title}\n\n'
            '## How to consult this skill\n\n'
            '- `load_topic(topic)` returns the chosen topic\'s manual page in one call.\n'
            '- `list_topics()` returns every topic name, one per line.\n\n'
            f'Each entry below has the form `- <topic> (<{"module" if APP=="darktable" else "page"} title>): <description>`; pass `<topic>` to load_topic. '
            'You may call load_topic at any step, not only at the start.\n\n## Topics\n\n'+index_text())

if __name__=='__main__':
    import sys
    if len(sys.argv)>1:use(sys.argv[1])
    build();print(len(pages()),'pages in',OUT)
