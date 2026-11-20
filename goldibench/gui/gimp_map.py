"""Where each bench_gimp1 field lives in the GIMP 3.2.6 GUI (gimp_env.py desktop: 1920x1080, image window without a
title bar) and how its displayed value relates to the program value (display = scale * program).

MENU: clicks that open the filter's dialog in a fresh session (Colors / Filters menu, submenu hover, item). Once any
filter has been applied the Filters menu gains a "Recently Used" row, which gimp_replay adds (FILTERS_SHIFT), and widens
(its first row names the last filter); submenu items are clicked at x=800, inside the submenu either way.
FIELDS: (label shown in the dialog, x, y of the number in the field relative to the dialog window's reported position,
scale). The replay moves each dialog to DIALOG_AT first; typing into a field = triple-click the number, type, Tab.
OK: the dialog's OK button, same frame. Scales are checked by gimp_calibrate.py (type a value, read the saved filter).
"""
DIALOG_AT=(240,60)
MENU={'color_balance':[(320,13),(374,38)],'color_temperature':[(320,13),(389,63)],'hue_saturation':[(320,13),(378,113)],
      'exposure':[(320,13),(359,163)],'shadows_highlights':[(320,13),(394,188)],'brightness_contrast':[(320,13),(394,213)],
      'levels':[(320,13),(350,238)],
      'gaussian_blur':[(427,13),(442,114),(800,139)],'unsharp_mask':[(427,13),(456,139),(800,289)],
      'vignette':[(427,13),(486,189),(800,390)],'softglow':[(427,13),(452,314),(800,489)]}
# tool -> ({field: (label, x, y, scale)}, OK (x, y))
FIELDS={
 'brightness_contrast':({'brightness':('Brightness',313,67,127.0),'contrast':('Contrast',313,99,127.0)},(318,275)),
 'exposure':({'black_level':('Black level',300,67,1.0),'exposure':('Exposure',300,95,1.0)},(318,185)),
 'color_temperature':({'original_temperature':('Original temperature',270,67,1.0),'intended_temperature':('Intended temperature',270,95,1.0)},(318,185)),
 'hue_saturation':({'hue':('Hue',310,311,180.0),'saturation':('Saturation',310,341,100.0),'lightness':('Lightness',310,371,100.0)},(318,489)),
 'color_balance':({'cyan_red':('Cyan - Red',265,182,100.0),'magenta_green':('Magenta - Green',265,210,100.0),
                   'yellow_blue':('Yellow - Blue',265,238,100.0)},(318,381)),
 'levels':({'low_input':('Input Levels: black point (left box)',90,274,255.0),'gamma':('Input Levels: gamma (middle box)',315,274,1.0),
            'high_input':('Input Levels: white point (right box)',445,274,255.0)},(473,542)),
 'shadows_highlights':({'shadows':('Shadows',305,90,1.0),'highlights':('Highlights',305,171,1.0)},(318,396)),
 'unsharp_mask':({'radius':('Radius',300,68,1.0),'amount':('Amount',300,96,1.0)},(318,211)),
 'gaussian_blur':({'size':('Size X (Size Y follows while the chain is linked)',270,68,1.0)},(318,262)),
 'vignette':({'radius':('Radius',290,123,1.0),'softness':('Softness',290,151,1.0)},(318,440)),
 'softglow':({'glow_radius':('Glow radius',300,67,1.0),'brightness':('Brightness',300,95,1.0)},(318,211)),
}

# decimals each field's entry keeps (read off the dialogs): an integer entry drops a typed '.', so 50.9 would become 509
DIGITS={('brightness_contrast','brightness'):0,('brightness_contrast','contrast'):0,('levels','low_input'):0,('levels','high_input'):0,
        ('levels','gamma'):2,('hue_saturation','hue'):1,('hue_saturation','saturation'):1,('hue_saturation','lightness'):1,
        ('color_balance','cyan_red'):1,('color_balance','magenta_green'):1,('color_balance','yellow_blue'):1,
        ('shadows_highlights','shadows'):2,('shadows_highlights','highlights'):2,('gaussian_blur','size'):2,
        ('color_temperature','intended_temperature'):0}   # others: 3

def display(tool,field,value):return FIELDS[tool][0][field][3]*value

def shown(tool,field,value):
    """The display value as the GUI holds it (rounded to the entry's decimals)."""
    return round(display(tool,field,value),DIGITS.get((tool,field),3))

def program(tool,field,shown):return shown/FIELDS[tool][0][field][3]
