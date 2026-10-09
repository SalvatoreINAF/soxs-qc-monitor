"""Capture artist data and PNGs from a supplied checkout, for D4 equivalence QA.

Usage: python scripts/capture_d4_rendering.py CHECKOUT OUTPUT_DIRECTORY
The golden fixture was captured from ddf67a85793e8dd64bbac19fe29e7a84634b89f0,
not regenerated from the refactored implementation.
"""
from pathlib import Path
import json, sys, os
root=Path(sys.argv[1]);output=Path(sys.argv[2]);output.mkdir(parents=True,exist_ok=True)
os.environ['MPLCONFIGDIR']=str(output/'cache');os.environ['MPLBACKEND']='Agg'
sys.path[:0]=[str(root),str(root/'tests')]
import matplotlib.pyplot as plt
from test_d3c_rendering import example, render, KINDS
from qc_monitor import plotting
if (root / "qc_monitor/_plots_common.py").is_file():
 from qc_monitor import _plots_common as mechanics
else:
 mechanics=plotting
original=mechanics._save_figure
result={}
for kind in KINDS:
 def save(path,fig=None):
  axes=[]
  for ax in fig.axes:
   axes.append({'title':ax.get_title(),'xlabel':ax.get_xlabel(),'ylabel':ax.get_ylabel(),
    'lines':[{'x':line.get_xdata(orig=False).tolist(),'y':line.get_ydata(orig=False).tolist(),'label':line.get_label()} for line in ax.lines],
    'offsets':[collection.get_offsets().tolist() for collection in ax.collections],
    'bars':[[p.get_x(),p.get_y(),p.get_width(),p.get_height()] for p in ax.patches if hasattr(p,'get_height')]})
  result[kind]={'axes':axes}
  original(path,fig)
 mechanics._save_figure=save
 cfg,df,meta=example(kind,output)
 outcome,=render(kind,cfg,df,meta)
 assert outcome.state=='produced'
 result[kind]['state']=outcome.state
 result[kind]['discarded']=outcome.discarded
 assert plt.get_fignums()==[]
(output/'artists.json').write_text(json.dumps(result,indent=2,default=lambda value: value.item())+'\n')
print(output)
