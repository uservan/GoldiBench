"""darktable 5.6.2 module parameters from Python: parse each module's params struct from the pinned source,
pack values into the binary blob darktable stores in XMP, write a sidecar and render with darktable-cli.

Only fixed-size scalar fields and fixed arrays of them are supported (enough for exposure, sharpen, vignette, ...).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
import base64,os,re,struct,subprocess,tempfile,zlib

LOCAL=Path(os.environ.get('VE_LOCAL',str(gbpaths.LOCAL)))
DT=LOCAL/'apps/darktable-5.6.2/squashfs-root/usr/bin/darktable-cli'
SRC=LOCAL/'apps/darktable-src/src/iop'
# C type -> struct format; enums and gboolean are 32-bit ints.
FMT={'float':'f','int':'i','int32_t':'i','uint32_t':'I','unsigned int':'I','gboolean':'i','double':'d'}

_ALL=None
def _sources():
    """Shared headers only: another module's .c may define a different type under the same name."""
    global _ALL
    if _ALL is None:_ALL='\n'.join(p.read_text(errors='ignore') for p in SRC.parent.rglob('*.h'))
    return _ALL

def _struct_body(ctype,text):
    """Body of `typedef struct [name] { ... } ctype;`, named or anonymous."""
    end=re.search(r'\}\s*'+ctype+r'\s*;',text)
    if not end:return None
    start=text.rfind('typedef struct',0,end.start())
    return text[text.index('{',start)+1:end.start()] if start>=0 else None

def _dim(tok,text):
    """Array dimension: a number, a #define'd constant, or an enum constant (explicit or by position)."""
    if tok.isdigit():return int(tok)
    for src in (text,_sources()):
        m=re.search(r'#define\s+'+tok+r'\s+\(?\s*(\d+)\s*\)?',src) or re.search(r'\b'+tok+r'\s*=\s*(\d+)\s*[,}]',src)
        if m:return int(m.group(1))
        e=re.search(r'enum\s*\w*\s*\{([^}]*\b'+tok+r'\b[^}]*)\}',src)
        if e:
            names=[re.sub(r'//.*|/\*.*?\*/','',x,flags=re.S).strip().split('=')[0].strip() for x in e.group(1).split(',')]
            names=[n for n in names if n]
            if tok in names and not re.search(r'=',e.group(1)):return names.index(tok)
    raise ValueError(f'unknown array size {tok}')

def _normalise(body):
    """Block comments -> line comments on one line; declarations split over lines -> one line."""
    body=re.sub(r'/\*(.*?)\*/',lambda m:'//'+m.group(1).replace('\n',' ')+'\n',body,flags=re.S)
    out=[];pending=''
    for line in body.splitlines():
        code,_,comment=line.partition('//')
        if not code.strip() and not pending:continue
        pending+=' '+code.strip();cm=comment
        if pending.rstrip().endswith(';'):out.append(pending.strip()+(' //'+cm if cm else ''));pending=''
    return '\n'.join(out)

def _fields(body,where,text):
    """Flatten a struct body into [(field, fmt, count, default)]; nested typedef structs are expanded.
    Any declaration that cannot be parsed raises: a skipped field would silently corrupt the blob layout."""
    fields=[]
    for line in _normalise(body).splitlines():
        code=re.sub(r'//.*','',line).strip()
        if not code:continue
        m=re.match(r'([A-Za-z_][\w ]*?)\s+(\w+)((?:\s*\[\s*\w+\s*\])*)\s*;$',code)
        if not m:raise ValueError(f'{where}: cannot parse declaration {code!r}')
        comment=line[line.find('//'):] if '//' in line else ''
        ctype,fname=m.group(1).strip(),m.group(2)
        count=1
        for tok in re.findall(r'\[\s*(\w+)\s*\]',m.group(3)):count*=_dim(tok,text)
        d=re.search(r'\$DEFAULT:\s*([^\s$]+)',comment);default=d.group(1) if d else '0'
        if ctype in FMT:fields.append((fname,FMT[ctype],count,default));continue
        if re.search(r'typedef enum '+ctype+r'\b',text) or re.search(r'typedef enum '+ctype+r'\b',_sources()):
            fields.append((fname,'i',count,default));continue   # C enums are 32-bit ints
        sub=_struct_body(ctype,text) or _struct_body(ctype,_sources())
        if sub is None:raise ValueError(f'{where}.{fname}: unknown type {ctype}')
        for _ in range(count):fields+=[(f'{fname}.{f}',fm,c,df) for f,fm,c,df in _fields(sub,f'{where}.{fname}',text)]
    return fields

def module(name):
    """Return (modversion, [(field, fmt, count, default)]) parsed from src/iop/<name>.c."""
    text=(SRC/f'{name}.c').read_text()
    intro=re.search(r'DT_MODULE_INTROSPECTION\((\d+),\s*(\w+)\)',text)
    version=int(intro.group(1))
    body=_struct_body(intro.group(2),text)   # usually dt_iop_<name>_params_t; toneequal's is dt_iop_toneequalizer_params_t
    if body is None:raise ValueError(f'{name}: params struct not found')
    return version,_fields(body,name,text)

# Until 2026-10-24 symbolic $DEFAULTs (enum names, #define'd flags) were packed as 0. Only shadhi has nonzero ones
# (shadhi_algo SHADHI_ALGO_BILATERAL = 1, flags UNBOUND_DEFAULT = 127), so bench_pilot / bench_pilot2 targets with
# shadows and highlights used the gaussian filter and flags 0, unlike the GUI default. LEGACY_SYMBOLS=1 reproduces that.
LEGACY_SYMBOLS=os.environ.get('LEGACY_SYMBOLS')=='1'

def symbol(tok,text):
    """Value of an enum constant or #define'd integer expression named tok (module source first, then shared headers)."""
    for src in (text,_sources()):
        m=re.search(r'#define\s+'+tok+r'\b((?:[^\n]*\\\n)*[^\n]*)',src)
        if m:
            expr=re.sub(r'/\*.*?\*/|//.*','',m.group(1).replace('\\\n',' '),flags=re.S)
            expr=re.sub(r'\b[A-Za-z_]\w*\b',lambda n:str(symbol(n.group(0),text)),expr)
            if not re.fullmatch(r'[\d\s()|&<>+\-~^]*',expr):raise ValueError(f'cannot evaluate #define {tok}')
            return int(eval(expr))
        e=re.search(r'enum\s*\w*\s*\{([^}]*\b'+tok+r'\b[^}]*)\}',src)
        if e:
            val=-1
            for item in re.sub(r'/\*.*?\*/|//[^\n]*','',e.group(1),flags=re.S).split(','):
                name,_,expl=item.strip().partition('=')
                if not name.strip():continue
                val=symbol_expr(expl,text) if expl.strip() else val+1
                if name.strip()==tok:return val
    raise ValueError(f'unknown symbol {tok}')

def symbol_expr(expr,text):
    expr=re.sub(r'\b[A-Za-z_]\w*\b',lambda n:str(symbol(n.group(0),text)),expr)
    return int(eval(expr))

def literal(v,fmt,text=''):
    if isinstance(v,(int,float,bool)):return float(v) if fmt in 'fd' else int(v)
    s=str(v).rstrip('f')
    if s in('TRUE','FALSE'):return int(s=='TRUE')
    try:return float(s) if fmt in 'fd' else int(float(s))
    except ValueError:
        if LEGACY_SYMBOLS:return 0
        x=symbol(str(v),text);return float(x) if fmt in 'fd' else x

def pack(name,values):
    version,fields=module(name);out=b'';text=(SRC/f'{name}.c').read_text()
    for fname,fmt,count,default in fields:
        v=values.get(fname,default);vs=v if isinstance(v,(list,tuple)) else [v]*count
        out+=struct.pack('<'+fmt*count,*(literal(x,fmt,text) for x in vs))
    return version,out.hex()

def unpack(name,blob,version=None):
    """Inverse of pack: {field: value} (arrays as lists). Raises if darktable wrote another modversion or blob size,
    since the field layout would then not match."""
    v,fields=module(name)
    # darktable writes large blobs as 'gz' + 2-digit ratio + base64(zlib(params)), small ones as hex
    raw=zlib.decompress(base64.b64decode(blob[4:])) if blob.startswith('gz') else bytes.fromhex(blob)
    if version is not None and (name,int(version),v) in LEGACY:   # older layout darktable converts on load: do the same
        fill=LEGACY[(name,int(version),v)];return {**unpack_fields([f for f in fields if f[0] not in fill],raw,name),**fill}
    if version is not None and int(version)!=v:raise ValueError(f'{name}: modversion {version} != {v}')
    return unpack_fields(fields,raw,name)

# (module, old modversion, current modversion) -> fields missing in the old layout, with their values after legacy_params
LEGACY={('exposure',6,7):{'compensate_hilite_pres':0}}   # exposure.c: "did not compensate h.p. before v7"

def unpack_fields(fields,raw,name):
    out={};pos=0
    for fname,fmt,count,_ in fields:
        n=struct.calcsize('<'+fmt*count);vals=struct.unpack('<'+fmt*count,raw[pos:pos+n]);pos+=n
        out[fname]=list(vals) if count>1 else vals[0]
    if pos!=len(raw):raise ValueError(f'{name}: blob has {len(raw)} bytes, layout {pos}')
    return out

def read_history(text):
    """XMP text -> [(operation, enabled, {field: value} or None)] for the active history (up to history_end).
    Modules this parser cannot lay out are returned with None params."""
    end=re.search(r'darktable:history_end="(\d+)"',text);end=int(end.group(1)) if end else 10**9
    out=[]
    for li in re.findall(r'<rdf:li\b[^>]*darktable:operation="[^"]*"[^>]*>',text):
        a=dict(re.findall(r'darktable:(\w+)="([^"]*)"',li))
        if int(a.get('num',0))>=end:continue
        try:p=unpack(a['operation'],a['params'],a.get('modversion'))
        except (ValueError,FileNotFoundError,AttributeError):p=None
        out.append((a['operation'],a.get('enabled')=='1',p))
    return out

def xmp(steps):
    """steps: [(module, {field: value})] applied in order."""
    lis=[]
    for i,(name,values) in enumerate(steps):
        version,blob=pack(name,values)
        lis.append(f'<rdf:li darktable:num="{i}" darktable:operation="{name}" darktable:enabled="1" darktable:modversion="{version}" '
                   f'darktable:params="{blob}" darktable:multi_name="" darktable:multi_priority="0"/>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            f'<rdf:Description rdf:about="" xmlns:darktable="http://darktable.sf.net/" darktable:xmp_version="5" darktable:history_end="{len(steps)}">'
            '<darktable:history><rdf:Seq>'+''.join(lis)+'</rdf:Seq></darktable:history></rdf:Description></rdf:RDF></x:xmpmeta>\n')

def render(src,steps,out,workdir=None,size=0):
    """Render with darktable-cli; size>0 bounds the long side (darktable's own scaling, deterministic)."""
    # darktable-cli never overwrites: an existing `out` makes it write out_01.png, out_02.png, ... instead.
    Path(out).unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        side=Path(tmp)/'edit.xmp';side.write_text(xmp(steps))
        dims=['--width',str(size),'--height',str(size)] if size else []
        r=subprocess.run([str(DT),str(src),str(side),str(out),*dims,'--core','--configdir',str(Path(tmp)/'conf'),'--library',':memory:'],
                         capture_output=True,text=True,timeout=600)
        if r.returncode or not Path(out).exists():raise RuntimeError(r.stdout[-800:]+r.stderr[-800:])
    return out
