"""Minimal Flask server for the ESV Fantasy Dashboard.

Serves the static dashboard files and exposes a REST API for draft pick
ownership management.

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
      Returns JSON: { picks: [...], ownership: {...} }
      picks   – full pick universe from league config
      ownership – current owner map from draft_pick_ownership.json

  POST /api/picks
      Body: JSON object { pick_id: team_name_or_null, ... }
      Saves ownership to draft_pick_ownership.json.
      Returns: { ok: true } on success, { ok: false, error: "..." } on failure.
"""

from __future__ import annotations

import sys
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
from src.utils.config import load_league_config

# ── Paths ──────────────────────────────────────────────────────────────────
DASHBOARD_SRC  = REPO_ROOT / "dashboard" / "src"
DASHBOARD_DATA = REPO_ROOT / "dashboard" / "data"

app = Flask(__name__, static_folder=None)

# ── Config — loaded once at startup ────────────────────────────────────────
_CONFIG = load_league_config()
_PICKS  = generate_picks(_CONFIG)


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

    return Response("Not found", status=404)


# ── API ─────────────────────────────────────────────────────────────────────

@app.route("/api/picks", methods=["GET"])
def api_get_picks() -> Response:
    """Return the full pick universe and current ownership."""
    ownership = load_ownership()
    return jsonify({"picks": _PICKS, "ownership": ownership})


@app.route("/api/picks", methods=["POST"])
def api_save_picks() -> Response:
    """Accept an ownership object and persist it to disk."""
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Body must be a JSON object"}), 400

    # Validate: every value must be a string (team name) or null.
    for pick_id, owner in data.items():
        if owner is not None and not isinstance(owner, str):
            return jsonify({
                "ok": False,
                "error": f"Owner for {pick_id!r} must be a string or null",
            }), 400

    # Validate: pick_ids must be in the known pick universe.
    valid_ids = {p["pick_id"] for p in _PICKS}
    unknown = [pid for pid in data if pid not in valid_ids]
    if unknown:
        return jsonify({
            "ok": False,
            "error": f"Unknown pick IDs: {unknown[:5]}",
        }), 400

    try:
        save_ownership(data)
    except Exception as exc:  # pragma: no cover
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True})


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"ESV Fantasy Dashboard  →  http://localhost:{port}")
    print(f"Ownership file         →  {DEFAULT_OWNERSHIP_PATH}")
    app.run(host="0.0.0.0", port=port, debug=True)
