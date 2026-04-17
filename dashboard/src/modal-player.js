// Player modal — opens when any .player-link is clicked.
// Shows headshot, bio, contract context, career timeline (historical + forecast),
// year-clickable weekly breakdown, and a Comparables tab.

(function () {
  // ── Chart instance refs ───────────────────────────────────────────────────
  let careerChart = null;
  let weeklyChart = null;

  // ── Per-open state ────────────────────────────────────────────────────────
  let _currentPlayer      = null;
  let _activeModalTab     = 'profile';
  let _compMetric         = 'tv_y0';   // 'tv_y0' | 'tv_sum' | 'surplus'
  let _compSamePos        = false;
  let _weeklyActiveSeason = null;

  // ── Helpers ───────────────────────────────────────────────────────────────

  /** Format height from inches to feet/inches string, e.g. 74 → 6'2" */
  function fmtHeight(inches) {
    if (!inches) return null;
    const ft = Math.floor(inches / 12);
    const inn = inches % 12;
    return `${ft}'${inn}"`;
  }

  /** Compute age from a birth_date string (YYYY-MM-DD or MM/DD/YYYY). */
  function calcAge(birthDate) {
    if (!birthDate) return null;
    const bd = new Date(birthDate);
    if (isNaN(bd)) return null;
    const now = new Date();
    let age = now.getFullYear() - bd.getFullYear();
    const m = now.getMonth() - bd.getMonth();
    if (m < 0 || (m === 0 && now.getDate() < bd.getDate())) age--;
    return age;
  }

  /** Format a dollar value with sign and 1 decimal. */
  function fmtDollar(v) {
    const sign = v >= 0 ? '+' : '';
    return `${sign}$${v.toFixed(1)}`;
  }

  /** Format a number to 1 decimal or '–' if null/undefined. */
  function fmt1(v) {
    return (v !== null && v !== undefined && !isNaN(v)) ? (+v).toFixed(1) : '–';
  }

  function _comparableMetricValue(tvRow, surplusAll) {
    if (!tvRow) return null;
    if (_compMetric === 'tv_y0') return tvRow.tv_y0;
    if (_compMetric === 'tv_sum') {
      return (tvRow.tv_y0 || 0) + (tvRow.tv_y1 || 0) + (tvRow.tv_y2 || 0) + (tvRow.tv_y3 || 0);
    }
    if (_compMetric === 'surplus') {
      const s = surplusAll.find(r => r.player === tvRow.player);
      return s ? (s.surplus_1yr ?? s.surplus_value) : null;
    }
    return null;
  }

  function _buildComparableWindow(playerName, tvAll, surplusAll, ledgerAll) {
    const focalTV  = tvAll.find(r => r.player === playerName);
    const focalPos = focalTV?.position || HEADSHOT_MAP[playerName]?.position || null;

    const rankedRows = tvAll
      .filter(r => !_compSamePos || !focalPos || r.position === focalPos)
      .map(r => {
        const sur = surplusAll.find(s => s.player === r.player);
        const led = ledgerAll.find(l => l.player === r.player);
        return {
          r,
          val: _comparableMetricValue(r, surplusAll),
          sur,
          led,
        };
      })
      .sort((a, b) => {
        const av = a.val;
        const bv = b.val;
        if (av === null || av === undefined) return 1;
        if (bv === null || bv === undefined) return -1;
        if (bv !== av) return bv - av;
        return a.r.player.localeCompare(b.r.player);
      });

    const focalIndex = rankedRows.findIndex(({ r }) => r.player === playerName);
    if (focalIndex === -1) return [];

    const start = Math.max(0, focalIndex - 5);
    const end = Math.min(rankedRows.length, focalIndex + 6);

    return rankedRows.slice(start, end).map((row, idx) => ({
      ...row,
      rank: start + idx + 1,
      isFocal: row.r.player === playerName,
    }));
  }

  // ── Tab switching ─────────────────────────────────────────────────────────

  function _switchModalTab(tabId, skipRender) {
    _activeModalTab = tabId;
    document.querySelectorAll('.modal-tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.modaltab === tabId);
    });
    const profilePanel     = document.getElementById('modal-tab-profile');
    const comparablesPanel = document.getElementById('modal-tab-comparables');
    if (profilePanel)     profilePanel.hidden     = (tabId !== 'profile');
    if (comparablesPanel) comparablesPanel.hidden = (tabId !== 'comparables');
    if (!skipRender && tabId === 'comparables' && _currentPlayer) {
      renderComparables(_currentPlayer);
    }
  }

  // ── Modal open/close ──────────────────────────────────────────────────────

  function closeModal() {
    const overlay = document.getElementById('player-modal');
    if (overlay) overlay.hidden = true;
    if (careerChart) { careerChart.destroy(); careerChart = null; }
    if (weeklyChart) { weeklyChart.destroy(); weeklyChart = null; }
    _currentPlayer      = null;
    _weeklyActiveSeason = null;
    _switchModalTab('profile', /* skipRender= */ true);
  }

  // ── Contract / roster context strip ──────────────────────────────────────

  function buildContractStrip(playerName) {
    const strip = document.getElementById('modal-contract-strip');
    if (!strip) return;

    const tv      = (typeof TV_DATA      !== 'undefined' ? TV_DATA      : []).find(r => r.player === playerName);
    const surplus = (typeof SURPLUS_DATA !== 'undefined' ? SURPLUS_DATA : []).find(r => r.player === playerName);
    const ledger  = (typeof LEDGER_DATA  !== 'undefined' ? LEDGER_DATA  : []).find(r => r.player === playerName);

    const pills = [];

    // Team
    const team = tv?.team || surplus?.team || ledger?.team || null;
    if (team) pills.push({ label: 'Team', value: team });

    // Roster status (from TV_DATA)
    if (tv) {
      pills.push({
        label: 'Rostered',
        value: tv.is_rostered ? 'Yes' : 'No',
        accent: tv.is_rostered,
      });
    }

    // Contract details
    if (ledger) {
      if (ledger.current_salary > 0)
        pills.push({ label: 'Cap Hit', value: `$${ledger.current_salary.toFixed(1)}` });
      if (ledger.real_salary > 0 && ledger.real_salary !== ledger.current_salary)
        pills.push({ label: 'Real Salary', value: `$${ledger.real_salary.toFixed(1)}` });
      if (ledger.years_remaining > 0)
        pills.push({ label: 'Yrs Left', value: String(ledger.years_remaining) });
      if (ledger.contract_type_bucket)
        pills.push({ label: 'Contract', value: ledger.contract_type_bucket });
      if (ledger.extension_eligible)
        pills.push({ label: 'Ext Eligible', value: '✓', accent: true });
      if (ledger.tag_eligible)
        pills.push({ label: 'Tag Eligible', value: '✓', accent: true });
    }

    // This year's surplus (color-coded).  Prefer the windowed surplus_1yr
    // column; fall back to the legacy pv-based surplus_value if not present.
    if (surplus) {
      const sv = surplus.surplus_1yr ?? surplus.surplus_value;
      const color = sv > 20  ? '#98c379'   // strong positive
                  : sv > 0   ? '#61afef'   // positive
                  : sv > -10 ? '#d19a66'   // slightly negative
                  :             '#e06c75'; // deeply negative
      pills.push({ label: 'This Year\'s Surplus', value: `$${sv.toFixed(1)}`, color });
    }

    // This year's projected value
    if (tv && tv.tv_y0) {
      pills.push({ label: 'This Year\'s Value', value: `$${tv.tv_y0.toFixed(1)}` });
    }

    if (pills.length === 0) {
      strip.hidden = true;
      return;
    }

    strip.hidden = false;
    strip.innerHTML = pills.map(p => {
      const colorStyle = p.color ? ` style="color:${p.color};font-weight:600;"` : '';
      const accentClass = p.accent ? ' modal-pill--accent' : '';
      return `<span class="modal-pill${accentClass}">` +
        `<span class="modal-pill-label">${p.label}</span>` +
        `<span class="modal-pill-value"${colorStyle}>${p.value}</span>` +
        `</span>`;
    }).join('');
  }

  // ── Career timeline chart ─────────────────────────────────────────────────

  function buildCareerChart(playerName, careerRows, posColor) {
    if (careerChart) { careerChart.destroy(); careerChart = null; }

    // Forecast rows: TV Y0=2026, Y1=2027, Y2=2028, Y3=2029
    const tv = (typeof TV_DATA !== 'undefined' ? TV_DATA : []).find(r => r.player === playerName);
    const historicalSeasons = new Set(careerRows.map(r => r.season));

    const forecastYears = [
      { season: 2026, value: tv?.tv_y0 ?? null },
      { season: 2027, value: tv?.tv_y1 ?? null },
      { season: 2028, value: tv?.tv_y2 ?? null },
      { season: 2029, value: tv?.tv_y3 ?? null },
    ].filter(y => y.value !== null && y.value > 0 && !historicalSeasons.has(y.season));

    const histLen   = careerRows.length;
    const fcstLen   = forecastYears.length;
    const allLabels = [
      ...careerRows.map(r => String(r.season)),
      ...forecastYears.map(y => String(y.season)),
    ];

    // Dataset arrays: historical values then nulls for forecast slots (and vice versa)
    const histDvData  = [...careerRows.map(r => +r.dollar_value.toFixed(1)), ...Array(fcstLen).fill(null)];
    const fcstDvData  = [...Array(histLen).fill(null), ...forecastYears.map(y => +y.value.toFixed(1))];
    const esvData     = [...careerRows.map(r => +r.esv.toFixed(1)),          ...Array(fcstLen).fill(null)];
    const esvFcstData = tv && fcstLen > 0
      ? [...Array(histLen).fill(null), ...forecastYears.map(() => tv.esv_p50 != null ? +tv.esv_p50.toFixed(1) : null)]
      : [];

    const datasets = [
      // Historical bars (solid)
      {
        type: 'bar',
        label: 'Dollar Value',
        data: histDvData,
        backgroundColor: hexToRgba(posColor, 0.55),
        borderColor: posColor,
        borderWidth: 1,
        borderRadius: 3,
        yAxisID: 'y',
      },
      // Historical ESV line
      {
        type: 'line',
        label: 'ESV',
        data: esvData,
        borderColor: THEME.accent,
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: THEME.accent,
        tension: 0.3,
        spanGaps: false,
        yAxisID: 'y',
      },
    ];

    // Forecast bars (dashed outline, light fill) — only if data exists
    if (fcstLen > 0) {
      datasets.push({
        type: 'bar',
        label: 'TV Forecast',
        data: fcstDvData,
        backgroundColor: hexToRgba(posColor, 0.18),
        borderColor: posColor,
        borderWidth: 1.5,
        borderDash: [4, 3],
        borderRadius: 3,
        yAxisID: 'y',
      });
    }

    // Forecast ESV p50 dotted line — only if data exists
    if (esvFcstData.length > 0 && esvFcstData.some(v => v !== null)) {
      datasets.push({
        type: 'line',
        label: 'ESV p50 (fcst)',
        data: esvFcstData,
        borderColor: THEME.accent,
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        borderDash: [4, 3],
        pointRadius: 2,
        pointBackgroundColor: THEME.accent,
        tension: 0.3,
        spanGaps: false,
        yAxisID: 'y',
      });
    }

    const careerCtx = document.getElementById('chart-modal-career').getContext('2d');
    careerChart = new Chart(careerCtx, {
      data: { labels: allLabels, datasets },
      options: {
        ...CHART_DEFAULTS,
        onClick: (evt, elements) => {
          if (!elements.length) return;
          const idx = elements[0].index;
          const clickedSeason = parseInt(allLabels[idx], 10);
          if (historicalSeasons.has(clickedSeason)) {
            loadWeeklyChart(playerName, clickedSeason, posColor);
          }
        },
        onHover: (evt, elements) => {
          const canvas = evt.native?.target;
          if (!canvas) return;
          const overHistorical = elements.length > 0 &&
            historicalSeasons.has(parseInt(allLabels[elements[0].index], 10));
          canvas.style.cursor = overHistorical ? 'pointer' : 'default';
        },
        plugins: {
          ...CHART_DEFAULTS.plugins,
          legend: {
            ...CHART_DEFAULTS.plugins.legend,
            display: true,
          },
          tooltip: {
            ...CHART_DEFAULTS.plugins.tooltip,
            callbacks: {
              label: ctx => {
                const label = ctx.dataset.label;
                const idx   = ctx.dataIndex;
                if (label === 'Dollar Value') {
                  const r = careerRows[idx];
                  if (!r) return ctx.formattedValue;
                  return ` ${fmtDollar(r.dollar_value)}  (SAV ${r.sav.toFixed(1)}, Rank #${r.pos_rank ?? '–'})`;
                }
                if (label === 'ESV') {
                  const r = careerRows[idx];
                  if (!r) return null;
                  return ` ESV ${r.esv.toFixed(1)}  pts ${r.total_points.toFixed(0)}`;
                }
                if (label === 'TV Forecast') {
                  const fy = forecastYears[idx - histLen];
                  return fy ? ` TV ${fmtDollar(fy.value)}` : ctx.formattedValue;
                }
                if (label === 'ESV p50 (fcst)') {
                  return ` ESV forecast median ${ctx.formattedValue}`;
                }
                return ctx.formattedValue;
              }
            }
          }
        },
        scales: {
          x: { ...CHART_DEFAULTS.scales.x },
          y: {
            ...CHART_DEFAULTS.scales.y,
            title: {
              display: true,
              text: '$ Value / ESV',
              color: THEME.muted,
              font: { size: 11 }
            }
          }
        }
      }
    });
  }

  // ── Weekly breakdown chart ────────────────────────────────────────────────

  function loadWeeklyChart(playerName, season, posColor) {
    const weeklyRows = (typeof WEEKLY_DATA !== 'undefined' ? WEEKLY_DATA : [])
      .filter(r => r.player === playerName && r.season === season)
      .sort((a, b) => a.week - b.week);

    // Update section title
    const title = document.getElementById('modal-weekly-title');
    if (title) title.textContent = `${season} Season — Weekly Breakdown`;

    if (weeklyChart) { weeklyChart.destroy(); weeklyChart = null; }

    const noDataNotice = document.getElementById('modal-weekly-no-data');

    if (!weeklyRows.length) {
      if (noDataNotice) noDataNotice.hidden = false;
      return;
    }
    if (noDataNotice) noDataNotice.hidden = true;

    _weeklyActiveSeason = season;

    const weeklyCtx = document.getElementById('chart-modal-weekly').getContext('2d');
    weeklyChart = new Chart(weeklyCtx, {
      data: {
        labels: weeklyRows.map(r => `Wk ${r.week}`),
        datasets: [
          {
            type: 'bar',
            label: 'Points',
            data: weeklyRows.map(r => +r.points.toFixed(1)),
            backgroundColor: hexToRgba(posColor, 0.5),
            borderColor: posColor,
            borderWidth: 1,
            borderRadius: 2,
            yAxisID: 'yPts',
          },
          {
            type: 'line',
            label: 'Start%',
            data: weeklyRows.map(r => +(r.start_prob * 100).toFixed(1)),
            borderColor: THEME.muted,
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            borderDash: [4, 3],
            pointRadius: 2,
            pointBackgroundColor: THEME.muted,
            tension: 0.3,
            yAxisID: 'yPct',
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
              label: ctx => {
                const r = weeklyRows[ctx.dataIndex];
                if (!r) return ctx.formattedValue;
                if (ctx.dataset.label === 'Points') {
                  return ` ${r.points.toFixed(1)} pts  (ESV ${r.esv_week.toFixed(1)}, WMSV ${r.wmsv.toFixed(1)})`;
                }
                return ` Start ${(r.start_prob * 100).toFixed(0)}%`;
              }
            }
          }
        },
        scales: {
          x: { ...CHART_DEFAULTS.scales.x },
          yPts: {
            ...CHART_DEFAULTS.scales.y,
            position: 'left',
            title: { display: true, text: 'Points', color: THEME.muted, font: { size: 11 } },
          },
          yPct: {
            ...CHART_DEFAULTS.scales.y,
            position: 'right',
            min: 0, max: 100,
            title: { display: true, text: 'Start %', color: THEME.muted, font: { size: 11 } },
            grid: { drawOnChartArea: false },
          }
        }
      }
    });
  }

  // ── Comparables table ─────────────────────────────────────────────────────

  function renderComparables(playerName) {
    const tbody = document.getElementById('modal-comp-tbody');
    if (!tbody) return;

    const tvAll      = typeof TV_DATA      !== 'undefined' ? TV_DATA      : [];
    const surplusAll = typeof SURPLUS_DATA !== 'undefined' ? SURPLUS_DATA : [];
    const ledgerAll  = typeof LEDGER_DATA  !== 'undefined' ? LEDGER_DATA  : [];

    if (!tvAll.length) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:20px;">Forecast data not available.</td></tr>';
      return;
    }

    const rows = _buildComparableWindow(playerName, tvAll, surplusAll, ledgerAll);

    // Update metric column header
    const hdr = document.getElementById('modal-comp-metric-header');
    if (hdr) {
      hdr.textContent = _compMetric === 'tv_y0'   ? 'This Year\'s Value'
                      : _compMetric === 'tv_sum'   ? 'Total 4-Yr Value'
                      :                              'This Year\'s Surplus';
    }

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:20px;">Comparable players are not available for this ranking window.</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(({ r, val, sur, led, isFocal }) => {
      const rowClass   = isFocal ? ' class="modal-comp-row-anchor"' : '';
      // Prefer windowed surplus_1yr; fall back to legacy surplus_value.
      const surplusVal = sur ? (sur.surplus_1yr ?? sur.surplus_value ?? null) : null;
      const capToday   = led?.current_salary ?? null;

      const surpColor = surplusVal !== null
        ? (surplusVal > 20  ? '#98c379'
          : surplusVal > 0  ? '#61afef'
          : surplusVal > -10 ? '#d19a66'
          :                    '#e06c75')
        : 'inherit';

      const posClass = r.position ? ` pos-${r.position.toLowerCase()}` : '';
      const nameCell = isFocal
        ? `<strong>${playerLink(r.player)}</strong>`
        : playerLink(r.player);

      return `<tr${rowClass}>` +
        `<td>${nameCell}</td>` +
        `<td>${r.team || '–'}</td>` +
        `<td><span class="pos-badge${posClass}">${r.position}</span></td>` +
        `<td class="num">${fmt1(val)}</td>` +
        `<td class="num">${fmt1(r.tv_y1)}</td>` +
        `<td class="num">${fmt1(r.tv_y2)}</td>` +
        `<td class="num">${fmt1(r.tv_y3)}</td>` +
        `<td class="num" style="color:${surpColor};">${fmt1(surplusVal)}</td>` +
        `<td class="num">${fmt1(capToday)}</td>` +
        `</tr>`;
    }).join('');
  }

  // ── Main open function ────────────────────────────────────────────────────

  function openPlayerModal(playerName) {
    const overlay = document.getElementById('player-modal');
    if (!overlay) return;

    _currentPlayer = playerName;

    // ── Bio / headshot ────────────────────────────────────────────────────
    const bio = HEADSHOT_MAP[playerName] || {};
    const img = document.getElementById('modal-headshot');

    if (bio.headshot_url) {
      img.src = bio.headshot_url;
      img.alt = playerName;
      img.hidden = false;
    } else {
      img.src = '';
      img.alt = '';
      img.hidden = true;
    }

    document.getElementById('modal-name').textContent = playerName;

    const age       = calcAge(bio.birth_date);
    const heightStr = fmtHeight(bio.height);
    const draftStr  = bio.draft_year
      ? `${bio.draft_year} Rd ${bio.draft_round}, Pick ${bio.draft_pick}`
      : null;

    const bioLines = [
      bio.position || null,
      (age ? `Age ${age}` : null),
      (heightStr && bio.weight ? `${heightStr} / ${bio.weight} lbs` : null),
      bio.college_name || null,
      draftStr,
    ].filter(Boolean);

    document.getElementById('modal-bio-details').innerHTML =
      bioLines.map(l => `<span>${l}</span>`).join('<span class="bio-sep">·</span>');

    // ── Contract / roster strip ───────────────────────────────────────────
    buildContractStrip(playerName);

    // ── Career timeline ───────────────────────────────────────────────────
    const careerRows = SEASON_DATA
      .filter(r => r.player === playerName)
      .sort((a, b) => a.season - b.season);

    const position = careerRows[0]?.position || bio.position || 'WR';
    const posColor = POS_COLORS[position] || THEME.accent;

    buildCareerChart(playerName, careerRows, posColor);

    // ── Weekly breakdown (latest historical season by default) ────────────
    const latestSeason = careerRows.length ? careerRows[careerRows.length - 1].season : null;
    if (latestSeason) {
      loadWeeklyChart(playerName, latestSeason, posColor);
    }

    // ── No historical data notice ─────────────────────────────────────────
    const tv = (typeof TV_DATA !== 'undefined' ? TV_DATA : []).find(r => r.player === playerName);
    const hasForecast = tv && (tv.tv_y0 > 0 || tv.tv_y1 > 0);
    const noDataNotice = document.getElementById('modal-no-data');
    if (noDataNotice) {
      noDataNotice.hidden = careerRows.length > 0 || hasForecast;
    }

    // ── Reset to Profile tab; reset comparables controls ──────────────────
    _switchModalTab('profile', /* skipRender= */ true);

    const metricSel = document.getElementById('modal-comp-metric');
    if (metricSel) metricSel.value = _compMetric;
    const samePosCb = document.getElementById('modal-comp-same-pos');
    if (samePosCb) samePosCb.checked = _compSamePos;

    overlay.hidden = false;
    const card = overlay.querySelector('.modal-card');
    if (card) card.scrollTop = 0;
  }

  // ── Wire up event listeners after DOM ready ───────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    // Delegated click on any .player-link anywhere in the document
    document.addEventListener('click', e => {
      const link = e.target.closest('.player-link');
      if (link) openPlayerModal(link.dataset.player);
    });

    // Close button
    const closeBtn = document.getElementById('modal-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', closeModal);

    // Click outside the modal card
    const overlay = document.getElementById('player-modal');
    if (overlay) {
      overlay.addEventListener('click', e => {
        if (e.target === overlay) closeModal();
      });
    }

    // Escape key
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeModal();
    });

    // Modal tab buttons
    document.querySelectorAll('.modal-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => _switchModalTab(btn.dataset.modaltab));
    });

    // Comparables: metric dropdown
    const compMetricSel = document.getElementById('modal-comp-metric');
    if (compMetricSel) {
      compMetricSel.addEventListener('change', () => {
        _compMetric = compMetricSel.value;
        if (_currentPlayer && _activeModalTab === 'comparables') {
          renderComparables(_currentPlayer);
        }
      });
    }

    // Comparables: same-position checkbox
    const compSamePosCb = document.getElementById('modal-comp-same-pos');
    if (compSamePosCb) {
      compSamePosCb.addEventListener('change', () => {
        _compSamePos = compSamePosCb.checked;
        if (_currentPlayer && _activeModalTab === 'comparables') {
          renderComparables(_currentPlayer);
        }
      });
    }
  });

  // Expose for external callers (e.g. table row clicks in view-league.js)
  window.openPlayerModal = openPlayerModal;
})();
