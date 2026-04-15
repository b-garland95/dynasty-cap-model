// Phase 3 — League Analysis
// Two sub-tabs: Contract Surplus (sortable table) and Cap Health (bar chart + table).

(function () {
  // ── State ─────────────────────────────────────────────────────────────────
  let capChartInstance = null;
  let surplusSortKey   = 'surplus_value';
  let surplusSortAsc   = false;
  let surplusFilter    = { position: 'All', team: 'All' };

  // ── Helpers ───────────────────────────────────────────────────────────────

  function fmt1(v) { return typeof v === 'number' ? v.toFixed(1) : '–'; }

  function surplusColor(v) {
    if (v > 20)  return 'var(--surplus-high)';
    if (v > 0)   return 'var(--surplus-pos)';
    if (v > -10) return 'var(--surplus-neg)';
    return 'var(--surplus-low)';
  }

  // ── Contract Surplus ──────────────────────────────────────────────────────

  function getFilteredSurplus() {
    return SURPLUS_DATA.filter(r => {
      if (surplusFilter.position !== 'All' && r.position !== surplusFilter.position) return false;
      if (surplusFilter.team !== 'All' && r.team !== surplusFilter.team) return false;
      return true;
    });
  }

  function renderSurplusTable(rows) {
    const tbody = document.getElementById('surplus-table-body');
    if (!tbody) return;

    const sorted = rows.slice().sort((a, b) => {
      const av = a[surplusSortKey] ?? 0;
      const bv = b[surplusSortKey] ?? 0;
      return surplusSortAsc ? av - bv : bv - av;
    });

    tbody.innerHTML = sorted.map(r => {
      const surpColor = surplusColor(r.surplus_value);
      const validFlag = r.needs_schedule_validation
        ? '<span class="validation-flag" title="Schedule needs validation">⚠</span>'
        : '';
      return `
        <tr>
          <td>${playerLink(r.player)}${validFlag}</td>
          <td class="team-cell">${r.team}</td>
          <td><span class="pos-badge pos-${r.position.toLowerCase()}">${r.position}</span></td>
          <td class="num">${fmt1(r.pv_tv)}</td>
          <td class="num">${fmt1(r.pv_cap)}</td>
          <td class="num surplus-cell" style="color:${surpColor};">${fmt1(r.surplus_value)}</td>
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
    renderSurplusTable(getFilteredSurplus());
  }

  // ── Cap Health ────────────────────────────────────────────────────────────

  function renderCapChart() {
    if (capChartInstance) { capChartInstance.destroy(); capChartInstance = null; }
    const ctx = document.getElementById('chart-cap-health');
    if (!ctx || !CAP_HEALTH_DATA.length) return;

    const sorted = CAP_HEALTH_DATA.slice().sort((a, b) => b.total_surplus - a.total_surplus);

    // Short team labels — take part after " | " if present, else use full name
    const labels = sorted.map(r => {
      const parts = r.team.split('|');
      return parts.length > 1 ? parts[parts.length - 1].trim() : r.team;
    });

    capChartInstance = new Chart(ctx.getContext('2d'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'PV TV',
            data: sorted.map(r => +r.total_pv_tv.toFixed(1)),
            backgroundColor: hexToRgba(THEME.accent, 0.6),
            borderColor:     THEME.accent,
            borderWidth: 1,
            borderRadius: 3,
          },
          {
            label: 'PV Cap',
            data: sorted.map(r => +r.total_pv_cap.toFixed(1)),
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
                  ` PV TV: $${r.total_pv_tv.toFixed(1)}`,
                  ` PV Cap: $${r.total_pv_cap.toFixed(1)}`,
                  ` Surplus: $${r.total_surplus.toFixed(1)}`,
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
            title: { display: true, text: '$ Value (PV @ 25%)', color: THEME.muted, font: { size: 11 } }
          }
        }
      }
    });
  }

  function renderCapTable() {
    const tbody = document.getElementById('cap-table-body');
    if (!tbody) return;

    const sorted = CAP_HEALTH_DATA.slice().sort((a, b) => b.total_surplus - a.total_surplus);

    tbody.innerHTML = sorted.map(r => {
      const surpColor = surplusColor(r.total_surplus);
      return `
        <tr>
          <td>${r.team}</td>
          <td class="num">${fmt1(r.current_cap_usage)}</td>
          <td class="num">${fmt1(r.total_pv_tv)}</td>
          <td class="num">${fmt1(r.total_pv_cap)}</td>
          <td class="num surplus-cell" style="color:${surpColor};">${fmt1(r.total_surplus)}</td>
          <td class="num">${fmt1(r.dead_money_cut_now_nominal)}</td>
        </tr>
      `;
    }).join('');
  }

  function refreshCap() {
    renderCapChart();
    renderCapTable();
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

    // Surplus filters
    ['surplus-position', 'surplus-team'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('change', () => {
        if (id === 'surplus-position') surplusFilter.position = el.value;
        if (id === 'surplus-team')     surplusFilter.team     = el.value;
        refreshSurplus();
      });
    });

    // Surplus column sort
    document.querySelectorAll('#surplus-table thead th[data-sort]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        if (surplusSortKey === th.dataset.sort) {
          surplusSortAsc = !surplusSortAsc;
        } else {
          surplusSortKey = th.dataset.sort;
          surplusSortAsc = false;
        }
        document.querySelectorAll('#surplus-table thead th[data-sort]').forEach(h => {
          h.classList.remove('sort-asc', 'sort-desc');
        });
        th.classList.add(surplusSortAsc ? 'sort-asc' : 'sort-desc');
        renderSurplusTable(getFilteredSurplus());
      });
    });

    // Default: Contract Surplus sub-tab
    switchLeagueTab('contract-surplus');
  }

  window.initLeague = initLeague;
})();
