// League Config — Draft Pick Ownership Management
//
// Renders a per-year assignment grid where each row is one pick and each pick
// has a team dropdown. Saving POSTs the full ownership map to /api/picks.
//
// Ownership records use the new format: pick_id → {original_team, owner}.
// Years with order_known=false show a banner and placeholder slot labels.
//
// Graceful degradation: if /api/picks is not reachable (direct file serving),
// the panel shows pick data in read-only mode with a notice.

(function () {
  // ── State ─────────────────────────────────────────────────────────────────

  // Live ownership map: pick_id → {original_team: str|null, owner: str|null}.
  // Mutated as the user changes dropdowns; flushed to server on Save.
  let _ownership = {};

  // Full team list derived from ALL_LG_TEAMS + any assigned owners.
  let _teams = [];

  let _apiAvailable = false;
  let _initialized  = false;

  // ── Helpers ──────────────────────────────────────────────────────────────

  function getOwner(pick_id) {
    const rec = _ownership[pick_id];
    return (rec && rec.owner) ? rec.owner : null;
  }

  function getOriginalTeam(pick_id) {
    const rec = _ownership[pick_id];
    return (rec && rec.original_team) ? rec.original_team : null;
  }

  function collectTeams() {
    const base  = Array.isArray(ALL_LG_TEAMS) ? ALL_LG_TEAMS : [];
    const extra = Object.values(_ownership)
      .map(rec => rec && rec.owner)
      .filter(Boolean);
    return [...new Set([...base, ...extra])].sort();
  }

  function slotLabel(p) {
    if (p.order_known) {
      return `${p.round}.${String(p.slot).padStart(2, '0')}`;
    }
    // Slot number is a placeholder until draft order is set.
    return `Rd.${p.round} #${String(p.slot).padStart(2, '0')} (order TBD)`;
  }

  function salaryLabel(salary) {
    return salary != null ? `$${salary}` : '–';
  }

  // ── Rendering ─────────────────────────────────────────────────────────────

  function renderYearBlock(year, picks) {
    const orderKnown = picks.some(p => p.order_known);
    const banner = orderKnown ? '' :
      `<p class="dp-order-unknown-notice">
         Draft order not yet finalized — slot numbers are placeholders, not real positions.
       </p>`;

    const roundGroups = {};
    picks.forEach(p => {
      (roundGroups[p.round] = roundGroups[p.round] || []).push(p);
    });

    const roundHtml = Object.keys(roundGroups)
      .sort((a, b) => +a - +b)
      .map(rnd => {
        const roundPicks = roundGroups[rnd];
        const rows = roundPicks.map(p => {
          const owner    = getOwner(p.pick_id) || '';
          const origTeam = getOriginalTeam(p.pick_id) || '';
          const traded   = origTeam && owner && origTeam !== owner;
          const tradeTag = traded ? ' <span class="dp-traded-tag">traded</span>' : '';
          const compTag  = p.is_compensatory ? ' <span class="dp-comp-tag">comp</span>' : '';

          const options = ['', ..._teams].map(t =>
            `<option value="${t}" ${t === owner ? 'selected' : ''}>${t || '— unowned —'}</option>`
          ).join('');

          return `
            <tr data-pick-id="${p.pick_id}">
              <td class="mono">${slotLabel(p)}${compTag}</td>
              <td class="num">${salaryLabel(p.salary)}</td>
              <td class="dp-original-team">${origTeam || '—'}</td>
              <td>
                <select class="pick-owner-select" data-pick-id="${p.pick_id}">
                  ${options}
                </select>
                ${tradeTag}
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
                  <th>Originally Assigned</th>
                  <th>Current Owner</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>`;
      }).join('');

    return `
      <div class="dp-year-block">
        <h3 class="dp-year-title">${year} Draft</h3>
        ${banner}
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

    const byYear = {};
    DRAFT_PICKS_DATA.forEach(p => {
      (byYear[p.year] = byYear[p.year] || []).push(p);
    });

    container.innerHTML = Object.keys(byYear)
      .sort((a, b) => +a - +b)
      .map(y => renderYearBlock(+y, byYear[y]))
      .join('');

    // Wire up change listeners — only update owner, preserve original_team.
    container.querySelectorAll('.pick-owner-select').forEach(sel => {
      sel.addEventListener('change', () => {
        const pickId = sel.dataset.pickId;
        const existing = _ownership[pickId] || {original_team: null, owner: null};
        _ownership[pickId] = {...existing, owner: sel.value || null};
        // Refresh the traded tag inline without full re-render.
        const row = sel.closest('tr');
        if (row) {
          const origTeam = existing.original_team || '';
          const newOwner = sel.value || '';
          const traded   = origTeam && newOwner && origTeam !== newOwner;
          let tag = row.querySelector('.dp-traded-tag');
          if (traded && !tag) {
            tag = document.createElement('span');
            tag.className = 'dp-traded-tag';
            tag.textContent = 'traded';
            sel.parentNode.appendChild(tag);
          } else if (!traded && tag) {
            tag.remove();
          }
        }
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
    const saveBtn  = document.getElementById('dp-save-btn');
    const statusEl = document.getElementById('dp-save-status');
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

    const saveBtn = document.getElementById('dp-save-btn');
    if (saveBtn) saveBtn.addEventListener('click', saveOwnership);

    fetch('/api/picks')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(({ picks, ownership }) => {
        _apiAvailable = true;
        // ownership is now {pick_id: {original_team, owner}}.
        _ownership = Object.assign({}, ownership);
        DRAFT_PICKS_DATA = picks.map(p => ({
          ...p,
          owner: (ownership[p.pick_id] || {}).owner || null,
        }));
        ALL_PICK_YEARS = [...new Set(DRAFT_PICKS_DATA.map(p => p.year))].sort((a, b) => a - b);
        render();
      })
      .catch(() => {
        // Fall back to pre-loaded CSV data (read-only mode).
        _apiAvailable = false;
        _ownership = {};
        DRAFT_PICKS_DATA.forEach(p => {
          _ownership[p.pick_id] = {original_team: null, owner: p.owner || null};
        });
        render();
      });
  }

  window.initDraftPicks = initDraftPicks;
})();
