// View 5: Positional Efficiency
// Shows what % of theoretical SAV owners actually capture (ESV/SAV) by rank.
// Single-season: one line per position.
// All-Seasons: scatter (individual) + bold average line, same pattern as Value Curves.

let peInitialized = false;

function initPositionalEfficiency() {
  if (peInitialized) {
    renderPositionalEfficiencyChart();
    return;
  }
  peInitialized = true;

  // ── Season dropdown — default "All Seasons" ───────────────────────────────
  const seasonSel = document.getElementById('pe-season');

  const allOpt = document.createElement('option');
  allOpt.value = 'all';
  allOpt.textContent = 'All Seasons (avg)';
  seasonSel.appendChild(allOpt);

  [...ALL_SEASONS].reverse().forEach(s => {
    const opt = document.createElement('option');
    opt.value = String(s);
    opt.textContent = String(s);
    seasonSel.appendChild(opt);
  });
  // Leave value = 'all' (first option is already selected)

  seasonSel.addEventListener('change', renderPositionalEfficiencyChart);

  renderPositionalEfficiencyChart();
}

function renderPositionalEfficiencyChart() {
  const seasonVal = document.getElementById('pe-season').value;

  destroyChart('positional-efficiency');

  const canvas = document.getElementById('chart-positional-efficiency');
  const ctx    = canvas.getContext('2d');

  if (seasonVal === 'all') {
    _peAllSeasons(ctx);
  } else {
    _peSingleSeason(ctx, +seasonVal);
  }
}

// ── Data helper ───────────────────────────────────────────────────────────────
// Top-24 players by ESV for a given (pos, season), filtered to sav > 0.
// Returns [{x: rank, y: pct, player, position}]

function _peTopData(season, pos) {
  return SEASON_DATA
    .filter(r => r.season === season && r.position === pos && r.sav > 0)
    .sort((a, b) => b.esv - a.esv)
    .slice(0, 24)
    .map((r, i) => ({
      x:        i + 1,
      y:        (r.esv / r.sav) * 100,
      player:   r.player,
      position: r.position
    }));
}

// ── Shared options ────────────────────────────────────────────────────────────

function _peOptions(extraTooltip, legendFilter) {
  const opts = {
    responsive: true,
    maintainAspectRatio: false,
    parsing: false,
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
        min: 1,
        title: {
          display: true,
          text: 'Position Rank',
          color: THEME.muted,
          font: { family: 'DM Sans', size: 12 }
        },
        ticks: {
          stepSize: 1,
          maxTicksLimit: 12,
          color: THEME.muted,
          font: { family: 'DM Sans', size: 11 }
        },
        grid: { color: THEME.border }
      },
      y: {
        min: 0,
        title: {
          display: true,
          text: 'ESV / SAV (%)',
          color: THEME.muted,
          font: { family: 'DM Sans', size: 12 }
        },
        ticks: {
          color: THEME.muted,
          font: { family: 'JetBrains Mono', size: 11 },
          callback: v => `${v.toFixed(0)}%`
        },
        grid: { color: THEME.border }
      }
    }
  };

  if (legendFilter) {
    opts.plugins.legend.labels.filter = legendFilter;
  }

  return opts;
}

// ── Single-season ─────────────────────────────────────────────────────────────

function _peSingleSeason(ctx, season) {
  const datasets = POSITIONS.map(pos => {
    const color = POS_COLORS[pos];
    return {
      label:            pos,
      data:             _peTopData(season, pos),
      borderColor:      color,
      backgroundColor:  hexToRgba(color, 0.12),
      fill:             false,
      tension:          0.3,
      pointRadius:      3,
      pointHoverRadius: 6,
      borderWidth:      2
    };
  });

  const options = _peOptions({
    callbacks: {
      title: () => '',
      label: ctx => {
        const p = ctx.raw;
        return `${ctx.dataset.label} #${p.x}: ${p.player} — ${p.y.toFixed(1)}%`;
      }
    }
  });

  chartInstances['positional-efficiency'] = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options
  });
}

// ── All-seasons ───────────────────────────────────────────────────────────────

function _peAllSeasons(ctx) {
  const datasets = [];

  POSITIONS.forEach(pos => {
    const color = POS_COLORS[pos];

    // Collect all individual season points
    const scatterData = [];
    ALL_SEASONS.forEach(season => {
      _peTopData(season, pos).forEach(p => {
        scatterData.push({ ...p, season });
      });
    });
    scatterData.sort((a, b) => a.x - b.x);

    // Average efficiency at each rank across all seasons
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

    // Individual season scatter (hidden from legend)
    datasets.push({
      label:            `${pos} seasons`,
      data:             scatterData,
      showLine:         false,
      backgroundColor:  hexToRgba(color, 0.2),
      borderColor:      'transparent',
      pointRadius:      2.5,
      pointHoverRadius: 5,
      fill:             false,
      hideLegend:       true
    });

    // Average line (shown in legend)
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

  const options = _peOptions(
    {
      callbacks: {
        title: () => '',
        label: ctx => {
          const p = ctx.raw;
          if (ctx.dataset.hideLegend) {
            const pos = ctx.dataset.label.split(' ')[0];
            return `${pos}: ${p.player} ${p.season} — ${p.y.toFixed(1)}%`;
          }
          return `${ctx.dataset.label} avg #${p.x}: ${p.y.toFixed(1)}%`;
        }
      }
    },
    (item, data) => !data.datasets[item.datasetIndex].hideLegend
  );

  chartInstances['positional-efficiency'] = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options
  });
}
