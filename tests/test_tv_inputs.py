import math

import pandas as pd

from src.contracts.tv_inputs import build_phase2_tv_inputs_from_frames


def _ledger_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player": "Alpha QB", "team": "Dynasty A", "position": "QB"},
            {"player": "Bravo RB", "team": "Dynasty A", "position": "RB"},
            {"player": "Charlie WR", "team": "Dynasty B", "position": "WR"},
        ]
    )


def _training_fixture() -> pd.DataFrame:
    rows = []
    for season, offset in [(2024, 0.0), (2025, 2.0)]:
        for rank, rsv in [(1, 80.0 + offset), (2, 70.0 + offset), (10, 40.0 + offset), (20, 20.0 + offset)]:
            rows.append({"season": season, "position": "QB", "log_adp": math.log(rank), "rsv": rsv})
        for rank, rsv in [(1, 70.0 + offset), (2, 60.0 + offset), (10, 30.0 + offset), (20, 12.0 + offset)]:
            rows.append({"season": season, "position": "RB", "log_adp": math.log(rank), "rsv": rsv})
        for rank, rsv in [(1, 65.0 + offset), (2, 55.0 + offset), (10, 28.0 + offset), (20, 10.0 + offset)]:
            rows.append({"season": season, "position": "WR", "log_adp": math.log(rank), "rsv": rsv})
        for rank, rsv in [(1, 45.0 + offset), (2, 38.0 + offset), (10, 18.0 + offset), (20, 8.0 + offset)]:
            rows.append({"season": season, "position": "TE", "log_adp": math.log(rank), "rsv": rsv})
    return pd.DataFrame(rows)


def _rankings_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"season": 2026, "rank": 1, "player": "Alpha QB", "team": "BUF", "position": "QB"},
            {"season": 2026, "rank": 10, "player": "Bravo RB", "team": "ATL", "position": "RB"},
            {"season": 2026, "rank": 12, "player": "Delta TE", "team": "KC", "position": "TE"},
            {"season": 2025, "rank": 5, "player": "Charlie WR", "team": "LAR", "position": "WR"},
        ]
    )


def test_build_phase2_tv_inputs_scores_target_season_and_builds_flat_path():
    tv_inputs = build_phase2_tv_inputs_from_frames(
        _ledger_fixture(),
        _training_fixture(),
        _rankings_fixture(),
        target_season=2026,
    )

    alpha = tv_inputs.loc[tv_inputs["player"] == "Alpha QB"].iloc[0]
    bravo = tv_inputs.loc[tv_inputs["player"] == "Bravo RB"].iloc[0]
    delta = tv_inputs.loc[tv_inputs["player"] == "Delta TE"].iloc[0]

    assert bool(alpha["matched_2026_rankings"]) is True
    assert bool(bravo["matched_2026_rankings"]) is True
    assert alpha["tv_y0"] == alpha["tv_y1"] == alpha["tv_y2"] == alpha["tv_y3"]
    assert bravo["tv_y0"] == bravo["tv_y1"] == bravo["tv_y2"] == bravo["tv_y3"]
    assert alpha["tv_y0"] > bravo["tv_y0"]
    assert alpha["tv_input_source"] == "phase2_2026_redraft_flat_path"
    assert bool(delta["is_rostered"]) is False
    assert delta["team"] == ""

def test_build_phase2_tv_inputs_uses_target_season_projection_universe_not_just_rosters():
    tv_inputs = build_phase2_tv_inputs_from_frames(
        _ledger_fixture(),
        _training_fixture(),
        _rankings_fixture(),
        target_season=2026,
    )

    assert set(tv_inputs["player"]) == {"Alpha QB", "Bravo RB", "Delta TE"}
    assert "Charlie WR" not in set(tv_inputs["player"])
