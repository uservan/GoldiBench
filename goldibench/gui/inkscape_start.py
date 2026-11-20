"""START copies for the Inkscape GUI bench. Inkscape 1.4.4's GUI opens every document whose inkscape:version is older than
0.92 (63 of the 100 B-1 sources, plus files without the attribute) with a modal "Convert legacy Inkscape file" dialog that
--convert-dpi-method does not suppress. The GUI therefore opens a copy whose root carries the current inkscape:version;
check() renders original and copy with the CLI exporter of the program bench and requires identical pixels, so TARGET and
the pass criterion are unchanged."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import re,sys,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
import ops_inkscape as O
VERSION='1.4.4 (dcaf3e7, 2026-05-05)'

def gui_copy(src,out):
    s=Path(src).read_text(encoding='utf-8',errors='surrogateescape')
    if re.search(r'inkscape:version="[^"]*"',s):s=re.sub(r'inkscape:version="[^"]*"',f'inkscape:version="{VERSION}"',s,count=1)
    else:
        if 'xmlns:inkscape=' not in s:s=re.sub(r'<svg\b',f'<svg xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"',s,count=1)
        s=re.sub(r'<svg\b',f'<svg inkscape:version="{VERSION}"',s,count=1)
    Path(out).write_text(s,encoding='utf-8',errors='surrogateescape');return Path(out)

def check(src,size=1024):
    with tempfile.TemporaryDirectory() as t:
        a=O.export(src,Path(t)/'a.png',size);b=O.export(gui_copy(src,Path(t)/'c.svg'),Path(t)/'b.png',size)
        A=np.asarray(Image.open(a).convert('RGBA'),dtype=int);B=np.asarray(Image.open(b).convert('RGBA'),dtype=int)
        return (A.shape==B.shape and int(np.abs(A-B).max())==0),(A.shape,B.shape,int(np.abs(A-B).max()) if A.shape==B.shape else None)

if __name__=='__main__':
    import json
    from concurrent.futures import ThreadPoolExecutor
    tasks=[json.loads(l) for l in gbpaths.open_tasks(O.DATA/'bench_b1_inkscape/tasks.jsonl')]
    res=list(ThreadPoolExecutor(16).map(lambda t:(t['task_id'],*check(t['source_path'])),tasks))
    bad=[r for r in res if not r[1]];print(f'{len(res)-len(bad)}/{len(res)} identical');[print(r) for r in bad]
