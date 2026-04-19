// Phase 3 — League Analysis
// Two sub-tabs: Contract Surplus (sortable table) and Cap Health (bar chart + table).
// Both views support a valuation-window selector: "1yr" (this year), "3yr" (3-year avg),
// or "5yr" (5-year avg).  Window-based metrics are annualized so the per-year values
// are directly comparable across different time horizons.

(function () {
  // ── State ─────────────────────────────────────────────────────────────────
  let capChartInstance  = null;
  let surplusSortKey    = 'surplus_1yr';
  let surplusSortAsc    = false;
  let surplusFilter     = { position: 'All', team: 'All' };
  let valuationWindow   = '1yr';   // '1yr' | '3yr' | '5yr'

  // ── Window field maps ─────────────────────────────────────────────────────
  // Maps a window key to the player-level and team-level field names used for
  // projected value, cap hit, and surplus.

  const PLAYER_FIELDS = {
    '1yr': { value: 'value_1yr',     cap: 'cap_1yr',     surplus: 'surplus_1yr'     },
    '3yr': { value: 'value_3yr_ann', cap: 'cap_3yr_ann', surplus: 'surplus_3yr_ann' },
    '5yr': { value: 'value_5yr_ann', cap: 'cap_5yr_ann', surplus: 'surplus_5yr_ann' },
  };

  const TEAM_FIELDS = {
    '1yr': { value: 'total_value_1yr',     cap: 'total_cap_1yr',     surplus: 'total_surplus_1yr'     },
    '3yr': { value: 'total_value_3yr_ann', cap: 'total_cap_3yr_ann', surplus: 'total_surplus_3yr_ann' },
    '5yr': { value: 'total_value_5yr_ann', cap: 'total_cap_5yr_ann', surplus: 'total_surplus_5yr_ann' },
  };

  const WINDOW_LABELS = {
    '1yr': { value: 'This Year\'s Value', cap: 'This Year\'s Cap Hit', surplus: 'This Year\'s Surplus', yAxis: 'Value ($)' },
    '3yr': { value: '3-Yr Avg Value',     cap: '3-Yr Avg Cap Hit',     surplus: '3-Yr Avg Surplus',     yAxis: 'Avg Annual Value ($)' },
    '5yr': { value: '5-Yr Avg Value',     cap: '5-Yr Avg Cap Hit',     surplus: '5-Yr Avg Surplus',     yAxis: 'Avg Annual Value ($)' },
  };

  // ── Helpers ───────────────────────────────────────────────────────────────

  function fmt1(v) { return typeof v === 'number' ? v.toFixed(1) : '–'; }

  function surplusColor(v) {
    if (v > 20)  return 'var(--surplus-high)';
    if (v > 0)   return 'var(--surplus-pos)';
    if (v > -10) return 'var(--surplus-neg)';
    return 'var(--surplus-low)';
  }

  function playerFields() { return PLAYER_FIELDS[valuationWindow]; }
  function teamFields()   { return TEAM_FIELDS[valuationWindow]; }
  function windowLabels() { return WINDOW_LABELS[valuationWindow]; }

  // ── Contract Surplus ──────────────────────────────────────────────────────

  function getFilteredSurplus() {
    return SURPLUS_DATA.filter(r => {
      if (surplusFilter.position !== 'All' && r.position !== surplusFilter.position) return false;
      if (surplusFilter.team !== 'All' && r.team !== surplusFilter.team) return false;
      return true;
    });
  }

  function updateSurplusHeaders() {
    const labels = windowLabels();
    const fields = playerFields();

    const valueHdr   = document.getElementById('surplus-col-value');
    const capHdr     = document.getElementById('surplus-col-cap');
    const surplusHdr = document.getElementById('surplus-col-surplus');

    if (valueHdr) {
      valueHdr.textContent = labels.value + ' ↕';
      valueHdr.dataset.sort = fields.value;
      valueHdr.style.cursor = 'pointer';
    }
    if (capHdr) {
      capHdr.textContent = labels.cap + ' ↕';
      capHdr.dataset.sort = fields.cap;
      capHdr.style.cursor = 'pointer';
    }
    if (surplusHdr) {
      surplusHdr.textContent = labels.surplus + ' ↕';
      surplusHdr.dataset.sort = fields.surplus;
      surplusHdr.style.cursor = 'pointer';
    }

    // Re-wire sort listeners on dynamically labelled columns.
    [valueHdr, capHdr, surplusHdr].forEach(th => {
      if (!th) return;
      th.onclick = () => {
        if (surplusSortKey === th.dataset.sort) {
          surplusSortAsc = !surplusSortAsc;
        } else {
          surplusSortKey = th.dataset.sort;
          surplusSortAsc = false;
        }
        document.querySelectorAll('#surplus-table thead th').forEach(h => {
          h.classList.remove('sort-asc', 'sort-desc');
        });
        th.classList.add(surplusSortAsc ? 'sort-asc' : 'sort-desc');
        renderSurplusTable(getFilteredSurplus());
      };
    });
  }

  function renderSurplusTable(rows) {
    const tbody = document.getElementById('surplus-table-body');
    if (!tbody) return;

    const fields = playerFields();

    const sorted = rows.slice().sort((a, b) => {
      const av = a[surplusSortKey] ?? 0;
      const bv = b[surplusSortKey] ?? 0;
      return surplusSortAsc ? av - bv : bv - av;
    });

    tbody.innerHTML = sorted.map(r => {
      const surpVal   = r[fields.surplus] ?? 0;
      const surpColor = surplusColor(surpVal);
      const validFlag = r.needs_schedule_validation
        ? '<span class="validation-flag" title="Schedule needs validation">⚠</span>'
        : '';
      return `
        <tr>
          <td>${playerLink(r.player)}${validFlag}</td>
          <td class="team-cell">${r.team}</td>
          <td><span class="pos-badge pos-${r.position.toLowerCase()}">${r.position}</span></td>
          <td class="num">${fmt1(r[fields.value])}</td>
          <td class="num">${fmt1(r[fields.cap])}</td>
          <td class="num surplus-cell" style="color:${surpColor};">${fmt1(surpVal)}</td>
          <td class="num">${fmt1(r.cap_today_current)}</td>
          <td class="num">${fmt1(r.dead_money_cut_now_nominal)}</td>
        </tr>
      `;
    }).join('');
  }

  function buildLeagueTeamOptions(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="All">All Teams</option>';
    ALL_LG_TEAMS.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t; opt.textContent = t;
      sel.appendChild(opt);
    });
    if ([...sel.options].some(o => o.value === current)) sel.value = current;
  }

  function refreshSurplus() {
    // Reset sort to surplus for active window when window changes.
    surplusSortKey = playerFields().surplus;
    updateSurplusHeaders();
    renderSurplusTable(getFilteredSurplus());
  }

  // ── Cap Health ────────────────────────────────────────────────────────────

  function updateCapHeaders() {
    const labels = windowLabels();
    const valueHdr   = document.getElementById('cap-col-value');
    const capHdr     = document.getElementById('cap-col-cap');
    const surplusHdr = document.getElementById('cap-col-surplus');
    if (valueHdr)   valueHdr.textContent   = labels.value;
    if (capHdr)     capHdr.textContent     = labels.cap;
    if (surplusHdr) surplusHdr.textContent = labels.surplus;
  }

  function renderCapChart() {
    if (capChartInstance) { capChartInstance.destroy(); capChartInstance = null; }
    const ctx = document.getElementById('chart-cap-health');
    if (!ctx || !CAP_HEALTH_DATA.length) return;

    const fields = teamFields();
    const labels = windowLabels();

    const sorted = CAP_HEALTH_DATA.slice().sort((a, b) => b[fields.surplus] - a[fields.surplus]);

    // Short team labels — take part after " | " if present, else use full name
    const teamLabels = sorted.map(r => {
      const parts = r.team.split('|');
      return parts.length > 1 ? parts[parts.length - 1].trim() : r.team;
    });

    capChartInstance = new Chart(ctx.getContext('2d'), {
      type: 'bar',
      data: {
        labels: teamLabels,
        datasets: [
          {
            label: labels.value,
            data: sorted.map(r => +r[fields.value].toFixed(1)),
            backgroundColor: hexToRgba(THEME.accent, 0.6),
            borderColor:     THEME.accent,
            borderWidth: 1,
            borderRadius: 3,
          },
          {
            label: labels.cap,
            data: sorted.map(r => +r[fields.cap].toFixed(1)),
            backgroundColor: hexToRgba('#e06c75', 0.55),
            borderColor:     '#e06c75',
            borderWidth: 1,
            borderRadius: 3,
          },
        ]
      },
      options: {
        ...CHART_DEFAULTS,
        plugins: {
          ...CHART_DEFAULTS.plugins,
          legend: { ...CHART_DEFAULTS.plugins.legend, display: true },
          tooltip: {
            ...CHART_DEFAULTS.plugins.tooltip,
            callbacks: {
              title: ctx2 => sorted[ctx2[0].dataIndex]?.team ?? '',
              label: ctx2 => {
                const r = sorted[ctx2[0]?.dataIndex ?? ctx2.dataIndex];
                if (!r) return '';
                return [
                  ` ${labels.value}: $${r[fields.value].toFixed(1)}`,
                  ` ${labels.cap}: $${r[fields.cap].toFixed(1)}`,
                  ` ${labels.surplus}: $${r[fields.surplus].toFixed(1)}`,
                  ` Dead $: $${r.dead_money_cut_now_nominal.toFixed(1)}`,
                ];
              }
            }
          }
        },
        scales: {
          x: { ...CHART_DEFAULTS.scales.x, ticks: { ...CHART_DEFAULTS.scales.x.ticks, maxRotation: 35, minRotation: 20 } },
          y: {
            ...CHART_DEFAULTS.scales.y,
            title: { display: true, text: labels.yAxis, color: THEME.muted, font: { size: 11 } }
          }
        }
      }
    });
  }

  function computeCapRemaining(team, currentCapUsage) {
    const baseCap = (typeof LEAGUE_CONFIG !== 'undefined' && LEAGUE_CONFIG['cap.base_cap']) || 0;
    const adj = (typeof TEAM_ADJUSTMENTS !== 'undefined' && TEAM_ADJUSTMENTS[team]) || {};
    const dm = +(adj.dead_money || 0);
    const ct = +(adj.cap_transactions || 0);
    const ro = +(adj.rollover || 0);
    return baseCap - currentCapUsage - dm - ct + ro;
  }

  function renderCapTable() {
    const tbody = document.getElementById('cap-table-body');
    if (!tbody) return;

    const fields = teamFields();

    const sorted = CAP_HEALTH_DATA.slice().sort((a, b) => b[fields.surplus] - a[fields.surplus]);

    tbody.innerHTML = sorted.map(r => {
      const surpColor = surplusColor(r[fields.surplus]);
      const capRemaining = computeCapRemaining(r.team, r.current_cap_usage);
      const crColor = capRemaining >= 0 ? 'var(--surplus-pos)' : 'var(--surplus-neg)';
      return `
        <tr>
          <td>${r.team}</td>
          <td class="num">${fmt1(r.current_cap_usage)}</td>
          <td class="num" style="color:${crColor};">${fmt1(capRemaining)}</td>
          <td class="num">${fmt1(r[fields.value])}</td>
          <td class="num">${fmt1(r[fields.cap])}</td>
          <td class="num surplus-cell" style="color:${surpColor};">${fmt1(r[fields.surplus])}</td>
          <td class="num">${fmt1(r.dead_money_cut_now_nominal)}</td>
        </tr>
      `;
    }).join('');
  }

  function refreshCap() {
    updateCapHeaders();
    renderCapChart();
    renderCapTable();
  }

  // ── Pick Inventory ────────────────────────────────────────────────────────

  let _piYearFilter = 'All';
  let _piTeamFilter = 'All';

  function buildPickInventoryFilters() {
    const yearSel = document.getElementById('pi-year');
    const teamSel = document.getElementById('pi-team');
    if (!yearSel || !teamSel) return;

    // Populate year options
    const curYear = yearSel.value;
    yearSel.innerHTML = '<option value="All">All Years</option>';
    (ALL_PICK_YEARS || []).forEach(y => {
      const opt = document.createElement('option');
      opt.value = y; opt.textContent = y;
      yearSel.appendChild(opt);
    });
    if ([...yearSel.options].some(o => o.value === curYear)) yearSel.value = curYear;

    // Populate team options from owners in pick data + contract teams
    const teamsInPicks = [...new Set(
      (DRAFT_PICKS_DATA || []).map(p => p.owner).filter(Boolean)
    )].sort();
    const allTeams = [...new Set([
      ...(ALL_LG_TEAMS || []),
      ...teamsInPicks,
    ])].sort();

    const curTeam = teamSel.value;
    teamSel.innerHTML = '<option value="All">All Teams</option>';
    allTeams.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t; opt.textContent = t;
      teamSel.appendChild(opt);
    });
    if ([...teamSel.options].some(o => o.value === curTeam)) teamSel.value = curTeam;
  }

  function getFilteredPicks() {
    return (DRAFT_PICKS_DATA || []).filter(p => {
      if (_piYearFilter !== 'All' && String(p.year) !== String(_piYearFilter)) return false;
      if (_piTeamFilter !== 'All' && p.owner !== _piTeamFilter) return false;
      return true;
    });
  }

  function renderPickInventory() {
    const tbody = document.getElementById('pick-inventory-tbody');
    if (!tbody) return;

    buildPickInventoryFilters();
    const rows = getFilteredPicks();

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--muted);">No picks match the current filter.</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(p => `
      <tr>
        <td class="mono">${p.pick_id}</td>
        <td>${p.year}</td>
        <td>${p.round}</td>
        <td>${p.slot}</td>
        <td class="num">${p.salary != null ? '$' + p.salary : '–'}</td>
        <td>${p.owner || '<span style="color:var(--muted)">–</span>'}</td>
      </tr>`).join('');
  }

  // ── Sub-tab switching ─────────────────────────────────────────────────────

  function switchLeagueTab(tabId) {
    document.querySelectorAll('#panel-league .sub-tab-panel').forEach(p => {
      p.hidden = p.id !== `sub-${tabId}`;
    });
    document.querySelectorAll('#panel-league .sub-tab-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.subtab === tabId);
    });

    if (tabId === 'contract-surplus') refreshSurplus();
    if (tabId === 'cap-health')       refreshCap();
    if (tabId === 'pick-inventory')   renderPickInventory();
    if (tabId === 'free-agent-market' && typeof window.refreshFreeAgentMarket === 'function') {
      window.refreshFreeAgentMarket();
    }
    if (tabId === 'trade-proposal' && typeof window.refreshTradeProposal === 'function') {
      window.refreshTradeProposal();
    }
  }

  // ── Init ─────────────────────────────────────────────────────────────────

  let _initialized = false;

  function initLeague() {
    if (_initialized) return;
    _initialized = true;

    buildLeagueTeamOptions('surplus-team');

    // Sub-tab buttons
    document.querySelectorAll('#panel-league .sub-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => switchLeagueTab(btn.dataset.subtab));
    });

    // Surplus window selector
    const surplusWindowSel = document.getElementById('surplus-window');
    if (surplusWindowSel) {
      surplusWindowSel.addEventListener('change', () => {
        valuationWindow = surplusWindowSel.value;
        // Keep cap-window in sync
        const capWindowSel = document.getElementById('cap-window');
        if (capWindowSel) capWindowSel.value = valuationWindow;
        refreshSurplus();
      });
    }

    // Cap Health window selector
    const capWindowSel = document.getElementById('cap-window');
    if (capWindowSel) {
      capWindowSel.addEventListener('change', () => {
        valuationWindow = capWindowSel.value;
        // Keep surplus-window in sync
        const surpWin = document.getElementById('surplus-window');
        if (surpWin) surpWin.value = valuationWindow;
        refreshCap();
      });
    }

    // Surplus position/team filters
    ['surplus-position', 'surplus-team'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('change', () => {
        if (id === 'surplus-position') surplusFilter.position = el.value;
        if (id === 'surplus-team')     surplusFilter.team     = el.value;
        renderSurplusTable(getFilteredSurplus());
      });
    });

    // Surplus column sort for static columns (Cap Today, Dead $)
    document.querySelectorAll('#surplus-table thead th[data-sort]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        if (surplusSortKey === th.dataset.sort) {
          surplusSortAsc = !surplusSortAsc;
        } else {
          surplusSortKey = th.dataset.sort;
          surplusSortAsc = false;
        }
        document.querySelectorAll('#surplus-table thead th').forEach(h => {
          h.classList.remove('sort-asc', 'sort-desc');
        });
        th.classList.add(surplusSortAsc ? 'sort-asc' : 'sort-desc');
        renderSurplusTable(getFilteredSurplus());
      });
    });

    // Pick Inventory filters
    const piYearSel = document.getElementById('pi-year');
    const piTeamSel = document.getElementById('pi-team');
    if (piYearSel) {
      piYearSel.addEventListener('change', () => {
        _piYearFilter = piYearSel.value;
        renderPickInventory();
      });
    }
    if (piTeamSel) {
      piTeamSel.addEventListener('change', () => {
        _piTeamFilter = piTeamSel.value;
        renderPickInventory();
      });
    }

    // Default: Contract Surplus sub-tab
    switchLeagueTab('contract-surplus');
  }

  window.initLeague = initLeague;
})();
