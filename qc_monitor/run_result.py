"""Versioned batch diagnostics; independent of acquisition and storage schemas."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import tempfile
import time
import uuid


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def publication_cleanup():
    """Additive v1 diagnostics; null counts mean that no inventory was verified."""
    def phase():
        return {'state': 'skipped', 'removed': {'generations': 0, 'staging': 0},
                'remaining': None, 'ignored': None, 'limits_guaranteed': None}
    return {'startup': phase(), 'retention': phase()}


@dataclass
class RunResult:
    mode: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_utc: str = field(default_factory=utc_now)
    families: dict = field(default_factory=dict)
    phases: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    storage: dict = field(default_factory=dict)
    coordination: dict = field(default_factory=dict)
    plots: dict = field(default_factory=lambda: {'state': 'skipped',
        'counts': {'produced': 0, 'no_data': 0, 'failed': 0, 'reused': 0}, 'figures': []})
    report: dict = field(default_factory=lambda: {'state': 'skipped', 'path': None})
    publication: dict = field(default_factory=lambda: {'state': 'skipped',
        'phase': None, 'generation_id': None, 'previous_generation_id': None,
        'report_path': None, 'manifest_path': None, 'durability': 'not_applicable',
        'staging_cleanup': 'not_required', 'cleanup': publication_cleanup(), 'errors': []})
    sqlite_operations: list = field(default_factory=list)
    exit_code: int = 0
    ended_utc: str | None = None
    duration_seconds: float | None = None
    _start: float = field(default_factory=time.monotonic, repr=False)

    @contextmanager
    def phase(self, name):
        item = {"name": name, "state": "running", "duration_seconds": None}
        self.phases.append(item)
        start = time.monotonic()
        try:
            yield
        except Exception:
            item["state"] = "failed"
            raise
        else:
            item["state"] = "completed"
        finally:
            item["duration_seconds"] = time.monotonic() - start

    def finish(self):
        if self.errors:
            self.exit_code = 2
        elif any(family.get("state") == "partial" for family in self.families.values()):
            self.exit_code = 1
        self.ended_utc = utc_now()
        self.duration_seconds = time.monotonic() - self._start

    def as_dict(self):
        versions = {"python": platform.python_version()}
        for package in ("qc-monitor", "numpy", "pandas", "PyYAML", "astropy", "matplotlib"):
            try:
                versions[package] = version(package)
            except PackageNotFoundError:
                versions[package] = "unavailable"
        return {"format_version": 1, "run_id": self.run_id, "mode": self.mode,
                "started_utc": self.started_utc, "ended_utc": self.ended_utc,
                "duration_seconds": self.duration_seconds, "versions": versions,
                "families": self.families, "phases": self.phases,
                "storage": self.storage, "coordination": self.coordination,
                "plots": self.plots, "report": self.report, "publication": self.publication,
                "sqlite_operations": self.sqlite_operations,
                "errors": self.errors, "exit_code": self.exit_code}

    def to_json(self):
        return json.dumps(self.as_dict(), ensure_ascii=True, allow_nan=False, sort_keys=True)


def write_summary(path: Path, result: RunResult):
    """Replace only the explicitly requested summary, on the same filesystem."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".qc-summary-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(result.to_json() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
