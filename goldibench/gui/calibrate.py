"""Check gui_map: for every field, type a display value into the GUI and decode what darktable stored in the XMP.
Prints field, typed display value, stored value and the value gui_map predicts. Fresh desktop per module."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(Path(__file__).parent.parent/'bench'))
import gui_map as G,replay,dt_params
from desktop import Desktop

# a typed display value per field, inside the GUI soft range
PROBE={'exposure':{'exposure':-0.8},'shadhi':{'shadows':30,'highlights':-40},
       'colorbalancergb':{'vibrance':20,'contrast':-15,'saturation_global':25,'global_H':40,'global_C':10,
                          'shadows_H':200,'shadows_C':12,'highlights_H':60,'highlights_C':8},
       'splittoning':{'shadow_hue':216,'shadow_saturation':0.3,'highlight_hue':36,'highlight_saturation':0.6,'balance':30},
       'bilat':{'detail':180},'sharpen':{'radius':3,'amount':1.2},'vignette':{'scale':40,'brightness':-0.7},'hazeremoval':{'strength':0.4}}

def main(work,image,mods=None):
    rows=[]
    for m,fields in PROBE.items():
        if mods and m not in mods:continue
        d=Desktop(f'{work}/{m}').start(image)
        try:
            replay.apply(d,{m:{f:G.program(m,f,x) for f,x in fields.items()}})
            time.sleep(1.5);d.screenshot().save(f'{work}/{m}.png');d.flush()
            hist=[p for op,_,p in dt_params.read_history(d.sidecar() or '') if op==m]
            stored=(hist[-1] if hist else None) or {}
            for f,x in fields.items():
                v=stored.get(f);v=v[0] if isinstance(v,list) else v
                want=G.program(m,f,x);ok=v is not None and abs(want-v)<=1e-3*max(1,abs(v))
                rows.append({'module':m,'field':f,'typed':x,'stored':v,'expected':want,'ok':ok})
                print(json.dumps(rows[-1]),flush=True)
        finally:d.close()
    Path(work,'calibration.json').write_text(json.dumps(rows,indent=1))
    print('ok',sum(r['ok'] for r in rows),'/',len(rows))

if __name__=='__main__':main(sys.argv[1],sys.argv[2],sys.argv[3:])
