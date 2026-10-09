"""Reproducible real-renderer D3-D QA in a temporary project (test extra required)."""
from pathlib import Path
import json
import os
import sys
import tempfile

os.environ['MPLBACKEND'] = 'Agg'
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests'))
from test_d3d_publication import configuration
from qc_monitor.figure_result import FigureResult
from qc_monitor.plotting import generate_plots_from_config
from qc_monitor.publication import publish_report
import pandas as pd

output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='qc-d3d-qa-'))
with tempfile.TemporaryDirectory(prefix='qc-d3d-mpl-') as cache:
    os.environ['MPLCONFIGDIR'] = cache
    os.environ['XDG_CACHE_HOME'] = cache
    cfg, config = configuration(output)
    cfg['plots']['page_title'] = 'SOXS QC — D3-D synthetic QA'
    cfg['plots']['figures'][0]['title'] = 'VIS — synthetic histogram'
    frame = pd.DataFrame({'qc_value': [98., 99., 100., 100., 101., 102.], 'eso seq arm': ['VIS'] * 6})
    def publish(render):
        import uuid
        return publish_report(cfg, project_root=output, config_path=config,
                              run_id=str(uuid.uuid4()), render=render)
    nominal = publish(lambda plots: generate_plots_from_config(frame, plots, continue_on_error=True))
    cfg['plots']['figures'].extend([
        dict(cfg['plots']['figures'][0], name='vis_failed', filename='failed.png', title='VIS — save failure'),
        dict(cfg['plots']['figures'][0], name='nir_empty', arm='NIR', filename='empty.png', title='NIR — no data')])
    def partial(plots):
        # Real save failure, confined to the staging owned by this run.
        (Path(plots['output_dir']) / 'failed.png').mkdir()
        good = generate_plots_from_config(frame, dict(plots, figures=plots['figures'][:2]), continue_on_error=True)
        f = plots['figures'][2]
        return good + [FigureResult(f['name'], f['type'], f['filename'], 'no_data', 'empty_history', 'No matching NIR measurements')]
    partial_result = publish(partial)
    outcomes = {'nominal': nominal.as_dict(), 'partial': partial_result.as_dict(),
                'nominal_archive': str(Path(nominal.manifest_path).parent / 'report.html'),
                'partial_archive': str(Path(partial_result.manifest_path).parent / 'report.html')}
    (output / 'qa.json').write_text(json.dumps(outcomes, indent=2) + '\n')
    print(output)
