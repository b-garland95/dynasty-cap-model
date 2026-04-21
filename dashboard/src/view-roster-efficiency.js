// Roster Efficiency view — part of the League Analysis section.
// Shows two sub-views:
//   1. Team RAV chart: raw TV vs Roster-Adjusted Value (RAV) per team, sorted by RAV.
//      The gap between the bars is "wasted" value sitting on the bench.
//   2. Trade Gap screen: bench players whose current team can't fully utilize their
//      value — sorted by trade_gap_y0 descending with position/team filters.

(function () {
  // ── State ─────────────────────────────────────────────────────────────────
  let ravChartInstance = null;
  let tgSortKey        = 'trade_gap_y0';
  let tgSortAsc        = false;
  let tgFilter         = { position: 'All', team: 'All' };

  // ── Helpers ───────────────────────────────────────────────────────────────

  function fmt1(v) { return typeof v === 'number' ? v.toFixed(1) : '–'; }
  function fmtPct(v) { return typeof v === 'number' ? (v * 100).toFixed(1) + '%' : '–'; }

  function tradeGapColor(v) {
    if (v >= 20) return 'var(--surplus-high)';
    if (v >= 10) return 'var(--surplus-pos)';
    if (v >  0)  return 'var(--text)';
    return 'var(--muted)';
  }

  function shortTeamLabel(team) {
    const parts = team.split('|');
    return parts.length > 1 ? parts[parts.length - 1].trim() : team;
  }

  // ── RAV Team Chart ────────────────────────────────────────────────────────

  function renderRavChart() {
    if (ravChartInstance) { ravChartInstance.destroy(); ravChartInstance = null; }
    const canvas = document.getElementById('chart-rav-teams');
    if (!canvas || !RAV_SUMMARY_DATA.length) return;

    // Sort by total_rav_y0 descending
    const rows = RAV_SUMMARY_DATA.slice().sort((a, b) => b.total_rav_y0 - a.total_rav_y0);
    const labels = rows.map(r => shortTeamLabel(r.team));

    const ravColor   = THEME.accent;         // deployed value
    const gapColor   = '#e06c75';            // wasted bench value

    ravChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Deployed Value (RAV)',
            data: rows.map(r => +r.total_rav_y0.toFixed(1)),
            backgroundColor: hexToRgba(ravColor, 0.72),
            borderColor:     ravColor,
            borderWidth: 1,
            stack: 'roster',
          },
          {
            label: 'Bench Overhang (Trade Gap)',
            data: rows.map(r => +Math.max(r.total_trade_gap_y0, 0).toFixed(1)),
            backgroundColor: hexToRgba(gapColor, 0.55),
            borderColor:     gapColor,
            borderWidth: 1,
            stack: 'roster',
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
              title: ctx2 => rows[ctx2[0].dataIndex]?.team ?? '',
              label: ctx2 => {
                const r = rows[ctx2[0]?.dataIndex ?? ctx2.dataIndex];
                if (!r) return '';
                const utilPct = (r.rav_utilization_rate * 100).toFixed(1);
                return [
                  ` Raw TV:          $${fmt1(r.total_tv_y0)}`,
                  ` Deployed (RAV):  $${fmt1(r.total_rav_y0)}  (${utilPct}% utilized)`,
                  ` Bench Overhang:  $${fmt1(r.total_trade_gap_y0)}`,
                  ``,
                  ` QB: $${fmt1(r.rav_qb)} deployed / $${fmt1(r.tv_qb)} raw`,
                  ` RB: $${fmt1(r.rav_rb)} deployed / $${fmt1(r.tv_rb)} raw`,
                  ` WR: $${fmt1(r.rav_wr)} deployed / $${fmt1(r.tv_wr)} raw`,
                  ` TE: $${fmt1(r.rav_te)} deployed / $${fmt1(r.tv_te)} raw`,
                ];
              }
            }
          }
        },
        scales: {
          x: {
            ...CHART_DEFAULTS.scales.x,
            stacked: true,
            ticks: { ...CHART_DEFAULTS.scales.x.ticks, maxRotation: 35, minRotation: 20 }
          },
          y: {
            ...CHART_DEFAULTS.scales.y,
            stacked: true,
            title: { display: true, text: 'Value ($)', color: THEME.muted, font: { size: 11 } },
          }
        }
      }
    });
  }

  function renderRavTable() {
    const tbody = document.getElementById('rav-team-tbody');
    if (!tbody) return;
    const rows = RAV_SUMMARY_DATA.slice().sort((a, b) => b.total_rav_y0 - a.total_rav_y0);
    tbody.innerHTML = rows.map(r => {
      const gap = r.total_trade_gap_y0;
      const gapColor = gap > 15 ? 'var(--surplus-neg)' : gap > 5 ? 'var(--text)' : 'var(--muted)';
      return `
        <tr>
          <td>${r.team}</td>
          <td class="num">${fmt1(r.total_tv_y0)}</td>
          <td class="num">${fmt1(r.total_rav_y0)}</td>
          <td class="num" style="color:${gapColor};">${fmt1(gap)}</td>
          <td class="num">${fmtPct(r.rav_utilization_rate)}</td>
          <td class="num">${fmt1(r.tv_qb)} / ${fmt1(r.rav_qb)}</td>
          <td class="num">${fmt1(r.tv_rb)} / ${fmt1(r.rav_rb)}</td>
          <td class="num">${fmt1(r.tv_wr)} / ${fmt1(r.rav_wr)}</td>
          <td class="num">${fmt1(r.tv_te)} / ${fmt1(r.rav_te)}</td>
        </tr>
      `;
    }).join('');
  }

  // ── Trade Gap Screen ──────────────────────────────────────────────────────

  function getFilteredTradeGap() {
    return TRADE_GAP_DATA.filter(r => {
      if (tgFilter.position !== 'All' && r.position !== tgFilter.position) return false;
      if (tgFilter.team     !== 'All' && r.team     !== tgFilter.team)     return false;
      return true;
    });
  }

  function renderTradeGapTable() {
    const tbody = document.getElementById('trade-gap-tbody');
    if (!tbody) return;

    const rows = getFilteredTradeGap().slice().sort((a, b) => {
      const av = a[tgSortKey] ?? 0;
      const bv = b[tgSortKey] ?? 0;
      return tgSortAsc ? av - bv : bv - av;
    });

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);">No bench players match the current filter.</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(r => {
      const gapColor = tradeGapColor(r.trade_gap_y0);
      const depthLabel = r.bench_depth === 0 ? '1st backup' : r.bench_depth === 1 ? '2nd backup' : `depth ${r.bench_depth + 1}`;
      return `
        <tr>
          <td>${playerLink(r.player)}</td>
          <td class="team-cell">${r.team}</td>
          <td><span class="pos-badge pos-${r.position.toLowerCase()}">${r.position}</span></td>
          <td class="num">${fmt1(r.tv_y0)}</td>
          <td class="num">${fmt1(r.rav_y0)}</td>
          <td class="num" style="color:${gapColor}; font-weight:600;">${fmt1(r.trade_gap_y0)}</td>
          <td class="num" style="color:var(--muted);">${fmtPct(r.depth_discount)}</td>
          <td class="num">${r.cap_y0 ? '$' + fmt1(r.cap_y0) : '–'}</td>
          <td style="color:var(--muted); font-size:0.82em;">${depthLabel}</td>
        </tr>
      `;
    }).join('');
  }

  function buildTgTeamOptions() {
    const sel = document.getElementById('tg-team');
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

  // ── Sub-view switching ────────────────────────────────────────────────────

  function switchRavSubview(subview) {
    document.querySelectorAll('#sub-roster-efficiency .re-subview').forEach(el => {
      el.hidden = el.id !== `re-${subview}`;
    });
    document.querySelectorAll('#re-subview-toggle .toggle-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.value === subview);
    });

    if (subview === 'team-chart') {
      renderRavChart();
      renderRavTable();
    } else {
      renderTradeGapTable();
    }
  }

  // ── Init ─────────────────────────────────────────────────────────────────

  let _initialized = false;

  function initRosterEfficiency() {
    if (_initialized) { renderRavChart(); renderRavTable(); return; }
    _initialized = true;

    // Sub-view toggle
    document.querySelectorAll('#re-subview-toggle .toggle-btn').forEach(btn => {
      btn.addEventListener('click', () => switchRavSubview(btn.dataset.value));
    });

    // Trade gap filters
    buildTgTeamOptions();
    ['tg-position', 'tg-team'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('change', () => {
        if (id === 'tg-position') tgFilter.position = el.value;
        if (id === 'tg-team')     tgFilter.team     = el.value;
        renderTradeGapTable();
      });
    });

    // Trade gap sort
    document.querySelectorAll('#trade-gap-table thead th[data-sort]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        if (tgSortKey === th.dataset.sort) {
          tgSortAsc = !tgSortAsc;
        } else {
          tgSortKey = th.dataset.sort;
          tgSortAsc = false;
        }
        document.querySelectorAll('#trade-gap-table thead th').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
        th.classList.add(tgSortAsc ? 'sort-asc' : 'sort-desc');
        renderTradeGapTable();
      });
    });

    // Default: team chart view
    switchRavSubview('team-chart');
  }

  window.initRosterEfficiency = initRosterEfficiency;
})();
