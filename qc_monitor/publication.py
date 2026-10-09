"""D3-D internal publication engine. The ordinary CLI deliberately does not call it.

The live HTML is the sole commit record. A finalised generation is immutable;
its manifest never claims to be current. All leases span temporary cleanup.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field, asdict
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import quote, unquote, urlsplit
import uuid

from . import __version__
from .coordination import (leases, runtime_requests, project_requests,
                           config_resources, configuration_requests)
from .figure_result import validate_figure_results, summarize_figures
from .generate_html import _render_html_report
from .run_result import utc_now

OWNER = 'soxs-qc-monitor'
MARKER = 'qc-publication-v1:'
MARKER_START = '<!-- ' + MARKER
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@dataclass
class PublicationResult:
    state: str = 'skipped'
    phase: str | None = None
    generation_id: str | None = None
    previous_generation_id: str | None = None
    report_path: str | None = None
    manifest_path: str | None = None
    durability: str = 'not_applicable'
    staging_cleanup: str = 'not_required'
    errors: list = field(default_factory=list)
    figures: list = field(default_factory=list)

    def as_dict(self):
        value = asdict(self)
        value.pop('figures')
        return value

    def apply_to(self, run):
        """Explicit future adapter; not wired into the D3-D CLI."""
        run.publication = self.as_dict()
        run.errors.extend(deepcopy(self.errors))
        if self.state != 'skipped':
            run.plots = summarize_figures(self.figures)
            run.report = {'state': self.state, 'path': self.report_path}
        for item in self.figures:
            if item.state == 'failed':
                run.errors.append({'phase': 'plots', 'figure': item.name,
                                   'reason_code': item.reason_code, 'reason': item.reason,
                                   'type': item.error_type})


class PublicationError(RuntimeError):
    def __init__(self, result):
        self.result = result
        super().__init__(result.errors[-1]['reason'])


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def _uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('Expected canonical UUID generation identifier')
    return value


@contextmanager
def _directory(path):
    """Open each component without following symlinks, including ancestors."""
    path = Path(os.path.abspath(path))
    fd = os.open(path.anchor, DIR_FLAGS)
    try:
        for part in path.parts[1:]:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _read(path):
    with _directory(path.parent) as parent:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f'Unsafe managed file: {path}')
        return stream.read()


def _write(path, content):
    with _directory(path.parent) as parent:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o644, dir_fd=parent)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(content.encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())


def _sync_directory(path):
    with _directory(path) as fd:
        os.fsync(fd)


def _plain_directory(path):
    """Create missing outer directories, refusing symlink components."""
    path = Path(os.path.abspath(path))
    with _directory(path.anchor) as start:
        fd = os.dup(start)
    try:
        for part in path.parts[1:]:
            try:
                os.mkdir(part, dir_fd=fd)
                os.fsync(fd)
            except FileExistsError:
                pass
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
    finally:
        os.close(fd)


def _owned_directory(path, identity):
    """Only a newly created directory may receive a new ownership marker."""
    with _directory(path.parent) as parent:
        try:
            os.mkdir(path.name, dir_fd=parent)
        except FileExistsError:
            if json.loads(_read(path / '.owner.json')) != identity:
                raise ValueError(f'Invalid ownership marker: {path}')
        else:
            try:
                _write(path / '.owner.json', _json(identity))
                _sync_directory(path)
                os.fsync(parent)
            except Exception:
                # Only remove entries created by this call, never adopt an unmarked root.
                with _directory(path) as child:
                    if os.listdir(child) == ['.owner.json']:
                        os.unlink('.owner.json', dir_fd=child)
                os.rmdir(path.name, dir_fd=parent)
                raise
    with _directory(path):
        pass


def _check_owned(path, identity):
    if path.exists() or path.is_symlink():
        if json.loads(_read(path / '.owner.json')) != identity:
            raise ValueError(f'Invalid ownership marker: {path}')


def _remove_owned(path, identity):
    """Descriptor-relative cleanup; symlinks are unlinked, never traversed."""
    if json.loads(_read(path / '.owner.json')) != identity:
        raise ValueError(f'Staging ownership changed: {path}')

    def empty(fd, preserve_marker=False):
        for name in os.listdir(fd):
            if preserve_marker and name == '.owner.json':
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIR_FLAGS, dir_fd=fd)
                try:
                    empty(child)
                finally:
                    os.close(child)
                os.rmdir(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)

    with _directory(path.parent) as parent, _directory(path) as child:
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (before.st_dev, before.st_ino) != (os.fstat(child).st_dev, os.fstat(child).st_ino):
            raise ValueError('Staging directory changed during cleanup')
        empty(child, preserve_marker=True)
        os.unlink('.owner.json', dir_fd=child)
        try:
            os.rmdir(path.name, dir_fd=parent)
        except Exception:
            # Keep a failed cleanup recognisable, even if the final rmdir fails.
            marker = os.open('.owner.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | os.O_NOFOLLOW, 0o644, dir_fd=child)
            with os.fdopen(marker, 'w', encoding='utf-8') as stream:
                stream.write(_json(identity))
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(child)
            raise
        os.fsync(parent)


def _sync_tree(path):
    """Reject unsafe renderer artifacts and sync every file/directory bottom-up."""
    with _directory(path) as fd:
        for name in os.listdir(fd):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                _sync_tree(path / name)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    os.fsync(child)
                finally:
                    os.close(child)
            else:
                raise ValueError(f'Unsafe renderer artifact: {path / name}')
        os.fsync(fd)


def _png(path):
    from PIL import Image
    data = _read(path)
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'PNG':
            raise ValueError(f'Expected PNG: {path}')
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        image.load()


def _relative_png(filename):
    path = Path(filename)
    if (not filename or path.is_absolute() or '..' in path.parts or '\\' in filename
            or path.suffix.lower() != '.png'):
        raise ValueError('Expected confined relative PNG filename')
    return path


def _url(path, html_path):
    return quote(Path(os.path.relpath(path, html_path.parent)).as_posix(), safe='/')


class _References(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images = []
        self.links = []
        self.base = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'base':
            self.base = True
        if tag == 'img':
            self.images.append(attrs.get('src', ''))
        if tag == 'a':
            self.links.append(attrs.get('href', ''))


def _validate_html(content, html_path, expected):
    parsed = _References()
    parsed.feed(content)
    if parsed.base or sorted(parsed.images) != sorted(expected):
        raise ValueError('HTML must reference exactly the produced images without a base URL')
    if any(Path(unquote(urlsplit(link).path)).suffix.lower() == '.png' and link not in expected
           for link in parsed.links):
        raise ValueError('HTML contains an unmanaged PNG link')
    for url in parsed.images + [link for link in parsed.links if link in expected]:
        parts = urlsplit(url)
        if parts.scheme or parts.netloc or parts.query or parts.fragment:
            raise ValueError('Expected a relative artifact URL')
        _png(html_path.parent / unquote(parts.path))


def _marker(content):
    if MARKER_START not in content:
        return None
    matches = re.findall(r'<!-- qc-publication-v1:([a-zA-Z0-9+/=]+) -->', content)
    if len(matches) != 1 or content.count(MARKER_START) != 1:
        raise ValueError('Invalid or duplicate publication marker')
    import base64
    return json.loads(base64.b64decode(matches[0], validate=True))


def _marked(content, marker):
    import base64
    if MARKER_START in content:
        raise ValueError('Template contains reserved publication marker')
    encoded = base64.b64encode(_json(marker).encode()).decode('ascii')
    return f'<!-- {MARKER}{encoded} -->\n' + content


def _current(html_path, root, report_id):
    if not html_path.exists() and not html_path.is_symlink():
        return None
    content = _read(html_path).decode('utf-8')
    marker = _marker(content)
    if marker is None:
        return None
    if (marker.get('format_version') != 1 or marker.get('owner') != OWNER
            or marker.get('report_id') != report_id):
        raise ValueError('Publication marker identity mismatch')
    generation = _uuid(marker.get('generation_id'))
    previous = marker.get('previous_generation_id')
    if previous is not None:
        _uuid(previous)
        if previous == generation:
            raise ValueError('Current generation cannot be its own predecessor')
    raw = _read(root / 'generations' / generation / 'manifest.json')
    manifest = json.loads(raw)
    generation_root = root / 'generations' / generation
    generation_owner = json.loads(_read(generation_root / '.owner.json'))
    expected_owner = {key: manifest.get(key) for key in
                      ('owner', 'format_version', 'report_id', 'report_path',
                       'generation_id', 'prepared_utc')}
    if generation_owner != dict(expected_owner, kind='generation'):
        raise ValueError('Current generation ownership mismatch')
    if (hashlib.sha256(raw).hexdigest() != marker.get('manifest_sha256')
            or any(manifest.get(key) != marker.get(key) for key in
                   ('format_version', 'owner', 'report_id', 'generation_id', 'previous_generation_id'))
            or manifest.get('report_path') != str(html_path)):
        raise ValueError('Current publication manifest mismatch')
    urls = []
    for figure in manifest['figures']:
        if figure['state'] == 'produced':
            expected = root / 'generations' / generation / 'plots' / _relative_png(figure['filename'])
            if figure['path'] != 'plots/' + Path(figure['filename']).as_posix():
                raise ValueError('Invalid manifest artifact path')
            urls.append(_url(expected, html_path))
    _validate_html(content, html_path, urls)
    return generation


def _validate_paths(cfg, config_path, root, html_path, summary_path):
    from .main import validate_path_collisions
    source_root = Path(cfg['paths']['upstream_root'])
    databases = list(source_root.rglob('*.db')) if source_root.is_dir() else []
    # Include the configured source database name even when its extension is not .db.
    if source_root.is_dir():
        databases.extend(source_root.rglob(cfg['acquisition']['upstream_database_name']))
    validate_path_collisions(cfg, config_path, databases)
    protected = [Path(config_path), *map(Path, cfg.get('_origins', {}).get('includes', [])),
                 Path(cfg['paths']['qc_database']), *databases]
    protected += [Path(str(cfg['paths']['qc_database']) + suffix)
                  for suffix in ('.lock', '-wal', '-shm', '-journal')]
    protected += list(Path(cfg['paths']['qc_database']).parent.glob(
        Path(cfg['paths']['qc_database']).name + '.backup-*.sqlite'))
    if cfg['plots'].get('template'):
        protected.append(Path(cfg['plots']['template']))
    if summary_path:
        protected.append(Path(summary_path))
    for key in ('upstream_root', 'reduced_root'):
        source = Path(cfg['paths'][key]).resolve()
        if root == source or root.is_relative_to(source):
            raise ValueError('Publication root overlaps input directory')
    for arm in cfg['detector_linearity']['arms'].values():
        source = Path(arm['root']).resolve()
        if root == source or root.is_relative_to(source):
            raise ValueError('Publication root overlaps detector input directory')
    namespace = root.parent
    if html_path == namespace or html_path.is_relative_to(namespace):
        raise ValueError('Live HTML overlaps managed generations')
    for value in protected:
        path = value.resolve()
        if path == html_path or path == namespace or path.is_relative_to(namespace):
            raise ValueError(f'Publication destination overlaps protected file: {value}')
    for figure in cfg['plots']['figures']:
        _relative_png(figure['filename'])
    # Check existing ancestors without resolving a symlink into an allowed destination.
    for path in (Path(cfg['plots']['output_dir']), html_path.parent):
        existing = path
        while not existing.exists() and not existing.is_symlink():
            existing = existing.parent
        with _directory(existing):
            pass
    if html_path.is_symlink():
        raise ValueError('Live report must not be a symlink')


def publish_report(cfg, *, project_root, config_path, run_id, render, summary_path=None):
    """Publish under B leases; ``render(staging_plots_cfg)`` returns C outcomes.

    cfg must already be normalised. Errors raise PublicationError with the complete
    result (including published state after the commit point). No SQLite writes,
    retention, fallback, or automatic CLI activation occur here.
    """
    result = PublicationResult()
    if not cfg['plots'].get('figures'):
        return result
    requests = (runtime_requests() + project_requests(project_root)
                + configuration_requests(config_path, cfg)
                + config_resources(cfg, summary=summary_path))
    try:
        with leases(requests):
            _publish(cfg, config_path, run_id, render, summary_path, result)
    except Exception as exc:
        if isinstance(exc, PublicationError):
            raise
        result.state = 'failed'
        result.errors.append({'phase': result.phase or 'coordination',
                              'type': type(exc).__name__, 'reason': str(exc)})
        raise PublicationError(result) from exc
    return result


def _publish(cfg, config_path, run_id, render, summary_path, result):
    stage = temporary = None
    stage_identity = None
    finalised = False
    try:
        result.state = 'failed'
        result.phase = 'validation'
        _uuid(run_id)
        html_path = Path(os.path.abspath(cfg['plots']['html_output']))
        output = Path(os.path.abspath(cfg['plots']['output_dir']))
        report_id = hashlib.sha256(str(html_path).encode()).hexdigest()
        root = output / '.qc-publication' / report_id
        _validate_paths(cfg, config_path, root, html_path, summary_path)
        identity = {'owner': OWNER, 'format_version': 1, 'report_id': report_id,
                    'report_path': str(html_path)}
        namespace = {'owner': OWNER, 'format_version': 1, 'kind': 'namespace'}
        _check_owned(root.parent, namespace)
        _check_owned(root, dict(identity, kind='report'))
        for kind in ('staging', 'generations'):
            _check_owned(root / kind, dict(identity, kind=kind))
        previous = _current(html_path, root, report_id)
        result.previous_generation_id = previous
        result.generation_id = run_id
        result.phase = 'prepare'
        _plain_directory(output)
        _plain_directory(html_path.parent)
        _owned_directory(root.parent, namespace)
        _owned_directory(root, dict(identity, kind='report'))
        for kind in ('staging', 'generations'):
            _owned_directory(root / kind, dict(identity, kind=kind))
        final = root / 'generations' / run_id
        if final.exists() or final.is_symlink():
            raise FileExistsError(f'Generation already exists: {run_id}')
        stage = root / 'staging' / run_id
        if stage.exists() or stage.is_symlink():
            stage = None  # Never clean a directory belonging to an earlier invocation.
            raise FileExistsError(f'Staging already exists: {run_id}')
        stage_identity = dict(identity, kind='generation', generation_id=run_id,
                              prepared_utc=utc_now())
        _owned_directory(stage, stage_identity)
        result.staging_cleanup = 'pending'
        _plain_directory(stage / 'plots')
        plots = deepcopy(cfg['plots'])
        plots['output_dir'] = str(stage / 'plots')
        plots['html_output'] = str(stage / 'report.html')
        result.phase = 'render'
        figures = list(render(plots))
        by_name = validate_figure_results(plots['figures'], figures)
        figures = [by_name[fig['name']] for fig in plots['figures']]
        result.figures = deepcopy(figures)
        result.phase = 'artifacts'
        _check_owned(stage, stage_identity)
        for figure in figures:
            if figure.state == 'produced':
                expected = stage / 'plots' / _relative_png(figure.filename)
                if Path(os.path.abspath(figure.path)) != expected:
                    raise ValueError(f'Figure path outside expected staging location: {figure.name}')
                _png(expected)
        template = Path(plots['template']) if plots.get('template') else None
        archive_urls = {item.name: _url(stage / 'plots' / item.filename, stage / 'report.html')
                        for item in figures if item.state == 'produced'}
        result.phase = 'archive_html'
        _write(stage / 'report.html', _render_html_report(
            plots, stage / 'report.html', template, figures, image_urls=archive_urls))
        archived = _read(stage / 'report.html').decode('utf-8')
        if MARKER_START in archived:
            raise ValueError('Template contains reserved publication marker')
        _validate_html(archived, stage / 'report.html', list(archive_urls.values()))
        snapshot = deepcopy(cfg['plots'])
        snapshot.pop('output_dir', None)
        snapshot.pop('html_output', None)
        manifest_figures = []
        for item in figures:
            value = item.as_dict()
            value['path'] = 'plots/' + Path(item.filename).as_posix() if item.state == 'produced' else None
            value['data_utc'] = None
            manifest_figures.append(value)
        manifest = dict(identity, generation_id=run_id, run_id=run_id,
                        previous_generation_id=previous, prepared_utc=stage_identity['prepared_utc'],
                        package_version=__version__, rendering_config=snapshot,
                        detector_linearity=deepcopy(cfg.get('detector_linearity', {})),
                        figures=manifest_figures)
        result.phase = 'manifest'
        raw_manifest = _json(manifest)
        _write(stage / 'manifest.json', raw_manifest)
        result.phase = 'sync_staging'
        _sync_tree(stage)
        result.phase = 'finalize'
        with _directory(stage.parent) as src, _directory(final.parent) as dst:
            # Resource leases prevent cooperative collisions; never replace an existing generation.
            if run_id in os.listdir(dst):
                raise FileExistsError(f'Generation already exists: {run_id}')
            os.rename(run_id, run_id, src_dir_fd=src, dst_dir_fd=dst)
            finalised = True
            result.staging_cleanup = 'not_required'
            result.manifest_path = str(final / 'manifest.json')
            os.fsync(dst)
            os.fsync(src)
        for item in result.figures:
            if item.state == 'produced':
                item.path = str(final / 'plots' / item.filename)
        result.phase = 'live_html'
        temporary = html_path.parent / ('.qc-report-' + run_id + '.html')
        urls = {item.name: _url(final / 'plots' / item.filename, html_path)
                for item in figures if item.state == 'produced'}
        marker = {key: manifest[key] for key in ('owner', 'format_version', 'report_id',
                   'generation_id', 'previous_generation_id')}
        marker['manifest_sha256'] = hashlib.sha256(raw_manifest.encode()).hexdigest()
        content = _marked(_render_html_report(plots, temporary, template, figures,
                                             image_urls=urls), marker)
        _validate_html(content, html_path, list(urls.values()))
        result.phase = 'sync_html'
        # Track ownership only after exclusive creation; never clean a preexisting name.
        live_temporary = temporary
        temporary = None
        with _directory(live_temporary.parent) as parent:
            fd = os.open(live_temporary.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW, 0o644, dir_fd=parent)
        temporary = live_temporary
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        result.phase = 'commit'
        with _directory(html_path.parent) as parent:
            os.replace(temporary.name, html_path.name, src_dir_fd=parent, dst_dir_fd=parent)
            temporary = None
            result.state = 'published'
            result.report_path = str(html_path)
            result.durability = 'unconfirmed'
            result.phase = 'sync_commit'
            os.fsync(parent)
        result.durability = 'confirmed'
        result.phase = 'completed'
    except Exception as exc:
        result.errors.append({'phase': result.phase, 'type': type(exc).__name__, 'reason': str(exc)})
    finally:
        try:
            if temporary is not None:
                with _directory(temporary.parent) as fd:
                    os.unlink(temporary.name, dir_fd=fd)
                    os.fsync(fd)
            if stage is not None and not finalised and stage_identity is not None:
                _remove_owned(stage, stage_identity)
                result.staging_cleanup = 'removed'
        except Exception as exc:
            result.staging_cleanup = 'failed'
            result.errors.append({'phase': 'staging_cleanup', 'type': type(exc).__name__, 'reason': str(exc)})
    if result.errors:
        raise PublicationError(result)
