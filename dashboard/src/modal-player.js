// Player modal — opens when any .player-link is clicked.
// Shows headshot, bio, career timeline chart, and latest-season weekly chart.

(function () {
  // ── Chart instance refs ───────────────────────────────────────────────────
  let careerChart  = null;
  let weeklyChart  = null;

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

  // ── Modal open/close ──────────────────────────────────────────────────────

  function closeModal() {
    const overlay = document.getElementById('player-modal');
    if (overlay) overlay.hidden = true;
    if (careerChart)  { careerChart.destroy();  careerChart  = null; }
    if (weeklyChart)  { weeklyChart.destroy();   weeklyChart  = null; }
  }

  function openPlayerModal(playerName) {
    const overlay = document.getElementById('player-modal');
    if (!overlay) return;

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

    const age        = calcAge(bio.birth_date);
    const heightStr  = fmtHeight(bio.height);
    const draftStr   = bio.draft_year
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

    // ── Career timeline chart ─────────────────────────────────────────────
    const careerRows = SEASON_DATA
      .filter(r => r.player === playerName)
      .sort((a, b) => a.season - b.season);

    if (careerChart) { careerChart.destroy(); careerChart = null; }

    const careerCtx = document.getElementById('chart-modal-career').getContext('2d');
    const position  = (careerRows[0]?.position) || (bio.position) || 'WR';
    const posColor  = POS_COLORS[position] || THEME.accent;

    careerChart = new Chart(careerCtx, {
      data: {
        labels: careerRows.map(r => String(r.season)),
        datasets: [
          {
            type: 'bar',
            label: 'Dollar Value',
            data: careerRows.map(r => +r.dollar_value.toFixed(1)),
            backgroundColor: hexToRgba(posColor, 0.55),
            borderColor: posColor,
            borderWidth: 1,
            borderRadius: 3,
            yAxisID: 'y',
          },
          {
            type: 'line',
            label: 'ESV',
            data: careerRows.map(r => +r.esv.toFixed(1)),
            borderColor: THEME.accent,
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: THEME.accent,
            tension: 0.3,
            yAxisID: 'y',
          },
        ]
      },
      options: {
        ...CHART_DEFAULTS,
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
                const r = careerRows[ctx.dataIndex];
                if (!r) return ctx.formattedValue;
                if (ctx.dataset.label === 'Dollar Value') {
                  return ` ${fmtDollar(r.dollar_value)}  (SAV ${r.sav.toFixed(1)}, Rank #${r.pos_rank ?? '–'})`;
                }
                return ` ESV ${r.esv.toFixed(1)}  pts ${r.total_points.toFixed(0)}`;
              }
            }
          }
        },
        scales: {
          x: { ...CHART_DEFAULTS.scales.x },
          y: {
            ...CHART_DEFAULTS.scales.y,
            title: { display: true, text: '$ Value / ESV', color: THEME.muted, font: { size: 11 } }
          }
        }
      }
    });

    // ── Latest season weekly chart ────────────────────────────────────────
    const latestSeason = careerRows.length ? careerRows[careerRows.length - 1].season : null;

    const weeklyRows = latestSeason
      ? WEEKLY_DATA
          .filter(r => r.player === playerName && r.season === latestSeason)
          .sort((a, b) => a.week - b.week)
      : [];

    // Update the section title to show the season
    const weeklyTitle = document.getElementById('modal-weekly-title');
    if (weeklyTitle) {
      weeklyTitle.textContent = latestSeason
        ? `${latestSeason} Season — Weekly Breakdown`
        : 'Latest Season — Weekly Breakdown';
    }

    if (weeklyChart) { weeklyChart.destroy(); weeklyChart = null; }

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

    // No data notice
    const noDataNotice = document.getElementById('modal-no-data');
    if (noDataNotice) {
      noDataNotice.hidden = careerRows.length > 0;
    }

    overlay.hidden = false;
    // Scroll modal card to top on reopen
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
  });

  // Expose for external callers (e.g. table row clicks in view-league.js)
  window.openPlayerModal = openPlayerModal;
})();
