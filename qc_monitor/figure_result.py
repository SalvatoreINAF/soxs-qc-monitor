"""Figure diagnostics independent of Matplotlib, storage and publication."""
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal


@dataclass
class FigureResult:
    name: str
    type: str
    filename: str
    state: Literal['produced', 'no_data', 'failed', 'reused']
    reason_code: str
    reason: str
    path: str | None = None
    error_type: str | None = None
    discarded: list[dict] = field(default_factory=list)
    generated_utc: str | None = None
    origin_generation_id: str | None = None
    reused_from_generation_id: str | None = None
    compatibility: dict | None = None
    fallback: dict | None = None

    def as_dict(self):
        return asdict(self)

    @classmethod
    def failed(cls, config, exc, reason_code='render_error'):
        return cls(config['name'], config['type'], config['filename'], 'failed',
                   reason_code, str(exc), error_type=type(exc).__name__)


def summarize_figures(results):
    counts = {state: sum(item.state == state for item in results)
              for state in ('produced', 'no_data', 'failed', 'reused')}
    errors = counts['failed'] + counts['reused']
    state = ('failed' if errors == len(results) and results else
             'partial' if errors else 'completed')
    return {'state': state, 'counts': counts, 'figures': [item.as_dict() for item in results]}


def validate_figure_results(figures, results):
    """An explicit collection must never fall back to a legacy image."""
    by_name = {}
    for result in results:
        if result.name in by_name:
            raise ValueError(f'Duplicate figure result: {result.name}')
        if result.state not in ('produced', 'no_data', 'failed', 'reused'):
            raise ValueError(f'Invalid figure state: {result.state}')
        if (result.path is not None) != (result.state in ('produced', 'reused')):
            raise ValueError(f'Inconsistent figure path: {result.name}')
        if result.state == 'reused':
            from datetime import datetime
            import uuid
            if (not result.generated_utc or not result.compatibility
                    or not result.fallback or result.fallback.get('state') != 'reused'):
                raise ValueError(f'Missing reuse provenance: {result.name}')
            timestamp = datetime.fromisoformat(result.generated_utc)
            if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
                raise ValueError(f'Expected UTC image timestamp: {result.name}')
            for value in (result.origin_generation_id, result.reused_from_generation_id):
                if not isinstance(value, str) or str(uuid.UUID(value)) != value:
                    raise ValueError(f'Invalid reuse generation: {result.name}')
        by_name[result.name] = result
    if set(by_name) != {fig['name'] for fig in figures}:
        raise ValueError('Figure results do not cover configured figures exactly')
    for fig in figures:
        result = by_name[fig['name']]
        if (result.type, result.filename) != (fig['type'], fig['filename']):
            raise ValueError(f'Figure result identity mismatch: {result.name}')
        if result.path is not None and Path(result.path).name != Path(result.filename).name:
            raise ValueError(f'Figure result filename mismatch: {result.name}')
    return by_name
