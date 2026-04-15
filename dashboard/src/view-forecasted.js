// Phase 2 — Forecasted Values
// Two sub-tabs: TV Forecast (sortable table with sparklines) and ADP→ESV scatter.

(function () {
  // ── State ─────────────────────────────────────────────────────────────────
  let adpChartInstance  = null;
  let tvSortKey         = 'tv_y0';
  let tvSortAsc         = false;
  let tvFilter          = { position: 'All', team: 'All', rosteredOnly: false };
  let tvSelectedPlayers = [];   // player name strings currently filtered via chips
  let adpFilter         = { position: 'All' };

  // ── Helpers ───────────────────────────────────────────────────────────────

  function fmt1(v)      { return typeof v === 'number' ? v.toFixed(1) : '–'; }
  function fmtInt(v)    { return typeof v === 'number' ? Math.round(v) : '–'; }
  function fmtDollar(v) { return typeof v === 'number' ? `$${v.toFixed(1)}` : '–'; }

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
      if (tvSelectedPlayers.length > 0 && !tvSelectedPlayers.includes(r.player)) return false;
      return true;
    });
  }

  // ── Sparkline (pure inline SVG, no library) ───────────────────────────────

  function tvSparkline(r) {
    const vals = [r.tv_y0, r.tv_y1, r.tv_y2, r.tv_y3];
    const W = 60, H = 22, PAD = 3;
    const min   = Math.min(...vals);
    const max   = Math.max(...vals);
    const range = max - min || 1;   // avoid divide-by-zero for flat trajectories

    const yPx = v => PAD + (H - 2 * PAD) * (1 - (v - min) / range);
    const xPx = i => PAD + i * ((W - 2 * PAD) / 3);

    const points = vals.map((v, i) => `${xPx(i).toFixed(1)},${yPx(v).toFixed(1)}`).join(' ');

    // Color-code direction: blue = rising, red = declining, gray = flat (±0.5 threshold)
    const delta  = r.tv_y3 - r.tv_y0;
    const stroke = delta > 0.5  ? '#6c8cff'
                 : delta < -0.5 ? '#e06c75'
                 :                '#8b90a5';

    // End dot marks the Y3 value
    const ex = xPx(3).toFixed(1);
    const ey = yPx(r.tv_y3).toFixed(1);

    return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="display:block;overflow:visible;">` +
      `<polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>` +
      `<circle cx="${ex}" cy="${ey}" r="2.5" fill="${stroke}"/>` +
      `</svg>`;
  }

  // ── TV Table ──────────────────────────────────────────────────────────────

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
        <td class="num tv-sparkline-cell">${tvSparkline(r)}</td>
        <td class="num">${fmtDollar(r.tv_y0)}</td>
        <td class="num">${fmtDollar(r.tv_y1)}</td>
        <td class="num">${fmtDollar(r.tv_y2)}</td>
        <td class="num">${fmtDollar(r.tv_y3)}</td>
        <td class="num">${fmtInt(r.adp)}</td>
        <td class="num">${fmtDollar(r.esv_p25)}</td>
        <td class="num">${fmtDollar(r.esv_p50)}</td>
        <td class="num">${fmtDollar(r.esv_p75)}</td>
      </tr>
    `).join('');
  }

  function refreshTV() {
    renderTVTable(getFilteredTV());
  }

  // ── TV Player Search ──────────────────────────────────────────────────────

  function _tvWireSearch() {
    const input    = document.getElementById('tv-search');
    const dropdown = document.getElementById('tv-dropdown');
    if (!input || !dropdown) return;

    input.addEventListener('input', () => {
      const q = input.value.trim();
      if (q.length < 2) { dropdown.hidden = true; return; }
      _tvRenderDropdown(_tvBuildItems(q));
    });

    // blur hides the dropdown; mousedown on items uses preventDefault()
    // so blur fires only after the mousedown handler completes.
    input.addEventListener('blur', () => { dropdown.hidden = true; });
  }

  function _tvBuildItems(query) {
    const lq = query.toLowerCase();
    return ALL_TV_PLAYERS
      .filter(p => p.toLowerCase().includes(lq))
      .slice(0, 12);
  }

  function _tvRenderDropdown(players) {
    const input    = document.getElementById('tv-search');
    const dropdown = document.getElementById('tv-dropdown');
    dropdown.innerHTML = '';

    if (players.length === 0) { dropdown.hidden = true; return; }

    players.forEach(player => {
      const el = document.createElement('div');
      el.className = 'pt-dropdown-item';   // reuse existing class
      el.textContent = player;

      el.addEventListener('mousedown', e => {
        e.preventDefault();
        _tvAddPlayer(player);
        input.value = '';
        dropdown.hidden = true;
      });

      dropdown.appendChild(el);
    });

    dropdown.hidden = false;
  }

  function _tvAddPlayer(player) {
    if (tvSelectedPlayers.includes(player)) return;   // no duplicates
    tvSelectedPlayers.push(player);
    _tvRenderChips();
    refreshTV();
  }

  function _tvRemovePlayer(player) {
    tvSelectedPlayers = tvSelectedPlayers.filter(p => p !== player);
    _tvRenderChips();
    refreshTV();
  }

  function _tvRenderChips() {
    const container = document.getElementById('tv-chips');
    if (!container) return;
    container.innerHTML = '';

    tvSelectedPlayers.forEach(player => {
      const chip = document.createElement('div');
      chip.className = 'pt-chip';           // reuse existing class

      const lbl = document.createElement('span');
      lbl.className = 'pt-chip-label';
      lbl.textContent = player;

      const rm = document.createElement('button');
      rm.className = 'pt-chip-remove';
      rm.setAttribute('aria-label', `Remove ${player}`);
      rm.textContent = '×';
      rm.addEventListener('click', () => _tvRemovePlayer(player));

      chip.appendChild(lbl);
      chip.appendChild(rm);
      container.appendChild(chip);
    });
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
    _tvWireSearch();

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
