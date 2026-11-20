"""Pilot operation library on darktable 5.6.2: which modules an agent may use, which fields it may set,
and their allowed ranges. Fields not listed keep the module default. darktable runs modules in a fixed
pipeline order and keeps one instance per module, so a program is a set {module: {field: value}}.
"""
from pathlib import Path
import os,sys
sys.path.insert(0,str(Path(__file__).parent))
import dt_params

PRODUCT='darktable'
ORDERED=False   # darktable applies modules in its own pipeline order
UNIT_WORD='module'
# module -> (name shown to models, what it does, {field: (min, max, unit/help)})
OPS={
 'exposure':('exposure','brightens or darkens the whole image in stops',{'exposure':(-1.5,1.5,'EV')}),
 'colisa':('contrast brightness saturation','simple global contrast, brightness and saturation',
           {'contrast':(-0.6,0.6,''),'brightness':(-0.5,0.5,''),'saturation':(-0.8,0.8,'')}),
 'levels':('levels','sets black point, mid-grey point and white point',{'levels':((0.0,0.3,0.75),(0.25,0.7,1.0),'[black, grey, white] in 0..1, black<grey<white')}),
 'shadhi':('shadows and highlights','lifts shadows and recovers highlights locally',{'shadows':(0.0,80.0,''),'highlights':(-80.0,0.0,'')}),
 'colorbalancergb':('color balance rgb','colour grading. *_C = strength of a colour tint in the shadows / highlights / whole image (0 = none; global_C is an '
           'additive offset and is very strong), *_H = hue of that tint in degrees (0 red, 60 yellow, 120 green, 180 cyan, 240 blue, '
           '300 magenta; no effect while its *_C is 0); saturation_global and vibrance > 0 more colourful, < 0 muted; contrast > 0 more contrast',
           {'shadows_H':(0.0,360.0,'deg'),'shadows_C':(0.0,0.4,''),'highlights_H':(0.0,360.0,'deg'),'highlights_C':(0.0,0.25,''),
            'global_H':(0.0,360.0,'deg'),'global_C':(0.0,0.015,''),'saturation_global':(-0.6,0.6,''),'vibrance':(-0.6,0.6,''),'contrast':(-0.5,0.5,'')}),
 'bilat':('local contrast','local detail: > 0 enhances local contrast and texture, < 0 softens it, 0 = unchanged',{'detail':(-1.0,4.0,'')}),
 'sharpen':('sharpen','unsharp-mask sharpening',{'amount':(0.0,2.0,''),'radius':(0.5,5.0,'px')}),
 'vignette':('vignetting','brightness < 0 darkens the borders, > 0 brightens them; scale = where the fall-off starts (smaller reaches further in)',{'brightness':(-1.0,0.5,''),'scale':(20.0,90.0,'% inner radius')}),
 'hazeremoval':('haze removal','strength > 0 removes haze (more contrast and colour, darker), < 0 adds haze',{'strength':(-0.5,0.8,'')}),
}
# Fields that must differ from darktable's own default for the module to be neutral or meaningful.
# 2026-11-01 (neutral check): vignette saturation is -0.5 by default (desaturates the borders even at brightness 0) -> 0;
# local contrast in its default local-laplacian mode changes the image at every detail value (0.3-1.6 dE) -> bilateral mode,
# which is the identity at detail 0. split-toning removed: enabled at zero saturation it still changes the image (1.4-6.2 dE).
FIXED={'shadhi':{'shadows':0.0,'highlights':0.0},'levels':{'levels':[0.0,0.5,1.0]},'vignette':{'saturation':0.0},
       'bilat':{'mode':0,'sigma_s':50.0,'sigma_r':20.0}}
# Program values with no effect (make_pilot.scaled moves fields away from these; hue fields have none).
NEUTRAL={'exposure':{'exposure':0},'colisa':{'contrast':0,'brightness':0,'saturation':0},'levels':{'levels':[0,0.5,1]},
         'shadhi':{'shadows':0,'highlights':0},'colorbalancergb':{'shadows_C':0,'highlights_C':0,'global_C':0,'saturation_global':0,'vibrance':0,'contrast':0},
         'bilat':{'detail':0},'sharpen':{'amount':0},'vignette':{'brightness':0},'hazeremoval':{'strength':0}}
HUE_PAIRS={'shadows_H':'shadows_C','highlights_H':'highlights_C','global_H':'global_C'}
DECIMALS={}   # no rounding: darktable stores floats
MIN_DE_LOCAL={'sharpen':3.0}   # sharpening alone changes few pixels: its mean dE never reached 4.1 in v1

# B-2 PlayRaw tasks (DT_LIBRARY=playraw, playraw.py): three modules real edits use often, settable fields and ranges from
# the 1st-99th percentiles of 1973 surveyed user XMPs. Other fields keep the user's values. Off by default, so the
# synthetic sets keep their library (and L3 its module list).
HUES=['red','orange','yellow','green','cyan','blue','lavender','magenta']
PLAYRAW_OPS={
 'toneequal':('tone equalizer','brightens or darkens each exposure band separately (deep blacks to speculars)',
              {b:(-2.0,2.0,'EV') for b in ['noise','ultra_deep_blacks','deep_blacks','blacks','shadows','midtones','highlights','whites','speculars']}),
 'colorequal':('color equalizer','per-hue saturation, hue shift and brightness',
              {**{f'sat_{h}':(0.5,1.8,'x') for h in HUES},**{f'hue_{h}':(-60.0,60.0,'deg shift') for h in HUES},**{f'bright_{h}':(0.4,1.5,'x') for h in HUES}}),
 'agx':('agx','scene-to-display tone mapping: dynamic range, contrast and look',
        {'range_white_relative_ev':(1.5,9.0,'EV above grey'),'range_black_relative_ev':(-20.0,-3.0,'EV below grey'),
         'curve_contrast_around_pivot':(2.0,5.5,''),'curve_pivot_y_linear_output':(0.05,0.7,'output grey'),
         'look_saturation':(0.8,1.5,''),'look_brightness':(0.5,1.5,'')}),
}
PLAYRAW_NEUTRAL={'toneequal':{b:0 for b in PLAYRAW_OPS['toneequal'][2]},
                 'colorequal':{f:(0 if f.startswith('hue_') else 1) for f in PLAYRAW_OPS['colorequal'][2]},
                 'agx':{'range_white_relative_ev':6.5,'range_black_relative_ev':-10.0,'curve_contrast_around_pivot':3.0,
                        'curve_pivot_y_linear_output':0.18,'look_saturation':1.0,'look_brightness':1.0}}
PLAYRAW=os.environ.get('DT_LIBRARY')=='playraw'
if PLAYRAW:
    OPS.update(PLAYRAW_OPS);NEUTRAL.update(PLAYRAW_NEUTRAL)
    OPS['exposure']=(*OPS['exposure'][:2],{'exposure':(-1.5,3.0,'EV')})   # raws often need +2 EV (users' p1-p99: -0.7 .. +1.9, tail to +3)

def render_steps(src,steps,out,size):
    if str(src).endswith('.bundle.json'):   # PlayRaw task: the program applied to the user's own sidecar
        import playraw;return playraw.render(src,steps,out,size,OPS,NEUTRAL)
    return dt_params.render(src,steps,out,size=size)
