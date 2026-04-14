from __future__ import annotations

import pandas as pd


def resolve_id_column(*dfs: pd.DataFrame) -> str:
    """Return the player identifier column to use for joins and grouping.

    Returns ``"gsis_id"`` when **all** provided DataFrames contain that column,
    otherwise falls back to ``"player"`` (the name string used in legacy data).

    Parameters
    ----------
    *dfs:
        One or more DataFrames to inspect.  Passing multiple DataFrames is
        useful when joining two frames and both must carry the id column for
        the join to be meaningful.

    Examples
    --------
    >>> resolve_id_column(df)                    # single df
    >>> resolve_id_column(sav_df, esv_df)        # require id in both
    """
    if not dfs:
        return "player"
    if all("gsis_id" in df.columns for df in dfs):
        return "gsis_id"
    return "player"
