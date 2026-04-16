// League Config — Draft Pick Ownership Management
//
// Renders a per-year assignment grid where each row is one pick and each pick
// has a team dropdown. Saving POSTs the full ownership map to /api/picks.
//
// Graceful degradation: if /api/picks is not reachable (direct file serving),
// the panel shows pick data in read-only mode with a notice.

(function () {
  // ── State ─────────────────────────────────────────────────────────────────

  // Live ownership map: pick_id → team name (or null).
  // Mutated as the user changes dropdowns; flushed to server on Save.
  let _ownership = {};

  // Full team list derived from DRAFT_PICKS_DATA + any assigned owners.
  let _teams = [];

  // Whether the API is available (detected on first load attempt).
  let _apiAvailable = false;

  let _initialized = false;

  // ── Helpers ──────────────────────────────────────────────────────────────

  function collectTeams() {
    // Use ALL_LG_TEAMS (from contract surplus) as the authoritative team list,
    // supplemented by any teams already recorded in ownership.
    const base  = Array.isArray(ALL_LG_TEAMS) ? ALL_LG_TEAMS : [];
    const extra = Object.values(_ownership).filter(Boolean);
    return [...new Set([...base, ...extra])].sort();
  }

  function pickLabel(p) {
    return `${p.year} — ${p.round}.${String(p.slot).padStart(2, '0')}`;
  }

  function salaryLabel(salary) {
    return salary != null ? `$${salary}` : '–';
  }

  // ── Rendering ─────────────────────────────────────────────────────────────

  function renderYearBlock(year, picks) {
    const roundGroups = {};
    picks.forEach(p => {
      (roundGroups[p.round] = roundGroups[p.round] || []).push(p);
    });

    const roundHtml = Object.keys(roundGroups)
      .sort((a, b) => +a - +b)
      .map(rnd => {
        const roundPicks = roundGroups[rnd];
        const rows = roundPicks.map(p => {
          const owner = _ownership[p.pick_id] || '';
          const options = ['', ..._teams].map(t =>
            `<option value="${t}" ${t === owner ? 'selected' : ''}>${t || '— unowned —'}</option>`
          ).join('');
          return `
            <tr data-pick-id="${p.pick_id}">
              <td class="mono">${p.round}.${String(p.slot).padStart(2, '0')}</td>
              <td class="num">${salaryLabel(p.salary)}</td>
              <td>
                <select class="pick-owner-select" data-pick-id="${p.pick_id}">
                  ${options}
                </select>
              </td>
            </tr>`;
        }).join('');

        return `
          <div class="dp-round-block">
            <h4 class="dp-round-title">Round ${rnd}</h4>
            <table class="data-table dp-pick-table">
              <thead>
                <tr>
                  <th>Pick</th>
                  <th class="num">Salary</th>
                  <th>Assigned To</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>`;
      }).join('');

    return `
      <div class="dp-year-block">
        <h3 class="dp-year-title">${year} Draft</h3>
        <div class="dp-rounds">${roundHtml}</div>
      </div>`;
  }

  function render() {
    const container = document.getElementById('dp-years-container');
    const loading   = document.getElementById('dp-loading');
    const error     = document.getElementById('dp-error');
    if (!container) return;

    loading.hidden = true;
    error.hidden   = true;

    if (!DRAFT_PICKS_DATA || !DRAFT_PICKS_DATA.length) {
      error.textContent = 'No pick data available. Run scripts/export_draft_picks.py or start the Flask server.';
      error.hidden = false;
      return;
    }

    _teams = collectTeams();

    // Group by year
    const byYear = {};
    DRAFT_PICKS_DATA.forEach(p => {
      (byYear[p.year] = byYear[p.year] || []).push(p);
    });

    container.innerHTML = Object.keys(byYear)
      .sort((a, b) => +a - +b)
      .map(y => renderYearBlock(+y, byYear[y]))
      .join('');

    // Wire up change listeners on every dropdown
    container.querySelectorAll('.pick-owner-select').forEach(sel => {
      sel.addEventListener('change', () => {
        const pickId = sel.dataset.pickId;
        _ownership[pickId] = sel.value || null;
      });
    });

    if (!_apiAvailable) {
      showReadOnlyNotice();
    }
  }

  function showReadOnlyNotice() {
    const error = document.getElementById('dp-error');
    error.textContent =
      'Flask server not detected — pick assignments are display-only. ' +
      'Run `python dashboard/server.py` to enable saving.';
    error.hidden = false;

    const saveBtn = document.getElementById('dp-save-btn');
    if (saveBtn) saveBtn.disabled = true;
  }

  // ── Save ──────────────────────────────────────────────────────────────────

  function saveOwnership() {
    const saveBtn    = document.getElementById('dp-save-btn');
    const statusEl   = document.getElementById('dp-save-status');
    if (!saveBtn || !statusEl) return;

    saveBtn.disabled = true;
    statusEl.textContent = 'Saving…';
    statusEl.className   = 'save-status save-status-pending';
    statusEl.hidden      = false;

    fetch('/api/picks', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(_ownership),
    })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          statusEl.textContent = 'Saved successfully.';
          statusEl.className   = 'save-status save-status-ok';
        } else {
          statusEl.textContent = `Save failed: ${data.error || 'unknown error'}`;
          statusEl.className   = 'save-status save-status-error';
        }
      })
      .catch(err => {
        statusEl.textContent = `Network error: ${err.message}`;
        statusEl.className   = 'save-status save-status-error';
      })
      .finally(() => {
        saveBtn.disabled = false;
        setTimeout(() => { statusEl.hidden = true; }, 4000);
      });
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  function initDraftPicks() {
    if (_initialized) { render(); return; }
    _initialized = true;

    // Wire Save button
    const saveBtn = document.getElementById('dp-save-btn');
    if (saveBtn) saveBtn.addEventListener('click', saveOwnership);

    // Fetch fresh ownership from the API; render with whatever DRAFT_PICKS_DATA
    // already has (possibly populated by data.js) plus the live owner map.
    fetch('/api/picks')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(({ picks, ownership }) => {
        _apiAvailable = true;
        // Merge server-side ownership into our local state
        _ownership = Object.assign({}, ownership);
        // Also refresh DRAFT_PICKS_DATA with live owner values
        DRAFT_PICKS_DATA = picks.map(p => ({
          ...p,
          owner: ownership[p.pick_id] || null,
        }));
        ALL_PICK_YEARS = [...new Set(DRAFT_PICKS_DATA.map(p => p.year))].sort((a, b) => a - b);
        render();
      })
      .catch(() => {
        // Build local ownership state from pre-loaded CSV data
        _apiAvailable = false;
        _ownership = {};
        DRAFT_PICKS_DATA.forEach(p => {
          _ownership[p.pick_id] = p.owner || null;
        });
        render();
      });
  }

  window.initDraftPicks = initDraftPicks;
})();
