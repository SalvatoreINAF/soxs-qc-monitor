"""D4 visual QA: ten real renderers and nominal/partial/reused/archived reports."""
from pathlib import Path
import json
import os
import subprocess
import sys
import uuid

root = Path(__file__).resolve().parents[1]
output = Path(sys.argv[1]).resolve()
output.mkdir(parents=True, exist_ok=True)
os.environ['MPLBACKEND'] = 'Agg'
os.environ['MPLCONFIGDIR'] = str(output / 'cache')
os.environ['XDG_CACHE_HOME'] = str(output / 'cache')
sys.path[:0] = [str(root), str(root / 'tests')]
subprocess.run([sys.executable, str(root / 'scripts/capture_d4_rendering.py'),
                str(root), str(output / 'renderers')], check=True)

import pandas as pd
from PIL import Image, ImageDraw, ImageOps
from test_d3d_publication import configuration
from qc_monitor.figure_result import FigureResult
from qc_monitor.plotting import generate_plots_from_config
from qc_monitor.publication import publish_report

canvas = Image.new('RGB', (1500, 3000), 'white')
draw = ImageDraw.Draw(canvas)
for index, file in enumerate(sorted((output / 'renderers/plots').glob('*.png'))):
    with Image.open(file) as source:
        image = ImageOps.contain(source.convert('RGB'), (730, 550))
    x, y = (index % 2) * 750, (index // 2) * 600
    draw.text((x + 12, y + 8), file.stem, fill='black')
    canvas.paste(image, (x + (750 - image.width) // 2, y + 35))
canvas.save(output / 'reference.png')

cfg, config = configuration(output / 'publication')
cfg['plots']['page_title'] = 'SOXS QC — D4 synthetic QA'
cfg['plots']['publication']['retained_generations'] = 4
first = cfg['plots']['figures'][0]
first['title'] = 'VIS — current measurements'
cfg['plots']['figures'].append(dict(first, name='vis_retry', filename='retry.png',
                                  title='VIS — image reuse on failure'))
frame = pd.DataFrame({'qc_value': [98., 99., 100., 100., 101., 102.],
                      'eso seq arm': ['VIS'] * 6})

def publish(render):
    return publish_report(cfg, project_root=output / 'publication', config_path=config,
                          run_id=str(uuid.uuid4()), render=render)

nominal = publish(lambda plots: generate_plots_from_config(frame, plots, continue_on_error=True))
cfg['plots']['figures'].extend([
    dict(first, name='vis_missing', filename='missing.png', title='VIS — failure without previous image'),
    dict(first, name='nir_empty', arm='NIR', filename='empty.png', title='NIR — no data')])

def partial(plots, reuse=False):
    if reuse:
        # Real save failure; publication may recover only the compatible current PNG.
        (Path(plots['output_dir']) / 'retry.png').mkdir()
    outcomes = generate_plots_from_config(frame, dict(plots, figures=plots['figures'][:2]),
                                         continue_on_error=True)
    outcomes.append(FigureResult.failed(plots['figures'][2], OSError('Synthetic save failure: no previous image')))
    empty = plots['figures'][3]
    outcomes.append(FigureResult(empty['name'], empty['type'], empty['filename'], 'no_data',
                                'empty_history', 'No matching NIR measurements'))
    return outcomes

partial_result = publish(partial)
reused = publish(lambda plots: partial(plots, reuse=True))
results = {}
for name, result in [('nominal', nominal), ('partial', partial_result), ('reused', reused)]:
    results[name] = {'archive': str(Path(result.manifest_path).parent / 'report.html'),
                     'publication': result.as_dict(),
                     'figures': [item.as_dict() for item in result.figures]}
results['live'] = cfg['plots']['html_output']
(output / 'qa.json').write_text(json.dumps(results, indent=2) + '\n')
print(output)
