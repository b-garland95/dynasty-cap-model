// View 1: Value Curves
// Shows how dollar value drops off by positional rank within a season.
// Single-season mode: filled line per position.
// All-Seasons mode:   scatter (individual seasons) + bold average line.

let vcInitialized = false;

function initValueCurves() {
  if (vcInitialized) {
    // Controls already wired; just re-render with current values.
    renderValueCurvesChart();
    return;
  }
  vcInitialized = true;

  // ── Season dropdown ───────────────────────────────────────────────────────
  const seasonSel = document.getElementById('vc-season');
  const allOpt = document.createElement('option');
  allOpt.value = 'all';
  allOpt.textContent = 'All Seasons (avg)';
  seasonSel.appendChild(allOpt);

  // Seasons in descending order so latest is at top (not selected yet)
  [...ALL_SEASONS].reverse().forEach(s => {
    const opt = document.createElement('option');
    opt.value = String(s);
    opt.textContent = String(s);
    seasonSel.appendChild(opt);
  });

  // Default: latest season
  seasonSel.value = String(ALL_SEASONS[ALL_SEASONS.length - 1]);

  // ── Top-N dropdown ────────────────────────────────────────────────────────
  const topNSel = document.getElementById('vc-topn');
  [15, 24, 36, 50].forEach(n => {
    const opt = document.createElement('option');
    opt.value = String(n);
    opt.textContent = `Top ${n}`;
    if (n === 24) opt.selected = true;
    topNSel.appendChild(opt);
  });

  // ── Change handlers ───────────────────────────────────────────────────────
  seasonSel.addEventListener('change', renderValueCurvesChart);
  topNSel.addEventListener('change', renderValueCurvesChart);
  document.getElementById('vc-xaxis').addEventListener('change', renderValueCurvesChart);

  renderValueCurvesChart();
}

function renderValueCurvesChart() {
  const seasonVal  = document.getElementById('vc-season').value;
  const topN       = +document.getElementById('vc-topn').value;
  const usePreseason = document.getElementById('vc-xaxis').value === 'preseason';

  destroyChart('value-curves');

  const canvas = document.getElementById('chart-value-curves');
  const ctx    = canvas.getContext('2d');

  if (seasonVal === 'all') {
    _vcRenderAllSeasons(ctx, topN, usePreseason);
  } else {
    _vcRenderSingleSeason(ctx, +seasonVal, topN, usePreseason);
  }
}

// ── Shared axis / plugin config ───────────────────────────────────────────────

function _vcBaseOptions(extraTooltip, xAxisLabel = 'Position Rank') {
  return {
    responsive: true,
    maintainAspectRatio: false,
    parsing: false,       // data is already {x, y[, player, season]}
    animation: { duration: 300 },
    plugins: {
      legend: {
        position: 'top',
        align: 'end',
        labels: {
          color: THEME.text,
          font: { family: 'DM Sans', size: 12 },
          usePointStyle: true,
          pointStyleWidth: 14
        }
      },
      tooltip: {
        backgroundColor: THEME.surface2,
        borderColor: THEME.border,
        borderWidth: 1,
        titleColor: THEME.text,
        bodyColor: THEME.muted,
        titleFont: { family: 'DM Sans', size: 12, weight: '600' },
        bodyFont: { family: 'JetBrains Mono', size: 12 },
        padding: 10,
        ...extraTooltip
      }
    },
    scales: {
      x: {
        type: 'linear',
        title: {
          display: true,
          text: xAxisLabel,
          color: THEME.muted,
          font: { family: 'DM Sans', size: 12 }
        },
        min: 1,
        ticks: {
          stepSize: 1,
          color: THEME.muted,
          font: { family: 'DM Sans', size: 11 },
          maxTicksLimit: 16
        },
        grid: { color: THEME.border }
      },
      y: {
        title: {
          display: true,
          text: 'Dollar Value ($)',
          color: THEME.muted,
          font: { family: 'DM Sans', size: 12 }
        },
        min: 0,
        ticks: {
          color: THEME.muted,
          font: { family: 'JetBrains Mono', size: 11 },
          callback: v => `$${v}`
        },
        grid: { color: THEME.border }
      }
    }
  };
}

// ── Single-season mode ────────────────────────────────────────────────────────

function _vcRenderSingleSeason(ctx, season, topN, usePreseason) {
  const rankField = usePreseason ? 'preseason_pos_rank' : 'pos_rank';
  const xAxisLabel = usePreseason ? 'Pre-season Position Rank' : 'Position Rank';

  const datasets = POSITIONS.map(pos => {
    const rows = SEASON_DATA
      .filter(r => r.season === season && r.position === pos &&
                   r[rankField] != null && r[rankField] <= topN)
      .sort((a, b) => a[rankField] - b[rankField]);

    const color = POS_COLORS[pos];
    return {
      label: pos,
      data: rows.map(r => ({
        x:      r[rankField],
        y:      r.dollar_value,
        player: r.player
      })),
      borderColor:     color,
      backgroundColor: hexToRgba(color, 0.15),
      fill:            'origin',
      tension:         0.3,
      pointRadius:     3,
      pointHoverRadius: 6,
      borderWidth:     2
    };
  });

  const options = _vcBaseOptions({
    callbacks: {
      title: () => '',
      label: ctx => {
        const p = ctx.raw;
        return `${ctx.dataset.label} #${p.x}: ${p.player} — $${p.y.toFixed(1)}`;
      }
    }
  }, xAxisLabel);

  chartInstances['value-curves'] = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options
  });
}

// ── All-Seasons mode ──────────────────────────────────────────────────────────

function _vcRenderAllSeasons(ctx, topN, usePreseason) {
  const rankField  = usePreseason ? 'preseason_pos_rank' : 'pos_rank';
  const xAxisLabel = usePreseason ? 'Pre-season Position Rank' : 'Position Rank';
  const datasets   = [];

  POSITIONS.forEach(pos => {
    const color = POS_COLORS[pos];

    // All individual points (one per player-season within top-N)
    const scatterData = SEASON_DATA
      .filter(r => r.position === pos && r[rankField] != null && r[rankField] <= topN)
      .map(r => ({
        x:      r[rankField],
        y:      r.dollar_value,
        player: r.player,
        season: r.season
      }))
      .sort((a, b) => a.x - b.x);

    // Average dollar_value at each rank across all seasons
    const byRank = {};
    scatterData.forEach(p => {
      (byRank[p.x] = byRank[p.x] || []).push(p.y);
    });
    const avgData = Object.entries(byRank)
      .map(([rank, vals]) => ({
        x: +rank,
        y: vals.reduce((a, b) => a + b, 0) / vals.length
      }))
      .sort((a, b) => a.x - b.x);

    // Scatter dataset — hidden from legend
    datasets.push({
      label:            `${pos} seasons`,
      data:             scatterData,
      showLine:         false,
      backgroundColor:  hexToRgba(color, 0.2),
      borderColor:      'transparent',
      pointRadius:      2.5,
      pointHoverRadius: 5,
      fill:             false,
      hideLegend:       true  // custom flag used in legend & tooltip filter
    });

    // Average line — shown in legend
    datasets.push({
      label:            pos,
      data:             avgData,
      borderColor:      color,
      backgroundColor:  'transparent',
      borderWidth:      3,
      pointRadius:      0,
      pointHoverRadius: 5,
      fill:             false,
      tension:          0.3
    });
  });

  const options = _vcBaseOptions({
    callbacks: {
      title: () => '',
      label: ctx => {
        const p = ctx.raw;
        // scatter dot
        if (ctx.dataset.hideLegend) {
          const pos = ctx.dataset.label.split(' ')[0];
          return `${pos}: ${p.player} ${p.season} — $${p.y.toFixed(1)}`;
        }
        // average line
        return `${ctx.dataset.label} avg #${p.x}: $${p.y.toFixed(1)}`;
      }
    }
  }, xAxisLabel);

  // Hide scatter series from legend
  options.plugins.legend.labels.filter =
    (item, data) => !data.datasets[item.datasetIndex].hideLegend;

  chartInstances['value-curves'] = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options
  });
}

// ── Historical Season Grid ────────────────────────────────────────────────────

(function () {
  // ── State ──────────────────────────────────────────────────────────────────
  let _gridInitialized = false;
  let _activePosSet    = new Set(['QB', 'RB', 'WR', 'TE']);
  let _activeYearSet   = null; // null = all years
  let _preMin          = null;
  let _preMax          = null;
  let _actMin          = null;
  let _actMax          = null;
  let _yosMin          = null;
  let _yosMax          = null;
  let _search          = '';
  let _sortKey         = 'season';
  let _sortAsc         = false;

  // ── Helpers ────────────────────────────────────────────────────────────────

  function _yearsOfService(player, season) {
    const bio = HEADSHOT_MAP[player];
    const rookieSeason = bio && bio.rookie_season ? +bio.rookie_season : null;
    if (!rookieSeason) return null;
    return season - rookieSeason + 1;
  }

  // ── Filter + sort ──────────────────────────────────────────────────────────

  function _getRows() {
    const q = _search.trim().toLowerCase();

    return SEASON_DATA
      .filter(r => {
        if (!_activePosSet.has(r.position)) return false;
        if (_activeYearSet && !_activeYearSet.has(r.season)) return false;
        if (_preMin !== null && (r.preseason_pos_rank == null || r.preseason_pos_rank < _preMin)) return false;
        if (_preMax !== null && (r.preseason_pos_rank == null || r.preseason_pos_rank > _preMax)) return false;
        if (_actMin !== null && (r.pos_rank == null || r.pos_rank < _actMin)) return false;
        if (_actMax !== null && (r.pos_rank == null || r.pos_rank > _actMax)) return false;
        if (_yosMin !== null || _yosMax !== null) {
          const yos = _yearsOfService(r.player, r.season);
          if (_yosMin !== null && (yos == null || yos < _yosMin)) return false;
          if (_yosMax !== null && (yos == null || yos > _yosMax)) return false;
        }
        if (q && !r.player.toLowerCase().includes(q)) return false;
        return true;
      })
      .map(r => ({
        ...r,
        years_of_service: _yearsOfService(r.player, r.season)
      }))
      .sort((a, b) => {
        let av = a[_sortKey];
        let bv = b[_sortKey];
        // Nulls always last
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === 'string') {
          return _sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
        }
        return _sortAsc ? av - bv : bv - av;
      });
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  function _render() {
    const rows  = _getRows();
    const tbody = document.getElementById('vc-grid-tbody');
    const count = document.getElementById('vc-grid-count');
    if (!tbody) return;

    count.textContent = `${rows.length.toLocaleString()} rows`;

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--muted);">No seasons match the current filters.</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(r => {
      const pos      = (r.position || '').toLowerCase();
      const yos      = r.years_of_service != null ? `Yr ${r.years_of_service}` : '–';
      const preRank  = r.preseason_pos_rank != null ? r.preseason_pos_rank : '–';
      const actRank  = r.pos_rank != null ? r.pos_rank : '–';
      const dollarV  = r.dollar_value != null ? `$${r.dollar_value.toFixed(1)}` : '–';

      // Show rank delta (pre → actual) when both are available
      let deltaBadge = '';
      if (r.preseason_pos_rank != null && r.pos_rank != null) {
        const delta = r.preseason_pos_rank - r.pos_rank; // positive = outperformed
        if (delta !== 0) {
          const sign  = delta > 0 ? '+' : '';
          const cls   = delta > 0 ? 'pos' : 'neg';
          deltaBadge  = `<span class="vc-rank-delta ${cls}">(${sign}${delta})</span>`;
        }
      }

      return `<tr>
        <td>${playerLink(r.player)}</td>
        <td><span class="pos-badge pos-${pos}">${r.position}</span></td>
        <td class="num">${r.season}</td>
        <td class="num">${yos}</td>
        <td class="num">${preRank}</td>
        <td class="num">${actRank}${deltaBadge}</td>
        <td class="num">${dollarV}</td>
      </tr>`;
    }).join('');
  }

  // ── Year chips ─────────────────────────────────────────────────────────────

  function _buildYearChips() {
    const container = document.getElementById('vc-f-year');
    if (!container) return;
    container.innerHTML = '';
    [...ALL_SEASONS].reverse().forEach(s => {
      const btn = document.createElement('button');
      btn.className = 'vc-chip active';
      btn.dataset.value = String(s);
      btn.textContent = String(s);
      btn.addEventListener('click', () => {
        btn.classList.toggle('active');
        _activeYearSet = _buildActiveSet('vc-f-year', ALL_SEASONS.map(String));
        _render();
      });
      container.appendChild(btn);
    });
    _activeYearSet = null; // all active = no filter
  }

  // Returns null (= all selected) or a Set of the selected values
  function _buildActiveSet(containerId, allValues) {
    const chips = document.querySelectorAll(`#${containerId} .vc-chip`);
    const active = [...chips].filter(c => c.classList.contains('active')).map(c => {
      const v = c.dataset.value;
      return isNaN(+v) ? v : +v;
    });
    if (active.length === allValues.length) return null;
    return new Set(active);
  }

  // ── Init ───────────────────────────────────────────────────────────────────

  function initValueCurvesGrid() {
    if (_gridInitialized) {
      _render();
      return;
    }
    _gridInitialized = true;

    // Build year chips once data is available
    _buildYearChips();

    // Position chips
    document.querySelectorAll('#vc-f-pos .vc-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        btn.classList.toggle('active');
        _activePosSet = new Set(
          [...document.querySelectorAll('#vc-f-pos .vc-chip.active')].map(c => c.dataset.value)
        );
        _render();
      });
    });

    // Range inputs — debounced
    let _debounceTimer;
    function _onRangeChange() {
      clearTimeout(_debounceTimer);
      _debounceTimer = setTimeout(() => {
        _preMin = +document.getElementById('vc-f-pre-min').value || null;
        _preMax = +document.getElementById('vc-f-pre-max').value || null;
        _actMin = +document.getElementById('vc-f-act-min').value || null;
        _actMax = +document.getElementById('vc-f-act-max').value || null;
        _yosMin = +document.getElementById('vc-f-yos-min').value || null;
        _yosMax = +document.getElementById('vc-f-yos-max').value || null;
        _render();
      }, 250);
    }
    ['vc-f-pre-min','vc-f-pre-max','vc-f-act-min','vc-f-act-max','vc-f-yos-min','vc-f-yos-max'].forEach(id => {
      document.getElementById(id).addEventListener('input', _onRangeChange);
    });

    // Search input — debounced
    document.getElementById('vc-f-search').addEventListener('input', e => {
      clearTimeout(_debounceTimer);
      _debounceTimer = setTimeout(() => {
        _search = e.target.value;
        _render();
      }, 200);
    });

    // Reset button
    document.getElementById('vc-f-reset').addEventListener('click', () => {
      _activePosSet = new Set(['QB', 'RB', 'WR', 'TE']);
      _activeYearSet = null;
      _preMin = _preMax = _actMin = _actMax = _yosMin = _yosMax = null;
      _search = '';

      document.querySelectorAll('#vc-f-pos .vc-chip, #vc-f-year .vc-chip')
        .forEach(c => c.classList.add('active'));
      ['vc-f-pre-min','vc-f-pre-max','vc-f-act-min','vc-f-act-max','vc-f-yos-min','vc-f-yos-max']
        .forEach(id => { document.getElementById(id).value = ''; });
      document.getElementById('vc-f-search').value = '';
      _render();
    });

    // Column sort
    document.querySelectorAll('#vc-grid-table thead th[data-sort]').forEach(th => {
      th.addEventListener('click', () => {
        if (_sortKey === th.dataset.sort) {
          _sortAsc = !_sortAsc;
        } else {
          _sortKey = th.dataset.sort;
          // Numeric columns default desc; player name defaults asc
          _sortAsc = _sortKey === 'player';
        }
        document.querySelectorAll('#vc-grid-table thead th').forEach(h => {
          h.classList.remove('sort-asc', 'sort-desc');
        });
        th.classList.add(_sortAsc ? 'sort-asc' : 'sort-desc');
        _render();
      });
    });

    _render();
  }

  window.initValueCurvesGrid = initValueCurvesGrid;
})();
