"""Lightweight CLI guard, acquired before importing the application."""
import argparse
from contextlib import nullcontext
import os
from pathlib import Path
import sys

from .coordination import leases, runtime_requests, project_requests
from .locking import WriterBusyError


def config_argument(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--preflight', action='store_true')
    args, _ = parser.parse_known_args(argv)
    if args.config:
        path = args.config.expanduser().resolve()
    elif os.environ.get('QC_MONITOR_ROOT'):
        path = Path(os.environ['QC_MONITOR_ROOT']).expanduser().resolve() / 'configs/qc_monitor.yaml'
    else:
        path = None
        for root in (Path.cwd(), *Path.cwd().parents):
            candidate = root / 'configs/qc_monitor.yaml'
            if candidate.is_file() and (root / 'pyproject.toml').is_file() and (root / 'qc_monitor').is_dir():
                path = candidate.resolve()
                break
    return args, path


def main():
    args, path = config_argument(sys.argv[1:])
    requests = runtime_requests()
    if path:
        requests.extend(project_requests(path.parent.parent))
    diagnosis = {'operation': 'rebuild' if '--rebuild-db' in sys.argv else 'run', 'resources': [], 'conflict_resource': None}
    guard = nullcontext() if args.dry_run or args.preflight or '--help' in sys.argv or '-h' in sys.argv else leases(requests, diagnosis)
    try:
        with guard:
            from .main import main as application_main
            return application_main()
    except WriterBusyError as exc:
        # No application/configuration import and no summary write on startup contention.
        from .run_result import RunResult
        result = RunResult('run')
        result.coordination = diagnosis
        result.coordination['conflict_resource'] = getattr(exc, 'resource', str(exc))
        result.errors.append({'type': type(exc).__name__, 'reason': str(exc), 'phase': 'coordination'})
        result.finish()
        print('RUN_SUMMARY ' + result.to_json(), file=sys.stderr)
        return 2
