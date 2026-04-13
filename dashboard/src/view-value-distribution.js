// View 3: Value Distribution
// Stacked-bar histogram of dollar value, binned at $10 increments.
// Shows where value concentrates (and where the big seasons come from).

let vdInitialized = false;
let vdTop10Plus   = [];   // top 10 players in $60+ bucket; set at render time

function initValueDistribution() {
  if (vdInitialized) {
    renderValueDistributionChart();
    return;
  }
  vdInitialized = true;

  // ── Season dropdown ───────────────────────────────────────────────────────
  const seasonSel = document.getElementById('vd-season');
  const allOpt = document.createElement('option');
  allOpt.value = 'all';
  allOpt.textContent = 'All Seasons';
  seasonSel.appendChild(allOpt);

  [...ALL_SEASONS].reverse().forEach(s => {
    const opt = document.createElement('option');
    opt.value = String(s);
    opt.textContent = String(s);
    seasonSel.appendChild(opt);
  });
  // Default: All Seasons (first option, already selected)

  // ── Position dropdown ─────────────────────────────────────────────────────
  const posSel = document.getElementById('vd-position');
  [{ v: 'all', t: 'All Positions' }, ...POSITIONS.map(p => ({ v: p, t: p }))]
    .forEach(({ v, t }) => {
      const opt = document.createElement('option');
      opt.value = v; opt.textContent = t;
      posSel.appendChild(opt);
    });

  // ── Min SAV dropdown — default 5 ─────────────────────────────────────────
  const savSel = document.getElementById('vd-minsav');
  [
    { v: 0,  t: 'None (all)' },
    { v: 5,  t: '≥ 5' },
    { v: 15, t: '≥ 15' },
    { v: 30, t: '≥ 30' }
  ].forEach(({ v, t }) => {
    const opt = document.createElement('option');
    opt.value = String(v); opt.textContent = t;
    if (v === 5) opt.selected = true;
    savSel.appendChild(opt);
  });

  // ── Change handlers ───────────────────────────────────────────────────────
  seasonSel.addEventListener('change', renderValueDistributionChart);
  posSel.addEventListener('change', renderValueDistributionChart);
  savSel.addEventListener('change', renderValueDistributionChart);

  renderValueDistributionChart();
}

function renderValueDistributionChart() {
  const season = document.getElementById('vd-season').value;
  const pos    = document.getElementById('vd-position').value;
  const minSav = +document.getElementById('vd-minsav').value;

  // ── Filter ────────────────────────────────────────────────────────────────
  const filtered = SEASON_DATA.filter(d => {
    if (minSav > 0 && d.sav < minSav)                          return false;
    if (season !== 'all' && d.season !== +season)              return false;
    if (pos    !== 'all' && d.position !== pos)                return false;
    return true;
  });

  destroyChart('value-distribution');

  const canvas = document.getElementById('chart-value-distribution');
  const ctx    = canvas.getContext('2d');

  if (filtered.length === 0) return;

  // ── Build bins ────────────────────────────────────────────────────────────
  const vals    = filtered.map(r => r.dollar_value);
  const minVal  = Math.min(...vals);
  const binFloor = Math.floor(minVal / 10) * 10;    // e.g. -19 → -20

  // Regular bins: [binFloor, binFloor+10), …, [50,60)
  const binEdges = [];
  for (let lo = binFloor; lo < 60; lo += 10) binEdges.push(lo);

  // Labels: "$-20 to $-10", …, "$50 to $60", "$60+"
  const labels = [
    ...binEdges.map(lo => `$${lo} to $${lo + 10}`),
    '$60+'
  ];

  // Helper: assign a dollar_value to its bin index
  function binOf(v) {
    if (v >= 60) return labels.length - 1;
    const idx = Math.floor((v - binFloor) / 10);
    return Math.max(0, Math.min(idx, labels.length - 2));
  }

  // ── Store top-10 for $60+ afterBody tooltip ───────────────────────────────
  vdTop10Plus = filtered
    .filter(r => r.dollar_value >= 60)
    .sort((a, b) => b.dollar_value - a.dollar_value)
    .slice(0, 10);

  // ── Datasets (one per position) ───────────────────────────────────────────
  const posToShow = pos === 'all' ? POSITIONS : [pos];

  const datasets = posToShow.map(p => {
    const counts = new Array(labels.length).fill(0);
    filtered
      .filter(r => r.position === p)
      .forEach(r => { counts[binOf(r.dollar_value)]++; });

    return {
      label:           p,
      data:            counts,
      backgroundColor: POS_COLORS[p],
      borderColor:     hexToRgba(POS_COLORS[p], 0.75),
      borderWidth:     1
    };
  });

  // ── Chart ─────────────────────────────────────────────────────────────────
  chartInstances['value-distribution'] = new Chart(ctx, {
    type: 'bar',
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
          mode: 'index',
          intersect: false,
          callbacks: {
            // List top 10 players only when hovering the $60+ bin
            afterBody: items => {
              if (!items.length || items[0].label !== '$60+') return [];
              if (vdTop10Plus.length === 0) return [];
              return [
                '',
                'Top $60+ seasons:',
                ...vdTop10Plus.map(
                  r => `  ${r.position} ${r.player}: $${r.dollar_value.toFixed(2)}`
                )
              ];
            }
          }
        }
      },
      scales: {
        x: {
          stacked: true,
          ticks: {
            color: THEME.muted,
            font: { family: 'DM Sans', size: 10 },
            maxRotation: 35
          },
          grid: { color: THEME.border }
        },
        y: {
          stacked: true,
          title: {
            display: true,
            text: 'Player Count',
            color: THEME.muted,
            font: { family: 'DM Sans', size: 12 }
          },
          ticks: { color: THEME.muted, font: { family: 'DM Sans', size: 11 } },
          grid:  { color: THEME.border }
        }
      }
    }
  });
}
