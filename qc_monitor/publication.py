"""Atomic publication, bounded retention and compatible image reuse (D3-F).

The live HTML is the sole commit record. A finalised generation is immutable;
its manifest never claims to be current. All leases span temporary cleanup.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
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
from .run_result import utc_now, publication_cleanup
from .schema import SCHEMA_VERSION

OWNER = 'soxs-qc-monitor'
MARKER = 'qc-publication-v1:'
MARKER_START = '<!-- ' + MARKER
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
COMPATIBILITY_VERSION = 1
IMAGE_STATES = ('produced', 'reused')


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
    cleanup: dict = field(default_factory=publication_cleanup)
    errors: list = field(default_factory=list)
    figures: list = field(default_factory=list)

    def as_dict(self):
        value = asdict(self)
        value.pop('figures')
        return value

    def apply_to(self, run):
        """Apply once, preserving publication even when subsequent cleanup failed."""
        run.publication = self.as_dict()
        run.errors.extend(deepcopy(self.errors))
        if self.state != 'skipped':
            run.plots = summarize_figures(self.figures)
            run.report = {'state': self.state, 'path': self.report_path}
        for item in self.figures:
            if item.state in ('failed', 'reused'):
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
            if _json(json.loads(_read(path / '.owner.json'))) != _json(identity):
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
        if _json(json.loads(_read(path / '.owner.json'))) != _json(identity):
            raise ValueError(f'Invalid ownership marker: {path}')


def _remove_owned(path, identity):
    """Descriptor-relative cleanup; symlinks are unlinked, never traversed."""
    if _json(json.loads(_read(path / '.owner.json'))) != _json(identity):
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
    _png_data(_read(path))


def _png_data(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'PNG':
            raise ValueError('Expected PNG')
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


def _validate_html(content, html_path, expected, *, verify_images=True):
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
        if verify_images:
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
        if figure['state'] in IMAGE_STATES:
            expected = root / 'generations' / generation / 'plots' / _relative_png(figure['filename'])
            if figure['path'] != 'plots/' + Path(figure['filename']).as_posix():
                raise ValueError('Invalid manifest artifact path')
            urls.append(_url(expected, html_path))
    _validate_existing_html(content, html_path, urls, manifest)
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
        if (root.parent == source or root.parent.is_relative_to(source)
                or source.is_relative_to(root.parent)):
            raise ValueError('Publication root overlaps input directory')
    for arm in cfg['detector_linearity']['arms'].values():
        source = Path(arm['root']).resolve()
        if (root.parent == source or root.parent.is_relative_to(source)
                or source.is_relative_to(root.parent)):
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


def _prepared(value):
    if not isinstance(value, str):
        raise ValueError('Expected UTC preparation timestamp')
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
        raise ValueError('Expected UTC preparation timestamp')
    return timestamp


def _validate_existing_html(content, html_path, urls, manifest):
    """Verify references/ownership independently of F fallback PNG availability.

    Legacy publications retain their strict image checks. F records can recover
    from missing/damaged PNGs: each candidate is decoded before copying, while
    every image in the newly prepared report is still verified strictly.
    """
    _validate_html(content, html_path, urls, verify_images=False)
    images = iter(urls)
    for figure in manifest['figures']:
        if figure['state'] in IMAGE_STATES and figure.get('compatibility') is None:
            _png(html_path.parent / unquote(next(images)))
        elif figure['state'] in IMAGE_STATES:
            next(images)


def _compatibility(cfg, figure):
    """Versioned per-figure input contract, not a fingerprint of changing data."""
    spec = deepcopy(figure)
    for key in ('section', 'wide'):
        spec.pop(key, None)
    names = set()

    def queries(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'datapoint_query':
                    names.add(child)
                else:
                    queries(child)
        elif isinstance(value, list):
            for child in value:
                queries(child)

    queries(spec)
    result = {'version': COMPATIBILITY_VERSION, 'figure': spec,
              'queries': {name: deepcopy(cfg['plots']['datapoint_queries'][name])
                          for name in sorted(names)},
              'database': {'path': str(Path(cfg['paths']['qc_database']).resolve()),
                           'schema_version': SCHEMA_VERSION}}
    if figure['type'] == 'detector_linearity':
        detlin = deepcopy(cfg['detector_linearity'])
        arms = detlin.pop('arms', {})
        detlin['arms'] = {figure['arm']: arms.get(figure['arm'])}
        result['detector_linearity'] = detlin
    return result


def _discard_artifact(path):
    """Remove only a confined staging artifact, never following a symlink."""
    def empty(fd):
        for name in os.listdir(fd):
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

    if not os.path.lexists(path):
        return
    with _directory(path.parent) as parent:
        info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child = os.open(path.name, DIR_FLAGS, dir_fd=parent)
            try:
                empty(child)
            finally:
                os.close(child)
            os.rmdir(path.name, dir_fd=parent)
        else:
            os.unlink(path.name, dir_fd=parent)
        os.fsync(parent)


def _copy_png(source, destination):
    data = _read(source)
    _png_data(data)
    _plain_directory(destination.parent)
    with _directory(destination.parent) as parent:
        fd = os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | os.O_NOFOLLOW, 0o644, dir_fd=parent)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _png(destination)


def _reuse_figures(cfg, figures, root, previous, stage, stage_identity):
    """Read only the current manifest; copy bytes, never follow origin links."""
    candidates = {}
    if previous is not None:
        manifest = json.loads(_read(root / 'generations' / previous / 'manifest.json'))
        for item in manifest['figures']:
            if item['name'] in candidates:
                raise ValueError('Duplicate current manifest figure')
            candidates[item['name']] = item
    for config, item in zip(cfg['plots']['figures'], figures):
        contract = _compatibility(cfg, config)
        item.compatibility = contract
        if item.state == 'produced':
            item.generated_utc = utc_now()
            item.origin_generation_id = stage_identity['generation_id']
            continue
        if item.state != 'failed':
            continue
        candidate = candidates.get(item.name)
        item.fallback = {'state': 'unavailable', 'reason_code': 'no_current_image',
                         'source_generation_id': previous}
        if candidate is None or candidate['state'] not in IMAGE_STATES:
            continue
        if candidate.get('compatibility') is None:
            item.fallback['reason_code'] = 'missing_metadata'
            continue
        if _json(candidate['compatibility']) != _json(contract):
            item.fallback['reason_code'] = 'incompatible'
            continue
        try:
            _prepared(candidate.get('generated_utc'))
            _uuid(candidate.get('origin_generation_id'))
            if candidate['state'] == 'produced' and candidate['origin_generation_id'] != previous:
                raise ValueError('Original generation mismatch')
            if candidate['state'] == 'reused':
                _uuid(candidate.get('reused_from_generation_id'))
        except (ValueError, TypeError, AttributeError):
            item.fallback['reason_code'] = 'missing_metadata'
            continue
        filename = _relative_png(candidate['filename'])
        if candidate['path'] != 'plots/' + filename.as_posix():
            raise ValueError('Invalid fallback artifact path')
        source = root / 'generations' / previous / 'plots' / filename
        try:
            _png(source)
        except Exception as exc:
            item.fallback.update(reason_code='source_unreadable',
                                 reason=str(exc), error_type=type(exc).__name__)
            continue
        destination = stage / 'plots' / _relative_png(item.filename)
        _check_owned(stage, stage_identity)
        # A failed renderer may have left a partial file or directory here.
        _discard_artifact(destination)
        try:
            _copy_png(source, destination)
        except Exception as exc:
            item.fallback.update(reason_code='copy_failed', reason=str(exc),
                                 error_type=type(exc).__name__)
            _discard_artifact(destination)  # Failure here blocks the publication.
            continue
        item.state = 'reused'
        item.path = str(destination)
        item.generated_utc = candidate['generated_utc']
        item.origin_generation_id = candidate['origin_generation_id']
        item.reused_from_generation_id = previous
        item.fallback.update(state='reused', reason_code='compatible_current_image')


def _inventory(root, kind, identity):
    """Recognise only canonical UUID directories with exact D ownership.

    Unmarked directories and non-UUID names are foreign. A present but unsafe or
    inconsistent marker cannot establish ownership and blocks automatic cleanup.
    """
    parent = root / kind
    found, ignored = {}, 0
    if not parent.exists() and not parent.is_symlink():
        return found, ignored
    with _directory(parent) as fd:
        names = sorted(os.listdir(fd))
    for name in names:
        if name == '.owner.json':
            continue
        try:
            _uuid(name)
        except (ValueError, TypeError, AttributeError):
            ignored += 1
            continue
        path = parent / name
        with _directory(path):
            pass
        try:
            marker = json.loads(_read(path / '.owner.json'))
        except FileNotFoundError:
            ignored += 1
            continue
        if not isinstance(marker, dict):
            raise ValueError(f'Invalid ownership marker: {path}')
        expected = dict(identity, kind='generation', generation_id=name,
                        prepared_utc=marker.get('prepared_utc'))
        if _json(marker) != _json(expected):
            raise ValueError(f'Ownership mismatch: {path}')
        _prepared(marker['prepared_utc'])
        found[name] = marker
    return found, ignored


def _history(root, identity, current, limit):
    """Validate only the retained prefix, including each autonomous archive HTML."""
    retained = []
    generation = current
    while generation is not None and len(retained) < limit:
        _uuid(generation)
        if generation in retained:
            raise ValueError('Cycle in retained publication history')
        path = root / 'generations' / generation
        marker = json.loads(_read(path / '.owner.json'))
        manifest = json.loads(_read(path / 'manifest.json'))
        if not retained and 'retained_history_length' in manifest:
            length = manifest['retained_history_length']
            if type(length) is not int or length < 1:
                raise ValueError('Invalid retained history length')
            # Increasing N cannot recreate history already pruned by an older run.
            limit = min(limit, length)
        expected = dict(identity, kind='generation', generation_id=generation,
                        prepared_utc=manifest.get('prepared_utc'))
        if (_json(marker) != _json(expected)
                or any(_json(manifest.get(key)) != _json(value)
                       for key, value in identity.items())
                or manifest.get('generation_id') != generation
                or manifest.get('run_id') != generation):
            raise ValueError(f'Retained generation identity mismatch: {path}')
        _prepared(marker['prepared_utc'])
        urls = []
        for figure in manifest['figures']:
            if figure['state'] in IMAGE_STATES:
                filename = _relative_png(figure['filename'])
                if figure['path'] != 'plots/' + filename.as_posix():
                    raise ValueError('Invalid retained manifest artifact path')
                urls.append(_url(path / 'plots' / filename, path / 'report.html'))
            elif figure['state'] not in ('no_data', 'failed') or figure['path'] is not None:
                raise ValueError('Invalid retained figure outcome')
        _validate_existing_html(_read(path / 'report.html').decode('utf-8'),
                                path / 'report.html', urls, manifest)
        retained.append(generation)
        generation = manifest['previous_generation_id']
        if generation is not None:
            _uuid(generation)
            if generation in retained:
                raise ValueError('Cycle in retained publication history')
    return retained


def validate_publication(cfg, *, config_path, summary_path=None):
    """Read-only path/property/history validation, usable before archive writes."""
    html = Path(os.path.abspath(cfg['plots']['html_output']))
    root = Path(os.path.abspath(cfg['plots']['output_dir'])) / '.qc-publication' / hashlib.sha256(str(html).encode()).hexdigest()
    identity = {'owner': OWNER, 'format_version': 1, 'report_id': root.name,
                'report_path': str(html)}
    _validate_paths(cfg, config_path, root, html, summary_path)
    _check_owned(root.parent, {'owner': OWNER, 'format_version': 1, 'kind': 'namespace'})
    _check_owned(root, dict(identity, kind='report'))
    for kind in ('staging', 'generations'):
        _check_owned(root / kind, dict(identity, kind=kind))
    current = _current(html, root, root.name)
    _history(root, identity, current, cfg['plots']['publication']['retained_generations'])
    return html, root, identity, current


def _cleanup(root, identity, current, policy, run_id, diagnostic):
    """Plan all deletions before modifying anything; stop on the first failure."""
    diagnostic['state'] = 'failed'
    diagnostic['limits_guaranteed'] = False
    retained = _history(root, identity, current, policy['retained_generations'])
    inventory = {}
    ignored = {}
    for kind in ('generations', 'staging'):
        inventory[kind], ignored[kind] = _inventory(root, kind, identity)
    diagnostic['ignored'] = ignored
    diagnostic['remaining'] = {kind: len(items) for kind, items in inventory.items()}
    now = _prepared(utc_now())
    stages = sorted((name for name in inventory['staging'] if name != run_id),
                    key=lambda name: (_prepared(inventory['staging'][name]['prepared_utc']), name))
    expired = [name for name in stages
               if (now - _prepared(inventory['staging'][name]['prepared_utc'])).total_seconds()
               >= policy['orphan_max_age_hours'] * 3600]
    survivors = [name for name in stages if name not in expired]
    excess = max(0, len(survivors) - policy['max_orphan_staging'])
    candidates = {'generations': sorted(set(inventory['generations']) - set(retained) - {run_id}),
                  'staging': expired + survivors[:excess]}
    for kind, names in candidates.items():
        for name in names:
            try:
                _remove_owned(root / kind / name, inventory[kind][name])
            finally:
                # rmdir may have succeeded before its directory fsync failed.
                if not os.path.lexists(root / kind / name):
                    diagnostic['remaining'][kind] -= 1
                    diagnostic['removed'][kind] += 1
    diagnostic['state'] = 'completed'
    diagnostic['limits_guaranteed'] = True


def publish_report(cfg, *, project_root, config_path, run_id, render, summary_path=None):
    """Publish under B leases; ``render(staging_plots_cfg)`` returns C outcomes.

    cfg must already be normalised. Errors raise PublicationError with the complete
    result (including published state after the commit point). No SQLite writes occur here. Reuse is confined to the current generation.
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
        html_path, root, identity, previous = validate_publication(
            cfg, config_path=config_path, summary_path=summary_path)
        output = root.parent.parent
        report_id = root.name
        namespace = {'owner': OWNER, 'format_version': 1, 'kind': 'namespace'}
        policy = cfg['plots']['publication']
        previous_history = _history(root, identity, previous, policy['retained_generations'])
        for kind in ('staging', 'generations'):
            candidate = root / kind / run_id
            if candidate.exists() or candidate.is_symlink():
                raise FileExistsError(f'Run identifier already exists: {candidate}')
        result.previous_generation_id = previous
        result.generation_id = run_id
        result.phase = 'prepare'
        _plain_directory(output)
        _plain_directory(html_path.parent)
        _owned_directory(root.parent, namespace)
        _owned_directory(root, dict(identity, kind='report'))
        for kind in ('staging', 'generations'):
            _owned_directory(root / kind, dict(identity, kind=kind))
        result.phase = 'startup_cleanup'
        _cleanup(root, identity, previous, policy, run_id, result.cleanup['startup'])
        result.phase = 'prepare'
        final = root / 'generations' / run_id
        stage = root / 'staging' / run_id
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
            elif figure.state == 'reused':
                raise ValueError('Renderer cannot supply a reused image')
        result.phase = 'fallback'
        try:
            _reuse_figures(cfg, figures, root, previous, stage, stage_identity)
        finally:
            result.figures = deepcopy(figures)
        validate_figure_results(plots['figures'], figures)
        template = Path(plots['template']) if plots.get('template') else None
        archive_urls = {item.name: _url(stage / 'plots' / item.filename, stage / 'report.html')
                        for item in figures if item.state in IMAGE_STATES}
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
            value['path'] = 'plots/' + Path(item.filename).as_posix() if item.state in IMAGE_STATES else None
            value['data_utc'] = None
            manifest_figures.append(value)
        manifest = dict(identity, generation_id=run_id, run_id=run_id,
                        previous_generation_id=previous, prepared_utc=stage_identity['prepared_utc'],
                        retained_history_length=min(policy['retained_generations'], 1 + len(previous_history)),
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
            if item.state in IMAGE_STATES:
                item.path = str(final / 'plots' / item.filename)
        result.phase = 'live_html'
        temporary = html_path.parent / ('.qc-report-' + run_id + '.html')
        urls = {item.name: _url(final / 'plots' / item.filename, html_path)
                for item in figures if item.state in IMAGE_STATES}
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
        result.phase = 'retention_cleanup'
        _cleanup(root, identity, run_id, policy, run_id, result.cleanup['retention'])
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
