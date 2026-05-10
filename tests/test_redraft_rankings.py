"""Unit tests for redraft rankings ingest pipeline."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pandas as pd
import pytest

from unittest.mock import patch

import polars as pl

from src.ingest.player_ids import CROSSWALK_COLUMNS
from src.ingest.redraft_rankings import (
    build_master_redraft_adp,
    build_master_redraft_adp_with_fallback,
    build_master_redraft_rankings,
    ensure_redraft_ranking_season,
    load_ff_rankings_live,
    load_single_redraft_adp,
    load_single_redraft_rankings,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
CROSSWALK_FIXTURE = FIXTURE_DIR / "ff_playerids_sample.csv"

# Sentinel paths that don't exist — forces empty override/ambiguity tables
_NO_OVERRIDES = Path("/dev/null/nonexistent_overrides.csv")
_NO_AMBIG = Path("/dev/null/nonexistent_ambig.csv")


@pytest.fixture(scope="module")
def crosswalk() -> pd.DataFrame:
    return pd.read_csv(CROSSWALK_FIXTURE, dtype={"fantasy_data_id": "string"})


# ---------------------------------------------------------------------------
# Helpers to create tiny CSV fixtures on the fly
# ---------------------------------------------------------------------------

_STANDARD_HEADER = '"RK",TIERS,"PLAYER NAME",TEAM,"POS","BEST","WORST","AVG.","STD.DEV","ECR VS. ADP"'
_2025_HEADER = '"RK",TIERS,"PLAYER NAME",TEAM,"POS","BYE WEEK","UPSIDE ","BUST ","SOS SEASON","ECR VS. ADP","AVG. DIFF ","% OVER "'


def _write_csv(tmp_path: Path, name: str, header: str, rows: list[str]) -> Path:
    p = tmp_path / name
    p.write_text(header + "\n" + "\n".join(rows) + "\n")
    return p


# ---------------------------------------------------------------------------
# load_single_redraft_rankings
# ---------------------------------------------------------------------------


def test_load_single_standard_schema(tmp_path):
    rows = [
        '"1",1,"Josh Allen",BUF,"QB1","1","7","2.0","0.7","-"',
        '"2",1,"Travis Etienne Jr.",JAC,"RB1","1","12","2.4","2.0","-"',
        '"3",2,"Justin Jefferson",MIN,"WR1","1","22","4.7","3.4","-"',
    ]
    p = _write_csv(tmp_path, "FantasyPros_2022_Draft_OP_Rankings.csv", _STANDARD_HEADER, rows)
    df = load_single_redraft_rankings(p)

    assert list(df.columns) == [
        "season", "rank", "tier", "player", "team", "position", "pos_rank",
    ]
    assert len(df) == 3
    assert df["season"].unique().tolist() == [2022]
    assert df.iloc[0]["position"] == "QB"
    assert df.iloc[0]["pos_rank"] == 1
    assert df.iloc[1]["position"] == "RB"
    assert df.iloc[2]["player"] == "Justin Jefferson"


def test_load_single_2025_schema(tmp_path):
    rows = [
        '"1",1,"Josh Allen",BUF,"QB1","7","Coach Upside","Coach Bust","4 stars","-","+2.0","56%"',
        '"2",1,"Bijan Robinson",ATL,"RB1","5","Coach Upside","Coach Bust","4 stars","-","+0.7","56%"',
    ]
    p = _write_csv(tmp_path, "FantasyPros_2025_Draft_OP_Rankings.csv", _2025_HEADER, rows)
    df = load_single_redraft_rankings(p)

    assert len(df) == 2
    assert df["season"].unique().tolist() == [2025]
    assert df.iloc[0]["position"] == "QB"
    assert df.iloc[1]["position"] == "RB"


def test_load_single_season_override(tmp_path):
    rows = ['"1",1,"Josh Allen",BUF,"QB1","1","7","2.0","0.7","-"']
    p = _write_csv(tmp_path, "FantasyPros_2022_Draft_OP_Rankings.csv", _STANDARD_HEADER, rows)
    df = load_single_redraft_rankings(p, season=9999)
    assert df["season"].iloc[0] == 9999


def test_pos_rank_parsed_as_int(tmp_path):
    rows = ['"1",1,"Travis Kelce",KC,"TE12","1","7","2.0","0.7","-"']
    p = _write_csv(tmp_path, "FantasyPros_2024_Draft_OP_Rankings.csv", _STANDARD_HEADER, rows)
    df = load_single_redraft_rankings(p)
    assert df.iloc[0]["pos_rank"] == 12
    assert df.iloc[0]["position"] == "TE"


# ---------------------------------------------------------------------------
# build_master_redraft_rankings
# ---------------------------------------------------------------------------


def test_build_master_stacks_years(tmp_path, crosswalk):
    for year in [2023, 2024]:
        rows = [f'"1",1,"Justin Jefferson",MIN,"WR1","1","7","2.0","0.7","-"']
        _write_csv(tmp_path, f"FantasyPros_{year}_Draft_OP_Rankings.csv", _STANDARD_HEADER, rows)

    master = build_master_redraft_rankings(tmp_path, crosswalk=crosswalk, name_overrides_path=_NO_OVERRIDES, ambiguous_ids_path=_NO_AMBIG)
    assert len(master) == 2
    assert set(master["season"]) == {2023, 2024}
    assert "merge_name" in master.columns
    assert "gsis_id" in master.columns


def test_build_master_attaches_gsis_id(tmp_path, crosswalk):
    rows = [
        '"1",1,"Justin Jefferson",MIN,"WR1","1","7","2.0","0.7","-"',
        '"2",1,"Travis Etienne Jr.",JAC,"RB1","1","12","2.4","2.0","-"',
        '"3",2,"Nobody Fakeplayer",FA,"QB1","1","22","4.7","3.4","-"',
    ]
    _write_csv(tmp_path, "FantasyPros_2024_Draft_OP_Rankings.csv", _STANDARD_HEADER, rows)

    master = build_master_redraft_rankings(tmp_path, crosswalk=crosswalk, name_overrides_path=_NO_OVERRIDES, ambiguous_ids_path=_NO_AMBIG)

    jj = master[master["player"] == "Justin Jefferson"].iloc[0]
    assert jj["gsis_id"] == "00-0036322"
    assert jj["merge_name"] == "justin jefferson"

    te = master[master["merge_name"] == "travis etienne"].iloc[0]
    assert te["gsis_id"] == "00-0036973"

    fake = master[master["player"] == "Nobody Fakeplayer"].iloc[0]
    assert pd.isna(fake["gsis_id"])


def test_build_master_resolves_duplicate_crosswalk_with_gsis_id(tmp_path, crosswalk):
    """Tom Brady has two crosswalk rows (one with gsis_id, one without).

    The builder should pick the row with gsis_id rather than dropping both.
    """
    rows = ['"1",1,"Tom Brady",FA,"QB1","1","7","2.0","0.7","-"']
    _write_csv(tmp_path, "FantasyPros_2020_Draft_OP_Rankings.csv", _STANDARD_HEADER, rows)

    master = build_master_redraft_rankings(tmp_path, crosswalk=crosswalk, name_overrides_path=_NO_OVERRIDES, ambiguous_ids_path=_NO_AMBIG)
    assert len(master) == 1
    assert master.iloc[0]["gsis_id"] == "00-0019596"
    assert master.iloc[0]["merge_name"] == "tom brady"


def test_build_master_no_files_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_master_redraft_rankings(tmp_path)


def test_build_master_output_columns(tmp_path, crosswalk):
    rows = ['"1",1,"Josh Allen",BUF,"QB1","1","7","2.0","0.7","-"']
    _write_csv(tmp_path, "FantasyPros_2026_Draft_OP_Rankings.csv", _STANDARD_HEADER, rows)

    master = build_master_redraft_rankings(tmp_path, crosswalk=crosswalk, name_overrides_path=_NO_OVERRIDES, ambiguous_ids_path=_NO_AMBIG)
    expected_cols = [
        "season", "rank", "tier", "player", "team",
        "position", "pos_rank", "merge_name", "gsis_id",
    ]
    assert list(master.columns) == expected_cols


# ---------------------------------------------------------------------------
# Name overrides
# ---------------------------------------------------------------------------


def test_name_override_corrects_merge_name(tmp_path, crosswalk):
    """A.J. Brown normalizes to 'aj brown' which matches the crosswalk.

    But a nickname like 'Hollywood Brown' → 'hollywood brown' does not.
    A name override should remap it to 'marquise brown' so the crosswalk
    can match.  We simulate this with the fixture crosswalk by overriding
    to 'aj brown' (which exists in our small fixture).
    """
    rows = ['"1",1,"Hollywood Brown",BAL,"WR1","1","7","2.0","0.7","-"']
    _write_csv(tmp_path, "FantasyPros_2020_Draft_OP_Rankings.csv", _STANDARD_HEADER, rows)

    overrides_path = tmp_path / "overrides.csv"
    overrides_path.write_text(
        "ranking_name,position,merge_name_override,gsis_id_override\n"
        "Hollywood Brown,WR,aj brown,\n"
    )

    master = build_master_redraft_rankings(
        tmp_path, crosswalk=crosswalk,
        name_overrides_path=overrides_path,
        ambiguous_ids_path=_NO_AMBIG,
    )
    assert len(master) == 1
    assert master.iloc[0]["merge_name"] == "aj brown"
    assert master.iloc[0]["gsis_id"] == "00-0035676"


def test_gsis_id_override_for_position_mismatch(tmp_path, crosswalk):
    """A direct gsis_id override should apply when the crosswalk can't
    match because the player's crosswalk position differs from the ranking.
    """
    rows = ['"1",1,"Some Player",FA,"WR1","1","7","2.0","0.7","-"']
    _write_csv(tmp_path, "FantasyPros_2020_Draft_OP_Rankings.csv", _STANDARD_HEADER, rows)

    overrides_path = tmp_path / "overrides.csv"
    overrides_path.write_text(
        "ranking_name,position,merge_name_override,gsis_id_override\n"
        "Some Player,WR,,00-0099999\n"
    )

    master = build_master_redraft_rankings(
        tmp_path, crosswalk=crosswalk,
        name_overrides_path=overrides_path,
        ambiguous_ids_path=_NO_AMBIG,
    )
    assert master.iloc[0]["gsis_id"] == "00-0099999"


# ---------------------------------------------------------------------------
# Ambiguous ID resolution
# ---------------------------------------------------------------------------


def test_ambiguous_resolution_by_season(tmp_path, crosswalk):
    """When (merge_name, position) maps to multiple gsis_ids in the
    crosswalk, the builder leaves gsis_id null. The ambiguous-resolution
    CSV should fill it in on a per-season basis.

    We use Tom Brady's fixture entry but add a second QB with the same
    merge_name + a different gsis_id to make it truly ambiguous.
    """
    # Extend the crosswalk fixture with a fake second 'tom brady' QB
    cw = crosswalk.copy()
    fake_row = cw[cw["merge_name"] == "tom brady"].iloc[0].copy()
    fake_row["gsis_id"] = "00-FAKE-TB"
    fake_row["team"] = "XXX"
    cw = pd.concat([cw, fake_row.to_frame().T], ignore_index=True)

    rows = [
        '"1",1,"Tom Brady",FA,"QB1","1","7","2.0","0.7","-"',
    ]
    _write_csv(tmp_path, "FantasyPros_2020_Draft_OP_Rankings.csv", _STANDARD_HEADER, rows)

    # Without resolution: gsis_id should be null (ambiguous)
    master_no_res = build_master_redraft_rankings(
        tmp_path, crosswalk=cw,
        name_overrides_path=_NO_OVERRIDES,
        ambiguous_ids_path=_NO_AMBIG,
    )
    assert pd.isna(master_no_res.iloc[0]["gsis_id"])

    # With resolution: should pick the one we specify
    ambig_path = tmp_path / "ambig.csv"
    ambig_path.write_text(
        "merge_name,position,season,gsis_id\n"
        "tom brady,QB,2020,00-0019596\n"
    )
    master_res = build_master_redraft_rankings(
        tmp_path, crosswalk=cw,
        name_overrides_path=_NO_OVERRIDES,
        ambiguous_ids_path=ambig_path,
    )
    assert master_res.iloc[0]["gsis_id"] == "00-0019596"


# ===========================================================================
# FantasyData 2QB ADP format (redraft_adp/)
# ===========================================================================

_ADP_HEADER = "rank,id,player,team,bye_week,age,pos,adp_2qb_pos_rank,adp_2qb"


def _write_adp_csv(tmp_path: Path, name: str, rows: list[str]) -> Path:
    p = tmp_path / name
    p.write_text(_ADP_HEADER + "\n" + "\n".join(rows) + "\n")
    return p


# ---------------------------------------------------------------------------
# load_single_redraft_adp
# ---------------------------------------------------------------------------


def test_adp_load_single_basic(tmp_path):
    rows = [
        "1,19801,Josh Allen,BUF,12,29,QB,QB1,1.6",
        "2,21831,Jalen Hurts,PHI,5,27,QB,QB2,1.9",
        "3,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2",
    ]
    p = _write_adp_csv(tmp_path, "nfl-2qb-adp-abc_2024.csv", rows)
    df = load_single_redraft_adp(p)

    assert list(df.columns) == [
        "season", "rank", "tier", "player", "team", "position", "pos_rank", "fantasy_data_id"
    ]
    assert len(df) == 3
    assert df["season"].unique().tolist() == [2024]
    assert df.iloc[0]["rank"] == 1.6
    assert df.iloc[0]["position"] == "QB"
    assert df.iloc[0]["pos_rank"] == 1
    assert df.iloc[0]["fantasy_data_id"] == "19801"
    assert pd.isna(df.iloc[0]["tier"])


def test_adp_load_single_dst_rows_dropped(tmp_path):
    rows = [
        "1,19801,Josh Allen,BUF,12,29,QB,QB1,1.6",
        "50,BAL,Baltimore Ravens,BAL,14,,DST,DST1,50.0",
    ]
    p = _write_adp_csv(tmp_path, "nfl-2qb-adp-abc_2024.csv", rows)
    df = load_single_redraft_adp(p)
    assert len(df) == 1
    assert df.iloc[0]["player"] == "Josh Allen"


def test_adp_load_single_non_skill_positions_dropped(tmp_path):
    rows = [
        "1,19801,Josh Allen,BUF,12,29,QB,QB1,1.6",
        "10,99999,Some Kicker,TEN,7,30,K,K1,10.0",
    ]
    p = _write_adp_csv(tmp_path, "nfl-2qb-adp-abc_2023.csv", rows)
    df = load_single_redraft_adp(p)
    assert len(df) == 1
    assert df.iloc[0]["position"] == "QB"


def test_adp_load_single_season_override(tmp_path):
    rows = ["1,19801,Josh Allen,BUF,12,29,QB,QB1,1.6"]
    p = _write_adp_csv(tmp_path, "nfl-2qb-adp-abc_2024.csv", rows)
    df = load_single_redraft_adp(p, season=9999)
    assert df["season"].iloc[0] == 9999


# ---------------------------------------------------------------------------
# build_master_redraft_adp
# ---------------------------------------------------------------------------


def test_adp_build_master_stacks_years(tmp_path, crosswalk):
    for year in [2023, 2024]:
        _write_adp_csv(
            tmp_path, f"nfl-2qb-adp-abc_{year}.csv",
            [f"1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.{year % 10}"],
        )
    master = build_master_redraft_adp(tmp_path, crosswalk=crosswalk)
    assert set(master["season"]) == {2023, 2024}
    assert len(master) == 2


def test_adp_build_master_no_files_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_master_redraft_adp(tmp_path)


def test_adp_build_master_output_columns(tmp_path, crosswalk):
    _write_adp_csv(tmp_path, "nfl-2qb-adp-abc_2024.csv",
                   ["1,19801,Josh Allen,BUF,12,29,QB,QB1,1.6"])
    master = build_master_redraft_adp(tmp_path, crosswalk=crosswalk)
    expected = ["season", "rank", "tier", "player", "team",
                "position", "pos_rank", "merge_name", "gsis_id"]
    assert list(master.columns) == expected


def test_adp_build_master_attaches_gsis_id(tmp_path, crosswalk):
    rows = [
        "1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2",
        "2,21696,Travis Etienne,JAC,9,26,RB,RB1,5.1",
        "3,99999,Nobody Fakeplayer,FA,0,25,QB,QB1,10.0",
    ]
    _write_adp_csv(tmp_path, "nfl-2qb-adp-abc_2024.csv", rows)
    master = build_master_redraft_adp(tmp_path, crosswalk=crosswalk)

    jj = master[master["player"] == "Justin Jefferson"].iloc[0]
    assert jj["gsis_id"] == "00-0036322"

    te = master[master["player"] == "Travis Etienne"].iloc[0]
    assert te["gsis_id"] == "00-0036973"

    fake = master[master["player"] == "Nobody Fakeplayer"].iloc[0]
    assert pd.isna(fake["gsis_id"])


def test_adp_rank_is_float(tmp_path, crosswalk):
    _write_adp_csv(tmp_path, "nfl-2qb-adp-abc_2024.csv",
                   ["1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2"])
    master = build_master_redraft_adp(tmp_path, crosswalk=crosswalk)
    assert master.iloc[0]["rank"] == 3.2


# ===========================================================================
# build_master_redraft_adp_with_fallback
# ===========================================================================


def test_fallback_output_columns(tmp_path, crosswalk):
    """Output schema includes ranking_source on top of the standard columns."""
    adp_dir = tmp_path / "adp"
    adp_dir.mkdir()
    rankings_dir = tmp_path / "rankings"
    rankings_dir.mkdir()

    _write_adp_csv(adp_dir, "nfl-2qb-adp-abc_2024.csv",
                   ["1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2"])

    master = build_master_redraft_adp_with_fallback(
        adp_dir, rankings_dir, crosswalk=crosswalk
    )
    expected = [
        "season", "rank", "tier", "player", "team",
        "position", "pos_rank", "merge_name", "gsis_id", "ranking_source",
    ]
    assert list(master.columns) == expected


def test_fallback_adp_season_gets_fantasydata_source(tmp_path, crosswalk):
    """Seasons present in ADP files are labelled fantasydata_adp."""
    adp_dir = tmp_path / "adp"
    adp_dir.mkdir()
    rankings_dir = tmp_path / "rankings"
    rankings_dir.mkdir()

    _write_adp_csv(adp_dir, "nfl-2qb-adp-abc_2025.csv",
                   ["1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2"])

    master = build_master_redraft_adp_with_fallback(
        adp_dir, rankings_dir, crosswalk=crosswalk
    )
    assert len(master) == 1
    assert master.iloc[0]["season"] == 2025
    assert master.iloc[0]["ranking_source"] == "fantasydata_adp"


def test_fallback_missing_adp_season_uses_rankings(tmp_path, crosswalk):
    """Seasons absent from ADP and not the target_season use fantasypros_rankings CSV."""
    adp_dir = tmp_path / "adp"
    adp_dir.mkdir()
    rankings_dir = tmp_path / "rankings"
    rankings_dir.mkdir()

    # 2025 has ADP; 2026 only has a CSV rankings file (no target_season passed
    # so live fetch is not triggered)
    _write_adp_csv(adp_dir, "nfl-2qb-adp-abc_2025.csv",
                   ["1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2"])
    _write_csv(rankings_dir, "FantasyPros_2026_Draft_OP_Rankings.csv",
               _STANDARD_HEADER,
               ['"1",1,"Josh Allen",BUF,"QB1","1","7","2.0","0.7","-"'])

    master = build_master_redraft_adp_with_fallback(
        adp_dir, rankings_dir,
        crosswalk=crosswalk,
        name_overrides_path=_NO_OVERRIDES,
        ambiguous_ids_path=_NO_AMBIG,
    )

    assert set(master["season"]) == {2025, 2026}
    adp_row = master[master["season"] == 2025].iloc[0]
    fallback_row = master[master["season"] == 2026].iloc[0]
    assert adp_row["ranking_source"] == "fantasydata_adp"
    assert fallback_row["ranking_source"] == "fantasypros_rankings"


def test_fallback_adp_season_not_duplicated_by_rankings(tmp_path, crosswalk):
    """When a season exists in both ADP and rankings, only the ADP rows appear."""
    adp_dir = tmp_path / "adp"
    adp_dir.mkdir()
    rankings_dir = tmp_path / "rankings"
    rankings_dir.mkdir()

    _write_adp_csv(adp_dir, "nfl-2qb-adp-abc_2025.csv",
                   ["1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2"])
    # Rankings file for the same 2025 season — should be suppressed
    _write_csv(rankings_dir, "FantasyPros_2025_Draft_OP_Rankings.csv",
               _STANDARD_HEADER,
               ['"1",1,"Josh Allen",BUF,"QB1","1","7","2.0","0.7","-"'])

    master = build_master_redraft_adp_with_fallback(
        adp_dir, rankings_dir,
        crosswalk=crosswalk,
        name_overrides_path=_NO_OVERRIDES,
        ambiguous_ids_path=_NO_AMBIG,
    )

    assert set(master["season"]) == {2025}
    assert len(master) == 1
    assert master.iloc[0]["ranking_source"] == "fantasydata_adp"


def test_fallback_raises_when_both_dirs_empty(tmp_path, crosswalk):
    """FileNotFoundError when neither directory has any usable files."""
    adp_dir = tmp_path / "adp"
    adp_dir.mkdir()
    rankings_dir = tmp_path / "rankings"
    rankings_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        build_master_redraft_adp_with_fallback(
            adp_dir, rankings_dir, crosswalk=crosswalk
        )


def test_ensure_redraft_ranking_season_rebuilds_missing_target_season(tmp_path, crosswalk):
    """Stale masters are rebuilt so a missing target season comes from the live feed."""
    adp_dir = tmp_path / "adp"
    adp_dir.mkdir()
    rankings_dir = tmp_path / "rankings"
    rankings_dir.mkdir()

    _write_adp_csv(
        adp_dir,
        "nfl-2qb-adp-abc_2025.csv",
        ["1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2"],
    )

    stale_master = pd.DataFrame(
        [
            {
                "season": 2025,
                "rank": 3.2,
                "tier": pd.NA,
                "player": "Justin Jefferson",
                "team": "MIN",
                "position": "WR",
                "pos_rank": 1,
                "merge_name": "justin jefferson",
                "gsis_id": "00-0036322",
                "ranking_source": "fantasydata_adp",
            }
        ]
    )

    live_rows = [
        ("/nfl/rankings/superflex.php", "redraft-op", "rsf", "Josh Allen", 17298, "QB", "BUF", 1.0),
    ]
    pl_df = _make_ff_rankings_polars(*live_rows)

    with patch("nflreadpy.load_ff_rankings", return_value=pl_df):
        refreshed = ensure_redraft_ranking_season(
            stale_master,
            target_season=2026,
            adp_dir=adp_dir,
            rankings_fallback_dir=rankings_dir,
            crosswalk=crosswalk,
            name_overrides_path=_NO_OVERRIDES,
            ambiguous_ids_path=_NO_AMBIG,
        )

    assert set(refreshed["season"]) == {2025, 2026}
    live_row = refreshed.loc[refreshed["season"] == 2026].iloc[0]
    assert live_row["player"] == "Josh Allen"
    assert live_row["ranking_source"] == "fantasypros_live"


# ===========================================================================
# load_ff_rankings_live
# ===========================================================================

def _make_ff_rankings_polars(*rows) -> "pl.DataFrame":
    """Build a minimal polars DataFrame mimicking load_ff_rankings() output."""
    data = {
        "fp_page": [r[0] for r in rows],
        "page_type": [r[1] for r in rows],
        "ecr_type": [r[2] for r in rows],
        "player": [r[3] for r in rows],
        "id": [r[4] for r in rows],
        "pos": [r[5] for r in rows],
        "team": [r[6] for r in rows],
        "ecr": [r[7] for r in rows],
        "sd": [0.5] * len(rows),
        "best": [1] * len(rows),
        "worst": [5] * len(rows),
        "sportsdata_id": [None] * len(rows),
        "player_filename": ["x.php"] * len(rows),
        "yahoo_id": [None] * len(rows),
        "cbs_id": [None] * len(rows),
        "player_owned_avg": [50.0] * len(rows),
        "player_owned_espn": [None] * len(rows),
        "player_owned_yahoo": [None] * len(rows),
        "player_image_url": [None] * len(rows),
        "player_square_image_url": [None] * len(rows),
        "rank_delta": [0.0] * len(rows),
        "bye": [None] * len(rows),
        "mergename": [r[3] for r in rows],
        "scrape_date": ["2026-05-08"] * len(rows),
        "tm": [r[6] for r in rows],
    }
    return pl.DataFrame(data)


# Rows format: (fp_page, page_type, ecr_type, player, id, pos, team, ecr)
_LIVE_SAMPLE_ROWS = [
    ("/nfl/rankings/superflex.php", "redraft-op", "rsf", "Justin Jefferson", 19236, "WR", "MIN", 3.2),
    ("/nfl/rankings/superflex.php", "redraft-op", "rsf", "Travis Etienne", 19231, "RB", "JAC", 5.1),
    ("/nfl/rankings/superflex.php", "redraft-op", "rsf", "Josh Allen", 17298, "QB", "BUF", 1.0),
    # Non-superflex row that should be filtered out
    ("/nfl/rankings/overall.php", "redraft-overall", "ro", "Josh Allen", 17298, "QB", "BUF", 1.0),
]


def test_load_ff_rankings_live_output_schema(crosswalk):
    pl_df = _make_ff_rankings_polars(*_LIVE_SAMPLE_ROWS)
    with patch("nflreadpy.load_ff_rankings", return_value=pl_df):
        result = load_ff_rankings_live(season=2026, crosswalk=crosswalk)

    expected_cols = [
        "season", "rank", "tier", "player", "team",
        "position", "pos_rank", "merge_name", "gsis_id",
    ]
    assert list(result.columns) == expected_cols


def test_load_ff_rankings_live_filters_to_superflex(crosswalk):
    """Only redraft-op + rsf rows should appear; the redraft-overall row is dropped."""
    pl_df = _make_ff_rankings_polars(*_LIVE_SAMPLE_ROWS)
    with patch("nflreadpy.load_ff_rankings", return_value=pl_df):
        result = load_ff_rankings_live(season=2026, crosswalk=crosswalk)

    # 3 superflex rows, not 4
    assert len(result) == 3


def test_load_ff_rankings_live_season_injected(crosswalk):
    pl_df = _make_ff_rankings_polars(*_LIVE_SAMPLE_ROWS)
    with patch("nflreadpy.load_ff_rankings", return_value=pl_df):
        result = load_ff_rankings_live(season=2026, crosswalk=crosswalk)

    assert (result["season"] == 2026).all()


def test_load_ff_rankings_live_ecr_used_as_rank(crosswalk):
    pl_df = _make_ff_rankings_polars(*_LIVE_SAMPLE_ROWS)
    with patch("nflreadpy.load_ff_rankings", return_value=pl_df):
        result = load_ff_rankings_live(season=2026, crosswalk=crosswalk)

    jj = result[result["player"] == "Justin Jefferson"].iloc[0]
    assert jj["rank"] == pytest.approx(3.2)


def test_load_ff_rankings_live_pos_rank_computed(crosswalk):
    """pos_rank should be 1-based rank within each position group by ECR."""
    pl_df = _make_ff_rankings_polars(*_LIVE_SAMPLE_ROWS)
    with patch("nflreadpy.load_ff_rankings", return_value=pl_df):
        result = load_ff_rankings_live(season=2026, crosswalk=crosswalk)

    jj = result[result["player"] == "Justin Jefferson"].iloc[0]
    te = result[result["player"] == "Travis Etienne"].iloc[0]
    ja = result[result["player"] == "Josh Allen"].iloc[0]
    # Each is the only player of their position → all pos_rank == 1
    assert jj["pos_rank"] == 1
    assert te["pos_rank"] == 1
    assert ja["pos_rank"] == 1


def test_load_ff_rankings_live_attaches_gsis_id(crosswalk):
    """fantasypros_id join should resolve gsis_id for known players."""
    pl_df = _make_ff_rankings_polars(*_LIVE_SAMPLE_ROWS)
    with patch("nflreadpy.load_ff_rankings", return_value=pl_df):
        result = load_ff_rankings_live(season=2026, crosswalk=crosswalk)

    jj = result[result["player"] == "Justin Jefferson"].iloc[0]
    te = result[result["player"] == "Travis Etienne"].iloc[0]
    assert jj["gsis_id"] == "00-0036322"
    assert te["gsis_id"] == "00-0036973"


def test_load_ff_rankings_live_unknown_id_is_null(crosswalk):
    """Players with an unrecognized fantasypros_id get a null gsis_id."""
    rows = [("/nfl/rankings/superflex.php", "redraft-op", "rsf", "Nobody Fake", 99999, "QB", "FA", 50.0)]
    pl_df = _make_ff_rankings_polars(*rows)
    with patch("nflreadpy.load_ff_rankings", return_value=pl_df):
        result = load_ff_rankings_live(season=2026, crosswalk=crosswalk)

    assert pd.isna(result.iloc[0]["gsis_id"])


# ===========================================================================
# build_master_redraft_adp_with_fallback — live fetch integration
# ===========================================================================


def test_fallback_uses_live_when_target_season_missing(tmp_path, crosswalk):
    """When target_season is absent from ADP, the live FantasyPros feed is used."""
    adp_dir = tmp_path / "adp"
    adp_dir.mkdir()
    rankings_dir = tmp_path / "rankings"
    rankings_dir.mkdir()

    # Only 2025 has ADP; 2026 is the target and has no files anywhere
    _write_adp_csv(adp_dir, "nfl-2qb-adp-abc_2025.csv",
                   ["1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2"])

    live_rows = [
        ("/nfl/rankings/superflex.php", "redraft-op", "rsf", "Josh Allen", 17298, "QB", "BUF", 1.0),
    ]
    pl_df = _make_ff_rankings_polars(*live_rows)

    with patch("nflreadpy.load_ff_rankings", return_value=pl_df):
        master = build_master_redraft_adp_with_fallback(
            adp_dir, rankings_dir,
            target_season=2026,
            crosswalk=crosswalk,
        )

    assert set(master["season"]) == {2025, 2026}
    live_row = master[master["season"] == 2026].iloc[0]
    assert live_row["player"] == "Josh Allen"
    assert live_row["ranking_source"] == "fantasypros_live"


def test_fallback_live_not_called_when_target_in_adp(tmp_path, crosswalk):
    """Live fetch is skipped when target_season is already in ADP files."""
    adp_dir = tmp_path / "adp"
    adp_dir.mkdir()
    rankings_dir = tmp_path / "rankings"
    rankings_dir.mkdir()

    _write_adp_csv(adp_dir, "nfl-2qb-adp-abc_2026.csv",
                   ["1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2"])

    with patch("nflreadpy.load_ff_rankings") as mock_live:
        master = build_master_redraft_adp_with_fallback(
            adp_dir, rankings_dir,
            target_season=2026,
            crosswalk=crosswalk,
        )
        mock_live.assert_not_called()

    assert len(master) == 1
    assert master.iloc[0]["ranking_source"] == "fantasydata_adp"


def test_ensure_redraft_ranking_season_uses_live_for_missing_target(tmp_path, crosswalk):
    """ensure_redraft_ranking_season triggers live fetch for a missing target season."""
    adp_dir = tmp_path / "adp"
    adp_dir.mkdir()
    rankings_dir = tmp_path / "rankings"
    rankings_dir.mkdir()

    _write_adp_csv(adp_dir, "nfl-2qb-adp-abc_2025.csv",
                   ["1,21685,Justin Jefferson,MIN,7,26,WR,WR1,3.2"])

    stale_master = pd.DataFrame([{
        "season": 2025, "rank": 3.2, "tier": pd.NA,
        "player": "Justin Jefferson", "team": "MIN",
        "position": "WR", "pos_rank": 1,
        "merge_name": "justin jefferson", "gsis_id": "00-0036322",
        "ranking_source": "fantasydata_adp",
    }])

    live_rows = [
        ("/nfl/rankings/superflex.php", "redraft-op", "rsf", "Josh Allen", 17298, "QB", "BUF", 1.0),
    ]
    pl_df = _make_ff_rankings_polars(*live_rows)

    with patch("nflreadpy.load_ff_rankings", return_value=pl_df):
        refreshed = ensure_redraft_ranking_season(
            stale_master,
            target_season=2026,
            adp_dir=adp_dir,
            rankings_fallback_dir=rankings_dir,
            crosswalk=crosswalk,
            name_overrides_path=_NO_OVERRIDES,
            ambiguous_ids_path=_NO_AMBIG,
        )

    assert set(refreshed["season"]) == {2025, 2026}
    live_row = refreshed[refreshed["season"] == 2026].iloc[0]
    assert live_row["player"] == "Josh Allen"
    assert live_row["ranking_source"] == "fantasypros_live"
