// View 6: Year-over-Year
// Shows how positional value has evolved across seasons.
// Per position: P25 / median / P75 of the top-12 players by selected metric.

let yoyInitialized = false;

function initYearOverYear() {
  if (yoyInitialized) {
    renderYearOverYearChart();
    return;
  }
  yoyInitialized = true;

  // ── Metric dropdown ───────────────────────────────────────────────────────
  const metricSel = document.getElementById('yoy-metric');
  [
    { value: 'dollar_value', label: 'Dollar Value' },
    { value: 'esv',          label: 'ESV' },
    { value: 'total_points', label: 'Total Points' }
  ].forEach(({ value, label }) => {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = label;
    metricSel.appendChild(opt);
  });
  // dollar_value is first ⟹ already selected by default

  // ── Position dropdown ─────────────────────────────────────────────────────
  const posSel = document.getElementById('yoy-position');
  const allOpt = document.createElement('option');
  allOpt.value = 'all';
  allOpt.textContent = 'All Positions';
  posSel.appendChild(allOpt);

  POSITIONS.forEach(pos => {
    const opt = document.createElement('option');
    opt.value = pos;
    opt.textContent = pos;
    posSel.appendChild(opt);
  });

  // ── Change handlers ───────────────────────────────────────────────────────
  metricSel.addEventListener('change', renderYearOverYearChart);
  posSel.addEventListener('change', renderYearOverYearChart);

  renderYearOverYearChart();
}

// ── Stats helpers ─────────────────────────────────────────────────────────────

/**
 * Linear-interpolation percentile on a sorted array.
 * @param {number[]} sorted - ascending-sorted values
 * @param {number}   p      - 0..100
 */
function _pctile(sorted, p) {
  if (sorted.length === 0) return null;
  if (sorted.length === 1) return sorted[0];
  const idx = (p / 100) * (sorted.length - 1);
  const lo  = Math.floor(idx);
  const hi  = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (idx - lo) * (sorted[hi] - sorted[lo]);
}

/**
 * For each season, return { season, p25, median, p75 } for the top-12 players
 * of `pos` ranked by `metricKey` descending.
 */
function _computeYoyStats(pos, metricKey) {
  return ALL_SEASONS.map(season => {
    const top12 = SEASON_DATA
      .filter(r => r.season === season && r.position === pos)
      .sort((a, b) => b[metricKey] - a[metricKey])
      .slice(0, 12);

    if (top12.length === 0) return null;

    const vals = top12.map(r => r[metricKey]).sort((a, b) => a - b);
    return {
      season,
      p25:    _pctile(vals, 25),
      median: _pctile(vals, 50),
      p75:    _pctile(vals, 75)
    };
  }).filter(Boolean);
}

// ── Chart render ──────────────────────────────────────────────────────────────

const YOY_METRIC_LABELS = {
  dollar_value: 'Dollar Value ($)',
  esv:          'ESV',
  total_points: 'Total Points'
};

function renderYearOverYearChart() {
  const metric    = document.getElementById('yoy-metric').value;
  const posFilter = document.getElementById('yoy-position').value;
  const activePosns = posFilter === 'all' ? POSITIONS : [posFilter];
  const labels    = ALL_SEASONS.map(String);

  destroyChart('year-over-year');

  const canvas = document.getElementById('chart-year-over-year');
  const ctx    = canvas.getContext('2d');

  const datasets = [];

  activePosns.forEach(pos => {
    const stats = _computeYoyStats(pos, metric);
    const statMap = Object.fromEntries(stats.map(s => [s.season, s]));
    const color   = POS_COLORS[pos];

    // Align each stat to ALL_SEASONS order; null for missing seasons
    const p75Row    = ALL_SEASONS.map(s => statMap[s]?.p75    ?? null);
    const medianRow = ALL_SEASONS.map(s => statMap[s]?.median ?? null);
    const p25Row    = ALL_SEASONS.map(s => statMap[s]?.p25    ?? null);

    // P75 — dashed, fills down to median (next dataset in array)
    datasets.push({
      label:           `${pos} P75`,
      data:            p75Row,
      borderColor:     hexToRgba(color, 0.4),
      backgroundColor: hexToRgba(color, 0.1),
      borderDash:      [5, 3],
      borderWidth:     1.5,
      pointRadius:     0,
      pointHoverRadius: 0,
      fill:            '+1',   // fill area between P75 and the next dataset (median)
      tension:         0.3,
      spanGaps:        true,
      hideLegend:      true
    });

    // Median — solid, shown in legend
    datasets.push({
      label:           pos,
      data:            medianRow,
      borderColor:     color,
      backgroundColor: 'transparent',
      borderWidth:     2.5,
      pointRadius:     4,
      pointHoverRadius: 6,
      pointBackgroundColor: color,
      fill:            false,
      tension:         0.3,
      spanGaps:        true
    });

    // P25 — dashed, no fill
    datasets.push({
      label:           `${pos} P25`,
      data:            p25Row,
      borderColor:     hexToRgba(color, 0.4),
      backgroundColor: 'transparent',
      borderDash:      [5, 3],
      borderWidth:     1.5,
      pointRadius:     0,
      pointHoverRadius: 0,
      fill:            false,
      tension:         0.3,
      spanGaps:        true,
      hideLegend:      true
    });
  });

  const isDollar = metric === 'dollar_value';

  chartInstances['year-over-year'] = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: {
          position: 'top',
          align: 'end',
          labels: {
            color: THEME.text,
            font: { family: 'DM Sans', size: 12 },
            usePointStyle: true,
            pointStyleWidth: 14,
            filter: (item, data) => !data.datasets[item.datasetIndex].hideLegend
          }
        },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: THEME.surface2,
          borderColor: THEME.border,
          borderWidth: 1,
          titleColor: THEME.text,
          bodyColor: THEME.muted,
          titleFont: { family: 'DM Sans', size: 12, weight: '600' },
          bodyFont: { family: 'JetBrains Mono', size: 12 },
          padding: 10,
          // Hide P25/P75 from tooltip
          filter: (item, data) => !data.datasets[item.datasetIndex].hideLegend,
          callbacks: {
            title: items => items.length ? `${items[0].label} season` : '',
            label: ctx => {
              const v = ctx.parsed.y;
              if (v == null) return null;
              const val = isDollar ? `$${v.toFixed(1)}` : v.toFixed(1);
              return `  ${ctx.dataset.label}  ${val}`;
            }
          }
        }
      },
      scales: {
        x: {
          title: {
            display: true,
            text: 'Season',
            color: THEME.muted,
            font: { family: 'DM Sans', size: 12 }
          },
          ticks: {
            color: THEME.muted,
            font: { family: 'DM Sans', size: 11 }
          },
          grid: { color: THEME.border }
        },
        y: {
          title: {
            display: true,
            text: YOY_METRIC_LABELS[metric],
            color: THEME.muted,
            font: { family: 'DM Sans', size: 12 }
          },
          ticks: {
            color: THEME.muted,
            font: { family: 'JetBrains Mono', size: 11 },
            callback: v => isDollar ? `$${v}` : v
          },
          grid: { color: THEME.border }
        }
      }
    }
  });
}
