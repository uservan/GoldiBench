"""Runs INSIDE gimp-console 3.2 (python-fu-eval batch, started by gimp_env.render_xcf): reads the XCF the GUI session
saved and renders it the way the program bench renders a program (ops_gimp / gimp_batch.py).

Writes <XCF>.json: {"filters": [{layer, op, name, visible, opacity, blend, props}], "layers": n, "size": [w, h]}
(non-destructive filters on each layer, bottom-up as GIMP lists them) and OUT: the image flattened (which merges the
filters), scaled with cubic interpolation so the long side is <= SIZE, as gimp_batch.py does.
Filters applied with "Merge filter" ticked are already pixels and cannot be listed. An image without layers gets only
the JSON.
"""
import json
import gi
gi.require_version('Gimp','3.0')
from gi.repository import Gimp,Gio

def plain(v):
    if isinstance(v,(int,float,bool,str,type(None))):return v
    return str(v)

def main(xcf,out,size):
    img=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(xcf))
    try:
        filters=[]
        for l in img.get_layers():
            for f in l.get_filters():
                c=f.get_config();props={}
                for p in c.list_properties():
                    try:props[p.name]=plain(c.get_property(p.name))
                    except Exception as e:props[p.name]=f'<{type(e).__name__}>'
                filters.append({'layer':l.get_name(),'op':f.get_operation_name(),'name':f.get_name(),'visible':f.get_visible(),
                                'opacity':f.get_opacity(),'blend':str(f.get_blend_mode()),'props':props})
        rec={'filters':filters,'layers':len(img.get_layers()),'size':[img.get_width(),img.get_height()]}
        if not rec['layers']:   # the agent deleted every layer: nothing to flatten or render (OUT is not written)
            json.dump(rec,open(xcf+'.json','w'),indent=1);return
        img.flatten();w,h=img.get_width(),img.get_height()
        if size and max(w,h)>size:
            k=size/max(w,h);Gimp.context_set_interpolation(Gimp.InterpolationType.CUBIC)
            img.scale(max(1,round(w*k)),max(1,round(h*k)))
        if not Gimp.file_save(Gimp.RunMode.NONINTERACTIVE,img,Gio.File.new_for_path(out),None):
            raise RuntimeError(f'could not save {out}')
        json.dump(rec,open(xcf+'.json','w'),indent=1)
    finally:
        img.delete()

main(XCF,OUT,SIZE)   # noqa: F821  (defined by the -b command that exec()s this file)
