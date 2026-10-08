"""Cooperative, nonblocking operation leases, shared by CLI, APIs and updater."""
from contextlib import ExitStack, contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import sys
import threading

from .locking import WriterBusyError

_guard = threading.RLock()
_active = {}


class CoordinationBusyError(WriterBusyError):
    def __init__(self, resource):
        self.resource = resource
        super().__init__(f'Operational resource already in use: {resource}')


def canonical(path):
    return str(Path(path).expanduser().resolve())


def project_requests(root):
    root = Path(root).expanduser().resolve()
    return [('project', str(root), True), *[('project', str(parent), False) for parent in root.parents]]


def runtime_requests(update=False, source=None):
    return [('environment', canonical(sys.prefix), update),
            ('source', canonical(source or Path(__file__).parent), update)]


def resource_requests(files=(), directories=()):
    requests = []
    for value, exclusive_directory in [(p, False) for p in files] + [(p, True) for p in directories]:
        path = Path(value).expanduser().resolve()
        requests.append(('resource', str(path), True))
        # Ancestors share the same namespace as protected directory roots.
        requests.extend(('resource', str(parent), False) for parent in path.parents)
    return requests


def archive_requests(database, *, exclusive=True):
    database = canonical(database)
    requests = resource_requests(files=[database + suffix for suffix in ('', '.lock', '-wal', '-shm', '-journal')])
    return requests if exclusive else [(kind, path, False) for kind, path, _ in requests]


def configuration_requests(config_path, cfg):
    paths = [config_path, *cfg.get('_origins', {}).get('includes', [])]
    return [(kind, path, False) for kind, path, _ in resource_requests(files=paths)]


def config_resources(cfg, *, no_plots=False, summary=None):
    files = []
    directories = []
    if not no_plots:
        output = Path(cfg['plots']['output_dir'])
        directories.append(output)
        files.append(cfg['plots']['html_output'])
        files.extend(output / fig['filename'] for fig in cfg['plots']['figures'])
    if summary:
        files.append(summary)
    return archive_requests(cfg['paths']['qc_database']) + resource_requests(files, directories)


def _registry():
    path = Path('/tmp') / f'soxs-qc-monitor-locks-{os.getuid()}'
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError(f'Unsafe operational lock registry: {path}')
    return path


@contextmanager
def _lease(kind, path, exclusive):
    key = (kind, path)
    owner = threading.get_ident()
    with _guard:
        entries = _active.setdefault(key, {})
        own = entries.get(owner)
        if own:
            if exclusive and not own[2]:
                raise CoordinationBusyError(f'{kind}:{path}')
            own[1] += 1
            entry = own
        else:
            if entries and (exclusive or any(item[2] for item in entries.values())):
                raise CoordinationBusyError(f'{kind}:{path}')
            filename = hashlib.sha256((kind + '\0' + path).encode()).hexdigest() + '.lock'
            registry_fd = os.open(_registry(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                fd = os.open(filename, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=registry_fd)
            finally:
                os.close(registry_fd)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                    raise RuntimeError('Unsafe operational lock file')
                fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                os.close(fd)
                raise CoordinationBusyError(f'{kind}:{path}') from exc
            except BaseException:
                os.close(fd)
                raise
            entry = [fd, 1, exclusive]
            entries[owner] = entry
    try:
        yield entry[0]
    finally:
        with _guard:
            entry[1] -= 1
            if not entry[1]:
                entries.pop(owner)
                os.close(entry[0])
                if not entries:
                    _active.pop(key, None)


@contextmanager
def leases(requests, diagnosis=None):
    merged = {}
    for kind, path, exclusive in requests:
        key = kind, canonical(path)
        merged[key] = merged.get(key, False) or exclusive
    # Source guards precede configuration-dependent resources in every entry path.
    order = {'environment': 0, 'project': 1, 'source': 2, 'resource': 3}
    with ExitStack() as stack:
        fds = []
        for (kind, path), exclusive in sorted(merged.items(), key=lambda item: (order[item[0][0]], item[0])):
            try:
                fds.append(stack.enter_context(_lease(kind, path, exclusive)))
            except CoordinationBusyError as exc:
                if diagnosis is not None:
                    diagnosis['conflict_resource'] = exc.resource
                raise
            if diagnosis is not None:
                diagnosis.setdefault('resources', []).append({'kind': kind, 'path': path, 'exclusive': exclusive})
        yield tuple(fds)
