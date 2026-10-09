"""Generate synthetic D3-C visual artifacts; requires the test extra."""
from pathlib import Path
import json
import os
import sys
import tempfile

os.environ['MPLBACKEND'] = 'Agg'
os.environ['MPLCONFIGDIR'] = tempfile.mkdtemp(prefix='qc-d3c-qa-cache-')
os.environ['XDG_CACHE_HOME'] = os.environ['MPLCONFIGDIR']
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests'))
from test_d3c_rendering import example, render
from qc_monitor.generate_html import generate_html_report
from qc_monitor.plotting import generate_plots_from_config, generate_order_location_plots_from_config
import pandas as pd
import numpy as np
from PIL import Image, ImageOps, ImageDraw

output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='qc-d3c-visual-'))
output.mkdir(exist_ok=True)
all_figures, results = [], []
for kind in ('time_series', 'order_location_fit', 'detector_linearity', 'dispersion_resolution'):
    cfg, df, meta = example(kind, output)
    if kind == 'time_series':
        bad = df.iloc[:1].copy()
        bad['qc_value'] = np.inf
        df = pd.concat([df, bad], ignore_index=True)
    result, = render(kind, cfg, df, meta)
    all_figures.extend(cfg['figures'])
    results.append(result)
cfg, df, meta = example('time_series', output)
fig = dict(cfg['figures'][0], name='nir_no_data', filename='no_data.png', title='NIR — no matching data', arm='NIR')
all_figures.append(fig)
cfg['figures'] = [fig]
cfg['datapoint_queries']['sample']['filters'] = {'eso seq arm': 'NIR'}
result, = generate_plots_from_config(df, cfg)
results.append(result)
cfg, df, meta = example('order_location_fit', output)
fig = dict(cfg['figures'][0], name='nir_failed', filename='failed.png', title='NIR — renderer failure', arm='NIR')
all_figures.append(fig)
cfg['figures'] = [fig]
df['eso seq arm'] = 'NIR'
(output / 'plots/failed.png').mkdir(exist_ok=True)
result, = generate_order_location_plots_from_config(df, meta, cfg, continue_on_error=True)
results.append(result)
cfg = {'figures': all_figures, 'output_dir': str(output / 'plots'), 'page_title': 'SOXS QC — D3-C synthetic QA'}
generate_html_report(cfg, output / 'partial.html', figure_results=results)
generate_html_report(dict(cfg, figures=all_figures[:4]), output / 'nominal.html', figure_results=results[:4])
canvas = Image.new('RGB', (1500, 1180), 'white')
draw = ImageDraw.Draw(canvas)
for index, item in enumerate(results[:4]):
    image = Image.open(item.path).convert('RGB')
    image = ImageOps.contain(image, (730, 540))
    x, y = (index % 2) * 750, (index // 2) * 590
    draw.text((x+12, y+8), item.name, fill='black')
    canvas.paste(image, (x+(750-image.width)//2, y+35))
canvas.save(root / 'docs/qa/d3-c-reference.png')
(output / 'outcomes.json').write_text(json.dumps([item.as_dict() for item in results], indent=2))
print(output)
