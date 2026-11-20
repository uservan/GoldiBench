"""START copies for the Blender GUI bench. The B-1 scenes reference their Poly Haven textures and HDRIs by relative
paths (//...), so a copy opened elsewhere renders magenta (missing images). gui_copy() writes the copy with absolute
paths (bpy make_paths_absolute + save_as, background mode); check() renders original and copy with the program bench's
renderer and requires identical pixels."""
import json,subprocess,sys,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
import ops_blender as B

def gui_copy(src,out):
    expr=(f"import bpy;bpy.ops.wm.open_mainfile(filepath={str(src)!r});bpy.ops.file.make_paths_absolute();"
          f"bpy.ops.wm.save_as_mainfile(filepath={str(out)!r},relative_remap=False)")
    r=subprocess.run([str(B.BLENDER),'-b','--factory-startup','--python-expr',expr],capture_output=True,text=True,timeout=300)
    if not Path(out).exists():raise RuntimeError('blender gui copy failed: '+(r.stdout+r.stderr)[-500:])
    return Path(out)

def check(src,size):
    with tempfile.TemporaryDirectory() as t:
        c=gui_copy(src,Path(t)/'c.blend');B.render_steps(src,[],Path(t)/'a.png',size);B.render_steps(c,[],Path(t)/'b.png',size)
        A=np.asarray(Image.open(Path(t)/'a.png').convert('RGB'),int);C=np.asarray(Image.open(Path(t)/'b.png').convert('RGB'),int)
        return A.shape==C.shape and int(np.abs(A-C).max())==0,int(np.abs(A-C).max()) if A.shape==C.shape else None
