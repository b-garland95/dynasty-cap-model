// Draft Pick Ownership Management
//
// Layout per year:
//   - Known-order year (target_season with order set):
//       "Set Draft Order" section (slot assignments) + pick list with slots shown
//   - Unknown-order year (future years or target_season before order is set):
//       Pick list showing original team → current owner, no slot numbers
//
// Pick rows display: Original Team | Current Owner (dropdown)
// Comp picks appear at the bottom of each year section.
//
// Ownership uses the new format: pick_id → {original_team, owner, slot}.
// Graceful degradation: read-only when Flask server is unreachable.
//
// Draft year lifecycle status (year_status per year):
//   "active"    — picks are tradeable; draft has not occurred
//   "finalized" — draft order set but draft has not occurred
//   "completed" — draft occurred; picks are spent (read-only, greyed out)

(function () {
  // ── State ─────────────────────────────────────────────────────────────────

  // Full picks list returned by the server (includes original_team, order_known, etc.)
  let _picks = [];

  // Ownership map: pick_id → {original_team, owner, slot}
  let _ownership = {};

  // Year lifecycle status: {year: 'active'|'finalized'|'completed'}
  let _yearStatus = {};

  // Sorted unique team names for dropdowns.
  let _teams = [];

  let _apiAvailable = false;
  let _initialized  = false;

  // ── Helpers ──────────────────────────────────────────────────────────────

  function ownerOf(pick_id) {
    const rec = _ownership[pick_id];
    if (rec && rec.owner != null) return rec.owner;
    // Fall back to pick's original_team from _picks.
    const pick = _picks.find(p => p.pick_id === pick_id);
    return (pick && pick.original_team) || null;
  }

  function collectTeams() {
    const fromOwnership = Object.values(_ownership)
      .map(r => r && r.owner)
      .filter(Boolean);
    const fromPicks = _picks.map(p => p.original_team).filter(Boolean);
    const base = Array.isArray(ALL_LG_TEAMS) ? ALL_LG_TEAMS : [];
    return [...new Set([...base, ...fromOwnership, ...fromPicks])].sort();
  }

  function salaryLabel(s) {
    return s != null ? `$${s}` : '—';
  }

  function teamOption(value, selected) {
    return `<option value="${escHtml(value)}" ${value === selected ? 'selected' : ''}>${escHtml(value)}</option>`;
  }

  function escHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function yearStatusForYear(year, picksForYear) {
    // year_status from server takes priority; fall back to order_known inference.
    if (_yearStatus[year]) return _yearStatus[year];
    return picksForYear.some(p => p.order_known) ? 'finalized' : 'active';
  }

  // ── Rendering ─────────────────────────────────────────────────────────────

  function renderStatusBadge(status) {
    const labels = { active: 'Active', finalized: 'Finalized', completed: 'Completed' };
    return `<span class="dp-status-badge dp-status-badge--${escHtml(status)}">${escHtml(labels[status] || status)}</span>`;
  }

  function renderPickRow(pick, isCompleted) {
    const owner     = ownerOf(pick.pick_id) || '';
    const origTeam  = pick.original_team || '—';
    const traded    = pick.original_team && owner && pick.original_team !== owner;
    const tradeTag  = traded ? '<span class="dp-traded-tag">traded</span>' : '';

    if (isCompleted) {
      const slotCell = (pick.order_known && pick.slot != null)
        ? `<td class="dp-slot-cell mono">#${String(pick.slot).padStart(2, '0')}</td>`
        : '';
      return `
        <tr class="dp-pick-row--spent" data-pick-id="${escHtml(pick.pick_id)}">
          ${slotCell}
          <td class="dp-orig-team">${escHtml(origTeam)}</td>
          <td class="dp-salary-cell num">${salaryLabel(pick.salary)}</td>
          <td class="dp-owner-cell dp-owner-cell--spent">${escHtml(owner || '—')} ${tradeTag}</td>
        </tr>`;
    }

    const opts = ['', ..._teams]
      .map(t => `<option value="${escHtml(t)}" ${t === owner ? 'selected' : ''}>${t ? escHtml(t) : '— unowned —'}</option>`)
      .join('');

    const slotCell = (pick.order_known && pick.slot != null)
      ? `<td class="dp-slot-cell mono">#${String(pick.slot).padStart(2, '0')}</td>`
      : '';

    return `
      <tr data-pick-id="${escHtml(pick.pick_id)}">
        ${slotCell}
        <td class="dp-orig-team">${escHtml(origTeam)}</td>
        <td class="dp-salary-cell num">${salaryLabel(pick.salary)}</td>
        <td class="dp-owner-cell">
          <select class="pick-owner-select" data-pick-id="${escHtml(pick.pick_id)}">${opts}</select>
          ${tradeTag}
        </td>
      </tr>`;
  }

  function renderCompRow(pick, isCompleted) {
    const owner = ownerOf(pick.pick_id) || '';
    const slotStr = pick.slot != null ? `Slot ${pick.slot}` : '—';

    if (isCompleted) {
      return `
        <tr class="dp-pick-row--spent" data-pick-id="${escHtml(pick.pick_id)}">
          <td class="dp-comp-label">Comp · ${slotStr}</td>
          <td class="dp-salary-cell num">${salaryLabel(pick.salary)}</td>
          <td class="dp-owner-cell dp-owner-cell--spent" colspan="2">${escHtml(owner || '—')}</td>
        </tr>`;
    }

    const opts  = ['', ..._teams]
      .map(t => `<option value="${escHtml(t)}" ${t === owner ? 'selected' : ''}>${t ? escHtml(t) : '— unowned —'}</option>`)
      .join('');

    return `
      <tr data-pick-id="${escHtml(pick.pick_id)}">
        <td class="dp-comp-label">Comp · ${slotStr}</td>
        <td class="dp-salary-cell num">${salaryLabel(pick.salary)}</td>
        <td class="dp-owner-cell" colspan="2">
          <select class="pick-owner-select" data-pick-id="${escHtml(pick.pick_id)}">${opts}</select>
        </td>
      </tr>`;
  }

  function renderRoundSection(rnd, regularPicks, compPicks, orderKnown, isCompleted) {
    const hasSlot   = orderKnown;
    const slotHeader = hasSlot ? '<th class="dp-slot-th">Slot</th>' : '';

    const regRows  = regularPicks.map(p => renderPickRow(p, isCompleted)).join('');
    const compRows = compPicks.map(p => renderCompRow(p, isCompleted)).join('');
    const divider  = compRows
      ? `<tr class="dp-comp-divider"><td colspan="4" class="dp-comp-divider-cell">Compensatory Picks</td></tr>${compRows}`
      : '';

    return `
      <div class="dp-round-section">
        <h4 class="dp-round-label">Round ${rnd}</h4>
        <table class="dp-pick-table">
          <thead>
            <tr>
              ${slotHeader}
              <th>Original Team</th>
              <th class="num">Salary</th>
              <th>Current Owner</th>
            </tr>
          </thead>
          <tbody>
            ${regRows}
            ${divider}
          </tbody>
        </table>
      </div>`;
  }

  function renderDraftOrderSection(year, picksForYear) {
    // Only for the target season — allows the user to assign slots.
    const numTeams  = _teams.length;
    if (!numTeams) return '';

    const slotRows = Array.from({length: numTeams}, (_, i) => {
      const slot = i + 1;
      // Find who is currently assigned to this slot for round 1 of this year.
      const assignedPick = picksForYear.find(
        p => !p.is_compensatory && p.slot === slot && p.round === 1
      );
      const currentTeam = assignedPick ? (assignedPick.original_team || '') : '';
      const opts = ['', ..._teams]
        .map(t => `<option value="${escHtml(t)}" ${t === currentTeam ? 'selected' : ''}>${t ? escHtml(t) : '— select team —'}</option>`)
        .join('');
      return `
        <div class="dp-order-row">
          <span class="dp-order-slot">#${slot}</span>
          <select class="dp-order-select" data-slot="${slot}">${opts}</select>
        </div>`;
    }).join('');

    return `
      <div class="dp-order-section" id="dp-order-${year}">
        <details>
          <summary class="dp-order-summary">Set Draft Order (${year})</summary>
          <div class="dp-order-body">
            <p class="dp-order-hint">Assign each slot position to a team. Applies to all rounds.</p>
            <div class="dp-order-grid">${slotRows}</div>
            <button class="dp-apply-order-btn action-btn" data-year="${year}">Apply Order</button>
            <span class="dp-order-status" hidden></span>
          </div>
        </details>
      </div>`;
  }

  function renderCompleteButton(year, status) {
    if (status === 'completed') return '';
    return `
      <button class="dp-complete-btn action-btn action-btn--warn" data-year="${year}"
              title="Mark this draft year as completed. All picks become spent inventory.">
        Mark Draft Complete
      </button>
      <span class="dp-complete-status" hidden></span>`;
  }

  function renderYearBlock(year, picksForYear, isTargetSeason) {
    const orderKnown  = picksForYear.some(p => p.order_known);
    const roundNums   = [...new Set(picksForYear.map(p => p.round))].sort((a, b) => a - b);
    const status      = yearStatusForYear(year, picksForYear);
    const isCompleted = status === 'completed';

    const notice = (!orderKnown && !isTargetSeason && !isCompleted)
      ? `<p class="dp-order-unknown-notice">Draft order not yet set — picks are identified by original team, not slot.</p>`
      : '';

    const spentNotice = isCompleted
      ? `<p class="dp-spent-notice">This draft has been completed. All picks from ${year} are spent inventory.</p>`
      : '';

    const orderSection = (isTargetSeason && !isCompleted)
      ? renderDraftOrderSection(year, picksForYear)
      : '';

    const rounds = roundNums.map(rnd => {
      const reg  = picksForYear.filter(p => p.round === rnd && !p.is_compensatory);
      const comp = picksForYear.filter(p => p.round === rnd && p.is_compensatory);
      return renderRoundSection(rnd, reg, comp, orderKnown, isCompleted);
    }).join('');

    return `
      <div class="dp-year-block ${isCompleted ? 'dp-year-block--completed' : ''}" data-year="${year}">
        <div class="dp-year-header">
          <h3 class="dp-year-title">${year} Draft</h3>
          ${renderStatusBadge(status)}
          ${_apiAvailable ? renderCompleteButton(year, status) : ''}
        </div>
        ${spentNotice}
        ${notice}
        ${orderSection}
        <div class="dp-rounds-list">${rounds}</div>
      </div>`;
  }

  // ── Main render ────────────────────────────────────────────────────────────

  function render() {
    const container = document.getElementById('dp-years-container');
    const loading   = document.getElementById('dp-loading');
    const error     = document.getElementById('dp-error');
    if (!container) return;

    loading.hidden = true;
    error.hidden   = true;

    _teams = collectTeams();

    if (!_picks.length) {
      if (_apiAvailable) {
        error.textContent = 'No picks found. Use "Initialize Teams" below or register teams via the API.';
      } else {
        error.textContent = 'No pick data available. Start the Flask server to enable pick management.';
      }
      error.hidden = false;
    }

    const targetSeason = getTargetSeason();
    const byYear = {};
    _picks.forEach(p => { (byYear[p.year] = byYear[p.year] || []).push(p); });

    container.innerHTML = Object.keys(byYear)
      .sort((a, b) => +a - +b)
      .map(y => renderYearBlock(+y, byYear[y], +y === targetSeason))
      .join('');

    // Wire dropdowns (only active/finalized years have editable selects).
    container.querySelectorAll('.pick-owner-select').forEach(sel => {
      sel.addEventListener('change', () => {
        const pickId  = sel.dataset.pickId;
        const existing = _ownership[pickId] || {original_team: null, owner: null, slot: null};
        _ownership[pickId] = {...existing, owner: sel.value || null};
        // Refresh traded badge.
        const row = sel.closest('tr');
        if (row) {
          const orig = existing.original_team || '';
          const nw   = sel.value || '';
          const traded = orig && nw && orig !== nw;
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

    // Wire draft-order apply buttons.
    container.querySelectorAll('.dp-apply-order-btn').forEach(btn => {
      btn.addEventListener('click', () => applyDraftOrder(btn));
    });

    // Wire "Mark Draft Complete" buttons.
    container.querySelectorAll('.dp-complete-btn').forEach(btn => {
      btn.addEventListener('click', () => completeDraftYear(btn));
    });

    if (!_apiAvailable) showReadOnlyNotice();
  }

  function getTargetSeason() {
    // Prefer server config; fall back to smallest pick year + 0.
    if (LEAGUE_CONFIG && LEAGUE_CONFIG['season.target_season']) {
      return +LEAGUE_CONFIG['season.target_season'];
    }
    const years = [...new Set(_picks.map(p => p.year))].sort((a, b) => a - b);
    return years[0] || 0;
  }

  // ── Draft order ───────────────────────────────────────────────────────────

  function applyDraftOrder(btn) {
    const year    = +btn.dataset.year;
    const section = btn.closest('.dp-order-section');
    const selects = section.querySelectorAll('.dp-order-select');
    const status  = section.querySelector('.dp-order-status');

    const order = [];
    for (const sel of selects) {
      if (!sel.value) {
        status.textContent = `Slot #${sel.dataset.slot} has no team assigned.`;
        status.hidden = false;
        return;
      }
      order.push(sel.value);
    }

    const unique = new Set(order);
    if (unique.size !== order.length) {
      status.textContent = 'Each team must appear exactly once in the draft order.';
      status.hidden = false;
      return;
    }

    btn.disabled = true;
    status.textContent = 'Applying…';
    status.hidden = false;

    fetch('/api/picks/draft-order', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({year, order}),
    })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          _picks      = data.picks;
          _ownership  = data.ownership;
          _yearStatus = data.year_status || {};
          status.textContent = 'Draft order set.';
          render();
        } else {
          status.textContent = `Error: ${data.error}`;
        }
      })
      .catch(err => { status.textContent = `Network error: ${err.message}`; })
      .finally(() => { btn.disabled = false; });
  }

  // ── Mark draft year complete ──────────────────────────────────────────────

  function completeDraftYear(btn) {
    const year       = +btn.dataset.year;
    const yearBlock  = btn.closest('.dp-year-block');
    const statusEl   = yearBlock ? yearBlock.querySelector('.dp-complete-status') : null;

    const confirmed = window.confirm(
      `Mark the ${year} draft as completed?\n\n` +
      `All ${year} picks will be treated as spent inventory and removed from active trading views. ` +
      `This cannot be undone from the UI.`
    );
    if (!confirmed) return;

    btn.disabled = true;
    if (statusEl) { statusEl.textContent = 'Saving…'; statusEl.hidden = false; }

    fetch('/api/picks/complete-year', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({year}),
    })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          _picks      = data.picks;
          _ownership  = data.ownership;
          _yearStatus = data.year_status || {};
          // Sync DRAFT_PICKS_DATA for other views.
          DRAFT_PICKS_DATA = _picks.map(p => ({
            ...p,
            owner: (_ownership[p.pick_id] || {}).owner || p.original_team || null,
          }));
          ALL_PICK_YEARS = [...new Set(DRAFT_PICKS_DATA.map(p => p.year))].sort((a, b) => a - b);
          render();
        } else {
          if (statusEl) { statusEl.textContent = `Error: ${data.error}`; }
          btn.disabled = false;
        }
      })
      .catch(err => {
        if (statusEl) { statusEl.textContent = `Network error: ${err.message}`; }
        btn.disabled = false;
      });
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
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify(_ownership),
    })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          statusEl.textContent = 'Saved.';
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

    document.getElementById('dp-save-btn')
      ?.addEventListener('click', saveOwnership);

    fetch('/api/picks')
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(({picks, ownership, year_status}) => {
        _apiAvailable = true;
        _picks        = picks;
        _ownership    = ownership;
        _yearStatus   = year_status || {};

        // If no team picks exist yet but ALL_LG_TEAMS is available, auto-register.
        const hasTeamPicks = picks.some(p => !p.is_compensatory);
        if (!hasTeamPicks && Array.isArray(ALL_LG_TEAMS) && ALL_LG_TEAMS.length) {
          return fetch('/api/picks/init-teams', {
            method:  'POST',
            headers: {'Content-Type': 'application/json'},
            body:    JSON.stringify({teams: ALL_LG_TEAMS}),
          })
            .then(r => r.json())
            .then(data => {
              if (data.ok) {
                _picks      = data.picks;
                _ownership  = data.ownership;
                _yearStatus = data.year_status || {};
              }
            });
        }
      })
      .then(() => {
        // Keep DRAFT_PICKS_DATA in sync for other views that use it.
        DRAFT_PICKS_DATA = _picks.map(p => ({
          ...p,
          owner: (_ownership[p.pick_id] || {}).owner || p.original_team || null,
        }));
        ALL_PICK_YEARS = [...new Set(DRAFT_PICKS_DATA.map(p => p.year))].sort((a, b) => a - b);
        render();
      })
      .catch(() => {
        _apiAvailable = false;
        // Fall back to pre-loaded CSV data.
        _picks = DRAFT_PICKS_DATA.map(p => ({...p, order_known: false, is_compensatory: false}));
        _ownership = {};
        _picks.forEach(p => {
          _ownership[p.pick_id] = {
            original_team: p.original_team || null,
            owner: p.owner || null,
            slot: p.slot || null,
          };
        });
        render();
      });
  }

  window.initDraftPicks = initDraftPicks;
})();
