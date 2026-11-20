"""Operation library of the app selected by $BENCH_APP (darktable = default, rawtherapee, gimp): which tools an agent
may use, which fields it may set, and their allowed ranges. Fields not listed keep the tool default. A program is
{tool: {field: value}}, one instance per tool. darktable and RawTherapee run tools in their own fixed pipeline order;
in GIMP (ORDERED) filters are applied in program order.

Per-app tables live in ops_<app>.py: PRODUCT, ORDERED, UNIT_WORD, OPS, FIXED, NEUTRAL, HUE_PAIRS, MIN_DE_LOCAL, DECIMALS,
render_steps(src, steps, out, size). Everything below is shared.
"""
from pathlib import Path
import importlib,os,sys
sys.path.insert(0,str(Path(__file__).parent))

APP=os.environ.get('BENCH_APP','darktable')
_lib=importlib.import_module(f'ops_{APP}')
PRODUCT,ORDERED,UNIT_WORD=_lib.PRODUCT,_lib.ORDERED,_lib.UNIT_WORD
OPS,FIXED,NEUTRAL,HUE_PAIRS,MIN_DE_LOCAL,DECIMALS=_lib.OPS,_lib.FIXED,_lib.NEUTRAL,_lib.HUE_PAIRS,_lib.MIN_DE_LOCAL,_lib.DECIMALS
V2_ANCHOR=getattr(_lib,'V2_ANCHOR',{})   # optional: V-2 scaling reference where it differs from NEUTRAL

def spec_text(modules=None):
    lines=[]
    for m,(name,desc,fields) in OPS.items():
        if modules and m not in modules:continue
        fs=', '.join(f'{f} [{lo} .. {hi}]{(" "+u) if u else ""}' if not isinstance(lo,tuple) else f'{f} {u}' for f,(lo,hi,u) in fields.items())
        lines.append(f'- {m} ("{name}"): {desc}. Fields: {fs}')
    return '\n'.join(lines)

def order_note():
    """How the app combines the steps of a program (shown to agents)."""
    if ORDERED:return (f'{PRODUCT} applies the {UNIT_WORD}s one after another in the order you list them; '
                       f'name each {UNIT_WORD} at most once.')
    return (f'{PRODUCT} applies {UNIT_WORD}s in its own fixed order (not your list order), one instance each, '
            f'so name each {UNIT_WORD} at most once.')

def schema(modules=None,exactly=None):
    """JSON schema for {"rationale": str, "steps": [{"module": m, "settings": [{"field": f, "value": v}, ...]}, ...]}.
    Lists, not objects: constrained decoding emits object properties in schema order, so with objects a field written
    out of order (e.g. highlights before shadows) can never be emitted and is silently dropped.
    settings needs minItems 1: without it GLM-5.3 often emitted "settings": [] while its rationale stated the values (v2)."""
    items=[]
    for m,(_,_,fields) in OPS.items():
        if modules and m not in modules:continue
        sets=[{'type':'object','additionalProperties':False,'required':['field','value'],
               'properties':{'field':{'const':f},'value':({'type':'array','items':{'type':'number'},'minItems':3,'maxItems':3}
                                                         if isinstance(lo,tuple) else {'type':'number'})}}
              for f,(lo,hi,_) in fields.items()]
        items.append({'type':'object','additionalProperties':False,'required':['module','settings'],
                      'properties':{'module':{'const':m},'settings':{'type':'array','items':{'anyOf':sets},'minItems':1,'maxItems':len(fields)}}})
    st={'type':'array','items':{'anyOf':items},'minItems':1}   # every task edits START; v3: GLM once returned no steps
    if exactly:st|={'minItems':exactly,'maxItems':exactly}
    return {'type':'object','additionalProperties':False,'required':['rationale','steps'],
            'properties':{'rationale':{'type':'string','maxLength':400},'steps':st}}

def from_steps(steps_list):
    """Model reply steps -> program {module: {field: value}}, plus violations (repeated module/field: the last one wins)."""
    prog={};viol=[]
    for s in steps_list or []:
        if not isinstance(s,dict):viol.append('bad step');continue
        m=s.get('module')
        if m in prog:viol.append(f'module {m} repeated')
        p=prog.setdefault(m,{})
        if not s.get('settings'):viol.append(f'{m} has no settings')
        for kv in s.get('settings') or []:
            if not isinstance(kv,dict):viol.append(f'{m} bad setting');continue
            if kv.get('field') in p:viol.append(f"{m}.{kv.get('field')} repeated")
            p[kv.get('field')]=kv.get('value')
    return prog,viol

def to_steps(program):
    """Program -> reply-format steps (fields in library order)."""
    return [{'module':m,'settings':[{'field':f,'value':p[f]} for f in OPS[m][2] if f in p]} for m,p in program.items()]

def clean(program,allowed=None):
    """Validate an agent's program: known modules only (and within `allowed`), known fields only, values clipped.
    Returns (clean_program, violations)."""
    out={};viol=[]
    for m,params in (program or {}).items():
        if m not in OPS or (allowed and m not in allowed):viol.append(f'module {m} not allowed');continue
        fields=OPS[m][2];p={}
        for f,v in (params or {}).items():
            if f not in fields:viol.append(f'{m}.{f} unknown');continue
            lo,hi,_=fields[f]
            try:
                if isinstance(lo,tuple):v=[min(max(float(x),a),b) for x,a,b in zip(v,lo,hi)];v=sorted(v)
                else:v=min(max(float(v),lo),hi)
            except (TypeError,ValueError):viol.append(f'{m}.{f} bad value');continue
            p[f]=v
        out[m]=p
    return quantize(out),viol

def quantize(program):
    """Round fields to the decimals the app stores (DECIMALS; empty for darktable, so programs are unchanged)."""
    return {m:{f:(round(v,DECIMALS[m][f]) if f in DECIMALS.get(m,{}) else v) for f,v in p.items()} for m,p in program.items()}

def steps(program):
    """Program -> app steps [(tool, {field: value})] (FIXED + given fields; the rest keep the tool default)."""
    return [(m,{**FIXED.get(m,{}),**p}) for m,p in program.items()]

def render(src,program,out,size=1024):
    return _lib.render_steps(src,steps(program),out,size)

if __name__=='__main__':print(spec_text())
