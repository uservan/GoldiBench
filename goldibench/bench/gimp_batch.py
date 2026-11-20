"""Runs INSIDE gimp-console 3.2 (python-fu-eval batch, started by ops_gimp.run_batch): renders a list of jobs.

Job file (JSON list), one entry per output:
  {"src": image path, "out": png path, "size": long-side bound (0 = none),
   "steps": [[gegl operation, {property: value}], ...]}   applied in order, each merged into the layer
Property values: numbers / booleans; {"enum": "Gimp.TRCType", "name": "PERCEPTUAL"} for GIMP enums.
Writes <job file>.result.json: {"ok": [...out], "errors": {out: message}}. One GIMP start serves the whole list.
Scaling after the edit uses GIMP's own Image.scale with cubic interpolation (the long side is bounded, never upscaled).
"""
import json,sys,traceback
import gi
gi.require_version('Gimp','3.0');gi.require_version('Gegl','0.4')
from gi.repository import Gimp,Gio

def value(v):
    if isinstance(v,dict) and 'enum' in v:
        return getattr(getattr(Gimp,v['enum'].split('.',1)[1]),v['name'])
    return v

def render(job):
    img=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(job['src']))
    try:
        layer=img.flatten()
        for op,props in job['steps']:
            f=Gimp.DrawableFilter.new(layer,op,'');c=f.get_config()
            for k,v in props.items():c.set_property(k,value(v))
            f.update();layer.merge_filter(f)
        w,h=img.get_width(),img.get_height();s=job.get('size') or 0
        if s and max(w,h)>s:
            k=s/max(w,h);Gimp.context_set_interpolation(Gimp.InterpolationType.CUBIC)
            img.scale(max(1,round(w*k)),max(1,round(h*k)))
        if not Gimp.file_save(Gimp.RunMode.NONINTERACTIVE,img,Gio.File.new_for_path(job['out']),None):
            raise RuntimeError(f"could not save {job['out']}")
    finally:
        img.delete()

def main(path):
    jobs=json.load(open(path));res={'ok':[],'errors':{}}
    for j in jobs:
        try:render(j);res['ok'].append(j['out'])
        except Exception:res['errors'][j['out']]=traceback.format_exc()[-800:]
    json.dump(res,open(path+'.result.json','w'))

main(JOB_FILE)   # noqa: F821  (defined by the -b command that exec()s this file)
