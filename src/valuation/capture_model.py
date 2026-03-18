from __future__ import annotations

from typing import Protocol

import pandas as pd


class CaptureModel(Protocol):
    """Protocol for roster/start capture probabilities."""

    def roster_prob(self, df: pd.DataFrame) -> pd.Series: ...

    def start_prob(self, df: pd.DataFrame) -> pd.Series: ...


class PerfectCaptureModel:
    """Capture model scaffold that assumes perfect roster and start capture."""

    def roster_prob(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index, dtype=float)

    def start_prob(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index, dtype=float)
