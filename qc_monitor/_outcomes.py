"""Internal acquisition evidence; public loaders continue to return DataFrames."""
from dataclasses import dataclass, field
import pandas as pd


@dataclass(frozen=True)
class InputOutcome:
    source: str
    state: str  # acquired, foreign, unusable, failed, skipped
    unit: tuple[str, ...] | None = None
    reason: str = ""
    arm: str | None = None
    details: dict = field(default_factory=dict)


@dataclass
class AcquisitionBatch:
    frames: dict[str, pd.DataFrame]
    outcomes: list[InputOutcome] = field(default_factory=list)

    # Counts of rows removed by loaders; unknown counts are explicitly omitted.
    discarded_rows: dict[str, int] = field(default_factory=dict)
    sqlite_operations: list[dict] = field(default_factory=list)

    def failures(self, unit: tuple[str, ...]) -> list[InputOutcome]:
        return [outcome for outcome in self.outcomes if outcome.state == "failed"
                and (outcome.unit == unit or (outcome.unit is None and
                     (outcome.arm is None or outcome.arm == unit[-1])))]
