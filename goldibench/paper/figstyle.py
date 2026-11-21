"""Shared style for the Sec. 3 figures (fig_pipeline.py, fig_task_example.py): Source Sans Pro (Adobe, SIL OFL, in
scripts/paper/fonts; close to Myriad, one family throughout), one palette, and image embedding without resampling (interpolation='none', saved at 600 dpi), so
photos stay sharp in the PDF (the default 100 dpi resampling made them blurry)."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch,Circle
from PIL import Image

HERE=os.path.dirname(os.path.abspath(__file__));ROOT=os.path.join(HERE,'..','..')
PAPER=os.environ.get('GOLDIBENCH_PAPER', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'paper_out'))
for _d in ('tab', 'fig'): os.makedirs(os.path.join(PAPER, _d), exist_ok=True)
D=str(gbpaths.DATA)
APPS=('darktable','rawtherapee','gimp','inkscape','blender')
APP_NAMES={'darktable':'darktable','rawtherapee':'RawTherapee','gimp':'GIMP','inkscape':'Inkscape','blender':'Blender'}
INK,INK2,MUTED,EDGE,PANEL,RULE=('#1a1a1a','#555555','#9a9a9a','#d6d6d6','#f5f5f3','#e3e3e0')
ACC='#2a78d6';LV=['#86b6ef','#2a78d6','#104281'];PASS,FAIL='#1baf7a','#e4572e'
DPI=600
for f in os.listdir(os.path.join(HERE,'fonts')):font_manager.fontManager.addfont(os.path.join(HERE,'fonts',f))
plt.rcParams.update({'font.family':'Source Sans Pro','pdf.fonttype':42,'font.size':7,'savefig.dpi':DPI,'image.interpolation':'none'})

def load(p,s=1200):
    im=Image.open(p).convert('RGB');im.thumbnail((s,s));return im

def square(im):
    s=min(im.size);l,t=(im.width-s)//2,(im.height-s)//2;return im.crop((l,t,l+s,t+s))

class Canvas:
    """A figure in inches with one full-size drawing axis; images go into their own axes at exact positions."""
    def __init__(self,W,H):
        self.W,self.H=W,H;self.fig=plt.figure(figsize=(W,H))
        self.ax=self.fig.add_axes([0,0,1,1]);self.ax.set_xlim(0,W);self.ax.set_ylim(0,H);self.ax.axis('off')
    def img(self,im,x,y,w,h=None,ec=None,lw=0.5,label=None):
        h=h or w*im.height/im.width
        a=self.fig.add_axes([x/self.W,y/self.H,w/self.W,h/self.H]);a.imshow(im,interpolation='none',aspect='auto')
        a.set_xticks([]);a.set_yticks([])
        for s in a.spines.values():s.set_color(ec or EDGE);s.set_linewidth(lw)
        if label:a.text(0.03,0.96,label,transform=a.transAxes,ha='left',va='top',fontsize=6.5,color='white',fontweight='semibold',
                        bbox=dict(boxstyle='round,pad=0.18,rounding_size=0.08',fc='black',ec='none',alpha=0.7))
        return h
    def panel(self,x,w,y=0.04,h=None,title=None,num=None):
        h=h or self.H-0.08;ax=self.ax
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=0.05',fc='white',ec='#b9cbe6',lw=0.6,ls=(0,(3,2))))
        if title:
            tx=x+0.1
            if num is not None:
                ax.add_patch(Circle((x+0.13,y+h-0.11),0.075,fc=ACC,ec='none'))
                ax.text(x+0.13,y+h-0.112,str(num),ha='center',va='center',fontsize=6,color='white',fontweight='bold');tx=x+0.25
            ax.text(tx,y+h-0.112,title,ha='left',va='center',fontsize=8.5,color=INK,fontweight='semibold')
    def arrow(self,x0,x1,y):
        self.ax.annotate('',xy=(x1,y),xytext=(x0,y),arrowprops=dict(arrowstyle='-|>',color=ACC,lw=0.9,mutation_scale=7,shrinkA=0,shrinkB=0))
    def save(self,out):
        os.makedirs(os.path.dirname(out),exist_ok=True);self.fig.savefig(out,dpi=DPI);print('wrote',out)
