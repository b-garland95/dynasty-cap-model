// Phase 3 — League Analysis
// Two sub-tabs: Contract Surplus (sortable table) and Cap Health (bar chart + table).
// Both views support a valuation-window selector: "1yr" (this year), "3yr" (3-year avg),
// or "5yr" (5-year avg).  Window-based metrics are annualized so the per-year values
// are directly comparable across different time horizons.

(function () {
  // ── State ─────────────────────────────────────────────────────────────────
  let capChartInstance     = null;
  let scatterChartInstance = null;
  let surplusSortKey       = 'surplus_1yr';
  let surplusSortAsc       = false;
  let surplusFilter        = { position: 'All', team: 'All' };
  // surplusWindow drives the Contract Surplus sub-tab only.
  // valuationWindow drives Cap Health (unchanged: '1yr' | '3yr' | '5yr').
  let surplusWindow        = '1yr';   // '1yr' | 'contract' | 'y0' | 'y1' | 'y2' | 'y3'
  let valuationWindow      = '1yr';   // '1yr' | '3yr' | '5yr'
  let scatterYMode         = 'value';    // 'value' | 'surplus'
  let scatterColorMode     = 'position'; // 'position' | 'team'
  let scatterSelection     = new Set();  // player names currently selected

  // Stable team→color map built once per scatter render
  let _teamColorMap = null;

  const TEAM_PALETTE = [
    '#e06c75', '#61afef', '#98c379', '#d19a66',
    '#c678dd', '#56b6c2', '#e5c07b', '#be5046',
    '#528bff', '#7bc275', '#d0a0d0', '#80aacc',
  ];

  // ── Window field maps ─────────────────────────────────────────────────────
  // PLAYER_FIELDS: maps surplusWindow key → player-level field names for the
  // Contract Surplus sub-tab (value, cap, surplus columns).
  // 'contract' mode exposes additional aggregate columns handled separately in
  // renderSurplusTable / renderSurplusScatter.
  const PLAYER_FIELDS = {
    '1yr':      { value: 'value_1yr',         cap: 'cap_1yr',         surplus: 'surplus_1yr'         },
    'contract': { value: 'contract_avg_value', cap: 'contract_avg_cap', surplus: 'contract_avg_surplus' },
    'y0':       { value: 'tv_y0',  cap: 'cap_y0',  surplus: 'surplus_y0' },
    'y1':       { value: 'tv_y1',  cap: 'cap_y1',  surplus: 'surplus_y1' },
    'y2':       { value: 'tv_y2',  cap: 'cap_y2',  surplus: 'surplus_y2' },
    'y3':       { value: 'tv_y3',  cap: 'cap_y3',  surplus: 'surplus_y3' },
  };

  // TEAM_FIELDS: maps valuationWindow key → team-level field names for Cap Health.
  // Unchanged — Cap Health still uses 1yr / 3yr / 5yr.
  const TEAM_FIELDS = {
    '1yr': { value: 'total_value_1yr',     cap: 'total_cap_1yr',     surplus: 'total_surplus_1yr'     },
    '3yr': { value: 'total_value_3yr_ann', cap: 'total_cap_3yr_ann', surplus: 'total_surplus_3yr_ann' },
    '5yr': { value: 'total_value_5yr_ann', cap: 'total_cap_5yr_ann', surplus: 'total_surplus_5yr_ann' },
  };

  // SURPLUS_WINDOW_LABELS: display strings for the Contract Surplus sub-tab.
  // Per-year entries are keyed 'y0'–'y3' and built at init time with actual years.
  const SURPLUS_WINDOW_LABELS = {
    '1yr':      { value: 'This Year\'s Value', cap: 'This Year\'s Cap Hit', surplus: 'This Year\'s Surplus', yAxis: 'Value ($)' },
    'contract': { value: 'Avg Value',          cap: 'Avg Cap Hit',          surplus: 'Avg Surplus',          yAxis: 'Avg Annual Value ($)' },
    'y0':       { value: 'Value',              cap: 'Cap Hit',              surplus: 'Surplus',              yAxis: 'Value ($)' },
    'y1':       { value: 'Value',              cap: 'Cap Hit',              surplus: 'Surplus',              yAxis: 'Value ($)' },
    'y2':       { value: 'Value',              cap: 'Cap Hit',              surplus: 'Surplus',              yAxis: 'Value ($)' },
    'y3':       { value: 'Value',              cap: 'Cap Hit',              surplus: 'Surplus',              yAxis: 'Value ($)' },
  };

  // WINDOW_LABELS: display strings for Cap Health (unchanged).
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

  function surplusFields()       { return PLAYER_FIELDS[surplusWindow] || PLAYER_FIELDS['1yr']; }
  function surplusWindowLabels() { return SURPLUS_WINDOW_LABELS[surplusWindow] || SURPLUS_WINDOW_LABELS['1yr']; }
  function teamFields()          { return TEAM_FIELDS[valuationWindow]; }
  function windowLabels()        { return WINDOW_LABELS[valuationWindow]; }

  // ── Contract Surplus ──────────────────────────────────────────────────────

  function getFilteredSurplus({ ignoreSelection = false } = {}) {
    const perYearMinYears = { y0: 1, y1: 2, y2: 3, y3: 4 };
    return SURPLUS_DATA.filter(r => {
      if (surplusFilter.position !== 'All' && r.position !== surplusFilter.position) return false;
      if (surplusFilter.team !== 'All' && r.team !== surplusFilter.team) return false;
      if (!ignoreSelection && scatterSelection.size > 0 && !scatterSelection.has(r.player)) return false;
      // For specific-year views, only show players whose contract extends to that year.
      if (surplusWindow in perYearMinYears && r.years_remaining < perYearMinYears[surplusWindow]) return false;
      return true;
    });
  }

  function updateSurplusHeaders() {
    if (surplusWindow === 'contract') {
      // Contract Value mode uses a custom thead rendered inside renderSurplusTable.
      return;
    }

    const labels = surplusWindowLabels();
    const fields = surplusFields();

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

  function _renderContractValueTable(rows, tbody) {
    const table = tbody.closest('table');
    if (table) {
      const thead = table.querySelector('thead tr');
      if (thead) {
        thead.innerHTML = `
          <th>Player</th>
          <th>Team</th>
          <th>Pos</th>
          <th class="num" data-sort-cv="contract_avg_cap" style="cursor:pointer;">Avg Cap Hit ↕</th>
          <th class="num" data-sort-cv="years_remaining" style="cursor:pointer;">Yrs Left ↕</th>
          <th class="num" data-sort-cv="contract_avg_value" style="cursor:pointer;">Avg Value ↕</th>
          <th class="num" data-sort-cv="contract_avg_surplus" style="cursor:pointer;">Avg Surplus ↕</th>
          <th class="num" data-sort-cv="contract_total_value" style="cursor:pointer;">Total Value ↕</th>
          <th class="num sort-desc" data-sort-cv="contract_total_surplus" style="cursor:pointer;">Total Surplus ↕</th>
          <th class="num" data-sort-cv="cap_today_current" style="cursor:pointer;">Cap Today ↕</th>
          <th class="num" data-sort-cv="dead_money_cut_now_nominal" style="cursor:pointer;">Dead $ ↕</th>
        `;
        thead.querySelectorAll('th[data-sort-cv]').forEach(th => {
          th.addEventListener('click', () => {
            if (surplusSortKey === th.dataset.sortCv) {
              surplusSortAsc = !surplusSortAsc;
            } else {
              surplusSortKey = th.dataset.sortCv;
              surplusSortAsc = false;
            }
            thead.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
            th.classList.add(surplusSortAsc ? 'sort-asc' : 'sort-desc');
            _renderContractValueTable(getFilteredSurplus(), tbody);
          });
        });
      }
    }

    const sorted = rows.slice().sort((a, b) => {
      const av = a[surplusSortKey] ?? 0;
      const bv = b[surplusSortKey] ?? 0;
      return surplusSortAsc ? av - bv : bv - av;
    });

    tbody.innerHTML = sorted.map(r => {
      const surpColor = surplusColor(r.contract_avg_surplus ?? 0);
      const totalSurpColor = surplusColor(r.contract_total_surplus ?? 0);
      const validFlag = r.needs_schedule_validation
        ? '<span class="validation-flag" title="Schedule needs validation">⚠</span>'
        : '';
      return `
        <tr>
          <td>${playerLink(r.player)}${validFlag}</td>
          <td class="team-cell">${r.team}</td>
          <td><span class="pos-badge pos-${r.position.toLowerCase()}">${r.position}</span></td>
          <td class="num">${fmt1(r.contract_avg_cap)}</td>
          <td class="num">${r.years_remaining}</td>
          <td class="num">${fmt1(r.contract_avg_value)}</td>
          <td class="num surplus-cell" style="color:${surpColor};">${fmt1(r.contract_avg_surplus)}</td>
          <td class="num">${fmt1(r.contract_total_value)}</td>
          <td class="num surplus-cell" style="color:${totalSurpColor};">${fmt1(r.contract_total_surplus)}</td>
          <td class="num">${fmt1(r.cap_today_current)}</td>
          <td class="num">${fmt1(r.dead_money_cut_now_nominal)}</td>
        </tr>
      `;
    }).join('');
  }

  function _restoreStandardSurplusHeader(tbody) {
    const table = tbody.closest('table');
    if (!table) return;
    const thead = table.querySelector('thead tr');
    if (!thead) return;
    thead.innerHTML = `
      <th>Player</th>
      <th>Team</th>
      <th>Pos</th>
      <th id="surplus-col-value" class="num sort-desc">Proj Value ↕</th>
      <th id="surplus-col-cap" class="num">Cap Hit ↕</th>
      <th id="surplus-col-surplus" class="num">Surplus ↕</th>
      <th data-sort="cap_today_current" class="num">Cap Today ↕</th>
      <th data-sort="dead_money_cut_now_nominal" class="num">Dead $ ↕</th>
    `;
    // Re-wire static sort columns.
    thead.querySelectorAll('th[data-sort]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        if (surplusSortKey === th.dataset.sort) {
          surplusSortAsc = !surplusSortAsc;
        } else {
          surplusSortKey = th.dataset.sort;
          surplusSortAsc = false;
        }
        thead.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
        th.classList.add(surplusSortAsc ? 'sort-asc' : 'sort-desc');
        renderSurplusTable(getFilteredSurplus());
      });
    });
  }

  function renderSurplusTable(rows) {
    const tbody = document.getElementById('surplus-table-body');
    if (!tbody) return;

    if (surplusWindow === 'contract') {
      _renderContractValueTable(rows, tbody);
      return;
    }

    // Ensure standard header is in place (may need restoring after contract mode).
    const hasContractHeader = tbody.closest('table')?.querySelector('th[data-sort-cv]');
    if (hasContractHeader) {
      _restoreStandardSurplusHeader(tbody);
      updateSurplusHeaders();
    }

    const fields = surplusFields();

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

  // ── Contract Scatter ──────────────────────────────────────────────────────

  function _buildTeamColorMap(rows) {
    const teams = [...new Set(rows.map(r => r.team))].sort();
    const map = {};
    teams.forEach((t, i) => { map[t] = TEAM_PALETTE[i % TEAM_PALETTE.length]; });
    return map;
  }

  function _buildBreakEvenDataset(maxCap) {
    if (scatterYMode === 'value') {
      const end = maxCap * 1.15;
      return {
        type: 'line',
        label: 'Break-even',
        data: [{ x: 0, y: 0 }, { x: end, y: end }],
        borderColor: 'rgba(255,255,255,0.22)',
        borderDash: [6, 4],
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
        order: 0,
      };
    } else {
      return {
        type: 'line',
        label: 'Break-even',
        data: [{ x: 0, y: 0 }, { x: maxCap * 1.15, y: 0 }],
        borderColor: 'rgba(255,255,255,0.22)',
        borderDash: [6, 4],
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
        order: 0,
      };
    }
  }

  function _pointAlpha(player) {
    if (scatterSelection.size === 0) return 0.72;
    return scatterSelection.has(player) ? 0.92 : 0.13;
  }

  function _pointRadius(player) {
    if (scatterSelection.size === 0) return 5;
    return scatterSelection.has(player) ? 6 : 4;
  }

  function renderSurplusScatter() {
    if (scatterChartInstance) { scatterChartInstance.destroy(); scatterChartInstance = null; }
    const canvas = document.getElementById('chart-contract-scatter');
    if (!canvas) return;

    // Use all position/team-filtered rows (ignore selection for scatter itself)
    const rows = getFilteredSurplus({ ignoreSelection: true });
    if (!rows.length) return;

    const fields = surplusFields();
    const labels = surplusWindowLabels();
    const xField = surplusWindow === 'contract' ? 'contract_avg_cap' : fields.cap;
    const yField = surplusWindow === 'contract'
      ? (scatterYMode === 'value' ? 'contract_avg_value' : 'contract_avg_surplus')
      : (scatterYMode === 'value' ? fields.value : fields.surplus);
    const xLabel = surplusWindow === 'contract' ? 'Avg Cap Hit' : labels.cap;
    const yLabel = surplusWindow === 'contract'
      ? (scatterYMode === 'value' ? 'Avg Value' : 'Avg Surplus')
      : (scatterYMode === 'value' ? labels.value : labels.surplus);

    const maxCap = Math.max(...rows.map(r => +(r[xField] || 0)));

    // Build team color map once
    _teamColorMap = _buildTeamColorMap(rows);

    // Group rows by position or team
    const groups = {};
    rows.forEach(r => {
      const key = scatterColorMode === 'position' ? r.position : r.team;
      (groups[key] = groups[key] || []).push(r);
    });

    const scatterDatasets = Object.entries(groups).map(([key, groupRows]) => {
      const baseColor = scatterColorMode === 'position'
        ? (POS_COLORS[key] || THEME.accent)
        : (_teamColorMap[key] || THEME.accent);

      return {
        type: 'scatter',
        label: key,
        data: groupRows.map(r => ({
          x: +(r[xField] || 0),
          y: +(r[yField] || 0),
          player: r.player,
          team: r.team,
          position: r.position,
        })),
        backgroundColor: groupRows.map(r => hexToRgba(baseColor, _pointAlpha(r.player))),
        borderColor:     groupRows.map(r => hexToRgba(baseColor, Math.min(_pointAlpha(r.player) + 0.2, 1))),
        borderWidth: 1,
        pointRadius:      groupRows.map(r => _pointRadius(r.player)),
        pointHoverRadius: groupRows.map(r => _pointRadius(r.player) + 2),
        order: 1,
      };
    });

    const allDatasets = [...scatterDatasets, _buildBreakEvenDataset(maxCap)];

    scatterChartInstance = new Chart(canvas.getContext('2d'), {
      type: 'scatter',
      data: { datasets: allDatasets },
      options: {
        ...CHART_DEFAULTS,
        animation: false,
        plugins: {
          ...CHART_DEFAULTS.plugins,
          legend: {
            ...CHART_DEFAULTS.plugins.legend,
            display: true,
            labels: {
              ...CHART_DEFAULTS.plugins.legend.labels,
              filter: item => item.text !== 'Break-even',
            },
          },
          tooltip: {
            ...CHART_DEFAULTS.plugins.tooltip,
            callbacks: {
              label: ctx2 => {
                const d = ctx2.raw;
                return ` ${fmtPlayerDim(d.player, d.position, d.team)} — Cap $${fmt1(d.x)}, ${scatterYMode === 'value' ? 'Value' : 'Surplus'} $${fmt1(d.y)}`;
              }
            }
          }
        },
        scales: {
          x: {
            ...CHART_DEFAULTS.scales.x,
            title: { display: true, text: xLabel, color: THEME.muted, font: { size: 11 } },
            min: 0,
          },
          y: {
            ...CHART_DEFAULTS.scales.y,
            title: { display: true, text: yLabel, color: THEME.muted, font: { size: 11 } },
          }
        }
      }
    });

    _setupScatterInteraction(scatterChartInstance, canvas);
  }

  function _updateScatterHighlight() {
    if (!scatterChartInstance) return;
    scatterChartInstance.data.datasets.forEach(ds => {
      if (ds.type !== 'scatter') return;
      ds.backgroundColor = ds.data.map(d => {
        const base = scatterColorMode === 'position'
          ? (POS_COLORS[d.position] || THEME.accent)
          : (_teamColorMap && _teamColorMap[d.team]) || THEME.accent;
        return hexToRgba(base, _pointAlpha(d.player));
      });
      ds.borderColor = ds.data.map(d => {
        const base = scatterColorMode === 'position'
          ? (POS_COLORS[d.position] || THEME.accent)
          : (_teamColorMap && _teamColorMap[d.team]) || THEME.accent;
        return hexToRgba(base, Math.min(_pointAlpha(d.player) + 0.2, 1));
      });
      ds.pointRadius      = ds.data.map(d => _pointRadius(d.player));
      ds.pointHoverRadius = ds.data.map(d => _pointRadius(d.player) + 2);
    });
    scatterChartInstance.update('none');
  }

  function _updateScatterAndTable() {
    _updateScatterHighlight();
    const clearWrap = document.getElementById('scatter-clear-wrap');
    if (clearWrap) clearWrap.hidden = scatterSelection.size === 0;
    renderSurplusTable(getFilteredSurplus());
  }

  function _setupScatterInteraction(chart, canvas) {
    const overlay = document.getElementById('scatter-select-box');
    let dragStart = null;
    let isDragging = false;

    function canvasOffset(e) {
      const rect = canvas.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    canvas.addEventListener('mousedown', e => {
      const pos = canvasOffset(e);
      dragStart = pos;
      isDragging = false;
    });

    canvas.addEventListener('mousemove', e => {
      if (!dragStart || !e.buttons) return;
      const pos = canvasOffset(e);
      const dx = pos.x - dragStart.x;
      const dy = pos.y - dragStart.y;
      if (!isDragging && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
      isDragging = true;
      if (overlay) {
        overlay.style.display = 'block';
        overlay.style.left   = Math.min(dragStart.x, pos.x) + 'px';
        overlay.style.top    = Math.min(dragStart.y, pos.y) + 'px';
        overlay.style.width  = Math.abs(dx) + 'px';
        overlay.style.height = Math.abs(dy) + 'px';
      }
    });

    canvas.addEventListener('mouseup', e => {
      if (overlay) overlay.style.display = 'none';

      if (!dragStart) return;
      const pos = canvasOffset(e);

      if (isDragging) {
        // Convert pixel rect to data coords
        const x0 = Math.min(dragStart.x, pos.x);
        const x1 = Math.max(dragStart.x, pos.x);
        const y0 = Math.min(dragStart.y, pos.y);
        const y1 = Math.max(dragStart.y, pos.y);

        const xScale = chart.scales.x;
        const yScale = chart.scales.y;
        const dataX0 = xScale.getValueForPixel(x0);
        const dataX1 = xScale.getValueForPixel(x1);
        const dataY0 = yScale.getValueForPixel(y1); // pixel y is inverted
        const dataY1 = yScale.getValueForPixel(y0);

        const inRect = new Set();
        chart.data.datasets.forEach(ds => {
          if (ds.type !== 'scatter') return;
          ds.data.forEach(d => {
            if (d.x >= dataX0 && d.x <= dataX1 && d.y >= dataY0 && d.y <= dataY1) {
              inRect.add(d.player);
            }
          });
        });

        if (e.metaKey || e.ctrlKey) {
          inRect.forEach(p => scatterSelection.add(p));
        } else {
          scatterSelection = inRect;
        }
      } else {
        // Single click
        const elements = chart.getElementsAtEventForMode(e, 'point', { intersect: true }, false);
        if (elements.length) {
          const el = elements[0];
          const ds = chart.data.datasets[el.datasetIndex];
          if (ds.type === 'scatter') {
            const d = ds.data[el.index];
            if (e.metaKey || e.ctrlKey) {
              if (scatterSelection.has(d.player)) {
                scatterSelection.delete(d.player);
              } else {
                scatterSelection.add(d.player);
              }
            } else {
              scatterSelection = new Set([d.player]);
            }
          }
        } else {
          scatterSelection = new Set();
        }
      }

      dragStart = null;
      isDragging = false;
      _updateScatterAndTable();
    });

    canvas.addEventListener('mouseleave', () => {
      if (overlay) overlay.style.display = 'none';
      dragStart = null;
      isDragging = false;
    });
  }

  function refreshSurplus() {
    // Reset sort to the primary surplus column for the active window.
    surplusSortKey = surplusWindow === 'contract'
      ? 'contract_total_surplus'
      : surplusFields().surplus;
    surplusSortAsc = false;
    updateSurplusHeaders();
    renderSurplusScatter();
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

  function computeCapRemaining(team, currentCapUsage) {
    const baseCap = (typeof LEAGUE_CONFIG !== 'undefined' && LEAGUE_CONFIG['cap.base_cap']) || 0;
    const adj = (typeof TEAM_ADJUSTMENTS !== 'undefined' && TEAM_ADJUSTMENTS[team]) || {};
    const dm = +(adj.dead_money || 0);
    const ct = +(adj.cap_transactions || 0);
    const ro = +(adj.rollover || 0);
    return baseCap - currentCapUsage - dm - ct + ro;
  }

  function getMarketMultiplier() {
    if (typeof window.getCapEnvironment === 'function') {
      const env = window.getCapEnvironment();
      if (env && typeof env.market_multiplier === 'number' && !isNaN(env.market_multiplier)) {
        return env.market_multiplier;
      }
    }
    if (typeof FA_MARKET_ENV !== 'undefined' &&
        typeof FA_MARKET_ENV.market_multiplier === 'number' &&
        !isNaN(FA_MARKET_ENV.market_multiplier)) {
      return FA_MARKET_ENV.market_multiplier;
    }
    return 1;
  }

  // Placeholder: pick valuations are not yet modeled. Returning 0 keeps the
  // dataset/column wired so the future implementation only needs to swap in
  // the real per-team value.
  function getPickValue(_team) { return 0; }

  function getRosterValueBreakdown(row, fields, multiplier) {
    const playerValue  = +(row[fields.value] || 0);
    const capRemaining = computeCapRemaining(row.team, row.current_cap_usage);
    const capAdjCap    = Math.max(capRemaining, 0) * multiplier;
    const pickValue    = getPickValue(row.team);
    return {
      playerValue,
      capAdjCap,
      pickValue,
      total: playerValue + capAdjCap + pickValue,
    };
  }

  function renderCapChart() {
    if (capChartInstance) { capChartInstance.destroy(); capChartInstance = null; }
    const ctx = document.getElementById('chart-cap-health');
    if (!ctx || !CAP_HEALTH_DATA.length) return;

    const fields     = teamFields();
    const labels     = windowLabels();
    const multiplier = getMarketMultiplier();

    const rows = CAP_HEALTH_DATA.map(r => ({
      row: r,
      breakdown: getRosterValueBreakdown(r, fields, multiplier),
    }));
    rows.sort((a, b) => b.breakdown.total - a.breakdown.total);

    // Short team labels — take part after " | " if present, else use full name
    const teamLabels = rows.map(({ row }) => {
      const parts = row.team.split('|');
      return parts.length > 1 ? parts[parts.length - 1].trim() : row.team;
    });

    const playerColor = THEME.accent;
    const capColor    = '#98c379';
    const pickColor   = '#d19a66';

    capChartInstance = new Chart(ctx.getContext('2d'), {
      type: 'bar',
      data: {
        labels: teamLabels,
        datasets: [
          {
            label: `Players (${labels.value})`,
            data: rows.map(({ breakdown }) => +breakdown.playerValue.toFixed(1)),
            backgroundColor: hexToRgba(playerColor, 0.7),
            borderColor:     playerColor,
            borderWidth: 1,
            stack: 'roster',
          },
          {
            label: `Cap Space × ${multiplier.toFixed(2)}`,
            data: rows.map(({ breakdown }) => +breakdown.capAdjCap.toFixed(1)),
            backgroundColor: hexToRgba(capColor, 0.7),
            borderColor:     capColor,
            borderWidth: 1,
            stack: 'roster',
          },
          {
            label: 'Picks (TBD)',
            data: rows.map(({ breakdown }) => +breakdown.pickValue.toFixed(1)),
            backgroundColor: hexToRgba(pickColor, 0.7),
            borderColor:     pickColor,
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
              title: ctx2 => rows[ctx2[0].dataIndex]?.row.team ?? '',
              label: ctx2 => {
                const entry = rows[ctx2[0]?.dataIndex ?? ctx2.dataIndex];
                if (!entry) return '';
                const { row, breakdown } = entry;
                return [
                  ` Players (${labels.value}): $${breakdown.playerValue.toFixed(1)}`,
                  ` Market-Adj Cap: $${breakdown.capAdjCap.toFixed(1)}  (× ${multiplier.toFixed(2)})`,
                  ` Picks: $${breakdown.pickValue.toFixed(1)}`,
                  ` Total Roster Value: $${breakdown.total.toFixed(1)}`,
                  ` ${labels.cap}: $${(row[fields.cap] || 0).toFixed(1)}`,
                  ` ${labels.surplus}: $${(row[fields.surplus] || 0).toFixed(1)}`,
                  ` Dead $: $${(row.dead_money_cut_now_nominal || 0).toFixed(1)}`,
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
            title: { display: true, text: 'Total Roster Value ($)', color: THEME.muted, font: { size: 11 } }
          }
        }
      }
    });
  }

  function renderCapTable() {
    const tbody = document.getElementById('cap-table-body');
    if (!tbody) return;

    const fields     = teamFields();
    const multiplier = getMarketMultiplier();

    const rows = CAP_HEALTH_DATA.map(r => ({
      row: r,
      breakdown: getRosterValueBreakdown(r, fields, multiplier),
    }));
    rows.sort((a, b) => b.breakdown.total - a.breakdown.total);

    tbody.innerHTML = rows.map(({ row: r, breakdown }) => {
      const surpColor = surplusColor(r[fields.surplus]);
      const capRemaining = computeCapRemaining(r.team, r.current_cap_usage);
      const crColor = capRemaining >= 0 ? 'var(--surplus-pos)' : 'var(--surplus-neg)';
      return `
        <tr>
          <td>${r.team}</td>
          <td class="num">${fmt1(r.current_cap_usage)}</td>
          <td class="num" style="color:${crColor};">${fmt1(capRemaining)}</td>
          <td class="num">${fmt1(breakdown.capAdjCap)}</td>
          <td class="num">${fmt1(breakdown.total)}</td>
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
    if (tabId === 'free-agent-market' && typeof window.initFreeAgentMarket === 'function') {
      window.initFreeAgentMarket();
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

    // Surplus window selector — populate per-year options from config then wire change handler.
    const surplusWindowSel = document.getElementById('surplus-window');
    if (surplusWindowSel) {
      for (let i = 0; i < 4; i++) {
        const opt = document.createElement('option');
        opt.value = `y${i}`;
        opt.textContent = String(tvYearLabel(i));
        surplusWindowSel.appendChild(opt);
      }
      surplusWindowSel.addEventListener('change', () => {
        surplusWindow = surplusWindowSel.value;
        refreshSurplus();
      });
    }

    // Cap Health window selector — independent of surplus window.
    const capWindowSel = document.getElementById('cap-window');
    if (capWindowSel) {
      capWindowSel.addEventListener('change', () => {
        valuationWindow = capWindowSel.value;
        refreshCap();
      });
    }

    // Scatter Y-axis toggle
    document.querySelectorAll('#scatter-y-toggle .toggle-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        scatterYMode = btn.dataset.value;
        document.querySelectorAll('#scatter-y-toggle .toggle-btn')
          .forEach(b => b.classList.toggle('active', b === btn));
        scatterSelection = new Set();
        renderSurplusScatter();
        renderSurplusTable(getFilteredSurplus());
      });
    });

    // Scatter color toggle
    document.querySelectorAll('#scatter-color-toggle .toggle-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        scatterColorMode = btn.dataset.value;
        document.querySelectorAll('#scatter-color-toggle .toggle-btn')
          .forEach(b => b.classList.toggle('active', b === btn));
        scatterSelection = new Set();
        renderSurplusScatter();
        renderSurplusTable(getFilteredSurplus());
      });
    });

    // Scatter clear-selection button
    const scatterClearBtn = document.getElementById('scatter-clear-btn');
    if (scatterClearBtn) {
      scatterClearBtn.addEventListener('click', () => {
        scatterSelection = new Set();
        _updateScatterAndTable();
      });
    }

    // Surplus position/team filters
    ['surplus-position', 'surplus-team'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('change', () => {
        if (id === 'surplus-position') surplusFilter.position = el.value;
        if (id === 'surplus-team')     surplusFilter.team     = el.value;
        scatterSelection = new Set();
        renderSurplusScatter();
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
