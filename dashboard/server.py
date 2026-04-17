"""Minimal Flask server for the ESV Fantasy Dashboard.

Serves the static dashboard files and exposes a REST API for draft pick
ownership management, league config editing, team cap adjustments, roster
upload, and analytical recomputation.

Usage
-----
From the repo root:
    python dashboard/server.py
    # Open http://localhost:5000 in your browser

The server serves:
  /           → dashboard/src/index.html
  /<file>     → dashboard/src/<file>  (JS, CSS)
  /data/<f>   → dashboard/data/<f>   (pre-computed CSVs)

API endpoints
-------------
  GET  /api/picks
  POST /api/picks           – Draft pick ownership CRUD

  GET  /api/config           – Editable league config fields
  POST /api/config           – Save config changes

  GET  /api/team-adjustments – Team cap adjustments
  POST /api/team-adjustments – Save team cap adjustments

  POST /api/roster-upload    – Upload and validate a roster CSV
  POST /api/recompute        – Re-run Phase 3 analytical pipeline
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

# Ensure src/ is importable when running as `python dashboard/server.py`.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, Response, jsonify, request, send_from_directory

from src.contracts.draft_picks import (
    DEFAULT_OWNERSHIP_PATH,
    generate_picks,
    load_ownership,
    save_ownership,
)
from src.contracts.phase3_exports import export_phase3_tables
from src.contracts.phase3_tables import validate_roster_csv
from src.contracts.team_adjustments import (
    load_team_adjustments,
    save_team_adjustments,
    validate_team_adjustments,
)
from src.utils.config import (
    EDITABLE_CONFIG_FIELDS,
    get_editable_config,
    load_league_config,
    save_league_config,
)

# ── Paths ──────────────────────────────────────────────────────────────────
DASHBOARD_SRC  = REPO_ROOT / "dashboard" / "src"
DASHBOARD_DATA = REPO_ROOT / "dashboard" / "data"

DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "interim" / "rosters"
DEFAULT_SCHEDULE_OVERRIDES_CSV = REPO_ROOT / "data" / "raw" / "roster_exports" / "contract_salary_schedule_overrides.csv"
DEFAULT_TV_INPUTS_CSV = REPO_ROOT / "data" / "interim" / "phase3" / "tv_inputs.csv"

app = Flask(__name__, static_folder=None)

# ── Config — loaded once at startup ────────────────────────────────────────
_CONFIG = load_league_config()
_PICKS  = generate_picks(_CONFIG)


def _roster_csv_path() -> Path:
    """Current roster CSV path based on active config."""
    current_season = int(_CONFIG["season"]["current_season"])
    return REPO_ROOT / "data" / "raw" / "roster_exports" / f"lbb_rosters_{current_season}.csv"


# ── Static file serving ─────────────────────────────────────────────────────

@app.route("/")
def index() -> Response:
    return send_from_directory(str(DASHBOARD_SRC), "index.html")


@app.route("/<path:filename>")
def src_files(filename: str) -> Response:
    """Serve JS/CSS from dashboard/src; fall through to dashboard/data."""
    src_path  = DASHBOARD_SRC  / filename
    data_path = DASHBOARD_DATA / filename

    if src_path.exists() and src_path.is_file():
        return send_from_directory(str(DASHBOARD_SRC), filename)
    if data_path.exists() and data_path.is_file():
        return send_from_directory(str(DASHBOARD_DATA), filename)

    # Strip a leading "data/" prefix — browsers resolve ../data/<f> relative to
    # the root as /data/<f>, but the files live directly in DASHBOARD_DATA.
    if filename.startswith("data/"):
        bare = filename[len("data/"):]
        bare_path = DASHBOARD_DATA / bare
        if bare_path.exists() and bare_path.is_file():
            return send_from_directory(str(DASHBOARD_DATA), bare)

    return Response("Not found", status=404)


# ── Draft Picks API ────────────────────────────────────────────────────────

@app.route("/api/picks", methods=["GET"])
def api_get_picks() -> Response:
    """Return the full pick universe and current ownership."""
    ownership = load_ownership()
    return jsonify({"picks": _PICKS, "ownership": ownership})


@app.route("/api/picks", methods=["POST"])
def api_save_picks() -> Response:
    """Accept an ownership object and persist it to disk.

    Accepts both the new format  {pick_id: {original_team, owner}}
    and the legacy format        {pick_id: string | null}  (auto-migrated).
    """
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Body must be a JSON object"}), 400

    normalized: dict = {}
    for pick_id, value in data.items():
        if value is None or isinstance(value, str):
            # Legacy format — treat string as both original_team and owner.
            normalized[pick_id] = {"original_team": value, "owner": value}
        elif isinstance(value, dict):
            ot = value.get("original_team")
            ow = value.get("owner")
            if ot is not None and not isinstance(ot, str):
                return jsonify({"ok": False,
                                "error": f"original_team for {pick_id!r} must be string or null"}), 400
            if ow is not None and not isinstance(ow, str):
                return jsonify({"ok": False,
                                "error": f"owner for {pick_id!r} must be string or null"}), 400
            normalized[pick_id] = {"original_team": ot, "owner": ow}
        else:
            return jsonify({"ok": False,
                            "error": f"Invalid ownership value for {pick_id!r}"}), 400

    valid_ids = {p["pick_id"] for p in _PICKS}
    unknown = [pid for pid in normalized if pid not in valid_ids]
    if unknown:
        return jsonify({
            "ok": False,
            "error": f"Unknown pick IDs: {unknown[:5]}",
        }), 400

    try:
        save_ownership(normalized)
    except Exception as exc:  # pragma: no cover
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True})


# ── League Config API ──────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_get_config() -> Response:
    """Return the editable subset of league config fields."""
    return jsonify({"config": get_editable_config(_CONFIG)})


@app.route("/api/config", methods=["POST"])
def api_save_config() -> Response:
    """Merge updates into the league config and persist."""
    global _CONFIG, _PICKS

    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Body must be a JSON object"}), 400

    try:
        updated = save_league_config(data)
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    _CONFIG = updated
    _PICKS = generate_picks(_CONFIG)

    return jsonify({"ok": True, "config": get_editable_config(_CONFIG)})


# ── Team Cap Adjustments API ───────────────────────────────────────────────

@app.route("/api/team-adjustments", methods=["GET"])
def api_get_team_adjustments() -> Response:
    """Return current team cap adjustments."""
    adjustments = load_team_adjustments()
    return jsonify({"adjustments": adjustments})


@app.route("/api/team-adjustments", methods=["POST"])
def api_save_team_adjustments() -> Response:
    """Validate and save team cap adjustments."""
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Body must be a JSON object"}), 400

    try:
        validate_team_adjustments(data)
        save_team_adjustments(data)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True})


# ── Roster Upload API ──────────────────────────────────────────────────────

@app.route("/api/roster-upload", methods=["POST"])
def api_roster_upload() -> Response:
    """Accept a multipart CSV upload, validate, and replace the backend roster."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"ok": False, "error": "No file selected"}), 400

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as tmp:
        uploaded.save(tmp)
        tmp_path = tmp.name

    try:
        result = validate_roster_csv(tmp_path)
        if not result["valid"]:
            Path(tmp_path).unlink(missing_ok=True)
            return jsonify({"ok": False, "error": result["error"]}), 400

        dest = _roster_csv_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(tmp_path, str(dest))

        return jsonify({"ok": True, "rows": result["rows"], "teams": result["teams"]})
    except Exception as exc:  # pragma: no cover
        Path(tmp_path).unlink(missing_ok=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── Recompute API ──────────────────────────────────────────────────────────

@app.route("/api/recompute", methods=["POST"])
def api_recompute() -> Response:
    """Re-run the Phase 3 analytical pipeline."""
    roster_path = _roster_csv_path()
    if not roster_path.exists():
        return jsonify({
            "ok": False,
            "error": f"Roster file not found at {roster_path}",
        }), 400

    t0 = time.time()
    try:
        exported = export_phase3_tables(
            roster_csv_path=str(roster_path),
            config=_CONFIG,
            output_dir=str(DEFAULT_OUTPUT_DIR),
            schedule_overrides_path=str(DEFAULT_SCHEDULE_OVERRIDES_CSV),
            tv_inputs_path=str(DEFAULT_TV_INPUTS_CSV),
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    duration_ms = int((time.time() - t0) * 1000)
    table_counts = {
        name: len(df) for name, df in exported.items()
        if hasattr(df, "__len__")
    }

    return jsonify({"ok": True, "duration_ms": duration_ms, "tables": table_counts})


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"ESV Fantasy Dashboard  →  http://localhost:{port}")
    print(f"Ownership file         →  {DEFAULT_OWNERSHIP_PATH}")
    app.run(host="0.0.0.0", port=port, debug=True)
