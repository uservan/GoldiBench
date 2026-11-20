"""B-2 real darktable tasks from PlayRaw (docs/paper-plan.md §3 B-2): render a program on top of a user's own XMP.

A task's source is a bundle (<set>/bundles/<task>.bundle.json): the raw file, the user's sidecar, and for every edit
module the user has enabled, the index of its final history entry and the user's full parameters. Rendering edits the
sidecar in place of regenerating it, so masks, blend modes, module order, other modules and the auto-preset flag stay
as the user wrote them: the final entry of each edit module gets the user's parameters with the agent-settable fields
(ops_darktable.OPS, DT_LIBRARY=playraw) replaced by the program's values, or by NEUTRAL when the program leaves the
module out (= START). A program module the user never used is appended as a new history entry with darktable's
defaults plus the program's fields. So the program = the user's values reproduces the user's render, and START is the
user's edit with every settable field at neutral.
"""
import json,re,subprocess,tempfile
from pathlib import Path
import dt_params

LI=re.compile(r'<rdf:li\b[^>]*?darktable:operation="[^"]*"[^>]*?/>',re.S)

def history(text):
    """(start, end) of the <darktable:history> block and its entries [(match, {attr: value})]."""
    a=text.index('<darktable:history>');b=text.index('</darktable:history>',a)
    return a,b,[(m,dict(re.findall(r'darktable:(\w+)="([^"]*)"',m.group(0)))) for m in LI.finditer(text,a,b)]

def history_end(text):
    m=re.search(r'darktable:history_end="(\d+)"',text);return int(m.group(1)) if m else None

def final_entries(text):
    """{(operation, multi_priority): (entry index, attrs)} of the active history (num < history_end)."""
    _,_,es=history(text);end=history_end(text);out={}
    for i,(_,a) in enumerate(es):
        if end is None or int(a.get('num',0))<end:out[(a['operation'],a.get('multi_priority','0'))]=(i,a)
    return out

def settable(op,values,ops,neutral):
    """Agent-settable fields of op: the program's values, NEUTRAL for fields the program leaves out."""
    fields=ops[op][2];return {f:values.get(f,neutral.get(op,{}).get(f)) for f in fields if f in values or f in neutral.get(op,{})}

def sidecar(bundle,steps,ops,neutral):
    """The user's sidecar with the program applied (steps: [(module, {field: value})])."""
    text=Path(bundle['xmp']).read_text(errors='ignore');a,b,es=history(text);prog=dict(steps)
    edits=[]   # (entry index, new li text)
    for op,e in bundle['edit'].items():
        vals={**e['params'],**settable(op,prog.get(op,{}),ops,neutral)}
        v,blob=dt_params.pack(op,vals);li=es[e['index']][0].group(0)   # packed in our layout (legacy ones converted)
        li=re.sub(r'darktable:params="[^"]*"',f'darktable:params="{blob}"',li);li=re.sub(r'darktable:modversion="\d+"',f'darktable:modversion="{v}"',li);li=re.sub(r'darktable:enabled="\d"','darktable:enabled="1"',li)
        edits.append((e['index'],li))
    for i,li in sorted(edits,reverse=True):
        m=es[i][0];text=text[:m.start()]+li+text[m.end():]
    new=[op for op in prog if op not in bundle['edit']]
    if new:
        end=history_end(text);lis=''
        for k,op in enumerate(new):
            v,blob=dt_params.pack(op,prog[op])   # pack() fills darktable's $DEFAULT for the other fields
            lis+=(f'<rdf:li darktable:num="{end+k}" darktable:operation="{op}" darktable:enabled="1" darktable:modversion="{v}" '
                  f'darktable:params="{blob}" darktable:multi_name="" darktable:multi_priority="0"/>')
        i=text.index('</rdf:Seq>',text.index('<darktable:history>'))
        text=text[:i]+lis+text[i:]
        text=re.sub(r'darktable:history_end="\d+"',f'darktable:history_end="{end+len(new)}"',text,count=1)
    return text

def render(bundle_path,steps,out,size,ops,neutral):
    bundle=json.loads(Path(bundle_path).read_text());Path(out).unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as t:
        side=Path(t)/'s.xmp';side.write_text(sidecar(bundle,steps,ops,neutral))
        dims=['--width',str(size),'--height',str(size)] if size else []
        r=subprocess.run([str(dt_params.DT),bundle['raw'],str(side),str(out),*dims,'--core','--configdir',str(Path(t)/'conf'),
                          '--library',':memory:'],capture_output=True,text=True,timeout=900)
        if r.returncode or not Path(out).exists():raise RuntimeError((r.stdout+r.stderr)[-800:])
    return out
