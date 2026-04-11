"""Unit tests for redraft rankings ingest pipeline."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pandas as pd
import pytest

from src.ingest.player_ids import CROSSWALK_COLUMNS
from src.ingest.redraft_rankings import (
    build_master_redraft_rankings,
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
