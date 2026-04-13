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

  renderValueCurvesChart();
}

function renderValueCurvesChart() {
  const seasonVal = document.getElementById('vc-season').value;
  const topN      = +document.getElementById('vc-topn').value;

  destroyChart('value-curves');

  const canvas = document.getElementById('chart-value-curves');
  const ctx    = canvas.getContext('2d');

  if (seasonVal === 'all') {
    _vcRenderAllSeasons(ctx, topN);
  } else {
    _vcRenderSingleSeason(ctx, +seasonVal, topN);
  }
}

// ── Shared axis / plugin config ───────────────────────────────────────────────

function _vcBaseOptions(extraTooltip) {
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
          text: 'Position Rank',
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

function _vcRenderSingleSeason(ctx, season, topN) {
  const datasets = POSITIONS.map(pos => {
    const rows = SEASON_DATA
      .filter(r => r.season === season && r.position === pos && r.pos_rank <= topN)
      .sort((a, b) => a.pos_rank - b.pos_rank);

    const color = POS_COLORS[pos];
    return {
      label: pos,
      data: rows.map(r => ({
        x:      r.pos_rank,
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
        return `${ctx.dataset.label} #${p.x}: ${p.player} — $${p.y.toFixed(2)}`;
      }
    }
  });

  chartInstances['value-curves'] = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options
  });
}

// ── All-Seasons mode ──────────────────────────────────────────────────────────

function _vcRenderAllSeasons(ctx, topN) {
  const datasets = [];

  POSITIONS.forEach(pos => {
    const color = POS_COLORS[pos];

    // All individual points (one per player-season within top-N)
    const scatterData = SEASON_DATA
      .filter(r => r.position === pos && r.pos_rank <= topN)
      .map(r => ({
        x:      r.pos_rank,
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
          return `${pos}: ${p.player} ${p.season} — $${p.y.toFixed(2)}`;
        }
        // average line
        return `${ctx.dataset.label} avg #${p.x}: $${p.y.toFixed(2)}`;
      }
    }
  });

  // Hide scatter series from legend
  options.plugins.legend.labels.filter =
    (item, data) => !data.datasets[item.datasetIndex].hideLegend;

  chartInstances['value-curves'] = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options
  });
}
