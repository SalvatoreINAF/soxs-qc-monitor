"""Real-renderer D3-F visual QA, confined to a synthetic temporary project."""
from pathlib import Path
import json
import os
import sys
import tempfile
import uuid

os.environ['MPLBACKEND'] = 'Agg'
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests'))
output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='qc-d3f-qa-'))
with tempfile.TemporaryDirectory(prefix='qc-d3f-mpl-') as cache:
    os.environ['MPLCONFIGDIR'] = cache
    os.environ['XDG_CACHE_HOME'] = cache
    import pandas as pd
    from test_d3d_publication import configuration
    from qc_monitor.figure_result import FigureResult
    from qc_monitor.plotting import generate_plots_from_config
    from qc_monitor.publication import publish_report
    cfg, config = configuration(output)
    cfg['plots']['page_title'] = 'SOXS QC — D3-F synthetic QA'
    cfg['plots']['publication']['retained_generations'] = 4
    first = cfg['plots']['figures'][0]
    first['title'] = 'VIS — current measurements'
    cfg['plots']['figures'].append(dict(first, name='vis_retry', filename='retry.png',
                                      title='VIS — image reuse on failure'))
    frame = pd.DataFrame({'qc_value': [98., 99., 100., 100., 101., 102.], 'eso seq arm': ['VIS'] * 6})
    def publish(render):
        return publish_report(cfg, project_root=output, config_path=config,
                              run_id=str(uuid.uuid4()), render=render)
    nominal = publish(lambda plots: generate_plots_from_config(frame, plots, continue_on_error=True))
    cfg['plots']['figures'].extend([
        dict(first, name='vis_missing', filename='missing.png', title='VIS — failure without previous image'),
        dict(first, name='nir_empty', arm='NIR', filename='empty.png', title='NIR — no data')])
    def partial(plots, reuse=False):
        if reuse:
            (Path(plots['output_dir']) / 'retry.png').mkdir()
        outcomes = generate_plots_from_config(frame, dict(plots, figures=plots['figures'][:2]), continue_on_error=True)
        outcomes.append(FigureResult.failed(plots['figures'][2], OSError('Synthetic save failure: no compatible current image')))
        fig = plots['figures'][3]
        outcomes.append(FigureResult(fig['name'], fig['type'], fig['filename'], 'no_data',
                                    'empty_history', 'No matching NIR measurements'))
        return outcomes
    partial_result = publish(partial)
    reused = publish(lambda plots: partial(plots, reuse=True))
    data = {}
    for name, result in [('nominal', nominal), ('partial', partial_result), ('reused', reused)]:
        archive = Path(result.manifest_path).parent / 'report.html'
        data[name] = {'archive': str(archive), 'publication': result.as_dict(),
                      'figures': [item.as_dict() for item in result.figures]}
    data['live'] = cfg['plots']['html_output']
    (output / 'qa.json').write_text(json.dumps(data, indent=2) + '\n')
    print(output)
