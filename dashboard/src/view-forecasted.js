// Phase 2 — Forecasted Values
// Two sub-tabs: TV Forecast (bar chart + sortable table) and ADP→ESV scatter.

(function () {
  // ── State ─────────────────────────────────────────────────────────────────
  let tvChartInstance  = null;
  let adpChartInstance = null;
  let tvSortKey        = 'tv_y0';
  let tvSortAsc        = false;
  let tvFilter         = { position: 'All', team: 'All', rosteredOnly: false };
  let adpFilter        = { position: 'All' };

  // ── Helpers ───────────────────────────────────────────────────────────────

  function fmt1(v) { return typeof v === 'number' ? v.toFixed(1) : '–'; }
  function fmtInt(v) { return typeof v === 'number' ? Math.round(v) : '–'; }

  function buildTeamOptions(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="All">All Teams</option>';
    ALL_TV_TEAMS.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t; opt.textContent = t;
      sel.appendChild(opt);
    });
    if ([...sel.options].some(o => o.value === current)) sel.value = current;
  }

  // ── TV Forecast ──────────────────────────────────────────────────────────

  function getFilteredTV() {
    return TV_DATA.filter(r => {
      if (tvFilter.position !== 'All' && r.position !== tvFilter.position) return false;
      if (tvFilter.team !== 'All' && r.team !== tvFilter.team) return false;
      if (tvFilter.rosteredOnly && !r.is_rostered) return false;
      return true;
    });
  }

  function renderTVChart(rows) {
    if (tvChartInstance) { tvChartInstance.destroy(); tvChartInstance = null; }
    const ctx = document.getElementById('chart-tv-forecast');
    if (!ctx || !rows.length) return;

    // Top 30 by tv_y0 descending for the chart
    const top = rows
      .slice()
      .sort((a, b) => b.tv_y0 - a.tv_y0)
      .slice(0, 30);

    tvChartInstance = new Chart(ctx.getContext('2d'), {
      type: 'bar',
      data: {
        labels: top.map(r => r.player),
        datasets: [
          {
            label: 'TV Y0',
            data: top.map(r => +r.tv_y0.toFixed(1)),
            backgroundColor: top.map(r => hexToRgba(POS_COLORS[r.position] || THEME.accent, 0.65)),
            borderColor:     top.map(r => POS_COLORS[r.position] || THEME.accent),
            borderWidth: 1,
            borderRadius: 3,
          },
          {
            label: 'ESV p50',
            data: top.map(r => +r.esv_p50.toFixed(1)),
            backgroundColor: hexToRgba(THEME.muted, 0.25),
            borderColor:     THEME.muted,
            borderWidth: 1,
            borderRadius: 3,
          },
        ]
      },
      options: {
        ...CHART_DEFAULTS,
        indexAxis: 'y',
        plugins: {
          ...CHART_DEFAULTS.plugins,
          legend: { ...CHART_DEFAULTS.plugins.legend, display: true },
          tooltip: {
            ...CHART_DEFAULTS.plugins.tooltip,
            callbacks: {
              title: ctx2 => {
                const r = top[ctx2[0].dataIndex];
                return r ? `${r.player} (${r.position}) · ${r.team}` : '';
              },
              label: ctx2 => {
                const r = top[ctx2[0]?.dataIndex ?? ctx2.dataIndex];
                if (!r) return '';
                return [
                  ` TV Y0: ${fmt1(r.tv_y0)}  Y1: ${fmt1(r.tv_y1)}  Y2: ${fmt1(r.tv_y2)}  Y3: ${fmt1(r.tv_y3)}`,
                  ` ESV p25/p50/p75: ${fmt1(r.esv_p25)} / ${fmt1(r.esv_p50)} / ${fmt1(r.esv_p75)}`,
                  ` ADP: ${fmtInt(r.adp)}`,
                ];
              }
            }
          }
        },
        scales: {
          x: { ...CHART_DEFAULTS.scales.x, title: { display: true, text: '$ Value', color: THEME.muted, font: { size: 11 } } },
          y: { ...CHART_DEFAULTS.scales.y, ticks: { ...CHART_DEFAULTS.scales.y.ticks, font: { family: 'DM Sans', size: 10 } } }
        }
      }
    });
  }

  function renderTVTable(rows) {
    const tbody = document.getElementById('tv-table-body');
    if (!tbody) return;

    const sorted = rows.slice().sort((a, b) => {
      const av = a[tvSortKey] ?? 0;
      const bv = b[tvSortKey] ?? 0;
      return tvSortAsc ? av - bv : bv - av;
    });

    tbody.innerHTML = sorted.map(r => `
      <tr>
        <td>${playerLink(r.player)}</td>
        <td>${r.team}</td>
        <td><span class="pos-badge pos-${r.position.toLowerCase()}">${r.position}</span></td>
        <td class="num">${fmt1(r.tv_y0)}</td>
        <td class="num">${fmt1(r.tv_y1)}</td>
        <td class="num">${fmt1(r.tv_y2)}</td>
        <td class="num">${fmt1(r.tv_y3)}</td>
        <td class="num">${fmtInt(r.adp)}</td>
        <td class="num">${fmt1(r.esv_p25)} / ${fmt1(r.esv_p50)} / ${fmt1(r.esv_p75)}</td>
      </tr>
    `).join('');
  }

  function refreshTV() {
    const rows = getFilteredTV();
    renderTVChart(rows);
    renderTVTable(rows);
  }

  // ── ADP → ESV scatter ────────────────────────────────────────────────────

  function getFilteredADP() {
    return TV_DATA.filter(r => {
      if (adpFilter.position !== 'All' && r.position !== adpFilter.position) return false;
      if (!r.adp || r.adp <= 0) return false;
      return true;
    });
  }

  function renderADPChart(rows) {
    if (adpChartInstance) { adpChartInstance.destroy(); adpChartInstance = null; }
    const ctx = document.getElementById('chart-adp-esv');
    if (!ctx || !rows.length) return;

    // Group by position for separate datasets
    const byPos = {};
    rows.forEach(r => {
      (byPos[r.position] = byPos[r.position] || []).push(r);
    });

    const datasets = Object.entries(byPos).map(([pos, posRows]) => ({
      label: pos,
      data: posRows.map(r => ({ x: r.adp, y: +r.esv_hat.toFixed(1), player: r.player, team: r.team })),
      backgroundColor: hexToRgba(POS_COLORS[pos] || THEME.accent, 0.6),
      borderColor:     POS_COLORS[pos] || THEME.accent,
      borderWidth: 1,
      pointRadius: 5,
      pointHoverRadius: 7,
    }));

    adpChartInstance = new Chart(ctx.getContext('2d'), {
      type: 'scatter',
      data: { datasets },
      options: {
        ...CHART_DEFAULTS,
        plugins: {
          ...CHART_DEFAULTS.plugins,
          legend: { ...CHART_DEFAULTS.plugins.legend, display: true },
          tooltip: {
            ...CHART_DEFAULTS.plugins.tooltip,
            callbacks: {
              label: ctx2 => {
                const d = ctx2.raw;
                return ` ${d.player} (${d.team}) — ADP ${fmtInt(d.x)}, ESV ${fmt1(d.y)}`;
              }
            }
          }
        },
        scales: {
          x: {
            ...CHART_DEFAULTS.scales.x,
            reverse: true,
            title: { display: true, text: 'ADP (lower = better)', color: THEME.muted, font: { size: 11 } }
          },
          y: {
            ...CHART_DEFAULTS.scales.y,
            title: { display: true, text: 'ESV Forecast', color: THEME.muted, font: { size: 11 } }
          }
        }
      }
    });
  }

  function refreshADP() {
    renderADPChart(getFilteredADP());
  }

  // ── Sub-tab switching ─────────────────────────────────────────────────────

  function switchForecastedTab(tabId) {
    document.querySelectorAll('#panel-forecasted .sub-tab-panel').forEach(p => {
      p.hidden = p.id !== `sub-${tabId}`;
    });
    document.querySelectorAll('#panel-forecasted .sub-tab-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.subtab === tabId);
    });

    if (tabId === 'tv-forecast')  refreshTV();
    if (tabId === 'adp-esv')      refreshADP();
  }

  // ── Init ─────────────────────────────────────────────────────────────────

  let _initialized = false;

  function initForecasted() {
    if (_initialized) return;
    _initialized = true;

    buildTeamOptions('tv-team');

    // Sub-tab buttons
    document.querySelectorAll('#panel-forecasted .sub-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => switchForecastedTab(btn.dataset.subtab));
    });

    // TV controls
    ['tv-position', 'tv-team'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('change', () => {
        if (id === 'tv-position') tvFilter.position = el.value;
        if (id === 'tv-team')     tvFilter.team     = el.value;
        refreshTV();
      });
    });

    const rosteredCb = document.getElementById('tv-rostered-only');
    if (rosteredCb) {
      rosteredCb.addEventListener('change', () => {
        tvFilter.rosteredOnly = rosteredCb.checked;
        refreshTV();
      });
    }

    // TV column sort
    document.querySelectorAll('#tv-table thead th[data-sort]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        if (tvSortKey === th.dataset.sort) {
          tvSortAsc = !tvSortAsc;
        } else {
          tvSortKey = th.dataset.sort;
          tvSortAsc = false;
        }
        // Update header indicators
        document.querySelectorAll('#tv-table thead th[data-sort]').forEach(h => {
          h.classList.remove('sort-asc', 'sort-desc');
        });
        th.classList.add(tvSortAsc ? 'sort-asc' : 'sort-desc');
        renderTVTable(getFilteredTV());
      });
    });

    // ADP position filter
    const adpPosSel = document.getElementById('adp-position');
    if (adpPosSel) {
      adpPosSel.addEventListener('change', () => {
        adpFilter.position = adpPosSel.value;
        refreshADP();
      });
    }

    // Default: TV Forecast sub-tab
    switchForecastedTab('tv-forecast');
  }

  window.initForecasted = initForecasted;
})();
