// Phase 3 — Trade Proposal Assessment
// Select two teams, pick assets (players, picks, cap $) moving each direction,
// and see net changes across four metrics: This Yr Value, This Yr Surplus,
// 3-Yr Value, 3-Yr Surplus. Pick values are calendar-aligned: a 2026 pick
// contributes to This Yr Value; a 2027 pick contributes only to 3-Yr Value.
// All picks carry zero surplus (projected value == contract salary by assumption).

(function () {
  // ── State ─────────────────────────────────────────────────────────────────
  let tpChartInstance = null;
  let tpTeamA = null;
  let tpTeamB = null;
  const tpPlayersFromA = new Set();  // player names leaving Team A
  const tpPlayersFromB = new Set();  // player names leaving Team B
  const tpPicksFromA   = new Set();  // pick_ids leaving Team A
  const tpPicksFromB   = new Set();  // pick_ids leaving Team B
  let tpCapFromA = 0;                // $ A → B, current year
  let tpCapFromB = 0;                // $ B → A, current year

  const METRICS = [
    { key: 'value_1yr',       label: 'This Yr Value'   },
    { key: 'surplus_1yr',     label: 'This Yr Surplus' },
    { key: 'value_3yr_ann',   label: '3-Yr Value'      },
    { key: 'surplus_3yr_ann', label: '3-Yr Surplus'    },
  ];

  // ── Helpers ───────────────────────────────────────────────────────────────

  function fmt1(v) { return typeof v === 'number' && isFinite(v) ? v.toFixed(1) : '–'; }

  function surplusColor(v) {
    if (v > 20)  return 'var(--surplus-high)';
    if (v > 0)   return 'var(--surplus-pos)';
    if (v > -10) return 'var(--surplus-neg)';
    return 'var(--surplus-low)';
  }

  function escapeAttr(s) {
    return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
  }

  function playersForTeam(team) {
    if (!team) return [];
    return SURPLUS_DATA.filter(r => r.team === team)
      .slice()
      .sort((a, b) => (b.value_1yr || 0) - (a.value_1yr || 0));
  }

  function picksForTeam(team) {
    if (!team) return [];
    return (DRAFT_PICKS_DATA || [])
      .filter(p => p.owner === team)
      .slice()
      .sort((a, b) => {
        if (a.year !== b.year) return a.year - b.year;
        if (a.round !== b.round) return a.round - b.round;
        return (a.slot ?? 99) - (b.slot ?? 99);
      });
  }

  // ── Team selectors ────────────────────────────────────────────────────────

  function populateTeamSelects() {
    const selA = document.getElementById('tp-team-a');
    const selB = document.getElementById('tp-team-b');
    if (!selA || !selB) return;

    const teams = ALL_LG_TEAMS || [];
    const options = teams.map(t => `<option value="${escapeAttr(t)}">${t}</option>`).join('');
    selA.innerHTML = options;
    selB.innerHTML = options;

    if (teams.length >= 2) {
      tpTeamA = teams[0];
      tpTeamB = teams[1];
    } else if (teams.length === 1) {
      tpTeamA = teams[0];
      tpTeamB = teams[0];
    } else {
      tpTeamA = null;
      tpTeamB = null;
    }
    selA.value = tpTeamA || '';
    selB.value = tpTeamB || '';
    syncTeamSelectDisabled();
  }

  function syncTeamSelectDisabled() {
    const selA = document.getElementById('tp-team-a');
    const selB = document.getElementById('tp-team-b');
    if (!selA || !selB) return;
    [...selA.options].forEach(o => { o.disabled = (o.value === tpTeamB && o.value !== tpTeamA); });
    [...selB.options].forEach(o => { o.disabled = (o.value === tpTeamA && o.value !== tpTeamB); });
  }

  // ── Asset pickers ─────────────────────────────────────────────────────────

  function renderPlayerList(team, fromSet, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const players = playersForTeam(team);
    if (!players.length) {
      container.innerHTML = '<div class="tp-empty">No players on this roster.</div>';
      return;
    }

    container.innerHTML = players.map(r => {
      const checked = fromSet.has(r.player) ? 'checked' : '';
      const surpColor = surplusColor(r.surplus_1yr || 0);
      return `
        <label class="tp-row">
          <input type="checkbox" data-player="${escapeAttr(r.player)}" ${checked} />
          <span class="pos-badge pos-${r.position.toLowerCase()}">${r.position}</span>
          <span class="tp-row-name">${r.player}</span>
          <span class="tp-row-metric num" title="This Yr Value">${fmt1(r.value_1yr)}</span>
          <span class="tp-row-metric num" title="This Yr Surplus" style="color:${surpColor};">${fmt1(r.surplus_1yr)}</span>
        </label>`;
    }).join('');

    container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', () => {
        const name = cb.dataset.player;
        if (cb.checked) fromSet.add(name); else fromSet.delete(name);
        refresh();
      });
    });
  }

  function renderPickList(team, fromSet, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const picks = picksForTeam(team);
    if (!picks.length) {
      container.innerHTML = '<div class="tp-empty">No picks owned.</div>';
      return;
    }

    container.innerHTML = picks.map(p => {
      const checked = fromSet.has(p.pick_id) ? 'checked' : '';
      const slotStr = p.slot ? ` · #${p.slot}` : '';
      const salary = p.salary != null ? `$${p.salary}` : '';
      const val1yr = (p.value_1yr != null && p.value_1yr > 0) ? fmt1(p.value_1yr) : '–';
      return `
        <label class="tp-row">
          <input type="checkbox" data-pick="${escapeAttr(p.pick_id)}" ${checked} />
          <span class="tp-row-name mono">${p.year} R${p.round}${slotStr}</span>
          <span class="tp-row-metric num">${salary}</span>
          <span class="tp-row-metric num" title="This Yr Value">${val1yr}</span>
        </label>`;
    }).join('');

    container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', () => {
        const id = cb.dataset.pick;
        if (cb.checked) fromSet.add(id); else fromSet.delete(id);
        refresh();
      });
    });
  }

  function rebuildPickers() {
    renderPlayerList(tpTeamA, tpPlayersFromA, 'tp-players-a');
    renderPickList(tpTeamA, tpPicksFromA, 'tp-picks-a');
    renderPlayerList(tpTeamB, tpPlayersFromB, 'tp-players-b');
    renderPickList(tpTeamB, tpPicksFromB, 'tp-picks-b');
  }

  // ── Deltas ────────────────────────────────────────────────────────────────

  function computeDeltas() {
    const deltas = {
      A: { value_1yr: 0, surplus_1yr: 0, value_3yr_ann: 0, surplus_3yr_ann: 0 },
      B: { value_1yr: 0, surplus_1yr: 0, value_3yr_ann: 0, surplus_3yr_ann: 0 },
    };

    const lookup = {};
    SURPLUS_DATA.forEach(r => { lookup[`${r.team}||${r.player}`] = r; });

    tpPlayersFromA.forEach(name => {
      const r = lookup[`${tpTeamA}||${name}`];
      if (!r) return;
      METRICS.forEach(m => {
        const v = r[m.key] || 0;
        deltas.A[m.key] -= v;
        deltas.B[m.key] += v;
      });
    });

    tpPlayersFromB.forEach(name => {
      const r = lookup[`${tpTeamB}||${name}`];
      if (!r) return;
      METRICS.forEach(m => {
        const v = r[m.key] || 0;
        deltas.B[m.key] -= v;
        deltas.A[m.key] += v;
      });
    });

    // Picks: calendar-aligned value metrics (surplus always 0).
    const pickLookup = {};
    (DRAFT_PICKS_DATA || []).forEach(p => { pickLookup[p.pick_id] = p; });

    tpPicksFromA.forEach(id => {
      const p = pickLookup[id];
      if (!p) return;
      METRICS.forEach(m => {
        const v = p[m.key] || 0;
        deltas.A[m.key] -= v;
        deltas.B[m.key] += v;
      });
    });

    tpPicksFromB.forEach(id => {
      const p = pickLookup[id];
      if (!p) return;
      METRICS.forEach(m => {
        const v = p[m.key] || 0;
        deltas.B[m.key] -= v;
        deltas.A[m.key] += v;
      });
    });

    // Cap $: sender's cap hit drops → surplus up for sender, down for receiver.
    // 1yr: full amount. 3yr annualized: divide by 3 (single-year transfer
    // averaged across the 3-year window).
    const net = (+tpCapFromA || 0) - (+tpCapFromB || 0);   // net A → B
    deltas.A.surplus_1yr     += net;
    deltas.B.surplus_1yr     -= net;
    deltas.A.surplus_3yr_ann += net / 3;
    deltas.B.surplus_3yr_ann -= net / 3;

    return deltas;
  }

  // ── Chart ─────────────────────────────────────────────────────────────────

  function renderChart(deltas) {
    if (tpChartInstance) { tpChartInstance.destroy(); tpChartInstance = null; }
    const ctx = document.getElementById('chart-trade-proposal');
    if (!ctx) return;

    const labels = METRICS.map(m => m.label);
    const dataA = METRICS.map(m => +(deltas.A[m.key] || 0).toFixed(2));
    const dataB = METRICS.map(m => +(deltas.B[m.key] || 0).toFixed(2));

    tpChartInstance = new Chart(ctx.getContext('2d'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: tpTeamA || 'Team A',
            data: dataA,
            backgroundColor: hexToRgba(THEME.accent, 0.6),
            borderColor:     THEME.accent,
            borderWidth: 1,
            borderRadius: 3,
          },
          {
            label: tpTeamB || 'Team B',
            data: dataB,
            backgroundColor: hexToRgba('#e06c75', 0.55),
            borderColor:     '#e06c75',
            borderWidth: 1,
            borderRadius: 3,
          },
        ],
      },
      options: {
        ...CHART_DEFAULTS,
        plugins: {
          ...CHART_DEFAULTS.plugins,
          legend: { ...CHART_DEFAULTS.plugins.legend, display: true },
          tooltip: {
            ...CHART_DEFAULTS.plugins.tooltip,
            callbacks: {
              label: ctx2 => {
                const v = ctx2.parsed.y;
                const sign = v > 0 ? '+' : '';
                return ` ${ctx2.dataset.label}: ${sign}${v.toFixed(1)}`;
              },
            },
          },
        },
        scales: {
          x: { ...CHART_DEFAULTS.scales.x },
          y: {
            ...CHART_DEFAULTS.scales.y,
            title: { display: true, text: 'Net change ($)', color: THEME.muted, font: { size: 11 } },
            grid: { ...CHART_DEFAULTS.scales.y.grid, color: THEME.border },
          },
        },
      },
    });
  }

  // ── Summary strip ─────────────────────────────────────────────────────────

  function renderSummary(deltas) {
    const el = document.getElementById('tp-summary');
    if (!el) return;

    const header =
      '<tr><th>Team</th>' +
      METRICS.map(m => `<th class="num">${m.label}</th>`).join('') +
      '</tr>';

    function row(team, d) {
      const cells = METRICS.map(m => {
        const v = d[m.key] || 0;
        const sign = v > 0 ? '+' : '';
        const color = surplusColor(v);
        return `<td class="num" style="color:${color};">${sign}${fmt1(v)}</td>`;
      }).join('');
      return `<tr><td>${team || '—'}</td>${cells}</tr>`;
    }

    el.innerHTML =
      '<table class="data-table tp-summary-table">' +
      `<thead>${header}</thead>` +
      `<tbody>${row(tpTeamA, deltas.A)}${row(tpTeamB, deltas.B)}</tbody>` +
      '</table>';
  }

  // ── Refresh & init ────────────────────────────────────────────────────────

  function refresh() {
    const titleA = document.getElementById('tp-col-a-title');
    const titleB = document.getElementById('tp-col-b-title');
    if (titleA) titleA.textContent = `${tpTeamA || 'Team A'} sends`;
    if (titleB) titleB.textContent = `${tpTeamB || 'Team B'} sends`;

    const deltas = computeDeltas();
    renderChart(deltas);
    renderSummary(deltas);
  }

  function resetSelections() {
    tpPlayersFromA.clear();
    tpPlayersFromB.clear();
    tpPicksFromA.clear();
    tpPicksFromB.clear();
    tpCapFromA = 0;
    tpCapFromB = 0;
    const capA = document.getElementById('tp-cap-a');
    const capB = document.getElementById('tp-cap-b');
    if (capA) capA.value = '0';
    if (capB) capB.value = '0';
  }

  function onTeamAChange(val) {
    if (!val || val === tpTeamA) return;
    if (val === tpTeamB) return;   // disabled option, but guard anyway
    tpTeamA = val;
    tpPlayersFromA.clear();
    tpPicksFromA.clear();
    syncTeamSelectDisabled();
    rebuildPickers();
    refresh();
  }

  function onTeamBChange(val) {
    if (!val || val === tpTeamB) return;
    if (val === tpTeamA) return;
    tpTeamB = val;
    tpPlayersFromB.clear();
    tpPicksFromB.clear();
    syncTeamSelectDisabled();
    rebuildPickers();
    refresh();
  }

  let _initialized = false;

  function initTradeProposal() {
    if (_initialized) return;
    _initialized = true;

    populateTeamSelects();

    const selA = document.getElementById('tp-team-a');
    const selB = document.getElementById('tp-team-b');
    if (selA) selA.addEventListener('change', () => onTeamAChange(selA.value));
    if (selB) selB.addEventListener('change', () => onTeamBChange(selB.value));

    const capA = document.getElementById('tp-cap-a');
    const capB = document.getElementById('tp-cap-b');
    if (capA) capA.addEventListener('input', () => {
      tpCapFromA = Math.max(0, +capA.value || 0);
      refresh();
    });
    if (capB) capB.addEventListener('input', () => {
      tpCapFromB = Math.max(0, +capB.value || 0);
      refresh();
    });

    const resetBtn = document.getElementById('tp-reset-btn');
    if (resetBtn) resetBtn.addEventListener('click', () => {
      resetSelections();
      rebuildPickers();
      refresh();
    });

    rebuildPickers();
    refresh();
  }

  function refreshTradeProposal() {
    if (!_initialized) {
      initTradeProposal();
      return;
    }
    // If teams were empty at init (data still loading), populate now.
    if (!tpTeamA && (ALL_LG_TEAMS || []).length) {
      populateTeamSelects();
      rebuildPickers();
    }
    refresh();
  }

  window.initTradeProposal    = initTradeProposal;
  window.refreshTradeProposal = refreshTradeProposal;
})();
