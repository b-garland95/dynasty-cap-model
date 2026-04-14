// View 4: WMSV vs ESV Scatter
// Each point = one player-week. X = WMSV (perfect capture), Y = ESV Week (rational capture).
// Diagonal reference line shows perfect capture. Outliers (high gap) highlighted in red.

let wrInitialized = false;

function initWmsvEsv() {
  if (wrInitialized) {
    renderWmsvEsvChart();
    return;
  }
  wrInitialized = true;

  // ── Season dropdown ──────────────────────────────────────────────────────��
  const seasonSel = document.getElementById('wr-season');
  const allOpt = document.createElement('option');
  allOpt.value = 'all';
  allOpt.textContent = 'All Seasons';
  seasonSel.appendChild(allOpt);

  [...ALL_SEASONS].reverse().forEach(s => {
    const opt = document.createElement('option');
    opt.value = String(s); opt.textContent = String(s);
    seasonSel.appendChild(opt);
  });

  // ── Position dropdown ─────────────────────────────────────────────────────
  const posSel = document.getElementById('wr-position');
  [{ v: 'all', t: 'All Positions' }, ...POSITIONS.map(p => ({ v: p, t: p }))]
    .forEach(({ v, t }) => {
      const opt = document.createElement('option');
      opt.value = v; opt.textContent = t;
      posSel.appendChild(opt);
    });

  // ── Min WMSV dropdown — default 5 ────────────────────────────────────────
  const wmsvSel = document.getElementById('wr-minwmsv');
  [
    { v: 0,  t: 'None' },
    { v: 5,  t: '≥ 5' },
    { v: 10, t: '≥ 10' },
    { v: 15, t: '≥ 15' }
  ].forEach(({ v, t }) => {
    const opt = document.createElement('option');
    opt.value = String(v); opt.textContent = t;
    if (v === 5) opt.selected = true;
    wmsvSel.appendChild(opt);
  });

  // ── Change handlers ───────────────────────────────────────────────────────
  seasonSel.addEventListener('change', renderWmsvEsvChart);
  posSel.addEventListener('change', renderWmsvEsvChart);
  wmsvSel.addEventListener('change', renderWmsvEsvChart);

  renderWmsvEsvChart();
}

// ── Sampling ────────────────────────────────���──────────────────────────��──────
// If > 3,000 points: keep top 200 by gap (guarantees outliers survive),
// then evenly downsample the remainder to ~2,800.

function _wrSample(pts) {
  if (pts.length <= 3000) return pts;

  const byGap  = [...pts].sort((a, b) => b.gap - a.gap);
  const top200 = byGap.slice(0, 200);
  const rest   = byGap.slice(200);

  const target = 2800;
  const step   = Math.max(1, Math.floor(rest.length / target));
  const sampled = [];
  for (let i = 0; i < rest.length && sampled.length < target; i += step) {
    sampled.push(rest[i]);
  }

  return [...top200, ...sampled];
}

// ── Chart render ──────────────────────────────────────────────────────────────

function renderWmsvEsvChart() {
  const season  = document.getElementById('wr-season').value;
  const pos     = document.getElementById('wr-position').value;
  const minWmsv = +document.getElementById('wr-minwmsv').value;

  // ── Filter ───────────────────────────���────────────────────────────────────
  const filteredWeekly = WEEKLY_DATA.filter(d => {
    if (d.wmsv < minWmsv)                           return false;
    if (season !== 'all' && d.season !== +season)   return false;
    if (pos    !== 'all' && d.position !== pos)     return false;
    return true;
  });

  destroyChart('wmsv-esv');

  const canvas = document.getElementById('chart-wmsv-esv');
  const ctx    = canvas.getContext('2d');

  if (filteredWeekly.length === 0) return;

  // ── Map to scatter points with gap precomputed ────────────────────────────
  let pts = filteredWeekly.map(d => ({
    x:          d.wmsv,
    y:          d.esv_week,
    gap:        d.wmsv - d.esv_week,
    player:     d.player,
    season:     d.season,
    week:       d.week,
    points:     d.points,
    start_prob: d.start_prob
  }));

  // ── Sample if needed ──────────────────────────────────────────────────────
  pts = _wrSample(pts);

  // ── Identify top-12 outliers (highest gap after sampling) ─────────────────
  const sortedByGap = [...pts].sort((a, b) => b.gap - a.gap);
  const outliers    = sortedByGap.slice(0, 12);
  const outlierSet  = new Set(outliers);
  const normals     = pts.filter(p => !outlierSet.has(p));

  // ── Shared axis max ───────────────────────────────────────────────────────
  const allX   = pts.map(p => p.x);
  const allY   = pts.map(p => p.y);
  const axisMax = Math.ceil(Math.max(...allX, ...allY, 45));

  // ── Colors ───────────────────────────────────��────────────────────────────
  const normalColor  = pos !== 'all'
    ? hexToRgba(POS_COLORS[pos], 0.27)
    : hexToRgba(THEME.accent,    0.27);

  // ── Datasets ──────────────────────────────────────────────────────────────
  const datasets = [
    // Normal player-weeks
    {
      label:            'Player-Weeks',
      data:             normals,
      backgroundColor:  normalColor,
      borderColor:      'transparent',
      pointRadius:      2.5,
      pointHoverRadius: 5
    },
    // Outliers — red at 80%, hidden from legend
    {
      label:            'Outliers',
      data:             outliers,
      backgroundColor:  hexToRgba('#e06c75', 0.8),
      borderColor:      'transparent',
      pointRadius:      5,
      pointHoverRadius: 7,
      hideLegend:       true
    },
    // Diagonal perfect-capture reference line
    {
      label:            'Perfect Capture',
      data:             [{ x: 0, y: 0 }, { x: axisMax, y: axisMax }],
      showLine:         true,
      borderColor:      hexToRgba('#ffffff', 0.27),
      backgroundColor:  'transparent',
      borderDash:       [6, 4],
      borderWidth:      1.5,
      pointRadius:      0,
      fill:             false
    }
  ];

  chartInstances['wmsv-esv'] = new Chart(ctx, {
    type: 'scatter',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      animation: { duration: 200 },
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
          backgroundColor: THEME.surface2,
          borderColor: THEME.border,
          borderWidth: 1,
          titleColor: THEME.text,
          bodyColor: THEME.muted,
          titleFont: { family: 'DM Sans', size: 12, weight: '600' },
          bodyFont: { family: 'JetBrains Mono', size: 11 },
          padding: 10,
          callbacks: {
            title: () => '',
            label: ctx => {
              const p = ctx.raw;
              // Diagonal reference line has no player property
              if (!p.player) return ` Perfect Capture`;
              return [
                `${p.player} ${p.season} W${p.week}`,
                `Pts:${p.points.toFixed(1)} | WMSV:${p.x.toFixed(2)} ESV:${p.y.toFixed(2)} | Start:${(p.start_prob * 100).toFixed(1)}%`
              ];
            }
          }
        }
      },
      scales: {
        x: {
          type: 'linear',
          min: 0,
          max: axisMax,
          title: {
            display: true,
            text: 'WMSV (Perfect Capture)',
            color: THEME.muted,
            font: { family: 'DM Sans', size: 12 }
          },
          ticks: { color: THEME.muted, font: { family: 'JetBrains Mono', size: 11 } },
          grid:  { color: THEME.border }
        },
        y: {
          type: 'linear',
          min: 0,
          max: axisMax,
          title: {
            display: true,
            text: 'ESV Week (Rational Capture)',
            color: THEME.muted,
            font: { family: 'DM Sans', size: 12 }
          },
          ticks: { color: THEME.muted, font: { family: 'JetBrains Mono', size: 11 } },
          grid:  { color: THEME.border }
        }
      }
    }
  });
}
