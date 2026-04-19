// View 2: Player Timeline
// Searchable player selection (up to 5 player-seasons), two chart sub-modes.

let ptInitialized = false;
let selectedPlayers = [];   // [{ id, player, season, color }]
let ptMode = 'points-start'; // 'points-start' | 'season-dollar'
let ptXMode = 'by-season';  // 'by-season' | 'years-in-league'
let ptNextId = 0;

const PT_COLORS = ['#6c8cff', '#e06c75', '#98c379', '#d19a66', '#c678dd'];

// ── Init ──────────────────────────────────────────────────────────────────────

function initPlayerTimeline() {
  if (ptInitialized) return;
  ptInitialized = true;

  _ptWireSearch();
  _ptWireModeToggle();
  _ptWireXAxisToggle();

  // Render empty initial state
  _ptUpdateView();
}

// ── Search & dropdown ─────────────────────────────────────────────────────────

function _ptWireSearch() {
  const input    = document.getElementById('pt-search');
  const dropdown = document.getElementById('pt-dropdown');

  input.addEventListener('input', () => {
    const q = input.value.trim();
    if (q.length < 2) { dropdown.hidden = true; return; }
    _ptRenderDropdown(_ptBuildItems(q));
  });

  // blur hides the dropdown; mousedown on items uses preventDefault()
  // so blur fires only after the mousedown handler completes.
  input.addEventListener('blur', () => { dropdown.hidden = true; });
}

function _ptBuildItems(query) {
  const lq = query.toLowerCase();
  const matchedPlayers = ALL_PLAYERS
    .filter(p => p.toLowerCase().includes(lq))
    .slice(0, 12);     // top 12 unique player names

  const items = [];
  matchedPlayers.forEach(player => {
    const seasons = [...new Set(
      SEASON_DATA.filter(r => r.player === player).map(r => r.season)
    )].sort((a, b) => b - a);  // most recent first

    // Bold "all seasons" shortcut when 2+ seasons exist
    if (seasons.length >= 2) {
      items.push({ player, season: null, type: 'all-seasons' });
    }
    // Individual season entries
    seasons.forEach(season => {
      items.push({ player, season, type: 'season' });
    });
  });

  return items;
}

function _ptRenderDropdown(items) {
  const dropdown = document.getElementById('pt-dropdown');
  dropdown.innerHTML = '';

  if (items.length === 0) { dropdown.hidden = true; return; }

  items.forEach(item => {
    const el = document.createElement('div');
    el.className = 'pt-dropdown-item';

    if (item.type === 'all-seasons') {
      el.classList.add('pt-dropdown-all');
      el.textContent = `${item.player} (all seasons)`;
    } else {
      el.textContent = `${item.player} (${item.season})`;
    }

    // mousedown + preventDefault keeps input focused → blur doesn't fire
    // before this handler runs, so we can hide the dropdown ourselves.
    el.addEventListener('mousedown', e => {
      e.preventDefault();
      if (item.type === 'all-seasons') {
        _ptAddAllSeasons(item.player);
      } else {
        _ptAddSelection(item.player, item.season);
      }
      document.getElementById('pt-search').value = '';
      document.getElementById('pt-dropdown').hidden = true;
    });

    dropdown.appendChild(el);
  });

  dropdown.hidden = false;
}

// ── Selection management ──────────────────────────────────────────────────────

function _ptNextColor() {
  const used = new Set(selectedPlayers.map(s => s.color));
  for (const c of PT_COLORS) { if (!used.has(c)) return c; }
  return PT_COLORS[selectedPlayers.length % PT_COLORS.length];
}

function _ptAddSelection(player, season) {
  if (selectedPlayers.length >= 5) return;
  if (selectedPlayers.find(s => s.player === player && s.season === season)) return;
  selectedPlayers.push({ id: ptNextId++, player, season, color: _ptNextColor() });
  _ptUpdateView();
}

function _ptAddAllSeasons(player) {
  const seasons = [...new Set(
    SEASON_DATA.filter(r => r.player === player).map(r => r.season)
  )].sort((a, b) => a - b);

  for (const season of seasons) {
    if (selectedPlayers.length >= 5) break;
    if (!selectedPlayers.find(s => s.player === player && s.season === season)) {
      selectedPlayers.push({ id: ptNextId++, player, season, color: _ptNextColor() });
    }
  }
  _ptUpdateView();
}

function _ptRemoveSelection(id) {
  selectedPlayers = selectedPlayers.filter(s => s.id !== id);
  _ptUpdateView();
}

function _ptUpdateView() {
  _ptRenderChips();
  _ptRenderMetricCards();
  renderTimelineChart();
}

// ── Chips ─────────────────────────────────────────────────────────────────────

function _ptRenderChips() {
  const container = document.getElementById('pt-chips');
  container.innerHTML = '';

  selectedPlayers.forEach(sel => {
    const chip = document.createElement('div');
    chip.className = 'pt-chip';

    const dot = document.createElement('span');
    dot.className = 'pt-chip-dot';
    dot.style.background = sel.color;

    const lbl = document.createElement('span');
    lbl.className = 'pt-chip-label';
    lbl.textContent = `${sel.player} ${sel.season}`;

    // addEventListener, never inline onclick — player names may contain apostrophes
    const rm = document.createElement('button');
    rm.className = 'pt-chip-remove';
    rm.setAttribute('aria-label', `Remove ${sel.player} ${sel.season}`);
    rm.textContent = '×';
    rm.addEventListener('click', () => _ptRemoveSelection(sel.id));

    chip.appendChild(dot);
    chip.appendChild(lbl);
    chip.appendChild(rm);
    container.appendChild(chip);
  });
}

// ── Metric cards ──────────────────────────────────────────────────────────────

function _ptRenderMetricCards() {
  const container = document.getElementById('pt-metric-cards');
  container.innerHTML = '';

  selectedPlayers.forEach(sel => {
    const row = SEASON_DATA.find(r => r.player === sel.player && r.season === sel.season);
    if (!row) return;

    const card = document.createElement('div');
    card.className = 'pt-metric-card';
    card.style.borderTopColor = sel.color;

    const header = document.createElement('div');
    header.className = 'pt-metric-header';
    // Player name is a clickable link that opens the modal
    header.innerHTML = `${playerLink(sel.player)} <span style="font-weight:400;">${sel.season}</span>`;

    const dv = document.createElement('div');
    dv.className = 'pt-metric-dv';
    dv.style.color = sel.color;
    dv.textContent = `$${row.dollar_value.toFixed(1)}`;

    const detail = document.createElement('div');
    detail.className = 'pt-metric-detail';
    detail.textContent =
      `ESV: ${row.esv.toFixed(1)} | Pts: ${row.total_points.toFixed(1)} | ${row.position}${row.pos_rank}`;

    card.appendChild(header);
    card.appendChild(dv);
    card.appendChild(detail);
    container.appendChild(card);
  });
}

// ── Mode toggle ───────────────────────────────────────────────────────────────

function _ptWireModeToggle() {
  document.querySelectorAll('.pt-mode-btn[data-mode]').forEach(btn => {
    btn.addEventListener('click', () => {
      ptMode = btn.dataset.mode;
      document.querySelectorAll('.pt-mode-btn[data-mode]').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === ptMode);
      });
      document.getElementById('pt-xaxis-toggle').hidden = (ptMode !== 'season-dollar');
      renderTimelineChart();
    });
  });
}

function _ptWireXAxisToggle() {
  document.querySelectorAll('[data-xmode]').forEach(btn => {
    btn.addEventListener('click', () => {
      ptXMode = btn.dataset.xmode;
      document.querySelectorAll('[data-xmode]').forEach(b =>
        b.classList.toggle('active', b.dataset.xmode === ptXMode));
      renderTimelineChart();
    });
  });
}

// ── Chart routing ─────────────────────────────────────────────────────────────

function renderTimelineChart() {
  destroyChart('player-timeline');

  if (ptMode === 'points-start') _ptModeA();
  else _ptModeC();
}

// ── Weekly data helper ────────────────────────────────────────────────────────

// Build an 18-element array (weeks 1–18) for a single numeric field.
// Weeks with no data entry return null (bye weeks, season end).
function _ptWeeks(player, season, field) {
  const map = {};
  WEEKLY_DATA
    .filter(r => r.player === player && r.season === season)
    .forEach(r => { map[r.week] = r; });
  return Array.from({ length: 18 }, (_, i) => {
    const row = map[i + 1];
    return row != null ? row[field] : null;
  });
}

// ── Shared chart option helpers ───────────────────────────────────────────────

function _ptXAxis() {
  return {
    title: {
      display: true, text: 'Week',
      color: THEME.muted, font: { family: 'DM Sans', size: 12 }
    },
    ticks: { color: THEME.muted, font: { family: 'DM Sans', size: 11 } },
    grid:  { color: THEME.border }
  };
}

function _ptYAxis(label, position, extraOpts) {
  return {
    position: position || 'left',
    title: {
      display: true, text: label,
      color: THEME.muted, font: { family: 'DM Sans', size: 12 }
    },
    ticks: { color: THEME.muted, font: { family: 'JetBrains Mono', size: 11 } },
    grid:  { color: THEME.border },
    ...extraOpts
  };
}

function _ptOptions(scales, extraPlugin) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 200 },
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
        intersect: false
      },
      ...extraPlugin
    },
    scales
  };
}

// ── Mode A: Points + Start% ───────────────────────────────────────────────────

function _ptModeA() {
  const ctx    = document.getElementById('chart-player-timeline').getContext('2d');
  const labels = Array.from({ length: 18 }, (_, i) => String(i + 1));
  const multi  = selectedPlayers.length > 1;
  const barPct = multi ? 0.35 : 0.55;
  const datasets = [];

  selectedPlayers.forEach(sel => {
    const c       = sel.color;
    const tag     = `${sel.player} ${sel.season}`;
    const points  = _ptWeeks(sel.player, sel.season, 'points');
    const margin  = _ptWeeks(sel.player, sel.season, 'margin');
    const repl    = points.map((p, i) =>
      p != null && margin[i] != null ? p - margin[i] : null);
    const startPct = _ptWeeks(sel.player, sel.season, 'start_prob')
      .map(v => v != null ? v * 100 : null);

    // Order 3 — replacement level line (drawn behind bars)
    datasets.push({
      label:            `Repl: ${tag}`,
      type:             'line',
      data:             repl,
      order:            3,
      yAxisID:          'y',
      borderColor:      hexToRgba('#98c379', 0.4),
      backgroundColor:  hexToRgba('#98c379', 0.1),
      borderWidth:      1.5,
      pointRadius:      0,
      fill:             'origin',
      tension:          0.3,
      spanGaps:         true
    });

    // Order 2 — points bar (middle layer)
    datasets.push({
      label:              tag,
      type:               'bar',
      data:               points,
      order:              2,
      yAxisID:            'y',
      backgroundColor:    hexToRgba(c, 0.53),
      borderColor:        c,
      borderWidth:        1,
      barPercentage:      barPct,
      categoryPercentage: 0.85
    });

    // Order 1 — start% dashed line (drawn on top)
    datasets.push({
      label:              `Start%: ${tag}`,
      type:               'line',
      data:               startPct,
      order:              1,
      yAxisID:            'y-right',
      borderColor:        c,
      backgroundColor:    'transparent',
      borderWidth:        1.5,
      borderDash:         [4, 3],
      pointRadius:        2,
      pointHoverRadius:   4,
      fill:               false,
      tension:            0,
      spanGaps:           false
    });
  });

  const scales = {
    x:       _ptXAxis(),
    y:       _ptYAxis('Points', 'left'),
    'y-right': {
      ..._ptYAxis('Start Prob %', 'right', {
        min: 0, max: 100,
        ticks: {
          color: THEME.muted,
          font: { family: 'JetBrains Mono', size: 11 },
          callback: v => `${v}%`
        },
        grid: { drawOnChartArea: false }
      })
    }
  };

  const options = _ptOptions(scales, {});

  // Hide Repl lines from legend and tooltip
  options.plugins.legend.labels.filter =
    (item) => !item.text.startsWith('Repl');
  options.plugins.tooltip.filter =
    (item, data) => !data.datasets[item.datasetIndex].label.startsWith('Repl');

  options.plugins.tooltip.callbacks = {
    title: items => items[0] ? `Week ${items[0].label}` : '',
    label: ctx => {
      const lbl = ctx.dataset.label;
      // Start% line — suppress (start% shown inline in points label below)
      if (lbl.startsWith('Start%:')) return null;
      // Points bar — lbl is "Player Season" (season is the trailing 4-digit year)
      const lastSpace = lbl.lastIndexOf(' ');
      const player = lbl.slice(0, lastSpace);
      const season = +lbl.slice(lastSpace + 1);
      const week   = +ctx.label;
      const row    = (typeof WEEKLY_DATA !== 'undefined' ? WEEKLY_DATA : [])
        .find(r => r.player === player && r.season === season && r.week === week);
      if (!row) return ` ${lbl}: ${ctx.formattedValue} pts`;
      return ` ${lbl}: ${row.points.toFixed(1)} pts  (ESV ${row.esv_week.toFixed(1)}, Start ${(row.start_prob * 100).toFixed(0)}%)`;
    }
  };

  chartInstances['player-timeline'] = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options
  });
}

// ── Mode B: Season $ ──────────────────────────────────────────────────────────

function _ptModeC() {
  const ctx         = document.getElementById('chart-player-timeline').getContext('2d');
  const playerNames = [...new Set(selectedPlayers.map(s => s.player))];
  const multi       = playerNames.length > 1;

  let labels, datasets, tooltipSeasonFor;

  if (ptXMode === 'years-in-league') {
    // First season = rookie_season from player bio; fall back to first row in data
    const firstSeasonMap = {};
    playerNames.forEach(p => {
      const bio = HEADSHOT_MAP[p];
      firstSeasonMap[p] = bio && bio.rookie_season
        ? +bio.rookie_season
        : Math.min(...SEASON_DATA.filter(r => r.player === p).map(r => r.season));
    });

    // How many years does the longest career span?
    const maxYears = Math.max(...playerNames.map(p => {
      const seasons = SEASON_DATA.filter(r => r.player === p).map(r => r.season);
      return Math.max(...seasons) - firstSeasonMap[p] + 1;
    }));

    labels = Array.from({ length: maxYears }, (_, i) => `Yr ${i + 1}`);

    // Helper: given player + dataIndex, recover the actual season
    tooltipSeasonFor = (pName, dataIndex) => firstSeasonMap[pName] + dataIndex;

    datasets = playerNames.map(playerName => {
      const color       = selectedPlayers.find(s => s.player === playerName).color;
      const firstSeason = firstSeasonMap[playerName];
      const data        = Array(maxYears).fill(null);

      SEASON_DATA
        .filter(r => r.player === playerName)
        .forEach(r => {
          const idx = r.season - firstSeason;
          if (idx >= 0 && idx < maxYears) data[idx] = r.dollar_value;
        });

      return multi
        ? { label: playerName, data, borderColor: color, backgroundColor: 'transparent',
            borderWidth: 2, pointRadius: 4, pointHoverRadius: 6, fill: false,
            tension: 0.2, spanGaps: false }
        : { label: playerName, data, backgroundColor: hexToRgba(color, 0.6),
            borderColor: color, borderWidth: 1, borderRadius: 3, spanGaps: false };
    });

  } else {
    // By Season — original behaviour
    labels = ALL_SEASONS.map(String);
    tooltipSeasonFor = (_pName, dataIndex) => ALL_SEASONS[dataIndex];

    datasets = playerNames.map(playerName => {
      const color = selectedPlayers.find(s => s.player === playerName).color;
      const data  = ALL_SEASONS.map(season => {
        const row = SEASON_DATA.find(r => r.player === playerName && r.season === season);
        return row != null ? row.dollar_value : null;
      });

      return multi
        ? { label: playerName, data, borderColor: color, backgroundColor: 'transparent',
            borderWidth: 2, pointRadius: 4, pointHoverRadius: 6, fill: false,
            tension: 0.2, spanGaps: false }
        : { label: playerName, data, backgroundColor: hexToRgba(color, 0.6),
            borderColor: color, borderWidth: 1, borderRadius: 3, spanGaps: false };
    });
  }

  const xTitle = ptXMode === 'years-in-league' ? 'Years in League' : 'Season';

  const scales = {
    x: {
      title: {
        display: true, text: xTitle,
        color: THEME.muted, font: { family: 'DM Sans', size: 12 }
      },
      ticks: { color: THEME.muted, font: { family: 'DM Sans', size: 11 } },
      grid:  { color: THEME.border }
    },
    y: {
      min: 0,
      title: {
        display: true, text: 'Dollar Value ($)',
        color: THEME.muted, font: { family: 'DM Sans', size: 12 }
      },
      ticks: {
        color: THEME.muted,
        font: { family: 'JetBrains Mono', size: 11 },
        callback: v => `$${v}`
      },
      grid: { color: THEME.border }
    }
  };

  const options = _ptOptions(scales, {});

  options.plugins.tooltip.callbacks = {
    label: ctx => {
      const pName  = ctx.dataset.label;
      const season = tooltipSeasonFor(pName, ctx.dataIndex);
      const row    = SEASON_DATA.find(r => r.player === pName && r.season === season);
      if (!row) return null;
      const seasonTag = ptXMode === 'years-in-league' ? ` (${season})` : '';
      return `${pName}${seasonTag}: $${row.dollar_value.toFixed(1)} ` +
             `(ESV ${row.esv.toFixed(1)}, ${row.position} #${row.pos_rank})`;
    }
  };

  chartInstances['player-timeline'] = new Chart(ctx, {
    type: multi ? 'line' : 'bar',
    data: { labels, datasets },
    options
  });
}
