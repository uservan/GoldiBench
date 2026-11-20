"""Operation library on RawTherapee 5.13 (BENCH_APP=rawtherapee). A program is written as a partial pp3 processing
profile: rawtherapee-cli starts from neutral values and overrides only the keys we give (see `rawtherapee-cli -h`),
so fields not listed keep RawTherapee's neutral value. RawTherapee runs tools in its fixed pipeline order, one
instance each. Program field names are lowercase; PP3 maps each to (section, key, scale): pp3 value = scale * value (LabGrid: the GUI's -1..1 grid is stored as -12000..12000,
rtengine/procparams.cc LABGRID_CORR_MAX).
Ranges were chosen by rendering each field at its ends on PSBench photos (visible, not destructive).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
from pathlib import Path
import os,subprocess,tempfile

LOCAL=Path(os.environ.get('VE_LOCAL',str(gbpaths.LOCAL)))
CLI=LOCAL/'apps/rawtherapee-5.13/squashfs-root/usr/bin/rawtherapee-cli'
PP3_VERSION=353   # written by rawtherapee-cli 5.13; LabGrid values are rescaled when loading versions < 337

PRODUCT='RawTherapee'
ORDERED=False
UNIT_WORD='tool'
# tool -> (name shown to models, what it does, {field: (min, max, unit/help)})
OPS={
 'exposure':('Exposure','exposure compensation in stops, plus global contrast and saturation',
             {'compensation':(-1.5,1.5,'EV'),'contrast':(-60.0,60.0,''),'saturation':(-60.0,60.0,'')}),
 'lab':('L*a*b* Adjustments','brightness and chromaticity in L*a*b*',{'brightness':(-50.0,50.0,''),'chromaticity':(-60.0,60.0,'')}),
 'shadows_highlights':('Shadows/Highlights','highlights > 0 darkens bright regions, shadows > 0 lifts dark regions (local)',{'highlights':(0.0,80.0,''),'shadows':(0.0,80.0,'')}),
 'vibrance':('Vibrance','saturation that treats muted (pastel) and saturated tones separately',
             {'pastels':(-100.0,100.0,''),'saturated':(-100.0,100.0,'')}),
 'local_contrast':('Local Contrast','unsharp-mask style local contrast enhancement',{'amount':(0.0,1.0,''),'radius':(20.0,200.0,'px')}),
 'sharpening':('Sharpening','unsharp-mask sharpening',{'amount':(0.0,800.0,''),'radius':(0.3,3.0,'px')}),
 'white_balance':('White Balance','temperature = colour temperature of the scene light: lower makes the image cooler / bluer, higher warmer / yellower (6504 = unchanged); green > 1 greener, < 1 more magenta',{'temperature':(4000.0,9000.0,'K'),'green':(0.88,1.14,'')}),
 'dehaze':('Haze Removal','removes haze',{'strength':(0.0,90.0,'')}),
 'vignette':('Vignette Filter','darkens (positive) or brightens (negative) the borders',{'strength':(-2.5,1.5,'EV'),'feather':(0.0,100.0,''),'roundness':(0.0,100.0,'')}),
 'soft_light':('Soft Light','soft-light blend of the image with itself: more contrast and saturation',{'strength':(0.0,100.0,'')}),
 'color_toning':('Color Toning (L*a*b* color correction grid)','tints shadows and highlights: *_a > 0 redder, < 0 greener; *_b > 0 yellower, < 0 bluer',
             {'shadows_a':(-1.0,1.0,''),'shadows_b':(-1.0,1.0,''),'highlights_a':(-1.0,1.0,''),'highlights_b':(-1.0,1.0,'')}),
}
# field -> (pp3 section, key, scale); every tool also writes its section's FIXED keys
PP3={
 'exposure':{'compensation':('Exposure','Compensation',1),'contrast':('Exposure','Contrast',1),'saturation':('Exposure','Saturation',1)},
 'lab':{'brightness':('Luminance Curve','Brightness',1),'chromaticity':('Luminance Curve','Chromaticity',1)},
 'shadows_highlights':{'highlights':('Shadows & Highlights','Highlights',1),'shadows':('Shadows & Highlights','Shadows',1)},
 'vibrance':{'pastels':('Vibrance','Pastels',1),'saturated':('Vibrance','Saturated',1)},
 'local_contrast':{'amount':('Local Contrast','Amount',1),'radius':('Local Contrast','Radius',1)},
 'sharpening':{'amount':('Sharpening','Amount',1),'radius':('Sharpening','Radius',1)},
 'white_balance':{'temperature':('White Balance','Temperature',1),'green':('White Balance','Green',1)},
 'dehaze':{'strength':('Dehaze','Strength',1)},
 'vignette':{'strength':('PCVignette','Strength',1),'feather':('PCVignette','Feather',1),'roundness':('PCVignette','Roundness',1)},
 'soft_light':{'strength':('SoftLight','Strength',1)},
 'color_toning':{'shadows_a':('ColorToning','LabGridALow',12000),'shadows_b':('ColorToning','LabGridBLow',12000),
                 'highlights_a':('ColorToning','LabGridAHigh',12000),'highlights_b':('ColorToning','LabGridBHigh',12000)},
}
# Keys every instance of a tool writes (turning it on, picking the method the fields belong to).
SECTION_KEYS={'lab':{'Luminance Curve':{'Enabled':'true'}},'shadows_highlights':{'Shadows & Highlights':{'Enabled':'true'}},
              'vibrance':{'Vibrance':{'Enabled':'true'}},'local_contrast':{'Local Contrast':{'Enabled':'true'}},
              'sharpening':{'Sharpening':{'Enabled':'true','Method':'usm'}},'white_balance':{'White Balance':{'Enabled':'true','Setting':'Custom'}},
              'dehaze':{'Dehaze':{'Enabled':'true'}},'vignette':{'PCVignette':{'Enabled':'true'}},'soft_light':{'SoftLight':{'Enabled':'true'}},
              'color_toning':{'ColorToning':{'Enabled':'true','Method':'LabGrid'}}}
# Program semantics are "omitted field = no effect", but an enabled tool starts from RawTherapee's own defaults
# (Dehaze 50, Soft Light 30, Local Contrast 0.2, Sharpening 200, Vignette 0.6): those fields are pinned to neutral.
FIXED={'dehaze':{'strength':0.0},'soft_light':{'strength':0.0},'local_contrast':{'amount':0.0},'sharpening':{'amount':0.0},
       'vignette':{'strength':0.0},'white_balance':{'temperature':6504.0,'green':1.0}}
NEUTRAL={'exposure':{'compensation':0,'contrast':0,'saturation':0},'lab':{'brightness':0,'chromaticity':0},
         'shadows_highlights':{'highlights':0,'shadows':0},'vibrance':{'pastels':0,'saturated':0},'local_contrast':{'amount':0},
         'sharpening':{'amount':0},'white_balance':{'temperature':6504,'green':1},'dehaze':{'strength':0},'vignette':{'strength':0},
         'soft_light':{'strength':0},'color_toning':{'shadows_a':0,'shadows_b':0,'highlights_a':0,'highlights_b':0}}
HUE_PAIRS={}
# Fields RawTherapee stores as integers (pp3 refuses '12.5'): programs are rounded to these decimals (ops.quantize).
DECIMALS={'exposure':{'contrast':0,'saturation':0},'lab':{'brightness':0,'chromaticity':0},'shadows_highlights':{'highlights':0,'shadows':0},
          'vibrance':{'pastels':0,'saturated':0},'local_contrast':{'radius':0,'amount':2},'sharpening':{'amount':0,'radius':2},
          'white_balance':{'temperature':0,'green':3},'dehaze':{'strength':0},'vignette':{'feather':0,'roundness':0,'strength':2},
          'soft_light':{'strength':0}}
MIN_DE_LOCAL={'sharpening':3.0,'local_contrast':4.0}

def pp3(steps,size=0):
    """steps [(tool, {field: value})] -> partial pp3 text (sections merged; Resize bounds the long side if size>0)."""
    sec={}
    for m,vals in steps:
        for s,kv in SECTION_KEYS.get(m,{}).items():sec.setdefault(s,{}).update(kv)
        for f,v in vals.items():
            s,k,scale=PP3[m][f];x=float(v)*scale
            sec.setdefault(s,{})[k]=str(round(x)) if DECIMALS.get(m,{}).get(f)==0 else repr(x)
    if size:sec['Resize']={'Enabled':'true','AppliesTo':'Cropped area','Method':'Lanczos','DataSpecified':'3',
                           'Width':str(size),'Height':str(size),'AllowUpscaling':'false'}
    return f'[Version]\nAppVersion=5.13\nVersion={PP3_VERSION}\n\n'+''.join(
        f'[{s}]\n'+''.join(f'{k}={v}\n' for k,v in kv.items())+'\n' for s,kv in sec.items())

def read_pp3(text):
    """pp3 text (e.g. the sidecar the GUI writes) -> {section: {key: value string}}."""
    out={};cur=None
    for line in text.splitlines():
        line=line.strip()
        if line.startswith('[') and line.endswith(']'):cur=out.setdefault(line[1:-1],{})
        elif '=' in line and cur is not None:k,v=line.split('=',1);cur[k]=v
    return out

def render_pp3(src,profile_text,out,workdir=None):
    Path(out).unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        prof=Path(tmp)/'edit.pp3';prof.write_text(profile_text)
        # HOME keeps RawTherapee's options/cache per call (no shared state between renders)
        r=subprocess.run([str(CLI),'-q','-o',str(out),'-n','-Y','-p',str(prof),'-c',str(src)],capture_output=True,text=True,
                         timeout=600,env={**os.environ,'HOME':tmp})
        if r.returncode or not Path(out).exists():raise RuntimeError(r.stdout[-800:]+r.stderr[-800:])
    return out

def render_steps(src,steps,out,size):
    return render_pp3(src,pp3(steps,size),out)
